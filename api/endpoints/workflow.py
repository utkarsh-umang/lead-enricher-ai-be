from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import logging
from typing import List, Optional, Dict
import os
from utils.helpers import process_url
from google_utils.google_sheet import GoogleSheetService
from llm_utils.gpt_utils import GPTService
from data.constants import (
    DEFAULT_SHEET_NAME, 
    COLUMN_PODCAST_TRANSCRIPT, 
    COLUMN_AVATAR_DEETS,
    AVATAR_DEETS_PROMPT,
    STATUS_SUCCESS,
    STATUS_ERROR,
    STATUS_PARTIAL,
    DEFAULT_BATCH_SIZE
)

# Create router
router = APIRouter(
    prefix="/workflow",
    tags=["Workflow Scripts"],
    responses={404: {"description": "Not found"}},
)

# Get logger
logger = logging.getLogger(__name__)

# Define request/response models
class ProcessAvatarDeetsRequest(BaseModel):
    spreadsheet_id: str
    sheet_name: str = DEFAULT_SHEET_NAME
    start_row: Optional[int] = 2
    end_row: Optional[int] = None
    batch_size: Optional[int] = DEFAULT_BATCH_SIZE

class ProcessResponse(BaseModel):
    status: str
    processed_rows: int
    successful_rows: List[int]
    failed_rows: Dict[int, str]
    message: str

class ProcessWebsiteContentRequest(BaseModel):
    spreadsheet_id: str
    sheet_name: str = DEFAULT_SHEET_NAME
    url_column_index: int  # Column index (0-based) containing URLs
    content_column_index: int  # Column index (0-based) to write scraped content
    start_row: Optional[int] = 2
    limit: Optional[int] = 50

class ProcessResponse(BaseModel):
    status: str
    processed_rows: int
    successful_rows: List[int]
    failed_rows: Dict[int, str]
    message: str

# Route for processing Avatar Deets
@router.post("/process-avatar-deets", response_model=ProcessResponse)
async def process_avatar_deets(request: ProcessAvatarDeetsRequest):
    """
    Process podcast transcripts to fill the Avatar Deets column
    
    This endpoint analyzes podcast transcripts using GPT and updates 
    the Avatar Deets column with extracted information.
    """
    try:
        # Validate API key
        api_key = os.getenv('OPENAI_API_KEY')
        logger.info(f"OpenAI API key present: {'Yes' if api_key else 'No'}")
        
        if not api_key:
            # Try to load the key again directly
            from dotenv import load_dotenv
            load_dotenv()
            api_key = os.getenv('OPENAI_API_KEY')
            logger.info(f"Retry loading OpenAI API key - present: {'Yes' if api_key else 'No'}")
            
            if not api_key:
                raise HTTPException(status_code=500, detail="OpenAI API key not configured. Please check your .env file.")
        
        # Initialize services
        sheet_service = GoogleSheetService()
        gpt_service = GPTService(api_key)
        
        # Get podcast transcript data
        success, transcript_data = sheet_service.get_column_data(
            request.spreadsheet_id, 
            request.sheet_name, 
            COLUMN_PODCAST_TRANSCRIPT
        )
        
        if not success:
            logger.error(f"Failed to get podcast transcript data: {transcript_data}")
            raise HTTPException(status_code=400, detail=f"Failed to get podcast transcript data: {transcript_data}")
        
        # Track results
        successful_rows = []
        failed_rows = {}
        
        # Determine range to process
        total_rows = len(transcript_data)
        start_row = request.start_row
        end_row = min(request.end_row or (start_row + total_rows - 1), start_row + total_rows - 1)
        
        logger.info(f"Processing rows {start_row} to {end_row} (total: {end_row - start_row + 1})")
        
        # Process each row
        for sheet_row in range(start_row, end_row + 1):
            # Calculate the corresponding index in transcript_data (0-based)
            transcript_index = sheet_row - start_row
            
            try:
                # Skip if index is out of bounds
                if transcript_index >= len(transcript_data):
                    logger.warning(f"Row {sheet_row} exceeds available transcript data (index {transcript_index})")
                    failed_rows[sheet_row] = "No transcript data (index out of bounds)"
                    continue
                    
                # Skip empty transcripts
                if not transcript_data[transcript_index]:
                    logger.info(f"Skipping row {sheet_row}: No transcript data")
                    failed_rows[sheet_row] = "No transcript data"
                    continue
                
                transcript = transcript_data[transcript_index]
                
                # Skip if transcript seems like an error message
                if transcript.startswith("Error:"):
                    logger.info(f"Skipping row {sheet_row}: Transcript contains error")
                    failed_rows[sheet_row] = "Transcript contains error"
                    continue
                
                # Process with GPT
                logger.info(f"Processing transcript for row {sheet_row}")
                gpt_result = gpt_service.process_content(transcript, AVATAR_DEETS_PROMPT)
                
                if not gpt_result["success"]:
                    logger.error(f"GPT processing failed for row {sheet_row}: {gpt_result.get('error')}")
                    failed_rows[sheet_row] = gpt_result.get('error', 'Unknown GPT error')
                    continue
                
                # Update the Avatar Deets column
                update_success, update_message = sheet_service.update_cell(
                    request.spreadsheet_id,
                    request.sheet_name,
                    sheet_row,
                    COLUMN_AVATAR_DEETS,
                    gpt_result["result"]
                )
                
                if update_success:
                    logger.info(f"Successfully updated Avatar Deets for row {sheet_row}")
                    successful_rows.append(sheet_row)
                else:
                    logger.error(f"Failed to update Avatar Deets for row {sheet_row}: {update_message}")
                    failed_rows[sheet_row] = f"Failed to update: {update_message}"
                
            except Exception as e:
                logger.error(f"Error processing row {sheet_row}: {str(e)}")
                failed_rows[sheet_row] = str(e)
        
        # Determine final status
        total_processed = len(successful_rows) + len(failed_rows)
        status = STATUS_SUCCESS
        
        if total_processed == 0:
            status = STATUS_ERROR
            message = "No rows were processed"
        elif len(failed_rows) > 0 and len(successful_rows) > 0:
            status = STATUS_PARTIAL
            message = f"Partially successful: {len(successful_rows)} rows updated, {len(failed_rows)} rows failed"
        elif len(successful_rows) > 0:
            message = f"Successfully updated {len(successful_rows)} rows"
        else:
            status = STATUS_ERROR
            message = f"Failed to update any rows. {len(failed_rows)} rows attempted"
        
        return ProcessResponse(
            status=status,
            processed_rows=total_processed,
            successful_rows=successful_rows,
            failed_rows=failed_rows,
            message=message
        )
        
    except Exception as e:
        logger.error(f"Error processing Avatar Deets: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to process: {str(e)}")
    except Exception as e:
        logger.error(f"Error starting Avatar Deets processing: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to start processing: {str(e)}")

@router.post("/process-website-content", response_model=ProcessResponse)
async def process_website_content(request: ProcessWebsiteContentRequest):
    """
    Process URLs from a Google Sheet column and scrape their content
    This endpoint scrapes website content from URLs in the specified column
    and updates another column with the scraped content.
    """
    try:
        # Initialize service
        sheet_service = GoogleSheetService()
        
        # Get URL data from the specified column
        # Modified to pass start_row to ensure we're getting data from the correct row
        success, url_data = sheet_service.get_column_data(
            request.spreadsheet_id,
            request.sheet_name,
            request.url_column_index,
            start_row=request.start_row 
        )
        
        if not success:
            logger.error(f"Failed to get URL data: {url_data}")
            raise HTTPException(status_code=400, detail=f"Failed to get URL data: {url_data}")
        
        # Track results
        successful_rows = []
        failed_rows = {}
        
        # Determine range to process
        start_row = request.start_row
        end_row = min(start_row + request.limit - 1, start_row + len(url_data) - 1)
        
        logger.info(f"Processing rows {start_row} to {end_row} (total: {end_row - start_row + 1})")
        
        # Process each row
        for sheet_row in range(start_row, end_row + 1):
            # Calculate the corresponding index in url_data (0-based)
            url_index = sheet_row - start_row
            
            try:
                # Skip if index is out of bounds
                if url_index >= len(url_data):
                    logger.warning(f"Row {sheet_row} exceeds available URL data (index {url_index})")
                    failed_rows[sheet_row] = "No URL data (index out of bounds)"
                    continue
                    
                # Skip empty URLs
                if not url_data[url_index]:
                    logger.info(f"Skipping row {sheet_row}: No URL data")
                    failed_rows[sheet_row] = "No URL data"
                    continue
                
                url = url_data[url_index]
                
                # Skip if URL seems like an error message
                if url.startswith("Error:"):
                    logger.info(f"Skipping row {sheet_row}: URL contains error")
                    failed_rows[sheet_row] = "URL contains error"
                    continue
                
                # Process the URL
                logger.info(f"Processing URL for row {sheet_row}: {url}")
                try:
                    content_result = process_url(url)
                    
                    # Update the content column
                    update_success, update_message = sheet_service.update_cell(
                        request.spreadsheet_id,
                        request.sheet_name,
                        sheet_row,
                        request.content_column_index,
                        str(content_result) if content_result is not None else "NA"
                    )
                    
                    if update_success:
                        logger.info(f"Successfully updated content for row {sheet_row}")
                        successful_rows.append(sheet_row)
                    else:
                        logger.error(f"Failed to update content for row {sheet_row}: {update_message}")
                        failed_rows[sheet_row] = f"Failed to update: {update_message}"
                    
                except Exception as e:
                    logger.error(f"Error scraping URL at row {sheet_row}: {str(e)}")
                    failed_rows[sheet_row] = f"Scraping error: {str(e)}"
                
            except Exception as e:
                logger.error(f"Error processing row {sheet_row}: {str(e)}")
                failed_rows[sheet_row] = str(e)
        
        # Determine final status
        total_processed = len(successful_rows) + len(failed_rows)
        status = STATUS_SUCCESS
        
        if total_processed == 0:
            status = STATUS_ERROR
            message = "No rows were processed"
        elif len(failed_rows) > 0 and len(successful_rows) > 0:
            status = STATUS_PARTIAL
            message = f"Partially successful: {len(successful_rows)} rows updated, {len(failed_rows)} rows failed"
        elif len(successful_rows) > 0:
            message = f"Successfully updated {len(successful_rows)} rows"
        else:
            status = STATUS_ERROR
            message = f"Failed to update any rows. {len(failed_rows)} rows attempted"
        
        return ProcessResponse(
            status=status,
            processed_rows=total_processed,
            successful_rows=successful_rows,
            failed_rows=failed_rows,
            message=message
        )
        
    except Exception as e:
        logger.error(f"Error processing website content: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to process: {str(e)}")