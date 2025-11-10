BOT_NAME = "url_crawler"

SPIDER_MODULES = ["url_crawler.spiders"]
NEWSPIDER_MODULE = "url_crawler.spiders"

ADDONS = {}

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

ROBOTSTXT_OBEY = False

CONCURRENT_REQUESTS = 16
CONCURRENT_REQUESTS_PER_DOMAIN = 8
CONCURRENT_REQUESTS_PER_IP = 8

DOWNLOAD_DELAY = 0
RANDOMIZE_DOWNLOAD_DELAY = 0

REACTOR_THREADPOOL_MAXSIZE = 20

RETRY_ENABLED = True
RETRY_TIMES = 2
RETRY_HTTP_CODES = [500, 502, 503, 504, 408, 429]

DOWNLOAD_TIMEOUT = 15
DNS_TIMEOUT = 10

DEFAULT_REQUEST_HEADERS = {
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
    'Accept-Encoding': 'gzip, deflate, br',
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1',
}

AUTOTHROTTLE_ENABLED = False

COOKIES_ENABLED = False

DOWNLOADER_MIDDLEWARES = {
    'scrapy.downloadermiddlewares.retry.RetryMiddleware': 90,
    'scrapy.downloadermiddlewares.httpcompression.HttpCompressionMiddleware': 810,
}

FEEDS = {
    'urls.csv': {
        'format': 'csv',
        'encoding': 'utf8',
        'store_empty': False,
        'overwrite': True,
    }
}

DNSCACHE_ENABLED = True
DNSCACHE_SIZE = 10000

DOWNLOAD_HANDLERS = {
    'http': 'scrapy.core.downloader.handlers.http.HTTPDownloadHandler',
    'https': 'scrapy.core.downloader.handlers.http.HTTPDownloadHandler',
}

LOG_LEVEL = 'INFO'

MEMUSAGE_ENABLED = True
MEMUSAGE_LIMIT_MB = 2048
MEMUSAGE_WARNING_MB = 1024

AJAXCRAWL_ENABLED = False
COMPRESSION_ENABLED = True

ITEM_PIPELINES = {
}