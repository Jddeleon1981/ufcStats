"""
Lambda function that runs weekly on Sunday mornings and updates the ufc db. Shares its
scraping, parsing, and DB helpers with the bulk load via the ufcPipeline package.
"""

import json
from collections import namedtuple
from datetime import datetime

import boto3
import numpy as np
import pandas as pd
import requests

from ufcPipeline.db import connect
from ufcPipeline.scraping import (
    EVENTS_URL,
    add_www_to_links,
    fight_stat_grabber_a,
    fight_stat_grabber_b,
    fighter_id_grabber,
    fighter_stat_grabber,
    parse_events,
    scrape_fighter_data,
)


def get_new_events(current_datetime, latest_stored_event_time):
    """
    Return the events that have taken place since the latest one stored in our db.

    Parameters:
        current_datetime - a datetime representing now, as this script runs
        latest_stored_event_time - a datetime for the most recent event already stored

    Return:
        new_events - list of (name, date, location, link) tuples to update our db with
    """
    response = requests.get(EVENTS_URL, timeout=25)
    new_events = []
    for event_name, event_date, event_location, event_link in parse_events(response.text):
        event_date_object = datetime.strptime(event_date, "%B %d, %Y")
        # keep events between our latest stored event and now
        if latest_stored_event_time < event_date_object < current_datetime:
            new_events.append((event_name, event_date, event_location, event_link))
    return new_events


def status_email(result):
    """Sends an email to me so I know if the update was succesful or not"""
    client = boto3.client("ses")
    subject = "lambda results"
    body = f"This is what we got from our lambda run: {result}"
    message = {"Subject": {"Data": subject}, "Body": {"Html": {"Data": body}}}
    client.send_email(
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
    cnx = connect()
    cursor = cnx.cursor()
    print("connected with secrets manager")

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
    new_events = get_new_events(current_time, latest_stored_event_time)

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
                firstName = %s,
                lastName = %s,
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
        query = "INSERT INTO fighterHyperlinks (firstName, lastName, hyperlink, Height, Weight, Reach, Stance, DOB, Strikes_Landed_Per_Minute, Strike_Accuracy, Strikes_Absorbed_Per_Minute, Strike_Defense, Takedown_Average, Takedown_Accuracy, Takedown_Defense, Submission_Average) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
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
