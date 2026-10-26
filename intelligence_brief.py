"""Read-only, explainable research briefs from completed AI Stock Hunter scans.

This module deliberately does not change rankings, scores, execution decisions,
or call data/LLM providers. Missing and stale evidence is reported, not inferred.
"""

from datetime import datetime, timezone
import math
import numbers
import re
from zoneinfo import ZoneInfo


BRIEF_VERSION = "6.4.3.28"
_MISSING = {"", "—", "-", "N/A", "NA", "NONE", "NAN", "NULL", "UNKNOWN", "NOT AVAILABLE", "<NA>", "NAT"}


def _value(row, *keys):
    for key in keys:
        try:
            value = row.get(key)
        except (AttributeError, TypeError):
            value = None
        if value is None:
            continue
        if isinstance(value, str) and value.strip().upper() in _MISSING:
            continue
        try:
            if isinstance(value, (int, float)) and not math.isfinite(float(value)):
                continue
        except (TypeError, ValueError, OverflowError):
            continue
        return value
    return None


def _number(row, *keys):
    value = _value(row, *keys)
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError, OverflowError):
        return None


def _flag(row, *keys):
    value = _value(row, *keys)
    if isinstance(value, bool):
        return value
    if isinstance(value, numbers.Real):
        return bool(value) if math.isfinite(float(value)) and float(value) in (0, 1) else None
    normalized = str(value).strip().upper()
    if normalized in {"TRUE", "YES", "PASS", "OK", "CONFIRMED", "1"}:
        return True
    if normalized in {"FALSE", "NO", "FAIL", "BLOCK", "0"}:
        return False
    return None


def _text(row, *keys, limit=220):
    value = _value(row, *keys)
    if value is None:
        return None
    clean = re.sub(r"\s+", " ", str(value)).strip()
    return clean[:limit] + ("…" if len(clean) > limit else "")


def _momentum_state(value):
    if value is None:
        return "אין נתון", "unknown"
    state = str(value).upper().strip()
    if any(word in state for word in ("BEAR", "DOWN", "NEGATIVE", "SELL")):
        return "שלילי", "negative"
    if any(word in state for word in ("BULL", "UP", "POSITIVE", "BUY")):
        return "חיובי", "positive"
    if any(word in state for word in ("NEUTRAL", "FLAT", "MIXED", "SIDEWAYS")):
        return "ניטרלי", "neutral"
    return "לא מסווג", "unknown"


def _gate_state(value):
    if value is True:
        return "אושר", "positive"
    if value is False:
        return "לא אושר", "negative"
    return "אין נתון", "unknown"


def _time_label(epoch):
    try:
        value = float(epoch)
        if math.isfinite(value) and value > 0:
            return datetime.fromtimestamp(value, timezone.utc).astimezone(
                ZoneInfo("Asia/Jerusalem")
            ).strftime("%d/%m/%Y %H:%M")
    except (ValueError, TypeError, OverflowError, OSError):
        pass
    return "לא ידוע"


def build_intelligence_brief(row, scan_finished_at=None):
    """Create a factual explanation from one saved scanner row.

    The *decision* is copied exactly from the engine. Never promote a research
    pattern, a score, or stale market data into an executable signal.
    """
    ticker = _text(row, "Ticker", limit=32) or "—"
    market = _text(row, "Market", limit=32) or "—"
    decision = (_text(row, "FinalTradeDecision", limit=48) or "WAIT").upper()
    stage = _text(row, "EffectiveDecisionStage", "DecisionBoardStage", limit=80) or "לא ידוע"
    score = _number(row, "OpportunityScore")
    rank = _number(row, "DecisionRankScore")

    daily = _gate_state(_flag(row, "DailySetupCheck", "DailySetup"))
    hourly = _gate_state(_flag(row, "HourlyEntryCheck"))
    intraday = _momentum_state(_value(row, "MomentumState15m"))
    frames = [
        {"label": "יומי · איכות התבנית", "state": daily[0], "tone": daily[1]},
        {"label": "שעתי · אישור תזמון", "state": hourly[0], "tone": hourly[1]},
        {"label": "15 דקות · מומנטום", "state": intraday[0], "tone": intraday[1]},
    ]
    measured = [item for item in frames if item["tone"] != "unknown"]
    positive = sum(item["tone"] == "positive" for item in measured)
    negative = sum(item["tone"] == "negative" for item in measured)
    consensus = (
        "התאמה חיובית" if measured and positive == len(measured)
        else "התאמה שלילית" if measured and negative == len(measured)
        else "תמונה מעורבת" if positive and negative
        else "התאמה חלקית" if measured
        else "אין די מידע"
    )

    quote_gate = (_text(row, "QuoteGateResult", limit=32) or "UNKNOWN").upper()
    quote_verified = _flag(row, "FinalQuoteVerified", "ProviderTimestampVerified")
    price_fresh = _flag(row, "LivePriceFresh")
    data_quality = (_text(row, "DataQuality", limit=80) or "UNKNOWN").upper()
    market_phase = (_text(row, "MarketPhase", limit=32) or "UNKNOWN").upper()
    hard_block = _flag(row, "FinalTradeHardBlock")
    executable = (
        decision == "ENTRY NOW" and quote_gate == "PASS"
        and quote_verified is True and price_fresh is True
        and market_phase == "OPEN" and hard_block is not True
    )

    risks = []
    if quote_gate != "PASS":
        risks.append("ביקורת הציטוט לא עברה או שלא קיימת ראיה שעברה.")
    if quote_verified is not True or price_fresh is not True:
        risks.append("עדכניות המחיר או חותמת הזמן לא אומתה במלואה.")
    if data_quality not in {"OK", "PASS", "GOOD"}:
        risks.append(f"איכות נתונים: {data_quality}.")
    if hard_block is True:
        risks.append("מנוע המסחר סימן חסימת ביצוע קשיחה.")
    if market_phase != "OPEN":
        risks.append(f"מצב השוק: {market_phase}; אין להסיק מכך אישור ביצוע חי.")
    if negative:
        risks.append("לפחות אחת משלוש בדיקות טווחי הזמן אינה תומכת בתרחיש.")
    if len(measured) < 3:
        risks.append("חלק מאישורי טווחי הזמן חסרים; לא הושלמו בהשערה.")

    reasons = []
    for label, keys in (
        ("נימוק החלטה", ("FinalTradeReason", "EffectiveDecisionReason")),
        ("מה נדרש להשלמה", ("EntryMissingChecks", "ActionabilityMissing")),
        ("חסימת כניסה", ("EntryBlockReason", "QuoteGateBlockReason")),
        ("תמונה טכנית", ("EntryWhyNow", "DecisionRankReason")),
    ):
        value = _text(row, *keys)
        if value:
            reasons.append({"label": label, "text": value})

    price = _number(row, "FinalQuotePrice", "Price")
    price_source = _text(row, "FinalQuoteSource", "PriceObservationSource", "PriceSource", limit=120) or "לא ידוע"
    price_timestamp = _text(row, "FinalQuoteTimestamp", "PriceObservationTimestampISO", "PriceTimestamp", limit=120) or "לא ידוע"
    plan = {
        "entry_low": _number(row, "ExecutionEntryLow"),
        "entry_high": _number(row, "ExecutionEntryHigh"),
        "stop": _number(row, "ExecutionInvalidation"),
        "target1": _number(row, "ExecutionTarget1"),
        "target2": _number(row, "ExecutionTarget2"),
        "rr_t1": _number(row, "ExecutionRR_T1"),
        "valid": _flag(row, "ExecutionPlanValid") is True,
    }
    if plan["valid"] and any(plan[key] is None for key in ("entry_low", "entry_high", "stop", "target1")):
        plan["valid"] = False
        risks.append("רמות הביצוע השמורות אינן שלמות; התוכנית לא מוצגת כהוראה.")
    if plan["entry_low"] is not None and plan["entry_high"] is not None:
        if plan["entry_low"] > plan["entry_high"]:
            plan["valid"] = False
            risks.append("טווח הכניסה אינו עקבי; אין להציגו כהוראה.")

    return {
        "ticker": ticker, "market": market, "decision": decision,
        "stage": stage, "opportunity_score": score, "decision_rank_score": rank,
        "timeframes": frames, "consensus": consensus,
        "measured_frames": len(measured), "positive_frames": positive,
        "executable": executable, "quote_gate": quote_gate,
        "quote_verified": quote_verified, "price_fresh": price_fresh,
        "market_phase": market_phase, "data_quality": data_quality,
        "price": price, "price_source": price_source,
        "price_timestamp": price_timestamp, "scan_timestamp": _time_label(scan_finished_at),
        "reasons": reasons, "risks": risks, "plan": plan,
        "research_only": True,
    }


def brief_markdown(brief):
    def fmt(value):
        return f"{value:,.3f}" if isinstance(value, (int, float)) and math.isfinite(value) else "—"

    lines = [
        f"# דוח אנליסט מסביר — {brief['ticker']} ({brief['market']})",
        f"סריקה: {brief['scan_timestamp']} (שעון ישראל)",
        f"החלטת מנוע: {brief['decision']} | מצב: {brief['stage']}",
        f"ציון הזדמנות: {fmt(brief['opportunity_score'])} | ציון דירוג החלטה: {fmt(brief['decision_rank_score'])}",
        f"התאמת טווחים: {brief['consensus']} ({brief['positive_frames']}/{brief['measured_frames']} מדידות חיוביות)",
        "", "## טווחי זמן",
    ]
    lines.extend(f"- {frame['label']}: {frame['state']}" for frame in brief["timeframes"])
    lines.extend(["", "## נתוני מחיר", f"מחיר: {fmt(brief['price'])}",
                  f"מקור: {brief['price_source']} | חותמת מקור: {brief['price_timestamp']}",
                  f"ביקורת ציטוט: {brief['quote_gate']} | מצב שוק: {brief['market_phase']}",
                  "", "## ראיות ונימוקים"])
    lines.extend(f"- {reason['label']}: {reason['text']}" for reason in brief["reasons"])
    if not brief["reasons"]:
        lines.append("- לא נמצאו נימוקים שמורים בתוצאת הסריקה.")
    lines.extend(["", "## מגבלות וסיכונים"])
    lines.extend(f"- {risk}" for risk in brief["risks"])
    if not brief["risks"]:
        lines.append("- לא זוהו חסימות מתוך השדות הנבדקים; זו אינה הוכחה להיעדר סיכון.")
    lines.extend(["", "מחקר והסבר לנתונים קיימים בלבד. אין שינוי בהחלטת מנוע המסחר, ואין זו המלצת השקעה."])
    return "\n".join(lines) + "\n"
