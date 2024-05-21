import mysql.connector
import boto3
from botocore.exceptions import ClientError
import json
from flask import Flask
app = Flask(__name__)
app.secret_key = 'your-secret-key'

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

from buildWeb import routes