import os
from openai import OpenAI
import csv
from datetime import datetime




# Set your API key
os.environ["OPENAI_API_KEY"] = ""
client = OpenAI()


def submit_batch(jsonl_file):
    """Upload JSONL and create batch job"""
    
    # Upload file
    with open(jsonl_file, 'rb') as file:
        batch_file = client.files.create(file=file, purpose="batch")
    
    # Create batch
    batch = client.batches.create(
        input_file_id=batch_file.id,
        endpoint="/v1/chat/completions",
        completion_window="24h"
    )

    # write to batch_data
    with open("batch_data.csv", "a", newline="", encoding="utf-8") as write_file:
        writer = csv.writer(write_file)

        writer.writerow([
            jsonl_file,
            batch.id,
            batch.status,
            datetime.utcfromtimestamp(batch.created_at).isoformat()
        ])

    
    print(f"Batch ID: {batch.id}")
    print(f"Status: {batch.status}")
    return batch.id

def check_status(batch_id):
    """Check batch status"""
    
    batch = client.batches.retrieve(batch_id)
    
    print(f"Status: {batch.status}")
    print(f"Completed: {batch.request_counts.completed}/{batch.request_counts.total}")
    
    return batch

def download_results(batch_id, output_file="batch_results.jsonl"):
    """Download results when complete"""
    
    batch = client.batches.retrieve(batch_id)
    
    if batch.status != "completed":
        print(f"Batch not ready yet. Status: {batch.status}")
        return None
    
    # Download results
    result = client.files.content(batch.output_file_id)
    
    with open(output_file, 'wb') as file:
        file.write(result.content)
    
    print(f"Results saved to: {output_file}")
    return output_file

# Usage:
if __name__ == "__main__":
    # Step 1: Submit
    # batch_id = submit_batch("batch_requests.jsonl")
    
    # Step 2: Check status (run this later)
    # check_status("batch_693d74a3cd208190b6702252fad148bd")
    
    # Step 3: Download results (run when complete)
    download_results("batch_693d74a3cd208190b6702252fad148bd")