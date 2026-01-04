#!/bin/bash
#
# Upload combined.json to GitHub Releases
#
# This script creates/updates a GitHub release with the latest combined.json file.
# The release is tagged as "data-latest" and is always overwritten with new data.
#
# Prerequisites:
#   - GitHub CLI (gh) installed and authenticated
#   - combined.json exists in all_stores/combined/
#
# Usage:
#   ./upload_data_release.sh
#

set -e

DATA_FILE="all_stores/combined/combined.json"
RELEASE_TAG="data-latest"
RELEASE_TITLE="Store Data (Latest)"

# Check if gh is installed
if ! command -v gh &> /dev/null; then
    echo "Error: GitHub CLI (gh) is not installed."
    echo "Install it with: brew install gh"
    exit 1
fi

# Check if authenticated
if ! gh auth status &> /dev/null; then
    echo "Error: Not authenticated with GitHub CLI."
    echo "Run: gh auth login"
    exit 1
fi

# Check if data file exists
if [ ! -f "$DATA_FILE" ]; then
    echo "Error: $DATA_FILE not found."
    echo "Run combine_all_stores.py first to generate the file."
    exit 1
fi

# Get file size
FILE_SIZE=$(ls -lh "$DATA_FILE" | awk '{print $5}')
STORE_COUNT=$(python3 -c "import json; print(len(json.load(open('$DATA_FILE'))['stores']))")

echo "========================================"
echo "Uploading Store Data to GitHub Releases"
echo "========================================"
echo ""
echo "File: $DATA_FILE"
echo "Size: $FILE_SIZE"
echo "Stores: $STORE_COUNT"
echo "Release tag: $RELEASE_TAG"
echo ""

# Delete existing release if it exists
echo "Checking for existing release..."
if gh release view "$RELEASE_TAG" &> /dev/null; then
    echo "Deleting existing release..."
    gh release delete "$RELEASE_TAG" --yes
fi

# Create new release with the data file
echo "Creating new release..."
gh release create "$RELEASE_TAG" \
    "$DATA_FILE" \
    --title "$RELEASE_TITLE" \
    --notes "Store data updated on $(date '+%Y-%m-%d %H:%M:%S')

**Statistics:**
- Total stores: $STORE_COUNT
- File size: $FILE_SIZE

This release is automatically updated when new store data is available."

echo ""
echo "Done! Release created successfully."
echo ""
echo "View release: gh release view $RELEASE_TAG"
echo "Download URL: https://github.com/$(gh repo view --json nameWithOwner -q .nameWithOwner)/releases/download/$RELEASE_TAG/combined.json"
