import asyncio
import aiohttp
import json
import logging
import os
from bs4 import BeautifulSoup
from urllib.parse import urljoin, unquote, quote
import time
from typing import Dict, List, Optional, Set, Tuple
from pathlib import Path
import re
from database import Database

# Configuration
API_KEY = os.getenv("LOGEION_API_KEY", "AIzaSyCT5aVzk3Yx-m8FH8rmTpEgfVyVA3pYbqg")  # Default to public key if env not set
CONCURRENCY = 3  # Max concurrent requests
REQUEST_DELAY = 1.2  # Seconds between requests
MAX_RETRIES = 3  # Maximum retry attempts for failed requests

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

# Common Greek lemmas for each letter
COMMON_GREEK_LEMMAS = {
    'α': ['ἀγαθός', 'ἄγω', 'ἀνήρ', 'ἄνθρωπος', 'ἀρχή'],
    'β': ['βαίνω', 'βάλλω', 'βασιλεύς', 'βίος', 'βούλομαι'],
    'γ': ['γῆ', 'γίγνομαι', 'γιγνώσκω', 'γράφω', 'γυνή'],
    'δ': ['δεῖ', 'δέχομαι', 'δῆμος', 'διά', 'δίδωμι'],
    'ε': ['ἐγώ', 'εἰμί', 'εἶπον', 'ἔρχομαι', 'ἔχω'],
    'ζ': ['ζάω', 'ζεύς', 'ζητέω', 'ζωή', 'ζῷον'],
    'η': ['ἡγέομαι', 'ἥκω', 'ἡμέρα', 'ἥρως', 'ἡσυχία'],
    'θ': ['θάλασσα', 'θάνατος', 'θεός', 'θυμός', 'θύω'],
    'ι': ['ἰδεῖν', 'ἱερός', 'ἵημι', 'ἵππος', 'ἴσος'],
    'κ': ['καί', 'καλέω', 'καλός', 'κατά', 'κεῖμαι'],
    'λ': ['λαμβάνω', 'λέγω', 'λείπω', 'λόγος', 'λύω'],
    'μ': ['μάχη', 'μέγας', 'μένω', 'μή', 'μόνος'],
    'ν': ['ναῦς', 'νέος', 'νῆσος', 'νικάω', 'νόμος'],
    'ξ': ['ξένος', 'ξίφος', 'ξύλον', 'ξυνός', 'ξύν'],
    'ο': ['ὁδός', 'οἶδα', 'οἶκος', 'ὄνομα', 'ὁράω'],
    'π': ['παῖς', 'πᾶς', 'πατήρ', 'πόλις', 'πρός'],
    'ρ': ['ῥέω', 'ῥήτωρ', 'ῥίπτω', 'ῥώμη', 'ῥώννυμι'],
    'σ': ['σοφία', 'σοφός', 'στρατός', 'σύ', 'σῶμα'],
    'τ': ['τάσσω', 'τε', 'τίθημι', 'τις', 'τόπος'],
    'υ': ['ὕδωρ', 'υἱός', 'ὕπνος', 'ὑπό', 'ὕστερος'],
    'φ': ['φαίνω', 'φέρω', 'φημί', 'φίλος', 'φύσις'],
    'χ': ['χαίρω', 'χείρ', 'χρή', 'χρόνος', 'χώρα'],
    'ψ': ['ψεύδω', 'ψηφίζομαι', 'ψυχή', 'ψύχω', 'ψαύω'],
    'ω': ['ὦ', 'ὧδε', 'ὥρα', 'ὡς', 'ὠφελέω']
}

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class LogeionScraper:
    def __init__(self, delay: float = REQUEST_DELAY):
        self.delay = delay
        self.last_request_time = 0
        self.api_key = API_KEY
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
        """Make API request with retries and error handling"""
        for attempt in range(MAX_RETRIES):
            try:
                async with session.get(url) as response:
                    if response.status != 200:
                        logger.error(f"Request failed: {url} (Status: {response.status})")
                        await asyncio.sleep(self.delay * (attempt + 1))
                        continue
                    return await response.json()
            except (aiohttp.ClientError, json.JSONDecodeError) as e:
                logger.error(f"Request error: {url} ({str(e)})")
                if attempt == MAX_RETRIES - 1:
                    return None
                await asyncio.sleep(self.delay * (attempt + 1))
        return None

    async def get_lexicon_entry(self, lemma: str) -> Optional[Dict]:
        """Fetch complete lexicon entry for a lemma, including language and definitions"""
        await self._wait_for_delay()
        
        # Check if we already have this entry
        existing_entry = await self.db.get_lexicon_entry(lemma)
        if existing_entry:
            return existing_entry
            
        encoded_lemma = quote(lemma)
        async with aiohttp.ClientSession() as session:
            # Check language first
            lang_url = f"{self.base_url}/checkLang/?key={self.api_key}&text={encoded_lemma}"
            lang_data = await self._make_request(session, lang_url)
            if not lang_data:
                return None
                
            # Get detailed entry data
            detail_url = f"{self.base_url}/detail?key={self.api_key}&type=normal&w={encoded_lemma}"
            detail_data = await self._make_request(session, detail_url)
            if not detail_data:
                return None
            
            entry = {
                'lemma': lemma,
                'language': lang_data.get('lang'),
                'details': detail_data.get('detail', {}),
                'source': 'LSJ'  # Default for Greek entries
            }
            
            # Store in database
            await self.db.add_lexicon_entry(entry)
            return entry

    async def process_letter(self, letter: str) -> Tuple[int, int]:
        """Process all lemmas for a given letter"""
        lemmas = await self.discover_lemmas(letter)
        total = len(lemmas)
        completed = 0
        
        async def process_lemma(lemma: str):
            entry = await self.get_lexicon_entry(lemma)
            if entry:
                nonlocal completed
                completed += 1
                if completed % 10 == 0:  # Progress update every 10 entries
                    logger.info(f"Letter {letter}: {completed}/{total} lemmas processed")
            
        # Process lemmas concurrently with rate limiting
        tasks = []
        for lemma in lemmas:
            if len(tasks) >= CONCURRENCY:
                await asyncio.gather(*tasks)
                tasks = []
            tasks.append(process_lemma(lemma))
        
        if tasks:
            await asyncio.gather(*tasks)
            
        return total, completed

    async def run_scraper(self, letters: List[str] = None):
        """Main scraping orchestration"""
        if not letters:
            letters = list(GREEK_LETTERS.keys())
            
        total_processed = 0
        total_lemmas = 0
        
        for letter in letters:
            logger.info(f"Starting letter: {letter}")
            total, completed = await self.process_letter(letter)
            total_lemmas += total
            total_processed += completed
            
            # Log progress after each letter
            progress = await self.db.get_progress()
            logger.info(
                f"Progress: {progress['completed']} completed | "
                f"{progress['pending']} pending | "
                f"{progress['failed']} failed | "
                f"{progress['processing']} processing"
            )
            
        return total_processed, total_lemmas

    async def resume_scraping(self):
        """Resume scraping from last point"""
        while True:
            next_url = await self.db.get_next_url()
            if not next_url:
                break
                
            url, retry_count = next_url
            try:
                # Process URL
                entry = await self._process_url(url)
                if entry:
                    await self.db.mark_url_completed(url)
                else:
                    await self.db.mark_url_failed(url, "Failed to process URL")
            except Exception as e:
                await self.db.mark_url_failed(url, str(e))
            
            # Log progress periodically
            if retry_count % 10 == 0:
                progress = await self.db.get_progress()
                logger.info(
                    f"Progress: {progress['completed']} completed | "
                    f"{progress['pending']} pending | "
                    f"{progress['failed']} failed"
                )

    async def export_results(self, output_path: str = "lexicon_export.json"):
        """Export all scraped entries to JSON"""
        success = await self.db.export_to_json(output_path)
        if success:
            logger.info(f"Successfully exported data to {output_path}")
        else:
            logger.error("Failed to export data")

    async def retry_failed(self):
        """Retry all failed URLs"""
        reset_count = await self.db.reset_failed()
        if reset_count > 0:
            logger.info(f"Reset {reset_count} failed URLs for retry")
            await self.resume_scraping()
        else:
            logger.info("No failed URLs to retry")

    async def discover_lemmas(self, letter: str) -> Set[str]:
        """Find all available lemmas starting with given letter using common lemmas as seed"""
        letter = letter.lower()
        if letter not in COMMON_GREEK_LEMMAS:
            logger.warning(f"No common lemmas found for letter '{letter}'")
            return set()
        
        lemmas = set(COMMON_GREEK_LEMMAS[letter])
        logger.info(f"Starting with {len(lemmas)} common lemmas for letter '{letter}'")
        
        async with aiohttp.ClientSession() as session:
            tasks = []
            for lemma in list(lemmas):
                if len(tasks) >= CONCURRENCY:
                    await asyncio.gather(*tasks)
                    tasks = []
                tasks.append(self._process_lemma(session, lemma, letter, lemmas))
            
            if tasks:
                await asyncio.gather(*tasks)
        
        logger.info(f"Found {len(lemmas)} total lemmas for letter '{letter}'")
        return lemmas

    async def _process_lemma(self, session: aiohttp.ClientSession, lemma: str, letter: str, lemmas: Set[str]):
        """Helper for discover_lemmas to process a single lemma and find related ones"""
        await self._wait_for_delay()
        
        # Verify it's a Greek lemma
        lang_url = f"{self.base_url}/checkLang/?key={self.api_key}&text={quote(lemma)}"
        lang_data = await self._make_request(session, lang_url)
        if not lang_data or lang_data.get('lang') != 'greek':
            return
        
        # Find related lemmas
        find_url = f"{self.base_url}/find?key={self.api_key}&w={quote(lemma)}"
        find_data = await self._make_request(session, find_url)
        if find_data and 'parses' in find_data:
            for parse in find_data['parses']:
                if 'lemma' in parse:
                    new_lemma = parse['lemma']
                    if new_lemma.lower().startswith(letter):
                        lemmas.add(new_lemma)

    async def get_corpus_site(self, lemma: str) -> Optional[str]:
        """Get reference corpus URL for a lemma"""
        await self._wait_for_delay()
        
        encoded_lemma = quote(lemma)
        async with aiohttp.ClientSession() as session:
            url = f"{self.base_url}/getCorpusSite?displayed={encoded_lemma}&key={self.api_key}"
            data = await self._make_request(session, url)
            return data.get('lemmaSite') if data else None

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

    async def run(self, concurrent_tasks: int = CONCURRENCY):
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