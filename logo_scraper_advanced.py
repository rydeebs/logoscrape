import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
import os
import uuid
import re
from urllib.parse import urljoin, urlparse
from PIL import Image
from io import BytesIO
import time
import concurrent.futures

class LogoScraper:
    def __init__(self, output_dir='logos', timeout=15):
        self.output_dir = output_dir
        self.timeout = timeout
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        os.makedirs(output_dir, exist_ok=True)
    
    def get_logo(self, url):
        """Main method to extract logo from a website"""
        # Clean and validate URL
        url = self._prepare_url(url)
        if not url:
            return None, "Invalid URL"
        
        try:
            # Fetch the webpage
            response = requests.get(url, headers=self.headers, timeout=self.timeout)
            response.raise_for_status()
            
            # Parse HTML
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Extract domain for naming
            domain = urlparse(url).netloc
            
            # Try different strategies to find the logo
            logo_candidates = []
            
            # Strategy 1: Check favicon and apple-touch-icon
            logo_candidates.extend(self._find_favicon_links(soup, url))
            
            # Strategy 2: Find images with 'logo' in attributes
            logo_candidates.extend(self._find_logo_in_img_attributes(soup, url))
            
            # Strategy 3: Look for SVG logos
            logo_candidates.extend(self._find_svg_logos(soup, url))
            
            # Strategy 4: Look for header logos
            logo_candidates.extend(self._find_header_logos(soup, url))
            
            # Process candidates and download the most promising logo
            return self._process_logo_candidates(logo_candidates, domain, url)
            
        except requests.exceptions.RequestException as e:
            return None, f"Request error: {str(e)}"
        except Exception as e:
            return None, f"Unexpected error: {str(e)}"
    
    def _prepare_url(self, url):
        """Clean and validate the URL"""
        if not url or not isinstance(url, str):
            return None
            
        url = url.strip()
        if not url:
            return None
            
        # Add http:// if missing
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
            
        # Remove trailing slashes
        url = url.rstrip('/')
        
        return url
    
    def _find_favicon_links(self, soup, base_url):
        """Find favicon and apple-touch-icon links"""
        candidates = []
        
        for link in soup.find_all('link'):
            rel = link.get('rel', [])
            if isinstance(rel, list):
                rel = ' '.join(rel).lower()
            else:
                rel = str(rel).lower()
                
            href = link.get('href')
            if not href:
                continue
                
            # Check for various icon types
            if any(x in rel for x in ['icon', 'shortcut icon', 'apple-touch-icon', 'apple-touch-icon-precomposed']):
                # Convert relative URL to absolute
                full_url = urljoin(base_url, href)
                candidates.append((full_url, 5))  # Priority 5
                
            # Look for application icons (usually higher quality)
            elif 'apple-touch-icon' in rel and 'precomposed' in rel:
                full_url = urljoin(base_url, href)
                candidates.append((full_url, 8))  # Higher priority
                
        return candidates
    
    def _find_logo_in_img_attributes(self, soup, base_url):
        """Find images with 'logo' in their attributes"""
        candidates = []
        
        for img in soup.find_all('img'):
            score = 0
            src = img.get('src')
            if not src:
                continue
                
            # Check various attributes for 'logo'
            for attr in ['class', 'id', 'alt', 'title', 'name']:
                value = img.get(attr, '')
                if isinstance(value, list):
                    value = ' '.join(value)
                else:
                    value = str(value).lower()
                
                # Look for logo indicators
                if 'logo' in value:
                    score += 3
                if 'brand' in value:
                    score += 2
                if 'header' in value:
                    score += 1
            
            # Check filename for logo indicators
            filename = os.path.basename(src).lower()
            if 'logo' in filename:
                score += 3
                
            # If score is positive, add to candidates
            if score > 0:
                full_url = urljoin(base_url, src)
                candidates.append((full_url, score))
                
        return candidates
    
    def _find_svg_logos(self, soup, base_url):
        """Look for SVG logos in the document"""
        candidates = []
        
        # Find inline SVG elements
        for svg in soup.find_all('svg'):
            # Check if it looks like a logo
            title = svg.find('title')
            if title and ('logo' in title.text.lower() or 'brand' in title.text.lower()):
                # Convert SVG to string
                svg_str = str(svg)
                candidates.append((svg_str, 7, 'inline_svg'))
                
        # Look for external SVG files
        for link in soup.find_all(['img', 'object', 'embed']):
            src = link.get('src') or link.get('data')
            if not src:
                continue
                
            if src.lower().endswith('.svg'):
                full_url = urljoin(base_url, src)
                candidates.append((full_url, 6))
                
        return candidates
    
    def _find_header_logos(self, soup, base_url):
        """Look for logos in header or navigation areas"""
        candidates = []
        
        # Find header or navigation elements
        header_elements = soup.find_all(['header', 'nav', 'div'], class_=lambda c: c and any(x in str(c).lower() for x in ['header', 'nav', 'top', 'logo', 'brand']))
        
        for header in header_elements:
            # Find images in header
            for img in header.find_all('img'):
                src = img.get('src')
                if src:
                    score = 4  # Default score for header images
                    # Increase score for likely logo images
                    if any(x in str(img).lower() for x in ['logo', 'brand']):
                        score += 2
                    
                    full_url = urljoin(base_url, src)
                    candidates.append((full_url, score))
                    
        return candidates
    
    def _process_logo_candidates(self, candidates, domain, base_url):
        """Process logo candidates and download the best one"""
        if not candidates:
            return None, "No logo candidates found"
            
        # Sort by score (highest first)
        candidates.sort(key=lambda x: x[1], reverse=True)
        
        # Try each candidate
        for candidate in candidates:
            try:
                if len(candidate) > 2 and candidate[2] == 'inline_svg':
                    # Handle inline SVG
                    svg_data = candidate[0]
                    filename = f"{domain.replace('.', '_')}_{uuid.uuid4().hex[:8]}.svg"
                    filepath = os.path.join(self.output_dir, filename)
                    
                    with open(filepath, 'w') as f:
                        f.write(svg_data)
                    
                    return filepath, "Success"
                else:
                    # Handle image URLs
                    img_url = candidate[0]
                    
                    # Download the image
                    img_response = requests.get(img_url, headers=self.headers, timeout=self.timeout)
                    img_response.raise_for_status()
                    
                    # Try to open as image to validate
                    img = Image.open(BytesIO(img_response.content))
                    
                    # Skip very small images (likely icons)
                    if img.width < 16 or img.height < 16:
                        continue
                    
                    # Generate filename
                    ext = img.format.lower() if img.format else 'png'
                    filename = f"{domain.replace('.', '_')}_{uuid.uuid4().hex[:8]}.{ext}"
                    filepath = os.path.join(self.output_dir, filename)
                    
                    # Save the image
                    img.save(filepath)
                    
                    return filepath, "Success"
            
            except Exception as e:
                continue  # Try next candidate
                
        return None, "No valid logo found among candidates"

def process_url_batch(scraper, batch_urls):
    """Process a batch of URLs with the scraper"""
    results = []
    for url in batch_urls:
        logo_path, message = scraper.get_logo(url)
        results.append((url, logo_path, message))
    return results

def main():
    st.set_page_config(page_title="Website Logo Scraper", layout="wide")
    
    st.title("Website Logo Scraper")
    st.write("Upload an Excel file with website URLs to extract logos")
    
    # Sidebar for advanced settings
    with st.sidebar:
        st.subheader("Advanced Settings")
        timeout = st.slider("Request Timeout (seconds)", 5, 30, 15)
        batch_size = st.slider("Batch Size", 1, 10, 5)
        max_workers = st.slider("Parallel Workers", 1, 5, 3)
    
    # Main area
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
                # Create a logo scraper instance
                scraper = LogoScraper(timeout=timeout)
                
                # Add progress indicators
                progress_bar = st.progress(0)
                status_text = st.empty()
                
                # Create new columns for results
                df['logo_path'] = None
                df['status'] = None
                
                # Get the list of URLs
                urls = df[url_column].astype(str).tolist()
                total_urls = len(urls)
                
                # Process in batches
                results = []
                processed_count = 0
                
                # Choose processing method based on max_workers
                if max_workers > 1:
                    # Process in parallel
                    with st.spinner("Extracting logos (parallel processing)..."):
                        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                            # Create batches
                            batches = [urls[i:i + batch_size] for i in range(0, len(urls), batch_size)]
                            
                            # Submit batches to executor
                            future_to_batch = {executor.submit(process_url_batch, scraper, batch): batch 
                                              for batch in batches}
                            
                            # Process results as they complete
                            for future in concurrent.futures.as_completed(future_to_batch):
                                batch_results = future.result()
                                results.extend(batch_results)
                                
                                # Update progress
                                processed_count += len(batch_results)
                                progress_bar.progress(processed_count / total_urls)
                                status_text.text(f"Processed {processed_count}/{total_urls} URLs")
                else:
                    # Process sequentially
                    with st.spinner("Extracting logos (sequential processing)..."):
                        for i, url in enumerate(urls):
                            logo_path, message = scraper.get_logo(url)
                            results.append((url, logo_path, message))
                            
                            # Update progress
                            progress_bar.progress((i + 1) / total_urls)
                            status_text.text(f"Processing {i+1}/{total_urls}: {url}")
                            
                            # Small delay to prevent overwhelming websites
                            time.sleep(0.5)
                
                # Update DataFrame with results
                result_dict = {url: (logo_path, message) for url, logo_path, message in results}
                for i, row in df.iterrows():
                    url = row[url_column]
                    if url in result_dict:
                        df.at[i, 'logo_path'] = result_dict[url][0]
                        df.at[i, 'status'] = result_dict[url][1]
                
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
                
                # Display summary
                success_count = df['logo_path'].notna().sum()
                st.success(f"Processed {total_urls} websites. Successfully extracted {success_count} logos ({success_count/total_urls*100:.1f}%).")
                
                # Show the results in an expandable section
                with st.expander("View Results"):
                    # Create columns for display
                    col1, col2 = st.columns([1, 2])
                    
                    with col1:
                        st.subheader("Successful Extractions")
                        for i, row in df[df['logo_path'].notna()].iterrows():
                            st.write(f"**{row[url_column]}**")
                            st.image(row['logo_path'], width=150)
                            st.divider()
                    
                    with col2:
                        st.subheader("All Results")
                        st.dataframe(df[[url_column, 'logo_path', 'status']])
                
        except Exception as e:
            st.error(f"An error occurred: {str(e)}")

if __name__ == "__main__":
    main()
