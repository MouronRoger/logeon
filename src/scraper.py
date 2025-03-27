import asyncio
import logging
from bs4 import BeautifulSoup
from urllib.parse import urljoin, unquote
import time
from typing import Dict, List, Optional
from pathlib import Path
import re
from database import Database
from playwright.async_api import async_playwright, Browser, Page

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

class LogeionScraper:
    def __init__(self, base_url: str = "https://logeion.uchicago.edu/"):
        self.base_url = base_url
        self.db = Database()
        self.browser: Optional[Browser] = None
        self.page: Optional[Page] = None

    async def __aenter__(self):
        playwright = await async_playwright().start()
        self.browser = await playwright.chromium.launch(headless=True)
        self.page = await self.browser.new_page()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.browser:
            await self.browser.close()

    def extract_lemma_from_url(self, url: str) -> str:
        """Extract and decode the Greek lemma from the URL."""
        path = url.split('/')[-1]
        return unquote(path)

    async def get_page_content(self, url: str) -> Optional[str]:
        """Fetch page content with retry logic and rate limiting."""
        if not self.page:
            raise RuntimeError("Browser not initialized. Use async with LogeionScraper().")

        max_retries = 3
        retry_delay = 1.2  # Base delay in seconds

        for attempt in range(max_retries):
            try:
                await asyncio.sleep(retry_delay * (attempt + 1))
                await self.page.goto(url, wait_until='networkidle')
                # Wait for Angular to finish rendering
                await self.page.wait_for_selector('.dictionary-entry', timeout=10000)
                return await self.page.content()
            except Exception as e:
                logging.error(f"Error fetching {url}: {str(e)}")
                if attempt == max_retries - 1:
                    return None
                retry_delay *= 2

        return None

    async def parse_lexicon_entry(self, html: str, url: str) -> List[Dict]:
        """Parse all lexicon entries from a page."""
        soup = BeautifulSoup(html, 'lxml')
        entries = []
        lemma = self.extract_lemma_from_url(url)

        # Find all dictionary entries
        for entry_div in soup.find_all('div', class_='dictionary-entry'):
            source = None
            definition = None

            # Get the dictionary source
            source_elem = entry_div.find(['h2', 'h3', 'h4', 'div'], class_='dictionary-name')
            if source_elem:
                source = source_elem.get_text(strip=True)
            else:
                continue

            # Get the definition
            definition_elem = entry_div.find('div', class_='definition')
            if definition_elem:
                definition = definition_elem.get_text(strip=True)
                raw_html = str(definition_elem)

                entries.append({
                    'lemma': lemma,
                    'lexicon_source': source,
                    'definition': definition,
                    'url': url,
                    'raw_html': raw_html
                })

        return entries

    async def discover_lemmas(self, start_url: str) -> List[str]:
        """Discover new lemma pages from an index or search page."""
        content = await self.get_page_content(start_url)
        if not content:
            return []

        soup = BeautifulSoup(content, 'lxml')
        lemma_links = []

        # Find all Greek word links
        for link in soup.find_all('a', href=True):
            href = link['href']
            # Match Greek Unicode ranges and common URL patterns
            if re.search(r'[Α-Ωα-ωἀ-ᾯ]', unquote(href)) and not href.startswith(('http://', 'https://', 'mailto:')):
                full_url = urljoin(self.base_url, href)
                if full_url not in lemma_links:
                    lemma_links.append(full_url)

        return lemma_links

    async def scrape_lemma_page(self, url: str) -> bool:
        """Scrape a single lemma page."""
        try:
            content = await self.get_page_content(url)
            if not content:
                self.db.update_url_status(url, 'error', 'Failed to fetch content')
                return False

            entries = await self.parse_lexicon_entry(content, url)
            if not entries:
                self.db.update_url_status(url, 'error', 'No entries found')
                return False

            for entry in entries:
                self.db.add_lexicon_entry(entry)

            self.db.update_url_status(url, 'completed')
            return True

        except Exception as e:
            logging.error(f"Error processing {url}: {str(e)}")
            self.db.update_url_status(url, 'error', str(e))
            return False

    async def run(self, concurrent_tasks: int = 3):
        """Main scraping loop."""
        async with self:  # Initialize browser
            while True:
                url = self.db.get_next_url()
                if not url:
                    break

                await self.scrape_lemma_page(url)
                progress = self.db.get_progress()
                logging.info(f"Progress: {progress['completed']}/{progress['total']} "
                           f"(Failed: {progress['failed']})")

async def main():
    scraper = LogeionScraper()
    
    # Add initial URLs to queue
    start_url = "https://logeion.uchicago.edu/α"
    async with scraper:
        lemma_urls = await scraper.discover_lemmas(start_url)
        for url in lemma_urls:
            scraper.db.add_to_queue(url)

    # Start scraping
    await scraper.run()

if __name__ == "__main__":
    asyncio.run(main()) 