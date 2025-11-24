# Algorand Post-Quantum Consensus before PQ-VRF

## Falcon Envelopes

# 1. Introduction

This paper proposes a technique that effectively provides for the PQ safety of Algorand
consensus before the long-term goal of a Post-Quantum VRF is put into place. It is NOT meant
to replace the full PQ-VRF solution that will eventually be put into place; instead, it
proposes a way to achieve quantum safety before today's elliptic-curve VRF is upgraded.

Algorand's consensus protocol requires that all committee messages be authentically linked
to the participation key owner. Quantum computers breaking participation-key identities put that
authentication at risk. However, Algorand consensus does not rely on VRF secrecy for safety—it
relies on message authenticity. Falcon Envelopes provide a minimal PQ authentication layer by
wrapping each BA★ message in a Falcon-1024 signature. Wrappers are verified during gossip and
cached temporarily for catchup peers. No block-format changes, no ledger growth, and no protocol
redesign. Notably, Falcon-1024 verification is ~5-10× faster than Ed25519, making this upgrade
a CPU performance improvement rather than a tradeoff.

# 2. Background

Algorand's security comes from three components: VRF-based eligibility, Ed25519 authentication,
and participation-key identity. A CRQC breaks all three, but BA★ safety depends only on authentic
messages, not VRF unpredictability. Falcon-1024 keypairs already exist inside participation keys
(`stateproof_pk`, `stateproof_sk`), originally for state proofs. These keys can be reused to provide
post-quantum authentication for consensus with zero changes to user workflows.

# 3. Threat Model

## 3.1 Adversary Capabilities

A quantum adversary can forge VRFs, forge Ed25519 signatures, and derive EC participation keys.
However, Falcon-1024 remains secure. Thus, replacing Ed25519 with Falcon signatures immediately
restores identity integrity. Forged VRFs become harmless noise: without a valid Falcon wrapper,
messages are dropped automatically. BA★ safety and liveness remain intact.

## 3.2 Degraded Properties Under Quantum Attack

**Properties Lost:**

- **Committee secrecy:** Adversary can predict current round selection once seed is published
- **Player replaceability:** Targeted DoS attacks become somewhat possible, though with great difficulty.
- **VRF unpredictability:** Future outputs computable once seed is known

**Properties Preserved:**

- **VRF verification:** Outputs remain checkable and deterministic
- **Sortition validity:** Cannot forge false committee selection
- **Message authentication:** Restored via Falcon-1024
- **BA★ safety:** Authenticated messages prevent forgery

**Critical distinction:** VRF secrecy (unpredictability) is lost, but VRF verification
(correctness checking) remains intact. Selection can be predicted but not forged.

# 4. Requirements for a Post-Quantum Upgrade

A PQ upgrade for Algorand must maintain BA★ safety, preserve liveness, avoid changes to blocks or
ledger state, reuse existing participation keys, support catchup without storing historic votes,
and impose minimal overhead. Falcon Envelopes satisfy all constraints with no modifications to
consensus rules.

## 4.1 Safety Preservation

BA★ safety requires that messages be authenticated. Under quantum attack, VRFs may be forgeable,
but authenticated Falcon-1024 wrappers guarantee that only legitimate committee members can send
valid votes or proposals.

## 4.2 Liveness Preservation

Liveness depends on reliable gossip, predictable round transitions, and minimal cryptographic
overhead. Falcon Envelopes introduce no new waiting conditions, no certificate assembly phases,
and no latency-sensitive operations.

## 4.3 No Ledger or Block-Format Changes

Algorand's block and header formats must remain small and stable. Falcon Envelopes are entirely
ephemeral and leave all on-chain structures unchanged.

## 4.4 Avoid Heavy Cryptographic Machinery

PQ multisignatures, PQ aggregation, and threshold certificates impose megabyte-scale overheads.
Falcon Envelopes require none of these, minimizing complexity and risk.

## 4.5 Reuse Existing Falcon Keys

Participation keys already include Falcon-1024 keypairs. No new user workflows or registration
steps are required.

## 4.6 Preserve Catchup Protocol

Catchup relies on state proofs and recent block headers—not historic BA★ votes. Falcon Envelopes
introduce only a temporary envelope cache for recent blocks, with automatic pruning.

## 4.7 Minimal Performance Overhead

Falcon Envelopes stay within relay node bandwidth and CPU budgets and maintain fast consensus.

# 5. Falcon Envelope Architecture

Falcon Envelopes wrap every BA★ message in a Falcon-1024 signature, providing PQ authentication
while preserving all protocol semantics.

## 5.1 Existing Participation-Key Material

Participation keys contain:

```
stateproof_pk
stateproof_sk
```

These Falcon-1024 keys are reused for consensus authentication.

## 5.2 PQ Message Wrapping

Every consensus message is accompanied by:

```
pq_sig = Falcon.Sign(stateproof_sk, transcript)
```

Nodes verify:

```
Falcon.Verify(stateproof_pk, transcript, pq_sig)
```

Invalid messages are dropped.

## 5.3 Transcript Binding

Transcripts include:

```
H('ALG-PQ-AUTH-V1' || genesis_hash || round || step || role || vrf_output || payload_hash)
```

**Components:**

- **Domain separator:** `'ALG-PQ-AUTH-V1'` (prevents cross-protocol signature reuse)
- **Genesis hash:** Prevents cross-chain replay (TestNet vs MainNet)
- **Round, step, role:** Prevents cross-round and cross-step replay
- **VRF output:** Binds to eligibility proof (even if VRF is forgeable)
- **Payload hash:** Binds to actual message content

This ensures message authenticity, role binding, and payload integrity.

## 5.4 Falcon Envelope Cache Lifecycle

**Cache Purpose:**
Support catchup peers requesting recent blocks not yet covered by a State Proof.

**Retention Policy:**
Nodes retain envelopes for all rounds R where:

```
last_state_proof_round < R ≤ current_round
```

**Typical retention window:** 256 rounds (one State Proof interval)  
**Maximum retention:** 400 rounds (emergency buffer if State Proof generation delayed)

**Pruning Trigger:**
When a new State Proof at round K is verified:

1. Delete all envelopes for rounds ≤ K
2. Retain only envelopes for rounds K+1 to current
3. Free memory automatically

**Storage Requirements:**

- **Typical:** 256 rounds × 100 envelopes × 1.5 KB = 38 MB
- **Worst case:** 400 rounds × 120 envelopes × 1.8 KB = 86 MB
- **Storage type:** RAM-only cache (never written to disk or chain)

**Serving to Catchup Peers:**
When a catchup peer requests blocks R₁ to R₂:

- If R₁ ≤ last_state_proof_round: Serve State Proof hash only (no envelopes needed)
- If R₁ > last_state_proof_round: Serve cached envelopes for verification
- If envelopes missing (pruned early): Return error; peer retries with different node

**Envelope Unavailability Handling:**

- **Scenario 1:** Peer pruned too early (clock skew, bug)
    - Response: "ENVELOPES_UNAVAILABLE"
    - Syncer action: Request from different peer

- **Scenario 2:** No peers have envelopes (coordinated failure)
    - Syncer action: Wait for next State Proof, then fast-catchup
    - Degraded but safe (can't verify recent blocks until State Proof)

- **Scenario 3:** Malicious peer sends invalid envelopes
    - Falcon signature verification fails
    - Syncer action: Ban peer, request from different source
    - Security: Unaffected (invalid signatures detected immediately)

## 5.5 No Ledger Changes

No block or ledger structures change. Envelopes are never written to chain data structures.

## 5.6 VRF Verification Under Quantum Attack

VRF verification continues to function correctly even under quantum attack. This is a critical
property that distinguishes VRF *secrecy* (broken) from VRF *verification* (intact).

**Verification Process:**

1. Extract sender's public key from participation record
2. Compute expected VRF output: `VRF_expected = f(pk, seed, round)`
3. Compare with provided VRF output in message
4. Reject if mismatch
5. Check if output meets selection threshold given stake

**Why This Works Under Quantum Attack:**

- VRF outputs are **deterministic** (function of public key + seed)
- Anyone can verify the output matches the declared public key
- Deriving the secret key doesn't let you forge different outputs
- The output is **publicly checkable** by all nodes

**What Quantum Computers Break:**

- VRF secrecy (outputs become predictable once seed is known)
- Committee anonymity (selection becomes public knowledge)

**What Remains Secure:**

- VRF verification (outputs remain deterministically checkable)
- Selection validity (cannot claim false committee membership)
- Sortition correctness (threshold checks work as designed)

**Attack That Does NOT Work:**

```
Attacker: "I'm selected! Here's my VRF output: X"
           [signs with valid Falcon key]
           
Verifier: "Let me check... given your public key and the seed,
           your VRF output should be Y, not X."
           REJECTED (VRF verification failed)
```

**Result:** Even with quantum-derived secret keys, adversaries cannot forge committee membership
because VRF outputs are deterministic and publicly verifiable. They can predict WHO will be
selected, but cannot make THEMSELVES selected when they're not.

# 6. Consensus Logic Unchanged

BA★ phases—proposal, soft vote, cert vote, next vote—remain exactly as defined. Thresholds,
timeouts, and round transitions do not change. Only:

```
Ed25519.Sign → Falcon.Sign
Ed25519.Verify → Falcon.Verify
```

is modified throughout the consensus message authentication layer.

# 7. Why Falcon Envelopes Preserve BA★ Safety

Falcon Envelopes restore the only property BA★ requires under quantum threat: authenticated
identity. VRF forgery becomes irrelevant because a forged VRF output without a corresponding
Falcon-1024 wrapper is ignored. BA★ safety—agreement, consistency, and validity—holds exactly as
before.

## 7.1 VRF Forgery Is Harmless

A quantum attacker can compute VRF outputs, but cannot forge selection because:

- VRF outputs are deterministic and verifiable by all nodes
- Claiming false selection fails VRF verification
- Without valid Falcon signature, message carries zero weight and is discarded

## 7.2 Identity Authentication Restored

Falcon-1024 wrappers provide post-quantum authentication. Impersonation of committee members
becomes impossible, restoring BA★ safety even under full EC compromise.

## 7.3 Weight Accumulation Remains Correct

Consensus weight derives from stake associated with participation keys. Falcon authentication
ensures only legitimate weight is counted.

## 7.4 Safety Proofs Remain Valid

BA★ safety proofs assume three properties:

1. Messages are authentically bound to participation keys
2. VRF sortition is correct (but not necessarily secret)
3. Byzantine nodes comprise < 1/3 of stake

Falcon Envelopes preserve all three:

1. **Authentication:** Falcon-1024 provides authentic binding (quantum-resistant, stronger than Ed25519)
2. **Sortition:** VRF selection mechanism unchanged (verification still works per Section 5.6)
3. **Byzantine threshold:** Stake distribution and threshold rules unchanged

Therefore, all existing BA★ safety proofs remain valid with the authentication substitution:

```
Ed25519_Auth(msg) → Falcon1024_Auth(msg)
```

This is a conservative strengthening (quantum-resistant cryptography), not a weakening.
The proof structure remains identical; only the authentication primitive has been upgraded.

# 8. Why Falcon Envelopes Preserve BA★ Liveness

Falcon Envelopes introduce no new waiting conditions and require no aggregation. Liveness remains
unchanged because gossip continues normally and nodes verify messages in parallel.

## 8.1 Gossip Behavior Unchanged

Consensus messages are validated, deduplicated, and propagated as before. Falcon verification
fits within gossip latency budgets.

## 8.2 Falcon Verification Is Parallelizable

Falcon-1024 verification is slower than Ed25519 but easily parallelized. Relays process tens to
hundreds of consensus messages per round without issue.

## 8.3 No New Timeouts or Waiting Stages

Threshold certificates require collection, assembly, and verification. Falcon Envelopes avoid
all certificate machinery, preserving fast round transitions.

## 8.4 Catchup Behavior

**Long-range catchup (unchanged):**
Uses State Proofs to skip millions of rounds. No envelope dependency.

**Short-range catchup (minor addition):**
For blocks since last State Proof:

- Nodes must serve Falcon Envelope cache to catchup peers
- Peers verify Falcon signatures on recent blocks
- If envelopes unavailable, fall back to waiting for next State Proof

**Data dependencies:**
Catchup for recent blocks (since last State Proof) now requires:

1. Block data (unchanged)
2. Falcon Envelopes (new, temporary dependency served from RAM cache)

**Impact:** Minimal

- Envelopes served from in-memory cache (fast, ~50-100ms)
- If cache miss, peer requests from different node
- Worst case: wait for next State Proof (maximum 256 rounds ≈ 12 minutes)

**New Degraded Mode:**
If envelope cache is unavailable across all peers (coordinated pruning, network partition):

- Catchup nodes cannot verify recent blocks independently
- Must wait for next State Proof (maximum 256 rounds ≈ 12 minutes)
- This is a NEW failure mode not present in classical Algorand

**Mitigation:**

- Unlikely scenario (requires coordinated cache miss across entire network)
- Temporary delay only (12 minutes maximum)
- State Proof provides guaranteed fallback
- Impact: Catchup latency degradation, not safety violation

The catchup protocol gains a small temporary data dependency but remains fundamentally
unchanged in structure and performance.

## 8.5 Recovery Mode and Transient Spikes

In rare instances of network partition or heavy packet loss, Algorand enters **Recovery Mode**,
utilizing larger committees (5,000+ participants) to force consensus and recover from deadlock.

**Transient Load During Recovery:**
During recovery, the number of Falcon Envelopes may spike significantly (2×-5× baseline volume)
as the network attempts to gather a supermajority from a larger committee pool.

**Example Spike Scenario:**

```
Normal operation: ~1,084 envelopes/round → 4.1-5.6 Mbps
Recovery mode: 1,500-2,500 envelopes/round → 5.6-12.8 Mbps (temporary)
```

**Relay Infrastructure Resilience:**
Even if the bandwidth load temporarily surges to ~12.8 Mbps during a recovery window, this
remains comfortably within the burst capacity of standard relay infrastructure:

- Modern relay nodes: 1 Gbps uplinks
- Actual burst requirement: ~12.8 Mbps
- Utilization during spike: < 1.3% of link capacity

**No Death Spiral:**
The protocol naturally reverts to standard committee sizes immediately upon round finalization.
Recovery mode is a transient state, typically lasting only a few rounds (< 30 seconds). The
system is designed to handle these short-duration bursts without entering congestion collapse
or creating a cascading failure mode.

**Assessment:** Recovery mode spikes are bounded, transient, and well within infrastructure
capacity. They do not threaten network stability or create sustained overload conditions.

# 9. Performance Model

Falcon Envelopes affect only gossip-layer bandwidth and in-memory caching. They impose no
ledger growth and no block-format overhead.

## 9.1 Envelope Size

- Falcon-1024 signature: ~1.2-1.3 KB
- Metadata: 0.2-0.4 KB
- **Total: 1.3-1.8 KB per envelope**

## 9.2 Envelopes per Round

### 9.2.1 Conservative Bandwidth Modeling Using Theoretical Maximum

For capacity planning and infrastructure provisioning, we use the **theoretical maximum message generation**
as a conservative upper bound rather than relying on empirical observations from specific nodes.

**Theoretical Total (Conservative Estimate):**
Using the November 23, 2025 stake distribution (`algorand-consensus.csv`) and the Poisson model from
`consensus_traffic.md`, the theoretical maximum message generation is:

- **Proposals:** ~20 messages
- **Soft votes:** ~354 messages (committee size 2,990)
- **Cert votes:** ~233 messages (committee size 1,500)
- **Next votes (pipelined):** ~477 messages (committee size 5,000)
- **Total theoretical generation: ~1,084 messages per round**

**Empirical Support:**
Mainnet telemetry from a well-connected node shows observed totals of ~1,077 messages per round,
closely matching the theoretical prediction. This supports the theoretical model and demonstrates
that it accurately represents real network behavior.

**Why Use Theoretical Rather Than Empirical:**

1. **Conservative:** Provisions for unoptimized worst-case scenarios
2. **Reproducible:** Anyone can verify the calculation from protocol parameters and stake distribution
3. **Topology-independent:** Not dependent on specific node position or network observations
4. **Protocol-grounded:** Derived directly from source code parameters (`config/consensus.go`)
5. **Future-proof:** Remains valid even if optimizations or network topology change

**For Falcon Envelope bandwidth calculations, we use ~1,084 envelopes per round** as the conservative
planning estimate. This represents the theoretical maximum that could be generated, supported by
empirical data showing actual generation closely matches this theoretical bound.

## 9.3 Rounds per Day

Block time = 2.85 seconds → **30,316 rounds/day**.

## 9.4 Relay Bandwidth Impact

Using the conservative theoretical estimate of **1,084 envelopes per round**:

Lower bound (compact envelopes):

```
1,084 × 1.3 KB × 30,316 ≈ 42.7 GB/day ≈ 4.1 Mbps
```

Upper bound (larger envelopes):

```
1,084 × 1.8 KB × 30,316 ≈ 59.1 GB/day ≈ 5.6 Mbps
```

Midpoint estimate:

```
1,084 × 1.5 KB × 30,316 ≈ 49.3 GB/day ≈ 4.7 Mbps
```

**Current baseline:** 3-8 GB/day (0.3-0.8 Mbps)
**With Falcon Envelopes:** 45-67 GB/day (4.3-6.4 Mbps) (baseline + PQ overhead)
**Increase factor:** ~6-9×, depending on relay role and peering.

### 9.4.1 Per-Peer Bandwidth Model

The bandwidth figures above represent the **per-peer traffic flow** between any two connected nodes in the network, regardless of node type (relay-to-relay, relay-to-participation, or participation-to-participation). The aggregate bandwidth a node experiences scales with its number of peer connections, but the per-peer message flow remains constant and topology-independent.

A relay node with many peers (e.g., 50-100 connections) will experience higher aggregate bandwidth proportional to its peer count. A participation node with fewer peers (e.g., 4-8 connections) will experience lower aggregate bandwidth. However, the bandwidth per individual peer connection remains consistent at ~45-67 GB/day as calculated above.

## 9.5 Storage (Falcon Envelope Cache)

- **Retention window:** 256-400 rounds
- **Envelopes per round:** ~1,084 (theoretical maximum)
- **Size per envelope:** 1.3-1.8 KB
- **Total storage:** ~416 MB (typical: 256 rounds × 1,084 × 1.5 KB) to ~780 MB (worst: 400 rounds × 1,084 × 1.8 KB) RAM
- **Type:** In-memory cache only (not persisted to disk)
- **Pruning:** Automatic when State Proof covers range

## 9.6 CPU Verification Cost

**Single Verification:**

- Ed25519: ~0.05-0.1 ms
- Falcon-1024: ~0.01 ms
- **Increase factor:** ~0.1-0.2× (Falcon is actually faster)

**Per-Round Verification (Relay Node):**

- Messages received: ~1,084 (theoretical maximum)
- Sequential verification time: 10.84 ms
- Block time budget: 2,850 ms
- **CPU overhead (sequential):** 0.38% of block time

**With Parallelization:**

- Falcon verification is embarrassingly parallel (no dependencies)
- 8-core relay: effective overhead ≈0.05% (10.84 ms ÷ 8 cores)
- 4-core relay: effective overhead ≈0.10%
- **No liveness impact**

**Byzantine Flood Resilience:**
Message flooding is not a new attack—it exists in current Algorand.
Falcon Envelopes actually decrease per-message verification cost (Falcon is ~5-10× faster
than Ed25519 for verification) and do not create new vulnerabilities.

Existing defenses remain effective:

- **VRF verification first:** Fast path (1ms) rejects invalid eligibility before Falcon check
- **Rate limiting per peer:** Prevents sustained floods
- **Early abort:** Stop verification on first invalid signature
- **Message deduplication:** Hash-based filtering prevents reprocessing
- **Peer reputation tracking:** Deprioritize or ban sources of invalid messages

**Assessment:** Falcon verification is actually faster than Ed25519, so no new DoS
vulnerabilities are introduced. The existing Byzantine resistance mechanisms remain fully effective.

# 10. Benefits of the Falcon Envelopes Approach

- No new cryptographic primitives (reuses existing Falcon-1024); only NIST-selected algorithms used.
- No changes to block structure or ledger format
- No heavy certificate machinery or aggregation
- Reuses existing participation key infrastructure
- Scales with current relay bandwidth (~4-6 Mbps, ≈6-9× today's baseline but still <1% of 1 Gbps links)
- Provides full PQ message authentication
- Minimal code changes to consensus implementation
- Temporary cache only (~0.4-0.8 GB RAM)
- Fast catchup preserved via State Proofs
- **CPU performance improvement:** Falcon-1024 verification is ~5-10× faster than Ed25519 (0.01 ms vs 0.05-0.1 ms), reducing verification overhead to <0.01% of block time

# 11. Conclusion

Falcon Envelopes enable post-quantum security to Algorand's consensus by securing the
property BA★ truly needs: authenticated committee messages. VRF verification remains functional
(committee selection cannot be forged), but granted, VRF secrecy is lost (selection becomes
predictable). This is deemed acceptable even under attack as the ability to exploit this is extremely limited.
Consensus logic, block structure, and ledger format remain unchanged. Falcon-1024 wrappers
introduce a manageable bandwidth overhead (steady-state ~4.3-6.4 Mbps for relays, still <0.7% of a 1 Gbps link)
and a moderate RAM cache (~0.4-0.8 GB) but avoid megabyte-scale certificate growth and on-chain bloat. Importantly,
Falcon-1024 verification is significantly faster than Ed25519 (~5-10× speedup), making this upgrade a CPU
performance improvement rather than a compromise.

Falcon Envelopes represent the simplest, safest, and most architecturally compatible PQ upgrade
path for Algorand pre PQ-VRF. By reusing existing Falcon-1024 keys from the state proof system and
maintaining all BA★ protocol invariants, this approach minimizes implementation risk while
providing complete post-quantum authentication security.

# 12. Limitations and Scope

Falcon Envelopes provide post-quantum authentication for consensus messages but do not constitute a
complete post-quantum upgrade. The principal remaining limitations are discussed below.

## 12.1 Loss of Committee Secrecy and Targeted-DoS Risk

### Relationship to Existing Liveness Risks

It is important to recognize that the Algorand protocol already carries liveness risks today stemming from its concentrated stake distribution. Approximately two-thirds of online voting weight is held by several dozen large institutional operators spread across exchanges, custodians, and enterprise validators. A well-resourced adversary could attempt to suppress these operators through targeted network attacks, thereby slowing or temporarily stalling consensus. This is not a hypothetical new risk introduced by quantum computing, but a structural liveness vulnerability intrinsic to the present-day network—independent of Falcon Envelopes or post-quantum considerations.

A cryptographically relevant quantum computer primarily alters the efficiency of such attacks rather than their nature. A CRQC breaks ECDSA/Ed25519 VRF secrecy, allowing an adversary to compute every committee membership and every block-proposer identity in advance once the sortition seed is revealed. While Falcon Envelopes remove the catastrophic new integrity failure mode introduced by quantum signature forgeries, they do not remove the pre-existing possibility of targeted censorship. Instead, quantum capabilities would allow an adversary to time these attacks more precisely due to loss of committee secrecy, increasing tactical efficiency but not introducing a fundamentally new attack class. Thus, the residual risk under Falcon Envelopes remains a liveness (DoS) concern that is already present today, rather than a new or unanticipated integrity risk.

### Quantum-Enhanced Predictability

The resulting new capability is **round-level predictability** of who must be suppressed to delay or
censor the chain. This is a genuine degradation: classical adversaries have only statistical knowledge of
target selection frequency, whereas a quantum adversary obtains exact timing.

However, obtaining this timing advantage requires substantial upfront quantum computational effort. To reveal committee participation schedules, an adversary would need to break the VRF keys of a large number of high-stake validators—likely the top twenty or more. This alone represents a massive quantum effort, and achieving it yields only marginal benefit. Even after recovering these keys, the attacker must still successfully execute a broad, sustained denial-of-service operation against those same operators in order to impact liveness at all. In practical terms, the quantum expenditure required to expose committee schedules does not eliminate or meaningfully reduce the operational burden of suppressing many large validators simultaneously; it merely refines the timing.

Beyond this quantum computational barrier, the degradation does **not** materially increase the practical feasibility of a successful attack, for reasons that apply equally today:

1. **Target-to-IP mapping remains extremely difficult**  
   Algorand’s relay-based gossip architecture, encrypted client connections, absence of a public validator directory,
   and frequent IP/relay rotation continue to make reliable, large-scale mapping of participation keys to network
   addresses a sophisticated, expensive, and detectable operation.

2. **Suppression of decisive stake remains operationally prohibitive**  
   60–70 % of online stake is controlled by 30–40 professional entities (exchanges, custodians, institutional stakers)
   running enterprise-grade infrastructure with DDoS mitigation, multi-region redundancy, and 24/7 operations teams.
   Suppressing even one-third of total stake requires simultaneous, sustained attacks against dozens of well-defended
   targets across multiple cloud providers and geographies.

3. **Economic and detection costs are unchanged**  
   Precise timing allows an adversary to concentrate resources more efficiently, but the marginal gain is small when the
   baseline cost of suppressing professionally protected infrastructure is already extraordinarily high and immediately
   visible.

In short, the threat model shifts from

“extremely difficult + somewhat random”

to

“extremely difficult + precisely timed.”

The difference is tactical, not strategic. A single unsuppressed honest proposer or supermajority in any voting step is
still sufficient to advance or finalize the chain, and the architectural barriers that make targeted censorship
impractical today remain the primary protection tomorrow.

Future deployment of a post-quantum VRF will restore committee secrecy and eliminate even this bounded degradation.
Falcon Envelopes are explicitly designed as a safe, minimal bridge until that occurs.

## 12.2 Account-Layer Security

Falcon Envelopes protect only consensus-message authentication. Account-level spending keys (still EC-based) remain
vulnerable to key recovery by a CRQC. Users holding significant value must migrate to post-quantum account signatures (
Dilithium or future equivalents) independently of this consensus upgrade.

## 12.3 Dependence on State Proofs for Long-Range Catchup

Short-range catchup (last ~256–400 rounds) now requires peers to serve temporary Falcon Envelopes from RAM. Long-range
catchup continues to rely exclusively on Falcon-signed State Proofs, which are already quantum-resistant. Any prolonged
failure to produce State Proofs would delay catchup exactly as it does today; the envelope cache adds no new dependency
for historical verification.

# Summary

Falcon Envelopes eliminate the catastrophic risk (unrestricted message forgery and impersonation) while accepting a
bounded, well-understood liveness degradation that is not materially worse than the threat model Algorand has always
faced from nation-state-level censorship. This is a deliberate and conservative trade-off that restores BA★ safety and
liveness guarantees under quantum attack today, at minimal architectural cost, without preempting a future full PQ-VRF
deployment.

---

# Appendix A — Bandwidth Calculations

## A.1 Envelope Size

Falcon-1024 signature: ~1,280 bytes  
Metadata (round, step, role): 200-400 bytes  
**Total:** 1.3-1.8 KB per envelope

## A.2 Envelopes per Round

**Theoretical maximum (derived from `consensus_traffic.md` with the Nov-23-2025 stake distribution):**

Using the Poisson selection model `P(vote≥1 | s, N) = 1 - exp(-s × N)` applied to the actual stake distribution:

- **Proposals:** ~20 messages
- **Soft votes:** ~354 messages (committee size 2,990)
- **Cert votes:** ~233 messages (committee size 1,500)
- **Next votes (pipelined):** ~477 messages (committee size 5,000)
- **Total theoretical generation: ~1,084 messages per round**

**For Falcon envelope calculations, we use ~1,084** as the conservative planning estimate.

**Empirical Support:**
Mainnet telemetry from a well-connected node shows observed message totals of ~1,077 per round,
closely matching the theoretical prediction and supporting the model's accuracy.

**Why Use Theoretical Rather Than Empirical:**

- **Conservative:** Provisions for unoptimized worst-case scenarios
- **Reproducible:** Verifiable from protocol parameters (`config/consensus.go`) and stake distribution
- **Topology-independent:** Not dependent on specific node position or network observations
- **Protocol-grounded:** Derived directly from sortition algorithm and committee sizes
- **Future-proof:** Remains valid even if optimizations or topology change

## A.3 Rounds per Day

Block time: 2.85 seconds  
Rounds/day: 86,400 seconds ÷ 2.85 seconds = **30,316 rounds/day**

## A.4 Relay Bandwidth

Using the theoretical maximum of **1,084 envelopes per round**:

**Lower bound (compact envelopes):**

```
1,084 envelopes/round × 1.3 KB/envelope × 30,316 rounds/day
= 42,716,448 KB/day
≈ 42.7 GB/day
```

**Upper bound (larger envelopes):**

```
1,084 envelopes/round × 1.8 KB/envelope × 30,316 rounds/day
= 59,144,544 KB/day
≈ 59.1 GB/day
```

**Midpoint estimate:**

```
1,084 envelopes/round × 1.5 KB/envelope × 30,316 rounds/day
= 49,283,880 KB/day
≈ 49.3 GB/day
```

**Current baseline:** 3-8 GB/day (0.3-0.8 Mbps)
**With Falcon Envelopes:** 45-67 GB/day (4.3-6.4 Mbps) (baseline + PQ overhead)
**Total relay bandwidth:** ~45-67 GB/day (~4.3-6.4 Mbps)

## A.5 Falcon Envelope Cache Size

**Typical scenario:**

```
256 rounds × 1,084 envelopes/round × 1.5 KB/envelope
= 416,256 KB
≈ 416 MB
```

**Worst-case scenario:**

```
400 rounds × 1,084 envelopes/round × 1.8 KB/envelope
= 780,480 KB
≈ 780 MB
```

**Recommended allocation:** ≥1 GB RAM reserved for the envelope cache (covers headroom plus instrumentation slop)

## A.6 CPU Verification Load

**Per-message verification:**

- Falcon-1024: ~0.01 ms
- Ed25519 (current): ~0.05-0.1 ms
- **Decrease:** Falcon is ~5-10× faster than Ed25519 per message

**Per-round aggregate (relay):**

```
Sequential: 1,084 messages × 0.01 ms = 10.84 ms
8-core parallel: 10.84 ms ÷ 8 = 1.36 ms effective
Block time: 2,850 ms
CPU utilization (8-core): 1.36 ms ÷ 2,850 ms ≈ 0.048%
```

**Conclusion:** CPU overhead remains negligible relative to block time budgets, especially given Falcon's faster per-message verification.

---

# Appendix B — Security Properties Summary

| Property                       | Current (Ed25519)       | Under CRQC Attack      | With Falcon Envelopes      |
|--------------------------------|-------------------------|------------------------|----------------------------|
| Message Authentication         | Secure                  | Broken                 | **Restored (Falcon-1024)** |
| VRF Sortition Verification     | Secure                  | **Still Functional**   | **Still Functional**       |
| VRF Secrecy (Unpredictability) | Secure                  | Broken                 | Broken (acknowledged)      |
| Committee Secrecy              | Present                 | Lost                   | Lost (acceptable)          |
| Participation Key Identity     | Secure                  | Broken                 | **Restored (Falcon-1024)** |
| BA★ Safety                     | Guaranteed              | Violated               | **Guaranteed**             |
| BA★ Liveness                   | Guaranteed              | Guaranteed             | **Guaranteed**             |
| Block Format                   | Unchanged               | Unchanged              | **Unchanged**              |
| Ledger Structure               | Unchanged               | Unchanged              | **Unchanged**              |
| State Proofs                   | PQ-Secure (Falcon)      | PQ-Secure              | **PQ-Secure (unchanged)**  |
| Catchup Correctness            | Guaranteed              | Guaranteed             | **Guaranteed**             |
| Storage Overhead               | 0                       | 0                      | **~0.4-0.8 GB (RAM only)** |
| Bandwidth Overhead             | Baseline                | Baseline               | **+42-59 GB/day (+4.0-5.6 Mbps)**          |
| DoS Resistance                 | High (secret selection) | Degraded (predictable) | Degraded (out of scope)    |

**Summary:** Falcon Envelopes restore all critical authentication and safety properties under
quantum attack while imposing minimal resource overhead and zero changes to ledger structure.
VRF verification remains functional (selection cannot be forged), but VRF secrecy is lost
(selection becomes predictable, enabling targeted DoS). Network-layer defenses or future PQ-VRF
deployment are required to restore DoS resistance.

---

# Appendix C — Message Quantity Justification

For detailed theoretical derivation and empirical support for the consensus message volume, see the companion document:

**"Algorand Consensus Message Quantity Analysis" (`traffic/consensus_traffic.md`)**

**Theoretical Foundation:**
The companion paper derives the theoretical maximum message generation from first principles using:
- Protocol parameters from `go-algorand/config/consensus.go` (committee sizes: 2,990, 1,500, 5,000)
- November 23, 2025 mainnet stake distribution
- Poisson selection model: `P(vote≥1 | s, N) = 1 - exp(-s × N)`

**Key Results:**
- **Proposals:** ~20 messages
- **Soft votes:** ~354 messages (committee size 2,990)
- **Cert votes:** ~233 messages (committee size 1,500)
- **Next votes (pipelined):** ~477 messages (committee size 5,000)
- **Total theoretical generation: ~1,084 messages per round**

**Empirical Support:**
Mainnet telemetry from a well-connected node shows observed message totals of ~1,077 per round,
closely matching the theoretical prediction and supporting the model's accuracy.

**Conservative Planning:**
This document uses the theoretical maximum (~1,084) rather than empirical observations for capacity planning because:
1. **Reproducible:** Verifiable from protocol parameters and stake distribution
2. **Conservative:** Provisions for unoptimized worst-case scenarios
3. **Topology-independent:** Not dependent on specific node position
4. **Protocol-grounded:** Derived directly from sortition algorithm

The companion paper includes full derivations, source code references, protocol optimization analysis (threshold
termination), and detailed empirical data collection methodology.

---

# End of Document
