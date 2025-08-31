# Updated settings.py - Add these settings to handle network issues better

BOT_NAME = "url_crawler"

SPIDER_MODULES = ["url_crawler.spiders"]
NEWSPIDER_MODULE = "url_crawler.spiders"

ADDONS = {}

# User agent - some sites block requests without proper user agent
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

# Obey robots.txt rules - you might want to disable this temporarily for testing
ROBOTSTXT_OBEY = False  # Changed to False for testing

# Concurrency and throttling settings
CONCURRENT_REQUESTS_PER_DOMAIN = 1
DOWNLOAD_DELAY = 2  # Increased delay
RANDOMIZE_DOWNLOAD_DELAY = 0.5  # Randomize delay (0.5 to 1.5 * DOWNLOAD_DELAY)

# Retry settings
RETRY_ENABLED = True
RETRY_TIMES = 5  # Increased from default 2
RETRY_HTTP_CODES = [500, 502, 503, 504, 408, 429]

# Timeout settings
DOWNLOAD_TIMEOUT = 30  # Increased timeout

# Request headers to appear more like a real browser
DEFAULT_REQUEST_HEADERS = {
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
    'Accept-Encoding': 'gzip, deflate, br',
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1',
}

# Modern FEEDS setting (replaces deprecated FEED_URI and FEED_FORMAT)
FEEDS = {
    'urls.csv': {
        'format': 'csv',
        'encoding': 'utf8',
        'store_empty': False,
        'overwrite': True,
    }
}

# Enable autothrottle for better request management
AUTOTHROTTLE_ENABLED = True
AUTOTHROTTLE_START_DELAY = 1
AUTOTHROTTLE_MAX_DELAY = 10
AUTOTHROTTLE_TARGET_CONCURRENCY = 1.0
AUTOTHROTTLE_DEBUG = True  # Enable to see throttling stats

# Disable cookies if not needed
COOKIES_ENABLED = False

# Log level for debugging
LOG_LEVEL = 'INFO'

# DNS timeout
DNSCACHE_ENABLED = True
DNSCACHE_SIZE = 10000
DNS_TIMEOUT = 60