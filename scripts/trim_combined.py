#!/usr/bin/env python3
"""
Trim combined.json to only include fields used by the frontend.
Reduces ~190 MB down to ~15-20 MB by stripping unused geoapify/google_places data.
"""

import json
import os
import sys

INPUT = "all_stores/combined/combined.json"
OUTPUT = "all_stores/combined/combined_trimmed.json"

# Top-level fields to keep per store
KEEP_TOP_LEVEL = {
    "id", "name", "displayName", "lat", "lng",
    "phone", "internationalPhoneNumber", "email",
    "url", "website", "websiteUri",
    "address", "display_address", "address_line_1", "formattedAddress", "streetaddress",
    "city", "state", "state_code", "postcode", "postal_code", "zip", "country",
    "brand", "brands", "source", "scraped_at",
    "rating", "userRatingCount", "googleMapsUri",
    "instagram", "facebook", "x_twitter",
    # These are kept as-is (small)
    "enrichment",
}

# geoapify.geocoding fields to keep
KEEP_GEOAPIFY_GEOCODING = {"formatted", "state_code", "postcode", "city"}

# google_places fields to keep
KEEP_GOOGLE_PLACES = {
    "rating", "userRatingCount", "googleMapsUri",
    "websiteUri", "internationalPhoneNumber", "nationalPhoneNumber",
}


def trim_geoapify(geoapify):
    if not isinstance(geoapify, dict):
        return None
    geocoding = geoapify.get("geocoding")
    if not isinstance(geocoding, dict):
        return None
    trimmed = {k: v for k, v in geocoding.items() if k in KEEP_GEOAPIFY_GEOCODING}
    return {"geocoding": trimmed} if trimmed else None


def trim_google_places(gp):
    if not isinstance(gp, dict):
        return None
    trimmed = {k: v for k, v in gp.items() if k in KEEP_GOOGLE_PLACES}
    return trimmed if trimmed else None


def trim_store(store):
    result = {}
    for key, value in store.items():
        if key == "geoapify":
            trimmed = trim_geoapify(value)
            if trimmed:
                result["geoapify"] = trimmed
        elif key == "google_places":
            trimmed = trim_google_places(value)
            if trimmed:
                result["google_places"] = trimmed
        elif key == "locations" and isinstance(value, list):
            trimmed_locs = []
            for loc in value:
                if isinstance(loc, dict):
                    trimmed_loc = trim_store(loc)  # recursive, same rules
                    trimmed_locs.append(trimmed_loc)
            if trimmed_locs:
                result["locations"] = trimmed_locs
        elif key in KEEP_TOP_LEVEL:
            result[key] = value
        # else: drop the field
    return result


def main():
    input_path = INPUT
    output_path = OUTPUT

    if len(sys.argv) > 1:
        input_path = sys.argv[1]
    if len(sys.argv) > 2:
        output_path = sys.argv[2]

    input_size = os.path.getsize(input_path)
    print(f"Reading {input_path} ({input_size / 1024 / 1024:.1f} MB)...")

    with open(input_path) as f:
        data = json.load(f)

    stores = data.get("stores", [])
    print(f"Trimming {len(stores)} stores...")

    trimmed_stores = [trim_store(s) for s in stores]

    output_data = {
        "metadata": data.get("metadata", {}),
        "stores": trimmed_stores,
    }

    print(f"Writing {output_path}...")
    with open(output_path, "w") as f:
        json.dump(output_data, f, separators=(",", ":"))

    output_size = os.path.getsize(output_path)
    print(f"Done! {input_size / 1024 / 1024:.1f} MB -> {output_size / 1024 / 1024:.1f} MB "
          f"({(1 - output_size / input_size) * 100:.0f}% reduction)")


if __name__ == "__main__":
    main()
