#!/usr/bin/env python3
"""
Generic Stockist Store Locator Scraper

This script scrapes ANY brand's Stockist-powered store locator by intercepting
the Stockist API calls made by their widget.

Usage: python scrape_stockist_stores.py <store_locator_url> [output_json]

Examples:
  python scrape_stockist_stores.py https://yolele.com/pages/store-locator
  python scrape_stockist_stores.py https://brand.com/find-stores stores.json
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


# Chain stores to exclude (CPG brands often in these, but not specialty/independent stores)
EXCLUDED_CHAINS = [
    'Whole Foods',
    'Stop & Shop',
    'Target'
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


def extract_stockist_user_id(page_source):
    """
    Extract the Stockist user ID from the page source.

    The user ID is typically embedded in the widget code or API calls.
    Common patterns: u12345, /api/v1/u12345/

    Args:
        page_source (str): HTML source of the page

    Returns:
        str: Stockist user ID (e.g., 'u12345') or None if not found
    """
    # Pattern 1: Look for /api/v1/u{id}/ in URLs (most reliable)
    # Matches: stockist.co/api/v1/u22327/widget.js
    pattern1 = r'stockist\.co/api/v1/(u\d+)'
    match = re.search(pattern1, page_source, re.IGNORECASE)
    if match:
        return match.group(1)

    # Pattern 2: Look for tag=u##### in API calls
    # Matches: tag=u22327&latitude=...
    pattern2 = r'tag=(u\d+)'
    match = re.search(pattern2, page_source, re.IGNORECASE)
    if match:
        return match.group(1)

    # Pattern 3: Look for data-stockist attributes
    pattern3 = r'data-stockist[^>]*["\']?(u\d+)["\']?'
    match = re.search(pattern3, page_source, re.IGNORECASE)
    if match:
        return match.group(1)

    # Pattern 4: Look for Stockist.init with user ID
    pattern4 = r'Stockist\.init\(["\']?(u\d+)["\']?'
    match = re.search(pattern4, page_source, re.IGNORECASE)
    if match:
        return match.group(1)

    # Pattern 5: Look for any u##### pattern near "stockist" (least reliable, last resort)
    pattern5 = r'stockist[^u]{0,100}(u\d+)'
    match = re.search(pattern5, page_source, re.IGNORECASE)
    if match:
        return match.group(1)

    return None


def fetch_all_locations_from_api(user_id):
    """
    Fetch all locations using Stockist's search API with multiple geographic queries.

    Since Stockist limits results to 100 per query, we query from multiple geographic
    centers across the US to ensure we capture all locations.

    Args:
        user_id (str): Stockist user ID (e.g., 'u22327')

    Returns:
        list: List of store objects, or empty list if request fails
    """
    print(f"\n→ Fetching all locations for {user_id} using multi-region search strategy...")

    # Define multiple geographic regions to cover the entire US and beyond
    # Each region is centered on a different part of the country
    # Using 15 regions to ensure 100% coverage including outlying areas
    regions = [
        {"name": "Pacific West", "lat": 45, "lon": -122},      # Seattle/Portland area
        {"name": "Mountain West", "lat": 40, "lon": -111},     # Utah/Colorado
        {"name": "Southwest", "lat": 33, "lon": -112},         # Arizona/New Mexico
        {"name": "South Central", "lat": 32, "lon": -96},      # Texas
        {"name": "Southeast", "lat": 33, "lon": -84},          # Georgia/Carolinas
        {"name": "Northeast", "lat": 41, "lon": -74},          # New York/New Jersey
        {"name": "New England", "lat": 43, "lon": -71},        # Vermont/New Hampshire
        {"name": "Great Lakes", "lat": 43, "lon": -88},        # Wisconsin/Michigan
        {"name": "Northern Plains", "lat": 46, "lon": -100},   # North Dakota/Montana
        {"name": "California", "lat": 37, "lon": -121},        # California Central
        # Additional regions for complete coverage of outlying areas
        {"name": "Hawaii", "lat": 21.3, "lon": -157.8},        # Hawaiian Islands
        {"name": "Alaska", "lat": 64.2, "lon": -149.5},        # Alaska
        {"name": "Puerto Rico", "lat": 18.2, "lon": -66.5},    # Puerto Rico & Caribbean
        {"name": "Florida South", "lat": 25.8, "lon": -80.2},  # South Florida & Keys
        {"name": "Maine North", "lat": 45.3, "lon": -69.0},    # Northern New England
    ]

    all_stores = {}  # Use dict for deduplication by ID

    for region in regions:
        search_url = f"https://stockist.co/api/v1/{user_id}/locations/search"
        params = {
            "tag": user_id,
            "latitude": region["lat"],
            "longitude": region["lon"],
            "distance": 5000,  # 5000 km radius (covers entire US from any point)
            "sort": "name"
        }

        try:
            response = requests.get(search_url, params=params, timeout=30)
            response.raise_for_status()

            data = response.json()
            locations = data.get("locations", [])

            # Add stores to our collection, using ID for deduplication
            for store in locations:
                store_id = store.get("id")
                if store_id:
                    all_stores[store_id] = store

            print(f"  {region['name']:16} - {len(locations):3} stores | Total unique: {len(all_stores)}")

            # Small delay to be respectful to the API
            time.sleep(0.2)

        except requests.exceptions.RequestException as e:
            print(f"  {region['name']:16} - ✗ Request failed: {str(e)[:60]}")
        except json.JSONDecodeError as e:
            print(f"  {region['name']:16} - ✗ JSON parse error: {str(e)[:60]}")

    stores_list = list(all_stores.values())
    print(f"\n  ✓ Multi-region search complete: {len(stores_list)} total unique locations")

    return stores_list


def scrape_stockist_stores(url, output_file='stockist_stores_raw.json', wait_time=10):
    """
    Scrape stores from a Stockist-powered store locator.

    Args:
        url (str): URL of the store locator page
        output_file (str): Output JSON file path
        wait_time (int): Max seconds to wait for Stockist widget to load

    Returns:
        dict: Store data with metadata
    """
    print("="*80)
    print("STOCKIST STORE LOCATOR SCRAPER")
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

        # Dismiss any unexpected alerts (like WebGL errors)
        try:
            alert = driver.switch_to.alert
            alert_text = alert.text
            print(f"⚠ Dismissing alert: {alert_text}")
            alert.dismiss()
        except:
            pass  # No alert present

        # Wait for page to load and widget to initialize
        print("Waiting for Stockist widget to load...")
        time.sleep(3)  # Initial load time

        # Close common popups/modals that might block the Stockist widget
        print("Checking for and closing any popups/modals...")
        try:
            # Common email signup popup selectors
            popup_selectors = [
                # Generic close buttons
                'button[aria-label*="Close"]',
                'button[class*="close"]',
                'button[class*="modal-close"]',
                'button[class*="popup-close"]',
                '[class*="close-button"]',
                '[class*="modal-close"]',
                # Email/newsletter popup close buttons
                '.klaviyo-close-form',
                '#klaviyo-close',
                '[data-testid="close-button"]',
                '[aria-label="Close dialog"]',
                '[aria-label="Close modal"]',
                # Cookie banners
                '#onetrust-accept-btn-handler',
                'button[id*="cookie-accept"]',
                'button[class*="cookie-accept"]',
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

            # Alternative: Remove modal overlays entirely via JavaScript
            driver.execute_script("""
                // Remove common modal overlay elements
                const overlays = document.querySelectorAll('[class*="modal"], [class*="popup"], [class*="overlay"], [id*="modal"], [id*="popup"]');
                overlays.forEach(el => {
                    if (el.style.display !== 'none' && el.offsetParent !== null) {
                        const rect = el.getBoundingClientRect();
                        // Only remove if it's a large overlay (likely blocking content)
                        if (rect.width > window.innerWidth * 0.5 || rect.height > window.innerHeight * 0.5) {
                            el.remove();
                        }
                    }
                });
                // Remove any elements with high z-index that might be blocking
                document.querySelectorAll('*').forEach(el => {
                    const zIndex = parseInt(window.getComputedStyle(el).zIndex);
                    if (zIndex > 1000) {
                        const rect = el.getBoundingClientRect();
                        if (rect.width > window.innerWidth * 0.3 && rect.height > window.innerHeight * 0.3) {
                            el.remove();
                        }
                    }
                });
            """)
            print("  ✓ Removed any blocking overlays")

        except Exception as e:
            print(f"  → No popups found or error closing: {str(e)[:50]}")

        # Give widget more time to load after clearing popups
        time.sleep(2)

        # Try to extract Stockist user ID from page source
        page_source = driver.page_source
        user_id = extract_stockist_user_id(page_source)

        if user_id:
            print(f"✓ Found Stockist user ID: {user_id}")
            api_stores = fetch_all_locations_from_api(user_id)
            if api_stores:
                stores_data.extend(api_stores)
        else:
            print("⚠ Could not extract Stockist user ID from initial page source")
            print("  → Will check network logs for user ID...")

        # Try to wait for Stockist widget to appear (if not already found)
        try:
            # Look for common Stockist elements
            WebDriverWait(driver, wait_time).until(
                lambda d: d.execute_script(
                    "return document.querySelector('[data-stockist]') !== null || "
                    "document.querySelector('.stockist-widget') !== null || "
                    "document.querySelector('#stockist-widget') !== null || "
                    "window.Stockist !== undefined"
                )
            )
            print("✓ Stockist widget detected")
        except TimeoutException:
            print("⚠ Stockist widget not detected - continuing anyway...")

        # Additional wait for API calls
        if not user_id:
            print("Waiting for Stockist API calls...")
            time.sleep(3)
        else:
            print("Checking for any additional network requests...")
            time.sleep(2)

        # Get all network logs
        logs = driver.get_log('performance')

        print(f"Analyzing {len(logs)} network requests...")

        # If we didn't find user_id yet, try to extract it from network logs
        if not user_id:
            for entry in logs:
                try:
                    log = json.loads(entry['message'])['message']
                    if log['method'] == 'Network.responseReceived':
                        response_url = log['params']['response']['url']
                        if 'stockist.co' in response_url:
                            # Extract user ID from URL
                            extracted_id = extract_stockist_user_id(response_url)
                            if extracted_id:
                                user_id = extracted_id
                                print(f"\n✓ Found Stockist user ID from network logs: {user_id}")
                                api_stores = fetch_all_locations_from_api(user_id)
                                if api_stores:
                                    stores_data.extend(api_stores)
                                break
                except:
                    pass

        # Parse network logs to find Stockist API calls
        for entry in logs:
            try:
                log = json.loads(entry['message'])['message']

                # Look for network responses
                if log['method'] == 'Network.responseReceived':
                    response_url = log['params']['response']['url']

                    # Check if this is a Stockist API call
                    if 'stockist.co' in response_url and ('/api/' in response_url or '/locations' in response_url):
                        print(f"\n✓ Found Stockist API call: {response_url}")

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

                                # Stockist usually returns locations in different formats
                                # Try common patterns
                                if isinstance(data, list):
                                    stores_data.extend(data)
                                    print(f"  → Extracted {len(data)} stores from list")
                                elif isinstance(data, dict):
                                    if 'locations' in data:
                                        stores_data.extend(data['locations'])
                                        print(f"  → Extracted {len(data['locations'])} stores from 'locations' key")
                                    elif 'stores' in data:
                                        stores_data.extend(data['stores'])
                                        print(f"  → Extracted {len(data['stores'])} stores from 'stores' key")
                                    elif 'data' in data:
                                        if isinstance(data['data'], list):
                                            stores_data.extend(data['data'])
                                            print(f"  → Extracted {len(data['data'])} stores from 'data' key")
                                        else:
                                            stores_data.append(data)
                                            print(f"  → Extracted 1 store object")
                                    else:
                                        # Might be a single store object
                                        stores_data.append(data)
                                        print(f"  → Extracted 1 store object")

                        except Exception as e:
                            print(f"  ✗ Could not get response body: {str(e)[:100]}")

            except Exception as e:
                # Skip malformed log entries
                pass

        if not stores_data:
            print("\n⚠ No stores found via API interception.")
            print("  Attempting to scrape from page content...")

            # Try to find store data in page source or JavaScript
            page_source = driver.page_source

            # Look for JSON data in script tags
            try:
                scripts = driver.find_elements(By.TAG_NAME, 'script')
                for script in scripts:
                    script_content = script.get_attribute('innerHTML')
                    if script_content and ('location' in script_content.lower() or 'store' in script_content.lower()):
                        # Try to extract JSON
                        import re
                        json_matches = re.findall(r'\{[^\{\}]*"(?:name|address|city)"[^\{\}]*\}', script_content)
                        for match in json_matches:
                            try:
                                store_obj = json.loads(match)
                                stores_data.append(store_obj)
                            except:
                                pass
            except Exception as e:
                print(f"  ✗ Could not scrape from page: {str(e)[:100]}")

        # Deduplicate stores (important since we may have data from both API and network interception)
        if stores_data:
            print(f"\n→ Deduplicating {len(stores_data)} total stores...")
            # Try to deduplicate based on common fields
            seen = set()
            unique_stores = []
            for store in stores_data:
                # Create a hash based on multiple fields for better deduplication
                # Try ID first (most reliable)
                store_id = store.get('id')
                if store_id:
                    store_hash = f"id:{store_id}"
                else:
                    # Fall back to name + address + city
                    store_hash = (
                        str(store.get('name', '')) + '|' +
                        str(store.get('address', '') or store.get('address_line_1', '')) + '|' +
                        str(store.get('city', ''))
                    )

                if store_hash not in seen:
                    seen.add(store_hash)
                    unique_stores.append(store)

            print(f"  ✓ Removed {len(stores_data) - len(unique_stores)} duplicates")
            print(f"  → {len(unique_stores)} unique stores remaining")
            stores_data = unique_stores

        # Filter out excluded chain stores (to save API costs during enrichment)
        if stores_data:
            print(f"\n→ Filtering out excluded chain stores...")
            stores_before_filter = len(stores_data)
            stores_data = [s for s in stores_data if not should_exclude_store(s.get('name', ''))]
            stores_after_filter = len(stores_data)

            excluded_count = stores_before_filter - stores_after_filter
            if excluded_count > 0:
                print(f"  ✓ Filtered out {excluded_count} stores from chains: {', '.join(EXCLUDED_CHAINS)}")
                print(f"  → {stores_after_filter} stores remaining for enrichment")
            else:
                print(f"  → No stores matched exclusion filters")

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
        print("Usage: python scrape_stockist_stores.py <store_locator_url> [output_json]")
        print("\nExamples:")
        print("  python scrape_stockist_stores.py https://yolele.com/pages/store-locator")
        print("  python scrape_stockist_stores.py https://brand.com/stores stores.json")
        return 1

    url = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else 'stockist_stores_raw.json'

    try:
        scrape_stockist_stores(url, output_file)
        return 0
    except Exception as e:
        print(f"\n✗ Fatal error: {e}")
        return 1


if __name__ == '__main__':
    exit(main())
