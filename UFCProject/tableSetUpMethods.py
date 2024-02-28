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