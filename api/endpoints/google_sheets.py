from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import logging
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from typing import Optional

# Create router
router = APIRouter(
    prefix="/google-sheet",
    tags=["Google Sheet Operations"],
    responses={404: {"description": "Not found"}},
)

# Get logger
logger = logging.getLogger(__name__)

# Define the request models
class SheetVerifyRequest(BaseModel):
    spreadsheet_id: str

class ColumnCheckRequest(BaseModel):
    spreadsheet_id: str
    sheet_name: Optional[str] = "Sheet1"

# Required column headers in exact order
REQUIRED_COLUMNS = [
    "Name",
    "Last Name",
    "Website Link",
    "LinkedIn",
    "Avatar Deets",
    "Recent LinkedIn Post",
    "Copy - Recent LinkedIn Post",
    "AboutUs / Mission Page",
    "Copy - AboutUs / Mission Page",
    "E-Book Page Link",
    "Copy - Ebook",
    "Recent Blog",
    "Copy - Recent Blog (3-6 Months)",
    "Testimonials / Reviews Page Link",
    "Copy - Testimonials / Reviews",
    "Webinar/Events Page Link",
    "Copy - Webinar/Events",
    "Recent News (TBD)"
]

@router.post("/verify-access")
async def verify_sheet_access(request: SheetVerifyRequest):
    """
    Verify if the Google Sheet is accessible by the service account
    """
    credentials_file = "data/url-to-email-445616-cebe4868914f.json"
    
    try:
        logger.info(f"Verifying access to spreadsheet: {request.spreadsheet_id}")
        
        # Set up credentials
        creds = service_account.Credentials.from_service_account_file(
            credentials_file,
            scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"]
        )
        
        # Build the Sheets API service
        service = build('sheets', 'v4', credentials=creds)
        
        # Test access by requesting spreadsheet metadata
        sheet_metadata = service.spreadsheets().get(
            spreadsheetId=request.spreadsheet_id
        ).execute()
        
        # If we get here, access is granted
        sheet_title = sheet_metadata.get('properties', {}).get('title', 'Untitled')
        
        return {
            "accessible": True,
            "spreadsheet_id": request.spreadsheet_id,
            "title": sheet_title,
            "sheet_names": [sheet.get('properties', {}).get('title') 
                           for sheet in sheet_metadata.get('sheets', [])]
        }
        
    except HttpError as error:
        if error.resp.status == 404:
            return {
                "accessible": False,
                "spreadsheet_id": request.spreadsheet_id,
                "error": "Spreadsheet not found. Check if the ID is correct."
            }
        elif error.resp.status == 403:
            return {
                "accessible": False,
                "spreadsheet_id": request.spreadsheet_id,
                "error": "Permission denied. Make sure the sheet is shared with the service account email: umang-utk@url-to-email-445616.iam.gserviceaccount.com"
            }
        else:
            logger.error(f"Error verifying sheet access: {str(error)}")
            return {
                "accessible": False,
                "spreadsheet_id": request.spreadsheet_id,
                "error": f"API error: {str(error)}"
            }
    except Exception as e:
        logger.error(f"Error verifying sheet access: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to verify access: {str(e)}")


@router.post("/verify-columns")
async def verify_sheet_columns(request: ColumnCheckRequest):
    """
    Verify if the Google Sheet has the required columns in the correct order
    """
    credentials_file = "data/url-to-email-445616-cebe4868914f.json"
    
    try:
        logger.info(f"Verifying columns for spreadsheet: {request.spreadsheet_id}, sheet: {request.sheet_name}")
        
        # Set up credentials
        creds = service_account.Credentials.from_service_account_file(
            credentials_file,
            scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"]
        )
        
        # Build the Sheets API service
        service = build('sheets', 'v4', credentials=creds)
        
        # Get the header row (first row)
        range_name = f"{request.sheet_name}!A1:ZZ1"
        result = service.spreadsheets().values().get(
            spreadsheetId=request.spreadsheet_id,
            range=range_name
        ).execute()
        
        # Extract header values
        headers = result.get('values', [[]])[0] if result.get('values') else []
        
        # Verify against required columns
        missing_columns = []
        misplaced_columns = []
        
        # Check which required columns are missing
        for column in REQUIRED_COLUMNS:
            if column not in headers:
                missing_columns.append(column)
        
        # Check if columns are in the correct order
        for i, column in enumerate(REQUIRED_COLUMNS):
            if i < len(headers) and column != headers[i]:
                misplaced_columns.append({
                    "expected": column,
                    "found": headers[i] if i < len(headers) else "None",
                    "position": i + 1
                })
        
        # Prepare result
        if not missing_columns and not misplaced_columns:
            return {
                "valid": True,
                "message": "All required columns are present in the correct order",
                "found_headers": headers
            }
        else:
            return {
                "valid": False,
                "missing_columns": missing_columns,
                "misplaced_columns": misplaced_columns,
                "required_columns": REQUIRED_COLUMNS,
                "found_headers": headers
            }
            
    except HttpError as error:
        if error.resp.status == 404:
            return {
                "valid": False,
                "error": "Spreadsheet or sheet not found. Check if the ID and sheet name are correct."
            }
        elif error.resp.status == 403:
            return {
                "valid": False,
                "error": "Permission denied. Make sure the sheet is shared with the service account."
            }
        else:
            logger.error(f"Error verifying sheet columns: {str(error)}")
            return {
                "valid": False,
                "error": f"API error: {str(error)}"
            }
    except Exception as e:
        logger.error(f"Error verifying sheet columns: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to verify columns: {str(e)}")