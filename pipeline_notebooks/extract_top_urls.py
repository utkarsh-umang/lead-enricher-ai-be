#!/usr/bin/env python3
"""
Extract Top URLs Script

This script processes all JSON files in the apollo_podcast_urls folder,
extracts the first URL (0th entry) from each file's array, and saves
them to a text file with one URL per line.
"""

import json
from pathlib import Path
from typing import List


def extract_top_urls_from_directory(directory_path: str) -> List[str]:
    """
    Extract the first URL (index 0) from each JSON file in the directory.
    
    Args:
        directory_path: Path to the directory containing JSON files
        
    Returns:
        List of URLs extracted from the first entry of each JSON file
    """
    top_urls = []
    directory = Path(directory_path)
    
    if not directory.exists():
        print(f"Error: Directory {directory_path} does not exist")
        return top_urls
    
    # Get all JSON files in the directory
    json_files = list(directory.glob("*.json"))
    total_files = len(json_files)
    
    print(f"Found {total_files} JSON files to process")
    
    processed_count = 0
    skipped_count = 0
    
    for json_file in json_files:
        try:
            # Read and parse JSON file
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Check if data is a list and has at least one element
            if isinstance(data, list) and len(data) > 0:
                first_url = data[0]
                # Validate that it's a string (URL)
                if isinstance(first_url, str) and first_url.strip():
                    top_urls.append(first_url.strip())
                    processed_count += 1
                else:
                    print(f"Warning: First element in {json_file.name} is not a valid URL string")
                    skipped_count += 1
            else:
                print(f"Warning: {json_file.name} is empty or not a list")
                skipped_count += 1
                
        except json.JSONDecodeError as e:
            print(f"Error: Invalid JSON in {json_file.name}: {e}")
            skipped_count += 1
        except Exception as e:
            print(f"Error: Failed to process {json_file.name}: {e}")
            skipped_count += 1
    
    print(f"\nProcessing complete:")
    print(f"  - Successfully processed: {processed_count} files")
    print(f"  - Skipped: {skipped_count} files")
    print(f"  - Total URLs extracted: {len(top_urls)}")
    
    return top_urls


def save_urls_to_file(urls: List[str], output_file_path: str) -> None:
    """
    Save URLs to a text file, one URL per line.
    
    Args:
        urls: List of URLs to save
        output_file_path: Path to the output text file
    """
    output_path = Path(output_file_path)
    
    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            for url in urls:
                f.write(url + '\n')
        
        print(f"\nSuccessfully saved {len(urls)} URLs to {output_path}")
    except Exception as e:
        print(f"Error: Failed to write to {output_file_path}: {e}")
        raise


def main():
    """Main function to execute the script."""
    # Get the directory where this script is located
    script_dir = Path(__file__).parent
    directory_path = '/Users/utkarshumang/my_projects/lead-enricher-ai-be/pipeline_notebooks/apollo_podcast_urls'
    print(directory_path)
    
    # Output file path (same directory as script)
    output_file = script_dir / "top_urls.txt"
    
    print(f"Processing JSON files in: {directory_path}")
    print(f"Output will be saved to: {output_file}\n")
    
    # Extract top URLs from all JSON files
    top_urls = extract_top_urls_from_directory(directory_path)
    
    if top_urls:
        # Save URLs to file
        save_urls_to_file(top_urls, str(output_file))
    else:
        print("\nNo URLs were extracted. Output file not created.")


if __name__ == "__main__":
    main()

