# Algorand Consensus Traffic Analysis: Learnings and Findings

## Summary

This document captures key learnings from analyzing Algorand consensus traffic, comparing theoretical models with empirical data, and setting up single-peer measurements.

---

## 1. Theoretical Model

### Committee Parameters (go-algorand v8+)
| Step | Committee Size | Threshold | Expected Unique Voters |
|------|---------------|-----------|------------------------|
| Soft | 2,990 | 2,267 (76%) | ~354 |
| Cert | 1,500 | 1,112 (74%) | ~233 |
| Next | 5,000 | 3,838 (77%) | ~477 |

### Key Formula
The expected unique voters is derived from binomial sortition:
```
P(selected) = 1 - (1 - committee_size/total_stake)^stake
```
Summed across all online accounts.

---

## 2. Empirical Observations (Multi-Peer: ~54 peers)

### From log2 (22,529 rounds):
| Metric | Soft | Cert |
|--------|------|------|
| Unique voters/round | 305.7 | 146.9 |
| Ratio to theory | 0.864x | 0.630x |
| Weight (mean) | 2,802 | 1,125 |
| Weight (min) | 2,462 | **1,112** (exactly at threshold) |
| Weight (max) | 5,527 | 1,181 |
| Round duration (mean) | 2,784 ms |

### Key Finding
The cert weight minimum of exactly 1112 confirms **threshold termination** — voting stops precisely when quorum is reached.

---

## 3. Simulation vs Reality Discrepancy

### Simulation Results (random arrival order):
| Step | Simulated Voters | Simulated Ratio | Observed Ratio |
|------|-----------------|-----------------|----------------|
| Soft | 276 | 0.780x | 0.864x |
| Cert | 179 | 0.770x | 0.630x |

### Explanation of Discrepancies

**Cert (observed < simulated):**
- Simulation assumes random arrival order
- Reality: **whale votes arrive earlier** (better connectivity, selection bias from soft phase)
- Top 20 cert contributors provide **65.5%** of total cert weight
- Average weight: top 20 = 38.7, everyone else = 3.5 (11x difference)
- Fewer voters needed because high-weight votes arrive first

**Soft (observed > simulated):**
- Simulation measures voters **to threshold** (~209)
- Observation measures **total voters per round** (~305)
- Difference (~96 votes) = **post-threshold arrivals**
- Soft phase doesn't end immediately at threshold — overlaps with proposal processing
- Extra votes arrive before cert phase begins

**Cert matches because:**
- Round ends immediately upon certification
- No time for post-threshold arrivals
- Threshold count ≈ total count

---

## 4. Single-Peer vs Multi-Peer Traffic

### Multi-Peer Aggregation Effects
| Effect | Description | Impact |
|--------|-------------|--------|
| Redundant delivery | Same vote via multiple peers | ~1.3x message duplication |
| Post-threshold arrivals | Peers send until THEIR threshold | ~96 extra soft votes |
| Union of views | Each peer's threshold-limited stream | Higher total unique count |

### Initial Prediction (REVISED - see Section 12)
| Metric | Multi-Peer | Single-Peer (predicted) |
|--------|-----------|------------------------|
| Soft votes/round | ~306 | **~209** (no post-threshold) |
| Cert votes/round | ~147 | **~147** (same) |
| Duplicates | Some | **Zero** |

### Original Hypothesis
- Single relay applies threshold termination
- You only receive what that relay sends before **its** threshold
- No aggregation of multiple peers' views
- No duplicate deliveries

**Note:** This prediction was partially incorrect. See Section 12 for actual results.

---

## 5. Single-Relay Configuration

### config.json
```json
{
    "GossipFanout": 1,
    "CatchupParallelBlocks": 1,
    "IncomingConnectionsLimit": 0,
    "NetAddress": "",
    "EnableP2P": false,
    "EnableP2PHybridMode": false,
    "DNSBootstrapID": ""
}
```

### Start Command
```bash
algod -d /path/to/data -p "r-9e.algorand-mainnet.network:4160"
```

### Enable Detailed Logging
```bash
touch /path/to/data/logdetails
```

### Connection Terminology
| Config | Controls | Direction |
|--------|----------|-----------|
| `GossipFanout` | Max **outgoing** connections | You → relay |
| `IncomingConnectionsLimit` | Max **incoming** connections | Others → you |

Connecting TO a relay is an **outgoing** connection (you initiate).

---

## 6. TCP Connection Behavior

### Observed: Multiple TCP connections to same relay
Even with `GossipFanout: 1`, you may see 2-3 TCP connections to the relay because:

1. **Websocket connection** — persistent, for gossip (votes, proposals)
2. **HTTP connection(s)** — for block fetching, catchup

Both services are multiplexed on **port 4160**.

### This is still valid single-peer measurement
- All connections go to one relay IP
- Combined bandwidth represents single-peer traffic
- Consensus messages flow over websocket; blocks over HTTP

---

## 7. Bandwidth Measurement

### Observed Single-Relay Bandwidth
```
Inbound:  ~450 Kbps
Outbound: ~17 Kbps (non-participating node)
```

### Validation Calculation
| Component | Per Round | Size | Total |
|-----------|-----------|------|-------|
| Soft votes | ~306 | ~500 bytes | ~153 KB |
| Cert votes | ~147 | ~500 bytes | ~74 KB |
| Proposals | ~6-7 | ~2 KB | ~14 KB |
| Cert bundle | 1 | ~10 KB | ~10 KB |
| **Total** | | | **~250 KB/round** |

At ~2.8 sec/round: `250 KB / 2.8s = ~714 Kbps`

Observed ~450 Kbps suggests some compression or smaller average vote sizes.

---

## 8. Whale Concentration Analysis

### From Detailed Vote Logs
```
Top 10 cert contributors: 38.7% of total cert weight
Top 20 cert contributors: 65.5% of total cert weight
Top 30 cert contributors: 81.5% of total cert weight
```

### Weight per Vote
- Top 20 by stake: **38.7** average weight per vote
- Everyone else: **3.5** average weight per vote
- **11x difference**

### Implication
To reach cert threshold (1112):
- With whales arriving first: ~29 votes sufficient
- With random arrival: ~179 votes needed
- Observed: ~147 votes (whales arrive early, but not first)

---

## 9. Key Facts Determined

1. **Theoretical model is accurate** for predicting unique participants; discrepancies come from network effects

2. **Threshold termination works precisely** — cert weight minimum = exactly 1112

3. **Soft vs Cert discrepancy** explained by post-threshold arrivals (soft has ~96 extra, cert has ~0)

4. **Whale concentration** causes cert to need fewer voters than simulation predicts

5. **Single-peer traffic** is ~30% lower for soft votes than multi-peer (no post-threshold arrivals)

6. **Next votes are absent** in healthy rounds — liveness mechanism rarely triggers

7. **Per-peer bandwidth** is ~450 Kbps inbound for consensus traffic

8. **Multiple TCP connections** to same relay is normal (websocket + HTTP on port 4160)

9. **No duplicates expected** from single-peer connection

10. **`GossipFanout`** controls outgoing connections (you → relay), not incoming

---

## 10. Files and Tools

### Logging Output Files
- `consensus_rounds.csv` — per-round summary (always logged)
- `consensus_votes_detail.csv` — detailed votes (requires `logdetails` file)
- `consensus_proposals_detail.csv` — detailed proposals (requires `logdetails` file)

### Analysis Scripts
- `analyze_rounds.sh` — analyze consensus_rounds.csv, compare to theory
- `derive_voters.py` — simulates sortition to predict voters-to-threshold

### Stake Distribution
- `algorand-consensus-20251124.csv` — mainnet stake snapshot

### Data Files
- `log2/consensus_rounds.csv` — 22,529 rounds, multi-peer (~54 inbound)
- `log3/` — 150 rounds, single-relay (r-9e), with detailed vote logs

---

## 11. Open Questions / Future Work

1. Why exactly do whale votes arrive earlier? (connectivity, infrastructure, geographic distribution?)

2. Can we model weighted arrival order analytically instead of assuming random?

3. How does single-relay latency affect pipelined vote counts?

4. What is the variance in per-relay traffic across different relays?

---

## 12. Single-Relay Experiment Results (log3)

### Experiment Setup
- **Relay**: r-9e.algorand-mainnet.network:4160
- **Node location**: Germany (Hetzner)
- **Rounds captured**: 150 (rounds 55991305 to 55991559)
- **Detailed logging**: enabled via `logdetails` file

### Actual Results vs Prediction

| Metric | Predicted | Actual | Multi-Peer (22.5k) |
|--------|-----------|--------|-------------------|
| Soft votes/round | ~209 | **300.5** | 305.7 |
| Cert votes/round | ~147 | **144.1** | 146.9 |
| Duplicates | 0 | **0** ✓ | Some |
| Pipelined votes | Some | **0** | ~0 |

### Key Finding: Prediction Was Wrong for Soft Votes

The soft vote count did **NOT** drop as predicted. Analysis of detailed votes revealed:

| Soft Vote Category | Per Round | Percentage |
|--------------------|-----------|------------|
| **On-time** | 163.4 | 54% |
| **Late** | 137.6 | 46% |
| **Total unique** | 301.0 | 100% |

### Why Single-Relay Still Shows ~300 Soft Votes

1. **Relay sends votes until ITS threshold** (~163 on-time from node's perspective)
2. **Network latency** (Germany ↔ relay) causes timing mismatch
3. **Votes "in flight"** when relay reaches threshold still arrive at node
4. **Node has already advanced** → classifies them as "late"
5. **Logger counts ALL unique votes** (on-time + late) = ~301 total

### The "Late" Votes Are Real Traffic

The ~138 late soft votes are:
- Sent by relay **before** relay's threshold
- Received by node **after** node's threshold (due to latency)
- Still consume bandwidth — they're real network traffic

### Revised Understanding

| What We Thought | What Actually Happens |
|-----------------|----------------------|
| Single-relay reduces total soft votes | Single-relay eliminates **duplicates**, not total count |
| "Late" votes only from slower peers | "Late" is relative to YOUR threshold, not sender's |
| On-time count = total count | On-time ≠ total; difference = latency-induced "late" votes |

### Validated Predictions

1. **Zero duplicates** ✓ — Single source = no duplicate deliveries
2. **Zero pipelined votes** ✓ — Node kept pace with relay (no votes for future rounds)
3. **Cert votes unchanged** ✓ — 144.1 vs 146.9 (within variance)
4. **Cert has minimal late votes** ✓ — Only 1.0% late (round ends at certification)

### Bandwidth Implication

Single-relay bandwidth (~450 Kbps) reflects the **full vote stream** the relay sends:
- ~300 soft votes + ~144 cert votes + proposals + bundles
- This is valid per-peer traffic measurement
- The "late" votes are part of real bandwidth consumption

### Updated Key Facts

5. ~~**Single-peer traffic** is ~30% lower for soft votes than multi-peer~~
   **REVISED**: Single-peer **total** soft votes are similar (~301 vs ~306); the difference is:
   - Single-peer: zero duplicates
   - Multi-peer: includes duplicates from redundant delivery

---

## 13. Corrected Model of Consensus Traffic

### Per-Relay Traffic (What One Relay Sends)

| Component | Count/Round | Notes |
|-----------|-------------|-------|
| Soft votes | ~300 | All votes relay saw before its threshold |
| Cert votes | ~144 | All votes relay saw before certification |
| Proposals | ~6-7 | Varies by round |
| Cert bundle | 1 | ~133 votes in bundle |

### Multi-Peer Aggregation

With N peers, you see:
- **Union** of each peer's ~300 soft votes (with overlap)
- **Duplicates** where multiple peers send same vote
- **Result**: ~306 unique soft + ~1.3x duplication factor

### Single-Peer Measurement Value

Single-relay logging provides:
1. **Clean per-peer traffic** — no duplicate counting confusion
2. **True relay output** — what one relay actually sends
3. **Latency visibility** — on-time vs late shows timing relationship
4. **Bandwidth baseline** — ~450 Kbps = realistic per-peer load

---

## 14. Cert Traffic Summary (Well Understood)

### Parameters
| Aspect | Value |
|--------|-------|
| Committee size | 1,500 |
| Threshold | 1,112 (74%) |
| Theoretical unique voters | ~233 |

### Observed Behavior
| Metric | Single-Peer (150) | Multi-Peer (22.5k) |
|--------|-------------------|-------------------|
| Voters/round | 144.1 | 146.9 |
| Ratio to theory | 0.62x | 0.63x |
| Late votes | ~1% | ~1% |
| Weight minimum | 1,112 | 1,112 |

### Why Cert is Predictable

1. **Immediate termination** — Round ends at certification, no post-threshold arrivals
2. **Whale concentration** — Top 20 accounts provide 65.5% of cert weight (avg 38.7 vs 3.5 for others)
3. **Threshold termination verified** — Minimum weight = exactly 1,112 across thousands of rounds
4. **Single vs multi-peer identical** — Only duplicates eliminated, not total count

### Per-Round Cert Bandwidth
| Component | Size |
|-----------|------|
| Cert votes (~147 × 500 bytes) | ~74 KB |
| Cert bundle (~134 votes) | ~10 KB |
| **Total cert traffic** | **~84 KB/round** |

### Key Insight
Cert traffic is deterministic: whale votes arrive early, threshold is reached with ~147 voters, round terminates immediately. No timing ambiguity, no late votes, no variance between single/multi-peer setups.
