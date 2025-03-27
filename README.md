# Logeion Dictionary Scraper

A Python-based scraper for extracting lexicon entries from the Logeion online Greek dictionary (https://logeion.uchicago.edu/).

## Features

- Asynchronous scraping with rate limiting and retry logic
- Automatic discovery of Greek lemmas
- SQLite database storage with progress tracking
- Extracts multiple dictionary sources per lemma (LSJ, DGE, Bailly, etc.)
- Preserves both plain text and HTML formatting
- Resumable scraping with error handling

## Requirements

- Python 3.8+
- Dependencies listed in `requirements.txt`

## Setup

1. Clone the repository:
```bash
git clone https://github.com/yourusername/logeion-scraper
cd logeion-scraper
```

2. Create and activate a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

## Usage

Run the scraper:
```bash
python src/scraper.py
```

The scraper will:
1. Start from the Greek letter α
2. Discover lemma pages
3. Extract dictionary entries
4. Store results in `logeion.sqlite`

## Database Schema

### lexicon_entries
- `id`: Primary key
- `lemma`: Greek word
- `lexicon_source`: Dictionary source (LSJ, DGE, etc.)
- `definition`: Plain text definition
- `url`: Source URL
- `raw_html`: Original HTML formatting
- `created_at`: Timestamp

### scrape_queue
- `id`: Primary key
- `url`: Target URL
- `status`: pending/completed/error
- `retry_count`: Number of attempts
- `last_attempt`: Last try timestamp
- `error_message`: Error details if any
- `created_at`: Timestamp

## Rate Limiting

The scraper implements respectful crawling:
- 1.2 second delay between requests
- Exponential backoff on errors
- User-Agent identification
- Maximum 3 retries per URL

## License

MIT License 