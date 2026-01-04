#!/usr/bin/env python3
"""
USA Store Filter Module

Shared module for filtering stores to USA-only locations.
Used by all scraper scripts to ensure consistent filtering.
"""

import re

# Valid US state codes for filtering
US_STATES = {
    'AL', 'AK', 'AZ', 'AR', 'CA', 'CO', 'CT', 'DE', 'FL', 'GA',
    'HI', 'ID', 'IL', 'IN', 'IA', 'KS', 'KY', 'LA', 'ME', 'MD',
    'MA', 'MI', 'MN', 'MS', 'MO', 'MT', 'NE', 'NV', 'NH', 'NJ',
    'NM', 'NY', 'NC', 'ND', 'OH', 'OK', 'OR', 'PA', 'RI', 'SC',
    'SD', 'TN', 'TX', 'UT', 'VT', 'VA', 'WA', 'WV', 'WI', 'WY',
    'DC', 'PR', 'VI', 'GU', 'AS', 'MP'
}


def is_usa_store(store):
    """
    Check if a store is located in the United States.

    Args:
        store (dict): Store data

    Returns:
        bool: True if store is in USA, False otherwise
    """
    # Check country field
    country = store.get('country', '').upper() if store.get('country') else ''
    if country in ('US', 'USA', 'UNITED STATES'):
        return True

    # Check state field - if it's a valid US state code, assume USA
    state = store.get('state', '') or store.get('state_code', '') or store.get('province', '')
    if state and len(state) == 2 and state.upper() in US_STATES:
        return True

    # Check address fields for US indicators
    address = (
        store.get('address', '') or
        store.get('address_line_1', '') or
        store.get('full_address', '') or
        store.get('formattedAddress', '') or
        ''
    )
    if address:
        address_upper = address.upper()
        if ', USA' in address_upper or 'UNITED STATES' in address_upper:
            return True
        # Check for US zip code pattern (5 digits, optionally followed by -4 digits)
        if re.search(r'\b\d{5}(-\d{4})?\b', address):
            # Has a zip code pattern - check if there's also a US state code
            for state_code in US_STATES:
                if f', {state_code} ' in address.upper() or f' {state_code} ' in address.upper():
                    return True

    return False


def filter_usa_stores(stores, verbose=True):
    """
    Filter a list of stores to only include USA locations.

    Args:
        stores (list): List of store dictionaries
        verbose (bool): Whether to print filtering stats

    Returns:
        list: Filtered list of USA-only stores
    """
    if not stores:
        return stores

    if verbose:
        print(f"\n→ Filtering to USA stores only...")

    stores_before = len(stores)
    usa_stores = [s for s in stores if is_usa_store(s)]
    stores_after = len(usa_stores)

    non_usa_count = stores_before - stores_after
    if verbose:
        if non_usa_count > 0:
            print(f"  ✓ Filtered out {non_usa_count} non-USA stores")
            print(f"  → {stores_after} USA stores remaining")
        else:
            print(f"  → All stores are in the USA")

    return usa_stores
