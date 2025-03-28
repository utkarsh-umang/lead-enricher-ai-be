import pandas as pd
import logging
import re
from scraper.homepage_scraper import get_about_us_link 
from scraper.about_us_scraper import scrape_about_us_content

def normalize_url(url):
    """Ensure URL has proper protocol"""
    if pd.isna(url) or not isinstance(url, str):
        return None
    url = url.strip().lower()
    if not url:
        return None
    # If URL already has a protocol, return it as is
    if url.startswith(('http://', 'https://')):
        return url
    # Remove www. if present (only if no protocol)
    url = re.sub(r'^www\.', '', url)
    # Add http:// prefix if no protocol present
    return f'http://{url}'

def is_valid_url(url):
    """Check if URL is valid"""
    if pd.isna(url) or not isinstance(url, str):
        return False
    url = url.strip()
    if not url:
        return False
    # Accept URLs with protocols
    if url.startswith(('http://', 'https://')):
        return True
    # For URLs without protocol, check basic domain format
    return bool(re.match(r'^[a-zA-Z0-9][-a-zA-Z0-9.]*\.[a-zA-Z]{2,}', url))


def process_url(url):
    """Process single URL with error handling"""
    try:
        if not is_valid_url(url):
            logging.warning(f"Invalid URL format: {url}")
            return "Invalid URL format"
        # Normalize URL (add http:// only if no protocol present)
        normalized_url = normalize_url(url)
        if normalized_url != url:
            logging.info(f"Processing {url} (normalized to {normalized_url})")
        else:
            logging.info(f"Processing {url}")
        if not normalized_url:
            return "Invalid URL"
        about_link = get_about_us_link(normalized_url)
        if about_link:
            logging.info(f"Found 'About Us' page: {about_link}")
            about_content = scrape_about_us_content(about_link)
        else:
            logging.info(f"No 'About Us' page found for {normalized_url}. Falling back to homepage content.")
            about_content = scrape_about_us_content(normalized_url)
        if not about_content:
            logging.warning(f"No content scraped for {normalized_url}")
            return "No content found"
        return about_content
    except Exception as e:
        logging.error(f"Error processing URL {url}: {str(e)}")
        return f"Error: {str(e)}"