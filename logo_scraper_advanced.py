import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
import os
import uuid
import zipfile
from urllib.parse import urljoin, urlparse
from PIL import Image
from io import BytesIO
import time
import csv

def get_site_logo(url):
    """
    Scrape a website to find and download its logo image.
    Returns the logo info or None if no logo was found.
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
                logo_candidates.append((link.get('href'), 1))  # Lower priority
        
        # 2. Look for images with 'logo' in the class, id, or alt attribute
        for img in soup.find_all('img'):
            score = 0
            for attr in ['class', 'id', 'alt', 'src']:
                value = img.get(attr, '')
                if isinstance(value, list):
                    value = ' '.join(value)
                else:
                    value = str(value)
                    
                if 'logo' in value.lower():
                    score += 2
                
            if score > 0 and img.get('src'):
                logo_candidates.append((img.get('src'), score + 2))  # Higher priority
        
        # If no logo candidates found, look for the first image in the header
        if not logo_candidates:
            header = soup.find('header')
            if header:
                img = header.find('img')
                if img and img.get('src'):
                    logo_candidates.append((img.get('src'), 3))  # Medium priority
        
        # Sort by priority (highest first)
        logo_candidates.sort(key=lambda x: x[1], reverse=True)
        
        # Process logo candidates
        for img_url, _ in logo_candidates:
            # Convert relative URLs to absolute URLs
            img_url = urljoin(url, img_url)
            
            try:
                # Download the image
                img_response = requests.get(img_url, headers=headers, timeout=10)
                img_response.raise_for_status()
                
                # Check if it's a valid image
                img = Image.open(BytesIO(img_response.content))
                
                # Determine best format - keep original format if possible
                save_format = img.format if img.format in ('JPEG', 'PNG') else 'PNG'
                ext = 'jpg' if save_format == 'JPEG' else 'png'
                
                # Convert to RGB if needed (for RGBA images)
                if img.mode == 'RGBA' and save_format == 'JPEG':
                    # Create a white background
                    background = Image.new('RGB', img.size, (255, 255, 255))
                    # Paste using alpha channel as mask
                    background.paste(img, mask=img.split()[3])
                    img = background
                elif img.mode != 'RGB' and save_format == 'JPEG':
                    img = img.convert('RGB')
                
                # Generate a unique filename
                domain = urlparse(url).netloc
                filename = f"{domain.replace('.', '_')}_{uuid.uuid4().hex[:8]}.{ext}"
                
                # Create images directory if it doesn't exist
                os.makedirs('logos', exist_ok=True)
                
                # Save the image
                img_path = os.path.join('logos', filename)
                img.save(img_path, save_format)
                
                # Return all the image information
                return {
                    'path': img_path,
                    'filename': filename,
                    'format': ext,
                    'domain': domain,
                    'url': url
                }
            
            except Exception as e:
                continue  # Try the next candidate if this one fails
        
        return None  # No valid logo found
        
    except Exception as e:
        st.error(f"Error processing {url}: {str(e)}")
        return None

def create_mapping_file(mapping_data):
    """
    Create a CSV file mapping website URLs to logo filenames.
    """
    filename = "logo_mapping.csv"
    with open(filename, 'w', newline='') as csvfile:
        fieldnames = ['website_url', 'domain', 'logo_filename', 'google_drive_url']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        
        writer.writeheader()
        for data in mapping_data:
            writer.writerow({
                'website_url': data['url'],
                'domain': data['domain'],
                'logo_filename': data['filename'],
                'google_drive_url': ''  # Empty column to be filled after Google Drive upload
            })
    
    return filename

def main():
    st.title("Website Logo Scraper with Mapping File")
    st.write("Upload an Excel file with website URLs to extract logos and create a mapping file for Google Drive")
    
    uploaded_file = st.file_uploader("Choose an Excel file", type=["xlsx", "xls", "csv"])
    
    if uploaded_file:
        try:
            # Read the uploaded file
            if uploaded_file.name.endswith('.csv'):
                df = pd.read_csv(uploaded_file)
            else:
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
                
                # Store the image data and mapping info
                all_logos = []
                mapping_data = []
                
                # Create new columns for results
                df['logo_found'] = False
                df['logo_filename'] = None
                
                # Process each URL
                for i, row in df.iterrows():
                    url = str(row[url_column])
                    status_text.text(f"Processing {i+1}/{len(df)}: {url}")
                    
                    # Get the logo
                    logo_info = get_site_logo(url)
                    
                    # Update the DataFrame and mapping data
                    if logo_info:
                        df.at[i, 'logo_found'] = True
                        df.at[i, 'logo_filename'] = logo_info['filename']
                        all_logos.append(logo_info)
                        mapping_data.append({
                            'url': url,
                            'domain': logo_info['domain'],
                            'filename': logo_info['filename']
                        })
                    
                    # Update progress
                    progress_bar.progress((i + 1) / len(df))
                    
                    # Small delay to prevent overwhelming websites
                    time.sleep(0.5)
                
                # Create a zip file with all logos
                if all_logos:
                    zip_filename = "all_logos.zip"
                    with zipfile.ZipFile(zip_filename, 'w') as zipf:
                        for logo in all_logos:
                            zipf.write(logo['path'], logo['filename'])
                    
                    # Provide download button for the zip file
                    with open(zip_filename, "rb") as f:
                        zip_data = f.read()
                        st.download_button(
                            label="Download All Logos (ZIP)",
                            data=zip_data,
                            file_name=zip_filename,
                            mime="application/zip"
                        )
                
                # Create mapping file
                if mapping_data:
                    mapping_filename = create_mapping_file(mapping_data)
                    
                    # Provide download button for the mapping file
                    with open(mapping_filename, "rb") as f:
                        mapping_data = f.read()
                        st.download_button(
                            label="Download Logo Mapping File (CSV)",
                            data=mapping_data,
                            file_name=mapping_filename,
                            mime="text/csv"
                        )
                
                # Save the results
                output_filename = "logos_extraction_results.xlsx"
                df.to_excel(output_filename, index=False)
                
                # Provide download button for the Excel file
                with open(output_filename, "rb") as file:
                    st.download_button(
                        label="Download Results (Excel)",
                        data=file,
                        file_name=output_filename,
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
                
                # Display the results
                success_count = df['logo_found'].sum()
                st.success(f"Processed {len(df)} websites. Successfully extracted {success_count} logos.")
                
                # Show how to use the mapping file
                st.subheader("Next Steps for Google Drive Integration")
                st.markdown("""
                1. **Extract the logo files** from the ZIP download
                2. **Upload the logos to Google Drive** in a shared folder
                3. **For each logo in Google Drive**:
                   - Get the sharing link (right-click > "Get link")
                   - Convert to direct link format: `https://drive.google.com/uc?export=view&id=FILE_ID`
                   - Update the `google_drive_url` column in the mapping CSV
                4. **Use the updated mapping file** for your Webflow CMS import
                """)
                
                # Show thumbnails of the extracted logos
                if all_logos:
                    st.subheader("Extracted Logos")
                    
                    # Create a grid layout
                    cols = st.columns(3)
                    for i, logo in enumerate(all_logos):
                        col = cols[i % 3]
                        with col:
                            st.image(logo['path'], caption=f"{logo['domain']} - {logo['filename']}", width=150)
        
        except Exception as e:
            st.error(f"An error occurred: {str(e)}")
            st.exception(e)

if __name__ == "__main__":
    main()
