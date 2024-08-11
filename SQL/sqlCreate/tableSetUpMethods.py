"""Helper file that contains methods that we will be using to scrape the ufc stats website."""

import json
import time
import boto3
import mysql.connector
import requests
from botocore.exceptions import ClientError
from bs4 import BeautifulSoup

def get_secret():
    """
    Using AWS secret manager retrieve the db credentials for our mysql ufc db
    """
    secret_name = "ufcDBcred"
    region_name = "us-west-1"

    # create client
    session = boto3.session.Session()
    client = session.client(service_name="secretsmanager", region_name=region_name)
    try:
        get_secret_value_response = client.get_secret_value(SecretId=secret_name)
    except ClientError as e:
        raise e

    # format as dict before returning
    secret = get_secret_value_response["SecretString"]
    return json.loads(secret)

def fighter_id_grabber(link, cursor):  
    """
    We use this method to query the fighterHyperLinks table and grab the fighterID for the fighter we're currently working with so that we can add it to its corresponding row when building the fighter_stats table

    PARAMETER
    link - A string representing the link to a fighter page. This is the fighter we want to grab the fighterID for
    """
    query = f"""
    select fighterID
    FROM fighterHyperlinks
    where hyperlink = '{link}'
    """
    cursor.execute(query)
    result = cursor.fetchall()
    fighter_id = result[0][0]
    return fighter_id


def add_www_to_links(links):
    """
    checks to make sure that our links have the www substring so that when we compare to the fighterHyperlinks table it's easier to see if we have that fighter in
    record
    """
    updated_links = []
    for link in links:
        updated_link = link.replace("http://", "http://www.")
        updated_links.append(updated_link)
    return updated_links

def fighter_stat_grabber(fighter):
    """
    This method is used to grab all the individual fighter stats like strikes absorbed per minute to feed into our database
    """
    time.sleep(1)
    fighter_first = fighter[0]
    fighter_last = fighter[1]
    fighter_url = fighter[2]
    # Make a request to the website and parse html content
    response = requests.get(fighter_url, timeout=25)
    soup = BeautifulSoup(response.content, "html.parser")

    # This grabs the list elements that make up the fighter stats page
    list_items = soup.find_all(
        "li", class_="b-list__box-list-item b-list__box-list-item_type_block"
    )

    # declare a dict we can store pairs for stats and their titles
    fighter_stats = {}  # Create an empty dictionary to store the stats
    fighter_stats["First Name"] = fighter_first
    fighter_stats["Last Name"] = fighter_last
    fighter_stats["URL"] = fighter_url

    for item in list_items:
        soup = BeautifulSoup(str(item), "html.parser")
        title = (
            soup.find("i").get_text(strip=True).rstrip(":")
        )  # Remove the colon from the title
        value = soup.get_text(strip=True).replace(
            title + ":", ""
        )  # Also remove the colon from the value
        fighter_stats[title] = value  # Add the title and value to the dictionary

    return fighter_stats  # Return the dictionary

def hyperlink_grabber(last_name_letter):
    """
    This method is used to grab all the hyper links for each individual fighters so that we can access their individual data
    """
    time.sleep(1)
    # Make a request to the website and parse html content
    url = f"http://www.ufcstats.com/statistics/fighters?char={last_name_letter}&page=all"
    response = requests.get(url, timeout=25)
    soup = BeautifulSoup(response.content, "html.parser")

    # navigate to the fighter table and extract all rows
    table = soup.find_all("table")[0]
    rows = table.find_all("tr")

    fighter_link_list = []
    # Loop through the rows
    for row in rows:
        cells = row.find_all("td")
        if len(cells) >= 2:
            first_cell = cells[0]
            second_cell = cells[1]

            first_name_link = first_cell.find("a")
            last_name_link = second_cell.find("a")
            first_name_hyperlink = first_name_link.get("href")
            first_name_text = first_name_link.text
            last_name_text = last_name_link.text
            tmp_tuple = (first_name_text, last_name_text, first_name_hyperlink)
            fighter_link_list.append(tmp_tuple)

    return fighter_link_list

def ufc_event_grabber():
    """
    This method grabs all of the zuffa events so that we can build the events table
    """
    time.sleep(1)
    url = "http://ufcstats.com/statistics/events/completed?page=all"
    response = requests.get(url, timeout=25)
    soup = BeautifulSoup(response.text, "html.parser")

    # Find the table that contains the data
    table = soup.find("table", {"class": "b-statistics__table-events"})

    # Get all rows in the table
    rows = table.find_all("tr")

    tmp_list = []
    for row in rows:
        # Get all columns in the row
        cols = row.find_all("td")

        # Check if columns exist
        if len(cols) >= 2:
            # this one gets a lil messy so we have to break into parts before grabbing individual event names and the date
            event_name_and_date = cols[0].text.strip()
            parts = event_name_and_date.split("\n")
            parts = [part for part in parts if part.strip()]
            event_name = parts[0].strip()
            event_date = parts[1].strip()

            event_link = cols[0].find("a")["href"]
            event_location = cols[1].text.strip()
            tmp_tuple = (event_name, event_date, event_location, event_link)
            tmp_list.append(tmp_tuple)
    return tmp_list

def fight_stat_grabber_a(event):
    """
    We had to split the original method in half because it was to intensive and things were getting lost in the middle. Now the first half
    is dedicated to taking in a event row from our eventHyperLinks table and vising the page related to that row. From there its going to scrape all
    the fights that occurred at this event as well as the winner of that individual fight. This will all be returned in a list of tuples that where each 
    individual tuple will represent a fight on the card and will contain things like the winner, link, and event_id.

    PARAMETERS
    event - A tuple representing a row from the eventHyperlinks table

    RETURN
    event_stats - A list of tuples where each tuple represents the winner, fight link, and the unique event_id for this particular fight
    """
    time.sleep(1)
    event_id = event[0]
    event_name = event[1]
    event_url = event[4]
    response = requests.get(event_url, timeout=25)
    soup = BeautifulSoup(response.content, "html.parser")

    # grab main fights table, which contains info on all fights that happened during this particular event
    tables = soup.find_all("table")
    if not tables:
        return [
            f"This {event_name} didnt have a table to grab. This was the link {event_url}"
        ]
    table = tables[0]
    rows = table.find_all("tr")

    # grab all onClick links in the fighter table, which represent pages for each individual fight that we can look at
    fight_links = []
    winners = []
    weight_classes = []
    for row in rows:

        # checks to see if theres a hyperlink thats activiated on click and if so add to our fight_links list
        onclick = row.get("onclick")
        if onclick:
            fight_links.append(onclick)

        # want to find the winner from this table and store for later
        winner_tag = row.find("a", class_="b-link b-link_style_black")
        header_tag = row.find("th")
        nc_tag = row.find("i", class_="b-flag__text")
        try:
            no_contest_tag_text = nc_tag.text.strip()
        except:
            no_contest_tag_text = None
        if winner_tag and not header_tag and no_contest_tag_text != "nc":
            winner = winner_tag.get_text().strip()
            winners.append(winner)
        elif winner_tag and not header_tag and no_contest_tag_text == "nc":
            winner = nc_tag.text.strip()
            winners.append(winner)

        # want to grab the weight class and store for later, stored in this kind of class but there multiple columns with this name. Grab the 2nd occurence
        weight_class_tags = row.find_all(
            "td", class_="b-fight-details__table-col l-page_align_left"
        )
        if weight_class_tags and len(weight_class_tags) > 1:
            weight_class_tag = weight_class_tags[1]
            weight_class_text = (
                weight_class_tag.find("p", class_="b-fight-details__table-text")
                .get_text()
                .strip()
            )
            weight_classes.append(weight_class_text)

    # pair the event_id with the winners and fight links for all fights that occured at this event
    fight_links = [fight.split("'")[1] for fight in fight_links]
    winner_and_link = list(zip(winners, weight_classes, fight_links))
    event_stats = [
        (winner, weight_class, link, event_id)
        for winner, weight_class, link in winner_and_link
    ]
    return event_stats

def fight_stat_grabber_b(event_stats):
    """
    This is the second part of the original fightStatGrabber method. This is meant to act upon the tuples that are produced by part A.
    Its going to take in a tuple labeled event_stats that contains the following information in this exact order:
    winner, weight_class, link, event_id
    We're going to grab the link to visit the individual fight page and try to find the top table pertaining to 'Totals' and scrape all of that 
    information.

    PARAMETER
    event_stats - a tuple containing the winner, weight_class, fight link, and event_id for a particular fight in the UFC
    """

    db_credentials = get_secret()
    cnx = mysql.connector.connect(
        user=db_credentials["username"],
        password=db_credentials["password"],
        host=db_credentials["host"],
        database=db_credentials["dbInstanceIdentifier"],
    )
    cursor = cnx.cursor()

    print(
        f"started fight_stats for {event_stats[0]} at the event with the following event_id:{event_stats[3]}"
    )
    time.sleep(1)
    fight_stats = []
    fight_link = event_stats[2]

    # navigate to the page for this fight
    response = requests.get(fight_link, timeout=25)
    soup = BeautifulSoup(response.content, "html.parser")

    # check if there are tables and if so grab the fight details
    tables = soup.find_all("table")
    if tables:
        # grab all stat info for this particular fight
        table = tables[0]
        stats = table.find_all("p", class_="b-fight-details__table-text")
        current_fight = [p.get_text(strip=True) for p in stats]

        # also grab fighterHyperLinks so we can grab their fighter_ids from the fighterHyperLinks table
        hyperlinks = table.find_all("a", class_="b-link b-link_style_black")
        hyperlinks = [link["href"] for link in hyperlinks]
        hyperlinks = add_www_to_links(hyperlinks)
        fighter_ids = [fighter_id_grabber(hyperlink, cursor) for hyperlink in hyperlinks]

        # add fighter_ids, winner, event_id, and fight_link to our current list
        current_fight.extend(fighter_ids)
        current_fight.extend(list(event_stats))
    else:
        return []

    # add code to scrape our three new columns round_number, time, and method
    time_content = soup.find("p", class_="b-fight-details__text")

    # grab method tag to extract the method the fight ended and the round_number
    method_tag = time_content.find("i", class_="b-fight-details__text-item_first")
    result = method_tag.find("i", style="font-style: normal").get_text(strip=True)
    round_number = method_tag.find_next_sibling("i").get_text(strip=True)
    round_number = round_number.split(':')[1]

    # Find the time tag to extract when the fight ended
    time_tag = time_content.find('i', class_='b-fight-details__text-item')
    time_result = time_tag.find_next_sibling('i').get_text(strip=True)
    time_result = time_result.split(":", 1)[1]
    tmp_list = [result, time_result, round_number]
    current_fight.extend(tmp_list)
    fight_stats.append(current_fight)
    
    cursor.close()
    cnx.close()
    return fight_stats
