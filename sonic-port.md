# Porting zebra-rs to SONiC — Recommended Approach

**Best path: keep SONiC’s southbound stack, teach zebra-rs to speak FPM like FRR zebra — don’t rewrite orchagent/SAI first.**

## SONiC routing path today

```
protocol → zebra RIB → (kernel netlink + FPM) → fpmsyncd → APPL_DB → orchagent → ASIC_DB → syncd → SAI
```

zebra-rs already has the right hook: `FibHandle` installs into the kernel and optionally **tees** to cradle (`CradleFib`). SONiC should be another tee — FPM — not a new data-plane story.

## Recommended approach

### 1. FPM client tee in zebra-rs (do this first)

Add something like `SonicFpm` / `FpmClient` beside `CradleFib`:

- TCP client to `fpmsyncd` (default `127.0.0.1:2620`)
- FRR FPM framing + netlink-encoded `RTM_NEWROUTE` / `RTM_DELROUTE`
- Still install into the Linux kernel (SONiC expects both)
- Match current SONiC expectations: nexthop groups, `NLM_F_REPLACE`, later offload feedback

That reuses **all** of sonic-swss with almost no SONiC code changes.

Natural first code slice: `src/fib/fpm/` (encode + TCP client) wired from `FibHandle` the same way cradle is.

### 2. Drop-in BGP container

Replace FRR inside `docker-fpm-frr` (or a sibling image) with zebra-rs + existing `fpmsyncd`. Prove IPv4/IPv6 BGP + static on SONiC VS before touching ASIC quirks.

### 3. Config bridge second

SONiC drives FRR via CONFIG_DB / `sonic-cfggen` / frr-mgmt. Build a translator (`CONFIG_DB` → zebra-rs candidate config) after FIB sync works. Don’t start by rewriting SONiC’s config framework.

### 4. Defer direct APPL_DB writes

Writing Redis yourself only pays off for features FPM encodes poorly (some SRv6/EVPN). It’s tighter coupling and duplicates `fpmsyncd` — wrong for v1.

## What not to do early

- Replace orchagent / invent a parallel SAI path
- Aim for full FRR feature parity before a working FPM loop
- Bypass kernel and only program hardware (breaks SONiC’s consistency model)

## Suggested milestones

| Phase | Outcome |
|---|---|
| A | FPM tee + dump/replay; routes appear in APPL_DB |
| B | BGP container image on VS; basic eBGP leaf/spine |
| C | NHG + route-replace + warm/fast reboot basics |
| D | CONFIG_DB bridge + sonic-buildimage packaging |
| E | EVPN/SRv6 only where SONiC already has orch support |

## Why this order

That sequence mirrors how cradle was integrated: **RIB stays in zebra-rs; southbound is a pluggable tee; the existing dataplane agent stays.**
