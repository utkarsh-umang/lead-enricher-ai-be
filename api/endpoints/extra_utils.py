async def _process_avatar_deets_background(
    sheet_service: GoogleSheetService,
    gpt_service: GPTService,
    spreadsheet_id: str,
    sheet_name: str,
    start_row: int,
    end_row: Optional[int],
    batch_size: int
):
    """
    Background task for processing podcast transcripts to Avatar Deets
    """
    logger.info(f"Starting background processing for Avatar Deets in {spreadsheet_id}")
    
    successful_rows = []
    failed_rows = {}
    
    try:
        # Get podcast transcript data
        success, transcript_data = sheet_service.get_column_data(
            spreadsheet_id, 
            sheet_name, 
            COLUMN_PODCAST_TRANSCRIPT
        )
        
        if not success:
            logger.error(f"Failed to get podcast transcript data: {transcript_data}")
            return
        
        # Determine range to process
        total_rows = len(transcript_data)
        end_row = min(end_row or (start_row + total_rows - 1), start_row + total_rows - 1)
        
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
                    spreadsheet_id,
                    sheet_name,
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
            
            # Log progress every batch_size rows
            if len(successful_rows) % batch_size == 0:
                logger.info(f"Progress: Processed {len(successful_rows) + len(failed_rows)} rows, "
                          f"Success: {len(successful_rows)}, Failed: {len(failed_rows)}")
        
        # Log final summary
        logger.info(f"Processing completed. Total processed: {len(successful_rows) + len(failed_rows)}, "
                  f"Success: {len(successful_rows)}, Failed: {len(failed_rows)}")
                  
    except Exception as e:
        logger.error(f"Background processing error: {str(e)}")