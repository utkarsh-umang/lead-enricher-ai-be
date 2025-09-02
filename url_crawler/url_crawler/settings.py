# Updated settings.py - Optimized for speed
BOT_NAME = "url_crawler"

SPIDER_MODULES = ["url_crawler.spiders"]
NEWSPIDER_MODULE = "url_crawler.spiders"

ADDONS = {}

# User agent - some sites block requests without proper user agent
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

# Obey robots.txt rules - disabled for speed
ROBOTSTXT_OBEY = False

# SPEED OPTIMIZATION SETTINGS
# =========================

# Concurrency settings - these are the key to speed
CONCURRENT_REQUESTS = 16              # Global concurrent requests
CONCURRENT_REQUESTS_PER_DOMAIN = 8   # Per domain concurrent requests
CONCURRENT_REQUESTS_PER_IP = 8      # Per IP concurrent requests

# Disable delays for maximum speed (be careful with this)
DOWNLOAD_DELAY = 0                    # No delay between requests
RANDOMIZE_DOWNLOAD_DELAY = 0          # No randomization

# Reactor settings for better performance
REACTOR_THREADPOOL_MAXSIZE = 20

# Retry settings - reduce retries for speed
RETRY_ENABLED = True
RETRY_TIMES = 2                       # Reduced from 5
RETRY_HTTP_CODES = [500, 502, 503, 504, 408, 429]

# Timeout settings - shorter timeouts for faster failures
DOWNLOAD_TIMEOUT = 15                 # Reduced from 30
DNS_TIMEOUT = 10                      # Reduced from 60

# Request headers
DEFAULT_REQUEST_HEADERS = {
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
    'Accept-Encoding': 'gzip, deflate, br',
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1',
}

# CRITICAL: Disable or configure AutoThrottle properly
# AutoThrottle conflicts with your speed settings!
AUTOTHROTTLE_ENABLED = False          # DISABLED for maximum speed
# If you want to keep AutoThrottle enabled, use these settings instead:
# AUTOTHROTTLE_ENABLED = True
# AUTOTHROTTLE_START_DELAY = 0
# AUTOTHROTTLE_MAX_DELAY = 1
# AUTOTHROTTLE_TARGET_CONCURRENCY = 8.0
# AUTOTHROTTLE_DEBUG = True

# Disable cookies for speed
COOKIES_ENABLED = False

# Disable unnecessary middlewares for speed
DOWNLOADER_MIDDLEWARES = {
    'scrapy.downloadermiddlewares.retry.RetryMiddleware': 90,
    'scrapy.downloadermiddlewares.httpcompression.HttpCompressionMiddleware': 810,
}

# Modern FEEDS setting
FEEDS = {
    'urls.csv': {
        'format': 'csv',
        'encoding': 'utf8',
        'store_empty': False,
        'overwrite': True,
    }
}

# DNS and connection settings
DNSCACHE_ENABLED = True
DNSCACHE_SIZE = 10000

# Connection pool settings for better performance
DOWNLOAD_HANDLERS = {
    'http': 'scrapy.core.downloader.handlers.http.HTTPDownloadHandler',
    'https': 'scrapy.core.downloader.handlers.http.HTTPDownloadHandler',
}

# Disable redirect middleware if you don't need it
# REDIRECT_ENABLED = False

# Log level
LOG_LEVEL = 'INFO'

# Memory usage optimization
MEMUSAGE_ENABLED = True
MEMUSAGE_LIMIT_MB = 2048
MEMUSAGE_WARNING_MB = 1024

# Additional speed optimizations
AJAXCRAWL_ENABLED = False
COMPRESSION_ENABLED = True

# Pipeline settings - disable if not needed
ITEM_PIPELINES = {
    # Add your pipelines here if needed
}

# Stats collection - disable for slight speed improvement
# STATS_CLASS = 'scrapy.statscollectors.DummyStatsCollector'