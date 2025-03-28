#!/usr/bin/env python3
import asyncio
import argparse
import os
from src.lsj_scraper import LSJScraper
import logging

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def run_scraper(args):
    """Run the LSJ scraper with the provided arguments"""
    async with LSJScraper(delay=args.delay) as scraper:
        if args.limit_letters is None and args.limit_groups is None:
            logger.warning("No limits specified. This will scrape the ENTIRE lexicon and may take a very long time.")
            if not args.force:
                logger.info("Use --force to run without limits or specify limits with --limit-letters and --limit-groups.")
                return

        # Run the crawler
        await scraper.run_full_crawl(
            limit_letters=args.limit_letters,
            limit_groups=args.limit_groups
        )
        
        # Export the results
        await scraper.export_results(args.output)
        
        logger.info(f"Scraping complete. Results exported to {args.output}")

def main():
    parser = argparse.ArgumentParser(description="Scrape the Liddell-Scott-Jones Greek-English Lexicon")
    
    parser.add_argument("--limit-letters", type=int, default=None, 
                        help="Limit the number of letters to process (for testing)")
    
    parser.add_argument("--limit-groups", type=int, default=None,
                        help="Limit the number of entry groups per letter to process (for testing)")
    
    parser.add_argument("--delay", type=float, default=1.2,
                        help="Delay between requests in seconds (default: 1.2)")
    
    parser.add_argument("--output", type=str, default="lsj_lexicon_export.json",
                        help="Output file path (default: lsj_lexicon_export.json)")
    
    parser.add_argument("--force", action="store_true",
                        help="Force running without limits")
    
    args = parser.parse_args()
    
    # Run the scraper
    asyncio.run(run_scraper(args))

if __name__ == "__main__":
    main() 