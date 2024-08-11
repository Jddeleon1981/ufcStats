"""Builds the basic register form for our website"""
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField


class RegisterForm(FlaskForm):
    """Establishes the different fields we'll need when creating the account"""
    username = StringField(label="User Name:")
    email_address = StringField(label="Email:")
    password = PasswordField(label="Password")
    verify_password = PasswordField(label="Verify Password")
    submit = SubmitField(label="Create Account")
