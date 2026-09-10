"""Polite HTTP session for ufcstats.com.

The site now fronts every page with a proof-of-work interstitial: instead of the
page it serves a small script carrying a ``nonce`` and a difficulty, and expects
the client to find an ``n`` such that ``sha256(f"{nonce}:{n}")`` begins with that
many zeros, POST the pair back to ``/__c``, and retry with the cookie it sets.

:func:`get` pays that cost inline rather than working around it, then reuses the
resulting cookie for the rest of the session so the work is done once. The check
exists to make bulk scraping expensive, so keep ``REQUEST_DELAY_SECONDS`` in
place and keep batches small.
"""

import hashlib
import re
import time

import requests

CHALLENGE_MARKER = "Checking your browser"
CHALLENGE_ENDPOINT = "http://ufcstats.com/__c"
# A healthy page answers in well under a second, so 25s only ever bought a long
# hang: three attempts plus backoff could cost ~82s on a single bad page, which
# is what turned one slow stretch of a backfill into hours. Fail fast instead.
REQUEST_TIMEOUT = 10
REQUEST_DELAY_SECONDS = 1
MAX_ATTEMPTS = 3
USER_AGENT = "ufcStats-portfolio-etl/0.1 (+https://github.com/Jddeleon1981/ufcStats)"

_NONCE_RE = re.compile(r'var nonce="([0-9a-f]+)"')
_DIFFICULTY_RE = re.compile(r"target=new Array\((\d+)\+1\)")


def is_challenge(html: str) -> bool:
    """True when the response is the interstitial rather than the real page."""
    return CHALLENGE_MARKER in html


def solve_challenge(html: str) -> tuple[str, int]:
    """Read the nonce and difficulty off an interstitial and do its work.

    Returns the ``(nonce, n)`` pair the server expects back. Difficulty is two
    hex zeros in practice, so this lands in a few hundred hashes.
    """
    nonce_match = _NONCE_RE.search(html)
    difficulty_match = _DIFFICULTY_RE.search(html)
    if not nonce_match or not difficulty_match:
        raise ValueError(
            "challenge page carried no nonce/difficulty — its format changed"
        )

    nonce = nonce_match.group(1)
    prefix = "0" * int(difficulty_match.group(1))
    n = 0
    while not hashlib.sha256(f"{nonce}:{n}".encode()).hexdigest().startswith(prefix):
        n += 1
    return nonce, n


def build_session(user_agent: str = USER_AGENT) -> requests.Session:
    """A session that identifies itself and carries the challenge cookie."""
    session = requests.Session()
    session.headers["User-Agent"] = user_agent
    return session


def get(
    session: requests.Session,
    url: str,
    delay: float = REQUEST_DELAY_SECONDS,
    attempts: int = MAX_ATTEMPTS,
) -> requests.Response:
    """GET a page, clearing the proof-of-work interstitial if one is served.

    Retries with backoff on transport errors so a long backfill isn't lost to a
    single dropped connection.
    """
    last_error = None
    for attempt in range(attempts):
        if delay:
            time.sleep(delay)
        try:
            response = session.get(url, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
        except requests.RequestException as error:
            last_error = error
            time.sleep(2**attempt)
            continue

        if not is_challenge(response.text):
            return response

        # solve it, post the answer, and let the next pass fetch the real page
        nonce, n = solve_challenge(response.text)
        session.post(
            CHALLENGE_ENDPOINT,
            data={"nonce": nonce, "n": n},
            timeout=REQUEST_TIMEOUT,
        )

    if last_error is not None:
        raise last_error
    raise RuntimeError(f"could not clear the proof-of-work challenge for {url}")
