import asyncio
import json
import logging
import os
import time
from typing import Dict, List, Optional, Set, Tuple
from pathlib import Path
from urllib.parse import quote, urljoin, urlparse, parse_qs

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
LSJ_URL = "https://www.perseus.tufts.edu/hopper/text?doc=Perseus:text:1999.04.0057"

class LSJScraper:
    def __init__(self, delay: float = REQUEST_DELAY):
        self.delay = delay
        self.last_request_time = 0
        self.db = Database("lsj.sqlite")
        self.playwright = None
        self.browser = None
        self.context = None

    async def __aenter__(self):
        """Set up Playwright browser"""
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch()
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

    async def scrape_alphabetic_letters(self) -> List[Dict]:
        """Scrape the alphabetic letters from the LSJ lexicon page"""
        await self._wait_for_delay()
        
        page = await self.context.new_page()
        try:
            await page.goto(LSJ_URL, wait_until='networkidle')
            
            # Get all the alphabetic letter links
            letters = []
            
            # Find all links to alphabetic letters
            elements = await page.query_selector_all('div.alphabetic_letter a')
            for element in elements:
                text = await element.text_content()
                href = await element.get_attribute('href')
                
                if href and text:
                    letters.append({
                        'letter': text.strip(),
                        'url': urljoin(BASE_URL, href)
                    })
            
            return letters
        finally:
            await page.close()

    async def scrape_entry_groups(self, letter_url: str) -> List[Dict]:
        """Scrape all the entry groups for a given letter"""
        await self._wait_for_delay()
        
        page = await self.context.new_page()
        try:
            await page.goto(letter_url, wait_until='networkidle')
            
            # Get all the entry group links
            groups = []
            
            elements = await page.query_selector_all('div.entry_group a')
            for element in elements:
                text = await element.text_content()
                href = await element.get_attribute('href')
                
                if href and text:
                    groups.append({
                        'group': text.strip(),
                        'url': urljoin(BASE_URL, href)
                    })
            
            return groups
        finally:
            await page.close()

    async def scrape_entry_definitions(self, group_url: str) -> Optional[List[Dict]]:
        """Scrape the definitions of entries in a group"""
        await self._wait_for_delay()
        
        page = await self.context.new_page()
        try:
            await page.goto(group_url, wait_until='networkidle')
            
            # Check if we're on a definition page
            definition_block = await page.query_selector('.text')
            
            if definition_block:
                entries = []
                
                # Get all <a> elements with named anchor links
                word_elements = await page.query_selector_all('.text a[name]')
                
                for word_element in word_elements:
                    name = await word_element.get_attribute('name')
                    
                    # Find the definition text that follows
                    # This is complex as the structure varies, so we'll grab the following elements
                    definition_text = ""
                    
                    # Try to find the most appropriate way to get the definition
                    # This might need refinement based on the actual HTML structure
                    current_element = word_element
                    next_word = False
                    
                    # Navigate through sibling elements until we reach the next word
                    while current_element and not next_word:
                        next_element = await current_element.evaluate_handle('el => el.nextSibling')
                        if next_element:
                            element_name = await next_element.evaluate('el => el.nodeName')
                            if element_name == "A" and await next_element.evaluate('el => el.hasAttribute("name")'):
                                next_word = True
                            else:
                                element_text = await next_element.evaluate('el => el.textContent || ""')
                                definition_text += element_text
                        
                        current_element = next_element
                    
                    if name:
                        entries.append({
                            'word': name,
                            'definition': definition_text.strip(),
                            'url': f"{group_url}#{name}"
                        })
                
                return entries
            
            # If not a definition page, look for links to individual definitions
            definition_links = await page.query_selector_all('a[href^="#"]')
            definitions = []
            
            for link in definition_links:
                text = await link.text_content()
                href = await link.get_attribute('href')
                
                if href and text and href.startswith('#'):
                    definitions.append({
                        'word': text.strip(),
                        'url': f"{group_url}{href}"
                    })
            
            return definitions
        except Exception as e:
            logger.error(f"Error scraping definitions from {group_url}: {str(e)}")
            return None
        finally:
            await page.close()
            
    async def extract_page_content(self, url: str) -> Dict:
        """Extract the full HTML and text content of a page"""
        await self._wait_for_delay()
        
        page = await self.context.new_page()
        try:
            await page.goto(url, wait_until='networkidle')
            
            # Get the main text content
            text_element = await page.query_selector('.text')
            
            if text_element:
                content_html = await text_element.inner_html()
                content_text = await text_element.text_content()
                
                return {
                    'url': url,
                    'html': content_html,
                    'text': content_text.strip()
                }
            
            return {
                'url': url,
                'html': '',
                'text': ''
            }
        finally:
            await page.close()

    async def run_full_crawl(self, limit_letters: int = None, limit_groups: int = None, limit_entries: int = None):
        """Run a full crawl of the LSJ lexicon"""
        # Get all alphabetic letters
        letters = await self.scrape_alphabetic_letters()
        logger.info(f"Found {len(letters)} alphabetic letters")
        
        if limit_letters:
            letters = letters[:limit_letters]
        
        for letter_info in letters:
            letter = letter_info['letter']
            letter_url = letter_info['url']
            
            logger.info(f"Processing letter: {letter}")
            
            # Get all entry groups for this letter
            groups = await self.scrape_entry_groups(letter_url)
            logger.info(f"Found {len(groups)} entry groups for letter {letter}")
            
            if limit_groups:
                groups = groups[:limit_groups]
            
            for group_info in groups:
                group = group_info['group']
                group_url = group_info['url']
                
                logger.info(f"Processing group: {group}")
                
                # Store the full page content
                page_content = await self.extract_page_content(group_url)
                
                # Use a safe key for database storage (group might contain characters not suitable for keys)
                parsed_url = urlparse(group_url)
                query_params = parse_qs(parsed_url.query)
                group_key = f"{letter}_{group}"
                
                if 'doc' in query_params:
                    group_key = query_params['doc'][0]
                    
                self.db.store_entry(group_key, {
                    'letter': letter,
                    'group': group,
                    'url': group_url,
                    'content': page_content
                })
    
    async def export_results(self, output_path: str = "lsj_lexicon_export.json"):
        """Export the scraped data to a JSON file"""
        entries = self.db.get_all_entries()
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(entries, f, ensure_ascii=False, indent=2)
            
        logger.info(f"Exported {len(entries)} entries to {output_path}")

async def main():
    """Main entry point"""
    async with LSJScraper() as scraper:
        # Run a limited crawl for testing
        await scraper.run_full_crawl(limit_letters=2, limit_groups=3)
        
        # Export the results
        await scraper.export_results()

if __name__ == "__main__":
    asyncio.run(main()) 