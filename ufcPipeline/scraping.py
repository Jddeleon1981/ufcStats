"""Pure HTML parsers for ufcstats.com.

Every function here takes HTML and returns structured data, so it can be
unit-tested against the fixtures in ``tests/fixtures`` without touching the
network. Fetching lives in :mod:`ufcPipeline.session`; turning parsed pages
into raw records lives in :mod:`ufcPipeline.extract`.
"""

from bs4 import BeautifulSoup

EVENTS_URL = "http://ufcstats.com/statistics/events/completed?page=all"


def add_www_to_links(links: list[str]) -> list[str]:
    """Insert ``www.`` into bare ufcstats links so requests can resolve them."""
    return [link.replace("http://", "http://www.") for link in links]


# Pure parsers
def parse_fighter_links(html) -> list[tuple[str, str, str]]:
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


def parse_events(html) -> list[tuple[str, str, str, str]]:
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


def parse_event_fights(html) -> list[tuple[str, str, str]]:
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
    # strict=True: these three lists are appended under different conditions, so a
    # divergence means the rows no longer line up. Zipping short would not just
    # drop bouts, it would pair a bout with the next one's winner -- silent
    # corruption. Raise instead and let the caller's error handler record it.
    return list(zip(winners, weight_classes, fight_links, strict=True))


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
        [
            link["href"]
            for link in table.find_all("a", class_="b-link b-link_style_black")
        ]
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
