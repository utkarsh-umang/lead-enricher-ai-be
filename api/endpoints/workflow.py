from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, HttpUrl
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
from youtube_transcript_api import YouTubeTranscriptApi, NoTranscriptFound, TranscriptsDisabled, VideoUnavailable

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

class YoutubeTranscriptRequest(BaseModel):
    youtube_url: HttpUrl

class YoutubeTranscriptResponse(BaseModel):
    video_id: str
    transcript: str
    status: str

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
    

@router.post("/process-icp-segmentation", response_model=ProcessResponse)
async def process_icp_segmentation(request: ProcessAvatarDeetsRequest):
    """
    Process customer data to perform ICP segmentation using LLM

    This endpoint combines data from multiple columns (name, podcast name, 
    transcript, website content, and industry) and uses GPT to generate
    ICP segmentation results.
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
        
        # Get all required column data
        columns_to_fetch = {
            'transcript': 7,     # Episode transcript - Column H
            'website': 8        # Website content - Column I
        }
        
        column_data = {}
        for key, column in columns_to_fetch.items():
            success, data = sheet_service.get_column_data(
                request.spreadsheet_id,
                request.sheet_name,
                column,
                start_row=request.start_row
            )
            if not success:
                logger.error(f"Failed to get {key} data: {data}")
                raise HTTPException(status_code=400, detail=f"Failed to get {key} data: {data}")
            column_data[key] = data
        
        # Track results
        successful_rows = []
        failed_rows = {}
        
        # Determine range to process
        total_rows = min([len(data) for data in column_data.values()])
        start_row = request.start_row
        end_row = min(request.end_row or (start_row + total_rows - 1), start_row + total_rows - 1)
        
        # Apply batch processing if specified
        current_batch = 0
        max_batch_rows = request.batch_size
        
        logger.info(f"Processing rows {start_row} to {end_row} (total: {end_row - start_row + 1})")
        
        # Process each row
        for sheet_row in range(start_row, end_row + 1):
            # Check if we've reached the batch limit
            if max_batch_rows and current_batch >= max_batch_rows:
                logger.info(f"Reached batch limit of {max_batch_rows} rows")
                break
                
            # Calculate the corresponding index in data arrays (0-based)
            data_index = sheet_row - start_row
            
            try:
                # Skip if index is out of bounds for any data column
                if data_index >= total_rows:
                    logger.warning(f"Row {sheet_row} exceeds available data (index {data_index})")
                    failed_rows[sheet_row] = "Data index out of bounds"
                    continue
                
                # Get data from each column for this row
                transcript = column_data['transcript'][data_index] if data_index < len(column_data['transcript']) else "No content"
                website = column_data['website'][data_index] if data_index < len(column_data['website']) else "No content"
                
                # Skip processing if there's no valid content
                if not website or website.startswith("Error") or "No Content found" in website:
                    website_content = "No website content"
                else:
                    website_content = website
                
                # Combine all data
                combined_content = f"Podcast Transcript: {transcript}\n\nWebsite Content: {website_content}"
                
                # Process with GPT using the ICP segmentation prompt
                logger.info(f"Processing ICP segmentation for row {sheet_row}")
                
                # Get the ICP segmentation prompt
                icp_prompt = """
                Task: Fill the given keys of the form using an episode transcript and website content if any, if no information is available or cannot be deduced from the transcript, just pass NA
                1. Sub-Industries (examples - Commercial Real Estate, Property Management Companies, Residential Real Estate Agents, Real Estate Developers, Etc)
                2. Company Size
                3. Location
                4. Revenue
                5. ICP Type options - ["NA", "Syndication", "REIT", "Multifamily"]
                
                Topic: ICP classification for Real Estate Industry
                Style: Business
                Tone: Confident
                Audience: Business audience
                Output Format:
                1. Sub-Industries -
                2. Company Size - 
                3. Location - 
                4. Revenue - 
                5. ICP Type - 
                """
                
                gpt_result = gpt_service.process_content(combined_content, icp_prompt)
                
                if not gpt_result["success"]:
                    logger.error(f"GPT processing failed for row {sheet_row}: {gpt_result.get('error')}")
                    failed_rows[sheet_row] = gpt_result.get('error', 'Unknown GPT error')
                    continue
                
                # Update the ICP segmentation results column (Column K)
                update_success, update_message = sheet_service.update_cell(
                    request.spreadsheet_id,
                    request.sheet_name,
                    sheet_row,
                    9,
                    gpt_result["result"]
                )
                
                if update_success:
                    logger.info(f"Successfully updated ICP segmentation for row {sheet_row}")
                    successful_rows.append(sheet_row)
                    current_batch += 1
                else:
                    logger.error(f"Failed to update ICP segmentation for row {sheet_row}: {update_message}")
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
        logger.error(f"Error processing ICP segmentation: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to process: {str(e)}")
    

@router.post("/process-outreach", response_model=ProcessResponse)
async def process_outreach(request: ProcessAvatarDeetsRequest):
    """
    Process prospect data to create a Cold Outreach using LLM
    
    This endpoint combines data from multiple columns (name, podcast name, 
    transcript, website content, and industry) and uses GPT to generate
    Cold Outreach Email.
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
        
        # Get all required column data
        columns_to_fetch = {
            'name': 0,           # Person name - Column A (0-based index)
            'podcast_name': 5,   # Podcast name - Column F (0-based index)
            'transcript': 7,     # Episode transcript - Column H (0-based index)
            'website': 8,        # Website content - Column I (0-based index)
            'industry': 9        # Industry - Column J (0-based index)
        }
        
        column_data = {}
        for key, column in columns_to_fetch.items():
            success, data = sheet_service.get_column_data(
                request.spreadsheet_id,
                request.sheet_name,
                column,
                start_row=request.start_row
            )
            
            if not success:
                logger.error(f"Failed to get {key} data: {data}")
                raise HTTPException(status_code=400, detail=f"Failed to get {key} data: {data}")
            
            column_data[key] = data
        
        # Track results
        successful_rows = []
        failed_rows = {}
        
        # Determine range to process
        total_rows = min([len(data) for data in column_data.values()])
        start_row = request.start_row
        end_row = min(request.end_row or (start_row + total_rows - 1), start_row + total_rows - 1)
        
        # Apply batch processing if specified
        current_batch = 0
        max_batch_rows = request.batch_size
        
        logger.info(f"Processing rows {start_row} to {end_row} (total: {end_row - start_row + 1})")
        
        # Process each row
        for sheet_row in range(start_row, end_row + 1):
            # Check if we've reached the batch limit
            if max_batch_rows and current_batch >= max_batch_rows:
                logger.info(f"Reached batch limit of {max_batch_rows} rows")
                break
                
            # Calculate the corresponding index in data arrays (0-based)
            data_index = sheet_row - start_row
            
            try:
                # Skip if index is out of bounds for any data column
                if data_index >= total_rows:
                    logger.warning(f"Row {sheet_row} exceeds available data (index {data_index})")
                    failed_rows[sheet_row] = "Data index out of bounds"
                    continue
                
                # Get data from each column for this row
                name = column_data['name'][data_index] if data_index < len(column_data['name']) else "No content"
                podcast_name = column_data['podcast_name'][data_index] if data_index < len(column_data['podcast_name']) else "No content"
                transcript = column_data['transcript'][data_index] if data_index < len(column_data['transcript']) else "No content"
                website = column_data['website'][data_index] if data_index < len(column_data['website']) else "No content"
                industry = column_data['industry'][data_index] if data_index < len(column_data['industry']) else "No content"
                
                # Skip processing if there's no valid content
                if not website or website.startswith("Error") or "No Content found" in website:
                    website_content = "No website content"
                else:
                    website_content = website
                
                # Combine all data
                combined_content = f"Person Name: {name}\n\nPodcast Name: {podcast_name}\n\nPodcast Transcript: {transcript}\n\nWebsite Content: {website_content}\n\nIndustry Details: {industry}"
                
                # Process with GPT using the ICP segmentation prompt
                logger.info(f"Processing ICP segmentation for row {sheet_row}")
                
                # Get the ICP segmentation prompt
                icp_prompt = """
                Custom GPT Bot Email Template Instructions

                Objective: Generate initial cold emails for outreach, following the specific template provided below. Only modify the sections within brackets for personalization; all other content should remain fixed.

                Email Template:

                "[Name of the Person] - watched your episode about [Personalisation] on the [Name of Pod]. Honestly so good.

                We're Scale Brands Lab—an invite-only firm that helps investor-friendly organizations gain major media exposure.

                We specialize in working with real estate firms, by getting them featured on top media outlets for massive exposure. 

                It goes from instant recognition to people flocking to your next {any-one from the following - [Syndication/REIT/Multifamily deal]}, real fast.

                Without a shadow of a doubt, we can explode your material. There's so much value there.

                Would you like to get more info?"

                Example Email:

                "Jason - watched your episode about "starting the clock" on the Real Estate Today. Honestly so good.

                We're Scale Brands Lab—an invite-only firm that helps investor-friendly organizations gain major media exposure.

                We specialize in working with real estate firms, by getting them featured on top media outlets for massive exposure. 

                It goes from instant recognition to people flocking to your next Multifamily deal, real fast.

                Without a shadow of a doubt, we can explode your material. There's so much value there.

                Would you like to get more info?"

                Instructions:

                1. Personalization Fields:
                - Replace [Name of the Person] with the name of the person given in the prompt.
                - Replace [PERSONALISATION] with a short, specific comment about a particular insight or segment of the podcast content.
                - Replace [Name of Pod] with the podcast name given in the prompt. 
                - Select any-one of the following - [Syndication/REIT/Multifamily deal] for this line, deduce it from the Industry details. If what has to be selected cannot be deduced from the ICP Type or any other information in Industry Details, then choose according to other details.
                - While personalizing: Write the personalization in 3rd Grade level. The sentence should not be too long and complex. Use shorter sentences and simpler words.
            

                2. Fixed Content:
                - Do not change any other text in the template. All non-bracketed content should remain exactly as written, preserving the wording, tone, and format. Be very very strict on this, I don't want anything else apart from the bracketed  content to change. 

                3. Tone and Language:
                - Keep the tone friendly and professional.
                - Ensure the language is simple, conversational, and concise to stay within a ~150-word limit.

                4. Dont send anything else except for the Email
                """
                
                gpt_result = gpt_service.process_content(combined_content, icp_prompt)
                
                if not gpt_result["success"]:
                    logger.error(f"GPT processing failed for row {sheet_row}: {gpt_result.get('error')}")
                    failed_rows[sheet_row] = gpt_result.get('error', 'Unknown GPT error')
                    continue
                
                # Update the ICP segmentation results column (Column K)
                update_success, update_message = sheet_service.update_cell(
                    request.spreadsheet_id,
                    request.sheet_name,
                    sheet_row,
                    10,
                    gpt_result["result"]
                )
                
                if update_success:
                    logger.info(f"Successfully created cold outreach for row {sheet_row}")
                    successful_rows.append(sheet_row)
                    current_batch += 1
                else:
                    logger.error(f"Failed to create cold outreach for row {sheet_row}: {update_message}")
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
        logger.error(f"Error processing outreach: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to process: {str(e)}")

def extract_video_id(youtube_url):
    """Extract the video ID from a YouTube URL."""
    # Handle standard YouTube URLs
    if "youtube.com/watch" in youtube_url:
        query_string = youtube_url.split("?")[1]
        params = {param.split("=")[0]: param.split("=")[1] for param in query_string.split("&")}
        if "v" in params:
            return params["v"]
    # Handle shortened youtu.be URLs
    elif "youtu.be/" in youtube_url:
        return youtube_url.split("youtu.be/")[1].split("?")[0]
    # Handle YouTube embed URLs
    elif "youtube.com/embed/" in youtube_url:
        return youtube_url.split("youtube.com/embed/")[1].split("?")[0]
    
    raise ValueError("Could not extract video ID from URL")

@router.post("/youtube-transcript", response_model=YoutubeTranscriptResponse)
async def get_youtube_transcript(request: YoutubeTranscriptRequest):
    """
    Get transcript for a YouTube video using youtube-transcript-api.
    
    This endpoint extracts the video ID from the provided YouTube URL,
    then fetches the transcript directly from YouTube.
    """
    try:
        # Extract video ID from the URL
        video_id = extract_video_id(str(request.youtube_url))
        logger.info(f"Processing transcript for YouTube video ID: {video_id}")
        
        # Fetch transcript - using get_transcript() instead of fetch()
        try:
            transcript_items = YouTubeTranscriptApi.get_transcript(video_id=video_id)
            transcript_text = " ".join([item["text"] for item in transcript_items])
            
            return YoutubeTranscriptResponse(
                video_id=video_id,
                transcript=transcript_text,
                status="success"
            )
            
        except NoTranscriptFound:
            logger.error(f"No transcript found for video ID: {video_id}")
            raise HTTPException(status_code=404, detail="No transcript found for this video")
        except TranscriptsDisabled:
            logger.error(f"Transcripts are disabled for video ID: {video_id}")
            raise HTTPException(status_code=404, detail="Transcripts are disabled for this video")
        except VideoUnavailable:
            logger.error(f"Video unavailable for ID: {video_id}")
            raise HTTPException(status_code=404, detail="The video is unavailable")
            
    except ValueError as e:
        logger.error(f"Invalid YouTube URL: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error processing transcript: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to process transcript: {str(e)}")