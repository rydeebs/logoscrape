from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
import pickle
import json

# Define the scopes
SCOPES = ['https://www.googleapis.com/auth/drive.file']

# Create the flow
flow = InstalledAppFlow.from_client_secrets_file(
    'credentials.json',  # Your downloaded credentials
    scopes=SCOPES
)

# Run the OAuth flow
creds = flow.run_local_server(port=0)

# Save credentials to a JSON format that can be used in Streamlit secrets
creds_data = {
    'token': creds.token,
    'refresh_token': creds.refresh_token,
    'token_uri': creds.token_uri,
    'client_id': creds.client_id,
    'client_secret': creds.client_secret,
}

# Print the credentials in a format ready for Streamlit secrets
print("\n\n=== COPY THIS INTO YOUR STREAMLIT SECRETS ===\n")
print("[google_credentials]")
for key, value in creds_data.items():
    print(f'{key} = "{value}"')

# Save to a file for backup
with open('google_creds_for_streamlit.json', 'w') as f:
    json.dump(creds_data, f)
    
print("\nCredentials also saved to 'google_creds_for_streamlit.json'")
