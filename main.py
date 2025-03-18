from data.google_sheet_parser import get_sheet_data, setup_google_sheets_service, update_sheet_values
from llm_utils.gpt_connector import process_with_gpt
from utils.helpers import process_url
from linkedin_utils.linkedin_parser import setup_driver, login_to_linkedin, check_connection_status, validate_profile, send_connection_request
from linkedin_utils.linkedin_sheet_parser import get_linkedin_profiles, update_linkedin_status
import logging
import sys
import os
import random
import time
from dotenv import load_dotenv

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('scraper.log'),
        logging.StreamHandler(sys.stdout)
    ]
)

load_dotenv()

def website_to_llm():
    credentials_file = "data/url-to-email-445616-cebe4868914f.json"
    spreadsheet_id = "1D7vcjKF-x05bnr_UBa6LwsyNNl2hdM7K5eFtXOd25ZQ"
    urls_range = "Sheet1!C:C"
    openai_api_key = os.getenv('OPENAI_API_KEY')

    try:
        service = setup_google_sheets_service(credentials_file)
        logging.info("Fetching data from Google Sheets...")
        urls_df = get_sheet_data(spreadsheet_id, urls_range, credentials_file)
        if urls_df.empty:
            logging.warning("No data found in the spreadsheet.")
            return

        # PHASE 1: Scrape URLs and write content immediately
        logging.info("Phase 1: Starting URL scraping...")
        total_urls = len(urls_df['Website'])
        for idx, url in enumerate(urls_df['Website'], 1):
            try:
                logging.info(f"Scraping URL {idx}/{total_urls}: {url}")
                content_result = process_url(url)
                website_content = [[str(content_result) if content_result is not None else ""]]
                gpt_result = process_with_gpt(f"{website_content}, if can't find anything just write NA", openai_api_key)
                update_sheet_values(service, spreadsheet_id, f"Sheet1!Q{idx+1}:Q{idx+1}", [[str(gpt_result)]])
                logging.info(f"Successfully scraped and stored content for URL {idx}")
            except Exception as e:
                error_message = f"Error: {str(e)}"
                logging.error(f"Error scraping URL at row {idx+1}: {error_message}")
                update_sheet_values(service, spreadsheet_id, f"Sheet1!Q{idx+1}", [[error_message]])
        logging.info("Phase 1 completed: All URLs scraped and content stored.")

        # PHASE 2: Process with GPT
        # logging.info("Phase 2: Starting GPT processing...")
        # data_a = get_sheet_data(spreadsheet_id, "Sheet1!A1:A", credentials_file) # irrelevant just the name of the person
        # data_g = get_sheet_data(spreadsheet_id, "Sheet1!G1:G", credentials_file) # irrelevant just the name of the person
        # data_l = get_sheet_data(spreadsheet_id, "Sheet1!L1:L", credentials_file)
        # for i in range(len(data_a.values)):
        #     try:
        #         current_row = i + 2
        #         content_a = data_a.values[i][0] if data_a.values[i] else "No content"
        #         content_g = data_g.values[i][0] if data_g.values[i] else "No content"
        #         content_l = data_l.values[i][0] if data_l.values[i] else "No content"
        #         # if isinstance(content_l, list):
        #         #     if any("No content found" in str(item) for item in content_l):
        #         #         logging.info(f"Skipping row {current_row} due to 'No content found'")
        #         #         continue
        #         # elif "No content found" in str(content_l):
        #         #     logging.info(f"Skipping row {current_row} due to 'No content found'")
        #         #     continue
        #         # if not content_g or content_g == "Beta - A Set 2" or content_g == "Beta - A" or content_g == "Copy Alpha A":
        #         #     logging.info(f"Skipping row {current_row} due to column G conditions")
        #         #     continue
        #         if (content_l and not content_l.startswith("Error")):
        #             logging.info(f"Processing content with GPT for row {current_row}")
        #             # combined_content = f"Person Name: {content_a}\n\nPodcast Transcript: {content_l}"
        #             combined_content = f"Podcast Transcript: {content_l}"
        #             gpt_result = process_with_gpt(combined_content, openai_api_key)
        #             update_sheet_values(service, spreadsheet_id, f"Sheet1!P{current_row}:P{current_row}", [[str(gpt_result)]])
        #             # update_sheet_values(service, spreadsheet_id, f"Sheet1!G{current_row}:G{current_row}", [["Beta - A Set 2"]])
        #             logging.info(f"Successfully processed and stored GPT result for row {current_row}")
        #         else:
        #             logging.warning(f"Skipping GPT processing for row {current_row} due to invalid content")
        #             update_sheet_values(service, spreadsheet_id, f"Sheet1!P{current_row}:P{current_row}", [["No valid content to analyze"]])
        #     except Exception as e:
        #         error_message = f"GPT Error: {str(e)}"
        #         logging.error(f"Error in GPT processing for row {current_row}: {error_message}")
                # update_sheet_values(service, spreadsheet_id, f"Sheet1!L{current_row}:L{current_row}", [[error_message]])
        logging.info("Phase 2 completed: All content processed with GPT.")
        logging.info("Script completed successfully")
    except Exception as e:
        logging.error(f"Script failed: {str(e)}")
        raise


def process_linkedin_profiles():
    """Process LinkedIn profiles from the Google Sheet"""
    credentials_file = "data/url-to-email-445616-cebe4868914f.json"
    spreadsheet_id = "1D7vcjKF-x05bnr_UBa6LwsyNNl2hdM7K5eFtXOd25ZQ"
    daily_requests_sent = 0
    MAX_DAILY_REQUESTS = 15

    driver = None

    try:
        # Initialize webdriver
        driver = setup_driver()
        if not driver:
            raise Exception("Failed to initialize web driver")
        
        # Login to Linkedin
        if not login_to_linkedin(driver, os.getenv('LINKEDIN_EMAIL'), os.getenv('LINKEDIN_PASSWORD')):
            raise Exception("Failed to login to LinkedIn")

        # Initialize Google Sheets service
        service = setup_google_sheets_service(credentials_file)
        
        # Get LinkedIn profile data from sheet
        profiles = get_linkedin_profiles(
            service,
            spreadsheet_id
        )
        
        if not profiles:
            logging.warning("No profiles found to process")
            return  

        for profile in profiles:
            try:
                # Random delay between profiles
                sleep_duration = random.uniform(30, 60)
                print(f"Waiting {sleep_duration:.2f}s before next profile")
                time.sleep(sleep_duration)

                # Check current status
                status = check_connection_status(driver, profile['url'])

                if status in ["Connected", "Pending"]:
                    update_linkedin_status(service, spreadsheet_id, profile['row_index'], status)
                    continue

                # Validate Profile
                # is_valid, message = validate_profile(
                #     driver,
                #     profile['url'],
                #     profile['first_name'],
                #     profile['last_name']
                # )

                # if not is_valid:
                #     update_linkedin_status(service, spreadsheet_id, profile['row_index'], "Incorrect Profile")
                #     continue

                # Send connection Request
                request_status = send_connection_request(driver, profile['url'], daily_requests_sent, MAX_DAILY_REQUESTS)
                update_linkedin_status(service, spreadsheet_id, profile['row_index'], request_status)

                if request_status == "Request Sent":
                    daily_requests_sent += 1

                if request_status == "Daily Limit Reached":
                    logging.info("Daily connection request limit reached, Stopping!")
                    break

            except Exception as e:
                logging.error(f"Error processing profile {profile['url']}: {str(e)}")
                update_linkedin_status(service, spreadsheet_id, profile['row_index'], f"Error: {str(e)}")
        
    except Exception as e:
        logging.error(f"LinkedIn profile processing failed: {str(e)}")
    finally: 
        if driver:
            driver.quit()

if __name__ == "__main__":
    website_to_llm()