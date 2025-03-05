import streamlit as st
import pandas as pd
import csv
import os
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
import pickle

# Set up Google Drive API constants
SCOPES = ['https://www.googleapis.com/auth/drive.metadata.readonly']
TOKEN_PATH = 'token.pickle'
CREDENTIALS_PATH = 'credentials.json'

def authenticate_google_drive():
    """Authenticate with Google Drive API to get file metadata"""
    creds = None
    
    # Check if token file exists
    if os.path.exists(TOKEN_PATH):
        with open(TOKEN_PATH, 'rb') as token:
            creds = pickle.load(token)
    
    # If no valid credentials, get user to log in
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            try:
                flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_PATH, SCOPES)
                creds = flow.run_local_server(port=0)
                # Save credentials for next run
                with open(TOKEN_PATH, 'wb') as token:
                    pickle.dump(creds, token)
            except FileNotFoundError:
                st.error("credentials.json file not found. Please download OAuth credentials from Google Cloud Console.")
                return None
    
    return build('drive', 'v3', credentials=creds)

def get_folder_contents(service, folder_name):
    """Get all files in a specific folder by name"""
    # First find the folder ID
    folder_results = service.files().list(
        q=f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder' and trashed=false",
        spaces='drive',
        fields='files(id, name)'
    ).execute()
    
    folders = folder_results.get('files', [])
    
    if not folders:
        st.error(f"Folder '{folder_name}' not found in your Google Drive.")
        return []
    
    folder_id = folders[0]['id']
    
    # Then list all files in that folder
    results = service.files().list(
        q=f"'{folder_id}' in parents and trashed=false",
        spaces='drive',
        fields='files(id, name, mimeType)'
    ).execute()
    
    return results.get('files', [])

def generate_direct_urls(files):
    """Convert Google Drive file IDs to direct image URLs"""
    file_data = []
    for file in files:
        if file['mimeType'].startswith('image/'):
            file_data.append({
                'filename': file['name'],
                'file_id': file['id'],
                'direct_url': f"https://drive.google.com/uc?export=view&id={file['id']}"
            })
    return file_data

def update_mapping_csv(file_data, mapping_path, output_path):
    """Update mapping CSV with Google Drive URLs"""
    try:
        # Read the existing mapping file
        df = pd.read_csv(mapping_path)
        
        # Create a dictionary to quickly look up file IDs by filename
        file_dict = {item['filename']: item['direct_url'] for item in file_data}
        
        # Update the google_drive_url column based on matching filenames
        df['google_drive_url'] = df['logo_filename'].map(lambda x: file_dict.get(x, ''))
        
        # Write the updated dataframe to a new CSV file
        df.to_csv(output_path, index=False)
        
        return df, True
    except Exception as e:
        st.error(f"Error updating mapping CSV: {e}")
        return None, False

def generate_manual_mapping(file_data, output_path):
    """Create a new CSV with just filenames and URLs"""
    try:
        with open(output_path, 'w', newline='') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=['filename', 'direct_url'])
            writer.writeheader()
            for item in file_data:
                writer.writerow({
                    'filename': item['filename'],
                    'direct_url': item['direct_url']
                })
        return True
    except Exception as e:
        st.error(f"Error generating manual mapping: {e}")
        return False

def main():
    st.title("Google Drive Image Link Generator")
    st.write("Connect your downloaded logo files with their Google Drive URLs for Webflow CMS")
    
    # Step 1: Connect to Google Drive
    st.header("Step 1: Connect to Google Drive")
    
    drive_service = None
    
    if st.button("Connect to Google Drive"):
        with st.spinner("Authenticating with Google Drive..."):
            drive_service = authenticate_google_drive()
            if drive_service:
                st.session_state.drive_service = drive_service
                st.success("Successfully connected to Google Drive!")
            else:
                st.error("Failed to connect to Google Drive.")
    
    # Use the stored service if authentication was already done
    if 'drive_service' in st.session_state:
        drive_service = st.session_state.drive_service
    
    if drive_service:
        # Step 2: Get folder contents
        st.header("Step 2: Select Your Image Folder")
        
        folder_name = st.text_input("Enter the exact name of your Google Drive folder containing logo images", value="Supplier Logo")
        
        if st.button("List Files in Folder"):
            with st.spinner(f"Fetching files from '{folder_name}'..."):
                files = get_folder_contents(drive_service, folder_name)
                
                if files:
                    # Filter for just image files
                    image_files = [f for f in files if f['mimeType'].startswith('image/')]
                    
                    if image_files:
                        st.session_state.files = files
                        st.session_state.file_data = generate_direct_urls(image_files)
                        st.success(f"Found {len(image_files)} image files in folder '{folder_name}'.")
                    else:
                        st.warning(f"No image files found in folder '{folder_name}'.")
        
        # Step 3: Generate links
        if 'file_data' in st.session_state and st.session_state.file_data:
            st.header("Step 3: Generate and Download Links")
            
            # Option 1: Update existing mapping file
            st.subheader("Option 1: Update Your Existing Mapping File")
            mapping_file = st.file_uploader("Upload your logo_mapping.csv file", type=["csv"])
            
            if mapping_file is not None:
                # Save the uploaded file temporarily
                with open("temp_mapping.csv", "wb") as f:
                    f.write(mapping_file.getbuffer())
                
                if st.button("Update Mapping File"):
                    with st.spinner("Updating mapping file..."):
                        df, success = update_mapping_csv(
                            st.session_state.file_data,
                            "temp_mapping.csv",
                            "updated_mapping.csv"
                        )
                        
                        if success:
                            # Show a preview of the updated file
                            st.write("Preview of updated mapping:")
                            st.dataframe(df.head())
                            
                            # Provide download button
                            with open("updated_mapping.csv", "rb") as file:
                                st.download_button(
                                    label="Download Updated Mapping File",
                                    data=file,
                                    file_name="updated_mapping.csv",
                                    mime="text/csv",
                                    key="updated_mapping"
                                )
            
            # Option 2: Generate simple filename to URL mapping
            st.subheader("Option 2: Generate Simple Filename to URL Mapping")
            
            if st.button("Generate Simple Mapping"):
                with st.spinner("Generating simple filename to URL mapping..."):
                    success = generate_manual_mapping(
                        st.session_state.file_data,
                        "filename_to_url.csv"
                    )
                    
                    if success:
                        # Create a preview dataframe
                        preview_df = pd.DataFrame(st.session_state.file_data)
                        st.write("Preview of filename to URL mapping:")
                        st.dataframe(preview_df[['filename', 'direct_url']].head())
                        
                        # Provide download button
                        with open("filename_to_url.csv", "rb") as file:
                            st.download_button(
                                label="Download Filename to URL Mapping",
                                data=file,
                                file_name="filename_to_url.csv",
                                mime="text/csv",
                                key="filename_mapping"
                            )
            
            # Display all the image files and their direct URLs
            if st.checkbox("Show all image files and their direct URLs"):
                st.subheader("All Images and Direct URLs")
                for item in st.session_state.file_data:
                    st.write(f"**{item['filename']}**")
                    st.write(f"Direct URL: `{item['direct_url']}`")
                    st.write("---")
            
            # Instructions for Webflow
            st.header("Next Steps for Webflow CMS")
            st.markdown("""
            1. Download either the updated mapping file or the simple filename-to-URL mapping
            2. For the updated mapping file, use the `google_drive_url` column in your Webflow CMS import
            3. For the simple mapping, manually merge this data with your other CMS data as needed
            4. In Webflow, these direct URLs will automatically be downloaded and added to your Assets
            """)
    
    else:
        st.info("Please connect to Google Drive to get started.")
        
        # Provide instructions for getting credentials
        st.markdown("""
        ### How to Get Google API Credentials

        1. Go to the [Google Cloud Console](https://console.cloud.google.com/)
        2. Create a new project or select an existing one
        3. Enable the Google Drive API
        4. Create OAuth 2.0 Client ID credentials
        5. Download the credentials as JSON
        6. Rename the file to `credentials.json` and place it in the same directory as this script
        """)

if __name__ == "__main__":
    main()
