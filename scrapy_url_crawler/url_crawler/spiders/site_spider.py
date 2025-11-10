import scrapy
from scrapy.linkextractors import LinkExtractor
from scrapy.spiders import CrawlSpider, Rule
import logging
from urllib.parse import urlparse

class SiteSpider(CrawlSpider):
    name = 'site_spider'
    start_urls = []

    def __init__(self, start_url=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if start_url:
            self.start_urls = [start_url]
            parsed = urlparse(start_url)
            domain = parsed.netloc
            self.allowed_domains = [domain, domain.replace('www.', '')] if domain.startswith('www.') else [domain, f'www.{domain}']
            self.logger.info(f"Set allowed_domains to {self.allowed_domains} for start_url {start_url}")

    rules = (
        Rule(LinkExtractor(
            deny_extensions=None,
            allow=(r'.*',),
            deny=(r'.*\.(css|js|json|xml|ico|png|jpg|jpeg|gif|pdf|doc|docx|zip|rar)$',),
        ), callback='parse_item', follow=True),
    )

    def start_requests(self):
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
        self.logger.info(f'Successfully crawled: {response.url}')
        yield {
            'url': response.url,
        }

    def handle_error(self, failure):
        self.logger.error(f'Request failed: {failure.request.url} - {failure.value}')
        yield {
            'url': failure.request.url,
        }