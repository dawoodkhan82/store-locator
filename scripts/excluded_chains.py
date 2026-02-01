"""
Shared list of chain stores to exclude from scraping results.

These are large national/regional chains that we don't want to include
in our independent grocery store database.
"""

EXCLUDED_CHAINS = [
    # Major grocery chains
    'Whole Foods',
    'Stop & Shop',
    'Stop and Shop',
    'Target',
    'Walmart',
    'Kroger',
    'Safeway',
    'Albertsons',
    'Publix',
    "Trader Joe's",
    'Sprouts Farmers Market',
    'Wegmans',
    'The Fresh Market',
    'H-E-B',
    'Costco',
    "Sam's Club",
    "Raley's",
    'Vons',
    'Pavilions',
    'Ralphs',
    "Lassen's",
    'Hy-Vee',
    'Erewhon',
    'Aldi',
    'Food Lion',
    'Giant Eagle',
    'Meijer',
    'ShopRite',
    'Winn-Dixie',
    'Piggly Wiggly',
    'Food 4 Less',
    'Fred Meyer',
    'Harris Teeter',
    'Jewel-Osco',
    'King Soopers',
    "Fry's Food",
    'QFC',
    "Smith's",
    'Acme Markets',
    'Giant Food',
    'Giant',
    'Market Basket',
    'Price Chopper',
    'Hannaford',
    'Big Y',
    'Stater Bros',
    'WinCo',
    'Grocery Outlet',
    'Save Mart',
    'Lucky',
    'Foodtown',
    'Key Food',
    'Associated Supermarkets',
    'C-Town',
    'Compare Foods',
    'Food Bazaar',
    'Western Beef',
    'Bravo Supermarkets',
    'Sedano\'s',
    'Northgate Market',
    'Cardenas',
    'Superior Grocers',
    'El Super',
    'Vallarta Supermarkets',

    # Drugstores
    'CVS',
    'Walgreens',
    'Rite Aid',

    # Convenience stores
    '7-Eleven',
    'Circle K',
    'Wawa',
    'Sheetz',
    'QuikTrip',
    'RaceTrac',
    'Speedway',
    'Casey\'s',
    'Kum & Go',
    'Pilot Flying J',
    'Love\'s Travel',
    'Buc-ee\'s',

    # Club stores
    "BJ's Wholesale",

    # General retail
    "Lowe's",
    'LOWES',  # Hardware store variant without apostrophe
    'Home Depot',
    'GNC',
    'Vitamin Shoppe',

    # Online/delivery
    'Instacart',
    'Amazon Fresh',
    'FreshDirect',
    'H E B',
    'HEB',
    'Go Puff',
    'GoPuff',
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
