from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, field_validator
import logging
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from typing import Optional, Dict, Literal
import re
from datetime import datetime
from utils.db import MongoDB

# Create router
router = APIRouter(
    prefix="/google-sheet",
    tags=["Google Sheet Operations"],
    responses={404: {"description": "Not found"}},
)

# Get logger
logger = logging.getLogger(__name__)

# Sheet Status Enum
SheetStatus = Literal[
    "NO_ACCESS", 
    "CONNECTED", 
    "ENRICHMENT_STARTED", 
    "ENRICHMENT_COMPLETED", 
    "OUTREACH_STARTED", 
    "COMPLETED"
]

# Helper function to get database connection
def get_database():
    """Get database connection safely"""
    db = MongoDB.get_db()
    if db is None:
        logger.error("Failed to get database connection")
        raise HTTPException(status_code=500, detail="Database connection error")
    return db

# Function to extract spreadsheet ID from URL
def extract_spreadsheet_id(url):
    """
    Extract the spreadsheet ID from a Google Sheets URL
    
    Example URLs:
    - https://docs.google.com/spreadsheets/d/1234567890abcdefg/edit#gid=0
    - https://docs.google.com/spreadsheets/d/1234567890abcdefg/edit?usp=sharing
    """
    # Pattern to match spreadsheet ID in Google Sheets URL
    pattern = r'https://docs\.google\.com/spreadsheets/d/([a-zA-Z0-9-_]+)'
    match = re.match(pattern, url)
    
    if match:
        return match.group(1)
    else:
        # If it's not a URL, assume it's already an ID
        return url

# Define the request models
class SheetVerifyRequest(BaseModel):
    spreadsheet_url: str
    agency_id: str
    
    @field_validator('spreadsheet_url')
    def validate_spreadsheet_url(cls, v):
        if not v:
            raise ValueError('Spreadsheet URL is required')
        return v
    
    @field_validator('agency_id')
    def validate_agency_id(cls, v):
        if not v:
            raise ValueError('Agency ID is required')
        return v

class ColumnCheckRequest(BaseModel):
    spreadsheet_url: str
    sheet_name: Optional[str] = "Sheet1"
    agency_id: str
    
    @field_validator('spreadsheet_url')
    def validate_spreadsheet_url(cls, v):
        if not v:
            raise ValueError('Spreadsheet URL is required')
        return v
    
    @field_validator('agency_id')
    def validate_agency_id(cls, v):
        if not v:
            raise ValueError('Agency ID is required')
        return v

# Required column headers in exact order
REQUIRED_COLUMNS = [
    "Name",
    "Last Name",
    "Website Link",
    "LinkedIn",
    "Email",
    "Podcast Name",
    "Episode Link",
    "Episode Transcript",
    "Avatar Deets",
    "Recent LinkedIn Post",
    # "Copy - Recent LinkedIn Post",
    "AboutUs / Mission Page",
    # "Copy - AboutUs / Mission Page",
    "E-Book Page Link",
    # "Copy - Ebook",
    "Recent Blog",
    # "Copy - Recent Blog (3-6 Months)",
    "Testimonials / Reviews Page Link",
    # "Copy - Testimonials / Reviews",
    "Webinar/Events Page Link",
    # "Copy - Webinar/Events",
    "Recent News (TBD)",
    "Custom Outreach Message"
]

# REQUIRED_COLUMNS_V2 = [
#     "First Name",
#     "Last Name",
#     "Website",
#     "Contact LI Profile URL",
#     "Email",
#     "Podcast Name",
#     "Episode Link",
#     "Episode Transcript",
#     "Website Content",
#     "Industry",
#     "Custom Message"
# ]

def update_or_create_sheet_record(agency_id, spreadsheet_url, spreadsheet_id, sheet_name, status):
    """
    Update an existing sheet record or create a new one
    """
    now = datetime.utcnow()
    
    # Get database connection
    db = get_database()
    
    # Try to find an existing record for this agency and sheet
    existing_record = db.agency_sheets.find_one({
        "agency_id": agency_id,
        "sheet_id": spreadsheet_id
    })
    
    if existing_record:
        # Update existing record
        db.agency_sheets.update_one(
            {"_id": existing_record["_id"]},
            {
                "$set": {
                    "status": status,
                    "sheet_url": spreadsheet_url,  # Update URL in case it changed
                    "sheet_name": sheet_name,      # Add/update sheet name
                    "updated_at": now
                }
            }
        )
        logger.info(f"Updated sheet record for agency {agency_id}, sheet {spreadsheet_id} with status {status}")
    else:
        # Create new record
        db.agency_sheets.insert_one({
            "agency_id": agency_id,
            "sheet_url": spreadsheet_url,
            "sheet_id": spreadsheet_id,
            "sheet_name": sheet_name,  # Include sheet name in new records
            "status": status,
            "created_at": now,
            "updated_at": now
        })
        logger.info(f"Created new sheet record for agency {agency_id}, sheet {spreadsheet_id} with status {status}")

@router.post("/verify-access")
def verify_sheet_access(request: SheetVerifyRequest):
    """
    Verify if the Google Sheet is accessible by the service account and update the database
    """
    credentials_file = "data/url-to-email-445616-cebe4868914f.json"
    
    try:
        # Extract spreadsheet ID from URL
        spreadsheet_id = extract_spreadsheet_id(request.spreadsheet_url)
        logger.info(f"Extracted spreadsheet ID: {spreadsheet_id} from URL: {request.spreadsheet_url}")
        logger.info(f"Verifying access to spreadsheet: {spreadsheet_id} for agency: {request.agency_id}")
        
        # Set up credentials
        creds = service_account.Credentials.from_service_account_file(
            credentials_file,
            scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"]
        )
        
        # Build the Sheets API service
        service = build('sheets', 'v4', credentials=creds)
        
        # Test access by requesting spreadsheet metadata
        sheet_metadata = service.spreadsheets().get(
            spreadsheetId=spreadsheet_id
        ).execute()
        
        # If we get here, access is granted
        sheet_title = sheet_metadata.get('properties', {}).get('title', 'Untitled')
        
        # Update database with CONNECTED status
        update_or_create_sheet_record(
            agency_id=request.agency_id,
            spreadsheet_url=request.spreadsheet_url,
            spreadsheet_id=spreadsheet_id,
            sheet_name=sheet_title,  # Save the sheet name
            status="CONNECTED"
        )
        
        return {
            "accessible": True,
            "spreadsheet_url": request.spreadsheet_url,
            "spreadsheet_id": spreadsheet_id,
            "agency_id": request.agency_id,
            "status": "CONNECTED",
            "title": sheet_title,
            "sheet_names": [sheet.get('properties', {}).get('title') 
                           for sheet in sheet_metadata.get('sheets', [])]
        }
        
    except HttpError as error:
        status = "NO_ACCESS"
        error_message = ""
        
        if error.resp.status == 404:
            error_message = "Spreadsheet not found. Check if the URL is correct."
        elif error.resp.status == 403:
            error_message = "Permission denied. Make sure the sheet is shared with the service account email: umang-utk@url-to-email-445616.iam.gserviceaccount.com"
        else:
            error_message = f"API error: {str(error)}"
        
        # Update database with NO_ACCESS status
        # Use a placeholder for sheet_name in error cases
        update_or_create_sheet_record(
            agency_id=request.agency_id,
            spreadsheet_url=request.spreadsheet_url,
            spreadsheet_id=spreadsheet_id,
            sheet_name="Unknown Sheet",  # Use placeholder for errors
            status=status
        )
        
        logger.error(f"Error verifying sheet access: {error_message}")
        return {
            "accessible": False,
            "spreadsheet_url": request.spreadsheet_url,
            "spreadsheet_id": spreadsheet_id,
            "agency_id": request.agency_id,
            "status": status,
            "error": error_message
        }
            
    except Exception as e:
        logger.error(f"Error verifying sheet access: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to verify access: {str(e)}")

@router.post("/verify-columns")
def verify_sheet_columns(request: ColumnCheckRequest):
    """
    Verify if the Google Sheet has the required columns in the correct order
    """
    credentials_file = "data/url-to-email-445616-cebe4868914f.json"
    
    try:
        # Extract spreadsheet ID from URL
        spreadsheet_id = extract_spreadsheet_id(request.spreadsheet_url)
        logger.info(f"Extracted spreadsheet ID: {spreadsheet_id} from URL: {request.spreadsheet_url}")
        logger.info(f"Verifying columns for spreadsheet: {spreadsheet_id}, sheet: {request.sheet_name}, agency: {request.agency_id}")
        
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
            spreadsheetId=spreadsheet_id,
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
                "agency_id": request.agency_id,
                "message": "All required columns are present in the correct order",
                "found_headers": headers
            }
        else:
            return {
                "valid": False,
                "agency_id": request.agency_id,
                "spreadsheet_url": request.spreadsheet_url,
                "missing_columns": missing_columns,
                "misplaced_columns": misplaced_columns,
                "required_columns": REQUIRED_COLUMNS,
                "found_headers": headers
            }
            
    except HttpError as error:
        if error.resp.status == 404:
            return {
                "valid": False,
                "agency_id": request.agency_id,
                "spreadsheet_url": request.spreadsheet_url,
                "error": "Spreadsheet or sheet not found. Check if the URL and sheet name are correct."
            }
        elif error.resp.status == 403:
            return {
                "valid": False,
                "agency_id": request.agency_id,
                "spreadsheet_url": request.spreadsheet_url,
                "error": "Permission denied. Make sure the sheet is shared with the service account."
            }
        else:
            logger.error(f"Error verifying sheet columns: {str(error)}")
            return {
                "valid": False,
                "agency_id": request.agency_id,
                "spreadsheet_url": request.spreadsheet_url,
                "error": f"API error: {str(error)}"
            }
    except Exception as e:
        logger.error(f"Error verifying sheet columns: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to verify columns: {str(e)}")

class LastRowRequest(BaseModel):
    spreadsheet_url: str
    sheet_name: Optional[str] = "Sheet1"
    use_version: Optional[str] = "v2"
    agency_id: str
    
    @field_validator('spreadsheet_url')
    def validate_spreadsheet_url(cls, v):
        if not v:
            raise ValueError('Spreadsheet URL is required')
        return v
    
    @field_validator('use_version')
    def validate_version(cls, v):
        if v not in ['v1', 'v2']:
            raise ValueError('Version must be either "v1" or "v2"')
        return v
    
    @field_validator('agency_id')
    def validate_agency_id(cls, v):
        if not v:
            raise ValueError('Agency ID is required')
        return v

@router.post("/get-last-filled-rows")
def get_last_filled_rows(request: LastRowRequest):
    """
    Get the last filled row for each of the required columns
    """
    credentials_file = "data/url-to-email-445616-cebe4868914f.json"
    
    try:
        # Extract spreadsheet ID from URL
        spreadsheet_id = extract_spreadsheet_id(request.spreadsheet_url)
        logger.info(f"Extracted spreadsheet ID: {spreadsheet_id} from URL: {request.spreadsheet_url}")
        logger.info(f"Getting last filled rows for spreadsheet: {spreadsheet_id}, sheet: {request.sheet_name}, agency: {request.agency_id}")
        
        # Determine which required columns to use
        if request.use_version == "v1":
            required_columns = REQUIRED_COLUMNS
        else:  # v2
            required_columns = REQUIRED_COLUMNS
        
        # Set up credentials
        creds = service_account.Credentials.from_service_account_file(
            credentials_file,
            scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"]
        )
        
        # Build the Sheets API service
        service = build('sheets', 'v4', credentials=creds)
        
        # First, get the header row to find column positions
        range_name = f"{request.sheet_name}!A1:ZZ1"
        result = service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range=range_name
        ).execute()
        
        # Extract header values
        headers = result.get('values', [[]])[0] if result.get('values') else []
        
        # Map required column names to their positions (0-based index)
        column_positions = {}
        for i, header in enumerate(headers):
            if header in required_columns:
                column_positions[header] = i
        
        # Now get all data to find the last filled row for each column
        range_name = f"{request.sheet_name}"
        result = service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range=range_name
        ).execute()
        
        values = result.get('values', [])
        if not values:
            return {
                "error": "No data found in the sheet",
                "agency_id": request.agency_id,
                "spreadsheet_url": request.spreadsheet_url,
                "sheet_name": request.sheet_name
            }
        
        # Find the last row with data for each column
        last_filled_rows: Dict[str, Dict] = {}
        total_rows = len(values)
        
        for column_name, column_index in column_positions.items():
            last_row = 0
            
            # Start from row 1 (skip headers)
            for row_index in range(1, total_rows):
                row = values[row_index]
                # Check if this column has a value in this row
                if column_index < len(row) and row[column_index] and row[column_index].strip():
                    last_row = row_index + 1  # Add 1 because spreadsheet rows are 1-indexed
            
            last_filled_rows[column_name] = {
                "last_row": last_row
            }
        
        # Calculate the total number of filled rows and columns
        columns_with_data = 0
        max_row_with_data = 0
        
        for column_info in last_filled_rows.values():
            if column_info["last_row"] > 0:
                columns_with_data += 1
                max_row_with_data = max(max_row_with_data, column_info["last_row"])
        
        return {
            "agency_id": request.agency_id,
            "spreadsheet_url": request.spreadsheet_url,
            "sheet_name": request.sheet_name,
            "version": request.use_version,
            "total_rows": total_rows,
            "columns_with_data": columns_with_data,
            "max_row_with_data": max_row_with_data,
            "last_filled_rows": last_filled_rows,
            "column_positions": column_positions
        }
            
    except HttpError as error:
        logger.error(f"HTTP Error getting last filled rows: {str(error)}")
        if error.resp.status == 404:
            return {
                "error": "Spreadsheet or sheet not found. Check if the URL and sheet name are correct.",
                "agency_id": request.agency_id,
                "spreadsheet_url": request.spreadsheet_url
            }
        elif error.resp.status == 403:
            return {
                "error": "Permission denied. Make sure the sheet is shared with the service account.",
                "agency_id": request.agency_id,
                "spreadsheet_url": request.spreadsheet_url
            }
        else:
            return {
                "error": f"API error: {str(error)}",
                "agency_id": request.agency_id,
                "spreadsheet_url": request.spreadsheet_url
            }
    except Exception as e:
        logger.error(f"Error getting last filled rows: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get last filled rows: {str(e)}")

@router.get("/status/{agency_id}")
def get_sheet_status(agency_id: str):
    """
    Get the status of all sheets associated with an agency
    """
    try:
        # Get database connection
        db = get_database()
        
        # Find all sheet records for this agency
        records = list(db.agency_sheets.find({"agency_id": agency_id}))
        
        if not records:
            return {
                "agency_id": agency_id,
                "sheets": []
            }
        
        # Format the records for response
        sheets = []
        for record in records:
            sheets.append({
                "sheet_id": record["sheet_id"],
                "sheet_url": record["sheet_url"],
                "sheet_name": record.get("sheet_name", "Untitled"),
                "status": record["status"],
                "updated_at": record.get("updated_at", None),
                "created_at": record.get("created_at", None)
            })
        
        return {
            "agency_id": agency_id,
            "sheets": sheets
        }
            
    except Exception as e:
        logger.error(f"Error getting sheet status: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to get sheet status: {str(e)}")

# Update sheet status
class UpdateStatusRequest(BaseModel):
    agency_id: str
    spreadsheet_url: str
    status: SheetStatus
    
    @field_validator('agency_id')
    def validate_agency_id(cls, v):
        if not v:
            raise ValueError('Agency ID is required')
        return v
    
    @field_validator('spreadsheet_url')
    def validate_spreadsheet_url(cls, v):
        if not v:
            raise ValueError('Spreadsheet URL is required')
        return v

@router.post("/update-status")
def update_sheet_status(request: UpdateStatusRequest):
    """
    Update the status of a sheet
    """
    try:
        # Extract spreadsheet ID from URL
        spreadsheet_id = extract_spreadsheet_id(request.spreadsheet_url)
        
        # Update the status in the database
        update_or_create_sheet_record(
            agency_id=request.agency_id,
            spreadsheet_url=request.spreadsheet_url,
            spreadsheet_id=spreadsheet_id,
            status=request.status
        )
        
        return {
            "success": True,
            "agency_id": request.agency_id,
            "spreadsheet_id": spreadsheet_id,
            "status": request.status
        }
            
    except Exception as e:
        logger.error(f"Error updating sheet status: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to update sheet status: {str(e)}")