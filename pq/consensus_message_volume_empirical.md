# Empirical Consensus Message Volume vs. Analytical Prediction

## 1. Context

The original `consensus_message_volume.md` paper estimated that Algorand rounds carry ~65–97 protocol-centric messages (or 115–157 concurrent gossip flows when next votes are included). Those figures fed directly into the Falcon envelope bandwidth analysis.

We instrumented `go-algorand` 4.4.1 with the `consensus_messages.csv` logger (counts proposals, soft votes, cert votes, next votes per round) and deployed it on production nodes. Sample output:

```
round,proposals,soft_votes,cert_votes,next_votes
55802615,0,309,164,0
55802616,4,331,157,0
55802617,6,334,151,0
55802618,1,321,163,0
55802619,1,285,139,0
```

We consistently observe:
- **Soft votes:** ~280–340 unique votes per round
- **Cert votes:** ~130–165 unique votes per round
- **Proposals:** ~0–6 (minor noise; the number of *unique* proposals that survive dedup each round)

Even with no next-vote logging yet, the measured totals per round exceed 400 messages—roughly **3×** the analytical estimate.

## 2. Why the empirical counts are higher

1. **Sortition weights vs. account counts**  
   `NumProposers`, `SoftCommitteeSize`, etc., are expectations over *weight*, not “number of accounts.” In today’s network, many medium-stake accounts (~5–10 weight) are online. To reach 2,267 soft weight you need ~300 of them; you do not see “75% stake in 40 operators” behavior in practice.

2. **Logger placement**  
   The paper implicitly counted only the votes that make it into the bundle (minimal quorum proof). Our instrumentation runs in `voteTracker.handle`, i.e., every deduped, fresh vote that arrives before threshold. Threshold termination still happens, but the logger captures the entire participation up to that point. That’s the right view for bandwidth budgeting—and it’s naturally higher than “votes in the final cert.”  
   - Code reference: `agreement/voteTracker.go:100-150` increments `recordConsensusVote` before any threshold logic.  
   - Bundles are trimmed later (weights sorted, truncated once quorum reached) in `agreement/voteTracker.go:317-360`, so the cert contains far fewer votes than what gossip actually carried.  
   - Proposals are logged in `agreement/proposalTracker.go:157-188` (post-dedup) and rounds flush when `player.handleThresholdEvent` sees a cert event (`agreement/player.go:349-376`), all of which happen prior to bundle packing.

3. **Stale assumptions about stake concentration**  
   The paper modeled top-40 accounts holding 75% stake with ~50–60 weight each. Real mainnet has many mid-tier validators; they participate and get logged. Unless the network re-concentrates, committees will continue to require hundreds of distinct votes per step.

4. **Next votes omitted**  
   Our current CSV logs proposals/soft/cert only. Once next votes are instrumented, the per-round total will be even higher than the ~450 messages we already see. That widens the gap versus the paper’s 115–157 concurrent message claim.

## 3. Implications for Falcon envelopes

Falcon envelope analysis assumed 115–157 messages/round → 30k rounds/day → ~4.5–8.5 GB/day of extra relay load. With empirical counts around 450 messages/round, the projected envelope traffic scales proportionally: expect **3× higher bandwidth** than the paper states. Any envelope rollout plan must use real telemetry rather than the optimistic analytical model.

## 4. Conclusion

The original analytical estimate understated consensus message volume because it relied on:
- Idealized stake concentration (few large operators satisfying quorum) and
- Counting only the minimal cert bundle rather than all votes gossiped until threshold.

Instrumentation shows that mainnet routinely exchanges ~300 soft + ~150 cert votes per round. The Falcon envelope cost (and any post-quantum bandwidth planning) must therefore be recalculated using these empirical counts; otherwise upgrade budgets will be off by a factor of ~3. We will continue logging to capture next votes and to monitor how stake distribution changes over time.
