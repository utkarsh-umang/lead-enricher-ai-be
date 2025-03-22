import pandas as pd
import logging
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError


def get_sheet_data(spreadsheet_id, range_name, credentials_file):
    try:
        # Authenticate with the service account
        creds = service_account.Credentials.from_service_account_file(
            credentials_file,
            scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"]
        )
        # Build the Sheets API service
        service = build('sheets', 'v4', credentials=creds)
        # Call the Sheets API
        sheet = service.spreadsheets()
        result = sheet.values().get(spreadsheetId=spreadsheet_id, range=range_name).execute()
        values = result.get('values', [])
        # Convert the data to a pandas DataFrame
        if not values:
            print("No data found.")
            return pd.DataFrame()
        else:
            return pd.DataFrame(values[1:], columns=values[0])
    except Exception as e:
        print(f"Error fetching data from Google Sheets: {e}")
        return pd.DataFrame()

    
def setup_google_sheets_service(credentials_file):
    """Set up and return Google Sheets service with error handling"""
    try:
        SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
        credentials = service_account.Credentials.from_service_account_file(
            credentials_file, scopes=SCOPES)
        service = build('sheets', 'v4', credentials=credentials)
        return service
    except FileNotFoundError:
        logging.error(f"Credentials file not found: {credentials_file}")
        raise
    except Exception as e:
        logging.error(f"Failed to setup Google Sheets service: {str(e)}")
        raise


def update_sheet_values(service, spreadsheet_id, range_name, values):
    """Update Google Sheet with error handling"""
    try:
        body = {'values': values}
        result = service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range=range_name,
            valueInputOption='RAW',
            body=body
        ).execute()
        logging.info(f"Updated {result.get('updatedCells')} cells in column M")
        return result
    except HttpError as e:
        if e.resp.status == 403:
            logging.error("Permission denied. Make sure the service account has write access to the spreadsheet")
        elif e.resp.status == 404:
            logging.error("Spreadsheet not found. Check the spreadsheet ID")
        else:
            logging.error(f"HTTP error occurred: {str(e)}")
        raise
    except Exception as e:
        logging.error(f"Failed to update sheet: {str(e)}")
        raise