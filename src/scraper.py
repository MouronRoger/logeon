import asyncio
import json
import logging
import os
from typing import Dict, List, Optional, Set, Tuple
from pathlib import Path
import unicodedata
from urllib.parse import quote
from playwright.async_api import async_playwright
from src.database import Database
import time

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
BASE_URL = "https://logeion.uchicago.edu"

def build_url(lemma: str) -> str:
    """Build URL with proper Unicode normalization and encoding"""
    lemma = unicodedata.normalize("NFC", lemma)
    encoded = quote(lemma)
    return f"{BASE_URL}/{encoded}"

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

class LogeionScraper:
    def __init__(self, delay: float = REQUEST_DELAY):
        self.delay = delay
        self.last_request_time = 0
        self.db = Database()
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

    async def _make_request(self, url: str) -> Optional[Dict]:
        """Make request with Playwright and handle dynamic content"""
        if not self.context:
            raise RuntimeError("Browser context not initialized. Use 'async with' to create scraper.")
            
        for attempt in range(MAX_RETRIES):
            try:
                page = await self.context.new_page()
                try:
                    # Navigate to the page and wait for network idle
                    await page.goto(url, wait_until='networkidle')
                    
                    # Wait for the dictionary entries to be visible
                    await page.wait_for_selector('.dictionary-entry', timeout=30000)
                    
                    # Wait a bit more for any additional content to load
                    await asyncio.sleep(1)
                    
                    # Get all dictionary entries
                    entries = []
                    dictionary_entries = await page.query_selector_all('.dictionary-entry')
                    
                    for entry in dictionary_entries:
                        source_elem = await entry.query_selector('.dictionary-name')
                        definition_elem = await entry.query_selector('.definition')
                        
                        if source_elem and definition_elem:
                            source = await source_elem.text_content()
                            definition = await definition_elem.text_content()
                            html_content = await definition_elem.inner_html()
                            
                            entries.append({
                                'source': source.strip(),
                                'definition': definition.strip(),
                                'html': html_content
                            })
                    
                    # Get related forms
                    related_forms = []
                    greek_links = await page.query_selector_all('a.greek[href^="/"]')
                    for link in greek_links:
                        text = await link.text_content()
                        if text:
                            related_forms.append(text.strip())
                    
                    if entries:
                        return {
                            'definitions': entries,
                            'related_forms': related_forms
                        }
                    else:
                        logger.warning(f"No definitions found for URL: {url}")
                        
                    return None
                    
                finally:
                    await page.close()
                    
            except Exception as e:
                logger.error(f"Request error: {url} ({str(e)})")
                if attempt == MAX_RETRIES - 1:
                    return None
                await asyncio.sleep(self.delay * (attempt + 1))
        return None

    async def get_lexicon_entry(self, lemma: str) -> Optional[Dict]:
        """Fetch complete lexicon entry for a lemma"""
        await self._wait_for_delay()
        
        # Check if we already have this entry
        existing_entry = self.db.get_entry(lemma)
        if existing_entry:
            return existing_entry

        url = build_url(lemma)
        entry_data = await self._make_request(url)
        
        if entry_data:
            # Store in database
            self.db.store_entry(lemma, entry_data)
            return entry_data
            
        return None

    async def process_letter(self, letter: str) -> Tuple[int, int]:
        """Process all lemmas for a given letter"""
        logger.info(f"Starting letter: {letter}")
        
        # Start with common lemmas for this letter
        lemmas = set(COMMON_GREEK_LEMMAS.get(letter, []))
        logger.info(f"Starting with {len(lemmas)} seed lemmas for letter '{letter}'")
        
        success_count = 0
        fail_count = 0
        
        async def process_lemma(lemma: str):
            nonlocal success_count, fail_count
            try:
                entry = await self.get_lexicon_entry(lemma)
                if entry:
                    success_count += 1
                    # Add any related forms to process
                    if 'related_forms' in entry:
                        for related in entry['related_forms']:
                            if related.startswith(letter):
                                lemmas.add(related)
                else:
                    fail_count += 1
                    self.db.add_failed_lemma(lemma)
            except Exception as e:
                logger.error(f"Error processing lemma {lemma}: {str(e)}")
                fail_count += 1
                self.db.add_failed_lemma(lemma)

        # Process lemmas concurrently with rate limiting
        tasks = []
        for lemma in lemmas:
            if len(tasks) >= CONCURRENCY:
                await asyncio.gather(*tasks)
                tasks = []
            tasks.append(process_lemma(lemma))
        
        if tasks:
            await asyncio.gather(*tasks)
            
        return success_count, fail_count

    async def run_scraper(self, letters: List[str] = None):
        """Run the scraper for specified letters or all letters"""
        if not letters:
            letters = list(GREEK_LETTERS.keys())
            
        total_success = 0
        total_fail = 0
        
        for letter in letters:
            success, fail = await self.process_letter(letter)
            total_success += success
            total_fail += fail
            
            logger.info(f"Letter {letter} complete. Success: {success}, Failed: {fail}")
            
        logger.info(f"Scraping complete. Total Success: {total_success}, Total Failed: {total_fail}")
        return total_success, total_fail

    async def auto_retry_failed_lemmas(self):
        """Automatically retry failed lemmas"""
        failed_lemmas = self.db.get_failed_lemmas()
        if not failed_lemmas:
            logger.info("No failed lemmas to retry")
            return 0, 0
            
        logger.info(f"Retrying {len(failed_lemmas)} failed lemmas")
        
        success_count = 0
        still_failed = 0
        
        async def retry_lemma(lemma: str):
            nonlocal success_count, still_failed
            try:
                entry = await self.get_lexicon_entry(lemma)
                if entry:
                    success_count += 1
                    self.db.remove_failed_lemma(lemma)
                else:
                    still_failed += 1
            except Exception as e:
                logger.error(f"Error retrying lemma {lemma}: {str(e)}")
                still_failed += 1
                
        tasks = []
        for lemma in failed_lemmas:
            if len(tasks) >= CONCURRENCY:
                await asyncio.gather(*tasks)
                tasks = []
            tasks.append(retry_lemma(lemma))
            
        if tasks:
            await asyncio.gather(*tasks)
            
        logger.info(f"Retry complete. Recovered: {success_count}, Still failed: {still_failed}")
        return success_count, still_failed

    async def export_failed_report(self, output_path: str = "failed_lemmas_report.json"):
        """Export a report of failed lemmas"""
        failed_lemmas = self.db.get_failed_lemmas()
        report = {
            'total_failed': len(failed_lemmas),
            'failed_lemmas': list(failed_lemmas),
            'timestamp': datetime.now().isoformat()
        }
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
            
        logger.info(f"Failed lemmas report exported to {output_path}")
        return report

    async def export_results(self, output_path: str = "lexicon_export.json"):
        """Export all successfully scraped entries"""
        entries = self.db.get_all_entries()
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(entries, f, ensure_ascii=False, indent=2)
            
        logger.info(f"Lexicon entries exported to {output_path}")
        return len(entries)

async def main():
    """Main entry point for the scraper"""
    logger.info("Starting Greek lexicon scraping...")
    
    async with LogeionScraper() as scraper:
        # Run the scraper for all letters
        await scraper.run_scraper()
        
        # Export results
        await scraper.export_results()
        await scraper.export_failed_report()

if __name__ == "__main__":
    asyncio.run(main()) 