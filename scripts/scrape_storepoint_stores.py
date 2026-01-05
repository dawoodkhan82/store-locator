#!/usr/bin/env python3
"""
Generic Storepoint Store Locator Scraper

This script scrapes ANY brand's Storepoint-powered store locator by intercepting
the Storepoint API calls made by their widget.

Usage: python scrape_storepoint_stores.py <store_locator_url> [output_json]

Examples:
  python scrape_storepoint_stores.py https://community.stellarsnacks.com/store-finder/
  python scrape_storepoint_stores.py https://brand.com/find-stores stores.json
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


def extract_storepoint_id(page_source):
    """
    Extract the Storepoint store ID from the page source.

    Storepoint typically uses patterns like:
    - cdn.storepoint.co/api/v1/js/1624f324b6336d.js
    - storepoint_id = "1624f324b6336d"

    Args:
        page_source (str): HTML source of the page

    Returns:
        str: Storepoint ID or None if not found
    """
    # Pattern 1: Look for storepoint.co script includes with ID
    pattern1 = r'cdn\.storepoint\.co/api/v1/js/([a-zA-Z0-9]+)\.js'
    match = re.search(pattern1, page_source, re.IGNORECASE)
    if match:
        return match.group(1)

    # Pattern 2: Look for storepoint.co URLs with different formats
    pattern2 = r'storepoint\.co/[^"\']*?([a-zA-Z0-9]{14,})'
    match = re.search(pattern2, page_source, re.IGNORECASE)
    if match:
        return match.group(1)

    # Pattern 3: Look for data-storepoint-id attributes
    pattern3 = r'data-storepoint-id=["\']([^"\']+)["\']'
    match = re.search(pattern3, page_source, re.IGNORECASE)
    if match:
        return match.group(1)

    # Pattern 4: Look for storepoint configuration in window object
    pattern4 = r'storepoint[^{]*\{[^}]*["\']?(?:id|store_id)["\']?\s*:\s*["\']([^"\']+)["\']'
    match = re.search(pattern4, page_source, re.IGNORECASE)
    if match:
        return match.group(1)

    # Pattern 5: Look for StorepointWidget constructor call
    # e.g., new StorepointWidget('1687e3499434ea', '#storepoint-widget', {})
    pattern5 = r'StorepointWidget\s*\(\s*["\']([a-zA-Z0-9]+)["\']'
    match = re.search(pattern5, page_source)
    if match:
        return match.group(1)

    return None


def fetch_stores_from_api(store_id):
    """
    Fetch all stores from Storepoint API.

    Storepoint provides various API endpoints for store data.

    Args:
        store_id (str): Storepoint store ID

    Returns:
        list: List of store objects, or empty list if request fails
    """
    print(f"\n→ Fetching stores for Storepoint ID: {store_id}")

    # Storepoint API endpoints
    api_endpoints = [
        # Primary API endpoints
        f"https://cdn.storepoint.co/api/v1/{store_id}/locations",
        f"https://api.storepoint.co/v1/{store_id}/locations",
        f"https://cdn.storepoint.co/api/{store_id}/locations.json",
        # Alternative formats
        f"https://storepoint.co/api/v1/{store_id}/locations",
        f"https://storepoint.co/api/{store_id}/stores",
    ]

    for endpoint in api_endpoints:
        try:
            print(f"  Trying endpoint: {endpoint}")
            response = requests.get(endpoint, timeout=30)
            response.raise_for_status()

            # Try to parse as JSON
            data = response.json()

            # Storepoint can return data in different formats
            if isinstance(data, list):
                print(f"  ✓ Found {len(data)} stores")
                return data
            elif isinstance(data, dict):
                # Check for nested results structure (common in Storepoint)
                if 'success' in data and 'results' in data:
                    results = data['results']
                    if isinstance(results, dict):
                        # Check for locations/stores in results
                        for key in ['locations', 'stores', 'data', 'items']:
                            if key in results:
                                stores = results[key]
                                if isinstance(stores, list):
                                    print(f"  ✓ Found {len(stores)} stores in 'results.{key}' key")
                                    return stores
                    elif isinstance(results, list):
                        print(f"  ✓ Found {len(results)} stores in 'results' key")
                        return results

                # Check various possible keys at top level
                for key in ['locations', 'stores', 'data', 'results', 'items']:
                    if key in data:
                        stores = data[key]
                        if isinstance(stores, list):
                            print(f"  ✓ Found {len(stores)} stores in '{key}' key")
                            return stores

            print(f"  ✗ Unexpected data format from {endpoint}")

        except requests.exceptions.RequestException as e:
            print(f"  ✗ Request failed: {str(e)[:80]}")
        except json.JSONDecodeError as e:
            print(f"  ✗ JSON parse error: {str(e)[:80]}")

    return []


def scrape_storepoint_stores(url, output_file='storepoint_stores_raw.json', wait_time=10):
    """
    Scrape stores from a Storepoint-powered store locator.

    Args:
        url (str): URL of the store locator page
        output_file (str): Output JSON file path
        wait_time (int): Max seconds to wait for Storepoint widget to load

    Returns:
        dict: Store data with metadata
    """
    print("="*80)
    print("STOREPOINT STORE LOCATOR SCRAPER")
    print("="*80)
    print(f"\nTarget URL: {url}")
    print(f"Output file: {output_file}")
    print(f"Max wait time: {wait_time}s\n")

    # Setup Chrome options
    chrome_options = Options()
    chrome_options.add_argument('--headless')  # Run in background
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--window-size=1920,1080')

    # Fix WebGL initialization errors in headless mode
    chrome_options.add_argument('--disable-webgl')
    chrome_options.add_argument('--disable-software-rasterizer')
    chrome_options.add_argument('--disable-features=WebGL,WebGL2')
    chrome_options.add_argument('--ignore-gpu-blocklist')

    # Additional stability options
    chrome_options.add_argument('--disable-blink-features=AutomationControlled')
    chrome_options.add_experimental_option('excludeSwitches', ['enable-automation'])
    chrome_options.add_experimental_option('useAutomationExtension', False)

    # Enable network interception
    chrome_options.set_capability('goog:loggingPrefs', {'performance': 'ALL'})

    driver = None
    stores_data = []

    try:
        # Initialize driver with automatic ChromeDriver management
        print("Initializing Chrome driver...")
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)

        # Enable Performance logging
        driver.execute_cdp_cmd('Network.enable', {})

        print(f"Loading page: {url}")
        driver.get(url)

        # Dismiss any unexpected alerts
        try:
            alert = driver.switch_to.alert
            alert_text = alert.text
            print(f"⚠ Dismissing alert: {alert_text}")
            alert.dismiss()
        except:
            pass  # No alert present

        # Wait for page to load and widget to initialize
        print("Waiting for Storepoint widget to load...")
        time.sleep(3)  # Initial load time

        # Close common popups/modals
        print("Checking for and closing any popups/modals...")
        try:
            popup_selectors = [
                'button[aria-label*="Close"]',
                'button[class*="close"]',
                'button[class*="modal-close"]',
                '[class*="close-button"]',
                '.klaviyo-close-form',
                '#klaviyo-close',
            ]

            for selector in popup_selectors:
                try:
                    close_button = driver.find_element(By.CSS_SELECTOR, selector)
                    if close_button.is_displayed():
                        close_button.click()
                        print(f"  ✓ Closed popup using selector: {selector}")
                        time.sleep(0.5)
                        break
                except:
                    continue

            # Remove modal overlays via JavaScript
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
            print("  ✓ Removed any blocking overlays")

        except Exception as e:
            print(f"  → No popups found or error closing: {str(e)[:50]}")

        # Give widget more time to load
        time.sleep(2)

        # Try to extract Storepoint ID from page source
        page_source = driver.page_source
        store_id = extract_storepoint_id(page_source)

        if store_id:
            print(f"✓ Found Storepoint ID: {store_id}")
            api_stores = fetch_stores_from_api(store_id)
            if api_stores:
                stores_data.extend(api_stores)
        else:
            print("⚠ Could not extract Storepoint ID from page source")
            print("  → Will check network logs...")

        # Try to wait for Storepoint widget to appear
        try:
            WebDriverWait(driver, wait_time).until(
                lambda d: d.execute_script(
                    "return document.querySelector('[data-storepoint]') !== null || "
                    "document.querySelector('.storepoint') !== null || "
                    "document.querySelector('#storepoint') !== null || "
                    "window.storepoint !== undefined"
                )
            )
            print("✓ Storepoint widget detected")
        except TimeoutException:
            print("⚠ Storepoint widget not detected - continuing anyway...")

        # Additional wait for API calls
        if not store_id:
            print("Waiting for Storepoint API calls...")
            time.sleep(3)
        else:
            print("Checking for any additional network requests...")
            time.sleep(2)

        # Get all network logs
        logs = driver.get_log('performance')
        print(f"Analyzing {len(logs)} network requests...")

        # Parse network logs to find Storepoint API calls
        storepoint_apis_found = []
        for entry in logs:
            try:
                log = json.loads(entry['message'])['message']

                # Look for network responses
                if log['method'] == 'Network.responseReceived':
                    response_url = log['params']['response']['url']

                    # Check if this is a Storepoint API call
                    if 'storepoint' in response_url.lower() and any(x in response_url.lower() for x in ['location', 'store', 'api', 'data']):
                        if response_url not in storepoint_apis_found:
                            storepoint_apis_found.append(response_url)
                            print(f"\n✓ Found Storepoint API call: {response_url}")

                            # Try to extract store ID from URL if we don't have it
                            if not store_id:
                                extracted_id = extract_storepoint_id(response_url)
                                if extracted_id:
                                    store_id = extracted_id
                                    print(f"  → Extracted Storepoint ID: {store_id}")

                            # Get the request ID
                            request_id = log['params']['requestId']

                            # Try to get response body
                            try:
                                response_body = driver.execute_cdp_cmd(
                                    'Network.getResponseBody',
                                    {'requestId': request_id}
                                )

                                # Parse JSON response
                                body_content = response_body.get('body', '')
                                if body_content:
                                    data = json.loads(body_content)

                                    # Storepoint usually returns locations in different formats
                                    if isinstance(data, list):
                                        stores_data.extend(data)
                                        print(f"  → Extracted {len(data)} stores from list")
                                    elif isinstance(data, dict):
                                        for key in ['locations', 'stores', 'data', 'results', 'items']:
                                            if key in data:
                                                store_list = data[key]
                                                if isinstance(store_list, list):
                                                    stores_data.extend(store_list)
                                                    print(f"  → Extracted {len(store_list)} stores from '{key}' key")
                                                    break

                            except Exception as e:
                                print(f"  ✗ Could not get response body: {str(e)[:100]}")

            except Exception as e:
                # Skip malformed log entries
                pass

        # If we found store_id but no stores yet, try the API again
        if store_id and not stores_data:
            print(f"\n→ Trying API again with ID: {store_id}")
            api_stores = fetch_stores_from_api(store_id)
            if api_stores:
                stores_data.extend(api_stores)

        if not stores_data:
            print("\n⚠ No stores found via API interception.")
            print("  Attempting to scrape from page content...")

            # Try to find store data in page source or JavaScript
            try:
                # Look for JSON data in script tags
                scripts = driver.find_elements(By.TAG_NAME, 'script')
                for script in scripts:
                    script_content = script.get_attribute('innerHTML')
                    if script_content and ('location' in script_content.lower() or 'store' in script_content.lower()):
                        # Try to extract JSON arrays
                        json_matches = re.findall(r'\[[\s\S]*?\{[\s\S]*?"(?:name|address|city)"[\s\S]*?\}[\s\S]*?\]', script_content)
                        for match in json_matches:
                            try:
                                stores_array = json.loads(match)
                                if isinstance(stores_array, list) and len(stores_array) > 0:
                                    stores_data.extend(stores_array)
                                    print(f"  ✓ Extracted {len(stores_array)} stores from script tag")
                                    break
                            except:
                                pass
            except Exception as e:
                print(f"  ✗ Could not scrape from page: {str(e)[:100]}")

        # Deduplicate stores
        if stores_data:
            print(f"\n→ Deduplicating {len(stores_data)} total stores...")
            seen = set()
            unique_stores = []
            for store in stores_data:
                # Create a hash based on multiple fields
                store_id_field = store.get('id') or store.get('store_id') or store.get('location_id')
                if store_id_field:
                    store_hash = f"id:{store_id_field}"
                else:
                    # Fall back to name + address + city
                    store_hash = (
                        str(store.get('name', '') or store.get('title', '')) + '|' +
                        str(store.get('address', '') or store.get('address1', '') or store.get('street', '')) + '|' +
                        str(store.get('city', ''))
                    )

                if store_hash not in seen:
                    seen.add(store_hash)
                    unique_stores.append(store)

            print(f"  ✓ Removed {len(stores_data) - len(unique_stores)} duplicates")
            print(f"  → {len(unique_stores)} unique stores remaining")
            stores_data = unique_stores

        # Filter out excluded chain stores
        if stores_data:
            print(f"\n→ Filtering out excluded chain stores...")
            stores_before_filter = len(stores_data)
            stores_data = [s for s in stores_data if not should_exclude_store(s.get('name', '') or s.get('title', ''))]
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
        print("Usage: python scrape_storepoint_stores.py <store_locator_url> [output_json]")
        print("\nExamples:")
        print("  python scrape_storepoint_stores.py https://community.stellarsnacks.com/store-finder/")
        print("  python scrape_storepoint_stores.py https://brand.com/stores stores.json")
        return 1

    url = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else 'storepoint_stores_raw.json'

    try:
        scrape_storepoint_stores(url, output_file)
        return 0
    except Exception as e:
        print(f"\n✗ Fatal error: {e}")
        return 1


if __name__ == '__main__':
    exit(main())
