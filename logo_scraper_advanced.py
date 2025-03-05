import streamlit as st
import pandas as pd
import csv
from io import StringIO

def main():
    st.title("Simple Google Drive URL Generator")
    st.write("Generate Google Drive direct URLs for your logos without needing API access")
    
    # Step 1: Get the folder ID
    st.header("Step 1: Get Your Google Drive Folder ID")
    
    st.markdown("""
    1. Open your Google Drive folder containing logo images
    2. Look at the URL in your browser
    3. The folder ID is the string after `folders/` in the URL
    
    For example, in `https://drive.google.com/drive/folders/1AbCdEfGhIj-KlMnOpQr`, the folder ID is `1AbCdEfGhIj-KlMnOpQr`
    """)
    
    folder_id = st.text_input("Enter your Google Drive folder ID")
    
    # Step 2: Manual file ID input
    st.header("Step 2: List Your Files and IDs")
    
    st.markdown("""
    ### Instructions:
    
    For each logo file in your Google Drive folder:
    
    1. Right-click on the file
    2. Select "Get link" (or "Share")
    3. Copy the ID from the sharing link (the part between `/d/` and `/view`)
    
    For example, from `https://drive.google.com/file/d/1AbCdEfGhIj-KlMnOpQr/view?usp=sharing`,
    the ID is `1AbCdEfGhIj-KlMnOpQr`
    
    You can add multiple files below by clicking "Add another file"
    """)
    
    # Initialize session state for files
    if 'files' not in st.session_state:
        st.session_state.files = [{"filename": "", "file_id": ""}]
    
    # Display fields for each file
    for i, file in enumerate(st.session_state.files):
        col1, col2 = st.columns([1, 1])
        with col1:
            st.session_state.files[i]["filename"] = st.text_input(
                "Filename (e.g., fruit4u_co_c30ad305.png)",
                file["filename"],
                key=f"filename_{i}"
            )
        with col2:
            st.session_state.files[i]["file_id"] = st.text_input(
                "File ID from sharing link",
                file["file_id"],
                key=f"file_id_{i}"
            )
        
        # Add delete button for each entry except the first one
        if i > 0:
            if st.button("Remove this file", key=f"remove_{i}"):
                st.session_state.files.pop(i)
                st.experimental_rerun()
        
        st.markdown("---")
    
    # Add button to add another file
    if st.button("Add another file"):
        st.session_state.files.append({"filename": "", "file_id": ""})
        st.experimental_rerun()
    
    # Alternative: Bulk entry
    st.header("OR: Bulk Entry")
    
    st.markdown("""
    If you have many files, you can enter them in bulk using this format (one per line):
    ```
    filename.png,fileID
    ```
    """)
    
    bulk_text = st.text_area("Enter filename,fileID pairs (one per line)")
    
    if st.button("Process Bulk Entry"):
        if bulk_text:
            # Parse the bulk text
            lines = bulk_text.strip().split('\n')
            new_files = []
            
            for line in lines:
                if ',' in line:
                    filename, file_id = line.split(',', 1)
                    new_files.append({"filename": filename.strip(), "file_id": file_id.strip()})
            
            if new_files:
                st.session_state.files = new_files
                st.success(f"Added {len(new_files)} files from bulk entry")
                st.experimental_rerun()
    
    # Step 3: Generate URLs
    st.header("Step 3: Generate Direct URLs")
    
    if st.button("Generate Direct URLs"):
        # Filter out entries with empty fields
        valid_files = [f for f in st.session_state.files if f["filename"] and f["file_id"]]
        
        if valid_files:
            # Generate direct URLs
            for file in valid_files:
                file["direct_url"] = f"https://drive.google.com/uc?export=view&id={file['file_id']}"
            
            # Store the result
            st.session_state.valid_files = valid_files
            
            # Show success message
            st.success(f"Generated direct URLs for {len(valid_files)} files")
        else:
            st.error("No valid files found. Please enter at least one filename and file ID.")
    
    # Step 4: Download results
    if 'valid_files' in st.session_state and st.session_state.valid_files:
        st.header("Step 4: Download Results")
        
        # Display the results
        st.subheader("Generated Direct URLs")
        result_df = pd.DataFrame(st.session_state.valid_files)
        st.dataframe(result_df)
        
        # Option 1: Simple mapping
        st.subheader("Option 1: Simple Filename to URL Mapping")
        
        csv_data = StringIO()
        csv_writer = csv.writer(csv_data)
        csv_writer.writerow(["filename", "direct_url"])
        
        for file in st.session_state.valid_files:
            csv_writer.writerow([file["filename"], file["direct_url"]])
        
        st.download_button(
            label="Download Simple Mapping CSV",
            data=csv_data.getvalue(),
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
                
                # Create a dictionary for faster lookup
                url_dict = {file["filename"]: file["direct_url"] for file in st.session_state.valid_files}
                
                # Update the google_drive_url column
                mapping_df["google_drive_url"] = mapping_df["logo_filename"].map(lambda x: url_dict.get(x, ""))
                
                # Preview
                st.write("Preview of updated mapping:")
                st.dataframe(mapping_df.head())
                
                # Create CSV for download
                updated_csv = StringIO()
                mapping_df.to_csv(updated_csv, index=False)
                
                st.download_button(
                    label="Download Updated Mapping CSV",
                    data=updated_csv.getvalue(),
                    file_name="updated_mapping.csv",
                    mime="text/csv",
                    key="updated_mapping"
                )
                
            except Exception as e:
                st.error(f"Error processing mapping file: {str(e)}")
        
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
