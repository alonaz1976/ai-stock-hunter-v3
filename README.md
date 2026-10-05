# AI Stock Hunter V6.3.9.67

## V6.3.9.67 — Pre-Breakout Acceleration + Causal Score Lift + Early Entry Confirmation

### What changed in V6.3.9.67

- **New Pre-Breakout Acceleration layer:** the engine now measures how quickly `Explosive`, `Move` and `Entry` scores are improving across the latest causal daily observations instead of looking only at their absolute levels. It also evaluates current EMA/RSI/CMF/MACD/volume structure and 15m/1H confirmation. No future outcome labels are used.
- **WATCH → ARMED → CONFIRMED progression:** qualified acceleration is classified as `EARLY WATCH`, `ARMED`, or `CONFIRMED`. A confirmed acceleration setup can produce `⚡ ACCELERATION ENTRY NOW` only when the existing timing, liquidity, R:R, no-chase, extension, market-regime and plan-integrity protections also pass.
- **1196-style Daily Setup recovery:** a very strong causal acceleration sequence may substitute only for the classic `Daily Setup` gate. It cannot override Fresh Signal, 15m/1H timing, Volume/Flow, No-Chase, Market Regime, extension/timing blocks, invalid plan geometry or other execution safety gates.
- **Score lift is visible and auditable:** the system preserves the raw score and applies a bounded acceleration bonus only while the setup remains early enough. `Entry`, `Explosive` and `Move` therefore rise when acceleration evidence strengthens; `Opportunity` and `Top Score` can then rise naturally through the existing scoring pipeline. Raw and adjusted values are exported side by side.
- **Bounded bonuses:** `EARLY WATCH` = Entry +6 / Explosive +6 / Move +4; `ARMED` = Entry +12 / Explosive +10 / Move +7; `CONFIRMED` = Entry +16 / Explosive +14 / Move +10. The Entry headline uses a conservative 70% of the Entry bonus, while the full bonus is available to Live Actionability; late/extended setups receive zero acceleration bonus.
- **Impulse persistence:** a strong acceleration burst remains visible for up to roughly two following sessions while structure remains intact, so a candidate does not disappear immediately after the first surge in its score deltas.
- **Deep-analysis priority:** high-acceleration candidates receive bounded Deep Analysis priority so names like VSH/MAT/0148-style early discoveries are less likely to be lost only because of the SMART depth quota. Liquidity remains a separate execution gate, and this priority does not itself create a trade signal.
- **Immediate breakout path:** when the acceleration state is `CONFIRMED`, price is still close to the causal trigger/VWAP/EMA structure, and all normal execution gates pass, the engine may enter without forcing a pullback first.
- **Analyze Momentum display fixed:** Analyze now carries the engine's current `MomentumState`, `MomentumState15m`, `MomentumState1H`, and short-timeframe volume trend into the ticket instead of incorrectly showing `NO DATA` when those fields were available.
- **No Optimizer/OOS Prediction rewrite:** calibrated Prediction and existing OOS optimizer weights are not artificially boosted. The new score lift is isolated, bounded and exported for later validation so we can test whether it improves hit rate before changing trained weights.
- All V6.3.9.66 liquidity isolation and Live R:R integrity fixes are retained.

### New audit fields

`PreBreakoutAccelerationScore`, `PreBreakoutAccelerationStage`, `PreBreakoutAccelerationReason`, `AccelerationRawDailyScore`, `AccelerationPersistedDailyScore`, `AccelerationExplosive1D/3D`, `AccelerationMove1D/3D`, `AccelerationEntry1D/3D`, `AccelerationShortScore`, `AccelerationIntradayConfirmations`, `AccelerationRecent3DMovePct`, `AccelerationDailySetupOverride`, `AccelerationBreakoutPriceOK`, `AccelerationEntryNow`, plus raw/bonus pairs for Entry, Explosive and Move.

V6.3.9.66 remains fully retained below.

## V6.3.9.66 — Analyze Liquidity Isolation + Live R:R Integrity

### What changed in V6.3.9.66

- **Analyze Liquidity NameError fixed:** Analyze now computes its own per-ticker liquidity profile before rendering the Decision Cockpit. It no longer depends on Scanner's `_liq_profile`, eliminating the crash seen after completed Analyze runs.
- **Cross-tab liquidity leakage prevented:** the Analyze fallback is ticker-local, so it cannot accidentally reuse a liquidity profile left behind by a different Scanner ticker.
- **Live R:R integrity tightened in Scanner and Analyze:** `LIVE R:R` now also requires the engine's `RRActionable` flag, a passing extension guard, and a decision stage that is not `TOO LATE`.
- **Misleading late-stage R:R removed:** extended / do-not-chase / too-late cases keep raw R:R values for audit, but the headline display changes to `N/A — R:R NOT ACTIONABLE`, `N/A — EXTENDED / DO NOT CHASE`, or `N/A — TOO LATE / DO NOT CHASE` instead of `LIVE R:R`.
- **Production scan audit:** the supplied V6.3.9.65 scan had 160 deep results. All 56 liquidity-blocked names were correctly excluded from current eligibility, qualification, and Actionable Now. One R:R display contradiction was found (`CYBR.TA`: `TOO LATE`, `RRActionable=False`, but displayed `LIVE R:R`) and is fixed here.
- **No scoring / Optimizer weight changes.** Liquidity thresholds, ranking weights, Pre-Move logic, Entry thresholds, and OOS optimizer weights are unchanged.

V6.3.9.65 remains fully retained below.

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

For V6.3.9.66 specifically, confirm that Scanner/Analyze show `LiquidityScore`, `LiquidityLabel`, `MedianDailyTurnover60`, and `LiquidityHardGateOK`; a LOW-liquidity row must not appear as live `ENTRY NOW` or qualified `ARMED`. Analyze completion should show Israel time in the glowing green completion banner, the main hero should show `Developed by Alon Azoulay`, Analyze must render without a liquidity `NameError`, and `LIVE R:R` must never be shown when `RRActionable=False`, the extension guard fails, or the effective stage is `TOO LATE`.

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
