import asyncio
import json
import logging
import os
import time
from typing import Dict, List, Optional, Set, Tuple
from pathlib import Path
from urllib.parse import quote, urljoin, urlparse, parse_qs

import requests
from bs4 import BeautifulSoup
from database import Database

# Configuration
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

class DirectLSJScraper:
    def __init__(self, delay: float = REQUEST_DELAY):
        self.delay = delay
        self.last_request_time = 0
        self.db = Database("lsj_direct.sqlite")
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

    def scrape_greek_letters(self) -> List[Dict]:
        """Extract Greek letter links from the main LSJ page"""
        html = self._make_request(LSJ_URL)
        if not html:
            logger.error("Failed to retrieve main LSJ page")
            return []
        
        # Try to extract Greek letters using our specialized method
        greek_letters = self.extract_greek_letters_from_html(html)
        
        # If we found letters, return them
        if greek_letters:
            return greek_letters
            
        # Fallback to the hardcoded approach
        logger.info("Using hardcoded approach for Greek letters")
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
            
        logger.info(f"Using {len(greek_letters)} hardcoded Greek letter URLs")
        return greek_letters

    def scrape_entry_groups(self, letter_url: str) -> List[Dict]:
        """Scrape all entry groups for a given letter"""
        html = self._make_request(letter_url)
        if not html:
            logger.error(f"Failed to retrieve letter page: {letter_url}")
            return []
        
        soup = BeautifulSoup(html, 'lxml')
        groups = []
        
        # The letter page structure is different - check if there's a list of entry groups
        entry_list = soup.select_one('div.entry_list')
        if entry_list:
            for link in entry_list.find_all('a'):
                href = link.get('href')
                group_text = link.get_text().strip()
                
                if href and group_text:
                    # Make sure the href is properly joined with the base URL
                    full_url = href if href.startswith('http') else urljoin(BASE_URL, href)
                    groups.append({
                        'group': group_text,
                        'url': full_url
                    })
            return groups
        
        # If no entry list was found, look for the entry group links
        entry_group_section = soup.select_one('div.entry_group')
        if entry_group_section:
            for link in entry_group_section.find_all('a'):
                href = link.get('href')
                group_text = link.get_text().strip()
                
                if href and group_text:
                    # Make sure the href is properly joined with the base URL
                    full_url = href if href.startswith('http') else urljoin(BASE_URL, href)
                    groups.append({
                        'group': group_text,
                        'url': full_url
                    })
        else:
            # If we still haven't found anything, look for any relevant links
            # in the main content area
            content_area = soup.select_one('div.text')
            if content_area:
                for link in content_area.find_all('a'):
                    href = link.get('href')
                    group_text = link.get_text().strip()
                    
                    # Filter out navigational links and focus on entry links
                    if (href and group_text and 
                        not href.startswith('#') and 
                        not 'browse' in href.lower() and 
                        len(group_text.strip()) > 1):
                        full_url = href if href.startswith('http') else urljoin(BASE_URL, href)
                        groups.append({
                            'group': group_text,
                            'url': full_url
                        })
            else:
                # Last resort: try to find links that look like entry groups
                for link in soup.find_all('a'):
                    href = link.get('href')
                    group_text = link.get_text().strip()
                    
                    if (href and group_text and 
                        not href.startswith('#') and 
                        ('text' in href or 'entry' in href) and 
                        len(group_text.strip()) > 1):
                        full_url = href if href.startswith('http') else urljoin(BASE_URL, href)
                        groups.append({
                            'group': group_text,
                            'url': full_url
                        })
        
        return groups

    def extract_page_content(self, url: str) -> Dict:
        """Extract the full HTML and text content of an entry page"""
        html = self._make_request(url)
        if not html:
            logger.error(f"Failed to retrieve page: {url}")
            return {'url': url, 'html': '', 'text': ''}
        
        soup = BeautifulSoup(html, 'lxml')
        
        # Find the main text content
        text_element = soup.select_one('.text')
        
        if text_element:
            return {
                'url': url,
                'html': str(text_element),
                'text': text_element.get_text().strip()
            }
        
        return {
            'url': url,
            'html': '',
            'text': ''
        }

    def run_full_crawl(self, limit_letters: int = None, limit_groups: int = None):
        """Run a full crawl of the LSJ lexicon"""
        # Get all Greek letters
        letters = self.scrape_greek_letters()
        logger.info(f"Found {len(letters)} Greek letters")
        
        if limit_letters:
            letters = letters[:limit_letters]
        
        for letter_info in letters:
            letter = letter_info['letter']
            letter_url = letter_info['url']
            
            logger.info(f"Processing letter: {letter}")
            
            # Get all entry groups for this letter
            groups = self.scrape_entry_groups(letter_url)
            logger.info(f"Found {len(groups)} entry groups for letter {letter}")
            
            if limit_groups:
                groups = groups[:limit_groups]
            
            for group_info in groups:
                group = group_info['group']
                group_url = group_info['url']
                
                logger.info(f"Processing group: {group}")
                
                # Store the full page content
                page_content = self.extract_page_content(group_url)
                
                # Use a safe key for database storage
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
    
    def export_results(self, output_path: str = "lsj_direct_export.json"):
        """Export the scraped data to a JSON file"""
        entries = self.db.get_all_entries()
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(entries, f, ensure_ascii=False, indent=2)
            
        logger.info(f"Exported {len(entries)} entries to {output_path}")

    def extract_greek_letters_from_html(self, html: str) -> List[Dict]:
        """Extract Greek letters directly from the HTML structure of the LSJ lexicon page.
        
        This method uses direct string manipulation to find the Greek letters section,
        which helps bypass potential JavaScript-related issues.
        """
        greek_letters = []
        
        # Look for the section containing alphabetic letters
        # The letters are typically in a section with IDs or classes related to 'alphabetic_letter'
        soup = BeautifulSoup(html, 'lxml')
        
        # Try different methods to find the letter sections
        
        # 1. Look for browse bar
        logger.debug("Trying to find browse bar...")
        browse_bar = soup.select_one('#browse_bar')
        if browse_bar:
            logger.debug("Found browse bar, looking for links inside")
            letter_section = None
            
            # The letters might be inside a specific child element
            for child in browse_bar.children:
                if hasattr(child, 'get_text'):
                    text = child.get_text().strip()
                    # Check if this element contains Greek letters
                    if any(greek_char in text for greek_char in 'ΑΒΓΔΕΖΗΘΙΚΛΜΝΞΟΠΡΣΤΥΦΧΨΩ'):
                        logger.debug(f"Found potential letter section: {text[:30]}...")
                        letter_section = child
                        break
            
            if letter_section:
                for link in letter_section.find_all('a'):
                    href = link.get('href')
                    text = link.get_text().strip()
                    if href and len(text) <= 2:  # Some Greek letters may have diacritics
                        greek_letters.append({
                            'letter': text,
                            'url': urljoin(BASE_URL, href)
                        })
        
        # 2. Manually search for links with Greek letters
        if not greek_letters:
            logger.debug("Manual search for Greek letter links")
            greek_alpha_range = set('ΑΒΓΔΕΖΗΘΙΚΛΜΝΞΟΠΡΣΤΥΦΧΨΩ')
            
            for link in soup.find_all('a'):
                href = link.get('href')
                text = link.get_text().strip()
                
                # Check if this is likely a Greek letter link
                if href and text and len(text) == 1 and text in greek_alpha_range:
                    greek_letters.append({
                        'letter': text,
                        'url': urljoin(BASE_URL, href)
                    })
        
        # 3. Try direct regex pattern matching on the HTML
        if not greek_letters:
            logger.debug("Using regex pattern matching")
            import re
            
            # Look for links with the pattern typically used for letter navigation
            alpha_letter_pattern = r'<a href="([^"]+)[^>]*>([ΑΒΓΔΕΖΗΘΙΚΛΜΝΞΟΠΡΣΤΥΦΧΨΩ])</a>'
            matches = re.findall(alpha_letter_pattern, html)
            
            for href, letter in matches:
                greek_letters.append({
                    'letter': letter,
                    'url': urljoin(BASE_URL, href)
                })
        
        # If we still don't have any letters, try hardcoding known URL patterns
        if not greek_letters:
            logger.debug("Using hardcoded pattern for Greek letter URLs")
            greek_letters = []
            base_url = "https://www.perseus.tufts.edu/hopper/text?doc=Perseus:text:1999.04.0057:alphabetic%20letter="
            
            # Map of Greek letters to URL encoding (if needed)
            greek_letter_map = {
                'Α': '*a', 'Β': '*b', 'Γ': '*g', 'Δ': '*d', 'Ε': '*e',
                'Ζ': '*z', 'Η': '*h', 'Θ': '*q', 'Ι': '*i', 'Κ': '*k',
                'Λ': '*l', 'Μ': '*m', 'Ν': '*n', 'Ξ': '*c', 'Ο': '*o',
                'Π': '*p', 'Ρ': '*r', 'Σ': '*s', 'Τ': '*t', 'Υ': '*u',
                'Φ': '*f', 'Χ': '*x', 'Ψ': '*y', 'Ω': '*w'
            }
            
            for greek_letter, url_code in greek_letter_map.items():
                greek_letters.append({
                    'letter': greek_letter,
                    'url': f"{base_url}{url_code}"
                })
        
        logger.info(f"Extracted {len(greek_letters)} Greek letters")
        return greek_letters

def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Directly scrape the LSJ Greek-English Lexicon")
    parser.add_argument("--limit-letters", type=int, default=None, 
                        help="Limit the number of letters to process")
    parser.add_argument("--limit-groups", type=int, default=None,
                        help="Limit the number of entry groups per letter")
    parser.add_argument("--output", type=str, default="lsj_direct_export.json",
                        help="Output file path")
    parser.add_argument("--force", action="store_true",
                        help="Force running without limits")
    
    args = parser.parse_args()
    
    if args.limit_letters is None and args.limit_groups is None and not args.force:
        logger.warning("No limits specified. This will scrape the ENTIRE lexicon and may take a very long time.")
        logger.info("Use --force to run without limits or specify limits with --limit-letters and --limit-groups.")
        return
    
    scraper = DirectLSJScraper()
    scraper.run_full_crawl(args.limit_letters, args.limit_groups)
    scraper.export_results(args.output)
    
    logger.info(f"Scraping complete. Results exported to {args.output}")

if __name__ == "__main__":
    main() 