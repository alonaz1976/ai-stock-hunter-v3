"""Read-only IBKR TASE last-trade verifier.

The Streamlit process never holds an IBKR account password and never sends an
order.  A separate, operator-owned, authenticated HTTPS bridge beside TWS / IB
Gateway exposes ONLY the quote endpoint defined in this module.

No available quote (including Yahoo/TradingView) may be promoted to an IBKR
real-time quote.  The operator must explicitly confirm the TASE price unit
multiplier against the scanner's Yahoo-quoted historical series.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import math
import os
import urllib.error
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

IBKR_VERIFIER_VERSION = "6.4.3.29"
IBKR_MAX_TRADE_AGE_MINUTES = 5.0


def _setting(key):
    value = os.environ.get(key)
    if value is not None:
        return str(value).strip()
    try:
        import streamlit as st
        return str(st.secrets.get(key, "") or "").strip()
    except Exception:
        return ""


def bridge_configuration():
    """Safe-to-display status only; credentials are never returned."""
    url = _setting("IBKR_BRIDGE_URL")
    token = _setting("IBKR_BRIDGE_TOKEN")
    factor = _setting("IBKR_TASE_PRICE_MULTIPLIER")
    parsed = urllib.parse.urlsplit(url)
    local_host = parsed.hostname in ("localhost", "127.0.0.1", "::1")
    secure_url = (parsed.scheme == "https" or (parsed.scheme == "http" and local_host))
    valid_path = parsed.path.rstrip("/") in ("", "/quote") and not parsed.query and not parsed.fragment
    try:
        mult = float(factor)
        valid_mult = math.isfinite(mult) and mult in (1.0, 100.0)
    except (ValueError, TypeError):
        mult = None
        valid_mult = False
    ready = bool(url and len(token) >= 24 and secure_url and valid_path and valid_mult)
    if not url:
        reason = "BRIDGE URL NOT CONFIGURED"
    elif not secure_url or not valid_path:
        reason = "BRIDGE URL MUST BE HTTPS (OR LOCALHOST HTTP)"
    elif len(token) < 24:
        reason = "BRIDGE TOKEN MISSING / TOO SHORT"
    elif not valid_mult:
        reason = "TASE PRICE MULTIPLIER MUST BE EXPLICITLY CONFIRMED: 1 OR 100"
    else:
        reason = "READY FOR LIVE CONNECTION TEST"
    return {"configured": ready, "status": reason, "base_url": url if ready else "",
            "price_multiplier": mult if ready else None}


def verify_tase_last_trade(ticker, reference_price=None, now=None, requester=None):
    """Return an execution-grade candidate *only* for an IBKR real-time TASE trade.

    `requester` is an injectable HTTP getter for offline tests.  The bridge
    delivers timestamps of *executed trades*, not candle start times or HTTP
    response arrival times.  Reject delayed/frozen feeds and unexplained units.
    """
    sym = str(ticker or "").strip().upper()
    cfg = bridge_configuration()
    if not sym.endswith(".TA") or not cfg["configured"]:
        return None
    if not sym[:-3] or not all(x.isalnum() or x in "-_" for x in sym[:-3]):
        return None
    url = cfg["base_url"].rstrip("/")
    if not url.endswith("/quote"):
        url += "/quote"
    url += "?symbol=" + urllib.parse.quote(sym, safe="")
    token = _setting("IBKR_BRIDGE_TOKEN")
    headers = {"Authorization": "Bearer " + token, "Accept": "application/json"}
    try:
        if requester is None:
            req = urllib.request.Request(url, headers=headers, method="GET")
            with urllib.request.urlopen(req, timeout=5.0) as response:
                raw = response.read(8193)
                if len(raw) > 8192:
                    return None
                payload = json.loads(raw.decode("utf-8"))
        else:
            payload = requester(url, headers)
        if not isinstance(payload, dict):
            return None
        if (str(payload.get("symbol", "")).upper() != sym or
                str(payload.get("exchange", "")).upper() != "TASE" or
                str(payload.get("currency", "")).upper() != "ILS" or
                str(payload.get("last_kind", "")).upper() != "LAST_TRADE" or
                str(payload.get("status", "")).upper() != "OK" or
                type(payload.get("market_data_type")) is not int or
                payload["market_data_type"] != 1):
            return None
        raw_price = float(payload["price"])
        if not (math.isfinite(raw_price) and raw_price > 0):
            return None
        ts_value = payload["timestamp"]
        if isinstance(ts_value, (int, float)) and not isinstance(ts_value, bool):
            observation = datetime.fromtimestamp(float(ts_value), tz=timezone.utc)
        else:
            observation = datetime.fromisoformat(str(ts_value).replace("Z", "+00:00"))
            if observation.tzinfo is None:
                return None
        now_utc = now or datetime.now(timezone.utc)
        if now_utc.tzinfo is None:
            return None
        now_utc = now_utc.astimezone(timezone.utc)
        obs_utc = observation.astimezone(timezone.utc)
        raw_age = (now_utc - obs_utc).total_seconds() / 60.0
        local = observation.astimezone(ZoneInfo("Asia/Jerusalem"))
        same_session = local.date() == now_utc.astimezone(ZoneInfo("Asia/Jerusalem")).date()
        if not (same_session and -0.5 <= raw_age <= IBKR_MAX_TRADE_AGE_MINUTES):
            return None
        price = raw_price * cfg["price_multiplier"]
        # The scanner's baseline is Yahoo .TA, typically ILA (agorot), while
        # the IBKR contract currency is ILS. Do not auto-guess a 100x scale.
        try:
            ref = float(reference_price)
        except (ValueError, TypeError):
            return None
        if not (math.isfinite(ref) and ref > 0 and 0.70 <= price / ref <= 1.30):
            return None
        return {"price": price, "timestamp": local.isoformat(),
                "timestamp_label": local.strftime("%Y-%m-%d %H:%M:%S"),
                "age_minutes": max(0.0, raw_age), "source": "IBKR TWS • TASE REALTIME",
                "fresh": True, "display_current": True, "trade_fresh": True,
                "anchor_eligible": True, "provider_timestamp_verified": True,
                "same_session_date": True, "quote_status": "IBKR REALTIME • VERIFIED LAST TRADE",
                "ibkr_contract_id": payload.get("conid"),
                "ibkr_feed_type": 1, "ibkr_price_multiplier": cfg["price_multiplier"]}
    except (ValueError, TypeError, KeyError, OverflowError, OSError,
            urllib.error.URLError, json.JSONDecodeError):
        return None
