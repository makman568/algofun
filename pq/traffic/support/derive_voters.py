#!/usr/bin/env python3
"""
Derive expected voters to reach quorum threshold using:
- go-algorand consensus parameters
- Actual stake distribution from mainnet snapshot

This simulates Algorand's VRF-based sortition and calculates how many
unique voters are needed to reach threshold for each consensus step.
"""

import csv
import random
import math
from dataclasses import dataclass
from typing import List, Tuple

# go-algorand consensus parameters (from config/consensus.go, v8+)
@dataclass
class ConsensusParams:
    soft_committee_size: int = 2990
    soft_threshold: int = 2267
    cert_committee_size: int = 1500
    cert_threshold: int = 1112
    next_committee_size: int = 5000
    next_threshold: int = 3838

def load_stakes(filepath: str) -> Tuple[List[float], float]:
    """Load stake distribution from CSV, return stakes in Algos and total."""
    stakes = []
    with open(filepath, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            balance = float(row['Balance'])
            if balance > 0:
                stakes.append(balance)

    total_stake = sum(stakes)
    return stakes, total_stake

def expected_unique_voters(stakes: List[float], total_stake: float, committee_size: int) -> float:
    """
    Calculate expected number of unique voters using binomial probability.
    P(selected) = 1 - (1 - committee_size/total_stake)^stake
    """
    tau_over_W = committee_size / total_stake
    expected = 0.0
    for stake in stakes:
        # P(at least 1 vote) = 1 - (1 - tau/W)^stake
        # Use log for numerical stability with large stakes
        log_prob_not_selected = stake * math.log(1.0 - tau_over_W)
        p_selected = 1.0 - math.exp(log_prob_not_selected)
        expected += p_selected
    return expected

def expected_weight_given_selected(stake: float, tau_over_W: float) -> float:
    """
    Calculate expected weight for an account given it was selected.
    E[X | X >= 1] = E[X] / P(X >= 1) for binomial X
    """
    expected_weight = stake * tau_over_W  # E[X] for binomial
    log_prob_not_selected = stake * math.log(1.0 - tau_over_W)
    p_selected = 1.0 - math.exp(log_prob_not_selected)
    if p_selected < 1e-10:
        return 1.0  # Tiny accounts contribute 1 if selected
    return expected_weight / p_selected

def sample_weight(stake: float, tau_over_W: float) -> int:
    """
    Sample weight from binomial distribution, conditioned on being > 0.
    Uses normal approximation for large expected values.
    """
    expected = stake * tau_over_W

    if expected > 30:
        # Normal approximation
        std = math.sqrt(stake * tau_over_W * (1 - tau_over_W))
        u1 = max(1e-10, random.random())
        u2 = random.random()
        z = math.sqrt(-2 * math.log(u1)) * math.cos(2 * math.pi * u2)
        weight = int(expected + std * z + 0.5)
        return max(1, weight)  # At least 1 since we're selected
    elif expected > 5:
        # Poisson approximation
        L = math.exp(-expected)
        k = 0
        p_val = 1.0
        while p_val > L and k < 1000:
            k += 1
            p_val *= random.random()
        return max(1, k - 1)
    else:
        # For small expected values, use geometric-ish sampling
        # P(selected) is small, weight is usually 1
        if expected < 0.1:
            return 1
        # Otherwise small chance of weight > 1
        weight = 1
        remaining_expected = expected - 1
        while remaining_expected > 0 and random.random() < min(0.5, remaining_expected):
            weight += 1
            remaining_expected -= 1
        return weight

def simulate_voters_to_threshold(
    stakes: List[float],
    total_stake: float,
    committee_size: int,
    threshold: int,
    trials: int = 1000
) -> Tuple[float, float, List[int]]:
    """
    Simulate sortition and calculate voters needed to reach threshold.
    Returns (mean, std, raw_results).
    """
    tau_over_W = committee_size / total_stake

    # Precompute selection probabilities
    selection_probs = []
    for stake in stakes:
        log_prob_not = stake * math.log(1.0 - tau_over_W)
        p_sel = 1.0 - math.exp(log_prob_not)
        selection_probs.append((stake, p_sel))

    voters_needed = []

    for trial in range(trials):
        # Sortition: determine who is selected and their weight
        selected_weights = []
        for stake, p_sel in selection_probs:
            if random.random() < p_sel:
                weight = sample_weight(stake, tau_over_W)
                selected_weights.append(weight)

        if not selected_weights:
            continue

        # Random arrival order
        random.shuffle(selected_weights)

        # Count voters to reach threshold
        cumulative = 0
        for i, w in enumerate(selected_weights):
            cumulative += w
            if cumulative >= threshold:
                voters_needed.append(i + 1)
                break
        else:
            voters_needed.append(len(selected_weights))

        # Progress indicator
        if (trial + 1) % 200 == 0:
            print(f"  Trial {trial + 1}/{trials}...")

    # Calculate statistics
    if not voters_needed:
        return 0.0, 0.0, []

    mean = sum(voters_needed) / len(voters_needed)
    variance = sum((x - mean) ** 2 for x in voters_needed) / len(voters_needed)
    std = math.sqrt(variance)

    return mean, std, voters_needed

def main():
    import sys

    # Load stake distribution
    stake_file = "/home/thong/algofun/pq/traffic/support/algorand-consensus-20251124.csv"
    if len(sys.argv) > 1:
        stake_file = sys.argv[1]

    print(f"Loading stakes from: {stake_file}")
    stakes, total_stake = load_stakes(stake_file)

    print(f"\n{'='*60}")
    print("STAKE DISTRIBUTION SUMMARY")
    print(f"{'='*60}")
    print(f"Total accounts: {len(stakes)}")
    print(f"Total stake: {total_stake:,.2f} Algos")

    # Sort for percentile analysis
    sorted_stakes = sorted(stakes, reverse=True)
    for threshold_pct in [10, 20, 30, 40, 50]:
        target = total_stake * threshold_pct / 100
        count = 0
        cumulative = 0
        for s in sorted_stakes:
            cumulative += s
            count += 1
            if cumulative >= target:
                break
        print(f"Top {count} accounts hold {threshold_pct}% of stake")

    params = ConsensusParams()

    print(f"\n{'='*60}")
    print("CONSENSUS PARAMETERS (go-algorand v8+)")
    print(f"{'='*60}")
    print(f"Soft: committee={params.soft_committee_size}, threshold={params.soft_threshold}")
    print(f"Cert: committee={params.cert_committee_size}, threshold={params.cert_threshold}")
    print(f"Next: committee={params.next_committee_size}, threshold={params.next_threshold}")

    print(f"\n{'='*60}")
    print("THEORETICAL EXPECTED UNIQUE VOTERS (full committee)")
    print(f"{'='*60}")

    soft_expected = expected_unique_voters(stakes, total_stake, params.soft_committee_size)
    cert_expected = expected_unique_voters(stakes, total_stake, params.cert_committee_size)
    next_expected = expected_unique_voters(stakes, total_stake, params.next_committee_size)

    print(f"Soft: {soft_expected:.1f} unique voters expected")
    print(f"Cert: {cert_expected:.1f} unique voters expected")
    print(f"Next: {next_expected:.1f} unique voters expected")

    print(f"\n{'='*60}")
    print("SIMULATED VOTERS TO REACH THRESHOLD (1000 trials each)")
    print(f"{'='*60}")

    # Soft votes
    print("\nSimulating Soft votes...")
    soft_mean, soft_std, _ = simulate_voters_to_threshold(
        stakes, total_stake, params.soft_committee_size, params.soft_threshold
    )
    soft_ratio = soft_mean / soft_expected
    print(f"Soft votes to threshold {params.soft_threshold}:")
    print(f"  Mean: {soft_mean:.1f} voters (std: {soft_std:.1f})")
    print(f"  Ratio to theory: {soft_ratio:.3f}x")
    print(f"  Paper observed:  0.871x (~308 voters)")

    # Cert votes
    print("\nSimulating Cert votes...")
    cert_mean, cert_std, _ = simulate_voters_to_threshold(
        stakes, total_stake, params.cert_committee_size, params.cert_threshold
    )
    cert_ratio = cert_mean / cert_expected
    print(f"Cert votes to threshold {params.cert_threshold}:")
    print(f"  Mean: {cert_mean:.1f} voters (std: {cert_std:.1f})")
    print(f"  Ratio to theory: {cert_ratio:.3f}x")
    print(f"  Paper observed:  0.627x (~147 voters)")

    # Next votes
    print("\nSimulating Next votes...")
    next_mean, next_std, _ = simulate_voters_to_threshold(
        stakes, total_stake, params.next_committee_size, params.next_threshold
    )
    next_ratio = next_mean / next_expected
    print(f"Next votes to threshold {params.next_threshold}:")
    print(f"  Mean: {next_mean:.1f} voters (std: {next_std:.1f})")
    print(f"  Ratio to theory: {next_ratio:.3f}x")

    print(f"\n{'='*60}")
    print("COMPARISON SUMMARY")
    print(f"{'='*60}")
    print(f"{'Step':<6} {'Theory':<10} {'Simulated':<12} {'Ratio':<8} {'Paper':<8} {'Empirical':<10}")
    print(f"{'-'*6} {'-'*10} {'-'*12} {'-'*8} {'-'*8} {'-'*10}")
    print(f"{'Soft':<6} {soft_expected:<10.1f} {soft_mean:<12.1f} {soft_ratio:<8.3f} {'0.871':<8} {'~308':<10}")
    print(f"{'Cert':<6} {cert_expected:<10.1f} {cert_mean:<12.1f} {cert_ratio:<8.3f} {'0.627':<8} {'~147':<10}")
    print(f"{'Next':<6} {next_expected:<10.1f} {next_mean:<12.1f} {next_ratio:<8.3f} {'N/A':<8} {'0':<10}")

    print(f"\n{'='*60}")
    print("INTERPRETATION")
    print(f"{'='*60}")
    print("If simulated ratios match paper's observed ratios (~0.87 soft,")
    print("~0.63 cert), then the stake distribution alone explains the")
    print("on-time voter counts via threshold termination.")

if __name__ == "__main__":
    main()
