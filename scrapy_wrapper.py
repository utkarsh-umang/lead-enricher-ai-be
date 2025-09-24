import subprocess
import json
import os
import csv
from typing import List
import logging

class ScrapySubprocessWrapper:
    def __init__(self, spider_name: str, project_dir: str = r"C:\Users\apwbm\OneDrive\Desktop\PROJECTS\P1\LEAD ENRICHMENT\lead-enricher-ai-be\url_crawler"):
        """
        Initialize the Scrapy subprocess wrapper.
        
        Args:
            spider_name (str): Name of the Scrapy spider to run (e.g., 'site_spider').
            project_dir (str): Path to the Scrapy project directory containing scrapy.cfg.
        """
        self.spider_name = spider_name
        self.project_dir = project_dir
        self.output_file = os.path.join(self.project_dir, "urls.csv")  # Absolute path
        
        # Setup logging
        self.logger = logging.getLogger(__name__)
        if not self.logger.handlers:
            logging.basicConfig(
                level=logging.DEBUG,  # Increased to DEBUG
                format='%(asctime)s - %(levelname)s - %(message)s',
                handlers=[
                    logging.FileHandler(os.path.join(self.project_dir, 'scrapy_wrapper.log')),
                    logging.StreamHandler()
                ]
            )

        # Verify project directory
        if not os.path.exists(os.path.join(self.project_dir, 'scrapy.cfg')):
            self.logger.error(f"Invalid Scrapy project directory: {self.project_dir}. Missing scrapy.cfg")
            raise ValueError(f"Scrapy project directory {self.project_dir} does not contain scrapy.cfg")

    def process_urls_batch(self, urls: List[str]) -> List[str]:
        """
        Process a batch of URLs using the Scrapy spider in a subprocess.
        
        Args:
            urls (List[str]): List of URLs to crawl.
            
        Returns:
            List[str]: List of extracted URLs from the spider output.
        """
        if not urls:
            self.logger.warning("No URLs provided for Scrapy subprocess")
            return []

        # Use the first URL as start_url
        start_url = urls[0]
        cmd = [
            "scrapy", "crawl", self.spider_name,
            "-a", f"start_url={start_url}",
            "-o", self.output_file
        ]

        try:
            # Check if output file already exists
            if os.path.exists(self.output_file):
                self.logger.warning(f"Output file {self.output_file} already exists. Removing it.")
                os.remove(self.output_file)

            self.logger.info(f"Running Scrapy subprocess for URL: {start_url}")
            self.logger.debug(f"Executing command: {' '.join(cmd)}")
            self.logger.debug(f"Current working directory: {os.getcwd()}")
            self.logger.debug(f"Scrapy project directory: {self.project_dir}")
            self.logger.debug(f"Environment PATH: {os.environ.get('PATH')}")

            result = subprocess.run(
                cmd,
                cwd=self.project_dir,
                check=True,
                capture_output=True,
                text=True
            )
            self.logger.debug(f"Scrapy subprocess stdout: {result.stdout}")
            self.logger.debug(f"Scrapy subprocess stderr: {result.stderr}")
            self.logger.debug(f"Subprocess exit code: {result.returncode}")

            # Check for output file in project directory
            if os.path.exists(self.output_file):
                with open(self.output_file, 'r', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    extracted_urls = [row['url'] for row in reader if 'url' in row]
                self.logger.info(f"Extracted {len(extracted_urls)} URLs from {start_url}")
                os.remove(self.output_file)  # Clean up
                return extracted_urls
            else:
                # Fallback: Check notebook's working directory
                notebook_output = os.path.join(os.getcwd(), "urls.csv")
                if os.path.exists(notebook_output):
                    self.logger.warning(f"Output file found in notebook directory: {notebook_output}")
                    with open(notebook_output, 'r', encoding='utf-8') as f:
                        reader = csv.DictReader(f)
                        extracted_urls = [row['url'] for row in reader if 'url' in row]
                    os.remove(notebook_output)  # Clean up
                    self.logger.info(f"Extracted {len(extracted_urls)} URLs from {start_url} in notebook directory")
                    return extracted_urls
                else:
                    self.logger.error(f"Output file {self.output_file} not found in project or notebook directory")
                    self.logger.debug(f"Scrapy stderr: {result.stderr}")
                    return []

        except subprocess.CalledProcessError as e:
            self.logger.error(f"Scrapy subprocess failed for {start_url}: {e.stderr}")
            self.logger.debug(f"Subprocess exit code: {e.returncode}")
            return []
        except Exception as e:
            self.logger.error(f"Unexpected error in Scrapy subprocess for {start_url}: {str(e)}")
            return []