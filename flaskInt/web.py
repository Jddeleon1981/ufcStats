from flask import Flask, request
from flask import render_template
import mysql.connector
import boto3
from botocore.exceptions import ClientError
import json
from collections import namedtuple
app = Flask(__name__)


def getSecret() -> dict:

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

dbCredentials = getSecret()
cnx = mysql.connector.connect(
    user=dbCredentials['username'],
    password=dbCredentials['password'],
    host=dbCredentials['host'],
    database=dbCredentials['dbInstanceIdentifier']
)
cursor = cnx.cursor()

@app.route("/")
@app.route("/home")
def homePage():
    return render_template('home.html', currentPage='home')

@app.route("/blog")
def blogPage():
    return render_template('blog.html', currentPage='blog')

@app.route("/feedback")
def contactPage():
    return render_template('contact.html', currentPage='contact')

@app.route('/stats')
def statsPage():
    page = request.args.get('page', 1, type=int)
    Fighter = namedtuple('Fighter', 'firstName lastName DOB')
    query = f"""
    select firstName, lastName, DOB
    FROM fighterHyperlinks
    LIMIT %s OFFSET %s
    """
    cursor.execute(query, (25, 25*(page-1)))
    fighters = cursor.fetchall()
    fighters = [Fighter(*fighter) for fighter in fighters]

    return render_template('stat.html', fighters=fighters, page=page, currentPage='stats')

@app.route('/fighter/<int:fighterID>')
def fighterPage(fighterID):
    return render_template('fighter.html', fighterID=fighterID)