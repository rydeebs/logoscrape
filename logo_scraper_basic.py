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
        
        # Look for the company name in meta tags to help with verification
        company_name = None
        for meta in soup.find_all('meta'):
            if meta.get('property') in ['og:site_name', 'og:title']:
                company_name = meta.get('content', '').lower()
                break
        
        if not company_name:
            title = soup.find('title')
            if title:
                company_name = title.text.lower()
        
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
    st.title("Website Logo Scraper")
    st.write("Upload an Excel file with website URLs to extract logos")
    
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
                
                # Create a new column for logo paths
                df['logo_path'] = None
                
                # Process each URL
                for i, row in df.iterrows():
                    url = str(row[url_column])
                    status_text.text(f"Processing {i+1}/{len(df)}: {url}")
                    
                    # Get the logo
                    logo_path = get_site_logo(url)
                    
                    # Update the DataFrame
                    df.at[i, 'logo_path'] = logo_path
                    
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
                st.success(f"Processed {len(df)} websites. Successfully extracted {df['logo_path'].notna().sum()} logos.")
                
                # Show the logos that were found
                st.subheader("Extracted Logos")
                for i, row in df.iterrows():
                    if pd.notna(row['logo_path']):
                        st.write(f"{row[url_column]}")
                        st.image(row['logo_path'], width=150)
                
        except Exception as e:
            st.error(f"An error occurred: {str(e)}")

if __name__ == "__main__":
    main()
