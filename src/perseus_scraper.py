import asyncio
import json
import logging
import os
import time
from typing import Dict, List, Optional, Set, Tuple
from pathlib import Path
from urllib.parse import quote, urljoin

from playwright.async_api import async_playwright, Page
from src.database import Database

# Configuration
CONCURRENCY = 3  # Max concurrent requests
REQUEST_DELAY = 1.2  # Seconds between requests
MAX_RETRIES = 3  # Maximum retry attempts for failed requests

# Set up logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Base URLs
BASE_URL = "https://www.perseus.tufts.edu/hopper"
LEXICON_URL = "https://www.perseus.tufts.edu/hopper/text?doc=Perseus:text:1999.04.0057"

class PerseusScraper:
    def __init__(self, delay: float = REQUEST_DELAY):
        self.delay = delay
        self.last_request_time = 0
        self.db = Database("perseus.sqlite")
        self.playwright = None
        self.browser = None
        self.context = None

    async def __aenter__(self):
        """Set up Playwright browser"""
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(headless=False)
        self.context = await self.browser.new_context()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Clean up Playwright resources"""
        if self.context:
            await self.context.close()
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()

    async def _wait_for_delay(self):
        """Ensure we respect the delay between requests."""
        now = time.time()
        time_since_last = now - self.last_request_time
        if time_since_last < self.delay:
            await asyncio.sleep(self.delay - time_since_last)
        self.last_request_time = time.time()

    async def scrape_letter_groups(self) -> List[Dict]:
        """Scrape the letter groups from the main lexicon page"""
        await self._wait_for_delay()
        
        page = await self.context.new_page()
        try:
            await page.goto(LEXICON_URL, wait_until='networkidle')
            
            # Get all the letter group links
            letter_groups = []
            
            # Find all links to letter groups
            elements = await page.query_selector_all('div.entry_group a')
            for element in elements:
                text = await element.text_content()
                href = await element.get_attribute('href')
                
                if href and text:
                    letter_groups.append({
                        'text': text.strip(),
                        'url': urljoin(BASE_URL, href)
                    })
            
            return letter_groups
        finally:
            await page.close()

    async def scrape_letter_entries(self, letter_group_url: str) -> List[Dict]:
        """Scrape all the entries for a given letter group"""
        await self._wait_for_delay()
        
        page = await self.context.new_page()
        try:
            await page.goto(letter_group_url, wait_until='networkidle')
            
            # Get all the entry links
            entries = []
            
            elements = await page.query_selector_all('div.entry_list a')
            for element in elements:
                text = await element.text_content()
                href = await element.get_attribute('href')
                
                if href and text:
                    entries.append({
                        'text': text.strip(),
                        'url': urljoin(BASE_URL, href)
                    })
            
            return entries
        finally:
            await page.close()

    async def scrape_entry_content(self, entry_url: str) -> Optional[Dict]:
        """Scrape the content of a dictionary entry"""
        await self._wait_for_delay()
        
        page = await self.context.new_page()
        try:
            await page.goto(entry_url, wait_until='networkidle')
            
            # Extract the entry header
            header_element = await page.query_selector('#lexicon_header')
            header = await header_element.text_content() if header_element else ""
            
            # Extract the main content
            content_element = await page.query_selector('#lexicon_content')
            content_html = await content_element.inner_html() if content_element else ""
            content_text = await content_element.text_content() if content_element else ""
            
            if content_html:
                return {
                    'header': header.strip(),
                    'content_html': content_html,
                    'content_text': content_text.strip(),
                    'url': entry_url
                }
            
            return None
        except Exception as e:
            logger.error(f"Error scraping entry {entry_url}: {str(e)}")
            return None
        finally:
            await page.close()

    async def extract_dictionary_structure(self):
        """Extract the overall structure of the dictionary"""
        letter_groups = await self.scrape_letter_groups()
        
        dictionary_structure = {}
        
        for letter_group in letter_groups[:3]:  # Limit to first 3 for testing
            logger.info(f"Processing letter group: {letter_group['text']}")
            entries = await self.scrape_letter_entries(letter_group['url'])
            
            dictionary_structure[letter_group['text']] = {
                'url': letter_group['url'],
                'entries': entries
            }
            
            # Store in database
            self.db.store_entry(letter_group['text'], {
                'url': letter_group['url'],
                'entries': entries
            })
        
        return dictionary_structure

    async def run_scraper(self, max_entries_per_letter: int = 5):
        """Run the scraper to extract the dictionary content"""
        letter_groups = await self.scrape_letter_groups()
        
        for letter_group in letter_groups:
            logger.info(f"Processing letter group: {letter_group['text']}")
            entries = await self.scrape_letter_entries(letter_group['url'])
            
            # Limit the number of entries to scrape
            entries_to_process = entries[:max_entries_per_letter]
            
            for entry in entries_to_process:
                logger.info(f"Scraping entry: {entry['text']}")
                entry_content = await self.scrape_entry_content(entry['url'])
                
                if entry_content:
                    # Store entry in database
                    self.db.store_entry(entry['text'], entry_content)

    async def export_results(self, output_path: str = "perseus_lexicon_export.json"):
        """Export the scraped data to a JSON file"""
        entries = self.db.get_all_entries()
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(entries, f, ensure_ascii=False, indent=2)
            
        logger.info(f"Exported {len(entries)} entries to {output_path}")

async def main():
    """Main entry point"""
    async with PerseusScraper() as scraper:
        # First, explore the structure
        structure = await scraper.extract_dictionary_structure()
        print(f"Found {len(structure)} letter groups")
        
        # Then run the scraper for a limited number of entries
        await scraper.run_scraper(max_entries_per_letter=3)
        
        # Export the results
        await scraper.export_results()

if __name__ == "__main__":
    asyncio.run(main()) 