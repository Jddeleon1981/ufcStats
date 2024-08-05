"""
Lambda function that runs weekly on Sunday mornings and updates the ufc db. Very similiar to the setup methods file
"""

import json
import time
from collections import namedtuple
from datetime import datetime
import boto3
import mysql.connector
import numpy as np
import pandas as pd
import requests
from botocore.exceptions import ClientError
from bs4 import BeautifulSoup

def ufc_event_grabber(current_datetime, latest_stored_event_time):
    """
    This method grabs events that have taken place that are not currently in our database 

    Parameters:
        current_datetime - a datetime object representing the time as this script is being run
        latest_stored_event_time - a datetime object that represents the time stamp of the latest event that is currently
        stored in our db

    Return:
        new_events - A list of tuples that represents all the events that we need to update our db with
    """

    # add buffer before connecting to ufc events page
    time.sleep(1)
    url = "http://ufcstats.com/statistics/events/completed?page=all"
    response = requests.get(url, timeout=25)
    soup = BeautifulSoup(response.text, "html.parser")

    # connect to aprop table and collect all rows
    table = soup.find("table", {"class": "b-statistics__table-events"})
    rows = table.find_all("tr")

    new_events = []
    for row in rows:

        # if there are columns we'll grab and store
        cols = row.find_all("td")
        if len(cols) >= 2:
            # event name and date are coupled we'll use this block to seperate them into their own values
            event_name_and_date = cols[0].text.strip()
            parts = event_name_and_date.split("\n")
            parts = [part for part in parts if part.strip()]
            event_name = parts[0].strip()
            event_date = parts[1].strip()
            event_date_object = datetime.strptime(parts[1].strip(), "%B %d, %Y")

            event_link = cols[0].find("a")["href"]
            event_location = cols[1].text.strip()

            # stores all events that are in between our current date and the last stored event in our db
            if latest_stored_event_time < event_date_object < current_datetime:
                tmp_tuple = (event_name, event_date, event_location, event_link)
                new_events.append(tmp_tuple)
            # break if we start to go back earlier than what we already have stored in the db
            if event_date_object < latest_stored_event_time:
                break
    return new_events

def scrape_fighter_data(url):
    """
    Given a event page we are going to scrape all the fighters and their respective url 

    Parameters:
        url - a link representing a singular ufc event fights page listing the fights, fighters, and outcomes

    Return:
        fight_links - a list that contains all of the figher names and their respective urls for this fight event
    """
    response = requests.get(url, timeout=25)
    soup = BeautifulSoup(response.content, "html.parser")

    # grab main fights table, which contains info on all fights that happened during this particular event
    tables = soup.find_all("table")
    if not tables:
        return [f"This  didnt have a table to grab. This was the link {url}"]
    table = tables[0]
    rows = table.find_all("tr")

    fight_links = []
    for row in rows:
        # want to grab figherName and store for later, stored in this kind of class but there multiple columns with this name. Grab the 1st occurence
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

                # Extract the fighter name and URL
                fighter_name = a_tag.text.strip()
                fighter_url = a_tag["href"]

                # Append the name and URL as a tuple to fight_links
                fight_links.append((fighter_name, fighter_url))

    return fight_links

def add_www_to_links(links):
    """
    Add www to links so that requests can process the links when we visit them later on
    """
    updated_links = []
    for link in links:
        updated_link = link.replace("http://", "http://www.")
        updated_links.append(updated_link)
    return updated_links

def fighter_id_grabber(link, cursor):
    """
    This method is used to retrieve the unique primary key for our current fighter based off of their fighter page url

    Parameter:
        link - The link that represents the fighter page url for our current fighter
        cursor - The cursor that will allow for us to query against our db and check if this person is new

    Return
        fighterID - The fighter ID returned for our current fighter from our db
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

def fighter_stat_grabber(fighter):
    """
    This method is used to retrieve all the personal stats that are listed on a fighters personal page

    Parameters:
        fighter - A 3 piece tuple containing first, last name and fighter url

    Return
        fighterStats - A dict where the keys are the statistic and the values are the measurements for these stats pertaining to this fighter
    """

    # add buffer and decouple the tuple
    time.sleep(1)
    fighter_first, fighter_last, fighter_url = fighter

    response = requests.get(fighter_url, timeout=25)
    soup = BeautifulSoup(response.content, "html.parser")

    # This grabs the list elements that make up the fighter stats page
    list_items = soup.find_all(
        "li", class_="b-list__box-list-item b-list__box-list-item_type_block"
    )

    # declare a dict so we can store pairs for stats and their titles
    fighter_stats = {}
    fighter_stats["First Name"] = fighter_first
    fighter_stats["Last Name"] = fighter_last
    fighter_stats["URL"] = fighter_url

    # add all personal stats for the fighter into our dict
    for item in list_items:
        soup = BeautifulSoup(str(item), "html.parser")

        # remove unnex ':' from values before adding
        title = soup.find("i").get_text(strip=True).rstrip(":")
        value = soup.get_text(strip=True).replace(title + ":", "")
        fighter_stats[title] = value

    return fighter_stats

def fight_stat_grabber_a(event):
    """
    We had to split the original method in half because it was to intensive and things were getting lost in the middle. Now the first half
    is dedicated to taking in a event row from our eventHyperLinks table and vising the page related to that row. From there its going to scrape all
    the fights that occurred at this event as well as the winner of that individual fight. This will all be returned in a list of tuples that where each 
    individual tuple will represent a fight on the card and will contain things like the winner, link, and eventID.

    PARAMETERS
    event - A tuple representing a row from the eventHyperlinks table

    RETURN
    eventStats - A list of tuples where each tuple represents the winner, fight link, and the unique eventID for this particular fight
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

    # pair the eventID with the winners and fight links for all fights that occured at this event
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
    Its going to take in a tuple labeled eventStats that contains the following information in this exact order:
    winner, weightClass, link, eventID
    We're going to grab the link to visit the individual fight page and try to find the top table pertaining to 'Totals' and scrape all of that 
    information.

    PARAMETER
    eventStats - a tuple containing the winner, weightClass, fight link, and eventID for a particular fight in the UFC
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
        f"started fightStats for {event_stats[0]} at the event with the following eventID:{event_stats[3]}"
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
        fighter_ids = [fighter_id_grabber(hyperLink, cursor) for hyperLink in hyperlinks]

        # add fighter_ids, winner, eventID, and fight_link to our current list
        current_fight.extend(fighter_ids)
        current_fight.extend(list(event_stats))
    else:
        return []

    # add code to scrape our three new columns round, time, and method
    text_content = soup.find("p", class_="b-fight-details__text")

    # grab method tag to extract the method the fight ended and the round
    method_tag = text_content.find("i", class_="b-fight-details__text-item_first")
    result = method_tag.find("i", style="font-style: normal").get_text(strip=True)
    round_number = method_tag.find_next_sibling("i").get_text(strip=True)
    round_number = round_number.split(':')[1]

    # Find the time tag to extract when the fight ended
    time_tag = text_content.find('i', class_='b-fight-details__text-item')
    time_result = time_tag.find_next_sibling('i').get_text(strip=True)
    time_result = time_result.split(":", 1)[1]
    tmp_list = [result, time_result, round_number]
    current_fight.extend(list(tmp_list))
    fight_stats.append(current_fight)

    cursor.close()
    cnx.close()
    return fight_stats

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


def status_email(result):
    """Sends an email to me so I know if the update was succesful or not"""
    client = boto3.client("ses")
    subject = "lambda results"
    body = f"This is what we got from our lambda run: {result}"
    message = {"Subject": {"Data": subject}, "Body": {"Html": {"Data": body}}}
    response = client.send_email(
        Source="josedeleAWS@gmail.com",
        Destination={"ToAddresses": ["josedeleAWS@gmail.com"]},
        Message=message,
    )


###
# MAIN
###
def lambda_handler(event, context):
    """calls lambda function to update db"""
    # grab credientals and connect to db
    db_credentials = get_secret()
    print('connected with secrets manager')
    cnx = mysql.connector.connect(
        user=db_credentials["username"],
        password=db_credentials["password"],
        host=db_credentials["host"],
        database=db_credentials["dbInstanceIdentifier"],
    )
    cursor = cnx.cursor()

    ###
    # This snippet is dedicated to updating the eventHyperLinks table
    ###

    # grab events table and store into a df
    query = """
        select *
        FROM eventHyperlinks
        """
    cursor.execute(query)
    event_data = cursor.fetchall()
    event_data_df = pd.DataFrame(
        event_data,
        columns=["eventID", "eventName", "eventDate", "eventLocation", "eventURL"],
    )

    # Get the row with the latest date so we can see if theres a event we havent added yet
    latest_event = event_data_df.loc[pd.to_datetime(event_data_df["eventDate"]).idxmax()]

    # grab current time for comparison purposes against latest event stored in the db
    current_time = datetime.now()
    latest_stored_event_time = pd.to_datetime(latest_event["eventDate"])
    new_events = ufc_event_grabber(current_time, latest_stored_event_time)

    # if new_events is empty a new event hasnt happened yet, exit with a 0
    if not new_events:
        now = datetime.now()
        result_string = f"No new events detected when checking on {now}"
        print(result_string)
        status_email(result_string)
        return {"statusCode": 200, "body": json.dumps(result_string)}

    # update the eventHyperLinks page
    query = "INSERT INTO eventHyperlinks (eventName, eventDate, eventLocation, eventHyperLink) VALUES (%s, %s, %s, %s)"
    cursor.executemany(query, new_events)
    cnx.commit()
    print("Finished updating the eventHyperLinks table")

    ###
    # This code block updates the fighterHyperLink page
    ###

    Event = namedtuple("Event", ["eventName", "eventDate", "eventLocation", "eventURL"])
    for event in new_events:
        event_tuple = Event(*event)
        query = f"""
            SELECT *
            FROM eventHyperlinks
            WHERE
                eventName = '{event_tuple.eventName}' and eventDate = '{event_tuple.eventDate}' and eventHyperLink = '{event_tuple.eventURL}' 
            """
    cursor.execute(query)
    event_data = cursor.fetchall()

    # scrape fighter links so we can see if we have stored in fighterHyperLinks, store in flattened list of tuples
    fighter_data = [
        data
        for sublist in (scrape_fighter_data(str(event[4])) for event in event_data)
        for data in sublist
    ]

    # seperate so we can add www to links before coupling as tuples again
    fighter_names, fighter_urls = zip(*fighter_data)
    updated_urls = add_www_to_links(fighter_urls)
    fighter_links = list(zip(fighter_names, updated_urls))

    # fighter_links now contains the unique links for each fighter, if our db doesnt have yet we need to update with the newly added fighter
    # this should be changed such that if it doesnt fail we update with the newest info
    new_fighters = []
    for elem in fighter_links:
        try:
            # gather first, last name, and url for current fighter and store as three part tuple
            name_parts = elem[0].strip().split(" ", 1)
            first_name = name_parts[0]
            last_name = name_parts[1] if len(name_parts) > 1 else ""
            url = elem[1]
            fighter_tuple = (first_name, last_name, url)

            # if fighter already in db then we need to update stats with latest information
            fighter_id = fighter_id_grabber(url, cursor)
            fighter_tuple = (first_name, last_name, url)
            updated_stats = fighter_stat_grabber(fighter_tuple)
            updated_stats.pop("", None)  # remove empty key that is added

            # update db for our current fighter
            query = """
            UPDATE fighterHyperlinks 
            SET 
                first_name = %s, 
                last_name = %s, 
                hyperlink = %s, 
                Height = %s, 
                Weight = %s, 
                Reach = %s, 
                Stance = %s, 
                DOB = %s, 
                Strikes_Landed_Per_Minute = %s, 
                Strike_Accuracy = %s, 
                Strikes_Absorbed_Per_Minute = %s, 
                Strike_Defense = %s, 
                Takedown_Average = %s, 
                Takedown_Accuracy = %s, 
                Takedown_Defense = %s, 
                Submission_Average = %s
            WHERE 
                fighterID = %s
            """
            data = (*updated_stats.values(), fighter_id)
            cursor.execute(query, data)
            cnx.commit()

            print(f"finished updating stats for {first_name} {last_name}")
        except (
            Exception
        ) as e:  # if we run into an error means we ran into a fighter not currently in the db -> new fighter
            print(e)
            new_fighters.append(fighter_stat_grabber(fighter_tuple))

    # add all new fighters into fighterHyperLinks
    if new_fighters:
        print(f"There was new fighters: {new_fighters}")

        # format new_fighters into format that can be used for sql inserts
        new_fighters_df = pd.DataFrame(new_fighters)
        new_fighters_df = new_fighters_df.drop("", axis=1)
        new_fighters_df['DOB'] = new_fighters_df['DOB'].replace({'--': np.nan})
        new_fighters_list = new_fighters_df.to_records(index=False).tolist()
        query = "INSERT INTO fighterHyperlinks (first_name, last_name, hyperlink, Height, Weight, Reach, Stance, DOB, Strikes_Landed_Per_Minute, Strike_Accuracy, Strikes_Absorbed_Per_Minute, Strike_Defense, Takedown_Average, Takedown_Accuracy, Takedown_Defense, Submission_Average) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
        cursor.executemany(query, new_fighters_list)
        cnx.commit()
    print("Finished updating fighterHyperLinks table")

    ###
    # This code block is dedicated to updating the fightStats page
    ###

    # grab the winners for our events and store in a flattened list
    winner_grabber = [fight_stat_grabber_a(row) for row in event_data]
    winner_grabber = [event for subList in winner_grabber for event in subList]

    # gather the fight stats for each fight in our events and store in flattened list
    all_fighter_stats = [fight_stat_grabber_b(row) for row in winner_grabber]
    all_fighter_stats = [event for subList in all_fighter_stats for event in subList]

    all_fighter_stats_df = pd.DataFrame(
        all_fighter_stats,
        columns=[
            "fighter_A",
            "fighter_B",
            "fighter_A_KD",
            "fighter_B_KD",
            "fighter_a_sig_strikes",
            "fighter_b_sig_strikes",
            "fighter_a_sig_strike_acc",
            "fighter_b_sig_strike_acc",
            "fighter_a_total_strikes",
            "fighter_b_total_strikes",
            "fighter_a_takedowns",
            "fighter_b_takedowns",
            "fighter_a_takedown_acc",
            "fighter_b_takedown_acc",
            "fighter_a_sub_attempts",
            "fighter_b_sub_attempts",
            "fighter_a_reversal",
            "fighter_b_reversal",
            "fighter_a_control_time",
            "fighter_b_control_time",
            "fighter_A_ID",
            "fighter_B_ID",
            "winner",
            "weightClass",
            "fightURL",
            "eventID",
            "method",
            "time",
            "round",
        ],
    )
    all_fighter_stats_df['fighter_a_takedowns'] = all_fighter_stats_df['fighter_a_takedowns'].str.split(' ').str[0].astype(int)
    all_fighter_stats_df['fighter_b_takedowns'] = all_fighter_stats_df['fighter_b_takedowns'].str.split(' ').str[0].astype(int)
    all_fighter_stats_df['fighter_a_sig_strikes'] = all_fighter_stats_df['fighter_a_sig_strikes'].str.split(' ').str[0].astype(int)
    all_fighter_stats_df['fighter_b_sig_strikes'] = all_fighter_stats_df['fighter_b_sig_strikes'].str.split(' ').str[0].astype(int)

    # insert into fightStats
    query = """INSERT INTO fightStats (fighterA, fighterB, fighter_A_KD, fighter_B_KD, fighter_A_sig_strikes, fighter_B_sig_strikes, 
                                    fighter_A_sig_strike_acc, fighter_B_sig_strike_acc, fighter_A_total_strikes, fighter_B_total_strikes, 
                                    fighter_A_takedowns, fighter_B_takedowns, fighter_A_takedown_acc, fighter_B_takedown_acc, fighter_A_sub_attempts, 
                                    fighter_B_sub_attempts, fighter_A_reversal, fighter_B_reversal, fighter_A_control_time, fighter_B_control_time, 
                                    fighter_A_ID, fighter_B_ID, winner, weightClass, fightURL, eventID, method, time, round) 
                                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"""
    all_fighter_stats_list = all_fighter_stats_df.to_records(index=False).tolist()
    cursor.executemany(query, all_fighter_stats_list)
    cnx.commit()

    print(
        f"Added {len(all_fighter_stats_df)} fights to our db for the following events: {all_fighter_stats_df['eventID'].unique()} and we had a total of {len(new_fighters)} new fighters from this event"
    )
    # close out
    cursor.close()
    cnx.close()

    now = datetime.now()
    result_string = f"Finished updating the database for run: {now}"
    status_email(result_string)
    return {
        "statusCode": 200,
        "body": json.dumps({"message": "success"}),
    }
