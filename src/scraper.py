import asyncio
import aiohttp
import json
import logging
from bs4 import BeautifulSoup
from urllib.parse import urljoin, unquote, quote
import time
from typing import Dict, List, Optional, Set
from pathlib import Path
import re
from database import Database

# Greek letter mapping
GREEK_LETTERS = {
    'α': 'alpha',
    'β': 'beta',
    'γ': 'gamma',
    'δ': 'delta',
    'ε': 'epsilon',
    'ζ': 'zeta',
    'η': 'eta',
    'θ': 'theta',
    'ι': 'iota',
    'κ': 'kappa',
    'λ': 'lambda',
    'μ': 'mu',
    'ν': 'nu',
    'ξ': 'xi',
    'ο': 'omicron',
    'π': 'pi',
    'ρ': 'rho',
    'σ': 'sigma',
    'τ': 'tau',
    'υ': 'upsilon',
    'φ': 'phi',
    'χ': 'chi',
    'ψ': 'psi',
    'ω': 'omega'
}

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class LogeionScraper:
    def __init__(self, delay: float = 1.2):
        self.delay = delay
        self.last_request_time = 0
        self.api_key = "AIzaSyCT5aVzk3Yx-m8FH8rmTpEgfVyVA3pYbqg"  # This is a public API key from their website
        self.base_url = "https://anastrophe.uchicago.edu/logeion-api"
        self.db = Database()

    async def _wait_for_delay(self):
        """Ensure we respect the delay between requests."""
        now = time.time()
        time_since_last = now - self.last_request_time
        if time_since_last < self.delay:
            await asyncio.sleep(self.delay - time_since_last)
        self.last_request_time = time.time()

    async def _make_request(self, session: aiohttp.ClientSession, url: str) -> Optional[Dict]:
        """Make a request to the API with proper error handling."""
        try:
            async with session.get(url) as response:
                if response.status != 200:
                    logger.error(f"Request failed: {url} (Status: {response.status})")
                    return None
                return await response.json()
        except aiohttp.ClientError as e:
            logger.error(f"Request error: {url} ({str(e)})")
            return None
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error: {url} ({str(e)})")
            return None

    async def get_lexicon_entry(self, lemma: str) -> Optional[Dict]:
        """Fetch lexicon entry for a given lemma."""
        await self._wait_for_delay()
        
        encoded_lemma = quote(lemma)
        async with aiohttp.ClientSession() as session:
            # First check the language
            lang_url = f"{self.base_url}/checkLang/?key={self.api_key}&text={encoded_lemma}"
            lang_data = await self._make_request(session, lang_url)
            if not lang_data:
                return None
                
            # Get the detailed entry
            detail_url = f"{self.base_url}/detail?key={self.api_key}&type=normal&w={encoded_lemma}"
            detail_data = await self._make_request(session, detail_url)
            if not detail_data:
                return None
            
            return {
                'lemma': lemma,
                'language': lang_data.get('lang'),
                'details': detail_data.get('detail', {})
            }

    async def discover_lemmas(self, letter: str) -> Set[str]:
        """Discover lemmas starting with a given letter."""
        await self._wait_for_delay()
        
        # If it's a Greek letter, try both the letter itself and its name
        encoded_letter = quote(letter)
        letter_name = GREEK_LETTERS.get(letter.lower())
        
        async with aiohttp.ClientSession() as session:
            lemmas = set()
            
            # Try with the letter itself
            find_url = f"{self.base_url}/find?key={self.api_key}&w={encoded_letter}"
            find_data = await self._make_request(session, find_url)
            if find_data and 'parses' in find_data:
                for parse in find_data['parses']:
                    if 'lemma' in parse:
                        lemmas.add(parse['lemma'])
            
            # If we have a letter name, try that too
            if letter_name:
                find_url = f"{self.base_url}/find?key={self.api_key}&w={letter_name}"
                find_data = await self._make_request(session, find_url)
                if find_data and 'parses' in find_data:
                    for parse in find_data['parses']:
                        if 'lemma' in parse:
                            lemmas.add(parse['lemma'])
            
            logger.info(f"Found {len(lemmas)} lemmas for letter '{letter}'")
            return lemmas

    async def get_corpus_site(self, lemma: str) -> Optional[str]:
        """Get the corpus site URL for a lemma."""
        await self._wait_for_delay()
        
        encoded_lemma = quote(lemma)
        async with aiohttp.ClientSession() as session:
            url = f"{self.base_url}/getCorpusSite?displayed={encoded_lemma}&key={self.api_key}"
            data = await self._make_request(session, url)
            if not data:
                return None
            async with session.get(url) as response:
                if response.status != 200:
                    logger.error(f"Failed to get corpus site for {lemma}: {response.status}")
                    return None
                data = await response.json()
                return data.get('lemmaSite')

    async def get_page_content(self, url: str) -> Optional[str]:
        """Fetch page content with retry logic and rate limiting."""
        max_retries = 3
        retry_delay = 1.2  # Base delay in seconds

        for attempt in range(max_retries):
            try:
                await asyncio.sleep(retry_delay * (attempt + 1))
                async with aiohttp.ClientSession() as session:
                    async with session.get(url) as response:
                        if response.status != 200:
                            logger.error(f"Failed to fetch {url}: {response.status}")
                            return None
                        return await response.text()
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