from os import environ

from flask import session
from requests_oauthlib import OAuth2Session


API_ENDPOINT = "https://discord.com/api/v6"
AUTHORIZATION_BASE_URL = API_ENDPOINT + "/oauth2/authorize"
TOKEN_URL = API_ENDPOINT + "/oauth2/token"

CLIENT_ID = environ.get("CLIENT_ID")
CLIENT_SECRET = environ.get("CLIENT_SECRET")
REDIRECT_URI = f"{environ.get('REDIRECT_URI')}/login/callback"


def token_updater(token):
    session["oauth2_token"] = token


def make_session(token=None, state=None, scope=None):
    return OAuth2Session(
        client_id=CLIENT_ID,
        token=token,
        state=state,
        scope=scope,
        redirect_uri=REDIRECT_URI,
        auto_refresh_kwargs={
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
        },
        auto_refresh_url=TOKEN_URL,
        token_updater=token_updater)


def get_user(oauth2_session):
    return oauth2_session.get(API_ENDPOINT + "/users/@me").json()


def get_guilds(oauth2_session):
    return oauth2_session.get(API_ENDPOINT + "/users/@me/guilds").json()


def get_managed_guilds(guilds):
    return list(filter(lambda g: (g["owner"] is True) or bool((int(g["permissions"]) >> 5) & 1), guilds))
