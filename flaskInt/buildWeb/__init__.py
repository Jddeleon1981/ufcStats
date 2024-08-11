"""Inits our app so that when it's called from run.py everything is ready to build our website"""
import json
import boto3
import mysql.connector
from botocore.exceptions import ClientError
from flask import Flask

app = Flask(__name__)
app.secret_key = "your-secret-key"


def get_secret() -> dict:
    """Retrieves db info from aws secrets manager"""
    secret_name = "ufcDBcred"
    region_name = "us-west-1"

    # create client
    session = boto3.session.Session(profile_name="tmpJose")
    client = session.client(service_name="secretsmanager", region_name=region_name)
    try:
        get_secret_value_response = client.get_secret_value(SecretId=secret_name)
    except ClientError as e:
        raise e

    # format as dict before returning
    secret = get_secret_value_response["SecretString"]
    return json.loads(secret)


db_credentials = get_secret()
cnx = mysql.connector.connect(
    user=db_credentials["username"],
    password=db_credentials["password"],
    host=db_credentials["host"],
    database=db_credentials["dbInstanceIdentifier"],
)
cursor = cnx.cursor()
