import os
from openai import OpenAI


os.environ["OPENAI_API_KEY"] = ""
client = OpenAI()

# client.batches.cancel("batch_69429f8fbef881909fcdd471d1e78fbf")

def check_status(batch_id):
    """Check batch status"""
    
    batch = client.batches.retrieve(batch_id)
    
    print(f"Status: {batch.status}")
    print(f"Completed: {batch.request_counts.completed}/{batch.request_counts.total}")
    
    return batch

if __name__ == "__main__":
    check_status("batch_69429f8fbef881909fcdd471d1e78fbf")