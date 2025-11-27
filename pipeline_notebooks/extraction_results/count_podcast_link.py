import json
from pathlib import Path

directory = "."  # Change this to your target directory

has_podcast = 0
total = 0

for file_path in Path(directory).glob("*.json"):
    try:
        with open(file_path, 'r') as f:
            data = json.load(f)
        
        # Check if sub_urls exists and is a list
        if 'sub_urls' in data and isinstance(data['sub_urls'], list):
            found_podcast = False
            
            # Check each URL in sub_urls for the word "podcast"
            for url in data['sub_urls']:
                if isinstance(url, str) and 'podcast' in url.lower():
                    found_podcast = True
                    break
            
            if found_podcast:
                has_podcast += 1
            
            total += 1
            
    except (json.JSONDecodeError, Exception) as e:
        print(f"Error processing {file_path}: {e}")

print(f"\nResults:")
print(f"Files with podcast links: {has_podcast}")
print(f"Total files processed: {total}")
print(f"Percentage: {(has_podcast/total*100):.2f}%" if total > 0 else "Percentage: N/A")