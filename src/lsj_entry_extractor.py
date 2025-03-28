#!/usr/bin/env python3
import os
import json
import time
import logging
import argparse
from urllib.parse import quote, urljoin
from typing import Dict, List, Optional, Set, Tuple
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from database import Database

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration
REQUEST_DELAY = 1.5  # Seconds between requests
MAX_RETRIES = 3  # Maximum number of retries

# Base URL for the Perseus LSJ dictionary
BASE_URL = "https://www.perseus.tufts.edu/hopper"
LSJ_URL = "https://www.perseus.tufts.edu/hopper/text?doc=Perseus:text:1999.04.0057"

class LSJEntryExtractor:
    """Specialized extractor for Greek dictionary entries in the LSJ lexicon using direct URL construction"""
    
    def __init__(self, db_path: str = "lsj_entries.sqlite", delay: float = REQUEST_DELAY):
        self.db = Database(db_path)
        self.delay = delay
        self.last_request_time = 0
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.114 Safari/537.36',
        })
    
    def _wait_for_delay(self):
        """Ensure we respect the delay between requests."""
        now = time.time()
        time_since_last = now - self.last_request_time
        if time_since_last < self.delay:
            time.sleep(self.delay - time_since_last)
        self.last_request_time = time.time()

    def _make_request(self, url: str) -> Optional[str]:
        """Make HTTP request with retry logic"""
        for attempt in range(MAX_RETRIES):
            try:
                self._wait_for_delay()
                response = self.session.get(url, timeout=30)
                response.raise_for_status()
                return response.text
            except Exception as e:
                logger.error(f"Request error on attempt {attempt+1}/{MAX_RETRIES}: {url} - {str(e)}")
                if attempt == MAX_RETRIES - 1:
                    return None
                time.sleep(self.delay * (attempt + 1))
        return None
    
    def get_greek_letters_with_codes(self) -> List[Dict]:
        """Get the list of Greek alphabet letters with their URL codes"""
        # Map of Greek letters to URL encoding
        greek_letter_map = {
            'Α': '*a', 'Β': '*b', 'Γ': '*g', 'Δ': '*d', 'Ε': '*e',
            'Ζ': '*z', 'Η': '*h', 'Θ': '*q', 'Ι': '*i', 'Κ': '*k',
            'Λ': '*l', 'Μ': '*m', 'Ν': '*n', 'Ξ': '*c', 'Ο': '*o',
            'Π': '*p', 'Ρ': '*r', 'Σ': '*s', 'Τ': '*t', 'Υ': '*u',
            'Φ': '*f', 'Χ': '*x', 'Ψ': '*y', 'Ω': '*w'
        }
        
        return [{'letter': letter, 'code': code} for letter, code in greek_letter_map.items()]
    
    def generate_entry_urls_for_letter(self, letter_info: Dict) -> List[Dict]:
        """Generate URLs for entries starting with a specific letter.
        This uses the known URL pattern format for the LSJ lexicon entries.
        """
        letter = letter_info['letter']
        code = letter_info['code']
        
        # First get the main letter page to see its full definition
        letter_url = f"{LSJ_URL}:alphabetic%20letter={code}"
        letter_html = self._make_request(letter_url)
        
        entries = []
        
        # Add the main letter entry
        if letter_html:
            soup = BeautifulSoup(letter_html, 'lxml')
            text_div = soup.select_one('div.text')
            
            if text_div:
                entries.append({
                    'id': f"{letter}_main",
                    'letter': letter,
                    'word': letter,
                    'url': letter_url,
                    'is_letter': True
                })
        
        # Based on the LSJ organization, we'll generate URLs for common entry patterns
        # For example, for letter Alpha (Α), we might have entries like:
        # - ἄα
        # - ἀάατος
        # - ἀβακέως
        # etc.
        
        # Using direct entry format:
        # https://www.perseus.tufts.edu/hopper/text?doc=Perseus:text:1999.04.0057:entry=a)a/atos
        
        # For Greek letters, the Perseus site uses a transliteration system
        # Where Greek characters are represented in ASCII:
        # α = a, β = b, γ = g, etc.
        # And diacritics have special codes:
        # smooth breathing (᾿) = ), rough breathing (῾) = (, 
        # acute accent (´) = /, grave accent (`) = \, circumflex (῀) = =
        
        # For demonstration, we'll generate entries for common combinations
        # In a real implementation, we would need a comprehensive list
        
        # Common Greek words for each letter
        if letter == 'Α':
            # Some common Alpha entries with their transliterated codes
            common_entries = [
                ('ἄα', 'a)/a'),                   # a with smooth breathing and acute
                ('ἀάατος', 'a)a/atos'),           # combination with smooth breathing and acute
                ('ἀβακέως', 'a)bake/ws'),         # alpha-beta combination
                ('ἀγαθός', 'a)gaqo/s'),           # alpha-gamma-theta
                ('ἄγαν', 'a)/gan'),               # alpha-gamma
                ('ἀδελφός', 'a)delfo/s'),         # alpha-delta-epsilon
                ('ἀήρ', 'a)h/r'),                 # alpha-eta
                ('αἰδώς', 'ai)dw/s'),             # alpha-iota
                ('ἄκρον', 'a)/kron'),             # alpha-kappa
                ('ἀλήθεια', 'a)lh/qeia')          # alpha-lambda-eta
            ]
        elif letter == 'Β':
            common_entries = [
                ('βαίνω', 'bai/nw'),              # beta-alpha-iota
                ('βάλλω', 'ba/llw'),              # beta-alpha-lambda
                ('βασιλεύς', 'basileu/s'),        # beta-alpha-sigma
                ('βέλος', 'be/los'),              # beta-epsilon
                ('βίος', 'bi/os'),                # beta-iota
                ('βλέπω', 'ble/pw'),              # beta-lambda
                ('βοή', 'boh/'),                  # beta-omicron
                ('βούλομαι', 'bou/lomai'),        # beta-omicron-upsilon
                ('βραχύς', 'braxu/s'),            # beta-rho
                ('βῶλος', 'bw=los')               # beta-omega
            ]
        elif letter == 'Γ':
            common_entries = [
                ('γαῖα', 'gai=a'),                # gamma-alpha-iota
                ('γάλα', 'ga/la'),                # gamma-alpha
                ('γέ', 'ge/'),                    # gamma-epsilon
                ('γῆ', 'gh='),                    # gamma-eta
                ('γίγνομαι', 'gi/gnomai'),        # gamma-iota-gamma
                ('γλαυκός', 'glauko/s'),          # gamma-lambda
                ('γνώμη', 'gnw/mh'),              # gamma-nu
                ('γόνυ', 'go/nu'),                # gamma-omicron
                ('γράφω', 'gra/fw'),              # gamma-rho
                ('γυνή', 'gunh/')                 # gamma-upsilon
            ]
        else:
            # Add more entries for other letters as needed
            common_entries = []
        
        # Add the common entries to our list
        for word, transliteration in common_entries:
            entry_url = f"{LSJ_URL}:entry={transliteration}"
            
            entries.append({
                'id': f"{letter}_{word}",
                'letter': letter,
                'word': word,
                'url': entry_url,
                'transliteration': transliteration,
                'is_letter': False
            })
        
        return entries
    
    def extract_entry_content(self, entry_info: Dict) -> Dict:
        """Extract the content of a dictionary entry"""
        url = entry_info['url']
        
        logger.info(f"Extracting entry: {entry_info['word']} ({url})")
        html = self._make_request(url)
        
        if not html:
            logger.error(f"Failed to retrieve entry: {url}")
            return {**entry_info, 'content': {'text': '', 'html': ''}, 'success': False}
        
        soup = BeautifulSoup(html, 'lxml')
        text_div = soup.select_one('div.text')
        
        if not text_div:
            logger.warning(f"No content found for entry: {url}")
            return {**entry_info, 'content': {'text': '', 'html': ''}, 'success': False}
        
        content = {
            'text': text_div.get_text().strip(),
            'html': str(text_div)
        }
        
        # Store in database
        self.db.store_entry(entry_info['id'], {**entry_info, 'content': content, 'success': True})
        
        return {**entry_info, 'content': content, 'success': True}
    
    def run(self, limit_letters: int = None, limit_entries: int = None):
        """Run the extractor for LSJ entries"""
        # Get all Greek letters
        greek_letters = self.get_greek_letters_with_codes()
        logger.info(f"Found {len(greek_letters)} Greek letters")
        
        if limit_letters:
            greek_letters = greek_letters[:limit_letters]
        
        all_entries = []
        for letter_info in greek_letters:
            letter = letter_info['letter']
            logger.info(f"Processing letter: {letter}")
            
            # Generate entry URLs for this letter
            entries = self.generate_entry_urls_for_letter(letter_info)
            
            if limit_entries:
                entries = entries[:limit_entries]
            
            for entry_info in entries:
                # Extract the content for this entry
                extracted = self.extract_entry_content(entry_info)
                all_entries.append(extracted)
        
        return all_entries
    
    def export_results(self, output_path: str = "lsj_entries_export.json"):
        """Export the scraped entries to a JSON file"""
        entries = self.db.get_all_entries()
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(entries, f, ensure_ascii=False, indent=2)
            
        logger.info(f"Exported {len(entries)} entries to {output_path}")

def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(description="Extract entries from the LSJ Greek-English Lexicon")
    parser.add_argument("--limit-letters", type=int, default=None, 
                        help="Limit the number of letters to process")
    parser.add_argument("--limit-entries", type=int, default=None,
                        help="Limit the number of entries per letter")
    parser.add_argument("--delay", type=float, default=REQUEST_DELAY,
                        help=f"Delay between requests in seconds (default: {REQUEST_DELAY})")
    parser.add_argument("--output", type=str, default="lsj_extracted_entries.json",
                        help="Output file path")
    parser.add_argument("--force", action="store_true",
                        help="Force running without limits")
    
    args = parser.parse_args()
    
    if args.limit_letters is None and args.limit_entries is None and not args.force:
        logger.warning("No limits specified. This will extract many entries and may take a very long time.")
        logger.info("Use --force to run without limits or specify limits with --limit-letters and --limit-entries.")
        return
    
    extractor = LSJEntryExtractor(delay=args.delay)
    extractor.run(args.limit_letters, args.limit_entries)
    extractor.export_results(args.output)
    
    logger.info(f"Extraction complete. Results exported to {args.output}")

if __name__ == "__main__":
    main() 