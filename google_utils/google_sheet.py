import logging
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import pandas as pd
from typing import List, Tuple, Union

from data.constants import CREDENTIALS_FILE, COLUMN_LETTERS

logger = logging.getLogger(__name__)

class GoogleSheetService:
    """Service for interacting with Google Sheets API"""
    
    def __init__(self, credentials_file: str = CREDENTIALS_FILE):
        """Initialize the Google Sheets service with credentials"""
        self.credentials_file = credentials_file
        self.service = self._setup_service()
        
    def _setup_service(self):
        """Set up and return Google Sheets service with error handling"""
        try:
            scopes = ['https://www.googleapis.com/auth/spreadsheets']
            credentials = service_account.Credentials.from_service_account_file(
                self.credentials_file, scopes=scopes)
            service = build('sheets', 'v4', credentials=credentials)
            return service
        except FileNotFoundError:
            logger.error(f"Credentials file not found: {self.credentials_file}")
            raise
        except Exception as e:
            logger.error(f"Failed to setup Google Sheets service: {str(e)}")
            raise
            
    def get_sheet_data(self, 
                      spreadsheet_id: str, 
                      range_name: str) -> Tuple[bool, Union[pd.DataFrame, str]]:
        """
        Get data from Google Sheet with error handling
        
        Args:
            spreadsheet_id: The ID of the spreadsheet
            range_name: The range to fetch (e.g., "Sheet1!A1:Z100")
            
        Returns:
            Tuple of (success, result) where result is either a DataFrame or error message
        """
        try:
            result = self.service.spreadsheets().values().get(
                spreadsheetId=spreadsheet_id, 
                range=range_name
            ).execute()
            
            values = result.get('values', [])
            if not values:
                return False, "No data found in specified range"
                
            # Convert to DataFrame
            df = pd.DataFrame(values[1:], columns=values[0] if values else [])
            return True, df
            
        except HttpError as error:
            error_message = f"Google Sheets API error: {str(error)}"
            logger.error(error_message)
            return False, error_message
            
        except Exception as e:
            error_message = f"Error fetching sheet data: {str(e)}"
            logger.error(error_message)
            return False, error_message
            
    def update_cell(self, 
                   spreadsheet_id: str, 
                   sheet_name: str, 
                   row: int, 
                   column_index: int, 
                   value: str) -> Tuple[bool, str]:
        """
        Update a single cell in the sheet
        
        Args:
            spreadsheet_id: The ID of the spreadsheet
            sheet_name: Name of the sheet
            row: Row number (1-based)
            column_index: Column index (0-based)
            value: Value to set
            
        Returns:
            Tuple of (success, message)
        """
        try:
            column_letter = COLUMN_LETTERS.get(column_index, f"Column{column_index+1}")
            range_name = f"{sheet_name}!{column_letter}{row}"
            
            body = {
                'values': [[value]]
            }
            
            result = self.service.spreadsheets().values().update(
                spreadsheetId=spreadsheet_id,
                range=range_name,
                valueInputOption='RAW',
                body=body
            ).execute()
            
            updated_cells = result.get('updatedCells', 0)
            return True, f"Updated {updated_cells} cells"
            
        except HttpError as error:
            error_message = f"Google Sheets API error: {str(error)}"
            logger.error(error_message)
            return False, error_message
            
        except Exception as e:
            error_message = f"Error updating cell: {str(e)}"
            logger.error(error_message)
            return False, error_message
            
    def get_column_data(self, 
                       spreadsheet_id: str, 
                       sheet_name: str, 
                       column_index: int) -> Tuple[bool, Union[List[str], str]]:
        """
        Get data from a specific column
        
        Args:
            spreadsheet_id: The ID of the spreadsheet
            sheet_name: Name of the sheet
            column_index: Column index (0-based)
            
        Returns:
            Tuple of (success, result) where result is either a list of values or error message
        """
        try:
            column_letter = COLUMN_LETTERS.get(column_index, f"Column{column_index+1}")
            range_name = f"{sheet_name}!{column_letter}:{column_letter}"
            
            result = self.service.spreadsheets().values().get(
                spreadsheetId=spreadsheet_id, 
                range=range_name
            ).execute()
            
            values = result.get('values', [])
            if not values:
                return True, []  # Empty column but successful request
                
            # Flatten the list and skip header
            flat_values = [item[0] if item else "" for item in values[1:]]
            return True, flat_values
            
        except HttpError as error:
            error_message = f"Google Sheets API error: {str(error)}"
            logger.error(error_message)
            return False, error_message
            
        except Exception as e:
            error_message = f"Error fetching column data: {str(e)}"
            logger.error(error_message)
            return False, error_message