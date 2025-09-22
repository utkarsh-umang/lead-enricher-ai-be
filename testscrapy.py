import asyncio
import aiohttp
import time
import os
import json
import hashlib
import logging
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass
from collections import defaultdict
from urllib.parse import urlparse, urljoin
from bs4 import BeautifulSoup
from google.oauth2 import service_account
from googleapiclient.discovery import build
import re
import multiprocessing
import tempfile
from scrapy import Spider, Request
from scrapy.crawler import CrawlerProcess, CrawlerRunner
from twisted.internet import reactor
import threading
from twisted.internet.asyncioreactor import AsyncioSelectorReactor
import sys
from twisted.internet import reactor
from twisted.internet.asyncioreactor import install as install_asyncio_reactor
from twisted.internet.defer import ensureDeferred

# Fix for Windows ProactorEventLoop
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    print("DEBUG: Set WindowsSelectorEventLoopPolicy for compatibility")

# Constants from original pipeline
CATEGORY_THRESHOLDS = {
    "ABOUT_US": 200,
    "EBOOK": 200,
    "COURSES": 300,
    "RECENT_BLOG": 450,
    "TESTIMONIALS": 100,
    "WEBINAR": 150,
    "SERVICES": 150,
    "PODCAST": 200,
    "SHOP": 100,
}

CATEGORY_KEYWORDS = {
    "ABOUT_US": [
        "about", "who-we-are", "company", "our-story", "mission", "values", 
        "about-us", "story", "timeline", "milestones", "why-us"
    ],
    "EBOOK": [
        "ebook", "e-book", "whitepaper", "white-paper", "guide", "pdf", 
        "resources", "downloads", "books", "library", "documents"
    ],
    "COURSES": [
        "course", "academy", "learning", "training", "workshop",
        "certification", "program", "bootcamp", "masterclass", 
        "education", "class", "e-learning"
    ],
    "RECENT_BLOG": [
        "blog", "insights", "articles", "news", "updates", 
        "post", "media", "latest", "trends", "press", 
        "content-hub"
    ],
    "TESTIMONIALS": [
        "testimonial", "reviews", "case-study", "success-story", 
        "client-story", "customer-story", "feedback", "clients", 
        "portfolio", "results", "social-proof"
    ],
    "WEBINAR": [
        "webinar", "event", "session", "live", "virtual-event", 
        "presentation", "conference", "summit", "registration", 
        "upcoming", "schedule"
    ],
    "SERVICES": [
        "service", "solution", "offering", "expertise", "consulting", 
        "what-we-do", "capability", "support", "practice", 
        "professional-services", "how-we-help"
    ],
    "PODCAST": [
        "podcast", "episodes", "audio", "listen", "show", 
        "interview", "series", "stream", "speakers", 
        "voice", "subscribe"
    ],
    "SHOP": [
        "shop", "store", "buy", "purchase", "products", 
        "cart", "checkout", "pricing", "e-commerce", 
        "merchandise", "order"
    ]
}

COLUMN_TO_WRITE_URL_TO = {
    "ABOUT_US": "M",
    "EBOOK": "N",
    "COURSES": "O",
    "RECENT_BLOG": "P",
    "TESTIMONIALS": "Q",
    "WEBINAR": "R",
    "SERVICES": "S",
    "PODCAST": "T",
    "SHOP": "U"
}

CATEGORY_RULES = {
    'ABOUT_US': 'ascending',
    'EBOOK': 'ascending',
    'COURSES': 'ascending',
    'RECENT_BLOG': 'descending',
    'TESTIMONIALS': 'ascending',
    'WEBINAR': 'descending',
    'SERVICES': 'descending',
    'PODCAST': 'descending',
    'SHOP': 'ascending'
}

EXTRACTION_METADATA_COLUMN = "V"
CACHE_DIR = "spider_cache"
os.makedirs(CACHE_DIR, exist_ok=True)

@dataclass
class ProcessingResult:
    category: str
    content: str
    metadata: str
    urls_found: List[str]

@dataclass
class ProductionConfig:
    # REDUCED Concurrency limits for debugging
    max_concurrent_rows: int = 2  # Reduced from 5
    max_concurrent_scrapes_per_row: int = 4  # Reduced from 8
    max_connections_per_host: int = 5  # Reduced from 10
    
    # INCREASED Rate limiting for stability
    spider_rate_limit_seconds: float = 10.0  # Increased from 5.0
    google_sheets_batch_size: int = 5  # Reduced from 10
    google_sheets_rate_limit: float = 2.0  # Increased from 1.0
    
    # INCREASED Timeouts
    scraping_timeout_seconds: int = 30  # Increased from 15
    spider_timeout_seconds: int = 120  # Increased from 60
    worker_timeout_seconds: int = 600  # Increased from 300
    
    # Retry settings
    max_retries: int = 3  # Increased from 2
    retry_delay_seconds: float = 1.0  # Increased from 0.5
    
    # Memory management
    max_content_size_bytes: int = 50000
    max_cache_size: int = 500  # Reduced from 1000

class ProductionMonitor:
    def __init__(self):
        self.stats = defaultdict(int)
        self.start_time = time.time()
        self.errors = []
        
        # Setup logging with DEBUG level
        logging.basicConfig(
            level=logging.DEBUG,  # Changed from INFO to DEBUG
            format='%(asctime)s - %(levelname)s - %(name)s - %(message)s',
            handlers=[
                logging.FileHandler('pipeline_debug.log'),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)

    def log_progress(self, processed: int, total: int):
        elapsed = time.time() - self.start_time
        rate = processed / elapsed if elapsed > 0 else 0
        eta = (total - processed) / rate if rate > 0 else 0
        
        self.logger.info(f"Progress: {processed}/{total} ({processed/total*100:.1f}%) "
                         f"Rate: {rate:.2f} rows/sec, ETA: {eta/60:.1f} min")

    def log_error(self, error: str, row_num: Optional[int] = None):
        error_msg = f"Row {row_num}: {error}" if row_num else error
        self.errors.append(error_msg)
        self.logger.error(error_msg)

    def log_stats(self):
        self.logger.info("Pipeline Statistics:")
        for key, value in self.stats.items():
            self.logger.info(f"  {key}: {value}")
        
        if self.errors:
            self.logger.error(f"Errors encountered: {len(self.errors)}")
            for error in self.errors[-10:]:
                self.logger.error(f"  {error}")

# Helper functions from original pipeline
def calculate_url_depth(url: str) -> int:
    try:
        parsed = urlparse(url)
        path = parsed.path.strip('/').split('/')
        return len(path) if path != [''] else 0
    except Exception:
        return -1

def truncate_to_bytes(text: str, max_bytes: int) -> str:
    encoded = text.encode('utf-8')
    if len(encoded) <= max_bytes:
        return text
    truncated = encoded[:max_bytes]
    return truncated.decode('utf-8', errors='ignore')

def safe_join(contents: List[str], max_bytes: int = 50000, delimiter: str = " --- NEXT CONTENT FROM HERE --- ") -> str:
    final_text = ""
    for content in contents:
        candidate = final_text + (delimiter if final_text else "") + content
        if len(candidate.encode('utf-8')) > max_bytes:
            break
        final_text = candidate
    return final_text

def extract_main_html_content(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    main = soup.find("main") or soup.find("article")
    if main:
        return main.get_text(separator="\n", strip=True)
    candidates = [
        div for div in soup.find_all("div")
        if len(div.get_text(strip=True)) > 200
           and not any(c in " ".join(div.get("class", [])).lower() for c in ["nav", "header", "footer", "popup"])
    ]
    if candidates:
        return max(candidates, key=lambda d: len(d.get_text(strip=True))).get_text(separator="\n", strip=True)
    return soup.get_text(separator="\n", strip=True)

class SiteSpider(Spider):
    name = 'site_spider'
    custom_settings = {
        'FEEDS': {},  # Will be set dynamically
        'USER_AGENT': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'ROBOTSTXT_OBEY': False,
        # REDUCED concurrency for debugging
        'CONCURRENT_REQUESTS': 4,  # Reduced from 16
        'CONCURRENT_REQUESTS_PER_DOMAIN': 2,  # Reduced from 8
        'CONCURRENT_REQUESTS_PER_IP': 2,  # Reduced from 8
        # INCREASED delays
        'DOWNLOAD_DELAY': 2,  # Reduced from 5 for faster debugging
        'RANDOMIZE_DOWNLOAD_DELAY': 0.5,  # Reduced from 1
        'RETRY_ENABLED': True,
        'RETRY_TIMES': 2,
        'RETRY_HTTP_CODES': [500, 502, 503, 504, 408, 429, 403],  # Added 403
        'DOWNLOAD_TIMEOUT': 30,  # Increased from 15
        'DNS_TIMEOUT': 15,  # Increased from 10
        'AUTOTHROTTLE_ENABLED': True,  # ENABLED for better rate limiting
        'AUTOTHROTTLE_START_DELAY': 1,
        'AUTOTHROTTLE_MAX_DELAY': 10,
        'AUTOTHROTTLE_TARGET_CONCURRENCY': 2.0,  # Reduced from default
        'COOKIES_ENABLED': True,  # ENABLED to handle session cookies
        'DNSCACHE_ENABLED': True,
        'DNSCACHE_SIZE': 10000,
        'MEMUSAGE_ENABLED': True,
        'MEMUSAGE_LIMIT_MB': 1024,  # Reduced from 2048
        'MEMUSAGE_WARNING_MB': 512,  # Reduced from 1024
        'AJAXCRAWL_ENABLED': False,
        'COMPRESSION_ENABLED': True,
        'LOG_LEVEL': 'DEBUG',  # Changed from INFO to DEBUG
        'CLOSESPIDER_PAGECOUNT': 500,  # Limit pages to prevent infinite crawl
        'DEPTH_LIMIT': 3,  # Limit crawl depth
        'DOWNLOADER_MIDDLEWARES': {
            'scrapy.downloadermiddlewares.retry.RetryMiddleware': 90,
            'scrapy.downloadermiddlewares.httpcompression.HttpCompressionMiddleware': 810,
            'scrapy.downloadermiddlewares.cookies.CookiesMiddleware': 700,  # Added
        },
        'DEFAULT_REQUEST_HEADERS': {
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Cache-Control': 'no-cache',
            'Pragma': 'no-cache',
        },
    }

    def __init__(self, start_url=None, output_file=None, *args, **kwargs):
        super(SiteSpider, self).__init__(*args, **kwargs)
        self.start_urls = [start_url] if start_url else []
        self.output_file = output_file
        self.found_urls = set()
        
        # Set the domain correctly
        if start_url:
            parsed = urlparse(start_url)
            self.allowed_domains = [parsed.netloc]
            self.base_url = f"{parsed.scheme}://{parsed.netloc}"
            self.logger.info(f"Spider initialized for domain: {parsed.netloc}")
        
        # Configure output
        if output_file:
            self.custom_settings['FEEDS'] = {
                output_file: {
                    'format': 'jsonlines',
                    'encoding': 'utf8',
                    'store_empty': False,
                    'overwrite': True
                }
            }

    def start_requests(self):
        for url in self.start_urls:
            self.logger.info(f"Starting crawl from: {url}")
            yield Request(
                url=url,
                callback=self.parse,
                meta={'depth': 0},
                dont_filter=True,  # Don't filter the start URL
                errback=self.handle_error
            )

    def parse(self, response):
        current_url = response.url
        depth = response.meta.get('depth', 0)
        
        self.logger.debug(f"Parsing URL: {current_url} (depth: {depth})")
        
        # Record this URL
        self.found_urls.add(current_url)
        yield {'url': current_url, 'depth': depth}
        
        # Don't go too deep
        if depth >= 3:
            self.logger.debug(f"Max depth reached for {current_url}")
            return
        
        # Extract and follow links
        links_found = 0
        for href in response.css('a::attr(href)').getall():
            if not href:
                continue
                
            # Clean and resolve URL
            href = href.strip()
            if not href or href.startswith('#') or href.startswith('javascript:') or href.startswith('mailto:'):
                continue
            
            # Convert relative URLs to absolute
            try:
                absolute_url = urljoin(response.url, href)
                parsed_url = urlparse(absolute_url)
                
                # Check if it's in our domain
                if parsed_url.netloc in self.allowed_domains:
                    # Avoid duplicates and common non-content URLs
                    if (absolute_url not in self.found_urls and 
                        not any(skip in absolute_url.lower() for skip in 
                               ['.pdf', '.jpg', '.png', '.gif', '.css', '.js', 'wp-admin', 'wp-login'])):
                        
                        links_found += 1
                        yield Request(
                            url=absolute_url,
                            callback=self.parse,
                            meta={'depth': depth + 1},
                            errback=self.handle_error
                        )
                        
            except Exception as e:
                self.logger.debug(f"Error processing link {href}: {e}")
        
        self.logger.debug(f"Found {links_found} valid links on {current_url}")

    def handle_error(self, failure):
        self.logger.error(f"Request failed: {failure.request.url} - {failure.value}")

# FIXED: Define run_spider at module level with proper error handling
async def run_spider_async(start_url, output_file):
    """Run spider asynchronously with AsyncioSelectorReactor"""
    print(f"DEBUG: Starting async spider for {start_url}")
    print(f"DEBUG: Output file: {output_file}")
    
    try:
        # Install AsyncioSelectorReactor if not already
        if not reactor.__class__.__name__ == 'AsyncioSelectorReactor':
            install_asyncio_reactor()
            print("DEBUG: Installed AsyncioSelectorReactor")
        
        # Configure settings
        settings = {
            'FEEDS': {
                output_file: {
                    'format': 'jsonlines',
                    'encoding': 'utf8',
                    'store_empty': False,
                    'overwrite': True
                }
            },
            'USER_AGENT': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'ROBOTSTXT_OBEY': False,
            'CONCURRENT_REQUESTS': 4,
            'CONCURRENT_REQUESTS_PER_DOMAIN': 2,
            'DOWNLOAD_DELAY': 2,
            'DOWNLOAD_TIMEOUT': 30,
            'RETRY_TIMES': 2,
            'RETRY_HTTP_CODES': [500, 502, 503, 504, 408, 429, 403],
            'LOG_LEVEL': 'DEBUG',
            'CLOSESPIDER_PAGECOUNT': 100,
            'DEPTH_LIMIT': 2,
            'AUTOTHROTTLE_ENABLED': True,
            'AUTOTHROTTLE_START_DELAY': 1,
            'AUTOTHROTTLE_MAX_DELAY': 10,
            'AUTOTHROTTLE_TARGET_CONCURRENCY': 2.0,
            'COOKIES_ENABLED': True,
            'DOWNLOADER_MIDDLEWARES': {
                'scrapy.downloadermiddlewares.retry.RetryMiddleware': 90,
                'scrapy.downloadermiddlewares.httpcompression.HttpCompressionMiddleware': 810,
                'scrapy.downloadermiddlewares.cookies.CookiesMiddleware': 700,
                'scrapy_useragents.RandomUserAgentMiddleware': 400,
            },
            'DEFAULT_REQUEST_HEADERS': {
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.9',
                'Accept-Encoding': 'gzip, deflate, br',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
                'Cache-Control': 'no-cache',
                'Pragma': 'no-cache',
            },
        }
        
        # Create runner
        runner = CrawlerRunner(settings)
        
        # Crawl and stop reactor when done
        d = runner.crawl(SiteSpider, start_url=start_url, output_file=output_file)
        d.addBoth(lambda _: reactor.stop())
        
        # Run reactor in thread to avoid blocking asyncio
        def run_reactor():
            reactor.run()
        
        thread = threading.Thread(target=run_reactor)
        thread.start()
        thread.join(timeout=120)  # Timeout for the thread
        
        if thread.is_alive():
            print("DEBUG: Spider thread timeout, stopping reactor")
            reactor.callFromThread(reactor.stop)
            thread.join(timeout=10)
        
        print(f"DEBUG: Spider finished for {start_url}")
        
    except Exception as e:
        print(f"DEBUG: Spider error for {start_url}: {e}")
        import traceback
        traceback.print_exc()

class OptimizedSiteSpiderWrapper:
    def __init__(self):
        self.cache = {}
        self.logger = logging.getLogger(__name__ + ".SpiderWrapper")
        
    def _hash_url(self, url: str) -> str:
        return hashlib.md5(url.encode()).hexdigest()

    def _get_cache_path(self, url: str) -> str:
        return os.path.join(CACHE_DIR, f"{self._hash_url(url)}.json")
    
    def get_cached_result(self, url: str) -> Optional[List[str]]:
        """Check if URL is cached"""
        cache_path = self._get_cache_path(url)
        if os.path.exists(cache_path):
            try:
                with open(cache_path, 'r') as f:
                    data = json.load(f)
                    urls = data if isinstance(data, list) else [item.get('url') for item in data if item.get('url')]
                    self.logger.info(f"Cache hit for {url}: {len(urls)} URLs")
                    return urls
            except Exception as e:
                self.logger.error(f"Cache read error for {url}: {e}")
                return None
        return None

    def map_url(self, url: str) -> List[str]:
        """Map URL using Scrapy spider with caching and better error handling"""
        self.logger.info(f"Starting spider mapping for: {url}")
        
        # Check cache first
        cached = self.get_cached_result(url)
        if cached:
            return cached
        
        # Validate URL
        try:
            parsed = urlparse(url)
            if not parsed.scheme or not parsed.netloc:
                self.logger.error(f"Invalid URL format: {url}")
                return []
        except Exception as e:
            self.logger.error(f"URL parsing error: {e}")
            return []
            
        try:
            # Create temporary file
            with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as temp_file:
                temp_filename = temp_file.name
            
            self.logger.info(f"Using temp file: {temp_filename}")
            
            # Run async spider (non-blocking)
            loop = asyncio.get_event_loop()
            loop.run_until_complete(run_spider_async(url, temp_filename))
            
            # Read and parse results
            links = []
            try:
                if os.path.exists(temp_filename) and os.path.getsize(temp_filename) > 0:
                    with open(temp_filename, 'r') as f:
                        content = f.read()
                        self.logger.debug(f"Temp file content ({len(content)} bytes): {content[:500]}...")
                        for line_num, line in enumerate(content.splitlines(), 1):
                            line = line.strip()
                            if not line:
                                continue
                            try:
                                item = json.loads(line)
                                if item.get('url'):
                                    links.append(item['url'])
                            except json.JSONDecodeError as e:
                                self.logger.error(f"JSON decode error on line {line_num}: {e}")
                                continue
                    
                    self.logger.info(f"Parsed {len(links)} URLs from spider results")
                    
                    # Cache the results
                    if links:
                        cache_path = self._get_cache_path(url)
                        with open(cache_path, 'w') as f:
                            json.dump(links, f, indent=2)
                        self.logger.info(f"Cached {len(links)} URLs for {url}")
                else:
                    self.logger.warning(f"Temp file {temp_filename} is empty or doesn't exist")
                    
            except Exception as e:
                self.logger.error(f"Error reading spider results: {e}")
                import traceback
                self.logger.error(traceback.format_exc())
            finally:
                # Clean up temp file
                try:
                    if os.path.exists(temp_filename):
                        os.unlink(temp_filename)
                except Exception as e:
                    self.logger.error(f"Error cleaning up temp file: {e}")
                    
            self.logger.info(f"Spider mapping completed for {url}: found {len(links)} URLs")
            return links
            
        except Exception as e:
            self.logger.error(f"Spider error for {url}: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            return []

    def filter_by_category(self, urls: List[str], category: str) -> List[str]:
        """Filter URLs by category keywords with better logging"""
        keywords = CATEGORY_KEYWORDS.get(category.upper(), [])
        if not keywords:
            self.logger.warning(f"No keywords defined for category: {category}")
            return []
        
        filtered = []
        for url in urls:
            url_lower = url.lower()
            for keyword in keywords:
                if keyword in url_lower:
                    filtered.append(url)
                    break
        
        self.logger.info(f"Category {category}: filtered {len(filtered)} URLs from {len(urls)} total")
        return filtered

# Rest of the classes remain the same but with updated logging and error handling
class GoogleSheetsManager:
    def __init__(self, credentials_file: str):
        scopes = ['https://www.googleapis.com/auth/spreadsheets']
        creds = service_account.Credentials.from_service_account_file(credentials_file, scopes=scopes)
        self.service = build('sheets', 'v4', credentials=creds)
        self.logger = logging.getLogger(__name__ + ".SheetsManager")

    def extract_spreadsheet_id(self, sheet_url: str) -> str:
        pattern = r'/spreadsheets/d/([a-zA-Z0-9-_]+)'
        match = re.search(pattern, sheet_url)
        if match:
            return match.group(1)
        raise ValueError("Invalid Google Sheet URL")

    def get_urls(self, spreadsheet_id: str, start_row: int = 2) -> List[Tuple[int, str]]:
        range_name = f"G{start_row}:G"
        result = self.service.spreadsheets().values().get(spreadsheetId=spreadsheet_id, range=range_name).execute()
        values = result.get('values', [])
        urls = [(i + start_row, row[0]) for i, row in enumerate(values) if row and row[0].strip()]
        self.logger.info(f"Retrieved {len(urls)} URLs from spreadsheet")
        return urls

    def batch_update_cells(self, spreadsheet_id: str, updates: List[Dict]):
        """Batch update multiple cells at once"""
        if not updates:
            return
            
        body = {
            'valueInputOption': 'RAW',
            'data': updates
        }
        
        try:
            self.service.spreadsheets().values().batchUpdate(
                spreadsheetId=spreadsheet_id, 
                body=body
            ).execute()
            self.logger.info(f"Successfully updated {len(updates)} cells in spreadsheet")
        except Exception as e:
            self.logger.error(f"Error updating spreadsheet: {e}")
            raise

class OptimizedPipeline:
    def __init__(self, config: ProductionConfig, credentials_file: str):
        self.config = config
        self.spider = OptimizedSiteSpiderWrapper()
        self.sheet_mgr = GoogleSheetsManager(credentials_file)
        self.monitor = ProductionMonitor()
        
        # Connection pooling with reduced limits
        self.connector = aiohttp.TCPConnector(
            limit=50,  # Reduced from 100
            limit_per_host=config.max_connections_per_host,
            keepalive_timeout=30,
            enable_cleanup_closed=True
        )
        self.session = None
        
        # Rate limiting
        self.spider_semaphore = asyncio.Semaphore(1)
        self.last_spider_call = 0
        
        # Work queues
        self.task_queue = asyncio.Queue()
        self.results_queue = asyncio.Queue()
        
        # Circuit breaker
        self.spider_failures = 0
        self.max_spider_failures = 5  # Reduced from 10

    async def __aenter__(self):
        self.session = aiohttp.ClientSession(
            connector=self.connector,
            timeout=aiohttp.ClientTimeout(total=self.config.scraping_timeout_seconds)
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
        await self.connector.close()

    async def smart_spider_call(self, url: str) -> List[str]:
        """Spider call with intelligent rate limiting and error handling"""
        self.monitor.logger.info(f"Spider call for: {url}")
        
        # Check cache first
        cached_result = self.spider.get_cached_result(url)
        if cached_result:
            self.monitor.logger.info(f"Cache hit for {url}: {len(cached_result)} URLs")
            self.monitor.stats['spider_cache_hits'] += 1
            return cached_result
            
        # Circuit breaker
        if self.spider_failures >= self.max_spider_failures:
            self.monitor.log_error(f"Spider circuit breaker open ({self.spider_failures} failures)")
            return []
            
        async with self.spider_semaphore:
            current_time = time.time()
            time_since_last_call = current_time - self.last_spider_call
            
            if time_since_last_call < self.config.spider_rate_limit_seconds:
                wait_time = self.config.spider_rate_limit_seconds - time_since_last_call
                self.monitor.logger.info(f"Rate limiting: waiting {wait_time:.1f}s for {url}")
                await asyncio.sleep(wait_time)
            
            try:
                # Call map_url directly (now handles async internally)
                result = self.spider.map_url(url)
                
                self.last_spider_call = time.time()
                self.spider_failures = 0
                self.monitor.stats['spider_success'] += 1
                self.monitor.logger.info(f"Spider success for {url}: found {len(result)} URLs")
                return result
            except Exception as e:
                self.spider_failures += 1
                self.monitor.log_error(f"Spider error for {url}: {e}")
                self.monitor.stats['spider_failures'] += 1
                return []

    async def scrape_url_with_session(self, url: str) -> str:
        """Scrape single URL using shared session"""
        try:
            async with self.session.get(
                url, 
                timeout=aiohttp.ClientTimeout(total=self.config.scraping_timeout_seconds)
            ) as response:
                if response.status == 200:
                    html = await response.text()
                    content = extract_main_html_content(html)
                    self.monitor.logger.debug(f"Scraped {len(content)} chars from {url}")
                    return content
                else:
                    self.monitor.logger.warning(f"HTTP {response.status} for {url}")
                    return f"Error: HTTP {response.status}"
        except Exception as e:
            self.monitor.logger.error(f"Scraping error for {url}: {e}")
            return f"Error: {str(e)}"

    async def scrape_multiple_urls(self, urls: List[str]) -> List[str]:
        """Scrape multiple URLs concurrently with retry logic"""
        if not urls:
            return []
            
        self.monitor.logger.info(f"Scraping {len(urls)} URLs")
        semaphore = asyncio.Semaphore(self.config.max_concurrent_scrapes_per_row)
        
        async def scrape_with_retry(url: str) -> str:
            async with semaphore:
                for attempt in range(self.config.max_retries):
                    try:
                        result = await self.scrape_url_with_session(url)
                        if not result.startswith("Error:"):
                            self.monitor.stats['scraping_success'] += 1
                            return result
                    except Exception as e:
                        if attempt == self.config.max_retries - 1:
                            self.monitor.stats['scraping_failures'] += 1
                            return f"Error: {str(e)}"
                        await asyncio.sleep(self.config.retry_delay_seconds * (attempt + 1))
                return f"Error: Max retries exceeded"
        
        tasks = [scrape_with_retry(url) for url in urls]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        successful_scrapes = len([r for r in results if isinstance(r, str) and not r.startswith("Error:")])
        self.monitor.logger.info(f"Successfully scraped {successful_scrapes}/{len(urls)} URLs")
        
        return [str(r) if isinstance(r, Exception) else r for r in results]

    async def process_single_category(self, sub_urls: List[str], category: str) -> ProcessingResult:
        """Process one category for a row"""
        self.monitor.logger.info(f"Processing category {category} with {len(sub_urls)} total URLs")
        
        filtered_urls = self.spider.filter_by_category(sub_urls, category)
        
        if not filtered_urls:
            self.monitor.logger.info(f"No URLs found for category {category}")
            return ProcessingResult(
                category=category,
                content="No URL found",
                metadata=f"{category.upper()}=0",
                urls_found=[]
            )

        self.monitor.logger.info(f"Found {len(filtered_urls)} URLs for category {category}")
        
        url_depth_pairs = [(url, calculate_url_depth(url)) for url in filtered_urls]
        url_depth_pairs = [(url, depth) for url, depth in url_depth_pairs if depth != -1]
        
        if not url_depth_pairs:
            return ProcessingResult(
                category=category,
                content="No valid URLs found",
                metadata=f"{category.upper()}=0",
                urls_found=[]
            )

        sort_order = CATEGORY_RULES.get(category.upper(), 'ascending')
        reverse_sort = sort_order == 'descending'
        sorted_pairs = sorted(url_depth_pairs, key=lambda x: x[1], reverse=reverse_sort)
        
        # Limit to top 5 URLs for debugging
        selected_urls = [url for url, _ in sorted_pairs[:5]]  # Reduced from 10
        self.monitor.logger.info(f"Selected {len(selected_urls)} URLs for scraping in category {category}")
        
        contents = await self.scrape_multiple_urls(selected_urls)
        
        valid_contents = [c for c in contents if c and not c.startswith("Error:")]
        
        if not valid_contents:
            content = "No meaningful content found"
            metadata = f"{category.upper()}=0"
        else:
            content = safe_join(valid_contents, self.config.max_content_size_bytes)
            metadata = f"{category.upper()}={len(valid_contents)}"

        self.monitor.logger.info(f"Category {category} completed: {len(valid_contents)} valid contents")
        
        return ProcessingResult(
            category=category,
            content=content,
            metadata=metadata,
            urls_found=selected_urls
        )

    async def process_all_categories_for_row(self, row_num: int, main_url: str) -> Dict[str, ProcessingResult]:
        """Process ALL 9 categories for a single row simultaneously"""
        self.monitor.logger.info(f"Processing all categories for row {row_num}: {main_url}")
        
        # Get all sub-URLs for this domain
        sub_urls = await self.smart_spider_call(main_url)
        
        if not sub_urls:
            self.monitor.logger.warning(f"No sub-URLs found for {main_url}")
            empty_results = {}
            for category in CATEGORY_KEYWORDS.keys():
                empty_results[category] = ProcessingResult(
                    category=category,
                    content="No URLs found from spider",
                    metadata=f"{category}=0",
                    urls_found=[]
                )
            return empty_results
        
        self.monitor.logger.info(f"Found {len(sub_urls)} sub-URLs for {main_url}")
        
        # Process all categories concurrently
        tasks = []
        for category in CATEGORY_KEYWORDS.keys():
            task = self.process_single_category(sub_urls, category)
            tasks.append((category, task))
        
        results = {}
        for category, task in tasks:
            try:
                result = await task
                results[category] = result
                self.monitor.logger.debug(f"Completed category {category} for row {row_num}")
            except Exception as e:
                self.monitor.log_error(f"Error processing category {category} for row {row_num}: {e}", row_num)
                results[category] = ProcessingResult(
                    category=category,
                    content=f"Error: {str(e)}",
                    metadata=f"{category}=0",
                    urls_found=[]
                )
        
        self.monitor.logger.info(f"Completed all categories for row {row_num}")
        return results

    async def worker(self, worker_id: int):
        """Queue-based worker for processing rows"""
        processed_count = 0
        self.monitor.logger.info(f"Worker {worker_id} started")
        
        while True:
            try:
                row_data = await asyncio.wait_for(
                    self.task_queue.get(),
                    timeout=self.config.worker_timeout_seconds
                )
                
                if row_data is None:
                    self.monitor.logger.info(f"Worker {worker_id} received shutdown signal")
                    break
                
                row_num, main_url = row_data
                start_time = time.time()
                
                self.monitor.logger.info(f"Worker {worker_id} processing row {row_num}: {main_url}")
                
                try:
                    results = await self.process_all_categories_for_row(row_num, main_url)
                    processing_time = time.time() - start_time
                    
                    await self.results_queue.put((row_num, results))
                    processed_count += 1
                    
                    self.monitor.stats['rows_processed'] += 1
                    self.monitor.stats['total_processing_time'] += processing_time
                    
                    self.monitor.logger.info(f"Worker {worker_id} completed row {row_num} in {processing_time:.2f}s")
                
                except Exception as e:
                    self.monitor.log_error(f"Worker {worker_id} failed on row {row_num}: {e}", row_num)
                    self.monitor.stats['worker_failures'] += 1
                
                finally:
                    self.task_queue.task_done()
                    
            except asyncio.TimeoutError:
                self.monitor.log_error(f"Worker {worker_id} timeout")
                break
            except Exception as e:
                self.monitor.log_error(f"Worker {worker_id} unexpected error: {e}")
                break
        
        self.monitor.logger.info(f"Worker {worker_id} finished after processing {processed_count} rows")

    async def batch_update_sheets(self, batch_results: List[Tuple[int, Dict[str, ProcessingResult]]]):
        """Batch update Google Sheets to reduce API calls"""
        if not batch_results:
            return
        
        self.monitor.logger.info(f"Updating Google Sheets with batch of {len(batch_results)} rows")
        
        updates = []
        
        for row_num, results in batch_results:
            # Update category columns
            for category, result in results.items():
                column = COLUMN_TO_WRITE_URL_TO.get(category)
                if column:
                    updates.append({
                        'range': f"{column}{row_num}",
                        'values': [[result.content]]
                    })
            
            # Update metadata column
            all_metadata = [result.metadata for result in results.values()]
            combined_metadata = ','.join(all_metadata)
            updates.append({
                'range': f"{EXTRACTION_METADATA_COLUMN}{row_num}",
                'values': [[combined_metadata]]
            })
        
        try:
            self.sheet_mgr.batch_update_cells(self.spreadsheet_id, updates)
            self.monitor.stats['sheets_updates'] += len(batch_results)
            self.monitor.logger.info(f"Successfully updated {len(batch_results)} rows in Google Sheets")
        except Exception as e:
            self.monitor.log_error(f"Batch sheets update failed: {e}")
            raise

    async def process_results(self, total_rows: int):
        """Process results as they come in and batch update sheets"""
        processed = 0
        batch_results = []
        
        self.monitor.logger.info(f"Starting results processor for {total_rows} rows")
        
        while processed < total_rows:
            try:
                row_num, results = await asyncio.wait_for(
                    self.results_queue.get(),
                    timeout=self.config.worker_timeout_seconds
                )
                
                batch_results.append((row_num, results))
                processed += 1
                
                if processed % 5 == 0 or processed == total_rows:
                    self.monitor.log_progress(processed, total_rows)
                
                # Update sheets in smaller batches for debugging
                if len(batch_results) >= self.config.google_sheets_batch_size or processed == total_rows:
                    self.monitor.logger.info(f"WRITING BATCH: {len(batch_results)} rows to Google Sheets")
                    self.monitor.logger.debug(f"Batch contains rows: {[r[0] for r in batch_results]}")
                    
                    await self.batch_update_sheets(batch_results)
                    
                    self.monitor.logger.info(f"BATCH WRITTEN: Rows {[r[0] for r in batch_results]} updated successfully")
                    batch_results = []
                    
                    # Rate limit Google Sheets API calls
                    await asyncio.sleep(self.config.google_sheets_rate_limit)
                    
            except asyncio.TimeoutError:
                self.monitor.log_error("Timeout waiting for results")
                break
            except Exception as e:
                self.monitor.log_error(f"Error in results processor: {e}")
                break
        
        self.monitor.logger.info(f"Results processor completed: {processed}/{total_rows} rows processed")

    async def process_all_optimized(self, sheet_url: str, start_row: int = 2):
        """Main optimized processing function"""
        try:
            self.monitor.logger.info("Starting optimized pipeline with DEBUG settings")
            self.spreadsheet_id = self.sheet_mgr.extract_spreadsheet_id(sheet_url)
            urls = self.sheet_mgr.get_urls(self.spreadsheet_id, start_row)
            
            if not urls:
                self.monitor.log_error("No URLs found in spreadsheet")
                return
            
            self.monitor.logger.info(f"Processing {len(urls)} rows with {self.config.max_concurrent_rows} workers")
            
            # Queue all tasks
            for row_num, main_url in urls:
                await self.task_queue.put((row_num, main_url))
                self.monitor.logger.debug(f"Queued row {row_num}: {main_url}")
            
            # Start workers
            workers = []
            for i in range(self.config.max_concurrent_rows):
                worker_task = asyncio.create_task(self.worker(i))
                workers.append(worker_task)
            
            # Start results processor
            results_processor = asyncio.create_task(self.process_results(len(urls)))
            
            # Wait for all tasks to be processed
            await self.task_queue.join()
            self.monitor.logger.info("All tasks completed, shutting down workers")
            
            # Send shutdown signals to workers
            for _ in workers:
                await self.task_queue.put(None)
            
            # Wait for workers and results processor to finish
            await asyncio.gather(*workers, return_exceptions=True)
            await results_processor
            
            self.monitor.log_stats()
            self.monitor.logger.info("Pipeline completed successfully")
            
        except Exception as e:
            self.monitor.log_error(f"Pipeline failed: {e}")
            import traceback
            self.monitor.logger.error(traceback.format_exc())
            raise

# Example usage and testing function
async def test_spider_directly(url: str = "https://example.com"):
    """Test the spider directly for debugging"""
    print(f"Testing spider directly with URL: {url}")
    
    spider_wrapper = OptimizedSiteSpiderWrapper()
    result = spider_wrapper.map_url(url)
    
    print(f"Spider returned {len(result)} URLs:")
    for i, found_url in enumerate(result[:10], 1):  # Show first 10
        print(f"  {i}. {found_url}")
    
    if len(result) > 10:
        print(f"  ... and {len(result) - 10} more URLs")
    
    return result

# Main execution function for debugging
if __name__ == "__main__":
    import asyncio
    
    # Test the spider directly first
    test_url = "https://www.barrerascpa.com"  # Replace with actual URL
    
    print("=" * 60)
    print("TESTING SPIDER DIRECTLY")
    print("=" * 60)
    
    result = asyncio.run(test_spider_directly(test_url))
    
    if result:
        print(f"\nSUCCESS: Spider test successful! Found {len(result)} URLs")
        
        # Test category filtering
        spider_wrapper = OptimizedSiteSpiderWrapper()
        for category in ["ABOUT_US", "SERVICES", "RECENT_BLOG"]:
            filtered = spider_wrapper.filter_by_category(result, category)
            print(f"  {category}: {len(filtered)} URLs")
            for url in filtered[:3]:  # Show first 3
                print(f"    - {url}")

    else:
        print("\nFAILED: Spider test failed - no URLs found")
        print("\nDebugging suggestions:")
        print("1. Check if the website blocks scrapers (try in browser)")
        print("2. Verify the URL is accessible")
        print("3. Check network connectivity")
        print("4. Look at the debug logs in 'pipeline_debug.log'")
        print("5. Try with a different website first")