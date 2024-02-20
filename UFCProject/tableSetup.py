import requests
import mysql.connector
from bs4 import BeautifulSoup
from sqlConfig import loginConfig

"""
This method visits the ufc stats fighters page and grabs the first name, last name, and fighter page url for every zuffa fighter
storing it in a list of tuples
"""
def hyperLinkGrabber(lastNameLetter):
    # Make a request to the website and parse html content
    url = f"http://www.ufcstats.com/statistics/fighters?char={lastNameLetter}&page=all"
    response = requests.get(url)
    soup = BeautifulSoup(response.content, 'html.parser')

    # navigate to the fighter table and extract all rows
    table = soup.find_all('table')[0] 
    rows = table.find_all('tr')

    tmpList = []
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
            tmpList.append(tmpTuple)
    return(tmpList)

#This grabs the fighter detail links for every single fighter on the ufc stats page as its paginated by the first letter of the last name
lastNameLetters = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'i', 'j', 'k', 'l', 'm', 'n', 'o', 'p', 'q', 'r', 's', 't', 'u', 'v', 'w', 'x', 'y', 'z']
allZuffaFighters = [hyperLinkGrabber(lastNameLetter) for lastNameLetter in lastNameLetters]
allZuffaFighters = [fighter for subList in allZuffaFighters for fighter in subList]

cnx = mysql.connector.connect(
    user=loginConfig['user'],
    password=loginConfig['password'],
    host=loginConfig['host'],
    database=loginConfig['database']
)
cursor = cnx.cursor()

#sets up the fighterHyperLink table 
cursor.execute("DROP TABLE IF EXISTS fighterHyperlinks")
cursor.execute("""
    CREATE TABLE fighterHyperlinks (
        fighterID INT AUTO_INCREMENT,
        firstName VARCHAR(255),
        lastName VARCHAR(255),
        hyperlink VARCHAR(255),
        PRIMARY KEY (fighterID)
    )
""")

query = "INSERT INTO fighterHyperlinks (firstName, lastName, hyperlink) VALUES (%s, %s, %s)"

# Insert the data
cursor.executemany(query, allZuffaFighters)
cnx.commit()
cursor.close()
cnx.close()