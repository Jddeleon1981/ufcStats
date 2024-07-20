from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField


class registerForm(FlaskForm):
    username = StringField(label="User Name:")
    emailAddress = StringField(label="Email:")
    password = PasswordField(label="Password")
    verifyPassword = PasswordField(label="Verify Password")
    submit = SubmitField(label="Create Account")
