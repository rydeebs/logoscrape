import streamlit as st
import pandas as pd
import json
import os
from google.oauth2 import service_account
from googleapiclient.discovery import build
from io import BytesIO

def authenticate_with_service_account(json_content):
    """Authenticate using a service account JSON key"""
    try:
        # Parse the JSON content
        if isinstance(json_content, str):
            credentials_info = json.loads(json_content)
        else:
            credentials_info = json_content
        
        # Create credentials
        credentials = service_account.Credentials.from_service_account_info(
            credentials_info, 
            scopes=['https://www.googleapis.com/auth/drive.readonly']
        )
        
        # Build the service
        drive_service = build('drive', 'v3', credentials=credentials)
        return drive_service, None
    except Exception as e:
        return None, str(e)

def get_folder_files(drive_service, folder_id):
    """Get all files in a specific Google Drive folder"""
    try:
        # List all files in the folder
        results = drive_service.files().list(
            q=f"'{folder_id}' in parents and trashed=false",
            fields="files(id, name, mimeType, webContentLink)",
            pageSize=1000
        ).execute()
        
        files = results.get('files', [])
        
        # If there are more files, get them with pagination
        page_token = results.get('nextPageToken')
        while page_token:
            results = drive_service.files().list(
                q=f"'{folder_id}' in parents and trashed=false",
                fields="files(id, name, mimeType, webContentLink)",
                pageSize=1000,
                pageToken=page_token
            ).execute()
            
            files.extend(results.get('files', []))
            page_token = results.get('nextPageToken')
        
        # Filter for image files only
        image_files = [f for f in files if f['mimeType'].startswith('image/')]
        
        # Add direct URL to each file
        for file in image_files:
            file['direct_url'] = f"https://drive.google.com/uc?export=view&id={file['id']}"
        
        return image_files, None
    except Exception as e:
        return None, str(e)

def update_mapping_csv(file_data, mapping_df):
    """Update mapping DataFrame with Google Drive URLs"""
    try:
        # Create a dictionary to quickly look up file IDs by filename
        file_dict = {item['name']: item['direct_url'] for item in file_data}
        
        # Update the google_drive_url column based on matching filenames
        mapping_df['google_drive_url'] = mapping_df['logo_filename'].map(lambda x: file_dict.get(x, ''))
        
        return mapping_df, True
    except Exception as e:
        return None, str(e)

def main():
    st.title("Google Drive Bulk URL Generator")
    st.write("Generate direct URLs for thousands of images in your Google Drive folder")
    
    st.header("Step 1: Set Up Google Drive Access")
    
    st.markdown("""
    ### Using a Service Account for Authentication
    
    For bulk processing thousands of images, you'll need to use a Google Service Account:
    
    1. Go to [Google Cloud Console](https://console.cloud.google.com)
    2. Create a project (or select existing one)
    3. Enable the Google Drive API
    4. Go to "IAM & Admin" > "Service Accounts"
    5. Create a Service Account
    6. Create a JSON key for the service account
    7. Download the JSON key
    8. Share your Google Drive folder with the service account email (it looks like `name@project-id.iam.gserviceaccount.com`)
    
    Then upload the JSON key file below:
    """)
    
    # Service account key upload
    service_account_key = st.file_uploader("Upload Service Account JSON key", type=["json"])
    
    if service_account_key:
        # Read the key content
        key_content = json.load(service_account_key)
        
        # Store in session state
        st.session_state.key_content = key_content
        
        # Show service account email for sharing
        if 'client_email' in key_content:
            st.info(f"Share your Google Drive folder with this email: **{key_content['client_email']}**")
    
    # Step 2: Get folder ID
    st.header("Step 2: Get Your Google Drive Folder ID")
    
    st.markdown("""
    1. Open your Google Drive folder containing the logo images
    2. The folder ID is the string after `folders/` in the URL
    
    For example, in `https://drive.google.com/drive/folders/1AbCdEfGhIj-KlMnOpQr`, the folder ID is `1AbCdEfGhIj-KlMnOpQr`
    """)
    
    folder_id = st.text_input("Enter your Google Drive folder ID")
    
    # Process the folder
    if folder_id and st.button("Process Folder") and 'key_content' in st.session_state:
        with st.spinner("Connecting to Google Drive..."):
            # Authenticate
            drive_service, error = authenticate_with_service_account(st.session_state.key_content)
            
            if error:
                st.error(f"Authentication failed: {error}")
            elif drive_service:
                # Get files from the folder
                with st.spinner(f"Fetching files from folder..."):
                    files, error = get_folder_files(drive_service, folder_id)
                    
                    if error:
                        st.error(f"Error fetching files: {error}")
                    elif files:
                        # Store in session state
                        st.session_state.files = files
                        
                        # Display summary
                        st.success(f"Found {len(files)} image files in the folder")
                        
                        # Show preview
                        preview_df = pd.DataFrame([
                            {'filename': f['name'], 'direct_url': f['direct_url']}
                            for f in files[:5]  # Just show first 5 for preview
                        ])
                        st.write("Preview of first 5 files:")
                        st.dataframe(preview_df)
                    else:
                        st.warning("No image files found in the specified folder")
    
    # Step 3: Generate mapping
    if 'files' in st.session_state and st.session_state.files:
        st.header("Step 3: Create or Update Mapping")
        
        # Option 1: Simple mapping
        if st.button("Generate Simple Mapping CSV"):
            file_data = [{'filename': f['name'], 'direct_url': f['direct_url']} for f in st.session_state.files]
            df = pd.DataFrame(file_data)
            
            # Convert to CSV
            csv = df.to_csv(index=False)
            
            # Offer download
            st.download_button(
                label="Download Simple Mapping CSV",
                data=csv,
                file_name="filename_to_url.csv",
                mime="text/csv",
                key="simple_mapping"
            )
        
        # Option 2: Update existing mapping
        st.subheader("Option 2: Update Your Existing Mapping CSV")
        
        mapping_file = st.file_uploader("Upload your logo_mapping.csv file", type=["csv"])
        
        if mapping_file is not None:
            try:
                # Read the mapping file
                mapping_df = pd.read_csv(mapping_file)
                
                if st.button("Update Mapping File"):
                    # Update the mapping
                    updated_df, success = update_mapping_csv(st.session_state.files, mapping_df)
                    
                    if success:
                        # Preview
                        st.write("Preview of updated mapping:")
                        st.dataframe(updated_df.head())
                        
                        # Convert to CSV
                        csv = updated_df.to_csv(index=False)
                        
                        # Offer download
                        st.download_button(
                            label="Download Updated Mapping CSV",
                            data=csv,
                            file_name="updated_mapping.csv",
                            mime="text/csv",
                            key="updated_mapping"
                        )
                        
                        # Show match statistics
                        matched = updated_df['google_drive_url'].notna().sum()
                        total = len(updated_df)
                        st.info(f"Successfully matched {matched} out of {total} logos ({matched/total*100:.1f}%)")
                    else:
                        st.error(f"Error updating mapping: {success}")
                
            except Exception as e:
                st.error(f"Error processing mapping file: {str(e)}")
        
        # Option 3: Export full file list
        st.subheader("Option 3: Export Complete File List")
        
        if st.button("Export Complete File List"):
            # Create a complete DataFrame with all metadata
            full_df = pd.DataFrame([
                {
                    'filename': f['name'], 
                    'file_id': f['id'],
                    'mime_type': f['mimeType'],
                    'direct_url': f['direct_url']
                }
                for f in st.session_state.files
            ])
            
            # Convert to CSV
            csv = full_df.to_csv(index=False)
            
            # Offer download
            st.download_button(
                label="Download Complete File List CSV",
                data=csv,
                file_name="complete_file_list.csv",
                mime="text/csv",
                key="complete_list"
            )
        
        # Instructions for Webflow
        st.header("Next Steps for Webflow CMS")
        st.markdown("""
        1. Download either the simple mapping or updated mapping file
        2. For the updated mapping file, use the `google_drive_url` column in your Webflow CMS import
        3. For the simple mapping, manually merge this data with your other CMS data as needed
        4. In Webflow, these direct URLs will automatically be downloaded and added to your Assets
        """)

if __name__ == "__main__":
    main()
