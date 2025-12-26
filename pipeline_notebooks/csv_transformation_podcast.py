import pandas as pd
from collections import defaultdict

MAX_PODCASTS = 10
CHUNK_SIZE = 200_000

data = defaultdict(list)

for chunk in pd.read_csv("/Users/utkarshumang/my_projects/lead-enricher-ai-be/pipeline_notebooks/podcast_scrape_results.csv", chunksize=CHUNK_SIZE):
    for _, row in chunk.iterrows():
        root = row["root_url"]
        if len(data[root]) < MAX_PODCASTS:
            data[root].append((
                row["podcast_url"],
                row["scraped_information"]
            ))

# Build rows
rows = []
for root, pairs in data.items():
    row = {"root_url": root}
    for i in range(MAX_PODCASTS):
        if i < len(pairs):
            row[f"podcast_{i+1}"] = pairs[i][0]
            row[f"info_{i+1}"] = pairs[i][1]
        else:
            row[f"podcast_{i+1}"] = ""
            row[f"info_{i+1}"] = ""
    rows.append(row)

final_df = pd.DataFrame(rows)

final_df.to_csv("/Users/utkarshumang/my_projects/lead-enricher-ai-be/pipeline_notebooks/compressed.csv", index=False)
