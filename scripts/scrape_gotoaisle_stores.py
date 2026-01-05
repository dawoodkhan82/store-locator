#!/usr/bin/env python3
"""
Generic GoToAisle Store Locator Scraper

This script scrapes ANY brand's GoToAisle-powered store locator by extracting
the API credentials from the page and querying the GoToAisle API directly.

Usage: python scrape_gotoaisle_stores.py <store_locator_url> [output_json]

Examples:
  python scrape_gotoaisle_stores.py https://getsauz.com/pages/store-locator-1
  python scrape_gotoaisle_stores.py https://brand.com/find-stores stores.json
"""

import json
import sys
import time
import re
import requests
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager

from excluded_chains import should_exclude_store
from usa_filter import filter_usa_stores


# US geographic grid for comprehensive coverage
# Using 3-degree latitude and 4-degree longitude spacing
US_GRID = []
for lat in range(25, 50, 3):
    for lon in range(-125, -65, 4):
        US_GRID.append((lat, lon))


def extract_gotoaisle_credentials(page_source, network_logs=None):
    """
    Extract GoToAisle API credentials from page source or network logs.

    Args:
        page_source (str): HTML source of the page
        network_logs (list): Optional list of network log entries

    Returns:
        tuple: (brand_api_key, store_locator_id) or (None, None) if not found
    """
    brand_api_key = None
    store_locator_id = None

    # Pattern 1: Look for storeLocatorId in page source
    pattern1 = r'storeLocatorId["\s:=]+([a-z0-9]+)'
    match = re.search(pattern1, page_source, re.IGNORECASE)
    if match:
        store_locator_id = match.group(1)

    # Pattern 2: Look for API URL in page source
    pattern2 = r'store-locator-v1/([a-z0-9]+)'
    match = re.search(pattern2, page_source, re.IGNORECASE)
    if match and not store_locator_id:
        store_locator_id = match.group(1)

    # Pattern 3: Look for brandApiKey in page source
    pattern3 = r'brandApiKey["\s:=]+([A-Za-z0-9%/+=]+)'
    match = re.search(pattern3, page_source, re.IGNORECASE)
    if match:
        brand_api_key = match.group(1)

    # If we have network logs, search there too
    if network_logs:
        for log in network_logs:
            msg = log.get('message', '')

            # Look for retail-locations API calls
            if 'gotoaisle' in msg and 'retail-locations' in msg:
                # Extract storeLocatorId
                match = re.search(r'storeLocatorId=([a-z0-9]+)', msg)
                if match and not store_locator_id:
                    store_locator_id = match.group(1)

                # Extract brandApiKey
                match = re.search(r'brandApiKey=([A-Za-z0-9%/+=]+)', msg)
                if match and not brand_api_key:
                    brand_api_key = match.group(1)

    return brand_api_key, store_locator_id


def fetch_stores_from_api(brand_api_key, store_locator_id, source_url):
    """
    Fetch all US stores using the GoToAisle API with geographic grid search.

    Args:
        brand_api_key (str): Brand API key for authentication
        store_locator_id (str): Store locator ID
        source_url (str): Original source URL for referer header

    Returns:
        list: List of store dictionaries
    """
    print(f"\n-> Fetching stores using grid search strategy...")
    print(f"   Grid points: {len(US_GRID)}")

    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
        'Accept': 'application/json',
        'Origin': '/'.join(source_url.split('/')[:3]),
        'Referer': source_url
    }

    all_stores = {}  # Use dict to dedupe by locationId

    for i, (lat, lon) in enumerate(US_GRID):
        # Create bounding box around the point
        north = lat + 3
        south = lat - 3
        east = lon + 4
        west = lon - 4

        url = "https://discover.gotoaisle.com/api/v2/store-locator/retail-locations"
        params = {
            'brandApiKey': brand_api_key,
            'storeLocatorId': store_locator_id,
            'autoExpand': 'true',
            'north': north,
            'south': south,
            'east': east,
            'west': west,
            'latitude': lat,
            'longitude': lon
        }

        try:
            resp = requests.get(url, params=params, headers=headers, timeout=15)
            if resp.status_code == 200:
                data = resp.json()
                if 'retailLocations' in data:
                    for store in data['retailLocations']:
                        loc_id = store.get('locationId')
                        if loc_id and loc_id not in all_stores:
                            all_stores[loc_id] = store

            # Progress update every 20 points
            if (i + 1) % 20 == 0:
                print(f"   [{i+1}/{len(US_GRID)}] Found {len(all_stores)} unique stores so far...")

            # Rate limiting
            time.sleep(0.2)

        except requests.exceptions.Timeout:
            print(f"   Timeout at ({lat}, {lon}), continuing...")
        except Exception as e:
            print(f"   Error at ({lat}, {lon}): {str(e)[:50]}")

    print(f"\n   Total unique stores found: {len(all_stores)}")
    return list(all_stores.values())


def transform_store_data(raw_stores):
    """
    Transform raw GoToAisle store data into standardized format.

    Args:
        raw_stores (list): List of raw store dictionaries from API

    Returns:
        list: List of standardized store dictionaries
    """
    stores = []
    for s in raw_stores:
        store = {
            'id': s.get('locationId'),
            'name': s.get('name'),
            'address_line_1': s.get('streetAddress'),
            'address_line_2': None,
            'city': s.get('city'),
            'state': s.get('state'),
            'postal_code': s.get('zipCode'),
            'country': 'USA',
            'phone': s.get('phone'),
            'website': s.get('website'),
            'lat': s.get('latitude'),
            'lng': s.get('longitude'),
            'merchant_id': s.get('merchantId'),
            'merchant_logo': s.get('merchantLogoUrl'),
        }
        stores.append(store)
    return stores


def scrape_gotoaisle_stores(url, output_file=None):
    """
    Main function to scrape stores from a GoToAisle-powered store locator.

    Args:
        url (str): URL of the store locator page
        output_file (str): Optional path to save JSON output

    Returns:
        dict: Store data dictionary
    """
    print("=" * 80)
    print("GOTOAISLE STORE LOCATOR SCRAPER")
    print("=" * 80)
    print(f"\nTarget URL: {url}")
    print(f"Output file: {output_file or 'stdout'}")

    # Set up Chrome with network logging
    print("\nInitializing Chrome driver...")
    options = Options()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.set_capability('goog:loggingPrefs', {'performance': 'ALL'})

    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=options
    )

    brand_api_key = None
    store_locator_id = None

    try:
        # Enable network logging
        driver.execute_cdp_cmd('Network.enable', {})

        print(f"Loading page: {url}")
        driver.get(url)
        time.sleep(8)  # Wait for JS to load and make API calls

        # Get page source and network logs
        page_source = driver.page_source
        network_logs = driver.get_log('performance')

        print("Extracting GoToAisle credentials...")

        # Try to extract credentials from network logs (most reliable)
        for log in network_logs:
            msg = log.get('message', '')
            if 'gotoaisle' in msg and 'retail-locations' in msg:
                # Extract from URL parameters
                match = re.search(r'storeLocatorId=([a-z0-9]+)', msg)
                if match:
                    store_locator_id = match.group(1)

                match = re.search(r'brandApiKey=([A-Za-z0-9%/+=]+)', msg)
                if match:
                    brand_api_key = match.group(1)
                    # URL decode if needed
                    import urllib.parse
                    brand_api_key = urllib.parse.unquote(brand_api_key)

        # Fallback to page source extraction
        if not store_locator_id or not brand_api_key:
            key, loc_id = extract_gotoaisle_credentials(page_source, network_logs)
            if not brand_api_key:
                brand_api_key = key
            if not store_locator_id:
                store_locator_id = loc_id

        if not store_locator_id:
            print("\n! Could not extract store locator ID")
            print("  This page may not use GoToAisle")
            return None

        if not brand_api_key:
            print("\n! Could not extract brand API key")
            print("  This page may not use GoToAisle")
            return None

        print(f"  Store Locator ID: {store_locator_id}")
        print(f"  Brand API Key: {brand_api_key[:30]}...")

    finally:
        driver.quit()
        print("\nClosed browser")

    # Fetch stores using API
    raw_stores = fetch_stores_from_api(brand_api_key, store_locator_id, url)

    if not raw_stores:
        print("\n! No stores found")
        return None

    # Transform to standardized format
    stores = transform_store_data(raw_stores)

    # Filter to USA only and exclude chains
    print("\nFiltering stores...")
    stores = filter_usa_stores(stores)
    stores = [s for s in stores if not should_exclude_store(s.get('name', ''))]

    print(f"  After filtering: {len(stores)} stores")

    # Build output
    result = {
        'source': 'gotoaisle',
        'source_url': url,
        'scraped_at': datetime.now().isoformat(),
        'total_stores': len(stores),
        'stores': stores
    }

    # Save to file
    if output_file:
        print(f"\n{'=' * 80}")
        print(f"Saving {len(stores)} stores to: {output_file}")
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(result, f, indent=2, ensure_ascii=False)

    print(f"\n{'=' * 80}")
    print("SCRAPING COMPLETE!")
    print(f"  Total stores: {len(stores)}")
    print("=" * 80)

    return result


def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print(__doc__)
        print("\nError: Please provide a store locator URL")
        print("\nUsage: python scrape_gotoaisle_stores.py <url> [output.json]")
        sys.exit(1)

    url = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else None

    result = scrape_gotoaisle_stores(url, output_file)

    if result and not output_file:
        # Print to stdout if no output file specified
        print(json.dumps(result, indent=2))

    sys.exit(0 if result else 1)


if __name__ == '__main__':
    main()
