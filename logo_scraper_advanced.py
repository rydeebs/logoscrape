import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
import os
import uuid
import base64
import json
from urllib.parse import urljoin, urlparse
from PIL import Image
from io import BytesIO
import time

# Google Drive API imports
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

# Constants for Google API
SCOPES = ['https://www.googleapis.com/auth/drive.file']

class GoogleDriveUploader:
    def __init__(self):
        # Get credentials from Streamlit secrets or environment
        self.drive_service = self._authenticate()
        if self.drive_service:
            self.folder_id = self._get_or_create_folder("Website_Logos")
        else:
            self.folder_id = None
        
    def _authenticate(self):
        """Authenticate with Google Drive API using stored credentials"""
        try:
            # Try to get credentials from Streamlit secrets
            if 'google_credentials' in st.secrets:
                creds_info = st.secrets['google_credentials']
                creds = Credentials(
                    token=creds_info.get('token'),
                    refresh_token=creds_info.get('refresh_token'),
                    token_uri=creds_info.get('token_uri', 'https://oauth2.googleapis.com/token'),
                    client_id=creds_info.get('client_id'),
                    client_secret=creds_info.get('client_secret'),
                    scopes=SCOPES
                )
                
                # Refresh if expired
                if creds.expired:
                    creds.refresh(Request())
                    
                return build('drive', 'v3', credentials=creds)
            else:
                # Fallback to check if credentials are passed as file
                st.warning("Google Drive credentials not found in Streamlit secrets.")
                
                # Check if credentials.json exists for local development
                if os.path.exists('credentials.json'):
                    st.info("Using credentials.json file for authentication.")
                    creds_upload = st.file_uploader("Upload service account JSON key file", type=['json'])
                    
                    if creds_upload:
                        creds_dict = json.load(creds_upload)
                        creds = Credentials.from_authorized_user_info(creds_dict, SCOPES)
                        
                        # Refresh if expired
                        if creds.expired and creds.refresh_token:
                            creds.refresh(Request())
                            
                        return build('drive', 'v3', credentials=creds)
                
                st.error("""
                To use Google Drive integration in cloud deployment:
                
                1. Go to Streamlit dashboard → App settings → Secrets
                2. Add your Google API credentials in the following format:
                
                ```
                [google_credentials]
                token = "your_token"
                refresh_token = "your_refresh_token"
                token_uri = "https://oauth2.googleapis.com/token"
                client_id = "your_client_id"
                client_secret = "your_client_secret"
                ```
                """)
                
                return None
                
        except Exception as e:
            st.error(f"Error authenticating with Google Drive: {str(e)}")
            return None
    
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
    
    # Detect if running in Streamlit Cloud
    is_cloud = os.environ.get('STREAMLIT_SHARING', '') or os.environ.get('STREAMLIT_CLOUD', '')
    
    # Initialize Google Drive uploader
    drive_uploader = None
    with st.spinner("Checking Google Drive authentication..."):
        drive_uploader = GoogleDriveUploader()
        if drive_uploader.drive_service:
            st.success("Connected to Google Drive!")
        else:
            st.warning("Not connected to Google Drive. Logos will be extracted but not uploaded.")
    
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
                if drive_uploader and drive_uploader.drive_service:
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
                    if drive_uploader and drive_uploader.drive_service and logo_path:
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
                    file_data = file.read()
                    st.download_button(
                        label="Download Results",
                        data=file_data,
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
                        if drive_uploader and drive_uploader.drive_service and pd.notna(row.get('drive_download_link')):
                            st.write("**Google Drive Links:**")
                            st.write(f"View: [{row['drive_view_link']}]({row['drive_view_link']})")
                            st.write(f"**Direct link for Webflow:** [{row['drive_download_link']}]({row['drive_download_link']})")
                            st.markdown("---")
        
        except Exception as e:
            st.error(f"An error occurred: {str(e)}")
            st.exception(e)

if __name__ == "__main__":
    main()
