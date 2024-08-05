"""
This script setups our db such that it will contain three tables: fightStats, fighterHyperlinks, and eventHyperlinks.
Making use of the tsum methods we will scrape the ufc stats page to gather all of the information that we'll later feed into
our ML models.
"""

from concurrent.futures import ThreadPoolExecutor
import mysql.connector
import pandas as pd
import numpy as np
import tableSetUpMethods as tsum

db_credentials = tsum.get_secret()
cnx = mysql.connector.connect(
    user=db_credentials["username"],
    password=db_credentials["password"],
    host=db_credentials["host"],
    database=db_credentials["dbInstanceIdentifier"],
)
cursor = cnx.cursor()

print("We connected with secrets manager!")


###
# This code block is dedicated to setting up the fighterHyperLink table. It contains all the fighters personal stats 
# as well as the hyperlink we grabbed it from
###

# This grabs the fighter detail links for every single fighter on the ufc stats page as its paginated by the first letter of the last name
last_name_letters = [
    "a",
    "b",
    "c",
    "d",
    "e",
    "f",
    "g",
    "h",
    "i",
    "j",
    "k",
    "l",
    "m",
    "n",
    "o",
    "p",
    "q",
    "r",
    "s",
    "t",
    "u",
    "v",
    "w",
    "x",
    "y",
    "z",
]

# grabs links for each fighter so we can scrape them later on
# its stored in a list of lists so we flatten it out before continuing
with ThreadPoolExecutor(5) as executor:
    all_zuffa_fighters = list(executor.map(tsum.hyperlink_grabber, last_name_letters))
all_zuffa_fighters = [fighter for subList in all_zuffa_fighters for fighter in subList]

# now scrape all of the stats from the recorded links
with ThreadPoolExecutor(5) as executor:
    all_fighter_stats = list(executor.map(tsum.fighter_stat_grabber, all_zuffa_fighters))

all_zuffa_fighters_df = pd.DataFrame(all_fighter_stats)
all_zuffa_fighters_df = all_zuffa_fighters_df.drop("", axis=1)
all_zuffa_fighters['DOB'] = all_zuffa_fighters['DOB'].replace({'--': np.nan})

cursor.execute("DROP TABLE IF EXISTS fighterHyperlinks")
cursor.execute(
    """
    CREATE TABLE fighterHyperlinks (
        fighterID INT AUTO_INCREMENT,
        firstName VARCHAR(255),
        lastName VARCHAR(255),
        hyperlink VARCHAR(255),
        Height VARCHAR(255),
        Weight VARCHAR(255),
        Reach VARCHAR(255),
        Stance VARCHAR(255),
        DOB VARCHAR(255),
        Strikes_Landed_Per_Minute DECIMAL(4, 2),
        Strike_Accuracy VARCHAR(255),
        Strikes_Absorbed_Per_Minute DECIMAL(4, 2),
        Strike_Defense VARCHAR(255),
        Takedown_Average DECIMAL(4, 2),
        Takedown_Accuracy VARCHAR(255),
        Takedown_Defense VARCHAR(255),
        Submission_Average DECIMAL(4, 2),
        PRIMARY KEY (fighterID)
    )
"""
)

# Insert the data
FIGHTER_LINK_QUERY = "INSERT INTO fighterHyperlinks (firstName, lastName, hyperlink, Height, Weight, Reach, Stance, DOB, Strikes_Landed_Per_Minute, Strike_Accuracy, Strikes_Absorbed_Per_Minute, Strike_Defense, Takedown_Average, Takedown_Accuracy, Takedown_Defense, Submission_Average) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
all_zuffa_fighters_list = all_zuffa_fighters_df.to_records(index=False).tolist()
cursor.executemany(FIGHTER_LINK_QUERY, all_zuffa_fighters_list)
cnx.commit()
print("finished creating the fighterHyperlinks table")

###
# This block of code is dedicated to building the events table
###
event_list = tsum.ufc_event_grabber()
cursor.execute("DROP TABLE IF EXISTS eventHyperlinks")
cursor.execute(
    """
    CREATE TABLE eventHyperlinks (
        eventID INT AUTO_INCREMENT,
        eventName VARCHAR(255),
        eventDate VARCHAR(255),
        eventLocation VARCHAR(255),
        eventHyperLink VARCHAR(255),
        PRIMARY KEY (eventID)
    )
"""
)

# Insert the data
EVENT_LINK_QUERY = "INSERT INTO eventHyperlinks (eventName, eventDate, eventLocation, eventHyperLink) VALUES (%s, %s, %s, %s)"
cursor.executemany(EVENT_LINK_QUERY, event_list)
cnx.commit()
print("finished creating the event hyperlinks table")


###
# This code block is dedicated to setting up the fightStats table. It contains fight stats for events starting from the 2000s 
# since thats when the unified rule set was established
###

RETRIEVE_EVENTS_QUERY = "SELECT * FROM eventHyperlinks"
cursor.execute(RETRIEVE_EVENTS_QUERY)
event_hyper_links = cursor.fetchall()

# switch to df so we can filter by events after the start of the modern ruleset for mma
modern_era = pd.DataFrame(
    event_hyper_links, columns=["Event ID", "Event Name", "Date", "Location", "URL"]
)
modern_era["Date"] = pd.to_datetime(modern_era["Date"], format="%B %d, %Y")
modern_era = modern_era[modern_era["Date"] >= "2000-09-01"]

structured_array = modern_era.to_records(index=False)
eventHyperLinks = list(structured_array)

with ThreadPoolExecutor(10) as executor:
    winner_grabber = list(executor.map(tsum.fight_stat_grabber_a, eventHyperLinks))
winner_grabber = [event for subList in winner_grabber for event in subList]
print("We finished winner_grabber")

with ThreadPoolExecutor(10) as executor:
    all_fighter_stats = list(executor.map(tsum.fight_stat_grabber_b, winner_grabber))
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

cursor.execute("DROP TABLE IF EXISTS fightStats")
cursor.execute(
    """
    CREATE TABLE fightStats (
        fightID INT AUTO_INCREMENT,
        fighterA VARCHAR(255),
        fighterB VARCHAR(255),
        fighter_A_KD VARCHAR(255),
        fighter_B_KD VARCHAR(255),
        fighter_A_sig_strikes VARCHAR(255),
        fighter_B_sig_strikes VARCHAR(255),
        fighter_A_sig_strike_acc VARCHAR(255),
        fighter_B_sig_strike_acc VARCHAR(255),
        fighter_A_total_strikes VARCHAR(255),
        fighter_B_total_strikes VARCHAR(255),
        fighter_A_takedowns VARCHAR(255),
        fighter_B_takedowns VARCHAR(255),
        fighter_A_takedown_acc VARCHAR(255),
        fighter_B_takedown_acc VARCHAR(255),
        fighter_A_sub_attempts VARCHAR(255),
        fighter_B_sub_attempts VARCHAR(255),
        fighter_A_reversal VARCHAR(255),
        fighter_B_reversal VARCHAR(255),
        fighter_A_control_time VARCHAR(255),
        fighter_B_control_time VARCHAR(255),
        fighter_A_ID INT,
        fighter_B_ID INT,
        winner VARCHAR(255),
        weightClass VARCHAR(255),
        fightURL VARCHAR(255),
        eventID INT,
        method varchar(255),
        time varchar(255),
        round varchar(255),
        PRIMARY KEY (fightID),
        FOREIGN KEY (eventID) REFERENCES eventHyperlinks(eventID),
        FOREIGN KEY (fighter_A_ID) REFERENCES fighterHyperlinks(fighterID),
        FOREIGN KEY (fighter_B_ID) REFERENCES fighterHyperlinks(fighterID)
    )
"""
)

# Insert the data
FIGHT_STATS_QUERY = """INSERT INTO fightStats (fighterA, fighterB, fighter_A_KD, fighter_B_KD, fighter_A_sig_strikes, fighter_B_sig_strikes, 
                                   fighter_A_sig_strike_acc, fighter_B_sig_strike_acc, fighter_A_total_strikes, fighter_B_total_strikes, 
                                   fighter_A_takedowns, fighter_B_takedowns, fighter_A_takedown_acc, fighter_B_takedown_acc, fighter_A_sub_attempts, 
                                   fighter_B_sub_attempts, fighter_A_reversal, fighter_B_reversal, fighter_A_control_time, fighter_B_control_time, 
                                   fighter_A_ID, fighter_B_ID, winner, weightClass, fightURL, eventID, method, time, round) 
                                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"""
all_fighter_statsList = all_fighter_stats_df.to_records(index=False).tolist()
cursor.executemany(FIGHT_STATS_QUERY, all_fighter_statsList)
cnx.commit()
print("finished creating the fightStats table")

cursor.close()
cnx.close()
