import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
import os
import uuid
from urllib.parse import urljoin, urlparse
from PIL import Image
from io import BytesIO
import time

# Google Drive API imports
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
import pickle

# Constants for Google API
SCOPES = ['https://www.googleapis.com/auth/drive.file']
TOKEN_PATH = 'token.pickle'
CREDENTIALS_PATH = 'credentials.json'

class GoogleDriveUploader:
    def __init__(self):
        self.drive_service = self._authenticate()
        self.folder_id = self._get_or_create_folder("Website_Logos")
        
    def _authenticate(self):
        """Authenticate with Google Drive API"""
        creds = None
        
        # Load credentials from saved token
        if os.path.exists(TOKEN_PATH):
            with open(TOKEN_PATH, 'rb') as token:
                creds = pickle.load(token)
                
        # Check if credentials are valid or need refresh
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                # If no valid credentials, need to authenticate
                if not os.path.exists(CREDENTIALS_PATH):
                    st.error("Missing credentials.json file. Please download it from Google Cloud Console.")
                    st.info("Instructions: \n1. Go to Google Cloud Console\n2. Create a project\n3. Enable Drive API\n4. Create OAuth credentials\n5. Download as credentials.json")
                    return None
                    
                flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_PATH, SCOPES)
                creds = flow.run_local_server(port=0)
                
            # Save the credentials
            with open(TOKEN_PATH, 'wb') as token:
                pickle.dump(creds, token)
                
        return build('drive', 'v3', credentials=creds)
    
    def _get_or_create_folder(self, folder_name):
        """Get ID of existing folder or create a new one"""
        if not self.drive_service:
            return None
            
        # Search for existing folder
        response = self.drive_service.files().list(
            q=f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder' and trashed=false",
            spaces='drive',
            fields='files(id, name)'
        ).execute()
        
        folders = response.get('files', [])
        
        # Return existing folder ID if found
        if folders:
            return folders[0]['id']
            
        # Create new folder
        folder_metadata = {
            'name': folder_name,
            'mimeType': 'application/vnd.google-apps.folder'
        }
        
        folder = self.drive_service.files().create(
            body=folder_metadata,
            fields='id'
        ).execute()
        
        return folder.get('id')
    
    def upload_image(self, file_path, filename=None):
        """Upload image to Google Drive and return sharing link"""
        if not self.drive_service or not self.folder_id:
            return None
            
        if not filename:
            filename = os.path.basename(file_path)
            
        file_metadata = {
            'name': filename,
            'parents': [self.folder_id]
        }
        
        media = MediaFileUpload(
            file_path,
            mimetype='image/*',
            resumable=True
        )
        
        # Upload file
        file = self.drive_service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id,webViewLink'
        ).execute()
        
        # Make file publicly accessible
        self.drive_service.permissions().create(
            fileId=file.get('id'),
            body={
                'role': 'reader',
                'type': 'anyone'
            }
        ).execute()
        
        # Get direct download link (useful for Webflow)
        download_link = f"https://drive.google.com/uc?export=view&id={file.get('id')}"
        
        return {
            'file_id': file.get('id'),
            'view_link': file.get('webViewLink'),
            'download_link': download_link
        }

def get_site_logo(url):
    """
    Scrape a website to find and download its logo image.
    Returns the path to the downloaded image or None if no logo was found.
    """
    # Make sure URL has proper format
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    
    try:
        # Send a request to get the website content
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()  # Raise exception for HTTP errors
        
        # Parse the HTML content
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Look for common logo patterns
        logo_candidates = []
        
        # 1. Check for link tags with 'icon' or 'logo' in the rel attribute
        for link in soup.find_all('link'):
            rel = link.get('rel', [])
            if isinstance(rel, list):
                rel = ' '.join(rel).lower()
            else:
                rel = str(rel).lower()
                
            if ('icon' in rel or 'logo' in rel) and link.get('href'):
                logo_candidates.append(link.get('href'))
        
        # 2. Look for images with 'logo' in the class, id, or alt attribute
        for img in soup.find_all('img'):
            for attr in ['class', 'id', 'alt', 'src']:
                value = img.get(attr, '')
                if isinstance(value, list):
                    value = ' '.join(value)
                else:
                    value = str(value)
                    
                if 'logo' in value.lower() and img.get('src'):
                    logo_candidates.append(img.get('src'))
        
        # If no logo candidates found, look for the first image in the header
        if not logo_candidates:
            header = soup.find('header')
            if header:
                img = header.find('img')
                if img and img.get('src'):
                    logo_candidates.append(img.get('src'))
        
        # Process logo candidates
        for img_url in logo_candidates:
            # Convert relative URLs to absolute URLs
            img_url = urljoin(url, img_url)
            
            try:
                # Download the image
                img_response = requests.get(img_url, headers=headers, timeout=10)
                img_response.raise_for_status()
                
                # Check if it's a valid image
                img = Image.open(BytesIO(img_response.content))
                
                # Generate a unique filename
                domain = urlparse(url).netloc
                filename = f"{domain.replace('.', '_')}_{uuid.uuid4().hex[:8]}.{img.format.lower() if img.format else 'png'}"
                
                # Create images directory if it doesn't exist
                os.makedirs('logos', exist_ok=True)
                
                # Save the image
                img_path = os.path.join('logos', filename)
                img.save(img_path)
                
                return img_path
            
            except Exception as e:
                continue  # Try the next candidate if this one fails
        
        return None  # No valid logo found
        
    except Exception as e:
        st.error(f"Error processing {url}: {str(e)}")
        return None

def main():
    st.title("Website Logo Scraper with Google Drive Integration")
    st.write("Upload an Excel file with website URLs to extract logos and upload them to Google Drive")
    
    # Check for credentials
    if not os.path.exists(CREDENTIALS_PATH):
        st.warning("Google Drive API credentials not found.")
        st.info("""
        To use Google Drive integration, you need to:
        1. Go to [Google Cloud Console](https://console.cloud.google.com/)
        2. Create a new project
        3. Enable the Google Drive API
        4. Create OAuth 2.0 Client ID credentials
        5. Download the credentials as JSON
        6. Rename the file to `credentials.json` and place it in the same directory as this script
        """)
        
        # Option to continue without Google Drive
        use_drive = st.checkbox("I'll add Google Drive integration later, continue without it", value=True)
        if not use_drive:
            return
    else:
        use_drive = True
    
    # Initialize Google Drive uploader if enabled
    drive_uploader = None
    if use_drive and os.path.exists(CREDENTIALS_PATH):
        with st.spinner("Authenticating with Google Drive..."):
            drive_uploader = GoogleDriveUploader()
            if drive_uploader.drive_service:
                st.success("Connected to Google Drive!")
            else:
                st.error("Failed to connect to Google Drive.")
                return
    
    uploaded_file = st.file_uploader("Choose an Excel file", type=["xlsx", "xls"])
    
    if uploaded_file:
        try:
            # Read the Excel file
            df = pd.read_excel(uploaded_file)
            
            # Check if the DataFrame has any columns
            if df.empty or len(df.columns) == 0:
                st.error("The uploaded file is empty or has no columns.")
                return
            
            # Let the user select the column containing URLs
            url_column = st.selectbox("Select the column containing website URLs", df.columns)
            
            if st.button("Extract Logos"):
                # Add a progress bar
                progress_bar = st.progress(0)
                status_text = st.empty()
                
                # Create new columns for results
                df['logo_path'] = None
                if drive_uploader:
                    df['drive_view_link'] = None
                    df['drive_download_link'] = None
                
                # Process each URL
                for i, row in df.iterrows():
                    url = str(row[url_column])
                    status_text.text(f"Processing {i+1}/{len(df)}: {url}")
                    
                    # Get the logo
                    logo_path = get_site_logo(url)
                    
                    # Update the DataFrame with local path
                    df.at[i, 'logo_path'] = logo_path
                    
                    # Upload to Google Drive if enabled and logo was found
                    if drive_uploader and logo_path:
                        with st.spinner(f"Uploading logo for {url} to Google Drive..."):
                            upload_result = drive_uploader.upload_image(logo_path)
                            if upload_result:
                                df.at[i, 'drive_view_link'] = upload_result['view_link']
                                df.at[i, 'drive_download_link'] = upload_result['download_link']
                    
                    # Update progress
                    progress_bar.progress((i + 1) / len(df))
                    
                    # Small delay to prevent overwhelming websites
                    time.sleep(0.5)
                
                # Save the results
                output_filename = "logos_extracted.xlsx"
                df.to_excel(output_filename, index=False)
                
                # Provide download button for the resulting Excel file
                with open(output_filename, "rb") as file:
                    st.download_button(
                        label="Download Results",
                        data=file,
                        file_name=output_filename,
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
                
                # Display the results
                success_count = df['logo_path'].notna().sum()
                st.success(f"Processed {len(df)} websites. Successfully extracted {success_count} logos.")
                
                # Show the logos that were found
                st.subheader("Extracted Logos")
                for i, row in df[df['logo_path'].notna()].iterrows():
                    col1, col2 = st.columns([1, 2])
                    with col1:
                        st.write(f"**{row[url_column]}**")
                        st.image(row['logo_path'], width=150)
                    with col2:
                        if drive_uploader and pd.notna(row.get('drive_download_link')):
                            st.write("**Google Drive Links:**")
                            st.write(f"View: [{row['drive_view_link']}]({row['drive_view_link']})")
                            st.write(f"**Direct link for Webflow:** [{row['drive_download_link']}]({row['drive_download_link']})")
                            st.markdown("---")
        
        except Exception as e:
            st.error(f"An error occurred: {str(e)}")

if __name__ == "__main__":
    main()
