# Lead Enricher AI Tool BE

This project extracts data from organization websites and generates personalized cold emails based on the content. The input URLs are provided in a Google Sheet, and the script scrapes relevant information (e.g., "About Us" sections) to create structured data for generating emails.

## Features
- **Google Sheets Integration**: Reads input URLs directly from a Google Sheet.
- **Web Scraping**: Scrapes "About Us" sections or homepage content if the section isn't directly available.
- **Data Storage**: Organizes extracted data in the same Google Sheet in a column for further processing.
- **Extensible Design**: Modular structure for easy enhancements.

## Prerequisites

1. **Python**: Version 3.8 or later.
2. **Google Cloud Project**:
  - Enable the **Google Sheets API** and **Google Drive API**.
  - Set up a **Service Account** and download the JSON key file.

## Installation

1. Clone the repository:
  ```bash
  git clone https://github.com/yourusername/url-to-llm.git
  cd url-to-llm
  ```

2. Create a Python virtual environment:
  ```bash
  python -m venv .env
  source .env/bin/activate 
  ```

3. Install dependencies:
  ```bash
  pip install -r requirements.txt
  ```

4. Set up your `data/` directory:
  - Ensure you have an input Google Sheet with URLs (in column `C`) shared with your Service Account.
  - Create `data/` folder:
    ```bash
    mkdir data
    ```

## Configuration

1. **Google Sheets Setup**:
  - Add your **spreadsheet ID** and the range containing the URLs in `main.py`:
    ```python
    spreadsheet_id = "your-spreadsheet-id"
    range_name = "Sheet1!C:C"
    ```
  - Ensure the Google Sheet is shared with your Service Account email.

2. **Service Account Key**:
  - Place the downloaded `JSON` key file in the project root.
  - Update the path in the script:
    ```python
    credentials_file = "path/to/your-service-account-key.json"
    ```

## Usage

Run the script:
```bash
python main.py
```

Output:
- The extracted data will be saved in `data/output_emails.csv`.

## Troubleshooting

1. **Google Sheets API Errors**:
  - Ensure the spreadsheet ID and range name are correct.
  - Check that the Google Sheet is shared with the Service Account.

2. **KeyError: 'url'**:
  - Verify the column name in your Google Sheet matches the expected name (`url` or adjust as necessary).

3. **Scraping Errors**:
  - Check for rate-limiting by the target websites.
  - Use a tool like Playwright if the website relies heavily on JavaScript.

## Next Steps

- Integrate with an email generation system.
- Add support for scraping JavaScript-heavy websites using Playwright.

## License

This project is licensed under the [MIT License](LICENSE).
