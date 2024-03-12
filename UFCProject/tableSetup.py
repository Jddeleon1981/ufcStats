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
query = "SELECT * FROM eventHyperlinks"
cursor.execute(query)
eventHyperLinks = cursor.fetchall()

#switch to df so we can filter by events after the start of the modern ruleset for mma
df = pd.DataFrame(eventHyperLinks, columns=['Event ID', 'Event Name', 'Date', 'Location', 'URL'])
df['Date'] = pd.to_datetime(df['Date'], format='%B %d, %Y')
df = df[df['Date'] >= '2000-09-01']

structured_array = df.to_records(index=False)
eventHyperLinks = list(structured_array)

with ThreadPoolExecutor(10) as executor:
    winnerGrabber = list(executor.map(tsum.fightStatGrabberA, eventHyperLinks))
winnerGrabber = [event for subList in winnerGrabber for event in subList]

with ThreadPoolExecutor(10) as executor:
    allFighterStats = list(executor.map(tsum.fightStatGrabberB, winnerGrabber))
allFighterStats = [event for subList in allFighterStats for event in subList]

allFighterStatsDF = pd.DataFrame(allFighterStats, columns=['fighter_A', 'fighter_B', 'fighter_A_KD', 'fighter_B_KD', 'fighter_a_sig_strikes', 'fighter_b_sig_strikes', 'fighter_a_sig_strike_acc', 'fighter_b_sig_strike_acc', 'fighter_a_total_strikes', 'fighter_b_total_strikes', 'fighter_a_takedowns', 'fighter_b_takedowns', 'fighter_a_takedown_acc', 'fighter_b_takedown_acc', 'fighter_a_sub_attempts', 'fighter_b_sub_attempts', 'fighter_a_reversal', 'fighter_b_reversal', 'fighter_a_control_time', 'fighter_b_control_time', 'weight_class', 'winner', 'fightURL', 'eventID'])

cursor.execute("DROP TABLE IF EXISTS fightStats")
cursor.execute("""
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
        weight_class VARCHAR(255),
        fighter_A_ID VARCHAR(255),
        fighter_B_ID VARCHAR(255),
        winner VARCHAR(255),
        fightURL VARCHAR(255),
        eventID INT,
        PRIMARY KEY (fightID),
        FOREIGN KEY (eventID) REFERENCES eventHyperlinks(eventID),
        FOREIGN KEY (fighter_A_ID) REFERENCES fighterHyperlinks(fighterID),
        FOREIGN KEY (fighter_B_ID) REFERENCES fighterHyperlinks(fighterID)
    )
""")

# Insert the data
query = "INSERT INTO fightStats (fighterA, fighterB, fighter_A_KD, fighter_B_KD, fighter_A_sig_strikes, fighter_B_sig_strikes, fighter_A_sig_strike_acc, fighter_B_sig_strike_acc, fighter_A_total_strikes, fighter_B_total_strikes, fighter_A_takedowns, fighter_B_takedowns, fighter_A_takedown_acc, fighter_B_takedown_acc, fighter_A_sub_attempts, fighter_B_sub_attempts, fighter_A_reversal, fighter_B_reversal, fighter_A_control_time, fighter_B_control_time, weight_class, fighter_A_ID, fighter_B_ID, winner, fightURL, eventID) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
allFighterStatsList = allFighterStatsDF.to_records(index=False).tolist()
cursor.executemany(query, allFighterStatsList)
cnx.commit()

#close out
cursor.close()
cnx.close()