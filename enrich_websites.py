#!/usr/bin/env python3
"""
Website Enrichment Script for Grocery Store Data (OpenAI-Powered)

This script scrapes store websites and uses OpenAI API to extract structured information:
- Product categories/inventory
- About Us descriptions
- Specialties (organic, vegan, local, etc.)
- Social media links (Instagram, Facebook, Twitter, TikTok)

Usage: python enrich_websites.py <input_json> [output_json]
"""

import json
import sys
import time
from pathlib import Path
import os

import requests
from bs4 import BeautifulSoup
from openai import OpenAI
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configuration
REQUEST_TIMEOUT = 10  # seconds
DELAY_BETWEEN_REQUESTS = 2  # seconds to be respectful
USER_AGENT = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
MAX_HTML_LENGTH = 100000  # Limit HTML content sent to OpenAI (to manage tokens)

# Initialize OpenAI client
client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))


def scrape_website_html(url, store_name):
    """
    Fetch and extract clean HTML content from a website.

    Args:
        url (str): Website URL to scrape
        store_name (str): Name of the store (for logging)

    Returns:
        dict: Dictionary with 'text' and 'links' keys, or None if failed
    """
    try:
        print(f"  Fetching: {url}")
        headers = {'User-Agent': USER_AGENT}
        response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT, allow_redirects=True)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, 'lxml')

        # Remove script and style elements
        for script in soup(['script', 'style', 'meta', 'link']):
            script.decompose()

        # Get text content - more useful than raw HTML
        html_text = soup.get_text(separator=' ', strip=True)

        # Also get the main structured content
        main_content = soup.find(['main', 'article', 'body'])
        if main_content:
            html_text = main_content.get_text(separator=' ', strip=True)

        # Limit length to avoid token limits
        if len(html_text) > MAX_HTML_LENGTH:
            html_text = html_text[:MAX_HTML_LENGTH] + "... [content truncated]"

        # Also extract all links for social media detection
        links = []
        for a in soup.find_all('a', href=True):
            links.append(a['href'])

        return {
            'text': html_text,
            'links': links[:100]  # Limit to first 100 links
        }

    except requests.Timeout:
        print(f"    ⏱ Timeout: {store_name}")
        return None
    except requests.RequestException as e:
        print(f"    ✗ Error: {store_name} - {str(e)[:80]}")
        return None
    except Exception as e:
        print(f"    ✗ Unexpected error: {store_name} - {str(e)[:80]}")
        return None


def extract_enrichment_with_openai(website_content, store_name, store_url):
    """
    Use OpenAI API to extract structured information from website content.

    Args:
        website_content (dict): Dictionary with 'text' and 'links' keys
        store_name (str): Name of the store
        store_url (str): URL of the store website

    Returns:
        dict: Enrichment data with productCategories, aboutText, specialties, socialLinks
    """
    if not website_content:
        return {
            'productCategories': [],
            'aboutText': '',
            'specialties': [],
            'socialLinks': {}
        }

    # Prepare the links list for social media extraction
    links_text = '\n'.join(website_content['links'][:50])  # First 50 links

    prompt = f"""You are analyzing a grocery store website to extract structured information.

Store Name: {store_name}
Store URL: {store_url}

Website Content (cleaned text):
{website_content['text'][:50000]}

Website Links (for social media detection):
{links_text}

Please analyze this website and extract the following information in JSON format:

1. **productCategories**: List of product categories this store offers (e.g., "Snacks", "Beverages", "Health Foods", "Produce", "Dairy"). Look for navigation menus, category pages, or descriptions of what they sell. Limit to 10 most relevant categories.

2. **aboutText**: A concise 1-2 sentence description of what makes this store unique or special. Focus on their mission, concept, or what differentiates them from regular grocery stores. Maximum 250 characters.

3. **specialties**: List of specialty attributes/keywords that describe this store (e.g., "organic", "vegan", "local", "artisanal", "curated", "emerging brands", "small-batch", "sustainable", "international", "gourmet", "prepared foods", "farm-to-table", "plant-based", "kosher", "halal"). Only include attributes that are clearly mentioned or strongly implied.

4. **socialLinks**: Extract social media URLs found in the links. Return as an object with keys: "instagram", "facebook", "twitter", "tiktok". Only include if you find actual links (look for instagram.com, facebook.com, twitter.com, x.com, tiktok.com in the links list).

Return ONLY a valid JSON object with these four keys. If you cannot find information for a field, use empty array [] or empty string "" or empty object {{}}.

Example format:
{{
  "productCategories": ["Snacks", "Beverages", "Health Foods"],
  "aboutText": "We showcase small brands and emerging CPG companies with a curated selection of unique products.",
  "specialties": ["organic", "small-batch", "emerging brands", "curated"],
  "socialLinks": {{"instagram": "https://instagram.com/storename", "facebook": "https://facebook.com/storename"}}
}}"""

    try:
        print(f"  Analyzing with OpenAI...")

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a helpful assistant that extracts structured information from website content. Always respond with valid JSON only."},
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"},
            temperature=0,
            max_tokens=2000
        )

        # Extract the JSON from OpenAI's response
        response_text = response.choices[0].message.content

        enrichment = json.loads(response_text)

        # Validate structure
        if not isinstance(enrichment.get('productCategories'), list):
            enrichment['productCategories'] = []
        if not isinstance(enrichment.get('aboutText'), str):
            enrichment['aboutText'] = ''
        if not isinstance(enrichment.get('specialties'), list):
            enrichment['specialties'] = []
        if not isinstance(enrichment.get('socialLinks'), dict):
            enrichment['socialLinks'] = {}

        print(f"    ✓ Extracted: {len(enrichment['productCategories'])} categories, "
              f"{len(enrichment['specialties'])} specialties, "
              f"{len(enrichment['socialLinks'])} social links")

        return enrichment

    except json.JSONDecodeError as e:
        print(f"    ✗ JSON parse error: {str(e)[:80]}")
        print(f"    Response was: {response_text[:200]}")
        return {
            'productCategories': [],
            'aboutText': '',
            'specialties': [],
            'socialLinks': {}
        }
    except Exception as e:
        print(f"    ✗ OpenAI API error: {str(e)[:80]}")
        return {
            'productCategories': [],
            'aboutText': '',
            'specialties': [],
            'socialLinks': {}
        }


def enrich_stores(input_file, output_file, limit=None):
    """
    Main function to enrich store data with OpenAI-powered website analysis.

    Args:
        input_file (str): Path to input JSON file with store data
        output_file (str): Path to save enriched JSON data
        limit (int): Optional limit on number of stores to enrich (for testing)
    """
    # Load existing data
    print(f"Loading data from: {input_file}")
    with open(input_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # Support both data structures: Manhattan stores (places) and Stockist stores (stores)
    if 'places' in data:
        places = data.get('places', [])
        data_key = 'places'
    elif 'stores' in data:
        places = data.get('stores', [])
        data_key = 'stores'
    else:
        print("Error: No 'places' or 'stores' key found in data")
        return

    total = len(places)

    print(f"Found {total} stores")

    # Count stores with websites - handle both data structures
    stores_with_websites = []
    for p in places:
        # Manhattan stores: websiteUri at top level
        if p.get('websiteUri'):
            stores_with_websites.append(p)
        # Stockist stores: websiteUri in google_places nested object
        elif p.get('google_places', {}).get('websiteUri'):
            stores_with_websites.append(p)

    print(f"Stores with websites: {len(stores_with_websites)}")

    if limit:
        print(f"⚠️  LIMIT MODE: Only processing first {limit} stores with websites")
        stores_with_websites = stores_with_websites[:limit]

    # Enrich each store with a website
    enriched_count = 0
    skipped_count = 0

    for idx, place in enumerate(places, 1):
        # Handle both data structures
        if 'websiteUri' in place:
            # Manhattan stores: websiteUri and displayName at top level
            website = place.get('websiteUri')
            store_name = place.get('displayName', {}).get('text', 'Unknown')
        else:
            # Stockist stores: websiteUri in google_places nested object
            google_places = place.get('google_places', {})
            website = google_places.get('websiteUri')
            store_name = google_places.get('displayName', {}).get('text', place.get('name', 'Unknown'))

        if website and (not limit or enriched_count < limit):
            print(f"\n[{enriched_count + 1}/{len(stores_with_websites) if limit else len(stores_with_websites)}] {store_name}")

            # Scrape the website
            website_content = scrape_website_html(website, store_name)

            # Use OpenAI to extract structured data
            enrichment = extract_enrichment_with_openai(website_content, store_name, website)

            # Add enrichment data to the place
            place['enrichment'] = enrichment
            enriched_count += 1

            # Be respectful - add delay between requests
            time.sleep(DELAY_BETWEEN_REQUESTS)
        else:
            if not website:
                skipped_count += 1

    # Save enriched data
    print(f"\n{'='*80}")
    print(f"Saving enriched data to: {output_file}")
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"\n✓ Enrichment complete!")
    print(f"  Total stores: {total}")
    print(f"  Stores enriched: {enriched_count}")
    print(f"  Stores skipped (no website): {skipped_count}")

    # Calculate estimated cost (GPT-4o-mini pricing)
    avg_tokens_per_request = 15000  # ~13k input + 500 output
    input_cost_per_1m_tokens = 0.150  # $0.150 per 1M input tokens
    output_cost_per_1m_tokens = 0.600  # $0.600 per 1M output tokens
    estimated_cost = (enriched_count * 13000 / 1_000_000) * input_cost_per_1m_tokens + \
                     (enriched_count * 500 / 1_000_000) * output_cost_per_1m_tokens
    print(f"  Estimated API cost: ${estimated_cost:.2f}")


def main():
    """Main entry point."""

    # Check for API key
    if not os.getenv('OPENAI_API_KEY'):
        print("Error: OPENAI_API_KEY not found in environment variables")
        print("Please add it to your .env file:")
        print("  OPENAI_API_KEY=your_api_key_here")
        return 1

    # Parse arguments
    limit = None
    auto_confirm = False
    if '--test' in sys.argv:
        limit = 5
        sys.argv.remove('--test')
        print("🧪 TEST MODE: Will only process 5 stores\n")
    if '--yes' in sys.argv or '-y' in sys.argv:
        auto_confirm = True
        if '--yes' in sys.argv:
            sys.argv.remove('--yes')
        if '-y' in sys.argv:
            sys.argv.remove('-y')

    if len(sys.argv) < 2:
        print("Usage: python enrich_websites.py <input_json> [output_json] [--test]")
        print("\nSearching for JSON files in current directory...")
        json_files = list(Path('.').glob('manhattan_specialty_grocery_stores_*.json'))
        if json_files:
            # Filter out enriched files
            json_files = [f for f in json_files if '_enriched' not in str(f)]
            if json_files:
                input_file = str(json_files[0])
                print(f"Found: {input_file}")
                output_file = input_file.replace('.json', '_enriched.json')
            else:
                print("No unenriched JSON files found.")
                return 1
        else:
            print("No JSON files found.")
            return 1
    else:
        input_file = sys.argv[1]
        output_file = sys.argv[2] if len(sys.argv) > 2 else input_file.replace('.json', '_enriched.json')

    if not Path(input_file).exists():
        print(f"Error: File not found: {input_file}")
        return 1

    print("="*80)
    print("OPENAI-POWERED WEBSITE ENRICHMENT SCRIPT")
    print("="*80)
    print("\nThis will:")
    print("  1. Scrape store websites to get content")
    print("  2. Use OpenAI API (GPT-4o-mini) to extract structured information:")
    print("     • Product categories/inventory")
    print("     • About Us descriptions")
    print("     • Specialties (organic, vegan, etc.)")
    print("     • Social media links (Instagram, etc.)")

    # Estimate time and cost
    with open(input_file, 'r') as f:
        data = json.load(f)
        stores_with_websites = len([p for p in data.get('places', []) if p.get('websiteUri')])

    if limit:
        stores_to_process = min(limit, stores_with_websites)
    else:
        stores_to_process = stores_with_websites

    estimated_time = stores_to_process * 3 / 60  # ~3 seconds per store
    # GPT-4o-mini cost calculation
    estimated_cost = (stores_to_process * 13000 / 1_000_000) * 0.150 + \
                     (stores_to_process * 500 / 1_000_000) * 0.600

    print(f"\nEstimated time: ~{estimated_time:.1f} minutes for {stores_to_process} websites")
    print(f"Estimated cost: ~${estimated_cost:.2f} (OpenAI GPT-4o-mini)")
    print("="*80 + "\n")

    # Confirm before proceeding
    if not limit and not auto_confirm and sys.stdin.isatty():  # Don't ask in test mode, with --yes flag, or when piped
        response = input("Continue? (y/n): ")
        if response.lower() != 'y':
            print("Cancelled.")
            return 0
    elif not limit and not auto_confirm:
        print("Running in non-interactive mode, proceeding automatically...")

    enrich_stores(input_file, output_file, limit=limit)

    return 0


if __name__ == '__main__':
    exit(main())
