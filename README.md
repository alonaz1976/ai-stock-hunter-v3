# AI Stock Hunter V6.4.2.20 — Unified Market-First Decisions

**Release 2026-10-09 • Premium Scanner / Analyze presentation**

- Before the regular-market open (`PRE-OPEN` / `PRE-MARKET`): display **WAIT — PRE-MARKET** on the primary User Signal card.
- After session close (`CLOSED` / `AFTER-MARKET`): display **WAIT — MARKET CLOSED** on the primary User Signal card.
- Show the technical lifecycle (`ARMED`, `LAST SESSION ENTRY`, `CLOSE WATCH`, etc.) separately as a labeled **SETUP:** chip.
- If the underlying model has an actual risk veto, keep the specific risk reason in the secondary line; do not imply that reopening alone removes it.
- While `OPEN`, keep existing `ENTER NOW` / `WAIT` / `DO NOT ENTER` and every preexisting execution/data/risk gate unchanged. The strict 17-minute timestamp check remains unchanged.
- Stable closed-session display uses the saved scan phase and decision, not a fresh market request per redraw. The underlying saved final decision remains available for audit.
- Shared display helpers cover both Scanner and Analyze; non-regular-market Analyze does not show a live-execution plan as though the market were open.

---

# Previous release: V6.4.2.19 — Stable Completed-Scan Decisions

- A completed CLOSED-market scanner result keeps the FinalTradeDecision, reason, user signal and ranking values saved with that scan. Visiting Scanner or changing display filters no longer recalculates those decisions into a different answer.
- Scanner continues to check other/open-market records and live execution gates. A previously open-market ENTRY NOW is **not** locked or guaranteed once the quote expires or the exchange closes.
- A **new scan** is still a new decision and may legitimately change if the official close, historical bars or other inputs were revised. This patch does not freeze independent new scans.
- Technical stage (e.g. previous-session `ENTRY NOW`) remains historical context, distinct from executable `FinalTradeDecision`.
- 17-minute quote age and all risk blocks remain unchanged.

# AI Stock Hunter V6.4.2.19 — Explain execution blocks on Premium tickets (2026-10-09)

- `ENTER NOW` is permitted with an **exchange-local, timestamp-verified quote no older than 17 minutes** (15-minute free-feed lag plus a 2-minute transport/refresh allowance), provided **all other entry, sell-pressure, risk and market-session guards pass**. This is still delayed, **not broker-executable real-time pricing**.
- Applies to Scanner, Analyze, direct/metadata Yahoo quotes, 1m/5m Yahoo candles, 15m confirmed-bar eligibility, and the final decision recheck. The boundary is inclusive at 17.0 minutes; older, missing, different-session or unverified timestamps remain blocked. One-hour candles remain analysis-only.
- Scanner/Analyze save the provider full-precision timestamp separately from the user-facing minute label, preventing minute truncation from consuming the 2-minute allowance.
- Favorites frozen price and completed-session close rules, chart candle intervals, and bearish-distribution/evidence gates stay unchanged. Do not regard this tolerance as proof of forecast reliability. Confirm executable price with the broker.

## V6.4.2.16 — 15-minute verified price for ENTRY NOW

- Free-feed policy: ENTER NOW may use a **verified exchange-local price timestamp no older than 15 minutes**, even when the provider labels the quote DELAYED. This is **not** live execution pricing; reconfirm with broker before placing an order.
- Scanner 15-minute confirmed bar or timestamped intraday quote can qualify; a 1-hour bar cannot establish executable price freshness. Scanner/Analyze and final-decision rechecks reject cached historical snapshots older than 15 minutes, other-session bars and missing/unverified timestamps.
- Confirmed bearish distribution after a failed spike vetoes PRIMARY ENTRY NOW. Very low historical samples require independent momentum, volume and flow confirmation for an immediate recommendation.
- All previously implemented Favorites, navigation, and independent-feed fallbacks retained. No subscription or API key is required for the timestamped Yahoo path, but 15-minute quotes are **not guaranteed** for every exchange/ticker.
- Exchange phase, liquidity, price zone, invalidation, R:R, same-session quality and chase safeguards remain mandatory. No retroactive promise of trade performance.

# AI Stock Hunter V6.4.2.16 — Fix Frozen-Return Price Suppression (2026-10-09)

## Why prices vanished in Favorites
The Favorites XLSX from V6.4.2.14 already contains Yahoo **completed 5m regular-session bar prices** of **HKD 8.85 at 16:05 HKT** for `2465.HK`, and **HKD 27.48 at 16:05 HKT** for `0470.HK`. Those values were rejected ONLY because the movement from the user-selected frozen price was >=4% and TradingView lacked an independent exchange trade timestamp. The 8.85 price is also corroborated by the user's Google screenshot at 16:08 HKT. The earlier claim that 9.87 was the verified Oct 9 closing price was wrong.

**Fix**: Keep strict market-session date and actual timestamp validation. Completed Yahoo intraday bars from the latest required session, near the scheduled exchange close, now supply the Favorites *display-only* price **without requiring a second vendor**. The validation status explicitly says LAST SESSION CLOSE, single vendor, not cross-vendor verified, and never grants trade entry. A 4% move relative to an arbitrary frozen price is not a quote-integrity test.

- `Frozen Price` remains immutable and the percentage change is measured against the frozen quote (not previous close).
- A provider price without verified session timestamp can still be withheld pending appropriate verification; the new export column `Provider Price (diagnostic)` helps explain whether a quote was retrieved but rejected.
- Existing optional EODHD provider support remains available, but the fix does not require subscribing to it where Yahoo intraday bars already suffice.
- The Favorites snapshot is invalidated once on first startup of this version so the old hidden prices are not retained.
- This is a **code-level** fix, not a live Streamlit deployment/provider availability test. Explicit Refresh prices once after installing.

---

# AI Stock Hunter V6.4.2.14 — Independent HK Market Data Connector (2026-10-09)

## Why prices are still missing in 6.4.2.13
- V6.4.2.13 export contained 11 Favorites, with **2465.HK** and **0470.HK** missing a validated displayed price. Yahoo's timestamped bar reported 8.85 and 27.48, conflicting with separately published 9-Oct closes of 9.87 and 28.80. The strict guard concealed the returns. The other TradingView fallback had no exchange trade timestamp, so it could not settle the conflict.
- A 4% move since **Frozen Price** does not itself make a quote unreliable. V6.4.2.14 changes the approach: an independently authenticated, exchange-date-and-time-verified *delayed* market data feed may supply the Favorites display price. It must not be confused with live execution eligibility.

## Enable independent Hong Kong delayed quotes
1. Create your own EODHD account and verify that your plan includes **Hong Kong stocks and the Live (Delayed) endpoint**. Provider documentation: https://eodhd.com/financial-apis/live-ohlcv-stocks-api . Free/demo entitlements and market coverage are limited.
2. In the **Streamlit application Settings > Secrets**, configure the key **server-side** (never commit it to GitHub):

   `EODHD_API_TOKEN = "YOUR_PRIVATE_TOKEN"`

   Alternatively configure server environment variable `EODHD_API_TOKEN`.
3. Restart the Streamlit app, then open **Favorites > Refresh prices**. Quote source and validation result appear in the Excel export. Vendor snapshot is cached 4 minutes; up to 15 HK symbols are fetched per batch to reduce latency and API traffic.
4. When the market is open, delayed quotes require a matching Hong Kong session date, valid market timestamp, a price inside reported session high/low, and age <= 40 minutes. After close, a near-close timestamp is identified as a last-session close. All EODHD quotes are **DELAYED** and never treated as live trade-entry confirmation.
5. Without a supported active vendor connection, the app continues to hide materially unverified prices (including 2465.HK/0470.HK) and shows why. No hard-coded third-party quote values or unlicensed page scraping are used.

## Validation boundary
The code path has been tested with simulated vendor responses and a missing-key case, but no EODHD credentials or live HK entitlement were supplied, so live quote availability **has not been verified**. Do not interpret the integration as confirmation that missing prices will immediately appear without a functioning provider key/plan.

Previously delivered batch removals, Scanner/Analyze fast navigation, Score/Entry/Backtest rules, quote conflict guards and four-file packaging are retained.

---

# AI Stock Hunter V6.4.2.13 — Verified closed-session prices + cache safety (2026-10-09)

- Favorites now checks the latest regular-session price **with a verified exchange-time timestamp**, preferring a Yahoo regularMarketTime quote, then a timestamped 5m/15m regular-session final bar for markets that have completed trading. This repairs situations where the daily reconstructed quote is incorrectly tagged as official for 2465.HK or 0470.HK and US previous-session close quotes such as CHKP are missing.
- Requires the correct expected exchange session and near-regular-close timing; HTTP fetch timestamps, stale TradingView scanner quotes and incomplete bars are never promoted to a verified close.
- A closing bar reconstructed from intraday data is labelled `LAST SESSION CLOSE`, not exchange-official. Material moves (>=4% versus frozen) still require time-verified independent evidence before any return is shown.
- Previously verified *completed-session closes* no longer disappear after 15 minutes in the UI; live/extended-session snapshots still expire and require explicit Refresh.
- Added cache generation reset so a new version will not reuse the old Favorites session snapshot.
- Price retrieval remains best effort: where providers do not expose a verifiable closing trade, current price and performance remain unavailable rather than inventing accuracy. Only a live deployment can validate actual provider coverage.
- Other Scanner / Analyze fast-navigation improvements from V6.4.2.12 remain intact. `app.py` and `quant_engine.py` match on V6.4.2.13.

# AI Stock Hunter V6.4.2.12 — Fast Scanner / Analyze Navigation (2026-10-09)

## Navigation performance hotfix

- **Lazy sections:** The previous `st.tabs` executed all five heavy pages on every rerun, even when hidden. Navigation now uses a persistent horizontal workspace selector and executes **only the active page**.
- **Preserves saved results and background jobs:** Scanner/Analyze worker runtimes and last completed snapshots are unchanged; switching pages does not trigger a new market scan, Analyze run, or Feedback recomputation. Common scanner settings and Analyze ticker/settings are retained when changing sections.
- **Scanner Excel prepared only on request:** `Prepare Scanner Excel` computes the filtered workbook only when clicked; a following Download button serves those prepared bytes. New scans or changed filters invalidate the prepared export. Excel still contains the original scan data/fields.
- **Analyze cached chart:** Default 3-month daily chart uses the features in the already-completed Analyze payload; opening the page no longer makes an extra blocking network request. Chart data outside the saved range or intraday charts require an explicit `Load / refresh chart data` press and use a 3-minute display-data cache.
- **Scanner live rerenders throttled:** The full scanner UI while a background scan is running is rebuilt every 4 seconds instead of every second. It is not a trading-data refresh interval and does not alter model calculations.
- **Matching app/engine versions:** Both app and quant engine identify as V6.4.2.12; scoring/market guard logic stays unchanged from V6.4.2.11.
- **Favorites:** prior batch remove and strict quote-validation changes from V6.4.2.10–11 are retained.

## Validation boundaries

Local syntax checks and isolated regression tests verify the lazy-page structure, navigation-value retention and no eager Scanner XLSX/Analyze chart network calls. The installed Streamlit environment and live price providers were not available for interactive end-to-end timing tests. Actual mobile navigation speed should be checked after deploy; server start, network/API delays during an explicitly started scan, and a newly requested chart may still take time.

---

# V6.4.2.11 — Strict Favorites price verification (2026-10-09)

Critical correction to V6.4.2.10: the cross-check accepted a TradingView scanner price without a verifiable exchange timestamp. For 2465.HK, the exported primary and secondary prices were both 8.85, creating a false CROSS-CHECKED -10.29% return although external market data for 2026-10-09 indicated about 9.87. V6.4.2.11 now rejects timestamp-less second-source values, requires the same verified exchange session and actual provider independence before confirming moves ≥4%, and blocks a daily bar being labeled an official close while the market is still OPEN. Rejected quotes show no Current Price/Change % and retain the original frozen price. It invalidates the previous in-session Favorites cache on first render. No quote is fabricated. Live market feed access still needs to be validated in the deployed application.

## Verification status
AST/code tests run locally with mocked feeds. A third-party live feed has not been authenticated in runtime, so a return hidden as unverified is intentional and must not be described as a verified gain/loss.

---

# AI Stock Hunter — V6.4.2.10 Favorites Safe Quotes + Batch Remove

## Main fixes (9 Oct 2026)

- Favorites: select multiple stars/checkboxes in a single form. Selection does not call Python, rerun Streamlit, refresh market prices, or delete a stock.
- Press **Remove selected Favorites** once: a single parameterized atomic SQLite DELETE and one DB persistence notification; the remaining prices are reused. A single fragment rerun updates the table, without rerunning Scanner/Analyze.
- Market prices are held in a dated snapshot until the user presses **Refresh prices**. An unrefreshed snapshot expires after 15 minutes; prices/returns are suppressed rather than reported as current.
- Favorites validates quote provenance and session dates. Unverified/stale provider timestamps, stale session dates and suspicious quote scales are not eligible for a percentage return.
- Price moves >= 4% from the original frozen ticket price are independently cross-checked with a second market-data provider. If the second quote is unavailable or differs by > 2%, **Current Price** and **Change %** are hidden, and a clear reason is exported. A TradingView scanner fetch cannot by itself establish real-time trade freshness.
- Official close quotes are explicitly labelled by their trading session (not as a misleading midnight quote timestamp).
- Production quote gate also rejects explicitly unverified/stale source timestamps and mismatched expected/actual session dates. Existing score weights, backtest methods and entry thresholds are unchanged.
- Exports include quote validation status, source, second-provider price, and reasons.
- Favorites frozen prices remain immutable until an item is removed and re-added. Existing Feedback/Favorites DB schema is unchanged.

**Important:** Quote cross-validation can be temporarily inconclusive when market data providers disagree or one is unavailable. That is intentional: show no performance figure rather than a false return. Check a broker or exchange for actual execution prices.

---

# AI Stock Hunter — V6.4.2.9 Favorites Remove-Star Hotfix

## V6.4.2.9 — yellow row star removal no longer crashes

- **Fixed the Favorites row-star crash shown on mobile.** Removing a Favorite from the yellow `⭐` row button successfully deleted the row, but the follow-up toast used the hollow star `☆` as Streamlit's `icon=` value. Streamlit accepts only a single supported emoji in that field, so it raised `StreamlitAPIException` after the click.
- **Removal toast now uses a supported emoji (`✅`).** The yellow `⭐` button remains the row action exactly as designed; after removal the stock disappears from Favorites and its ticket star returns to `☆`.
- The responsive Favorites table, exact ticket-price freeze, compact timestamps, Excel export, Analyze Series-safe fix, Action-first ranking, Timing Revalidation, bilingual help and Flow are all retained.
- No score weights, Entry thresholds, R:R floors, liquidity rules, Optimizer/OOS weights, or trading logic changed.

---

# AI Stock Hunter — V6.4.2.8 Favorites Responsive Table Fix

## V6.4.2.8 — Favorites stays a real table on mobile

- **Fixed the mobile Favorites layout shown in the screenshot.** Streamlit automatically collapsed each `st.columns` row into a vertical stack on narrow screens, which made the headers appear first and the AAPL values far below them. The Favorites area now uses a scoped responsive grid so every stock remains one horizontal table row.
- **Yellow removal star stays beside its own ticker row.** Each row begins with `⭐`; pressing it removes that exact stock immediately from Favorites.
- **Table columns remain aligned:** Ticker, Frozen Price, Current Price, Change %, and Frozen At. Market/currency stay as compact secondary text so the table remains readable.
- **Mobile behavior:** the table no longer turns into cards/stacked fields. On very narrow screens it keeps the row structure and allows a small horizontal swipe rather than breaking the row.
- Refresh Prices and Favorites Excel export remain unchanged. Exact ticket-price freezing, compact `D.M.YY HH:MM` timestamps, Analyze Series-safe fix, Action-first ranking, Timing Revalidation, bilingual help and Flow are all retained.
- No score weights, Entry thresholds, R:R floors, liquidity rules, Optimizer/OOS weights, or timing hard-block thresholds changed.

---

# AI Stock Hunter — V6.4.2.7 Favorites UX + Exact Ticket Freeze

## V6.4.2.7 — exact ticket-price freeze, yellow star behavior, compact Favorites table and Excel export

- **Frozen Price now uses exactly the price visible on the ticket at the instant the star is pressed.** Favorites no longer perform a second quote fetch before freezing, eliminating click-time price drift between the ticket and the stored reference price.
- **Star state is visually explicit.** `☆` means not in Favorites; after selection it becomes the yellow `⭐` and the stock is immediately added. Pressing the yellow star again removes it and returns the ticket to `☆`. Scanner and Analyze use the same behavior.
- **Per-row yellow remove star inside Favorites.** Every tracked ticker has its own `⭐` action; pressing it removes that row immediately, so the old separate Manage Favorites removal workflow is no longer needed.
- **Compact date/time format.** Favorite freeze timestamps are shown as `D.M.YY HH:MM` (for example `3.11.26 18:23`) with seconds and long ISO strings removed. Current quote timestamps use the same compact formatting when a parseable timestamp is available.
- **Cleaner Favorites screen.** Removed the redundant explanatory/summary/management blocks and kept the screen focused on refresh, export and the tracked rows.
- **Favorites Excel export added.** The tab now downloads an XLSX containing ticker, market, Frozen Price, Current Price, Change %, currency, freeze timestamp, current quote time and quote status.
- **All V6.4.2.6 fixes are retained**, including the Analyze pandas-Series crash fix, Action-first ranking, Timing Revalidation semantics, separated Market/Quote/Timing/Data gates, bilingual help and dedicated Flow.
- No score weights, Entry thresholds, R:R floors, liquidity rules, Optimizer/OOS weights, or timing hard-block thresholds changed.

---

# AI Stock Hunter — V6.4.2.6 Analyze Series-Safe Gate Fix

## V6.4.2.6 — Analyze no longer crashes on one-row audit DataFrames

- **Fixed the Analyze `ValueError: The truth value of a Series is ambiguous` crash.** The separated Timing / Market / Quote / Data gate helpers now normalize a one-row pandas DataFrame to a scalar row before boolean evaluation.
- **Analyze export uses scalar gate facts.** Summary and Entry Audit compute `TimingGateOK`, `TimingGateState`, `MarketGateOK`, `QuoteFreshGateOK`, `LiquidityGateOK`, and `DataGateOK` without ever evaluating an entire pandas Series as a boolean.
- **Data Gate separation is preserved.** Removed a stale Analyze-export overwrite that accidentally mixed live quote freshness back into `DataGateOK`. Quote freshness remains only in `QuoteFreshGateOK`, exactly as designed in V6.4.2.4.
- **Favorites + Action-first + Timing Revalidation are all retained** from V6.4.2.5.
- No score weights, Entry thresholds, R:R floors, liquidity rules, optimizer/OOS weights, or timing hard-block thresholds changed.

---

# AI Stock Hunter — V6.4.2.5 Favorites + Action-First UX + Timing Revalidation

## V6.4.2.5 — Favorites tracking, action-first Top cards and clean timing semantics

- **New `⭐ Favorites` tab.** Tap the small star beside a ticker title in Scanner or Analyze to add/remove it from durable Favorites. Favorites are stored in the same portable Feedback DB, so they survive Streamlit restarts and participate in the existing backup/persistence flow.
- **Frozen price is immutable.** On selection the app freezes the freshest market-aware price available at that moment; if a fresher quote is unavailable it falls back to the ticket price. `Frozen Price` never moves until the stock is removed and added again.
- **Live Favorites tracking.** The Favorites table shows `Frozen Price`, market-aware `Current Price`, and `Change % = Current / Frozen - 1`, plus market, currency, freeze time, current quote time and quote status. A dedicated Refresh button clears the 30-second quote cache and reloads prices.
- **Action-first customer hierarchy.** In the default Scanner view, real `ENTRY NOW` names are shown first in `Top Actionable Now`, sorted by `Action Rank`. Strong but non-actionable names are moved to a separate `Top Setups — Not Actionable Yet` section. Pre-Move remains its own radar.
- **Headline rank is no longer ambiguous.** An actionable ticket shows `ACTION RANK #…`. A non-actionable candidate shows `SETUP RANK #…` instead of the confusing `OVERALL RANK`. On actionable tickets the Setup Rank remains a small secondary context line. Analyze uses the same semantics.
- **Previous-session Timing is no longer called a hard block.** When current-session timing has not yet been revalidated, the UI/export reason is `TIMING REVALIDATION REQUIRED`; a genuine reliable same-session timing veto alone is `TIMING HARD BLOCK`.
- **New Timing audit fields:** `TimingGateState` and `TimingGateReason` distinguish `PASS`, `NOT REQUIRED`, `REVALIDATION REQUIRED`, `INCOMPLETE`, and `HARD BLOCK`.
- Regression check on the V6.4.2.4 scan: 71/72 non-executable-market rows resolve to `Timing NOT REQUIRED`; the one genuine reliable timing hard block remains blocked. `TTWO` and `SAC` now classify as `TIMING REVALIDATION REQUIRED`, not false hard blocks.
- No score weights, OOS/Optimizer weights, Entry thresholds, R:R floors, liquidity thresholds, chase thresholds, or timing hard-block thresholds changed.

---

# AI Stock Hunter — V6.4.2.4 Market / Quote / Timing Gate Separation

## V6.4.2.4 — closed market no longer masquerades as a Timing failure

- **Timing is now a pure timing gate.** `TimingGateOK` fails only for a genuine reliable same-session timing hard block, or when live timing is required during an executable phase and the required timing measurement is incomplete. `CLOSED`, `AFTER-MARKET`, and `PRE-OPEN` no longer turn missing live timing into a red Timing failure.
- **Market availability is independent.** New `MarketGateOK` records whether the current exchange phase is executable under the existing rules. Regular `OPEN` passes; `PRE-MARKET` passes only when the existing pre-market confirmation is confirmed; non-executable phases fail the Market gate.
- **Live quote freshness is independent.** New `QuoteFreshGateOK` carries only the live-price freshness fact. When the market is not executable, the Premium parameter panel shows `N/A • MARKET NOT EXECUTABLE` instead of a misleading red quote/timing failure.
- **Data Gate is now session/data integrity only.** `DataGateOK` checks `SessionDataFresh` + `DataQuality`; it no longer includes live quote freshness. Quote age/freshness remains a separate execution gate.
- **Closed-session ARMED / previous-session ENTRY context stays intact.** A saved strong setup can remain `CLOSE WATCH — RECHECK AT OPEN` without being demoted to `TIMING INCOMPLETE / HARD BLOCK` merely because current-session move-consumed timing is unavailable after the market closes.
- **Real timing hard blocks still win.** A reliable same-session `MoveConsumedBeforeTriggerPct` hard block remains a Timing failure even after close; this release removes only false failures caused by non-executable market state.
- **Premium drilldown is clearer.** USER SIGNAL / ENTRY parameter panels now separate `Timing Gate`, `Market Gate`, `Live Quote Gate`, `Liquidity Gate`, and `Data Gate`. The TIMING panel itself no longer mixes market/quote status into the timing diagnosis.
- **Scanner and Analyze exports** now include `MarketGateOK` and `QuoteFreshGateOK` beside `TimingGateOK`, `LiquidityGateOK`, and `DataGateOK`.
- No score weights, OOS/Optimizer weights, Entry thresholds, R:R floors, liquidity thresholds, chase thresholds, or timing hard-block thresholds changed.

---

# AI Stock Hunter — V6.4.2.3 Bilingual Help + Flow + Execution Gate Truth

## V6.4.2.3 — clearer ticket, bilingual parameter drilldown, dedicated Flow and strict active-path semantics

- **`ExecutionPath=NONE` is now authoritative.** When no active execution path exists, Scanner/Analyze never infer a live Primary path from a legacy `PriceActionableNow` flag and never show `PRICE ABOVE ENTRY ZONE` / `PRICE BELOW ENTRY ZONE`. Old Primary geometry remains research context only. The front reason becomes missing Entry confirmation or `NO ACTIVE EXECUTION PATH`.
- **`PriceActionableNow` is price-only.** It answers only whether the current quote is inside the active execution zone. Separate audit gates now carry the other truths: `ExecutionGeometryValid`, `ExecutionRRFloorOK`, `TimingGateOK`, `LiquidityGateOK`, `DataGateOK`, and final `EntryNowHardGateOK`. No safety gate is loosened.
- **Dedicated FLOW tile added to every Premium ticket** in both Scanner and Analyze. The front tile shows Net Flow (or Money Flow when Net is unavailable) plus the buyer/seller label. Its first-level detail shows `Net Flow`, `Inflow`, `Outflow`, `Money Flow`, `Institutional Flow`, and `Flow Label`, with positive/negative/watch coloring. Missing Flow remains `NO DATA`; the UI no longer manufactures a bullish default.
- **Every second-level parameter explanation is bilingual.** Desktop uses a true 50/50 English / Hebrew split. Mobile stacks English first and Hebrew second so the panel stays readable and inside the viewport.
- **Hebrew explanations are RTL-safe.** Hebrew prose is kept clean and English technical terms/values are isolated instead of being mixed into Hebrew sentences in a way that breaks reading direction.
- **Nested `i` behavior is preserved everywhere.** The first `i` opens the compact parameter list; each parameter has its own `i`/row drilldown with bilingual meaning, current value and current interpretation. Entry Score still adds its exact numeric score breakdown underneath the bilingual explanation.
- **Analyze now mirrors Scanner gate semantics** before decision rendering: pure price location, independent R:R, timing, liquidity and data gates, and the same active execution path.
- Scanner/Analyze audit exports include `TimingGateOK`, `LiquidityGateOK`, and `DataGateOK` beside the existing execution-path fields.
- No scoring weights, Optimizer/OOS weights, Entry thresholds, R:R floors, liquidity thresholds or timing thresholds changed. This release is execution truth + explainability + UI transparency.

---

# AI Stock Hunter — V6.4.2.2 Active Zone + R:R Truth

## V6.4.2.2 — price-in-zone is independent from R:R validity

- **Execution zone is now the price truth even when R:R fails.** `ExecutionPlanValid` includes the R:R floor, so it can no longer decide whether the current quote is inside/outside the active entry zone. A valid `ExecutionPath` + `ExecutionEntryLow/High` owns the price comparison.
- **Fixes false `PRICE ABOVE ENTRY ZONE` blockers** seen in V6.4.2.1 when the quote was actually inside the active zone but T1 R:R was below minimum. In those cases the front decision is now `WAIT — R:R BELOW MINIMUM`, with the price shown as `PASS • IN ENTRY ZONE` inside the info panel.
- **Price and R:R are separate engine facts.** New engine audit fields: `ExecutionPriceInZone`, `ExecutionGeometryValid`, and `ExecutionRRFloorOK`. `PriceActionableNow` now means executable price geometry only; `RRActionable` remains the independent R:R gate. `ENTRY NOW` still requires both, so no safety gate is loosened.
- **Closed / pre-open markets stay clear.** Market state outranks price/R:R presentation when execution is not currently possible, so closed names show `RECHECK AT OPEN` instead of a misleading live-zone blocker.
- **No fake Active R:R when no path exists.** `ActiveExecutionRR_T1/T2` are blank when `ExecutionPath=NONE`. Research-only geometry is preserved separately as `CandidateExecutionRR_T1/T2`. `LiveRRDisplayStatus` becomes `N/A — NO ACTIVE EXECUTION PATH`.
- **Recommended Action and Premium card now share one blocker engine.** This removes cases where the card said one thing and the exported/secondary action string said another.
- Added the separated execution facts and Active/Candidate R:R fields to Scanner/Analyze audit exports.
- No scoring weights, OOS/Optimizer weights, liquidity thresholds, Entry thresholds, Timing thresholds, or R:R floors changed. This is an execution-semantics consistency fix.

---

# AI Stock Hunter — V6.4.2.1 Execution Truth Sync

## V6.4.2.1 — active path owns Price, Timing Hard Block and Live R:R

- **Active execution zone is now the price truth.** If `ExecutionPath` has a valid live plan and the quote is inside that exact zone, stale Primary `EntryDistancePct` / `PullbackNeededPct` can no longer produce `WAIT — PRICE ABOVE ENTRY ZONE`. A 1-basis-point edge tolerance also prevents floating-point rounding from turning an on-edge quote into a false pullback warning.
- **Timing hard blocks now require reliability everywhere.** `TimingConsumedHardBlock` is canonical only when `TimingConsumedReliable=True` and the measurement is same-session. Low-reliability, below-trigger, tiny-move or previous-session ratios remain audit context and cannot silently become `TOO LATE`, `ARMED BLOCKED`, or a Close-Watch contradiction. The old raw flag is preserved as `RawTimingConsumedHardBlock`.
- **Decision Ranking uses the same reliability rule.** The 70%/80% `AGING / RETEST / TOO LATE` states are applied only to reliable Move-Consumed measurements.
- **Hard Block still wins when it is real.** A genuine reliable timing hard block remains `DO NOT ENTER` and cannot be promoted to `CLOSE WATCH`.
- **One Live R:R truth: the active Execution Path.** Scanner and Analyze headline/filter R:R now use `ExecutionRR_T1/T2` (or the current computed execution-plan values), never legacy Primary `LiveRR` from another path. This fixes RETEST cases such as 1921.HK / 0199.HK where the displayed R:R differed from the active execution plan.
- Added `ActiveExecutionRR_T1/T2` audit fields. `DecisionRankRRQuality` also prefers the active execution-path T1 R:R.
- No scoring weights, OOS/Optimizer weights, liquidity thresholds or Entry confirmation thresholds changed. This release synchronizes existing execution facts across the UI, decision hierarchy and export.

---

# AI Stock Hunter — V6.4.2.0 Decision Clarity + Exact Blocker Drilldown

## V6.4.2.0 — one front reason, exact numbers behind `i`

- **Front decision is now deliberately short.** Scanner and Analyze show one primary actionable reason such as `WAIT — PRICE ABOVE ENTRY ZONE`, `WAIT — R:R BELOW MINIMUM`, `WAIT — LIVE DATA NOT FRESH`, or `DO NOT ENTER — LIQUIDITY TOO LOW`. Internal strings such as `PRIMARY NOT ACTIONABLE NOW`, `CONFIRMED ENTRY GATE FALSE`, and duplicate `R:R NOT ACTIONABLE` no longer spill into the customer-facing Recommended Action.
- **Next action is a separate short line.** Examples: `WAIT FOR PULLBACK`, `WAIT FOR BETTER R:R`, `WAIT FOR MISSING CONFIRMATION`, or `REFRESH / RECHECK LIVE PRICE`.
- **Primary-reason priority is more useful.** A genuine stale-session/data-integrity failure still outranks everything. But when the session is current and the quote is merely delayed, a clearly out-of-zone price can be the front reason while quote freshness remains a secondary blocker inside the `i` panel. Example: 1780.HK can show `WAIT — PRICE ABOVE ENTRY ZONE` instead of a long mixed reason.
- **Exact blocker drilldown:** the info panel now exposes the actual numbers for each failed execution check: current price, executable entry zone, distance to zone, live R:R to T1/T2 and required floors, quote age/freshness limit, quote status/source/timestamp, session freshness/data quality, liquidity score/median turnover/minimum turnover, timing reliability, chase/extension state, and missing entry confirmations.
- **No duplicate blocker prose.** The raw `FinalTradeReason` remains in Excel/audit for traceability, but the front UI and `RecommendedAction` use the compact primary reason only. Secondary blockers are individual parameter rows in the info drilldown.
- **Live quote age is now exported.** Scanner/Analyze add `PriceObservationAgeMinutes`, `PriceFreshLimitMinutes`, `QuoteStatus`, `PriceObservationSource`, and `PriceObservationTimestamp` so `LIVE DATA NOT FRESH` can be explained numerically instead of vaguely.
- **Stale-score info is richer.** `CURRENT SCORE N/A • STALE DATA` now also shows quote age, freshness limit, quote status, provider/source and timestamp when available.
- All V6.4.1.9 Research Score/Data Gate separation, current Trigger→T1 integrity, V6.4.1.8 live-plan alignment, Pre-Move confidence semantics, session-safe timing reliability, nested parameter `i` help and mobile-safe dialogs are retained.
- **No scoring weights, Optimizer/OOS weights, entry thresholds, R:R floors, or liquidity thresholds changed in this release.** This is a decision-clarity/audit upgrade.

---

# AI Stock Hunter — V6.4.1.9 Score Semantics + Data Gate Separation + Current Progress Integrity

## V6.4.1.9 — Research Score stays truthful; stale data blocks execution instead of zeroing the score

- **Stale/data quality no longer subtracts 20 points from Overall / Research Score.** Technical score is now explicitly the technical composite after risk (and invalidation if applicable). Example: Core 15.6 minus Risk 9.0 displays **Research Score 6.6/100**, not 0/100.
- **Data Quality is a separate hard execution/rank gate.** A stale or unverified open session displays **CURRENT SCORE N/A • STALE DATA** and remains BLOCKED until current data is verified. It cannot become ranked/actionable merely because the research score is non-zero.
- **Live-data confidence no longer numerically depresses the technical score.** Its prior penalty remains visible as confidence/audit context only; eligible fresh-session names already have zero live-data penalty.
- Adds audit fields: `ResearchCoreScore`, `RiskAdjustedResearchScore`, `CurrentScoreAvailable`, `CurrentScoreStatus`, `LegacyDataPenaltyWouldHaveBeen`, and `DecisionRankInvalidationPenalty`.
- Scanner and Analyze use **FINAL SCORE** only for currently rank-eligible names; blocked/unverified names use **RESEARCH SCORE**. Stale sessions get a compact `CURRENT SCORE N/A • STALE DATA` line with a blue info drilldown showing Core, Risk, Research Score, Data Quality, Session Freshness, and execution status.
- **Current Trigger→T1 progress integrity fixed.** A previous-session trigger or missing current Target 1 can no longer produce a current progress percentage. The current field becomes N/A / PREVIOUS SESSION, and Continuation no longer consumes historical progress as if it belonged to today's executable plan.
- All V6.4.1.8 execution-plan/path alignment, Pre-Move clarity, nested parameter help, timing-reliability, and mobile-safe info windows are retained.

---

# AI Stock Hunter — V6.4.1.8

## Execution-Plan Consistency + Entry Path + Pre-Move Clarity

- **`ENTRY NOW` and the displayed plan are now one execution truth.** The current quote must be inside the exact entry zone shown to the user. A stock can no longer say `ENTER NOW` while the visible plan still shows an old Primary zone below the market (for example, price 298 while Entry remains 295–296).
- Added an explicit **Entry Path**: `PRIMARY`, `ACCELERATION`, `CONTINUATION`, or `RETEST`. Scanner and Analyze show the path beside the live plan, with a highlighted blue `i` drill-down.
- **Acceleration / Continuation entries receive a current-price execution plan.** The engine builds a compact zone around the current quote, keeps the validated structural stop/targets, and recomputes live R:R from the current price. If geometry or R:R no longer passes, the headline is demoted to `WAIT — LIVE PLAN NOT ALIGNED`; it cannot remain `ENTRY NOW`.
- **Primary and Retest paths use their own executable zones.** The same plan is used by the headline decision, `Price Actionable`, `R:R Actionable`, Scanner live-plan strip, Analyze live-plan grid, and the price chart.
- The chart now draws **`Live entry • <PATH>`** for an executable entry; the old setup geometry is labelled **`Primary setup zone`** when it is only research/context.
- `ENTRY PATH • LIVE PLAN` drill-down exposes: path, executable zone, current price, live stop, T1, T2, live R:R to T1/T2, and Entry confidence. Every row retains its nested `i` explanation.
- **Weak Pre-Move is now explicitly contextual, not contradictory.** During a valid `ENTRY NOW`, a low Pre-Move score displays `EARLY SETUP WEAK • NOT A CURRENT BLOCK`. Pre-Move can lower the displayed confidence tier, but it never independently creates or cancels an entry signal.
- Fixed the remaining tiny-move timing edge case: a raw `Move Consumed >=100%` can produce `TOO LATE` only when the same-session Move Consumed measurement is **reliable**. This preserves the V6.4.1.6 small-denominator protection.
- All responsive/nested info panels, neutral Entry Score breakdown, session-safe timing logic, Timing Reliability guard, blocker `i`, and the V6.4.1.7 Analyze render hotfix are retained.
- No Optimizer/OOS model-weight changes. This release tightens execution consistency and explanation; it does not boost prediction scores or loosen safety gates.
- Version/build IDs synchronized to `6.4.1.8`.

---

# AI Stock Hunter — V6.4.1.7

## Analyze render hotfix

- Fixes the Analyze `NameError: name '_num6395' is not defined` introduced in V6.4.1.6.
- Root cause: `_num6395` is intentionally local to the Scanner renderer, but two Analyze Live R:R status checks referenced it outside that scope.
- Analyze now uses the existing module-level numeric helper `_num_v6394`, so cached/saved Analyze results can render normally again.
- No scoring, ranking, Entry, Timing Reliability, Move Consumed, liquidity, R:R, or decision logic changed.
- All V6.4.1.6 timing-reliability and blocker-info improvements are retained.

---

# AI Stock Hunter — V6.4.1.6 Timing Reliability + Blocked Explanation

## V6.4.1.6 — tiny-move timing guard + explicit WHY BLOCKED info

- **Move Consumed no longer hard-blocks on a tiny denominator.** The 80% timing veto now requires a same-session trigger, at least **+0.75% current-session move**, at least **0.30 ATR** of session progress (or a stricter +1.50% absolute fallback when ATR is unavailable), at least **+0.50% move before trigger**, and price not materially retraced below the causal trigger.
- A measured 80–100% ratio that fails those reliability checks is labeled **LOW RELIABILITY** and cannot by itself create `TOO LATE`, `DO NOT ENTER`, or an execution hard block.
- This directly fixes cases such as TTWO showing `100% of current-session move used before trigger` while the entire session move was only about +0.34%.
- New audit fields: `TimingConsumedReliable`, `TimingConsumedReliability`, `TimingConsumedHardBlockReason`, plus the individual reliability checks from the engine.
- **Blocked badge now has a highlighted blue `i` icon** in Scanner and Analyze. Tapping it opens a compact `WHY BLOCKED` parameter panel showing the exact blocker and the relevant measured values/thresholds. Every parameter inside that panel keeps its own nested `i` explanation.
- `TIMING • PARAMETERS` now shows `Timing Reliability` and the `80%` hard limit explicitly. A low-reliability consumed ratio is amber/watch, not red/fail.
- Cached older snapshots are presentation-sanitized with the same reliability test so a stale tiny-move 100% ratio does not remain a fake timing hard block after deploy.
- No Optimizer/OOS weight changes. Liquidity, Entry-score weights, R:R geometry, Pre-Move and Pre-Breakout scoring remain unchanged.

---

# AI Stock Hunter V6.4.1.5 Premium

## V6.4.1.5 — Neutral Entry Score + One-Tap Score Breakdown (2026-10-07)

- `ENTRY • PARAMETERS` now treats `Entry Score` as an **informational strength score**, not a green PASS gate. The first-level row is neutral/blue-gray even when the score is high.
- The first panel stays compact: it shows only `Entry Score 78/100` plus the highlighted `i`. No formula wall is shown by default.
- Tapping the `i` on `Entry Score` opens the second-level breakdown with the exact score construction: Daily strength 42%, 15m/1H timing 24%, Signal freshness 17%, Volume/Flow 17%, then Exit-pressure deduction, Extension-risk deduction, and the bounded Acceleration bonus.
- The breakdown shows both each component score and its weighted point contribution, plus the final score, so `6/6 PASS` can no longer be mistaken for `100/100 strength`.
- Added exact audit fields from the engine for every Entry-score component/adjustment. New scans and Analyze runs therefore explain the score from the same production numbers that created it; older cached snapshots degrade gracefully until refreshed.
- The positive-count headline now counts only true positive/pass rows, so `Entry Score` no longer inflates the green-positive count.
- No entry formula, thresholds, gates, scoring weights, liquidity rules, timing rules, rank logic, or Optimizer/OOS weights changed. This release is transparency/UI only.
- Version/build IDs synchronized to `6.4.1.5`.

---

# AI Stock Hunter V6.4.1.4 Premium

## V6.4.1.4 — Session-Safe Move Consumed + Nested Parameter Help (2026-10-07)

- Fixed the cross-session `MoveConsumedBeforeTriggerPct` bug that could compare a prior-session trigger with the next session's tiny PRE-MARKET move and create misleading values such as `217%`.
- The 80% timing hard block now applies only when trigger anchor and move denominator belong to the **same exchange session**. A previous-session trigger is shown as `N/A • PREVIOUS SESSION` and cannot by itself create `TOO LATE / MOVE-CONSUMED BLOCK`.
- The engine now records `PREVIOUS_SESSION_TRIGGER` in TimingDataSource and keeps the previous trigger only as context until a new current-session causal trigger appears.
- Added a presentation guard so cached scans from older builds cannot continue to show a stale cross-session 100%+ consumed value as a current hard blocker.
- `Move Consumed` display is bounded to 0–100%; raw audit values remain available in exported data when applicable.
- Made every main `i` control visually prominent with an electric-blue/cyan border, fill and glow.
- Added a **second-level `i` beside every parameter** inside USER SIGNAL, OPPORTUNITY, ENTRY, TIMING, LIQUIDITY, PRE-MOVE and PRE-BREAKOUT ACCEL detail panels.
- Tapping a parameter row expands a concise explanation of what it measures, its current value, and why the current state is positive / negative / watch / informational.
- Nested explanations expand inline inside the already mobile-safe modal, so they do not overflow the viewport.
- Scanner and Analyze share the same renderer and semantics. No Opportunity weights, Optimizer/OOS weights, liquidity thresholds, or unrelated production gates were changed.
- Version/build IDs synchronized to `6.4.1.4`.

---

# AI Stock Hunter V6.4.1.3 Premium

## V6.4.1.3 — Responsive Parameter Info / Mobile-Safe Audit Panels (2026-10-07)

- Rebuilt every Premium ticket `i` disclosure as a **viewport-safe responsive modal**. It is centered inside the visible screen, width-limited to the viewport, vertically scrollable, and no longer expands outside the mobile screen.
- Added an `i` disclosure to **Opportunity** and **Entry**, so every field in the six-card Premium KPI grid now has the same drill-down behavior. `USER SIGNAL` keeps its own parameter disclosure as well.
- Replaced long explanatory paragraphs with **parameter-first audit rows**. Each popup shows the underlying values/gates instead of prose-heavy descriptions.
- Positive/passed parameters are **green**, negative/failed parameters are **red**, intermediate/watch states are amber, and informational/not-applicable values are muted.
- Added compact positive/negative/watch counts at the top of every popup for immediate visual diagnosis.
- `OPPORTUNITY` now exposes its actual production composition: Move 19%, Explosive 24%, Entry 19%, Acceleration 12%, Hourly 10%, Reliability 16%, plus Exit Pressure penalty.
- `ENTRY` shows the six production gates plus Price Actionable, Execution Gate, Trade Plan and R:R Actionable, making cases such as `6/6` but `WAIT RETEST` auditable.
- `TIMING` now shows state, entry confirmation, price context, move stage, move consumed, chase risk, extension guard, retest state, market phase and live-data confidence.
- `LIQUIDITY`, `PRE-MOVE`, and `PRE-BREAKOUT ACCEL` now expose their key production parameters and gate states rather than generic descriptions.
- The open info control becomes a visible close `×`, with a dark backdrop and internal scrolling, preventing the user from getting stuck behind an oversized popup.
- Shared renderer remains identical in Scanner and Analyze. No scoring weights, entry thresholds, ranking logic, liquidity rules, chase rules, Pre-Move logic, Pre-Breakout logic, or Optimizer/OOS weights changed.
- Version/build IDs synchronized to `6.4.1.3`.

---

# AI Stock Hunter V6.4.1.2 Premium

## V6.4.1.2 — Timing Entry Confirmation / Gate Breakdown (2026-10-07)

- TIMING now shows a persistent `ENTRY CONFIRMATION N/6` line directly on the front ticket.
- The TIMING `i` disclosure now lists the six production entry gates, split into **Passed** and **Missing**, so a state such as `4/6` is immediately auditable.
- The six displayed gates are Daily Setup, Fresh Signal, Hourly Timing, Volume / Flow, No Chase, and Market Regime.
- The same shared ticket renderer is used by both Scanner and Analyze, so the confirmation count and help text are identical in both views.
- This is presentation/audit only: no scoring weights, entry thresholds, gates, liquidity rules, chase logic, ranking, Pre-Move, or Pre-Breakout logic changed.
- Version/build IDs synchronized to `6.4.1.2`.

---

# AI Stock Hunter V6.4.1.1 Premium

## V6.4.1.1 — Timing Info Clarity / Unified Scanner + Analyze (2026-10-07)

- Added a compact `i` help control to the **TIMING** KPI in the shared Premium ticket used by both Scanner and Analyze.
- The Timing help explains three things only: **current timing state**, **why it is in that state**, and **what must happen next** before timing becomes actionable.
- Clarifies that Timing answers whether the entry trigger is ready **now**; it is not the overall attractiveness/rank of the stock.
- No scoring weights, entry gates, liquidity thresholds, chase rules, ranking logic, Pre-Move logic, or Pre-Breakout Acceleration logic changed.
- Version synchronized: `app.py` and `quant_engine.py` = **6.4.1.1**.

---

# AI Stock Hunter V6.4.1.0 Premium

## V6.4.1.0 — Luxury Clean Ticket / Dual Pre-Move + Pre-Breakout / Unified Scanner + Analyze (2026-10-07)

Build `V6410-LUXURY-CLEAN-TICKET-DUAL-PREMOVE-PREBREAKOUT-20261007-A`.

- Rebuilt the Premium front ticket around one customer question: **what should I do now?** `USER SIGNAL` remains the single action instruction.
- Lifecycle state such as `ARMED` is no longer a separate competing block; when useful it appears as a compact chip inside the same `USER SIGNAL` card.
- `EXECUTION CHECK` is hidden from the front. A mobile-friendly `i` disclosure inside `USER SIGNAL` reveals the execution reason, entry context, and last-live state on demand.
- Removed the duplicate front `PREMIUM RANK` block. The ticket starts with one large, gold, single-line `OVERALL RANK #N`.
- `ACTION RANK` appears only when a real numeric Action Rank exists. No more `ACTION RANK — / NOT ACTIONABLE NOW` clutter.
- Scanner and Analyze now use the same rank/score header hierarchy: **Overall Rank + Final Score + ticker**. Analyze reuses the latest Scanner rank when available and never invents a one-stock rank.
- Added both early-move measures to the front grid as separate fields: **PRE-MOVE** (broader accumulation/radar pattern) and **PRE-BREAKOUT ACCEL** (technical acceleration before breakout). They are not interchangeable.
- `PRE-MOVE` shows its 0–100 pattern score plus real radar rank when eligible; blocked/not-ranked reasons are shown only inside that field instead of a separate banner.
- `LIQUIDITY` remains front-and-center with level, score, median turnover, and hard-gate state.
- Added small clickable `i` disclosures to `USER SIGNAL`, `LIQUIDITY`, `PRE-MOVE`, and `PRE-BREAKOUT ACCEL` for concise explanations without permanent visual clutter.
- Front KPI grid is now a symmetric 3×2 desktop / 2-column mobile layout with consistent height, padding, wrapping, and no clipped field text. Evidence remains available in Details/Excel rather than competing for front space.
- Increased visual separation between tickets, added a subtle gold divider, calmer shadows, and a more premium dark/gold hierarchy.
- The separate Top Pre-Move queue now still uses the stock's `OVERALL RANK` as the ticket title; its dedicated `PRE-MOVE` field shows the Pre-Move rank. This removes competing rank systems from the title.
- No production weights, Entry gates, liquidity thresholds, chase logic, or optimizer weights changed in this release. This is a presentation/clarity release on top of V6.4.0.9.
- Version synchronized: `app.py` and `quant_engine.py` = **6.4.1.0**.

---

## Historical release notes — V6.4.0.9

## V6.4.0.9 — Clear User Signal / Unified Scanner + Analyze / Pre-Move Rank Integrity (2026-10-07)

Build `V6409-CLEAR-USER-SIGNAL-UNIFIED-TICKET-PREMOVE-RANK-20261007-A`.

- Added one customer-facing **USER SIGNAL** to every Premium ticket: `ENTER NOW`, `CLOSE WATCH`, `WATCH`, `WAIT`, or `DO NOT ENTER`.
- `ENTER NOW` is still generated only by the existing final execution gate; the new layer never relaxes risk/liquidity/timing rules.
- `ARMED` and qualified `LAST SESSION ENTRY` map to `CLOSE WATCH`: close monitoring, not an entry instruction.
- High-priority 1196-style early breakouts map to `CLOSE WATCH` while their missing confirmation remains explicit.
- Hard liquidity/chase/invalidated states override everything and map to `DO NOT ENTER`.
- Scanner and Analyze use the same shared Premium renderer for USER SIGNAL, STATUS, execution check, Liquidity, and Pre-Breakout Acceleration.
- Scanner filtering adds `CLOSE WATCH` and `WATCH` views so the user can immediately isolate near-entry candidates versus earlier setups.
- Fixed Pre-Move contradiction: a card can no longer show `PRE-MOVE RANK #N` together with `NOT RANKED`. Rank comes only from `PreMoveRadarRank`; actionability is shown separately. The numeric 0–100 value is labelled `PATTERN SCORE` so it is not confused with rank or live entry timing.
- Missing Action Rank is now self-explanatory: `ACTION RANK — • NOT ACTIONABLE NOW • <USER SIGNAL>`.
- Analyze reuses the latest Scanner Pre-Move rank/eligibility context when available, just like Overall/Action Rank.
- Fixed entry-zone geometry wording: if price is numerically inside EntryLow–EntryHigh, the UI says `PRICE IN ENTRY ZONE` even when another gate blocks execution.
- Front KPI label clarified to **Pre-Breakout Accel** so it cannot be confused with the separate Pre-Move Radar score/rank.
- Liquidity + median turnover remain front-and-center and identical in Scanner and Analyze.
- Last-Live state memory and Mover Miss Learning from V6.4.0.8 are retained unchanged.
- Version synchronized: `app.py` and `quant_engine.py` = **6.4.0.9**.

---

## V6.4.0.8 — Pre-Breakout + Liquidity Front / Last-Live Memory / Mover Miss Learning (2026-10-07)

Build `V6408-PREBREAKOUT-LIQUIDITY-MISS-LEARNING-STATE-PERSISTENCE-20261007-A`.

This release is based on an audit of the latest V6.4.0.7 scan (`2026-10-07 10:41`) before changing production code. The Premium rank logic was clean in that scan: no duplicate Overall/Action ranks, no hard-blocked name with a Premium rank, and no false `ENTRY NOW`. The scan also showed why liquidity context needs to be visible: PBT ranked Overall #1 while carrying a LOW liquidity label (still above the hard turnover floor), while 2722.HK ranked #4 with MEDIUM liquidity and Pre-Breakout Acceleration 92.

- **Pre-Breakout Acceleration is now front-and-center** in the shared Premium ticket used by both Scanner and Analyze. It shows the score (`0–100`) and stage (`CONFIRMED`, `ARMED`, `EARLY WATCH`, etc.) without opening Details.
- **Liquidity is now front-and-center** in the same shared ticket. It shows `HIGH / MEDIUM / LOW + score`, median 60-day daily turnover, currency, and `PASS / BLOCKED` so a high-ranked low-liquidity name cannot be mistaken for a deep-liquid one.
- **Scanner and Analyze use the same presentation path** for these KPIs; no separate Analyze-only wording or hidden metric.
- **Last Live Status memory** stores the last trustworthy OPEN-session lifecycle state. A later closed/pre-open scan can display context such as `LAST LIVE: ARMED • 12h ago` while the current Final Trade Action remains WAIT. This is context only and can never create `ENTRY NOW`.
- **Mover Miss Learning Audit** automatically audits MEDIUM/HIGH-liquidity stocks that moved at least **+8% in 3D or 5D**. It classifies `CAUGHT EARLY`, `GATE REVIEW`, `PARTIAL / LATE SIGNAL`, `LATE SIGNAL`, `TOO-LATE CORRECT • EARLY MISS`, or `NO EARLY SIGNAL / COVERAGE MISS`.
- The mover audit records the **actual historical indicators at the earliest qualifying signal snapshot**: Entry Score, Hourly, RVOL, Money Flow, Institutional Flow, Pre-Breakout score/stage, Liquidity score/label, signal price, lead time and move-capture %. This is strictly historical information from our own snapshots; no look-ahead is used.
- Scanner Excel export adds a dedicated **`Mover Miss Audit`** sheet and exposes separate `RecentRun3DPct`, `RecentRun5DPct`, and `RecentRun10DPct` fields for cleaner research.
- **Build integrity fixed:** the stale V6.4.0.6 `APP_BUILD_ID` that remained inside V6.4.0.7 is replaced and synchronized with the engine build ID.
- Existing V6.4.0.7 Overall Rank / Action Rank / BLOCKED-with-no-rank behavior and the V6.4.0.5 1196 Early Breakout High-Priority Watch are preserved.
- **No production weights, Entry thresholds, liquidity thresholds, optimizer weights, or Final Trade Action gates are loosened in this release.** The new Miss Learning layer is research/audit only.
- Version synchronized: `app.py` and `quant_engine.py` = **6.4.0.8**.

---

# AI Stock Hunter V6.4.0.7 Premium

## V6.4.0.7 — Premium Overall Rank + Action Rank + No Rank for Hard-Blocked Names (2026-10-06)

Build `V6407-PREMIUM-OVERALL-ACTION-RANK-20261006-A`.

- **Hard-blocked names no longer receive a normal user-facing Rank.** Low-liquidity, execution-hard-blocked, or `DO NOT ENTER` rows keep their research score and audit rank in Excel, but the Premium ticket shows `BLOCKED • <reason>` and `NO PREMIUM RANK`.
- **OVERALL RANK** is assigned only among names that pass the Premium trade hard gates, ordered by the same visible `FinalScore`. A 30-point eligible stock can no longer visually outrank a 60-point eligible stock because of Stage.
- **ACTION RANK** is a separate rank among current `ENTRY NOW` candidates only. `ARMED`, `BUILDING SETUP`, `RETEST`, `LAST SESSION ENTRY`, and closed-market WAIT names have `ACTION RANK —`.
- Scanner cards now show `OVERALL RANK #...` in the headline and an explicit `ACTION RANK #...` / `ACTION RANK —` line. Hard-blocked cards label the numeric value as `RESEARCH SCORE`, not Final Score.
- The shared Premium ticket (Scanner + Analyze) displays rank context next to the existing visible `STATUS` and separate `FINAL TRADE ACTION`.
- Analyze never invents a one-stock `#1`: it reuses Overall/Action ranks from the last completed Scanner snapshot for that ticker when available; otherwise rank is omitted.
- Top Decisions excludes hard-blocked rows whenever at least one Premium-eligible candidate exists.
- Existing full-scan research/audit ranking fields are retained for backward compatibility. No model weights, indicator thresholds, entry gates, liquidity thresholds, or optimizer weights changed.
- Version synchronized: `app.py` and `quant_engine.py` = **6.4.0.7**.

---

## V6.4.0.6 — Final-Score Rank + Visible Ticket Status (2026-10-06)

- **Rank now follows one visible numeric score.** `FinalScore = CurrentRankScore` is the exact Premium ranking number; Stage no longer acts as a hidden primary sort tier.
- **Hard gates still matter first.** Liquidity/execution hard-blocked names are placed below execution-eligible names, even when their research score is high.
- **No more 30-before-60 anomaly.** Among execution-eligible names, the higher Final Score ranks first; ties use DecisionRankScore, Setup and Entry timing.
- **Top ticket headline changed to `FINAL SCORE`.** The number beside `RANK #` is now the score actually used to order that queue. `Opportunity` remains a supporting KPI inside the ticket.
- **Visible STATUS on every Scanner + Analyze ticket.** The shared Premium ticket now explicitly shows lifecycle state such as `BUILDING SETUP`, `ARMED`, `ARMED • BLOCKED`, `LAST SESSION ENTRY`, `RETEST`, `WAIT`, or `ENTRY NOW`, separately from the executable `FINAL TRADE ACTION`.
- **High-Priority Breakout Watch remains visible as status context** and still cannot create `ENTRY NOW` by itself.
- `ActionQueueRank` is now one score-consistent eligible queue. The prior per-stage queue value is retained as `LegacyStageQueueRank` for audit.
- Version synchronized: `app.py` and `quant_engine.py` = **6.4.0.6**.

---

## V6.4.0.5 — 1196 Early-Breakout High-Priority Watch (2026-10-06)

Build `V6405-EARLY-BREAKOUT-HIGH-PRIORITY-WATCH-20261006-A`.

This release converts the retrospective 1196.HK lesson into a production WATCH escalation without weakening the execution gate.

- Adds **HIGH PRIORITY WATCH — EARLY BREAKOUT** for the narrow case where the **raw Daily Setup is the only missing classic entry confirmation** while Fresh Signal, 15m/1H timing, Volume/Flow, No-Chase and Market Regime already pass.
- Requires exceptional short-term evidence: **Hourly >=75**, **RVOL >=2.50x**, broad 15m/1H volume acceleration, constructive multi-timeframe momentum, positive flow, valid liquidity/data/plan/extension guards and an **EARLY** trigger/progress context. A recent move already >=12% is excluded so the rule does not become a chase detector.
- The new state is **watch-only**. It never sets `ConfirmedEntryGateOK`, `ActionableNow`, or `FinalTradeDecision=ENTRY NOW`. The Premium front explicitly says **NO ENTRY NOW** and identifies **Daily setup pending** as the remaining confirmation.
- High-priority early-breakout candidates sort ahead of ordinary WATCH/RESEARCH names inside the same watch bucket, while ENTRY NOW and ARMED remain higher execution classes. **OverallScore weights are unchanged.**
- Scanner + Analyze export `HighPriorityBreakoutWatch`, `HighPriorityBreakoutScore`, `HighPriorityBreakoutReason`, and `HighPriorityBreakoutMissingConfirmation`. Feedback snapshots persist the same flag/score/reason so 1D/3D/5D outcomes can measure whether this 1196-style escalation adds lift.
- `WHY YES / WHY NOT` shows the exceptional Hourly/RVOL/Volume/Momentum/Flow alignment under WHY YES while keeping the missing Daily Setup under WHY NOT.

---

# AI Stock Hunter V6.4.0.4 Premium

## V6.4.0.4 — Top-5 Local Rank Integrity (2026-10-06)

Build `V6404-TOP5-LOCAL-RANK-20261006-A`.

- **Top Decisions cards now always display local Top-5 rank `RANK #1` through `RANK #5`.** A card that is the 1st item in the visible Top Decisions queue can no longer show a full-scan number such as `RANK #23`.
- The full-scan/global rank is preserved for audit inside the collapsed `WHY YES / WHY NOT • DETAILS` section and in exports; it no longer competes with the user-facing Top-5 position.
- Pre-Move keeps its own independent `PRE-MOVE #1` through `PRE-MOVE #5` ranking.
- This is a display/rank-semantics correction only. **No scoring weights, thresholds, entry gates, trade decisions, price logic, or optimizer logic changed.**

---

# AI Stock Hunter V6.4.0.3 Premium

## V6.4.0.3 — Decision Clarity + Snapshot Price Integrity (2026-10-06)

Build `V6403-DECISION-CLARITY-SNAPSHOT-PRICE-20261006-A`.

This is a Premium decision-clarity and display-integrity release over V6.4.0.2. Core scoring weights, indicator thresholds, Optimizer weights and execution gates are unchanged.

- **Final Trade Action uses plain language.** A failed confirmed-entry gate now shows `WAIT — SETUP NOT CONFIRMED` and, when available, the exact missing confirmations such as `Daily setup + Volume/flow` instead of the internal phrase `ENTRY GATES INCOMPLETE`.
- **Timing on the front is action-oriented.** The card no longer shows a green `EARLY` headline when execution is blocked. It shows `READY NOW`, `WAIT RETEST`, `WAIT PRICE`, `WAIT DATA`, `RECHECK OPEN`, `NOT READY`, or `BLOCKED`. The technical `Move stage EARLY/MID/LATE` remains only as secondary context.
- **`NO DATA` is no longer used when timing is simply not required yet.** Before a causal trigger, Details says `NO TRIGGER YET`; this is not presented as a data failure.
- **Opportunity means Opportunity.** Scanner and Analyze front cards now bind `OPPORTUNITY` to `OpportunityScore`, not `DecisionRankScore/OverallScore`. Ranking logic itself is unchanged.
- **Scanner price is frozen to the completed scan snapshot.** The UI no longer refreshes only the displayed price while keeping older Entry/Chase/R:R/Final Action values. This removes the price/decision mismatch observed after the V6.4.0.2 scan.
- **Price direction is visible beside price.** Scanner and Analyze show `▲ +change (+%)` in green or `▼ -change (-%)` in red, using the session-correct reference. Scanner exports add `ScanReferencePrice`, `ScanChangeAbs`, `ScanChangePct`, `ScanChangeReference`, `PriceObservationSource`, and `PriceObservationTimestamp`; Analyze exports add equivalent `Observed*` audit fields.
- The large `US OPEN REVALIDATION REQUIRED` front-page warning is replaced by a compact calm one-line status directly below `LAST COMPLETED SCAN`.
- Scanner and Analyze retain one unified `WHY YES / WHY NOT • DETAILS` section. Evidence remains confidence-only.

---

# AI Stock Hunter V6.4.0.2 Premium

## V6.4.0.2 — Unified WHY + Clear Final Trade Action (2026-10-06)

Build `V6402-UNIFIED-WHY-CLEAR-FINAL-ACTION-20261006-A`.

This is a presentation/UX clarification release over V6.4.0.1. Core scoring, indicator thresholds, Optimizer weights and execution gates are unchanged.

- **Final Decision is renamed visually to `FINAL TRADE ACTION`** so the card says what the user should do now, not merely a model state.
- Price-context waits are now explicit. Instead of `WAIT — PRICE NOT IN ENTRY CONTEXT`, the card states, when applicable, **`WAIT — PULLBACK TO ENTRY ZONE`** and shows the current price, the entry zone and the approximate % above the zone. A 6/6 technical setup can therefore clearly say `SETUP CONFIRMED • NO ENTRY NOW` until price returns to an executable area.
- **Scanner diagnostics are fully consolidated into `WHY YES / WHY NOT`.** The old separate `TECHNICAL DETAILS` paragraph block is removed from the Scanner card. The raw/research audit remains in Excel.
- `WHY YES / WHY NOT` now includes the execution-relevant diagnostic in one place: price/entry-zone context, Entry score/gates, why-now, timing/chase, condensed Daily/15m/1H momentum, Inflow/Outflow/Net flow, RVOL, R:R, data/session blockers and meaningful Pre-Move/original-move context.
- **Analyze no longer renders the WHY YES / WHY NOT panels twice.** The second duplicated block and the repeated raw-stage/flow/RVOL/exit captions are removed. Remaining deep content is explicitly labelled `SUPPORTING / RESEARCH DETAILS`.
- Evidence remains confidence-only and is not turned into a WHY NOT execution blocker.
- Scanner and Analyze continue to use the same Premium ticket hierarchy and `Developed by Alon Azoulay` signature.

---

# AI Stock Hunter V6.4.0.1 Premium

## V6.4.0.1 — Premium UI Polish / Unified Scanner + Analyze (2026-10-06)

Build `V6401-PREMIUM-UI-POLISH-20261006-A`.

This is a **presentation/UX polish release over V6.4.0**. Core scoring, indicator thresholds, Optimizer weights, Evidence execution influence, and trade-gate logic are unchanged.

- **Scanner and Analyze now use the same Premium ticket language and hierarchy.** The front stays decision-first: ticker/rank, price/session context, Final Decision, and the five KPIs `Opportunity`, `Entry`, `Timing`, `Liquidity`, `Evidence`.
- `Why this decision` and `Advanced diagnostics` are merged into one closed **`WHY YES / WHY NOT • DETAILS`** section. Positive confirmations and blockers are shown first in a short two-panel format; technical/research detail remains available underneath.
- **Verbose Analyze text is removed from the front.** Live-actionability prose, causal-trigger audit, trigger-efficiency text, feedback-event text, backtest/sample statistics, research validation, dynamic calibration, and the long Precision Entry/Risk Plan now live inside Details by default.
- For a true `ENTRY NOW`, Analyze may show a compact plan strip with `Entry / Stop / T1 / T2 / R:R` on the front; non-actionable/retest plans stay inside Details.
- **Primary blocker wording is explicit.** A high Chase/Extension block now renders `DO NOT ENTER — CHASE RISK HIGH` (for example `Chase 70/100 • wait for retest`) instead of the vague `TIMING BLOCK`. Liquidity, timing/move-consumed, data, R:R and invalidation blockers receive similarly specific wording.
- **Final Decision remains the only executable headline.** Raw/technical `ENTRY NOW` can never appear as the Premium headline if execution is not currently allowed.
- Evidence remains **confidence-only** and is intentionally excluded from `WHY NOT`; it does not create/cancel `ARMED`, `CONFIRMED ENTRY`, `ENTRY NOW`, or Global Rank.
- Mobile KPI layout is balanced as **3 cards + 2 cards**, avoiding a single orphan Evidence card.
- `Developed by Alon Azoulay` remains as the product signature, with a more restrained Premium treatment.

---

# AI Stock Hunter V6.4.0 Premium

## V6.4.0 — Premium Decision Cockpit (2026-10-06)

Build `V6400-PREMIUM-DECISION-UX-20261006-A`.

V6.4.0 is the first Premium UI release. It is intentionally a **presentation / decision-hierarchy upgrade over the stabilized V6.3.9.84 execution engine**; indicator weights, Optimizer weights, Evidence execution influence, and core entry thresholds are unchanged.

- **Final Decision is the only executable headline.** The Premium front card can show `ENTRY NOW` only when `FinalTradeDecision == ENTRY NOW`. A raw/technical `ENTRY NOW` while the market is closed, data is unverified, price/R:R is not actionable, or another execution dependency is missing is shown on the front as a contextual `WAIT ...` state instead.
- Raw `DecisionBoardStage` / technical stage is still preserved for audit, but it is moved to **Advanced diagnostics** and clearly labelled diagnostic-only.
- **5-second Premium ticket:** the front of each Scanner/Analyze card is reduced to five decision KPIs: `Opportunity`, `Entry`, `Timing`, `Liquidity`, and `Evidence`. Price, market phase, Live Data Confidence, window and exit status remain in one compact context line.
- Full RVOL, Flow, Momentum, Acceleration, Continuation, trigger-memory, chase, R:R and historical metrics remain available in `Why this decision`, `Advanced diagnostics • all metrics`, and Excel. Nothing is deleted from the model.
- Evidence remains **confidence-only**. It does not create, cancel, demote or block `ARMED`, `CONFIRMED ENTRY`, `ENTRY NOW`, `ActionableNow`, or Global Rank.
- Normal WAIT / closed-market / retest states use calm premium amber/slate styling. Red remains reserved for real application/data failures rather than ordinary trade guidance.
- Adds Excel audit fields `PremiumHeadlineDecision`, `PremiumHeadlineExecutable`, and `PremiumHeadlineSource` so the UI hierarchy can be checked directly from scan exports.
- Scanner and Analyze now share the same Premium decision-first visual language.

---

# AI Stock Hunter V6.3.9.84

## V6.3.9.84 — Premium Foundation / Clean Execution Separation (2026-10-06)

Build `V63984-PREMIUM-FOUNDATION-CLEAN-EXECUTION-20261006-A`.

This is the final stabilization build before V6.4.0 Premium.

- **Evidence is now strictly confidence-only.** It cannot create, cancel, demote, or block `ARMED`, `CONFIRMED ENTRY`, `ENTRY NOW`, `ActionableNow`, or the user-facing Global Rank. Even negative historical OOS Evidence is displayed as a confidence warning only.
- **Execution gates remain execution gates:** liquidity, timing/move-consumed, live/session freshness, price context, R:R, plan validity, extension/chase and exit pressure can still block a trade.
- Adds **Live Data Confidence** (`HIGH / MEDIUM / LOW / CONTEXT ONLY`) with a reason and a small **ranking-context penalty**. This does not change the technical Overall Score or the execution state; it only prevents an otherwise similar prior-session/PM-unverified setup from outranking a setup with verified live data.
- Fixes the confusing `WAIT` + `All actual trade-trigger gates aligned` combination. When technical gates are aligned but execution context is not, the app now says exactly what is missing, e.g. `pre-market live data unavailable`, `fresh live price required`, `price outside entry context`, or `R:R not actionable`.
- Global/Trade Priority rank is now **execution-first and Evidence-independent**. Q/E/EV historical/research ranks remain available separately for diagnostics.
- Keeps all V6.3.9.83 calm decision colors and ticket wrapping.
- **No Optimizer weight changes and no indicator-threshold changes.**

---

# AI Stock Hunter V6.3.9.83

## V6.3.9.83 — Calm Decision UX (2026-10-06)

Build `V63983-CALM-DECISION-UX-20261006-A`.

- Removes the remaining red styling from **normal non-entry decisions** in Scanner and Analyze. `TOO LATE`, `CLOSED`, and `DO NOT ENTER NOW` are now shown in a calm amber/slate treatment.
- The large red Streamlit error box for `DO NOT ENTER` is replaced by one compact calm decision banner.
- Extension/chase blocks use the user-facing wording **WAIT FOR RETEST** in the main banner, while the detailed diagnostics and Excel audit keep the exact technical blocker (`DO NOT CHASE`, extension guard, etc.).
- The collapsed **Why / Risks** decision panel also uses calm amber instead of red for ordinary blockers.
- True application/data failures (scan failure, incompatible engine, unavailable trustworthy current price, invalid data quality) can still use red because those are actual errors rather than trade guidance.
- **No scoring, ranking, liquidity, optimizer, threshold, or trade-gate logic changed.** This is a UI/semantics patch over V6.3.9.82.


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

## V6.4.2.18 — Premium WHY BLOCKED truth
- Explain confirmed failed breakout and bearish 15-minute selling pressure on the USER SIGNAL front (rather than generic EXECUTION BLOCKED).
- Show EXIT PRESSURE hard blocker with its actual numeric value and 55/100 threshold.
- Keep all underlying execution decisions unchanged. This is a presentation fix only.
- Show TIMING CLEAR instead of TIMING BLOCKED when the timing gate passed but a *different* safety check vetoed the trade.
- Behind the user-signal info icon, include the actual underlying hard-block reason and underlying failed-breakout signals.
- Preserve the previous 17-minute delayed-quote gate and Favorites improvements.
