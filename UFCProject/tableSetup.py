import requests
import mysql.connector
from bs4 import BeautifulSoup
from sqlConfig import loginConfig
import tableSetUpMethods as tsum
import time
from concurrent.futures import ThreadPoolExecutor

cnx = mysql.connector.connect(
    user=loginConfig['user'],
    password=loginConfig['password'],
    host=loginConfig['host'],
    database=loginConfig['database']
)
cursor = cnx.cursor()

"""
This code block is dedicated to setting up the fighterHyperLink table. It contains all the fighters personal stats as well as the hyperlink we grabbed it from
"""
#This grabs the fighter detail links for every single fighter on the ufc stats page as its paginated by the first letter of the last name
lastNameLetters = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'i', 'j', 'k', 'l', 'm', 'n', 'o', 'p', 'q', 'r', 's', 't', 'u', 'v', 'w', 'x', 'y', 'z']
with ThreadPoolExecutor(5) as executor:
    allZuffaFighters = list(executor.map(tsum.hyperLinkGrabber, lastNameLetters))

allZuffaFighters = [fighter for subList in allZuffaFighters for fighter in subList]

with ThreadPoolExecutor(5) as executor:
    allFighterStats = list(executor.map(tsum.fighterStatGrabber, allZuffaFighters))

allZuffaFighters = pd.DataFrame(allFighterStats)
allZuffaFighters = allZuffaFighters.drop('', axis=1)

cursor.execute("DROP TABLE IF EXISTS fighterHyperlinks")
cursor.execute("""
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
""")

# Insert the data
query = "INSERT INTO fighterHyperlinks (firstName, lastName, hyperlink, Height, Weight, Reach, Stance, DOB, Strikes_Landed_Per_Minute, Strike_Accuracy, Strikes_Absorbed_Per_Minute, Strike_Defense, Takedown_Average, Takedown_Accuracy, Takedown_Defense, Submission_Average) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
allZuffaFightersList = allZuffaFighters.to_records(index=False).tolist()
cursor.executemany(query, allZuffaFightersList)
cnx.commit()

"""
This block of code is dedicated to building the events table
"""
eventList = tsum.ufcEventGrabber()
cursor.execute("DROP TABLE IF EXISTS eventHyperlinks")
cursor.execute("""
    CREATE TABLE eventHyperlinks (
        eventID INT AUTO_INCREMENT,
        eventName VARCHAR(255),
        eventDate VARCHAR(255),
        eventLocation VARCHAR(255),
        eventHyperLink VARCHAR(255),
        PRIMARY KEY (eventID)
    )
""")

# Insert the data
query = "INSERT INTO eventHyperlinks (eventName, eventDate, eventLocation, eventHyperLink) VALUES (%s, %s, %s, %s)"
cursor.executemany(query, eventList)
cnx.commit()


"""
This code block is dedicated to setting up the fightStats table. It contains fight stats for events starting from the 2000s since thats when the unified rule
set was established
"""
with ThreadPoolExecutor(10) as executor:
    winnerGrabber = list(executor.map(tsum.fightStatGrabberA, eventHyperLinks))
winnerGrabber = [event for subList in winnerGrabber for event in subList]

with ThreadPoolExecutor(10) as executor:
    allFighterStats = list(executor.map(tsum.fightStatGrabberB, winnerGrabber))
allFighterStats = [event for subList in allFighterStats for event in subList]

allFighterStatsDF = pd.DataFrame(allFighterStats, columns=['fighter_A', 'fighter_B', 'fighter_A_KD', 'fighter_B_KD', 'fighter_a_sig_strikes', 'fighter_b_sig_strikes', 'fighter_a_sig_strike_acc', 'fighter_b_sig_strike_acc', 'fighter_a_total_strikes', 'fighter_b_total_strikes', 'fighter_a_takedowns', 'fighter_b_takedowns', 'fighter_a_takedown_acc', 'fighter_b_takedown_acc', 'fighter_a_sub_attempts', 'fighter_b_sub_attempts', 'fighter_a_reversal', 'fighter_b_reversal', 'fighter_a_control_time', 'fighter_b_control_time', 'weight_class', 'winner', 'fightURL', 'eventID', 'event', 'date', 'location'])
allFighterStatsDF['date'] = allFighterStatsDF['date'].astype(str)

cursor.execute("DROP TABLE IF EXISTS fightStats")
cursor.execute("""
    CREATE TABLE fightStats (
        fightID INT AUTO_INCREMENT,
        fighterA VARCHAR(255),
        fighterB VARCHAR(255),
        fighter_A_KD VARCHAR(255),
        fighter_B_KD VARCHAR(255),
        fighter_a_sig_strikes VARCHAR(255),
        fighter_b_sig_strikes VARCHAR(255),
        fighter_a_sig_strike_acc VARCHAR(255),
        fighter_b_sig_strike_acc VARCHAR(255),
        fighter_a_total_strikes VARCHAR(255),
        fighter_b_total_strikes VARCHAR(255),
        fighter_a_takedowns VARCHAR(255),
        fighter_b_takedowns VARCHAR(255),
        fighter_a_takedown_acc VARCHAR(255),
        fighter_b_takedown_acc VARCHAR(255),
        fighter_a_sub_attempts VARCHAR(255),
        fighter_b_sub_attempts VARCHAR(255),
        fighter_a_reversal VARCHAR(255),
        fighter_b_reversal VARCHAR(255),
        fighter_a_control_time VARCHAR(255),
        fighter_b_control_time VARCHAR(255),
        weight_class VARCHAR(255),
        winner VARCHAR(255),
        fightURL VARCHAR(255),
        eventID INT,
        event VARCHAR(255),
        date VARCHAR(255),
        location VARCHAR(255),
        PRIMARY KEY (fightID),
        FOREIGN KEY (eventID) REFERENCES eventHyperlinks(eventID)
    )
""")

# Insert the data
query = "INSERT INTO fightStats (fighterA, fighterB, fighter_A_KD, fighter_B_KD, fighter_a_sig_strikes, fighter_b_sig_strikes, fighter_a_sig_strike_acc, fighter_b_sig_strike_acc, fighter_a_total_strikes, fighter_b_total_strikes, fighter_a_takedowns, fighter_b_takedowns, fighter_a_takedown_acc, fighter_b_takedown_acc, fighter_a_sub_attempts, fighter_b_sub_attempts, fighter_a_reversal, fighter_b_reversal, fighter_a_control_time, fighter_b_control_time, weight_class, winner, fightURL, eventID, event, date, location) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
allFighterStatsList = allFighterStatsDF.to_records(index=False).tolist()
cursor.executemany(query, allFighterStatsList)
cnx.commit()

#close out
cursor.close()
cnx.close()