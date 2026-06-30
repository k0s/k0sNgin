#!/bin/bash
# Simple site scanner using wget and curl
# Usage: ./scan_site.sh http://cephalopod.ink

BASE_URL="${1:-http://localhost:8000}"
BASE_URL="${BASE_URL%/}"

echo "Scanning $BASE_URL..."
echo "============================================================"

# Check security endpoints
echo ""
echo "🔒 Checking Security Endpoints:"
echo "------------------------------------------------------------"

for endpoint in /docs /redoc /openapi.json /openapi.yaml; do
    status=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL$endpoint")
    if [ "$status" = "200" ]; then
        echo "⚠️  $endpoint: $status (SHOULD BE DISABLED!)"
    elif [ "$status" = "404" ]; then
        echo "✅ $endpoint: $status (correctly disabled)"
    else
        echo "ℹ️  $endpoint: $status"
    fi
done

echo ""
echo "📥 Downloading site structure (this may take a moment)..."
echo "------------------------------------------------------------"

# Use wget to recursively download (if available)
if command -v wget &> /dev/null; then
    DOWNLOAD_DIR="site_scan_$(date +%s)"
    mkdir -p "$DOWNLOAD_DIR"
    cd "$DOWNLOAD_DIR"

    wget --recursive \
         --no-parent \
         --no-host-directories \
         --cut-dirs=0 \
         --level=3 \
         --accept=html,json,txt,md,css,js \
         --quiet \
         --show-progress \
         "$BASE_URL" 2>&1 | tail -5

    cd ..
    echo ""
    echo "📊 Files downloaded to: $(pwd)/$DOWNLOAD_DIR"
    echo ""
    echo "To see all files:"
    echo "  find $DOWNLOAD_DIR -type f"
    echo ""
    echo "File count: $(find "$DOWNLOAD_DIR" -type f | wc -l) files"
else
    echo "⚠️  wget not found. Install it for full site mirroring:"
    echo "  sudo apt-get install wget  # Debian/Ubuntu"
    echo "  brew install wget          # macOS"
    echo ""
    echo "Or use the Python scanner: python scripts/scan_site.py $BASE_URL"
fi

echo ""
echo "🚦 Testing Rate Limiting:"
echo "------------------------------------------------------------"
echo "Making 70 rapid requests to test rate limiting (limit is 60/min)..."
rate_limited=false
for i in {1..70}; do
    status=$(curl -s -o /dev/null -w "%{http_code}" "$BASE_URL/")
    if [ "$status" = "429" ]; then
        echo "✅ Rate limiting triggered after $i requests"
        rate_limited=true
        break
    fi
    # Make requests quickly to test rate limit
    sleep 0.05
done

if [ "$rate_limited" = false ]; then
    echo "ℹ️  No rate limit triggered in 70 requests"
    echo "   (This might be normal if requests are spread over time)"
fi
