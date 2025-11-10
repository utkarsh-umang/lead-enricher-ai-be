import scrapy
from scrapy.crawler import CrawlerProcess
from scrapy.linkextractors import LinkExtractor
from scrapy.spiders import CrawlSpider, Rule
from scrapy.utils.log import configure_logging
from urllib.parse import urlparse, urljoin
import logging
import tempfile
import os
import csv
from typing import List
import multiprocessing
import sys


class URLCrawlerSpider(CrawlSpider):
    """Internal spider class for URL discovery"""
    name = 'url_discovery_spider'
    
    def __init__(self, target_url: str, max_depth: int = 2, *args, **kwargs):
        super(URLCrawlerSpider, self).__init__(*args, **kwargs)
        
        # Parse the target URL and normalize
        if not target_url.startswith(('http://', 'https://')):
            target_url = 'https://' + target_url
        
        parsed_url = urlparse(target_url)
        self.domain = parsed_url.netloc
        self.base_domain = self.domain.replace('www.', '') if self.domain.startswith('www.') else self.domain
        
        # Set spider configuration
        self.start_urls = [target_url]
        
        # Create comprehensive allowed domains list
        domains_to_allow = {
            self.domain,
            self.base_domain,
            f"www.{self.base_domain}",
        }
        # Remove empty strings and None values
        self.allowed_domains = list(filter(None, domains_to_allow))
        
        # Store found URLs
        self.discovered_urls = set()
        self.max_depth = max_depth
        
        # Configure LinkExtractor rules - Allow more file types including XML
        self.rules = (
            Rule(
                LinkExtractor(
                    allow_domains=self.allowed_domains,
                    deny_extensions=[
                        'png', 'jpg', 'jpeg', 'gif', 'pdf', 'doc', 'docx', 
                        'zip', 'rar', 'mp3', 'mp4', 'avi', 'mov', 'wmv', 'flv', 'swf'
                    ],
                    canonicalize=True,
                    unique=True,
                    strip=True,
                ),
                callback='parse_page',
                follow=True,
                process_request='process_request'
            ),
        )
        
        # Re-compile rules after setting them
        self._compile_rules()
    
    def process_request(self, request, spider):
        """Process each request to add depth limiting"""
        depth = request.meta.get('depth', 0)
        if depth >= self.max_depth:
            return None
        return request
    
    def parse_page(self, response):
        """Parse each discovered page"""
        # Add URL to discovered set
        self.discovered_urls.add(response.url)
        
        # Log progress
        self.logger.info(f'Discovered URL: {response.url}')
        
        # Yield item for potential pipeline processing
        yield {
            'url': response.url,
            'status_code': response.status,
            'depth': response.meta.get('depth', 0),
            'title': response.css('title::text').get(default='').strip(),
            'content_type': response.headers.get('content-type', b'').decode('utf-8')
        }
    
    def start_requests(self):
        """Generate initial requests with proper headers"""
        for url in self.start_urls:
            yield scrapy.Request(
                url=url,
                errback=self.handle_error,
                headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.5',
                    'Accept-Encoding': 'gzip, deflate',
                    'Connection': 'keep-alive',
                }
            )
    
    def parse(self, response):
        """Handle the initial response and apply rules for following links"""
        # Process this page
        yield from self.parse_page(response)
        
        # Apply CrawlSpider rules to find and follow links
        return self._parse(response)
    
    def handle_error(self, failure):
        """Handle request failures"""
        self.logger.error(f'Request failed: {failure.request.url} - {failure.value}')


def _run_crawler_process(url, settings, temp_filename, max_depth):
    """Function to run crawler in a separate process"""
    try:
        # Configure logging to suppress scrapy noise
        configure_logging({'LOG_LEVEL': 'ERROR'})
        
        # Create and run crawler process
        process = CrawlerProcess(settings=settings)
        
        process.crawl(URLCrawlerSpider, target_url=url, max_depth=max_depth)
        
        # Start the process
        process.start()
        
        return True
    except Exception as e:
        print(f"Crawler process error: {e}")
        import traceback
        traceback.print_exc()
        return False


class URLCrawler:
    """Main URL Crawler class with enhanced discovery capabilities"""
    
    def __init__(self, 
                 max_depth: int = 3,
                 max_pages: int = 500,
                 delay: float = 1.0,
                 concurrent_requests: int = 8,
                 timeout: int = 30,
                 respect_robots: bool = True,
                 user_agent: str = None,
                 include_sitemaps: bool = True):
        """
        Initialize URL Crawler
        
        Args:
            max_depth: Maximum crawl depth (default: 3)
            max_pages: Maximum pages to crawl (default: 500)
            delay: Delay between requests in seconds (default: 1.0)
            concurrent_requests: Number of concurrent requests (default: 8)
            timeout: Request timeout in seconds (default: 30)
            respect_robots: Whether to obey robots.txt (default: True)
            user_agent: Custom user agent string
            include_sitemaps: Whether to discover and parse sitemaps (default: True)
        """
        self.max_depth = max_depth
        self.max_pages = max_pages
        self.delay = delay
        self.concurrent_requests = concurrent_requests
        self.timeout = timeout
        self.respect_robots = respect_robots
        self.include_sitemaps = include_sitemaps
        self.user_agent = user_agent or 'URLCrawler/1.0'
        
        # Configure logging
        self._setup_logging()
    
    def _setup_logging(self):
        """Setup logging configuration"""
        # Setup our own logger
        self.logger = logging.getLogger('URLCrawler')
        self.logger.setLevel(logging.INFO)
        
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
    
    def _get_crawler_settings(self, output_file):
        """Get optimized Scrapy settings"""
        settings = {
            # Basic settings
            'BOT_NAME': 'url_crawler',
            'ROBOTSTXT_OBEY': self.respect_robots,
            'USER_AGENT': self.user_agent,
            
            # Performance settings
            'CONCURRENT_REQUESTS': self.concurrent_requests,
            'CONCURRENT_REQUESTS_PER_DOMAIN': min(self.concurrent_requests // 2, 4),
            'DOWNLOAD_DELAY': self.delay,
            'RANDOMIZE_DOWNLOAD_DELAY': 0.5,
            'DOWNLOAD_TIMEOUT': self.timeout,
            'DNS_TIMEOUT': 10,
            
            # AutoThrottle for intelligent rate limiting
            'AUTOTHROTTLE_ENABLED': True,
            'AUTOTHROTTLE_START_DELAY': self.delay,
            'AUTOTHROTTLE_MAX_DELAY': self.delay * 10,
            'AUTOTHROTTLE_TARGET_CONCURRENCY': 2.0,
            'AUTOTHROTTLE_DEBUG': False,
            
            # Retry settings
            'RETRY_ENABLED': True,
            'RETRY_TIMES': 3,
            'RETRY_HTTP_CODES': [500, 502, 503, 504, 408, 429, 403],
            
            # Memory and performance
            'COOKIES_ENABLED': False,
            'REDIRECT_ENABLED': True,
            'DNSCACHE_ENABLED': True,
            'DNSCACHE_SIZE': 10000,
            'REACTOR_THREADPOOL_MAXSIZE': 20,
            
            # Disable unnecessary features
            'TELNETCONSOLE_ENABLED': False,
            'HTTPPROXY_ENABLED': False,
            
            # Logging
            'LOG_LEVEL': 'WARNING',
            
            # Request headers
            'DEFAULT_REQUEST_HEADERS': {
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.9',
                'Accept-Encoding': 'gzip, deflate, br',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
            },
            
            # Close spider settings
            'CLOSESPIDER_ITEMCOUNT': self.max_pages,
            'CLOSESPIDER_TIMEOUT': 1800,  # 30 minutes max
            
            # Output settings
            'FEEDS': {
                output_file: {
                    'format': 'csv',
                    'encoding': 'utf8',
                    'store_empty': False,
                    'overwrite': True,
                    'fields': ['url']
                }
            }
        }
        
        return settings
    
    def _discover_sitemaps(self, url: str) -> List[str]:
        """Discover and parse sitemap files"""
        import requests
        import xml.etree.ElementTree as ET
        
        sitemap_urls = set()
        parsed = urlparse(url)
        base_url = f"{parsed.scheme}://{parsed.netloc}"
        
        # Common sitemap locations
        sitemap_locations = [
            urljoin(base_url, '/sitemap.xml'),
            urljoin(base_url, '/sitemap_index.xml'),
            urljoin(base_url, '/robots.txt'),
        ]
        
        session = requests.Session()
        session.headers.update({'User-Agent': self.user_agent})
        
        for sitemap_url in sitemap_locations:
            try:
                response = session.get(sitemap_url, timeout=10)
                if response.status_code == 200:
                    if sitemap_url.endswith('.xml'):
                        # Parse XML sitemap
                        try:
                            root = ET.fromstring(response.content)
                            # Handle both sitemap and sitemapindex files
                            for elem in root.iter():
                                if elem.tag.endswith('}loc') or elem.tag == 'loc':
                                    if elem.text:
                                        sitemap_urls.add(elem.text)
                        except ET.ParseError:
                            pass
                    else:
                        # Parse robots.txt for sitemap references
                        for line in response.text.split('\n'):
                            if line.lower().startswith('sitemap:'):
                                sitemap_link = line.split(':', 1)[1].strip()
                                sitemap_urls.add(sitemap_link)
                                # Also parse the referenced sitemap
                                try:
                                    sitemap_response = session.get(sitemap_link, timeout=10)
                                    if sitemap_response.status_code == 200:
                                        root = ET.fromstring(sitemap_response.content)
                                        for elem in root.iter():
                                            if elem.tag.endswith('}loc') or elem.tag == 'loc':
                                                if elem.text:
                                                    sitemap_urls.add(elem.text)
                                except:
                                    pass
            except:
                continue
        
        return list(sitemap_urls)
    
    def discover_urls(self, url: str) -> List[str]:
        """
        Discover all sub-URLs for a given domain using multiple methods
        
        Args:
            url: The target URL to crawl
            
        Returns:
            List of discovered URLs
            
        Raises:
            ValueError: If URL is invalid
            Exception: If crawling fails
        """
        # Validate URL
        if not url or not isinstance(url, str):
            raise ValueError("URL must be a non-empty string")
        
        # Add protocol if missing
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
        
        # Parse and validate URL
        try:
            parsed = urlparse(url)
            if not parsed.netloc:
                raise ValueError("Invalid URL format")
        except Exception as e:
            raise ValueError(f"Invalid URL: {e}")
        
        self.logger.info(f"Starting comprehensive URL discovery for: {url}")
        
        discovered_urls = set()
        
        # Method 1: Sitemap discovery
        if self.include_sitemaps:
            self.logger.info("Discovering URLs from sitemaps...")
            try:
                sitemap_urls = self._discover_sitemaps(url)
                discovered_urls.update(sitemap_urls)
                self.logger.info(f"Found {len(sitemap_urls)} URLs from sitemaps")
            except Exception as e:
                self.logger.warning(f"Sitemap discovery failed: {e}")
        
        # Method 2: Scrapy crawling
        self.logger.info("Starting Scrapy crawl...")
        try:
            scrapy_urls = self._crawl_with_scrapy(url)
            discovered_urls.update(scrapy_urls)
            self.logger.info(f"Found {len(scrapy_urls)} URLs from Scrapy crawl")
        except Exception as e:
            self.logger.warning(f"Scrapy crawl failed: {e}")
        
        # Method 3: Add common files
        parsed = urlparse(url)
        base_url = f"{parsed.scheme}://{parsed.netloc}"
        common_files = [
            urljoin(base_url, '/robots.txt'),
            urljoin(base_url, '/sitemap.xml'),
            base_url,  # Root domain
        ]
        discovered_urls.update(common_files)
        
        # Filter URLs to only include same domain
        domain = parsed.netloc
        base_domain = domain.replace('www.', '') if domain.startswith('www.') else domain
        allowed_domains = {domain, f"www.{base_domain}", base_domain}
        
        filtered_urls = []
        for discovered_url in discovered_urls:
            try:
                parsed_discovered = urlparse(discovered_url)
                if parsed_discovered.netloc in allowed_domains:
                    filtered_urls.append(discovered_url)
            except:
                continue
        
        # Remove duplicates and sort
        final_urls = sorted(list(set(filtered_urls)))
        
        self.logger.info(f"Total URLs discovered: {len(final_urls)}")
        return final_urls
    
    def _crawl_with_scrapy(self, url: str) -> List[str]:
        """Run Scrapy crawl and return discovered URLs"""
        # Create temporary file for output
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as temp_file:
            temp_filename = temp_file.name
        
        try:
            # Get crawler settings
            settings = self._get_crawler_settings(temp_filename)
            
            # Run crawler in a separate process to avoid reactor conflicts
            process = multiprocessing.Process(
                target=_run_crawler_process,
                args=(url, settings, temp_filename, self.max_depth)
            )
            process.start()
            process.join()
            
            # Read results from temporary file
            discovered_urls = []
            try:
                if os.path.exists(temp_filename) and os.path.getsize(temp_filename) > 0:
                    with open(temp_filename, 'r', encoding='utf-8') as f:
                        reader = csv.DictReader(f)
                        for row in reader:
                            if 'url' in row and row['url'] and row['url'].strip():
                                discovered_urls.append(row['url'].strip())
            except Exception as e:
                self.logger.error(f"Error reading Scrapy results: {e}")
            
            return discovered_urls
        
        finally:
            # Clean up temporary file
            try:
                if os.path.exists(temp_filename):
                    os.unlink(temp_filename)
            except OSError:
                pass


# Simple alternative implementation using requests + BeautifulSoup
class SimpleURLCrawler:
    """Alternative simple implementation using requests + BeautifulSoup"""
    
    def __init__(self, max_depth: int = 2, delay: float = 1.0, max_urls: int = 1000):
        self.max_depth = max_depth
        self.delay = delay
        self.max_urls = max_urls
        
    def discover_urls(self, url: str) -> List[str]:
        """
        Simple URL discovery using requests + BeautifulSoup
        
        Args:
            url: Target URL to crawl
            
        Returns:
            List of discovered URLs
        """
        import requests
        from bs4 import BeautifulSoup
        from urllib.parse import urljoin, urlparse
        import time
        
        # Add protocol if missing
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url
        
        # Parse domain
        parsed = urlparse(url)
        domain = parsed.netloc
        base_domain = domain.replace('www.', '') if domain.startswith('www.') else domain
        allowed_domains = {domain, f"www.{base_domain}", base_domain}
        
        discovered_urls = set()
        to_crawl = [(url, 0)]  # (url, depth)
        crawled = set()
        
        session = requests.Session()
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        })
        
        while to_crawl and len(discovered_urls) < self.max_urls:
            current_url, depth = to_crawl.pop(0)
            
            if current_url in crawled or depth > self.max_depth:
                continue
            
            try:
                print(f"Crawling: {current_url} (depth: {depth})")
                response = session.get(current_url, timeout=30)
                response.raise_for_status()
                
                crawled.add(current_url)
                discovered_urls.add(current_url)
                
                if 'text/html' in response.headers.get('content-type', ''):
                    soup = BeautifulSoup(response.content, 'html.parser')
                    
                    for link in soup.find_all('a', href=True):
                        href = link['href']
                        full_url = urljoin(current_url, href)
                        parsed_link = urlparse(full_url)
                        
                        if (parsed_link.netloc in allowed_domains and 
                            full_url not in crawled and 
                            not any(full_url.endswith(ext) for ext in ['.pdf', '.jpg', '.png', '.gif', '.css', '.js'])):
                            
                            to_crawl.append((full_url, depth + 1))
                
                time.sleep(self.delay)
                
            except Exception as e:
                print(f"Error crawling {current_url}: {e}")
                continue
        
        return sorted(list(discovered_urls))


# Example usage and testing
if __name__ == "__main__":
    # Set multiprocessing start method for compatibility
    if __name__ == "__main__":
        multiprocessing.set_start_method('spawn', force=True)
    
    print("URL Crawler Test")
    print("=" * 50)
    
    # Choose crawler type
    use_simple = len(sys.argv) > 1 and sys.argv[1] == '--simple'
    
    if use_simple:
        print("Using Simple Crawler (requests + BeautifulSoup)")
        crawler = SimpleURLCrawler(max_depth=2, delay=1.0, max_urls=50)
    else:
        print("Using Scrapy Crawler with Enhanced Discovery")
        crawler = URLCrawler(
            max_depth=3,  # Increased depth
            max_pages=200,  # Reasonable limit
            delay=1.0,
            concurrent_requests=4,
            respect_robots=True,
            include_sitemaps=True  # Enable sitemap discovery
        )
    
    # Test with multiple websites
    test_urls = [
        "https://www.marcusmillichap.com/"
    ]
    
    for test_url in test_urls:
        try:
            print(f"\nTesting with: {test_url}")
            print("-" * 30)
            urls = crawler.discover_urls(test_url)
            
            if urls:
                print(f"✓ Discovered {len(urls)} URLs:")
                for i, url in enumerate(urls[:13], 1):
                    print(f"  {i:2d}. {url}")
                
                if len(urls) > 10:
                    print(f"  ... and {len(urls) - 10} more")
                break  # Stop after first successful crawl
            else:
                print("✗ No URLs discovered")
                
        except Exception as e:
            print(f"✗ Error with {test_url}: {e}")
            continue
    
    else:
        print("\n❌ All test URLs failed. This might indicate:")
        print("1. Network connectivity issues")  
        print("2. All test sites are blocking requests")
        print("3. Configuration issues with the crawler")
        print("\nTry running with --simple flag:")
        print("python filename.py --simple")