# AI Stock Hunter V6.4.3.29 — IBKR TASE Quote Verification + Analyst History

## New in V6.4.3.29 — IBKR TASE live-last-trade verification

- **Dedicated area:** `🔐 אימות מחירים` appears in primary navigation, separate from `🔎 סריקה` and `🧠 מרכז אנליסט AI`. It shows the configuration status, an opt-in per-symbol live quote test, explicit result timestamp/age/source/contract ID, and setup help in Hebrew.
- **Real-time data entitlement required:** TASE (`.TA`) can pass the execution quote freshness gate only with an authenticated IBKR TWS/Gateway real-time last-trade observation. The bridge accepts only TASE stock contracts in ILS, live `marketDataType=1`, and a timestamped RTVolume trade (generic tick 233). Delayed, frozen, unentitled, unidentified-contract and stale responses fail closed. A freshly received HTTP response is *not* a recent trade.
- **No false real-time Yahoo pass:** Yahoo `.TA` prices can be roughly 20 minutes delayed; even a recent-looking Yahoo 1m/5m or quote metadata timestamp and a confirmed 15m candle remain **display/research only** and cannot independently certify `ENTRY NOW`. For other markets, the existing price policy is retained. This is an intentional TASE quote-gate tightening.
- **Explicit price denomination:** IBKR TASE contracts use ILS, while Yahoo `.TA` histories are commonly quoted in ILA (agorot). Set `IBKR_TASE_PRICE_MULTIPLIER` to `100` or `1` **after comparing a real symbol manually**. The verifier also demands a current Daily benchmark, rejecting gaps of more than 30% to protect against a 100× unit mistake. No auto-inferred scale can enable trading.
- **Read-only secure architecture:** `ibkr_gateway_bridge.py` is a small, localhost-bound, bearer-protected server beside TWS/Gateway using IBKR's official Python `ibapi`. It requests contract data and streaming quotes only, never orders. Streamlit communicates via a private HTTPS bridge URL and token stored in Secrets; IBKR login credentials are **never** stored in the Stock Hunter app. Do not publicly expose the TWS socket or plaintext HTTP bridge.
- **Not yet connected to your account:** The connection requires a running IBKR client, eligible TASE data subscription, correct local/remote networking, and user-verified quote units. Offline tests were completed; **no live IBKR execution-grade price has yet been observed or certified from your account**.
- **Video enhancements preserved:** The separately accessible Analyst Center, optional AI bull/bear source-limited scenarios, comparison radar and graphical history of saved recommendations versus observed/evaluated outcomes remain in this build. Historical missing observations remain missing; the graph does not manufacture a continuous price history.

### Setup: single-user TWS / IB Gateway bridge

1. In IBKR Account Management, verify your **TASE Level 1** market data entitlement and any applicable personal/non-professional/display restrictions. Having an IBKR account alone is not enough.
2. Download and install the **current official TWS Python API** (module `ibapi`) following [IBKR Campus setup](https://ibkrcampus.com/campus/trading-lessons/accessing-the-tws-python-api-source-code/). This separate bridge machine alone needs `ibapi`.
3. Start TWS or IB Gateway and open **API → Settings**. Enable socket clients and keep **Read-Only API** selected. Check the configured socket port: TWS paper 7497 / live 7496; Gateway paper 4002 / live 4001 (defaults).
4. Generate a strong, random bridge token locally (at least 24 characters). Set the environment variable `IBKR_BRIDGE_TOKEN` on the bridge machine. **Never paste it into chat, GitHub or a ZIP.** Start the bridge on the machine running TWS, e.g. `python ibkr_gateway_bridge.py --tws-port 7497` for TWS paper. It listens on `127.0.0.1:8765` by default.
5. If Streamlit runs **on the same machine**, set the following locally or in Streamlit Secrets (using a real private token):

   ```toml
   IBKR_BRIDGE_URL = "http://127.0.0.1:8765/quote"
   IBKR_BRIDGE_TOKEN = "your-own-private-random-token-at-least-24-chars"
   IBKR_TASE_PRICE_MULTIPLIER = "100"
   ```

   `100` is an **example to verify** against your selected IBKR instrument and Yahoo `.TA` daily prices; some feeds/symbols may already be expressed in the same units.

6. If Streamlit runs **on Streamlit Community Cloud**, `localhost` points to Streamlit's cloud machine, **not your home computer**. You must deploy an authenticated TLS/HTTPS reverse proxy or trusted private tunnel to the local bridge before setting `IBKR_BRIDGE_URL = "https://.../quote"` in **Streamlit Cloud → App → Settings → Secrets**. Keep TWS API socket bound to localhost. Do not use an unrestricted public HTTP port.
7. During TASE continuous trading, open `🔐 אימות מחירים`, enter a known `.TA` symbol that can be resolved in your IBKR account, then press `🧪 בדוק מחיר מול IBKR`. Verify price unit, exchange trading phase, source, age and IBKR conId. Outside trading hours / in an illiquid stock without a fresh trade, `BLOCK` is correct and expected.
8. Only after the independent pilot succeeds, run a **small CUSTOM / SMART TASE scan** and check `QuoteStatus`, `PriceObservationSource`, `FinalQuoteRecheck`, `FinalQuoteVerified` and `FinalTradeDecision`. An API-confirmed quote does not override timing, liquidity, market phase, entry geometry, R:R or other execution gates.

**Current scope:** TASE equities only. The IBKR account's other market-data permissions, broad US consolidated quotes, and Hong Kong feeds have **not** been enabled as execution-grade in this release. The bridge is a single-user prototype; professional deployment needs resiliency monitoring, quote caching/pacing, security review and appropriate market-data usage/redistribution rights.

**Primary IBKR references:** [TWS API setup](https://ibkrcampus.com/campus/trading-lessons/installing-configuring-tws-for-the-api/), [RTVolume trade/time tick 233](https://interactivebrokers.github.io/tws-api/tick_types.html), [Market Data Types](https://interactivebrokers.github.io/tws-api/market_data_type.html), [official API installation](https://ibkrcampus.com/campus/trading-lessons/accessing-the-tws-python-api-source-code/).

---

## New in V6.4.3.28 — Dedicated Analyst Center

- **New primary navigation area:** `🧠 מרכז אנליסט AI`, separate from `🔎 סריקה`. The deterministic three-timeframe analyst, consent-based OpenAI scenario analyst, and the 20-stock explainable radar appear in this new area. Scanner keeps its existing trading cards and a short pointer to the new area.
- **No rescoring or retrospective signals:** The new center reads the last completed Scanner snapshot (preferring the saved last full run over a finalist-only rerun) in its original order. It filters stocks by US / Hong Kong / Tel Aviv for display only, without altering scan results or trade decisions.
- **Graphical recommendation history:** The new history plot reads only timestamped Feedback observations captured by `LIVE SCANNER` or `ANALYZE`. A top chart plots recorded observation prices, **not** a fabricated continuous market-price series; a bottom chart plots actual evaluated percentage changes after 1/2/3/5 future trading sessions. Markers retain the saved original `ENTRY NOW`, `WAIT`, `DO NOT ENTER` or unknown decision. Imported Excel/replay rows are excluded. Pending outcomes remain visibly missing.
- **Traceable detail and export:** Per-observation source, original date, recorded price, engine decision, evaluation status and measured future change are available in a right-aligned table and downloadable CSV. Future price change is **not** filled-trade P&L or an `ENTRY NOW` win rate; actual paper-entry policy is evaluated separately in Reliability First.
- **Safe deployment:** The ZIP now contains **nine files**, adding `recommendation_history.py`. All module/build versions are V6.4.3.28; the trading engine's only changes are its version strings. No portfolio transactions, gate changes, feedback writes or ranking changes were introduced by the new area.

## Previous V6.4.3.27 — RTL Explainable Brief + Optional AI Scenarios

### Right-to-left analyst and optional AI scenarios

- **Hebrew layout:** The analyst renders explanations, evidence, risks and metrics as right-aligned RTL HTML, with mixed English/numeric snippets isolated for readable punctuation.
- **Easy to find:** The explainable 20-stock comparison radar is a separate expander under the analyst within the new dedicated center.
- **Optional real AI narrative:** For one ticker, select **✨ צור תרחיש שורי ודובי ב־AI** to request conditional bull/bear scenarios, invalidation criteria, what could change the research conclusion and data-source IDs. This does **not** re-score stocks, place trades, promote ENTRY NOW or change trading decisions or saved feedback.
- **Explicit opt-in and source limits:** The user must check a consent box first; only the selected ticker's saved scanner evidence is sent. OpenAI Responses API uses `store=false`, no tools and a strict JSON schema. `S1` and `S2` are the saved scanner and quote provenance, **not** live web research, independent filing analysis or news fact-checking. Missing evidence must be disclosed. AI output is research commentary, not independent source verification.
- **Credentials & billing:** Set `OPENAI_API_KEY` in **Streamlit Cloud > App > Settings > Secrets**; optionally set `OPENAI_ANALYST_MODEL` (default `gpt-5.4-mini`). Never include keys in source, GitHub commits or chat. API usage is billed separately from ChatGPT. Without the key, the deterministic Hebrew analyst and radar remain fully available, and no AI request occurs.
- **Deployment:** The optional AI module `ai_scenario_analyst.py` must be uploaded with the other matching-version files.
- **No trading-policy change:** `quant_engine.py` changes version metadata only; rankings, quote gates, stops, targets, scan depth and official SEC filing audit remain unchanged.

Based on the complete V6.4.3.25 release. Trading ranking, ENTRY NOW, quote gates, stop/targets, Winner DNA, feedback persistence, scanning limits, and overall scanner strategy are unchanged. Both the new explanation panel and official filing information are **research only**.

## Previous V6.4.3.26 — Explainable Analyst Brief

- In the **Scanner**, open **🧠 אנליסט מסביר — סיכום מניה בשלושה טווחי זמן**, then choose any stock from the current filtered scan results.
- The report presents the **existing engine decision and scores without rescoring them**, three distinct existing checks (daily setup, 1H entry confirmation, 15m momentum), available reasons for and against, missing evidence, quote-source timestamp, freshness and quote gate.
- Download a stand-alone Hebrew Markdown report for the selected stock. The report contains the cached scan's timestamp and keeps unavailable evidence explicitly unknown.
- An expandable **explainable radar comparison** shows up to 20 names in the existing display order with their already-computed rankings, three-frame evidence, quote gate and data-quality status.
- A saved scan is **never a live execution authorization**; even a previously verified ENTRY NOW requires a new deep analysis before acting. No external LLM or API call is made and no market data leaves the app for this report.
- The explanatory module `intelligence_brief.py` remains mandatory. It is read-only and does not alter scan results, positions, trading or feedback data.

### Why we did not replace the existing radar

Stock Hunter already has an Opportunity score, Decision Ranking, Pre-Move radar, multi-timeframe execution logic, empirical/OOS research and hard safety gates. This release improves *explainability* and transparent evidence rather than introducing a second uncalibrated score or an AI-generated trade signal.

## What is new

- **SEC EDGAR / XBRL integration for the FINAL Scanner Top 5:** After the production trade ranking and final quote / decision audit, the app looks up any U.S.-listed Top-5 ticker in the SEC's official ticker-to-CIK registry and requests the company's public `companyfacts` JSON. No Financial Modeling Prep calls or keys.
- **Guarded, audited accounting inputs:** Only annual reported USD facts from a matching 10-K, 20-F or 40-F accession, reporting period and company CIK are eligible. Revenue and profit must be from the same annual filing, with a 330–400-day duration; SEC annual periods over 550 days old are rejected. FCF is accepted only when operating cash flow and capex match the same filing. `P/S`, trailing `P/E`, annual margin, `P/B` and `FCF yield` are recomputed from SEC inputs (when available) and Yahoo market capitalization. Missing metrics stay missing. Yahoo forecasts and other fundamentals remain **separate, mixed-source research**; no fair value is described as an audited valuation.
- **Hong Kong and Tel Aviv:** Official report portal links are added to the Top 5 and the workbook. These PDF/HTML statements are **not automatically parsed** in this version, and they are explicitly labeled `OFFICIAL REPORTS — MANUAL REVIEW` until a tested parser is added. Yahoo existing coverage remains but is not misrepresented as official verification.
- **One-click SEC test:** In `💎 שווי חברה` > `🏛️ בדיקת SEC עצמאית — ללא סריקה`, enter a U.S. ticker (default AAPL) and click to test the SEC route independently of the 160-stock scan.
- **Auditable exports:** `Official Filings Top 5` worksheet appears in normal Scanner Excel and in Valuation Excel. Top-5 columns include URL to official reports, SEC fiscal period, filing date, whether SEC financial inputs were used, and exact connection/parsing status.
- **Safe failure:** If SEC identification, connectivity or an annual filing is unavailable, no SEC values are fabricated; the prior Yahoo valuation remains a Yahoo estimate. The trading decision is never recalculated by this overlay.

## One-time optional setup for official U.S. financial statements

The SEC public API has **no API key**, but requires an identifying User-Agent with a genuine contact. In **Streamlit Cloud > App > Settings > Secrets**, add a line with your own contact information:

```toml
SEC_USER_AGENT = "AIStockHunter your-real-email@domain.com"
```

Change `your-real-email@domain.com` to a real contact email. Do **not** paste your personal contact or any private credentials in chat or public GitHub files. Only Streamlit Secrets. If you do not set it, SEC connections are skipped with `SEC NOT CONFIGURED`, and Yahoo valuations continue unchanged. The old FMP key is unused and may be removed from Secrets.

SEC endpoints: official ticker registry `https://www.sec.gov/files/company_tickers.json` and `https://data.sec.gov/api/xbrl/companyfacts/CIK##########.json`. The application uses explicit User-Agent headers, paced requests and cached responses; restrictions or IP blocking can still cause `SEC ACCESS / RATE LIMIT`.

## Deployment and verification

1. Back up the feedback SQLite database (Streamlit Cloud local files can be ephemeral).
2. For the current **V6.4.3.29**, upload the updated Streamlit files and `ibkr_price_verifier.py` together. Keep `ibkr_gateway_bridge.py` on the machine running TWS/Gateway, not as a public web service. Do not overwrite feedback backups. This ZIP is not an automatic deployment.
3. Verify app, engine, Hebrew help, AI and history modules show **V6.4.3.29**. Open `🧠 מרכז אנליסט AI` after a completed scan; the new `🔐 אימות מחירים` area is accessible immediately.
4. In **💎 שווי חברה**, run the **independent SEC test** first (no full scan needed). If it succeeds, run **one SMART scan with Valuation ON** to populate the FINAL Top 5 audit and Excel.
5. In Scanner Excel, inspect `Official Filings Top 5`; in Valuation Excel, inspect the same tab and `Top 5 Source Audit`.

## Limits / safety

- SEC responses have **not been successfully live-tested from your Streamlit Cloud instance**, since this environment has no access to your private app settings. Offline mocked-behavior tests and Python syntax validation were performed. A live check may reveal a SEC HTTP 403/429, incomplete taxonomy tagging or other access constraint.
- U.S. statements are annual historical SEC facts, **not** analyst forecasts or present-day cash flow. Values remain estimates. `SEC VERIFIED ANNUAL USD FACTS` confirms reported raw accounting inputs, **not** a verified fair value.
- SEC is used only for the five final-ranked scanner tickers; when the final Top 5 are all HK/TA, no SEC calls are made and their official reports require manual review.
- HKEXnews and TASE Maya statement extraction and quote/accounting FX reconciliation are still future engineering tasks; missing values remain unknown. Do not infer fair value from missing or conflicting figures.
- No FMP API calls, no FMP key reads, no FMP UI. Do not upload any Secrets or feedback SQLite backups to a public repository.
- The deterministic analyst brief uses **daily, 1H and 15m** evidence already computed by the engine; these are *not* weekly/monthly forecasts. The **optional** AI narrative makes a separate manual, paid API call and must not override the production decision. Neither reports empirical win probability.

## QA

- Python compile checks on all seven Python files.
- Offline mock tests for valid SEC annual facts, exact fiscal/filer matching, stale/missing SEC data, absent SEC contact, currency mismatch, HK/TA manual route, successful SEC ratios, and invariance of production trade decisions.
- Package member checks and consistent app/engine/help version markers.
- Pure-function tests of the analyst brief: no data, stale/blocked quotes, multi-timeframe disagreements, executable snapshot label, report export and unchanged input values.
- Offline tests of source-bound optional AI responses and of graphical history: only captured observations, imported/replay exclusion, exact future horizon, preserved original decision and pending outcome ≠ loss.
