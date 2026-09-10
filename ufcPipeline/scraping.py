"""Scraping and parsing helpers for ufcstats.com.

The ``parse_*`` functions are pure: they take HTML and return structured data, so
they can be unit-tested against fixtures without touching the network. The
``*_grabber`` / ``scrape_*`` functions wrap them with the actual HTTP requests.
"""
import time
from typing import List, Tuple

import requests
from bs4 import BeautifulSoup

REQUEST_TIMEOUT = 25
REQUEST_DELAY_SECONDS = 1
FIGHTERS_URL = "http://www.ufcstats.com/statistics/fighters?char={letter}&page=all"
EVENTS_URL = "http://ufcstats.com/statistics/events/completed?page=all"


def add_www_to_links(links: List[str]) -> List[str]:
    """Insert ``www.`` into bare ufcstats links so requests can resolve them."""
    return [link.replace("http://", "http://www.") for link in links]


# ---------------------------------------------------------------------------
# Pure parsers (unit-tested against fixtures in tests/)
# ---------------------------------------------------------------------------
def parse_fighter_links(html) -> List[Tuple[str, str, str]]:
    """Parse the paginated fighter table into (first, last, url) tuples."""
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find_all("table")[0]
    fighters = []
    for row in table.find_all("tr"):
        cells = row.find_all("td")
        if len(cells) >= 2:
            first_link = cells[0].find("a")
            last_link = cells[1].find("a")
            fighters.append((first_link.text, last_link.text, first_link.get("href")))
    return fighters


def parse_fighter_stats(html, first_name, last_name, url) -> dict:
    """Parse a fighter's detail page into a {stat title: value} dict."""
    soup = BeautifulSoup(html, "html.parser")
    list_items = soup.find_all(
        "li", class_="b-list__box-list-item b-list__box-list-item_type_block"
    )
    stats = {"First Name": first_name, "Last Name": last_name, "URL": url}
    for item in list_items:
        # remove the trailing colon from the title and strip it back out of the value
        title = item.find("i").get_text(strip=True).rstrip(":")
        value = item.get_text(strip=True).replace(title + ":", "")
        stats[title] = value
    return stats


def parse_events(html) -> List[Tuple[str, str, str, str]]:
    """Parse the completed-events table into (name, date, location, url) tuples."""
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", {"class": "b-statistics__table-events"})
    events = []
    for row in table.find_all("tr"):
        cols = row.find_all("td")
        if len(cols) >= 2:
            # the name and date share a cell separated by a newline
            parts = [part.strip() for part in cols[0].text.split("\n") if part.strip()]
            event_name = parts[0]
            event_date = parts[1]
            event_link = cols[0].find("a")["href"]
            event_location = cols[1].text.strip()
            events.append((event_name, event_date, event_location, event_link))
    return events


def parse_fighter_name(html) -> str:
    """Pull a fighter's display name off their detail page."""
    soup = BeautifulSoup(html, "html.parser")
    title = soup.find("span", class_="b-content__title-highlight")
    return title.get_text(strip=True) if title else ""


def parse_event_fights(html) -> List[Tuple[str, str, str]]:
    """Parse one event page into (winner, weight class, fight url) per bout."""
    soup = BeautifulSoup(html, "html.parser")

    # the main fights table lists every bout on the card
    tables = soup.find_all("table")
    if not tables:
        return []
    rows = tables[0].find_all("tr")

    # collected in parallel lists and zipped, because a row can contribute to
    # one list without contributing to the others
    fight_links = []
    winners = []
    weight_classes = []
    for row in rows:

        # rows carry the individual fight page as an onclick handler
        onclick = row.get("onclick")
        if onclick:
            fight_links.append(onclick)

        # find the winner, accounting for no-contest results
        winner_tag = row.find("a", class_="b-link b-link_style_black")
        header_tag = row.find("th")
        nc_tag = row.find("i", class_="b-flag__text")
        no_contest_tag_text = nc_tag.text.strip() if nc_tag else None
        if winner_tag and not header_tag:
            if no_contest_tag_text == "nc":
                winners.append(no_contest_tag_text)
            else:
                winners.append(winner_tag.get_text().strip())

        # the weight class is the 2nd left-aligned column
        weight_class_tags = row.find_all(
            "td", class_="b-fight-details__table-col l-page_align_left"
        )
        if weight_class_tags and len(weight_class_tags) > 1:
            weight_class_text = (
                weight_class_tags[1]
                .find("p", class_="b-fight-details__table-text")
                .get_text()
                .strip()
            )
            weight_classes.append(weight_class_text)

    fight_links = [fight.split("'")[1] for fight in fight_links]
    return list(zip(winners, weight_classes, fight_links))


def parse_bout(html) -> dict:
    """Parse one fight page into its 'Totals' box-score plus the outcome.

    Returns ``{}`` when the page carries no totals table, which happens for
    older cards. ``totals`` is the table's 20 cells in page order (both fighter
    names, then each stat as an A/B pair) left exactly as the site renders
    them — ``"14 of 31"``, ``"---"``, ``"0:02"``. Casting is a staging concern.
    """
    soup = BeautifulSoup(html, "html.parser")

    tables = soup.find_all("table")
    if not tables:
        return {}
    table = tables[0]

    totals = [
        p.get_text(strip=True)
        for p in table.find_all("p", class_="b-fight-details__table-text")
    ]
    fighter_urls = add_www_to_links(
        [link["href"] for link in table.find_all("a", class_="b-link b-link_style_black")]
    )

    # method, round, and time live in the summary paragraph below the table
    text_content = soup.find("p", class_="b-fight-details__text")
    method_tag = text_content.find("i", class_="b-fight-details__text-item_first")
    method = method_tag.find("i", style="font-style: normal").get_text(strip=True)
    finish_round = method_tag.find_next_sibling("i").get_text(strip=True).split(":")[1]

    time_tag = text_content.find("i", class_="b-fight-details__text-item")
    finish_time = time_tag.find_next_sibling("i").get_text(strip=True).split(":", 1)[1]

    return {
        "totals": totals,
        "fighter_urls": fighter_urls,
        "method": method,
        "finish_round": finish_round,
        "finish_time": finish_time,
    }


# ---------------------------------------------------------------------------
# Network-backed scrapers
# ---------------------------------------------------------------------------
def hyperlink_grabber(last_name_letter: str) -> List[Tuple[str, str, str]]:
    """Fetch and parse every fighter link for one last-name letter."""
    time.sleep(REQUEST_DELAY_SECONDS)
    response = requests.get(
        FIGHTERS_URL.format(letter=last_name_letter), timeout=REQUEST_TIMEOUT
    )
    return parse_fighter_links(response.content)


def fighter_stat_grabber(fighter: Tuple[str, str, str]) -> dict:
    """Fetch a fighter's detail page and parse their personal stats."""
    time.sleep(REQUEST_DELAY_SECONDS)
    first_name, last_name, url = fighter
    response = requests.get(url, timeout=REQUEST_TIMEOUT)
    return parse_fighter_stats(response.content, first_name, last_name, url)


def ufc_event_grabber() -> List[Tuple[str, str, str, str]]:
    """Fetch and parse every completed UFC event (used by the bulk load)."""
    time.sleep(REQUEST_DELAY_SECONDS)
    response = requests.get(EVENTS_URL, timeout=REQUEST_TIMEOUT)
    return parse_events(response.text)


def scrape_fighter_data(url):
    """Scrape (fighter name, url) pairs from a single event's fight table."""
    response = requests.get(url, timeout=REQUEST_TIMEOUT)
    soup = BeautifulSoup(response.content, "html.parser")

    # grab the main fights table, which lists every fight at this event
    tables = soup.find_all("table")
    if not tables:
        return [f"This  didnt have a table to grab. This was the link {url}"]
    table = tables[0]
    rows = table.find_all("tr")

    fight_links = []
    for row in rows:
        # the fighter names live in the first left-aligned column of each row
        fighter_row_tags = row.find_all(
            "td", class_="b-fight-details__table-col l-page_align_left"
        )
        if fighter_row_tags and len(fighter_row_tags) > 1:
            fighter_name_tag = fighter_row_tags[0]
            fighter_name_text = fighter_name_tag.find_all(
                "p", class_="b-fight-details__table-text"
            )
            for tag in fighter_name_text:
                a_tag = tag.find("a")
                fighter_name = a_tag.text.strip()
                fighter_url = a_tag["href"]
                fight_links.append((fighter_name, fighter_url))
    return fight_links


def fighter_id_grabber(link, cursor):
    """Look up a fighter's primary key (fighterID) by their detail-page URL."""
    # NOTE: still string-formatted; parameterizing this is the separate SQL-safety task.
    query = f"""
    select fighterID
    FROM fighterHyperlinks
    where hyperlink = '{link}'
    """
    cursor.execute(query)
    result = cursor.fetchall()
    return result[0][0]


def fight_stat_grabber_a(event):
    """Scrape every fight (winner, weight class, link, eventID) at one event.

    Split from the original single grabber because the combined version was too
    heavy and dropped rows mid-run. Part A walks an event page and returns one
    tuple per fight on the card.
    """
    time.sleep(REQUEST_DELAY_SECONDS)
    event_id = event[0]
    event_name = event[1]
    event_url = event[4]
    response = requests.get(event_url, timeout=REQUEST_TIMEOUT)

    fights = parse_event_fights(response.content)
    if not fights:
        return [f"This {event_name} didnt have a table to grab. This was the link {event_url}"]

    # pair the eventID with each fight's winner and link
    return [
        (winner, weight_class, link, event_id) for winner, weight_class, link in fights
    ]


def fight_stat_grabber_b(event_stats):
    """Scrape the per-fight 'Totals' box-score for one fight.

    Part B acts on each tuple produced by :func:`fight_stat_grabber_a`
    (winner, weight class, fight link, eventID) and returns the full stat row,
    with each fighter's URL resolved back to their fighterID.
    """
    # imported lazily so the pure parsers above can be used without boto3/mysql
    from ufcPipeline.db import connect  # pylint: disable=import-outside-toplevel

    cnx = connect()
    cursor = cnx.cursor()

    print(
        f"started fightStats for {event_stats[0]} at event with eventID:{event_stats[3]}"
    )
    time.sleep(REQUEST_DELAY_SECONDS)
    fight_link = event_stats[2]
    response = requests.get(fight_link, timeout=REQUEST_TIMEOUT)
    bout = parse_bout(response.content)

    if not bout:
        cursor.close()
        cnx.close()
        return []

    current_fight = list(bout["totals"])
    current_fight.extend(
        fighter_id_grabber(hyperlink, cursor) for hyperlink in bout["fighter_urls"]
    )
    current_fight.extend(list(event_stats))
    current_fight.extend([bout["method"], bout["finish_time"], bout["finish_round"]])

    cursor.close()
    cnx.close()
    return [current_fight]
