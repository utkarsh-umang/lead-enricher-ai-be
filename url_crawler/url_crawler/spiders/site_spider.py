import scrapy
from scrapy.linkextractors import LinkExtractor
from scrapy.spiders import CrawlSpider, Rule
import logging

class SiteSpider(CrawlSpider):
    name = 'site_spider'
    allowed_domains = ['barrerascpa.com']
    start_urls = ['https://barrerascpa.com']

    # Custom settings for this spider
    # custom_settings = {
    #     'DOWNLOAD_DELAY': 2,
    #     'CONCURRENT_REQUESTS_PER_DOMAIN': 1,
    #     'RETRY_TIMES': 5,
    #     'DOWNLOAD_TIMEOUT': 30,
    # }

    rules = (
        Rule(LinkExtractor(
            allow_domains=['barrerascpa.com'],
            deny_extensions=None,  # Use default extensions to deny
            # Only follow HTML pages
            allow=(r'.*',),
            # Deny common non-HTML resources
            deny=(r'.*\.(css|js|json|xml|ico|png|jpg|jpeg|gif|pdf|doc|docx|zip|rar)$',),
        ), callback='parse_item', follow=True),
    )

    def start_requests(self):
        """Override start_requests to add custom headers and error handling"""
        for url in self.start_urls:
            yield scrapy.Request(
                url=url,
                errback=self.handle_error,
                meta={'dont_redirect': False, 'handle_httpstatus_list': [404, 403, 500]},
                headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.5',
                    'Accept-Encoding': 'gzip, deflate',
                    'Connection': 'keep-alive',
                }
            )

    def parse_item(self, response):
        """Parse each page and extract information"""
        # Log successful page crawl
        self.logger.info(f'Successfully crawled: {response.url}')
        
        # # Extract title (handle cases where title might not exist)
        # title = response.css('title::text').get()
        # if title:
        #     title = title.strip()
        
        # # Extract meta description
        # description = response.css('meta[name="description"]::attr(content)').get()
        # if description:
        #     description = description.strip()
        
        yield {
            'url': response.url,
            # 'status_code': response.status,
            # 'title': title or 'No title',
            # 'description': description or 'No description',
            # 'page_size': len(response.body),
        }

    def handle_error(self, failure):
        """Handle request failures"""
        self.logger.error(f'Request failed: {failure.request.url} - {failure.value}')
        
        # You could yield an item with error info if needed
        yield {
            'url': failure.request.url,
            # 'status_code': 'ERROR',
            # 'title': f'Error: {failure.value}',
            # 'description': 'Failed to crawl',
            # 'page_size': 0,
        }