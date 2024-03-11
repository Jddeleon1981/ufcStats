import requests
import mysql.connector
from bs4 import BeautifulSoup
import time
from concurrent.futures import ThreadPoolExecutor
from sqlConfig import loginConfig

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
individual tuple will represent a fight on the card and will contain things like the winner, link, eventID, eventName, eventDate, eventLocation
"""
def fightStatGrabberA(event):
    time.sleep(1)
    eventID = event[0]
    eventName = event[1]
    eventDate = event[2]
    eventLocation = event[3]
    eventURL = event[4]
    response = requests.get(eventURL)
    soup = BeautifulSoup(response.content, 'html.parser')
    
    #grab main fights table
    tables = soup.find_all('table')
    if not tables:
        print(f"This {eventName} didnt have a table to grab. This was the link {eventURL}")
        return [f"This {eventName} didnt have a table to grab. This was the link {eventURL}"]
    table = tables[0]
    rows = table.find_all('tr')
    
    #grab all onClick links in the fighter table
    fightLinks = []
    winners = []
    for row in rows:
        onclick = row.get('onclick')
        if onclick:
            fightLinks.append(onclick)
    
        #want to find the winner from this table and store for later
        winner_tag = row.find('a', class_='b-link b-link_style_black')
        header_tag = row.find('th')
        if winner_tag and not header_tag:  # Check if the tag exists before calling get_text()
            winner = winner_tag.get_text().strip()
            winners.append(winner)

    #pair
    fightLinks = [fight.split("'")[1] for fight in fightLinks]
    winnerAndLink = list(zip(winners, fightLinks))
    eventStats = [(winner, link, eventID, eventName, eventDate, eventLocation) for winner, link in winnerAndLink]
    return(eventStats)

"""
This is the second part of the original fightStatGrabber method. This is meant to act upon the tuples that are produced by part A.
Its going to take in a tuple labeled eventStats that contains the following information in this exact order:
winner, link, eventID, eventName, eventDate, eventLocation
We're going to grab the link to visit the individual fight page and try to find the top table pertaining to 'Totals' and scrape all of that 
information.
"""
def fightStatGrabberB(eventStats):
    fightStats = []   
    fightLink = eventStats[1]
    time.sleep(1)
    response = requests.get(fightLink)
    soup = BeautifulSoup(response.content, 'html.parser')
        
    tables = soup.find_all('table')
    if tables:
        table = tables[0] 
        stats = table.find_all('p', class_='b-fight-details__table-text')
        currFight = [p.get_text(strip=True) for p in stats]

        #also add in weight class
        weightClass = soup.find("i", class_="b-fight-details__fight-title").get_text(strip=True)
        weight = weightClass.split()[0]
        currFight.append(weight)
        
        currFight.extend(list(eventStats))
        fightStats.append(currFight)
    else:
        return []
    return(fightStats)