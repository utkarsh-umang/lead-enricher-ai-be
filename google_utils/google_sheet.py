import logging
import re
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

    def extract_spreadsheet_id(self, url: str) -> str:
        """
        Extract the spreadsheet ID from a Google Sheets URL.

        Args:
            url: Google Sheets URL or spreadsheet ID

        Returns:
            Spreadsheet ID. If input is a URL, extracts ID; otherwise returns as-is.
        """
        pattern = r'https://docs\.google\.com/spreadsheets/d/([a-zA-Z0-9-_]+)'
        match = re.search(pattern, url)
        if match:
            return match.group(1)
        return url

    def list_sheets(self, spreadsheet_id: str) -> Tuple[bool, Union[List[str], str]]:
        """
        List all sheet names in the spreadsheet.

        Args:
            spreadsheet_id: The ID of the spreadsheet

        Returns:
            Tuple of (success, result) where result is either a list of sheet names or error message
        """
        try:
            sheet_metadata = self.service.spreadsheets().get(
                spreadsheetId=spreadsheet_id
            ).execute()
            sheet_names = [
                sheet.get('properties', {}).get('title')
                for sheet in sheet_metadata.get('sheets', [])
            ]
            return True, sheet_names
        except HttpError as error:
            error_message = f"Google Sheets API error: {str(error)}"
            logger.error(error_message)
            return False, error_message
        except Exception as e:
            error_message = f"Error listing sheets: {str(e)}"
            logger.error(error_message)
            return False, error_message

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

    def get_sheet_values(self, spreadsheet_id: str, range_name: str) -> Tuple[bool, Union[List[List], str]]:
        """
        Get raw values from Google Sheet (list of lists) to preserve row structure.

        Args:
            spreadsheet_id: The ID of the spreadsheet
            range_name: The range to fetch (e.g., "Sheet1!A:Z")

        Returns:
            Tuple of (success, result) where result is either raw values (list of lists) or error message
        """
        try:
            result = self.service.spreadsheets().values().get(
                spreadsheetId=spreadsheet_id,
                range=range_name
            ).execute()
            values = result.get('values', [])
            return True, values
        except HttpError as error:
            error_message = f"Google Sheets API error: {str(error)}"
            logger.error(error_message)
            return False, error_message
        except Exception as e:
            error_message = f"Error fetching sheet values: {str(e)}"
            logger.error(error_message)
            return False, error_message

    def clear_and_rewrite_sheet(self, spreadsheet_id: str, sheet_name: str, data: List[List]) -> Tuple[bool, str]:
        """
        Clear a sheet and rewrite with new data.

        Args:
            spreadsheet_id: The ID of the spreadsheet
            sheet_name: Name of the sheet
            data: List of rows (list of lists) to write

        Returns:
            Tuple of (success, message)
        """
        try:
            range_name = f"{sheet_name}!A:Z"
            self.service.spreadsheets().values().clear(
                spreadsheetId=spreadsheet_id,
                range=range_name
            ).execute()

            if data:
                body = {'values': data}
                self.service.spreadsheets().values().update(
                    spreadsheetId=spreadsheet_id,
                    range=f"{sheet_name}!A1",
                    valueInputOption='RAW',
                    body=body
                ).execute()
                return True, f"Rewrote {sheet_name} with {len(data)} rows"
            return True, f"Cleared {sheet_name} (no data to write)"
        except HttpError as error:
            error_message = f"Google Sheets API error: {str(error)}"
            logger.error(error_message)
            return False, error_message
        except Exception as e:
            error_message = f"Error clearing/rewriting sheet: {str(e)}"
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
                       column_index: int,
                       start_row: int = 2) -> Tuple[bool, Union[List[str], str]]:
        """
        Get data from a specific column starting from a specified row
        
        Args:
            spreadsheet_id: The ID of the spreadsheet
            sheet_name: Name of the sheet
            column_index: Column index (0-based)
            start_row: Row to start from (1-based, default=2 for skipping header)
            
        Returns:
            Tuple of (success, result) where result is either a list of values or error message
        """
        try:
            column_letter = COLUMN_LETTERS.get(column_index, f"Column{column_index+1}")
            # Specify range with start_row to get data from that row onwards
            range_name = f"{sheet_name}!{column_letter}{start_row}:{column_letter}"
            
            result = self.service.spreadsheets().values().get(
                spreadsheetId=spreadsheet_id, 
                range=range_name
            ).execute()
            
            values = result.get('values', [])
            if not values:
                return True, []  # Empty column but successful request
                
            # Flatten the list - no need to skip header as we're starting from start_row
            flat_values = [item[0] if item else "" for item in values]
            return True, flat_values
            
        except HttpError as error:
            error_message = f"Google Sheets API error: {str(error)}"
            logger.error(error_message)
            return False, error_message
            
        except Exception as e:
            error_message = f"Error fetching column data: {str(e)}"
            logger.error(error_message)
            return False, error_message
        
    def append_rows(
        self,
        spreadsheet_id: str,
        sheet_name: str,
        rows: List[List],
    ) -> Tuple[bool, str]:
        """Append rows to the end of a sheet."""
        try:
            body = {"values": rows}
            self.service.spreadsheets().values().append(
                spreadsheetId=spreadsheet_id,
                range=f"{sheet_name}!A1",
                valueInputOption="RAW",
                insertDataOption="INSERT_ROWS",
                body=body,
            ).execute()
            return True, f"Appended {len(rows)} rows to {sheet_name}"
        except HttpError as error:
            error_message = f"Google Sheets API error: {str(error)}"
            logger.error(error_message)
            return False, error_message
        except Exception as e:
            error_message = f"Error appending rows: {str(e)}"
            logger.error(error_message)
            return False, error_message


    def delete_rows_by_indices(
        self,
        spreadsheet_id: str,
        sheet_name: str,
        row_indices: List[int],  # 0-based, not counting header
    ) -> Tuple[bool, str]:
        """
        Delete specific rows by index.
        Deletes from bottom to top to avoid index shifting.
        row_indices are 0-based data row indices (not counting header).
        """
        try:
            # Get sheet ID first
            sheet_metadata = self.service.spreadsheets().get(
                spreadsheetId=spreadsheet_id
            ).execute()
            sheet_id = None
            for sheet in sheet_metadata.get("sheets", []):
                if sheet["properties"]["title"] == sheet_name:
                    sheet_id = sheet["properties"]["sheetId"]
                    break

            if sheet_id is None:
                return False, f"Sheet '{sheet_name}' not found"

            # Convert to actual sheet row indices (add 1 for header, add 1 for 0-based)
            # Sheet rows are 1-based, row 1 is header, data starts at row 2
            sheet_row_indices = sorted(
                [i + 1 for i in row_indices],  # +1 to skip header row
                reverse=True,  # delete from bottom to top
            )

            requests = [
                {
                    "deleteDimension": {
                        "range": {
                            "sheetId": sheet_id,
                            "dimension": "ROWS",
                            "startIndex": row_idx,      # 0-based in API
                            "endIndex": row_idx + 1,
                        }
                    }
                }
                for row_idx in sheet_row_indices
            ]

            self.service.spreadsheets().batchUpdate(
                spreadsheetId=spreadsheet_id,
                body={"requests": requests},
            ).execute()

            return True, f"Deleted {len(row_indices)} rows from {sheet_name}"

        except HttpError as error:
            error_message = f"Google Sheets API error: {str(error)}"
            logger.error(error_message)
            return False, error_message
        except Exception as e:
            error_message = f"Error deleting rows: {str(e)}"
            logger.error(error_message)
            return False, error_message