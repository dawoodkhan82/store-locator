import json
import re
import requests
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options

BRANDS = {
    # "rootedfare": "https://rootedfare.com/pages/store-locator-1",
    # "alicemushrooms": "https://alicemushrooms.com/pages/store-locator",
    # "rishitea": "https://www.rishi-tea.com/pages/store-locator",
    "theonlybean": "https://theonlybean.com/pages/find-us"
}

def setup_driver():
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--disable-popup-blocking")
    chrome_options.add_argument("--disable-notifications")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    return webdriver.Chrome(options=chrome_options)

# --------------------------
# DETECT PLATFORM
# --------------------------

def detect_storepoint_id(url):
    """Extract StorePoint ID from page HTML."""
    resp = requests.get(url, timeout=15)
    match = re.search(r'data-map-id="([^"]+)"', resp.text)
    if match:
        return match.group(1)
    return None

def detect_storemapper_id(url):
    """Extract Storemapper ID from page HTML."""
    resp = requests.get(url, timeout=15)
    match = re.search(r'data-id="(\d+)"', resp.text)
    if match:
        return match.group(1)
    return None

# --------------------------
# FETCH FROM APIs
# --------------------------

def fetch_storepoint_stores(storepoint_id: str):
    """Fetch stores from StorePoint by storepoint_id, using fallback JSONP/HTML parsing."""
    possible_urls = [
        f"https://storepoint.co/api/get_locations?storepoint_id={storepoint_id}",
        f"https://api.storepoint.co/v1/locations?storepoint_id={storepoint_id}",
    ]
    for url in possible_urls:
        print(f"Trying StorePoint endpoint: {url}")
        try:
            resp = requests.get(url, timeout=15)
            if resp.status_code == 200:
                text = resp.text.strip()

                # Try JSON first
                try:
                    return resp.json().get("locations", [])
                except Exception:
                    pass  # maybe JSONP

                # Try JSONP fallback
                match = re.search(r'\{.*\}', text)
                if match:
                    data = json.loads(match.group(0))
                    if isinstance(data, dict) and "locations" in data:
                        return data["locations"]

            print(f"No valid data found at {url}")
        except Exception as e:
            print(f"Error fetching StorePoint data from {url}: {e}")
    print("Falling back to empty store list.")
    return []

def fetch_storemapper_stores(storemapper_id):
    """Fetch store data directly from Storemapper API."""
    api_url = f"https://www.storemapper.co/api/get_stores?storemapper_id={storemapper_id}"
    print(f"Fetching Storemapper data from {api_url}")
    resp = requests.get(api_url, timeout=15)
    data = resp.json()

    stores = []
    for s in data.get("stores", []):
        stores.append({
            "name": s.get("name", "Unknown"),
            "address_line_1": s.get("address", ""),
            "city": s.get("city", ""),
            "state": s.get("state", "")
        })
    return stores

# --------------------------
# SELENIUM FALLBACK
# --------------------------

def scrape_non_api(driver, brand, url):
    """Fallback for brands not using Storemapper/StorePoint."""
    driver.get(url)
    time.sleep(5)
    stores = []

    if brand == "rootedfare":
        elements = driver.find_elements(By.CSS_SELECTOR, ".store-locator-item")
        for e in elements:
            try:
                name = e.find_element(By.CSS_SELECTOR, "h3").text.strip()
                addr = e.find_element(By.CSS_SELECTOR, "p").text.strip()
                parts = addr.split(',')
                city = parts[-2].strip() if len(parts) >= 2 else ''
                state = parts[-1].strip() if len(parts) >= 1 else ''
                stores.append({
                    "name": name,
                    "address_line_1": addr,
                    "city": city,
                    "state": state
                })
            except:
                continue

    elif brand == "rishitea":
        elements = driver.find_elements(By.CSS_SELECTOR, ".store")
        for e in elements:
            try:
                name = e.find_element(By.CSS_SELECTOR, ".store-name").text.strip()
                addr = e.find_element(By.CSS_SELECTOR, ".store-address").text.strip()
                parts = addr.split(',')
                city = parts[-2].strip() if len(parts) >= 2 else ''
                state = parts[-1].strip() if len(parts) >= 1 else ''
                stores.append({
                    "name": name,
                    "address_line_1": addr,
                    "city": city,
                    "state": state
                })
            except:
                continue

    elif brand == "theonlybean":
        elements = driver.find_elements(By.CSS_SELECTOR, ".store-item")
        for e in elements:
            try:
                name = e.find_element(By.CSS_SELECTOR, ".store-name").text.strip()
                addr = e.find_element(By.CSS_SELECTOR, ".store-address").text.strip()
                parts = addr.split(',')
                city = parts[-2].strip() if len(parts) >= 2 else ''
                state = parts[-1].strip() if len(parts) >= 1 else ''
                stores.append({
                    "name": name,
                    "address_line_1": addr,
                    "city": city,
                    "state": state
                })
            except:
                continue

    return stores

# --------------------------
# MAIN
# --------------------------

def main():
    driver = setup_driver()
    all_data = {}

    for brand, url in BRANDS.items():
        print(f"\n--- Scraping {brand} ---")
        stores = []

        # Try StorePoint first
        storepoint_id = detect_storepoint_id(url)
        if storepoint_id:
            print(f"Found StorePoint ID: {storepoint_id}")
            stores = fetch_storepoint_stores(storepoint_id)
        else:
            # Try Storemapper
            storemapper_id = detect_storemapper_id(url)
            if storemapper_id:
                print(f"Found Storemapper ID: {storemapper_id}")
                stores = fetch_storemapper_stores(storemapper_id)
            else:
                print("No StorePoint or Storemapper ID found — using Selenium fallback.")
                stores = scrape_non_api(driver, brand, url)

        all_data[brand] = stores
        print(f"✅ {brand}: {len(stores)} stores scraped")

    driver.quit()

    with open("stores.json", "w") as f:
        json.dump(all_data, f, indent=2)

    print("\n✅ All data saved to stores.json")

if __name__ == "__main__":
    main()
