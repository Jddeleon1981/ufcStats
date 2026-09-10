"""Unit tests for the proof-of-work handling in ufcPipeline.session.

The challenge solver is pure — it takes the interstitial HTML and returns the
answer — so it is testable against a fixture without touching the network.
"""
import hashlib
from pathlib import Path

import pytest

from ufcPipeline.session import is_challenge, solve_challenge

FIXTURES = Path(__file__).parent / "fixtures"


def _fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_is_challenge_distinguishes_interstitial_from_content():
    assert is_challenge(_fixture("challenge.html"))
    assert not is_challenge(_fixture("events.html"))


def test_solve_challenge_returns_a_nonce_meeting_the_difficulty():
    nonce, n = solve_challenge(_fixture("challenge.html"))
    assert nonce == "c601bd1881782273"
    digest = hashlib.sha256(f"{nonce}:{n}".encode()).hexdigest()
    # the fixture asks for two leading zeros
    assert digest.startswith("00")


def test_solve_challenge_finds_the_first_answer():
    _, n = solve_challenge(_fixture("challenge.html"))
    for lower in range(n):
        digest = hashlib.sha256(f"c601bd1881782273:{lower}".encode()).hexdigest()
        assert not digest.startswith("00")


def test_solve_challenge_rejects_a_page_it_cannot_read():
    with pytest.raises(ValueError):
        solve_challenge("<html><body>no nonce here</body></html>")
