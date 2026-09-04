"""Inits our app so that when it's called from run.py everything is ready to build our website"""
from flask import Flask

from ufcPipeline.db import connect

app = Flask(__name__)
app.secret_key = "your-secret-key"

# local profile used when running the site from a workstation
cnx = connect(profile_name="tmpJose")
cursor = cnx.cursor()
