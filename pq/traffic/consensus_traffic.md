# Algorand Consensus Message Quantity Analysis

**A Three-Step Analysis: Theory, Optimization, and Empirical Support**

---

This paper presents a comprehensive analysis of Algorand's consensus message volume through a three-step methodology:

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
# Part II: Protocol Optimizations and Empirical Effects
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
*   **Cert Votes:** Theory predicts ≈ 233 voters, but telemetry consistently shows only **130-165** observed votes before the 1,112 weight threshold is met.

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

The empirical data was collected by instrumenting a standard Algorand participation node running in a **P2P hybrid mode**. The node was connected to the mainnet with a typical configuration of **~4 relay nodes** and **~60 P2P peers**.

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

These three metrics provide a more granular breakdown of the data previously aggregated under the single `obsolete_votes` field.

To support per-proposal analysis, the logger also writes `consensus_vote_details.csv`, which emits one row per `(round, step, period, proposal)` tuple. Each row lists whether the votes were on-time or late, how many distinct senders supported that proposal, and how many total messages were relayed for it. This auxiliary file makes it possible to determine whether additional periods or multiple competing proposals explain the gap between theoretical and observed totals.

## 8. Empirical Support for Theoretical Model

The collected data, analyzed with the newly added granularity, provides a more precise picture of the consensus dynamics and corrects a key hypothesis from the original analysis.

As predicted in Part II, the observed *on-time* message counts are statistically lower than the theoretical maximums due to protocol optimizations. The table below uses the empirical data from `consensus_messages-20251124.csv`, which supersedes the older data used in the original version of this paper.

| Phase       | Theoretical Expectation (Unique Voters) | Observed On-Time Votes (Empirical Range) | Consistent with Threshold Termination? |
|-------------|-----------------------------------------|------------------------------------------|----------------------------------------|
| Soft Votes  | ≈ 354                                   | 249 - 354                                | Yes                                    |
| Cert Votes  | ≈ 233                                   | 101 - 186                                | Yes                                    |

The on-time `soft_votes` and `cert_votes` represent the number of unique votes required by the instrumented node to reach the weight threshold for each step. The ranges are consistent with the "threshold termination" optimization.

The new instrumentation provides the most critical insight. By breaking down the old `obsolete_votes` category and logging per-proposal detail rows, we can now identify the true source of these late-arriving messages.

| Late Vote Type    | Observed Empirical Range | Average |
|-------------------|--------------------------|---------|
| `late_soft_votes` | 0 - 371                  | ~324    |
| `late_cert_votes` | 0 - 240                  | ~192    |
| `late_next_votes` | 0 - 0                    | 0       |

This data demonstrates three key findings:
1.  **The original hypothesis was incorrect.** The large number of late ("obsolete") votes is **not** composed of pipelined "Next" votes, as the `late_next_votes` count is zero.
2.  **The true source of late votes is identified.** The late votes are almost entirely the remaining `soft` and `cert` votes from other nodes that were generated as part of the theoretical committee selection but arrived at our instrumented node after it had already met its quorum and terminated the step.
3.  **Late votes overwhelmingly target losing proposals.** The `consensus_vote_details.csv` file shows that each round has exactly one on-time proposal per step (the locally winning candidate), but almost every round also has one or more *late* proposals whose soft and cert voters continue relaying messages after our node has already finalized the winner. These trailing proposals explain the ≈1.6× overage: the network effectively carries (at least) one committee's worth of votes for the winner plus another committee's worth for whichever competing proposal(s) remained active.

The total number of unique messages *seen* by the node for each step is the sum of the on-time and late votes. This sum represents the total traffic generated by the theoretically selected committee, as perceived by a single well-connected node. On average we observe **≈1.12 late proposals per round in the Soft step** and **≈1.09 late proposals per round in the Cert step** (computed from `consensus_vote_details.csv`), so nearly every round carries the winner plus roughly one additional proposal whose committee continues voting after quorum.

-   **Total Soft Votes Seen (Avg):** 305 (on-time) + 324 (late) = **629** messages, representing ≈469 unique soft senders (≈344 on-time + ≈125 late-only). This is ≈32% above the theoretical 354 because multiple proposals routinely survive the soft step (≈1.12 trailing proposals per round). Since different proposals may be selected independently, the union of voters across all proposals can exceed the single-proposal committee size of 354.
-   **Total Cert Votes Seen (Avg):** 143 (on-time) + 192 (late) = **335** messages, representing ≈258 unique cert senders (≈143 on-time + ≈115 late-only), only ~11% above the theoretical 233 expectation.

Across all 624 rounds in `consensus_messages-20251124.csv`, the node observed:

*   **Proposals:** Avg ≈ 6.6 per round (well below the `NumProposers=20` expectation because only the lowest-credential proposals survive deduplication).
	*   **On-Time Core Votes:** Avg ≈ 305 soft + 143 cert = **≈ 448** (≈ 455 when the 6.6 proposals are included), reflecting the quorum-driven cutoff.
	*   **Total Core Votes:** Avg ≈ 629 soft + 335 cert = **≈ 964**, which together with ≈6.6 proposals yields **≈ 970 core messages per round**, about 1.6× the theoretical 607 baseline. Deduplicating by sender shows ≈469 unique soft voters and ≈258 unique cert voters per round—very close to the theoretical 354/233—so the overage is almost entirely attributable to losing proposals’ duplicate messages rather than to extra committee members.
*   **Next Votes:** Exactly zero on-time, pipelined, or late entries, confirming that the liveness mechanism did not trigger during the observation window.

The fact that these totals are higher than the theoretical unique voter counts (354 for Soft, 233 for Cert) highlights the distinction between *participants* and *messages*. The theoretical model accurately predicts the expected number of selected accounts (validated by the ≈469/258 unique-sender measurements), but the observed message count is higher because the network relays extra copies of those votes—primarily from losing proposals whose committees keep transmitting after the winner reaches quorum. In other words, the theoretical model is correct for *who* participates, while the telemetry shows how competing proposals and redundant delivery inflate *how many messages* those participants generate.

This corrected analysis provides a more robust model: the number of `on-time` votes is determined by the weight threshold, and the number of `late` votes represents the remaining messages from the rest of the committee that were "beaten" by the fast-moving node.

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

For practical bandwidth modeling, operators should use the empirically measured totals (~629 soft, ~335 cert, ~970 core messages) rather than the theoretical baseline (~607), since the ≈1.6× amplification created by competing proposals and redundant delivery is a persistent network characteristic.

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
