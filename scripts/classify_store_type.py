#!/usr/bin/env python3
"""
Store Type Classifier

Classifies stores into one of a fixed set of store types based on:
1. Rule-based chain name matching (fast, covers major chains)
2. Heuristic matching on categories/specialties/aboutText
3. Name-based heuristic fallback
4. Brand-source inference for unenriched stores from CPG brand locators

Store Types (with Grocery and Other subtypes):
  Grocery:
    - Supermarket
    - Warehouse Club
    - Discount Grocery
    - Specialty/Gourmet Grocery
    - International Grocery
    - Independent Grocery
  Other:
    - Retail/Department Store
    - Outdoor/Sporting Goods
    - Juice/Smoothie Bar
    - Butcher/Meat Shop
    - Pharmacy/Drug Store
    - Hotel/Hospitality
    - Delivery Service
    - Uncategorized
  Specialty:
    - Natural/Organic Market
    - Boutique Grocer
    - Co-op
    - Convenience Store
    - Coffee Shop/Cafe
    - Wine/Beer/Liquor
    - Bakery
    - Deli/Prepared Foods
    - Health/Supplement Store
    - Gift/Specialty Shop
    - Farmers Market
    - Restaurant/Eatery
    - Gas Station/Travel Stop
"""

import json

# ── Fixed store type taxonomy ──
STORE_TYPES = [
    # Grocery subtypes
    "Supermarket",
    "Warehouse Club",
    "Discount Grocery",
    "Specialty/Gourmet Grocery",
    "International Grocery",
    "Independent Grocery",
    # Specialty store types
    "Natural/Organic Market",
    "Boutique Grocer",
    "Co-op",
    "Convenience Store",
    "Coffee Shop/Cafe",
    "Wine/Beer/Liquor",
    "Bakery",
    "Deli/Prepared Foods",
    "Health/Supplement Store",
    "Gift/Specialty Shop",
    "Farmers Market",
    "Restaurant/Eatery",
    "Gas Station/Travel Stop",
    # Other subtypes
    "Retail/Department Store",
    "Outdoor/Sporting Goods",
    "Juice/Smoothie Bar",
    "Butcher/Meat Shop",
    "Pharmacy/Drug Store",
    "Hotel/Hospitality",
    "Delivery Service",
    "Uncategorized",
]

# ── Rule-based chain matching (case-insensitive) ──
# Maps lowercased store name patterns to store types
CHAIN_RULES = {
    # ── Grocery subtypes ──

    # Warehouse Clubs (check before Supermarket since some names overlap)
    "Warehouse Club": [
        "costco", "sam's club", "sams club", "bj's", "bjs wholesale",
    ],

    # Discount Grocery
    "Discount Grocery": [
        "aldi", "lidl", "grocery outlet", "food 4 less",
        "save-a-lot", "save a lot", "ruler foods", "price rite",
        "pricerite", "price cutter",
    ],

    # International Grocery
    "International Grocery": [
        "99 ranch", "h mart", "hmart", "mitsuwa", "uwajimaya",
        "zion market", "ranch market", "super king",
        "patel brothers", "lotte plaza", "seafood city",
        "fiesta mart", "el super", "cardenas", "vallarta",
        "northgate market", "la michoacana", "asia market",
        "asian market", "india market", "indian grocery",
        "korean market", "chinese market", "japanese market",
        "middle eastern", "mediterranean market",
    ],

    # Specialty/Gourmet Grocery
    "Specialty/Gourmet Grocery": [
        "world market", "cost plus", "fresh market", "the fresh market",
        "dean & deluca", "williams sonoma", "williams-sonoma",
        "sur la table", "balducci",
    ],

    # Supermarket (large national & regional chains)
    "Supermarket": [
        "publix", "kroger", "safeway", "albertsons", "heb", "h e b",
        "h-e-b", "meijer", "wegmans", "wegman's",
        "hy-vee", "hy vee", "hyvee",
        "giant eagle", "giant food", "giant",
        "stop & shop", "stop and shop",
        "shoprite", "food lion", "harris teeter", "fred meyer",
        "king soopers", "ralphs", "ralph's", "vons",
        "jewel", "jewel-osco",
        "acme", "winn dixie", "winn-dixie", "piggly wiggly",
        "bi-lo", "bilo", "food city", "ingles", "stater bros",
        "winco", "winco foods",
        "save mart", "savemart",
        "big y", "bigy", "price chopper", "market basket", "hannaford",
        "shaw's", "shaws", "dierbergs", "schnucks", "brookshire",
        "fareway", "iga", "foodtown", "key food", "associated",
        "c-town", "ctown", "compare foods", "bravo supermarket",
        "shoppers food", "foodarama", "food bazaar", "food emporium",
        "pathmark", "a&p", "tops markets", "tops friendly",
        "tom thumb", "randalls", "pavilions",
        "lucky supermarkets", "lucky's", "market street",
        "united supermarkets", "weis markets", "coborn's", "coborns",
        "festival foods", "pick n save", "pick 'n save",
        "raley's", "raleys", "nob hill foods", "bel air",
        "mariano's", "marianos", "sendik's", "sendiks",
        "woodman's", "woodmans", "mccaffrey's", "mccaffreys",
        "urm stores", "haggen", "rosauers", "harmons",
        "smart & final",
        "target", "walmart", "walmart supercenter",
        "walmart neighborhood",
        "martin's", "martins",
        "roberts fresh market", "hollywood markets",
        "clark's market", "fry's", "fry's marketplace",
        "fry's food", "frys food",
        "smith's", "smiths", "smith's marketplace",
        "dillons", "dillon's", "rouses", "rouses market",
        "quality food center", "qfc", "roundy's", "roundys",
        "super 1 foods", "cub foods", "family fare",
        "king kullen", "kings", "food maxx",
        "market district", "market 32", "nugget market",
        "heinen's", "heinens", "maceys", "macey's grocers",
        "roche bros", "busch's market", "buschs",
        "cash wise", "cashwise", "morton williams",
        "strack and van til", "strack & van til",
        "foodland", "town & country",
        "lunds & byerlys", "lunds",
        "reasors", "srs north", "metro market",
        "betterhealth market",
        "harps", "carrs", "gristedes", "kowalski's", "kowalskis",
        "mollie stone's", "mollie stones",
        "nob hill", "broulims", "berkots",
        "hornbachers", "angelo caputo", "hen house",
        "fruitful yield", "dollar fresh", "econo", "selectos",
        "pueblo", "grade a", "new leaf", "nugget",
        "tops", "certified", "amigo", "rays",
        "homeland",
        "uncle giuseppe", "milams", "north shore farms",
        "manassero farms",
    ],

    # ── Specialty store types ──

    # Natural/Organic Markets
    "Natural/Organic Market": [
        "whole foods", "sprouts", "sprouts farmers", "natural grocers",
        "earth fare", "fresh thyme", "mother's market", "mothers market",
        "new seasons", "lazy acres", "mrs green's", "mrs greens",
        "lassens", "lassen's", "jimbo's", "jimbos",
        "central market", "erewhon", "bristol farms",
        "gelson's", "gelsons",
        "huckleberry's", "huckleberrys",
        "mom's organic", "natural food store", "green goddess",
        "organic market", "down to earth",
    ],

    # Co-ops
    "Co-op": [
        "co-op", "coop", "cooperative", "food co op",
        "community market",
    ],

    # Convenience Stores
    "Convenience Store": [
        "7-eleven", "7 eleven", "7eleven", "wawa", "sheetz",
        "circle k", "casey's", "caseys", "kwik trip", "kum & go",
        "kum and go", "racetrac", "quiktrip", "qt ", "speedway",
        "cumberland farms", "rutters", "rutter's",
        "royal farms", "rofo", "buc-ee's", "buc-ees", "bucees",
        "fast & fresh", "express mart", "mini mart", "minimart",
        "ampm", "am/pm", "maverik", "thorntons", "loaf n jug",
        "kwik shop", "quik stop", "fastrac", "jiffy mart",
        "mapco", "stripes", "alltown", "on the run",
    ],

    # Coffee Shop/Cafe
    "Coffee Shop/Cafe": [
        "starbucks", "peet's", "peets", "dunkin", "coffee",
        "coffeebar", "cafe ", "café", "espresso",
        "roasters", "roastery",
    ],

    # Wine/Beer/Liquor
    "Wine/Beer/Liquor": [
        "wine", "liquor", "spirits", "beer co", "taproom",
        "bottle shop", "beverage depot", "vinovore",
        "total wine", "binny's", "binnys", "spec's", "specs",
        "bevmo",
    ],

    # Bakery
    "Bakery": [
        "bakery", "bakehouse", "bake shop", "patisserie",
        "bread ", "donut", "doughnut",
    ],

    # Deli/Prepared Foods
    "Deli/Prepared Foods": [
        "deli", "delicatessen", "prepared foods",
        "provisions",
    ],

    # Health/Supplement Store
    "Health/Supplement Store": [
        "vitamin", "gnc", "supplement", "health food",
        "nutrition", "apothecary", "health hut",
    ],

    # Gas Station/Travel Stop
    "Gas Station/Travel Stop": [
        "petro", "flying j", "pilot ", "love's", "loves travel",
        "ta travel", "travel center", "truck stop",
        "gas station", "fuel", "nouria", "shell",
        "mobil", "bp ",
    ],

    # Restaurant/Eatery
    "Restaurant/Eatery": [
        "restaurant", "grill ", "grille", "bistro",
        "eatery", "dining", "pizzeria", "taqueria",
    ],

    # Gift/Specialty Shop
    "Gift/Specialty Shop": [
        "gift shop", "boutique", "curiosities",
        "general store",
    ],

    # Farmers Market
    "Farmers Market": [
        "farmers market", "farmer's market", "farm stand",
        "farmstand",
    ],

    # ── Other subtypes ──

    # Retail/Department Store
    "Retail/Department Store": [
        "urban outfitters", "nordstrom", "anthropolog",
        "homegoods", "home goods", "bed bath",
        "popshelf", "the paper store",
        "it's sugar", "its sugar",
    ],

    # Outdoor/Sporting Goods
    "Outdoor/Sporting Goods": [
        "rei ", "rei\t", "backcountry",
    ],

    # Juice/Smoothie Bar
    "Juice/Smoothie Bar": [
        "juice press", "pure green", "juice bar",
        "jamba", "smoothie", "juicery", "squeeze",
        "pressed juicery",
    ],

    # Butcher/Meat Shop
    "Butcher/Meat Shop": [
        "butcher", "meat shop", "meat market",
        "new york butcher",
    ],

    # Pharmacy/Drug Store
    "Pharmacy/Drug Store": [
        "pharmacy", "drug emporium", "cvs", "walgreens",
        "rite aid",
    ],

    # Hotel/Hospitality
    "Hotel/Hospitality": [
        "omni hotel", "marriott", "hilton", "hyatt",
        "hotel ", "resort",
    ],

    # Delivery Service
    "Delivery Service": [
        "doordash", "gopuff", "go puff", "instacart",
        "uber eats", "grubhub",
    ],
}

# Name-based heuristics for stores without enrichment data
NAME_HEURISTIC_RULES = {
    "Supermarket": [
        "grocery", "supermarket", "food store",
        "super ", "foods",
    ],
    "Independent Grocery": [
        "market", "mart", "fresh ",
    ],
    "Natural/Organic Market": [
        "organic", "natural", "health market", "whole ",
    ],
    "Convenience Store": [
        "convenience", "quick stop", "ez mart",
    ],
    "Coffee Shop/Cafe": [
        "coffee", "cafe", "café", "tea ",
    ],
    "Bakery": [
        "bakery", "bake",
    ],
    "Deli/Prepared Foods": [
        "deli ",
    ],
    "Health/Supplement Store": [
        "vitamin", "health & nutrition", "health and nutrition",
    ],
    "Wine/Beer/Liquor": [
        "wine", "liquor", "beer", "beverage",
    ],
    "Farmers Market": [
        "farm stand", "farmers market",
    ],
    "Butcher/Meat Shop": [
        "butcher",
    ],
    "Juice/Smoothie Bar": [
        "juice", "smoothie",
    ],
}

# Keywords in categories/specialties/about that suggest store types (for heuristic pass)
HEURISTIC_RULES = {
    "Natural/Organic Market": {
        "categories": {"organic", "natural foods", "vitamins & body care", "bulk", "supplements"},
        "specialties": {"organic", "natural", "non-gmo", "holistic", "wellness", "health-focused"},
        "about_keywords": ["organic", "natural foods", "health food", "natural grocery"],
        "threshold": 3,
    },
    "Boutique Grocer": {
        "categories": {"gourmet", "artisan", "local products", "specialty"},
        "specialties": {"curated", "artisanal", "emerging brands", "small-batch", "gourmet", "boutique"},
        "about_keywords": ["curated", "artisan", "boutique", "specialty grocery", "independent", "emerging brands", "small brands"],
        "threshold": 2,
    },
    "Coffee Shop/Cafe": {
        "categories": {"coffee", "espresso", "tea", "pastries"},
        "specialties": {"coffee", "espresso", "roasted", "barista", "latte"},
        "about_keywords": ["coffee", "cafe", "coffeebar", "espresso", "roast"],
        "threshold": 2,
    },
    "Wine/Beer/Liquor": {
        "categories": {"wine", "beer", "spirits", "liquor", "beer & wine"},
        "specialties": {"wine", "craft beer", "spirits", "sommelier", "winemaker"},
        "about_keywords": ["wine", "beer", "spirits", "liquor", "brewery", "winery"],
        "threshold": 2,
    },
    "Bakery": {
        "categories": {"bakery", "pastries", "bread", "cakes", "donuts"},
        "specialties": {"baked", "pastry", "sourdough", "artisan bread"},
        "about_keywords": ["bakery", "baked", "bread", "pastry", "donut", "doughnut"],
        "threshold": 2,
    },
    "Health/Supplement Store": {
        "categories": {"vitamins", "supplements", "dietary supplements", "health & wellness"},
        "specialties": {"supplements", "vitamins", "adaptogenic", "wellness", "health-focused"},
        "about_keywords": ["supplement", "vitamin", "health food store", "nutrition store"],
        "threshold": 2,
    },
    "Deli/Prepared Foods": {
        "categories": {"deli", "sandwiches", "prepared foods", "prepared meals", "hot foods", "salads"},
        "specialties": {"prepared foods", "deli", "catering"},
        "about_keywords": ["deli", "sandwich", "prepared food"],
        "threshold": 2,
    },
    "Convenience Store": {
        "categories": {"convenience", "snacks", "tobacco"},
        "specialties": {"convenience", "24/7 service", "24 hours", "24/7"},
        "about_keywords": ["convenience store", "convenient", "24/7", "open 24"],
        "threshold": 2,
    },
    "Restaurant/Eatery": {
        "categories": {"restaurant", "dining", "entrees", "appetizers"},
        "specialties": {"dining", "restaurant", "chef-driven"},
        "about_keywords": ["restaurant", "dining", "eatery", "bistro"],
        "threshold": 2,
    },
    "Juice/Smoothie Bar": {
        "categories": {"juices", "smoothies", "acai bowls", "cold pressed"},
        "specialties": {"juice", "smoothie", "cold-pressed", "acai"},
        "about_keywords": ["juice", "smoothie", "cold pressed", "juicery"],
        "threshold": 2,
    },
    "Outdoor/Sporting Goods": {
        "categories": {"camping", "climbing", "cycling", "hiking", "paddling", "skiing"},
        "specialties": {"outdoor", "expert advice", "outdoor equity"},
        "about_keywords": ["outdoor", "gear", "camping", "hiking"],
        "threshold": 3,
    },
    "Retail/Department Store": {
        "categories": {"womens", "mens", "juniors", "home décor", "furniture"},
        "specialties": {"designer", "fashion", "luxury"},
        "about_keywords": ["clothing", "fashion", "home decor", "furniture"],
        "threshold": 2,
    },
    "Hotel/Hospitality": {
        "categories": {"rooms", "suites", "spa", "resort"},
        "specialties": {"luxury", "hospitality", "amenity-rich"},
        "about_keywords": ["hotel", "resort", "hospitality", "suites"],
        "threshold": 2,
    },
    # Supermarket heuristic (high threshold - needs many grocery signals)
    "Supermarket": {
        "categories": {"produce", "dairy", "meat", "bakery", "seafood", "frozen foods", "grocery", "deli"},
        "specialties": {"local", "sustainable", "prepared foods"},
        "about_keywords": ["grocery", "supermarket", "one-stop"],
        "threshold": 4,
    },
}

# Brands from CPG store locators — stores carrying these brands are
# almost certainly independent grocery/specialty stores
CPG_BRAND_SOURCES = {
    "fish_wife", "brightland", "spice_walla", "masa_chips",
    "stellar_snacks", "behave", "unreal_snacks", "fly_by_jing",
    "rishi_tea", "graza", "zabs_hot_sauce", "freestyle_snacking",
    "evies_snacks", "alice_mushrooms", "realsy", "a_dozen_cousins",
    "joon", "diaspora_co", "whims", "one_trick_pony", "chomps",
    "coconut_cult", "smash_foods", "neuro_gum", "floura", "loisa",
    "bjorn_qorn", "glonuts", "btr_bar", "bon_bon_swedish_candy",
    "narra", "hormbles_chormbles", "blobs", "cauli_puffs",
    "hot_girl_pickles", "chikka_chikka", "shuug", "rooted_fare",
    "brez", "pistakio", "munchrooms", "zaza_snacks", "flings",
    "drumroll_donuts", "droosh", "date_better_stores",
    "better_sour_stores", "the_only_bean", "yolele",
    "stuzzi", "transcendence_coffee", "everyday_dose",
    "culture_pop", "clevr_blends", "doosra", "sauz",
    "bezi",
}


def classify_by_chain_name(name):
    """Classify store by matching against known chain names."""
    if not name:
        return None
    name_lower = name.lower().strip()

    # Special case: exact match "REI" (avoid matching words containing "rei")
    if name_lower == "rei" or name_lower.startswith("rei "):
        return "Outdoor/Sporting Goods"

    for store_type, patterns in CHAIN_RULES.items():
        for pattern in patterns:
            if pattern in name_lower:
                return store_type
    return None


def classify_by_name_heuristic(name):
    """Classify store by generic name keywords (fallback for unenriched stores)."""
    if not name:
        return None
    name_lower = name.lower().strip()
    for store_type, patterns in NAME_HEURISTIC_RULES.items():
        for pattern in patterns:
            if pattern in name_lower:
                return store_type
    return None


def classify_by_heuristics(store):
    """Classify store by scoring categories, specialties, and aboutText."""
    enrichment = store.get('enrichment', {}) or {}
    categories = set(c.lower() for c in (enrichment.get('productCategories') or []) if c)
    specialties = set(s.lower() for s in (enrichment.get('specialties') or []) if s)
    about = (enrichment.get('aboutText') or '').lower()
    name = (store.get('name') or store.get('displayName', {}).get('text') or '').lower()

    best_type = None
    best_score = 0

    for store_type, rules in HEURISTIC_RULES.items():
        score = 0

        # Category matches
        rule_cats = {c.lower() for c in rules.get("categories", set())}
        score += len(categories & rule_cats)

        # Specialty matches
        rule_specs = {s.lower() for s in rules.get("specialties", set())}
        score += len(specialties & rule_specs)

        # About text keyword matches
        for keyword in rules.get("about_keywords", []):
            if keyword in about:
                score += 1.5
            if keyword in name:
                score += 1

        if score >= rules.get("threshold", 2) and score > best_score:
            best_score = score
            best_type = store_type

    return best_type


def classify_by_brand_source(store):
    """
    Classify stores from CPG brand store locators as Independent Grocery.
    These are stores that carry indie CPG brands but have no website enrichment.
    """
    brand = store.get('brand') or store.get('source') or ''
    if brand in CPG_BRAND_SOURCES:
        return "Independent Grocery"
    return None


def classify_store(store):
    """
    Classify a single store into a store type.

    Priority:
    1. Chain name matching (fast, deterministic)
    2. Heuristic scoring on enrichment data
    3. Name-based heuristic
    4. Brand source inference (CPG brand locator stores → Independent Grocery)
    5. Default to "Uncategorized"

    Returns the store type string.
    """
    name = store.get('name') or store.get('displayName', {}).get('text') or ''

    # Step 1: Chain name match
    store_type = classify_by_chain_name(name)
    if store_type:
        return store_type

    # Step 2: Heuristic scoring on enrichment data
    store_type = classify_by_heuristics(store)
    if store_type:
        return store_type

    # Step 3: Name-based heuristic (for unenriched stores)
    store_type = classify_by_name_heuristic(name)
    if store_type:
        return store_type

    # Step 4: Brand source inference
    store_type = classify_by_brand_source(store)
    if store_type:
        return store_type

    # Step 5: Default
    return "Uncategorized"


def classify_stores(stores):
    """
    Classify a list of stores, adding 'storeType' to each store's enrichment.

    Args:
        stores: List of store dictionaries

    Returns:
        dict: Counts of each store type assigned
    """
    from collections import Counter
    type_counts = Counter()

    for store in stores:
        store_type = classify_store(store)

        # Add to enrichment
        if 'enrichment' not in store:
            store['enrichment'] = {}
        store['enrichment']['storeType'] = store_type

        type_counts[store_type] += 1

    return type_counts


if __name__ == '__main__':
    import sys

    if len(sys.argv) < 2:
        print("Usage: python classify_store_type.py <combined.json> [output.json]")
        print("\nClassifies all stores and adds storeType to enrichment data.")
        sys.exit(1)

    input_file = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else input_file

    print("=" * 80)
    print("STORE TYPE CLASSIFIER")
    print("=" * 80)

    with open(input_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    stores = data.get('stores', [])
    print(f"\nLoaded {len(stores):,} stores from {input_file}")

    type_counts = classify_stores(stores)

    print(f"\nClassification results:")
    print("-" * 50)
    for store_type in STORE_TYPES:
        count = type_counts.get(store_type, 0)
        if count > 0:
            pct = count / len(stores) * 100 if stores else 0
            print(f"  {store_type:<30} {count:>6,}  ({pct:>5.1f}%)")
    print("-" * 50)
    print(f"  {'TOTAL':<30} {len(stores):>6,}")

    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, separators=(',', ':'))

    print(f"\nSaved to {output_file}")
