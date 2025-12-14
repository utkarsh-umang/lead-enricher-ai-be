import csv
import json

BASE_PROMPT = """
Objective: Generate initial cold emails openings for outreach, following the specific template provided below. Only modify the sections within square brackets for personalisation; all other content should remain fixed.
 
Instructions:
  - Personalization Fields:
    - Replace [FIRST NAME] with the name of the person given in the prompt.
    - Replace [PERSONALISATION] with a short, specific comment as per the instruction given in the square bracket of [PERSONALISATION - instruction here].
    - The short specific comment as mentioned above should provide some sort of insight and it should go along and tie in to the next line in the email template so that the overall email can make sense. 
    - While personalizing: Write the personalization in 3rd Grade level. The sentence should not be too long and complex. Use shorter sentences and simpler words.
  - Fixed Content:
    - Do not change any other text in the template. All non-bracketed content should remain exactly as written, preserving the wording, tone, and format. Be very very strict on this, I don't want anything else apart from the bracketed  content to change. 
  - Tone and Language:
    - Keep the tone friendly and professional.
  - Don't send anything else except for the Email opening in the output
  - Judge if the given data point is useful for the same, if not send "NONSENSICAL DATA POINT" in the output – VERY VERY IMPORTANT

Here's the template I'm using:

Saw you are helping [their ICP, be very specific with it based on the data points] with [very specific problem they're helping their ICP with], {{First Name}} 


[Compliment the Insight on how we think it's helping their ICP overcome that problem. Share what's the end benefits on how it's helping their ICP.]

===================

Examples based on this Template:

EXAMPLE - 1 : 

Saw you are helping companies with unconscious bias training, Marguerite.

I think it's great how you help people see their own biases. That makes workshops better for everyone

EXAMPLE - 2 :

Saw you are helping organizations improve their processes and build high-performing teams, Kevin.

I think it's wonderful how you help teams work together better and reach their goals. That is super important! 

EXAMPLE - 3 :

Saw you are helping communities in Uganda with access to healthcare, education, justice, and environmental sustainability, Steven.

I think it's wonderful how you empower children and transform lives. That is super important! 

===================

•⁠  ⁠Do the personalization using the pool of knowledge from the data points I'm giving you
•⁠  ⁠Looking at the data pool you'd be able to tell what's the profile of the prospect we're trying to reach out to and what kind of customers do they serve and what pain points do our prospects help their customers overcome.

•⁠  ⁠An Example of an Email that is strictly following the rules:

"Saw you are helping marketers adapt to the changes in digital privacy and data collection, Rydal.

It's cool that you are helping them get ready for the cookieless future. That is super important!"

I really like the fact that the above email is sticking to the template and using the personalization on the first line alone as mentioned in the instructions.
"""

def collect_all_usable_datapoints(row, column_indices):

    datapoints = {}
    
    for category, col_index in column_indices.items():
        # Skip non-datapoint columns like name and company
        if category in ["First Name", "Last Name"]:
            continue
            
        if col_index < len(row):
            content = str(row[col_index]).strip()
            
            # Check if content is usable (not empty, not "no content", etc.)
            if (content and
                content.lower() != "no content" and 
                content.lower() != "no meaningful content" and
                content.lower() != "nan" and
                content.strip() != ""):
                datapoints[category] = content
    
    return datapoints

def csv_to_batch_jsonl(file_path, output_path, model="gpt-4o-mini", max_tokens=500,temperature=0.7):

    with open(file_path, 'r', encoding='utf-8') as file:
        csv_reader = csv.reader(file)
        
        headers = next(csv_reader)
        
        column_indices = {}

        for i, header in enumerate(headers):
            column_indices[header] = i
        
        batch_requests = []
        
        for row_num, row in enumerate(csv_reader, start=1):
            
            # Extract first name and company name with safe indexing
            first_name = column_indices["First Name"]
            company_name = column_indices["Company Name for Emails"]
            
                
            first_name = row[first_name].strip() 
            company_name = row[company_name].strip() 
            
            
            datapoints = collect_all_usable_datapoints(row, column_indices)
            
            
            # Prepare datapoints text for the prompt
            datapoints_text = ""
            for category, content in datapoints.items():
                datapoints_text += f"{category}: {content}\n"
            
            prompt = f"""
            {BASE_PROMPT}

            Person's first name: {first_name}
            Company name: {company_name}

            Available datapoints to personalize with:
            {datapoints_text}

            Generate a personalized email using ALL the datapoints provided.
            """
            
            batch_request = {
                "custom_id": f"req{row_num}",
                "method": "POST",
                "url": "/v1/chat/completions",
                "body": {
                    "model": "gpt-4o-mini",
                    "messages": [
                        {"role": "user", "content": prompt}
                    ],
                    "max_tokens": 500,
                    "temperature": 0.7
                }
            }
            
            batch_requests.append(batch_request)
                

        with open(output_path, 'w', encoding='utf-8') as jsonl_file:
            for request in batch_requests:
                jsonl_file.write(json.dumps(request) + '\n')

        return len(batch_requests)

# Example usage:
if __name__ == "__main__":
    csv_to_batch_jsonl(
        file_path="No Customisation __ Set 3 - Sheet1.csv",
        output_path="batch_requests.jsonl"
    )
