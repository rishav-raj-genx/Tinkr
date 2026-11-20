# auth_server.py
import hmac
import os

from flask import Flask, abort, request, session
from google_auth_oauthlib.flow import Flow

from config import config
from logger import get_logger

logger = get_logger("auth_server")

# OAuthlib's HTTP exception is limited to local development. Production must use HTTPS.
if config.FLASK_ENV != "production" and config.GOOGLE_REDIRECT_URI.startswith("http://localhost"):
    os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"

app = Flask(__name__)
app.secret_key = config.SECRET_KEY
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax")

# Build the config dynamically from centralized configuration
client_config = {
    "web": {
        "client_id": config.GOOGLE_CLIENT_ID,
        "client_secret": config.GOOGLE_CLIENT_SECRET,
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
    }
}

# Set up the OAuth flow
SCOPES = [
    'https://www.googleapis.com/auth/calendar',
    'https://www.googleapis.com/auth/gmail.readonly',
    'https://www.googleapis.com/auth/gmail.compose'
    , 'https://www.googleapis.com/auth/tasks'
]

flow = Flow.from_client_config(
    client_config,
    scopes=SCOPES,
    redirect_uri=config.GOOGLE_REDIRECT_URI
)


@app.route('/')
def index():
    auth_url, state = flow.authorization_url(prompt='consent')
    session["oauth_state"] = state
    return f'<h2>AI Calling Assistant</h2><a href="{auth_url}">Click here to Authorize Google Calendar and Gmail</a>'


@app.route('/auth/callback')
def callback():
    expected_state = session.pop("oauth_state", None)
    received_state = request.args.get("state")
    if not expected_state or not received_state or not hmac.compare_digest(expected_state, received_state):
        abort(400, description="Invalid OAuth state")
    flow.fetch_token(authorization_response=request.url)
    creds = flow.credentials

    # Save the credentials for the next run
    config.save_token_json(creds.to_json())

    logger.info("Saved OAuth credentials to %s", config.TOKEN_PATH)
    return "✅ Success! Token has been saved. You can close this window and stop the terminal script."


if __name__ == '__main__':
    logger.info("Starting local auth server on port 8000...")
    logger.info("Open http://localhost:8000 in your browser to log in.")
    app.run(port=8000)
