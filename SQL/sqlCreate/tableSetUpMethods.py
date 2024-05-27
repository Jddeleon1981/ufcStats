import requests
import mysql.connector
from bs4 import BeautifulSoup
import time
from concurrent.futures import ThreadPoolExecutor
import boto3
from botocore.exceptions import ClientError
import json


"""
Using AWS secret manager retrieve the db credentials for our mysql ufc db
"""
def getSecret():

    secret_name = "ufcDBcred"
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


"""
We use this method to query the fighterHyperLinks table and grab the fighterID for the fighter we're currently working with so that we can add it to its corresponding row when building the fighterStats table

PARAMETER
link - A string representing the link to a fighter page. This is the fighter we want to grab the fighterID for
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
checks to make sure that our links have the www substring so that when we compare to the fighterHyperlinks table it's easier to see if we have that fighter in
record
"""
def add_www_to_links(links):
    updated_links = []
    for link in links:
        updated_link = link.replace('http://', 'http://www.')
        updated_links.append(updated_link)
    return updated_links


"""
This method is used to grab all the individual fighter stats like strikes absorbed per minute to feed into our database
"""
def fighterStatGrabber(fighter):
    time.sleep(1)
    fighterFirst = fighter[0]
    fighterLast = fighter[1]
    fighterURL = fighter[2]
    # Make a request to the website and parse html content
    response = requests.get(fighterURL)
    soup = BeautifulSoup(response.content, 'html.parser')

    # This grabs the list elements that make up the fighter stats page
    overallList = soup.find('ul', {'class': 'b-list__box-list'})
    listItems = soup.find_all('li', class_='b-list__box-list-item b-list__box-list-item_type_block')

    #declare a dict we can store pairs for stats and their titles
    fighterStats = {}  # Create an empty dictionary to store the stats
    fighterStats['First Name'] = fighterFirst
    fighterStats['Last Name'] = fighterLast
    fighterStats['URL'] = fighterURL

    for item in listItems:
        soup = BeautifulSoup(str(item), 'html.parser')
        title = soup.find('i').get_text(strip=True).rstrip(':')  # Remove the colon from the title
        value = soup.get_text(strip=True).replace(title + ':', '')  # Also remove the colon from the value
        fighterStats[title] = value  # Add the title and value to the dictionary

    return fighterStats  # Return the dictionary


"""
This method is used to grab all the hyper links for each individual fighters so that we can access their individual data
"""
def hyperLinkGrabber(lastNameLetter):
    time.sleep(1)
    # Make a request to the website and parse html content
    url = f"http://www.ufcstats.com/statistics/fighters?char={lastNameLetter}&page=all"
    response = requests.get(url)
    soup = BeautifulSoup(response.content, 'html.parser')

    # navigate to the fighter table and extract all rows
    table = soup.find_all('table')[0] 
    rows = table.find_all('tr')

    fighterLinkList = []
    # Loop through the rows
    for row in rows:
        cells = row.find_all('td')
        if len(cells) >= 2:
            firstCell = cells[0]
            secondCell = cells[1]
    
            firstNameLink = firstCell.find('a')
            lastNameLink = secondCell.find('a')
            firstNameHyperLink = firstNameLink.get('href')
            firstNameText = firstNameLink.text
            lastNameText = lastNameLink.text
            tmpTuple = (firstNameText, lastNameText, firstNameHyperLink)
            fighterLinkList.append(tmpTuple)
        
    return(fighterLinkList)

"""
This method grabs all of the zuffa events so that we can build the events table
"""
def ufcEventGrabber():
    time.sleep(1)
    url = "http://ufcstats.com/statistics/events/completed?page=all"
    response = requests.get(url)
    soup = BeautifulSoup(response.text, 'html.parser')
    
    # Find the table that contains the data
    table = soup.find('table', {'class': 'b-statistics__table-events'})
    
    # Get all rows in the table
    rows = table.find_all('tr')
    
    tmpList = []
    for row in rows:
        # Get all columns in the row
        cols = row.find_all('td')
    
        # Check if columns exist
        if len(cols) >= 2:
            #this one gets a lil messy so we have to break into parts before grabbing individual event names and the date
            eventNameAndDate = cols[0].text.strip()
            parts = eventNameAndDate.split('\n')
            parts = [part for part in parts if part.strip()]
            eventName = parts[0].strip()
            eventDate = parts[1].strip()
            
            eventLink = cols[0].find('a')['href']
            eventLocation = cols[1].text.strip()
            tmpTuple = (eventName, eventDate, eventLocation, eventLink)
            tmpList.append(tmpTuple)
    return(tmpList)

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
        database=dbCredentials['dbInstanceIdentifier']
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
    
    #add code to scrape our three new columns round, time, and method
    textContent = soup.find('p', class_='b-fight-details__text')

    #grab method tag to extract the method the fight ended and the round
    method_tag = textContent.find('i', class_='b-fight-details__text-item_first')
    result = method_tag.find('i', style='font-style: normal').get_text(strip=True)
    round = method_tag.find_next_sibling('i').get_text(strip=True)

    # Find the time tag to extract when the fight ended
    time_tag = textContent.find('i', class_='b-fight-details__text-item')
    time = time_tag.find_next_sibling('i').get_text(strip=True)
    tmpList = [result, time, round]
    fightStats.append(tmpList)
    
    cursor.close()
    cnx.close()
    return(fightStats)