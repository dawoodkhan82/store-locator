#!/usr/bin/env python3
"""
Generic Destini Store Locator Scraper

This script scrapes ANY brand's Destini-powered store locator by intercepting
the Destini API calls made by their widget.

Usage: python scrape_destini_stores.py <store_locator_url> [output_json]

Examples:
  python scrape_destini_stores.py https://flybyjing.com/pages/store-locator
  python scrape_destini_stores.py https://brand.com/find-stores stores.json
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

from excluded_chains import EXCLUDED_CHAINS, should_exclude_store


def extract_destini_locator_id(page_source, url=""):
    """
    Extract the Destini locator ID or subdomain from the page source or URL.

    Destini typically uses patterns like:
    - locator-id="3389"
    - data-destini-locator="3389"
    - destinilocators.com/thecoconutcult/ (subdomain pattern)

    Args:
        page_source (str): HTML source of the page
        url (str): The page URL

    Returns:
        str: Destini locator ID/subdomain or None if not found
    """
    # Pattern 0: Check URL for subdomain pattern (destinilocators.com/brandname/)
    if url and 'destinilocators.com' in url:
        pattern0 = r'destinilocators\.com/([a-zA-Z0-9_-]+)'
        match = re.search(pattern0, url)
        if match:
            subdomain = match.group(1)
            # Exclude common paths that aren't brand subdomains
            if subdomain not in ['api', 'www', 'cdn', 'site', 'ajax', 'data']:
                return subdomain

    # Pattern 1: Look for locator-id attribute
    pattern1 = r'locator-id=["\'](\d+)["\']'
    match = re.search(pattern1, page_source, re.IGNORECASE)
    if match:
        return match.group(1)

    # Pattern 2: Look for data-destini-locator attribute
    pattern2 = r'data-destini-locator=["\'](\d+)["\']'
    match = re.search(pattern2, page_source, re.IGNORECASE)
    if match:
        return match.group(1)

    # Pattern 3: Look for destini script includes with locator ID
    pattern3 = r'destini[^"\']*locator[^"\']*[?&]id=(\d+)'
    match = re.search(pattern3, page_source, re.IGNORECASE)
    if match:
        return match.group(1)

    # Pattern 4: Look in destiniDataLayer
    pattern4 = r'destiniDataLayer[^}]*locator[^:]*:\s*["\']?(\d+)'
    match = re.search(pattern4, page_source, re.IGNORECASE)
    if match:
        return match.group(1)

    # Pattern 5: Look for destinilocators.com in page with brand subdomain
    pattern5 = r'destinilocators\.com/([a-zA-Z0-9_-]+)/'
    match = re.search(pattern5, page_source)
    if match:
        subdomain = match.group(1)
        if subdomain not in ['api', 'www', 'cdn', 'site', 'ajax', 'data']:
            return subdomain

    return None


def fetch_stores_from_api(locator_id):
    """
    Fetch all stores from Destini API.

    Args:
        locator_id (str): Destini locator ID or brand subdomain

    Returns:
        list: List of store objects, or empty list if request fails
    """
    print(f"\n→ Fetching stores for Destini Locator ID/Subdomain: {locator_id}")

    # Destini API endpoints to try - handle both numeric IDs and brand subdomains
    api_endpoints = []

    # If it's a subdomain (not all digits), try subdomain-based endpoints first
    if not locator_id.isdigit():
        api_endpoints.extend([
            # Brand subdomain endpoints (e.g., thecoconutcult)
            f"https://destinilocators.com/{locator_id}/data/locations.json",
            f"https://destinilocators.com/{locator_id}/ajax/get_locator_data.php",
            f"https://api.destinilocators.com/v1/brands/{locator_id}/locations",
        ])

    # Numeric ID endpoints
    api_endpoints.extend([
        # destinilocators.com endpoints (most common)
        f"https://www.destinilocators.com/api/locator/{locator_id}/locations",
        f"https://destinilocators.com/api/locator/{locator_id}/locations",
        f"https://www.destinilocators.com/locators/{locator_id}/locations.json",
        # destini.io endpoints
        f"https://api.destini.io/v1/locators/{locator_id}/locations",
        f"https://destini.io/api/v1/locators/{locator_id}/locations",
        f"https://api.destini.io/locators/{locator_id}/locations",
    ])

    headers = {
        'Accept': 'application/json',
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
        'Referer': f'https://destinilocators.com/{locator_id}/'
    }

    for endpoint in api_endpoints:
        try:
            print(f"  Trying endpoint: {endpoint}")
            response = requests.get(endpoint, headers=headers, timeout=30)

            # Check if response is successful
            if response.status_code == 200:
                data = response.json()

                # Destini can return data in different formats
                if isinstance(data, list):
                    print(f"  ✓ Found {len(data)} stores")
                    return data
                elif isinstance(data, dict):
                    # Check various possible keys
                    for key in ['locations', 'stores', 'data', 'results', 'items']:
                        if key in data:
                            stores = data[key]
                            if isinstance(stores, list):
                                print(f"  ✓ Found {len(stores)} stores in '{key}' key")
                                return stores

                print(f"  ✗ Unexpected data format from {endpoint}")
            else:
                print(f"  ✗ HTTP {response.status_code}")

        except requests.exceptions.RequestException as e:
            print(f"  ✗ Request failed: {str(e)[:80]}")
        except json.JSONDecodeError as e:
            print(f"  ✗ JSON parse error: {str(e)[:80]}")

    return []


def scrape_destini_stores(url, output_file='destini_stores_raw.json', wait_time=10):
    """
    Scrape stores from a Destini-powered store locator.

    Args:
        url (str): URL of the store locator page
        output_file (str): Output JSON file path
        wait_time (int): Max seconds to wait for Destini widget to load

    Returns:
        dict: Store data with metadata
    """
    print("="*80)
    print("DESTINI STORE LOCATOR SCRAPER")
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
        print("Waiting for Destini widget to load...")
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

        # Try to extract Destini locator ID from page source and URL
        page_source = driver.page_source
        locator_id = extract_destini_locator_id(page_source, url)

        if locator_id:
            print(f"✓ Found Destini Locator ID/Subdomain: {locator_id}")
            api_stores = fetch_stores_from_api(locator_id)
            if api_stores:
                stores_data.extend(api_stores)
        else:
            print("⚠ Could not extract Destini Locator ID from page source")
            print("  → Will check network logs...")

        # Try to wait for Destini widget to appear
        try:
            WebDriverWait(driver, wait_time).until(
                lambda d: d.execute_script(
                    "return document.querySelector('[data-destini]') !== null || "
                    "document.querySelector('.destini-locator') !== null || "
                    "document.querySelector('#destini-locator') !== null || "
                    "window.destiniDataLayer !== undefined"
                )
            )
            print("✓ Destini widget detected")
        except TimeoutException:
            print("⚠ Destini widget not detected - continuing anyway...")

        # Additional wait for API calls
        if not locator_id:
            print("Waiting for Destini API calls...")
            time.sleep(3)
        else:
            print("Checking for any additional network requests...")
            time.sleep(2)

        # Get all network logs
        logs = driver.get_log('performance')
        print(f"Analyzing {len(logs)} network requests...")

        # Parse network logs to find Destini API calls
        destini_apis_found = []
        knox_post_data = None

        for entry in logs:
            try:
                log = json.loads(entry['message'])['message']

                # Look for knox POST requests (AWS Lambda based Destini)
                if log['method'] == 'Network.requestWillBeSent':
                    request = log['params']['request']
                    request_url = request['url']

                    if 'knox' in request_url and request.get('method') == 'POST' and request.get('postData'):
                        print(f"\n✓ Found Destini knox endpoint (AWS Lambda)")
                        knox_post_data = request['postData']
                        print(f"  POST data found, will fetch all stores...")

                # Look for network responses
                if log['method'] == 'Network.responseReceived':
                    response_url = log['params']['response']['url']

                    # Check if this is a Destini API call
                    if 'destini' in response_url.lower() and any(x in response_url.lower() for x in ['location', 'store', 'api', 'data']):
                        if response_url not in destini_apis_found:
                            destini_apis_found.append(response_url)
                            print(f"\n✓ Found Destini API call: {response_url}")

                            # Try to extract locator ID from URL if we don't have it
                            if not locator_id:
                                extracted_id = extract_destini_locator_id(response_url, response_url)
                                if extracted_id:
                                    locator_id = extracted_id
                                    print(f"  → Extracted Destini Locator ID/Subdomain: {locator_id}")

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

                                    # Destini usually returns locations in different formats
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

        # If we found knox POST data, fetch all stores from AWS Lambda endpoint
        if knox_post_data and not stores_data:
            print(f"\n→ Fetching all stores from knox endpoint...")
            try:
                post_params = json.loads(knox_post_data)
                # Modify to get all stores
                post_params['params']['distance'] = 10000  # Very large distance
                post_params['params']['maxStores'] = 10000  # Maximum stores
                post_params['params']['latitude'] = 39.8283  # Center of US
                post_params['params']['longitude'] = -98.5795

                response = requests.post(
                    'https://hlc7l6v5w6.execute-api.us-west-2.amazonaws.com/prod/knox',
                    json=post_params,
                    headers={'Content-Type': 'application/json', 'Accept': 'application/json'},
                    timeout=30
                )

                if response.status_code == 200:
                    data = response.json()
                    if 'data' in data and isinstance(data['data'], list):
                        stores_data.extend(data['data'])
                        print(f"  ✓ Fetched {len(data['data'])} stores from knox endpoint")
                else:
                    print(f"  ✗ Knox endpoint returned {response.status_code}")
            except Exception as e:
                print(f"  ✗ Error fetching from knox: {str(e)[:100]}")

        # If we found locator_id but no stores yet, try the API again
        if locator_id and not stores_data:
            print(f"\n→ Trying API again with Locator ID: {locator_id}")
            api_stores = fetch_stores_from_api(locator_id)
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
        print("Usage: python scrape_destini_stores.py <store_locator_url> [output_json]")
        print("\nExamples:")
        print("  python scrape_destini_stores.py https://flybyjing.com/pages/store-locator")
        print("  python scrape_destini_stores.py https://brand.com/stores stores.json")
        return 1

    url = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else 'destini_stores_raw.json'

    try:
        scrape_destini_stores(url, output_file)
        return 0
    except Exception as e:
        print(f"\n✗ Fatal error: {e}")
        return 1


if __name__ == '__main__':
    exit(main())
