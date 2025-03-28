# Perseus LSJ Greek-English Lexicon Scraper

This tool extracts dictionary entries from the Perseus Digital Library's Liddell-Scott-Jones Greek-English Lexicon.

## Overview

The Perseus LSJ dictionary is accessible via URL patterns that follow a specific structure. This scraper uses these patterns to directly access individual entries without having to navigate through the site's JavaScript-heavy interface.

## Key Features

- Direct URL access to dictionary entries using the Perseus Betacode transliteration system
- Extracts both the main letter entries and specific word entries
- Stores entries in a SQLite database for easy access
- Exports all entries to a JSON file

## Results

With our approach, we've successfully extracted detailed dictionary entries including:

- Letter definitions (e.g., Α, Β, Γ)
- Common Greek words with their full definitions
- Detailed grammatical information, citations, and cross-references

Example entries extracted:
- βαίνω (to go, walk, step) - 5,857 characters of detailed grammatical forms and usage
- ἀγαθός (good) - 4,279 characters of definitions and examples
- βάλλω (to throw) - 8,367 characters of complete lexical information

## Usage

```bash
# Basic usage with limits (recommended for testing)
python src/lsj_entry_extractor.py --limit-letters 3 --limit-entries 5

# To run with all letters (warning: this will make many requests)
python src/lsj_entry_extractor.py --force

# To customize the output file
python src/lsj_entry_extractor.py --limit-letters 1 --output my_entries.json

# To adjust the delay between requests (default is 1.5 seconds)
python src/lsj_entry_extractor.py --limit-letters 1 --delay 2.0
```

## Understanding the Perseus Betacode System

The Perseus Digital Library uses a transliteration system called "Betacode" for Greek characters:

- Basic letters: α=a, β=b, γ=g, δ=d, etc.
- Diacritics:
  - Smooth breathing (᾿) = )
  - Rough breathing (῾) = (
  - Acute accent (´) = /
  - Grave accent (`) = \\
  - Circumflex (῀) = =

For example:
- ἄα (alpha with acute and smooth breathing followed by alpha) = a)/a
- βαίνω (beta, alpha with iota and acute, nu, omega) = bai/nw

## URL Structure

The Perseus LSJ URLs follow this pattern:

```
# For a letter
https://www.perseus.tufts.edu/hopper/text?doc=Perseus:text:1999.04.0057:alphabetic%20letter=*a

# For a specific entry
https://www.perseus.tufts.edu/hopper/text?doc=Perseus:text:1999.04.0057:entry=a)a/atos
```

Where:
- `1999.04.0057` is the document ID for the LSJ lexicon
- `*a` is the uppercase alpha (capital letters are preceded by *)
- `a)a/atos` is the betacode for ἀάατος

## Output Format

The extracted entries are stored in a structured JSON format:

```json
{
  "Α_main": {
    "id": "Α_main",
    "letter": "Α",
    "word": "Α",
    "url": "https://www.perseus.tufts.edu/hopper/text?doc=Perseus:text:1999.04.0057:alphabetic%20letter=*a",
    "is_letter": true,
    "content": {
      "text": "Α α, ἄλφα (q.v.), τό, indecl., first letter of the Gr. alphabet: as Numeral, ά A.= εἷς and πρῶτος, but 'α = 1,000.",
      "html": "<div class=\"text\">...</div>"
    },
    "success": true
  },
  "Α_ἀάατος": {
    "id": "Α_ἀάατος",
    "letter": "Α",
    "word": "ἀάατος",
    "url": "https://www.perseus.tufts.edu/hopper/text?doc=Perseus:text:1999.04.0057:entry=a)a/atos",
    "transliteration": "a)a/atos",
    "is_letter": false,
    "content": {
      "text": "ἀάατος, ον, (ἀάω) in Il. ...",
      "html": "<div class=\"text\">...</div>"
    },
    "success": true
  }
}
```

## Extending the Tool

To expand this tool for more comprehensive use:

1. Add more Greek words to the `common_entries` lists in the `generate_entry_urls_for_letter` method
2. Develop a more systematic approach to generating transliterations for Greek words
3. Consider implementing a full Betacode converter for automated entry generation
4. Add functionality to process and structure the extracted definitions

## Notes

- The delay parameter helps to avoid overloading the Perseus server
- The script currently includes a limited set of common Greek words for demonstration
- In a real implementation, you would want to generate a more comprehensive list of entries

## Source

This tool works with the Perseus LSJ Greek-English Lexicon available at:
https://www.perseus.tufts.edu/hopper/text?doc=Perseus:text:1999.04.0057

## License

This tool is provided for educational and research purposes only. Please respect the terms of use of the Perseus Digital Library. 