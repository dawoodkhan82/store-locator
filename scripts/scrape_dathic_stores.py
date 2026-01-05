#!/usr/bin/env python3
"""
Scraper for Dathic store locator platform (growth.dathic.com)

Uses the dathic API to collect all store inventory data for a given organization.
"""

import requests
import json
import time
import sys
import os
import re

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.excluded_chains import EXCLUDED_CHAINS
from scripts.usa_filter import filter_usa_stores


def login_to_dathic():
    """Login to dathic API and get access token."""
    session = requests.Session()
    login_resp = session.post(
        "https://api-1.dathic.com/login",
        json={"username": "teaser@dathic.com", "password": "teaser"},
        headers={"Content-Type": "application/json"}
    )
    if login_resp.status_code != 200:
        raise Exception(f"Failed to login: {login_resp.status_code}")

    token_data = login_resp.json()
    return session, token_data["access_token"]


def get_org_id_from_url(url):
    """Extract organization ID from dathic store locator URL or page."""
    # First check if it's a direct dathic URL
    match = re.search(r'growth\.dathic\.com/locator/[^/]+-(\d+)', url)
    if match:
        return match.group(1)

    # Otherwise fetch the page and look for iframe or embedded dathic
    try:
        resp = requests.get(url, timeout=10, headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        })
        # Look for dathic iframe
        match = re.search(r'growth\.dathic\.com/locator/[^/]+-(\d+)', resp.text)
        if match:
            return match.group(1)

        # Look for DATHIC_ORG_ID
        match = re.search(r'DATHIC_ORG_ID\s*=\s*(\d+)', resp.text)
        if match:
            return match.group(1)

        # Look for dathic clientid attribute (format: clientid="brand-name-1234")
        match = re.search(r'clientid="[^"]*-(\d+)"', resp.text)
        if match:
            return match.group(1)

        # Look for dathic S3 URL (format: dathicstorelocator.s3.amazonaws.com/brand-name-1234)
        match = re.search(r'dathicstorelocator\.s3\.amazonaws\.com/[^/]+-(\d+)', resp.text)
        if match:
            return match.group(1)

    except Exception as e:
        print(f"Error fetching URL: {e}")

    return None


def get_all_zipcodes(session, headers):
    """Collect all US zipcodes using grid search."""
    print("Collecting US zipcodes using grid search...")
    all_zipcodes = set()

    # Grid search across US with 200 mile radius queries
    grid_points = []
    for lat in range(25, 50, 4):  # 4 degree spacing
        for lon in range(-123, -68, 5):  # 5 degree spacing
            grid_points.append((lat, lon))

    # Add Alaska, Hawaii, Puerto Rico
    grid_points.extend([
        (61, -150),   # Alaska
        (21.5, -158), # Hawaii
        (18.2, -66.5) # Puerto Rico
    ])

    for i, (lat, lon) in enumerate(grid_points):
        try:
            resp = session.get(
                f"https://api-1.dathic.com/api/zipcodes_in_radius?latitude={lat}&longitude={lon}&radius_mi=200",
                headers=headers
            )
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, dict) and "zipcodes" in data:
                    all_zipcodes.update(data["zipcodes"])

            if (i + 1) % 20 == 0:
                print(f"  Progress: {i+1}/{len(grid_points)}, collected {len(all_zipcodes)} zipcodes")
            time.sleep(0.05)
        except Exception as e:
            print(f"  Error at ({lat}, {lon}): {e}")

    print(f"Total unique zipcodes collected: {len(all_zipcodes)}")
    return list(all_zipcodes)


def get_inventory(session, headers, org_id, zipcodes, batch_size=100):
    """Query inventory endpoint for all zipcodes in batches."""
    print(f"Querying inventory for org {org_id}...")

    all_stores = {}
    total_batches = (len(zipcodes) + batch_size - 1) // batch_size

    for batch_idx in range(total_batches):
        start = batch_idx * batch_size
        end = min(start + batch_size, len(zipcodes))
        batch_zips = zipcodes[start:end]

        # Build query string with multiple zipcode params
        zip_params = "&".join([f"zipcode={z}" for z in batch_zips])
        url = f"https://api-1.dathic.com/api/store_locator/inventory/{org_id}?{zip_params}"

        try:
            resp = session.get(url, headers=headers)
            if resp.status_code == 200:
                items = resp.json()
                if isinstance(items, list):
                    for item in items:
                        # Extract store info from delivery_entity
                        entity = item.get("delivery_entity", {})
                        store_uid = entity.get("uid")
                        if store_uid and store_uid not in all_stores:
                            all_stores[store_uid] = {
                                "id": store_uid,
                                "name": entity.get("store_name", ""),
                                "chain": entity.get("chain", ""),
                                "address": entity.get("address", ""),
                                "city": entity.get("city", ""),
                                "state": entity.get("state", ""),
                                "zip": entity.get("zipcode", ""),
                                "country": entity.get("country", ""),
                                "lat": entity.get("latitude"),
                                "lng": entity.get("longitude"),
                                "phone": entity.get("phone", ""),
                                "website": entity.get("store_url", "")
                            }

            if (batch_idx + 1) % 50 == 0:
                print(f"  Progress: {batch_idx+1}/{total_batches} batches, found {len(all_stores)} unique stores")

            time.sleep(0.05)
        except Exception as e:
            print(f"  Error in batch {batch_idx}: {e}")

    return list(all_stores.values())


def scrape_dathic_stores(url_or_org_id, output_file=None, include_chains=False):
    """
    Main function to scrape stores from dathic platform.

    Args:
        url_or_org_id: Either a store locator URL or dathic organization ID
        output_file: Path to save JSON output (optional)
        include_chains: If False, filter out major chain stores

    Returns:
        List of store dictionaries
    """
    # Determine org ID
    if str(url_or_org_id).isdigit():
        org_id = str(url_or_org_id)
    else:
        org_id = get_org_id_from_url(url_or_org_id)
        if not org_id:
            print(f"Could not find dathic organization ID from URL: {url_or_org_id}")
            return []

    print(f"Scraping dathic org ID: {org_id}")

    # Login and setup
    session, access_token = login_to_dathic()
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json"
    }

    # Get org config
    config_resp = session.get(
        f"https://api-1.dathic.com/api/store_locator/config/{org_id}",
        headers=headers
    )
    if config_resp.status_code == 200:
        config = config_resp.json()
        org_name = config.get("organization", {}).get("name", "Unknown")
        print(f"Organization: {org_name}")

    # Collect all US zipcodes
    all_zipcodes = get_all_zipcodes(session, headers)

    # Query inventory
    stores = get_inventory(session, headers, org_id, all_zipcodes)
    print(f"\nTotal stores found: {len(stores)}")

    # Filter to USA only
    usa_stores = filter_usa_stores(stores)
    print(f"USA stores: {len(usa_stores)}")

    # Filter out chain stores if requested
    if not include_chains:
        filtered_stores = []
        for store in usa_stores:
            chain_name = (store.get("chain") or "").lower()
            store_name = (store.get("name") or "").lower()

            is_chain = False
            for excluded in EXCLUDED_CHAINS:
                excluded_lower = excluded.lower()
                if excluded_lower in chain_name or excluded_lower in store_name:
                    is_chain = True
                    break

            if not is_chain:
                filtered_stores.append(store)

        print(f"After filtering chains: {len(filtered_stores)} stores")
        stores = filtered_stores
    else:
        stores = usa_stores

    # Save to file if specified
    if output_file:
        with open(output_file, 'w') as f:
            json.dump(stores, f, indent=2)
        print(f"Saved to {output_file}")

    return stores


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Scrape stores from Dathic platform")
    parser.add_argument("url_or_id", help="Store locator URL or dathic organization ID")
    parser.add_argument("-o", "--output", help="Output JSON file path")
    parser.add_argument("--include-chains", action="store_true",
                        help="Include major chain stores (default: filter them out)")

    args = parser.parse_args()

    stores = scrape_dathic_stores(args.url_or_id, args.output, args.include_chains)
    print(f"\nFinal count: {len(stores)} stores")
