import requests
import socket
from urllib.parse import urlparse

def test_website_connectivity(url):
    """Test if a website is accessible"""
    print(f"Testing connectivity to: {url}")
    print("-" * 50)
    
    # Parse URL
    parsed = urlparse(url)
    domain = parsed.netloc
    
    # Test 1: DNS Resolution
    try:
        ip = socket.gethostbyname(domain)
        print(f"✓ DNS Resolution: {domain} -> {ip}")
    except socket.gaierror as e:
        print(f"✗ DNS Resolution failed: {e}")
        return False
    
    # Test 2: HTTP Request with different methods
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate',
        'Connection': 'keep-alive',
    }
    
    # Try HTTPS first, then HTTP
    test_urls = [url]
    if url.startswith('https://'):
        test_urls.append(url.replace('https://', 'http://'))
    elif url.startswith('http://'):
        test_urls.append(url.replace('http://', 'https://'))
    
    for test_url in test_urls:
        try:
            print(f"\nTesting: {test_url}")
            response = requests.get(test_url, headers=headers, timeout=10, allow_redirects=True)
            print(f"✓ HTTP Request successful: Status {response.status_code}")
            print(f"  Final URL: {response.url}")
            print(f"  Content-Type: {response.headers.get('content-type', 'Unknown')}")
            print(f"  Content-Length: {len(response.content)} bytes")
            
            # Check if it's HTML content
            if 'text/html' in response.headers.get('content-type', ''):
                print("✓ Received HTML content - good for scraping")
            
            return True
            
        except requests.exceptions.ConnectionError as e:
            print(f"✗ Connection Error: {e}")
        except requests.exceptions.Timeout as e:
            print(f"✗ Timeout Error: {e}")
        except requests.exceptions.RequestException as e:
            print(f"✗ Request Error: {e}")
    
    return False

# Test the target website
if __name__ == "__main__":
    target_url = "https://jenkinscpa.com"
    
    # Also test some alternative URLs in case there are redirects
    test_urls = [
        "https://jenkinscpa.com",
        "http://jenkinscpa.com",
        "https://www.jenkinscpa.com",
        "http://www.jenkinscpa.com"
    ]
    
    print("Website Connectivity Test")  
    print("=" * 50)
    
    for url in test_urls:
        success = test_website_connectivity(url)
        print("\n" + "=" * 50)
        if success:
            print(f"✓ SUCCESS: {url} is accessible")
            break
    else:
        print("✗ All attempts failed - website may be down or blocking requests")
        print("\nTroubleshooting suggestions:")
        print("1. Check if you can access the website in your browser")
        print("2. Try using a VPN if the site might be geo-blocked")
        print("3. The site might be temporarily down")
        print("4. Try a different website for testing")