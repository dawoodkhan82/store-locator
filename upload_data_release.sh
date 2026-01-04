#!/bin/bash
#
# Upload combined.json to Cloudflare R2
#
# This script uploads the combined.json file to a Cloudflare R2 bucket.
# R2 is S3-compatible, so we use the AWS CLI with R2 endpoint.
#
# Prerequisites:
#   - AWS CLI installed (brew install awscli)
#   - Environment variables set (see below)
#   - combined.json exists in all_stores/combined/
#
# Required Environment Variables (add to .env file or export):
#   R2_ACCESS_KEY_ID     - Your R2 API token access key
#   R2_SECRET_ACCESS_KEY - Your R2 API token secret key
#   R2_ACCOUNT_ID        - Your Cloudflare account ID
#   R2_BUCKET_NAME       - Your R2 bucket name
#
# To get these credentials:
#   1. Go to Cloudflare Dashboard > R2 > Manage R2 API Tokens
#   2. Create a new API token with "Object Read & Write" permissions
#   3. Copy the Access Key ID and Secret Access Key
#   4. Your Account ID is in the URL: dash.cloudflare.com/<ACCOUNT_ID>/r2
#
# Usage:
#   ./upload_data_release.sh
#

set -e

DATA_FILE="all_stores/combined/combined.json"

# Load .env file if it exists
if [ -f ".env" ]; then
    echo "Loading environment from .env file..."
    export $(grep -v '^#' .env | xargs)
fi

# Check required environment variables
if [ -z "$R2_ACCESS_KEY_ID" ]; then
    echo "Error: R2_ACCESS_KEY_ID is not set."
    echo "Add it to .env file or export it."
    exit 1
fi

if [ -z "$R2_SECRET_ACCESS_KEY" ]; then
    echo "Error: R2_SECRET_ACCESS_KEY is not set."
    echo "Add it to .env file or export it."
    exit 1
fi

if [ -z "$R2_ACCOUNT_ID" ]; then
    echo "Error: R2_ACCOUNT_ID is not set."
    echo "Add it to .env file or export it."
    exit 1
fi

if [ -z "$R2_BUCKET_NAME" ]; then
    echo "Error: R2_BUCKET_NAME is not set."
    echo "Add it to .env file or export it."
    exit 1
fi

# Check if aws cli is installed
if ! command -v aws &> /dev/null; then
    echo "Error: AWS CLI is not installed."
    echo "Install it with: brew install awscli"
    exit 1
fi

# Check if data file exists
if [ ! -f "$DATA_FILE" ]; then
    echo "Error: $DATA_FILE not found."
    echo "Run combine_all_stores.py first to generate the file."
    exit 1
fi

# Get file size and store count
FILE_SIZE=$(ls -lh "$DATA_FILE" | awk '{print $5}')
STORE_COUNT=$(python3 -c "import json; print(len(json.load(open('$DATA_FILE'))['stores']))")

echo "========================================"
echo "Uploading Store Data to Cloudflare R2"
echo "========================================"
echo ""
echo "File: $DATA_FILE"
echo "Size: $FILE_SIZE"
echo "Stores: $STORE_COUNT"
echo "Bucket: $R2_BUCKET_NAME"
echo ""

# R2 endpoint
R2_ENDPOINT="https://${R2_ACCOUNT_ID}.r2.cloudflarestorage.com"

# Upload to R2 using AWS CLI with S3 compatibility
echo "Uploading to R2..."
AWS_ACCESS_KEY_ID="$R2_ACCESS_KEY_ID" \
AWS_SECRET_ACCESS_KEY="$R2_SECRET_ACCESS_KEY" \
aws s3 cp "$DATA_FILE" "s3://${R2_BUCKET_NAME}/combined.json" \
    --endpoint-url "$R2_ENDPOINT" \
    --content-type "application/json"

echo ""
echo "Done! File uploaded successfully."
echo ""
echo "Public URL: https://pub-d99370c7254e4d15a17f3ee6c25072ca.r2.dev/combined.json"
echo ""
echo "Note: Make sure your R2 bucket has public access enabled:"
echo "  Cloudflare Dashboard > R2 > Your Bucket > Settings > Public Access"
