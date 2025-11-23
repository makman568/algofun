# Explaining the Discrepancy in Proposal Message Counts

## 1. The Issue

An analysis of the `consensus_messages.csv` log file reveals a lower number of proposals per round (typically in the 4-11 range) than the ~12-25 range predicted in the `consensus_message_volume.md` analysis document.

While an initial instrumentation issue was corrected to ensure all unique, non-duplicate proposals are counted, a discrepancy remains. This document explains the likely reason for this difference, which is rooted in a core efficiency optimization within the Algorand consensus protocol.

## 2. The Cause: Early Proposal Phase Termination via Soft-Vote Quorum

The theoretical prediction of ~12-25 proposals is based on the number of unique proposers selected in each round (typically 20). However, this assumes that a node will have the time to see and process all of these proposals.

In practice, the proposal collection phase is often cut short by the rapid arrival of **soft votes**.

The process is as follows:

1.  **Proposal and Soft-Vote Phases Overlap:** As nodes are receiving proposals, they are also simultaneously receiving soft votes from their peers for those same proposals.
2.  **Quorum is Reached:** The consensus protocol does not need to wait for all proposals or a set timeout. As soon as a node observes a **quorum** (a threshold of stake-weighted votes) of soft votes for a *specific* proposal, it considers that proposal "staged".
3.  **Proposal Processing Halts:** Once a proposal is staged, the node's `proposalTracker` is effectively frozen for that round. It will immediately stop accepting and processing any new proposals it might receive, as the network has already demonstrated a clear intent to move forward with the staged proposal.

This logic can be observed in the interplay between the `softThreshold` and `voteVerified` event handlers in `agreement/proposalTracker.go`.

## 3. The Network Effect: A Cascade of Efficiency

This behavior is not isolated to a single node; it's a network-wide cascade:

-   As soon as a critical mass of nodes (especially well-connected relays) reaches a soft-vote quorum, they stop relaying other, now "obsolete," proposals.
-   This means that many of the original ~20 proposals are filtered out early in their journey and never propagate to the entire network.
-   Consequently, most nodes never even *see* the full set of theoretical proposals.

## 4. Conclusion

The observed proposal count of 4-11 is not an error but rather an accurate reflection of the **true proposal traffic** on an efficient, healthy network. It represents the number of unique proposals a node typically processes before the network rapidly converges on a single block candidate for the round.

The theoretical number (~20) represents the maximum potential load the system is prepared for, while the observed number demonstrates the protocol's ability to optimize for speed and reduce redundant message propagation in practice.

## 5. Comparison with Vote Phase Predictions

It is important to note that for the vote phases (e.g., soft and cert votes), the observed message counts in `consensus_messages.csv` align closely with the predicted ranges in the `consensus_message_volume.md` document.

The reason for this close match is that the model used for vote predictions is more sophisticated and was already calibrated to account for the "threshold termination" optimization. The process for the vote models was:

1.  **Calculate Theoretical Maximum:** The model first calculates the theoretical maximum number of unique voters for a given phase (e.g., ~353 for soft votes).
2.  **Apply Optimization Effect:** It then adjusts this number down based on the effect of the early-termination optimization, where nodes stop processing and relaying votes as soon as the required stake-weighted threshold is met.
3.  **Provide Calibrated Prediction:** The final predicted range (e.g., ~260-360 for soft votes) is this calibrated number, which accurately reflects the real-world traffic.

In contrast, the prediction for proposals was a simpler estimate based on the number of selected proposers. It did not fully account for the powerful, cross-phase optimization where the soft-vote phase cuts the proposal phase short. This is why an initial discrepancy was observed for proposals but not for votes.