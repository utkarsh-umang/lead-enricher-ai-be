import json
import re

ALLOWED_TITLES = {"dr", "mr", "ms", "mrs", "dj"}


def should_replace_with_hello(content: str) -> bool:
    words = content.split()

    if not words or words[0].lower() != "hey":
        return False
    
    if bool(re.search(r"[^A-Za-z\s.]", content)):
        return True
    
    if len(words) < 2:
        return True
    
    if len(words) > 4:
        return True

    if len(words) in [3, 4]:
        second_word = words[1].lower().rstrip(".,!?")
        if second_word in ALLOWED_TITLES:
            return False 
        else:
            return True
    
    return False


with open(r"C:\Users\apwbm\OneDrive\Desktop\PROJECTS\P1\LEAD ENRICHMENT\lead-enricher-ai-be\batch_api\jsonl\results\batch_results_no_data.jsonl", "r", encoding="utf-8") as in_file, \
     open(r"C:\Users\apwbm\OneDrive\Desktop\PROJECTS\P1\LEAD ENRICHMENT\lead-enricher-ai-be\batch_api\jsonl\results\cleaned\no_data_results_cleaned.jsonl", "w", encoding="utf-8") as out_file:

    for line in in_file:
        obj = json.loads(line)
        choices = obj.get("response", {}).get("body", {}).get("choices", [])

        if not choices:
            out_file.write(json.dumps(obj) + "\n")
            continue

        message = choices[0].get("message", {})
        content = message.get("content", "")
        content = re.sub(",", "", content).strip()

        if should_replace_with_hello(content):
            message["content"] = "Hello"
        else:
            message["content"] = content

        out_file.write(json.dumps(obj) + "\n")
