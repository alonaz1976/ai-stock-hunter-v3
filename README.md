# AI Stock Hunter V6.4.3.28 — Analyst Center + Captured Recommendation History

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
2. Upload **all nine files** in this ZIP together to your app repository, without overwriting feedback backups. This ZIP is not an automatic deployment.
3. Verify app, engine, Hebrew help, AI and history modules show **V6.4.3.28**. Open `🧠 מרכז אנליסט AI` from the primary navigation after a completed scan.
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
