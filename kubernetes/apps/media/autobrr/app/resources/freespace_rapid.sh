#!/bin/bash

# 1. Check if required environment variables are set
if [[ -z "$DASHBOARD_URL" || -z "$DASHBOARD_LOGIN" || -z "$DASHBOARD_PASSWORD" ]]; then
    echo "Error: Missing environment variables."
    echo "Usage: DASHBOARD_URL='https://your-domain.com' DASHBOARD_LOGIN='...' DASHBOARD_PASSWORD='...' ./check_disk.sh"
    exit 2
fi

THRESHOLD=90
# Define the specific path to the data
DATA_PATH="/widgets/disk_data.php"

# 2. Construct the full URL
# ${DASHBOARD_URL%/} removes a trailing slash if the user included one.
FULL_URL="${DASHBOARD_URL%/}${DATA_PATH}"

# 3. Get the data using curl with Basic Auth
RESPONSE=$(curl -s -u "$DASHBOARD_LOGIN:$DASHBOARD_PASSWORD" "$FULL_URL")

# Check if curl failed (e.g., DNS error, connection refused)
if [ $? -ne 0 ]; then
    echo "Error: Failed to connect to $FULL_URL"
    exit 2
fi

# 4. Extract the percentage
# Finds "You have used X%" and strips it down to just the number.
PERCENTAGE=$(echo "$RESPONSE" | grep -o "You have used [0-9.]*%" | sed 's/[^0-9.]//g')

# Check if we successfully extracted a number (handles 404s or bad logins returning HTML without the specific data)
if [ -z "$PERCENTAGE" ]; then
    echo "Error: Could not find disk usage percentage. Check credentials or if URL is correct."
    echo "Attempted URL: $FULL_URL"
    exit 2
fi

# 5. Compare the value using awk
RESULT=$(awk -v p="$PERCENTAGE" -v t="$THRESHOLD" 'BEGIN {print (p > t) ? 1 : 0}')

if [ "$RESULT" -eq 1 ]; then
    # echo "CRITICAL: Disk usage is ${PERCENTAGE}% (Threshold: ${THRESHOLD}%)"
    exit 1
else
    # echo "OK: Disk usage is ${PERCENTAGE}% (Threshold: ${THRESHOLD}%)"
    exit 0
fi