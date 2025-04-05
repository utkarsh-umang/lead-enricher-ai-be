# Column dependencies
DEPENDENCIES = {
    "podcast_transcript": ["podcast_link"],
    "website_content": ["website"],
    "industry": ["podcast_transcript"],
    "custom_email": ["podcast_transcript", "website_content", "industry"]
}
from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, List, Any
import logging
import httpx
import asyncio
from datetime import datetime

# Create router
router = APIRouter(
    prefix="/orchestrator",
    tags=["Workflow Orchestrator"],
    responses={404: {"description": "Not found"}},
)

# Get logger
logger = logging.getLogger(__name__)

# Define request/response models
class OrchestratorRequest(BaseModel):
    spreadsheet_url: str
    sheet_name: Optional[str] = "Sheet1"
    start_row: Optional[int] = 2
    end_row: Optional[int] = None
    batch_size: Optional[int] = 10
    process_all: Optional[bool] = False

class OrchestratorResponse(BaseModel):
    status: str
    message: str
    job_id: Optional[str] = None

# Column mapping for reference (adjusted to match the API response)
COLUMN_MAPPING = {
    "first_name": 0,              # Column A - "First Name"
    "last_name": 1,               # Column B - "Last Name"
    "website": 2,                 # Column C - "Website"
    "linkedin": 3,                # Column D - "Contact LI Profile URL"
    "email": 4,                   # Column E - "Email"
    "podcast_name": 5,            # Column F - "Podcast Name"
    "podcast_link": 6,            # Column G - "Episode Link"
    "podcast_transcript": 7,      # Column H - "Episode Transcript"
    "website_content": 8,         # Column I - "Website Content"
    "industry": 9,                # Column J - "Industry"
    "custom_email": 10            # Column K - "Custom Message"
}

# Map API response column names to our internal names
COLUMN_NAME_MAPPING = {
    "First Name": "first_name",
    "Last Name": "last_name",
    "Website": "website",
    "Contact LI Profile URL": "linkedin",
    "Email": "email",
    "Podcast Name": "podcast_name",
    "Episode Link": "podcast_link",
    "Episode Transcript": "podcast_transcript",
    "Website Content": "website_content",
    "Industry": "industry",
    "Custom Message": "custom_email"
}

# Update all API endpoint URLs to match your router
API_BASE_URL = ""  # No /api prefix

# API endpoint mapping
API_ENDPOINTS = {
    "get_last_filled_rows": f"{API_BASE_URL}/google-sheet/get-last-filled-rows",
    "process_website_content": f"{API_BASE_URL}/workflow/process-website-content",
    "process_industry": f"{API_BASE_URL}/workflow/process-icp-segmentation",
    "process_custom_email": f"{API_BASE_URL}/workflow/process-outreach",
    "youtube_transcript": f"{API_BASE_URL}/workflow/youtube-transcript"
}

# Tracking active jobs
active_jobs = {}

async def process_api_request(url: str, payload: Dict[str, Any], client: httpx.AsyncClient, job_id: str = None) -> Dict[str, Any]:
    """Helper function to make API requests with improved error handling"""
    # Track API call for debugging
    call_info = {
        "url": url,
        "payload": payload,
        "timestamp": datetime.now().isoformat()
    }
    
    if job_id and job_id in active_jobs:
        active_jobs[job_id]["debug_info"]["api_calls"].append(call_info)
    
    # Add retry mechanism
    max_retries = 3
    retry_count = 0
    retry_delay = 2  # seconds
    
    while retry_count < max_retries:
        try:
            logger.info(f"Making API request to {url} with payload: {payload}")
            
            # Add timeout to prevent hanging indefinitely
            response = await client.post(url, json=payload, timeout=60.0)
            response.raise_for_status()
            result = response.json()
            
            # Log the response for debugging
            call_info["status_code"] = response.status_code
            call_info["response"] = result
            
            return result
            
        except httpx.TimeoutException as e:
            retry_count += 1
            error_msg = f"Request timeout (attempt {retry_count}/{max_retries}): {str(e)}"
            logger.warning(error_msg)
            
            if retry_count < max_retries:
                logger.info(f"Retrying in {retry_delay} seconds...")
                await asyncio.sleep(retry_delay)
                retry_delay *= 2  # Exponential backoff
            else:
                logger.error(f"Max retries reached: {error_msg}")
                call_info["status_code"] = "timeout"
                call_info["error"] = error_msg
                return {"status": "error", "message": error_msg}
                
        except httpx.HTTPStatusError as e:
            error_msg = f"HTTP error: {e.response.status_code} - {e.response.text}"
            logger.error(error_msg)
            
            # Log the error for debugging
            call_info["status_code"] = e.response.status_code
            call_info["error"] = error_msg
            
            # Don't retry 4xx client errors, only retry 5xx server errors
            if 500 <= e.response.status_code < 600 and retry_count < max_retries:
                retry_count += 1
                logger.info(f"Retrying in {retry_delay} seconds...")
                await asyncio.sleep(retry_delay)
                retry_delay *= 2  # Exponential backoff
            else:
                return {"status": "error", "message": error_msg}
                
        except httpx.NetworkError as e:
            retry_count += 1
            error_msg = f"Network error (attempt {retry_count}/{max_retries}): {str(e)}"
            logger.warning(error_msg)
            
            if retry_count < max_retries:
                logger.info(f"Retrying in {retry_delay} seconds...")
                await asyncio.sleep(retry_delay)
                retry_delay *= 2  # Exponential backoff
            else:
                logger.error(f"Max retries reached: {error_msg}")
                call_info["error"] = error_msg
                return {"status": "error", "message": error_msg}
                
        except Exception as e:
            error_msg = f"Request error: {str(e)}"
            logger.error(error_msg)
            
            # Log the error for debugging
            call_info["error"] = error_msg
            
            return {"status": "error", "message": error_msg}
    
def determine_next_row_to_process(column_status: Dict, start_row: int = 2) -> int:
    """Determine the next row that needs processing in any column"""
    # Find the minimum row where any column needs processing
    min_row = float('inf')
    
    # Check each target column against its dependencies
    for target_col, dependencies in DEPENDENCIES.items():
        api_target_col = next((k for k, v in COLUMN_NAME_MAPPING.items() if v == target_col), target_col)
        target_last_row = column_status.get(api_target_col, {}).get("last_row", 0)
        
        # Check each dependency
        for dep in dependencies:
            api_dep_col = next((k for k, v in COLUMN_NAME_MAPPING.items() if v == dep), dep)
            dep_last_row = column_status.get(api_dep_col, {}).get("last_row", 0)
            
            # If dependency has data but target doesn't
            if dep_last_row > target_last_row:
                # Next row that needs target data is target_last_row + 1
                min_row = min(min_row, target_last_row + 1)
    
    # Return the earliest row that needs processing, if any
    if min_row == float('inf'):
        return start_row  # Default to requested start row if nothing needs processing
    else:
        return max(min_row, start_row)  # Don't go below requested start row

async def orchestrate_workflow(request: OrchestratorRequest, job_id: str):
    """Main workflow orchestration function that runs in the background"""
    print(f"[DEBUG] Starting job {job_id} for spreadsheet: {request.spreadsheet_url}")
    
    # Update job status
    active_jobs[job_id] = {
        "status": "running",
        "start_time": datetime.now().isoformat(),
        "spreadsheet_url": request.spreadsheet_url,
        "sheet_name": request.sheet_name,
        "progress": {},
        "debug_info": {
            "api_calls": []
        }
    }
    
    try:
        print(f"[DEBUG] Setting up HTTP client")
        async with httpx.AsyncClient(timeout=300) as client:
            # Step 1: Get the current state of the sheet
            spreadsheet_id = extract_spreadsheet_id(request.spreadsheet_url)
            print(f"[DEBUG] Extracted spreadsheet ID: {spreadsheet_id}")
            
            status_payload = {
                "spreadsheet_url": request.spreadsheet_url,
                "sheet_name": request.sheet_name,
                "use_version": "v2"
            }
            print(f"[DEBUG] Status payload: {status_payload}")
            
            # Print all API endpoints
            print(f"[DEBUG] API Endpoints:")
            for name, url in API_ENDPOINTS.items():
                print(f"[DEBUG]   {name}: {url}")
            
            print(f"[DEBUG] Calling get_last_filled_rows API at {API_ENDPOINTS['get_last_filled_rows']}")
            status_result = await process_api_request(
                API_ENDPOINTS["get_last_filled_rows"], 
                status_payload,
                client,
                job_id
            )
            print(f"[DEBUG] Status result received: {type(status_result)}")
            
            # Error handling for empty or unexpected responses
            if "error" in status_result:
                print(f"[DEBUG] Error found in status result: {status_result['error']}")
                active_jobs[job_id]["status"] = "error"
                active_jobs[job_id]["message"] = status_result["error"]
                return
                
            if "last_filled_rows" not in status_result:
                print(f"[DEBUG] 'last_filled_rows' missing from status result. Full result: {status_result}")
                active_jobs[job_id]["status"] = "error"
                active_jobs[job_id]["message"] = f"API response missing 'last_filled_rows'. Response: {status_result}"
                return
            
            # Extract information about which columns have data
            column_status = status_result["last_filled_rows"]
            print(f"[DEBUG] Column status extracted: {len(column_status)} columns found")
            
            # Verify column_status has data
            if not column_status:
                print(f"[DEBUG] Empty column status in API response")
                active_jobs[job_id]["status"] = "error"
                active_jobs[job_id]["message"] = f"Empty column status in API response: {status_result}"
                return
                
            # Store column status in job info for reference
            active_jobs[job_id]["column_status"] = column_status
            
            # Determine the range of rows to process
            # Find the next row that needs processing based on all column dependencies
            next_row_to_process = determine_next_row_to_process(column_status, request.start_row)
            print(f"[DEBUG] Next row needing processing: {next_row_to_process}")
            
            max_row = status_result.get("max_row_with_data", 0)
            end_row = request.end_row or max_row
            print(f"[DEBUG] Row range: start={next_row_to_process}, max={max_row}, end={end_row}")
            
            if request.process_all:
                # Process all rows with data
                rows_to_process = list(range(next_row_to_process, max_row + 1))
            else:
                # Process only up to batch_size rows
                rows_to_process = list(range(next_row_to_process, min(next_row_to_process + request.batch_size, end_row + 1)))
            
            print(f"[DEBUG] Rows to process: {rows_to_process}")
            
            # Update job status with processing range
            active_jobs[job_id]["rows_to_process"] = rows_to_process
            active_jobs[job_id]["total_rows"] = len(rows_to_process)
            active_jobs[job_id]["processed_rows"] = 0
            
            # PHASE 1: Process podcast transcript, website content, and industry for each row
            print(f"[DEBUG] PHASE 1: Starting to process transcript, website content, and industry for {len(rows_to_process)} rows")
            processed_transcript_rows = []
            processed_website_content_rows = []
            processed_industry_rows = []
            
            for row in rows_to_process:
                try:
                    print(f"[DEBUG] Processing row {row} (Phase 1)")
                    row_log = {
                        "row": row,
                        "steps": [],
                        "phase1_success": {}
                    }
                    active_jobs[job_id]["progress"][row] = row_log
                    
                    # Process podcast transcript if needed
                    api_podcast_link = next((k for k, v in COLUMN_NAME_MAPPING.items() if v == "podcast_link"), "podcast_link")
                    api_podcast_transcript = next((k for k, v in COLUMN_NAME_MAPPING.items() if v == "podcast_transcript"), "podcast_transcript")
                    
                    podcast_link_last_row = column_status.get(api_podcast_link, {}).get("last_row", 0)
                    podcast_transcript_last_row = column_status.get(api_podcast_transcript, {}).get("last_row", 0)
                    
                    if podcast_link_last_row >= row and podcast_transcript_last_row < row:
                        print(f"[DEBUG] Phase 1: Row {row} needs podcast transcript processing")
                        result = await process_podcast_transcript(row, request, client, job_id)
                        success = (result.get("status", "").lower() == "success" or "Successfully" in result.get("message", ""))
                        row_log["phase1_success"]["podcast_transcript"] = success
                        if success:
                            processed_transcript_rows.append(row)
                    else:
                        row_log["phase1_success"]["podcast_transcript"] = (podcast_transcript_last_row >= row)
                    
                    # Process website content if needed
                    api_website = next((k for k, v in COLUMN_NAME_MAPPING.items() if v == "website"), "website")
                    api_website_content = next((k for k, v in COLUMN_NAME_MAPPING.items() if v == "website_content"), "website_content")
                    
                    website_last_row = column_status.get(api_website, {}).get("last_row", 0)
                    website_content_last_row = column_status.get(api_website_content, {}).get("last_row", 0)
                    
                    if website_last_row >= row and website_content_last_row < row:
                        print(f"[DEBUG] Phase 1: Row {row} needs website content processing")
                        result = await process_website_content(row, request, client, job_id)
                        success = (result.get("status", "").lower() == "success" or "Successfully" in result.get("message", ""))
                        row_log["phase1_success"]["website_content"] = success
                        if success:
                            processed_website_content_rows.append(row)
                    else:
                        row_log["phase1_success"]["website_content"] = (website_content_last_row >= row)
                    
                    # Process industry if needed
                    api_industry = next((k for k, v in COLUMN_NAME_MAPPING.items() if v == "industry"), "industry")
                    industry_last_row = column_status.get(api_industry, {}).get("last_row", 0)
                    
                    if podcast_transcript_last_row >= row and industry_last_row < row:
                        print(f"[DEBUG] Phase 1: Row {row} needs industry processing")
                        result = await process_industry(row, request, client, job_id)
                        success = (result.get("status", "").lower() == "success" or "Successfully" in result.get("message", ""))
                        row_log["phase1_success"]["industry"] = success
                        if success:
                            processed_industry_rows.append(row)
                    else:
                        row_log["phase1_success"]["industry"] = (industry_last_row >= row)
                    
                    active_jobs[job_id]["processed_rows"] += 1
                except Exception as e:
                    print(f"[DEBUG] Error processing row {row} in Phase 1: {str(e)}")
                    logger.error(f"Error processing row {row} in Phase 1: {str(e)}")
                    active_jobs[job_id]["row_errors"] = active_jobs[job_id].get("row_errors", {})
                    active_jobs[job_id]["row_errors"][row] = str(e)
            
            # PHASE 2: Refresh sheet status and process custom emails
            print(f"[DEBUG] PHASE 1 complete. Refreshing sheet status for PHASE 2")
            print(f"[DEBUG] Summary of Phase 1: Processed transcripts: {len(processed_transcript_rows)}, websites: {len(processed_website_content_rows)}, industries: {len(processed_industry_rows)}")
            
            # Refresh status to see which rows now have all prerequisites
            refresh_status_result = await process_api_request(
                API_ENDPOINTS["get_last_filled_rows"], 
                status_payload,
                client,
                job_id
            )
            
            if "error" in refresh_status_result or "last_filled_rows" not in refresh_status_result:
                print(f"[DEBUG] Error refreshing status for Phase 2: {refresh_status_result}")
                active_jobs[job_id]["phase2_error"] = "Failed to refresh sheet status"
            else:
                # Updated column status after Phase 1
                updated_column_status = refresh_status_result["last_filled_rows"]
                print(f"[DEBUG] PHASE 2: Updated column status received")
                
                # Get the latest last row values
                api_podcast_transcript = next((k for k, v in COLUMN_NAME_MAPPING.items() if v == "podcast_transcript"), "podcast_transcript")
                api_website_content = next((k for k, v in COLUMN_NAME_MAPPING.items() if v == "website_content"), "website_content")
                api_industry = next((k for k, v in COLUMN_NAME_MAPPING.items() if v == "industry"), "industry")
                api_custom_email = next((k for k, v in COLUMN_NAME_MAPPING.items() if v == "custom_email"), "custom_email")
                
                podcast_transcript_last_row = updated_column_status.get(api_podcast_transcript, {}).get("last_row", 0)
                website_content_last_row = updated_column_status.get(api_website_content, {}).get("last_row", 0)
                industry_last_row = updated_column_status.get(api_industry, {}).get("last_row", 0)
                custom_email_last_row = updated_column_status.get(api_custom_email, {}).get("last_row", 0)
                
                print(f"[DEBUG] PHASE 2: Updated last rows - transcript: {podcast_transcript_last_row}, website: {website_content_last_row}, industry: {industry_last_row}, email: {custom_email_last_row}")
                
                # Find rows eligible for custom email processing
                eligible_rows = []
                for row in rows_to_process:
                    # Check if all prerequisites are met and email not yet generated
                    if (podcast_transcript_last_row >= row and 
                        website_content_last_row >= row and 
                        industry_last_row >= row and
                        custom_email_last_row < row):
                        eligible_rows.append(row)
                
                print(f"[DEBUG] PHASE 2: Found {len(eligible_rows)} rows eligible for custom email processing")
                
                # Process custom email for eligible rows
                for row in eligible_rows:
                    try:
                        print(f"[DEBUG] Processing custom email for row {row} (Phase 2)")
                        
                        # Ensure the row has a progress entry
                        if row not in active_jobs[job_id]["progress"]:
                            active_jobs[job_id]["progress"][row] = {
                                "row": row,
                                "steps": [],
                                "phase2_success": {}
                            }
                        elif "phase2_success" not in active_jobs[job_id]["progress"][row]:
                            active_jobs[job_id]["progress"][row]["phase2_success"] = {}
                        
                        # Process custom email
                        result = await process_custom_email(row, request, client, job_id)
                        
                        success = (result.get("status", "").lower() == "success" or "Successfully" in result.get("message", ""))
                        
                        # Store result
                        active_jobs[job_id]["progress"][row]["phase2_success"]["custom_email"] = success
                        
                    except Exception as e:
                        print(f"[DEBUG] Error processing custom email for row {row} in Phase 2: {str(e)}")
                        logger.error(f"Error processing custom email for row {row} in Phase 2: {str(e)}")
                        if "row_errors" not in active_jobs[job_id]:
                            active_jobs[job_id]["row_errors"] = {}
                        active_jobs[job_id]["row_errors"][row] = active_jobs[job_id]["row_errors"].get(row, "") + f" | Phase 2: {str(e)}"
            
            print(f"[DEBUG] All processing completed, marking job as completed")
            # Mark as completed
            active_jobs[job_id]["status"] = "completed"
            active_jobs[job_id]["end_time"] = datetime.now().isoformat()
            
            try:
                # Optional final status check after processing
                print(f"[DEBUG] Performing final status check...")
                final_status = await process_api_request(
                    API_ENDPOINTS["get_last_filled_rows"], 
                    status_payload,
                    client,
                    job_id
                )
                print(f"[DEBUG] Final status check completed")
                
                # Add error handling for final status call
                if "error" in final_status:
                    print(f"[DEBUG] Error in final status check: {final_status['error']}")
                    active_jobs[job_id]["final_status_error"] = final_status["error"]
                elif "last_filled_rows" not in final_status:
                    print(f"[DEBUG] Missing 'last_filled_rows' in final status: {final_status}")
                    active_jobs[job_id]["final_status_error"] = "Missing 'last_filled_rows' in response"
                else:
                    # Final status successful
                    active_jobs[job_id]["final_status"] = final_status
                    print(f"[DEBUG] Final status check successful")
                    print(f"[DEBUG] Job completely finished")
            except Exception as e:
                # Don't fail the job if final status check fails
                print(f"[DEBUG] Exception in final status check: {str(e)}")
                active_jobs[job_id]["final_status_error"] = str(e)
            
    except Exception as e:
        print(f"[DEBUG] Error in orchestration job {job_id}: {str(e)}")
        logger.error(f"Error in orchestration job {job_id}: {str(e)}")
        active_jobs[job_id]["status"] = "error"
        active_jobs[job_id]["message"] = str(e)
        active_jobs[job_id]["end_time"] = datetime.now().isoformat()

async def process_row(row: int, column_status: Dict, request: OrchestratorRequest, client: httpx.AsyncClient, job_id: str):
    """Process a single row through all required APIs based on the current state"""
    print(f"[DEBUG] process_row: Starting for row {row}")
    
    row_log = {
        "row": row,
        "steps": [],
        "processed_columns": {}  # Track which columns were successfully processed in this run
    }
    active_jobs[job_id]["progress"][row] = row_log
    
    # Step 1: Check if podcast transcript is needed
    api_podcast_link = next((k for k, v in COLUMN_NAME_MAPPING.items() if v == "podcast_link"), "podcast_link")
    api_podcast_transcript = next((k for k, v in COLUMN_NAME_MAPPING.items() if v == "podcast_transcript"), "podcast_transcript")
    
    podcast_link_last_row = column_status.get(api_podcast_link, {}).get("last_row", 0)
    podcast_transcript_last_row = column_status.get(api_podcast_transcript, {}).get("last_row", 0)
    
    print(f"[DEBUG] process_row: Checking podcast transcript need")
    print(f"[DEBUG] process_row: podcast_link column={api_podcast_link}, last row={podcast_link_last_row}")
    print(f"[DEBUG] process_row: podcast_transcript column={api_podcast_transcript}, last row={podcast_transcript_last_row}")
    
    # Process podcast transcript if link exists but transcript doesn't
    transcript_processed = False
    if podcast_link_last_row >= row and podcast_transcript_last_row < row:
        print(f"[DEBUG] process_row: Row {row} needs podcast transcript processing")
        transcript_result = await process_podcast_transcript(row, request, client, job_id)
        transcript_processed = (transcript_result.get("status", "").lower() == "success" or "Successfully" in transcript_result.get("message", ""))
        row_log["processed_columns"]["podcast_transcript"] = transcript_processed
        print(f"[DEBUG] process_row: Podcast transcript processed successfully? {transcript_processed}")
    else:
        print(f"[DEBUG] process_row: Row {row} already has podcast transcript or missing link")
    
    # Step 2: Process website content if needed
    api_website = next((k for k, v in COLUMN_NAME_MAPPING.items() if v == "website"), "website")
    api_website_content = next((k for k, v in COLUMN_NAME_MAPPING.items() if v == "website_content"), "website_content")
    
    website_last_row = column_status.get(api_website, {}).get("last_row", 0)
    website_content_last_row = column_status.get(api_website_content, {}).get("last_row", 0)
    
    print(f"[DEBUG] process_row: Checking website content need")
    print(f"[DEBUG] process_row: website column={api_website}, last row={website_last_row}")
    print(f"[DEBUG] process_row: website_content column={api_website_content}, last row={website_content_last_row}")
    
    # Process website content if website exists but content doesn't
    website_content_processed = False
    if website_last_row >= row and website_content_last_row < row:
        print(f"[DEBUG] process_row: Row {row} needs website content processing")
        website_result = await process_website_content(row, request, client, job_id)
        website_content_processed = (website_result.get("status", "").lower() == "success" or "Successfully" in website_result.get("message", ""))
        row_log["processed_columns"]["website_content"] = website_content_processed
        print(f"[DEBUG] process_row: Website content processed successfully? {website_content_processed}")
    else:
        print(f"[DEBUG] process_row: Row {row} already has website content or missing website")
    
    # Step 3: Determine industry if transcript is available but industry isn't
    api_industry = next((k for k, v in COLUMN_NAME_MAPPING.items() if v == "industry"), "industry")
    industry_last_row = column_status.get(api_industry, {}).get("last_row", 0)
    
    print(f"[DEBUG] process_row: Checking industry need")
    print(f"[DEBUG] process_row: industry column={api_industry}, last row={industry_last_row}")
    
    # Process industry if transcript exists but industry doesn't
    industry_processed = False
    if podcast_transcript_last_row >= row and industry_last_row < row:
        print(f"[DEBUG] process_row: Row {row} needs industry processing")
        industry_result = await process_industry(row, request, client, job_id)
        industry_processed = (industry_result.get("status", "").lower() == "success" or "Successfully" in industry_result.get("message", ""))
        row_log["processed_columns"]["industry"] = industry_processed
        print(f"[DEBUG] process_row: Industry processed successfully? {industry_processed}")
    else:
        print(f"[DEBUG] process_row: Row {row} already has industry or missing transcript")
    
    # Step 4: Generate custom email if all prerequisites are met
    api_custom_email = next((k for k, v in COLUMN_NAME_MAPPING.items() if v == "custom_email"), "custom_email")
    custom_email_last_row = column_status.get(api_custom_email, {}).get("last_row", 0)
    
    print(f"[DEBUG] process_row: Checking custom email need")
    print(f"[DEBUG] process_row: custom_email column={api_custom_email}, last row={custom_email_last_row}")
    
    # Check if all dependencies for custom email are filled
    # Consider both existing data and newly processed data in this run
    has_transcript = podcast_transcript_last_row >= row or row_log["processed_columns"].get("podcast_transcript", False)
    has_website_content = website_content_last_row >= row or row_log["processed_columns"].get("website_content", False)
    has_industry = industry_last_row >= row or row_log["processed_columns"].get("industry", False)
    needs_custom_email = custom_email_last_row < row
    
    dependencies_met = has_transcript and has_website_content and has_industry and needs_custom_email
    
    print(f"[DEBUG] process_row: Custom Email dependencies check:")
    print(f"[DEBUG] process_row: - Has transcript: {has_transcript}")
    print(f"[DEBUG] process_row: - Has website content: {has_website_content}")
    print(f"[DEBUG] process_row: - Has industry: {has_industry}")
    print(f"[DEBUG] process_row: - Needs custom email: {needs_custom_email}")
    print(f"[DEBUG] process_row: All custom email dependencies met? {dependencies_met}")
    
    if dependencies_met:
        print(f"[DEBUG] process_row: Row {row} needs custom email processing")
        custom_email_result = await process_custom_email(row, request, client, job_id)
        custom_email_processed = (custom_email_result.get("status", "").lower() == "success" or "Successfully" in custom_email_result.get("message", ""))
        row_log["processed_columns"]["custom_email"] = custom_email_processed
        print(f"[DEBUG] process_row: Custom email processed successfully? {custom_email_processed}")
    else:
        print(f"[DEBUG] process_row: Row {row} already has custom email or missing prerequisites")
    
    print(f"[DEBUG] process_row: Completed row {row}")

def needs_processing(target_col: str, source_col: str, row: int, column_status: Dict) -> bool:
    """Check if a column needs processing based on dependencies"""
    # First convert our internal column names to the API response column names
    api_target_col = next((k for k, v in COLUMN_NAME_MAPPING.items() if v == target_col), target_col)
    api_source_col = next((k for k, v in COLUMN_NAME_MAPPING.items() if v == source_col), source_col)
    
    # Check if source data exists but target doesn't
    source_last_row = column_status.get(api_source_col, {}).get("last_row", 0)
    target_last_row = column_status.get(api_target_col, {}).get("last_row", 0)
    
    return source_last_row >= row and target_last_row < row

def check_dependencies(target_col: str, row: int, column_status: Dict) -> bool:
    """Check if all dependencies for a target column are satisfied"""
    if target_col not in DEPENDENCIES:
        return True
    
    for dep in DEPENDENCIES[target_col]:
        # Convert internal column name to API response column name
        api_dep_col = next((k for k, v in COLUMN_NAME_MAPPING.items() if v == dep), dep)
        dep_last_row = column_status.get(api_dep_col, {}).get("last_row", 0)
        if dep_last_row < row:
            return False
    
    return True

async def process_podcast_transcript(row: int, request: OrchestratorRequest, client: httpx.AsyncClient, job_id: str):
    """Process podcast transcript for a row"""
    step_log = {"step": "podcast_transcript", "status": "starting"}
    active_jobs[job_id]["progress"][row]["steps"].append(step_log)
    
    try:
        # TODO: Get the podcast link from the spreadsheet first
        # This is a simplified example assuming YouTube links
        
        # For actual implementation, you'd need to:
        # 1. Read the podcast link from the row
        # 2. Determine if it's YouTube or another platform
        # 3. Call the appropriate API
        
        # Placeholder for YouTube transcript processing
        transcript_result = await process_api_request(
            API_ENDPOINTS["youtube_transcript"],
            {"youtube_url": "https://www.youtube.com/watch?v=EXAMPLE"},  # This would come from the sheet
            client,
            job_id
        )
        
        if transcript_result.get("status") == "success":
            # Now update the sheet with the transcript
            # This is where you'd call your update cell API
            step_log["status"] = "success"
            return {"status": "success"}
        else:
            step_log["status"] = "error"
            step_log["error"] = transcript_result.get("error", "Unknown error")
            return {"status": "error", "error": transcript_result.get("error", "Unknown error")}
    
    except Exception as e:
        step_log["status"] = "error"
        step_log["error"] = str(e)
        logger.error(f"Error processing podcast transcript for row {row}: {str(e)}")
        return {"status": "error", "error": str(e)}

async def process_website_content(row: int, request: OrchestratorRequest, client: httpx.AsyncClient, job_id: str):
    """Process website content for a row"""
    step_log = {"step": "website_content", "status": "starting"}
    active_jobs[job_id]["progress"][row]["steps"].append(step_log)
    
    try:
        # Call the website content processing API
        website_result = await process_api_request(
            API_ENDPOINTS["process_website_content"],
            {
                "spreadsheet_id": extract_spreadsheet_id(request.spreadsheet_url),
                "sheet_name": request.sheet_name,
                "url_column_index": COLUMN_MAPPING["website"],
                "content_column_index": COLUMN_MAPPING["website_content"],
                "start_row": row,
                "limit": 1  # Process just this row
            },
            client,
            job_id
        )
        
        if website_result.get("status") in ["SUCCESS", "PARTIAL"]:
            step_log["status"] = "success"
            return {"status": "success"}
        else:
            step_log["status"] = "error"
            step_log["error"] = website_result.get("message", "Unknown error")
            return {"status": "error", "error": website_result.get("message", "Unknown error")}
    
    except Exception as e:
        step_log["status"] = "error"
        step_log["error"] = str(e)
        logger.error(f"Error processing website content for row {row}: {str(e)}")
        return {"status": "error", "error": str(e)}

async def process_industry(row: int, request: OrchestratorRequest, client: httpx.AsyncClient, job_id: str):
    """Process industry segmentation for a row"""
    step_log = {"step": "industry", "status": "starting"}
    active_jobs[job_id]["progress"][row]["steps"].append(step_log)
    
    try:
        # Call the ICP segmentation API
        industry_result = await process_api_request(
            API_ENDPOINTS["process_industry"],
            {
                "spreadsheet_id": extract_spreadsheet_id(request.spreadsheet_url),
                "sheet_name": request.sheet_name,
                "start_row": row,
                "end_row": row,
                "batch_size": 1  # Process just this row
            },
            client,
            job_id
        )
        
        if industry_result.get("status") in ["SUCCESS", "PARTIAL"]:
            step_log["status"] = "success"
            return {"status": "success"}
        else:
            step_log["status"] = "error"
            step_log["error"] = industry_result.get("message", "Unknown error")
            return {"status": "error", "error": industry_result.get("message", "Unknown error")}
    
    except Exception as e:
        step_log["status"] = "error"
        step_log["error"] = str(e)
        logger.error(f"Error processing industry for row {row}: {str(e)}")
        return {"status": "error", "error": str(e)}

async def process_custom_email(row: int, request: OrchestratorRequest, client: httpx.AsyncClient, job_id: str):
    """Process custom email for a row"""
    step_log = {"step": "custom_email", "status": "starting"}
    active_jobs[job_id]["progress"][row]["steps"].append(step_log)
    
    try:
        # Call the outreach email API
        email_result = await process_api_request(
            API_ENDPOINTS["process_custom_email"],
            {
                "spreadsheet_id": extract_spreadsheet_id(request.spreadsheet_url),
                "sheet_name": request.sheet_name,
                "start_row": row,
                "end_row": row,
                "batch_size": 1 
            },
            client,
            job_id
        )
        
        # Log the full response for debugging
        print(f"[DEBUG] Custom email API response: {email_result}")
        
        # Check for success based on the API response structure
        success = False
        if isinstance(email_result, dict):
            if email_result.get("status") in ["SUCCESS", "PARTIAL"]:
                # Check if the current row is in successful_rows
                if row in email_result.get("successful_rows", []):
                    success = True
        
        if success:
            step_log["status"] = "success"
            row_log = active_jobs[job_id]["progress"][row]
            row_log["processed_columns"] = row_log.get("processed_columns", {})
            row_log["processed_columns"]["custom_email"] = True
            print(f"[DEBUG] process_row: Custom email processed successfully")
            return {"status": "success"}
        else:
            step_log["status"] = "error"
            error_message = "Unknown error"
            if isinstance(email_result, dict):
                if row in email_result.get("failed_rows", {}):
                    error_message = email_result["failed_rows"][row]
                elif "message" in email_result:
                    error_message = email_result["message"]
            
            step_log["error"] = error_message
            print(f"[DEBUG] process_row: Custom email processing failed: {error_message}")
            return {"status": "error", "error": error_message}
    
    except Exception as e:
        step_log["status"] = "error"
        step_log["error"] = str(e)
        logger.error(f"Error processing custom email for row {row}: {str(e)}")
        print(f"[DEBUG] process_row: Custom email processing exception: {str(e)}")
        return {"status": "error", "error": str(e)}

def extract_spreadsheet_id(spreadsheet_url: str) -> str:
    """Extract spreadsheet ID from Google Sheets URL"""
    import re
    
    # Handle standard Google Sheets URL
    pattern = r"/d/([a-zA-Z0-9-_]+)"
    match = re.search(pattern, spreadsheet_url)
    if match:
        return match.group(1)
    
    # Handle Google Drive 'open?id=' format
    pattern = r"id=([a-zA-Z0-9-_]+)"
    match = re.search(pattern, spreadsheet_url)
    if match:
        return match.group(1)
    
    # If it's already just the ID (no URL)
    if re.match(r"^[a-zA-Z0-9-_]+$", spreadsheet_url):
        return spreadsheet_url
    
    raise ValueError("Invalid Google Sheets URL. Unable to extract spreadsheet ID.")

@router.post("/start", response_model=OrchestratorResponse)
async def start_orchestration(request: OrchestratorRequest, background_tasks: BackgroundTasks):
    """
    Start the workflow orchestration process
    
    This endpoint coordinates the entire workflow across all APIs.
    It processes rows based on their current state and dependencies.
    """
    try:
        # Generate a unique job ID
        import uuid
        job_id = str(uuid.uuid4())
        
        # Start the background task
        background_tasks.add_task(orchestrate_workflow, request, job_id)
        
        return OrchestratorResponse(
            status="started",
            message="Workflow orchestration started",
            job_id=job_id
        )
        
    except Exception as e:
        logger.error(f"Error starting orchestration: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to start orchestration: {str(e)}")

@router.get("/status/{job_id}")
async def get_job_status(job_id: str):
    """
    Get the status of a running job
    """
    if job_id not in active_jobs:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    
    # Include additional debugging information in the response
    job_info = active_jobs[job_id].copy()
    
    # Add more detailed error information if available
    if job_info.get("status") == "error" and "progress" in job_info:
        error_details = []
        for row_id, row_data in job_info["progress"].items():
            if "steps" in row_data:
                for step in row_data["steps"]:
                    if step.get("status") == "error":
                        error_details.append({
                            "row": row_id,
                            "step": step.get("step"),
                            "error": step.get("error")
                        })
        
        job_info["error_details"] = error_details
    
    return job_info

@router.get("/jobs")
async def list_jobs():
    """
    List all jobs and their statuses
    """
    return {
        "total_jobs": len(active_jobs),
        "jobs": {
            job_id: {
                "status": job["status"],
                "start_time": job["start_time"],
                "end_time": job.get("end_time", "running"),
                "spreadsheet_url": job["spreadsheet_url"]
            } for job_id, job in active_jobs.items()
        }
    }