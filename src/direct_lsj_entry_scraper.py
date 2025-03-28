#!/usr/bin/env python3
import os
import json
import time
import logging
from urllib.parse import quote, urljoin
from typing import Dict, List, Optional, Set, Tuple
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from database import Database

# Set up logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuration
REQUEST_DELAY = 1.2  # Seconds between requests
MAX_RETRIES = 3  # Maximum number of retries

# Base URL for the Perseus LSJ dictionary
BASE_URL = "https://www.perseus.tufts.edu/hopper"
LSJ_URL = "https://www.perseus.tufts.edu/hopper/text?doc=Perseus:text:1999.04.0057"

class LSJEntryScraper:
    """Specialized scraper for Greek dictionary entries in the LSJ lexicon"""
    
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
    
    def get_greek_letters(self) -> List[Dict]:
        """Get the list of Greek alphabet letters with their URLs"""
        base_url = "https://www.perseus.tufts.edu/hopper/text?doc=Perseus:text:1999.04.0057:alphabetic%20letter="
        
        # Map of Greek letters to URL encoding
        greek_letter_map = {
            'Α': '*a', 'Β': '*b', 'Γ': '*g', 'Δ': '*d', 'Ε': '*e',
            'Ζ': '*z', 'Η': '*h', 'Θ': '*q', 'Ι': '*i', 'Κ': '*k',
            'Λ': '*l', 'Μ': '*m', 'Ν': '*n', 'Ξ': '*c', 'Ο': '*o',
            'Π': '*p', 'Ρ': '*r', 'Σ': '*s', 'Τ': '*t', 'Υ': '*u',
            'Φ': '*f', 'Χ': '*x', 'Ψ': '*y', 'Ω': '*w'
        }
        
        greek_letters = []
        for greek_letter, url_code in greek_letter_map.items():
            greek_letters.append({
                'letter': greek_letter,
                'url': f"{base_url}{url_code}"
            })
            
        return greek_letters
    
    def parse_entry_groups(self, html: str) -> List[Dict]:
        """Parse entry groups from a letter page"""
        soup = BeautifulSoup(html, 'lxml')
        groups = []
        
        # Look for entry groups in the content
        entry_list = soup.select_one('div.entry_list')
        
        if entry_list:
            # This is a list of entries page
            for link in entry_list.find_all('a'):
                href = link.get('href')
                text = link.get_text().strip()
                
                if href and text:
                    full_url = href if href.startswith('http') else urljoin(BASE_URL, href)
                    groups.append({
                        'group': text,
                        'url': full_url
                    })
        else:
            # Try to find entry groups directly from the text
            content = soup.select_one('div.text')
            if content:
                for link in content.find_all('a'):
                    href = link.get('href')
                    text = link.get_text().strip()
                    
                    # Only include links that appear to be to dictionary entries
                    if (href and text and 
                        ('entry' in href or 'text:1999.04.0057' in href) and
                        not href.startswith('#')):
                        full_url = href if href.startswith('http') else urljoin(BASE_URL, href) 
                        groups.append({
                            'group': text,
                            'url': full_url
                        })
        
        return groups
    
    def parse_entry_content(self, html: str) -> Dict:
        """Parse the dictionary entry content"""
        soup = BeautifulSoup(html, 'lxml')
        
        # Get the main content
        content_div = soup.select_one('div.text')
        if not content_div:
            return {'text': '', 'html': ''}
        
        # Extract text and HTML
        text_content = content_div.get_text().strip()
        html_content = str(content_div)
        
        return {
            'text': text_content,
            'html': html_content
        }
    
    def scrape_letter(self, letter_info: Dict, limit_groups: int = None) -> List[Dict]:
        """Scrape all entry groups for a letter"""
        letter = letter_info['letter']
        url = letter_info['url']
        
        logger.info(f"Scraping letter: {letter}")
        html = self._make_request(url)
        
        if not html:
            logger.error(f"Failed to retrieve letter page: {url}")
            return []
        
        # Log some debug info about the HTML
        soup = BeautifulSoup(html, 'lxml')
        title = soup.title.string if soup.title else "No title"
        logger.debug(f"Page title: {title}")
        
        # Check if we got the expected content
        text_div = soup.select_one('div.text')
        if text_div:
            logger.debug(f"Found text div with content: {text_div.get_text()[:100]}...")
            
            # Store the entire letter page as one entry since it contains the actual definitions
            content = {
                'text': text_div.get_text().strip(),
                'html': str(text_div)
            }
            
            entry = {
                'letter': letter,
                'group': f"{letter} - Complete Letter Entries",
                'url': url,
                'content': content
            }
            
            # Store in database
            key = f"{letter}_complete"
            self.db.store_entry(key, entry)
            
            return [entry]
        else:
            logger.warning("No div.text found on the page")
            
        # Parse entry groups - this is for fallback only
        groups = self.parse_entry_groups(html)
        logger.info(f"Found {len(groups)} entry groups for letter {letter}")
        
        # If we didn't find direct content or groups, try a different URL format
        if not groups:
            logger.info("Trying different URL format for this letter")
            # The Perseus site sometimes uses this format: entry for a specific letter
            alt_url = f"https://www.perseus.tufts.edu/hopper/text?doc=Perseus:text:1999.04.0057:entry={letter.lower()}"
            logger.debug(f"Trying alternate URL: {alt_url}")
            
            alt_html = self._make_request(alt_url)
            if alt_html:
                alt_soup = BeautifulSoup(alt_html, 'lxml')
                alt_text_div = alt_soup.select_one('div.text')
                
                if alt_text_div:
                    logger.info(f"Found content with alternate URL")
                    content = {
                        'text': alt_text_div.get_text().strip(),
                        'html': str(alt_text_div)
                    }
                    
                    entry = {
                        'letter': letter,
                        'group': f"{letter} - Alternate Format",
                        'url': alt_url,
                        'content': content
                    }
                    
                    # Store in database
                    key = f"{letter}_alternate"
                    self.db.store_entry(key, entry)
                    
                    return [entry]
        
        if limit_groups:
            groups = groups[:limit_groups]
        
        entries = []
        for group_info in groups:
            group = group_info['group']
            group_url = group_info['url']
            
            logger.info(f"Scraping group: {group}")
            group_html = self._make_request(group_url)
            
            if not group_html:
                logger.error(f"Failed to retrieve group page: {group_url}")
                continue
            
            # Parse the entry content
            content = self.parse_entry_content(group_html)
            
            entry = {
                'letter': letter,
                'group': group,
                'url': group_url,
                'content': content
            }
            
            # Store in database
            key = f"{letter}_{group}"
            self.db.store_entry(key, entry)
            
            entries.append(entry)
        
        return entries
    
    def run(self, limit_letters: int = None, limit_groups: int = None):
        """Run the scraper for LSJ entries"""
        # Get all Greek letters
        greek_letters = self.get_greek_letters()
        logger.info(f"Found {len(greek_letters)} Greek letters")
        
        if limit_letters:
            greek_letters = greek_letters[:limit_letters]
        
        all_entries = []
        for letter_info in greek_letters:
            entries = self.scrape_letter(letter_info, limit_groups)
            all_entries.extend(entries)
        
        return all_entries
    
    def export_results(self, output_path: str = "lsj_entries_export.json"):
        """Export the scraped entries to a JSON file"""
        entries = self.db.get_all_entries()
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(entries, f, ensure_ascii=False, indent=2)
            
        logger.info(f"Exported {len(entries)} entries to {output_path}")

def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Scrape entries from the LSJ Greek-English Lexicon")
    parser.add_argument("--limit-letters", type=int, default=None, 
                        help="Limit the number of letters to process")
    parser.add_argument("--limit-groups", type=int, default=None,
                        help="Limit the number of entry groups per letter")
    parser.add_argument("--delay", type=float, default=REQUEST_DELAY,
                        help=f"Delay between requests in seconds (default: {REQUEST_DELAY})")
    parser.add_argument("--output", type=str, default="lsj_entries_export.json",
                        help="Output file path")
    parser.add_argument("--force", action="store_true",
                        help="Force running without limits")
    
    args = parser.parse_args()
    
    if args.limit_letters is None and args.limit_groups is None and not args.force:
        logger.warning("No limits specified. This will scrape the ENTIRE lexicon and may take a very long time.")
        logger.info("Use --force to run without limits or specify limits with --limit-letters and --limit-groups.")
        return
    
    scraper = LSJEntryScraper(delay=args.delay)
    scraper.run(args.limit_letters, args.limit_groups)
    scraper.export_results(args.output)
    
    logger.info(f"Scraping complete. Results exported to {args.output}")

if __name__ == "__main__":
    main() 