import streamlit as st
import pandas as pd
import json
import os
import time
from google.oauth2 import service_account
from googleapiclient.discovery import build
from io import BytesIO, StringIO
import concurrent.futures

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

def get_folder_files(drive_service, folder_id, progress_bar=None, status_text=None):
    """Get all files in a specific Google Drive folder with pagination"""
    try:
        all_files = []
        page_token = None
        page_count = 0
        
        # Update initial status
        if status_text:
            status_text.text("Fetching files from Google Drive... (page 1)")
        
        # Keep fetching pages until there are no more
        while True:
            # Construct the query
            query = f"'{folder_id}' in parents and trashed=false"
            
            # Make the API request
            results = drive_service.files().list(
                q=query,
                fields="nextPageToken, files(id, name, mimeType)",
                pageSize=1000,  # Maximum allowed by API
                pageToken=page_token
            ).execute()
            
            # Get the current batch of files
            batch_files = results.get('files', [])
            all_files.extend(batch_files)
            
            # Update progress
            page_count += 1
            if status_text:
                status_text.text(f"Fetching files from Google Drive... (page {page_count}, found {len(all_files)} files so far)")
            
            # Get the next page token
            page_token = results.get('nextPageToken')
            
            # If no more pages, break the loop
            if not page_token:
                break
        
        # Filter for image files only
        image_files = [f for f in all_files if f.get('mimeType', '').startswith('image/')]
        
        # Final status update
        if status_text:
            status_text.text(f"Processing {len(image_files)} image files...")
        
        # Add direct URL to each file
        for file in image_files:
            file['direct_url'] = f"https://drive.google.com/uc?export=view&id={file['id']}"
        
        return image_files, None
    except Exception as e:
        return None, str(e)

def update_mapping_csv(file_data, mapping_df, progress_bar=None):
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
    st.set_page_config(page_title="Google Drive Bulk URL Generator", layout="wide")
    
    st.title("Google Drive Bulk URL Generator for 2500+ Images")
    st.write("Generate direct URLs for thousands of images in your Google Drive folder")
    
    # Add a sidebar for processing status/logs
    status_sidebar = st.sidebar.empty()
    
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
    8. Share your Google Drive folder with the service account email
    
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
    
    # Display improved instructions for error avoidance
    st.warning("**IMPORTANT:** Enter ONLY the folder ID, not the entire URL. The folder ID is the part after 'folders/' in your browser address bar.")
    
    # Add processing options
    st.header("Step 3: Processing Options")
    
    # Process the folder
    if folder_id and st.button("Process Folder") and 'key_content' in st.session_state:
        # Clear previous results
        if 'files' in st.session_state:
            del st.session_state.files
        
        # Set up progress tracking
        progress_bar = st.progress(0)
        status_text = st.empty()
        status_text.text("Connecting to Google Drive...")
        
        with st.spinner("Processing..."):
            # Authenticate
            drive_service, error = authenticate_with_service_account(st.session_state.key_content)
            
            if error:
                st.error(f"Authentication failed: {error}")
            elif drive_service:
                # Get files from the folder
                status_text.text("Fetching files from folder...")
                files, error = get_folder_files(drive_service, folder_id, progress_bar, status_text)
                
                if error:
                    st.error(f"Error fetching files: {error}")
                elif files:
                    # Store in session state
                    st.session_state.files = files
                    
                    # Display summary
                    st.success(f"Found {len(files)} image files in the folder")
                    
                    # Show preview in a scrollable container
                    with st.expander("Preview of files (first 20 shown)"):
                        preview_df = pd.DataFrame([
                            {'filename': f['name'], 'direct_url': f['direct_url']}
                            for f in files[:20]  # Just show first 20 for preview
                        ])
                        st.dataframe(preview_df)
                    
                    # Show more detailed stats
                    st.subheader("File Statistics")
                    
                    # Get file extensions
                    extensions = {}
                    for f in files:
                        ext = os.path.splitext(f['name'])[1].lower()
                        extensions[ext] = extensions.get(ext, 0) + 1
                    
                    # Display extension counts
                    ext_df = pd.DataFrame([
                        {'Extension': ext, 'Count': count}
                        for ext, count in extensions.items()
                    ]).sort_values('Count', ascending=False)
                    
                    st.write("Files by extension:")
                    st.dataframe(ext_df)
                else:
                    st.warning("No image files found in the specified folder")
                    
                # Clear progress indicators
                progress_bar.empty()
                status_text.empty()
    
    # Step 4: Generate mapping
    if 'files' in st.session_state and st.session_state.files:
        st.header("Step 4: Create or Update Mapping")
        
        # Tabs for different options
        tab1, tab2, tab3 = st.tabs(["Simple Mapping", "Update Existing Mapping", "Export Full List"])
        
        # Option 1: Simple mapping
        with tab1:
            st.subheader("Generate Simple Filename to URL Mapping")
            
            if st.button("Generate Simple Mapping CSV"):
                with st.spinner("Generating mapping file..."):
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
                    
                    # Show preview
                    st.write("Preview (first 10 rows):")
                    st.dataframe(df.head(10))
        
        # Option 2: Update existing mapping
        with tab2:
            st.subheader("Update Your Existing Mapping CSV")
            
            mapping_file = st.file_uploader("Upload your logo_mapping.csv file", type=["csv"])
            
            if mapping_file is not None:
                try:
                    # Read the mapping file
                    mapping_df = pd.read_csv(mapping_file)
                    
                    st.write("Preview of uploaded mapping file:")
                    st.dataframe(mapping_df.head())
                    
                    if st.button("Update Mapping File"):
                        with st.spinner("Updating mapping file..."):
                            status_text = st.empty()
                            status_text.text("Matching filenames with URLs...")
                            
                            # Update the mapping
                            updated_df, success = update_mapping_csv(
                                st.session_state.files, 
                                mapping_df.copy(),  # Use copy to avoid modification warnings
                                status_text
                            )
                            
                            if success:
                                # Preview
                                st.write("Preview of updated mapping:")
                                st.dataframe(updated_df.head(10))
                                
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
                                match_percent = (matched/total*100) if total > 0 else 0
                                
                                # Create columns for stats
                                col1, col2, col3 = st.columns(3)
                                col1.metric("Total Logos", total)
                                col2.metric("Matched Logos", matched)
                                col3.metric("Match Rate", f"{match_percent:.1f}%")
                                
                                # Show unmatched rows if any
                                if matched < total:
                                    with st.expander("View unmatched logos"):
                                        unmatched = updated_df[updated_df['google_drive_url'] == '']
                                        st.dataframe(unmatched)
                            else:
                                st.error(f"Error updating mapping: {success}")
                    
                except Exception as e:
                    st.error(f"Error processing mapping file: {str(e)}")
        
        # Option 3: Export full file list
        with tab3:
            st.subheader("Export Complete File List")
            
            if st.button("Export Complete File List"):
                with st.spinner("Exporting file list..."):
                    # Create a complete DataFrame with all metadata
                    full_df = pd.DataFrame([
                        {
                            'filename': f['name'], 
                            'file_id': f['id'],
                            'mime_type': f.get('mimeType', ''),
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
                    
                    # Show preview
                    st.write("Preview (first 10 rows):")
                    st.dataframe(full_df.head(10))
        
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
