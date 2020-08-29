import os
from flask import Flask, render_template, redirect, request, url_for, abort

from web.utilities import *


app = Flask("Ice Cube")
app.secret_key = CLIENT_SECRET


@app.context_processor
def override_url_for():
    return dict(url_for=dated_url_for)


def dated_url_for(endpoint, **values):
    if endpoint == "static":
        filename = values.get("filename", None)
        if filename:
            file_path = os.path.join(app.root_path, endpoint, filename)
            values["q"] = int(os.stat(file_path).st_mtime)

    return url_for(endpoint, **values)


@app.route("/")
def index():
    token = session.get("oauth2_token")

    if token:
        discord = make_session(token=session.get("oauth2_token"))
        user = get_user(discord)

        data = {
            "auth": True,
            "username": user["username"]
        }
    else:
        data = {"auth": False}

    return render_template("index.html", **data)


@app.route("/invite_bot")
def invite_bot():
    return redirect("https://discord.com/oauth2/authorize?client_id=637682828284395530&scope=bot&permissions=8")


@app.route("/login")
def login():
    discord = make_session(scope="identify guilds")
    authorization_url, state = discord.authorization_url(AUTHORIZATION_BASE_URL)

    session["oauth2_state"] = state

    return redirect(authorization_url)


@app.route("/login/callback", methods=["get"])
def login_callback():
    if request.values.get("error"):
        return request.values["error"]

    discord = make_session(state=session.get("oauth2_state"))
    token = discord.fetch_token(
        TOKEN_URL,
        client_secret=CLIENT_SECRET,
        authorization_response=request.url)

    session["oauth2_token"] = token

    return redirect(url_for(".guilds_list"))


@app.route("/logout")
def logout():
    if "oauth2_token" in session.keys():
        del session["oauth2_token"]
    else:
        abort(401)

    return redirect(url_for(".index"))


@app.route("/guilds")
def guilds_list():
    token = session.get("oauth2_token")

    if not token:
        abort(401)

    discord = make_session(token)
    user = get_user(discord)
    guilds = get_managed_guilds(get_guilds(discord))
    print(guilds)

    data = {
        "username": user["username"],
        "guilds": guilds
    }

    return render_template("guilds.html", **data)


@app.route("/guild/<int:server_id>")
def guild_settings(server_id):
    token = session.get("oauth2_token")

    if not token:
        abort(401)

    discord = make_session(token)
    managed_guilds = get_managed_guilds(get_guilds(discord))
    data = {}

    for g in managed_guilds:
        if g["id"] == str(server_id):
            data["guild"] = g
            break
    else:
        abort(403)

    user = get_user(discord)
    data["username"] = user["username"]

    settings = {
        "prefix": ".",
        "levelup_message": "$member_mention получил `$level уровень`"
    }

    return render_template("guild_settings.html", **data, settings=settings)


if __name__ == '__main__':
    app.run()
