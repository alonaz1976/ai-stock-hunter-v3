# AI Stock Hunter V6.3.9.82

## FINAL PREP — RESILIENT FEED (2026-10-06)

This is the valid repack of build `V63982-FINAL-PREP-RESILIENT-FEED-20261006-B`.

Final deltas over the earlier V6.3.9.82 package:

- Top Action header is split cleanly: large `RANK #N` on its own line, ticker below it.
- Ticket/status/alert text wraps fully; long strings are not clipped with ellipsis.
- Provider coverage is explicit: for broad scans (50+ names), Daily-history coverage below 95% shows a degraded-data warning and makes clear skipped tickers were not evaluated.
- Keeps the calm data-wait semantics: data/freshness alone is WAIT, while red DO NOT ENTER remains for true hard execution blocks.
- Keeps Pre-Move LiquidityScore >=60 for actionable/ranked early candidates, Continuity Recovery reservation, TASE degraded-data guard, and all V6.3.9.81 logic.
- No scoring-weight changes.

---

# AI Stock Hunter V6.3.9.82

## V6.3.9.82 — Rank-first ticket + calm data-wait semantics

- Top Action tickets now use a clean large headline: `RANK #N` + ticker. `DO NOT ENTER`, `WAIT`, and `ENTRY NOW` are no longer repeated in the headline or the secondary rank line.
- Removes the duplicate `Decision ...` pill from the price/status line. The dedicated decision banner is now the single visible action headline.
- Data/freshness-only problems are **WAIT**, not `DO NOT ENTER`: OPEN/PRE-MARKET without verified live data shows `WAIT • LIVE DATA NOT CONFIRMED` in amber.
- Red `DO NOT ENTER` remains reserved for true hard trade blocks such as liquidity, timing/move-consumed, extension/chase, invalidation, heavy exit pressure, or negative evidence guard.
- Keeps the full-text wrapping, Pre-Move LiquidityScore >=60 ranking requirement, guaranteed Continuity Recovery slots, TASE degraded-data guard, Signal Gates vs Execution wording, and all V6.3.9.81 logic.
- No scoring weights were changed.

# AI Stock Hunter V6.3.9.81


## V6.3.9.81 — Premium-prep reliability + ticket readability

- Ticket fields never truncate with ellipsis: labels, values and sub-lines wrap to full text on desktop/mobile.
- Pre-Move execution quality: the baseline market turnover hard gate remains, but Top Pre-Move / ACTIONABLE EARLY now also requires LiquidityScore >= 60. Scores 40–59 remain visible as WATCH/research only.
- Continuity Recovery now has guaranteed independent SMART-Deep slots: up to 14 normal continuity names plus up to 2 prior cutoff names per market, hard-capped at 20 total. Recovery can no longer be starved by the continuity list.
- TASE market-data degradation guard: when >=70% of analyzed TASE names are stale while the exchange is OPEN (minimum 8 names), all TASE live-entry claims are blocked until fresh data returns. Raw data remains auditable.
- Signal Gates vs Execution wording from V6.3.9.80 is retained.
- No scoring weights or normal Entry/Timing/R:R rules were changed in this release.

## V6.3.9.80 — Continuity Recovery + Signal/Execution clarity
- Fixes SMART Continuity Recovery starvation: recovery names now have guaranteed bounded slots and cannot be crowded out by the fresh continuity list.
- Reserve cap widened from 14 to 20 while recovery remains limited to 2 names per market; Deep coverage only, never a trade-signal override.
- Scanner ticket now labels `Signal Gates X/6` explicitly and adds a compact execution state such as `EXECUTION READY` or `EXECUTION: WAIT RETEST`, so 6/6 signal conditions cannot be mistaken for a live executable entry.
- Preserves all V6.3.9.79 scoring, liquidity, timing, Pre-Move, Israel-time, compact-UI and tab-isolation behavior.


## V6.3.9.79 — Continuity Deep Reserve

- Adds a small **Continuity Deep Reserve** for SMART scans so prior `ENTRY NOW`, `ARMED`, `BUILDING SETUP`, `LAST SESSION ENTRY`, Top Overall and Top Action names do not disappear only because the next market-balanced Deep quota is crowded.
- Reserve is **coverage-only**: it guarantees Deep analysis but never bypasses Liquidity, Timing, R:R, Chase, Evidence or Final Decision guards.
- Uses a 2-scan TTL for qualified continuity names so the reserve cannot become a permanent shadow universe.
- Adds a tiny one-scan **SMART cutoff recovery** lane (max 2 per market, prior Discovery Score >= 80) to recover strong Daily names that were cut from Deep in the immediately prior scan. This specifically closes the class of gap that caused VST to pass Stage-0/Daily yet disappear from Deep.
- Discovery Audit now records `ReservedContinuityDeep` and `ReservedContinuityRecovery`, plus reserve lists/TTL in scan metadata.
- Keeps V6.3.9.78 collapsed scan settings, compact UI, Israel-time exports, Overall V3.14, liquid-only Overall rank, Pre-Move timing/liquidity gates and tab isolation.


## V6.3.9.78 — Collapsed Scanner settings / cleaner mobile default

- Hides the routine Scanner menu shown on mobile behind a collapsed **⚙️ Scan settings & filters** expander by default.
- The collapsed menu contains History, Forecast horizon, Target %, Decision stage, Timing context, Evidence, Risk / geometry, OOS model details and optional research overlays; behavior and saved widget values are unchanged.
- Keeps the high-level scan controls visible: Decision model, Scan depth, Coverage, Markets to scan and Display market.
- For AFTER-MARKET / CLOSED / PRE-OPEN snapshots, the compact WAIT reason now prioritizes **RECHECK AT OPEN** instead of misleadingly calling expected non-live quotes a DATA / FRESHNESS BLOCK.
- Preserves V6.3.9.77 Pre-Move blocker-label integrity, V6.3.9.76 compact ticket, liquid-only Overall ranking, Israel-time exports and Overall V3.14 scoring.
- Synchronizes app/engine build identifiers to V6.3.9.78.


## V6.3.9.77 — Pre-Move blocker-label integrity + cleaner default summary

- Fixes the remaining Pre-Move explanation bug: stale/unverified session data is now labeled **DATA BLOCK**, even when an old RETEST context is also present. A true **TIMING / MOVE-CONSUMED BLOCK** is reserved for real timing evidence such as >=60% consumed, timing hard block, late trigger, aging/too-late qualification, late/extended recent run, or high chase risk.
- Keeps blocked Pre-Move patterns **NOT RANKED** exactly as in V6.3.9.75/76; this release changes the primary explanation, not the safety gate.
- Replaces the two long Scanner summary lines with one compact **Quick status** line: `ENTRY NOW • NEAR • PRE-MOVE RANKED`. Full Decision Board and Pre-Move counts move into collapsed **Scan diagnostics**.
- Moves the Analyze explanatory note behind a collapsed **Analyze notes** expander and hides the routine "app/engine synced" line unless there is an actual mismatch/error.
- Synchronizes all engine/app build identifiers to V6.3.9.77.
- Preserves V6.3.9.76 compact UI, V6.3.9.75 timing-safe Pre-Move ranking, liquid-only Overall ranking, tab isolation, Israel-time exports and Overall V3.14 weights.

## V6.3.9.76 — Compact default UI / hidden detail text

- Keeps FINAL DECISION visible but compresses it to one short reason (for example `WAIT • RECHECK AT OPEN` or `DO NOT ENTER • TIMING BLOCK`).
- Hides the long RecommendedAction sentence from Scanner and Analyze; the complete reason remains in `Details / Why?`, Advanced diagnostics and Excel.
- Moves Scanner explanatory prose, research-overlay status, Original Signal Memory details and rank legends behind collapsed expanders.
- Keeps hard timing / liquidity / chase alerts visible because they change the action.
- Preserves all V6.3.9.75 Pre-Move timing eligibility and duplicate-column fixes.



## V6.3.9.75 — Pre-Move timing integrity + Scanner duplicate-column fix

- Top Pre-Move ranking now requires the pattern to still be early enough to matter: no timing hard block, no RETEST/TOO LATE state, less than 60% move consumed before the causal trigger, no LATE trigger, no late/extended recent-run context, and no HIGH/EXTREME chase state.
- A valid early pattern may still stay ranked while the market is closed, but is labelled **RECHECK AT OPEN** rather than **DATA BLOCK**.
- Late/move-consumed Pre-Move patterns remain visible for audit but are explicitly **NOT RANKED**.
- Scanner summary now separates **RANKED HIGH / RANKED WATCH / BLOCKED / ACTIONABLE EARLY**.
- Scanner table rendering now de-duplicates repeated/cached column labels so Streamlit/PyArrow cannot fail with `Duplicate column names found`.
- All V6.3.9.74 liquid-only Overall ranking, V6.3.9.73 tab isolation, V6.3.9.72 Analyze safety, V6.3.9.71 Overall weights/Israel time, and earlier logic remain intact.

## V6.3.9.74 — Liquid-only Overall ranking
- Keeps the **Overall Score itself unchanged**; the V3.14 score still uses 40% Setup/Momentum + 30% Entry Timing + 18% Money Flow + 12% R:R, with Evidence kept outside the numeric score.
- `OverallStrengthRank` is now assigned **only when `LiquidityHardGateOK = TRUE`**. A stock with a liquidity execution block can no longer occupy #1/#2/etc. in the user-facing Overall leaderboard.
- Adds `RawOverallStrengthRank` for audit/research so the all-stock raw score ordering is still preserved without contaminating the executable Overall leaderboard.
- Adds `OverallStrengthEligible` and `OverallStrengthStatus` (`RANKED — LIQUID` / `NOT RANKED — LIQUIDITY BLOCK`) to Scanner/Excel diagnostics.
- Low-liquidity names remain visible in research/diagnostic views with their raw Overall Score, but their user-facing Overall Rank is blank and they remain hard-blocked from execution/Pre-Move ranking.
- Retains all V6.3.9.73 tab isolation, Analyze cached-payload safety, Israel-time exports, compact ticket, single Final Decision, and liquid-only Pre-Move protections.


## V6.3.9.73 — Tab isolation + Analyze cached-payload safety
- Adds a render boundary around Scanner, Analyze, Optimizer and Feedback. A stale/corrupt cached result in one tab can no longer abort the whole Streamlit script and leave later tabs blank.
- Finishes Analyze numeric hardening for the remaining legacy research-summary counters and last-price fallback. Text sentinels such as `—`, `N/A` and `None` are safely treated as unavailable instead of raising `ValueError`/`TypeError`.
- If a tab-specific render problem still occurs, that tab now shows a compact error message while the other tabs continue to render normally.
- Keeps all V6.3.9.71/72 changes: OVERALL Score weights without Evidence, Evidence as confidence only, Israel-time exports, compact ticket, liquid-only Pre-Move ranking and single final decision semantics.



## V6.3.9.72 — Overall Score + Evidence separation + Israel-time exports
- Renames the user-facing `Decision Score` to **OVERALL SCORE**. Internal `DecisionRankScore` remains for backward compatibility with Feedback and older exports.
- Overall V3.14 weights are now **40% Setup/Momentum + 30% Entry Timing + 18% Money Flow + 12% R:R**. Historical Evidence has **0% numeric weight**.
- Evidence remains a separate confidence/validation layer (`LOW SAMPLE / BUILDING / VALIDATED`) and a genuine negative-OOS hard guard can still block qualification. Low sample alone no longer depresses Overall.
- Acceleration still raises Overall only indirectly through Entry / Move / Explosive. `RawOverallScore`, `OverallAccelerationBonus`, and `OverallWeights` make the uplift auditable without double counting.
- Scanner and Analyze use **OVERALL** as the main score headline even when the final action is `ENTRY NOW`; Entry remains a separate timing tile.
- Low-sample Evidence no longer creates a large yellow warning on the front ticket; the Evidence tile carries that confidence information. A true Evidence hard guard is still prominent.
- Final trade decision is recomputed after Decision Board live-gate normalization, and the `ENTRY NOW` filter now uses `FinalTradeDecision`, preventing legacy stage labels from contradicting the final action.
- Top Action excludes `DO NOT ENTER` rows; `ENTRY NOW` can only appear as a card headline when the final execution decision is actually `ENTRY NOW`.
- Scanner Excel filenames use the **actual completed scan time in Israel**. The About sheet now records both `Generated` and `Scan completed` in `Asia/Jerusalem`, so a 21:29 scan is no longer exported with a UTC-looking filename.
- Other user-facing export filenames / Generated timestamps use Israel local time as well.
- V6.3.9.70 compact Momentum labels, reduced front-ticket prose, liquid-only Pre-Move ranking, score-lift card, liquidity/R:R protections and all prior safety gates are retained.

## V6.3.9.70 — Compact ticket + Decision lift audit + liquid Pre-Move
- Momentum ticket labels are compact (`STRONG`, `MIXED`, `COOL`, `BEAR`, `N/A`) so 15m/1H state fits on mobile.
- Verbose front-of-ticket path/original-memory/acceleration prose is hidden; details remain in Excel / Advanced diagnostics.
- ENTRY NOW cards headline the actionable **Live Entry Score** instead of the lower composite Overall score; Overall remains visible as context.
- Decision/Overall already receives the acceleration improvement indirectly through boosted Entry, Move and Explosive. New audit fields `RawDecisionRankScore` and `AccelerationDecisionBonus` expose the exact uplift without double-counting.
- Score Lift card now shows Entry bonus, Overall/Decision bonus, Explosive bonus and Move bonus.
- Low-liquidity Pre-Move patterns are hard-blocked from `PreMoveRadarEligible`, receive no `PreMoveRadarRank`, and cannot appear in Top Pre-Move. Research pattern fields remain available for audit.


## V6.3.9.69 — Clean ENTRY NOW UI + Explicit Acceleration Score Lift

### What changed in V6.3.9.69

- **Hide irrelevant Continuation BLOCKED during a valid Primary ENTRY NOW:** when `FinalTradeDecision=ENTRY NOW` and `FinalTradePath=PRIMARY`, the red/blocked Continuation tile and blocked-path caption are omitted. Continuation remains in the exported audit fields and still appears whenever the final decision is WAIT/DO NOT ENTER.
- **New visible `Acceleration Score Lift` tile:** the ticket now shows the score improvement caused by the V6.3.9.67 acceleration layer as raw → adjusted values, for example `Entry 72→84 (+12)`, together with `Explosive` and `Move` raw→adjusted lifts.
- **Existing Entry subtitle remains auditable:** the Entry card still shows `raw X +Y accel`, while the new lift tile makes the effect much easier to see at a glance.
- No scoring thresholds, optimizer weights, liquidity gates, R:R gates, Chase protection, or final-entry rules were changed in this UI release.

V6.3.9.68 remains fully retained below.


## V6.3.9.68 — Final Entry Decision Hierarchy + Primary / Continuation Separation

### What changed in V6.3.9.68

- **One final user-facing trade decision:** every analyzed row now resolves to `ENTRY NOW`, `WAIT`, or `DO NOT ENTER`. In this release an immediate `ENTRY NOW` still requires the existing live `ActionableNow` gate; the executable path is labeled `PRIMARY`, while Continuation/Retest remain separate diagnostics and are not silently promoted into new trades.
- **Primary and Continuation are separated:** a valid live `PRIMARY` entry is no longer cancelled or visually contradicted by `Continuation = BLOCKED`. Continuation is a later-entry path, not a prerequisite for the initial trade.
- **VST contradiction fixed:** the supplied V6.3.9.67 snapshot had `ActionableNow=True`, 6/6 entry conditions, Liquidity 100, Chase LOW and live R:R 1.92x, but the visible recommendation still said `RESEARCH ONLY` because the ranking lane was `EMERGING SETUP`. V6.3.9.68 now correctly renders that same snapshot as `⚡ ENTRY NOW — PRIMARY PATH • LOW / LOW-SAMPLE EVIDENCE`.
- **Evidence is confidence unless truly negative:** low sample / unvalidated OOS evidence reduces the displayed confidence; it does not overwrite an otherwise valid live entry. A populated negative-OOS hard guard still blocks entry.
- **Acceleration wording is no longer ambiguous:** `AccelerationEntryNow` is treated as an acceleration confirmation signal, not the final trade decision by itself. The UI shows `ACCELERATION CONFIRMED` unless the final execution decision is also `ENTRY NOW`.
- **Ticket hierarchy cleaned up:** the top of Scanner/Analyze now shows `FINAL DECISION`, `Confidence`, `Continuation`, and `Opportunity Window`. The decision reason explicitly states when a valid Primary path remains active despite a blocked Continuation path.
- **New audit fields:** `FinalTradeDecision`, `FinalTradePath`, `FinalTradeConfidence`, `FinalTradeReason`, `FinalTradeEntryNow`, and `FinalTradeHardBlock` are exported for later validation.
- No Optimizer/OOS Prediction weight changes. V6.3.9.67 Pre-Breakout Acceleration and score-lift logic remain intact.

V6.3.9.67 remains fully retained below.

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


## V6.3.9.72
- Fixed Analyze tab ValueError caused by cached/legacy display sentinels (such as `—`, `N/A`, or `None`) reaching direct numeric formatting/casts.
- Analyze now uses safe numeric parsing for live quote, AH metrics, RVOL, reliability, optimized diagnostics, chase/timing fields, backtest summary, trade plan, retest plan and dynamic weights.
- Preserves all V6.3.9.71 Overall Score / no-Evidence-weight / Israel-time changes.