#!/usr/bin/env python3
"""
Profile consensus votes by stake tier.
Analyzes how many votes emanate from top-10, 10-20, 20-30, etc. accounts.
"""

import csv
from collections import defaultdict

# Load stake distribution and rank accounts
def load_stake_ranks(stake_file):
    """Load stake distribution and return address -> rank mapping."""
    accounts = []
    with open(stake_file, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            addr = row['Address']
            balance = float(row['Balance'].replace(',', ''))
            accounts.append((addr, balance))

    # Sort by balance descending
    accounts.sort(key=lambda x: x[1], reverse=True)

    # Create address -> (rank, balance) mapping (1-indexed)
    addr_to_rank = {}
    for i, (addr, balance) in enumerate(accounts):
        addr_to_rank[addr] = (i + 1, balance)

    return addr_to_rank, accounts

def get_tier(rank):
    """Return tier name for a given rank."""
    if rank <= 10:
        return "1-10"
    elif rank <= 20:
        return "11-20"
    elif rank <= 30:
        return "21-30"
    elif rank <= 50:
        return "31-50"
    elif rank <= 100:
        return "51-100"
    elif rank <= 200:
        return "101-200"
    elif rank <= 500:
        return "201-500"
    else:
        return "500+"

def analyze_votes(votes_file, addr_to_rank):
    """Analyze votes and group by stake tier."""
    # Track by step: 1=soft, 2=cert
    tiers = ["1-10", "11-20", "21-30", "31-50", "51-100", "101-200", "201-500", "500+"]

    soft_votes = defaultdict(int)
    soft_weight = defaultdict(int)
    cert_votes = defaultdict(int)
    cert_weight = defaultdict(int)

    unknown_senders = set()
    total_soft = 0
    total_cert = 0

    with open(votes_file, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            sender = row['sender']
            step = int(row['step'])
            weight = int(row['credential_weight'])

            if sender in addr_to_rank:
                rank, _ = addr_to_rank[sender]
                tier = get_tier(rank)
            else:
                unknown_senders.add(sender)
                tier = "500+"  # Treat unknown as small accounts

            if step == 1:  # Soft vote
                soft_votes[tier] += 1
                soft_weight[tier] += weight
                total_soft += 1
            elif step == 2:  # Cert vote
                cert_votes[tier] += 1
                cert_weight[tier] += weight
                total_cert += 1

    return {
        'tiers': tiers,
        'soft_votes': soft_votes,
        'soft_weight': soft_weight,
        'cert_votes': cert_votes,
        'cert_weight': cert_weight,
        'total_soft': total_soft,
        'total_cert': total_cert,
        'unknown_senders': unknown_senders
    }

def print_results(results, accounts):
    """Print formatted results."""
    tiers = results['tiers']

    print("=" * 80)
    print("CONSENSUS VOTE PROFILE BY STAKE TIER")
    print("=" * 80)

    # Show top accounts for context
    print("\n### Top 30 Accounts by Stake ###\n")
    print(f"{'Rank':<6} {'Address':<60} {'Stake (M Algo)':<15}")
    print("-" * 80)
    for i, (addr, balance) in enumerate(accounts[:30]):
        print(f"{i+1:<6} {addr:<60} {balance/1e6:>12.2f}")

    # Soft votes
    print("\n" + "=" * 80)
    print("SOFT VOTES (step=1)")
    print("=" * 80)
    print(f"\n{'Tier':<12} {'Votes':>10} {'% Votes':>10} {'Weight':>12} {'% Weight':>10} {'Avg Wt/Vote':>12}")
    print("-" * 70)

    total_soft = results['total_soft']
    total_soft_weight = sum(results['soft_weight'].values())

    for tier in tiers:
        votes = results['soft_votes'].get(tier, 0)
        weight = results['soft_weight'].get(tier, 0)
        pct_votes = (votes / total_soft * 100) if total_soft > 0 else 0
        pct_weight = (weight / total_soft_weight * 100) if total_soft_weight > 0 else 0
        avg_weight = (weight / votes) if votes > 0 else 0
        print(f"{tier:<12} {votes:>10,} {pct_votes:>9.1f}% {weight:>12,} {pct_weight:>9.1f}% {avg_weight:>12.1f}")

    print("-" * 70)
    print(f"{'TOTAL':<12} {total_soft:>10,} {'100.0':>9}% {total_soft_weight:>12,} {'100.0':>9}%")

    # Cert votes
    print("\n" + "=" * 80)
    print("CERT VOTES (step=2)")
    print("=" * 80)
    print(f"\n{'Tier':<12} {'Votes':>10} {'% Votes':>10} {'Weight':>12} {'% Weight':>10} {'Avg Wt/Vote':>12}")
    print("-" * 70)

    total_cert = results['total_cert']
    total_cert_weight = sum(results['cert_weight'].values())

    for tier in tiers:
        votes = results['cert_votes'].get(tier, 0)
        weight = results['cert_weight'].get(tier, 0)
        pct_votes = (votes / total_cert * 100) if total_cert > 0 else 0
        pct_weight = (weight / total_cert_weight * 100) if total_cert_weight > 0 else 0
        avg_weight = (weight / votes) if votes > 0 else 0
        print(f"{tier:<12} {votes:>10,} {pct_votes:>9.1f}% {weight:>12,} {pct_weight:>9.1f}% {avg_weight:>12.1f}")

    print("-" * 70)
    print(f"{'TOTAL':<12} {total_cert:>10,} {'100.0':>9}% {total_cert_weight:>12,} {'100.0':>9}%")

    # Summary stats
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)

    # Per-round averages (1001 rounds)
    rounds = 1001
    print(f"\nPer-Round Averages (over {rounds} rounds):")
    print(f"  Soft votes: {total_soft/rounds:.1f}")
    print(f"  Cert votes: {total_cert/rounds:.1f}")

    # Top 10 concentration
    top10_soft_votes = results['soft_votes'].get("1-10", 0)
    top10_soft_weight = results['soft_weight'].get("1-10", 0)
    top10_cert_votes = results['cert_votes'].get("1-10", 0)
    top10_cert_weight = results['cert_weight'].get("1-10", 0)

    top20_soft_weight = top10_soft_weight + results['soft_weight'].get("11-20", 0)
    top20_cert_weight = top10_cert_weight + results['cert_weight'].get("11-20", 0)

    print(f"\nWhale Concentration:")
    print(f"  Top 10 accounts: {top10_soft_weight/total_soft_weight*100:.1f}% of soft weight, {top10_cert_weight/total_cert_weight*100:.1f}% of cert weight")
    print(f"  Top 20 accounts: {top20_soft_weight/total_soft_weight*100:.1f}% of soft weight, {top20_cert_weight/total_cert_weight*100:.1f}% of cert weight")

    if results['unknown_senders']:
        print(f"\nUnknown senders (not in stake file): {len(results['unknown_senders'])}")


def main():
    stake_file = "/home/thong/algofun/pq/traffic/support/algorand-consensus-20251128.csv"
    votes_file = "/home/thong/algofun/pq/traffic/logs/log5/consensus_votes_detail.csv"

    print("Loading stake distribution...")
    addr_to_rank, accounts = load_stake_ranks(stake_file)
    print(f"  Loaded {len(accounts)} accounts")

    print("Analyzing votes...")
    results = analyze_votes(votes_file, addr_to_rank)
    print(f"  Soft votes: {results['total_soft']:,}")
    print(f"  Cert votes: {results['total_cert']:,}")

    print_results(results, accounts)


if __name__ == "__main__":
    main()
