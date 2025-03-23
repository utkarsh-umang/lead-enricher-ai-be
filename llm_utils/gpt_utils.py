import logging
from openai import OpenAI
from time import sleep
import os
from typing import Optional, Dict, Any
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

logger = logging.getLogger(__name__)

class GPTService:
    """Service for interacting with OpenAI GPT models"""
    
    def __init__(self, api_key: Optional[str] = None):
        """Initialize the GPT service with API key"""
        self.api_key = api_key or os.getenv('OPENAI_API_KEY')
        if not self.api_key:
            logger.warning("No OpenAI API key provided. Set OPENAI_API_KEY environment variable.")
        self.client = OpenAI(api_key=self.api_key) if self.api_key else None
        
    def process_content(self, 
                       content: str, 
                       prompt: str, 
                       model: str = "gpt-4o-mini",
                       max_retries: int = 3, 
                       delay: int = 1,
                       temperature: float = 0.7,
                       max_tokens: int = 500) -> Dict[str, Any]:
        """
        Process content with GPT API with retry logic
        
        Args:
            content: The content to process
            prompt: The prompt to use for processing
            model: The GPT model to use
            max_retries: Maximum number of retry attempts
            delay: Base delay between retries (will be multiplied by attempt number)
            temperature: Controls randomness (0-1)
            max_tokens: Maximum tokens in the response
            
        Returns:
            Dictionary with success status and result/error
        """
        if not self.client:
            return {
                "success": False,
                "error": "OpenAI API key not configured"
            }
            
        try:
            full_prompt = f"{prompt.strip()}\n\nContent to analyze:\n{content}"
            
            for attempt in range(max_retries):
                try:
                    response = self.client.chat.completions.create(
                        model=model,
                        messages=[
                            {"role": "system", "content": "You are a helpful assistant that analyzes content and extracts specific information."},
                            {"role": "user", "content": full_prompt}
                        ],
                        temperature=temperature,
                        max_tokens=max_tokens
                    )
                    
                    return {
                        "success": True,
                        "result": response.choices[0].message.content.strip()
                    }
                    
                except Exception as e:
                    if "rate_limit" in str(e).lower() and attempt < max_retries - 1:
                        sleep_time = delay * (attempt + 1)
                        logger.warning(f"Rate limit reached. Retrying in {sleep_time} seconds...")
                        sleep(sleep_time)
                    else:
                        raise
                        
        except Exception as e:
            logger.error(f"Failed to process content with GPT: {str(e)}")
            return {
                "success": False,
                "error": f"GPT processing error: {str(e)}"
            }