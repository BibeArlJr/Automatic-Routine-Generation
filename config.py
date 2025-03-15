# config.py
import os

class Config:
    SECRET_KEY = os.getenv('SECRET_KEY', 'your_unique_secret_key')
    MAIL_SERVER = 'smtp.gmail.com'
    MAIL_PORT = 465
    MAIL_USERNAME = 'bibekaryal717@gmail.com'
    MAIL_PASSWORD = 'tgum rjoz gqnb onhv'
    MAIL_USE_TLS = False
    MAIL_USE_SSL = True
    MONGO_URI = "mongodb+srv://major:project@majorproject.nrvy0xw.mongodb.net/"
    TWILIO_ACCOUNT_SID = 'ACb01c1959644a84b93f30a62b22ffd924'
    TWILIO_AUTH_TOKEN = 'ec0e71bc19aeafb6be4557a0001fcf51'
    TWILIO_VERIFY_SERVICE_SID = 'VA2e656ce8b504e5ae179a26c9ccb20cac'


