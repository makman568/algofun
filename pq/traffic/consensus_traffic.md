# Algorand Consensus Traffic Analysis: Single-Channel Characterization

**Quantifying Per-Peer Consensus Message Flow**

---

## Summary

This paper characterizes the consensus message traffic on a single Algorand network channel (one peer connection). Using 1,001 rounds of empirical data from a single-relay node, we quantify exactly how many votes, proposals, and other consensus messages flow through one connection.

The key findings:

| Message Type | Theory | Observed | Ratio |
|--------------|--------|----------|-------|
| Soft votes | 354 | 303 | 0.86x |
| Cert votes | 233 | 144 | 0.62x |
| Proposals | 20 | 3.3 | 0.16x |
| Next votes | 477 | 0 | 0.00x |

The observed counts are consistently **below** theoretical expectations due to protocol optimizations—primarily threshold termination, which stops vote propagation once quorum weight is reached.

---

## Methodology

### Data Collection

**Dataset:** log5 (single-peer, 1,001 rounds)
- **Configuration:** Single relay connection via `-p` flag
- **Relay:** Algorand mainnet relay
- **Detailed logging:** Enabled via `logdetails` file
- **Round duration:** Mean 2,776 ms

**Files produced:**
- `consensus_rounds.csv` — per-round summary
- `consensus_votes_detail.csv` — every vote with timing metadata
- `consensus_proposals_detail.csv` — every proposal received

### Consensus Parameters

The Algorand protocol defines committee sizes and thresholds in `go-algorand/config/consensus.go`:

```go
NumProposers = 20
SoftCommitteeSize = 2990
SoftCommitteeThreshold = 2267   // 76%
CertCommitteeSize = 1500
CertCommitteeThreshold = 1112   // 74%
NextCommitteeSize = 5000
NextCommitteeThreshold = 3838   // 77%
```

These are not hard limits but statistical expectations for total committee weight.

### Stake Distribution

Using the November 2025 mainnet stake distribution (~1,700 online accounts, ~6.4B Algos), we calculate expected unique voters using the binomial sortition formula:

```
P(selected) = 1 - (1 - committee_size / total_stake)^stake
```

---

## Part I: Soft Votes

### 1.1 Theoretical Expectation

| Parameter | Value |
|-----------|-------|
| Committee size | 2,990 |
| Threshold | 2,267 (76%) |
| Expected unique voters | **354** |

### 1.2 Observed

| Metric | Value |
|--------|-------|
| Total per round | **303.0** |
| On-time (before threshold) | 168.9 |
| Late (after threshold) | 134.1 |
| Late percentage | 44.3% |
| Ratio to theory (354) | **0.856x** |

**Timing Breakdown:**

| When Vote Arrived | Count/Round | % |
|-------------------|-------------|---|
| During soft step (on-time) | 168.9 | 56% |
| During cert step (late) | 134.0 | 44% |
| After certification | 0.1 | <0.1% |
| **Total** | **303.0** | **100%** |

### 1.3 Explaining the Deviation

The 0.86x ratio emerges from two competing effects: extreme whale concentration that dramatically reduces the votes needed to reach threshold, offset by massive late arrivals.

#### Threshold Termination

Nodes stop propagating votes once quorum **weight** is reached (2,267). Since high-stake accounts contribute more weight per vote, fewer unique voters are needed to reach quorum.

#### Whale Concentration

**Vote Distribution (303,292 votes across 1,001 rounds):**

| Tier | Votes | % Votes | Weight | % Weight | Avg Wt/Vote |
|------|-------|---------|--------|----------|-------------|
| 1-10 | 10,001 | 3.3% | 885,467 | **31.6%** | 88.5 |
| 11-20 | 8,995 | 3.0% | 623,075 | **22.2%** | 69.3 |
| 21-30 | 9,949 | 3.3% | 515,111 | 18.4% | 51.8 |
| 31-50 | 18,324 | 6.0% | 368,358 | 13.1% | 20.1 |
| 51-100 | 36,187 | 11.9% | 127,030 | 4.5% | 3.5 |
| 101-200 | 55,223 | 18.2% | 93,743 | 3.3% | 1.7 |
| 201-500 | 86,965 | 28.7% | 108,560 | 3.9% | 1.2 |
| 500+ | 77,648 | 25.6% | 82,511 | 2.9% | 1.1 |

Key findings:
- Top 20 accounts cast only **6.3% of votes** but contribute **53.8% of weight**
- **~80x weight advantage** for top-10 vs small accounts (88.5 vs 1.1)

#### Mathematical Decomposition

```
Let:
  T = threshold = 2,267
  N = theoretical unique voters = 354
  C = committee size = 2,990
  w̄_uniform = C/N = 8.45 (uniform weight per voter)
  w̄_observed = 9.26 (actual average)
  G = Gini coefficient = 0.780 (very high inequality)

Uniform baseline (threshold termination only):
  V_uniform = T / w̄_uniform = 2,267 / 8.45 = 268.4 voters

Whale effect (empirical, whales-first ordering):
  V_whale = 38.2 voters

Whale reduction factor:
  ρ = V_whale / V_uniform = 38.2 / 268.4 = 0.142
```

#### The Overshoot Effect

The whale concentration is extreme—only ~38 voters are needed to reach threshold. However, 303 voters are observed—a **265-voter overshoot**.

This occurs because threshold termination is **ineffective for soft votes**:

1. **Phase overlap:** Soft phase overlaps with proposal processing
2. **Node advances:** After reaching threshold, node transitions to cert step
3. **Votes keep streaming:** 44% of soft votes arrive "late" (after node advances)
4. **Relay latency:** The relay doesn't instantly stop sending votes

**Why 44% of soft votes are "late":**

1. The relay (well-connected) accumulates 2,267 weight and stops actively soliciting votes
2. Votes already queued/in-transit continue arriving
3. After receiving enough weight, our node moves to cert step
4. Votes sent before relay's threshold arrive after our threshold
5. These votes are valid, consumed bandwidth, but arrived "late" relative to our state

"Late" does not mean wasted or duplicate—these 134 votes/round are real channel traffic.

#### Summary

| Stage | Voters | Reduction | Cumulative |
|-------|--------|-----------|------------|
| Theoretical (no termination) | 354 | — | — |
| + Threshold termination | 268 | 86 | 24% |
| + Whale concentration | 38 | 230 | 89% |
| On-time observed | 169 | +131 | 52% |
| Total observed (with late) | 303 | +134 | 14% |

The 0.86x ratio emerges from extreme whale concentration (86% reduction) being **offset** by massive late arrivals (+265 overshoot).

---

## Part II: Cert Votes

### 2.1 Theoretical Expectation

| Parameter | Value |
|-----------|-------|
| Committee size | 1,500 |
| Threshold | 1,112 (74%) |
| Expected unique voters | **233** |

### 2.2 Observed

| Metric | Value |
|--------|-------|
| Total per round | **143.8** |
| On-time (before threshold) | 143.5 |
| Late (after certification) | 0.4 |
| Late percentage | 0.3% |
| Ratio to theory (233) | **0.617x** |

**Timing Breakdown:**

| When Vote Arrived | Count/Round | % |
|-------------------|-------------|---|
| During cert step (on-time) | 143.5 | 99.7% |
| After certification | 0.4 | 0.3% |
| **Total** | **143.8** | **100%** |

**Validation:**

| Check | Result |
|-------|--------|
| Cert weight minimum | 1,112 (exactly at threshold) ✓ |
| Duplicates | 0 (single peer) ✓ |

Across 1,001 rounds, the minimum cert weight observed was **exactly 1,112**—the threshold. This confirms threshold termination works precisely.

### 2.3 Explaining the Deviation

The 0.62x ratio reflects effective threshold termination with minimal overshoot, amplified by whale concentration.

#### Whale Concentration

**Vote Distribution (143,973 votes across 1,001 rounds):**

| Tier | Votes | % Votes | Weight | % Weight | Avg Wt/Vote |
|------|-------|---------|--------|----------|-------------|
| 1-10 | 9,156 | 6.4% | 405,055 | **36.0%** | 44.2 |
| 11-20 | 7,217 | 5.0% | 250,269 | **22.2%** | 34.7 |
| 21-30 | 7,461 | 5.2% | 188,722 | 16.8% | 25.3 |
| 31-50 | 13,355 | 9.3% | 138,773 | 12.3% | 10.4 |
| 51-100 | 17,988 | 12.5% | 41,708 | 3.7% | 2.3 |
| 101-200 | 24,273 | 16.9% | 31,959 | 2.8% | 1.3 |
| 201-500 | 35,389 | 24.6% | 39,548 | 3.5% | 1.1 |
| 500+ | 29,134 | 20.2% | 29,976 | 2.7% | 1.0 |

Key findings:
- Top 20 accounts: **58.2% of cert weight** while casting only **11.4% of votes**
- **~44x weight advantage** for top-10 vs small accounts (44.2 vs 1.0)
- Cert shows higher whale concentration than soft (36% vs 31.6% for top 10) because the smaller committee (1,500 vs 2,990) amplifies stake-based selection probability

#### Mathematical Decomposition

```
Let:
  T = threshold = 1,112
  N = theoretical unique voters = 233
  C = committee size = 1,500
  w̄_uniform = C/N = 6.44 (uniform weight per voter)
  w̄_observed = 7.96 (actual average)
  G = Gini coefficient = 0.711 (high inequality)

Uniform baseline (threshold termination only):
  V_uniform = T / w̄_uniform = 1,112 / 6.44 = 172.7 voters

Whale effect (empirical, whales-first ordering):
  V_whale = 130.6 voters

Whale reduction factor:
  ρ = V_whale / V_uniform = 130.6 / 172.7 = 0.756

Whale savings:
  ΔV = V_uniform - V_whale = 42.2 voters/round
```

#### Why Cert Has Virtually No Late Votes

Unlike soft votes, cert has only 0.3% late votes because:
- Round terminates immediately upon certification
- No subsequent step for votes to arrive "late" into
- The 0.3% are edge cases (votes arriving within milliseconds of certification)

#### Summary

| Stage | Voters | Reduction | Cumulative |
|-------|--------|-----------|------------|
| Theoretical (no termination) | 233 | — | — |
| + Threshold termination | 173 | 60 | 26% |
| + Whale concentration | 131 | 42 | 44% |
| Observed (with overshoot) | 144 | +13 | 38% |

The 44% total reduction from theory (233 → 131 voters to threshold) decomposes as:
- **Threshold termination:** 26% reduction (stops voting at quorum)
- **Whale concentration:** 18% additional reduction (whales reach quorum faster)

The +13 overshoot is explained by in-flight votes (latency).

**Validation:**

| Metric | Model | Empirical | Match |
|--------|-------|-----------|-------|
| Voters to threshold | 131 | 130.6 | ✓ (<1% error) |
| Overshoot (in-flight votes) | — | 13.2 | Explained by latency |
| Total observed | 144 | 143.8 | ✓ |

---

## Part III: Proposals

### 3.1 Theoretical Expectation

| Parameter | Value |
|-----------|-------|
| NumProposers | 20 |
| Expected proposals | **~20** |

### 3.2 Observed

| Metric | Value |
|--------|-------|
| Total per round | **3.3** |
| Ratio to theory (20) | **0.16x** |

### 3.3 Explaining the Deviation

Only **3.3 proposals per round** are observed instead of 20 because of aggressive quorum-based filtering:

1. **Soft-vote quorum freezes proposals:** Once soft quorum forms for a leading proposal, the `proposalTracker` stops relaying new proposals

2. **Network propagation:** By the time proposals reach a single-peer node, quorum has often already formed at well-connected relays

3. **Competing proposals filtered:** Relays stop forwarding proposals for which they've already seen quorum

The 0.16x ratio reflects that most proposals are filtered before reaching edge nodes—only the leading proposal and a few early competitors make it through.

---

## Part IV: Next Votes

### 4.1 Theoretical Expectation

| Parameter | Value |
|-----------|-------|
| Committee size | 5,000 |
| Threshold | 3,838 (77%) |
| Expected unique voters | **477** |

### 4.2 Observed

| Metric | Value |
|--------|-------|
| Total per round | **0** |
| Ratio to theory (477) | **0.00x** |

### 4.3 Explaining the Deviation

Next votes are a **liveness mechanism** that triggers only when:
- A round takes too long to certify
- Network partition or failure conditions exist

In healthy network conditions (which describe 100% of our 1,001-round sample), Next votes never trigger. The theoretical 477 Next voters exist as capacity for failure recovery, not normal operation.

The 0.00x ratio is expected and healthy—it indicates the network is functioning normally without requiring the liveness fallback mechanism.

---

## Part V: Traffic Profile

### Vote Compression (vpack)

Algorand uses a custom compression scheme called **vpack** for consensus votes, implemented in `go-algorand/network/vpack/`. This is not generic compression—it's a domain-specific encoding that strips msgpack formatting and field names.

#### Compression Layers

Vote compression operates in two layers:

| Layer | Tag | Description |
|-------|-----|-------------|
| **Stateless** | `AV` | Strips msgpack field names, uses bitmask for optional fields |
| **Stateful** | `VP` | Adds lookup table for repeated values across votes |

From `msgCompressor.go`:
- Stateless compression is applied to all votes
- Stateful compression (when negotiated) further compresses by tracking common values between votes on the same connection

#### Vote Structure and Size

From `vpack.go`, a vote contains 14 fields (8 required, 6 optional):

**Required fields:**
- `cred.pf` — VRF proof (80 bytes)
- `r.rnd` — Round number (varint, typically 3-4 bytes)
- `r.snd` — Sender address (32 bytes)
- `sig.p`, `sig.p1s`, `sig.p2`, `sig.p2s`, `sig.s` — One-time signature components (32+64+32+64+64 = 256 bytes)

**Optional fields (presence indicated by bitmask):**
- `r.per` — Period (varint)
- `r.step` — Step (varint)
- `r.prop.dig`, `r.prop.encdig`, `r.prop.oper`, `r.prop.oprop` — Proposal metadata

#### Size Constants (from source)

```go
// go-algorand/network/vpack/vpack.go
MaxMsgpackVoteSize    = ~520 bytes  // Uncompressed msgpack
MaxCompressedVoteSize = 502 bytes   // Stateless compressed (worst case)
```

**Typical compressed vote size:** ~350-400 bytes

The maximum (502 bytes) assumes all optional fields present and maximum-length varints (9 bytes each). In practice:
- Varints are 2-4 bytes (not 9)
- Some optional fields are absent
- Stateful compression (VP) further reduces size

#### Proposal Compression

Proposals use **zstd compression** (not vpack):
- Tag: `PP` (ProposalPayload)
- Compression level: `BestSpeed`
- Typical compression ratio: ~40-50%

### Per-Round Message Summary

| Component | Messages/Round | Wire Bytes Each | KB/Round |
|-----------|----------------|-----------------|----------|
| Soft votes | 303 | ~350 | 106 |
| Cert votes | 144 | ~350 | 50 |
| Proposals | 3.3 | ~1,200 (zstd) | 4 |
| Cert bundle | 1 | ~6,000 | 6 |
| **Total** | **~451** | | **~166** |

*Note: "Wire Bytes" reflects compressed on-the-wire size, not uncompressed payload.*

### Bandwidth Estimate

At mean round duration of 2.78 seconds:

```
166 KB / 2.78 sec = 60 KB/sec = ~480 Kbps
```

**Single-channel consensus bandwidth: ~400-500 Kbps inbound**

This aligns with empirical observation via `iftop` showing ~400 Kbps on a live single-peer connection.

### Traffic Composition

| Component | % of Messages | % of Bandwidth |
|-----------|---------------|----------------|
| Soft votes | 67% | 64% |
| Cert votes | 32% | 30% |
| Proposals | 0.7% | 2% |
| Cert bundle | 0.2% | 4% |

Soft votes dominate both message count and bandwidth.

---

## Part VI: Summary

### Key Findings

1. **Soft votes:** 303 per channel (0.86x theory). Extreme whale concentration (86% reduction) is offset by 44% late arrivals.

2. **Cert votes:** 144 per channel (0.62x theory). Effective threshold termination with minimal overshoot. Top 20 accounts provide 58% of weight.

3. **Proposals:** 3.3 per channel (0.16x theory). Aggressive quorum-based filtering removes most proposals before they reach edge nodes.

4. **Next votes:** 0 per channel (0.00x theory). Liveness mechanism unused in healthy network conditions.

5. **Bandwidth:** ~400-500 Kbps per channel (vpack-compressed).

6. **Whale effect:** Top 20 accounts cast only 6-11% of votes but contribute 54-58% of weight. The ~44-80x weight advantage of top accounts explains why threshold termination is so effective.

### Deviation Summary

| Message Type | Theory | Observed | Ratio | Primary Cause |
|--------------|--------|----------|-------|---------------|
| Soft votes | 354 | 303 | 0.86x | Whale effect (86%) offset by late arrivals (+265) |
| Cert votes | 233 | 144 | 0.62x | Whale effect (24%) + effective termination (+13) |
| Proposals | 20 | 3.3 | 0.16x | Quorum-based filtering |
| Next votes | 477 | 0 | 0.00x | Healthy network (liveness unused) |

### Practical Implications

For capacity planning on a single peer connection:
- Budget **~450 messages/round** (not 607 theoretical)
- Budget **~400-500 Kbps** inbound bandwidth (vpack-compressed)
- Soft votes are the dominant traffic component (67%)
- Cert traffic is predictable and consistent

---

## Appendix: Data Source

**Dataset:** log5
- **Rounds:** 1,001
- **Configuration:** Single relay peer
- **Collection date:** November 2025
- **Files:** `consensus_rounds.csv`, `consensus_votes_detail.csv`, `consensus_proposals_detail.csv`

**Stake data:** `support/algorand-consensus-20251128.csv` — Account balances and voting eligibility (1,699 accounts)

**Analysis scripts:** Located in `/home/thong/algofun/pq/traffic/support/`
- `analyze_rounds.sh` — Per-round statistics
- `derive_voters.py` — Theoretical voter calculation from stake distribution
- `profile_votes_by_stake.py` — Vote distribution analysis by stake tier
- `quantify_whale_impact.py` — Mathematical decomposition of cert whale effect
- `quantify_whale_impact_soft.py` — Mathematical decomposition of soft whale effect

---

## End of Document
