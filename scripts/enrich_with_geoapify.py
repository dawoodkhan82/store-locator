#!/usr/bin/env python3
"""
Geoapify Places API Enrichment Script

This script takes a list of stores (from Stockist or any source) and enriches them
with detailed data from Geoapify Places API including:
- Full address, phone, website
- Rating, reviews, photos
- Business hours, types
- Location coordinates (verified/improved)

Usage: python enrich_with_geoapify.py <input_json> [output_json]
"""

import json
import sys
import time
import os
from datetime import datetime
from pathlib import Path
import requests
from requests.structures import CaseInsensitiveDict
from dotenv import load_dotenv
from urllib.parse import quote

# Load environment variables
load_dotenv()

# Geoapify API configuration
GEOAPIFY_API_KEY = os.getenv('GEOAPIFY_API_KEY')
GEOCODING_API_BASE = 'https://api.geoapify.com/v1/geocode/search'
PLACE_DETAILS_API_BASE = 'https://api.geoapify.com/v2/place-details'


def search_geoapify_places(store_name, address, city, state):
    """
    Search for a store in Geoapify API by name and location.

    Args:
        store_name (str): Name of the store
        address (str): Street address
        city (str): City name
        state (str): State/province

    Returns:
        dict: Geoapify place data or None if not found
    """
    # Build search query
    query = f"{store_name} {address} {city} {state}".strip()
    
    # First, search using Geocoding API to find the place
    params = {
        'text': query,
        'apiKey': GEOAPIFY_API_KEY,
        'limit': 1,  # Only get top result
        'type': 'amenity'  # Focus on businesses/amenities
    }
    
    headers = CaseInsensitiveDict()
    headers["Accept"] = "application/json"
    
    try:
        # Step 1: Search for the place
        response = requests.get(
            GEOCODING_API_BASE,
            params=params,
            headers=headers,
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            features = data.get('features', [])
            
            if features:
                # Get the first result
                feature = features[0]
                properties = feature.get('properties', {})
                place_id = properties.get('place_id')
                
                if place_id:
                    # Step 2: Get detailed place information
                    place_details = get_place_details(place_id)
                    if place_details:
                        # Merge geocoding data with place details
                        result = {
                            'geocoding': properties,
                            'geometry': feature.get('geometry', {}),
                            'place_details': place_details
                        }
                        return result
                    else:
                        # If place details fail, return geocoding data
                        return {
                            'geocoding': properties,
                            'geometry': feature.get('geometry', {})
                        }
        else:
            print(f"    ✗ Geocoding API error: {response.status_code} - {response.text[:100]}")
    
    except Exception as e:
        print(f"    ✗ Request error: {str(e)[:100]}")
    
    return None


def get_place_details(place_id):
    """
    Get detailed place information from Geoapify Place Details API.

    Args:
        place_id (str): Place ID from geocoding search

    Returns:
        dict: Place details or None if not found
    """
    # Format place_id for API (can be just the ID or "id=..." format)
    if not place_id.startswith('id='):
        place_id_param = f"id={quote(place_id)}"
    else:
        place_id_param = place_id
    
    url = f"{PLACE_DETAILS_API_BASE}?{place_id_param}&apiKey={GEOAPIFY_API_KEY}"
    
    headers = CaseInsensitiveDict()
    headers["Accept"] = "application/json"
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            return response.json()
        else:
            print(f"    ✗ Place Details API error: {response.status_code} - {response.text[:100]}")
    
    except Exception as e:
        print(f"    ✗ Place Details request error: {str(e)[:100]}")
    
    return None


def enrich_stores(input_file, output_file='stores_geoapify_enriched.json', limit=None):
    """
    Enrich stores with Geoapify Places API data.

    Args:
        input_file (str): Input JSON file with stores
        output_file (str): Output JSON file
        limit (int): Optional limit for testing
    """
    if not GEOAPIFY_API_KEY:
        print("Error: GEOAPIFY_API_KEY not found in .env file")
        return 1

    print("="*80)
    print("GEOAPIFY PLACES API ENRICHMENT")
    print("="*80)
    print(f"\nInput: {input_file}")
    print(f"Output: {output_file}\n")

    # Load input data
    with open(input_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    stores = data.get('stores', [])
    total = len(stores)

    if limit:
        stores = stores[:limit]
        print(f"⚠️ LIMIT MODE: Only processing {limit} stores\n")

    enriched_count = 0
    not_found_count = 0

    for idx, store in enumerate(stores, 1):
        store_name = store.get('name', 'Unknown')
        address = store.get('address_line_1', '')
        city = store.get('city', '')
        state = store.get('state', '')

        print(f"[{idx}/{len(stores)}] {store_name}")
        print(f"  Address: {address}, {city}, {state}")

        # Search Geoapify
        geoapify_data = search_geoapify_places(store_name, address, city, state)

        if geoapify_data:
            # Merge Geoapify data into store
            store['geoapify'] = geoapify_data
            enriched_count += 1
            print(f"  ✓ Found on Geoapify")

            # Log key data found
            geocoding = geoapify_data.get('geocoding', {})
            place_details = geoapify_data.get('place_details', {})
            
            # Check for website
            website = geocoding.get('website') or (place_details.get('properties', {}).get('website') if place_details else None)
            if website:
                print(f"    Website: {website}")
            
            # Check for phone
            phone = geocoding.get('phone') or (place_details.get('properties', {}).get('phone') if place_details else None)
            if phone:
                print(f"    Phone: {phone}")
            
            # Check for address
            formatted_address = geocoding.get('formatted')
            if formatted_address:
                print(f"    Address: {formatted_address}")

        else:
            not_found_count += 1
            print(f"  ✗ Not found on Geoapify")

        # Rate limiting - be respectful to API
        time.sleep(0.5)

    # Prepare output
    result = {
        'source_file': input_file,
        'enriched_at': datetime.now().isoformat(),
        'total_stores': len(stores),
        'enriched_count': enriched_count,
        'not_found_count': not_found_count,
        'stores': stores
    }

    # Save to file
    print(f"\n{'='*80}")
    print(f"Saving enriched data to: {output_file}")
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    print(f"\n✓ Enrichment complete!")
    print(f"  Total stores: {len(stores)}")
    print(f"  Successfully enriched: {enriched_count}")
    print(f"  Not found: {not_found_count}")
    print(f"  Success rate: {enriched_count/len(stores)*100:.1f}%")

    # Estimate API cost
    # Geoapify free plan: 3,000 credits/day
    # Geocoding: ~0.1 credits per request, Place Details: ~0.1 credits per request
    # Total: ~0.2 credits per store
    credits_used = len(stores) * 0.2
    print(f"\n  Estimated API credits used: {credits_used:.1f}")

    return 0


def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print("Usage: python enrich_with_geoapify.py <input_json> [output_json] [--test]")
        print("\nExamples:")
        print("  python enrich_with_geoapify.py stockist_stores_raw.json")
        print("  python enrich_with_geoapify.py stores.json enriched.json --test")
        return 1

    # Parse arguments
    limit = None
    if '--test' in sys.argv:
        limit = 5
        sys.argv.remove('--test')
        print("🧪 TEST MODE: Will only process 5 stores\n")

    input_file = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else 'stores_geoapify_enriched.json'

    if not Path(input_file).exists():
        print(f"Error: File not found: {input_file}")
        return 1

    try:
        return enrich_stores(input_file, output_file, limit=limit)
    except Exception as e:
        print(f"\n✗ Fatal error: {e}")
        return 1


if __name__ == '__main__':
    exit(main())

