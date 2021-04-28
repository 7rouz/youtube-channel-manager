# internal imports
from app.db_utilities import get_db_connection, init_db_command
from app.user import User
from app.playlist import Playlist



# Python standard libraries
import json
import os

# Third-party libraries
from flask import Flask, redirect, render_template, request, url_for
from werkzeug.exceptions import abort
from flask_login import (
    LoginManager,
    current_user,
    login_required,
    login_user,
    logout_user,
)
from oauthlib.oauth2 import WebApplicationClient
import requests
import sqlite3

# Configuration
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", None)
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", None)
GOOGLE_DISCOVERY_URL = (
    "https://accounts.google.com/.well-known/openid-configuration"
)

def get_post(post_id):
    conn = get_db_connection()
    post = conn.execute('SELECT * FROM posts WHERE id = ?',
                        (post_id,)).fetchone()
    conn.close()
    if post is None:
        abort(404)
    return post

app = Flask(__name__)

app.secret_key = os.environ.get("SECRET_KEY") or os.urandom(24)

# User session management setup
# https://flask-login.readthedocs.io/en/latest
login_manager = LoginManager()
login_manager.init_app(app)

# Naive database setup
try:
    init_db_command()
except sqlite3.OperationalError:
    # Assume it's already been created
    pass

# OAuth 2 client setup
client = WebApplicationClient(GOOGLE_CLIENT_ID)

# Flask-Login helper to retrieve a user from our db
@login_manager.user_loader
def load_user(user_id):
    return User.get(user_id)

def get_google_provider_cfg():
    # TODO: add error handling
    return requests.get(GOOGLE_DISCOVERY_URL).json()

@app.route('/')
def index():
    if current_user.is_authenticated:
        conn = get_db_connection()
        playlists = conn.execute('SELECT * FROM playlist').fetchall()
        conn.close()
        return render_template('index.html', playlists= playlists,name=current_user.name, profile_pic=current_user.profile_pic)
    else:
        return render_template("new_login.html")

@app.route('/<int:post_id>')
def post(post_id):
    post = get_post(post_id)
    return render_template('post.html', post=post)    

# Login
@app.route("/login")
def login():
    # Find out what URL to hit for Google login
    google_provider_cfg = get_google_provider_cfg()
    authorization_endpoint = google_provider_cfg["authorization_endpoint"]

    # Use library to construct the request for Google login and provide
    # scopes that let you retrieve user's profile from Google
    request_uri = client.prepare_request_uri(
        authorization_endpoint,
        redirect_uri=request.base_url + "/callback",
        scope=["openid", "email", "profile", "https://www.googleapis.com/auth/youtube.force-ssl"],
    )
    return redirect(request_uri)

# Callback
@app.route("/login/callback")
def callback():
    # Get authorization code Google sent back to you
    code = request.args.get("code")

    # Get token endpoint 
    google_provider_cfg = get_google_provider_cfg()
    token_endpoint = google_provider_cfg["token_endpoint"]

    # Prepare and send a request to get tokens! Yay tokens!
    token_url, headers, body = client.prepare_token_request(
        token_endpoint,
        authorization_response=request.url,
        redirect_url=request.base_url,
        code=code
    )
    token_response = requests.post(
       token_url,
       headers=headers,
       data=body,
       auth=(GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET),
    )

    # Parse the tokens!
    client.parse_request_body_response(json.dumps(token_response.json()))

    userinfo_endpoint = google_provider_cfg["userinfo_endpoint"]
    uri, headers, body = client.add_token(userinfo_endpoint)
    userinfo_response = requests.get(uri, headers=headers, data=body)

    # You want to make sure their email is verified.
    # The user authenticated with Google, authorized your
    # app, and now you've verified their email through Google!
    if userinfo_response.json().get("email_verified"):
       unique_id = userinfo_response.json()["sub"]
       users_email = userinfo_response.json()["email"]
       picture = userinfo_response.json()["picture"]
       users_name = userinfo_response.json()["given_name"]
    else:
        return "User email not available or not verified by Google.", 400

    # Create a user in your db with the information provided
    # by Google
    user = User(
        id_=unique_id, name=users_name, email=users_email, profile_pic=picture
    )

    # Doesn't exist? Add it to the database.
    if not User.get(unique_id):
        User.create(unique_id, users_name, users_email, picture)

    # Begin user session by logging the user in
    login_user(user)

    # Get playlists (50 is the max results that can be returned)
    yt_uri, yt_headers, yt_body = client.add_token("https://www.googleapis.com/youtube/v3/playlists?part=snippet&mine=true&maxResults=50")
    yt_playlist_response = requests.get(yt_uri, headers=yt_headers, data=yt_body)

    # print(yt_playlist_response.json())
    playlists = yt_playlist_response.json()["items"]
    # get the rest of the playlists if there are any
    while "nextPageToken" in yt_playlist_response.json():
        next_page_token = yt_playlist_response.json()["nextPageToken"]
        yt_uri, yt_headers, yt_body = client.add_token("https://www.googleapis.com/youtube/v3/playlists?part=snippet&mine=true&maxResults=50&pageToken="+next_page_token)
        yt_playlist_response = requests.get(yt_uri, headers=yt_headers, data=yt_body)
        playlists = playlists + yt_playlist_response.json()["items"]

    for playlist in playlists:
        playlist_id = playlist["id"]
        playlist_name = playlist["snippet"]["title"]
        playlist_thumbnail = playlist["snippet"]["thumbnails"]["high"]['url']
        playlist_published_at = playlist["snippet"]["publishedAt"]

        # create a playlist object 
        playlist_obj = Playlist(id_ = playlist_id, name = playlist_name, thumbnail = playlist_thumbnail, published_at = playlist_published_at) 

        # add playlist to local database
        if not Playlist.get(playlist_id):
            Playlist.create(playlist_id, playlist_name, playlist_thumbnail, playlist_published_at)

    # Send user back to homepage
    return redirect(url_for("index"))

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("index"))