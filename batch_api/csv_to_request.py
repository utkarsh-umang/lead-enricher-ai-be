import csv
import json
from textwrap import dedent
import re

BASE_PROMPT = """

I am writing cold email openings and I have multiple columns for which I need to figure out which one of them makes the most sense to use in the salutation with Hey {variable}. 

For example if this was the data 

ownerFullName - NA
fullName - Nick Papadopoulos
username - coachnicknyc
email - marmaladeskies.store@gmail.com
description- Marketplace At The Forge 49 Randolph Road Space M-2 Middletown, CT 06457 marmaladeskies.store@gmail.com marmalade-skies.com ... New York. You can still …
title - Nick Papadopoulos (@coachnicknyc)

Then for the email I would use Hey Nick, 

Important - I want to address the person behind the email, not their business entity. 
I want you to decide out of these 5 data points which one makes the most sense for me to use as an opening, if nothing makes sense, just return “Hello” as the salutation. 

Instructions: Don't send anything else except for the Email opening in the output

Now return the salutation for this case 

"""

def collect_all_usable_datapoints(row, column_indices):

    datapoints = {}
    
    for category, col_index in column_indices.items():
        # Skip non-datapoint columns like name and company
        if category not in ["ownerFullName", "fullName", "username", "email", "description", "title"]:
            continue
            
        if col_index < len(row):
            content = str(row[col_index]).strip()
            
            # Check if content is usable (not empty, not "no content", etc.)
            if (content and
                # content.lower() != "no content" and 
                # content.lower() != "no meaningful content" and
                # content.lower() != "nan" and
                content.strip() != ""):
                datapoints[category] = content
    
    return datapoints

def csv_to_batch_jsonl(file_path, output_path, model="gpt-4o-mini", max_tokens=150,temperature=0.2):

    with open(file_path, 'r', encoding='utf-8') as file:
        csv_reader = csv.reader(file)
        
        headers = next(csv_reader)
        
        column_indices = {}

        for i, header in enumerate(headers):
            column_indices[header] = i
        
        batch_requests = []
        
        for row_num, row in enumerate(csv_reader, start=1):
            
            # Extract first name and company name with safe indexing
            ownerFullName_idx = column_indices["ownerFullName"] 
            fullName_idx = column_indices["fullName"]
            username_idx = column_indices["username"]
            email_idx = column_indices["email"]
            description_idx = column_indices["description"]
            title_idx = column_indices["title"]
            
            def empty_check(row,idx):
                if idx < len(row):
                    value = row[idx].strip()
                    return value if value else "NA"
                return "NA"
            


            ownerFullName = empty_check(row, ownerFullName_idx)
            fullName = empty_check(row, fullName_idx)
            username = empty_check(row, username_idx)
            email = empty_check(row, email_idx)
            description = empty_check(row, description_idx)
            title = empty_check(row, title_idx)
            
             
            
            
            datapoints = collect_all_usable_datapoints(row, column_indices)
            
            
            # Prepare datapoints text for the prompt
            datapoints_text = ""
            for category, content in datapoints.items():
                datapoints_text += f"{category}: {content}\n"
            
            prompt = dedent(f"""
            {BASE_PROMPT}

            ownerFullName - {ownerFullName} 
            fullName - {fullName}
            username - {username} 
            email - {email}
            description- {description} 
            title - {title} 
            """).strip()


            prompt = re.sub(r"\s+", " ", prompt).strip()

            
            batch_request = {
                "custom_id": f"req{row_num}",
                "method": "POST",
                "url": "/v1/chat/completions",
                "body": {
                    "model": "gpt-4o-mini",
                    "messages": [
                        {"role": "user", "content": prompt}
                    ],
                    "max_tokens": 150,
                    "temperature": 0.2
                }
            }
            
            batch_requests.append(batch_request)
                

        with open(output_path, 'w', encoding='utf-8') as jsonl_file:
            for request in batch_requests:
                jsonl_file.write(json.dumps(request, ensure_ascii=False) + '\n')

        return len(batch_requests)

# Example usage:
if __name__ == "__main__":
    csv_to_batch_jsonl(
        file_path="merged_apify_leads - apify_list_with_full_data.csv",
        output_path="full_data_batch_requests.jsonl"
    )
