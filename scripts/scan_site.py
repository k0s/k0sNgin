#!/usr/bin/env python3
"""
Simple site scanner for k0sNgin deployment verification.
Scans a website to verify:
- API docs are disabled (/docs, /redoc, /openapi.json)
- Lists all accessible files/endpoints
- Checks rate limiting behavior
"""

import sys
import argparse
import requests
from urllib.parse import urljoin, urlparse
from collections import deque, defaultdict
import time

class SiteScanner:
    def __init__(self, base_url, max_depth=5, delay=0.1):
        self.base_url = base_url.rstrip('/')
        self.max_depth = max_depth
        self.delay = delay
        self.visited = set()
        self.to_visit = deque([(self.base_url, 0)])
        self.results = defaultdict(list)
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'k0sNgin-SiteScanner/1.0'
        })

    def scan(self):
        """Main scanning loop"""
        print(f"Scanning {self.base_url}...")
        print("=" * 60)

        # First, check critical security endpoints
        self.check_security_endpoints()

        # Then crawl the site
        while self.to_visit:
            url, depth = self.to_visit.popleft()

            if depth > self.max_depth:
                continue

            if url in self.visited:
                continue

            self.visited.add(url)
            self.check_url(url, depth)
            time.sleep(self.delay)

        self.print_results()

    def check_security_endpoints(self):
        """Check that API docs are disabled"""
        print("\n🔒 Checking Security Endpoints:")
        print("-" * 60)

        security_endpoints = [
            '/docs',
            '/redoc',
            '/openapi.json',
            '/openapi.yaml',
            '/api/docs',
            '/swagger',
        ]

        for endpoint in security_endpoints:
            url = urljoin(self.base_url, endpoint)
            try:
                response = self.session.get(url, timeout=5, allow_redirects=False)
                status = response.status_code

                if status == 200:
                    print(f"⚠️  {endpoint}: {status} (SHOULD BE DISABLED!)")
                    self.results['security_issues'].append(f"{endpoint} returns 200")
                elif status == 404:
                    print(f"✅ {endpoint}: {status} (correctly disabled)")
                else:
                    print(f"ℹ️  {endpoint}: {status}")

            except requests.RequestException as e:
                print(f"❌ {endpoint}: Error - {e}")

    def check_url(self, url, depth):
        """Check a single URL and extract links"""
        try:
            response = self.session.get(url, timeout=10, allow_redirects=True)
            status = response.status_code

            # Categorize the response
            if status == 200:
                content_type = response.headers.get('Content-Type', '')
                if 'text/html' in content_type:
                    self.results['html_pages'].append(url)
                    # Extract links from HTML
                    if depth < self.max_depth:
                        self.extract_links(url, response.text)
                elif 'application/json' in content_type:
                    self.results['json_files'].append(url)
                else:
                    self.results['other_files'].append((url, content_type))
            elif status == 404:
                self.results['not_found'].append(url)
            elif status == 429:
                self.results['rate_limited'].append(url)
                print(f"⚠️  Rate limited at: {url}")
            else:
                self.results['other_status'].append((url, status))

        except requests.RequestException as e:
            self.results['errors'].append((url, str(e)))

    def extract_links(self, base_url, html):
        """Extract links from HTML (simple regex-based)"""
        import re
        from html.parser import HTMLParser

        class LinkExtractor(HTMLParser):
            def __init__(self):
                super().__init__()
                self.links = []

            def handle_starttag(self, tag, attrs):
                if tag == 'a':
                    for attr, value in attrs:
                        if attr == 'href' and value:
                            self.links.append(value)

        parser = LinkExtractor()
        try:
            parser.feed(html)
            for link in parser.links:
                absolute_url = urljoin(base_url, link)
                parsed = urlparse(absolute_url)
                # Only follow links from the same domain
                if parsed.netloc == urlparse(self.base_url).netloc:
                    if absolute_url not in self.visited:
                        self.to_visit.append((absolute_url, len(self.visited) + 1))
        except:
            pass

    def test_rate_limiting(self):
        """Test rate limiting by making rapid requests"""
        print("\n🚦 Testing Rate Limiting:")
        print("-" * 60)

        test_url = urljoin(self.base_url, '/')
        rate_limited = False
        request_count = 0

        for i in range(100):  # Try 100 rapid requests
            try:
                response = self.session.get(test_url, timeout=5)
                request_count += 1
                if response.status_code == 429:
                    rate_limited = True
                    print(f"✅ Rate limiting triggered after {request_count} requests")
                    break
                time.sleep(0.01)  # Very small delay
            except requests.RequestException:
                break

        if not rate_limited:
            print(f"⚠️  Rate limiting not triggered after {request_count} requests")
        else:
            print(f"Rate limit response: {response.status_code}")
            if 'Retry-After' in response.headers:
                print(f"Retry-After: {response.headers['Retry-After']} seconds")

    def print_results(self):
        """Print scan results summary"""
        print("\n" + "=" * 60)
        print("📊 Scan Results Summary:")
        print("=" * 60)

        print(f"\n✅ HTML Pages ({len(self.results['html_pages'])}):")
        for url in sorted(self.results['html_pages']):
            print(f"   {url}")

        print(f"\n📄 JSON Files ({len(self.results['json_files'])}):")
        for url in sorted(self.results['json_files']):
            print(f"   {url}")

        print(f"\n📁 Other Files ({len(self.results['other_files'])}):")
        for url, content_type in sorted(self.results['other_files']):
            print(f"   {url} ({content_type})")

        if self.results['rate_limited']:
            print(f"\n⚠️  Rate Limited URLs ({len(self.results['rate_limited'])}):")
            for url in self.results['rate_limited']:
                print(f"   {url}")

        if self.results['security_issues']:
            print(f"\n🚨 SECURITY ISSUES ({len(self.results['security_issues'])}):")
            for issue in self.results['security_issues']:
                print(f"   ⚠️  {issue}")

        if self.results['errors']:
            print(f"\n❌ Errors ({len(self.results['errors'])}):")
            for url, error in self.results['errors']:
                print(f"   {url}: {error}")

        print(f"\n📈 Total URLs scanned: {len(self.visited)}")


def main():
    parser = argparse.ArgumentParser(description='Scan k0sNgin site for security verification')
    parser.add_argument('url', help='Base URL to scan (e.g., http://cephalopod.ink)')
    parser.add_argument('--max-depth', type=int, default=5, help='Maximum crawl depth (default: 5)')
    parser.add_argument('--delay', type=float, default=0.1, help='Delay between requests in seconds (default: 0.1)')
    parser.add_argument('--test-rate-limit', action='store_true', help='Test rate limiting behavior')

    args = parser.parse_args()

    scanner = SiteScanner(args.url, max_depth=args.max_depth, delay=args.delay)
    scanner.scan()

    if args.test_rate_limit:
        scanner.test_rate_limiting()


if __name__ == '__main__':
    main()
