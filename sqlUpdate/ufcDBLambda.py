"""
This file is what is currently running in our lambda function on aws. It runs on a cron like schedule every week on Sundays at 10am. It updates the
fighter, event and fightStat tables with all of the new data that has potentially occured given that ufc events usually run everynight on Saturdays.
"""

import requests
import mysql.connector
from bs4 import BeautifulSoup
import time
import pandas as pd
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from collections import namedtuple
import boto3
from botocore.exceptions import ClientError
import json

"""
This method grabs events that have taken place that are not currently in our database 

Parameters:
    currentDateTime - a datetime object representing the time as this script is being run
    latestStoredEventTime - a datetime object that represents the time stamp of the latest event that is currently
    stored in our db

Return:
    newEvents - A list of tuples that represents all the events that we need to update our db with
"""
def ufcEventGrabber(currentDateTime, latestStoredEventTime):
    #add buffer before connecting to ufc events page 
    time.sleep(1)
    url = "http://ufcstats.com/statistics/events/completed?page=all"
    response = requests.get(url)
    soup = BeautifulSoup(response.text, 'html.parser')
    
    # connect to aprop table and collect all rows
    table = soup.find('table', {'class': 'b-statistics__table-events'})
    rows = table.find_all('tr')
    
    newEvents = []
    for row in rows:

        # if there are columns we'll grab and store
        cols = row.find_all('td')
        if len(cols) >= 2:
            #event name and date are coupled we'll use this block to seperate them into their own values
            eventNameAndDate = cols[0].text.strip()
            parts = eventNameAndDate.split('\n')
            parts = [part for part in parts if part.strip()]
            eventName = parts[0].strip()
            eventDate = parts[1].strip()
            eventDateObject = datetime.strptime(parts[1].strip(), '%B %d, %Y')
            
            eventLink = cols[0].find('a')['href']
            eventLocation = cols[1].text.strip()

            #stores all events that are in between our current date and the last stored event in our db
            if latestStoredEventTime < eventDateObject < currentDateTime:
                tmpTuple = (eventName, eventDate, eventLocation, eventLink)
                newEvents.append(tmpTuple)
            #break if we start to go back earlier than what we already have stored in the db
            if eventDateObject < latestStoredEventTime:
                break  
    return(newEvents)

"""
Given a event page we are going to scrape all the fighters and their respective url 

Parameters:
    url - a link representing a singular ufc event fights page listing the fights, fighters, and outcomes

Return:
    fightLinks - a list that contains all of the figher names and their respective urls for this fight event
"""
def scrape_fighter_data(url):
    response = requests.get(url)
    soup = BeautifulSoup(response.content, 'html.parser')
    
    #grab main fights table, which contains info on all fights that happened during this particular event
    tables = soup.find_all('table')
    if not tables:
        return [f"This  didnt have a table to grab. This was the link {url}"]
    table = tables[0]
    rows = table.find_all('tr')

    fightLinks = []
    for row in rows:
        #want to grab figherName and store for later, stored in this kind of class but there multiple columns with this name. Grab the 1st occurence
        fighterRowTags = row.find_all('td', class_='b-fight-details__table-col l-page_align_left')
        if fighterRowTags and len(fighterRowTags) > 1:  
            fighterNameTag = fighterRowTags[0] 
            fighterNameText = fighterNameTag.find_all('p', class_='b-fight-details__table-text')

            for tag in fighterNameText:
                a_tag = tag.find('a')

                # Extract the fighter name and URL
                fighter_name = a_tag.text.strip()
                fighter_url = a_tag['href']

                # Append the name and URL as a tuple to fightLinks
                fightLinks.append((fighter_name, fighter_url))

    return fightLinks

"""
Add www to links so that requests can process the links when we visit them later on
"""
def add_www_to_links(links):
    updated_links = []
    for link in links:
        updated_link = link.replace('http://', 'http://www.')
        updated_links.append(updated_link)
    return updated_links

"""
This method is used to retrieve the unique primary key for our current fighter based off of their fighter page url

Parameter:
    link - The link that represents the fighter page url for our current fighter
    cursor - The cursor that will allow for us to query against our db and check if this person is new

Return
    fighterID - The fighter ID returned for our current fighter from our db
"""
def fighterIDGrabber(link, cursor):
    query = f"""
    select fighterID
    FROM fighterHyperlinks
    where hyperlink = '{link}'
    """
    cursor.execute(query)
    result = cursor.fetchall()
    fighterID = result[0][0]
    return(fighterID)

"""
This method is used to retrieve all the personal stats that are listed on a fighters personal page

Parameters:
    fighter - A 3 piece tuple containing first, last name and fighter url

Return
    fighterStats - A dict where the keys are the statistic and the values are the measurements for these stats pertaining to this fighter
"""
def fighterStatGrabber(fighter):

    #add buffer and decouple the tuple
    time.sleep(1)
    fighterFirst, fighterLast, fighterURL = fighter

    response = requests.get(fighterURL)
    soup = BeautifulSoup(response.content, 'html.parser')

    # This grabs the list elements that make up the fighter stats page
    listItems = soup.find_all('li', class_='b-list__box-list-item b-list__box-list-item_type_block')

    #declare a dict so we can store pairs for stats and their titles
    fighterStats = {}  
    fighterStats['First Name'] = fighterFirst
    fighterStats['Last Name'] = fighterLast
    fighterStats['URL'] = fighterURL

    #add all personal stats for the fighter into our dict
    for item in listItems:
        soup = BeautifulSoup(str(item), 'html.parser')

        #remove unnex ':' from values before adding
        title = soup.find('i').get_text(strip=True).rstrip(':')  
        value = soup.get_text(strip=True).replace(title + ':', '')  
        fighterStats[title] = value  

    return fighterStats  

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
def fightStatGrabberA(event):
    time.sleep(1)
    eventID = event[0]
    eventName = event[1]
    eventURL = event[4]
    response = requests.get(eventURL)
    soup = BeautifulSoup(response.content, 'html.parser')
    
    #grab main fights table, which contains info on all fights that happened during this particular event
    tables = soup.find_all('table')
    if not tables:
        return [f"This {eventName} didnt have a table to grab. This was the link {eventURL}"]
    table = tables[0]
    rows = table.find_all('tr')
    
    #grab all onClick links in the fighter table, which represent pages for each individual fight that we can look at
    fightLinks = []
    winners = []
    weightClasses = []
    for row in rows:

        #checks to see if theres a hyperlink thats activiated on click and if so add to our fightLinks list
        onclick = row.get('onclick')
        if onclick:
            fightLinks.append(onclick)
    
        #want to find the winner from this table and store for later
        winner_tag = row.find('a', class_='b-link b-link_style_black')
        header_tag = row.find('th')
        if winner_tag and not header_tag:  # want to avoid grabbing the tag that just says 'winner'
            winner = winner_tag.get_text().strip()
            winners.append(winner)

        #want to grab the weight class and store for later, stored in this kind of class but there multiple columns with this name. Grab the 2nd occurence
        weightClass_tags = row.find_all('td', class_='b-fight-details__table-col l-page_align_left')
        if weightClass_tags and len(weightClass_tags) > 1:  
            weightClass_tag = weightClass_tags[1] 
            weightClass_text = weightClass_tag.find('p', class_='b-fight-details__table-text').get_text().strip()
            weightClasses.append(weightClass_text)
            
    #pair the eventID with the winners and fight links for all fights that occured at this event
    fightLinks = [fight.split("'")[1] for fight in fightLinks]
    winnerAndLink = list(zip(winners, weightClasses, fightLinks))
    eventStats = [(winner, weightClass, link, eventID) for winner, weightClass, link in winnerAndLink]
    return(eventStats)

"""
This is the second part of the original fightStatGrabber method. This is meant to act upon the tuples that are produced by part A.
Its going to take in a tuple labeled eventStats that contains the following information in this exact order:
winner, weightClass, link, eventID
We're going to grab the link to visit the individual fight page and try to find the top table pertaining to 'Totals' and scrape all of that 
information.

PARAMETER
eventStats - a tuple containing the winner, weightClass, fight link, and eventID for a particular fight in the UFC
"""
def fightStatGrabberB(eventStats):

    dbCredentials = getSecret()
    cnx = mysql.connector.connect(
        user=dbCredentials['username'],
        password=dbCredentials['password'],
        host=dbCredentials['host'],
        database=dbCredentials['dbname']
    )
    cursor = cnx.cursor()

    print(f'started fightStats for {eventStats[0]} at the event with the following eventID:{eventStats[3]}')
    time.sleep(1)
    fightStats = []   
    fightLink = eventStats[2]
    
    #navigate to the page for this fight
    response = requests.get(fightLink)
    soup = BeautifulSoup(response.content, 'html.parser')

    #check if there are tables and if so grab the fight details
    tables = soup.find_all('table')
    if tables:
        #grab all stat info for this particular fight
        table = tables[0] 
        stats = table.find_all('p', class_='b-fight-details__table-text')
        currFight = [p.get_text(strip=True) for p in stats]

        #also grab fighterHyperLinks so we can grab their fighterIDs from the fighterHyperLinks table
        hyperLinks = table.find_all('a', class_='b-link b-link_style_black')
        hyperLinks = [link['href'] for link in hyperLinks]
        hyperLinks = add_www_to_links(hyperLinks)
        fighterIDs = [fighterIDGrabber(hyperLink, cursor) for hyperLink in hyperLinks]

        #add fighterIDs, winner, eventID, and fightLink to our current list
        currFight.extend(fighterIDs)
        currFight.extend(list(eventStats))
        fightStats.append(currFight)
    else:
        return []
    
    cursor.close()
    cnx.close()
    return(fightStats)

"""
Using AWS secret manager retrieve the db credentials for our mysql ufc db
"""
def getSecret():

    secret_name = "ufcStats-db-credentials"
    region_name = "us-west-1"

    #create client
    session = boto3.session.Session()
    client = session.client(
        service_name='secretsmanager',
        region_name=region_name
    )
    try:
        get_secret_value_response = client.get_secret_value(
            SecretId=secret_name
        )
    except ClientError as e:
        raise e

    #format as dict before returning
    secret = get_secret_value_response['SecretString']
    return json.loads(secret)


###
#MAIN
###
def lambda_handler(event, context):

    #grab credientals and connect to db
    dbCredentials = getSecret()
    cnx = mysql.connector.connect(
        user=dbCredentials['username'],
        password=dbCredentials['password'],
        host=dbCredentials['host'],
        database=dbCredentials['dbname']
    )
    cursor = cnx.cursor()

    ###
    #This snippet is dedicated to updating the eventHyperLinks table
    ###

    #grab events table and store into a df
    query = f"""
        select *
        FROM eventHyperlinks
        """
    cursor.execute(query)
    eventData = cursor.fetchall()
    eventDataDF = pd.DataFrame(eventData, columns=['eventID', 'eventName', 'eventDate', 'eventLocation', 'eventURL'])

    # Get the row with the latest date so we can see if theres a event we havent added yet
    latestEvent = eventDataDF.loc[pd.to_datetime(eventDataDF['eventDate']).idxmax()]

    #grab current time for comparison purposes against latest event stored in the db
    currentTime = datetime.now()
    latestStoredEventTime = pd.to_datetime(latestEvent['eventDate'])
    newEvents = ufcEventGrabber(currentTime, latestStoredEventTime)

    #if newEvents is empty a new event hasnt happened yet, exit with a 0
    if not newEvents:
        print("No deteced new events to update our db with")
        return {
            'statusCode': 200,
            'body': json.dumps('No new events detected')
        }

    #update the eventHyperLinks page
    query = "INSERT INTO eventHyperlinks (eventName, eventDate, eventLocation, eventHyperLink) VALUES (%s, %s, %s, %s)"
    cursor.executemany(query, newEvents)
    cnx.commit()
    print("Finished updating the eventHyperLinks table")


    ###
    #This code block updates the fighterHyperLink page
    ###

    Event = namedtuple('Event', ['eventName', 'eventDate', 'eventLocation', 'eventURL'])
    for event in newEvents:
        eventTuple = Event(*event)
        query = f"""
            SELECT *
            FROM eventHyperlinks
            WHERE
                eventName = '{eventTuple.eventName}' and eventDate = '{eventTuple.eventDate}' and eventHyperLink = '{eventTuple.eventURL}' 
            """
    cursor.execute(query)
    eventData = cursor.fetchall()

    # scrape fighter links so we can see if we have stored in fighterHyperLinks, store in flattened list of tuples
    fighterData = [data for sublist in (scrape_fighter_data(str(event[4])) for event in eventData) for data in sublist]

    #seperate so we can add www to links before coupling as tuples again
    fighterNames, fighterURLs = zip(*fighterData)  
    updatedURLs = add_www_to_links(fighterURLs)  
    fighterLinks = list(zip(fighterNames, updatedURLs))

    #fighterLinks now contains the unique links for each fighter, if our db doesnt have yet we need to update with the newly added fighter
    #this should be changed such that if it doesnt fail we update with the newest info
    newFighters = []
    for elem in fighterLinks:
        try:
            #gather first, last name, and url for current fighter and store as three part tuple
            nameParts = elem[0].strip().split(' ', 1)
            firstName = nameParts[0]
            lastName = nameParts[1] if len(nameParts) > 1 else ''
            url = elem[1]
            fighterTuple = (firstName, lastName, url)

            #if fighter already in db then we need to update stats with latest information
            fighterID = fighterIDGrabber(url, cursor)
            fighterTuple = (firstName, lastName, url)
            updatedStats = (fighterStatGrabber(fighterTuple))
            updatedStats.pop('', None) #remove empty key that is added

            #update db for our current fighter
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
            data = (*updatedStats.values(), fighterID)
            cursor.execute(query, data)
            cnx.commit()
            
            print(f"finished updating stats for {firstName} {lastName}")
        except Exception as e: #if we run into an error means we ran into a fighter not currently in the db -> new fighter 
            print(e)
            newFighters.append(fighterStatGrabber(fighterTuple))


    #add all new fighters into fighterHyperLinks
    if newFighters:
        print(f"There was new fighters: {newFighters}")

        #format newFighters into format that can be used for sql inserts
        newFightersDF = pd.DataFrame(newFighters)
        newFightersDF = newFightersDF.drop('', axis=1)
        newFightersList = newFightersDF.to_records(index=False).tolist()
        query = "INSERT INTO fighterHyperlinks (firstName, lastName, hyperlink, Height, Weight, Reach, Stance, DOB, Strikes_Landed_Per_Minute, Strike_Accuracy, Strikes_Absorbed_Per_Minute, Strike_Defense, Takedown_Average, Takedown_Accuracy, Takedown_Defense, Submission_Average) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
        cursor.executemany(query, newFightersList)
        cnx.commit()
    print("Finished updating fighterHyperLinks table")

    ###
    #This code block is dedicated to updating the fightStats page
    ###

    #grab the winners for our events and store in a flattened list
    winnerGrabber = [fightStatGrabberA(row) for row in eventData]
    winnerGrabber = [event for subList in winnerGrabber for event in subList]

    #gather the fight stats for each fight in our events and store in flattened list
    allFighterStats = [fightStatGrabberB(row) for row in winnerGrabber]
    allFighterStats = [event for subList in allFighterStats for event in subList]

    allFighterStatsDF = pd.DataFrame(allFighterStats, columns=['fighter_A', 'fighter_B', 'fighter_A_KD', 'fighter_B_KD', 'fighter_a_sig_strikes', 'fighter_b_sig_strikes', 'fighter_a_sig_strike_acc', 'fighter_b_sig_strike_acc', 'fighter_a_total_strikes', 'fighter_b_total_strikes', 'fighter_a_takedowns', 'fighter_b_takedowns', 'fighter_a_takedown_acc', 'fighter_b_takedown_acc', 'fighter_a_sub_attempts', 'fighter_b_sub_attempts', 'fighter_a_reversal', 'fighter_b_reversal', 'fighter_a_control_time', 'fighter_b_control_time', 'fighter_A_ID', 'fighter_B_ID', 'winner', 'weightClass', 'fightURL', 'eventID'])

    #insert into fightStats
    query = """INSERT INTO fightStats (fighterA, fighterB, fighter_A_KD, fighter_B_KD, fighter_A_sig_strikes, fighter_B_sig_strikes, 
                                    fighter_A_sig_strike_acc, fighter_B_sig_strike_acc, fighter_A_total_strikes, fighter_B_total_strikes, 
                                    fighter_A_takedowns, fighter_B_takedowns, fighter_A_takedown_acc, fighter_B_takedown_acc, fighter_A_sub_attempts, 
                                    fighter_B_sub_attempts, fighter_A_reversal, fighter_B_reversal, fighter_A_control_time, fighter_B_control_time, 
                                    fighter_A_ID, fighter_B_ID, winner, weightClass, fightURL, eventID) 
                                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"""
    allFighterStatsList = allFighterStatsDF.to_records(index=False).tolist()
    cursor.executemany(query, allFighterStatsList)
    cnx.commit()

    print(f"Added {len(allFighterStatsDF)} fights to our db for the following events: {allFighterStatsDF['eventID'].unique()} and we had a total of {len(newFighters)} new fighters from this event")
    #close out
    cursor.close()
    cnx.close()

    return {
        "statusCode": 200,
        "body": json.dumps({
            "message": "success"
        }),
    }
