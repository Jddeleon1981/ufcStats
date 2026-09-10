"""Unit tests for the pure HTML parsers in ufcPipeline.scraping.

These run against saved HTML fixtures, so they need no network access and pin
down the parsing contract the pipeline depends on.
"""
from pathlib import Path

from ufcPipeline.scraping import (
    add_www_to_links,
    parse_bout,
    parse_event_fights,
    parse_events,
    parse_fighter_links,
    parse_fighter_stats,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_parse_fighter_links_extracts_name_and_url():
    fighters = parse_fighter_links(_fixture("fighterList.html"))
    assert fighters == [
        ("Israel", "Adesanya", "http://ufcstats.com/fighter-details/abc123"),
        ("Jon", "Jones", "http://ufcstats.com/fighter-details/def456"),
    ]


def test_parse_fighter_stats_maps_titles_to_values():
    stats = parse_fighter_stats(
        _fixture("fighterStats.html"),
        "Israel",
        "Adesanya",
        "http://ufcstats.com/fighter-details/abc123",
    )
    assert stats["First Name"] == "Israel"
    assert stats["Last Name"] == "Adesanya"
    assert stats["URL"] == "http://ufcstats.com/fighter-details/abc123"
    assert stats["Height"] == "6' 4\""
    assert stats["Weight"] == "185 lbs."
    assert stats["STANCE"] == "Switch"


def test_parse_fighter_stats_keeps_empty_spacer_key():
    # the page has a blank list item that yields an empty-string key; downstream
    # code explicitly drops it, so this guards that the quirk still exists.
    stats = parse_fighter_stats(_fixture("fighterStats.html"), "Israel", "Adesanya", "url")
    assert "" in stats


def test_parse_events_extracts_rows_and_keeps_apostrophes():
    events = parse_events(_fixture("events.html"))
    assert len(events) == 2
    assert events[0] == (
        "UFC 300: Pereira vs Hill",
        "April 13, 2024",
        "Las Vegas, Nevada, USA",
        "http://ufcstats.com/event-details/aaa111",
    )
    # an apostrophe in the name must survive parsing intact
    assert events[1][0] == "UFC 299: O'Malley vs Vera 2"


def test_add_www_to_links_inserts_subdomain():
    assert add_www_to_links(["http://ufcstats.com/x"]) == ["http://www.ufcstats.com/x"]


def test_parse_event_fights_pairs_winner_weightclass_and_link():
    fights = parse_event_fights(_fixture("eventPage.html"))
    assert fights == [
        ("Israel Adesanya", "Middleweight", "http://ufcstats.com/fight-details/fight111"),
        # a no contest has no winner, so the flag text stands in for one
        ("nc", "Light Heavyweight", "http://ufcstats.com/fight-details/fight222"),
    ]


def test_parse_bout_returns_totals_in_page_order():
    bout = parse_bout(_fixture("fightPage.html"))
    assert bout["totals"][:2] == ["Israel Adesanya", "Jon Jones"]
    assert len(bout["totals"]) == 20
    # values stay exactly as rendered — parsing them is a staging concern
    assert bout["totals"][4] == "14 of 31"
    assert bout["totals"][12] == "---"
    assert bout["totals"][19] == "1:06"


def test_parse_bout_extracts_outcome_and_fighter_urls():
    bout = parse_bout(_fixture("fightPage.html"))
    assert bout["method"] == "KO/TKO"
    assert bout["finish_round"] == "1"
    assert bout["finish_time"] == "2:35"
    assert bout["fighter_urls"] == [
        "http://www.ufcstats.com/fighter-details/abc123",
        "http://www.ufcstats.com/fighter-details/def456",
    ]


def test_parse_bout_returns_empty_when_no_totals_table():
    # older cards have no box score; callers skip these rather than fail
    assert parse_bout("<html><body><p>no tables here</p></body></html>") == {}
