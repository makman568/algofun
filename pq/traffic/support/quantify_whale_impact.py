#!/usr/bin/env python3
"""
Quantify the mathematical impact of whale stake concentration on cert votes.
Extended analysis comparing to theoretical expectations.
"""

import csv
from collections import defaultdict
import statistics
import math

CERT_THRESHOLD = 1112
CERT_COMMITTEE_SIZE = 1500
THEORETICAL_UNIQUE_VOTERS = 233  # From derive_voters.py

def load_votes_by_round(votes_file):
    """Load cert votes grouped by round."""
    rounds = defaultdict(list)

    with open(votes_file, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            step = int(row['step'])
            if step != 2:  # Only cert votes
                continue

            rnd = int(row['round'])
            weight = int(row['credential_weight'])
            sender = row['sender']
            rounds[rnd].append({'sender': sender, 'weight': weight})

    return rounds


def analyze_round(votes):
    """Analyze a single round's cert votes."""
    if not votes:
        return None

    total_weight = sum(v['weight'] for v in votes)
    total_voters = len(votes)

    if total_weight < CERT_THRESHOLD:
        return None

    # Actual scenario: sort by weight descending (whales first)
    sorted_votes = sorted(votes, key=lambda x: x['weight'], reverse=True)

    cumulative = 0
    actual_voters = 0
    for v in sorted_votes:
        cumulative += v['weight']
        actual_voters += 1
        if cumulative >= CERT_THRESHOLD:
            break

    # Uniform scenario
    avg_weight = total_weight / total_voters
    uniform_voters = CERT_THRESHOLD / avg_weight

    return {
        'actual_voters': actual_voters,
        'uniform_voters': uniform_voters,
        'total_weight': total_weight,
        'total_voters': total_voters,
        'avg_weight': avg_weight,
        'weights': [v['weight'] for v in votes]
    }


def gini_coefficient(weights):
    """Calculate Gini coefficient."""
    sorted_weights = sorted(weights)
    n = len(sorted_weights)
    if n == 0:
        return 0
    cumsum = sum((2 * (i + 1) - n - 1) * w for i, w in enumerate(sorted_weights))
    return cumsum / (n * sum(sorted_weights)) if sum(sorted_weights) > 0 else 0


def main():
    votes_file = "/home/thong/algofun/pq/traffic/logs/log5/consensus_votes_detail.csv"

    print("Loading cert votes...")
    rounds = load_votes_by_round(votes_file)

    results = []
    all_weights = []

    for rnd, votes in rounds.items():
        r = analyze_round(votes)
        if r:
            results.append(r)
            all_weights.extend(r['weights'])

    # Aggregate
    actual_voters = [r['actual_voters'] for r in results]
    uniform_voters = [r['uniform_voters'] for r in results]
    total_voters = [r['total_voters'] for r in results]
    avg_weights = [r['avg_weight'] for r in results]
    total_weights = [r['total_weight'] for r in results]

    mean_actual = statistics.mean(actual_voters)
    mean_uniform = statistics.mean(uniform_voters)
    mean_total = statistics.mean(total_voters)
    mean_weight = statistics.mean(avg_weights)
    mean_total_weight = statistics.mean(total_weights)
    gini = gini_coefficient(all_weights)

    print("\n" + "=" * 80)
    print("WHALE IMPACT ON CERT VOTES: QUANTIFIED")
    print("=" * 80)

    print(f"""
### Baseline Parameters ###

Cert committee size:        {CERT_COMMITTEE_SIZE}
Cert threshold:             {CERT_THRESHOLD} (74%)
Theoretical unique voters:  {THEORETICAL_UNIQUE_VOTERS}

### Observed Values (mean across {len(results)} rounds) ###

Unique voters per round:    {mean_total:.1f}
Total weight per round:     {mean_total_weight:.0f}
Average weight per vote:    {mean_weight:.2f}
Gini coefficient:           {gini:.3f} (high inequality)
""")

    print("=" * 80)
    print("DECOMPOSING THE GAP: 233 theoretical → 144 observed")
    print("=" * 80)

    # The gap from 233 to 144 comes from two factors:
    # 1. Threshold termination (stops at 1112 instead of collecting all votes)
    # 2. Whale ordering (whales vote first, reaching threshold faster)

    # Factor 1: Threshold termination effect
    # If all 233 theoretical voters voted and we had uniform stake:
    # Expected weight per voter = committee_size / theoretical_voters = 1500/233 = 6.44
    # To reach 1112 threshold: 1112 / 6.44 = 172.7 voters

    theoretical_weight_per_voter = CERT_COMMITTEE_SIZE / THEORETICAL_UNIQUE_VOTERS

    # With uniform distribution among theoretical voters, how many to reach threshold?
    uniform_threshold_voters = CERT_THRESHOLD / theoretical_weight_per_voter

    # Factor 2: Actual whale distribution
    # Observed avg weight is higher (7.96) because small accounts don't make it
    # And whales voting first means even fewer needed

    print(f"""
### Step 1: Theoretical Baseline ###

If {THEORETICAL_UNIQUE_VOTERS} unique voters participated with uniform stake:
  Weight per voter = {CERT_COMMITTEE_SIZE} / {THEORETICAL_UNIQUE_VOTERS} = {theoretical_weight_per_voter:.2f}
  Voters to threshold = {CERT_THRESHOLD} / {theoretical_weight_per_voter:.2f} = {uniform_threshold_voters:.1f}

This is the "uniform stake + threshold termination" baseline.
""")

    print(f"""
### Step 2: Actual Observed ###

Observed voters to threshold (whales-first): {mean_actual:.1f}
Observed voters in round: {mean_total:.1f}

The gap from {uniform_threshold_voters:.1f} → {mean_actual:.1f} is the whale effect.
""")

    # Decomposition
    gap_total = THEORETICAL_UNIQUE_VOTERS - mean_total
    gap_threshold = uniform_threshold_voters - mean_actual

    print(f"""
### Gap Decomposition ###

Total gap: {THEORETICAL_UNIQUE_VOTERS} - {mean_total:.1f} = {gap_total:.1f} voters

This decomposes into:

1. THRESHOLD TERMINATION EFFECT
   Without termination: {THEORETICAL_UNIQUE_VOTERS} voters
   With uniform termination: {uniform_threshold_voters:.1f} voters
   Reduction: {THEORETICAL_UNIQUE_VOTERS - uniform_threshold_voters:.1f} voters ({(THEORETICAL_UNIQUE_VOTERS - uniform_threshold_voters)/THEORETICAL_UNIQUE_VOTERS*100:.1f}%)

2. WHALE CONCENTRATION EFFECT
   Uniform to threshold: {uniform_threshold_voters:.1f} voters
   Whales-first to threshold: {mean_actual:.1f} voters
   Reduction: {uniform_threshold_voters - mean_actual:.1f} voters ({(uniform_threshold_voters - mean_actual)/uniform_threshold_voters*100:.1f}%)

3. VOTE ARRIVAL (observed > threshold)
   Voters to threshold: {mean_actual:.1f}
   Voters observed: {mean_total:.1f}
   Overshoot: {mean_total - mean_actual:.1f} voters
""")

    # Summary table
    print("=" * 80)
    print("SUMMARY TABLE")
    print("=" * 80)
    print(f"""
| Stage                          | Voters | Reduction | Cumulative |
|--------------------------------|--------|-----------|------------|
| Theoretical (no termination)   |    {THEORETICAL_UNIQUE_VOTERS} |       n/a |        n/a |
| + Threshold termination        |    {uniform_threshold_voters:.0f} |       {THEORETICAL_UNIQUE_VOTERS - uniform_threshold_voters:.0f} |     {(1 - uniform_threshold_voters/THEORETICAL_UNIQUE_VOTERS)*100:.0f}% |
| + Whale concentration          |    {mean_actual:.0f} |       {uniform_threshold_voters - mean_actual:.0f} |     {(1 - mean_actual/THEORETICAL_UNIQUE_VOTERS)*100:.0f}% |
| Observed (with overshoot)      |    {mean_total:.0f} |      +{mean_total - mean_actual:.0f} |     {(1 - mean_total/THEORETICAL_UNIQUE_VOTERS)*100:.0f}% |
""")

    # Mathematical formulas
    print("=" * 80)
    print("MATHEMATICAL FORMULAS")
    print("=" * 80)
    print(f"""
Let:
  T = threshold = {CERT_THRESHOLD}
  N = theoretical unique voters = {THEORETICAL_UNIQUE_VOTERS}
  C = committee size = {CERT_COMMITTEE_SIZE}
  w̄_uniform = C/N = {theoretical_weight_per_voter:.2f}
  w̄_observed = {mean_weight:.2f}
  G = Gini coefficient = {gini:.3f}

Uniform baseline voters:
  V_uniform = T / w̄_uniform = {CERT_THRESHOLD} / {theoretical_weight_per_voter:.2f} = {uniform_threshold_voters:.1f}

Whale effect (empirical):
  V_whale = {mean_actual:.1f}

Whale reduction factor:
  ρ = V_whale / V_uniform = {mean_actual:.1f} / {uniform_threshold_voters:.1f} = {mean_actual/uniform_threshold_voters:.3f}

Whale savings:
  ΔV = V_uniform - V_whale = {uniform_threshold_voters:.1f} - {mean_actual:.1f} = {uniform_threshold_voters - mean_actual:.1f} voters/round

Percentage impact:
  (1 - ρ) × 100 = {(1 - mean_actual/uniform_threshold_voters)*100:.1f}%
""")

    # Efficiency gain
    print("=" * 80)
    print("EFFICIENCY INTERPRETATION")
    print("=" * 80)
    print(f"""
The whale concentration creates a {(1 - mean_actual/uniform_threshold_voters)*100:.1f}% reduction in voters needed
beyond what threshold termination alone would achieve.

Combined effect:
  Theoretical: {THEORETICAL_UNIQUE_VOTERS} voters
  Observed: {mean_actual:.1f} voters (to threshold)
  Total reduction: {(1 - mean_actual/THEORETICAL_UNIQUE_VOTERS)*100:.1f}%

Of this {(1 - mean_actual/THEORETICAL_UNIQUE_VOTERS)*100:.1f}% reduction:
  - Threshold termination contributes: {(1 - uniform_threshold_voters/THEORETICAL_UNIQUE_VOTERS)*100:.1f}%
  - Whale concentration contributes: {(uniform_threshold_voters/THEORETICAL_UNIQUE_VOTERS - mean_actual/THEORETICAL_UNIQUE_VOTERS)*100:.1f}%
""")


if __name__ == "__main__":
    main()
