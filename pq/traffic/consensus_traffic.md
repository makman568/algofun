# Algorand Consensus Traffic Analysis

**A Three-Step Analysis: Theory, Optimization, and Empirical Support**

---

This paper presents a comprehensive analysis of Algorand's consensus traffic through a three-step methodology:

1.  **Theoretical Profile Derivation:** First, we derive a *theoretical traffic profile* from first principles. Using core consensus parameters from the `go-algorand` source code and a November 24, 2025 snapshot of the mainnet stake distribution, we calculate the statistical expectation for the number of unique voters in an unoptimized, purely theoretical consensus round.

2.  **Protocol Optimization Analysis:** Second, we explain how the live Algorand protocol optimizes this theoretical traffic. We detail the "early threshold termination" mechanism, where nodes suppress the propagation of votes once a quorum weight is achieved, effectively making subsequent votes for that phase obsolete and preventing them from congesting the network.

3.  **Empirical Analysis of Observed Traffic:** Finally, we examine mainnet telemetry (`consensus_messages-20251124.csv`) to understand how real rounds compare with the theoretical profile. The on-time votes required to reach quorum are indeed lower than the theoretical expectation due to threshold termination, while the *total* message count per round is higher because of network amplification (competing proposals and redundant delivery). The empirical data therefore validates the theoretical committee-size model while quantifying these real-world amplification factors.

This analysis juxtaposes the theoretical and empirical perspectives on Algorand's consensus traffic. The theoretical committee sizes accurately predict unique participants, while the telemetry quantifies network amplification factors: competing proposals cause voters to split across multiple candidates, and redundant delivery paths increase message counts beyond unique sender counts. Understanding these amplification effects is essential for capacity planning and protocol analysis.

---
# Part I: The Theoretical Traffic Profile
---

This section derives the theoretical message count from first principles, combining the protocol's fixed parameters with the real-world distribution of stake.

## 1. Theoretical Inputs: Parameters and Stake Distribution

Two inputs are required to model the theoretical message count: the consensus parameters defined in the source code, and the distribution of online stake that participates in consensus.

### 1.1 Consensus Parameters

The Algorand protocol defines the expected committee sizes and weight thresholds for each step of consensus. These are defined in the `go-algorand` repository in `config/consensus.go`.

**File: go-algorand `config/consensus.go`**
```go
// v10 introduces fast partition recovery (and also raises NumProposers).
v10 := v9
v10.NumProposers = 20
v10.SoftCommitteeSize = 2990
v10.SoftCommitteeThreshold = 2267   // 76% of expected committee weight
v10.CertCommitteeSize = 1500
v10.CertCommitteeThreshold = 1112   // 74% of expected committee weight
v10.NextCommitteeSize = 5000
v10.NextCommitteeThreshold = 3838   // 77% of expected committee weight
// ... other parameters for recovery mode etc.
```
Protocol versions **v10 and above therefore run with `NumProposers = 20`**. The committee sizes (2990, 1500, 5000) are not enforced limits but rather statistical expectations for the total committee weight selected.

### 1.2 Stake Distribution (Nov 24, 2025)

The second input is the actual distribution of stake among online accounts. The file `algorand-consensus-20251124.csv` provides a snapshot of every online participation key and its balance on this date.

| Accounts | Cumulative stake |
|----------|------------------|
| Top 5    | 17.7% |
| Top 10   | 30.9% |
| Top 20   | 54.0% |
| Top 30   | 70.4% |
| Top 40   | **79.3%** |
| Top 100  | 88.8% |

A key insight is the existence of a sizable "middle tier" of accounts:
- 0.10-0.50% stake: 25 accounts
- 0.05-0.10% stake: 47 accounts
- 0.01-0.05% stake: 318 accounts

While high-stake operators provide significant weight, the sheer number of these mid-tier accounts is critical in determining how many unique messages are generated per round.

## 2. The Mathematical Model for Voter Selection

Algorand's VRF-based sortition draws a *weight* for every account using the binomial distribution implemented in `data/committee/credential.go` (which calls `github.com/algorand/sortition`). Given an account with stake `w`, total online stake `W`, and committee parameter `τ`, the sortition module samples `X ~ Binomial(w, τ/W)` and the node sends a single message with weight `X`. An account participates in a step iff `X ≥ 1`, producing the exact probability
```
P(vote≥1 | w, τ, W) = 1 - (1 - τ / W)^{w}.
```
This expression replaces the earlier Poisson approximation and matches the production code across all stake sizes, including large "whale" accounts. Because high-stake accounts routinely have `w × τ / W` in the dozens, the Poisson shortcut systematically underestimates unique voters, whereas the binomial probability is exact. Summing the probability across every online account (from the CSV snapshot) yields the *expected number of unique voters* for any given step.

Applying this exact model to the November 24, 2025 stake snapshot produces the following expectations:

The table below shows the result of this calculation for the main consensus steps:

| Step      | Committee Size `N` | Expected Unique Voters (Theoretical) |
|-----------|--------------------|--------------------------------------|
| Soft      | 2,990              | **≈ 354**                            |
| Cert      | 1,500              | **≈ 233**                            |
| Next      | 5,000              | **≈ 477**                            |

It is important to understand that these numbers are the pure, unoptimized, statistical expectation. They represent the number of unique accounts that would be selected if the protocol ran to completion without any optimizations.

## 3. Theoretical Message Counts per Phase

Applying this model to each phase of a consensus round yields the following theoretical message counts.

*   **Proposal Phase:** The theoretical expectation is **≈ 20 proposals**, based directly on the `NumProposers=20` protocol parameter.

*   **Soft Vote Phase:** The theoretical expectation is **≈ 354 unique votes**, based on the calculation with `N=2,990`.

*   **Cert Vote Phase:** The theoretical expectation is **≈ 233 unique votes**, based on the calculation with `N=1,500`.

*   **Next Vote Phase:** "Next" votes are a core liveness mechanism. They are cast when a round is taking too long to certify a block, allowing the network to formally agree to move on to the next round. While they can be sent ahead of time as part of general network pipelining, their primary role is not pipelining itself, but ensuring the chain does not stall. The theoretical expectation for the number of potential Next voters is ≈ 477, based on the calculation with N=5,000, but these votes are typically absent in healthy rounds because the liveness path rarely triggers.

Summing the core components (Proposals, Soft, Cert) gives a total **theoretical core consensus traffic of ≈ 607 messages per round.** Including the liveness contingency adds another ≈ 477 potential Next votes, yielding ≈ 1,084 messages only in rounds that actually require the fallback.

---
# Part II: Protocol Optimizations
---

The theoretical profile calculated in Part I does not match observed network traffic. This is because the Algorand protocol includes several powerful optimizations designed to reduce message propagation. This section details those optimizations.

## 4. The Core Optimization: Threshold Termination

The most significant optimization is "threshold termination." The protocol does not wait for all theoretically selected voters to submit their votes. Instead, it stops counting and propagating votes for a given step as soon as a required *weight* threshold is met.

### 4.1 Quorum Detection

The `reachesQuorum` function in `agreement/types.go` checks if the accumulated vote weight has met the threshold for the current step (e.g., 2,267 for Soft votes, 1,112 for Cert votes). Once this returns true, the step concludes.

### 4.2 Impact on Observed Traffic

This mechanism has a dramatic effect on traffic. Because a small number of high-stake accounts can contribute a large amount of weight, quorum is often reached long before all ~354 (Soft) or ~233 (Cert) unique voters have been heard from.

This explains the discrepancy between the theoretical numbers and the observed telemetry:
*   **Soft Votes:** Theory predicts ≈ 354 voters, but telemetry typically shows **280-340** observed votes before the 2,267 weight threshold is met.
*   **Cert Votes:** Theory predicts ≈ 233 voters, but telemetry consistently shows only **101-186** observed votes before the 1,112 weight threshold is met (matching the empirical ranges in Section 8).

The optimization effectively "trims the tail" of the theoretical distribution, resulting in a statistically lower number of observed messages.

## 5. Supporting Optimizations: Deduplication and Filtering

In addition to threshold termination, the agreement layer employs several other filtering mechanisms to reduce redundant traffic.

*   **Sender-Based Deduplication:** The `voteTracker` in `agreement/voteTracker.go` ensures that a sender can only vote once per proposal, per step. Subsequent votes from the same sender are filtered and not propagated.
*   **Freshness Filtering:** The `voteAggregator` in `agreement/voteAggregator.go` rejects votes from old rounds or periods.
*   **Network-Level Deduplication:** At a lower level, both the relay network and P2P layers use hash-based deduplication to avoid processing the exact same message bytes twice. This is secondary to the agreement layer's more sophisticated semantic filtering.

## 6. Architectural Basis for Optimization

These optimization mechanisms are enforced by the agreement layer, making them a fundamental property of the protocol, independent of the network topology.

*   **Agreement Layer Control:** As shown in `agreement/gossip/network.go` and `agreement/player.go`, the network layer immediately passes messages to the agreement layer, which makes the explicit decision to `Relay` or `Ignore`. It does not relay automatically.
*   **Topology Independence:** Because the filtering logic resides in the agreement layer, it functions identically across relay networks, P2P networks, and any hybrid configurations. The topology affects *how* messages are routed, but not *which* or *how many* are ultimately propagated.

---
# Part III: Empirical Analysis of Observed Behavior
---

To complete the analysis, we collected empirical data from the Algorand mainnet to measure how closely the "theory + optimization" model matches reality and to pinpoint any systematic deviations. This section describes our data collection methodology and presents the results.

## 7. Data Collection Methodology

The empirical data was collected by instrumenting a standard Algorand participation node running in a **P2P hybrid mode**. The node was connected to the mainnet with a typical configuration of **~4 relay nodes** and **~60 P2P peers**. The core message counts cover 624 rounds within `consensus_messages-20251124.csv`, while the per-proposal detail log (`consensus_vote_details.csv`) spans 337 rounds (the detail logger was introduced partway through the capture window).

**Note on node choice:** A participation node was chosen for data collection purely for operational convenience. The agreement layer's design ensures that all nodes—relay or non-relay—observe the same set of *distinct consensus messages* before reaching their local threshold, making any well-connected node suitable for measuring the theoretical message generation rate. The per-peer message flow is topology-independent.

We "snooped" the consensus message traffic visible to this node over a 24-hour period on November 24, 2025. The instrumentation aggregated the number of unique consensus messages per round, recording them into the `consensus_messages-20251124.csv` file.

Each row in this file represents a single consensus round and contains the following key data points used in this analysis:
- `round`: The round number.
- `soft_votes`: The total count of unique soft votes observed by the node in that round.
- `cert_votes`: The total count of unique cert votes observed by the node in that round.
- `late_soft_votes`: The count of unique soft votes that were received for a round that was already completed.
- `late_cert_votes`: The count of unique cert votes that were received for a round that was already completed.
- `late_next_votes`: The count of unique "Next" votes that were received for a round that was already completed.
- `soft_unique_senders` / `cert_unique_senders`: Number of distinct accounts required to reach quorum during the round.
- `soft_total_unique_senders` / `cert_total_unique_senders`: Number of distinct accounts observed once late votes are included.
- `soft_periods` / `cert_periods`: Number of distinct periods whose votes were seen for that step within the round.
- `round_duration_ms`, `in_peers`, `out_peers`, `bundle_votes`: Timing and peer metadata captured at certification.

To support per-proposal analysis, the logger also writes `consensus_vote_details.csv`, which emits one row per `(round, step, period, proposal)` tuple. Each row lists whether the votes were on-time or late, how many distinct senders supported that proposal, and how many total messages were relayed for it. This auxiliary file makes it possible to determine whether additional periods or multiple competing proposals explain the gap between theoretical and observed totals.

## 8. Empirical Committee Realization and Amplification Metrics

The empirical dataset (337 rounds with per-proposal detail and 624 rounds in the summary logger) quantifies how the live network instantiates the theoretical committees and where message amplification arises. We structure the findings into five measurements.

### 8.1 Theoretical Committee Expectations

Using the November 24, 2025 stake snapshot and Algorand’s binomial sortition formula, the expected number of unique voters per round is:

- **Soft:** ≈ **353.78** accounts.
- **Cert:** ≈ **232.51** accounts.
- **Next:** ≈ **476.40** accounts (not observed in this capture).

These values incorporate the actual stake distribution rather than the nominal committee parameters.

### 8.2 On-Time Participation (Unique ÷ Theory)

On-time participation stays below the theoretical expectation because quorum weight is met before the full committee responds:

- **Soft:** Mean on-time unique ratio **0.885×** (±0.0023 s.e.; median 0.882×; 99th percentile 0.994×).
- **Cert:** Mean on-time unique ratio **0.600×** (±0.0029 s.e.; median 0.602×; 99th percentile 0.725×).

On-time message ratios match these numbers because each participant contributes one vote before quorum is satisfied. This validates that the theoretical committee-size model correctly predicts *who* participates in each step.

Because the theoretical expectation is constant across rounds (≈354 soft, ≈233 cert), scatterplots of observed on-time unique counts versus theory collapse to vertical bands centered on those constants. The ratios above therefore convey the same information more directly: observed points cluster tightly around the theoretical line for on-time uniques, while total-unique and total-message ratios (Sections 8.4–8.5) show the amplification once trailing proposals and duplicate deliveries are included.

The lower on-time ratio for cert (0.60× vs. 0.885× for soft) reflects the cert committee’s smaller expected size (1,500 vs. 2,990) combined with the whale-heavy stake distribution: the same high-stake accounts supply a larger fraction of the 1,112 cert quorum weight, so fewer total accounts need to respond before the threshold is hit.

### 8.3 Absence of Next Votes

The Next/liveness step never triggered during this capture window: all `next_*` columns remain zero. This indicates that every observed round completed soft and cert voting without invoking the liveness fallback, so the theoretical Next committee expectation (≈476 voters) remains a contingency for worst-case planning rather than an observed load.

### 8.4 Total Unique Amplification (Trailing Proposals + Cross-Round Stragglers)

Counting all unique senders attributed to a round yields:

- **Soft:** Mean total unique ratio **1.385×** theory (±0.0037 s.e.; median 1.374×; 99th percentile 1.636×).
- **Cert:** Mean total unique ratio **1.142×** theory (±0.0041 s.e.; median 1.131×; 99th percentile 1.396×).

This metric intentionally exceeds the single-round committee size because the logger attributes votes to the round in which they are received, not the round in which they were cast. “Total unique senders for round R” therefore includes both the on-time voters from round R’s committee and stragglers from round R−1 that arrive while round R is executing. It is an operational load measure—how many distinct votes the node must ingest—rather than evidence that more than ~354/~233 accounts were selected by sortition. Within a given round, the additional proposals that survive past quorum ensure that many of those stragglers are votes for losing candidates, but the primary driver of the >1.0 ratios is this cross-round attribution.

### 8.5 Message-Level Amplification

Counting all messages (on-time + pipelined + late) further amplifies load:

- **Soft:** Mean total message ratio **1.838×** theory (±0.0050 s.e.; median 1.823×; 99th percentile 2.173×).
- **Cert:** Mean total message ratio **1.439×** theory (±0.0050 s.e.; median 1.428×; 99th percentile 1.750×).

These ≈1.6× factors explain why the network relays ~970 core messages per round instead of the theoretical 607.

### 8.6 Duplication Factor (Messages per Sender)

Redundant gossip and retransmissions add ≈30% overhead per participant even after deduplication by sender:

- **Soft:** Mean duplication factor **1.33×** (±0.0010 s.e.; median 1.33×; 99th percentile 1.37×).
- **Cert:** Mean duplication factor **1.26×** (±0.0011 s.e.; median 1.26×; 99th percentile 1.31×).

### 8.7 Percentile Reference Table

| Phase | Metric | Mean | P50 | P90 | P95 | P99 |
|-------|--------|------|-----|-----|-----|-----|
| Soft  | Unique ÷ theory (on-time)  | 0.885× | 0.882× | 0.941× | 0.961× | 0.994× |
| Soft  | Unique ÷ theory (total)    | 1.385× | 1.374× | 1.456× | 1.512× | 1.636× |
| Soft  | Messages ÷ theory (total)  | 1.838× | 1.823× | 1.931× | 2.011× | 2.173× |
| Soft  | Duplication factor (total) | 1.327× | 1.326× | 1.352× | 1.357× | 1.374× |
| Cert  | Unique ÷ theory (on-time)  | 0.600× | 0.602× | 0.671× | 0.688× | 0.725× |
| Cert  | Unique ÷ theory (total)    | 1.142× | 1.131× | 1.234× | 1.283× | 1.396× |
| Cert  | Messages ÷ theory (total)  | 1.439× | 1.428× | 1.553× | 1.618× | 1.750× |
| Cert  | Duplication factor (total) | 1.260× | 1.258× | 1.287× | 1.295× | 1.310× |

(Next votes remain zero throughout the capture; see §8.3.)

### 8.8 Amplification Drivers and Observables

| Driver / Mechanism          | Observable Metric                                        |
|----------------------------|----------------------------------------------------------|
| Threshold termination      | On-time unique ÷ theory (Section 8.2)                     |
| Trailing proposals         | Total unique ÷ theory (Section 8.4)                       |
| Redundant gossip/delivery  | Messages ÷ theory and duplication factor (Sections 8.5–8.6) |

This mapping ties each causal mechanism to the statistic that quantifies it in the telemetry.

### 8.9 Takeaway

Thus, the discrepancy between theoretical and observed message volume is *not* due to higher-than-expected participation. On-time unique participation closely tracks the theoretical committees. The higher message counts arise from two amplification mechanisms:
1. **Multi-proposal contention:** trailing proposals continue to receive votes, so the union of unique senders exceeds the single-proposal expectation.
2. **Redundant delivery:** gossip relays multiple copies of the same vote, producing ≈1.3× duplication per sender.

These effects are persistent network characteristics and must be included in capacity planning even though the underlying committee-selection model is accurate.

---
# Part IV: Summary and Implications
---

## 9. Summary and Key Findings

This analysis provides two distinct but related views of consensus traffic: the theoretical potential and the empirically observed reality. The updated telemetry shows that while quorum formation follows the theoretical expectations (unique senders line up with theory), the total number of distinct *messages* per round can materially exceed the theoretical unique-voter counts because of redundant deliveries and trailing proposals. The empirical view therefore complements the theory by quantifying network amplification effects rather than exposing a flaw in committee-size modeling.

### 9.1 The Theoretical Model

The **Theoretical Message Count** represents the pure mathematical expectation for messages generated in a consensus round, derived from protocol parameters and the stake distribution.
*   **Proposals:** ≈ 20
*   **Soft Votes:** ≈ 354
*   **Cert Votes:** ≈ 233
*   **Next Votes (Liveness):** ≈ 477
*   **Total Theoretical Generation (Core + Next): ≈ 1084 messages per round**

This view is useful for understanding the raw output of the sortition algorithm and forms the conservative basis for bandwidth planning. In steady-state rounds (no Next votes) the model therefore projects **≈607 core messages per round**, a figure now directly comparable to the ≈970 messages actually observed.

### 9.2 Empirical Validation and Network Amplification

The **Empirically Observed Traffic**, collected via instrumentation, yields three conclusions:
1.  **Threshold Termination is Confirmed:** The number of *on-time* votes observed by the node (Avg: ~305 Soft, ~143 Cert) is consistently lower than the theoretical maximum, demonstrating that quorum weight, not committee size, determines when a step stops relaying votes.
2.  **Source of Late Traffic is Identified:** The granular `late_` vote metrics confirm that messages arriving after a step is complete are the remaining `soft` and `cert` votes from the theoretical committee, not `Next` votes as previously hypothesized.
3.  **Total Messages Exceed Theory:** When late votes are included, the node processes ~629 soft and ~335 cert votes per round on average—materially higher than the ≈354/233 unique-voter expectations. The per-proposal detail proves this isn’t double-counting the same accounts: the extra traffic is dominated by losing proposals whose committees keep voting after quorum has already been reached for the winner. The theoretical model remains accurate for predicting *participants*; the higher message totals reflect network amplification (duplicate deliveries plus competing proposals) that must be considered when modeling raw traffic.

For practical bandwidth modeling, operators should use the empirically measured totals (~629 soft, ~335 cert, ~970 core messages) rather than the theoretical baseline (~607), since the ≈1.6× amplification created by competing proposals and redundant delivery is a persistent network characteristic (per the 624-round summary and 337-round detail logs).

## 10. Conclusion

This paper now presents a two-part narrative: the theoretical derivation establishes the expected number of *unique voters* implied by the protocol parameters and stake snapshot (a prediction validated by telemetry), while the empirical measurements show that the network often relays more *messages* per round because losing proposals and redundant deliveries keep circulating after quorum. Threshold termination and late-vote composition behave exactly as specified; the surplus cert and soft messages simply reflect network amplification rather than a flaw in the committee-size model.

For capacity planning and future protocol upgrades, the theoretical maximum remains a reproducible baseline for unique participants. Operators should treat the empirically measured totals (~629 soft, ~335 cert, ~970 core messages) as the practical indicator of message load, recognizing that they include roughly one extra proposal’s worth of traffic per step due to honest-but-late votes from competing candidates.

---
## Appendix: Source Code References

All findings verified against the `algorand/go-algorand` repository:
- **Repository**: github.com/algorand/go-algorand
- **Access date**: 2025-11-20
- **Key files analyzed**: `config/consensus.go`, `agreement/types.go`, `agreement/voteTracker.go`, `agreement/voteAggregator.go`, `agreement/player.go`, `agreement/gossip/network.go`, `network/wsNetwork.go`, `network/p2pNetwork.go`, `network/messageFilter.go`, `network/p2p/pubsub.go`

---

# End of Document
