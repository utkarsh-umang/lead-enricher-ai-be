# Google Sheets Constants
CREDENTIALS_FILE = "/data/url-to-email-445616-cebe4868914f.json"
DEFAULT_SHEET_NAME = "Sheet1"

# Sheet Column Indices (0-based)
COLUMN_NAME = 0
COLUMN_LAST_NAME = 1
COLUMN_WEBSITE_LINK = 2
COLUMN_LINKEDIN = 3
COLUMN_AVATAR_DEETS = 4
COLUMN_RECENT_LINKEDIN_POST = 5
COLUMN_COPY_LINKEDIN_POST = 6
COLUMN_ABOUTUS_PAGE = 7
COLUMN_COPY_ABOUTUS = 8
COLUMN_EBOOK_LINK = 9
COLUMN_COPY_EBOOK = 10
COLUMN_RECENT_BLOG = 11
COLUMN_COPY_RECENT_BLOG = 12
COLUMN_TESTIMONIALS_LINK = 13
COLUMN_COPY_TESTIMONIALS = 14
COLUMN_WEBINAR_LINK = 15
COLUMN_COPY_WEBINAR = 16
COLUMN_RECENT_NEWS = 17
COLUMN_PODCAST_TRANSCRIPT = 18  # Column S

# Column Letters (for Google Sheets API)
COLUMN_LETTERS = {
    COLUMN_NAME: "A",
    COLUMN_LAST_NAME: "B",
    COLUMN_WEBSITE_LINK: "C",
    COLUMN_LINKEDIN: "D",
    COLUMN_AVATAR_DEETS: "E",
    COLUMN_RECENT_LINKEDIN_POST: "F", 
    COLUMN_COPY_LINKEDIN_POST: "G",
    COLUMN_ABOUTUS_PAGE: "H",
    COLUMN_COPY_ABOUTUS: "I",
    COLUMN_EBOOK_LINK: "J",
    COLUMN_COPY_EBOOK: "K",
    COLUMN_RECENT_BLOG: "L",
    COLUMN_COPY_RECENT_BLOG: "M",
    COLUMN_TESTIMONIALS_LINK: "N",
    COLUMN_COPY_TESTIMONIALS: "O",
    COLUMN_WEBINAR_LINK: "P",
    COLUMN_COPY_WEBINAR: "Q",
    COLUMN_RECENT_NEWS: "R",
    COLUMN_PODCAST_TRANSCRIPT: "S"
}

# GPT Prompts
AVATAR_DEETS_PROMPT = """
Task: Fill the given keys of the form using an episode transcript, if no information is available or cannot be deduced from the transcript, just pass NA 
1. Sub-Industries (examples - Commercial Real Estate, Property Management Companies, Residential Real Estate Agents, Real Estate Developers, Etc) 
2. Company Size 
3. Location 
4. Revenue

Topic: ICP classification for Real Estate Industry
Style: Business
Tone: Confident
Audience: Business audience
Format: 
1. Sub-Industries - 
2. Company Size - 
3. Location - 
4. Revenue - 
"""

# API Status Codes
STATUS_SUCCESS = "success"
STATUS_ERROR = "error"
STATUS_PARTIAL = "partial_success"

# Processing batch sizes
DEFAULT_BATCH_SIZE = 10