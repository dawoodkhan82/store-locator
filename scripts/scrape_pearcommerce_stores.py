#!/usr/bin/env python3
"""
Generic Pear Commerce Store Locator Scraper

This script scrapes ANY brand's Pear Commerce-powered store locator by intercepting
the Pear Commerce API calls made by their widget.

Usage: python scrape_pearcommerce_stores.py <store_locator_url> [output_json]

Examples:
  python scrape_pearcommerce_stores.py https://www.cocojune.co/find-us/
  python scrape_pearcommerce_stores.py https://brand.com/find-stores stores.json
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
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from webdriver_manager.chrome import ChromeDriverManager

from excluded_chains import should_exclude_store
from usa_filter import filter_usa_stores


def extract_pear_vendor_id(page_source):
    """
    Extract the Pear Commerce vendor ID from the page source.

    Pear Commerce typically uses patterns like:
    - vendorId:'2631217615038593'
    - vendorId: "2631217615038593"

    Args:
        page_source (str): HTML source of the page

    Returns:
        str: Pear Commerce vendor ID or None if not found
    """
    # Pattern 1: Look for vendorId in script tags
    pattern1 = r'vendorId\s*:\s*["\'](\d+)["\']'
    match = re.search(pattern1, page_source, re.IGNORECASE)
    if match:
        return match.group(1)

    # Pattern 2: Look for data-vendor-id attributes
    pattern2 = r'data-vendor-id=["\'](\d+)["\']'
    match = re.search(pattern2, page_source, re.IGNORECASE)
    if match:
        return match.group(1)

    # Pattern 3: Look for pearcommerce URLs with vendor ID
    pattern3 = r'pearcommerce\.com/[^"\']*vendors?[/\-](\d+)'
    match = re.search(pattern3, page_source, re.IGNORECASE)
    if match:
        return match.group(1)

    return None


def fetch_stores_from_api(vendor_id):
    """
    Fetch all stores from Pear Commerce API using geographic grid search.

    Args:
        vendor_id (str): Pear Commerce vendor ID

    Returns:
        list: List of store objects, or empty list if request fails
    """
    print(f"\n→ Fetching stores for Pear Commerce Vendor ID: {vendor_id}")
    print("  Using dense geographic grid to ensure complete coverage...")

    # Create a grid covering the entire US
    regions = []

    # Continental US grid - 2 degree spacing
    for lat in range(25, 50, 2):
        for lon in range(-125, -65, 2):
            regions.append({"lat": lat, "lon": lon})

    # Major metro areas for extra coverage
    metros = [
        {"lat": 40.7, "lon": -74},    # NYC
        {"lat": 34.0, "lon": -118},   # LA
        {"lat": 41.8, "lon": -87.6},  # Chicago
        {"lat": 37.8, "lon": -122.4}, # SF
        {"lat": 33.4, "lon": -112.1}, # Phoenix
        {"lat": 39.9, "lon": -75.2},  # Philadelphia
        {"lat": 32.8, "lon": -96.8},  # Dallas
        {"lat": 29.8, "lon": -95.4},  # Houston
        {"lat": 38.9, "lon": -77.0},  # DC
        {"lat": 25.8, "lon": -80.2},  # Miami
        {"lat": 33.7, "lon": -84.4},  # Atlanta
        {"lat": 42.4, "lon": -71.1},  # Boston
        {"lat": 47.6, "lon": -122.3}, # Seattle
        {"lat": 45.5, "lon": -122.7}, # Portland
        {"lat": 32.7, "lon": -117.2}, # San Diego
        {"lat": 30.3, "lon": -97.7},  # Austin
        {"lat": 39.7, "lon": -104.9}, # Denver
        {"lat": 36.2, "lon": -115.1}, # Las Vegas
    ]
    regions.extend(metros)

    # Pear Commerce API endpoints to try
    api_endpoints = [
        "https://offers.pearcommerce.com/api/v2/vendors/{vendor_id}/product-locator/search",
        "https://offers.pearcommerce.com/api/v1/vendors/{vendor_id}/locations",
        "https://api.pearcommerce.com/v2/vendors/{vendor_id}/locations",
    ]

    all_stores = {}  # Use dict for deduplication

    for endpoint_template in api_endpoints:
        endpoint = endpoint_template.format(vendor_id=vendor_id)
        print(f"\n  Trying endpoint: {endpoint}")

        # Try different approaches for this endpoint
        for region in regions[:3]:  # Test with first 3 regions
            try:
                # Try with query parameters
                params = {
                    "lat": region["lat"],
                    "lng": region["lon"],
                    "radius": 500,  # Large radius in miles
                    "limit": 1000
                }

                headers = {
                    'Accept': 'application/json',
                    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
                }

                response = requests.get(endpoint, params=params, headers=headers, timeout=30)

                if response.status_code == 200:
                    try:
                        data = response.json()

                        # Check various response formats
                        if isinstance(data, list):
                            for store in data:
                                store_id = store.get('id') or store.get('_id')
                                if store_id:
                                    all_stores[store_id] = store
                            if len(data) > 0:
                                print(f"    ✓ Found {len(data)} stores from this region")
                        elif isinstance(data, dict):
                            for key in ['locations', 'stores', 'data', 'results', 'retailers']:
                                if key in data:
                                    stores = data[key]
                                    if isinstance(stores, list):
                                        for store in stores:
                                            store_id = store.get('id') or store.get('_id')
                                            if store_id:
                                                all_stores[store_id] = store
                                        print(f"    ✓ Found {len(stores)} stores in '{key}' key")
                                        break
                    except json.JSONDecodeError:
                        continue

                time.sleep(0.3)  # Rate limiting

            except requests.exceptions.RequestException:
                continue

        if all_stores:
            print(f"\n  ✓ Successfully fetched {len(all_stores)} unique stores")
            break

    return list(all_stores.values())


def scrape_pearcommerce_stores(url, output_file='pearcommerce_stores_raw.json', wait_time=10):
    """
    Scrape stores from a Pear Commerce-powered store locator.

    Args:
        url (str): URL of the store locator page
        output_file (str): Output JSON file path
        wait_time (int): Max seconds to wait for Pear Commerce widget to load

    Returns:
        dict: Store data with metadata
    """
    print("="*80)
    print("PEAR COMMERCE STORE LOCATOR SCRAPER")
    print("="*80)
    print(f"\nTarget URL: {url}")
    print(f"Output file: {output_file}")
    print(f"Max wait time: {wait_time}s\n")

    # Setup Chrome options
    chrome_options = Options()
    chrome_options.add_argument('--headless')
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--window-size=1920,1080')
    chrome_options.add_argument('--disable-webgl')
    chrome_options.add_argument('--disable-software-rasterizer')
    chrome_options.add_argument('--disable-features=WebGL,WebGL2')
    chrome_options.add_argument('--ignore-gpu-blocklist')
    chrome_options.add_argument('--disable-blink-features=AutomationControlled')
    chrome_options.add_experimental_option('excludeSwitches', ['enable-automation'])
    chrome_options.add_experimental_option('useAutomationExtension', False)
    chrome_options.set_capability('goog:loggingPrefs', {'performance': 'ALL'})

    driver = None
    stores_data = []

    try:
        print("Initializing Chrome driver...")
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        driver.execute_cdp_cmd('Network.enable', {})

        print(f"Loading page: {url}")
        driver.get(url)

        # Dismiss alerts
        try:
            alert = driver.switch_to.alert
            alert.dismiss()
        except:
            pass

        print("Waiting for Pear Commerce widget to load...")
        time.sleep(3)

        # Close popups
        print("Checking for and closing any popups/modals...")
        try:
            popup_selectors = [
                'button[aria-label*="Close"]',
                'button[class*="close"]',
                '[class*="close-button"]',
                '.klaviyo-close-form',
            ]
            for selector in popup_selectors:
                try:
                    close_button = driver.find_element(By.CSS_SELECTOR, selector)
                    if close_button.is_displayed():
                        close_button.click()
                        time.sleep(0.5)
                        break
                except:
                    continue

            driver.execute_script("""
                const overlays = document.querySelectorAll('[class*="modal"], [class*="popup"], [class*="overlay"]');
                overlays.forEach(el => {
                    if (el.style.display !== 'none' && el.offsetParent !== null) {
                        const rect = el.getBoundingClientRect();
                        if (rect.width > window.innerWidth * 0.5 || rect.height > window.innerHeight * 0.5) {
                            el.remove();
                        }
                    }
                });
            """)
        except Exception as e:
            print(f"  → No popups found: {str(e)[:50]}")

        time.sleep(2)

        # Extract vendor ID
        page_source = driver.page_source
        vendor_id = extract_pear_vendor_id(page_source)

        if vendor_id:
            print(f"✓ Found Pear Commerce Vendor ID: {vendor_id}")
            api_stores = fetch_stores_from_api(vendor_id)
            if api_stores:
                stores_data.extend(api_stores)
        else:
            print("⚠ Could not extract Pear Commerce Vendor ID")
            print("  → Will check network logs...")

        # Wait for widget
        try:
            WebDriverWait(driver, wait_time).until(
                lambda d: d.execute_script(
                    "return document.querySelector('#pear-map-target') !== null || "
                    "document.querySelector('[data-pear]') !== null || "
                    "window.pearcommerce !== undefined"
                )
            )
            print("✓ Pear Commerce widget detected")
        except TimeoutException:
            print("⚠ Pear Commerce widget not detected - continuing anyway...")

        time.sleep(3)

        # Get network logs
        logs = driver.get_log('performance')
        print(f"Analyzing {len(logs)} network requests...")

        for entry in logs:
            try:
                log = json.loads(entry['message'])['message']

                if log['method'] == 'Network.responseReceived':
                    response_url = log['params']['response']['url']

                    if 'pearcommerce' in response_url.lower() and any(x in response_url.lower() for x in ['location', 'store', 'retailer', 'product-locator']):
                        print(f"\n✓ Found Pear Commerce API call: {response_url}")

                        if not vendor_id:
                            extracted_id = extract_pear_vendor_id(response_url)
                            if extracted_id:
                                vendor_id = extracted_id
                                print(f"  → Extracted Vendor ID: {vendor_id}")

                        request_id = log['params']['requestId']

                        try:
                            response_body = driver.execute_cdp_cmd(
                                'Network.getResponseBody',
                                {'requestId': request_id}
                            )

                            body_content = response_body.get('body', '')
                            if body_content:
                                data = json.loads(body_content)

                                if isinstance(data, list):
                                    stores_data.extend(data)
                                    print(f"  → Extracted {len(data)} stores")
                                elif isinstance(data, dict):
                                    for key in ['locations', 'stores', 'data', 'results', 'retailers']:
                                        if key in data:
                                            store_list = data[key]
                                            if isinstance(store_list, list):
                                                stores_data.extend(store_list)
                                                print(f"  → Extracted {len(store_list)} stores from '{key}' key")
                                                break
                        except Exception as e:
                            print(f"  ✗ Could not get response body: {str(e)[:100]}")

            except:
                pass

        # If we found vendor_id but no stores yet, try the API again
        if vendor_id and not stores_data:
            print(f"\n→ Trying API again with Vendor ID: {vendor_id}")
            api_stores = fetch_stores_from_api(vendor_id)
            if api_stores:
                stores_data.extend(api_stores)

        # Deduplicate stores
        if stores_data:
            print(f"\n→ Deduplicating {len(stores_data)} total stores...")
            seen = set()
            unique_stores = []
            for store in stores_data:
                store_id = store.get('id') or store.get('_id') or store.get('retailer_id')
                if store_id:
                    store_hash = f"id:{store_id}"
                else:
                    store_hash = (
                        str(store.get('name', '') or store.get('retailer_name', '')) + '|' +
                        str(store.get('address', '') or store.get('street', '')) + '|' +
                        str(store.get('city', ''))
                    )

                if store_hash not in seen:
                    seen.add(store_hash)
                    unique_stores.append(store)

            print(f"  ✓ Removed {len(stores_data) - len(unique_stores)} duplicates")
            print(f"  → {len(unique_stores)} unique stores remaining")
            stores_data = unique_stores

        # Filter out excluded chains
        if stores_data:
            print(f"\n→ Filtering out excluded chain stores...")
            stores_before_filter = len(stores_data)
            stores_data = [s for s in stores_data if not should_exclude_store(
                s.get('name', '') or s.get('retailer_name', '')
            )]
            stores_after_filter = len(stores_data)

            excluded_count = stores_before_filter - stores_after_filter
            if excluded_count > 0:
                print(f"  ✓ Filtered out {excluded_count} stores from chains")
                print(f"  → {stores_after_filter} stores remaining")
            else:
                print(f"  → No stores matched exclusion filters")

        # Filter to USA stores only
        if stores_data:
            stores_data = filter_usa_stores(stores_data)

    except Exception as e:
        print(f"\n✗ Error: {str(e)}")
        raise

    finally:
        if driver:
            driver.quit()
            print("\nClosed browser")

    # Prepare output
    result = {
        'source_url': url,
        'scraped_at': datetime.now().isoformat(),
        'total_stores': len(stores_data),
        'stores': stores_data
    }

    # Save to file
    print(f"\n{'='*80}")
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
        print("Usage: python scrape_pearcommerce_stores.py <store_locator_url> [output_json]")
        print("\nExamples:")
        print("  python scrape_pearcommerce_stores.py https://www.cocojune.co/find-us/")
        print("  python scrape_pearcommerce_stores.py https://brand.com/stores stores.json")
        return 1

    url = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else 'pearcommerce_stores_raw.json'

    try:
        scrape_pearcommerce_stores(url, output_file)
        return 0
    except Exception as e:
        print(f"\n✗ Fatal error: {e}")
        return 1


if __name__ == '__main__':
    exit(main())
