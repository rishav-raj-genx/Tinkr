# auth_server.py
import os
from flask import Flask, request
from google_auth_oauthlib.flow import Flow
from dotenv import load_dotenv

load_dotenv()

# Allow HTTP traffic for local localhost testing
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

app = Flask(__name__)

# Build the config dynamically from your .env file
client_config = {
    "web": {
        "client_id": os.getenv("GOOGLE_CLIENT_ID"),
        "client_secret": os.getenv("GOOGLE_CLIENT_SECRET"),
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
    }
}

# Set up the OAuth flow
SCOPES = [
    'https://www.googleapis.com/auth/calendar',
    'https://www.googleapis.com/auth/gmail.readonly',
    'https://www.googleapis.com/auth/gmail.compose'
]

flow = Flow.from_client_config(
    client_config,
    scopes=SCOPES,
    redirect_uri=os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:8000/auth/callback")
)

@app.route('/')
def index():
    auth_url, _ = flow.authorization_url(prompt='consent')
    return f'<h2>AI Calling Assistant</h2><a href="{auth_url}">Click here to Authorize Google Calendar and Gmail</a>'

@app.route('/auth/callback')
def callback():
    flow.fetch_token(authorization_response=request.url)
    creds = flow.credentials
    
    # Save the credentials for the next run
    with open('token.json', 'w') as f:
        f.write(creds.to_json())
        
    return "✅ Success! token.json has been saved. You can close this window and stop the terminal script."

if __name__ == '__main__':
    print("🚀 Starting local auth server...")
    print("👉 Open http://localhost:8000 in your browser to log in.")
    app.run(port=8000)