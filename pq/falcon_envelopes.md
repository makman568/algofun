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
redesign. 

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
Normal operation: 80-120 envelopes/round → 7-15 GB/day
Recovery mode: 300-500 envelopes/round → 20-35 GB/day (temporary)
```

**Relay Infrastructure Resilience:**
Even if the bandwidth load temporarily surges to ~30 GB/day during a recovery window, this
remains comfortably within the burst capacity of standard relay infrastructure:
- Modern relay nodes: 1 Gbps uplinks (86 TB/day theoretical)
- Actual burst requirement: ~30 GB/day
- Utilization during spike: < 0.04% of link capacity

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

### 9.2.1 Empirical vs. Theoretical Bandwidth Modeling

It is critical to distinguish between the **Theoretical Committee Size** (total eligible voters,
~3,000-4,500 participants) and the **Effective Gossip Volume** (actual messages propagated by
relays in practice).

While the BA★ protocol specifies large committees to ensure honest majority safety, the gossip
network operates on a "sufficient quorum" basis:

**Theoretical Maximum:**
If every committee member voted and every vote was propagated to every node, the load would
exceed 100 GB/day per relay.

**Empirical Reality:**
Mainnet relays typically observe **80-120 distinct envelopes per round** before a certificate is
formed and the round concludes. Once a certificate threshold is reached, honest nodes stop
propagating redundant votes for that step.

**Why Empirical ≪ Theoretical:**
1. **Threshold-based termination:** Nodes stop collecting votes after 2f+1 threshold reached
2. **Gossip deduplication:** Redundant messages are filtered before propagation
3. **Network topology:** Efficient relay architecture prevents unnecessary rebroadcast
4. **Fast finalization:** Rounds conclude quickly, limiting vote accumulation window

**Our Bandwidth Model:**
Our calculations (See Appendix A) utilize the **Empirical High-Water Mark (120 envelopes)**.
This reflects the optimized reality of Algorand's propagation layer, where redundant gossip is
pruned, keeping the steady-state load between **7-15 GB/day** rather than the theoretical maximum.

**Conservative Assumptions:**
We use the upper bound (120 envelopes) to provide safety margin. Actual observed traffic may be
lower (~80-100 envelopes) in well-connected network conditions.

## 9.3 Rounds per Day
Block time = 2.85 seconds → **30,316 rounds/day**.

## 9.4 Relay Bandwidth Impact
Lower bound:
```
80 × 1.3 KB × 30,316 ≈ 3.16 GB/day
```
Upper bound:
```
120 × 1.8 KB × 30,316 ≈ 6.55 GB/day
```

**Current baseline:** 3-8 GB/day  
**With Falcon Envelopes:** 7-15 GB/day  
**Increase factor:** ~1.7-2×

## 9.5 Validator Bandwidth
Non-relay participation nodes: **1-2 GB/day** (minimal increase).

## 9.6 Storage (Falcon Envelope Cache)
- **Retention window:** 256-400 rounds
- **Envelopes per round:** 80-120
- **Size per envelope:** 1.3-1.8 KB
- **Total storage:** 30-80 MB RAM
- **Type:** In-memory cache only (not persisted to disk)
- **Pruning:** Automatic when State Proof covers range

## 9.7 CPU Verification Cost

**Single Verification:**
- Ed25519: ~0.05-0.1 ms
- Falcon-1024: ~1-3 ms
- **Increase factor:** ~10-30×

**Per-Round Verification (Relay Node):**
- Messages received: 80-120
- Sequential verification time: 80-360 ms
- Block time budget: 2,850 ms
- **CPU overhead (sequential):** 3-13% of block time

**With Parallelization:**
- Falcon verification is embarrassingly parallel (no dependencies)
- 8-core relay: effective overhead < 2% (80-360ms ÷ 8 cores ≈ 10-45ms)
- 4-core relay: effective overhead < 4% (80-360ms ÷ 4 cores ≈ 20-90ms)
- **No liveness impact**

**Byzantine Flood Resilience:**
Message flooding is not a new attack—it exists in current Algorand.
Falcon Envelopes increase per-message verification cost (~3×) but do not
create new vulnerabilities.

Existing defenses remain effective:
- **VRF verification first:** Fast path (1ms) rejects invalid eligibility before Falcon check
- **Rate limiting per peer:** Prevents sustained floods
- **Early abort:** Stop verification on first invalid signature
- **Message deduplication:** Hash-based filtering prevents reprocessing
- **Peer reputation tracking:** Deprioritize or ban sources of invalid messages

**Assessment:** Falcon overhead does not enable new DoS attacks. The existing
Byzantine resistance mechanisms handle the modest increase in verification cost.

# 10. Benefits of the Falcon Envelopes Approach

- No new cryptographic primitives (reuses existing Falcon-1024); only NIST-selected algorithms used.
- No changes to block structure or ledger format
- No heavy certificate machinery or aggregation
- Reuses existing participation key infrastructure
- Scales with current relay bandwidth (1.7-2× increase)
- Provides full PQ message authentication
- Minimal code changes to consensus implementation
- Temporary cache only (30-80 MB RAM)
- Fast catchup preserved via State Proofs

# 11. Conclusion

Falcon Envelopes enable post-quantum security to Algorand's consensus by securing the 
property BA★ truly needs: authenticated committee messages. VRF verification remains functional
(committee selection cannot be forged), but granted, VRF secrecy is lost (selection becomes 
predictable). This is deemed acceptable even under attack as the ability to exploit this is extremely limited.
Consensus logic, block structure, and ledger format remain unchanged. Falcon-1024 wrappers
introduce modest bandwidth overhead (1.7-2× increase) and minimal storage overhead (30-80 MB RAM
cache) but avoid megabyte-scale certificate growth and on-chain bloat.

Falcon Envelopes represent the simplest, safest, and most architecturally compatible PQ upgrade
path for Algorand pre PQ-VRF. By reusing existing Falcon-1024 keys from the state proof system and
maintaining all BA★ protocol invariants, this approach minimizes implementation risk while
providing complete post-quantum authentication security.

# 12. Limitations and Scope

## 12.1 Loss of VRF Secrecy leading to Denial-of-Service Risk
We examine this section in detail because this is the primary cryptographic weakness in the Falcon Signatures
scheme. 

The TLDR: Even though VRF secrecy is vulnerable with a CRQC, the main risk - denial-of-service attack - is 
not practically exploitable and in fact remains about the same as exists today in the classic network.

### The Fundamental Threat (Classical and Quantum)

In any proof-of-stake system, suppressing consensus requires suppressing a sufficient fraction of total stake. For Algorand:
- **Liveness threshold**: >1/3 of stake must be silenced to prevent block production
- **Safety threshold**: >2/3 of stake must be suppressed to enable safety violations

Algorand's stake distribution is such that 30-40 large operators (exchanges, custodians, institutional validators) control 60-70% of total stake. These entities are:
These entities are largely hosted in professional cloud providers and data centers. Because both block production and
committee participation are influenced by stake weight, any attempt to do a DoS attack will focus primarily on this
group.

**Why DoS on Algorand is Difficult: Decoupling Identity and Location (Anonymity)**

The crucial factor that renders the theoretical DDoS threat impractical is the decoupling of the on-chain 
stake identity (the account and its participation key) from its off-chain network address (the validator's 
IP address).

- Participation Key Anonymity: Algorand uses separate, specialized participation keys for consensus voting, which are distinct from the account's spending keys. The nodes connect anonymously to the relay network.
- No Public Directory: The Algorand network architecture is designed so that there is no public gossip list, validator IP directory, or permanent identity-to-IP mapping.
- Encrypted Connections: Participation nodes communicate over encrypted connections via the relay mesh. Relay nodes, which handle the gossip traffic, do not possess knowledge of the participation keys represented by their clients.
- Mapping Accounts to IPs Requires Sophisticated Multi-Step Attacks: To correlate participation keys with IP addresses, an attacker would need to execute difficult, resource-intensive operations:

In Relay Architecture, an Attacker would need to:

- Compromise or monitor multiple relay nodes across the network
- Capture and log all incoming connections with their source IPs
- Perform long-term traffic analysis to correlate voting message timing patterns with connection sources
- Cross-reference voting signatures with on-chain stake distribution
- Maintain persistent surveillance over extended time periods as node IPs and relay connections change

In P2P Architecture, an Attacker would need to:

- Deploy a Sybil attack by flooding the network with malicious nodes to maximize mesh visibility
- Build a topology map of peer connections across the network
- Perform first-propagator detection to identify likely sources of proposals and votes
- Execute timing analysis across multiple observation points to triangulate message origins
- Correlate cryptographic voting patterns with network-level propagation patterns
- Sustain this sophisticated traffic analysis infrastructure continuously


Targeting is effectively impossible. Since the attacker cannot discover the physical IP address or hosting location of high-stake validator accounts without executing these complex, expensive, and detectable attack chains, they are fundamentally unable to "aim for the largest accounts" with a targeted DDoS attack.

But let's say they somehow are able to determine the mapping of account to IP address
(through social engineering, etc). DoS attacks of the largest staked accounts would still be difficult 
to execute due to the following factors.
- **Infrastructure robustness**: Major operators run enterprise-grade DDoS protection, multi-region redundancy, and professional network defenses
- **Geographic distribution**: No single network location controls decisive stake; suppression requires coordinated global attacks
- **Economic cost**: Sustained DDoS against fortified infrastructure at cloud-provider scale remains expensive
- **Detection and response**: Network-layer attacks at this scale are immediately visible and trigger operational countermeasures
- **Self-healing property**: Any single unsuppressed proposer per round regenerates unpredictability, limiting attack persistence

**All of these impediments to DoS exist TODAY under classical cryptography.** 

### What Quantum VRF Compromise Adds

A quantum adversary capable of extracting VRF private keys gains some **tactical precision** but does not fundamentally change the strategic landscape:

**New capabilities:**
- **Round-specific prediction**: May know to a limited degree that a specific whale account will propose 
in an specific upcoming round
- **Multi-round optimization**: Identify correlated windows where multiple high-value targets are simultaneously vulnerable
- **Seed grinding**: Selectively withhold proposals in advantageous branches
- **Committee timing**: Predict exact rounds where specific operators hold decisive committee weight

**Unchanged barriers:**
All of the barriers present in the classical enviroment (anonymity, etc) still exist in the PQ compromise
scenario.

### The Correct Framing

**Classical setting (today):**
- Adversary knows: "Account A controls 2% of stake and will be selected ~700 times today"
- Invisibility: Must somehow determine IP address from Account
- Attack feasibility: Must sustain suppression against professionally-protected, globally-distributed infrastructure
- Operational cost: Prohibitively expensive for sustained liveness degradation

**Quantum setting (PQ VRF compromise):**
- Adversary knows: "Account A will most likely propose at rounds 1,000,042 and 1,000,089 and will be 
in soft-vote committee at round 1,000,103"
- Invisibility: **Unchanged** - still must somehow determine IP address from Account
- Attack feasibility: **Unchanged** - still must suppress the same professionally-protected infrastructure
- Operational cost: **Unchanged** - temporal precision does not reduce DDoS cost against fortified targets

The delta is **tactical optimization** (when to concentrate effort) rather than **strategic transformation** 
(ability to execute suppression). An adversary who cannot localte the whale's IP address and suppress 
their infrastructure today will not gain that capability merely from knowing precise timing.

### 12.1A — Block Proposers (Proposal Step)

Now, let's consider that to halt block production, an adversary must suppress **every** block proposer that
self-selects due to having a winning VRF lottery ticket. Even ONE honest proposer that is not successfully 
DoS'd produces the block. 

Thus to supopress block production via DoS, an attacker must :
- Simultaneously target 15-20 VRF-selected operators with apriori-known IP address
- Sustain attacks across globally distributed infrastructure
- Overcome enterprise DDoS mitigation at multiple cloud providers
- Maintain suppression continuously (even one proposer per round that escapes DoS restores progress)

**PQ VRF compromise changes timing precision, not target identity or infrastructure resilience.
** The same large operators who are proposers today remain the targets tomorrow. 
Knowing round numbers does not make IP addresses easy to discover, bypass DDoS protection or 
reduce operational costs.

**Conclusion**: Proposer DoS remains a **bounded liveness threat** under both classical and 
quantum settings. PQ VRF compromise provides tactical optimization but does not 
materially increase attack feasibility. The operational barriers (invisibility, infrastructure 
robustness, geographic distribution, economic cost) are unchanged.

### 12.1B — Committee Members (Voting Steps)

BA★ safety depends on honest supermajority in each voting step (soft-vote, certify-vote, final-vote). The critical insight: **committee weight, not committee size, determines safety.**

- Top 30-40 operators contribute 60-70% of total committee weight
- They run the same professionally-protected infrastructure
- They are already continuously exposed due to high selection frequency

To violate safety, an adversary must suppress **>2/3 of total stake weight** across all three voting steps. This requires:
- Suppressing 20-30 major operators simultaneously
- Maintaining suppression across sequential voting steps (~10-15 seconds)
- Overcoming enterprise infrastructure defenses at each target
- Doing this repeatedly across multiple rounds to achieve finality manipulation

**PQ VRF compromise reveals:**
- Which specific operators are in each committee. 
- Their relative weight in that committee
- The exact timing of their participation

BUT overwhelmingly the committee is already naturally dominated by whale accounts, in which case PQ VRF compromise doesn't buy much information.

**PQ VRF compromise does NOT change:**
- The identity of high-value targets (already known from stake distribution)
- The infrastructure protection these operators deploy
- The operational cost of suppressing >2/3 stake simultaneously
- The detection risk from network-wide attacks

**The decisive point**: Knowing that "Account A holds 2% of soft-vote committee weight at round 1,234,567" 
provides no advantage if you don't know their IP and cannot suppress the account's infrastructure in 
the first place. The temporal precision is irrelevant when the operational barrier remains intact.

**Conclusion**: Committee DoS feasibility is **unchanged** under PQ VRF compromise. The threat exists at the same level today: 
theoretically possible but operationally implausible against invisibility and modern infrastructure 
defenses. 

### Scope of Falcon Envelopes

Falcon Envelopes restore **authentication**, not **anonymity**. They eliminate the catastrophic threat (signature forgery enabling impersonation) while accepting the bounded liveness risk (predictability enabling optimized but not fundamentally easier DoS).

This is the correct engineering prioritization because:
1. **The DoS threat exists today** at approximately the same operational difficulty
2. **Signature forgery is novel and catastrophic** - it creates attack vectors that don't exist classically
3. **Infrastructure defenses are effective** - professional operators already mitigate network-layer attacks
4. **Self-healing limits damage** - randomness regeneration bounds attack persistence
5. **Future PQ-VRF deployment** can address residual predictability concerns without requiring immediate architectural changes

VRF secrecy loss does not create new attack feasibility; it provides marginal tactical improvement to an already difficult operational challenge. The real defense is—and always has been—infrastructure robustness, not cryptographic unpredictability.

1
## 12.2 Account-Layer Quantum Resistance

Falcon Envelopes secure **consensus message authentication** but do not address **account 
security**.

## 12.3 State Proof Dependency

Falcon Envelopes rely on State Proofs for long-range catchup. State Proofs are already
Falcon-secured, but any failure in State Proof generation would affect catchup capability for
nodes more than 256 rounds behind.

**Mitigation:** State Proof infrastructure is mature and battle-tested. Monitoring and alerting
for State Proof generation latency is standard operational practice.

---

# Appendix A — Bandwidth Calculations

## A.1 Envelope Size
Falcon-1024 signature: ~1,280 bytes  
Metadata (round, step, role): 200-400 bytes  
**Total:** 1.3-1.8 KB per envelope

## A.2 Envelopes per Round
**Empirical observation (mainnet relays):** 80-120 envelopes/round

**Why not 3,000-4,500?**
Committee size is theoretical maximum. Actual gossip volume is limited by:
- Threshold-based termination (stop at 2f+1)
- Deduplication
- Efficient network topology

## A.3 Rounds per Day
Block time: 2.85 seconds  
Rounds/day: 86,400 seconds ÷ 2.85 seconds = **30,316 rounds/day**

## A.4 Relay Bandwidth

**Lower bound:**
```
80 envelopes/round × 1.3 KB/envelope × 30,316 rounds/day
= 3,152,864 KB/day
≈ 3.16 GB/day
```

**Upper bound:**
```
120 envelopes/round × 1.8 KB/envelope × 30,316 rounds/day
= 6,548,256 KB/day
≈ 6.55 GB/day
```

**Current baseline:** 3-8 GB/day  
**With Falcon Envelopes:** 6.16-14.55 GB/day (baseline + PQ overhead)  
**Total relay bandwidth:** ~7-15 GB/day

## A.5 Falcon Envelope Cache Size

**Typical scenario:**
```
256 rounds × 100 envelopes/round × 1.5 KB/envelope
= 38,400 KB
≈ 38 MB
```

**Worst-case scenario:**
```
400 rounds × 120 envelopes/round × 1.8 KB/envelope
= 86,400 KB
≈ 86 MB
```

**Recommended allocation:** 100 MB RAM for envelope cache (includes headroom)

## A.6 CPU Verification Load

**Per-message verification:**
- Falcon-1024: ~1-3 ms
- Ed25519 (current): ~0.05-0.1 ms
- **Increase:** ~10-30× per message

**Per-round aggregate (relay):**
```
Sequential: 100 messages × 2 ms = 200 ms
8-core parallel: 200 ms ÷ 8 = 25 ms effective
Block time: 2,850 ms
CPU utilization: 25 ms ÷ 2,850 ms ≈ 0.9%
```

**Conclusion:** CPU overhead is negligible with parallelization, well within relay node budgets.

---

# Appendix B — Security Properties Summary

| Property | Current (Ed25519) | Under CRQC Attack | With Falcon Envelopes |
|----------|-------------------|-------------------|----------------------|
| Message Authentication | Secure | Broken | **Restored (Falcon-1024)** |
| VRF Sortition Verification | Secure | **Still Functional** | **Still Functional** |
| VRF Secrecy (Unpredictability) | Secure | Broken | Broken (acknowledged) |
| Committee Secrecy | Present | Lost | Lost (acceptable) |
| Participation Key Identity | Secure | Broken | **Restored (Falcon-1024)** |
| BA★ Safety | Guaranteed | Violated | **Guaranteed** |
| BA★ Liveness | Guaranteed | Guaranteed | **Guaranteed** |
| Block Format | Unchanged | Unchanged | **Unchanged** |
| Ledger Structure | Unchanged | Unchanged | **Unchanged** |
| State Proofs | PQ-Secure (Falcon) | PQ-Secure | **PQ-Secure (unchanged)** |
| Catchup Correctness | Guaranteed | Guaranteed | **Guaranteed** |
| Storage Overhead | 0 | 0 | **30-80 MB (RAM only)** |
| Bandwidth Overhead | Baseline | Baseline | **+3-6 GB/day** |
| DoS Resistance | High (secret selection) | Degraded (predictable) | Degraded (out of scope) |

**Summary:** Falcon Envelopes restore all critical authentication and safety properties under
quantum attack while imposing minimal resource overhead and zero changes to ledger structure.
VRF verification remains functional (selection cannot be forged), but VRF secrecy is lost
(selection becomes predictable, enabling targeted DoS). Network-layer defenses or future PQ-VRF
deployment are required to restore DoS resistance.

---

# End of Document
