#!/usr/bin/env python3
"""
Generic StoreRocket Store Locator Scraper

This script scrapes ANY brand's StoreRocket-powered store locator by calling
their public API directly - NO SELENIUM REQUIRED!

StoreRocket exposes a public JSON API that returns ALL locations in a single call.

Usage: python scrape_storerocket_stores.py <store_locator_url> [output_json]

Examples:
  python scrape_storerocket_stores.py https://www.rishi-tea.com/pages/store-locator
  python scrape_storerocket_stores.py https://brand.com/find-stores stores.json
"""

import json
import sys
import re
import requests
from datetime import datetime


# Chain stores to exclude (CPG brands often in these, but not specialty/independent stores)
EXCLUDED_CHAINS = [
    'Whole Foods',
    'Stop & Shop',
    'Target',
    'Walmart',
    'Kroger',
    'Safeway',
]


def should_exclude_store(store_name):
    """
    Check if store should be excluded based on chain filter list.

    Args:
        store_name (str): Name of the store to check

    Returns:
        bool: True if store should be excluded, False otherwise
    """
    if not store_name:
        return False

    store_name_lower = store_name.lower()
    for chain in EXCLUDED_CHAINS:
        if chain.lower() in store_name_lower:
            return True
    return False


def extract_storerocket_id(url):
    """
    Extract the StoreRocket account ID from a store locator page.

    The account ID is embedded in the HTML as data-storerocket-id attribute.
    Format: <div id='storerocket-widget' data-storerocket-id='ACCOUNT_ID'>

    Args:
        url (str): URL of the store locator page

    Returns:
        str: StoreRocket account ID (e.g., 'vZ4vPay8Qd') or None if not found
    """
    print(f"Fetching page to extract StoreRocket account ID...")

    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        html = response.text

        # Pattern: data-storerocket-id='ACCOUNT_ID' or data-storerocket-id="ACCOUNT_ID"
        pattern = r"data-storerocket-id=['\"]([a-zA-Z0-9_-]+)['\"]"
        match = re.search(pattern, html, re.IGNORECASE)

        if match:
            account_id = match.group(1)
            print(f"✓ Found StoreRocket account ID: {account_id}")
            return account_id
        else:
            print("✗ Could not find data-storerocket-id in page HTML")
            return None

    except requests.exceptions.RequestException as e:
        print(f"✗ Error fetching page: {str(e)}")
        return None


def fetch_all_locations(account_id):
    """
    Fetch all locations from StoreRocket's public API.

    The API endpoint format: https://storerocket.io/api/user/{account_id}/locations

    This endpoint returns ALL locations in a single call - no pagination needed!

    Args:
        account_id (str): StoreRocket account ID (e.g., 'vZ4vPay8Qd')

    Returns:
        list: List of store objects, or empty list if request fails
    """
    api_url = f"https://storerocket.io/api/user/{account_id}/locations"
    print(f"\nFetching all locations from StoreRocket API...")
    print(f"API endpoint: {api_url}")

    try:
        response = requests.get(api_url, timeout=30)
        response.raise_for_status()

        data = response.json()

        # Check for success
        if not data.get('success'):
            print("✗ API returned success=false")
            return []

        # Extract locations from response
        locations = data.get('results', {}).get('locations', [])

        print(f"✓ Successfully fetched {len(locations)} locations")
        return locations

    except requests.exceptions.RequestException as e:
        print(f"✗ API request failed: {str(e)}")
        return []
    except json.JSONDecodeError as e:
        print(f"✗ JSON parse error: {str(e)}")
        return []


def scrape_storerocket_stores(url, output_file='storerocket_stores_raw.json'):
    """
    Scrape stores from a StoreRocket-powered store locator.

    Process:
    1. Extract StoreRocket account ID from page HTML
    2. Call StoreRocket API to get all locations
    3. Filter out chain stores
    4. Save to JSON

    Args:
        url (str): URL of the store locator page
        output_file (str): Output JSON file path

    Returns:
        dict: Store data with metadata
    """
    print("=" * 80)
    print("STOREROCKET STORE LOCATOR SCRAPER")
    print("=" * 80)
    print(f"\nTarget URL: {url}")
    print(f"Output file: {output_file}\n")

    # Step 1: Extract StoreRocket account ID
    account_id = extract_storerocket_id(url)

    if not account_id:
        print("\n✗ Failed to extract StoreRocket account ID")
        print("  Make sure the URL contains a StoreRocket widget")
        return {
            'source_url': url,
            'scraped_at': datetime.now().isoformat(),
            'total_stores': 0,
            'stores': []
        }

    # Step 2: Fetch all locations from API
    stores_data = fetch_all_locations(account_id)

    if not stores_data:
        print("\n✗ No stores found")
        return {
            'source_url': url,
            'scraped_at': datetime.now().isoformat(),
            'total_stores': 0,
            'stores': []
        }

    # Step 3: Filter out excluded chain stores
    print(f"\n→ Filtering out excluded chain stores...")
    stores_before_filter = len(stores_data)
    stores_data = [s for s in stores_data if not should_exclude_store(s.get('name', ''))]
    stores_after_filter = len(stores_data)

    excluded_count = stores_before_filter - stores_after_filter
    if excluded_count > 0:
        print(f"  ✓ Filtered out {excluded_count} stores from chains: {', '.join(EXCLUDED_CHAINS)}")
        print(f"  → {stores_after_filter} stores remaining")
    else:
        print(f"  → No stores matched exclusion filters")

    # Prepare output
    result = {
        'source_url': url,
        'storerocket_account_id': account_id,
        'scraped_at': datetime.now().isoformat(),
        'total_stores': len(stores_data),
        'stores': stores_data
    }

    # Save to file
    print(f"\n{'=' * 80}")
    print(f"Saving {len(stores_data)} stores to: {output_file}")
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    print(f"\n✓ Scraping complete!")
    print(f"  Total stores found: {len(stores_data)}")

    if stores_data:
        print(f"\nSample store data:")
        print(json.dumps(stores_data[0], indent=2)[:500] + "...")

    return result


def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print("Usage: python scrape_storerocket_stores.py <store_locator_url> [output_json]")
        print("\nExamples:")
        print("  python scrape_storerocket_stores.py https://www.rishi-tea.com/pages/store-locator")
        print("  python scrape_storerocket_stores.py https://brand.com/stores stores.json")
        return 1

    url = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else 'storerocket_stores_raw.json'

    try:
        scrape_storerocket_stores(url, output_file)
        return 0
    except Exception as e:
        print(f"\n✗ Fatal error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    exit(main())
