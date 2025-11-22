# Participation Node Visibility: Why Telemetry Is Accurate

## Overview

This document explains **why a participation node (non-relay) can reliably collect accurate consensus message telemetry** on Algorand, despite not being a relay, and why the message counts observed at such a node closely match those that would be seen by a relay node.

Specifically, we clarify why participation nodes:

* Are exposed to nearly all *distinct, fresh consensus votes* in each step
* Do **not** miss the vast majority of consensus messages despite their position in the topology
* Can therefore be used to empirically validate message-volume models

---

## Key Insight

Algorand’s agreement layer is designed such that **every node continues receiving fresh consensus votes until *it* reaches the phase threshold locally**, regardless of what peers have experienced.

This means a participation node will see nearly the same distinct messages as a relay node, even if it has fewer peers.

---

## Local vs Global Thresholds

### Not global: thresholds are not synchronized

There is *no global threshold cutoff event* on the network.

Each node independently:

* accumulates authenticated votes
* tracks committee weight
* checks threshold
* terminates *locally*

A threshold event at relay X **does not stop** relay X from forwarding fresh votes to node Y **so long as Y has not seen enough weight yet**.

---

## Why Participation Nodes Still See Nearly All Unique Votes

### **1. Pre-threshold relay forwarding behavior**

Relay nodes forward fresh, authenticated votes until the *receiver* crosses threshold.

This means:

* You receive every unique vote until **you** locally reach threshold
* Even if upstream relays reached threshold earlier

### **2. Distinct-vote fairness**

Consensus messages relayed are:

* authenticated
* deduplicated semantically
* forwarded once

Relays do not forward *fewer* distinct votes to you.
They forward fewer *duplicates*.

### **3. Redundant network connectivity**

Even participation nodes have:

* multiple upstream sources
* redundant gossip paths

It is extremely rare for a unique vote to exist network-wide and not reach you.

### **4. Logger placement matters**

You instrumented before:

* bundle trimming
* relay stop events
* downstream suppression

Therefore, you count the complete set of fresh arrivals.

---

## What Participation Nodes Miss

Almost nothing *unique*.

What they do miss:

* redundant duplicate deliveries
* some late, stale, post-threshold votes that don't matter

Neither impacts distinct-message counts.

---

## Why This Produces Accurate Empirical Data

Because the telemetry point aligns with the **semantic filtering boundary**, not the network boundary.

You are counting:

* each unique, verified, pre-threshold vote

That is the correct unit for empirical study.

---

## Conclusion

Participation nodes are excellent platforms for collecting consensus message telemetry.

Even though relays have greater connectivity, agreement-layer design ensures that **nearly all distinct consensus messages propagate to all nodes before local threshold termination occurs**, enabling accurate empirical measurement of real consensus message volume without needing to run a relay node.

---

