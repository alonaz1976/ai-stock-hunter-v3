"""Point-in-time recommendation history for the read-only Analyst Center.

Input snapshots must have been captured by a running Scanner or Analyze.
Outcomes are joined only when an actual future-market evaluation exists; no
historical research rows, hindsight signals or pending returns are fabricated.
"""

import pandas as pd


HISTORY_VERSION = "6.4.3.28"
_VALID_SOURCES = {"LIVE SCANNER", "ANALYZE"}
_REQUIRED_COLUMNS = {"id", "ts_utc", "ticker", "price", "snapshot_source"}
_OUTPUT_COLUMNS = [
    "snapshot_id", "observed_at", "ticker", "market", "observed_price",
    "engine_decision", "observation_source", "event_role", "event_id",
    "horizon", "observed_return_pct", "max_favorable_pct", "max_adverse_pct",
    "first_event", "outcome_state",
]


def history_for_ticker(snapshots, outcomes, ticker, horizon=3, limit=500):
    """Return real captured observations plus *only* evaluated future outcomes.

    `observed_return_pct` is the raw stock-price change from the recorded
    observation, NOT a simulated fill/P&L and NOT an ENTRY NOW success rate.
    """
    empty = pd.DataFrame(columns=_OUTPUT_COLUMNS)
    if not isinstance(snapshots, pd.DataFrame) or not _REQUIRED_COLUMNS.issubset(snapshots.columns):
        return empty
    if not ticker or int(horizon) not in (1, 2, 3, 5):
        return empty

    s = snapshots.loc[
        snapshots["ticker"].astype(str).str.upper().eq(str(ticker).upper())
        & snapshots["snapshot_source"].astype(str).str.upper().isin(_VALID_SOURCES)
    ].copy()
    if s.empty:
        return empty
    s["observed_at"] = pd.to_datetime(s["ts_utc"], utc=True, errors="coerce")
    s["observed_price"] = pd.to_numeric(s["price"], errors="coerce")
    s["snapshot_id"] = pd.to_numeric(s["id"], errors="coerce")
    s = s.loc[
        s["observed_at"].notna() & s["snapshot_id"].notna()
        & s["observed_price"].gt(0)
    ].sort_values(["observed_at", "snapshot_id"]).drop_duplicates("snapshot_id", keep="last")
    if s.empty:
        return empty
    s = s.tail(max(1, min(int(limit), 2000))).copy()
    s["snapshot_id"] = s["snapshot_id"].astype(int)

    decision_col = "final_trade_decision" if "final_trade_decision" in s.columns else None
    s["engine_decision"] = (
        s[decision_col].fillna("UNKNOWN").astype(str).str.upper().str.strip()
        if decision_col else "UNKNOWN"
    )
    s.loc[~s["engine_decision"].isin(["ENTRY NOW", "WAIT", "DO NOT ENTER"]), "engine_decision"] = "UNKNOWN"
    for col, default in (("market", "—"), ("snapshot_source", "UNKNOWN"),
                         ("event_role", "UNKNOWN"), ("event_id", "")):
        if col not in s.columns:
            s[col] = default
    s["observation_source"] = s["snapshot_source"].astype(str)
    s["horizon"] = int(horizon)

    if isinstance(outcomes, pd.DataFrame) and {"snapshot_id", "horizon", "end_return"}.issubset(outcomes.columns):
        o = outcomes.copy()
        o["snapshot_id"] = pd.to_numeric(o["snapshot_id"], errors="coerce")
        o["horizon"] = pd.to_numeric(o["horizon"], errors="coerce")
        o = o.loc[o["horizon"].eq(int(horizon)) & o["snapshot_id"].notna()].copy()
        for col in ("end_return", "max_favorable", "max_adverse"):
            if col not in o.columns:
                o[col] = float("nan")
            o[col] = pd.to_numeric(o[col], errors="coerce") * 100.0
        if "first_event" not in o.columns:
            o["first_event"] = ""
        o = o.sort_values("snapshot_id").drop_duplicates("snapshot_id", keep="last")
        o = o[["snapshot_id", "end_return", "max_favorable", "max_adverse", "first_event"]]
        s = s.merge(o, on="snapshot_id", how="left", validate="one_to_one")
    else:
        for col in ("end_return", "max_favorable", "max_adverse"):
            s[col] = float("nan")
        s["first_event"] = ""

    s = s.rename(columns={"end_return": "observed_return_pct",
                           "max_favorable": "max_favorable_pct",
                           "max_adverse": "max_adverse_pct"})
    s["outcome_state"] = s["observed_return_pct"].apply(
        lambda x: "EVALUATED" if pd.notna(x) else "PENDING")
    s["first_event"] = s["first_event"].fillna("")
    s["observed_at"] = s["observed_at"].dt.tz_convert("Asia/Jerusalem")
    return s[_OUTPUT_COLUMNS].reset_index(drop=True)
