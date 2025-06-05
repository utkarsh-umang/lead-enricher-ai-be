import asyncio

import asyncio
import os
import sys
import time
from typing import List, Dict
from urllib.parse import urlparse
import re
import logging
from firecrawl import FirecrawlApp
from crawl4ai import AsyncWebCrawler
from crawl4ai.extraction_strategy import LLMExtractionStrategy
from bs4 import BeautifulSoup
from pydantic import BaseModel, Field
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

# Setup logging
logging.basicConfig(
    filename="crawl_script.log",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

# Fix for Windows event loop
if sys.platform.startswith("win"):
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

# --- Firecrawl Configuration ---
FIRECRAWL_API_KEY = os.getenv("FIRECRAWL_API_KEY")  # Set as environment variable
if not FIRECRAWL_API_KEY:
    raise ValueError("FIRECRAWL_API_KEY environment variable not set")

app = FirecrawlApp(api_key=FIRECRAWL_API_KEY)

# --- Pydantic Model for Crawl4AI Extraction ---
class PageContent(BaseModel):
    title: str = Field(..., description="The title of the webpage")
    main_content: str = Field(..., description="The main text content of the page, excluding navigation, footers, and ads")

# --- Google Sheets Configuration ---
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
CREDENTIALS_FILE = "credentials.json"  # Update with your path
SPREADSHEET_URL = "your_google_sheet_link"  # Update with your Google Sheet URL

class GoogleSheetsManager:
    def __init__(self, credentials_file: str):
        self.credentials_file = credentials_file
        self.service = self._authenticate()

    def _authenticate(self):
        creds = None
        if os.path.exists("token.json"):
            creds = Credentials.from_authorized_user_file("token.json", SCOPES)
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(self.credentials_file, SCOPES)
                creds = flow.run_local_server(port=0)
            with open("token.json", "w") as token:
                token.write(creds.to_json())
        return build("sheets", "v4", credentials=creds)

    def extract_spreadsheet_id(self, url: str) -> str:
        match = re.search(r"/spreadsheets/d/([a-zA-Z0-9-_]+)", url)
        if match:
            return match.group(1)
        raise ValueError("Invalid Google Sheets URL")

    def update_results(self, spreadsheet_id: str, results: List[Dict], category_column: str):
        try:
            sheet = self.service.spreadsheets()
            # Example: Append results to a specific sheet
            values = []
            for result in results:
                values.append([
                    result["url"],
                    result["status"],
                    result.get("title", ""),
                    result.get("content", "")[:1000],  # Limit content length
                    result.get("error", "")
                ])
            body = {"values": values}
            sheet.values().append(
                spreadsheetId=spreadsheet_id,
                range=f"{category_column}!A2:E",  # Adjust range as needed
                valueInputOption="RAW",
                body=body
            ).execute()
            logging.info(f"Updated Google Sheets for category {category_column}")
        except Exception as e:
            logging.error(f"Failed to update Google Sheets: {str(e)}")

# --- Firecrawl URL Crawling ---
def categorize_urls(urls: List[str]) -> Dict[str, List[str]]:
    categorized_urls = {
        "EBOOK": [],
        "ABOUT_US": [],
        "RECENT_BLOG": [],
        "UNCATEGORIZED": []
    }

    for url in urls:
        parsed_url = urlparse(url)
        path = parsed_url.path.lower()

        if "ebook" in path or "template" in path:
            categorized_urls["EBOOK"].append(url)
        elif "about" in path or "company" in path:
            categorized_urls["ABOUT_US"].append(url)
        elif "blog" in path or "news" in path or "press" in path:
            categorized_urls["RECENT_BLOG"].append(url)
        else:
            categorized_urls["UNCATEGORIZED"].append(url)

    # Filter recent blog posts (example: 2025)
    categorized_urls["RECENT_BLOG"] = [
        url for url in categorized_urls["RECENT_BLOG"] if "2025" in url
    ][:2]  # Limit to 2 for testing

    return categorized_urls

async def crawl_website(base_url: str) -> Dict[str, List[str]]:
    try:
        logging.info(f"Crawling website: {base_url}")
        crawl_result = app.crawl_url(
            base_url,
            params={
                "limit": 100,
                "scrapeOptions": {"formats": ["markdown", "html"]}
            }
        )
        if crawl_result and isinstance(crawl_result, list):
            urls = [result["metadata"]["sourceURL"] for result in crawl_result if "metadata" in result and "sourceURL" in result]
            logging.info(f"Found {len(urls)} URLs")
            return categorize_urls(urls)
        else:
            logging.warning("No URLs found during crawl")
            return categorize_urls([])
    except Exception as e:
        logging.error(f"Error crawling website: {str(e)}")
        return categorize_urls([])

# --- Crawl4AI Content Extraction ---
class Crawl4AIExtractor:
    def __init__(self, urls: List[str]):
        self.urls = urls

    async def extract_first_url(self) -> Dict:
        if not self.urls:
            return {"status": "fail", "reason": "No URLs provided."}
        
        url = self.urls[0]
        logging.info(f"Processing single URL: {url}")
        try:
            async with AsyncWebCrawler(verbose=True, user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36") as crawler:
                result = await crawler.arun(
                    url=url,
                    word_count_threshold=1,
                    bypass_cache=True,
                    headless=True,  # Use headless for stability
                    timeout=60,
                    extraction_strategy=LLMExtractionStrategy(
                        schema=PageContent.schema(),
                        instruction="Extract the title and main content from the webpage. Focus on the primary content section, ignoring navigation, footers, and ads."
                    )
                )
                if result.success and result.extracted_content:
                    logging.info(f"Successfully extracted content from {url}")
                    return {
                        "url": url,
                        "status": "success",
                        "title": result.extracted_content.get("title", "No title"),
                        "content": result.extracted_content.get("main_content", "No content extracted"),
                        "markdown": result.markdown,
                        "full_html": result.html[:1000]
                    }
                else:
                    logging.warning(f"Extraction failed for {url}: {result.message}")
                    return {
                        "url": url,
                        "status": "fail",
                        "error": result.message or "Extraction failed"
                    }
        except Exception as e:
            logging.error(f"Error processing {url}: {str(e)}")
            return {
                "url": url,
                "status": "fail",
                "error": str(e)
            }

    async def extract_limited_urls(self, max_urls: int = 3) -> List[Dict]:
        results = []
        urls_to_process = self.urls[:max_urls]
        
        for i, url in enumerate(urls_to_process):
            print(f"Processing URL {i+1}/{len(urls_to_process)}: {url}")
            logging.info(f"Processing URL: {url}")
            try:
                if i > 0:
                    await asyncio.sleep(3)
                
                async with AsyncWebCrawler(verbose=True, user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36") as crawler:
                    result = await crawler.arun(
                        url=url,
                        word_count_threshold=1,
                        bypass_cache=True,
                        headless=True,
                        timeout=60,
                        extraction_strategy=LLMExtractionStrategy(
                            schema=PageContent.schema(),
                            instruction="Extract the title and main content from the webpage. Focus on the primary content section, ignoring navigation, footers, and ads."
                        )
                    )
                    if result.success and result.extracted_content:
                        results.append({
                            "url": url,
                            "status": "success",
                            "title": result.extracted_content.get("title", "No title"),
                            "content": result.extracted_content.get("main_content", "No content extracted"),
                            "markdown": result.markdown,
                            "full_html": result.html[:1000]
                        })
                        print(f"✔ Successfully processed: {url}")
                        logging.info(f"Successfully processed: {url}")
                    else:
                        soup = BeautifulSoup(result.html, "html.parser")
                        main_content = soup.find("main")
                        content_text = main_content.get_text(separator="\n", strip=True) if main_content else soup.get_text(separator="\n", strip=True)
                        results.append({
                            "url": url,
                            "status": "success (fallback)",
                            "title": soup.title.string if soup.title else "No title",
                            "content": content_text[:2000],
                            "markdown": result.markdown,
                            "full_html": result.html[:1000]
                        })
                        print(f"✔ Processed with fallback: {url}")
                        logging.info(f"Processed with fallback: {url}")
            except Exception as e:
                print(f"✖ Error processing {url}: {str(e)}")
                logging.error(f"Error processing {url}: {str(e)}")
                results.append({
                    "url": url,
                    "status": "fail",
                    "error": str(e)
                })
        
        return results

async def process_categorized_urls_with_crawl4ai(categorized_urls: Dict[str, List[str]], max_urls_per_category: int = 2) -> Dict[str, List[Dict]]:
    all_results = {}
    
    for category, urls in categorized_urls.items():
        if not urls or category == "UNCATEGORIZED":
            continue
            
        print(f"\n{'='*50}")
        print(f"Processing {category} URLs")
        print(f"{'='*50}")
        logging.info(f"Processing category: {category}")
        
        extractor = Crawl4AIExtractor(urls)
        results = await extractor.extract_limited_urls(max_urls=max_urls_per_category)
        all_results[category] = results
        
        await asyncio.sleep(2)
    
    return all_results

# --- Main Processing Logic ---
async def main():
    # Step 1: Crawl website
    base_url = "https://www.canva.com/"  # Update as needed
    print(f"Starting crawl for: {base_url}")
    categorized_urls = await crawl_website(base_url)
    
    if not any(categorized_urls.values()):
        print("No URLs found. Exiting.")
        logging.error("No URLs found during crawl")
        return None
    
    print(f"Available categories: {list(categorized_urls.keys())}")
    
    # Step 2: Test single URL
    print("\nStep 1: Testing single URL extraction...")
    test_url = None
    test_category = None
    for category, urls in categorized_urls.items():
        if urls and category != "UNCATEGORIZED":
            test_url = urls[0]
            test_category = category
            break
    
    if test_url:
        print(f"Testing URL from {test_category}: {test_url}")
        extractor = Crawl4AIExtractor([test_url])
        test_result = await extractor.extract_first_url()
        
        print("\nTest Result:")
        print(f"Status: {test_result['status']}")
        if test_result['status'] == 'success':
            print(f"Title: {test_result.get('title', 'No title')}")
            print(f"Content length: {len(test_result.get('content', ''))}")
            content_preview = test_result['content'][:300].replace('\n', ' ')
            print(f"Content preview: {content_preview}...")
        else:
            print(f"Error: {test_result.get('error', 'Unknown error')}")
        
        if test_result['status'] != 'success':
            print("\n" + "="*60)
            print("✖ Single URL test failed. Please check your setup and 'crawl_script.log'.")
            print("="*60)
            return None
    
    print("\n" + "="*60)
    print("✔ Single URL test successful! Proceeding with full processing...")
    print("="*60)
    
    # Step 3: Process all URLs
    full_results = await process_categorized_urls_with_crawl4ai(categorized_urls, max_urls_per_category=2)
    
    print(f"\n{'='*60}")
    print("CRAWL4AI PROCESSING RESULTS")
    print(f"{'='*60}")
    
    for category, category_results in full_results.items():
        print(f"\n{category} Category:")
        print("-" * 40)
        
        successful = [r for r in category_results if r['status'].startswith("success")]
        failed = [r for r in category_results if r['status'] == 'fail']
        
        print(f"✔ Successful: {len(successful)}")
        print(f"✖ Failed: {len(failed)}")
        
        for result in category_results:
            print(f"\nURL: {result['url']}")
            print(f"Status: {result['status']}")
            
            if result['status'].startswith("success"):
                print(f"Title: {result.get('title', 'No title')}")
                content_preview = result['content'][:200].replace('\n', ' ') if result['content'] else 'No content'
                print(f"Content preview: {content_preview}...")
                if result.get('markdown'):
                    markdown_preview = result['markdown'][:100].replace('\n', ' ')
                    print(f"Markdown preview: {markdown_preview}...")
            else:
                print(f"Error: {result.get('error', 'Unknown error')}")
    
    # Step 4: Write to Google Sheets (optional)
    try:
        sheets_manager = GoogleSheetsManager(CREDENTIALS_FILE)
        spreadsheet_id = sheets_manager.extract_spreadsheet_id(SPREADSHEET_URL)
        for category, results in full_results.items():
            sheets_manager.update_results(spreadsheet_id, results, category_column=category)
        print("\nResults written to Google Sheets")
    except Exception as e:
        print(f"\nFailed to write to Google Sheets: {str(e)}")
        logging.error(f"Failed to write to Google Sheets: {str(e)}")
    
    return full_results

# --- Run the script ---
if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        print(f"Unexpected error: {e}. Check 'crawl_script.log' for details.")
        logging.error(f"Unexpected error: {str(e)}")
