#!/bin/bash
#
# analyze_rounds.sh - Analyze consensus_rounds.csv and validate against paper statistics
#
# Usage: ./analyze_rounds.sh <path_to_consensus_rounds.csv>
#
# Outputs statistics comparing observed data to theoretical model:
# - Vote counts per round (soft, cert, next)
# - Weight statistics and ranges
# - Ratios to theoretical expected values
# - Peer counts and round duration

set -e

if [ -z "$1" ]; then
    echo "Usage: $0 <path_to_consensus_rounds.csv>"
    exit 1
fi

CSV_FILE="$1"

if [ ! -f "$CSV_FILE" ]; then
    echo "Error: File not found: $CSV_FILE"
    exit 1
fi

# Theoretical values from go-algorand consensus parameters
SOFT_THEORY=354
CERT_THEORY=233
NEXT_THEORY=477
CERT_THRESHOLD=1112
SOFT_THRESHOLD=2267

echo "============================================================"
echo "Consensus Rounds Analysis"
echo "============================================================"
echo "File: $CSV_FILE"
echo ""

awk -F',' -v soft_theory="$SOFT_THEORY" -v cert_theory="$CERT_THEORY" -v cert_thresh="$CERT_THRESHOLD" '
NR==1 {
    # Verify header
    if ($1 != "round") {
        print "Error: Expected CSV with round as first column"
        exit 1
    }
    next
}
{
    # Accumulate sums
    soft += $8
    cert += $9
    next_v += $10
    soft_w += $11
    cert_w += $12
    next_w += $13
    bundle += $5
    dur += $4
    in_peers += $6
    out_peers += $7
    count++

    # Track min/max
    if (count == 1 || $12 < cert_min) cert_min = $12
    if (count == 1 || $12 > cert_max) cert_max = $12
    if (count == 1 || $11 < soft_min) soft_min = $11
    if (count == 1 || $11 > soft_max) soft_max = $11
    if (count == 1 || $4 < dur_min) dur_min = $4
    if (count == 1 || $4 > dur_max) dur_max = $4
}
END {
    printf "Total rounds analyzed: %d\n", count
    print ""

    print "=== Vote Counts (per round) ==="
    printf "%-25s %8.1f\n", "Unique soft voters:", soft/count
    printf "%-25s %8.1f\n", "Unique cert voters:", cert/count
    printf "%-25s %8.1f\n", "Unique next voters:", next_v/count
    print ""

    print "=== Ratio to Theory ==="
    printf "%-25s %8.3fx  (theory: %d)\n", "Soft ratio:", (soft/count)/soft_theory, soft_theory
    printf "%-25s %8.3fx  (theory: %d)\n", "Cert ratio:", (cert/count)/cert_theory, cert_theory
    print ""

    print "=== Weights (per round) ==="
    printf "%-25s %8.1f\n", "Soft weight mean:", soft_w/count
    printf "%-25s %8.1f\n", "Cert weight mean:", cert_w/count
    printf "%-25s %8.1f\n", "Next weight mean:", next_w/count
    print ""

    print "=== Weight Ranges ==="
    printf "%-25s %8d  (threshold: %d)\n", "Cert weight min:", cert_min, cert_thresh
    printf "%-25s %8d\n", "Cert weight max:", cert_max
    printf "%-25s %8d\n", "Soft weight min:", soft_min
    printf "%-25s %8d\n", "Soft weight max:", soft_max
    print ""

    print "=== Other Metrics ==="
    printf "%-25s %8.1f\n", "Bundle votes mean:", bundle/count
    printf "%-25s %8.1f ms\n", "Round duration mean:", dur/count
    printf "%-25s %8.1f ms\n", "Round duration min:", dur_min
    printf "%-25s %8.1f ms\n", "Round duration max:", dur_max
    print ""

    print "=== Peer Counts ==="
    printf "%-25s %8.1f\n", "Inbound peers mean:", in_peers/count
    printf "%-25s %8.1f\n", "Outbound peers mean:", out_peers/count
    print ""

    print "=== Threshold Termination Check ==="
    if (cert_min == cert_thresh) {
        printf "Cert weight min = %d (exactly at threshold) ✓\n", cert_min
    } else if (cert_min > cert_thresh) {
        printf "Cert weight min = %d (above threshold by %d)\n", cert_min, cert_min - cert_thresh
    } else {
        printf "Cert weight min = %d (BELOW threshold - unexpected)\n", cert_min
    }
}
' "$CSV_FILE"

echo ""
echo "============================================================"
