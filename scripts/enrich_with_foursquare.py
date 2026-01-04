#!/usr/bin/env python3
"""
Foursquare Places API Enrichment Script

This script takes a list of stores (from raw scraped data) and enriches them
with data from Foursquare Places API including:
- Website URL
- Social media links (Instagram, Facebook, Twitter)
- Phone, email
- Hours of operation
- Ratings and popularity

Usage: python enrich_with_foursquare.py <input_json> [output_json]

Examples:
  python enrich_with_foursquare.py all_stores/raw/brand.json
  python enrich_with_foursquare.py stores.json enriched.json --test
"""

import json
import sys
import time
import os
from datetime import datetime
from pathlib import Path
import requests
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Foursquare API configuration
FOURSQUARE_API_KEY = os.getenv('FOURSQUARE_API_KEY')
PLACES_SEARCH_URL = 'https://places-api.foursquare.com/places/search'
PLACE_MATCH_URL = 'https://places-api.foursquare.com/places/match'
API_VERSION = '2025-06-17'

# Fields to request from Foursquare API
# Core fields + website + social_media + contact info
# Note: Some fields like fsq_id, geocodes, verified are not valid for the Places API
REQUESTED_FIELDS = ','.join([
    'name',
    'location',
    'categories',
    'chains',
    'website',
    'social_media',
    'tel',
    'email',
    'hours',
    'hours_popular',
    'rating',
    'popularity',
    'price',
    'link'
])


def get_store_coordinates(store):
    """
    Extract latitude and longitude from store data.

    Args:
        store (dict): Store data object

    Returns:
        tuple: (lat, lng) or (None, None) if not found
    """
    # Try different coordinate field names
    lat = store.get('lat') or store.get('latitude')
    lng = store.get('lng') or store.get('longitude')

    if lat and lng:
        try:
            return float(lat), float(lng)
        except (ValueError, TypeError):
            pass

    # Try nested location object
    location = store.get('location', {})
    if location:
        lat = location.get('latitude') or location.get('lat')
        lng = location.get('longitude') or location.get('lng')
        if lat and lng:
            try:
                return float(lat), float(lng)
            except (ValueError, TypeError):
                pass

    return None, None


def search_foursquare_place(store_name, lat, lng, address=None, city=None, state=None):
    """
    Search for a store in Foursquare Places API.

    Uses Place Match if we have good coordinates, otherwise falls back to Place Search.

    Args:
        store_name (str): Name of the store
        lat (float): Latitude
        lng (float): Longitude
        address (str): Street address (optional)
        city (str): City name (optional)
        state (str): State/province (optional)

    Returns:
        dict: Foursquare place data or None if not found
    """
    headers = {
        'accept': 'application/json',
        'X-Places-Api-Version': API_VERSION,
        'Authorization': f'Bearer {FOURSQUARE_API_KEY}'
    }

    # Try Place Match first if we have coordinates (more accurate)
    if lat and lng:
        match_params = {
            'name': store_name,
            'll': f"{lat},{lng}",
            'fields': REQUESTED_FIELDS
        }

        # Add address if available
        if address:
            match_params['address'] = address
        if city:
            match_params['city'] = city
        if state:
            match_params['state'] = state

        try:
            response = requests.get(
                PLACE_MATCH_URL,
                params=match_params,
                headers=headers,
                timeout=10
            )

            if response.status_code == 200:
                data = response.json()
                if data.get('place'):
                    return data['place']
            elif response.status_code == 404:
                # No match found, try search
                pass
            else:
                print(f"    ! Match API returned {response.status_code}")

        except Exception as e:
            print(f"    ! Match request error: {str(e)[:50]}")

    # Fall back to Place Search
    search_params = {
        'query': store_name,
        'fields': REQUESTED_FIELDS,
        'limit': 1
    }

    if lat and lng:
        search_params['ll'] = f"{lat},{lng}"
        search_params['radius'] = 1000  # 1km radius
    elif city and state:
        search_params['near'] = f"{city}, {state}"

    try:
        response = requests.get(
            PLACES_SEARCH_URL,
            params=search_params,
            headers=headers,
            timeout=10
        )

        if response.status_code == 200:
            data = response.json()
            results = data.get('results', [])
            if results:
                return results[0]
        else:
            print(f"    ! Search API returned {response.status_code}: {response.text[:100]}")

    except Exception as e:
        print(f"    ! Search request error: {str(e)[:50]}")

    return None


def extract_enrichment_data(fsq_data):
    """
    Extract useful enrichment data from Foursquare API response.

    Args:
        fsq_data (dict): Raw Foursquare place data

    Returns:
        dict: Cleaned enrichment data with website, social_media, etc.
    """
    enrichment = {
        'fsq_id': fsq_data.get('fsq_id'),
        'name': fsq_data.get('name'),
        'verified': fsq_data.get('verified', False),
    }

    # Website
    if fsq_data.get('website'):
        enrichment['website'] = fsq_data['website']

    # Social media
    social_media = fsq_data.get('social_media', {})
    if social_media:
        enrichment['social_media'] = {}
        if social_media.get('instagram'):
            enrichment['social_media']['instagram'] = social_media['instagram']
        if social_media.get('facebook_id'):
            enrichment['social_media']['facebook_id'] = social_media['facebook_id']
        if social_media.get('twitter'):
            enrichment['social_media']['twitter'] = social_media['twitter']

    # Contact info
    if fsq_data.get('tel'):
        enrichment['phone'] = fsq_data['tel']
    if fsq_data.get('email'):
        enrichment['email'] = fsq_data['email']

    # Location
    location = fsq_data.get('location', {})
    if location:
        enrichment['location'] = {
            'address': location.get('address'),
            'locality': location.get('locality'),
            'region': location.get('region'),
            'postcode': location.get('postcode'),
            'country': location.get('country'),
            'formatted_address': location.get('formatted_address')
        }

    # Geocodes
    geocodes = fsq_data.get('geocodes', {})
    if geocodes.get('main'):
        enrichment['coordinates'] = {
            'latitude': geocodes['main'].get('latitude'),
            'longitude': geocodes['main'].get('longitude')
        }

    # Hours
    if fsq_data.get('hours'):
        enrichment['hours'] = fsq_data['hours']

    # Rating and popularity
    if fsq_data.get('rating'):
        enrichment['rating'] = fsq_data['rating']
    if fsq_data.get('popularity'):
        enrichment['popularity'] = fsq_data['popularity']
    if fsq_data.get('price'):
        enrichment['price'] = fsq_data['price']

    # Categories
    categories = fsq_data.get('categories', [])
    if categories:
        enrichment['categories'] = [
            {'id': cat.get('id'), 'name': cat.get('name')}
            for cat in categories
        ]

    # Link to Foursquare page
    if fsq_data.get('link'):
        enrichment['foursquare_link'] = fsq_data['link']

    return enrichment


def enrich_stores(input_file, output_file='stores_foursquare_enriched.json', limit=None):
    """
    Enrich stores with Foursquare Places API data.

    Args:
        input_file (str): Input JSON file with stores
        output_file (str): Output JSON file
        limit (int): Optional limit for testing
    """
    if not FOURSQUARE_API_KEY:
        print("Error: FOURSQUARE_API_KEY not found in .env file")
        print("Add your API key: FOURSQUARE_API_KEY=your_key_here")
        print("\nTo get a Foursquare API key:")
        print("  1. Go to https://foursquare.com/developers/signup")
        print("  2. Create a project and get your API key")
        print("  3. Add it to your .env file")
        return 1

    # Ensure output directory exists
    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    print("=" * 80)
    print("FOURSQUARE PLACES API ENRICHMENT")
    print("=" * 80)
    print(f"\nInput: {input_file}")
    print(f"Output: {output_file}")
    print(f"Requesting fields: website, social_media, contact info, hours, rating\n")

    # Load input data
    with open(input_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    stores = data.get('stores', [])
    total = len(stores)

    if limit:
        stores = stores[:limit]
        print(f"LIMIT MODE: Only processing {limit} stores\n")

    enriched_count = 0
    not_found_count = 0
    with_website = 0
    with_instagram = 0

    for idx, store in enumerate(stores, 1):
        store_name = store.get('name', 'Unknown')
        address = store.get('address_line_1', '') or store.get('address', '')
        city = store.get('city', '')
        state = store.get('state', '')
        lat, lng = get_store_coordinates(store)

        print(f"[{idx}/{len(stores)}] {store_name}")
        if lat and lng:
            print(f"  Coords: {lat:.4f}, {lng:.4f}")
        else:
            print(f"  Location: {city}, {state}")

        # Search Foursquare
        fsq_data = search_foursquare_place(store_name, lat, lng, address, city, state)

        if fsq_data:
            # Extract and merge enrichment data
            enrichment = extract_enrichment_data(fsq_data)
            store['foursquare'] = enrichment
            enriched_count += 1

            # Log key data found
            if enrichment.get('website'):
                print(f"  + Website: {enrichment['website']}")
                with_website += 1

            social = enrichment.get('social_media', {})
            if social.get('instagram'):
                print(f"  + Instagram: @{social['instagram']}")
                with_instagram += 1
            if social.get('facebook_id'):
                print(f"  + Facebook: {social['facebook_id']}")
            if social.get('twitter'):
                print(f"  + Twitter: @{social['twitter']}")

            if enrichment.get('phone'):
                print(f"  + Phone: {enrichment['phone']}")

            if enrichment.get('rating'):
                print(f"  + Rating: {enrichment['rating']}/10")

            print(f"  Found on Foursquare")
        else:
            not_found_count += 1
            print(f"  x Not found on Foursquare")

        # Rate limiting - Foursquare allows 50 requests/second but let's be respectful
        time.sleep(0.2)

    # Prepare output
    result = {
        'source_file': input_file,
        'enriched_at': datetime.now().isoformat(),
        'enrichment_source': 'foursquare',
        'total_stores': len(stores),
        'enriched_count': enriched_count,
        'not_found_count': not_found_count,
        'with_website': with_website,
        'with_instagram': with_instagram,
        'stores': stores
    }

    # Save to file
    print(f"\n{'=' * 80}")
    print(f"Saving enriched data to: {output_file}")
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    print(f"\n ENRICHMENT COMPLETE!")
    print(f"  Total stores: {len(stores)}")
    print(f"  Successfully enriched: {enriched_count}")
    print(f"  Not found: {not_found_count}")
    print(f"  Success rate: {enriched_count/len(stores)*100:.1f}%")
    print(f"\n  Stores with website: {with_website}")
    print(f"  Stores with Instagram: {with_instagram}")

    return 0


def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print("Usage: python enrich_with_foursquare.py <input_json> [output_json] [--test]")
        print("\nExamples:")
        print("  python enrich_with_foursquare.py all_stores/raw/brand.json")
        print("  python enrich_with_foursquare.py stores.json enriched.json --test")
        print("\nThis script enriches store data with:")
        print("  - Website URLs")
        print("  - Instagram handles")
        print("  - Facebook and Twitter IDs")
        print("  - Phone numbers and emails")
        print("  - Hours of operation")
        print("  - Ratings and popularity")
        return 1

    # Parse arguments
    limit = None
    if '--test' in sys.argv:
        limit = 5
        sys.argv.remove('--test')
        print("TEST MODE: Will only process 5 stores\n")

    input_file = sys.argv[1]

    # Generate output filename
    if len(sys.argv) > 2:
        output_file = sys.argv[2]
    else:
        # Default: input_foursquare.json
        input_path = Path(input_file)
        output_file = str(input_path.parent / f"{input_path.stem}_foursquare{input_path.suffix}")

    if not Path(input_file).exists():
        print(f"Error: File not found: {input_file}")
        return 1

    try:
        return enrich_stores(input_file, output_file, limit=limit)
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        return 1
    except Exception as e:
        print(f"\n x Fatal error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    exit(main())
