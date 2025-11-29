# Liveness Attacks After VRF Compromise (Notes)

## 1. Suppressing Proposers vs. Voters
- A round only stalls if **every selected proposer** fails to publish. With 12–25 proposers per round, silencing them all is rarely practical.
- Liveness is usually halted by **blocking quorum votes**: prevent ≥⅓ stake from soft/cert voting so thresholds are never met.
- In the current stake snapshot (`algorand-consensus_2025-11-23.csv`), the top 11 accounts already control >33% of stake and the top 12 control ~34%. Suppressing that cohort per round is enough to kill cert votes.

## 2. Seed Grinding vs. Targeted Suppression
- Falcon Envelopes block signature forgery but VRF secrecy loss lets attackers predict committees.
- **Seed grinding**: a malicious proposer tries many publication strategies and only releases blocks whose resulting seeds favor compromised stake in future rounds.
  - Predicting even ~10 rounds requires extracting the VRF keys of *every proposer* in that window (dozens per round) to know who would win priority.
  - This is quantum-expensive: hundreds of keys, full priority comparisons, deep branch simulation.
- **Targeted suppression**: once committee schedules are known, an attacker can focus operational pressure (DoS, legal, routing) on the same ~10–20 high-stake participants whenever they appear.
  - Requires no additional key extraction beyond identifying which public keys/stake owners dominate quorum.
  - May be cheaper than grinding, since it leverages existing DoS or coercion tools rather than large quantum computations.
- Conclusion: grinding yields scheduling advantage but is often dominated by the simpler strategy of suppressing known quorum-critical stake per round.

## 3. Other Predictability Levers
- **Selective withholding**: a compromised proposer can drop blocks until a favorable future committee appears; doesn’t require anyone else’s IP.
- **Multi-round censorship planning**: with committee schedules known, attackers pre-arrange collusion or timings to ensure enough stake abstains in specific rounds.
- **Branch simulation / timed publication**: simulate many future rounds and publish only when a favorable sequence arrives, forcing repeated recovery phases.
- **Short-range catchup denial**: when Falcon envelope caches are required for recent rounds, refusing to serve them (or flooding with invalid envelopes) delays new entrants up to the next state proof (~12 minutes).

## 4. Practical Limits
- Committee delays still need either colluding stake or the ability to suppress honest participants (e.g., DoS). Predictive knowledge alone isn’t enough to stop votes.
- Sustained halts require keeping >⅓ total stake offline continuously. BA★ keeps retrying; once honest supermajority communication is restored, the network recovers automatically.
- Therefore, VRF compromise + Falcon envelopes puts all attacks in the “bounded liveness degradation” category: they can stall progress while suppression lasts but cannot rewrite history or bypass quorum signatures.

## 5. Falcon Envelopes and Quantum Resistance
- Falcon signatures restore authentication, so even with VRF predictability a quantum attacker cannot forge blocks or votes; the ledger remains safe (quantum-resistant safety).
- Liveness attacks remain possible but transient: the worst realistic outcome is a stall for a handful of rounds (1–2 blocks or as long as >⅓ stake stays suppressed). Once suppression or partitioning ends, Algorand’s protocol finalizes the pending round automatically and continues.
