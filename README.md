# AI Stock Hunter V6.3.9.65

## V6.3.9.65 — Liquidity Rank Integrity + R:R Semantics + Pre-Move Blocker Priority + Neon Credit


### What changed in V6.3.9.65

- **Liquidity now governs active ranking lanes:** a failed `LiquidityHardGateOK` can never remain `Q — QUALIFIED NOW`, `E — EMERGING NOW`, `CurrentOpportunityQualified`, or `TradePriorityCurrentEligible`. Raw `DecisionRankScore`/`DecisionScoreRank` remain available for research; execution `GlobalRank` / `TradePriorityRank` pushes liquidity-blocked names into `BLOCKED / LOW LIQUIDITY`.
- **R:R semantics are explicit:** `LIVE R:R` requires a valid plan, fresh live/session data, price-entry context, live market phase, and a passing liquidity gate. A valid geometry on a liquidity-blocked name is shown only as `RESEARCH R:R — LIQUIDITY BLOCK`.
- **Pre-Move blocker priority is deterministic:** `LIQUIDITY BLOCK` → `DATA BLOCK` → `RETEST / LATE` → `EXTENDED / DO NOT CHASE` → generic WATCH. This prevents a low-liquidity stock from being mislabeled primarily as an extension/chase issue.
- **Main-page credit is now neon green:** `Developed by Alon Azoulay` is bold, pill-framed, and glow-highlighted.
- V6.3.9.64 liquidity scoring, market-specific turnover floors, Analyze Israel-time completion banner, retest integrity, core-deep reservation, and all prior feedback/audit behavior remain intact.
- **No Optimizer weight changes** in this release.

- Adds a market-aware **Liquidity Score (0–100)** using robust 20/60-day traded value. US uses USD, Hong Kong uses HKD, and Tel Aviv turnover is converted from Yahoo agorot to ILS.
- Adds **LiquidityHardGateOK**: low baseline liquidity can remain visible for research/radar but cannot qualify as live ENTRY NOW or a trade-qualified ARMED setup.
- Liquidity audit fields are visible in Scanner/Analyze cards and Excel exports. RVOL remains a separate abnormal-activity signal and never substitutes for baseline liquidity.
- Pre-Move WATCH now inherits Chase / Extension / Retest / stale-data / liquidity veto reasons. Extended WATCH cases display **EXTENDED / DO NOT CHASE** instead of a misleading generic WATCH.
- Analyze completed status now shows the exact **Israel time** in bright green.
- Main header includes **Developed by Alon Azoulay**.
- Retains all V6.3.9.63 Actionability, Previous-Session, R:R display, Retest-plan integrity, and reserved Deep Analysis fixes.
- Production/OOS optimizer weights are unchanged.

## Purpose
V6.3.9.65 builds on V6.3.9.64 without changing Optimizer weights, the main 80% Trade Timing hard gate, Continuation thresholds, Ranking weights or the normal confirmed-entry thresholds. It fixes actionability/display contradictions found in the V6.3.9.62 production scan and adds a structurally valid retest plan.

## V6.3.9.63 retained changes

### 1. Pre-Move pattern is no longer the same thing as "actionable now"
Scanner now exports and displays separate fields:

- `PreMovePatternDetected` — a HIGH/WATCH pattern exists and remains useful for research/memory;
- `PreMoveRadarActionable` — the pattern is still early enough to act on now;
- `PreMovePatternOnly` — pattern exists, but current timing is no longer actionable.

A confirmed Pre-Move with **60% or more of the observed move consumed before the causal trigger**, or an `AGING / RETEST` timing qualification, is kept on the radar but becomes **RETEST ONLY**, never `ACTIONABLE EARLY`. This is intentionally stricter than the existing 80% full Trade Timing hard gate; the 80% production entry threshold itself is unchanged.

### 2. Live Early Radar requires live-quality data
`LiveEarlyRadarCandidate` is hard-blocked when the market is not in an eligible live phase, session data is stale/unverified, timing data is incomplete/hard-blocked, or an OPEN-session price is not fresh. Structural Pre-Move patterns may still remain visible separately.

### 3. Previous-session entries cannot look live
A raw prior-session `CONFIRMED ENTRY` is now rendered as `PREVIOUS SESSION CONFIRMED ENTRY` / `LAST SESSION ENTRY` when the current session requires revalidation. The historical signal remains auditable, but the UI no longer presents it as a fresh entry.

### 4. Live R:R is context-gated
Raw `LiveRR_T1` / `LiveRR_T2` are retained for audit, while headline/filter fields `LiveRRDisplayT1`, `LiveRRDisplayT2` and `LiveRRDisplayStatus` are populated only when price/session/live-data context is actionable. Otherwise the UI shows `N/A — PRICE OUTSIDE ENTRY CONTEXT` or the relevant live-data block instead of extreme/misleading R:R values.

### 5. SMART Deep Analysis keeps priority anchors
The reserved Deep set now explicitly protects `COIN`, `SMCI`, `NICE`, `1196.HK`, `1570.HK` and `1780.HK` (in addition to the existing liquid US core when that market is selected), so these priority case-study names cannot be lost only because of the SMART depth quota.

### 6. Retest-specific trade geometry
A Retest no longer reuses an incompatible original plan. New fields are calculated independently:

- `RetestEntryLow` / `RetestEntryHigh`
- `RetestInvalidation`
- `RetestTarget1` / `RetestTarget2`
- `RetestRR_T1` / `RetestRR_T2`
- `RetestPlanValid` / `RetestPlanReason`

The retest entry band is forced above its stop with a volatility/price buffer. Targets and R:R are recalibrated from the new retest geometry; existing structural targets act only as conservative ceilings. If the zone would overlap/breach invalidation or cannot preserve acceptable T1 geometry, the engine returns **NO VALID RETEST GEOMETRY / PLAN NOT QUALIFIED** instead of showing a trade plan.

### 7. Analyze uses the same semantics
Analyze receives the same previous-session display, Pre-Move actionability separation, live-R:R gating and retest-specific plan. Feedback/Decision Outcome Validation introduced in V6.3.9.62 remains intact.

---

## V6.3.9.62 retained — Analyze Feedback + Decision Outcome Validation
V6.3.9.62 closed the Feedback gap between Scanner and Analyze and made the model evaluate the **recommendation that was actually shown** against what happened later.

## 1. Analyze now saves Feedback automatically
Every completed Analyze run now writes one snapshot into the same portable Feedback SQLite DB used by Scanner.

- `snapshot_source = ANALYZE`
- deterministic EventID uses the same causal setup/session rules as Scanner;
- repeated Analyze runs for the same event overwrite one Analyze event row;
- if Scanner already captured the same event, Analyze is stored as `TRACKING`;
- if Analyze was first, it can be the `ORIGIN` and the later Scanner observation becomes tracking;
- ORIGIN-only learning therefore prevents Scanner + Analyze from double-counting the same market event.

Analyze displays a small audit line after completion showing whether its Feedback snapshot was saved, EventID and ORIGIN/TRACKING role. The Analyze Excel also contains Feedback snapshot metadata.

## 2. Recommendation-aware Feedback
Snapshots now persist the decision that existed at the time of analysis:

- `DecisionDisplayStage`
- `EffectiveDecisionStage`
- `RecommendationType`
- `RecommendationText`
- `EntryPath`
- `ContinuationEntryState`
- `RetestStatus`
- `PreMoveRadarStatus`

This lets Feedback separate the model's recommendation from later price outcomes instead of judging every event only as a generic trade.

## 3. Decision Outcome Validation
Feedback adds a new **Decision Outcome Validation** table by recommendation, entry path and 1D/2D/3D/5D horizon. It reports:

- independent Event N;
- Target1-before-Invalidation rate;
- realized +3% MFE hit rate;
- realized +5% MFE hit rate;
- realized +10% MFE hit rate;
- average MFE;
- average MAE;
- average end return.

Interpretation remains stage-aware:

- `ENTRY NOW` / `CONTINUATION READY`: trade audit focuses on Target1-first plus MFE/MAE;
- `ARMED`: checks whether a meaningful move followed readiness;
- `BUILDING SETUP`: checks whether early setup observations led to +3%/+5% movement;
- `TOO LATE`: explicitly measures false negatives — how often price still added +3%/+5%/+10% after the warning;
- `RETEST`: current table shows MFE/MAE as an audit proxy; exact pullback-before-continuation sequencing remains research/audit only until sufficient intraday outcome history is available.

The table is shown in Feedback and exported to the Feedback workbook as `Decision Outcome Validation`.

## 4. Scanner + Analyze source audit
Feedback now displays and exports `Feedback Source Audit`, showing Scanner vs Analyze and ORIGIN vs TRACKING counts. This makes duplicate-control visible instead of implicit.

## 5. Original Trigger progress display
When the Original Trigger → T1 path reaches or exceeds 100%, the shared Scanner/Analyze ticket no longer shows a confusing value such as `100.4%` as the headline. It displays:

`TARGET REACHED • 100%+`

The exact percentage is still retained in audit/details/Excel.

## 6. Existing V6.3.9.61 behavior retained
V6.3.9.62 retains:

- persistent Last Completed Scan + exact Israel completion time;
- BUILDING SETUP canonical naming;
- qualified ARMED vs ARMED BLOCKED;
- 1780.HK verified Original Signal migration;
- Top Action + Top Pre-Move separation;
- selective Pre-Move HIGH/WATCH model;
- common-stock discovery guard;
- strict live ENTRY NOW gate and LAST SESSION semantics;
- market-balanced SMART Deep quotas and Core reserve;
- Continuation READY / WATCH / BLOCKED;
- Original Trigger vs Current Trigger separation;
- Scanner/Analyze shared ticket, Momentum 15m/1H and WHY YES / WHY NOT.

## Validation after upload

For V6.3.9.65 specifically, confirm that Scanner/Analyze show `LiquidityScore`, `LiquidityLabel`, `MedianDailyTurnover60`, and `LiquidityHardGateOK`; a LOW-liquidity row must not appear as live `ENTRY NOW` or qualified `ARMED`. Analyze completion should show Israel time in the glowing green completion banner, and the main hero should show `Developed by Alon Azoulay`.

No Optimizer rerun is required.

Recommended validation:
1. Run one Analyze on a ticker that is also present in the latest Scanner result.
2. Open Feedback and confirm the Analyze snapshot is visible with `snapshot_source = ANALYZE`.
3. Confirm the same EventID is not counted twice as independent ORIGIN observations.
4. After outcomes mature, inspect `Decision Outcome Validation` for +3/+5/+10, Target1-first, MFE and MAE by recommendation.
5. On 1780.HK, confirm Original progress displays `TARGET REACHED • 100%+` while Current Trigger progress remains independent.

## Files
The deployment ZIP contains exactly:
- `app.py`
- `quant_engine.py`
- `README.md`
- `requirements.txt`
