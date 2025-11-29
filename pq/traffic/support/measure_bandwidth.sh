#!/bin/bash
# Measure average bandwidth on port 4160 using iptables
# Usage: ./measure_bandwidth.sh [duration_seconds]

PORT=4160
DURATION=${1:-60}  # Default 60 seconds if not specified
INTERVAL=1

if ! [[ "$DURATION" =~ ^[0-9]+$ ]]; then
    echo "Usage: $0 [duration_seconds]"
    echo "Example: $0 60"
    exit 1
fi

# Detect if we need IPv4 or IPv6 (check for existing connections)
if ss -tn "dport = :$PORT" | grep -q ':'; then
    if ss -tn "dport = :$PORT" | grep -qE '^\[|:.*:'; then
        USE_IPV6=true
    else
        USE_IPV6=false
    fi
else
    # Default to IPv6 based on user's earlier connection
    USE_IPV6=true
fi

if $USE_IPV6; then
    IPTABLES="ip6tables"
    echo "Using IPv6 (ip6tables)"
else
    IPTABLES="iptables"
    echo "Using IPv4 (iptables)"
fi

RULE_COMMENT="bw_measure_$PORT"

# Cleanup function
cleanup() {
    echo -e "\nCleaning up iptables rule..."
    sudo $IPTABLES -D INPUT -p tcp --sport $PORT -m comment --comment "$RULE_COMMENT" -j ACCEPT 2>/dev/null
    exit 0
}

trap cleanup INT TERM EXIT

# Add counter rule
echo "Adding iptables rule for port $PORT..."
sudo $IPTABLES -I INPUT -p tcp --sport $PORT -m comment --comment "$RULE_COMMENT" -j ACCEPT

if [ $? -ne 0 ]; then
    echo "Failed to add iptables rule. Are you root?"
    exit 1
fi

# Get initial byte count
get_bytes() {
    sudo $IPTABLES -L INPUT -v -n -x | grep "$RULE_COMMENT" | awk '{print $2}'
}

echo "Measuring bandwidth on port $PORT for $DURATION seconds..."
echo ""

START_BYTES=$(get_bytes)
START_TIME=$(date +%s)

# Collect samples
declare -a SAMPLES
PREV_BYTES=$START_BYTES

for ((i=1; i<=DURATION; i++)); do
    sleep $INTERVAL
    CURR_BYTES=$(get_bytes)
    DELTA=$((CURR_BYTES - PREV_BYTES))
    KBPS=$(echo "scale=1; $DELTA * 8 / 1000" | bc)
    SAMPLES+=($DELTA)
    PREV_BYTES=$CURR_BYTES

    # Progress indicator every 10 seconds
    if ((i % 10 == 0)); then
        echo "  ${i}s: current rate = ${KBPS} Kbps"
    fi
done

END_BYTES=$(get_bytes)
END_TIME=$(date +%s)

# Calculate statistics
TOTAL_BYTES=$((END_BYTES - START_BYTES))
ELAPSED=$((END_TIME - START_TIME))
AVG_KBPS=$(echo "scale=1; $TOTAL_BYTES * 8 / $ELAPSED / 1000" | bc)
AVG_MBPS=$(echo "scale=3; $TOTAL_BYTES * 8 / $ELAPSED / 1000000" | bc)

# Calculate min/max from samples
MIN_KBPS=999999999
MAX_KBPS=0
for s in "${SAMPLES[@]}"; do
    kbps=$((s * 8 / 1000))
    ((kbps < MIN_KBPS)) && MIN_KBPS=$kbps
    ((kbps > MAX_KBPS)) && MAX_KBPS=$kbps
done

echo ""
echo "========================================="
echo "  Bandwidth Report (port $PORT)"
echo "========================================="
echo "  Duration:     $ELAPSED seconds"
echo "  Total bytes:  $TOTAL_BYTES"
echo "  Average:      $AVG_KBPS Kbps ($AVG_MBPS Mbps)"
echo "  Min:          $MIN_KBPS Kbps"
echo "  Max:          $MAX_KBPS Kbps"
echo "========================================="
