import streamlit as st
import pandas as pd
import numpy as np
import math
import threading
import sqlite3
import json
import re
import os
import base64
import gzip
import pickle
import gc
import tempfile
import urllib.request as urllib_request
import urllib.error as urllib_error
import urllib.parse as urllib_parse
import time as time_module
from concurrent.futures import ThreadPoolExecutor
from itertools import combinations
import importlib.util
import html as html_lib
import hashlib
from pathlib import Path
from datetime import datetime, time, timedelta, timezone
from io import BytesIO
from zoneinfo import ZoneInfo
import plotly.graph_objects as go
import yfinance as yf
from plotly.subplots import make_subplots

APP_VERSION = "6.3.9.65"
APP_BUILD_ID = "V63965-LIQUIDITY-RANK-RR-PREMOVE-CREDIT-20261005-A"

# Shared HTML-escape helper used by both Scanner and Analyze cards.
# V6.3.9.22 had a Scanner-local helper with the same name, which caused
# Analyze to raise NameError when rendering its Scanner-style card.
def _e6395(v):
    return html_lib.escape(str(v if v is not None else ""))

def _decision_stage_canonical_v63961(stage):
    """Canonical V6.3.9.61 Decision Board stage.

    EARLY RADAR is accepted only as a legacy input from older saved scans/Feedback.
    New Scanner/Analyze/Excel output uses BUILDING SETUP everywhere.
    """
    s=str(stage or 'WAIT').upper().strip()
    if s=='EARLY RADAR': return 'BUILDING SETUP'
    if s in ('ARMED • BLOCKED','ARMED - BLOCKED','ARMED / BLOCKED'): return 'ARMED BLOCKED'
    return s

def _decision_stage_display_v63960(stage):
    s=_decision_stage_canonical_v63961(stage)
    return 'ARMED • BLOCKED' if s=='ARMED BLOCKED' else s

def _decision_stage_internal_v63960(stage):
    # Kept under the old function name because many UI call-sites already use it.
    # V6.3.9.61 no longer converts BUILDING SETUP back to EARLY RADAR.
    return _decision_stage_canonical_v63961(stage)

# Always load the quant engine from the quant_engine.py file that sits next to
# this app.py.  Using a unique module name deliberately bypasses a stale
# sys.modules entry that Streamlit can keep alive across hot-reloads.
def _load_local_quant_engine():
    engine_path = Path(__file__).resolve().with_name("quant_engine.py")
    if not engine_path.exists():
        raise FileNotFoundError(f"Missing quant engine file: {engine_path}")
    unique_name = f"ai_stock_hunter_quant_{APP_BUILD_ID.replace('-', '_')}"
    spec = importlib.util.spec_from_file_location(unique_name, engine_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not create import spec for {engine_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

qe = _load_local_quant_engine()
# Bind engine functions defensively so an out-of-sync quant_engine.py does not crash
# the whole Streamlit app during import. The UI below will show an explicit sync error
# if any required V5.4.x function is missing.
fetch_ohlcv = getattr(qe, "fetch_ohlcv", None)
fetch_recent_split_events = getattr(qe, "fetch_recent_split_events", lambda ticker, lookback_days=45: [])
temporary_counter_info = getattr(qe, "temporary_counter_info", lambda ticker, on_date=None: None)
market_data_symbol = getattr(qe, "_market_data_symbol", lambda ticker, on_date=None: str(ticker or "").upper().strip())
provider_reference_close = getattr(qe, "_provider_reference_close", lambda symbol, ref_date=None, current_price=np.nan, split_ratio=np.nan: (np.nan,None,"UNAVAILABLE"))
fetch_premarket_snapshots = getattr(qe, "fetch_premarket_snapshots", lambda tickers: {})
fetch_aftermarket_snapshots = getattr(qe, "fetch_aftermarket_snapshots", lambda tickers: {})
compute_features = getattr(qe, "compute_features", None)
pre_breakout_accumulation = getattr(qe, "_pre_breakout_accumulation_v63956", getattr(qe, "_pre_breakout_accumulation_v63955", lambda feat: {"score":0.0,"stage":"NO CURRENT ACCUMULATION SETUP","reason":"Unavailable","recent_price_move_pct":float("nan"),"volume_shock_ratio":float("nan"),"confirmed_pre_move":False}))
score_latest = getattr(qe, "score_latest", None)
backtest_signal = getattr(qe, "backtest_signal", None)
scan_universe_dynamic = getattr(qe, "scan_universe_dynamic", None)
entry_timing = getattr(qe, "entry_timing", None)
score_row = getattr(qe, "score_row", None)
early_score_row = getattr(qe, "early_score_row", None)
dynamic_scores = getattr(qe, "dynamic_scores", None)
compare_static_dynamic_backtest = getattr(qe, "compare_static_dynamic_backtest", None)
explosive_latest = getattr(qe, "explosive_latest", None)
explosive_walkforward = getattr(qe, "explosive_walkforward", None)
historical_signal_timeline = getattr(qe, "historical_signal_timeline", None)
threshold_optimization = getattr(qe, "threshold_optimization", None)
adaptive_target_horizon = getattr(qe, "adaptive_target_horizon", None)
adaptive_target_horizon_v2 = getattr(qe, "adaptive_target_horizon_v2", None)
pre_move_study = getattr(qe, "pre_move_study", None)
pre_move_indicator_lift = getattr(qe, "pre_move_indicator_lift", None)
hourly_lift_study = getattr(qe, "hourly_lift_study", None)
topk_daily_validation = getattr(qe, "topk_daily_validation", None)
atr_target_validation = getattr(qe, "atr_target_validation", None)
hourly_confirmation = getattr(qe, "hourly_confirmation", None)
signal_timing_latest = getattr(qe, "signal_timing_latest", None)
acceleration_validation = getattr(qe, "acceleration_validation", None)
confirmed_intraday_bars = getattr(qe, "confirmed_intraday_bars", lambda x: x)
normalize_cross_timeframes = getattr(qe, "normalize_cross_timeframes", lambda d,h=None,m=None,anchor_price=None,split_ratio=None,split_date=None: (d,h,m,{"split_adjusted":False,"split_detected":False,"data_quality":"OK","details":[]}))
fetch_live_intraday_snapshot = getattr(qe, "fetch_live_intraday_snapshot", lambda ticker,daily=None: {"price":np.nan,"prev_close":np.nan,"change_pct":np.nan,"timestamp_label":"—","source":"unavailable","fresh":False,"display_current":False,"trade_fresh":False,"anchor_eligible":False,"quote_status":"UNAVAILABLE","same_session_date":False,"age_minutes":np.nan,"split_ratio":np.nan,"split_date":None,"split_detected":False})

# Level-1 order book intentionally disabled. The user requested Level-2 only;
# until a genuine L2 feed is connected, no order-book signal is shown.

@st.cache_data(ttl=30, show_spinner=False)
def _top5_current_price_v63915(ticker):
    """Refresh a Top-5 price without ever calling an old session "current".

    CLOSED/PRE-OPEN markets are allowed to show an official close only when the
    Daily provider is current through the exchange's expected completed session.
    Otherwise the card explicitly reports stale price data and falls back to the
    scan snapshot only as a labelled historical reference.
    """
    logical=str(ticker or "").upper().strip()
    try:
        market=_market_for_ticker_v612(logical)
        detail=_market_status_detail_v612(market) or {}
        phase=str(detail.get('phase','UNKNOWN')).upper()
        expected=_expected_required_session_v63930(market)
    except Exception:
        market='';phase='UNKNOWN';expected=None
    try:
        q=dict(fetch_live_intraday_snapshot(logical,None) or {})
    except Exception:
        q={}

    def _quote_date(obj):
        try:
            raw=obj.get('timestamp')
            if raw is not None:
                ts=pd.Timestamp(raw)
                if ts.tzinfo is not None and market:
                    ts=ts.tz_convert(ZoneInfo(_market_timezone_v612(market)))
                return ts.date()
        except Exception:
            pass
        try:
            lab=str(obj.get('timestamp_label','') or '')
            if len(lab)>=10:
                return pd.Timestamp(lab[:10]).date()
        except Exception:
            pass
        return None

    # During an open/extended US session, a provider-verified current quote keeps priority.
    if phase in ('OPEN','PRE-MARKET','AFTER-MARKET') and q.get('display_current'):
        return q

    daily=None
    if fetch_ohlcv is not None:
        try:
            daily=fetch_ohlcv(logical,period='10d',interval='1d')
            if market:
                daily,_=_reconstruct_completed_daily_from_intraday_v63924(logical,daily,market)
        except Exception:
            daily=None
    fresh=_session_freshness_v63915(daily,market) if market else {'ok':False,'latest':None,'expected':expected,'status':'UNRESOLVED'}
    if isinstance(daily,pd.DataFrame) and not daily.empty and 'Close' in daily.columns:
        try:
            dd=daily.dropna(subset=['Close'])
            if not dd.empty:
                px=float(pd.to_numeric(dd['Close'],errors='coerce').dropna().iloc[-1])
                if np.isfinite(px) and px>0 and bool(fresh.get('ok')):
                    provider=(temporary_counter_info(logical) or {}).get('temporary_symbol',logical)
                    latest=fresh.get('latest')
                    return {
                        'price':px,'display_current':True,'fresh':False,'trade_fresh':False,
                        'provider_symbol':provider,
                        'timestamp_label':(str(latest)+' close') if latest else 'latest close',
                        'source':'Latest official Daily close','quote_status':'OFFICIAL CLOSE',
                        'same_session_date':bool(latest==expected),'age_minutes':np.nan,
                        'price_session_date':str(latest) if latest else None,
                        'expected_session_date':str(expected) if expected else None,
                        'freshness_status':fresh.get('status','CURRENT')
                    }
        except Exception:
            pass

    # If Daily is stale but another provider has a timestamp from the expected
    # completed session, it may be shown as delayed/current context, never trade-fresh.
    qd=_quote_date(q)
    if q.get('display_current') and expected is not None and qd is not None and qd>=expected:
        q=dict(q);q['trade_fresh']=False
        q['freshness_status']=f'CURRENT PROVIDER SESSION {qd}'
        q['expected_session_date']=str(expected);q['price_session_date']=str(qd)
        return q

    stale=dict(q)
    stale.update({
        'price':np.nan,'display_current':False,'fresh':False,'trade_fresh':False,
        'source':'STALE PRICE DATA',
        'quote_status':'STALE SESSION',
        'freshness_status':fresh.get('status','STALE SESSION'),
        'expected_session_date':str(expected) if expected else None,
        'price_session_date':str(fresh.get('latest')) if fresh.get('latest') else None,
    })
    return stale

frame_price_snapshot = getattr(qe, "frame_price_snapshot", lambda ticker,frame,max_age_minutes=60.0: {"price":np.nan,"timestamp_label":"—","fresh":False,"same_session_date":False,"age_minutes":np.nan,"source":"unavailable"})
resolve_current_market_snapshot = getattr(qe, "resolve_current_market_snapshot", lambda ticker,daily=None,hourly=None,m15=None,primary=None,market_open=False,market_phase=None,market_date=None: dict(primary or {}))
directional_volume_row = getattr(qe, "directional_volume_row", lambda r: {"magnitude":0.0,"bullish":0.0,"bearish":0.0,"label":"N/A","rvol":np.nan})
institutional_flow_row = getattr(qe, "institutional_flow_row", lambda r: {"score":0.0,"label":"NEUTRAL","components":[]})
exit_pressure_row = getattr(qe, "exit_pressure_row", lambda r: (0.0,[],"CLEAR"))
entry_score_row = getattr(qe, "entry_score_row", None)
setup_origin_validation_v619 = getattr(qe, "setup_origin_validation_v619", lambda m15_feat, target_pct=.02, stop_pct=.015, max_bars=16: pd.DataFrame())
setup_origin_validation_summary_v619 = getattr(qe, "setup_origin_validation_summary_v619", lambda events: pd.DataFrame())
setup_origin_validation_summary_v620 = getattr(qe, "setup_origin_validation_summary_v620", setup_origin_validation_summary_v619)
setup_origin_robustness_v620 = getattr(qe, "setup_origin_robustness_v620", lambda m15_feat: pd.DataFrame())
continuation_base_validation_v620 = getattr(qe, "continuation_base_validation_v620", lambda m15_feat, breakout_lookahead=8, target_pct=.02, stop_pct=.015, outcome_bars=16: pd.DataFrame())
continuation_base_validation_summary_v620 = getattr(qe, "continuation_base_validation_summary_v620", lambda events: pd.DataFrame())
continuation_base_validation_v621 = getattr(qe, "continuation_base_validation_v621", continuation_base_validation_v620)
continuation_base_validation_summary_v621 = getattr(qe, "continuation_base_validation_summary_v621", continuation_base_validation_summary_v620)
setup_origin_matched_baseline_v622 = getattr(qe, "setup_origin_matched_baseline_v622", lambda m15_feat, target_pct=.02, stop_pct=.015, max_bars=16: pd.DataFrame())
research_evidence_summary_v622 = getattr(qe, "research_evidence_summary_v622", lambda origin_summary, matched_baseline, robustness, continuation_summary: pd.DataFrame())
setup_origin_matched_confidence_v623 = getattr(qe, "setup_origin_matched_confidence_v623", lambda matched_baseline: pd.DataFrame())
setup_origin_session_pairs_v624 = getattr(qe, "setup_origin_session_pairs_v624", lambda m15_feat, target_pct=.02, stop_pct=.015, max_bars=16: pd.DataFrame())
cluster_bootstrap_matched_edge_v624 = getattr(qe, "cluster_bootstrap_matched_edge_v624", lambda pairs, n_boot=1200, seed=624: pd.DataFrame())
pre_move_stock_oos_v625 = getattr(qe, "pre_move_stock_oos_v625", lambda feat, target_pct=.05, horizon_days=3, discovery_fraction=.70: pd.DataFrame())
aggregate_pre_move_oos_v625 = getattr(qe, "aggregate_pre_move_oos_v625", lambda rows, min_discovery_signals=25, min_validation_signals=12, min_discovery_lift=1.20: pd.DataFrame())


# -----------------------------------------------------------------------------
# V5.5 robust dynamic-calibration fallback
# The dynamic layer is duplicated locally on purpose. If Streamlit ever serves an
# older cached quant_engine.py during a deploy, Analyze/Scanner/Backtest still work
# instead of stopping with an incompatibility error.
# -----------------------------------------------------------------------------
def _v544_clamp(x, lo=0.0, hi=100.0):
    try:
        return max(lo, min(hi, float(x)))
    except Exception:
        return lo


def _v544_component_dict(r, kind='early', min_turnover=0):
    comps = early_score_row(r)[1] if kind == 'early' else score_row(r, min_turnover)[1]
    return {name: (float(pts), float(mx)) for name, pts, mx in comps}


def _v544_calibrate_components(feat, kind='early', event_pct=.03, lookbacks=(1,2,3), min_turnover=0):
    f = feat.copy()
    if f is None or len(f) < 35:
        return {'events':0,'confidence':0.0,'multipliers':{},'table':pd.DataFrame()}
    event_ret = f['Close'].pct_change()
    events = [i for i in range(1,len(f)) if pd.notna(event_ret.iloc[i]) and float(event_ret.iloc[i]) >= float(event_pct) and abs(float(event_ret.iloc[i])) <= 0.60]
    sample_rel = min(1.0, math.sqrt(len(events)/30.0)) if events else 0.0
    baseline, maxima = {}, {}
    for _, r in f.iterrows():
        for name,(pts,mx) in _v544_component_dict(r,kind,min_turnover).items():
            maxima[name]=mx
            baseline.setdefault(name,[]).append(pts>0)
    rows=[]; multipliers={}
    for name,mx in maxima.items():
        pre=[]; seen=set(); by_lb={lb:[] for lb in lookbacks}
        for eno,i in enumerate(events):
            for lb in lookbacks:
                j=i-int(lb)
                if j<0: continue
                active=_v544_component_dict(f.iloc[j],kind,min_turnover).get(name,(0,mx))[0] > 0
                pre.append(active); by_lb[lb].append(active)
                if active: seen.add(eno)
        pre_rate=float(np.mean(pre)) if pre else np.nan
        base_rate=float(np.mean(baseline.get(name,[]))) if baseline.get(name) else np.nan
        lift=pre_rate/base_rate if np.isfinite(pre_rate) and np.isfinite(base_rate) and base_rate>0 else 1.0
        coverage=len(seen)/len(events) if events else 0.0
        lb_rates=[float(np.mean(v)) for v in by_lb.values() if v]
        stability=max(0.55,1.0-(float(np.std(lb_rates))/0.35)) if lb_rates else 0.55
        evidence=sample_rel*(0.55+0.45*coverage)*stability
        mult=float(np.clip(1.0 + evidence*(lift-1.0)*1.65,0.45,1.80))
        multipliers[name]=mult
        rows.append({'Component':name,'Base Weight':mx,'Dynamic Weight':mx*mult,'Lift x':lift,'Coverage %':coverage*100,'Sample Reliability %':sample_rel*100,'Stability %':stability*100,'Multiplier':mult})
    table=pd.DataFrame(rows)
    if not table.empty:
        table=table.sort_values(['Dynamic Weight','Lift x'],ascending=False).reset_index(drop=True)
    return {'events':len(events),'confidence':sample_rel*100,'multipliers':multipliers,'table':table}


def _v544_dynamic_score_row(r, calibration, kind='early', min_turnover=0):
    comps=_v544_component_dict(r,kind,min_turnover)
    mults=(calibration or {}).get('multipliers',{})
    num=den=0.0; details=[]
    for name,(pts,mx) in comps.items():
        m=float(mults.get(name,1.0)); dw=mx*m
        strength=(pts/mx) if mx>0 else 0.0
        num += strength*dw; den += dw
        details.append((name,pts,mx,dw,m))
    score=100.0*num/den if den>0 else 0.0
    return float(_v544_clamp(score)), details


def _v544_calibrate_combinations(feat,event_pct=.03,lookbacks=(1,2,3),min_turnover=0,top_n=12):
    f=feat.copy()
    if f is None or len(f)<35: return pd.DataFrame()
    er=f['Close'].pct_change()
    events=[i for i in range(1,len(f)) if pd.notna(er.iloc[i]) and float(er.iloc[i])>=float(event_pct)]
    if not events: return pd.DataFrame()
    def active_set(r):
        e={f'E:{n}' for n,(p,m) in _v544_component_dict(r,'early',min_turnover).items() if p>0}
        q={f'Q:{n}' for n,(p,m) in _v544_component_dict(r,'quant',min_turnover).items() if p>0}
        return e|q
    sets=[active_set(r) for _,r in f.iterrows()]
    names=sorted(set().union(*sets)) if sets else []
    pairs=[]
    for a_i,a in enumerate(names):
        for b in names[a_i+1:]:
            if a[0]==b[0]: continue
            base=np.mean([(a in ss and b in ss) for ss in sets])
            if base<=0: continue
            pre=[]; seen=set()
            for eno,i in enumerate(events):
                for lb in lookbacks:
                    j=i-int(lb)
                    if j<0: continue
                    on=a in sets[j] and b in sets[j]
                    pre.append(on)
                    if on: seen.add(eno)
            pr=np.mean(pre) if pre else 0.0
            lift=pr/base if base else np.nan
            cov=100*len(seen)/len(events)
            if np.isfinite(lift):
                pairs.append({'Combination':a[2:]+' + '+b[2:],'Lift x':lift,'Coverage %':cov,'Pre-event active %':100*pr,'Baseline active %':100*base})
    z=pd.DataFrame(pairs)
    if z.empty: return z
    return z.sort_values(['Lift x','Coverage %'],ascending=False).head(top_n).reset_index(drop=True)


def _v544_dynamic_scores(feat,event_pct=.03,min_turnover=0):
    r=feat.dropna(subset=['Close']).iloc[-1]
    ec=_v544_calibrate_components(feat,'early',event_pct,(1,2,3),min_turnover)
    qc=_v544_calibrate_components(feat,'quant',event_pct,(1,2,3),min_turnover)
    se=early_score_row(r)[0]; sq=score_row(r,min_turnover)[0]
    de,ed=_v544_dynamic_score_row(r,ec,'early',min_turnover)
    dq,qd=_v544_dynamic_score_row(r,qc,'quant',min_turnover)
    er=float(ec.get('confidence',0))/100.0; qr=float(qc.get('confidence',0))/100.0
    early_w=float(np.clip(.35+.10*(er-qr),.25,.45)); quant_w=1.0-early_w
    pred=quant_w*dq+early_w*de
    return {'static_early':se,'static_quant':sq,'dynamic_early':de,'dynamic_quant':dq,'final_prediction':float(_v544_clamp(pred)),'early_weight':early_w,'quant_weight':quant_w,'early_calibration':ec,'quant_calibration':qc,'combinations':_v544_calibrate_combinations(feat,event_pct,(1,2,3),min_turnover)}


def _v544_forward_outcomes(f,horizon,target_pct):
    highs=f['High'].to_numpy(dtype='float64'); lows=f['Low'].to_numpy(dtype='float64'); closes=f['Close'].to_numpy(dtype='float64')
    hit=np.full(len(f),np.nan); ret=np.full(len(f),np.nan); dd=np.full(len(f),np.nan)
    for i in range(len(f)-horizon):
        hit[i]=1.0 if np.nanmax(highs[i+1:i+1+horizon])>=closes[i]*(1+target_pct) else 0.0
        ret[i]=closes[i+horizon]/closes[i]-1.0
        dd[i]=np.nanmin(lows[i+1:i+1+horizon])/closes[i]-1.0
    return hit,ret,dd


def _v544_compare_static_dynamic_backtest(feat,horizon=5,target_pct=.03,score_threshold=66,min_turnover=0,train_fraction=.70):
    f=feat.copy().dropna(subset=['Close'])
    if len(f)<60:
        return {'static':{},'dynamic':{},'baseline':np.nan,'signal_lift_static':np.nan,'signal_lift_dynamic':np.nan,'train_rows':0,'test_rows':0}
    cut=max(35,min(len(f)-int(horizon)-10,int(len(f)*train_fraction)))
    train=f.iloc[:cut].copy()
    ec=_v544_calibrate_components(train,'early',target_pct,(1,2,3),min_turnover)
    qc=_v544_calibrate_components(train,'quant',target_pct,(1,2,3),min_turnover)
    hit,ret,dd=_v544_forward_outcomes(f,int(horizon),float(target_pct))
    rows=[]
    for i in range(cut,len(f)):
        if not np.isfinite(hit[i]): continue
        r=f.iloc[i]
        ss=score_row(r,min_turnover)[0]
        de,_=_v544_dynamic_score_row(r,ec,'early',min_turnover)
        dq,_=_v544_dynamic_score_row(r,qc,'quant',min_turnover)
        ew=float(np.clip(.35+.10*((ec.get('confidence',0)-qc.get('confidence',0))/100.0),.25,.45))
        pred=(1-ew)*dq+ew*de
        rows.append((ss,pred,hit[i],ret[i],dd[i]))
    if not rows:
        return {'static':{},'dynamic':{},'baseline':np.nan,'signal_lift_static':np.nan,'signal_lift_dynamic':np.nan,'train_rows':len(train),'test_rows':0}
    z=pd.DataFrame(rows,columns=['static','dynamic','hit','ret','dd']); baseline=float(z.hit.mean())
    def pack(col):
        v=z[z[col]>=score_threshold]; n=len(v)
        if not n: return {'n':0,'hits':0,'hit_rate':np.nan,'avg_return':np.nan,'max_drawdown':np.nan,'sample_reliability':0.0}
        return {'n':n,'hits':int(v.hit.sum()),'hit_rate':float(v.hit.mean()),'avg_return':float(v.ret.mean()),'max_drawdown':float(v.dd.min()),'sample_reliability':100*min(1.0,math.sqrt(n/60.0))}
    sb=pack('static'); db=pack('dynamic')
    return {'static':sb,'dynamic':db,'baseline':baseline,'signal_lift_static':(sb.get('hit_rate',np.nan)/baseline if baseline>0 and np.isfinite(sb.get('hit_rate',np.nan)) else np.nan),'signal_lift_dynamic':(db.get('hit_rate',np.nan)/baseline if baseline>0 and np.isfinite(db.get('hit_rate',np.nan)) else np.nan),'train_rows':len(train),'test_rows':len(z)}


def _balanced_stage2_candidates_v63948(stage,prefilter_top,mandatory_tickers=None):
    """SMART Deep selection with reserved anchors *inside* market quotas.

    V6.3.9.58 reserves US Core 51 / active signals / bridge names without letting
    those reserved names consume the entire cross-market discovery balance.
    Mandatory names are guaranteed, then each market is filled toward its normal
    55% / 30% / 15% total target. Only true mandatory overflow can exceed a
    market target.
    """
    if not stage:return []
    cap=max(5,min(int(prefilter_top),len(stage)))
    mandatory=set(str(x).upper().strip() for x in (mandatory_tickers or []) if str(x).strip())
    must=[x for x in stage if str(x[1]).upper().strip() in mandatory]
    must=sorted(must,key=lambda x:x[0],reverse=True)
    cap=max(cap,len(must))
    if cap>=len(stage):return sorted(stage,key=lambda x:x[0],reverse=True)
    used={x[1] for x in must}
    remaining=[x for x in stage if x[1] not in used]
    groups={}
    for item in remaining:
        m=_market_for_ticker_v612(item[1]);m='US' if m in ('NASDAQ','NYSE','US') else m
        groups.setdefault(m,[]).append(item)
    for g in groups.values():g.sort(key=lambda x:x[0],reverse=True)
    must_counts={}
    for item in must:
        m=_market_for_ticker_v612(item[1]);m='US' if m in ('NASDAQ','NYSE','US') else m
        must_counts[m]=must_counts.get(m,0)+1
    active=sorted(set(groups)|set(must_counts))
    if len(active)<=1:
        chosen=sorted(remaining,key=lambda x:x[0],reverse=True)[:max(0,cap-len(must))]
        return sorted(must+chosen,key=lambda x:x[0],reverse=True)[:cap]
    weights={'US':.55,'HONG KONG':.30,'TEL AVIV':.15}
    denom=sum(weights.get(m,.20) for m in active) or 1.0
    target={m:max(1,int(round(cap*weights.get(m,.20)/denom))) for m in active}
    # Reconcile rounding to the exact cap before applying mandatory floors.
    while sum(target.values())>cap:
        m=max(active,key=lambda x:target[x])
        if target[m]>1:target[m]-=1
        else:break
    while sum(target.values())<cap:
        m=max(active,key=lambda x:weights.get(x,.20))
        target[m]+=1
    for m,c in must_counts.items():target[m]=max(target.get(m,0),c)
    # Mandatory overflow is allowed, but reduce only non-mandatory headroom first.
    while sum(target.values())>cap:
        reducible=[m for m in active if target[m]>max(1,must_counts.get(m,0))]
        if not reducible:break
        m=max(reducible,key=lambda x:target[x]-max(1,must_counts.get(x,0)))
        target[m]-=1
    chosen=[];chosen_ids=set()
    for m in active:
        need=max(0,target.get(m,0)-must_counts.get(m,0))
        for item in groups.get(m,[])[:need]:
            chosen.append(item);chosen_ids.add(item[1])
    if len(must)+len(chosen)<cap:
        for item in sorted(remaining,key=lambda x:x[0],reverse=True):
            if item[1] in chosen_ids:continue
            chosen.append(item);chosen_ids.add(item[1])
            if len(must)+len(chosen)>=cap:break
    return sorted(must+chosen,key=lambda x:x[0],reverse=True)[:cap]

def _v544_scan_universe_dynamic(tickers,daily_period='6mo',use_hourly=True,hourly_period='1mo',horizon=5,target_pct=.03,min_turnover=0,buy_threshold=66,prefilter_top=30,progress_callback=None,optimizer_model=None,mandatory_deep_tickers=None):
    stage=[]
    skipped=[]
    for scan_i,ticker in enumerate(tickers,1):
        if progress_callback:
            progress_callback('stage1',scan_i,len(tickers),ticker)
        try:
            d=fetch_ohlcv(ticker,daily_period,'1d')
            if d is None or len(d)<35:
                skipped.append({'Ticker':ticker,'Stage':'Daily','Reason':'Insufficient daily data'})
                continue
            _daily_recon={'used':False,'source':'PROVIDER DAILY','status':'NO RECONSTRUCTION','bars':0}
            try:
                d,_daily_recon=_reconstruct_completed_daily_from_intraday_v63924(ticker,d,_market_for_ticker_v612(ticker))
            except Exception:
                pass
            f=compute_features(d); ds=_v544_dynamic_scores(f,target_pct,min_turnover)
            pre=.85*ds['final_prediction']+.15*(.72*ds['static_quant']+.28*ds['static_early'])
            # V6.3.9.56 selective PRE-MOVE priority. This affects ONLY which
            # Stage-0 names receive expensive Deep Analysis. It does not create an
            # Entry signal and does not bypass OOS/Entry/R:R/Chase safety gates.
            _pre_acc=pre_breakout_accumulation(f)
            _pre_acc_score=float(_pre_acc.get('score',0) or 0)
            _pre_acc_stage=str(_pre_acc.get('stage','') or '').upper()
            try:_pre_acc_move=float(_pre_acc.get('recent_price_move_pct',np.nan))
            except Exception:_pre_acc_move=np.nan
            _pre_acc_confirmed=bool(_pre_acc.get('confirmed_pre_move',False))
            _pre_acc_watch=bool(_pre_acc_stage=='PRE-MOVE WATCH')
            # V6.3.9.56: raw accumulation remains visible for audit, but only a
            # multi-family confirmed signal (or a strong WATCH) earns Deep priority.
            _pre_acc_priority=bool(_pre_acc_confirmed and (not np.isfinite(_pre_acc_move) or _pre_acc_move<8.0))
            opt_pre=np.nan
            if optimizer_model:
                rr=f.dropna(subset=['Close']).iloc[-1]; q0=float(ds.get('dynamic_quant',ds.get('static_quant',50))); e0=_entry_score_from_row(rr,q0,float(ds.get('dynamic_early',50))); rf=_entry_research_features_v612(rr,q0,e0)
                inst=institutional_flow_row(rr); tmp={'Ticker':ticker,'DailySetupCheck':rf.get('DailySetup'),'FreshSignalCheck':rf.get('FreshSignal'),'VolumeFlowCheck':rf.get('VolumeFlow'),'NoChaseCheck':rf.get('NoChase'),'EntryScore':e0,'DynamicQuant':q0,'ExitPressure':rf.get('ExitPressureAtSignal',50),'InstitutionalFlowScore':inst.get('score',0),'DailyRobustRVOL':rr.get('robust_volume_ratio',np.nan),'ADX14':rr.get('adx14',np.nan),'VolumeAccel':rr.get('vol_accel',np.nan),'FreshTransitionCount':rr.get('fresh_transition_count',0)}
                opt_pre,_,_=_optimized_score_from_row_v612(tmp,optimizer_model,ticker)
                if np.isfinite(opt_pre):
                    pre=.82*opt_pre+.18*float(ds['final_prediction'])
                elif _hourly_model_for_ticker_v613(optimizer_model,ticker)[0]:
                    # V6.3.9.46 hourly-only OOS: retain the Production daily
                    # prefilter until intraday features are available in stage 2.
                    pass
                else:
                    pre=-1e6  # no eligible Daily or Hourly OOS support for this market
            if _pre_acc_priority:
                # HIGH-CONFIDENCE PRE-MOVE: reserve enough prefilter strength to
                # survive SMART depth selection, without changing final trade scores.
                _acc_prefilter=min(96.0,82.0+0.16*_pre_acc_score)
                pre=max(float(pre),float(_acc_prefilter))
            elif _pre_acc_watch and _pre_acc_score>=60 and (not np.isfinite(_pre_acc_move) or _pre_acc_move<8.0):
                # WATCH receives a moderate nudge, not a guaranteed Deep slot.
                pre=max(float(pre),min(84.0,68.0+0.16*_pre_acc_score))
            stage.append((pre,ticker,f,ds,opt_pre,_daily_recon))
        except Exception as e:
            skipped.append({'Ticker':ticker,'Stage':'Daily','Reason':f'{type(e).__name__}: {str(e)[:140]}'})
            continue
    if not stage:
        out=pd.DataFrame(); out.attrs['scan_meta']={'requested':len(tickers),'daily_success':0,'finalists':0,'deep_success':0,'skipped':skipped,'daily_success_tickers':[],'deep_selected_tickers':[],'deep_success_tickers':[]}
        return out
    daily_success=len(stage)
    daily_success_tickers=[x[1] for x in stage]
    stage.sort(key=lambda x:x[0],reverse=True)
    stage=_balanced_stage2_candidates_v63948(stage,prefilter_top,mandatory_deep_tickers)
    deep_selected_tickers=[x[1] for x in stage]
    rows=[]
    for deep_i,(pre,ticker,f,ds,opt_pre,_daily_recon) in enumerate(stage,1):
        if progress_callback:
            progress_callback('stage2',deep_i,len(stage),ticker)
        try:
            hfeat=m15feat=None; h=m15=None; hq=he=np.nan
            ca_report={'split_adjusted':False,'data_quality':'OK','details':[]}
            _bridge_split={}
            if use_hourly:
                h=confirmed_intraday_bars(fetch_ohlcv(ticker,hourly_period,'1h'))
                m15=confirmed_intraday_bars(fetch_ohlcv(ticker,'1mo','15m'))
                _bridge_split=temporary_counter_info(ticker,(_market_status_detail_v612(_market_for_ticker_v612(ticker)) or {}).get('local_date')) or {}
                _,h,m15,ca_report=normalize_cross_timeframes(f,h,m15,split_ratio=_bridge_split.get('subdivision_ratio',np.nan),split_date=_bridge_split.get('start_date'))
                if h is not None and len(h)>=30:
                    hfeat=compute_features(h,True); hr=hfeat.dropna(subset=['Close']).iloc[-1]
                    hq,_=_v544_dynamic_score_row(hr,ds['quant_calibration'],'quant',0)
                    he,_=_v544_dynamic_score_row(hr,ds['early_calibration'],'early',0)
                if m15 is not None and len(m15)>=30: m15feat=compute_features(m15,True)
            dq=ds['dynamic_quant'] if not np.isfinite(hq) else .78*ds['dynamic_quant']+.22*hq
            de=ds['dynamic_early'] if not np.isfinite(he) else .70*ds['dynamic_early']+.30*he
            ew=ds['early_weight']; pred=(1-ew)*dq+ew*de
            market_regime=_market_regime_v610(ticker)
            cmp=_v544_compare_static_dynamic_backtest(f,horizon,target_pct,buy_threshold,min_turnover)
            db=cmp.get('dynamic',{})
            conf=float(ds['early_calibration'].get('confidence',0)+ds['quant_calibration'].get('confidence',0))/2.0
            daily_lr=f.dropna(subset=['Close']).iloc[-1]
            live_f=f.copy()
            if hfeat is not None and len(hfeat):
                try:
                    hr_live=hfeat.dropna(subset=['Close']).iloc[-1]; rv_live=float(hr_live.get('time_adjusted_rvol',np.nan))
                    if np.isfinite(rv_live):
                        live_f.loc[live_f.index[-1],'robust_volume_ratio']=rv_live; live_f.loc[live_f.index[-1],'volume_ratio']=rv_live
                except Exception:pass
            lr=live_f.dropna(subset=['Close']).iloc[-1]
            market_scan=_market_for_ticker_v612(ticker)
            phase_detail_scan=_market_status_detail_v612(market_scan)
            phase_scan=phase_detail_scan.get('phase','UNKNOWN')
            session_fresh=_session_freshness_v63915(f,market_scan)
            session_data_fresh=bool(session_fresh.get('ok',False))
            if bool((_daily_recon or {}).get('used')) and session_data_fresh:
                session_fresh=dict(session_fresh);session_fresh['status']=str(_daily_recon.get('status') or session_fresh.get('status'))
            ps15=frame_price_snapshot(ticker,m15,45.0);ps1h=frame_price_snapshot(ticker,h,110.0)
            ps=ps15 if ps15.get('fresh') else (ps1h if ps1h.get('fresh') else None)
            # During an OPEN local cash session, a confirmed same-date intraday bar
            # can verify today's session even if the Daily endpoint has not printed
            # its partial candle yet. After the close, completed Daily/reconstruction
            # must match the exact expected session date.
            if phase_scan=='OPEN' and ps is not None and bool(ps.get('same_session_date',False)):
                session_data_fresh=True
                session_fresh=dict(session_fresh)
                session_fresh['status']=f"CURRENT VIA INTRADAY • {phase_detail_scan.get('local_date')} • Daily {session_fresh.get('latest') or '—'}"
            liveq=None
            # Keep the full 151-stock scan light: only invoke the richer current-quote
            # fallback for a deep-analysis finalist when 15m/1H cannot supply today's price.
            if phase_scan=='OPEN' and ps is None:
                try:liveq=fetch_live_intraday_snapshot(ticker,f)
                except Exception:liveq=None
            if liveq and liveq.get('display_current') and np.isfinite(float(liveq.get('price',np.nan))):
                intraday_price=float(liveq.get('price'));display_price=intraday_price
                live_price_fresh=bool(liveq.get('trade_fresh'))
                price_source=str(liveq.get('source','current/delayed fallback'))
                price_timestamp=str(liveq.get('timestamp_label','—'))
                if phase_scan=='OPEN' and bool(liveq.get('trade_fresh')) and bool(liveq.get('same_session_date',False)):
                    session_data_fresh=True
                    session_fresh=dict(session_fresh);session_fresh['status']=f"CURRENT VIA LIVE PROVIDER • {phase_detail_scan.get('local_date')}"
            else:
                # CLOSED/PRE-OPEN is never "live fresh". The Daily reference can still
                # be a valid official close, but only when it reaches the expected
                # completed exchange session.
                live_price_fresh=bool(ps is not None) if phase_scan=='OPEN' else False
                intraday_price=float(ps.get('price',np.nan)) if ps is not None and np.isfinite(float(ps.get('price',np.nan))) else np.nan
                display_price=intraday_price if np.isfinite(intraday_price) else float(lr['Close'])
                if ps is not None:
                    price_source='15m current-session confirmed bar' if ps is ps15 else '1H current-session confirmed bar'
                    price_timestamp=ps.get('timestamp_label','—')
                else:
                    price_source='Latest official Daily close' if session_data_fresh else 'STALE Daily reference'
                    _ld=session_fresh.get('latest')
                    price_timestamp=(str(_ld)+' close') if _ld else '—'
            if not session_data_fresh:
                ca_report=dict(ca_report)
                ca_report['data_quality']='STALE_SESSION'
                ca_report.setdefault('details',[])
                ca_report['details']=list(ca_report.get('details') or [])+[str(session_fresh.get('status','STALE SESSION'))]
            _scan_prev_close=np.nan
            if liveq and np.isfinite(float((liveq or {}).get('prev_close',np.nan))):_scan_prev_close=float(liveq.get('prev_close'))
            elif len(f)>=2:
                try:_scan_prev_close=float(f.dropna(subset=['Close']).iloc[-2]['Close'])
                except Exception:_scan_prev_close=np.nan
            # V6.3.9.56: temporary/reopened HK counters must compare current price
            # with the SAME provider counter's previous close. This also works on
            # weekends/holidays by anchoring the provider lookup to the latest
            # completed Daily session rather than the calendar date.
            if _bridge_split:
                try:
                    _active_ref=pd.Timestamp(f.dropna(subset=['Close']).index[-1]).date()
                    _provider_sym=market_data_symbol(ticker,_active_ref)
                    _pc,_pc_date,_pc_src=provider_reference_close(_provider_sym,_active_ref,display_price,_bridge_split.get('subdivision_ratio',np.nan))
                    if np.isfinite(float(_pc)) and float(_pc)>0:
                        _scan_prev_close=float(_pc)
                        ca_report=dict(ca_report);ca_report.setdefault('details',[]);ca_report['details']=list(ca_report.get('details') or [])+[f'Session reference: {_provider_sym} {_pc_src}']
                except Exception:pass
            ent=entry_timing(f,dq,de,hourly_feat=hfeat,m15_feat=m15feat,current_price=display_price,market_regime=market_regime,previous_close=_scan_prev_close,market_phase=phase_scan,market_date=phase_detail_scan.get('local_date'))
            ca_report,ent=_split_plan_integrity_guard_v63949(ca_report,ent,display_price,_bridge_split.get('subdivision_ratio',np.nan),ticker)
            if str(ca_report.get('data_quality','OK'))!='OK':
                ent=dict(ent);ent.update({'plan_valid':False,'plan_reason':'Blocked by cross-timeframe data-quality gate','trigger_state':'WAIT','status':'WAIT','zone_low':np.nan,'zone_high':np.nan,'trigger':np.nan,'invalidation':np.nan,'target1':np.nan,'target2':np.nan})
            if optimizer_model:
                ent,(hopt_score,hopt_match,hopt_status,hopt_horizon)=_apply_hourly_oos_entry_v63945(ent,ticker,hfeat,optimizer_model)
            else:
                hopt_score,hopt_match,hopt_status,hopt_horizon=np.nan,np.nan,'NO ELIGIBLE HOURLY MODEL','—'
            ex=explosive_latest(live_f,hfeat) if callable(explosive_latest) else {}
            timing=signal_timing_latest(live_f,hfeat) if callable(signal_timing_latest) else {}
            latest_live=score_latest(live_f,0); latest_live['price']=display_price
            rows.append({'Ticker':ticker,'Prediction':round(pred,1),'DynamicQuant':round(dq,1),'DynamicEarly':round(de,1),'StaticQuant':round(ds['static_quant'],1),'StaticEarly':round(ds['static_early'],1),'EntryScore':ent['entry_score'],'LiveActionabilityScore':ent.get('live_actionability_score',ent.get('entry_score',0)),'SetupEntryScore':ent.get('setup_entry_score_pre_chase',ent.get('entry_score',0)),'EntryStatus':ent['status'],'EntryTriggerState':ent.get('trigger_state',ent.get('status','WAIT')),'EntryConfirmationPct':ent.get('confirmation_pct',0),'EntryConfirmedConditions':ent.get('confirmed_conditions',0),'EntryTotalConditions':ent.get('total_conditions',6),'DailySetupCheck':ent.get('daily_setup',False),'FreshSignalCheck':ent.get('fresh_signal',False),'HourlyEntryCheck':ent.get('hourly_entry_ok',False),'VolumeFlowCheck':ent.get('volume_flow_ok',False),'NoChaseCheck':ent.get('no_chase',False),'RawNoChaseCheck':ent.get('raw_no_chase',ent.get('no_chase',False)),'NoChaseConsistencyOverride':ent.get('no_chase_consistency_override',False),'NoChaseReason':ent.get('no_chase_reason',''),'ExtensionGuardCheck':ent.get('extension_guard_ok',True),'ChaseRiskScore':ent.get('chase_risk_score',0),'ChaseRiskLabel':ent.get('chase_risk_label','LOW'),'SessionMovePct':ent.get('session_move_pct',np.nan),'MoveBeforeTriggerPct':ent.get('move_before_trigger_pct',np.nan),'SessionMoveATR':ent.get('session_move_atr',np.nan),'SessionMovePercentile':ent.get('session_move_percentile',np.nan),'SinceTriggerPct':ent.get('since_trigger_pct',np.nan),'GapPct':ent.get('gap_pct',np.nan),'VWAPDistanceATR':ent.get('vwap_distance_atr',np.nan),'EMA9DistanceATR':ent.get('ema9_distance_atr',np.nan),'EMA20DistanceATR':ent.get('ema20_distance_atr',np.nan),'Target1ProgressPct':ent.get('target1_progress_pct',np.nan),'LiveRR_T1':ent.get('live_rr_t1',np.nan),'LiveRR_T2':ent.get('live_rr_t2',np.nan),'LiveRRGuardOK':ent.get('live_rr_guard_ok',True),'CarryoverExtension':ent.get('carryover_extension',False),'CarryoverHardVeto':ent.get('carryover_hard_veto',False),'PriorSessionMovePct':ent.get('prior_session_move_pct',np.nan),'CarryoverRetentionPct':ent.get('carryover_retention_pct',np.nan),'NextSessionCarryoverCandidate':ent.get('next_session_carryover_candidate',False),'NextSessionCarryoverHardCandidate':ent.get('next_session_carryover_hard_candidate',False),'NextSessionCarryoverReason':ent.get('next_session_carryover_reason',''),'OriginToTriggerPct':ent.get('origin_to_trigger_pct',np.nan),'TriggerLagMinutes':ent.get('trigger_lag_minutes',np.nan),'TriggerLagATR':ent.get('trigger_lag_atr',np.nan),'MoveConsumedBeforeTriggerPct':ent.get('move_consumed_before_trigger_pct',np.nan),'PreBreakoutAccumulationScore':ent.get('pre_breakout_accumulation_score',0.0),'PreBreakoutAccumulationStage':ent.get('pre_breakout_accumulation_stage','NO CURRENT ACCUMULATION SETUP'),'PreBreakoutAccumulationReason':ent.get('pre_breakout_accumulation_reason',''),'PreMoveConfirmed':ent.get('pre_move_confirmed',False),'PreMoveConfidenceTier':ent.get('pre_move_confidence_tier','NONE'),'PreMoveFamilyCount':ent.get('pre_move_family_count',0),'PreMoveFamilySignature':ent.get('pre_move_family_signature','NONE'),'PreMoveBaselineGuardOK':ent.get('pre_move_baseline_guard_ok',False),'PreMoveBaselineVolume':ent.get('pre_move_baseline_volume',np.nan),'PreMoveBaselineTurnover':ent.get('pre_move_baseline_turnover',np.nan),'EffectiveVolumeShockRatio':ent.get('effective_volume_shock_ratio',np.nan),'PreMoveShockRecoveryOK':ent.get('pre_move_shock_recovery_ok',False),'PreMoveFlowConfirmation':ent.get('pre_move_flow_confirmation',False),'PreMoveMomentumConfirmation':ent.get('pre_move_momentum_confirmation',False),'VolumeRegimeRatio':ent.get('volume_regime_ratio',np.nan),'VolumeShockRatio':ent.get('volume_shock_ratio',np.nan),'VolumeShockDate':ent.get('volume_shock_date','—'),'VolumeShockReturnPct':ent.get('volume_shock_return_pct',np.nan),'AbsorptionCandidate':ent.get('absorption_candidate',False),'VolumePersistenceRatio':ent.get('volume_persistence_ratio',np.nan),'PriceRetentionSinceVolumeShockPct':ent.get('price_retention_since_volume_shock_pct',np.nan),'PreBreakoutHigherLowCount':ent.get('pre_breakout_higher_low_count',0),'PreBreakoutRegimeShift':ent.get('pre_breakout_regime_shift',False),'RecentRunPct':ent.get('recent_run_pct',np.nan),'RecentRunATR':ent.get('recent_run_atr',np.nan),'RecentRunWindow':ent.get('recent_run_window','—'),'RecentRunLabel':ent.get('recent_run_label','NO DATA'),'PostTriggerConsumedPct':ent.get('post_trigger_consumed_pct',np.nan),'PostTriggerConsumedLabel':ent.get('post_trigger_consumed_label','NO DATA'),'RecentRunRetestContext':ent.get('recent_run_retest_context',False),'TriggerEfficiencyLabel':ent.get('trigger_efficiency_label','NO DATA'),'TimingConsumedHardBlock':ent.get('timing_consumed_hard_block',False),'TimingDataComplete':ent.get('timing_data_complete',True),'TimingDataSource':ent.get('timing_data_source','NOT REQUIRED'),'TimingDataReason':ent.get('timing_data_reason',''),'VolumeTrend':ent.get('volume_trend','NO DATA'),'VolumeTrend15m':ent.get('volume_trend_15m','NO DATA'),'VolumeTrend1H':ent.get('volume_trend_1h','NO DATA'),'MomentumState':ent.get('momentum_state','NO DATA'),'MomentumState15m':ent.get('momentum_state_15m','NO DATA'),'MomentumState1H':ent.get('momentum_state_1h','NO DATA'),'PostSpikeState':ent.get('post_spike_state','NO DATA'),'PostSpikeDistributionRisk':ent.get('post_spike_distribution_risk','NO DATA'),'ContinuationBaseCandidate':ent.get('continuation_base_candidate',False),'ContinuationBaseStatus':ent.get('continuation_base_status','RESEARCH • NO BASE'),'ContinuationBaseQuality':ent.get('continuation_base_quality','NO DATA'),'ContinuationSessionPeak':ent.get('continuation_session_peak',np.nan),'ContinuationBreakoutTrigger':ent.get('continuation_breakout_trigger',np.nan),'ContinuationBreakoutReference':ent.get('continuation_breakout_reference','—'),'BreakoutContinuationActionable':ent.get('breakout_continuation_actionable',False),'BreakoutContinuationTrigger':ent.get('breakout_continuation_trigger',np.nan),'BreakoutContinuationVolumeOK':ent.get('breakout_continuation_volume_ok',False),'BreakoutContinuationMomentumOK':ent.get('breakout_continuation_momentum_ok',False),'BreakoutContinuationFlowOK':ent.get('breakout_continuation_flow_ok',False),'ContinuationEntryState':ent.get('continuation_entry_state','N/A'),'ContinuationEntryWatch':ent.get('continuation_entry_watch',False),'ContinuationEntryReady':ent.get('continuation_entry_ready',False),'ContinuationEntryReason':ent.get('continuation_entry_reason',''),'ContinuationLiveRVOL':ent.get('continuation_live_rvol',np.nan),'ContinuationVolumeState':ent.get('continuation_volume_state','NO DATA'),'ContinuationFadingStrongOverride':ent.get('continuation_fading_strong_override',False),'ContinuationDistributionState':ent.get('continuation_distribution_state','NO DATA'),'ContinuationDistributionSoftOverride':ent.get('continuation_distribution_soft_override',False),'ContinuationBearishDistributionConfirmed':ent.get('continuation_bearish_distribution_confirmed',False),'ContinuationProgressOK':ent.get('continuation_progress_ok',False),'ContinuationTimingOK':ent.get('continuation_timing_ok',False),'ContinuationRROK':ent.get('continuation_rr_ok',False),'ContinuationDistributionOK':ent.get('continuation_distribution_ok',False),'SetupOriginPrice':ent.get('setup_origin_price',np.nan),'SetupOriginTime':ent.get('setup_origin_time','—'),'MoveBeforeSetupOriginPct':ent.get('move_before_setup_origin_pct',np.nan),'SinceSetupOriginPct':ent.get('since_setup_origin_pct',np.nan),'TriggerAnchorPrice':ent.get('trigger_anchor_price',np.nan),'TriggerAnchorTime':ent.get('trigger_anchor_time','—'),'TriggerAnchorBarStartTime':ent.get('trigger_anchor_bar_start_time','—'),'TriggerAnchorTimeframe':ent.get('trigger_anchor_timeframe','—'),'TriggerAnchorQuality':ent.get('trigger_anchor_quality','NONE'),'TriggerAnchorAgeBars':ent.get('trigger_anchor_age_bars',np.nan),'RetestZoneLow':ent.get('retest_zone_low',np.nan),'RetestZoneHigh':ent.get('retest_zone_high',np.nan),'PullbackNeededPct':ent.get('pullback_needed_pct',np.nan),'RetestStatus':ent.get('retest_status','—'),'RetestEntryLow':ent.get('retest_entry_low',np.nan),'RetestEntryHigh':ent.get('retest_entry_high',np.nan),'RetestInvalidation':ent.get('retest_invalidation',np.nan),'RetestTarget1':ent.get('retest_target1',np.nan),'RetestTarget2':ent.get('retest_target2',np.nan),'RetestRR_T1':ent.get('retest_rr_t1',np.nan),'RetestRR_T2':ent.get('retest_rr_t2',np.nan),'RetestPlanValid':ent.get('retest_plan_valid',False),'RetestPlanReason':ent.get('retest_plan_reason',''),'RecommendedAction':ent.get('recommended_action',''),'SetupConfirmed':ent.get('setup_confirmed',False),'EntryZoneCheck':ent.get('entry_zone_check',False),'RetestActionable':ent.get('retest_actionable',False),'PriceActionableNow':ent.get('price_actionable_now',False),'RRActionable':ent.get('rr_actionable',False),'ConfirmedEntryGateOK':ent.get('confirmed_entry_gate_ok',False),'EntryDistancePct':ent.get('entry_distance_pct',np.nan),'ActionabilityMissing':ent.get('actionability_missing','None'),'MarketRegime':ent.get('market_regime','NEUTRAL'),'MarketRegimeCheck':ent.get('market_regime_ok',True),'EntryWhyNow':ent.get('why_now',''),'EntryMissingChecks':ent.get('missing_checks',''),'EntryLow':round(float(ent.get('zone_low',np.nan)),4) if np.isfinite(float(ent.get('zone_low',np.nan))) else np.nan,'EntryHigh':round(float(ent.get('zone_high',np.nan)),4) if np.isfinite(float(ent.get('zone_high',np.nan))) else np.nan,'BreakoutTrigger':round(float(ent.get('trigger',np.nan)),4) if np.isfinite(float(ent.get('trigger',np.nan))) else np.nan,'Invalidation':round(float(ent.get('invalidation',np.nan)),4) if np.isfinite(float(ent.get('invalidation',np.nan))) else np.nan,'Target1':round(float(ent.get('target1',np.nan)),4) if np.isfinite(float(ent.get('target1',np.nan))) else np.nan,'Target2':round(float(ent.get('target2',np.nan)),4) if np.isfinite(float(ent.get('target2',np.nan))) else np.nan,'ExplosiveScore':ex.get('score',np.nan),'ExplosiveStage':ex.get('stage','—'),'MoveScore':timing.get('move_score',np.nan),'Accel1D':timing.get('accel_1d',np.nan),'Accel2D':timing.get('accel_2d',np.nan),'Accel3D':timing.get('accel_3d',np.nan),'Rising3D':timing.get('rising_3d',False),'TimingStage':timing.get('timing_stage','—'),'HourlyConfirm':ex.get('hourly_confirmation',np.nan),'P5_5D':ex.get('p5_5d',np.nan),'P10_5D':ex.get('p10_5d',np.nan),'P15_5D':ex.get('p15_5d',np.nan),'P15_5D_N':ex.get('p15_5d_n',0),'RobustRVOL':ex.get('robust_volume_ratio',np.nan),'Retention':ex.get('post_impulse_retention',np.nan),'DryUp':ex.get('volume_dryup',np.nan),'ReExpansion':ex.get('volume_reexpansion',np.nan),'SignalLift':round(cmp.get('signal_lift_dynamic',np.nan),2) if np.isfinite(cmp.get('signal_lift_dynamic',np.nan)) else np.nan,'CalibrationConfidence':round(conf,1),'BacktestN':int(db.get('n',0) or 0),'EmpiricalHitRate':round(float(db.get('hit_rate'))*100,1) if db.get('n',0) and np.isfinite(db.get('hit_rate',np.nan)) else np.nan,'Price':round(float(display_price),4),'LivePriceFresh':live_price_fresh,'SessionDataFresh':session_data_fresh,'SessionReconstructed':bool((_daily_recon or {}).get('used')),'SessionReconstructionSource':str((_daily_recon or {}).get('source','PROVIDER DAILY')),'PriceSessionDate':str(session_fresh.get('latest')) if session_fresh.get('latest') else None,'ExpectedSessionDate':str(session_fresh.get('expected')) if session_fresh.get('expected') else None,'PriceFreshnessStatus':session_fresh.get('status','UNRESOLVED'),'SessionCalendarSource':session_fresh.get('calendar_source',('HKEX LOCAL CASH MARKET (NOT STOCK CONNECT)' if market_scan=='HONG KONG' else f'{market_scan} LOCAL EXCHANGE CALENDAR')),'SessionCalendarReason':session_fresh.get('calendar_reason','LOCAL CASH-MARKET HOLIDAYS ONLY'),'SessionFreshnessVerified':bool(session_data_fresh),'PriceSource':price_source,'PriceTimestamp':price_timestamp,'VolumeRatio':round(float(lr.get('volume_ratio',np.nan)),2) if np.isfinite(float(lr.get('volume_ratio',np.nan))) else np.nan,'IntradayCumulativeRVOL':round(float((m15feat.dropna(subset=['Close']).iloc[-1].get('intraday_cum_rvol',np.nan) if m15feat is not None and len(m15feat) else (hfeat.dropna(subset=['Close']).iloc[-1].get('intraday_cum_rvol',np.nan) if hfeat is not None and len(hfeat) else np.nan))),2) if np.isfinite(float((m15feat.dropna(subset=['Close']).iloc[-1].get('intraday_cum_rvol',np.nan) if m15feat is not None and len(m15feat) else (hfeat.dropna(subset=['Close']).iloc[-1].get('intraday_cum_rvol',np.nan) if hfeat is not None and len(hfeat) else np.nan)))) else np.nan,'LiveIntradayRVOL':round(float(hfeat.dropna(subset=['Close']).iloc[-1].get('time_adjusted_rvol',np.nan)),2) if hfeat is not None and len(hfeat) and np.isfinite(float(hfeat.dropna(subset=['Close']).iloc[-1].get('time_adjusted_rvol',np.nan))) else np.nan,'FullSessionRVOL':round(float(daily_lr.get('volume_ratio',np.nan)),2) if np.isfinite(float(daily_lr.get('volume_ratio',np.nan))) else np.nan,'DailyRobustRVOL':round(float(daily_lr.get('robust_volume_ratio',np.nan)),2) if np.isfinite(float(daily_lr.get('robust_volume_ratio',np.nan))) else np.nan,'TimeAdjustedRVOL':round(float((hfeat.dropna(subset=['Close']).iloc[-1].get('time_adjusted_rvol',np.nan) if hfeat is not None and len(hfeat) else daily_lr.get('robust_volume_ratio',np.nan))),2) if np.isfinite(float((hfeat.dropna(subset=['Close']).iloc[-1].get('time_adjusted_rvol',np.nan) if hfeat is not None and len(hfeat) else daily_lr.get('robust_volume_ratio',np.nan)))) else np.nan,'VolumeContext':latest_live.get('volume_context','N/A'),'BullishVolumeEvidence':latest_live.get('bullish_volume_evidence',np.nan),'BearishVolumeEvidence':latest_live.get('bearish_volume_evidence',np.nan),'ExitPressure':timing.get('exit_pressure',latest_live.get('exit_pressure',np.nan)),'ExitStage':timing.get('exit_stage',latest_live.get('exit_stage','CLEAR')),'PlanValid':bool(ent.get('plan_valid',False)),'PlanReason':ent.get('plan_reason',''),'SplitAdjusted':bool(ca_report.get('split_adjusted',False)),'DataQuality':str(ca_report.get('data_quality','OK')),'RSI14':round(float(lr.get('rsi14',np.nan)),1) if np.isfinite(float(lr.get('rsi14',np.nan))) else np.nan,'ADX14':round(float(lr.get('adx14',np.nan)),1) if np.isfinite(float(lr.get('adx14',np.nan))) else np.nan,'VolumeAccel':round(float(lr.get('vol_accel',np.nan)),3) if np.isfinite(float(lr.get('vol_accel',np.nan))) else np.nan,'FreshTransitionCount':float(lr.get('fresh_transition_count',0) or 0),'InstitutionalFlowScore':latest_live.get('institutional_flow_score',np.nan),'InstitutionalFlowLabel':latest_live.get('institutional_flow_label','NEUTRAL'),'HourlyOptimizedScore':hopt_score,'HourlyOptimizedMatchPct':hopt_match,'HourlyOptimizedStatus':hopt_status,'HourlyOptimizedHorizon':hopt_horizon,'HourlyTimingSource':ent.get('hourly_timing_source','BASE TIMING'),'HourlyOOSTimingScore':ent.get('hourly_entry_score',np.nan),'HourlyOOSModelID':ent.get('hourly_oos_model_id','—'),'HourlyOOSScope':ent.get('hourly_oos_scope','—'),'HourlyOOSFold4Lift':ent.get('hourly_oos_fold4_lift',np.nan),'OptimizedPrefilterScore':opt_pre})
            rows[-1].update(_liquidity_profile_v63964(f,ticker))
        except Exception as e:
            skipped.append({'Ticker':ticker,'Stage':'Deep','Reason':f'{type(e).__name__}: {str(e)[:140]}'})
            continue
    out=pd.DataFrame(rows).sort_values(['Prediction','DynamicEarly','EntryScore'],ascending=False).reset_index(drop=True) if rows else pd.DataFrame()
    out.attrs['scan_meta']={'requested':len(tickers),'daily_success':daily_success,'finalists':len(stage),'deep_success':len(rows),'skipped':skipped,'daily_success_tickers':daily_success_tickers,'deep_selected_tickers':deep_selected_tickers,'deep_success_tickers':[str(r.get('Ticker')) for r in rows]}
    return out

# Prefer engine implementations when present; otherwise use the verified local copy.
dynamic_scores = dynamic_scores if callable(dynamic_scores) else _v544_dynamic_scores
compare_static_dynamic_backtest = compare_static_dynamic_backtest if callable(compare_static_dynamic_backtest) else _v544_compare_static_dynamic_backtest
scan_universe_dynamic = scan_universe_dynamic if callable(scan_universe_dynamic) else _v544_scan_universe_dynamic

def early_event_backtest(feat, event_pct=.06, lookbacks=(1, 2, 3), min_turnover=0):
    """Single-ticker diagnostic: scores 1/2/3 trading days before close-to-close gains >= target."""
    f = feat.copy()
    if f is None or len(f) == 0:
        return pd.DataFrame()
    f["quant_score_bt"] = [score_row(r, min_turnover)[0] for _, r in f.iterrows()]
    f["early_score_bt"] = [early_score_row(r)[0] for _, r in f.iterrows()]
    f["day_return_bt"] = f["Close"].pct_change()
    rows = []
    for i in range(1, len(f)):
        day_ret = float(f["day_return_bt"].iloc[i]) if pd.notna(f["day_return_bt"].iloc[i]) else np.nan
        if not np.isfinite(day_ret) or day_ret < float(event_pct):
            continue
        row = {
            "EventDate": f.index[i],
            "EventReturnPct": day_ret * 100.0,
            "EventQuality": "OUTLIER REVIEW" if abs(day_ret) > 0.60 else "NORMAL",
            "PrevClose": float(f["Close"].iloc[i-1]),
            "EventClose": float(f["Close"].iloc[i]),
        }
        for lb in lookbacks:
            j = i - int(lb)
            row[f"Quant_D{lb}"] = float(f["quant_score_bt"].iloc[j]) if j >= 0 else np.nan
            row[f"Early_D{lb}"] = float(f["early_score_bt"].iloc[j]) if j >= 0 else np.nan
        rows.append(row)
    return pd.DataFrame(rows)


def component_calibration(feat, event_pct=.03, lookbacks=(1,2,3), min_turnover=0):
    """Compare component activation before strong up-days with its normal historical baseline.

    Returns two summary DataFrames (Early and Quant). The event sample is made of the
    1/2/3 trading days before each close-to-close gain >= event_pct. Baseline is all
    eligible historical days. Lift > 1 means the component was active more often before
    strong up-days than on a typical historical day.
    """
    f = feat.copy()
    if f is None or len(f) == 0:
        return pd.DataFrame(), pd.DataFrame(), 0
    f['event_ret_cal'] = f['Close'].pct_change()
    event_indices = [i for i in range(1, len(f)) if pd.notna(f['event_ret_cal'].iloc[i]) and float(f['event_ret_cal'].iloc[i]) >= float(event_pct)]
    if not event_indices:
        return pd.DataFrame(), pd.DataFrame(), 0

    def build(kind):
        # Historical baseline: how often each component is active on an ordinary eligible row.
        baseline = {}
        component_max = {}
        for _, r in f.iterrows():
            comps = early_score_row(r)[1] if kind == 'early' else score_row(r, min_turnover)[1]
            for name, pts, mx in comps:
                component_max[name] = float(mx)
                baseline.setdefault(name, []).append(float(pts) if np.isfinite(float(pts)) else 0.0)

        event_records = []
        event_component_seen = {name: set() for name in component_max}
        by_lb = {lb: {name: [] for name in component_max} for lb in lookbacks}
        for event_no, i in enumerate(event_indices):
            for lb in lookbacks:
                j = i - int(lb)
                if j < 0:
                    continue
                r = f.iloc[j]
                comps = early_score_row(r)[1] if kind == 'early' else score_row(r, min_turnover)[1]
                for name, pts, mx in comps:
                    pts = float(pts) if np.isfinite(float(pts)) else 0.0
                    mx = float(mx)
                    active = pts > 0
                    event_records.append((event_no, lb, name, pts, mx, active))
                    by_lb[lb][name].append(active)
                    if active:
                        event_component_seen.setdefault(name, set()).add(event_no)

        rows=[]
        total_events=len(event_indices)
        for name,mx in component_max.items():
            rec=[x for x in event_records if x[2]==name]
            pts=[x[3] for x in rec]
            active=[x[5] for x in rec]
            base=baseline.get(name,[])
            event_active=100*np.mean(active) if active else np.nan
            base_active=100*np.mean([p>0 for p in base]) if base else np.nan
            lift=(event_active/base_active) if np.isfinite(event_active) and np.isfinite(base_active) and base_active>0 else np.nan
            strength=100*np.mean([p/mx for p in pts]) if pts and mx>0 else np.nan
            coverage=100*len(event_component_seen.get(name,set()))/total_events if total_events else np.nan
            row={
                'Component':name,
                'Event coverage %':coverage,
                'Pre-event active %':event_active,
                'Baseline active %':base_active,
                'Lift x':lift,
                'Avg strength %':strength,
            }
            for lb in sorted(lookbacks, reverse=True):
                vals=by_lb[lb].get(name,[])
                row[f'D-{lb} active %']=100*np.mean(vals) if vals else np.nan
            rows.append(row)
        z=pd.DataFrame(rows)
        if not z.empty:
            z=z.sort_values(['Lift x','Event coverage %','Avg strength %'],ascending=[False,False,False],na_position='last').reset_index(drop=True)
        return z

    return build('early'), build('quant'), len(event_indices)




def normalize_backtest_confidence(bt):
    """V5.3.3 single source of truth for confidence UI and decision logic.

    Recomputes the 80/20 confidence from raw backtest outputs so the displayed
    Backtest Performance, Sample Reliability and Combined Confidence can never
    disagree, even if app.py and quant_engine.py were uploaded out of sync.
    """
    out = dict(bt or {})
    n = int(out.get("n", 0) or 0)
    hr = out.get("hit_rate", np.nan)
    try:
        hr = float(hr)
    except Exception:
        hr = np.nan
    if n <= 0 or not np.isfinite(hr):
        performance = 0.0
        reliability = 0.0
        confidence = 0.0
        label = "LOW"
    else:
        performance = 100.0 * hr
        reliability = 100.0 * min(1.0, math.sqrt(n / 60.0))
        confidence = 0.80 * performance + 0.20 * reliability
        label = "HIGH" if n >= 30 and hr >= 0.60 else ("MEDIUM" if n >= 12 and hr >= 0.45 else "LOW")
    out["backtest_performance"] = round(performance, 1)
    out["sample_reliability"] = round(reliability, 1)
    out["confidence"] = round(confidence, 1)
    out["confidence_label"] = label
    return out

def backtest_display(bt):
    """Avoid presenting a fragile percentage as strong evidence when the sample is tiny."""
    n=int(bt.get('n',0) or 0)
    if n == 0:
        return '—', 'NO SAMPLE'
    hits=int(bt.get('hits', round(float(bt.get('hit_rate',0))*n)))
    if n < 12:
        return f'{hits}/{n} hits', 'LOW SAMPLE'
    return f"{float(bt.get('hit_rate',np.nan))*100:.1f}%", bt.get('confidence_label','')

st.set_page_config(page_title=f"AI Stock Hunter — V{APP_VERSION}",page_icon="📈",layout="wide",initial_sidebar_state="collapsed")
st.markdown("""<style>
:root{--bg:#080b12;--panel:#111722;--panel2:#151d2b;--text:#f5f7fb;--muted:#8f9bad;--accent:#8b6cff;--cyan:#39d9e8;--good:#35d49a;--warn:#f6c85f;--bad:#ff647c;--line:#243044}
html,body,[data-testid="stAppViewContainer"]{background:radial-gradient(circle at 15% 0%,#151a2e 0,#080b12 34%);color:var(--text)} [data-testid="stHeader"]{background:transparent}.block-container{max-width:1180px;padding-top:2rem;padding-bottom:5rem} h1,h2,h3,h4,p,label,span,div{font-family:Inter,system-ui,-apple-system,Segoe UI,sans-serif}.hero{padding:30px 30px;border:1px solid #2b3954;border-radius:26px;background:radial-gradient(circle at 85% 15%,rgba(57,217,232,.12),transparent 34%),linear-gradient(135deg,rgba(139,108,255,.20),rgba(17,23,34,.95));box-shadow:0 24px 70px rgba(0,0,0,.32);margin-bottom:22px}.hero-title{font-size:clamp(2.4rem,6vw,4.5rem);font-weight:850;line-height:.98;letter-spacing:-.05em}.hero-sub{color:var(--muted);font-size:1.08rem;margin-top:14px}.hero-credit{display:inline-block;margin-top:12px;padding:5px 11px;border:1px solid rgba(57,255,136,.72);border-radius:999px;background:rgba(35,255,112,.07);color:#39ff88;font-size:1.02rem;font-weight:950;letter-spacing:.035em;text-shadow:0 0 7px rgba(57,255,136,.98),0 0 16px rgba(57,255,136,.66),0 0 28px rgba(57,255,136,.36);box-shadow:0 0 8px rgba(57,255,136,.62),0 0 20px rgba(57,255,136,.22),inset 0 0 12px rgba(57,255,136,.06)}.analyze-complete-il{margin:10px 0 14px;padding:11px 16px;border:1px solid #35ff7a;border-radius:14px;background:rgba(35,255,112,.08);color:#54ff8c;font-weight:900;font-size:1.02rem;box-shadow:0 0 8px rgba(53,255,122,.75),0 0 24px rgba(53,255,122,.30);text-shadow:0 0 10px rgba(84,255,140,.9)}.badge{display:inline-block;padding:5px 10px;border-radius:999px;background:#20283a;color:#b8c2d5;font-size:.78rem;font-weight:700;letter-spacing:.04em}.card{background:linear-gradient(180deg,rgba(22,30,45,.98),rgba(14,20,31,.98));border:1px solid #2a3851;border-radius:20px;padding:18px 20px;margin-bottom:14px;box-shadow:0 14px 34px rgba(0,0,0,.20)}.good{color:var(--good);font-weight:800}.warn{color:var(--warn);font-weight:800}.bad{color:var(--bad);font-weight:800}.muted{color:var(--muted)}.section{font-size:1.55rem;font-weight:800;margin:28px 0 12px}.score{font-size:2.1rem;font-weight:850}.stButton>button{width:100%;min-height:52px;border-radius:14px;background:linear-gradient(90deg,#6e56ff,#3c8cff);border:0;color:white;font-weight:750}.stButton>button:hover{filter:brightness(1.08);color:white}.stTextArea textarea,.stTextInput input,div[data-baseweb="select"]>div{background:#111722!important;border-color:#29354a!important;border-radius:13px!important}.stDataFrame{border:1px solid #263249;border-radius:16px;overflow:hidden}[data-testid="stMetric"]{background:#111722;border:1px solid #263249;padding:14px;border-radius:16px}[data-testid="stMetricValue"]{font-size:1.55rem}.stTabs [data-baseweb="tab-list"]{gap:10px}.stTabs [data-baseweb="tab"]{border-radius:12px;padding:8px 14px}.stTabs [aria-selected="true"]{background:#171f31}
.top5-head{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:6px}.top5-name{font-size:1.25rem;font-weight:850;letter-spacing:-.02em;flex:1 1 140px}.top5-score{font-size:1.62rem;font-weight:950;white-space:nowrap;letter-spacing:-.025em;color:#f2f6ff}.top5-score small,.top5-price small,.top5-opp small{font-size:.68rem;color:var(--muted);font-weight:800;letter-spacing:.06em}.top5-score .den{font-size:.72rem;color:#9ea9bc;font-weight:800;margin-left:1px}.top5-price{font-size:1.06rem;font-weight:900;white-space:nowrap;color:#e9eef8}.top5-price .ccy{font-size:.62rem;color:#9ea9bc;font-weight:800;margin-left:3px}.top5-opp{font-size:.95rem;font-weight:800;white-space:nowrap;color:#cbd4e6}.top5-rankline{font-size:.75rem;color:#9ea9bc;margin:-1px 0 5px}.top5-rankline b{color:#e9eef8;font-weight:900}.top5-status{font-size:.82rem;line-height:1.45;color:#c7d0df;margin:5px 0 8px}.top5-pill{display:inline-block;padding:2px 7px;border-radius:999px;background:#1a2332;border:1px solid #2d3a50;font-size:.72rem;font-weight:800}.top5-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:7px;margin:7px 0}.top5-mini{min-width:0;background:#0e1520;border:1px solid #263249;border-radius:11px;padding:8px 9px}.top5-mini .lbl{display:block;color:var(--muted);font-size:.66rem;font-weight:750;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.top5-mini .val{display:block;font-size:.98rem;font-weight:850;line-height:1.25;margin-top:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.top5-mini .sub{display:block;color:#9eabc0;font-size:.64rem;line-height:1.25;margin-top:2px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.top5-alert{margin:7px 0 3px;padding:7px 9px;border-radius:10px;border:1px solid #59482b;background:rgba(246,200,95,.08);font-size:.76rem;line-height:1.35}.top5-plan{margin:7px 0 2px;padding:8px 9px;border:1px solid #284a3d;border-radius:11px;background:rgba(39,190,120,.06);font-size:.76rem;line-height:1.45}.top5-detail-line{font-size:.78rem;line-height:1.45;color:#aeb9ca;margin:3px 0}
.scan-complete-banner{margin:10px 0 10px;padding:12px 14px;border-radius:14px;border:1px solid rgba(57,255,136,.72);background:linear-gradient(90deg,rgba(20,95,58,.24),rgba(9,31,24,.74));color:#39ff88;font-size:1.02rem;font-weight:950;letter-spacing:.045em;text-shadow:0 0 9px rgba(57,255,136,.78),0 0 18px rgba(57,255,136,.35);box-shadow:0 0 0 1px rgba(57,255,136,.08) inset,0 0 18px rgba(57,255,136,.18)}.scan-complete-banner .scan-time{color:#d8ffe8;font-weight:900;letter-spacing:.02em}.scan-complete-banner .scan-tz{color:#9fffc3;font-size:.72rem;font-weight:850;margin-left:6px}.scan-summary-grid{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:7px;margin:7px 0 8px}.scan-summary-card{background:#0e1520;border:1px solid #263249;border-radius:11px;padding:8px 9px;min-width:0}.scan-summary-card .n{display:block;font-size:1.05rem;font-weight:900;color:#f4f7fb}.scan-summary-card .l{display:block;font-size:.64rem;font-weight:800;color:#8f9bad;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.decision-strip{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:7px;margin:5px 0 9px}.decision-chip{border-radius:11px;padding:9px 10px;border:1px solid #2a3851;background:#101724}.decision-chip .k{display:block;color:#8f9bad;font-size:.65rem;font-weight:800}.decision-chip .v{display:block;margin-top:2px;font-size:.92rem;font-weight:900}.why-grid{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin:8px 0}.why-panel{border-radius:14px;padding:11px 12px}.why-panel.yes{border:1px solid rgba(53,212,154,.46);background:rgba(53,212,154,.055);box-shadow:0 0 18px rgba(53,212,154,.055)}.why-panel.no{border:1px solid rgba(255,100,124,.42);background:rgba(255,100,124,.045);box-shadow:0 0 18px rgba(255,100,124,.045)}.why-title{font-size:.86rem;font-weight:950;letter-spacing:.04em;margin-bottom:7px}.why-panel.yes .why-title{color:#52efaF}.why-panel.no .why-title{color:#ff7187}.why-row{display:flex;align-items:flex-start;justify-content:space-between;gap:10px;padding:5px 0;border-top:1px solid rgba(255,255,255,.055);font-size:.75rem;line-height:1.3}.why-row:first-of-type{border-top:0}.why-row .wk{color:#9eabc0;font-weight:700;min-width:0}.why-row .wv{font-weight:900;text-align:right}.why-row .wv.yes{color:#52efaf}.why-row .wv.no{color:#ff7187}.why-row .wv.warn{color:#f6c85f}.why-empty{font-size:.74rem;color:#9eabc0;padding:5px 0}.why-tech-title{font-size:.72rem;color:#8f9bad;font-weight:800;margin:10px 0 2px}
@media (max-width: 700px){
  .block-container{padding-left:.85rem;padding-right:.85rem;padding-top:1rem}
  .stTabs [data-baseweb="tab-list"]{gap:2px;width:100%;overflow:visible}
  .stTabs [data-baseweb="tab"]{flex:1 1 0;min-width:0;padding:7px 4px;font-size:.82rem;white-space:nowrap;justify-content:center}
  .stTabs [data-baseweb="tab"] p{font-size:.82rem!important;white-space:nowrap!important}
  .top5-grid{grid-template-columns:repeat(2,minmax(0,1fr));gap:6px}
  .scan-summary-grid{grid-template-columns:repeat(2,minmax(0,1fr));gap:6px}
  .decision-strip{grid-template-columns:1fr}
  .why-grid{grid-template-columns:1fr}
  .top5-mini{padding:7px 8px;border-radius:10px}
  .top5-name{font-size:1.12rem}.top5-score{font-size:1.42rem}.top5-price{font-size:.96rem}.top5-opp{font-size:.88rem}
}

</style>""",unsafe_allow_html=True)
st.markdown(f"""<div class='hero'><span class='badge'>V{APP_VERSION} • MARKET DISCOVERY • DECISION BOARD • PERSISTENT FEEDBACK</span><div class='hero-title'>📈 AI Stock Hunter<br>V{APP_VERSION}</div><div class='hero-sub'>Persistent Last Scan • Pre-Move Radar • Building Setup • Strict Live Entry • Original Signal Audit</div><div class='hero-credit'>Developed by Alon Azoulay</div></div>""",unsafe_allow_html=True)

DEFAULT_TICKERS="1196.HK,1780.HK,NVDA,NVMI,MU,AMD,AVGO,AMZN,META,GOOGL,MSFT,AAPL,TSLA,PLTR,CRWV,NBIS,GILD,ORCL,SMCI,ARM,TSM,QCOM,NFLX,UBER,COIN,HOOD,TTWO"
NASDAQ_50="NVDA,AMD,MU,AVGO,NVMI,QCOM,ARM,INTC,AMAT,MSFT,GOOGL,META,AMZN,AAPL,ORCL,ADBE,PLTR,CSCO,NFLX,COST,PEP,MDLZ,AMGN,GILD,REGN,VRTX,ISRG,MRNA,BIIB,TSLA,TTWO,EA,RBLX,ABNB,BKNG,DASH,CRWD,PANW,FTNT,DDOG,ZS,MRVL,ADI,MCHP,ON,LRCX,KLAC,CDNS,SNPS,INTU"
NASDAQ_100="NVDA,AMD,MU,AVGO,NVMI,QCOM,ARM,INTC,AMAT,MSFT,GOOGL,META,AMZN,AAPL,ORCL,ADBE,PLTR,CSCO,NFLX,COST,PEP,MDLZ,AMGN,GILD,REGN,VRTX,ISRG,MRNA,BIIB,TSLA,TTWO,EA,RBLX,ABNB,BKNG,DASH,CRWD,PANW,FTNT,DDOG,ZS,MRVL,ADI,MCHP,ON,LRCX,KLAC,CDNS,SNPS,INTU,GOOG,TXN,ADP,MELI,PYPL,MAR,ORLY,CEG,CTAS,NXPI,PCAR,AEP,MNST,KDP,ROST,PAYX,FAST,ODFL,CSX,EXC,VRSK,BKR,XEL,WBD,GEHC,APP,MSTR,HOOD,COIN,SMCI,CRWV,NBIS,MDB,NET,TTD,SHOP,PDD,JD,BIDU,NTES,BILI,TCOM,TME,FUTU,LI,RIVN,LCID,SOFI,AFRM,UPST"
NASDAQ_200="NVDA,AMD,MU,AVGO,NVMI,QCOM,ARM,INTC,AMAT,MSFT,GOOGL,META,AMZN,AAPL,ORCL,ADBE,PLTR,CSCO,NFLX,COST,PEP,MDLZ,AMGN,GILD,REGN,VRTX,ISRG,MRNA,BIIB,TSLA,TTWO,EA,RBLX,ABNB,BKNG,DASH,CRWD,PANW,FTNT,DDOG,ZS,MRVL,ADI,MCHP,ON,LRCX,KLAC,CDNS,SNPS,INTU,GOOG,TXN,ADP,MELI,PYPL,MAR,ORLY,CEG,CTAS,NXPI,PCAR,AEP,MNST,KDP,ROST,PAYX,FAST,ODFL,CSX,EXC,VRSK,BKR,XEL,WBD,GEHC,APP,MSTR,HOOD,COIN,SMCI,CRWV,NBIS,MDB,NET,TTD,SHOP,PDD,JD,BIDU,NTES,BILI,TCOM,TME,FUTU,LI,RIVN,LCID,SOFI,AFRM,UPST,TROW,FITB,HBAN,NDAQ,IBKR,LULU,ULTA,CELH,DUOL,CART,ETSY,WING,FOXA,FOX,CHTR,SIRI,WMG,WDAY,DOCU,ZM,OKTA,GTLB,CFLT,DBX,BILL,PCOR,MNDY,FIVN,NICE,CYBR,CHKP,GEN,AKAM,FFIV,JKHY,MPWR,LSCC,SWKS,QRVO,ALGM,ACLS,SITM,CRDO,MTSI,CAMT,TSEM,ASML,AMKR,COHU,FORM,ICHR,TER,SYNA,SMTC,POWI,RMBS,ALNY,INCY,BMRN,SRPT,NBIX,CRSP,NTLA,BEAM,EDIT,RXRX,EXAS,ILMN,DXCM,PODD,HOLX,MASI,INSP,TECH,MEDP,RARE,IONS,CYTK,PCVX,RVMD,ACLX,TMDX,VCEL,GH,NTRA,TEM,AXON,CPRT,MANH,PCTY,FSLR,ENPH,RUN,CSIQ,ARRY,NXT,ASTS,RKLB,LUNR,RGTI"
BROAD_200=NASDAQ_200  # compatibility alias; V6.2.9 expanded research/scan universe
US_51=NASDAQ_50+",ITT"
US_201=NASDAQ_200+",ITT"
HK_50="1196.HK,1570.HK,0700.HK,9988.HK,3690.HK,9618.HK,1810.HK,9999.HK,1024.HK,9888.HK,0005.HK,0939.HK,1398.HK,3988.HK,1299.HK,2318.HK,0388.HK,0883.HK,0857.HK,0386.HK,0941.HK,0762.HK,0728.HK,0002.HK,0003.HK,0006.HK,0011.HK,0016.HK,0012.HK,0823.HK,1109.HK,1997.HK,2020.HK,2331.HK,2313.HK,1928.HK,0291.HK,9633.HK,1211.HK,0175.HK,9866.HK,2015.HK,6690.HK,2269.HK,6160.HK,1177.HK,3750.HK,2899.HK,2600.HK,0669.HK"
HK_100="1196.HK,1570.HK,0700.HK,9988.HK,3690.HK,9618.HK,1810.HK,9999.HK,1024.HK,9888.HK,0005.HK,0939.HK,1398.HK,3988.HK,1299.HK,2318.HK,0388.HK,0883.HK,0857.HK,0386.HK,0941.HK,0762.HK,0728.HK,0002.HK,0003.HK,0006.HK,0011.HK,0016.HK,0012.HK,0823.HK,1109.HK,1997.HK,2020.HK,2331.HK,2313.HK,1928.HK,0291.HK,9633.HK,1211.HK,0175.HK,9866.HK,2015.HK,6690.HK,2269.HK,6160.HK,1177.HK,3750.HK,2899.HK,2600.HK,0669.HK,0017.HK,0027.HK,0066.HK,0083.HK,0101.HK,0151.HK,0267.HK,0288.HK,0322.HK,0384.HK,0688.HK,0763.HK,0968.HK,1038.HK,1044.HK,1066.HK,1093.HK,1113.HK,1209.HK,1288.HK,1336.HK,1378.HK,1658.HK,1876.HK,1919.HK,1929.HK,2007.HK,2202.HK,2238.HK,2382.HK,2388.HK,2628.HK,3328.HK,3968.HK,6098.HK,6618.HK,6862.HK,9616.HK,9626.HK,9698.HK,0981.HK,0992.HK,1801.HK,1800.HK,1880.HK,2688.HK,2689.HK,3311.HK,3888.HK,9992.HK"
HK_101=HK_100+",1780.HK"  # V6.3.9.47 priority HK addition; legacy HK_100 remains intact for registry compatibility
TASE_50="TEVA.TA,NICE.TA,LUMI.TA,POLI.TA,MZTF.TA,FIBI.TA,DSCT.TA,ESLT.TA,ICL.TA,CAMT.TA,NVMI.TA,TSEM.TA,ENLT.TA,OPCE.TA,DORL.TA,ORL.TA,DELG.TA,FTAL.TA,FOX.TA,RMLI.TA,SHUF.TA,STRA.TA,ILCO.TA,PTNR.TA,CEL.TA,BEZQ.TA,AZRG.TA,MLSR.TA,AMOT.TA,GCT.TA,ALHE.TA,MGDL.TA,CLIS.TA,PHOE.TA,HAREL.TA,MMHD.TA,ONE.TA,MTRX.TA,HIPR.TA,AURA.TA,DLEKG.TA,NWMD.TA,ISRA.TA,ELAL.TA,FORTY.TA,SPNS.TA,AQAR.TA,ARGO.TA,KRNT.TA,PERI.TA"
VALIDATION_50=NASDAQ_50
VALIDATION_51=US_51
VALIDATION_151=US_51+","+HK_50+","+TASE_50
VALIDATION_350=NASDAQ_200+","+HK_100+","+TASE_50  # legacy 350 universe
VALIDATION_351=US_201+","+HK_100+","+TASE_50  # legacy 351 universe incl. ITT
VALIDATION_351_HK101=NASDAQ_200+","+HK_101+","+TASE_50
VALIDATION_352=US_201+","+HK_101+","+TASE_50
VALIDATION_150=VALIDATION_151  # compatibility alias for older helpers
DISCOVERY_UNIVERSE=','.join(dict.fromkeys(VALIDATION_352.split(',')))
DISCOVERY_COUNT=len([x for x in DISCOVERY_UNIVERSE.split(',') if x])
MARKET_MAP={**{t:'NASDAQ' for t in NASDAQ_200.split(',')},'ITT':'NYSE',**{t:'HONG KONG' for t in HK_101.split(',')},**{t:'TEL AVIV' for t in TASE_50.split(',')}}
SECTOR_MAP={}
for t in NASDAQ_200.split(','): SECTOR_MAP[t]='Diversified NASDAQ / US Growth'
SECTOR_MAP['ITT']='Industrials'
for t in HK_101.split(','): SECTOR_MAP[t]='Diversified HK'
for t in TASE_50.split(','): SECTOR_MAP[t]='Diversified TASE'
# Explicit anchors/case-study names are always included in the large universes.
SECTOR_MAP.update({'1196.HK':'Conglomerate / Digital','1570.HK':'Industrial / Property','0700.HK':'Technology','0005.HK':'Banking','0883.HK':'Energy','1211.HK':'EV','2269.HK':'Healthcare','0823.HK':'REIT','3750.HK':'Battery','2899.HK':'Materials','1780.HK':'Diversified HK / Priority'})

# -----------------------------------------------------------------------------
# V6.3.9.48 Broad Market Discovery
# Stage 0 intentionally uses a cheap public market-list screen before the normal
# Yahoo/quant pipeline.  It prevents the curated 352 list from being mistaken for
# "the whole market".  Deep analysis still uses the existing causal engine.
# -----------------------------------------------------------------------------
def _num_discovery_v63948(v,default=np.nan):
    try:
        x=float(v);return x if np.isfinite(x) else default
    except Exception:return default


def _http_json_v63948(url,params=None,timeout=12):
    q=url
    if params:
        q += ('&' if '?' in q else '?') + urllib_parse.urlencode(params)
    req=urllib_request.Request(q,headers={'User-Agent':'Mozilla/5.0','Accept':'application/json,text/plain,*/*'})
    with urllib_request.urlopen(req,timeout=timeout) as resp:
        return json.loads(resp.read().decode('utf-8','ignore'))


_NON_COMMON_INSTRUMENT_RE_V63960=re.compile(
    r'(?i)\b(?:warrants?|rights?|units?|bonds?|notes?|debentures?|subordinated|'+
    r'senior\s+notes?|junior\s+notes?|capital\s+securities|trust\s+certificates?|'+
    r'etf|etn|closed[- ]end\s+fund|perpetual|convertible\s+(?:notes?|bonds?|securities)|'+
    r'preferred\s+(?:stock|shares?|securities)|preference\s+shares?|depositary\s+shares?)\b'
)

def _common_stock_name_ok_v63960(name, ticker='', market=''):
    """Cheap Stage-0 guard that keeps ordinary equity while excluding exchange-traded debt/units."""
    n=str(name or '').strip()
    if not n:
        return True
    if _NON_COMMON_INSTRUMENT_RE_V63960.search(n):
        return False
    # Percentage-bearing Series names are commonly listed debt/preferred securities.
    if re.search(r'(?i)\bseries\s+[0-9A-Z]{2,}\b.*\b\d+(?:\.\d+)?%\b',n):
        return False
    return True

@st.cache_data(ttl=1800,show_spinner=False)
def _eastmoney_market_rows_v63948(market):
    """Best-effort broad US/HK discovery list with cheap live ranking fields."""
    m=str(market).upper().strip()
    fs='m:105,m:106,m:107' if m=='US' else ('m:116,m:113,m:114,m:115,m:128' if m=='HONG KONG' else '')
    if not fs:return pd.DataFrame()
    rows=[];page=1;seen=set();total=None
    while page<=12:
        try:
            data=_http_json_v63948('https://push2.eastmoney.com/api/qt/clist/get',{
                'np':1,'fltt':2,'invt':2,'fs':fs,'fields':'f2,f3,f5,f6,f7,f10,f12,f13,f14,f20',
                'fid':'f6','pn':page,'pz':500,'po':1,'dect':1,'ut':'fa5fd1943c7b386f172d6893dbfba10b','wbp2u':'|0|0|0|web'})
            body=(data or {}).get('data') or {};diff=body.get('diff') or []
            if total is None:total=int(body.get('total') or 0)
            if not diff:break
            for d in diff:
                code=str(d.get('f12','') or '').strip();name=str(d.get('f14','') or '').strip()
                if not code or code in seen:continue
                seen.add(code)
                if not _common_stock_name_ok_v63960(name,code,m):continue
                if m=='HONG KONG':
                    if not code.isdigit():continue
                    try:ticker=str(int(code)).zfill(4)+'.HK'
                    except Exception:continue
                    market_label='HONG KONG'
                else:
                    if not re.match(r'^[A-Za-z][A-Za-z0-9.\-]{0,9}$',code):continue
                    ticker=code.upper().replace('.','-');market_label='US'
                px=_num_discovery_v63948(d.get('f2'));chg=_num_discovery_v63948(d.get('f3'),0.0);amount=_num_discovery_v63948(d.get('f6'),0.0);amp=_num_discovery_v63948(d.get('f7'),0.0);vr=_num_discovery_v63948(d.get('f10'),np.nan);mcap=_num_discovery_v63948(d.get('f20'),np.nan)
                if not np.isfinite(px) or px<=0 or amount<=0:continue
                rows.append({'Ticker':ticker,'Market':market_label,'Name':name,'Price':px,'ChangePct':chg,'Turnover':amount,'VolumeRatio':vr,'AmplitudePct':amp,'MarketCap':mcap,'DiscoverySource':'PUBLIC MARKET LIST','InstrumentType':'COMMON STOCK'})
            page+=1
            if total and len(seen)>=total:break
        except Exception:
            break
    return pd.DataFrame(rows)


@st.cache_data(ttl=1800,show_spinner=False)
def _tradingview_market_rows_v63950(market):
    """Second broad public discovery source for US / Hong Kong.

    Eastmoney is useful but can be unavailable from some Streamlit hosts. V6.3.9.50
    adds TradingView as an independent fallback so MARKET DISCOVERY does not quietly
    collapse to the curated list. This stage is symbol discovery/ranking only; final
    prices and signals still come from the normal Yahoo/quant pipeline.
    """
    m=str(market or '').upper().strip()
    if m=='US':region='america';tv_market='america';market_label='US'
    elif m=='HONG KONG':region='hongkong';tv_market='hongkong';market_label='HONG KONG'
    else:return pd.DataFrame()
    rows=[];start=0;page_size=2500;total=None
    while start < 10000:
        payload={
            'filter':[{'left':'type','operation':'equal','right':'stock'}],
            'options':{'lang':'en'},'markets':[tv_market],
            'symbols':{'query':{'types':[]},'tickers':[]},
            'columns':['name','description','close','change','volume','relative_volume_10d_calc','market_cap_basic'],
            'sort':{'sortBy':'volume','sortOrder':'desc'},'range':[start,start+page_size-1]
        }
        try:
            req=urllib_request.Request(
                f'https://scanner.tradingview.com/{region}/scan',
                data=json.dumps(payload).encode('utf-8'),
                headers={'User-Agent':'Mozilla/5.0','Content-Type':'application/json','Accept':'application/json'},method='POST')
            raw=json.loads(urllib_request.urlopen(req,timeout=15).read().decode('utf-8','ignore'))
            data=(raw or {}).get('data') or []
            if total is None:
                try:total=int((raw or {}).get('totalCount') or len(data))
                except Exception:total=len(data)
            if not data:break
            for item in data:
                sym=str(item.get('s','') or '');vals=item.get('d') or []
                code=sym.split(':',1)[-1].upper().strip()
                name=str(vals[1] if len(vals)>1 and vals[1] is not None else code)
                if not _common_stock_name_ok_v63960(name,code,m):continue
                if m=='HONG KONG':
                    digits=re.sub(r'\D','',code)
                    if not digits:continue
                    try:ticker=str(int(digits)).zfill(4)+'.HK'
                    except Exception:continue
                else:
                    # Yahoo uses dash for class shares such as BRK-B.
                    ticker=code.replace('.','-')
                    if not re.match(r'^[A-Z][A-Z0-9\-]{0,11}$',ticker):continue
                px=_num_discovery_v63948(vals[2] if len(vals)>2 else np.nan)
                chg=_num_discovery_v63948(vals[3] if len(vals)>3 else 0.0,0.0)
                vol=_num_discovery_v63948(vals[4] if len(vals)>4 else 0.0,0.0)
                vr=_num_discovery_v63948(vals[5] if len(vals)>5 else np.nan)
                mcap=_num_discovery_v63948(vals[6] if len(vals)>6 else np.nan)
                turnover=(px*vol) if np.isfinite(px) and np.isfinite(vol) else 0.0
                if not np.isfinite(px) or px<=0 or turnover<=0:continue
                rows.append({'Ticker':ticker,'Market':market_label,'Name':name,'Price':px,'ChangePct':chg,
                             'Turnover':turnover,'VolumeRatio':vr,'AmplitudePct':0.0,'MarketCap':mcap,
                             'DiscoverySource':'PUBLIC SCREENER • TRADINGVIEW','InstrumentType':'COMMON STOCK'})
            start += page_size
            if total is not None and start>=total:break
        except Exception:
            break
    return pd.DataFrame(rows).drop_duplicates('Ticker').reset_index(drop=True) if rows else pd.DataFrame()


def _best_broad_discovery_source_v63950(market):
    """Pick/merge the broadest working public source; never pretend fallback is broad."""
    m=str(market or '').upper().strip()
    east=_eastmoney_market_rows_v63948(m) if m in ('US','HONG KONG') else pd.DataFrame()
    tv=_tradingview_market_rows_v63950(m) if m in ('US','HONG KONG') else pd.DataFrame()
    parts=[x for x in (east,tv) if isinstance(x,pd.DataFrame) and not x.empty]
    if not parts:return pd.DataFrame()
    # Prefer the larger source for rank fields, but union the other source so one
    # provider cannot silently hide a symbol. Duplicates keep the preferred row.
    parts=sorted(parts,key=len,reverse=True)
    out=pd.concat(parts,ignore_index=True,sort=False).drop_duplicates('Ticker',keep='first')
    return out.reset_index(drop=True)


@st.cache_data(ttl=1800,show_spinner=False)
def _tase_market_rows_v63948():
    """Best-effort broad TASE list with a second public-source fallback."""
    rows=[]
    # TradingView's public stock screener is used only for Stage-0 symbol discovery.
    # Final prices/signals still come from the normal provider/quant pipeline.
    try:
        payload={
            'filter':[{'left':'type','operation':'equal','right':'stock'}],
            'options':{'lang':'en'},'markets':['israel'],
            'symbols':{'query':{'types':[]},'tickers':[]},
            'columns':['name','description','close','change','volume','relative_volume_10d_calc','market_cap_basic'],
            'sort':{'sortBy':'volume','sortOrder':'desc'},'range':[0,2500]
        }
        req=urllib_request.Request('https://scanner.tradingview.com/israel/scan',data=json.dumps(payload).encode('utf-8'),headers={'User-Agent':'Mozilla/5.0','Content-Type':'application/json','Accept':'application/json'},method='POST')
        raw=json.loads(urllib_request.urlopen(req,timeout=15).read().decode('utf-8','ignore'))
        for item in (raw or {}).get('data',[]):
            sym=str(item.get('s','') or '');vals=item.get('d') or []
            code=sym.split(':',1)[-1].upper().strip()
            if not re.match(r'^[A-Z0-9][A-Z0-9.\-]{0,11}$',code):continue
            name=str(vals[1] if len(vals)>1 else code)
            if not _common_stock_name_ok_v63960(name,code,'TEL AVIV'):continue
            px=_num_discovery_v63948(vals[2] if len(vals)>2 else np.nan);chg=_num_discovery_v63948(vals[3] if len(vals)>3 else 0,0);vol=_num_discovery_v63948(vals[4] if len(vals)>4 else 0,0);vr=_num_discovery_v63948(vals[5] if len(vals)>5 else np.nan);mcap=_num_discovery_v63948(vals[6] if len(vals)>6 else np.nan)
            turnover=(px*vol) if np.isfinite(px) and np.isfinite(vol) else 0.0
            if np.isfinite(px) and px>0:
                rows.append({'Ticker':code+'.TA','Market':'TEL AVIV','Name':name,'Price':px,'ChangePct':chg,'Turnover':turnover,'VolumeRatio':vr,'AmplitudePct':0.0,'MarketCap':mcap,'DiscoverySource':'PUBLIC SCREENER','InstrumentType':'COMMON STOCK'})
    except Exception:
        rows=[]
    # If the screener format changes, try the TASE public page before conceding to
    # the curated compatibility universe.
    if len(rows)<80:
        page_rows=[]
        try:
            req=urllib_request.Request('https://market.tase.co.il/en/market_data/securities/data/stocks',headers={'User-Agent':'Mozilla/5.0','Accept-Language':'en-US'})
            html=urllib_request.urlopen(req,timeout=12).read().decode('utf-8','ignore')
            symbols=set(re.findall(r'"(?:Symbol|symbol)"\s*:\s*"([A-Z0-9.\-]+)"',html))
            banned={'CSV','TSV','TASE','HOME','SHARES','STOCKS','DATA','INDEX'}
            for sym in sorted(symbols):
                u=sym.upper().strip()
                if u in banned or '.' in u or len(u)>10:continue
                page_rows.append({'Ticker':u+'.TA','Market':'TEL AVIV','Name':u,'Price':np.nan,'ChangePct':0.0,'Turnover':0.0,'VolumeRatio':np.nan,'AmplitudePct':0.0,'MarketCap':np.nan,'DiscoverySource':'TASE PUBLIC LIST','InstrumentType':'COMMON STOCK / UNKNOWN NAME'})
        except Exception:
            page_rows=[]
        if len(page_rows)>len(rows):rows=page_rows
    if len(rows)<80:
        rows=[{'Ticker':t,'Market':'TEL AVIV','Name':t.replace('.TA',''),'Price':np.nan,'ChangePct':0.0,'Turnover':0.0,'VolumeRatio':np.nan,'AmplitudePct':0.0,'MarketCap':np.nan,'DiscoverySource':'CURATED FALLBACK','InstrumentType':'CURATED COMMON STOCK'} for t in TASE_50.split(',')]
    return pd.DataFrame(rows).drop_duplicates('Ticker').reset_index(drop=True)


def _rank_discovery_rows_v63948(df):
    if df is None or df.empty:return pd.DataFrame()
    z=df.copy()
    for c in ('Turnover','VolumeRatio','ChangePct','AmplitudePct'):
        z[c]=pd.to_numeric(z.get(c,np.nan),errors='coerce')
    def pct(s):
        x=pd.to_numeric(s,errors='coerce');return x.rank(pct=True,method='average').fillna(0.0)
    turn=pct(np.log1p(z['Turnover'].clip(lower=0)))
    vr=pct(z['VolumeRatio'].clip(lower=0).fillna(0))
    move=pct(z['ChangePct'].clip(lower=-3,upper=12))
    amp=pct(z['AmplitudePct'].clip(lower=0,upper=20))
    z['DiscoveryScore']=100*(.36*turn+.34*vr+.18*move+.12*amp)
    return z.sort_values(['DiscoveryScore','Turnover'],ascending=False).reset_index(drop=True)


def _market_discovery_candidates_v63948(markets,progress_callback=None):
    """Broad Stage-0 discovery plus mandatory curated anchors.

    V6.3.9.49 fixes a coverage hole exposed by 1196.HK: public screeners may omit
    a temporarily suspended/renumbered counter.  Discovery therefore NEVER gets
    to delete the curated/core anchors.  The broad list discovers unknown names;
    curated anchors are unioned afterwards and marked explicitly for audit.
    """
    markets=[str(x).upper() for x in (markets or [])]
    frames=[];source_notes=[]
    for i,m in enumerate(markets,1):
        if progress_callback:progress_callback('discovery',i,max(1,len(markets)),m)
        if m=='US':d=_best_broad_discovery_source_v63950('US')
        elif m=='HONG KONG':d=_best_broad_discovery_source_v63950('HONG KONG')
        elif m=='TEL AVIV':d=_tase_market_rows_v63948()
        else:d=pd.DataFrame()
        if d is None:d=pd.DataFrame()
        fallback=US_201 if m=='US' else (HK_101 if m=='HONG KONG' else TASE_50)
        anchors=[x for x in fallback.split(',') if x]
        if d.empty:
            d=pd.DataFrame({'Ticker':anchors,'Market':m,'DiscoveryScore':50.0,'DiscoverySource':'CURATED FALLBACK'})
        d=_rank_discovery_rows_v63948(d) if 'DiscoveryScore' not in d.columns else d.copy()
        # Mandatory anchors are appended even when the public source did not list them.
        # Keep the logical ticker (e.g. 1196.HK); quant_engine handles any temporary
        # market-data counter bridge internally.
        present=set(d.get('Ticker',pd.Series(dtype=str)).astype(str))
        missing=[t for t in anchors if t not in present]
        if missing:
            anchor_rows=pd.DataFrame({
                'Ticker':missing,'Market':m,'Name':missing,'Price':np.nan,'ChangePct':0.0,
                'Turnover':0.0,'VolumeRatio':np.nan,'AmplitudePct':0.0,'MarketCap':np.nan,
                'DiscoveryScore':49.0,'DiscoverySource':'MANDATORY CURATED ANCHOR','InstrumentType':'CURATED COMMON STOCK'})
            d=pd.concat([d,anchor_rows],ignore_index=True,sort=False)
        d['DiscoveryMandatoryAnchor']=d['Ticker'].astype(str).isin(set(anchors))
        frames.append(d)
        _srcs=' + '.join(sorted(set(d.get('DiscoverySource',pd.Series(dtype=str)).dropna().astype(str)))) if not d.empty else 'NONE'
        source_notes.append(f"{m}:{len(d)} [{_srcs}]")
    allf=pd.concat(frames,ignore_index=True) if frames else pd.DataFrame()
    if allf.empty:return [],{'broad_scanned':0,'eligible':0,'candidates':0,'by_market':{},'source':'NONE'},allf
    allf=allf.drop_duplicates(['Market','Ticker'],keep='first').reset_index(drop=True)
    quotas={'US':160,'HONG KONG':120,'TEL AVIV':80}
    allf['DiscoveryEarlyVolumePriority']=False
    selected=[];by_market={}
    for m in markets:
        g=allf[allf['Market'].eq(m)].copy().sort_values(['DiscoveryScore','Turnover'],ascending=False,na_position='last')
        core=set((US_201 if m=='US' else (HK_101 if m=='HONG KONG' else TASE_50)).split(','))
        cap=min(len(g),quotas.get(m,80))
        idx=set(g.head(cap).index.tolist())
        # V6.3.9.56 PRE-MOVE lane: a 1780-style abnormal-volume day can happen
        # before a large price move. Reserve broad Stage-0 attention for relative-
        # volume shocks instead of requiring price momentum to already exist.
        if 'VolumeRatio' in g:
            _vr=pd.to_numeric(g['VolumeRatio'],errors='coerce')
            _vr_rank=g.assign(_VR=_vr).sort_values(['_VR','Turnover'],ascending=[False,False],na_position='last')
            idx.update(_vr_rank.head(min(60,max(cap,60))).index.tolist())
            _shock_pool=g.loc[_vr.index[(_vr>=3.0).fillna(False)]].sort_values('Turnover',ascending=False,na_position='last').head(80)
            idx.update(_shock_pool.index.tolist())
            g['DiscoveryEarlyVolumePriority']=False
            _early_idx=list(set(_vr_rank.head(min(60,max(cap,60))).index.tolist()) | set(_shock_pool.index.tolist()))
            g.loc[_early_idx,'DiscoveryEarlyVolumePriority']=True
            allf.loc[_early_idx,'DiscoveryEarlyVolumePriority']=True
        else:
            g['DiscoveryEarlyVolumePriority']=False
        if 'Turnover' in g:idx.update(g.sort_values('Turnover',ascending=False,na_position='last').head(min(35,cap)).index.tolist())
        # The core/curated names are mandatory even when this pushes Stage-0 above
        # the nominal discovery quota. This is intentional: coverage comes before rank.
        idx.update(g[g['Ticker'].astype(str).isin(core)].index.tolist())
        gg=g.loc[list(idx)].sort_values(['DiscoveryMandatoryAnchor','DiscoveryEarlyVolumePriority','DiscoveryScore','Turnover'],ascending=[False,False,False,False],na_position='last')
        selected.extend(gg['Ticker'].astype(str).tolist())
        by_market[m]={'scanned':len(g),'candidates':len(gg),'mandatory_anchors':int(gg['DiscoveryMandatoryAnchor'].fillna(False).sum())}
    selected=list(dict.fromkeys(selected))
    meta={'broad_scanned':len(allf),'eligible':len(allf),'candidates':len(selected),'by_market':by_market,'source':' • '.join(source_notes),
          'coverage_rule':'PUBLIC DISCOVERY + COMMON-STOCK GUARD + MANDATORY CURATED ANCHORS'}
    return selected,meta,allf



def _split_plan_integrity_guard_v63949(report,ent,current_price,split_ratio=np.nan,ticker=''):
    """Block mixed-scale trade plans, especially around recent subdivisions.

    Cross-timeframe last prices can look consistent while historical indicators are
    still polluted by a pre-split scale.  A near-exact split multiple in T1/T2 or
    implausibly mixed plan geometry is therefore treated as a hard data-quality block.
    """
    rep=dict(report or {}); e=dict(ent or {});rep.setdefault('details',[])
    try:p=float(current_price)
    except Exception:p=np.nan
    try:sr=float(split_ratio)
    except Exception:sr=np.nan
    suspicious=[]
    if np.isfinite(p) and p>0:
        vals={k:float(e.get(k,np.nan)) if np.isfinite(float(e.get(k,np.nan))) else np.nan for k in ('zone_low','zone_high','trigger','invalidation','target1','target2')}
        if np.isfinite(sr) and sr>1.15:
            for k in ('target1','target2','trigger','zone_low','zone_high'):
                v=vals.get(k,np.nan)
                if np.isfinite(v) and v>0:
                    ratio=v/p
                    if abs(ratio/sr-1.0)<=0.18 or abs(ratio*sr-1.0)<=0.18:
                        suspicious.append(f'{k} {ratio:.2f}x current ≈ split ratio {sr:g}')
        # A near-term T1 several hundred percent away is never normal plan geometry;
        # around a detected split it is much more likely mixed-scale ATR/resistance.
        if np.isfinite(vals.get('target1',np.nan)) and vals['target1']/p>=2.5:
            suspicious.append(f'target1/current = {vals["target1"]/p:.2f}x')
    if suspicious and (bool(rep.get('split_detected')) or (np.isfinite(sr) and sr>1.15)):
        rep['data_quality']='SPLIT_SCALE_MISMATCH';rep['scale_integrity_ok']=False;rep['split_scale_mismatch']=True
        rep['details']=list(rep.get('details') or [])+[f'{str(ticker).upper()} split integrity guard: '+ ' | '.join(suspicious[:4])]
        e.update({'plan_valid':False,'plan_reason':'Blocked by split/price scale integrity guard','zone_low':np.nan,'zone_high':np.nan,'trigger':np.nan,'invalidation':np.nan,'target1':np.nan,'target2':np.nan,
                  'setup_confirmed':False,'confirmed_entry_gate_ok':False,'price_actionable_now':False,'rr_actionable':False,'status':'WAIT','trigger_state':'WAIT','session_entry_state':'WAIT','recommended_action':'WAIT — SPLIT SCALE MISMATCH'})
    else:
        rep.setdefault('scale_integrity_ok',True);rep.setdefault('split_scale_mismatch',False)
    return rep,e

def _market_for_ticker_v612(ticker):
    t=str(ticker).upper()
    if t in MARKET_MAP:return MARKET_MAP[t]
    if t.endswith('.HK'):return 'HONG KONG'
    if t.endswith('.TA'):return 'TEL AVIV'
    return 'US'
def _clip100(x):
    try: return float(np.clip(float(x),0,100))
    except: return 0.0

def _outflow_label_v63921(score):
    """Human-readable bearish/outflow pressure band for the 0..100 card score."""
    v=_clip100(score)
    if v < 20:return 'LOW'
    if v < 40:return 'LIGHT'
    if v < 60:return 'MODERATE'
    if v < 80:return 'HIGH'
    return 'VERY HIGH'


def _inflow_label_v63922(score):
    v=_clip100(score)
    if v < 20:return 'LOW'
    if v < 40:return 'LIGHT'
    if v < 60:return 'MODERATE'
    if v < 80:return 'HIGH'
    return 'VERY HIGH'


def _net_flow_label_v63922(balance):
    try:v=float(balance)
    except Exception:v=0.0
    if v >= 20:return 'BUYERS DOMINANT'
    if v >= 8:return 'BUYERS LEAD'
    if v <= -20:return 'SELLERS DOMINANT'
    if v <= -8:return 'SELLERS LEAD'
    return 'MIXED / BALANCED'


def _rvol_label_v63929(value):
    """Direction-neutral magnitude band for the visible Intraday RVOL tile."""
    try:v=float(value)
    except Exception:return 'NO DATA'
    if not np.isfinite(v):return 'NO DATA'
    if v < 0.75:return 'LOW'
    if v < 1.25:return 'NORMAL'
    if v < 2.00:return 'HIGH'
    return 'VERY HIGH'


def _rvol_display_v63929(row, phase):
    """Single card RVOL: time-adjusted while OPEN, full-session after close."""
    ph=str(phase or '').upper()
    def _num(v):
        try:
            x=float(v)
            return x if np.isfinite(x) else np.nan
        except Exception:return np.nan
    live=_num(row.get('IntradayCumulativeRVOL',row.get('LiveIntradayRVOL',np.nan)))
    final=_num(row.get('FullSessionRVOL',row.get('VolumeRatio',np.nan)))
    if not np.isfinite(final):final=_num(row.get('DailyRobustRVOL',np.nan))
    if ph=='OPEN':
        val=live;mode='LIVE • TIME-ADJUSTED'
    else:
        val=final;mode='FINAL • CLOSED' if ph in ('CLOSED','AFTER-MARKET') else 'FINAL • PRIOR SESSION'
    return val,_rvol_label_v63929(val),mode

# V6.3.9.64 — execution liquidity layer.
# RVOL answers "is activity unusual now?"; this layer answers "is the stock
# normally liquid enough to enter/exit without relying on an exceptional day?".
def _liquidity_profile_v63964(feat, ticker):
    """Market-aware baseline liquidity score + hard execution gate.

    Uses robust daily traded value (median/average turnover), not RVOL. TASE
    Yahoo prices are quoted in agorot, so turnover is converted to ILS for the
    liquidity thresholds. Thresholds are intentionally conservative production
    guards, not exchange rules and not a guarantee of fill quality.
    """
    market=str(_market_for_ticker_v612(str(ticker or '')) or '').upper()
    if market in ('NASDAQ','NYSE','US'): key='US';currency='USD';scale=1.0;floor=2_000_000.0;strong=20_000_000.0;excellent=75_000_000.0
    elif market in ('HONG KONG','HK'): key='HONG KONG';currency='HKD';scale=1.0;floor=3_000_000.0;strong=20_000_000.0;excellent=80_000_000.0
    else: key='TEL AVIV';currency='ILS';scale=0.01;floor=1_500_000.0;strong=8_000_000.0;excellent=30_000_000.0
    out={'LiquidityScore':0.0,'LiquidityLabel':'NO DATA','LiquidityHardGateOK':False,'LiquidityBlockReason':'LIQUIDITY DATA UNAVAILABLE',
         'AvgDailyTurnover20':np.nan,'AvgDailyTurnover60':np.nan,'MedianDailyTurnover20':np.nan,'MedianDailyTurnover60':np.nan,
         'LiquidityTurnoverCurrency':currency,'LiquidityMinTurnover':floor,'LiquidityStableDaysPct':np.nan,'LiquiditySampleDays':0}
    try:
        if feat is None or not isinstance(feat,pd.DataFrame) or feat.empty:return out
        q=feat.copy().dropna(subset=['Close'])
        if q.empty:return out
        if 'turnover' in q:
            tv=pd.to_numeric(q['turnover'],errors='coerce')*scale
        else:
            tv=pd.to_numeric(q.get('Close'),errors='coerce')*pd.to_numeric(q.get('Volume'),errors='coerce')*scale
        tv=tv.replace([np.inf,-np.inf],np.nan).dropna()
        if tv.empty:return out
        last60=tv.tail(60);last20=tv.tail(20)
        avg20=float(last20.mean()) if len(last20) else np.nan;avg60=float(last60.mean()) if len(last60) else np.nan
        med20=float(last20.median()) if len(last20) else np.nan;med60=float(last60.median()) if len(last60) else np.nan
        robust=med60 if np.isfinite(med60) else med20
        stable=float((last20>=0.50*floor).mean()*100.0) if len(last20) else np.nan
        # Log scale prevents mega-caps from overwhelming the 0-100 score.
        low=max(floor/4.0,1.0)
        if np.isfinite(robust) and robust>0:
            turn_score=float(np.clip((np.log10(robust)-np.log10(low))/max(np.log10(excellent)-np.log10(low),1e-9)*85.0,0,85))
        else:turn_score=0.0
        stability_score=float(np.clip((stable if np.isfinite(stable) else 0.0)/100.0*15.0,0,15))
        score=float(np.clip(turn_score+stability_score,0,100))
        gate=bool(np.isfinite(robust) and robust>=floor and len(last60)>=15)
        if score>=80:label='HIGH'
        elif score>=60:label='MEDIUM'
        elif score>=40:label='LOW'
        else:label='VERY LOW'
        if not gate:
            if len(last60)<15:reason=f'LIQUIDITY BLOCK — ONLY {len(last60)} DAILY SAMPLES'
            elif not np.isfinite(robust):reason='LIQUIDITY BLOCK — TURNOVER UNAVAILABLE'
            else:reason=f'LIQUIDITY BLOCK — MEDIAN DAILY TURNOVER {robust:,.0f} {currency} < {floor:,.0f} {currency}'
        else:reason=f'PASS — MEDIAN DAILY TURNOVER {robust:,.0f} {currency}'
        out.update({'LiquidityScore':round(score,1),'LiquidityLabel':label,'LiquidityHardGateOK':gate,'LiquidityBlockReason':reason,
                    'AvgDailyTurnover20':avg20,'AvgDailyTurnover60':avg60,'MedianDailyTurnover20':med20,'MedianDailyTurnover60':med60,
                    'LiquidityStableDaysPct':stable,'LiquiditySampleDays':int(len(last60))})
        return out
    except Exception as e:
        out['LiquidityBlockReason']=f'LIQUIDITY DATA ERROR — {type(e).__name__}'
        return out

# V6.3.9.48 — one decision-board vocabulary for Scanner + Analyze.
def _trigger_timing_label_v63948(row):
    raw=str(row.get('TriggerEfficiencyLabel','') or '').upper()
    if 'TOO LATE' in raw or 'LATE' in raw:return 'LATE'
    if 'AGING' in raw or 'MID' in raw:return 'MID'
    if 'EARLY' in raw:return 'EARLY'
    try:c=float(row.get('MoveConsumedBeforeTriggerPct',np.nan))
    except Exception:c=np.nan
    if np.isfinite(c):return 'EARLY' if c<45 else ('MID' if c<80 else 'LATE')
    return 'NO DATA'


def _live_early_radar_v63949(row):
    """Strict LIVE early-discovery candidate.

    V6.3.9.63 separates a historical/structural Pre-Move pattern from a LIVE
    radar candidate. Stale session data, incomplete timing, closed sessions or an
    unverified live quote can never receive a Live Early Radar badge.
    """
    def _b(v,default=False):
        try:
            if pd.isna(v):return bool(default)
            return bool(v)
        except Exception:return bool(default)
    def n(v,d=np.nan):
        try:
            x=float(v);return x if np.isfinite(x) else d
        except Exception:return d
    phase=str(row.get('MarketPhase','UNKNOWN') or 'UNKNOWN').upper()
    data_ok=str(row.get('DataQuality','OK') or 'OK').upper()=='OK'
    session_fresh=_b(row.get('SessionDataFresh',False),False)
    timing_complete=_b(row.get('TimingDataComplete',True),True) and not _b(row.get('TimingConsumedHardBlock',False),False)
    live_price_fresh=_b(row.get('LivePriceFresh',False),False)
    if not _b(row.get('LiquidityHardGateOK',True),True):
        return False,0,'LIVE RADAR BLOCK — LOW LIQUIDITY'
    if phase not in ('OPEN','PRE-MARKET'):
        return False,0,f'LIVE RADAR BLOCK — MARKET {phase}'
    if phase=='PRE-MARKET' and str(row.get('PMConfirmation','N/A') or 'N/A').upper()!='CONFIRMED':
        return False,0,'LIVE RADAR BLOCK — PRE-MARKET NOT CONFIRMED'
    if not data_ok or not session_fresh:
        return False,0,'LIVE RADAR BLOCK — STALE / UNVERIFIED SESSION DATA'
    if not timing_complete:
        return False,0,'LIVE RADAR BLOCK — TIMING DATA INCOMPLETE / HARD BLOCK'
    if phase=='OPEN' and not live_price_fresh:
        return False,0,'LIVE RADAR BLOCK — LIVE PRICE NOT FRESH'
    try:recent=float(row.get('RecentRunPct',np.nan))
    except Exception:recent=np.nan
    rlab=str(row.get('RecentRunLabel','NO DATA') or 'NO DATA').upper()
    chase=str(row.get('ChaseRiskLabel','LOW') or 'LOW').upper()
    stage=str(row.get('TradeStage',row.get('EntryTriggerState','WAIT')) or 'WAIT').upper()
    trig=_trigger_timing_label_v63948(row)
    consumed=n(row.get('MoveConsumedBeforeTriggerPct',np.nan))
    timing_q=str(row.get('TimingQualification','') or '').upper()
    if (rlab in ('LATE CONTEXT','EXTENDED CONTEXT') or chase in ('HIGH','EXTREME') or
            trig=='LATE' or any(x in stage for x in ('RETEST','TOO LATE','EXTENDED','INVALIDATED')) or
            any(x in timing_q for x in ('RETEST','TOO LATE')) or
            (np.isfinite(consumed) and consumed>=60.0) or
            (np.isfinite(recent) and recent>=8)):
        return False,0,'Not an early setup — timing/recent-move/chase veto'
    rvol=n(row.get('IntradayCumulativeRVOL',row.get('LiveIntradayRVOL',row.get('TimeAdjustedRVOL',row.get('VolumeRatio',np.nan)))))
    inflow=n(row.get('InflowPressure',row.get('MoneyFlowScore',50)),50);outflow=n(row.get('OutflowPressure',row.get('ExitPressure',0)),0);net=n(row.get('NetFlowBalance',inflow-outflow),inflow-outflow)
    hour=n(row.get('HourlyOOSTimingScore',row.get('HourlyConfirm',np.nan)))
    entry=n(row.get('EntryTimingScore',row.get('LiveActionabilityScore',row.get('EntryScore',0))),0)
    fresh=_b(row.get('FreshSignalCheck',False)); daily=_b(row.get('DailySetupCheck',False)); trans=n(row.get('FreshTransitionCount',0),0)
    momentum=str(row.get('MomentumState','') or '').upper();m15=str(row.get('MomentumState15m','') or '').upper()
    acc_score=n(row.get('PreBreakoutAccumulationScore',0),0);acc_stage=str(row.get('PreBreakoutAccumulationStage','') or '').upper();acc_confirmed=_b(row.get('PreMoveConfirmed',False));acc_families=int(n(row.get('PreMoveFamilyCount',0),0) or 0)
    regime=n(row.get('VolumeRegimeRatio',np.nan));shock=n(row.get('VolumeShockRatio',np.nan));persist=n(row.get('VolumePersistenceRatio',np.nan));absorb=_b(row.get('AbsorptionCandidate',False))
    score=0;why=[]
    if fresh or trans>=1:score+=25;why.append('fresh transition')
    if daily:score+=15;why.append('daily setup')
    if np.isfinite(rvol) and rvol>=1.25:score+=20;why.append(f'RVOL {rvol:.2f}x')
    if net>=8 or (inflow>=55 and outflow<45):score+=18;why.append('positive flow')
    if np.isfinite(hour) and hour>=55:score+=12;why.append(f'hourly {hour:.0f}')
    if momentum in ('STRENGTHENING','STABLE') or m15=='STRENGTHENING':score+=10;why.append('momentum building')
    if acc_confirmed or 'HIGH-CONFIDENCE PRE-MOVE' in acc_stage:
        score+=34;why.append(f'high-confidence pre-move {acc_score:.0f} ({acc_families}/5 families)')
    elif acc_stage=='PRE-MOVE WATCH':
        score+=14;why.append(f'pre-move watch {acc_score:.0f}')
    elif acc_stage=='RAW ACCUMULATION':
        score+=4;why.append('raw accumulation only')
    if absorb:score+=6;why.append('absorption on abnormal volume')
    if np.isfinite(regime) and regime>=1.8:score+=6;why.append(f'volume regime {regime:.1f}x')
    elif np.isfinite(shock) and shock>=3:score+=3;why.append(f'volume shock {shock:.1f}x')
    if np.isfinite(persist) and persist>=1.5:score+=4
    accumulation_early=bool(acc_confirmed or 'HIGH-CONFIDENCE PRE-MOVE' in acc_stage)
    watch_early=bool(acc_stage=='PRE-MOVE WATCH' and acc_score>=65 and acc_families>=3)
    candidate=bool(score>=55 and (entry>=35 or accumulation_early or (watch_early and entry>=28)) and not _b(row.get('ConfirmedEntryGateOK',False)))
    return candidate,min(100,score),' • '.join(why[:6]) if why else 'No live early evidence'

def _retest_qualified_v63949(row):
    """A RETEST must be a good setup that became poorly priced, not merely a high price."""
    stage=str(row.get('TradeStage',row.get('EntryTriggerState','WAIT')) or 'WAIT').upper()
    setup=bool(row.get('SetupConfirmed',False))
    daily=bool(row.get('DailySetupCheck',False));fresh=bool(row.get('FreshSignalCheck',False));hour=bool(row.get('HourlyEntryCheck',False));flow=bool(row.get('VolumeFlowCheck',False))
    try:base=float(row.get('SetupEntryScore',row.get('EntryScore',0)) or 0)
    except Exception:base=0.0
    try:gates=int(float(row.get('EntryConfirmedConditions',0) or 0))
    except Exception:gates=0
    strong_pre_chase=bool(base>=58 and daily and (fresh or hour) and (flow or gates>=4))
    return bool(setup or 'CONFIRMED ENTRY' in stage or 'ARMED' in stage or strong_pre_chase)


def _entry_now_hard_gate_v63958(row):
    """Single source of truth for a live ENTRY NOW decision."""
    def _b(k,default=False):
        try:return bool(row.get(k,default))
        except Exception:return bool(default)
    def _n(k,default=np.nan):
        try:
            v=float(row.get(k,default));return v if np.isfinite(v) else default
        except Exception:return default
    phase=str(row.get('MarketPhase','UNKNOWN') or 'UNKNOWN').upper()
    data_ok=str(row.get('DataQuality','OK') or 'OK').upper()=='OK'
    timing_ok=_b('TimingDataComplete',True) and not _b('TimingConsumedHardBlock',False)
    gate_ok=_b('ConfirmedEntryGateOK',False)
    price_ok=_b('PriceActionableNow',False)
    rr_ok=_b('RRActionable',False)
    session_fresh=_b('SessionDataFresh',False)
    plan_ok=_b('PlanValid',True)
    extension_ok=_b('ExtensionGuardCheck',True)
    evidence_ok=_b('EvidenceGuardOK',True)
    exit_ok=_n('ExitPressure',0.0)<55.0
    live_price_ok=_b('LivePriceFresh',True)
    liquidity_ok=_b('LiquidityHardGateOK',True)
    session_ok=False
    if phase=='OPEN':
        session_ok=True
    elif phase=='PRE-MARKET':
        session_ok=str(row.get('PMConfirmation','N/A') or 'N/A').upper()=='CONFIRMED'
    ok=bool(session_ok and timing_ok and gate_ok and price_ok and rr_ok and session_fresh and data_ok and plan_ok and extension_ok and evidence_ok and exit_ok and live_price_ok and liquidity_ok)
    missing=[]
    if not session_ok:missing.append(f'MARKET {phase}')
    if not timing_ok:missing.append('TIMING INCOMPLETE / HARD BLOCK')
    if not gate_ok:missing.append('CONFIRMED ENTRY GATE FALSE')
    if not price_ok:missing.append('PRICE NOT ACTIONABLE')
    if not rr_ok:missing.append('R:R NOT ACTIONABLE')
    if not session_fresh:missing.append('SESSION DATA NOT FRESH')
    if not live_price_ok:missing.append('LIVE PRICE NOT FRESH')
    if not liquidity_ok:missing.append(str(row.get('LiquidityBlockReason','LOW LIQUIDITY / EXECUTION BLOCK')))
    if not data_ok:missing.append('DATA QUALITY BLOCK')
    if not plan_ok:missing.append('TRADE PLAN INVALID')
    if not extension_ok:missing.append('EXTENSION HARD BLOCK')
    if not evidence_ok:missing.append('EVIDENCE HARD GUARD')
    if not exit_ok:missing.append('EXIT PRESSURE HARD BLOCK')
    return ok,' • '.join(dict.fromkeys(missing)) if missing else 'ALL LIVE ENTRY GATES PASSED'


def _current_session_revalidation_v63958(row):
    """Detect a new regular session after a completed pre/open/closed snapshot."""
    market=str(row.get('Market',_market_for_ticker_v612(str(row.get('Ticker','')))) or '')
    scan_phase=str(row.get('MarketPhase','UNKNOWN') or 'UNKNOWN').upper()
    try:now_phase=str(_market_phase(market) or 'UNKNOWN').upper()
    except Exception:now_phase=scan_phase
    needs=bool(now_phase=='OPEN' and scan_phase!='OPEN')
    reason=(f'{now_phase} NOW • SNAPSHOT WAS {scan_phase} — REVALIDATE 15m/1H/RVOL/FLOW' if needs else 'CURRENT SESSION MATCHES SNAPSHOT PHASE')
    return needs,now_phase,reason


def _armed_qualification_v63961(row):
    """Structural qualification for an ARMED setup.

    ARMED is allowed to wait for price/R:R entry conditions, so PriceActionableNow
    and ConfirmedEntryGateOK are deliberately NOT required here.  What *is*
    required is enough trustworthy timing/data/plan structure to justify placing
    the name ahead of a healthy BUILDING SETUP.
    """
    def _b(k,default=False):
        try:
            v=row.get(k,default)
            if pd.isna(v): return bool(default)
            return bool(v)
        except Exception:return bool(default)
    def _n(k,default=np.nan):
        try:
            x=float(row.get(k,default));return x if np.isfinite(x) else default
        except Exception:return default
    trade=str(row.get('TradeStage',row.get('EntryTriggerState','')) or '').upper()
    setup_ok=_b('SetupConfirmed',False) or ('ARMED' in trade) or ('CONFIRMED ENTRY' in trade)
    timing_ok=_b('TimingDataComplete',True) and not _b('TimingConsumedHardBlock',False)
    data_ok=str(row.get('DataQuality','OK') or 'OK').upper()=='OK'
    session_ok=_b('SessionDataFresh',True)
    plan_ok=_b('PlanValid',True)
    extension_ok=_b('ExtensionGuardCheck',True) and not _b('CarryoverHardVeto',False)
    evidence_ok=_b('EvidenceGuardOK',True)
    exit_ok=_n('ExitPressure',0.0)<55.0
    liquidity_ok=_b('LiquidityHardGateOK',True)
    ok=bool(setup_ok and timing_ok and data_ok and session_ok and plan_ok and extension_ok and evidence_ok and exit_ok and liquidity_ok)
    missing=[]
    if not setup_ok:missing.append('SETUP NOT CONFIRMED')
    if not timing_ok:missing.append('TIMING DATA INCOMPLETE / HARD BLOCK')
    if not data_ok:missing.append('DATA QUALITY BLOCK')
    if not session_ok:missing.append('SESSION DATA NOT FRESH')
    if not plan_ok:missing.append('TRADE PLAN INVALID')
    if not extension_ok:missing.append('EXTENSION / CARRYOVER HARD BLOCK')
    if not evidence_ok:missing.append('EVIDENCE HARD GUARD')
    if not exit_ok:missing.append('EXIT PRESSURE HARD BLOCK')
    if not liquidity_ok:missing.append(str(row.get('LiquidityBlockReason','LOW LIQUIDITY / EXECUTION BLOCK')))
    return ok,(' • '.join(dict.fromkeys(missing)) if missing else 'ARMED STRUCTURAL GATES PASSED')


def _effective_decision_stage_v63958(row, raw_board):
    """Current-action stage used by Scanner filtering, ordering and Top Tickets."""
    raw=_decision_stage_canonical_v63961(raw_board)
    live_ok,live_reason=_entry_now_hard_gate_v63958(row)
    armed_ok,armed_reason=_armed_qualification_v63961(row)
    needs_reval,now_phase,reval_reason=_current_session_revalidation_v63958(row)
    phase=str(row.get('MarketPhase','UNKNOWN') or 'UNKNOWN').upper()
    if raw=='ENTRY NOW':
        if live_ok and not needs_reval:
            return 'ENTRY NOW','ENTRY NOW','ALL CURRENT ENTRY GATES PASSED',False,live_reason
        if phase in ('CLOSED','AFTER-MARKET','PRE-OPEN') or needs_reval:
            why=reval_reason if needs_reval else f'{phase} • PREVIOUS SESSION SIGNAL — RECHECK AT OPEN'
            return 'LAST SESSION ENTRY','LAST SESSION ENTRY',why,needs_reval,live_reason
        mature=bool(row.get('SetupConfirmed',False)) or 'CONFIRMED ENTRY' in str(row.get('TradeStage','')).upper() or 'ARMED' in str(row.get('TradeStage','')).upper()
        if mature:
            eff='ARMED' if armed_ok else 'ARMED BLOCKED'
            why=(f'RAW ENTRY BLOCKED • {live_reason}' if armed_ok else f'RAW ENTRY BLOCKED • {live_reason} • ARMED INCOMPLETE: {armed_reason}')
        else:
            eff='WAIT';why=f'RAW ENTRY BLOCKED • {live_reason}'
        return eff,eff,why,needs_reval,live_reason
    if raw=='ARMED':
        if armed_ok:return 'ARMED','ARMED',str(row.get('OpportunityWindowReason','') or 'ARMED STRUCTURAL GATES PASSED'),needs_reval,live_reason
        return 'ARMED BLOCKED','ARMED BLOCKED',f'ARMED INCOMPLETE • {armed_reason}',needs_reval,live_reason
    if raw=='ARMED BLOCKED':
        return 'ARMED BLOCKED','ARMED BLOCKED',armed_reason,needs_reval,live_reason
    return raw,raw,str(row.get('OpportunityWindowReason','') or ''),needs_reval,live_reason

def _core_reserved_deep_tickers_v63958(markets):
    """Reserved SMART-Deep anchors that must not disappear behind a quota cutoff.

    V6.3.9.63 keeps the liquid US core and explicitly guarantees the priority
    case-study names that were previously visible in Discovery but could be cut
    before Deep Analysis.
    """
    ms={str(x).upper() for x in (markets or [])}
    out=set()
    if 'US' in ms:
        out.update(x for x in US_51.split(',') if x)
        out.update({'COIN','SMCI','NICE'})
    if 'HONG KONG' in ms or 'HK' in ms:
        out.update({'1196.HK','1570.HK','1780.HK'})
    return out

def _decision_board_state_v63948(row):
    stage=str(row.get('TradeStage',row.get('EntryTriggerState','WAIT')) or 'WAIT').upper()
    rec=str(row.get('RecommendedAction','') or '').upper();retest=str(row.get('RetestStatus','') or '').upper()
    action=bool(row.get('ActionableNow',False))
    _live_entry_ok,_live_entry_reason=_entry_now_hard_gate_v63958(row)
    pm=str(row.get('PreMoveStage','') or '').upper();fresh=bool(row.get('FreshSignalCheck',False))
    breakout=bool(row.get('BreakoutContinuationActionable',False))
    continuation_ready=bool(row.get('ContinuationEntryReady',False))
    continuation_watch=bool(row.get('ContinuationEntryWatch',False))
    continuation_reason=str(row.get('ContinuationEntryReason','') or '')
    # Recent rise alone is context, not a RETEST command. RETEST requires an
    # explicit timing/retest state or the engine's compound context flag.
    retest_signal=bool('RETEST' in stage or row.get('RecentRunRetestContext',False) or row.get('TimingConsumedHardBlock',False))
    retest_qualified=_retest_qualified_v63949(row)
    early_live,early_score,early_reason=_live_early_radar_v63949(row)
    if 'INVALIDATED' in stage or 'TOO LATE' in stage or 'EXTENDED' in stage:
        board='TOO LATE';window='CLOSED';reason=stage
    elif (breakout or continuation_ready) and action and _live_entry_ok:
        board='ENTRY NOW';window='OPEN';reason=('Continuation entry ready — '+continuation_reason if continuation_ready and continuation_reason else 'Strict breakout-continuation confirmation + normal live entry/R:R gates')
    elif retest_signal and retest_qualified:
        board='RETEST';window='WAIT';reason=(retest if retest and retest!='—' else rec) or 'WAIT FOR RETEST'
    elif 'CONFIRMED ENTRY' in stage and str(row.get('MarketPhase','UNKNOWN') or 'UNKNOWN').upper() in ('CLOSED','AFTER-MARKET','PRE-OPEN'):
        board='ENTRY NOW';window='RECHECK AT OPEN';reason='Previous regular-session confirmed entry; live session is closed and must be revalidated'
    elif action and _live_entry_ok:
        board='ENTRY NOW';window='OPEN';reason='Entry gates + current price/R:R/session actionable'
    elif 'CONFIRMED ENTRY' in stage:
        board='ARMED';window='NEAR';reason='Historical/technical confirmation exists, but live entry gate is blocked — '+_live_entry_reason
    elif 'ARMED' in stage or breakout or continuation_watch:
        board='ARMED';window='NEAR';reason=(('Continuation watch — '+continuation_reason) if continuation_watch and continuation_reason else ('Breakout continuation building' if breakout else str(row.get('ActionabilityMissing','') or 'Setup armed; waiting for entry window')))
    elif pm in ('PRE-MOVE CANDIDATE','STRONG PRE-MOVE CANDIDATE') or ('WATCH' in stage and fresh) or early_live:
        board='BUILDING SETUP';window='BUILDING';reason=(early_reason if early_live else 'Early setup / fresh transition before confirmed entry')
    elif retest_signal and not retest_qualified:
        board='WAIT';window='IDLE';reason='Price/retest condition exists, but setup quality is not strong enough for RETEST'
    else:
        board='WAIT';window='IDLE';reason=str(row.get('WhyNotTradeTrigger',row.get('EntryMissingChecks','Waiting for setup')) or 'Waiting for setup')
    recent=str(row.get('RecentRunLabel','NO DATA') or 'NO DATA').upper()
    if recent=='EXTENDED CONTEXT':timing='EXTENDED'
    elif recent in ('LATE CONTEXT','MID CONTEXT'):timing='MID'
    elif recent=='EARLY CONTEXT':timing='EARLY'
    else:timing='NO DATA'
    return board,window,reason,timing


def _pre_move_actionability_v63957(row, board=None):
    """Separate pattern detection from whether the early setup is actionable NOW.

    V6.3.9.63 keeps a good pattern visible for research, but a setup with >=60%
    of its observed move consumed before the causal trigger, AGING/RETEST timing,
    or stale/live-session problems can no longer be labelled ACTIONABLE EARLY.
    """
    acc=str(row.get('PreBreakoutAccumulationStage','NO CURRENT ACCUMULATION SETUP') or 'NO CURRENT ACCUMULATION SETUP').upper()
    confirmed=bool(row.get('PreMoveConfirmed',False)) or 'HIGH-CONFIDENCE PRE-MOVE' in acc
    if confirmed: strength='HIGH'
    elif acc=='PRE-MOVE WATCH': strength='WATCH'
    elif acc=='RAW ACCUMULATION': strength='RAW'
    elif 'ACCUMULATION PERSISTS' in acc: strength='EXTENDED'
    else: strength='NONE'
    if strength=='NONE':
        return strength,False,'NO CURRENT PRE-MOVE PATTERN','No selective accumulation pattern is active'
    veto=[]
    phase=str(row.get('MarketPhase','UNKNOWN') or 'UNKNOWN').upper()
    if phase!='OPEN':veto.append(f'MARKET {phase} — RECHECK AT OPEN')
    if not bool(row.get('LiquidityHardGateOK',True)):veto.append(str(row.get('LiquidityBlockReason','LOW LIQUIDITY — RESEARCH ONLY')))
    if not bool(row.get('SessionDataFresh',True)) or str(row.get('DataQuality','OK') or 'OK').upper()!='OK':veto.append('STALE / UNVERIFIED SESSION DATA')
    rlab=str(row.get('RecentRunLabel','NO DATA') or 'NO DATA').upper()
    if rlab in ('LATE CONTEXT','EXTENDED CONTEXT'):veto.append(rlab)
    chase=str(row.get('ChaseRiskLabel','LOW') or 'LOW').upper()
    if chase in ('HIGH','EXTREME'):veto.append(f'CHASE {chase}')
    trig=_trigger_timing_label_v63948(row)
    if trig=='LATE':veto.append('TRIGGER LATE')
    tstage=str(row.get('TradeStage',row.get('EntryTriggerState','')) or '').upper()
    if any(x in tstage for x in ('TOO LATE','EXTENDED','INVALIDATED')):veto.append(tstage)
    try:consumed=float(row.get('MoveConsumedBeforeTriggerPct',np.nan))
    except Exception:consumed=np.nan
    if np.isfinite(consumed) and consumed>=60.0:veto.append(f'MOVE {consumed:.0f}% CONSUMED BEFORE TRIGGER — RETEST ONLY')
    timing_q=str(row.get('TimingQualification','') or '').upper()
    if 'AGING' in timing_q:veto.append('TIMING AGING — WATCH RETEST')
    if 'RETEST' in timing_q or 'TOO LATE' in timing_q:veto.append('TIMING RETEST ONLY')
    if bool(row.get('TimingConsumedHardBlock',False)):veto.append('TIMING HARD BLOCK — RETEST ONLY')
    retest_status=str(row.get('RetestStatus','') or '').upper()
    if board is not None and str(board).upper()=='RETEST':veto.append('DECISION BOARD RETEST ONLY')
    if 'RETEST' in retest_status and ('WAIT' not in retest_status or (np.isfinite(consumed) and consumed>=60)):veto.append('RETEST CONTEXT')
    try:recent=float(row.get('RecentRunPct',np.nan))
    except Exception:recent=np.nan
    if np.isfinite(recent) and recent>=8:veto.append(f'RECENT RISE {recent:.1f}%')
    if board is not None and str(board).upper()=='TOO LATE':veto.append('DECISION BOARD TOO LATE')
    veto=list(dict.fromkeys(veto))
    actionable=bool(confirmed and not veto)
    if actionable:
        state='ACTIONABLE PRE-MOVE NOW';reason='High-confidence multi-family pattern + timing/data gates still early'
    elif confirmed and any('RETEST' in x or 'AGING' in x or 'CONSUMED' in x for x in veto):
        state='HIGH-CONFIDENCE PATTERN • RETEST ONLY';reason=' • '.join(veto)
    elif confirmed:
        state='HIGH-CONFIDENCE PATTERN • NOT ACTIONABLE NOW';reason=' • '.join(veto) if veto else 'Pattern confirmed, but live action gate is not open'
    elif strength=='WATCH':
        if veto:
            _vtxt=' • '.join(veto).upper()
            # V6.3.9.65 — blocker hierarchy. The headline must name the primary
            # execution problem instead of collapsing every severe veto into CHASE.
            if 'LIQUIDITY BLOCK' in _vtxt:
                state='PRE-MOVE WATCH • LIQUIDITY BLOCK'
            elif any(x in _vtxt for x in ('STALE','UNVERIFIED SESSION DATA','DATA QUALITY','MARKET CLOSED')):
                state='PRE-MOVE WATCH • RECHECK / DATA BLOCK'
            elif any(x in _vtxt for x in ('RETEST','TOO LATE','MOVE ') ) and ('CONSUMED' in _vtxt or 'RETEST' in _vtxt or 'TOO LATE' in _vtxt):
                state='PRE-MOVE WATCH • RETEST / LATE'
            elif any(x in _vtxt for x in ('CHASE HIGH','CHASE EXTREME','EXTENDED')):
                state='PRE-MOVE WATCH • EXTENDED / DO NOT CHASE'
            else:
                state='PRE-MOVE WATCH • NOT ACTIONABLE NOW'
            reason=' • '.join(veto)+' • another independent confirmation is still required'
        else:
            state='PRE-MOVE WATCH ONLY';reason='Promising pattern; another independent confirmation is still required'
    elif strength=='RAW':
        state='RAW ACCUMULATION ONLY';reason='Research context only; insufficient independent confirmation'
    else:
        state='PATTERN PERSISTS • MOVE NOT EARLY';reason='Accumulation evidence persists after the early-entry window'
    return strength,actionable,state,reason

def _pre_move_radar_enrich_v63959(df):
    """Rank pattern detection separately from current Pre-Move actionability."""
    if df is None or not isinstance(df,pd.DataFrame) or df.empty:return df
    z=df.copy()
    strength=z.get('PreMovePatternStrength',pd.Series('NONE',index=z.index)).fillna('NONE').astype(str).str.upper()
    eligible=strength.isin(['HIGH','WATCH'])
    action=z.get('PreMoveActionableNow',pd.Series(False,index=z.index)).fillna(False).astype(bool)
    z['PreMovePatternDetected']=eligible
    z['PreMoveRadarEligible']=eligible  # compatibility: pattern belongs on the radar
    z['PreMoveRadarActionable']=eligible & action
    z['PreMovePatternOnly']=eligible & ~z['PreMoveRadarActionable']
    z['PreMoveRadarRank']=pd.Series(pd.NA,index=z.index,dtype='Int64')
    statuses=[]
    for ix,r in z.iterrows():
        stg=str(r.get('PreMovePatternStrength','NONE') or 'NONE').upper()
        eff=str(r.get('EffectiveDecisionStage',r.get('DecisionBoardStage','WAIT')) or 'WAIT').upper()
        act=bool(r.get('PreMoveRadarActionable',r.get('PreMoveActionableNow',False)))
        astate=str(r.get('PreMoveActionabilityState','') or '').upper();areason=str(r.get('PreMoveActionabilityReason','') or '').upper()
        retest=('RETEST' in astate or 'RETEST' in areason or eff=='RETEST')
        liq_block=('LIQUIDITY BLOCK' in astate or 'LIQUIDITY BLOCK' in areason or not bool(r.get('LiquidityHardGateOK',True)))
        data_block=any(x in (astate+' • '+areason) for x in ('STALE','UNVERIFIED SESSION DATA','DATA QUALITY','MARKET CLOSED'))
        late_block=(retest or eff=='TOO LATE' or 'TOO LATE' in astate or 'TOO LATE' in areason)
        chase_block=('DO NOT CHASE' in astate or any(x in areason for x in ('CHASE HIGH','CHASE EXTREME','EXTENDED CONTEXT')))
        # V6.3.9.65 primary blocker priority:
        # Liquidity -> data freshness -> retest/late -> extension/chase -> generic watch.
        if stg=='HIGH' and act:status='HIGH PRE-MOVE • ACTIONABLE EARLY'
        elif stg=='HIGH' and liq_block:status='HIGH PRE-MOVE PATTERN • LIQUIDITY BLOCK'
        elif stg=='HIGH' and data_block:status='HIGH PRE-MOVE PATTERN • RECHECK / DATA BLOCK'
        elif stg=='HIGH' and late_block:status='HIGH PRE-MOVE PATTERN • RETEST / LATE'
        elif stg=='HIGH' and chase_block:status='HIGH PRE-MOVE PATTERN • EXTENDED / DO NOT CHASE'
        elif stg=='HIGH':status='HIGH PRE-MOVE PATTERN • WATCH'
        elif stg=='WATCH' and liq_block:status='PRE-MOVE WATCH • LIQUIDITY BLOCK'
        elif stg=='WATCH' and data_block:status='PRE-MOVE WATCH • RECHECK / DATA BLOCK'
        elif stg=='WATCH' and late_block:status='PRE-MOVE WATCH • RETEST / LATE'
        elif stg=='WATCH' and chase_block:status='PRE-MOVE WATCH • EXTENDED / DO NOT CHASE'
        elif stg=='WATCH':status='PRE-MOVE WATCH'
        else:status='NOT IN TOP PRE-MOVE RADAR'
        statuses.append(status)
    z['PreMoveRadarStatus']=statuses
    if bool(eligible.any()):
        _tier=strength.map({'HIGH':0,'WATCH':1}).fillna(9)
        _action=z['PreMoveRadarActionable'].astype(int)
        _score=pd.to_numeric(z.get('PreBreakoutAccumulationScore',pd.Series(np.nan,index=z.index)),errors='coerce').fillna(-1)
        _fam=pd.to_numeric(z.get('PreMoveFamilyCount',pd.Series(0,index=z.index)),errors='coerce').fillna(0)
        _flow=pd.to_numeric(z.get('NetFlowBalance',z.get('MoneyFlowScore',pd.Series(0,index=z.index))),errors='coerce').fillna(0)
        _mom=z.get('MomentumState',pd.Series('NO DATA',index=z.index)).fillna('NO DATA').astype(str).str.upper().map({'STRENGTHENING':3,'STABLE':2,'MIXED':1,'COOLING':0,'BEARISH':-1}).fillna(0)
        _dec=pd.to_numeric(z.get('DecisionRankScore',pd.Series(np.nan,index=z.index)),errors='coerce').fillna(-1)
        _tmp=pd.DataFrame({'idx':z.index,'tier':_tier,'action':_action,'score':_score,'fam':_fam,'flow':_flow,'mom':_mom,'dec':_dec}).set_index('idx')
        _idx=_tmp.loc[eligible].sort_values(['tier','action','score','fam','flow','mom','dec'],ascending=[True,False,False,False,False,False,False],na_position='last',kind='stable').index
        for pos,ix in enumerate(_idx,1):z.at[ix,'PreMoveRadarRank']=pos
    return z

def _decision_board_enrich_v63948(df):
    if df is None or not isinstance(df,pd.DataFrame) or df.empty:return df
    z=df.copy();boards=[];wins=[];reasons=[];timings=[];triggers=[];early_flags=[];early_scores=[];early_reasons=[];retestq=[]
    pm_strength=[];pm_action=[];pm_state=[];pm_reason=[]
    for _,r in z.iterrows():
        er,es,ew=_live_early_radar_v63949(r);b,w,why,tc=_decision_board_state_v63948(r)
        ps,pa,pst,pr=_pre_move_actionability_v63957(r,b)
        boards.append(b);wins.append(w);reasons.append(why);timings.append(tc);triggers.append(_trigger_timing_label_v63948(r));early_flags.append(er);early_scores.append(es);early_reasons.append(ew);retestq.append(_retest_qualified_v63949(r))
        pm_strength.append(ps);pm_action.append(pa);pm_state.append(pst);pm_reason.append(pr)
    z['DecisionBoardStage']=boards;z['OpportunityWindow']=wins;z['OpportunityWindowReason']=reasons;z['TimingContext']=timings;z['TriggerTimingDisplay']=triggers
    z['DecisionBoardStage']=[_decision_stage_canonical_v63961(x) for x in z['DecisionBoardStage']];z['RawDecisionBoardStage']=z['DecisionBoardStage'].astype(str)
    _eff=[];_disp=[];_eff_reason=[];_reval=[];_live_gate=[];_live_gate_reason=[];_now_phase=[]
    for _,_r in z.iterrows():
        _ok,_why=_entry_now_hard_gate_v63958(_r);_e,_d,_er,_rv,_lwhy=_effective_decision_stage_v63958(_r,_r.get('DecisionBoardStage','WAIT'));_rv2,_np,_rr=_current_session_revalidation_v63958(_r)
        _eff.append(_e);_disp.append(_d);_eff_reason.append(_er);_reval.append(bool(_rv or _rv2));_live_gate.append(bool(_ok));_live_gate_reason.append(_why);_now_phase.append(_np)
    z['EffectiveDecisionStage']=[_decision_stage_canonical_v63961(x) for x in _eff];z['DecisionDisplayStage']=[_decision_stage_canonical_v63961(x) for x in _disp];z['DecisionStageLabel']=[_decision_stage_display_v63960(x) for x in _disp];z['EffectiveDecisionReason']=_eff_reason;z['NeedsOpenRevalidation']=_reval;z['EntryNowHardGateOK']=_live_gate;z['EntryNowHardGateReason']=_live_gate_reason;z['CurrentMarketPhaseNow']=_now_phase
    # V6.3.9.64: ActionableNow is the final live decision, not the raw Entry-engine flag.
    _raw_actionable=z.get('ActionableNow',pd.Series(False,index=z.index)).fillna(False).astype(bool)
    z['ActionableNow']=_raw_actionable & z['EntryNowHardGateOK'].fillna(False).astype(bool)
    _aq=[];_aqs=[];_aqr=[]
    for _,_r in z.iterrows():
        _ok,_why=_armed_qualification_v63961(_r);_aq.append(bool(_ok));_aqs.append('QUALIFIED' if _ok else 'BLOCKED / INCOMPLETE');_aqr.append(_why)
    z['ArmedQualified']=_aq;z['ArmedQualificationState']=_aqs;z['ArmedQualificationReason']=_aqr
    z['LiveEarlyRadarCandidate']=early_flags;z['LiveEarlyRadarScore']=early_scores;z['LiveEarlyRadarReason']=early_reasons;z['RetestQualifiedSetup']=retestq
    z['PreMovePatternStrength']=pm_strength;z['PreMoveActionableNow']=pm_action;z['PreMoveActionabilityState']=pm_state;z['PreMoveActionabilityReason']=pm_reason
    # V6.3.9.63: never render an old-session raw CONFIRMED ENTRY as if it were live.
    _raw_trade=z.get('TradeStage',z.get('EntryTriggerState',pd.Series('WAIT',index=z.index))).fillna('WAIT').astype(str)
    _phase=z.get('MarketPhase',pd.Series('UNKNOWN',index=z.index)).fillna('UNKNOWN').astype(str).str.upper()
    _effs=z.get('EffectiveDecisionStage',pd.Series('WAIT',index=z.index)).fillna('WAIT').astype(str).str.upper()
    _prev=(_effs.eq('LAST SESSION ENTRY') | (_raw_trade.str.upper().eq('CONFIRMED ENTRY') & _phase.isin(['CLOSED','AFTER-MARKET','PRE-OPEN'])))
    z['TradeStageDisplay']=_raw_trade
    z.loc[_prev,'TradeStageDisplay']='PREVIOUS SESSION CONFIRMED ENTRY'
    # Raw LiveRR remains in Excel for audit. Headline/filter R:R exists only inside
    # a fresh price-actionable live context, preventing absurd/stale values (e.g.
    # when current price is outside the entry geometry) from looking actionable.
    _price_ok=z.get('PriceActionableNow',pd.Series(False,index=z.index)).fillna(False).astype(bool)
    _sess_ok=z.get('SessionDataFresh',pd.Series(False,index=z.index)).fillna(False).astype(bool)
    _livepx=z.get('LivePriceFresh',pd.Series(False,index=z.index)).fillna(False).astype(bool)
    _rr_phase=_phase.isin(['OPEN','PRE-MARKET'])
    _liq_ok=z.get('LiquidityHardGateOK',pd.Series(True,index=z.index)).fillna(False).astype(bool)
    _plan_ok=z.get('PlanValid',pd.Series(True,index=z.index)).fillna(False).astype(bool)
    _rr_base_ctx=_price_ok & _sess_ok & _livepx & _rr_phase & ~_prev & _plan_ok
    _rr_ctx=_rr_base_ctx & _liq_ok
    _rr_research_liq=_rr_base_ctx & ~_liq_ok
    _rr1=pd.to_numeric(z.get('LiveRR_T1',pd.Series(np.nan,index=z.index)),errors='coerce')
    _rr2=pd.to_numeric(z.get('LiveRR_T2',pd.Series(np.nan,index=z.index)),errors='coerce')
    # Raw LiveRR remains auditable. A liquidity-blocked plan can show its geometry
    # only as RESEARCH R:R; it can never be labelled LIVE R:R.
    z['LiveRRDisplayT1']=_rr1.where(_rr_ctx | _rr_research_liq)
    z['LiveRRDisplayT2']=_rr2.where(_rr_ctx | _rr_research_liq)
    _rr_status=pd.Series('LIVE R:R',index=z.index,dtype='object')
    _rr_status.loc[~_price_ok]='N/A — PRICE OUTSIDE ENTRY CONTEXT'
    _rr_status.loc[_price_ok & ~_rr_phase]='N/A — MARKET NOT LIVE'
    _rr_status.loc[_price_ok & _rr_phase & (~_sess_ok | ~_livepx)]='N/A — STALE / UNVERIFIED LIVE DATA'
    _rr_status.loc[_price_ok & _sess_ok & _livepx & _rr_phase & ~_prev & ~_plan_ok]='N/A — PLAN INVALID'
    _rr_status.loc[_rr_research_liq]='RESEARCH R:R — LIQUIDITY BLOCK'
    _rr_status.loc[(_rr_ctx | _rr_research_liq) & _rr1.isna()]='N/A — R:R UNAVAILABLE'
    z['LiveRRDisplayStatus']=_rr_status
    _rs=pd.to_numeric(z.get('DecisionRankScore',z.get('TopScore',pd.Series(np.nan,index=z.index))),errors='coerce')
    z['OverallStrengthRank']=_rs.rank(method='first',ascending=False,na_option='bottom').astype('Int64')
    z['ActionQueueRank']=pd.Series(pd.NA,index=z.index,dtype='Int64')
    for _stage,_g in z.groupby('EffectiveDecisionStage',dropna=False):
        _idx=_g.assign(_RankScore=_rs.loc[_g.index]).sort_values(['_RankScore'],ascending=False,na_position='last').index
        for _pos,_ix in enumerate(_idx,1):z.at[_ix,'ActionQueueRank']=_pos
    return _pre_move_radar_enrich_v63959(z)


def _signal_memory_candidate_v63955(row):
    """Whether this snapshot is meaningful enough to start persistent move memory.

    V6.3.9.56 intentionally does NOT start memory from raw accumulation alone.
    Only an actual decision-stage signal, continuation signal, research Pre-Move
    candidate, or the new multi-family HIGH-CONFIDENCE PRE-MOVE can start a move.
    """
    board=str(row.get('DecisionBoardStage','') or '').upper()
    stage=str(row.get('TradeStage',row.get('EntryTriggerState','')) or '').upper()
    pre=str(row.get('PreMoveStage','') or '').upper()
    acc=str(row.get('PreBreakoutAccumulationStage','') or '').upper()
    cont=str(row.get('ContinuationEntryState','') or '').upper()
    confirmed=bool(row.get('PreMoveConfirmed',row.get('pre_move_confirmed',False))) or 'HIGH-CONFIDENCE PRE-MOVE' in acc
    return bool(
        _decision_stage_canonical_v63961(board) in ('BUILDING SETUP','ARMED','ENTRY NOW') or
        stage in ('ARMED','CONFIRMED ENTRY') or
        'PRE-MOVE CANDIDATE' in pre or
        confirmed or
        cont in ('WATCH','READY')
    )


def _active_signal_deep_tickers_v63956(max_age_days=21):
    """Return tickers whose existing move deserves a reserved Deep slot.

    Uses signal_memory first and recent Feedback snapshots as a migration/backfill
    path, so a stock identified before this version (e.g. an earlier ENTRY NOW)
    cannot disappear only because SMART quota ranks newer names above it.
    """
    keep=set();now=pd.Timestamp.now(tz='UTC')
    try:con=_feedback_conn_v600()
    except Exception:return []
    def recent(ts):
        try:
            x=pd.to_datetime(ts,utc=True);return bool(pd.notna(x) and (now-x).total_seconds()<=max_age_days*86400)
        except Exception:return False
    def meaningful(board='',stage='',entry='',orig=''):
        b=str(board or '').upper();s=str(stage or '').upper();e=str(entry or '').upper();o=str(orig or '').upper()
        return bool(_decision_stage_canonical_v63961(b) in ('BUILDING SETUP','ARMED','ENTRY NOW','LAST SESSION ENTRY') or s in ('ARMED','CONFIRMED ENTRY') or e=='CONFIRMED ENTRY' or 'HIGH-CONFIDENCE PRE-MOVE' in o or 'PRE-MOVE CANDIDATE' in o)
    try:
        for t,ts,stg,active in con.execute("SELECT ticker,original_signal_ts,original_signal_stage,active FROM signal_memory WHERE active=1").fetchall():
            if t and recent(ts) and meaningful(orig=stg):keep.add(str(t).upper().strip())
        # Backfill from the latest recent snapshot for tickers that pre-date the
        # signal_memory table. Latest state is used so a later TOO LATE/invalidated
        # observation does not remain reserved forever.
        rows=con.execute("SELECT ticker,ts_utc,decision_board_stage,trade_stage,entry_state,original_signal_stage FROM snapshots ORDER BY id DESC LIMIT 6000").fetchall()
        seen=set()
        for t,ts,b,st,e,o in rows:
            tt=str(t or '').upper().strip()
            if not tt or tt in seen:continue
            seen.add(tt)
            if recent(ts) and meaningful(b,st,e,o):keep.add(tt)
    except Exception:pass
    try:con.close()
    except Exception:pass
    return sorted(keep)


def _legacy_original_signal_seed_v63961(ticker):
    """One-time verified migration for pre-memory Scanner lineage.

    These values come from the user's own V6.3.9.47 Analyze export, before the
    persistent Original-Signal table existed.  The seed is used only when no
    earlier genuine Feedback memory is available; it is never derived from the
    current trigger.  The structure is intentionally generic so future verified
    legacy migrations can be added without changing the memory algorithm.
    """
    seeds={
        '1780.HK':{
            'time':'2026-09-28T02:15:00+00:00',
            'stage':'ARMED',
            'price':5.054999828338623,
            'trigger':5.054999828338623,
            'trigger_time':'2026-09-28 10:15:00+08:00',
            't1':5.976532370412917,
            'inv':4.885402945981707,
            'source':'V6.3.9.62 LEGACY VERIFIED V6.3.9.47 USER SCAN',
            'signal_id':'1780.HK|2026-09-28T02:15:00+00:00',
            'locked_ts':'2026-09-28T02:15:00+00:00',
            'event_id':'LEGACY-1780-V63947'
        }
    }
    x=seeds.get(str(ticker or '').upper().strip())
    return dict(x) if isinstance(x,dict) else None


def _signal_memory_enrich_v63955(df):
    """Attach a true historical Original Signal and a separate current trigger.

    V6.3.9.57 integrity rules:
    - Original is loaded only from persisted memory or a prior Feedback snapshot.
    - Current Trigger/T1 are always calculated separately.
    - Current is never copied into Original merely to fill the display.
    - V6.3.9.55/.56 memories are repaired from an earlier Feedback event when one
      exists, so previously manufactured Original==Current rows can self-heal.
    """
    if df is None or not isinstance(df,pd.DataFrame) or df.empty:return df
    z=df.copy()
    defaults={
        'OriginalSignalId':'—','OriginalSignalTime':'—','OriginalSignalStage':'NO MEMORY','OriginalSignalPrice':np.nan,
        'OriginalTriggerPrice':np.nan,'OriginalTriggerTime':'—','OriginalTarget1':np.nan,'OriginalInvalidation':np.nan,
        'OriginalProgressToT1Pct':np.nan,'OriginalMoveSinceSignalPct':np.nan,'OriginalSignalMemorySource':'NONE',
        'OriginalMemoryIntegrity':'NO MEMORY','OriginalMemoryStatus':'MISSING','OriginalMemoryAvailable':False,'OriginalTriggerLocked':False,'OriginalEqualsCurrentTrigger':False,
        'CurrentTriggerPrice':np.nan,'CurrentTriggerTime':'—','CurrentTarget1':np.nan,'CurrentProgressToT1Pct':np.nan,
    }
    for k,v in defaults.items():
        if k not in z.columns:z[k]=v
    def num(v):
        try:
            x=float(v);return x if np.isfinite(x) else np.nan
        except Exception:return np.nan
    try:con=_feedback_conn_v600()
    except Exception:con=None
    now=pd.Timestamp.now(tz='UTC');cutoff=now-pd.Timedelta(days=21)

    def _historical_backfill(ticker,before_ts=None,preferred_event_id=None):
        """Reconstruct the earliest real signal for the *current move* from Feedback.

        Prefer the stable Feedback EventID when available. If legacy snapshots do not
        have a matching event, use the latest meaningful event/contiguous cluster —
        never the oldest unrelated signal in the whole lookback window.
        """
        if con is None:return None
        try:
            rows=con.execute("""SELECT id,ts_utc,price,trade_stage,entry_state,pre_move_stage,
                trigger_anchor_price,trigger_anchor_time,target1,invalidation,decision_board_stage,
                pre_breakout_accumulation_stage,pre_move_confirmed,confirmed_entry_gate,price_actionable,
                trigger,current_trigger_price,current_trigger_time,current_target1,event_id,event_origin_ts_utc
                FROM snapshots WHERE ticker=? ORDER BY id ASC""",(ticker,)).fetchall()
        except Exception:return None
        parsed=[]
        for rr in rows:
            try:ts=pd.to_datetime(rr[1],utc=True)
            except Exception:continue
            if pd.isna(ts) or ts<(now-pd.Timedelta(days=90)):continue
            if before_ts is not None:
                try:
                    if ts>=pd.to_datetime(before_ts,utc=True):continue
                except Exception:pass
            trade=str(rr[3] or '').upper();entry=str(rr[4] or '').upper();pre=str(rr[5] or '').upper();board=str(rr[10] or '').upper();acc=str(rr[11] or '').upper()
            pm_conf=bool(int(rr[12] or 0));confirmed_gate=bool(int(rr[13] or 0));price_action=bool(int(rr[14] or 0))
            meaningful=(
                _decision_stage_canonical_v63961(board) in ('BUILDING SETUP','ARMED','ENTRY NOW','LAST SESSION ENTRY') or
                any(x in trade for x in ('ARMED','CONFIRMED ENTRY')) or
                any(x in entry for x in ('ARMED','CONFIRMED ENTRY')) or
                'PRE-MOVE CANDIDATE' in pre or 'HIGH-CONFIDENCE PRE-MOVE' in acc or
                pm_conf or (confirmed_gate and price_action)
            )
            if meaningful:parsed.append((ts,rr,str(rr[19] or '').strip()))
        if not parsed:return None

        # Event-aware selection. If current SetupOrigin produces a known EventID,
        # reconstruct only that move. Otherwise choose the latest historical event,
        # then its earliest meaningful snapshot.
        usable=[];method='LATEST CONTIGUOUS FEEDBACK'
        pe=str(preferred_event_id or '').strip()
        if pe:
            usable=[x for x in parsed if x[2] and x[2]==pe]
            if usable:method='MATCHED FEEDBACK EVENT'
        if not usable:
            with_event=[x for x in parsed if x[2]]
            if with_event:
                latest_event=sorted(with_event,key=lambda x:x[0])[-1][2]
                usable=[x for x in with_event if x[2]==latest_event];method='LATEST FEEDBACK EVENT'
            else:
                # Legacy rows: take the latest contiguous meaningful cluster. A gap
                # greater than 7 calendar days starts a new move.
                clusters=[];cur=[];prev=None
                for item in sorted(parsed,key=lambda x:x[0]):
                    if prev is not None and (item[0]-prev).total_seconds()>7*86400:
                        if cur:clusters.append(cur)
                        cur=[]
                    cur.append(item);prev=item[0]
                if cur:clusters.append(cur)
                usable=clusters[-1] if clusters else []
        if not usable:return None
        usable=sorted(usable,key=lambda x:x[0]);ots,orr,_=usable[0]
        trig=np.nan;trig_time='—';t1=np.nan;inv=np.nan;lock_ts='—'
        # Lock the FIRST causal trigger that appears at/after the earliest signal.
        for uts,rr,_ev in usable:
            candidates=[num(rr[6]),num(rr[15]),num(rr[16])]
            tv=next((x for x in candidates if np.isfinite(x) and x>0),np.nan)
            if np.isfinite(tv):
                trig=tv;trig_time=str(rr[7] or rr[17] or '—');lock_ts=uts.isoformat();t1=num(rr[8]);inv=num(rr[9])
                if not np.isfinite(t1):t1=num(rr[18])
                break
        bstage=str(orr[10] or orr[3] or orr[4] or orr[11] or 'EARLY SIGNAL')
        sid=f"{ticker}|{ots.isoformat()}"
        return {'time':ots.isoformat(),'stage':bstage,'price':orr[2],'trigger':trig,'trigger_time':trig_time,'t1':t1,'inv':inv,'source':f'V6.3.9.62 {method}','signal_id':sid,'locked_ts':lock_ts,'candidate_count':len(usable),'event_id':str(orr[19] or '')}


    for ix,r in z.iterrows():
        ticker=str(r.get('Ticker','') or '').upper().strip()
        if not ticker:continue
        px=num(r.get('Price'));curtr=num(r.get('TriggerAnchorPrice',r.get('BreakoutTrigger',np.nan)));curt1=num(r.get('Target1'));curtime=str(r.get('TriggerAnchorTime','—') or '—')
        curprog=num(r.get('PostTriggerConsumedPct',np.nan))
        if not np.isfinite(curprog) and np.isfinite(px) and np.isfinite(curtr) and np.isfinite(curt1) and curt1>curtr:curprog=100.0*(px-curtr)/(curt1-curtr)
        z.at[ix,'CurrentTriggerPrice']=curtr;z.at[ix,'CurrentTriggerTime']=curtime;z.at[ix,'CurrentTarget1']=curt1;z.at[ix,'CurrentProgressToT1Pct']=curprog
        _preferred_event_id=''
        try:
            if str(r.get('SetupOriginTime','') or '').strip() not in ('','—','nan','None'):_preferred_event_id=_feedback_event_id_v63934(r,now.isoformat())
        except Exception:_preferred_event_id=''

        mem=None;integrity='NO MEMORY';known_memory=False;rec=None
        if con is not None:
            try:rec=con.execute("SELECT original_signal_ts,original_signal_stage,original_signal_price,original_trigger_price,original_trigger_time,original_target1,original_invalidation,source,active,updated_ts,signal_id,trigger_locked_ts FROM signal_memory WHERE ticker=?",(ticker,)).fetchone()
            except Exception:rec=None
        if rec:
            known_memory=True;active=bool(int(rec[8] or 0))
            mem={'time':rec[0],'stage':rec[1],'price':rec[2],'trigger':rec[3],'trigger_time':rec[4],'t1':rec[5],'inv':rec[6],'source':rec[7] or 'PERSISTED','signal_id':rec[10] or '—','locked_ts':rec[11] or '—'}
            integrity=('LOCKED PERSISTED' if active else 'LOCKED CLOSED')
            # V6.3.9.59: always compare persisted memory to EARLIER Feedback evidence.
            # This repairs memories created by any later version/source, not only .55/.56.
            hist=_historical_backfill(ticker,preferred_event_id=_preferred_event_id)
            # If a later persisted memory has no same-event predecessor, look just
            # before its timestamp. This recovers legacy daily-reset events such as
            # 1780 without jumping back to an unrelated old move.
            if (not hist) and mem.get('time'):
                prior=_historical_backfill(ticker,before_ts=mem.get('time'))
                if prior:
                    try:
                        gap=(pd.to_datetime(mem.get('time'),utc=True)-pd.to_datetime(prior.get('time'),utc=True)).total_seconds()/86400.0
                        if 0<=gap<=7:hist=prior
                    except Exception:pass
            repair=False
            if hist:
                try:
                    hts=pd.to_datetime(hist.get('time'),utc=True);mts=pd.to_datetime(mem.get('time'),utc=True)
                    repair=bool(pd.notna(hts) and (pd.isna(mts) or hts<mts-pd.Timedelta(seconds=1)))
                except Exception:repair=False
                if not np.isfinite(num(mem.get('price'))) or str(mem.get('stage','')).upper() in ('','NO MEMORY'):repair=True
                if not np.isfinite(num(mem.get('trigger'))) and np.isfinite(num(hist.get('trigger'))):repair=True
            if repair:
                mem=hist;integrity='REPAIRED EARLIEST FEEDBACK BACKFILL'
                try:
                    con.execute("UPDATE signal_memory SET original_signal_ts=?,original_signal_stage=?,original_signal_price=?,original_trigger_price=?,original_trigger_time=?,original_target1=?,original_invalidation=?,source=?,signal_id=?,trigger_locked_ts=?,updated_ts=? WHERE ticker=?",(mem.get('time'),mem.get('stage'),num(mem.get('price')),num(mem.get('trigger')),mem.get('trigger_time'),num(mem.get('t1')),num(mem.get('inv')),'V6.3.9.62 EARLIEST FEEDBACK BACKFILL',mem.get('signal_id'),mem.get('locked_ts'),now.isoformat(),ticker));con.commit()
                    mem['source']='V6.3.9.62 EARLIEST FEEDBACK BACKFILL'
                except Exception:pass
        # Verified pre-memory migration may repair a later persisted memory, but it
        # never overrides an earlier genuine Feedback signal.
        _legacy_seed=_legacy_original_signal_seed_v63961(ticker)
        if _legacy_seed and mem is not None:
            _use_legacy=False
            if mem is not None:
                try:
                    _lt=pd.to_datetime(_legacy_seed.get('time'),utc=True);_mt=pd.to_datetime(mem.get('time'),utc=True)
                    _use_legacy=bool(pd.notna(_lt) and (pd.isna(_mt) or _lt<_mt-pd.Timedelta(seconds=1)))
                except Exception:_use_legacy=False
            if _use_legacy:
                mem=_legacy_seed;integrity='BACKFILLED VERIFIED LEGACY SCAN'
                try:
                    _lp=num(mem.get('t1'));_inv=num(mem.get('inv'));_active=0
                    if np.isfinite(px) and np.isfinite(_lp) and px<_lp and (not np.isfinite(_inv) or px>_inv):_active=1
                    if con is not None:
                        con.execute("INSERT OR REPLACE INTO signal_memory(ticker,market,original_signal_ts,original_signal_stage,original_signal_price,original_trigger_price,original_trigger_time,original_target1,original_invalidation,source,active,updated_ts,signal_id,trigger_locked_ts) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(ticker,str(r.get('Market','') or _market_for_ticker_v612(ticker)),mem.get('time'),mem.get('stage'),num(mem.get('price')),num(mem.get('trigger')),mem.get('trigger_time'),num(mem.get('t1')),num(mem.get('inv')),mem.get('source'),_active,now.isoformat(),mem.get('signal_id'),mem.get('locked_ts')));con.commit()
                except Exception:pass
        if mem:
            try:
                age=(now-pd.to_datetime(mem.get('time'),utc=True)).total_seconds()/86400.0
                if age>90:mem=None;integrity='NO MEMORY'
            except Exception:pass
        # If no usable persisted memory exists, rebuild from the earliest prior signal.
        # The backfill is historical/audit only; it does NOT automatically mark a closed
        # signal as active or reserve a Deep slot.
        if mem is None:
            hist=_historical_backfill(ticker,preferred_event_id=_preferred_event_id)
            if hist:
                mem=hist;integrity='BACKFILLED EARLIEST FEEDBACK'
                if not known_memory:
                    try:
                        con.execute("INSERT OR REPLACE INTO signal_memory(ticker,market,original_signal_ts,original_signal_stage,original_signal_price,original_trigger_price,original_trigger_time,original_target1,original_invalidation,source,active,updated_ts,signal_id,trigger_locked_ts) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(ticker,str(r.get('Market','') or _market_for_ticker_v612(ticker)),mem.get('time'),mem.get('stage'),num(mem.get('price')),num(mem.get('trigger')),mem.get('trigger_time'),num(mem.get('t1')),num(mem.get('inv')),'V6.3.9.62 EARLIEST FEEDBACK BACKFILL',0,now.isoformat(),mem.get('signal_id'),mem.get('locked_ts')));con.commit()
                        mem['source']='V6.3.9.62 EARLIEST FEEDBACK BACKFILL'
                    except Exception:pass
        # Final migration path for verified pre-memory Scanner artifacts.  This is
        # deliberately later than Feedback backfill so real persisted history wins.
        if mem is None:
            legacy=_legacy_original_signal_seed_v63961(ticker)
            if legacy:
                mem=legacy;integrity='BACKFILLED VERIFIED LEGACY SCAN'
                try:
                    _active=0
                    _lp=num(mem.get('t1'));_inv=num(mem.get('inv'))
                    if np.isfinite(px) and np.isfinite(_lp) and px<_lp and (not np.isfinite(_inv) or px>_inv):_active=1
                    if con is not None:
                        con.execute("INSERT OR REPLACE INTO signal_memory(ticker,market,original_signal_ts,original_signal_stage,original_signal_price,original_trigger_price,original_trigger_time,original_target1,original_invalidation,source,active,updated_ts,signal_id,trigger_locked_ts) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(ticker,str(r.get('Market','') or _market_for_ticker_v612(ticker)),mem.get('time'),mem.get('stage'),num(mem.get('price')),num(mem.get('trigger')),mem.get('trigger_time'),num(mem.get('t1')),num(mem.get('inv')),mem.get('source'),_active,now.isoformat(),mem.get('signal_id'),mem.get('locked_ts')));con.commit()
                except Exception:pass
        if not mem:continue
        op=num(mem.get('price'));ot=num(mem.get('trigger'));t1=num(mem.get('t1'))
        progress=100.0*(px-ot)/(t1-ot) if np.isfinite(px) and np.isfinite(ot) and np.isfinite(t1) and t1>ot else np.nan
        move=100.0*(px/op-1.0) if np.isfinite(px) and np.isfinite(op) and op>0 else np.nan
        same=bool(np.isfinite(ot) and np.isfinite(curtr) and abs(ot-curtr)<=max(1e-8,abs(ot)*1e-6))
        z.at[ix,'OriginalSignalId']=str(mem.get('signal_id','—'));z.at[ix,'OriginalSignalTime']=str(mem.get('time','—'));z.at[ix,'OriginalSignalStage']=str(mem.get('stage','EARLY SIGNAL'));z.at[ix,'OriginalSignalPrice']=op
        z.at[ix,'OriginalTriggerPrice']=ot;z.at[ix,'OriginalTriggerTime']=str(mem.get('trigger_time','—'));z.at[ix,'OriginalTarget1']=t1;z.at[ix,'OriginalInvalidation']=num(mem.get('inv'))
        z.at[ix,'OriginalProgressToT1Pct']=progress;z.at[ix,'OriginalMoveSinceSignalPct']=move;z.at[ix,'OriginalSignalMemorySource']=str(mem.get('source','PERSISTED'))
        z.at[ix,'OriginalMemoryIntegrity']=integrity;z.at[ix,'OriginalTriggerLocked']=bool(np.isfinite(ot));z.at[ix,'OriginalEqualsCurrentTrigger']=same
        _src=str(mem.get('source','') or '').upper();_integ=str(integrity or '').upper()
        if 'BACKFILL' in _integ or 'BACKFILL' in _src:_mstat='BACKFILLED'
        elif 'SCANNER' in _src:_mstat='NEW'
        else:_mstat='PERSISTED'
        z.at[ix,'OriginalMemoryStatus']=_mstat;z.at[ix,'OriginalMemoryAvailable']=True
    if con is not None:
        try:con.close()
        except Exception:pass
    return z

def _signal_memory_persist_v63955(con,row,ts_utc):
    """Persist the first signal and lock its first causal trigger exactly once."""
    if con is None:return
    ticker=str(row.get('Ticker','') or '').upper().strip()
    if not ticker:return
    market=str(row.get('Market','') or _market_for_ticker_v612(ticker))
    def num(v):
        try:
            x=float(v);return x if np.isfinite(x) else None
        except Exception:return None
    try:
        existing=con.execute("SELECT original_signal_ts,original_signal_stage,original_signal_price,original_trigger_price,original_trigger_time,original_target1,original_invalidation,active,signal_id,trigger_locked_ts FROM signal_memory WHERE ticker=?",(ticker,)).fetchone()
    except Exception:return
    current_candidate=_signal_memory_candidate_v63955(row)
    stage=str(row.get('TradeStage',row.get('EntryTriggerState','')) or '').upper();px=num(row.get('Price'))
    curtr=num(row.get('TriggerAnchorPrice',row.get('BreakoutTrigger')));curtr_time=str(row.get('TriggerAnchorTime','—') or '—');curt1=num(row.get('Target1'));curinv=num(row.get('Invalidation'))
    if existing and int(existing[7] or 0)==1:
        vals=list(existing[:7]);signal_id=str(existing[8] or f"{ticker}|{existing[0]}");locked_ts=existing[9]
        # Radar-only memories may not have had a causal trigger yet. Lock it once,
        # together with the target/invalidation from that same trigger snapshot.
        if vals[3] is None and curtr is not None:
            vals[3]=curtr;vals[4]=curtr_time;vals[5]=curt1;vals[6]=curinv;locked_ts=ts_utc
        inv=vals[6];t1=vals[5]
        active=0 if ('INVALIDATED' in stage or (px is not None and inv is not None and px<=inv) or (px is not None and t1 is not None and px>=t1)) else 1
        con.execute("UPDATE signal_memory SET original_trigger_price=?,original_trigger_time=?,original_target1=?,original_invalidation=?,active=?,updated_ts=?,signal_id=?,trigger_locked_ts=? WHERE ticker=?",(vals[3],vals[4],vals[5],vals[6],active,ts_utc,signal_id,locked_ts,ticker))
        return
    if not current_candidate:return
    # New memory is written only after the snapshot is complete. On this very scan
    # the UI deliberately shows NO ORIGINAL MEMORY; on the next scan this row is the
    # persisted historical Original reference.
    sig_time=str(ts_utc);sig_stage=str(row.get('DecisionBoardStage') or stage or 'EARLY SIGNAL');sig_price=px
    signal_id=f"{ticker}|{sig_time}"
    locked_ts=ts_utc if curtr is not None else None
    con.execute("INSERT OR REPLACE INTO signal_memory(ticker,market,original_signal_ts,original_signal_stage,original_signal_price,original_trigger_price,original_trigger_time,original_target1,original_invalidation,source,active,updated_ts,signal_id,trigger_locked_ts) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(ticker,market,sig_time,sig_stage,sig_price,curtr,curtr_time if curtr is not None else '—',curt1 if curtr is not None else None,curinv if curtr is not None else None,'V6.3.9.62 SIGNAL MEMORY',1,ts_utc,signal_id,locked_ts))

def _render_core_grid_v63948(row,phase):
    """Render the exact same compact core grid in Scanner and Analyze."""
    def num(v,default=np.nan):
        try:
            x=float(v);return x if np.isfinite(x) else default
        except Exception:return default
    setup=num(row.get('SetupQualityScore'),0);entry=num(row.get('EntryTimingScore',row.get('LiveActionabilityScore',row.get('EntryScore',0))),0)
    hour_oos=str(row.get('HourlyTimingSource','BASE TIMING') or 'BASE TIMING').upper().startswith('OOS LEARNED')
    hour=num(row.get('HourlyOOSTimingScore',np.nan) if hour_oos else row.get('HourlyConfirm',np.nan));hmatch=num(row.get('HourlyOptimizedMatchPct',np.nan));hh=str(row.get('HourlyOptimizedHorizon','—') or '—')
    hsub=(f"OOS {hh} • Match {hmatch:.0f}%" if hour_oos and np.isfinite(hmatch) else (f"OOS {hh}" if hour_oos else 'timing'))
    inflow=num(row.get('InflowPressure',row.get('MoneyFlowScore',50)),50);outflow=num(row.get('OutflowPressure',row.get('BearishVolumeEvidence',row.get('ExitPressure',0))),0);net=num(row.get('NetFlowBalance',inflow-outflow),inflow-outflow)
    inlab=str(row.get('InflowLabel',_inflow_label_v63922(inflow)) or _inflow_label_v63922(inflow));outlab=str(row.get('OutflowLabel',_outflow_label_v63921(outflow)) or _outflow_label_v63921(outflow));netlab=str(row.get('NetFlowLabel',_net_flow_label_v63922(net)) or _net_flow_label_v63922(net))
    rvol,rvol_band,rvol_mode=_rvol_display_v63929(row,phase);rvol_txt=f"{rvol:.2f}×" if np.isfinite(rvol) else '—'
    cons=num(row.get('MoveConsumedBeforeTriggerPct',np.nan));trigger_timing=_trigger_timing_label_v63948(row)
    recent=num(row.get('RecentRunPct',np.nan));recent_window=str(row.get('RecentRunWindow','—') or '—');recent_label=str(row.get('RecentRunLabel','NO DATA') or 'NO DATA');recent_atr=num(row.get('RecentRunATR',np.nan))
    post=num(row.get('CurrentProgressToT1Pct',row.get('PostTriggerConsumedPct',np.nan)));post_label=str(row.get('PostTriggerConsumedLabel','NO DATA') or 'NO DATA');cur_trig=num(row.get('CurrentTriggerPrice',row.get('TriggerAnchorPrice',np.nan)));cur_t1=num(row.get('CurrentTarget1',row.get('Target1',np.nan)))
    chase=str(row.get('ChaseRiskLabel','LOW') or 'LOW');cr=num(row.get('ChaseRiskScore',0),0);rr1=num(row.get('LiveRRDisplayT1',np.nan));rr2=num(row.get('LiveRRDisplayT2',np.nan));rr_status=str(row.get('LiveRRDisplayStatus','N/A — PRICE OUTSIDE ENTRY CONTEXT') or 'N/A — PRICE OUTSIDE ENTRY CONTEXT')
    momentum=str(row.get('MomentumState','NO DATA') or 'NO DATA').upper();mom15=str(row.get('MomentumState15m','NO DATA') or 'NO DATA').upper();mom1h=str(row.get('MomentumState1H','NO DATA') or 'NO DATA').upper()
    cont_state=str(row.get('ContinuationEntryState','N/A') or 'N/A').upper();cont_reason=str(row.get('ContinuationEntryReason','') or '')
    cont_vol=str(row.get('ContinuationVolumeState','NO DATA') or 'NO DATA');cont_dist=str(row.get('ContinuationDistributionState','NO DATA') or 'NO DATA')
    acc_score=num(row.get('PreBreakoutAccumulationScore',np.nan));acc_stage=str(row.get('PreBreakoutAccumulationStage','NO CURRENT ACCUMULATION SETUP') or 'NO CURRENT ACCUMULATION SETUP');acc_shock=num(row.get('VolumeShockRatio',np.nan));acc_eff=num(row.get('EffectiveVolumeShockRatio',np.nan));acc_regime=num(row.get('VolumeRegimeRatio',np.nan));acc_absorb=bool(row.get('AbsorptionCandidate',False));acc_confirmed=bool(row.get('PreMoveConfirmed',False));acc_tier=str(row.get('PreMoveConfidenceTier','NONE') or 'NONE');acc_families=int(num(row.get('PreMoveFamilyCount',0),0) or 0);acc_sig=str(row.get('PreMoveFamilySignature','NONE') or 'NONE')
    orig_prog=num(row.get('OriginalProgressToT1Pct',np.nan));orig_sig_px=num(row.get('OriginalSignalPrice',np.nan));orig_trig=num(row.get('OriginalTriggerPrice',np.nan));orig_t1=num(row.get('OriginalTarget1',np.nan));orig_time=str(row.get('OriginalSignalTime','—') or '—');orig_stage=str(row.get('OriginalSignalStage','NO MEMORY') or 'NO MEMORY');orig_integrity=str(row.get('OriginalMemoryIntegrity','NO MEMORY') or 'NO MEMORY');pm_action=bool(row.get('PreMoveActionableNow',False));pm_state=str(row.get('PreMoveActionabilityState','NO ACTIONABLE PRE-MOVE') or 'NO ACTIONABLE PRE-MOVE');pm_reason=str(row.get('PreMoveActionabilityReason','') or '')
    evn=int(num(row.get('EvidenceSampleN',row.get('BacktestN',0)),0) or 0);evq=str(row.get('EvidenceQualification',row.get('EvidenceState','UNPROVEN')) or 'UNPROVEN');evlift=num(row.get('EvidenceLiftX',row.get('SignalLift',np.nan)))
    liq=num(row.get('LiquidityScore',np.nan));liq_label=str(row.get('LiquidityLabel','NO DATA') or 'NO DATA');liq_ok=bool(row.get('LiquidityHardGateOK',True));liq_turn=num(row.get('MedianDailyTurnover60',np.nan));liq_curr=str(row.get('LiquidityTurnoverCurrency','') or '');liq_cls='good' if liq_ok and liq>=70 else ('warn' if liq_ok else 'bad');liq_txt=f'{liq:.0f}/100' if np.isfinite(liq) else '—';liq_sub=(f'{liq_label} • Median {liq_turn/1e6:.1f}M {liq_curr}' if np.isfinite(liq_turn) else liq_label)
    recent_txt=f"+{recent:.1f}%" if np.isfinite(recent) else '—';recent_sub=(f"{recent_label} • {recent_window}" if np.isfinite(recent) else 'NO DATA')
    post_txt=f"{post:.0f}%" if np.isfinite(post) else '—';rr1_txt=f"1:{rr1:.2f}" if np.isfinite(rr1) else 'N/A';rr2_txt=(f"T2 1:{rr2:.2f}" if np.isfinite(rr2) else (rr_status if not np.isfinite(rr1) else 'T2 —'));hour_txt=f"{hour:.0f}" if np.isfinite(hour) else '—';evprog=f"{evn}/12" if evn<12 else f"{evn}/12 ✓";lift_txt=f"{evlift:.2f}x" if np.isfinite(evlift) else '—'
    recent_cls='bad' if recent_label=='EXTENDED CONTEXT' else ('warn' if recent_label in ('LATE CONTEXT','MID CONTEXT') else ('good' if recent_label=='EARLY CONTEXT' else ''))
    post_cls='good' if np.isfinite(post) and post<20 else ('warn' if np.isfinite(post) and post<75 else ('bad' if np.isfinite(post) else ''));trigger_cls='good' if trigger_timing=='EARLY' else ('warn' if trigger_timing=='MID' else ('bad' if trigger_timing=='LATE' else ''))
    chase_cls='good' if chase=='LOW' and bool(row.get('ExtensionGuardCheck',True)) else ('bad' if chase in ('HIGH','EXTREME') or not bool(row.get('ExtensionGuardCheck',True)) else 'warn');flow_cls='good' if net>=8 else ('bad' if net<=-8 else 'warn')
    mom_cls='good' if momentum=='STRENGTHENING' else ('warn' if momentum in ('STABLE','MIXED','SHORT-TERM COOLING') else ('bad' if momentum in ('COOLING','BEARISH') else ''))
    cont_cls='good' if cont_state=='READY' else ('warn' if cont_state=='WATCH' else ('bad' if cont_state=='BLOCKED' else ''))
    acc_cls='good' if pm_action else ('warn' if (acc_confirmed or 'HIGH-CONFIDENCE PRE-MOVE' in acc_stage.upper() or acc_stage.upper() in ('PRE-MOVE WATCH','RAW ACCUMULATION') or 'ACCUMULATION PERSISTS' in acc_stage.upper()) else '')
    orig_cls='good' if np.isfinite(orig_prog) and orig_prog<40 else ('warn' if np.isfinite(orig_prog) and orig_prog<75 else ('bad' if np.isfinite(orig_prog) else ''))
    _acc_sub=(f'{pm_state} • ')+(f'{acc_tier} • Families {acc_families}/5 • ' if acc_tier!='NONE' else '')+('Absorption • ' if acc_absorb else '')+(f'Shock {acc_shock:.1f}x' if np.isfinite(acc_shock) else '')+(f' (effective {acc_eff:.1f}x)' if np.isfinite(acc_eff) and np.isfinite(acc_shock) and acc_shock>acc_eff else '')+(f' • Regime {acc_regime:.1f}x' if np.isfinite(acc_regime) else '')
    _cont_sub=(f'Vol: {cont_vol} • Dist: {cont_dist}') if cont_state in ('READY','WATCH','BLOCKED') else 'not in continuation path'
    st.markdown(
        "<div class='top5-grid'>"+
        f"<div class='top5-mini'><span class='lbl'>Setup</span><span class='val'>{setup:.0f}/100</span><span class='sub'>setup strength</span></div>"+
        f"<div class='top5-mini'><span class='lbl'>Entry</span><span class='val'>{entry:.0f}/100</span><span class='sub'>Gates {int(num(row.get('EntryConfirmedConditions',row.get('ConfirmedConditions',0)),0))}/{int(num(row.get('EntryTotalConditions',row.get('TotalConditions',6)),6))}</span></div>"+
        f"<div class='top5-mini'><span class='lbl'>Hourly</span><span class='val'>{hour_txt}</span><span class='sub'>{_e6395(hsub)}</span></div>"+
        f"<div class='top5-mini'><span class='lbl'>Intraday RVOL</span><span class='val'>{rvol_txt}</span><span class='sub'>{_e6395(rvol_band)} • {_e6395(rvol_mode)}</span></div>"+
        f"<div class='top5-mini'><span class='lbl'>Liquidity</span><span class='val {liq_cls}'>{liq_txt}</span><span class='sub {liq_cls}'>{_e6395(liq_sub)}</span></div>"+
        f"<div class='top5-mini'><span class='lbl'>Flow</span><span class='val {flow_cls}'>{net:+.0f}</span><span class='sub'>In {inflow:.0f} • Out {outflow:.0f}</span></div>"+
        f"<div class='top5-mini'><span class='lbl'>Momentum</span><span class='val {mom_cls}'>{_e6395(momentum)}</span><span class='sub'>15m {_e6395(mom15)} • 1H {_e6395(mom1h)}</span></div>"+
        f"<div class='top5-mini'><span class='lbl'>Continuation</span><span class='val {cont_cls}'>{_e6395(cont_state)}</span><span class='sub'>{_e6395(_cont_sub)}</span></div>"+
        f"<div class='top5-mini'><span class='lbl'>Pre-move Radar</span><span class='val {acc_cls}'>{f'{acc_score:.0f}/100' if np.isfinite(acc_score) else '—'}</span><span class='sub {acc_cls}'>{_e6395(acc_stage)} • {_e6395(_acc_sub)}</span></div>"+
        f"<div class='top5-mini'><span class='lbl'>Recent rise</span><span class='val {recent_cls}'>{recent_txt}</span><span class='sub {recent_cls}'>{_e6395(recent_sub)}</span></div>"+
        f"<div class='top5-mini'><span class='lbl'>Trigger Timing</span><span class='val {trigger_cls}'>{_e6395(trigger_timing)}</span><span class='sub'>current-session trigger</span></div>"+
        f"<div class='top5-mini'><span class='lbl'>Current Trigger → T1</span><span class='val {post_cls}'>{post_txt}</span><span class='sub {post_cls}'>{_e6395((f'{cur_trig:.3f}→{cur_t1:.3f} • ' if np.isfinite(cur_trig) and np.isfinite(cur_t1) else '')+post_label)}</span></div>"+
        f"<div class='top5-mini'><span class='lbl'>Original Trigger → T1</span><span class='val {orig_cls}'>{('TARGET REACHED • 100%+' if np.isfinite(orig_prog) and orig_prog>=100 else (f'{orig_prog:.0f}%' if np.isfinite(orig_prog) else '—'))}</span><span class='sub {orig_cls}'>{_e6395((orig_integrity+' • '+orig_stage) if np.isfinite(orig_trig) else 'NO ORIGINAL SIGNAL MEMORY')}</span></div>"+
        f"<div class='top5-mini'><span class='lbl'>Chase</span><span class='val {chase_cls}'>{_e6395(chase)}</span><span class='sub'>{cr:.0f}/100</span></div>"+
        f"<div class='top5-mini'><span class='lbl'>R:R</span><span class='val'>{rr1_txt}</span><span class='sub'>{rr2_txt}</span></div>"+
        f"<div class='top5-mini'><span class='lbl'>Evidence</span><span class='val'>{evprog}</span><span class='sub'>{_e6395(evq)} • Lift {lift_txt}</span></div>"+
        "</div>",unsafe_allow_html=True)
    # Shared entry-path explanation for Scanner + Analyze. This makes it explicit
    # why a low Trigger→T1 progress can still be WATCH rather than ENTRY NOW.
    _primary='READY' if bool(row.get('EntryZoneCheck',False)) else 'OUTSIDE'
    _retest='READY' if bool(row.get('RetestActionable',False)) else ('WAIT' if str(row.get('RetestStatus','')).upper().startswith('WAIT') else '—')
    _cont=cont_state if cont_state in ('READY','WATCH','BLOCKED') else ('READY' if bool(row.get('ContinuationEntryReady',False)) else ('WATCH' if bool(row.get('ContinuationEntryWatch',False)) else '—'))
    _path=f"Entry Path: PRIMARY {_primary} | CONTINUATION {_cont} | RETEST {_retest}"
    if cont_reason and _cont in ('WATCH','BLOCKED'): _path+=f" • Why not continuation: {cont_reason}"
    st.caption(_path)
    if np.isfinite(orig_sig_px) or np.isfinite(orig_trig):
        _oline=f"Original move memory: {orig_integrity} • {orig_stage} • signal {orig_time}"
        if np.isfinite(orig_sig_px):_oline+=f" @ {orig_sig_px:.3f}"
        if np.isfinite(orig_trig):_oline+=f" • original trigger {orig_trig:.3f}"
        if np.isfinite(orig_t1):_oline+=f" → T1 {orig_t1:.3f}"
        if np.isfinite(orig_prog):_oline+=f" • {orig_prog:.0f}% of original Trigger→T1 path used"
        st.caption(_oline)
    elif np.isfinite(cur_trig):
        st.caption(f"Original move memory: NO HISTORICAL MEMORY YET • Current trigger {cur_trig:.3f} is kept separate and is NOT copied into Original.")
    return {'setup':setup,'entry':entry,'hour':hour,'hour_sub':hsub,'inflow':inflow,'outflow':outflow,'net':net,'inflow_label':inlab,'outflow_label':outlab,'net_label':netlab,'rvol':rvol,'rvol_band':rvol_band,'rvol_mode':rvol_mode,'consumed':cons,'trigger_timing':trigger_timing,'recent':recent,'recent_atr':recent_atr,'recent_window':recent_window,'recent_label':recent_label,'post':post,'post_label':post_label,'chase':chase,'chase_score':cr,'rr1':rr1,'rr2':rr2,'ev_n':evn,'ev_q':evq,'ev_lift':evlift,'rr1_txt':rr1_txt,'rr2_txt':rr2_txt,'rr_status':rr_status,'momentum':momentum,'momentum15':mom15,'momentum1h':mom1h,'continuation_state':cont_state}


def _decision_display_semantics_v63953(row, board=None, window=None, reason=None):
    """Presentation-only market-session semantics.

    The stored DecisionBoardStage remains the research/action-queue state from the
    completed scan. Outside the regular session we never label that snapshot as a
    fresh live entry. This avoids a CLOSED scan saying ENTRY NOW / OPEN while keeping
    the last-session setup available for ranking and audit.
    """
    if board is None or window is None or reason is None:
        board0,window0,reason0,_=_decision_board_state_v63948(row)
        board=board if board is not None else row.get('EffectiveDecisionStage',board0)
        window=window if window is not None else window0
        reason=reason if reason is not None else row.get('EffectiveDecisionReason',reason0)
    board=str(row.get('EffectiveDecisionStage',board) or board)
    reason=str(row.get('EffectiveDecisionReason',reason) or reason)
    phase=str(row.get('MarketPhase','UNKNOWN') or 'UNKNOWN').upper()
    _mkt=str(row.get('Market','') or _market_for_ticker_v612(row.get('Ticker','')))
    try:_md=_market_status_detail_v612(_mkt);_holiday=str(_md.get('reason','') or '')
    except Exception:_holiday=''
    if str(board).upper()=='LAST SESSION ENTRY':
        _window=('MARKET HOLIDAY' if _holiday else 'RECHECK AT OPEN')
        _why=((f'Market holiday: {_holiday} • ' if _holiday else '')+reason)
        return 'LAST SESSION ENTRY',_window,_why
    if phase!='OPEN' and str(board).upper()=='ENTRY NOW':
        _window=('MARKET HOLIDAY' if _holiday else 'RECHECK AT OPEN')
        _why=((f'Market holiday: {_holiday} • ' if _holiday else '')+'Last regular-session entry state; revalidate price, RVOL, flow and momentum at the next regular open')
        return 'LAST SESSION ENTRY',_window,_why
    return str(board),str(window),str(reason)


def _render_decision_why_v63953(row, phase=None):
    """Shared visual Decision / Why Yes / Why Not block for Scanner and Analyze."""
    def _num(v,default=np.nan):
        try:
            x=float(v);return x if np.isfinite(x) else default
        except Exception:return default
    def _esc(v):return _e6395(v if v not in (None,'') else '—')
    phase=str(phase or row.get('MarketPhase','UNKNOWN') or 'UNKNOWN').upper()
    board,window,reason,_=_decision_board_state_v63948(row)
    dboard,dwindow,dreason=_decision_display_semantics_v63953(row,board,window,reason)
    cont=str(row.get('ContinuationEntryState','N/A') or 'N/A').upper()
    cont_display=(cont+' • RECHECK AT OPEN') if phase!='OPEN' and cont=='READY' else cont
    trig=_trigger_timing_label_v63948(row)
    post=_num(row.get('CurrentProgressToT1Pct',row.get('PostTriggerConsumedPct',np.nan)));momentum=str(row.get('MomentumState','NO DATA') or 'NO DATA').upper();m15=str(row.get('MomentumState15m','NO DATA') or 'NO DATA').upper();m1h=str(row.get('MomentumState1H','NO DATA') or 'NO DATA').upper()
    entry=_num(row.get('EntryTimingScore',row.get('LiveActionabilityScore',row.get('EntryScore',np.nan))));gates=int(_num(row.get('EntryConfirmedConditions',0),0) or 0);total=int(_num(row.get('EntryTotalConditions',6),6) or 6)
    flow=_num(row.get('MoneyFlowScore',row.get('NetFlowScore',np.nan)));net=_num(row.get('NetFlowBalance',np.nan));
    if not np.isfinite(flow) and np.isfinite(net):flow=max(0,min(100,50+net/2))
    rvol,_,_=_rvol_display_v63929(row,phase);rr=_num(row.get('LiveRR_T1',np.nan));chase=str(row.get('ChaseRiskLabel','LOW') or 'LOW').upper();chase_score=_num(row.get('ChaseRiskScore',0),0)
    vol=str(row.get('ContinuationVolumeState',row.get('VolumeTrend','NO DATA')) or 'NO DATA').upper();dist=str(row.get('ContinuationDistributionState',row.get('PostSpikeDistributionRisk','NO DATA')) or 'NO DATA').upper()
    acc_score=_num(row.get('PreBreakoutAccumulationScore',np.nan));acc_stage=str(row.get('PreBreakoutAccumulationStage','NO CURRENT ACCUMULATION SETUP') or 'NO CURRENT ACCUMULATION SETUP').upper();acc_shock=_num(row.get('VolumeShockRatio',np.nan));acc_eff=_num(row.get('EffectiveVolumeShockRatio',np.nan));acc_regime=_num(row.get('VolumeRegimeRatio',np.nan));acc_absorb=bool(row.get('AbsorptionCandidate',False));acc_confirmed=bool(row.get('PreMoveConfirmed',False));acc_tier=str(row.get('PreMoveConfidenceTier','NONE') or 'NONE').upper();acc_families=int(_num(row.get('PreMoveFamilyCount',0),0) or 0);acc_sig=str(row.get('PreMoveFamilySignature','NONE') or 'NONE')
    orig_prog=_num(row.get('OriginalProgressToT1Pct',np.nan));orig_sig=_num(row.get('OriginalSignalPrice',np.nan));orig_trig=_num(row.get('OriginalTriggerPrice',np.nan));orig_t1=_num(row.get('OriginalTarget1',np.nan));orig_time=str(row.get('OriginalSignalTime','—') or '—');orig_integrity=str(row.get('OriginalMemoryIntegrity','NO MEMORY') or 'NO MEMORY');pm_action=bool(row.get('PreMoveActionableNow',False));pm_state=str(row.get('PreMoveActionabilityState','NO ACTIONABLE PRE-MOVE') or 'NO ACTIONABLE PRE-MOVE');pm_reason=str(row.get('PreMoveActionabilityReason','') or '')
    hard_timing=bool(row.get('TimingConsumedHardBlock',False));ext_ok=bool(row.get('ExtensionGuardCheck',True));evidence_ok=bool(row.get('EvidenceGuardOK',True));data_ok=bool(row.get('SessionDataFresh',True)) and str(row.get('DataQuality','OK')).upper()=='OK'
    missing=str(row.get('EntryMissingChecks',row.get('ActionabilityMissing','')) or '').strip()

    def item(label,value,tone='yes'):
        return f"<div class='why-row'><span class='wk'>{_esc(label)}</span><span class='wv {tone}'>{_esc(value)}</span></div>"
    yes=[];no=[]
    if pm_action:
        _accv=f'{acc_score:.0f}/100 • {acc_families}/5 families • {pm_state}' if np.isfinite(acc_score) else pm_state
        if np.isfinite(acc_shock):_accv+=f' • shock {acc_shock:.1f}x'
        if acc_absorb:_accv+=' • ABSORPTION'
        yes.append(item('Actionable Pre-Move',_accv,'yes'))
    elif acc_confirmed or 'HIGH-CONFIDENCE PRE-MOVE' in acc_stage:
        _accv=f'{acc_score:.0f}/100 • strong pattern, NOT actionable now • {pm_state}' if np.isfinite(acc_score) else pm_state
        if pm_reason:_accv+=f' • {pm_reason}'
        no.append(item('Strong Pre-Move Pattern',_accv,'warn'))
    elif acc_stage=='PRE-MOVE WATCH':
        _accv=f'{acc_score:.0f}/100 • {acc_families}/5 families • needs another independent confirmation' if np.isfinite(acc_score) else acc_stage
        no.append(item('Pre-Move Watch',_accv,'warn'))
    elif acc_stage=='RAW ACCUMULATION':
        _accv=f'{acc_score:.0f}/100 • raw evidence only; not a confirmed early signal' if np.isfinite(acc_score) else acc_stage
        no.append(item('Raw accumulation',_accv,'warn'))
    elif 'ACCUMULATION PERSISTS' in acc_stage:
        _accv=f'{acc_score:.0f}/100 • evidence persists, but price is no longer early' if np.isfinite(acc_score) else acc_stage
        no.append(item('Accumulation context',_accv,'warn'))
    if np.isfinite(orig_prog):
        _ov=(f'TARGET REACHED • {orig_prog:.1f}% of original Trigger→T1 • {orig_integrity}' if orig_prog>=100 else f'{orig_prog:.1f}% of original Trigger→T1 used • {orig_integrity}')
        if np.isfinite(orig_trig) and np.isfinite(orig_t1):_ov+=f' • {orig_trig:.3f}→{orig_t1:.3f}'
        (yes if orig_prog<40 else no).append(item('Original move progress',_ov,'yes' if orig_prog<40 else ('warn' if orig_prog<75 else 'no')))
    if np.isfinite(orig_sig):yes.append(item('Original signal',f'{orig_time} @ {orig_sig:.3f}','yes'))
    if trig in ('EARLY','MID'):yes.append(item('Current Trigger Timing',trig,'yes'))
    elif trig not in ('NO DATA','—'):no.append(item('Trigger Timing',trig,'no'))
    if np.isfinite(post):
        (yes if post<40 else no).append(item('Current Trigger → T1',f'{post:.1f}%', 'yes' if post<40 else ('warn' if post<70 else 'no')))
    for lab,val in [('Momentum',momentum),('15m',m15),('1H',m1h)]:
        good=val in ('STRENGTHENING','STABLE');target=yes if good else no;target.append(item(lab,val,'yes' if good else ('warn' if val in ('MIXED','SHORT-TERM COOLING','NO DATA') else 'no')))
    if np.isfinite(entry):
        (yes if entry>=65 else no).append(item('Entry',f'{entry:.1f}','yes' if entry>=65 else 'warn'))
    (yes if gates>=max(4,total-1) else no).append(item('Entry conditions',f'{gates}/{total}','yes' if gates>=max(4,total-1) else 'warn'))
    if np.isfinite(flow):
        (yes if flow>=60 else no).append(item('Flow',f'{flow:.1f}','yes' if flow>=60 else ('warn' if flow>=45 else 'no')))
    if np.isfinite(rvol):
        (yes if rvol>=1.5 else no).append(item('RVOL',f'{rvol:.2f}×','yes' if rvol>=1.5 else 'warn'))
    if np.isfinite(rr):
        (yes if rr>=1.5 else no).append(item('R:R T1',f'{rr:.2f}','yes' if rr>=1.5 else 'no'))
    if chase!='LOW' or chase_score>=25:no.append(item('Chase',f'{chase} {chase_score:.0f}','warn' if chase not in ('HIGH','EXTREME') else 'no'))
    if 'FADING' in vol or ('WEAK' in vol):no.append(item('Volume',vol,'warn' if 'BUT STRONG' in vol else 'no'))
    if dist not in ('NO DATA','NONE','LOW','CLEAR','NO CONFIRMED DISTRIBUTION'):
        no.append(item('Distribution',dist,'warn' if ('SOFT' in dist or 'NO CONFIRMED' in dist) else 'no'))
    if hard_timing or not ext_ok or not evidence_ok:
        _parts=[]
        if hard_timing:_parts.append('TIMING')
        if not ext_ok:_parts.append('CHASE / EXTENSION')
        if not evidence_ok:_parts.append('EVIDENCE')
        no.append(item('Hard Block',' + '.join(_parts),'no'))
    else:yes.append(item('Hard Block','NONE','yes'))
    if phase!='OPEN':
        try:_mstat=_market_status_detail_v612(str(row.get('Market','') or _market_for_ticker_v612(row.get('Ticker',''))));_hre=str(_mstat.get('reason','') or '')
        except Exception:_hre=''
        no.append(item('Market session',(f'{phase} • HOLIDAY: {_hre}' if _hre else f'{phase} • RECHECK AT OPEN'),'warn'))
    if not data_ok:no.append(item('Data','STALE / QUALITY BLOCK','no'))
    if missing and missing not in ('None','NONE','—') and dboard not in ('LAST SESSION ENTRY','ENTRY NOW'):
        no.append(item('Still missing',missing,'warn'))
    if not no:no=["<div class='why-empty'>No active blocking/risk reason detected in this snapshot.</div>"]
    if not yes:yes=["<div class='why-empty'>No positive entry confirmations are active yet.</div>"]
    bcls='good' if dboard=='ENTRY NOW' else ('bad' if dboard=='TOO LATE' else 'warn')
    ccls='good' if cont=='READY' else ('warn' if cont=='WATCH' else ('bad' if cont=='BLOCKED' else ''))
    wcls='good' if dwindow=='OPEN' else ('bad' if dwindow=='CLOSED' else 'warn')
    st.markdown(
        "<div class='decision-strip'>"+
        f"<div class='decision-chip'><span class='k'>Decision Board</span><span class='v {bcls}'>{_esc(dboard)}</span></div>"+
        f"<div class='decision-chip'><span class='k'>Continuation</span><span class='v {ccls}'>{_esc(cont_display)}</span></div>"+
        f"<div class='decision-chip'><span class='k'>Opportunity Window</span><span class='v {wcls}'>{_esc(dwindow)}</span></div>"+
        "</div>"+
        "<div class='why-grid'>"+
        "<div class='why-panel yes'><div class='why-title'>✓ WHY YES</div>"+''.join(yes)+"</div>"+
        "<div class='why-panel no'><div class='why-title'>✕ WHY NOT / RISKS</div>"+''.join(no)+"</div>"+
        "</div>"+
        f"<div class='top5-detail-line'><b>Decision reason:</b> {_esc(dreason)}</div>",unsafe_allow_html=True)


def opportunity_fields(row):
    """V6.0 unified long-side decision layer. Volume is direction-aware; exit pressure can veto bullish setups."""
    move=_clip100(row.get('MoveScore',0)); explosive=_clip100(row.get('ExplosiveScore',0)); entry=_clip100(row.get('EntryScore',0)); hourly=_clip100(row.get('HourlyConfirm',50))
    exitp=_clip100(row.get('ExitPressure',0))
    a1=float(row.get('Accel1D',0) or 0); a2=float(row.get('Accel2D',0) or 0)
    accel=_clip100(50 + 2.0*a1 + 1.5*a2)
    conf=_clip100(row.get('CalibrationConfidence',0)); n=max(0,float(row.get('BacktestN',0) or 0)); lift=float(row.get('SignalLift',1) or 1)
    # Thin backtests cannot dominate reliability. Full evidence weight is reached around 20+ signals.
    evidence=min(1.0,math.sqrt(n/20.0)) if n>0 else 0.0
    sample=_clip100(100*np.sqrt(n/60.0))
    lift_score=_clip100(max(0,50+35*(lift-1)))
    reliability=_clip100(.45*conf*evidence + .30*sample + .25*lift_score*evidence)
    raw=_clip100(.19*move+.24*explosive+.19*entry+.12*accel+.10*hourly+.16*reliability)
    score=_clip100(raw*(1.0-0.40*exitp/100.0))
    if exitp>=72: stage='WAIT'
    elif score>=78 and entry>=65 and hourly>=60 and exitp<45 and (a1>=5 or a2>=8): stage='TRIGGER'
    elif score>=68 and entry>=55 and exitp<55: stage='ARMED'
    elif score>=55 and exitp<72: stage='WATCH'
    else: stage='WAIT'
    return round(score,1),round(reliability,1),stage


# Exchange-session display metadata. Keep phase strings stable because they are
# used throughout Scanner/Analyze decision logic.
_MARKET_CLOSURES_V612 = {
    'NASDAQ': {
        '2026-01-01': "New Year's Day", '2026-01-19': 'MLK Day',
        '2026-02-16': "Presidents Day", '2026-04-03': 'Good Friday',
        '2026-05-25': 'Memorial Day', '2026-06-19': 'Juneteenth',
        '2026-07-03': 'Independence Day observed', '2026-09-07': 'Labor Day',
        '2026-11-26': 'Thanksgiving', '2026-12-25': 'Christmas Day',
    },
    'NYSE': {
        '2026-01-01': "New Year's Day", '2026-01-19': 'MLK Day',
        '2026-02-16': "Presidents Day", '2026-04-03': 'Good Friday',
        '2026-05-25': 'Memorial Day', '2026-06-19': 'Juneteenth',
        '2026-07-03': 'Independence Day observed', '2026-09-07': 'Labor Day',
        '2026-11-26': 'Thanksgiving', '2026-12-25': 'Christmas Day',
    },
    'US': {
        '2026-01-01': "New Year's Day", '2026-01-19': 'MLK Day',
        '2026-02-16': "Presidents Day", '2026-04-03': 'Good Friday',
        '2026-05-25': 'Memorial Day', '2026-06-19': 'Juneteenth',
        '2026-07-03': 'Independence Day observed', '2026-09-07': 'Labor Day',
        '2026-11-26': 'Thanksgiving', '2026-12-25': 'Christmas Day',
    },
    'HONG KONG': {
        '2026-01-01': 'New Year holiday', '2026-02-17': 'Lunar New Year',
        '2026-02-18': 'Lunar New Year', '2026-02-19': 'Lunar New Year',
        '2026-04-03': 'Good Friday', '2026-04-06': 'Ching Ming holiday',
        '2026-04-07': 'Easter holiday', '2026-05-01': 'Labour Day',
        '2026-05-25': 'Buddha Birthday holiday', '2026-06-19': 'Tuen Ng Festival',
        '2026-07-01': 'HKSAR Establishment Day', '2026-10-01': 'National Day',
        '2026-10-19': 'Chung Yeung holiday', '2026-12-25': 'Christmas Day',
    },
    # Current known TASE 2026 special closures. Explicit dates avoid guessing
    # Jewish-holiday dates; regular Friday shortening is handled separately below.
    'TEL AVIV': {
        '2026-09-18': 'Yom Kippur schedule',
        '2026-09-21': 'Yom Kippur',
        '2026-09-25': 'Sukkot',
        '2026-10-02': 'Simchat Torah',
    },
}

_MARKET_EARLY_CLOSES_V612 = {
    # U.S. cash equities close at 13:00 ET on these 2026 dates.
    'NASDAQ': {'2026-11-27': time(13,0), '2026-12-24': time(13,0)},
    'NYSE': {'2026-11-27': time(13,0), '2026-12-24': time(13,0)},
    'US': {'2026-11-27': time(13,0), '2026-12-24': time(13,0)},
    # HKEX half-day securities sessions around major holiday eves.
    'HONG KONG': {'2026-02-16': time(12,10), '2026-12-24': time(12,10), '2026-12-31': time(12,10)},
}

def _market_status_detail_v612(market):
    cfg={
        'NASDAQ':('America/New_York',time(4,0),time(9,30),time(16,0),time(20,0)),
        'NYSE':('America/New_York',time(4,0),time(9,30),time(16,0),time(20,0)),
        'US':('America/New_York',time(4,0),time(9,30),time(16,0),time(20,0)),
        'HONG KONG':('Asia/Hong_Kong',time(9,0),time(9,30),time(16,10),None),
        # TASE moved to Monday-Friday in 2026. Friday is a shortened session.
        'TEL AVIV':('Asia/Jerusalem',time(9,25),time(9,59),time(17,30),None),
    }
    if market not in cfg:
        return {'phase':'UNKNOWN','reason':'','local_time':'—','market':market}
    tz,pre,op,cl,after=cfg[market]
    now=datetime.now(ZoneInfo(tz)); t=now.time().replace(tzinfo=None)
    dkey=now.date().isoformat(); reason=_MARKET_CLOSURES_V612.get(market,{}).get(dkey,'')
    early_close=_MARKET_EARLY_CLOSES_V612.get(market,{}).get(dkey)
    if reason:
        phase='CLOSED'
    elif market=='TEL AVIV':
        # Since 2026: Saturday/Sunday closed; Friday closes at 13:50 local time.
        if now.weekday() in (5,6):
            phase='CLOSED'
        else:
            close_today=time(13,50) if now.weekday()==4 else cl
            if pre<=t<op:
                phase='PRE-OPEN'
            elif op<=t<close_today:
                phase='OPEN'
            else:
                phase='CLOSED'
    else:
        if now.weekday()>=5:
            phase='CLOSED'
        else:
            close_today=early_close or cl
            if pre<=t<op:
                phase='PRE-MARKET' if market in ('NASDAQ','NYSE','US') else 'PRE-OPEN'
            elif op<=t<close_today:
                phase='OPEN'
            elif after is not None and close_today<=t<after:
                phase='AFTER-MARKET'
            else:
                phase='CLOSED'
    return {
        'phase':phase,
        'reason':reason,
        'local_time':now.strftime('%H:%M'),
        'local_date':now.strftime('%Y-%m-%d'),
        'market':market,
    }

def _feedback_market_key_v612(market, ticker=''):
    """Normalize stored market labels for feedback calendar/session logic."""
    m=str(market or '').upper().strip()
    if m in ('NASDAQ','NYSE','US','HONG KONG','TEL AVIV'):
        return m
    return _market_for_ticker_v612(ticker)

def _market_timezone_v612(market):
    m=_feedback_market_key_v612(market)
    return {
        'NASDAQ':'America/New_York','NYSE':'America/New_York','US':'America/New_York',
        'HONG KONG':'Asia/Hong_Kong','TEL AVIV':'Asia/Jerusalem',
    }.get(m,'UTC')

def _market_close_for_date_v612(market, d):
    """Regular-session close used only for feedback maturity timing."""
    m=_feedback_market_key_v612(market)
    early=_MARKET_EARLY_CLOSES_V612.get(m,{}).get(d.isoformat())
    if early is not None:return early
    if m=='TEL AVIV':
        return time(13,50) if d.weekday()==4 else time(17,30)
    if m=='HONG KONG':return time(16,10)
    return time(16,0)


def _previous_trading_date_v63915(market, d):
    """Return the most recent scheduled trading date strictly before ``d``."""
    cur=d
    for _ in range(20):
        cur=cur-timedelta(days=1)
        if _is_trading_date_v612(market,cur):
            return cur
    return cur

def _expected_last_completed_session_v63915(market):
    """Expected latest *completed* regular session in the exchange timezone.

    This is used only as a freshness guard. It intentionally separates "market is
    closed now" from "the provider actually supplied the latest completed session".
    """
    m=_feedback_market_key_v612(market)
    tz=ZoneInfo(_market_timezone_v612(m))
    now=datetime.now(tz)
    d=now.date()
    if _is_trading_date_v612(m,d):
        close_t=_market_close_for_date_v612(m,d)
        if now.time().replace(tzinfo=None) >= close_t:
            return d
    return _previous_trading_date_v63915(m,d)

def _expected_required_session_v63930(market):
    """Session date the provider should represent *now*.

    During an OPEN regular session the required date is today, not yesterday's
    last completed session. PRE-MARKET/PRE-OPEN still require the prior completed
    session; AFTER-MARKET requires today. This fixes misleading exports where an
    open NASDAQ scan showed ExpectedSessionDate as the previous trading day.
    """
    m=_feedback_market_key_v612(market)
    tz=ZoneInfo(_market_timezone_v612(m));now=datetime.now(tz);d=now.date()
    detail=_market_status_detail_v612(m);phase=str(detail.get('phase','UNKNOWN')).upper()
    if _is_trading_date_v612(m,d) and phase in ('OPEN','AFTER-MARKET'):
        return d
    return _expected_last_completed_session_v63915(m)

def _frame_latest_session_date_v63915(frame, market):
    """Newest valid Close bar date, normalized to the exchange date when possible."""
    try:
        if frame is None or not isinstance(frame,pd.DataFrame) or frame.empty or 'Close' not in frame.columns:
            return None
        x=frame.dropna(subset=['Close'])
        if x.empty:return None
        ts=pd.Timestamp(x.index[-1])
        if ts.tzinfo is not None:
            ts=ts.tz_convert(ZoneInfo(_market_timezone_v612(_feedback_market_key_v612(market))))
        return ts.date()
    except Exception:
        return None

def _session_freshness_v63915(frame, market):
    """Strict local-exchange session freshness (never Stock Connect calendar)."""
    expected=_expected_required_session_v63930(market)
    latest=_frame_latest_session_date_v63915(frame,market)
    m=_feedback_market_key_v612(market)
    calendar_source=('HKEX LOCAL CASH MARKET (NOT STOCK CONNECT)' if m=='HONG KONG' else f'{m} LOCAL EXCHANGE CALENDAR')
    # Exact date equality is intentional. A provider bar from another session is
    # never allowed to pass just because its timestamp compares greater/lesser.
    ok=bool(latest is not None and expected is not None and latest==expected)
    if latest is None:
        status='NO DAILY SESSION DATE'
    elif expected is None:
        status=f'UNRESOLVED SESSION • data {latest}'
    elif ok:
        status=f'CURRENT THROUGH {latest}'
    else:
        status=f'STALE SESSION • expected {expected} • data {latest}'
    return {'ok':ok,'latest':latest,'expected':expected,'status':status,'calendar_source':calendar_source,'calendar_reason':'LOCAL CASH-MARKET HOLIDAYS ONLY'}

def _hk_intraday_reconstruction_source_v63931(ticker):
    """Best-effort Hong Kong completed-session bars using multiple Yahoo routes.

    Daily HK bars can lag after the exchange closes even while intraday history is
    already complete. Keep this strictly as a freshness fallback: it reconstructs
    only the just-completed regular session and never creates live/entry signals by
    itself. The lighter 1H route is tried first; 15m is used when needed.
    """
    t=str(ticker or '').upper().strip()
    provider=t
    try:
        fn=getattr(qe,'_market_data_symbol',None)
        if callable(fn): provider=str(fn(t) or t).upper()
    except Exception:
        provider=t
    attempts=[]
    # Existing download path first. 1H is much lighter for a 100-name HK scan.
    attempts.extend([
        ('YAHOO DOWNLOAD 1H',60,lambda: fetch_ohlcv(t,'10d','1h')),
        ('YAHOO DOWNLOAD 15M',15,lambda: fetch_ohlcv(t,'10d','15m')),
    ])
    # Alternate yfinance Ticker.history endpoint. This often refreshes independently
    # from yf.download when the Daily endpoint is one session behind.
    attempts.extend([
        ('YAHOO TICKER.HISTORY 1H',60,lambda: yf.Ticker(provider).history(period='10d',interval='1h',auto_adjust=True,actions=False)),
        ('YAHOO TICKER.HISTORY 15M',15,lambda: yf.Ticker(provider).history(period='10d',interval='15m',auto_adjust=True,actions=False)),
    ])
    for source,bar_minutes,getter in attempts:
        try:
            q=getter()
            canon=getattr(qe,'_canonical_ohlcv',None)
            if callable(canon): q=canon(q,ticker=provider)
            q=confirmed_intraday_bars(q)
            if q is not None and isinstance(q,pd.DataFrame) and not q.empty:
                return q,source,bar_minutes
        except Exception:
            continue
    return None,'NO HK INTRADAY FALLBACK',None


def _reconstruct_completed_daily_from_intraday_v63924(ticker, daily, market, intraday=None):
    """Repair a one-session stale Daily series from confirmed intraday bars.

    This is deliberately conservative and is used only for provider lag on
    TEL AVIV / HONG KONG. Reconstruction is allowed only for the exchange's
    *completed* expected session and only when confirmed intraday bars cover the
    regular-session close. The synthetic row is temporary analysis data; it never
    alters provider history.
    """
    meta={'used':False,'source':'PROVIDER DAILY','status':'NO RECONSTRUCTION','bars':0,'session_date':None,'last_bar':None}
    try:
        m=_feedback_market_key_v612(market,ticker)
        expected=_expected_last_completed_session_v63915(m)
        latest=_frame_latest_session_date_v63915(daily,m)
        completed_ok=bool(latest is not None and expected is not None and latest>=expected)
        if completed_ok or m not in ('TEL AVIV','HONG KONG') or expected is None:
            return daily,meta
        # Only repair the immediately expected completed session. Larger gaps stay blocked.
        if latest is None or _previous_trading_date_v63915(m,expected)!=latest:
            meta['status']='STALE GAP > 1 SESSION — NOT RECONSTRUCTED';return daily,meta
        q=intraday
        source='CALLER INTRADAY' if q is not None else None
        bar_minutes=15
        if q is None and m=='HONG KONG':
            q,source,bar_minutes=_hk_intraday_reconstruction_source_v63931(ticker)
        elif q is None:
            q=confirmed_intraday_bars(fetch_ohlcv(str(ticker),'10d','15m'));source='YAHOO DOWNLOAD 15M';bar_minutes=15
        else:
            q=confirmed_intraday_bars(q)
            # Infer caller-supplied bar duration when possible (e.g. a cached 1H frame).
            try:
                _di=pd.Series(pd.DatetimeIndex(q.index)).diff().dropna().dt.total_seconds().div(60)
                if len(_di):bar_minutes=int(np.clip(float(_di.median()),1,120))
            except Exception:
                pass
        if q is None or not isinstance(q,pd.DataFrame) or q.empty:
            meta['status']='NO CONFIRMED INTRADAY BARS';return daily,meta
        z=q.copy();idx=pd.DatetimeIndex(z.index)
        tz=ZoneInfo(_market_timezone_v612(m))
        if idx.tz is not None:
            local_idx=idx.tz_convert(tz)
        else:
            local_idx=idx.tz_localize(tz)
        mask=[x.date()==expected for x in local_idx]
        day=z.loc[mask].copy()
        if day.empty:
            meta['status']=f'NO INTRADAY BARS FOR {expected}';return daily,meta
        day_idx=pd.DatetimeIndex(day.index)
        if day_idx.tz is not None:day_local=day_idx.tz_convert(tz)
        else:day_local=day_idx.tz_localize(tz)
        last_local=day_local[-1]
        close_dt=datetime.combine(expected,_market_close_for_date_v612(m,expected),tzinfo=tz)
        # _market_close_for_date_v612 intentionally includes a 10-minute HK
        # completion buffer for feedback maturity. Reconstruction needs the actual
        # cash-session close, so remove that buffer here (16:00 full day / 12:00 half day).
        if m=='HONG KONG':close_dt=close_dt-timedelta(minutes=10)
        # Judge coverage by the END of the final confirmed bar, not only its start.
        # This allows a confirmed 15:00-16:00 1H HK bar to prove the 16:00 close.
        try:_bm=max(1,int(bar_minutes or 15))
        except Exception:_bm=15
        covered_until=last_local.to_pydatetime()+timedelta(minutes=_bm)
        if covered_until < close_dt-timedelta(minutes=5):
            meta['status']=f'INTRADAY INCOMPLETE • last {last_local.strftime("%H:%M")} • {_bm}m';return daily,meta
        need=['Open','High','Low','Close']
        if any(c not in day.columns for c in need):
            meta['status']='INTRADAY OHLC MISSING';return daily,meta
        vals={c:pd.to_numeric(day[c],errors='coerce') for c in need}
        if any(v.dropna().empty for v in vals.values()):
            meta['status']='INTRADAY OHLC INVALID';return daily,meta
        row={
            'Open':float(vals['Open'].dropna().iloc[0]),
            'High':float(vals['High'].max()),
            'Low':float(vals['Low'].min()),
            'Close':float(vals['Close'].dropna().iloc[-1]),
        }
        if 'Volume' in day.columns:
            vv=pd.to_numeric(day['Volume'],errors='coerce').fillna(0);row['Volume']=float(vv.sum())
        out=daily.copy()
        # Preserve additional Daily columns as NaN on the synthetic row; feature
        # engineering recalculates indicators from OHLCV afterwards.
        r={c:np.nan for c in out.columns};r.update({k:v for k,v in row.items() if k in out.columns or k=='Volume'})
        if 'Volume' not in out.columns and 'Volume' in row:out['Volume']=np.nan
        # Match the existing Daily index convention.
        if isinstance(out.index,pd.DatetimeIndex) and out.index.tz is not None:
            ridx=pd.Timestamp(datetime.combine(expected,time(0,0),tzinfo=tz)).tz_convert(out.index.tz)
        else:
            ridx=pd.Timestamp(expected)
        out.loc[ridx]=r
        out=out.sort_index()
        meta.update({'used':True,'source':str(source or 'CONFIRMED INTRADAY'),'status':f'SESSION RECONSTRUCTED FROM INTRADAY • {expected} • {source or "CONFIRMED"}','bars':int(len(day)),'session_date':str(expected),'last_bar':last_local.isoformat()})
        return out,meta
    except Exception as e:
        meta['status']=f'RECONSTRUCTION ERROR • {type(e).__name__}: {str(e)[:120]}'
        return daily,meta


def _is_trading_date_v612(market, d):
    """Calendar estimate for UI scheduling only. Actual outcome maturity is bar-count based."""
    m=_feedback_market_key_v612(market)
    if d.weekday()>=5:return False
    return d.isoformat() not in _MARKET_CLOSURES_V612.get(m,{})

def _nth_future_trading_date_v612(market, after_date, n):
    n=max(1,int(n)); cur=after_date; seen=0
    for _ in range(40):
        cur=cur+timedelta(days=1)
        if _is_trading_date_v612(market,cur):
            seen+=1
            if seen>=n:return cur
    return cur

def _snapshot_market_date_v612(ts_utc, market, ticker=''):
    """Convert the UTC snapshot timestamp to the exchange's local trade date."""
    try:
        z=pd.to_datetime(ts_utc,utc=True)
        return z.tz_convert(ZoneInfo(_market_timezone_v612(_feedback_market_key_v612(market,ticker)))).date()
    except Exception:
        try:return pd.Timestamp(ts_utc).date()
        except Exception:return datetime.utcnow().date()

def _feedback_due_at_v612(ts_utc, market, horizon, ticker=''):
    """Approximate UTC time when H future regular sessions should be complete.
    Actual evaluation still requires H provider daily bars, so holidays/provider gaps cannot
    cause an outcome to mature early.
    """
    m=_feedback_market_key_v612(market,ticker); tz=ZoneInfo(_market_timezone_v612(m))
    start=_snapshot_market_date_v612(ts_utc,m,ticker)
    d=_nth_future_trading_date_v612(m,start,int(horizon))
    close_t=_market_close_for_date_v612(m,d)
    local_dt=datetime.combine(d,close_t).replace(tzinfo=tz)+timedelta(minutes=30)
    return pd.Timestamp(local_dt.astimezone(timezone.utc))

def _completed_future_daily_bars_v612(frame, scan_date, market, horizon=None):
    """Return completed provider daily bars strictly after the snapshot's LOCAL market date.
    This is the source of truth for 1D/2D/3D/5D maturity: weekends/holidays never count.
    Current still-open sessions are excluded even if the provider exposes a partial daily bar.
    """
    if frame is None or frame.empty:return frame
    z=frame.copy(); idx_dates=np.array(pd.to_datetime(z.index).date)
    z=z.loc[idx_dates>scan_date]
    if z.empty:return z
    m=_feedback_market_key_v612(market); now_utc=datetime.now(timezone.utc); keep=[]
    for idx in z.index:
        d=pd.Timestamp(idx).date()
        if not _is_trading_date_v612(m,d):
            keep.append(False);continue
        tz=ZoneInfo(_market_timezone_v612(m)); close_t=_market_close_for_date_v612(m,d)
        complete_at=datetime.combine(d,close_t).replace(tzinfo=tz)+timedelta(minutes=20)
        keep.append(now_utc>=complete_at.astimezone(timezone.utc))
    z=z.loc[np.array(keep,dtype=bool)]
    return z.head(int(horizon)) if horizon is not None else z

def _market_phase(market):
    return _market_status_detail_v612(market).get('phase','UNKNOWN')

def _market_phase_icon_v612(phase):
    return {
        'OPEN':'🟢','PRE-MARKET':'🟡','PRE-OPEN':'🟡','AFTER-MARKET':'🟠',
        'CLOSED':'⚫','UNKNOWN':'⚪'
    }.get(str(phase),'⚪')

def _render_market_status_badges_v612():
    markets=[('US','NASDAQ'),('Hong Kong','HONG KONG'),('Tel Aviv','TEL AVIV')]
    cols=st.columns(3)
    for col,(label,key) in zip(cols,markets):
        d=_market_status_detail_v612(key); phase=d.get('phase','UNKNOWN'); icon=_market_phase_icon_v612(phase)
        reason=f"<div style='font-size:.72rem;color:#ffcf66;margin-top:3px'>{d.get('reason')}</div>" if d.get('reason') else ''
        col.markdown(
            f"<div style='border:1px solid #2a3851;border-radius:14px;padding:10px 12px;background:#111722'>"
            f"<div style='font-size:.78rem;color:#8f9bad'>{label}</div>"
            f"<div style='font-weight:850;font-size:1.02rem'>{icon} {phase}</div>"
            f"<div style='font-size:.72rem;color:#8f9bad'>Local {d.get('local_time','—')}</div>{reason}</div>",
            unsafe_allow_html=True,
        )



_MARKET_REGIME_CACHE_V610={}
def _market_regime_v610(ticker):
    """Lightweight broad-market gate, cached per benchmark for the process."""
    t=str(ticker).upper()
    bench='^HSI' if t.endswith('.HK') else ('^TA125.TA' if t.endswith('.TA') else 'SPY')
    if not bench:return 'NEUTRAL'
    cached=_MARKET_REGIME_CACHE_V610.get(bench)
    if cached and time_module.time()-cached[0] < 1800:return cached[1]
    regime='NEUTRAL'
    try:
        d=fetch_ohlcv(bench,'6mo','1d')
        if d is not None and len(d)>=55:
            f=compute_features(d);r=f.dropna(subset=['Close']).iloc[-1]
            c=float(r.get('Close',np.nan));e20=float(r.get('ema20',np.nan));e50=float(r.get('ema50',np.nan));m5=float(r.get('mom5',np.nan))
            if np.isfinite(c) and np.isfinite(e20) and np.isfinite(e50):
                if c<e20 and e20<e50 and np.isfinite(m5) and m5<-0.02:regime='RISK-OFF'
                elif c>=e20 and e20>=e50:regime='SUPPORTIVE'
    except Exception:pass
    _MARKET_REGIME_CACHE_V610[bench]=(time_module.time(),regime)
    return regime


def _trade_stage_label(stage):
    stg=str(stage)
    return 'CONFIRMED ENTRY' if stg in ('TRIGGER','TRADE TRIGGER','LIVE TRIGGERED') else stg


def _movement_stage_label(stage):
    return 'MOVEMENT TRIGGER' if str(stage)=='TRIGGER' else str(stage)


def _why_not_trade_trigger(r):
    """Mirror the actual Entry engine instead of maintaining a second threshold system."""
    stg=str(r.get('EntryTriggerState',r.get('TradeStage','')) or '')
    if stg=='EXTENDED — DO NOT CHASE':return 'Chase/Extension Guard blocked entry — wait for retest'
    if stg=='TOO LATE / CHASE':return 'No-Chase gate failed — price already extended'
    if stg=='RETEST ONLY / LATE':return 'Timing gate blocked entry — 80%+ of the observed move occurred before the causal trigger'
    if stg=='INVALIDATED':return 'Trade plan invalidated / exit-risk gate'
    ev=str(r.get('EvidenceConfirmationGate','OK') or 'OK')
    if ev!='OK':return ev
    missing=str(r.get('EntryMissingChecks','') or '').strip()
    if missing and missing.lower()!='none':return missing
    action_missing=str(r.get('ActionabilityMissing','') or '').strip()
    if bool(r.get('SetupConfirmed',False)) and not bool(r.get('ConfirmedEntryGateOK',False)):
        return action_missing if action_missing and action_missing.lower()!='none' else 'Setup confirmed, but the current price is not actionable'
    if not bool(r.get('PlanValid',True)):return 'Trade-plan data check'
    if str(r.get('DataQuality','OK'))!='OK':return 'Cross-timeframe data mismatch'
    return 'All actual trade-trigger gates aligned' if stg=='CONFIRMED ENTRY' else 'Waiting for the remaining Entry-engine confirmation'


def _armed_timing_class_v639(r):
    """Research-only timing bucket for forward Feedback validation.

    It never promotes a trade.  It only tags ARMED snapshots as early/mid/late
    using information already available at the snapshot time.
    """
    stage=str(r.get('TradeStage','') or '')
    if stage=='CONFIRMED ENTRY':return 'CONFIRMED ENTRY','All production entry gates passed'
    if stage!='ARMED':return 'N/A','Not an ARMED snapshot'
    def n(k):
        try:
            v=float(r.get(k,np.nan));return v if np.isfinite(v) else np.nan
        except Exception:return np.nan
    chase=n('ChaseRiskScore');prog=n('Target1ProgressPct');cons=n('MoveConsumedBeforeTriggerPct');rr1=n('LiveRR_T1');dist=n('EntryDistancePct');sess=n('SessionMovePct')
    ret=str(r.get('RetestStatus','') or '')
    reasons=[]
    late=False
    if np.isfinite(chase) and chase>=35:late=True;reasons.append(f'Chase {chase:.0f}')
    if np.isfinite(prog) and prog>=60:late=True;reasons.append(f'T1 path {prog:.0f}% used')
    if np.isfinite(cons) and cons>=70:late=True;reasons.append(f'{cons:.0f}% move consumed before trigger')
    if np.isfinite(rr1) and rr1<1.0:late=True;reasons.append(f'R:R T1 {rr1:.2f}x')
    if np.isfinite(dist) and dist>1.0:late=True;reasons.append(f'{dist:.1f}% above entry zone')
    if ret=='WAIT FOR PULLBACK':late=True;reasons.append('wait for pullback')
    if late:return 'LATE ARMED',' • '.join(reasons[:4])
    early=True
    if np.isfinite(chase) and chase>=25:early=False
    if np.isfinite(prog) and prog>45:early=False
    if np.isfinite(cons) and cons>50:early=False
    if np.isfinite(rr1) and rr1<1.20:early=False
    if np.isfinite(dist) and dist>0.75:early=False
    if np.isfinite(sess) and sess>7.0:early=False
    if early:
        e=[]
        if np.isfinite(cons):e.append(f'{cons:.0f}% move consumed')
        if np.isfinite(rr1):e.append(f'R:R T1 {rr1:.2f}x')
        if np.isfinite(chase):e.append(f'Chase {chase:.0f}')
        return 'EARLY ARMED',' • '.join(e) if e else 'Constructive ARMED state before material extension'
    return 'MID ARMED','ARMED is not clearly early, but no late-entry veto is present'


def _evidence_profile_v63916(row):
    """V6.3.9.30 evidence profile: warning != veto.

    Low sample, unavailable lift, or low Reliability are confidence warnings; they
    do not by themselves cancel a technically confirmed live entry. A hard evidence
    veto is reserved for a sufficiently populated OOS sample that is actually below
    baseline (12+ signals with lift < 0.90x). Trade-grade validation remains stricter
    and is tracked separately from the live guard.
    """
    try: n=max(0,int(float(row.get('BacktestN',0) or 0)))
    except Exception: n=0
    try: lift=float(row.get('SignalLift',np.nan))
    except Exception: lift=np.nan
    try: rel=float(row.get('Reliability',0) or 0)
    except Exception: rel=0.0

    guard_ok=True
    trade_grade=False
    # V6.3.9.44 evidence maturity ladder: evidence becomes visible/useful from N=6,
    # while full trade-grade validation still requires N>=12. This avoids hiding a
    # useful early read without pretending a six-event sample is fully validated.
    if n < 6:
        state='UNPROVEN — LOW SAMPLE'; reason=f'Only {n} historical OOS signal(s); need 6+ for provisional Evidence and 12+ for validation'
    elif n < 8:
        state='PROVISIONAL EVIDENCE'; reason=f'{n} historical OOS signals; early Evidence is visible, but 12+ are still required for validation'
    elif n < 12:
        state='BUILDING EVIDENCE'; reason=f'{n} historical OOS signals; Evidence is building, but remains unvalidated until 12+ signals'
    elif not np.isfinite(lift):
        state='UNPROVEN — NO LIFT'; reason='OOS lift unavailable; warning only, not negative evidence'
    elif lift < 0.75:
        state='NEGATIVE OOS — HARD GUARD'; guard_ok=False; reason=f'{n} OOS signals with lift {lift:.2f}x materially below baseline'
    elif lift < 0.90:
        state='NEGATIVE OOS — GUARD'; guard_ok=False; reason=f'{n} OOS signals with lift {lift:.2f}x below the 0.90x hard-guard floor'
    elif rel < 30.0:
        state='LOW RELIABILITY — WARNING'; reason=f'Reliability {rel:.1f}/100 is low; no hard veto because OOS lift is not negative'
    elif n >= 20 and lift >= 1.20 and rel >= 50.0:
        state='STRONG'; trade_grade=True; reason=f'{n} OOS signals • lift {lift:.2f}x • reliability {rel:.1f}'
    elif lift >= 1.05 and rel >= 35.0:
        state='SUPPORTIVE'; trade_grade=True; reason=f'{n} OOS signals • lift {lift:.2f}x • reliability {rel:.1f}'
    else:
        state='MIXED / QUALIFIED'; trade_grade=True; reason=f'{n} OOS signals • lift {lift:.2f}x • reliability {rel:.1f}'

    return {
        'EvidenceState':state,
        'EvidenceGuardOK':bool(guard_ok),
        'EvidenceTradeGrade':bool(trade_grade),
        'EvidenceQualificationReason':reason,
        'EvidenceSampleN':int(n),
        'EvidenceLiftX':round(lift,3) if np.isfinite(lift) else np.nan,
    }

def _evidence_gate_v63916(row):
    p=_evidence_profile_v63916(row)
    return p['EvidenceState'],p['EvidenceGuardOK']


def add_market_and_opportunity(df):
    z=df.copy()
    z['Market']=z['Ticker'].map(lambda x:_market_for_ticker_v612(x))
    z['Sector']=z['Ticker'].map(SECTOR_MAP).fillna('Discovery / Other')
    if 'ExitPressure' not in z:z['ExitPressure']=0.0
    if 'ExitStage' not in z:z['ExitStage']='CLEAR'
    vals=z.apply(opportunity_fields,axis=1,result_type='expand'); vals.columns=['OpportunityScore','Reliability','OpportunityStage']
    z=pd.concat([z,vals],axis=1)
    def _evidence_quality(r):
        n=float(r.get('BacktestN',0) or 0); rel=float(r.get('Reliability',0) or 0); conf=float(r.get('CalibrationConfidence',0) or 0)
        if n>=30 and rel>=65 and conf>=55:return 'STRONG'
        if n>=12:return 'MEDIUM' if rel>=45 else 'LOW'
        if n>=8:return 'BUILDING'
        if n>=6:return 'PROVISIONAL'
        return 'LOW'
    z['EvidenceQuality']=z.apply(_evidence_quality,axis=1)
    _ep=z.apply(lambda r: pd.Series(_evidence_profile_v63916(r)),axis=1)
    for _c in _ep.columns:z[_c]=_ep[_c].values
    if 'EntryTriggerState' in z.columns:
        z['RawEntryTriggerState']=z['EntryTriggerState'].fillna('WAIT').astype(str)
        z['TradeStage']=z['RawEntryTriggerState'].copy()
    else:
        z['RawEntryTriggerState']=z['OpportunityStage'].map(_trade_stage_label)
        z['TradeStage']=z['RawEntryTriggerState'].copy()

    # V6.3.9.30 evidence guard: only sufficiently sampled negative OOS evidence
    # blocks CONFIRMED ENTRY. Low sample/no-lift/low-reliability remain warnings.
    _evguard=z['EvidenceGuardOK'].fillna(False).astype(bool)
    z['EvidenceConfirmationGate']='OK'
    _evblock=z['TradeStage'].eq('CONFIRMED ENTRY') & (~_evguard)
    if _evblock.any():
        z.loc[_evblock,'EvidenceConfirmationGate']=z.loc[_evblock].apply(
            lambda r:f"{r.get('EvidenceState','UNPROVEN')} — CONFIRMATION BLOCKED",axis=1)
    z.loc[_evblock,'TradeStage']='ARMED'
    if 'EntryTriggerState' in z.columns:z.loc[_evblock,'EntryTriggerState']='ARMED'

    def _entry_action_state(r):
        raw=str(r.get('RawEntryTriggerState',r.get('TradeStage','WAIT')) or 'WAIT')
        gate=str(r.get('EvidenceConfirmationGate','OK') or 'OK')
        if raw=='CONFIRMED ENTRY' and gate!='OK':return 'SETUP CONFIRMED — EVIDENCE BLOCK'
        if bool(r.get('SetupConfirmed',False)) and not bool(r.get('ConfirmedEntryGateOK',False)):return 'SETUP CONFIRMED — WAIT FOR ENTRY'
        return str(r.get('TradeStage','WAIT'))
    z['EntryActionabilityState']=z.apply(_entry_action_state,axis=1)
    _armed=z.apply(_armed_timing_class_v639,axis=1,result_type='expand');_armed.columns=['ArmedTimingClass','ArmedTimingReason'];z[['ArmedTimingClass','ArmedTimingReason']]=_armed
    z['MovementStage']=z.get('TimingStage',pd.Series(['—']*len(z),index=z.index)).map(_movement_stage_label)
    z['WhyNotTradeTrigger']=z.apply(_why_not_trade_trigger,axis=1)
    z['MarketPhase']=z['Market'].map(_market_phase)
    z['PreviousSessionTrigger']=z['TradeStage'].eq('CONFIRMED ENTRY')

    z['PMPrice']=np.nan; z['PMChangePct']=np.nan; z['PMVolume']=np.nan; z['PMVolumeStrength']=np.nan; z['PMData']='N/A'; z['PMConfirmation']='N/A'
    nas_pm=z[(z['Market'].isin(['NASDAQ','NYSE','US'])) & (z['MarketPhase'].eq('PRE-MARKET'))]['Ticker'].tolist()
    pm=fetch_premarket_snapshots(nas_pm) if nas_pm else {}
    for i,r in z.iterrows():
        snap=pm.get(str(r['Ticker']).upper())
        if snap:
            for k in ['PMPrice','PMChangePct','PMVolume','PMVolumeStrength','PMData']: z.at[i,k]=snap.get(k,np.nan if k!='PMData' else 'N/A')
            ch=float(snap.get('PMChangePct',np.nan)); vr=float(snap.get('PMVolumeStrength',np.nan))
            if np.isfinite(ch):
                if ch>=0.6 and np.isfinite(vr) and vr>=0.8: c='CONFIRMED'
                elif ch>=0.6 and not np.isfinite(vr): c='PRICE CONFIRMED • VOLUME UNAVAILABLE'
                elif ch<=-1.5 and np.isfinite(vr) and vr>=1.0: c='STRONGLY WEAKENED'
                elif ch<=-0.5: c='WEAKENED'
                else: c='NEUTRAL'
                z.at[i,'PMConfirmation']=c

    z['AHPrice']=np.nan; z['RegularClose']=np.nan; z['AHChangePct']=np.nan; z['AHVolume']=np.nan; z['AHVolumeStrength']=np.nan; z['AHData']='N/A'; z['AHLastTime']='—'; z['AHAgeMinutes']=np.nan; z['AHFresh']=False; z['AHConfirmation']='N/A'
    nas_ah=z[(z['Market'].isin(['NASDAQ','NYSE','US'])) & (z['MarketPhase'].eq('AFTER-MARKET'))]['Ticker'].tolist()
    ah=fetch_aftermarket_snapshots(nas_ah) if nas_ah else {}
    for i,r in z.iterrows():
        snap=ah.get(str(r['Ticker']).upper())
        if snap:
            for k in ['AHPrice','RegularClose','AHChangePct','AHVolume','AHVolumeStrength','AHAgeMinutes']: z.at[i,k]=snap.get(k,np.nan)
            z.at[i,'AHData']=snap.get('AHData','N/A'); z.at[i,'AHLastTime']=snap.get('AHLastTime','—'); z.at[i,'AHFresh']=bool(snap.get('AHFresh',False))
            ch=float(snap.get('AHChangePct',np.nan)); vr=float(snap.get('AHVolumeStrength',np.nan))
            if np.isfinite(ch):
                if ch>=0.6 and np.isfinite(vr) and vr>=0.8: c='CONFIRMED'
                elif ch>=0.6 and not np.isfinite(vr): c='PRICE CONFIRMED • VOLUME UNAVAILABLE'
                elif ch<=-1.5 and np.isfinite(vr) and vr>=1.0: c='STRONGLY WEAKENED'
                elif ch<=-0.5: c='WEAKENED'
                else: c='NEUTRAL'
                z.at[i,'AHConfirmation']=c

    z['LiveStage']=z['TradeStage']
    _live_price_ok=z['LivePriceFresh'].fillna(True).astype(bool) if 'LivePriceFresh' in z else pd.Series(True,index=z.index)
    _live_data_ok=z['DataQuality'].eq('OK') if 'DataQuality' in z else pd.Series(True,index=z.index)
    _live_plan_ok=z['PlanValid'].astype(bool) if 'PlanValid' in z else pd.Series(True,index=z.index)
    live_ok=z['TradeStage'].eq('CONFIRMED ENTRY') & z['MarketPhase'].eq('OPEN') & (pd.to_numeric(z['ExitPressure'],errors='coerce').fillna(0)<55) & _live_price_ok & _live_data_ok & _live_plan_ok
    z.loc[live_ok,'LiveStage']='CONFIRMED ENTRY — LIVE'
    z.loc[z['PreviousSessionTrigger'] & z['MarketPhase'].eq('OPEN') & (~_live_price_ok),'LiveStage']='LIVE DATA STALE'
    z.loc[z['PreviousSessionTrigger'] & z['MarketPhase'].eq('OPEN') & (~_live_data_ok),'LiveStage']='DATA CHECK — TRIGGER BLOCKED'
    pm_trigger=z['PreviousSessionTrigger'] & z['MarketPhase'].eq('PRE-MARKET')
    z.loc[pm_trigger,'LiveStage']='PRE-MARKET SETUP'; z.loc[pm_trigger & z['PMConfirmation'].eq('CONFIRMED'),'LiveStage']='PRE-MARKET CONFIRMED'; z.loc[pm_trigger & z['PMConfirmation'].isin(['WEAKENED','STRONGLY WEAKENED']),'LiveStage']='PRE-MARKET WEAKENED'
    ah_trigger=z['PreviousSessionTrigger'] & z['MarketPhase'].eq('AFTER-MARKET')
    z.loc[ah_trigger,'LiveStage']='AFTER-MARKET SETUP'; z.loc[ah_trigger & z['AHConfirmation'].eq('CONFIRMED'),'LiveStage']='AFTER-MARKET CONFIRMED'; z.loc[ah_trigger & z['AHConfirmation'].isin(['WEAKENED','STRONGLY WEAKENED']),'LiveStage']='AFTER-MARKET WEAKENED'
    z.loc[z['PreviousSessionTrigger'] & z['MarketPhase'].eq('CLOSED'),'LiveStage']='PREVIOUS SESSION CONFIRMED ENTRY'
    # Keep the underlying regular-session stage visible, but expose a separate session-aware state.
    if 'RegularSessionEntryState' not in z.columns:z['RegularSessionEntryState']=z['TradeStage']
    else:z['RegularSessionEntryState']=z['RegularSessionEntryState'].fillna(z['TradeStage'])
    if 'SessionEntryState' not in z.columns:z['SessionEntryState']=z['TradeStage']
    else:z['SessionEntryState']=z['SessionEntryState'].fillna(z['TradeStage'])
    _ahmask=z['MarketPhase'].eq('AFTER-MARKET')
    z.loc[_ahmask & z['TradeStage'].eq('CONFIRMED ENTRY'),'SessionEntryState']='AFTER-MARKET SETUP — RECONFIRM NEXT SESSION'
    z.loc[_ahmask & z['TradeStage'].eq('EXTENDED — DO NOT CHASE'),'SessionEntryState']='EXTENDED — DO NOT CHASE'
    z.loc[_ahmask & (~z['TradeStage'].isin(['CONFIRMED ENTRY','EXTENDED — DO NOT CHASE'])),'SessionEntryState']='AFTER-MARKET REVIEW — '+z.loc[_ahmask & (~z['TradeStage'].isin(['CONFIRMED ENTRY','EXTENDED — DO NOT CHASE'])),'TradeStage'].astype(str)
    _tot=pd.to_numeric(z.get('SessionMovePct',np.nan),errors='coerce'); _ahm=pd.to_numeric(z.get('AHChangePct',np.nan),errors='coerce')
    if 'TotalMoveIncludingAHPct' not in z.columns:z['TotalMoveIncludingAHPct']=np.where(_ahmask,_tot,np.nan)
    if 'AfterHoursMovePct' not in z.columns:z['AfterHoursMovePct']=np.where(_ahmask,_ahm,np.nan)
    if 'AfterHoursPrice' not in z.columns:z['AfterHoursPrice']=np.where(_ahmask,pd.to_numeric(z.get('AHPrice',np.nan),errors='coerce'),np.nan)
    if 'AfterHoursVolumeStrength' not in z.columns:z['AfterHoursVolumeStrength']=np.where(_ahmask,pd.to_numeric(z.get('AHVolumeStrength',np.nan),errors='coerce'),np.nan)
    if 'RegularSessionMovePct' not in z.columns:
        _den=1.0+_ahm/100.0
        z['RegularSessionMovePct']=np.where(_ahmask & _tot.notna() & _ahm.notna() & (_den>0),100.0*((1.0+_tot/100.0)/_den-1.0),np.where(~_ahmask,_tot,np.nan))

    def session_status(r):
        phase=str(r.get('MarketPhase','UNKNOWN')); stage=str(r.get('TradeStage','WAIT')); live=str(r.get('LiveStage',stage))
        if phase=='CLOSED': return f'CLOSED • PREVIOUS SESSION: {stage}'
        if phase=='PRE-OPEN': return f'PRE-OPEN • PREVIOUS SESSION: {stage}'
        if phase=='PRE-MARKET':
            pmc=str(r.get('PMConfirmation','N/A')); ch=r.get('PMChangePct',np.nan); move=f' ({float(ch):+.2f}%)' if pd.notna(ch) else ''; label='DATA UNAVAILABLE' if pmc=='N/A' else pmc
            return f'PRE-MARKET: {label}{move} • PREVIOUS SESSION: {stage}'
        if phase=='AFTER-MARKET':
            ahc=str(r.get('AHConfirmation','N/A')); ch=r.get('AHChangePct',np.nan); move=f' ({float(ch):+.2f}%)' if pd.notna(ch) else ''; label='DATA UNAVAILABLE' if ahc=='N/A' else ahc
            return f'AFTER-MARKET: {label}{move} • REGULAR SESSION: {stage}'
        if phase=='OPEN': return f'OPEN • {live}'
        return f'{phase} • {stage}'
    z['SessionStatus']=z.apply(session_status,axis=1)

    def decision(r):
        stg=str(r.get('TradeStage','WAIT')); pred=float(r.get('Prediction',0) or 0); xp=float(r.get('ExitPressure',0) or 0)
        if xp>=72:return 'EXIT TRIGGER'
        if xp>=55:return 'EXIT ARMED'
        if stg=='CONFIRMED ENTRY':return 'CONFIRMED ENTRY'
        if stg=='EXTENDED — DO NOT CHASE':return 'EXTENDED — DO NOT CHASE'
        if stg=='TOO LATE / CHASE':return 'TOO LATE / CHASE'
        if stg=='RETEST ONLY / LATE':return 'RETEST ONLY / LATE'
        if stg=='INVALIDATED':return 'INVALIDATED'
        if stg=='ARMED':return 'ARMED'
        if stg=='WATCH' or pred>=58:return 'WATCH'
        return 'WAIT'
    z['Signal']=z.apply(decision,axis=1)

    def top_score(r):
        # Entry is already inside Opportunity; no direct duplicate Entry weight here.
        base=_clip100(.66*float(r.get('OpportunityScore',0) or 0)+.20*_clip100(r.get('Prediction',0))+.14*_clip100(r.get('Reliability',0)))
        pmc=str(r.get('PMConfirmation','N/A')); ahc=str(r.get('AHConfirmation','N/A')); scale={'CONFIRMED':3.0,'NEUTRAL':0.0,'WEAKENED':-5.0,'STRONGLY WEAKENED':-9.0,'PRICE CONFIRMED • VOLUME UNAVAILABLE':0.5}
        mod=scale.get(pmc,0.0)+scale.get(ahc,0.0)
        return round(_clip100(base+mod),1)
    z['TopScore']=z.apply(top_score,axis=1)
    z=z.sort_values(['TopScore','OpportunityScore','ExplosiveScore'],ascending=False).reset_index(drop=True)
    z['GlobalRank']=np.arange(1,len(z)+1)
    z['_RankScore']=pd.to_numeric(z['TopScore'],errors='coerce').fillna(0)
    z['MarketRank']=z.groupby('Market')['_RankScore'].rank(method='first',ascending=False).astype(int)
    z['SectorRank']=z.groupby(['Market','Sector'])['_RankScore'].rank(method='first',ascending=False).astype(int)
    priority={'CONFIRMED ENTRY':8,'ARMED':7,'WATCH':6,'WAIT':5,'RETEST ONLY / LATE':4,'EXTENDED — DO NOT CHASE':3,'TOO LATE / CHASE':2,'INVALIDATED':1}
    z['_StagePriority']=z['TradeStage'].map(priority).fillna(1)
    z['_ExitPenalty']=(pd.to_numeric(z['ExitPressure'],errors='coerce').fillna(0)>=55).astype(int)
    order=z.sort_values(['_ExitPenalty','_StagePriority','TopScore'],ascending=[True,False,False]).index.tolist()
    pr={idx:i+1 for i,idx in enumerate(order)}; z['TradePriorityRank']=[pr[i] for i in z.index]
    _plan_ok=z['PlanValid'].astype(bool) if 'PlanValid' in z else True
    _data_ok=z['DataQuality'].eq('OK') if 'DataQuality' in z else True
    _price_fresh=z['LivePriceFresh'].fillna(True).astype(bool) if 'LivePriceFresh' in z else True
    # V6.1.4 AH-aware: after-hours confirmation is context only, not ActionableNow.
    # Hourly/15m Entry indicators are regular-session features, so an AH print must be
    # reconfirmed in the next regular session before becoming a trade-grade live entry.
    _evidence_ok=z['EvidenceGuardOK'].fillna(True).astype(bool) if 'EvidenceGuardOK' in z else True
    z['ActionableNow']=(((z['MarketPhase'].eq('OPEN')) & z['LiveStage'].eq('CONFIRMED ENTRY — LIVE')) | ((z['MarketPhase'].eq('PRE-MARKET')) & z['PMConfirmation'].eq('CONFIRMED') & z['TradeStage'].eq('CONFIRMED ENTRY'))) & (pd.to_numeric(z['ExitPressure'],errors='coerce').fillna(0)<55) & _plan_ok & _data_ok & _price_fresh & _evidence_ok
    return z.drop(columns=['_StagePriority','_ExitPenalty','_RankScore'],errors='ignore')


def safe(x,d=2):
    try:return "—" if pd.isna(x) else f"{float(x):.{d}f}"
    except:return "—"
def cls(s):
    s=str(s).upper()
    # Order matters: previous-session/closed labels must never turn green just because they contain “TRIGGER”.
    if any(x in s for x in ["WEAKENED","AVOID","COLD","EXIT TRIGGER","EXIT ARMED","DISTRIBUTION","DATA CHECK"]): return "bad"
    if any(x in s for x in ["CLOSED","PREVIOUS SESSION","PRE-OPEN","WATCH","WAIT","ARMED","RETEST ONLY / LATE","SETUP","NEUTRAL","MOVEMENT TRIGGER"]): return "warn"
    if any(x in s for x in ["PRE-MARKET CONFIRMED","AFTER-MARKET CONFIRMED","CONFIRMED ENTRY","ENTER"]): return "good"
    return "warn"
def chart(df,title,layers=None,show_rsi=False,show_macd=False,trade_plan=None,current_price=None):
    """Stable display-only Plotly chart with persistent UI state and mobile-safe controls."""
    q=df.copy()
    layers=layers or ["EMA9","EMA20","EMA50","VWAP","Volume"]
    extra_rows=int(bool(show_rsi))+int(bool(show_macd))
    rows=2+extra_rows
    heights=[.68,.20]
    if show_rsi: heights.append(.12)
    if show_macd: heights.append(.16)
    # normalize heights for Plotly
    total=sum(heights); heights=[h/total for h in heights]
    fig=make_subplots(rows=rows,cols=1,shared_xaxes=True,row_heights=heights,vertical_spacing=.035)
    fig.add_trace(go.Candlestick(x=q.index,open=q.Open,high=q.High,low=q.Low,close=q.Close,name="Price"),row=1,col=1)
    if current_price is not None and np.isfinite(float(current_price)):
        fig.add_hline(y=float(current_price),line_dash="dot",line_width=1.2,annotation_text="Last price",row=1,col=1)
    if isinstance(trade_plan,dict) and bool(trade_plan.get('plan_valid',False)):
        try:
            zl=float(trade_plan.get('zone_low')); zh=float(trade_plan.get('zone_high')); inv=float(trade_plan.get('invalidation')); trg=float(trade_plan.get('trigger')); t1=float(trade_plan.get('target1')); t2=float(trade_plan.get('target2'))
            if all(np.isfinite(v) for v in [zl,zh,inv,trg,t1,t2]):
                fig.add_hrect(y0=zl,y1=zh,opacity=.10,line_width=0,annotation_text="Entry zone",row=1,col=1)
                fig.add_hline(y=trg,line_dash="dash",line_width=1,annotation_text="Trade trigger",row=1,col=1)
                fig.add_hline(y=inv,line_dash="dash",line_width=1,annotation_text="Invalidation",row=1,col=1)
                fig.add_hline(y=t1,line_dash="dot",line_width=1,annotation_text="T1",row=1,col=1)
                fig.add_hline(y=t2,line_dash="dot",line_width=1,annotation_text="T2",row=1,col=1)
        except Exception:
            pass
    overlays={"EMA9":"ema9","EMA20":"ema20","EMA50":"ema50","VWAP":"vwap"}
    for label,col in overlays.items():
        if label in layers and col in q:
            fig.add_trace(go.Scatter(x=q.index,y=q[col],name=label,line=dict(width=1.25)),row=1,col=1)
    if "Volume" in layers:
        fig.add_trace(go.Bar(x=q.index,y=q.Volume,name="Volume",opacity=.65),row=2,col=1)
    else:
        fig.add_trace(go.Bar(x=q.index,y=[0]*len(q),name="Volume",opacity=0,showlegend=False),row=2,col=1)
    next_row=3
    if show_rsi:
        if 'rsi14' in q:
            fig.add_trace(go.Scatter(x=q.index,y=q.rsi14,name="RSI14",line=dict(width=1.2)),row=next_row,col=1)
            fig.add_hline(y=70,line_dash="dot",row=next_row,col=1)
            fig.add_hline(y=30,line_dash="dot",row=next_row,col=1)
            fig.update_yaxes(range=[0,100],row=next_row,col=1)
        next_row+=1
    if show_macd:
        if 'macd_hist' in q:
            fig.add_trace(go.Bar(x=q.index,y=q.macd_hist,name="MACD hist",opacity=.75),row=next_row,col=1)
        if 'macd' in q:
            fig.add_trace(go.Scatter(x=q.index,y=q.macd,name="MACD",line=dict(width=1.1)),row=next_row,col=1)
        if 'macd_signal' in q:
            fig.add_trace(go.Scatter(x=q.index,y=q.macd_signal,name="MACD signal",line=dict(width=1.0)),row=next_row,col=1)
    fig.update_layout(
        height=610 + 100*extra_rows,
        title=title,
        template="plotly_dark",
        paper_bgcolor="#0b0f17",plot_bgcolor="#0b0f17",
        margin=dict(l=8,r=8,t=45,b=8),
        xaxis_rangeslider_visible=False,
        legend=dict(orientation="h",yanchor="bottom",y=1.02,xanchor="left",x=0),
        uirevision=f"stable-stock-chart-v590-{title}",
        dragmode="pan",
        autosize=True,
    )
    # Quick range buttons live on the bottom shared x-axis. Double-click also resets.
    fig.update_xaxes(
        rangeselector=dict(buttons=[
            dict(count=5,label="5D",step="day",stepmode="backward"),
            dict(count=1,label="1M",step="month",stepmode="backward"),
            dict(count=3,label="3M",step="month",stepmode="backward"),
            dict(count=6,label="6M",step="month",stepmode="backward"),
            dict(count=1,label="1Y",step="year",stepmode="backward"),
            dict(label="MAX",step="all"),
        ]),
        row=rows,col=1
    )
    return fig

CHART_CONFIG={
    "displaylogo":False,
    "responsive":True,
    "scrollZoom":True,
    "staticPlot":False,
    "displayModeBar":True,
    "modeBarButtonsToAdd":["zoom2d","pan2d","zoomIn2d","zoomOut2d","autoScale2d","resetScale2d"],
    "doubleClick":"reset",
    "modeBarButtonsToRemove":["select2d","lasso2d"],
    "toImageButtonOptions":{"format":"png","filename":"AI_Stock_Hunter_chart","scale":2},
}

def _entry_score_from_row(r, quant_score, early_score=0.0):
    """Single-source V6.0 Entry Score used by live analysis and validation."""
    if callable(entry_score_row):
        try:return float(entry_score_row(r,quant_score)[0])
        except Exception:pass
    return 0.0


def _entry_forward_metrics(feat, horizon, target_pct):
    f=feat.copy(); n=len(f)
    highs=f['High'].to_numpy(dtype='float64'); lows=f['Low'].to_numpy(dtype='float64'); closes=f['Close'].to_numpy(dtype='float64')
    hit=np.full(n,np.nan); ret=np.full(n,np.nan); mae=np.full(n,np.nan); mfe=np.full(n,np.nan); days=np.full(n,np.nan)
    for i in range(n-int(horizon)):
        p=closes[i]; fh=highs[i+1:i+1+int(horizon)]; fl=lows[i+1:i+1+int(horizon)]
        if not np.isfinite(p) or p<=0 or len(fh)==0 or len(fl)==0:continue
        target=p*(1+float(target_pct)); reached=np.where(fh>=target)[0]
        hit[i]=1.0 if len(reached) else 0.0
        days[i]=float(reached[0]+1) if len(reached) else np.nan
        ret[i]=closes[i+int(horizon)]/p-1.0
        mfe[i]=np.nanmax(fh)/p-1.0
        mae[i]=np.nanmin(fl)/p-1.0
    return hit,ret,mfe,mae,days


def _entry_bucket(score):
    if score>=80:return '80–100'
    if score>=70:return '70–79'
    if score>=60:return '60–69'
    return '<60'



def _entry_research_features_v612(r,quant_score,entry_score):
    """Historical daily feature builder used by the nested OOS Entry Optimizer.

    Restored in V6.3.9.41 from the original V6.1.2 implementation. The
    optimizer and the live OOS scorer intentionally share the same causal
    feature semantics.
    """
    xp,_,_=exit_pressure_row(r); dv=directional_volume_row(r); inst=institutional_flow_row(r)
    p=float(r.get('Close',np.nan));atr=float(r.get('atr14',np.nan));e20=float(r.get('ema20',np.nan));e9=float(r.get('ema9',np.nan));rs=float(r.get('rsi14',np.nan));mom3=float(r.get('mom3',0) or 0)
    a=atr if np.isfinite(atr) and atr>0 else (p*.02 if np.isfinite(p) else 1.0)
    setup=bool(entry_score>=56 and quant_score>=58 and xp<55 and (not np.isfinite(e20) or p>=e20-.2*a) and (not (np.isfinite(e9) and np.isfinite(e20)) or e9>=e20-.08*a))
    fresh=bool(float(r.get('fresh_transition_count',0) or 0)>0 or (float(r.get('macd_hist_slope',0) or 0)>0 and float(r.get('vol_accel',0) or 0)>=1.08))
    flow=bool(dv.get('bullish',0)>=.22 and dv.get('bullish',0)>dv.get('bearish',0))
    nochase=bool((not np.isfinite(e20) or (p-e20)/a<=1.65) and (not np.isfinite(rs) or rs<=76) and mom3<=.16)
    rr=float(r.get('robust_volume_ratio',r.get('volume_ratio',np.nan)));adx=float(r.get('adx14',np.nan));va=float(r.get('vol_accel',np.nan));ft=float(r.get('fresh_transition_count',0) or 0)
    return {
        'TriggerEligible':bool(setup and fresh and flow and nochase and xp<45),'DailySetup':setup,'FreshSignal':fresh,'VolumeFlow':flow,'NoChase':nochase,'ExitPressureAtSignal':xp,
        'InstitutionalFlow':float(inst.get('score',0))/100.0,'InstitutionalFlowScore':float(inst.get('score',0)),'InstitutionalFlowLabel':inst.get('label','NEUTRAL'),
        'RVOLNorm':float(np.clip((rr-0.8)/1.7,0,1)) if np.isfinite(rr) else 0.0,'ADXNorm':float(np.clip((adx-15)/30,0,1)) if np.isfinite(adx) else 0.0,
        'VolAccelNorm':float(np.clip((va-0.85)/0.75,0,1)) if np.isfinite(va) else 0.0,'FreshTransitionNorm':float(np.clip(ft/3.0,0,1)),
    }


def _entry_research_gate_v610(r,quant_score,entry_score):
    return _entry_research_features_v612(r,quant_score,entry_score)



SHADOW_MODEL_PATH_V612=Path(__file__).resolve().with_name('entry_shadow_model_v612.json')
MODEL_REGISTRY_PATH_V613=Path(__file__).resolve().with_name('entry_model_registry_v613.json')


def _load_shadow_model_v612():
    """Legacy latest-model loader kept for backward compatibility."""
    try:
        if SHADOW_MODEL_PATH_V612.exists():
            obj=json.loads(SHADOW_MODEL_PATH_V612.read_text())
            return obj if isinstance(obj,dict) else None
    except Exception:pass
    return None


def _save_shadow_model_v612(model):
    try:
        if model and model.get('scopes'):SHADOW_MODEL_PATH_V612.write_text(json.dumps(model,indent=2,sort_keys=True))
    except Exception:pass


def _load_model_registry_v613():
    try:
        if MODEL_REGISTRY_PATH_V613.exists():
            obj=json.loads(MODEL_REGISTRY_PATH_V613.read_text())
            if isinstance(obj,dict) and isinstance(obj.get('models'),list):return obj
    except Exception:pass
    return {'version':APP_VERSION,'updated':None,'models':[]}


def _save_model_registry_v613(reg):
    try:
        if isinstance(reg,dict):
            reg['version']=APP_VERSION;reg['updated']=datetime.now().isoformat(timespec='seconds')
            MODEL_REGISTRY_PATH_V613.write_text(json.dumps(reg,indent=2,sort_keys=True))
    except Exception:pass


def _model_id_v613(model,cfg):
    created=str(model.get('created') or datetime.now().isoformat(timespec='seconds')).replace(':','').replace('-','')
    return f"{created}_{str(cfg.get('market','ALL')).replace(' ','_')}_{int(cfg.get('horizon',3))}D_{float(cfg.get('target',3)):g}P"


def _register_model_v613(model,cfg,hourly_model=None):
    """Append one optimizer run to the persistent registry; never overwrite older evidence."""
    if not isinstance(model,dict):return _load_model_registry_v613()
    daily_scopes=model.get('scopes',{}) or {}
    hourly_scopes=(hourly_model or {}).get('scopes',{}) if isinstance(hourly_model,dict) else {}
    if not daily_scopes and not hourly_scopes:return _load_model_registry_v613()
    reg=_load_model_registry_v613(); mid=_model_id_v613(model,cfg)
    rec={
        'model_id':mid,'version':APP_VERSION,'created':model.get('created',datetime.now().isoformat(timespec='seconds')),
        'source_universe':cfg.get('market','CUSTOM'),'history':cfg.get('history','1y'),
        'horizon_days':int(cfg.get('horizon',3)),'target_pct':float(cfg.get('target',3)),
        'hourly_target_pct':float(cfg.get('hourly_target',3)),'hourly_bars':[int(x) for x in cfg.get('hourly_bars',(1,2,4))],
        'scopes':daily_scopes,'hourly_scopes':hourly_scopes,
    }
    models=[x for x in reg.get('models',[]) if x.get('model_id')!=mid];models.append(rec)
    # Keep a bounded registry while preserving enough history to compare repeated optimizations.
    models=sorted(models,key=lambda x:str(x.get('created','')))[-80:]
    reg['models']=models;_save_model_registry_v613(reg)
    # Keep legacy latest file too so an older deployment can still read something.
    legacy=dict(model);legacy.update({'source_universe':rec['source_universe'],'history':rec['history'],'horizon_days':rec['horizon_days'],'target_pct':rec['target_pct'],'model_id':mid,'hourly_scopes':rec['hourly_scopes']})
    _save_shadow_model_v612(legacy)
    return reg



def _import_optimizer_workbook_v613(file_obj):
    """Import prior Optimizer evidence into the registry, including Hourly OOS.

    V6.3.9.46 can reuse prior 1Y optimizer workbooks after redeploy, so the
    user does not need to rerun ~100k intraday observations merely to activate a
    SHADOW ELIGIBLE timing model. Daily and Hourly layers are imported separately.
    """
    try:
        xls=pd.ExcelFile(file_obj)
        about=pd.read_excel(xls,'About') if 'About' in xls.sheet_names else pd.DataFrame()
        meta={str(r['Field']):r['Value'] for _,r in about.iterrows()} if set(['Field','Value']).issubset(about.columns) else {}
        scopes={};hourly_scopes={}
        opt_name='Daily OOS Optimizer' if 'Daily OOS Optimizer' in xls.sheet_names else ('Entry Optimizer Shadow' if 'Entry Optimizer Shadow' in xls.sheet_names else None)
        wt_name='Daily OOS Weights' if 'Daily OOS Weights' in xls.sheet_names else ('Optimizer Weights' if 'Optimizer Weights' in xls.sheet_names else None)
        if opt_name and wt_name:
            opt=pd.read_excel(xls,opt_name);wt=pd.read_excel(xls,wt_name)
            for _,r in opt.iterrows():
                scope=str(r.get('Scope','')).strip()
                if not scope:continue
                wg=wt[wt['Scope'].astype(str)==scope] if 'Scope' in wt else pd.DataFrame()
                weights={str(x.get('Feature')):float(x.get('Learned weight %'))/100.0 for _,x in wg.iterrows() if pd.notna(x.get('Feature')) and pd.notna(x.get('Learned weight %'))}
                if not weights:continue
                scopes[scope]={'weights':weights,'threshold':float(r.get('Shadow threshold',wg['Shadow threshold'].iloc[0] if not wg.empty and 'Shadow threshold' in wg else .65)),'status':str(r.get('Status','RESEARCH ONLY')),'inner_median_lift':float(r.get('Inner median OOS lift',np.nan)) if pd.notna(r.get('Inner median OOS lift',np.nan)) else None,'inner_worst_lift':float(r.get('Inner worst OOS lift',np.nan)) if pd.notna(r.get('Inner worst OOS lift',np.nan)) else None,'stability':float(r.get('Stability',np.nan)) if pd.notna(r.get('Stability',np.nan)) else None,'inner_signals':int(r.get('Inner validation signals',0) or 0),'inner_positive_folds_pct':float(r.get('Inner positive folds %',np.nan)) if pd.notna(r.get('Inner positive folds %',np.nan)) else None,'validation_objective':float(r.get('Validation selection score',np.nan)) if pd.notna(r.get('Validation selection score',np.nan)) else None,'fold4_lift':float(r.get('Final Fold4 OOS lift',np.nan)) if pd.notna(r.get('Final Fold4 OOS lift',np.nan)) else None,'fold4_signals':int(r.get('Final Fold4 signals',0) or 0)}
        if 'Hourly OOS Optimizer' in xls.sheet_names and 'Hourly OOS Weights' in xls.sheet_names:
            hop=pd.read_excel(xls,'Hourly OOS Optimizer');hwt=pd.read_excel(xls,'Hourly OOS Weights')
            for _,r in hop.iterrows():
                scope=str(r.get('Scope','')).strip();hlabel=str(r.get('Hourly Horizon','')).strip()
                if not scope or not hlabel:continue
                mask=(hwt['Scope'].astype(str)==scope) if 'Scope' in hwt else pd.Series(False,index=hwt.index)
                if 'Hourly Horizon' in hwt:mask=mask & (hwt['Hourly Horizon'].astype(str)==hlabel)
                wg=hwt[mask]
                weights={str(x.get('Feature')):float(x.get('Learned weight %'))/100.0 for _,x in wg.iterrows() if pd.notna(x.get('Feature')) and pd.notna(x.get('Learned weight %'))}
                if not weights:continue
                
                _med=float(r.get('Inner median OOS lift',np.nan)) if pd.notna(r.get('Inner median OOS lift',np.nan)) else None
                _worst=float(r.get('Inner worst OOS lift',np.nan)) if pd.notna(r.get('Inner worst OOS lift',np.nan)) else None
                _stab=float(r.get('Stability',np.nan)) if pd.notna(r.get('Stability',np.nan)) else None
                _inner=int(r.get('Inner signals',0) or 0);_pos=float(r.get('Positive folds %',np.nan)) if pd.notna(r.get('Positive folds %',np.nan)) else None;_corr=float(r.get('Correlation penalty',0) or 0)
                _vobj=float(r.get('Validation selection score',np.nan)) if pd.notna(r.get('Validation selection score',np.nan)) else None
                if _vobj is None and _med is not None and _worst is not None and _pos is not None:
                    _vobj=(_med-1)*2.3+(_worst-1)*1.0+(_pos/100.0-.5)*.45+((_stab or 0)*.1)+min(_inner,300)/5000.0-_corr*.3
                hourly_scopes.setdefault(scope,{})[hlabel]={'weights':weights,'threshold':float(r.get('Threshold',.5) or .5),'status':str(r.get('Status','RESEARCH ONLY')),'inner_median_lift':_med,'inner_worst_lift':_worst,'stability':_stab,'inner_signals':_inner,'inner_positive_folds_pct':_pos,'validation_objective':_vobj,'fold4_lift':float(r.get('Fold4 matched OOS lift',np.nan)) if pd.notna(r.get('Fold4 matched OOS lift',np.nan)) else None,'fold4_signals':int(r.get('Fold4 signals',0) or 0)}
        if not scopes and not hourly_scopes:return False,'No Daily or Hourly learned scopes found.'
        model={'version':str(meta.get('Version','6.3.9.44')),'created':str(meta.get('Generated',datetime.now().isoformat(timespec='seconds'))),'scopes':scopes}
        hmodel={'scopes':hourly_scopes}
        cfg={'market':meta.get('Market','IMPORTED'),'history':meta.get('History','1y'),'target':float(meta.get('TargetPct',3)),'horizon':int(float(meta.get('HorizonDays',3))),'hourly_target':float(meta.get('HourlyTargetPct',3)),'hourly_bars':tuple(int(str(x).replace('h','')) for x in str(meta.get('HourlyHorizons','1h,2h,4h')).split(',') if str(x).strip()) or (1,2,4)}
        reg=_register_model_v613(model,cfg,hmodel)
        hd=sum(len(v) for v in hourly_scopes.values())
        he=sum(1 for v in hourly_scopes.values() for sc in v.values() if str(sc.get('status',''))=='SHADOW ELIGIBLE')
        de=sum(1 for sc in scopes.values() if str(sc.get('status',''))=='SHADOW ELIGIBLE')
        return True,f"Imported {len(scopes)} Daily scope(s) ({de} eligible) + {hd} Hourly scope(s) ({he} eligible) for {cfg['horizon']}D / +{cfg['target']:g}% into registry ({len(reg.get('models',[]))} runs saved)."
    except Exception as e:
        return False,f'{type(e).__name__}: {str(e)[:180]}'


REGISTRY_SELECTION_POLICY_V63946 = "SPECIFICITY > NEWEST ELIGIBLE 1Y RUN > INNER VALIDATION/STABILITY; FOLD4 = ELIGIBILITY ONLY"

def _scope_validation_key_v63946(scope):
    """Ranking key that never reads final Fold4 outcome quality.

    Fold4 is permitted only through the pre-computed SHADOW ELIGIBLE status.
    Once a scope has passed that gate, model/horizon selection uses information
    from the inner walk-forward validation folds only.
    """
    try:
        obj=float(scope.get('validation_objective')) if scope.get('validation_objective') is not None else float('-inf')
    except Exception:obj=float('-inf')
    def sf(key,default=0.0):
        try:
            v=float(scope.get(key,default));return v if np.isfinite(v) else default
        except Exception:return default
    worst=sf('inner_worst_lift',0.0);med=sf('inner_median_lift',0.0);stability=sf('stability',0.0);signals=sf('inner_signals',0.0);positive=sf('inner_positive_folds_pct',0.0)
    # Prefer the optimizer's own inner-validation objective when available.
    # Remaining fields are deterministic tie-breakers and also validation-only.
    return (obj,worst,med,stability,min(signals,10000.0),positive)

def _registry_recency_key_v63946(rec):
    try:
        ts=pd.Timestamp(rec.get('created'))
        if pd.isna(ts):return 0
        return int(ts.value)
    except Exception:return 0

def _pick_registry_candidate_v63946(options,scope_index=-1,rec_index=-3):
    """Pick without peeking at Fold4 lift.

    Options must already be SHADOW ELIGIBLE. Exact-market/US/ALL specificity
    remains the first rule. Among that tier, the newest eligible data vintage
    is used so repeated optimizer runs cannot create a historical Fold4
    champion. Multiple candidates inside the same run (mainly 1h/2h/4h) are
    resolved only by inner-validation/stability metrics.
    """
    if not options:return None
    best_pri=max(x[0] for x in options);tier=[x for x in options if x[0]==best_pri]
    newest=max(_registry_recency_key_v63946(x[rec_index]) for x in tier)
    current=[x for x in tier if _registry_recency_key_v63946(x[rec_index])==newest]
    return max(current,key=lambda x:_scope_validation_key_v63946(x[scope_index]))


def _candidate_scope_v613(rec,market):
    scopes=rec.get('scopes',{}) if isinstance(rec,dict) else {};source=str(rec.get('source_universe','ALL 151')).upper()
    # An "ALL" scope inside a US-only/HK-only/TASE-only run is local to that universe,
    # not a license to apply those weights to another exchange.
    source_ok=(source.startswith('ALL') or source in ('CUSTOM','IMPORTED')) or (source.startswith('US') and market in ('NASDAQ','NYSE','US')) or ('HONG KONG' in source and market=='HONG KONG') or ('TEL AVIV' in source and market=='TEL AVIV')
    order=[]
    if market in scopes:order.append((3,market,scopes[market]))
    if market in ('NASDAQ','NYSE','US') and 'US' in scopes:order.append((2,'US',scopes['US']))
    if source_ok and 'ALL' in scopes:order.append((1,'ALL',scopes['ALL']))
    return order


def _candidate_hourly_scope_v613(rec,market,horizon_label):
    scopes=rec.get('hourly_scopes',{}) if isinstance(rec,dict) else {};source=str(rec.get('source_universe','ALL 151')).upper()
    source_ok=(source.startswith('ALL') or source in ('CUSTOM','IMPORTED')) or (source.startswith('US') and market in ('NASDAQ','NYSE','US')) or ('HONG KONG' in source and market=='HONG KONG') or ('TEL AVIV' in source and market=='TEL AVIV')
    out=[]
    for pri,key in ((3,market),(2,'US' if market in ('NASDAQ','NYSE','US') else None),(1,'ALL' if source_ok else None)):
        if not key or key not in scopes:continue
        hobj=(scopes.get(key) or {}).get(horizon_label)
        if hobj:out.append((pri,key,hobj))
    return out


def _select_active_model_v613(registry,horizon_days,target_pct,hourly_target_pct=3.0):
    """Select eligible 1Y Daily and Hourly layers without holdout cherry-picking.

    V6.3.9.46 makes Fold4 a final pass/fail gate only.  It is never used to
    choose one already-eligible registry model over another. Selection order:
      1) exact market > US fallback > ALL fallback;
      2) newest eligible 1Y optimizer run in that specificity tier;
      3) when that run has multiple Hourly horizons, the optimizer's INNER
         validation/stability evidence chooses the horizon.
    This preserves Fold4 as a genuine untouched audit holdout across repeated
    runs rather than turning the highest historical Fold4 lift into production.
    """
    models=[] if not isinstance(registry,dict) else list(registry.get('models',[]))
    models=[m for m in models if str(m.get('history','')).strip().lower()=='1y']
    daily_candidates=[m for m in models if (horizon_days is None or int(m.get('horizon_days',-1))==int(horizon_days)) and abs(float(m.get('target_pct',-999))-float(target_pct))<1e-9]
    hourly_candidates=[m for m in models if abs(float(m.get('hourly_target_pct',3))-float(hourly_target_pct))<1e-9]
    active={'version':APP_VERSION,'created':datetime.now().isoformat(timespec='seconds'),'horizon_days':'AUTO' if horizon_days is None else int(horizon_days),'target_pct':float(target_pct),'hourly_target_pct':float(hourly_target_pct),'selection_policy':REGISTRY_SELECTION_POLICY_V63946,'scopes':{},'hourly_scopes':{},'selected_models':{},'selected_hourly_models':{}}
    for market in ('NASDAQ','NYSE','HONG KONG','TEL AVIV'):
        opts=[]
        for rec in daily_candidates:
            for pri,skey,scope in _candidate_scope_v613(rec,market):
                if str(scope.get('status',''))!='SHADOW ELIGIBLE':continue
                opts.append((pri,rec,skey,scope))
        picked=_pick_registry_candidate_v63946(opts,scope_index=3,rec_index=1)
        if picked:
            pri,rec,skey,scope=picked
            chosen=dict(scope);chosen.update({'registry_model_id':rec.get('model_id'),'registry_scope':skey,'registry_source':rec.get('source_universe'),'registry_created':rec.get('created'),'horizon_days':rec.get('horizon_days'),'target_pct':rec.get('target_pct'),'selection_policy':REGISTRY_SELECTION_POLICY_V63946})
            active['scopes'][market]=chosen
            active['selected_models'][market]={'model_id':rec.get('model_id'),'scope':skey,'horizon_days':rec.get('horizon_days'),'target_pct':rec.get('target_pct'),'inner_median_lift':scope.get('inner_median_lift'),'inner_worst_lift':scope.get('inner_worst_lift'),'stability':scope.get('stability'),'inner_signals':scope.get('inner_signals'),'validation_objective':scope.get('validation_objective'),'fold4_lift':scope.get('fold4_lift'),'fold4_signals':scope.get('fold4_signals'),'source_universe':rec.get('source_universe'),'created':rec.get('created'),'selection_policy':REGISTRY_SELECTION_POLICY_V63946}

        # Hourly timing is selected independently from Daily/Core. Fold4 only
        # decides eligibility. It does NOT rank eligible runs or horizons.
        hopts=[]
        for hrec in hourly_candidates:
            for hlabel in ('1h','2h','4h'):
                for hpri,hkey,hscope in _candidate_hourly_scope_v613(hrec,market,hlabel):
                    if str(hscope.get('status',''))!='SHADOW ELIGIBLE':continue
                    hopts.append((hpri,hlabel,hrec,hkey,hscope))
        hpicked=_pick_registry_candidate_v63946(hopts,scope_index=4,rec_index=2)
        if hpicked:
            hpri,hlabel,hrec,hkey,hscope=hpicked
            hchosen=dict(hscope);hchosen.update({'registry_model_id':hrec.get('model_id'),'registry_scope':hkey,'registry_source':hrec.get('source_universe'),'registry_created':hrec.get('created'),'hourly_target_pct':hrec.get('hourly_target_pct',3),'selection_policy':REGISTRY_SELECTION_POLICY_V63946})
            active['hourly_scopes'][market]={hlabel:hchosen}
            active['selected_hourly_models'][market]={'model_id':hrec.get('model_id'),'scope':hkey,'hourly_horizon':hlabel,'hourly_target_pct':hrec.get('hourly_target_pct',3),'inner_median_lift':hscope.get('inner_median_lift'),'inner_worst_lift':hscope.get('inner_worst_lift'),'stability':hscope.get('stability'),'inner_signals':hscope.get('inner_signals'),'validation_objective':hscope.get('validation_objective'),'fold4_lift':hscope.get('fold4_lift'),'fold4_signals':hscope.get('fold4_signals'),'source_universe':hrec.get('source_universe'),'created':hrec.get('created'),'selection_policy':REGISTRY_SELECTION_POLICY_V63946}
    active['source_universe']='MODEL REGISTRY'
    return active


def _active_model_has_any_v63945(model):
    return bool(isinstance(model,dict) and ((model.get('scopes') or {}) or (model.get('hourly_scopes') or {})))


def _select_promoted_hourly_model_v63945(registry,hourly_target_pct=3.0):
    """Return only the promoted 1Y SHADOW ELIGIBLE Hourly timing layer.

    This is the V6.3.9.46 production promotion path: Scanner PRODUCTION and
    Analyze may use proven intraday timing weights, while Daily/Core OOS weights
    stay disabled unless the user explicitly chooses OOS OPTIMIZED in Scanner.
    """
    full=_select_active_model_v613(registry,None,3.0,hourly_target_pct)
    return {
        'version':APP_VERSION,
        'created':datetime.now().isoformat(timespec='seconds'),
        'history':'1y',
        'hourly_target_pct':float(hourly_target_pct),
        'scopes':{},
        'hourly_scopes':dict(full.get('hourly_scopes',{}) or {}),
        'selected_models':{},
        'selected_hourly_models':dict(full.get('selected_hourly_models',{}) or {}),
        'source_universe':'MODEL REGISTRY • PROMOTED HOURLY OOS',
    }


def _registry_selection_frame_v613(active):
    rows=[]
    active=active or {}
    markets=sorted(set((active.get('selected_models',{}) or {}).keys()) | set((active.get('selected_hourly_models',{}) or {}).keys()))
    for market in markets:
        meta=(active.get('selected_models',{}) or {}).get(market,{})
        hmeta=(active.get('selected_hourly_models',{}) or {}).get(market,{})
        rows.append({
            'Market':market,
            'Daily Layer':'ACTIVE' if meta else 'PRODUCTION / NO ELIGIBLE DAILY OOS',
            'Daily Horizon':f"{meta.get('horizon_days','—')}D" if meta else '—',
            'Daily Target %':meta.get('target_pct',np.nan) if meta else np.nan,
            'Daily Model ID':meta.get('model_id','—'),
            'Daily Scope':meta.get('scope','—'),
            'Daily Inner Worst Lift':meta.get('inner_worst_lift',np.nan),
            'Daily Inner Median Lift':meta.get('inner_median_lift',np.nan),
            'Daily Stability':meta.get('stability',np.nan),
            'Daily Inner Signals':meta.get('inner_signals',0) if meta else 0,
            'Daily Fold4 OOS Lift (eligibility only)':meta.get('fold4_lift',np.nan),
            'Daily Fold4 Signals':meta.get('fold4_signals',0) if meta else 0,
            'Hourly Layer':'ACTIVE — OOS LEARNED TIMING' if hmeta else 'FALLBACK — BASE TIMING',
            'Hourly Model':hmeta.get('hourly_horizon','—'),
            'Hourly Target %':hmeta.get('hourly_target_pct',np.nan) if hmeta else np.nan,
            'Hourly Model ID':hmeta.get('model_id','—'),
            'Hourly Scope':hmeta.get('scope','—'),
            'Hourly Inner Worst Lift':hmeta.get('inner_worst_lift',np.nan),
            'Hourly Inner Median Lift':hmeta.get('inner_median_lift',np.nan),
            'Hourly Stability':hmeta.get('stability',np.nan),
            'Hourly Inner Signals':hmeta.get('inner_signals',0) if hmeta else 0,
            'Hourly Validation Score':hmeta.get('validation_objective',np.nan),
            'Hourly Fold4 OOS Lift (eligibility only)':hmeta.get('fold4_lift',np.nan),
            'Hourly Fold4 Signals':hmeta.get('fold4_signals',0) if hmeta else 0,
            'Selection Policy':meta.get('selection_policy',hmeta.get('selection_policy',REGISTRY_SELECTION_POLICY_V63946)),
            'Source':meta.get('source_universe',hmeta.get('source_universe','—')),
            'Created':meta.get('created',hmeta.get('created','—')),
        })
    return pd.DataFrame(rows)


def _registry_candidate_audit_v63946(registry,horizon_days,target_pct,hourly_target_pct,active):
    """Expose every eligible registry candidate and prove Fold4 is not ranked."""
    models=[] if not isinstance(registry,dict) else [m for m in registry.get('models',[]) if str(m.get('history','')).strip().lower()=='1y']
    rows=[];active=active or {}
    selected_d=active.get('selected_models',{}) or {};selected_h=active.get('selected_hourly_models',{}) or {}
    def append_row(market,layer,pri,rec,scope_key,scope,hlabel='—'):
        sm=selected_h.get(market,{}) if layer=='HOURLY' else selected_d.get(market,{})
        selected=(str(sm.get('model_id',''))==str(rec.get('model_id','')) and str(sm.get('scope',''))==str(scope_key) and (layer!='HOURLY' or str(sm.get('hourly_horizon',''))==str(hlabel)))
        rows.append({'Market':market,'Layer':layer,'Hourly Horizon':hlabel,'Specificity':{3:'EXACT MARKET',2:'US FALLBACK',1:'ALL FALLBACK'}.get(pri,str(pri)),'Model ID':rec.get('model_id'),'Scope':scope_key,'Created':rec.get('created'),'Inner Validation Score':scope.get('validation_objective',np.nan),'Inner Worst Lift':scope.get('inner_worst_lift',np.nan),'Inner Median Lift':scope.get('inner_median_lift',np.nan),'Stability':scope.get('stability',np.nan),'Inner Signals':scope.get('inner_signals',0),'Fold4 Lift (eligibility only)':scope.get('fold4_lift',np.nan),'Fold4 Signals':scope.get('fold4_signals',0),'Selected':bool(selected),'Selection Policy':REGISTRY_SELECTION_POLICY_V63946})
    for market in ('NASDAQ','NYSE','HONG KONG','TEL AVIV'):
        for rec in models:
            if (horizon_days is None or int(rec.get('horizon_days',-1))==int(horizon_days)) and abs(float(rec.get('target_pct',-999))-float(target_pct))<1e-9:
                for pri,key,scope in _candidate_scope_v613(rec,market):
                    if str(scope.get('status',''))=='SHADOW ELIGIBLE':append_row(market,'DAILY',pri,rec,key,scope)
            if abs(float(rec.get('hourly_target_pct',3))-float(hourly_target_pct))<1e-9:
                for hlabel in ('1h','2h','4h'):
                    for pri,key,scope in _candidate_hourly_scope_v613(rec,market,hlabel):
                        if str(scope.get('status',''))=='SHADOW ELIGIBLE':append_row(market,'HOURLY',pri,rec,key,scope,hlabel)
    if not rows:return pd.DataFrame()
    out=pd.DataFrame(rows)
    spec={'EXACT MARKET':0,'US FALLBACK':1,'ALL FALLBACK':2}
    out['_spec']=out['Specificity'].map(spec).fillna(9)
    out['_sel']=(~out['Selected']).astype(int)
    out=out.sort_values(['Market','Layer','_sel','_spec','Created','Inner Worst Lift','Inner Median Lift'],ascending=[True,True,True,True,False,False,False]).drop(columns=['_spec','_sel']).reset_index(drop=True)
    return out


def _model_scope_for_ticker_v612(model,ticker):
    if not model:return None
    market=_market_for_ticker_v612(ticker)
    scopes=model.get('scopes',{})
    if market in scopes:return scopes[market]
    if market in ('NASDAQ','NYSE','US') and 'US' in scopes:return scopes['US']
    return scopes.get('ALL')


def _optimized_feature_values_v612(row):
    def n(key,default=0):
        try:
            v=float(row.get(key,default));return v if np.isfinite(v) else default
        except:return default
    return {
        'DailySetup':1.0 if bool(row.get('DailySetupCheck',row.get('DailySetup',False))) else 0.0,
        'FreshSignal':1.0 if bool(row.get('FreshSignalCheck',row.get('FreshSignal',False))) else 0.0,
        'VolumeFlow':1.0 if bool(row.get('VolumeFlowCheck',row.get('VolumeFlow',False))) else 0.0,
        'NoChase':1.0 if bool(row.get('NoChaseCheck',row.get('NoChase',False))) else 0.0,
        'EntryNorm':np.clip(n('EntryScore')/100.0,0,1),'QuantNorm':np.clip(n('DynamicQuant',n('QuantScore'))/100.0,0,1),
        'ExitSafety':np.clip((100-n('ExitPressure',n('ExitPressureAtSignal',50)))/100.0,0,1),'InstitutionalFlow':np.clip(n('InstitutionalFlowScore')/100.0,0,1),
        'RVOLNorm':np.clip((n('DailyRobustRVOL',n('RobustRVOL',1))-0.8)/1.7,0,1),'ADXNorm':np.clip((n('ADX14',15)-15)/30,0,1),
        'VolAccelNorm':np.clip((n('VolumeAccel',0.85)-0.85)/0.75,0,1),'FreshTransitionNorm':np.clip(n('FreshTransitionCount')/3.0,0,1),
    }


def _live_hourly_features_v613(hourly_feat):
    """Features used by the separately learned intraday timing model."""
    names=['HourlyFreshEMA','HourlyRVOLNorm','HourlyBullVolume','HourlyVolAccelNorm','HourlyMACDCross','HourlyVWAPReclaim','HourlyMACDStrength','HourlyInstitutionalFlow','HourlyADXNorm']
    if hourly_feat is None or not isinstance(hourly_feat,pd.DataFrame) or hourly_feat.empty:return {k:np.nan for k in names}
    h=hourly_feat.dropna(subset=['Close']).tail(3)
    if h.empty:return {k:np.nan for k in names}
    last=h.iloc[-1]
    def mx(col,default=0):
        try:
            v=pd.to_numeric(h[col],errors='coerce') if col in h else pd.Series(dtype=float)
            return float(np.nanmax(v)) if len(v) and np.isfinite(np.nanmax(v)) else default
        except:return default
    rr=float(last.get('time_adjusted_rvol',last.get('robust_volume_ratio',np.nan)))
    va=float(last.get('vol_accel',np.nan));adx=float(last.get('adx14',np.nan));ms=float(last.get('macd_hist_slope',np.nan));mh=float(last.get('macd_hist',np.nan))
    dv=directional_volume_row(last);inst=institutional_flow_row(last)
    return {
        'HourlyFreshEMA':1.0 if mx('ema9_cross_up',0)>0 else 0.0,
        'HourlyRVOLNorm':float(np.clip((rr-.8)/1.7,0,1)) if np.isfinite(rr) else np.nan,
        'HourlyBullVolume':float(np.clip(dv.get('bullish',0),0,1)),
        'HourlyVolAccelNorm':float(np.clip((va-.85)/.75,0,1)) if np.isfinite(va) else np.nan,
        'HourlyMACDCross':1.0 if mx('macd_cross_up',0)>0 else 0.0,
        'HourlyVWAPReclaim':1.0 if mx('vwap_cross_up',0)>0 else 0.0,
        'HourlyMACDStrength':1.0 if np.isfinite(ms) and ms>0 and np.isfinite(mh) and mh>0 else 0.0,
        'HourlyInstitutionalFlow':float(np.clip(float(inst.get('score',0))/100.0,0,1)),
        'HourlyADXNorm':float(np.clip((adx-15)/30,0,1)) if np.isfinite(adx) else np.nan,
    }


def _hourly_model_for_ticker_v613(model,ticker):
    if not model:return None,None
    market=_market_for_ticker_v612(ticker);hs=(model.get('hourly_scopes',{}) or {}).get(market,{})
    if not hs:return None,None
    hlabel=next(iter(hs.keys()),None)
    return (hs.get(hlabel),hlabel) if hlabel else (None,None)


def _hourly_score_live_v613(ticker,hourly_feat,model):
    scope,hlabel=_hourly_model_for_ticker_v613(model,ticker)
    if not scope:return np.nan,np.nan,'NO ELIGIBLE HOURLY MODEL','—'
    vals=_live_hourly_features_v613(hourly_feat);weights=scope.get('weights',{})
    present=[k for k in weights if np.isfinite(float(vals.get(k,np.nan)))]
    wsum=sum(float(weights.get(k,0)) for k in present)
    if wsum<=0:return np.nan,np.nan,str(scope.get('status','RESEARCH ONLY')),hlabel
    score=sum(float(weights.get(k,0))*float(vals[k]) for k in present)/wsum
    th=float(scope.get('threshold',.5));match=float(np.clip(100*score/max(th,1e-9),0,100))
    return float(100*score),match,str(scope.get('status','RESEARCH ONLY')),hlabel


def _apply_hourly_oos_entry_v63945(ent,ticker,hourly_feat,model):
    """Apply a SHADOW ELIGIBLE hourly OOS model to the live Entry timing layer.

    The learned model replaces only the Hourly/15m timing gate and the 24% short-
    timing component already present in Entry Score. Daily/Core weights, Top Score,
    Opportunity weights and all safety gates remain unchanged. If no eligible
    hourly model/data exists, the original Entry result is returned untouched.
    """
    out=dict(ent or {})
    scope,hlabel=_hourly_model_for_ticker_v613(model,ticker)
    if not scope or str(scope.get('status',''))!='SHADOW ELIGIBLE':
        out['hourly_oos_active']=False;out['hourly_timing_source']='BASE TIMING'
        return out,(np.nan,np.nan,'NO ELIGIBLE HOURLY MODEL','—')
    vals=_live_hourly_features_v613(hourly_feat);weights=scope.get('weights',{}) or {}
    present=[]
    for k,v in weights.items():
        try:
            vv=float(vals.get(k,np.nan))
            if np.isfinite(vv):present.append((k,float(v),vv))
        except Exception:continue
    wsum=sum(w for _,w,_ in present)
    if wsum<=0:
        out['hourly_oos_active']=False;out['hourly_timing_source']='BASE TIMING — NO LIVE FEATURES'
        return out,(np.nan,np.nan,str(scope.get('status','RESEARCH ONLY')),hlabel or '—')
    score=sum(w*vv for _,w,vv in present)/wsum
    th=float(scope.get('threshold',.5) or .5)
    ratio=score/max(th,1e-9)
    match=float(np.clip(100.0*ratio,0,100))
    # Map the learned threshold to the legacy Hourly pass point (62/100), so
    # the existing Entry architecture keeps the same semantic scale.
    learned_timing=float(np.clip(62.0+55.0*(ratio-1.0),0,100))
    try:legacy=float(out.get('hourly_entry_score',np.nan))
    except Exception:legacy=np.nan
    if not np.isfinite(legacy):legacy=45.0
    # Entry uses Hourly/15m timing at 24%. Reweight only that existing family;
    # cap the live delta so OOS timing cannot overpower Daily/Flow/Safety layers.
    delta=float(np.clip(.24*(learned_timing-legacy),-10.0,10.0))
    def adj(key,factor=1.0):
        try:v=float(out.get(key,np.nan))
        except Exception:v=np.nan
        if np.isfinite(v):out[key]=round(float(np.clip(v+factor*delta,0,100)),1)
    adj('entry_score',1.0);adj('setup_entry_score_pre_chase',1.0);adj('live_actionability_score',.80)
    out['hourly_entry_ok']=bool(score>=th)
    out['hourly_entry_score']=round(learned_timing,1)
    out['hourly_oos_active']=True
    out['hourly_timing_source']='OOS LEARNED'
    out['hourly_oos_score']=round(100*score,2)
    out['hourly_oos_match_pct']=round(match,1)
    out['hourly_oos_ratio']=round(ratio,3)
    out['hourly_oos_threshold']=round(100*th,2)
    out['hourly_oos_horizon']=hlabel or '—'
    out['hourly_oos_model_id']=scope.get('registry_model_id','—')
    out['hourly_oos_scope']=scope.get('registry_scope','—')
    out['hourly_oos_fold4_lift']=scope.get('fold4_lift',np.nan)

    checks={
        'Daily Setup':bool(out.get('daily_setup',False)),
        'Fresh Signal':bool(out.get('fresh_signal',False)),
        'Hourly OOS Timing':bool(out.get('hourly_entry_ok',False)),
        'Volume / Flow':bool(out.get('volume_flow_ok',False)),
        'No Chase':bool(out.get('no_chase',False)),
        'Market Regime':bool(out.get('market_regime_ok',True)),
    }
    confirmed=sum(checks.values());total=len(checks)
    out['confirmed_conditions']=int(confirmed);out['total_conditions']=int(total);out['confirmation_pct']=round(100.0*confirmed/max(total,1),1)
    out['missing_checks']=' • '.join(k for k,v in checks.items() if not v) or 'None'
    plan_valid=bool(out.get('plan_valid',False));ext_ok=bool(out.get('extension_guard_ok',True))
    try:xp=float(out.get('exit_pressure',0) or 0)
    except Exception:xp=0.0
    setup_confirmed=bool(all(checks.values()) and plan_valid and xp<45 and ext_ok)
    price_ok=bool(out.get('price_actionable_now',False));rr_ok=bool(out.get('rr_actionable',False))
    confirmed_gate=bool(setup_confirmed and price_ok and rr_ok)
    out['setup_confirmed']=setup_confirmed;out['confirmed_entry_gate_ok']=confirmed_gate
    existing=str(out.get('trigger_state',out.get('status','WAIT')) or 'WAIT').upper()
    blocked={'INVALIDATED','EXTENDED — DO NOT CHASE','TOO LATE / CHASE','RETEST ONLY / LATE'}
    if existing not in blocked:
        if confirmed_gate and float(out.get('entry_score',0) or 0)>=62:new_state='CONFIRMED ENTRY'
        elif setup_confirmed:new_state='ARMED'
        elif plan_valid and checks['Daily Setup'] and checks['Fresh Signal'] and xp<55 and confirmed>=4:new_state='ARMED'
        elif plan_valid and checks['Daily Setup'] and xp<55:new_state='WATCH'
        else:new_state='WAIT'
        out['status']=new_state;out['trigger_state']=new_state
        if new_state=='CONFIRMED ENTRY':out['recommended_action']=f'ENTRY CONDITIONS CONFIRMED • OOS HOURLY {hlabel}'
        elif new_state=='ARMED':out['recommended_action']=f'ARMED • OOS HOURLY {hlabel} • WAIT FOR FULL ENTRY GATE'
        elif new_state=='WATCH':out['recommended_action']=f'WATCH • OOS HOURLY {hlabel}'
    _why=str(out.get('why_now','') or '')
    oos_note=f'OOS hourly {hlabel} {match:.0f}% • Fold4 lift {float(scope.get("fold4_lift",np.nan)):.2f}x' if np.isfinite(float(scope.get('fold4_lift',np.nan))) else f'OOS hourly {hlabel} {match:.0f}%'
    out['why_now']=' • '.join(x for x in (_why,oos_note) if x)
    return out,(float(100*score),match,str(scope.get('status','RESEARCH ONLY')),hlabel or '—')


def _optimized_score_from_row_v612(row,model,ticker=None):
    scope=_model_scope_for_ticker_v612(model,ticker or row.get('Ticker',''))
    if not scope:return np.nan,np.nan,'NO ELIGIBLE MODEL'
    vals=_optimized_feature_values_v612(row); w=scope.get('weights',{})
    score=sum(float(w.get(k,0))*float(vals.get(k,0)) for k in w)
    th=float(scope.get('threshold',0.65)); status=str(scope.get('status','RESEARCH ONLY'))
    return float(100*score),float(np.clip(100*score/max(th,1e-9),0,100)),status


def _apply_optimized_model_v612(df,model):
    if df is None or not isinstance(df,pd.DataFrame) or df.empty:return df
    z=df.copy(); vals=z.apply(lambda r:_optimized_score_from_row_v612(r,model,r.get('Ticker','')),axis=1)
    z['OptimizedScore']=[x[0] for x in vals];z['OptimizedMatchPct']=[x[1] for x in vals];z['OptimizedModelStatus']=[x[2] for x in vals]
    def model_meta(ticker):
        s=_model_scope_for_ticker_v612(model,ticker)
        return (s or {}).get('registry_model_id','—'),(s or {}).get('registry_scope','—'),(s or {}).get('fold4_lift',np.nan),(s or {}).get('horizon_days',np.nan)
    metas=[model_meta(t) for t in z.get('Ticker',pd.Series('',index=z.index))]
    z['OptimizedModelID']=[x[0] for x in metas];z['OptimizedModelScope']=[x[1] for x in metas];z['OptimizedModelOOSLift']=[x[2] for x in metas];z['OptimizedModelHorizon']=[x[3] for x in metas]
    # Live hourly OOS score is computed during deep analysis and placed on the row.
    def ost(r):
        match=float(r.get('OptimizedMatchPct',0) or 0); hmatch=float(r.get('HourlyOptimizedMatchPct',np.nan));regime=bool(r.get('MarketRegimeCheck',True));xp=float(r.get('ExitPressure',0) or 0)
        hourly_ok=(np.isfinite(hmatch) and hmatch>=100) if pd.notna(r.get('HourlyOptimizedMatchPct',np.nan)) else bool(r.get('HourlyEntryCheck',False))
        ext_ok=bool(r.get('ExtensionGuardCheck',True)) and str(r.get('ChaseRiskLabel','LOW')).upper()!='HIGH'
        if not ext_ok:return 'OPTIMIZED WAIT — EXTENDED'
        if match>=100 and hourly_ok and regime and xp<55:return 'OPTIMIZED CONFIRMED'
        if match>=100 and regime and xp<65:return 'OPTIMIZED ARMED'
        if match>=85:return 'OPTIMIZED WATCH'
        return 'OPTIMIZED WAIT'
    z['OptimizedStage']=z.apply(ost,axis=1);z['OptimizedDelta']=pd.to_numeric(z['OptimizedScore'],errors='coerce')-pd.to_numeric(z.get('TopScore',0),errors='coerce')
    return z

def _aggregate_lift_rows_v611(df, keys, baseline_col):
    if df is None or not isinstance(df,pd.DataFrame) or df.empty:return pd.DataFrame()
    x=df.copy();x['Signals']=pd.to_numeric(x['Signals'],errors='coerce').fillna(0)
    out=[]
    for kvals,g in x.groupby(keys,dropna=False):
        if not isinstance(kvals,tuple):kvals=(kvals,)
        n=float(g.Signals.sum())
        if n<=0:continue
        hits=float((g.Signals*pd.to_numeric(g['Hit Rate %'],errors='coerce').fillna(0)/100).sum())
        bases=float((g.Signals*pd.to_numeric(g[baseline_col],errors='coerce').fillna(0)/100).sum())
        rec={k:v for k,v in zip(keys,kvals)};rec.update({'Signals':int(n),'Hit Rate %':100*hits/n,'Baseline %':100*bases/n,'Lift x':hits/bases if bases>0 else np.nan,'Avg MFE %':float(np.average(pd.to_numeric(g['Avg MFE %'],errors='coerce').fillna(0),weights=g.Signals)),'Avg MAE %':float(np.average(pd.to_numeric(g['Avg MAE %'],errors='coerce').fillna(0),weights=g.Signals)),'Tickers':int(g['Ticker'].nunique()) if 'Ticker' in g else np.nan})
        out.append(rec)
    z=pd.DataFrame(out)
    return z.sort_values(['Lift x','Signals'],ascending=[False,False]).reset_index(drop=True) if not z.empty else z

def _entry_optimizer_v611(rows, min_signals=60, seed=612, cancel_check=None, progress_cb=None):
    """V6.1.2 nested OOS optimizer, optimized in V6.3.9.42.

    Statistical semantics are unchanged: folds 2-3 select the candidate and
    threshold; fold 4 remains untouched until the final OOS report.  V6.3.9.42
    removes repeated DataFrame filtering from the candidate loop, evaluates the
    threshold grid with NumPy, and exposes cancellation/progress hooks so the
    UI no longer appears frozen after ticker collection reaches 100%.
    """
    z=pd.DataFrame(rows)
    if z.empty:return pd.DataFrame(),pd.DataFrame(),{}
    z=z[z.get('Mode','').astype(str).eq('Dynamic')].copy() if 'Mode' in z else z.copy()
    features=['DailySetup','FreshSignal','VolumeFlow','NoChase','EntryNorm','QuantNorm','ExitSafety','InstitutionalFlow','RVOLNorm','ADXNorm','VolAccelNorm','FreshTransitionNorm']
    z['EntryNorm']=pd.to_numeric(z['EntryScore'],errors='coerce').fillna(0).clip(0,100)/100.0
    z['QuantNorm']=pd.to_numeric(z['QuantScore'],errors='coerce').fillna(0).clip(0,100)/100.0
    z['ExitSafety']=(100-pd.to_numeric(z['ExitPressureAtSignal'],errors='coerce').fillna(50).clip(0,100))/100.0
    for c in ['DailySetup','FreshSignal','VolumeFlow','NoChase']:z[c]=z[c].astype(bool).astype(float)
    for c in ['InstitutionalFlow','RVOLNorm','ADXNorm','VolAccelNorm','FreshTransitionNorm']:
        if c not in z:z[c]=0.0
        z[c]=pd.to_numeric(z[c],errors='coerce').fillna(0).clip(0,1)
    z['Fold']=pd.to_numeric(z.get('Fold',0),errors='coerce').fillna(0).astype(int)
    z['Hit']=pd.to_numeric(z.get('Hit',0),errors='coerce').fillna(0).astype(float)
    z['MFE']=pd.to_numeric(z.get('MFE',0),errors='coerce').fillna(0).astype(float)
    z['MAE']=pd.to_numeric(z.get('MAE',0),errors='coerce').fillna(0).astype(float)
    rng=np.random.default_rng(seed)
    anchors=[np.array([.10,.13,.14,.02,.09,.07,.07,.12,.10,.06,.06,.04]),np.array([.08,.14,.15,.01,.08,.06,.06,.14,.12,.06,.06,.04]),np.array([.11,.12,.14,.00,.10,.07,.07,.12,.11,.06,.06,.04])]
    alpha=np.array([1.5,2.1,2.2,.45,1.4,1.1,1.1,2.0,1.8,1.0,1.3,1.0])
    candidates=anchors+list(rng.dirichlet(alpha,size=720)); thresholds=np.arange(.48,.84,.025)
    scopes=[('ALL',z)]
    if 'Market' in z:
        us=z[z.Market.astype(str).isin(['NASDAQ','NYSE','US'])].copy()
        if len(us)>=250:scopes.append(('US',us))
        for m,g in z.groupby('Market'):
            if len(g)>=250:scopes.append((str(m),g.copy()))

    # Prepare every usable scope once. The old code re-filtered the same
    # DataFrame for every one of 723 candidate weight vectors.
    contexts=[]
    for scope,g in scopes:
        folds=g['Fold'].to_numpy(int)
        final_mask=folds==4;inner_mask=np.isin(folds,[1,2,3])
        if int(inner_mask.sum())<240 or int(final_mask.sum())<40:continue
        inner=g.loc[inner_mask]
        corr=inner[features].corr().abs().fillna(0)
        pairs=[(i,j,float(corr.loc[i,j])) for ix,i in enumerate(features) for j in features[ix+1:] if float(corr.loc[i,j])>=.85]
        fold_cache=[]
        for vf in (2,3):
            tr_mask=folds<vf;va_mask=folds==vf
            if int(tr_mask.sum())<80 or int(va_mask.sum())<30:continue
            tr=g.loc[tr_mask];va=g.loc[va_mask]
            Xt=tr[features].to_numpy(float); yt=tr['Hit'].to_numpy(float)
            Xv=va[features].to_numpy(float); yv=va['Hit'].to_numpy(float)
            fold_cache.append({
                'Xt':Xt,'yt':yt,'Xv':Xv,'yv':yv,
                'vmfe':va['MFE'].to_numpy(float),'vmae':va['MAE'].to_numpy(float),
                'btr':float(np.mean(yt)) if len(yt) else np.nan,
                'bval':float(np.mean(yv)) if len(yv) else np.nan,
            })
        if len(fold_cache)<2:continue
        final=g.loc[final_mask]
        contexts.append({
            'scope':scope,'pairs':pairs,'folds':fold_cache,
            'Xfinal':final[features].to_numpy(float),'yfinal':final['Hit'].to_numpy(float),
            'base_final':float(final['Hit'].mean()),
        })

    best_rows=[];weight_rows=[];model={'version':APP_VERSION,'created':datetime.now().isoformat(timespec='seconds'),'scopes':{}}
    total_work=max(1,len(contexts)*len(candidates));done=0
    if progress_cb:progress_cb('Preparing Daily OOS candidate search',0.0)
    min_train=max(25,int(min_signals*.6))
    for ctx in contexts:
        scope=ctx['scope'];best=None
        if cancel_check:cancel_check()
        for wi,w in enumerate(candidates,1):
            if cancel_check and (wi==1 or wi%8==0):cancel_check()
            fold_metrics=[];total_signals=0
            for fc in ctx['folds']:
                st=fc['Xt']@w;sv=fc['Xv']@w
                tm=st[:,None]>=thresholds[None,:]
                counts=tm.sum(axis=0).astype(int)
                hit_sums=tm.T@fc['yt']
                hrs=np.divide(hit_sums,counts,out=np.full(len(thresholds),np.nan),where=counts>0)
                lifts=hrs/fc['btr'] if np.isfinite(fc['btr']) and fc['btr']>0 else np.full(len(thresholds),np.nan)
                valid=(counts>=min_train)&np.isfinite(lifts)
                if not valid.any():continue
                masked=np.where(valid,lifts,-np.inf);ti=int(np.argmax(masked));best_th=float(thresholds[ti])
                vm=sv>=best_th;ns=int(vm.sum())
                if ns<15:continue
                hr=float(np.mean(fc['yv'][vm]));lift=hr/fc['bval'] if np.isfinite(fc['bval']) and fc['bval']>0 else np.nan
                if not np.isfinite(lift):continue
                mfe=float(np.mean(fc['vmfe'][vm]));mae=float(np.mean(fc['vmae'][vm]))
                fold_metrics.append((lift,ns,hr,mfe,mae,best_th));total_signals+=ns
            if len(fold_metrics)>=2:
                lifts=np.array([x[0] for x in fold_metrics if np.isfinite(x[0])])
                if len(lifts)>=2:
                    med=float(np.median(lifts));worst=float(np.min(lifts));pos=float(np.mean(lifts>1.0));stability=max(0.0,1.0-float(np.std(lifts)))
                    corr_pen=sum(min(float(w[features.index(i)]),float(w[features.index(j)]))*max(0,c-.85)/.15 for i,j,c in ctx['pairs'])
                    mfe=float(np.mean([x[3] for x in fold_metrics]));mae=float(np.mean([x[4] for x in fold_metrics]));sample=min(1.0,np.sqrt(total_signals/max(min_signals*2,1)))
                    objective=(med-1)*2.2+(worst-1)*.9+(pos-.5)*.5+stability*.12+(mfe+mae)*.12+sample*.06-corr_pen*.35
                    avg_th=float(np.median([x[5] for x in fold_metrics]));rec=(objective,med,worst,pos,total_signals,avg_th,w,stability,corr_pen)
                    if best is None or rec[0]>best[0]:best=rec
            done+=1
            if progress_cb and (wi==len(candidates) or wi%12==0):
                progress_cb(f'{scope} • candidate {wi}/{len(candidates)}',done/total_work)
        if best is None:continue
        objective,med,worst,pos,ns,th,w,stability,corr_pen=best
        score=ctx['Xfinal']@w;mask=score>=th;tn=int(mask.sum());base_test=ctx['base_final']
        thr=float(np.mean(ctx['yfinal'][mask])) if tn else np.nan;tl=thr/base_test if tn and base_test>0 else np.nan
        status='SHADOW ELIGIBLE' if tn>=25 and med>=1.03 and worst>=.98 and np.isfinite(tl) and tl>=1.03 else 'RESEARCH ONLY'
        best_rows.append({'Scope':scope,'Inner validation signals':ns,'Inner median OOS lift':med,'Inner worst OOS lift':worst,'Inner positive folds %':100*pos,'Stability':stability,'Correlation penalty':corr_pen,'Validation selection score':objective,'Shadow threshold':th,'Final Fold4 signals':tn,'Final Fold4 hit rate %':100*thr if np.isfinite(thr) else np.nan,'Final Fold4 baseline %':100*base_test,'Final Fold4 OOS lift':tl,'Status':status})
        weights={name:float(val) for name,val in zip(features,w)}
        model['scopes'][scope]={'weights':weights,'threshold':float(th),'status':status,'inner_median_lift':med,'inner_worst_lift':worst,'stability':stability,'inner_signals':int(ns),'inner_positive_folds_pct':100*pos,'validation_objective':float(objective),'fold4_lift':float(tl) if np.isfinite(tl) else None,'fold4_signals':tn}
        for name,val in weights.items():weight_rows.append({'Scope':scope,'Feature':name,'Learned weight %':100*val,'Shadow threshold':th,'Status':status})
    if progress_cb:progress_cb('Daily OOS candidate search complete',1.0)
    return pd.DataFrame(best_rows),pd.DataFrame(weight_rows),model


def _hourly_optimizer_observations_v613(hourly_feat,ticker,target_pct=.03,horizon_bars=(1,2,4),max_anchor_rows=240):
    """Create causal intraday observations with deterministic memory-bounded sampling.

    V6.3.9.44 keeps the *full requested time span* (default 1y) but samples at
    most ``max_anchor_rows`` evenly-spaced hourly anchor bars per ticker before
    expanding the requested 1h/2h/4h horizons.  The original implementation
    retained every hourly bar as a Python dict; on ALL 151 this could exceed
    Streamlit Community memory before final OOS optimization even started.

    Fold assignment still uses the anchor's original position in the full
    history, so all four chronological OOS folds remain represented.  Sampling
    is deterministic (no random seed / no look-ahead) and reduces highly
    overlapping hourly observations rather than shortening the history window.
    """
    if hourly_feat is None or not isinstance(hourly_feat,pd.DataFrame) or len(hourly_feat)<120:return []
    f=hourly_feat.dropna(subset=['Close','High','Low']).copy()
    if not isinstance(f.index,pd.DatetimeIndex):
        try:f.index=pd.to_datetime(f.index)
        except Exception:return []
    n=len(f);cl=f['Close'].to_numpy(float);hi=f['High'].to_numpy(float);lo=f['Low'].to_numpy(float);out=[]
    horizons=tuple(sorted(set(max(1,int(x)) for x in horizon_bars)))
    max_h=max(horizons) if horizons else 1
    usable=max(0,n-max_h)
    if usable<=0:return []
    cap=max(80,int(max_anchor_rows or 240))
    if usable<=cap:
        anchor_idx=np.arange(usable,dtype=int)
    else:
        # Evenly spread anchors across the entire history so chronological OOS
        # folds remain balanced and the selected window is genuinely preserved.
        anchor_idx=np.unique(np.linspace(0,usable-1,num=cap,dtype=int))
    market=_market_for_ticker_v612(ticker)
    for i in anchor_idx:
        ts=f.index[int(i)];r=f.iloc[int(i)]
        frac=(int(i)+1)/max(n,1);fold=min(4,max(1,int(np.ceil(frac*4))))
        rr=float(r.get('time_adjusted_rvol',r.get('robust_volume_ratio',np.nan)));va=float(r.get('vol_accel',np.nan));adx=float(r.get('adx14',np.nan));ms=float(r.get('macd_hist_slope',np.nan));mh=float(r.get('macd_hist',np.nan));dv=directional_volume_row(r);inst=institutional_flow_row(r)
        vals={
            'HourlyFreshEMA':1.0 if float(r.get('ema9_cross_up',0) or 0)>0 else 0.0,
            'HourlyRVOLNorm':float(np.clip((rr-.8)/1.7,0,1)) if np.isfinite(rr) else 0.0,
            'HourlyBullVolume':float(np.clip(dv.get('bullish',0),0,1)),
            'HourlyVolAccelNorm':float(np.clip((va-.85)/.75,0,1)) if np.isfinite(va) else 0.0,
            'HourlyMACDCross':1.0 if float(r.get('macd_cross_up',0) or 0)>0 else 0.0,
            'HourlyVWAPReclaim':1.0 if float(r.get('vwap_cross_up',0) or 0)>0 else 0.0,
            'HourlyMACDStrength':1.0 if np.isfinite(ms) and ms>0 and np.isfinite(mh) and mh>0 else 0.0,
            'HourlyInstitutionalFlow':float(np.clip(float(inst.get('score',0))/100.0,0,1)),
            'HourlyADXNorm':float(np.clip((adx-15)/30,0,1)) if np.isfinite(adx) else 0.0,
        }
        for hb in horizons:
            if int(i)+hb>=n or not np.isfinite(cl[int(i)]) or cl[int(i)]<=0:continue
            fh=hi[int(i)+1:int(i)+1+hb];fl=lo[int(i)+1:int(i)+1+hb]
            mfe=float(np.nanmax(fh)/cl[int(i)]-1.0);mae=float(np.nanmin(fl)/cl[int(i)]-1.0)
            # Ticker is intentionally omitted: the hourly optimizer never uses
            # it. Removing a repeated string from ~100k rows saves substantial
            # Python-object memory while Market/Fold/Hour retain model semantics.
            out.append({'Market':market,'Fold':fold,'Hour':int(ts.hour),'HorizonBars':hb,'Hit':float(mfe>=float(target_pct)),'MFE':mfe,'MAE':mae,**vals})
    return out


def _hourly_matched_lift_v613(g,mask):
    if g is None or g.empty:return np.nan,0,np.nan,np.nan,np.nan
    m=np.asarray(mask,dtype=bool)
    if len(m)!=len(g) or not m.any():return np.nan,0,np.nan,np.nan,np.nan
    base_by_hour=g.groupby('Hour')['Hit'].mean().to_dict()
    sel=g.loc[m]
    mb=float(np.mean([base_by_hour.get(int(h),np.nan) for h in sel.Hour])) if len(sel) else np.nan
    hr=float(sel.Hit.mean()) if len(sel) else np.nan
    lift=hr/mb if np.isfinite(hr) and np.isfinite(mb) and mb>0 else np.nan
    return lift,len(sel),hr,float(sel.MFE.mean()),float(sel.MAE.mean())


def _hourly_optimizer_v613(rows,min_signals=80,seed=613,cancel_check=None,progress_cb=None,release_input=False):
    """Nested OOS optimizer for intraday timing signals using same-hour baselines.

    V6.3.9.42 preserves the original model rules but caches fold arrays and
    vectorizes the threshold grid. This removes the expensive groupby/DataFrame
    work that previously ran thousands of times after the ticker scan reached
    100%, and adds cooperative cancellation/progress reporting.
    """
    input_count=len(rows) if hasattr(rows,'__len__') else 0
    z=pd.DataFrame.from_records(rows) if isinstance(rows,list) else pd.DataFrame(rows)
    if z.empty:return pd.DataFrame(),pd.DataFrame(),{'scopes':{}}
    if release_input and isinstance(rows,list):
        rows.clear();gc.collect()
    if 'Market' in z.columns:
        z['Market']=z['Market'].astype('category')
    feats=['HourlyFreshEMA','HourlyRVOLNorm','HourlyBullVolume','HourlyVolAccelNorm','HourlyMACDCross','HourlyVWAPReclaim','HourlyMACDStrength','HourlyInstitutionalFlow','HourlyADXNorm']
    for c in feats:z[c]=pd.to_numeric(z.get(c,0),errors='coerce').fillna(0).clip(0,1)
    z['Fold']=pd.to_numeric(z.get('Fold',0),errors='coerce').fillna(0).astype(int)
    z['Hour']=pd.to_numeric(z.get('Hour',0),errors='coerce').fillna(0).astype(int)
    z['HorizonBars']=pd.to_numeric(z.get('HorizonBars',0),errors='coerce').fillna(0).astype(int)
    z['Hit']=pd.to_numeric(z.get('Hit',0),errors='coerce').fillna(0).astype(float)
    z['MFE']=pd.to_numeric(z.get('MFE',0),errors='coerce').fillna(0).astype(float)
    z['MAE']=pd.to_numeric(z.get('MAE',0),errors='coerce').fillna(0).astype(float)
    rng=np.random.default_rng(seed)
    anchors=[np.array([.18,.18,.16,.10,.10,.06,.08,.08,.06]),np.array([.22,.20,.18,.09,.09,.04,.07,.06,.05])]
    alpha=np.array([2.2,2.2,2.0,1.3,1.5,.8,1.1,1.2,1.0]);candidates=anchors+list(rng.dirichlet(alpha,size=360));thresholds=np.arange(.30,.81,.03)
    scope_sets=[('ALL',z)]
    us=z[z.Market.astype(str).isin(['NASDAQ','NYSE','US'])].copy()
    if len(us)>=800:scope_sets.append(('US',us))
    for m,g in z.groupby('Market'):
        if len(g)>=800:scope_sets.append((str(m),g.copy()))

    def matched_base_vector(hours,hits):
        out=np.empty(len(hits),dtype=float)
        for h in np.unique(hours):
            m=hours==h;out[m]=float(np.mean(hits[m])) if m.any() else np.nan
        return out

    contexts=[]
    horizons=sorted(set(int(x) for x in z.HorizonBars.unique()))
    for hb in horizons:
        for scope,base_scope in scope_sets:
            g=base_scope[base_scope.HorizonBars==hb].copy()
            if len(g)<500:continue
            folds=g['Fold'].to_numpy(int);final_mask=folds==4;inner_mask=np.isin(folds,[1,2,3])
            if int(final_mask.sum())<100 or int(inner_mask.sum())<300:continue
            inner=g.loc[inner_mask];corr=inner[feats].corr().abs().fillna(0)
            pairs=[(i,j,float(corr.loc[i,j])) for ix,i in enumerate(feats) for j in feats[ix+1:] if float(corr.loc[i,j])>=.85]
            fold_cache=[]
            for vf in (2,3):
                tr_mask=folds<vf;va_mask=folds==vf
                if int(tr_mask.sum())<150 or int(va_mask.sum())<80:continue
                tr=g.loc[tr_mask];va=g.loc[va_mask]
                thours=tr['Hour'].to_numpy(int);vhours=va['Hour'].to_numpy(int)
                ty=tr['Hit'].to_numpy(float);vy=va['Hit'].to_numpy(float)
                fold_cache.append({
                    'Xt':tr[feats].to_numpy(float),'yt':ty,'tb':matched_base_vector(thours,ty),
                    'tmfe':tr['MFE'].to_numpy(float),'tmae':tr['MAE'].to_numpy(float),
                    'Xv':va[feats].to_numpy(float),'yv':vy,'vb':matched_base_vector(vhours,vy),
                    'vmfe':va['MFE'].to_numpy(float),'vmae':va['MAE'].to_numpy(float),
                })
            if len(fold_cache)<2:continue
            final=g.loc[final_mask];fy=final['Hit'].to_numpy(float);fh=final['Hour'].to_numpy(int)
            contexts.append({'hb':hb,'scope':scope,'pairs':pairs,'folds':fold_cache,'Xfinal':final[feats].to_numpy(float),'yfinal':fy,'bfinal':matched_base_vector(fh,fy),'mfe_final':final['MFE'].to_numpy(float),'mae_final':final['MAE'].to_numpy(float)})

    # Contexts now own only compact NumPy arrays; release the source frame
    # before candidate search to keep peak RAM bounded on Community Cloud.
    del scope_sets
    try:del z
    except Exception:pass
    gc.collect()
    rows_out=[];weights_out=[];model={'scopes':{}}
    total_work=max(1,len(contexts)*len(candidates));done=0
    if progress_cb:progress_cb('Preparing Hourly OOS candidate search',0.0)
    min_train=max(40,int(min_signals*.6))
    for ctx in contexts:
        hb=ctx['hb'];scope=ctx['scope'];best=None
        if cancel_check:cancel_check()
        for wi,w in enumerate(candidates,1):
            if cancel_check and (wi==1 or wi%8==0):cancel_check()
            mets=[];total=0
            for fc in ctx['folds']:
                st=fc['Xt']@w;sv=fc['Xv']@w
                tm=st[:,None]>=thresholds[None,:]
                counts=tm.sum(axis=0).astype(int)
                hit_sums=tm.T@fc['yt'];base_sums=tm.T@fc['tb']
                hrs=np.divide(hit_sums,counts,out=np.full(len(thresholds),np.nan),where=counts>0)
                mbs=np.divide(base_sums,counts,out=np.full(len(thresholds),np.nan),where=counts>0)
                lifts=np.divide(hrs,mbs,out=np.full(len(thresholds),np.nan),where=np.isfinite(mbs)&(mbs>0))
                mfe_sums=tm.T@fc['tmfe'];mae_sums=tm.T@fc['tmae']
                mfes=np.divide(mfe_sums,counts,out=np.zeros(len(thresholds)),where=counts>0)
                maes=np.divide(mae_sums,counts,out=np.zeros(len(thresholds)),where=counts>0)
                objs=(lifts-1)*2.0+np.minimum(counts,300)/3000.0+(mfes+maes)*.08
                valid=(counts>=min_train)&np.isfinite(lifts)
                if not valid.any():continue
                masked=np.where(valid,objs,-np.inf);ti=int(np.argmax(masked));bth=float(thresholds[ti])
                vm=sv>=bth;ns=int(vm.sum())
                if ns<25:continue
                hr=float(np.mean(fc['yv'][vm]));mb=float(np.mean(fc['vb'][vm]));lift=hr/mb if np.isfinite(mb) and mb>0 else np.nan
                if not np.isfinite(lift):continue
                mfe=float(np.mean(fc['vmfe'][vm]));mae=float(np.mean(fc['vmae'][vm]));mets.append((lift,ns,hr,mfe,mae,bth));total+=ns
            if len(mets)>=2:
                lifts=np.array([x[0] for x in mets]);med=float(np.median(lifts));worst=float(np.min(lifts));pos=float(np.mean(lifts>1));stability=max(0,1-float(np.std(lifts)))
                corr_pen=sum(min(float(w[feats.index(i)]),float(w[feats.index(j)]))*max(0,c-.85)/.15 for i,j,c in ctx['pairs'])
                th=float(np.median([x[5] for x in mets]));objective=(med-1)*2.3+(worst-1)*1.0+(pos-.5)*.45+stability*.1+min(total,300)/5000-corr_pen*.3
                rec=(objective,med,worst,pos,total,th,w,stability,corr_pen)
                if best is None or rec[0]>best[0]:best=rec
            done+=1
            if progress_cb and (wi==len(candidates) or wi%12==0):
                progress_cb(f'{scope} • {hb}h • candidate {wi}/{len(candidates)}',done/total_work)
        if best is None:continue
        objective,med,worst,pos,total,th,w,stability,corr_pen=best;score=ctx['Xfinal']@w;mask=score>=th;tn=int(mask.sum())
        if tn:
            thr=float(np.mean(ctx['yfinal'][mask]));mb=float(np.mean(ctx['bfinal'][mask]));tl=thr/mb if np.isfinite(mb) and mb>0 else np.nan
            mfe=float(np.mean(ctx['mfe_final'][mask]));mae=float(np.mean(ctx['mae_final'][mask]))
        else:thr=tl=mfe=mae=np.nan
        status='SHADOW ELIGIBLE' if tn>=35 and med>=1.08 and worst>=1.00 and np.isfinite(tl) and tl>=1.08 else 'RESEARCH ONLY'
        hlabel=f'{hb}h';rows_out.append({'Scope':scope,'Hourly Horizon':hlabel,'Inner signals':total,'Inner median OOS lift':med,'Inner worst OOS lift':worst,'Positive folds %':100*pos,'Stability':stability,'Correlation penalty':corr_pen,'Validation selection score':objective,'Threshold':th,'Fold4 signals':tn,'Fold4 hit rate %':100*thr if np.isfinite(thr) else np.nan,'Fold4 matched OOS lift':tl,'Status':status})
        weights={k:float(v) for k,v in zip(feats,w)};model['scopes'].setdefault(scope,{})[hlabel]={'weights':weights,'threshold':th,'status':status,'inner_median_lift':med,'inner_worst_lift':worst,'stability':stability,'inner_signals':int(total),'inner_positive_folds_pct':100*pos,'validation_objective':float(objective),'fold4_lift':float(tl) if np.isfinite(tl) else None,'fold4_signals':tn}
        for k,v in weights.items():weights_out.append({'Scope':scope,'Hourly Horizon':hlabel,'Feature':k,'Learned weight %':100*v,'Status':status,'Fold4 OOS lift':tl})
    if progress_cb:progress_cb('Hourly OOS candidate search complete',1.0)
    return pd.DataFrame(rows_out),pd.DataFrame(weights_out),model


def _aggregate_entry_validation(rows):
    z=pd.DataFrame(rows)
    if z.empty:return pd.DataFrame(),pd.DataFrame(),pd.DataFrame()
    base=float(z['Hit'].mean()) if len(z) else np.nan
    out=[]
    for mode in ['Static','Dynamic']:
        m=z[z['Mode']==mode]
        for bucket in ['80–100','70–79','60–69','<60']:
            g=m[m['Bucket']==bucket]
            if g.empty:continue
            stock_rates=g.groupby('Ticker')['Hit'].mean()
            out.append({
                'Mode':mode,'Entry Score':bucket,'Signals':len(g),'Hit Rate %':100*float(g['Hit'].mean()),
                'Lift vs baseline':float(g['Hit'].mean()/base) if np.isfinite(base) and base>0 else np.nan,
                'Avg Forward Return %':100*float(g['ForwardReturn'].mean()),
                'Avg MFE %':100*float(g['MFE'].mean()),
                'Avg MAE %':100*float(g['MAE'].mean()),
                'Avg Drawdown %':100*float(g['Drawdown'].mean()),
                'Median Days to Target':float(g.loc[g['Hit']>0,'DaysToTarget'].median()) if (g['Hit']>0).any() else np.nan,
                'Positive stocks %':100*float((stock_rates>base).mean()) if len(stock_rates) and np.isfinite(base) else np.nan,
            })
    summary=pd.DataFrame(out)
    # V6.1.1 daily causal proxy for Entry Trigger V3. Hourly confirmation is
    # validated live/short-horizon separately because provider intraday history is limited.
    gates=[]
    for mode in ['Static','Dynamic']:
        if 'TriggerEligible' in z.columns:g=z[(z.Mode==mode)&(z.TriggerEligible.astype(bool))]
        else:g=z[(z.Mode==mode)&(z.EntryScore>=72)]
        if g.empty:continue
        gates.append({'Mode':mode,'Signals':len(g),'Hit Rate %':100*float(g.Hit.mean()),
                      'Lift vs baseline':float(g.Hit.mean()/base) if np.isfinite(base) and base>0 else np.nan,
                      'Avg Forward Return %':100*float(g.ForwardReturn.mean()),
                      'Avg MFE %':100*float(g.MFE.mean()),
                      'Avg MAE %':100*float(g.MAE.mean()),
                      'Avg Drawdown %':100*float(g.Drawdown.mean()),
                      'Median Days to Target':float(g.loc[g.Hit>0,'DaysToTarget'].median()) if (g.Hit>0).any() else np.nan})
    market_rows=[]
    if 'Market' in z.columns:
        for market in sorted(z['Market'].dropna().astype(str).unique()):
            zm=z[z.Market.astype(str)==market]
            for mode in ['Static','Dynamic']:
                all_m=zm[zm.Mode==mode]
                if all_m.empty:continue
                market_base=float(all_m.Hit.mean())
                g=all_m[all_m.TriggerEligible.astype(bool)] if 'TriggerEligible' in all_m.columns else all_m[all_m.EntryScore>=72]
                if g.empty:continue
                fold_rates=g.groupby('Fold')['Hit'].mean(); positive_folds=int((fold_rates>market_base).sum()) if len(fold_rates) else 0
                market_rows.append({
                    'Market':market,'Mode':mode,'Signals':len(g),'Stocks':int(g.Ticker.nunique()),
                    'Baseline Hit Rate %':100*market_base,'Trigger Hit Rate %':100*float(g.Hit.mean()),
                    'Lift vs market baseline':float(g.Hit.mean()/market_base) if market_base>0 else np.nan,
                    'Avg Forward Return %':100*float(g.ForwardReturn.mean()),'Avg MFE %':100*float(g.MFE.mean()),'Avg MAE %':100*float(g.MAE.mean()),
                    'Positive folds':f"{positive_folds}/{len(fold_rates)}",
                    'Median Days to Target':float(g.loc[g.Hit>0,'DaysToTarget'].median()) if (g.Hit>0).any() else np.nan,
                })
    return summary,pd.DataFrame(gates),pd.DataFrame(market_rows)

def chart_request(timeframe_label, period_label):
    interval_map={"15m":"15m","1H":"1h","1D":"1d","1W":"1wk"}
    period_map={"1D":"1d","1W":"5d","5D":"5d","1M":"1mo","3M":"3mo","6M":"6mo","1Y":"1y","MAX":"max"}
    interval=interval_map[timeframe_label]
    period=period_map[period_label]
    capped=False
    # Short display periods should actually show intraday structure rather than one daily candle.
    if period_label=="1D":
        interval="5m"
    elif period_label in ("1W","5D") and timeframe_label in ("1D","1W"):
        interval="30m"
    # Yahoo intraday history is limited. Cap only the display request, never model calculations.
    if interval=="15m" and period not in ("1d","5d","1mo"):
        period="1mo"; capped=True
    if interval=="30m" and period not in ("1d","5d","1mo"):
        period="1mo"; capped=True
    return interval,period,capped



def _excel_safe_df(obj):
    """Return a copy that Excel/openpyxl can serialize safely.

    Excel does not support timezone-aware datetimes. Intraday 15m/1H
    frames intentionally keep exchange-aware timestamps for calculations,
    so exports must strip only the timezone metadata (preserving the local
    wall-clock time shown to the user). Object columns are handled too
    because mixed audit tables can contain pandas/Python datetime objects.
    """
    if obj is None:
        return pd.DataFrame()
    if not isinstance(obj, pd.DataFrame):
        try:
            obj = pd.DataFrame(obj)
        except Exception:
            return pd.DataFrame()
    out = obj.copy()

    # Index is normally exported with index=False, but sanitize it as well
    # so this helper is safe for future callers.
    try:
        if isinstance(out.index, pd.DatetimeIndex) and out.index.tz is not None:
            out.index = out.index.tz_localize(None)
    except Exception:
        pass

    def _strip_tz_value(v):
        try:
            if isinstance(v, pd.Timestamp):
                return v.tz_localize(None) if v.tzinfo is not None else v
            if isinstance(v, datetime):
                return v.replace(tzinfo=None) if v.tzinfo is not None else v
        except Exception:
            return v
        return v

    for col in out.columns:
        ser = out[col]
        try:
            if isinstance(ser.dtype, pd.DatetimeTZDtype):
                out[col] = ser.dt.tz_localize(None)
                continue
        except Exception:
            pass
        if ser.dtype == 'object':
            # Apply only when at least one tz-aware datetime is present.
            try:
                sample = ser.dropna().head(200)
                has_tz = any(
                    (isinstance(v, pd.Timestamp) and v.tzinfo is not None) or
                    (isinstance(v, datetime) and v.tzinfo is not None)
                    for v in sample
                )
                if has_tz:
                    out[col] = ser.map(_strip_tz_value)
            except Exception:
                pass
    return out

def scanner_excel_bytes(df,scan_meta=None):
    bio=BytesIO()
    out_df=df.copy()
    if 'BacktestN' in out_df:
        _bn=pd.to_numeric(out_df['BacktestN'],errors='coerce').fillna(0)
        out_df['BacktestQuality']=np.select([_bn>=12,_bn>=8,_bn>=6,_bn>0],['EVIDENCE OK','BUILDING EVIDENCE','PROVISIONAL EVIDENCE','LOW SAMPLE'],default='NO SAMPLE')
        # V6.3.9.44: reveal empirical Hit Rate from N=6, but do not call it validated before N=12.
        if 'EmpiricalHitRate' in out_df:out_df.loc[_bn<6,'EmpiricalHitRate']=np.nan
    with pd.ExcelWriter(bio,engine="openpyxl") as writer:
        _excel_safe_df(out_df).to_excel(writer,index=False,sheet_name="Scanner Results")
        exp_cols=[c for c in ["Rank","Ticker","Signal","TradeStage","MovementStage","ExitPressure","ExitStage","VolumeContext","LiveIntradayRVOL","DailyRobustRVOL","TimeAdjustedRVOL","ExplosiveScore","ExplosiveStage","HourlyConfirm","P5_5D","P10_5D","P15_5D","P15_5D_N","EntryScore","Prediction","EvidenceQuality","BacktestQuality"] if c in out_df.columns]
        _excel_safe_df(out_df[exp_cols]).to_excel(writer,index=False,sheet_name="Explosive Move")
        early_cols=[c for c in ['Ticker','Market','LiquidityScore','LiquidityLabel','LiquidityHardGateOK','LiquidityBlockReason','AvgDailyTurnover20','AvgDailyTurnover60','MedianDailyTurnover20','MedianDailyTurnover60','LiquidityTurnoverCurrency','LiquidityMinTurnover','LiquidityStableDaysPct','LiquiditySampleDays','TradeStage','RawEntryTriggerState','EntryActionabilityState','ArmedTimingClass','ArmedTimingReason','SetupConfirmed','PriceActionableNow','RRActionable','ConfirmedEntryGateOK','EntryDistancePct','RetestStatus','LiveRR_T1','LiveRR_T2','Target1ProgressPct','DecisionBoardStage','OpportunityWindow','OpportunityWindowReason','TimingContext','TriggerTimingDisplay','LiveEarlyRadarCandidate','LiveEarlyRadarScore','LiveEarlyRadarReason','RetestQualifiedSetup','BreakoutContinuationActionable','BreakoutContinuationTrigger','BreakoutContinuationVolumeOK','BreakoutContinuationMomentumOK','BreakoutContinuationFlowOK','MoveConsumedBeforeTriggerPct','RecentRunPct','RecentRunATR','RecentRunWindow','RecentRunLabel','PostTriggerConsumedPct','PostTriggerConsumedLabel','RecentRunRetestContext','TimingDataComplete','TimingDataSource','TimingDataReason','ChaseRiskScore','ChaseRiskLabel','SessionMovePct','EntryScore','HourlyConfirm','OpportunityScore','Prediction','EvidenceQuality','EvidenceConfirmationGate','RegularRadarTargetPct','RegularRadarLeadWindow','RegularRadarScore','RegularRadarLiftX','RegularRadarFreshness','RegularRadarMoveConsumedPct','PreMoveConfirmed','PreMoveConfidenceTier','PreMoveFamilyCount','PreMoveFamilySignature','PreMoveBaselineGuardOK','EffectiveVolumeShockRatio','PreMoveShockRecoveryOK','PreMoveFlowConfirmation','PreMoveMomentumConfirmation','PreMovePatternStrength','PreMovePatternDetected','PreMoveActionableNow','PreMoveRadarActionable','PreMovePatternOnly','PreMoveActionabilityState','PreMoveActionabilityReason','PreMoveRadarEligible','PreMoveRadarRank','PreMoveRadarStatus','RegularFunnelStage','RegularFunnelFinalN','RegularFunnelFinalHitRatePct','RegularFunnelFinalBaselinePct','RegularFunnelFinalLiftX'] if c in out_df.columns]
        if early_cols:_excel_safe_df(out_df[early_cols]).to_excel(writer,index=False,sheet_name="Early Entry Snapshot")
        di_cols=[c for c in ['Ticker','Market','Sector','LiquidityScore','LiquidityLabel','LiquidityHardGateOK','LiquidityBlockReason','AvgDailyTurnover20','AvgDailyTurnover60','MedianDailyTurnover20','MedianDailyTurnover60','LiquidityTurnoverCurrency','LiquidityMinTurnover','LiquidityStableDaysPct','LiquiditySampleDays','DecisionBoardStage','DecisionStageLabel','OverallStrengthRank','ActionQueueRank','OriginalSignalTime','OriginalSignalStage','OriginalSignalPrice','OriginalTriggerPrice','OriginalTriggerTime','OriginalTarget1','OriginalProgressToT1Pct','OriginalMoveSinceSignalPct','OriginalSignalId','OriginalMemoryIntegrity','OriginalMemoryStatus','OriginalMemoryAvailable','OriginalTriggerLocked','OriginalEqualsCurrentTrigger','CurrentTriggerPrice','CurrentTriggerTime','CurrentTarget1','CurrentProgressToT1Pct','PreBreakoutAccumulationScore','PreBreakoutAccumulationStage','PreBreakoutAccumulationReason','VolumeRegimeRatio','VolumeShockRatio','VolumeShockDate','VolumeShockReturnPct','AbsorptionCandidate','VolumePersistenceRatio','PriceRetentionSinceVolumeShockPct','PreBreakoutHigherLowCount','PreBreakoutRegimeShift','PreMoveConfirmed','PreMoveConfidenceTier','PreMoveFamilyCount','PreMoveFamilySignature','PreMoveBaselineGuardOK','EffectiveVolumeShockRatio','PreMoveShockRecoveryOK','PreMoveFlowConfirmation','PreMoveMomentumConfirmation','PreMovePatternStrength','PreMoveActionableNow','PreMoveActionabilityState','PreMoveActionabilityReason','PreMoveRadarEligible','PreMoveRadarRank','PreMoveRadarStatus','OpportunityWindow','OpportunityWindowReason','TimingContext','TriggerTimingDisplay','TradePriorityRank','TradePriorityClass','TradePriorityCurrentEligible','TradePriorityBucket','TradePriorityVersion','QualifiedRank','EmergingRank','EmergingFreshnessTier','EvidenceRank','DecisionLane','EmergingSetupEligible','EmergingSetupScore','EmergingSetupReason','DecisionRankScore','DecisionRankCore','DecisionScoreRank','SetupQualityScore','EntryTimingScore','DecisionEvidenceScore','DecisionRiskScore','DecisionRankSetupQuality','DecisionRankEntryTiming','DecisionRankMoneyFlow','DecisionRankEvidence','DecisionRankRRQuality','DecisionRankRiskPenalty','DecisionRankEvidencePenalty','DecisionRankQualificationCap','DecisionRankEligible','ValidatedOpportunityEligible','EvidenceValidated','CurrentOpportunityQualified','CurrentOpportunityQualification','ValidatedOpportunityReason','DecisionRankQualification','EvidenceQualification','EvidenceQualificationReason','EvidenceTradeGrade','EvidenceSampleN','EvidenceLiftX','TimingQualification','TimingDataComplete','TimingDataSource','TimingDataReason','DataFreshnessQualification','DecisionRankModelModifier','DecisionRankDataPenalty','DecisionRankStageModifier','DecisionRankTimingPenalty','DecisionRankChasePenalty','DecisionRankExitPenalty','DecisionRankReason','DecisionRankVersion','LegacyTradePriorityRank','LegacyGlobalRank','TopScore','OpportunityScore','TradeStage','EntryTriggerState','MoneyFlowScore','MoneyFlowLabel','MoneyFlowEvidence','InflowPressure','InflowLabel','OutflowPressure','OutflowLabel','NetFlowBalance','NetFlowScore','NetFlowLabel','FlowPressureEvidence','MarketCycleScore','MarketCycleStage','MarketCycleReason','CatalystScore','CatalystLabel','CatalystEvidence','CatalystTopHeadline','CatalystRecentNewsCount','CatalystEventRisk','CatalystCoverage','EntryScore','LiveActionabilityScore','HourlyConfirm','LiveEarlyRadarCandidate','LiveEarlyRadarScore','LiveEarlyRadarReason','RetestQualifiedSetup','BreakoutContinuationActionable','BreakoutContinuationTrigger','BreakoutContinuationVolumeOK','BreakoutContinuationMomentumOK','BreakoutContinuationFlowOK','MoveConsumedBeforeTriggerPct','RecentRunPct','RecentRunATR','RecentRunWindow','RecentRunLabel','PostTriggerConsumedPct','PostTriggerConsumedLabel','RecentRunRetestContext','RawNoChaseCheck','NoChaseCheck','NoChaseConsistencyOverride','NoChaseReason','ChaseRiskScore','ChaseRiskLabel','LiveRR_T1','LiveRR_T2','SessionDataFresh','SessionFreshnessVerified','SessionCalendarSource','SessionCalendarReason','SessionReconstructed','SessionReconstructionSource','PriceFreshnessStatus','ExitPressure','ExitStage'] if c in out_df.columns]
        if di_cols:_excel_safe_df(out_df[di_cols]).to_excel(writer,index=False,sheet_name="Decision Intelligence")
        valuation_cols=[c for c in ['Ticker','Market','Sector','Price','Currency','ValuationScore','ValuationLabel','EstimatedDiscountPct','FairValueLow','FairValueMid','FairValueHigh','ValuationEvidence','ValuationArchetype','ValuationMetricCount','ValuationPeerCount','ValuationPeerScope','InfoPrice','ValuationPriceMismatch','ValuationPriceMismatchPct','TrailingPE','ForwardPE','PriceToSales','PriceToBook','EVToEBITDA','EVToRevenue','FCFYieldPct','PEGRatio','RevenueGrowth','EarningsGrowth','ReturnOnEquity','ProfitMargins','ValuationMethod'] if c in out_df.columns]
        if valuation_cols:_excel_safe_df(out_df[valuation_cols]).to_excel(writer,index=False,sheet_name="Valuation Research")
        hk=out_df[out_df["Ticker"].astype(str).str.endswith(".HK")].copy() if "Ticker" in out_df else pd.DataFrame()
        _excel_safe_df(hk).to_excel(writer,index=False,sheet_name="Hong Kong Universe")
        sm=scan_meta or {}
        skipped=sm.get('skipped') or []
        _da=sm.get('discovery_audit')
        if isinstance(_da,pd.DataFrame) and not _da.empty:_excel_safe_df(_da).to_excel(writer,index=False,sheet_name='Discovery Audit')
        _fun=sm.get('discovery_funnel') or {}
        meta=pd.DataFrame({"Field":["Version","Generated","Rows in export","Requested","Daily success","Deep success","Skipped/errors","Forecast horizon days","Target %","Scan mode","Universe mode","Universe size","Discovery broad scanned","Discovery Stage-0 selected","Discovery Daily OK","Discovery Deep selected","Discovery Deep OK","Discovery coverage rule"],"Value":[APP_VERSION,datetime.now().strftime("%Y-%m-%d %H:%M:%S"),len(df),sm.get('requested','—'),sm.get('daily_success','—'),sm.get('deep_success','—'),len(skipped),sm.get('forecast_horizon_days','—'),sm.get('target_pct','—'),sm.get('scan_mode','—'),sm.get('universe_mode','—'),sm.get('universe_size','—'),_fun.get('broad_scanned','—'),_fun.get('stage0_selected','—'),_fun.get('daily_ok','—'),_fun.get('deep_selected','—'),_fun.get('deep_ok','—'),(sm.get('discovery') or {}).get('coverage_rule','—')]})
        meta.to_excel(writer,index=False,sheet_name="About")
        if skipped:_excel_safe_df(pd.DataFrame(skipped)).to_excel(writer,index=False,sheet_name="Skipped")
    return bio.getvalue()


def _auto_backtest_threshold(feat,horizon,target_pct):
    rows=[]
    for th in [60,62,64,66,68,70,72,75]:
        b=normalize_backtest_confidence(backtest_signal(feat,int(horizon),float(target_pct),th,0))
        n=int(b.get('n',0) or 0); hr=float(b.get('hit_rate',np.nan)); ar=float(b.get('avg_return',np.nan))
        # Reward evidence first; tiny samples cannot win only because of 100% hit rate.
        evidence=min(1.0,math.sqrt(n/20.0)) if n else 0.0
        quality=(100*hr if np.isfinite(hr) else 0)*evidence + 10*max(-.1,min(.2,ar if np.isfinite(ar) else 0))*evidence + min(15,n/2)
        rows.append({'Threshold':th,'Signals':n,'Observed Hit Rate %':100*hr if n and np.isfinite(hr) else np.nan,'Hit Rate %':100*hr if n>=6 and np.isfinite(hr) else np.nan,'Avg Return %':100*ar if n and np.isfinite(ar) else np.nan,'Evidence':round(100*evidence,1),'Quality':quality})
    tb=pd.DataFrame(rows)
    qualified=tb[tb.Signals>=12]
    pick=int((qualified if not qualified.empty else tb).sort_values(['Quality','Signals'],ascending=False).iloc[0].Threshold)
    return pick,tb


_FEEDBACK_REMOTE_STATE_V630={'attempted_pull':False,'last_pull':None,'last_push':None,'last_error':None}
_FEEDBACK_REMOTE_LOCK_V630=threading.RLock()

def _feedback_db_path_v600():
    # Keep the historic filename so an in-place V6.2.x -> V6.3.0 upgrade reuses
    # every snapshot already present on the current host. V6.3.0 adds portable
    # backup/restore and optional GitHub persistence around this same DB.
    base=Path.home()/'.ai_stock_hunter'
    try:base.mkdir(parents=True,exist_ok=True)
    except Exception:base=Path('/tmp')
    return base/'feedback_v600.sqlite3'

def _feedback_persistence_cfg_v630():
    """Optional durable GitHub store configured only through Streamlit secrets.

    Example .streamlit/secrets.toml:
      [feedback_persistence]
      github_token = "github_pat_..."
      repo = "alonaz1976/ai-stock-hunter-v2"
      branch = "main"
      path = "data/feedback_v630.sqlite3.gz"

    The token is never rendered or exported. Without it the app still supports
    one-click DB download + restore, so the user can keep portable backups.
    """
    try:
        sec=st.secrets.get('feedback_persistence',{})
        token=str(sec.get('github_token','')).strip()
        repo=str(sec.get('repo','alonaz1976/ai-stock-hunter-v2')).strip()
        branch=str(sec.get('branch','main')).strip() or 'main'
        path=str(sec.get('path','data/feedback_v630.sqlite3.gz')).strip() or 'data/feedback_v630.sqlite3.gz'
        enabled=bool(token and repo and '/' in repo and path)
        return {'enabled':enabled,'token':token,'repo':repo,'branch':branch,'path':path}
    except Exception:
        return {'enabled':False,'token':'','repo':'','branch':'main','path':'data/feedback_v630.sqlite3.gz'}

def _feedback_checkpoint_v630():
    try:
        path=_feedback_db_path_v600()
        if not path.exists():return
        con=sqlite3.connect(str(path),timeout=30)
        try:con.execute('PRAGMA wal_checkpoint(FULL)')
        finally:con.close()
    except Exception:pass

def _feedback_db_bytes_v630():
    try:
        _feedback_checkpoint_v630();p=_feedback_db_path_v600()
        return p.read_bytes() if p.exists() else b''
    except Exception:return b''

def _feedback_validate_db_file_v630(path):
    con=None
    try:
        con=sqlite3.connect(str(path),timeout=10)
        ok=con.execute('PRAGMA integrity_check').fetchone()[0]
        tables={r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        return str(ok).lower()=='ok' and 'snapshots' in tables and 'outcomes' in tables
    except Exception:return False
    finally:
        try:
            if con is not None:con.close()
        except Exception:pass

def _feedback_restore_bytes_v630(data, push_remote=False):
    if not data:return False,'Backup file is empty.'
    target=_feedback_db_path_v600();tmp=target.with_suffix('.restore.tmp')
    try:
        tmp.write_bytes(bytes(data))
        if not _feedback_validate_db_file_v630(tmp):
            try:tmp.unlink()
            except Exception:pass
            return False,'The uploaded file is not a valid AI Stock Hunter Feedback database.'
        # Remove stale WAL/SHM before atomically replacing the database.
        for ext in ('-wal','-shm'):
            try:Path(str(target)+ext).unlink()
            except Exception:pass
        os.replace(tmp,target)
        _FEEDBACK_REMOTE_STATE_V630['attempted_pull']=True
        if push_remote:_feedback_schedule_remote_push_v630()
        return True,'Feedback database restored successfully.'
    except Exception as e:
        try:tmp.unlink()
        except Exception:pass
        return False,f'{type(e).__name__}: {e}'

def _feedback_github_request_v630(method,url,token,payload=None):
    headers={'Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28','User-Agent':'AI-Stock-Hunter-V630'}
    if token:headers['Authorization']=f'Bearer {token}'
    body=json.dumps(payload).encode('utf-8') if payload is not None else None
    req=urllib_request.Request(url,data=body,headers=headers,method=method)
    with urllib_request.urlopen(req,timeout=45) as resp:
        raw=resp.read()
        return json.loads(raw.decode('utf-8')) if raw else {}

def _feedback_remote_pull_v630(force=False):
    cfg=_feedback_persistence_cfg_v630()
    if not cfg['enabled']:return False,'GitHub persistence is not configured.'
    with _FEEDBACK_REMOTE_LOCK_V630:
        if _FEEDBACK_REMOTE_STATE_V630['attempted_pull'] and not force:return False,'Already checked this session.'
        _FEEDBACK_REMOTE_STATE_V630['attempted_pull']=True
    qpath=urllib_parse.quote(cfg['path'],safe='/')
    url=f"https://api.github.com/repos/{cfg['repo']}/contents/{qpath}?ref={urllib_parse.quote(cfg['branch'])}"
    try:
        obj=_feedback_github_request_v630('GET',url,cfg['token'])
        raw_content=str(obj.get('content','') or '').replace('\n','')
        if raw_content:
            content=base64.b64decode(raw_content)
        elif obj.get('git_url'):
            blob=_feedback_github_request_v630('GET',str(obj.get('git_url')),cfg['token'])
            content=base64.b64decode(str(blob.get('content','') or '').replace('\n',''))
        elif obj.get('download_url'):
            headers={'Authorization':f"Bearer {cfg['token']}",'User-Agent':'AI-Stock-Hunter-V630'}
            req=urllib_request.Request(str(obj.get('download_url')),headers=headers,method='GET')
            with urllib_request.urlopen(req,timeout=60) as resp:content=resp.read()
        else:
            return False,'Remote Feedback backup has no downloadable content.'
        if str(cfg.get('path','')).lower().endswith('.gz'):
            content=gzip.decompress(content)
        ok,msg=_feedback_restore_bytes_v630(content,push_remote=False)
        if ok:_FEEDBACK_REMOTE_STATE_V630.update({'last_pull':datetime.utcnow().isoformat()+'Z','last_error':None})
        else:_FEEDBACK_REMOTE_STATE_V630['last_error']=msg
        return ok,msg
    except urllib_error.HTTPError as e:
        if e.code==404:return False,'No remote Feedback backup exists yet.'
        msg=f'GitHub pull HTTP {e.code}'
        _FEEDBACK_REMOTE_STATE_V630['last_error']=msg;return False,msg
    except Exception as e:
        msg=f'{type(e).__name__}: {e}';_FEEDBACK_REMOTE_STATE_V630['last_error']=msg;return False,msg

def _feedback_remote_push_v630():
    cfg=_feedback_persistence_cfg_v630()
    if not cfg['enabled']:return False,'GitHub persistence is not configured.'
    data=_feedback_db_bytes_v630()
    if not data:return False,'Feedback database is empty.'
    upload_data=gzip.compress(data,compresslevel=6) if str(cfg.get('path','')).lower().endswith('.gz') else data
    qpath=urllib_parse.quote(cfg['path'],safe='/')
    url=f"https://api.github.com/repos/{cfg['repo']}/contents/{qpath}"
    sha=None
    try:
        cur=_feedback_github_request_v630('GET',url+f"?ref={urllib_parse.quote(cfg['branch'])}",cfg['token']);sha=cur.get('sha')
    except urllib_error.HTTPError as e:
        if e.code!=404:
            msg=f'GitHub lookup HTTP {e.code}';_FEEDBACK_REMOTE_STATE_V630['last_error']=msg;return False,msg
    except Exception as e:
        msg=f'{type(e).__name__}: {e}';_FEEDBACK_REMOTE_STATE_V630['last_error']=msg;return False,msg
    payload={'message':f'Feedback DB sync V{APP_VERSION} {datetime.utcnow().replace(microsecond=0).isoformat()}Z','content':base64.b64encode(upload_data).decode('ascii'),'branch':cfg['branch']}
    if sha:payload['sha']=sha
    try:
        _feedback_github_request_v630('PUT',url,cfg['token'],payload)
        _FEEDBACK_REMOTE_STATE_V630.update({'last_push':datetime.utcnow().isoformat()+'Z','last_error':None});return True,'Remote Feedback backup updated.'
    except Exception as e:
        msg=f'{type(e).__name__}: {e}';_FEEDBACK_REMOTE_STATE_V630['last_error']=msg;return False,msg

def _feedback_schedule_remote_push_v630():
    if not _feedback_persistence_cfg_v630().get('enabled'):return
    def run():
        try:_feedback_remote_push_v630()
        except Exception:pass
    threading.Thread(target=run,daemon=True,name='feedback-persistence-v630').start()

def _feedback_auto_restore_v630():
    path=_feedback_db_path_v600()
    if path.exists() and path.stat().st_size>0:
        _FEEDBACK_REMOTE_STATE_V630['attempted_pull']=True;return
    if _feedback_persistence_cfg_v630().get('enabled'):
        _feedback_remote_pull_v630(force=False)

def _feedback_conn_v600():
    _feedback_auto_restore_v630()
    con=sqlite3.connect(str(_feedback_db_path_v600()),timeout=30)
    con.execute('PRAGMA journal_mode=WAL')
    con.execute('PRAGMA busy_timeout=30000')
    con.execute("""CREATE TABLE IF NOT EXISTS snapshots(
        id INTEGER PRIMARY KEY AUTOINCREMENT, scan_id TEXT, ts_utc TEXT, ticker TEXT, market TEXT, price REAL,
        top_score REAL, opportunity REAL, trade_stage TEXT, movement_stage TEXT, prediction REAL, move_score REAL,
        explosive REAL, entry_score REAL, hourly REAL, exit_pressure REAL, global_rank INTEGER, market_rank INTEGER,
        session_status TEXT, entry_low REAL, entry_high REAL, trigger REAL, invalidation REAL, target1 REAL, target2 REAL,
        horizon_days INTEGER, UNIQUE(scan_id,ticker))""")
    con.execute("""CREATE TABLE IF NOT EXISTS outcomes(
        snapshot_id INTEGER, horizon INTEGER, evaluated_at TEXT, end_return REAL, max_favorable REAL, max_adverse REAL,
        target1_hit INTEGER, target2_hit INTEGER, invalidation_hit INTEGER, first_event TEXT,
        PRIMARY KEY(snapshot_id,horizon))""")
    con.execute("""CREATE TABLE IF NOT EXISTS replay_runs(
        run_id TEXT PRIMARY KEY, created_at TEXT, scope TEXT, history TEXT, target_pct REAL, horizon_days INTEGER,
        sample_every INTEGER, requested_tickers INTEGER, successful_tickers INTEGER, event_rows INTEGER, clean_rows INTEGER)""")
    con.execute("""CREATE TABLE IF NOT EXISTS replay_events(
        id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT, ticker TEXT, market TEXT, signal_date TEXT, price REAL,
        quant_score REAL, early_score REAL, entry_score REAL, atr_pct REAL, target1 REAL, invalidation REAL,
        end_return REAL, max_favorable REAL, max_adverse REAL, first_event TEXT, clean_outcome TEXT, indicators TEXT, candidate INTEGER,
        UNIQUE(run_id,ticker,signal_date))""")
    con.execute("""CREATE TABLE IF NOT EXISTS replay_combinations(
        run_id TEXT, combination TEXT, combo_size INTEGER, families TEXT, discovery_rank INTEGER, discovery_score REAL,
        discovery_n INTEGER, discovery_wins INTEGER, discovery_success REAL, discovery_baseline REAL, discovery_lift REAL, discovery_delta REAL, discovery_stocks INTEGER,
        validation_n INTEGER, validation_wins INTEGER, validation_success REAL, validation_baseline REAL, validation_lift REAL, validation_delta REAL, validation_stocks INTEGER,
        positive_folds INTEGER, usable_folds INTEGER, stability_gap REAL, research_tier TEXT, oos_status TEXT,
        PRIMARY KEY(run_id,combination))""")
    con.execute("""CREATE TABLE IF NOT EXISTS replay_combo_folds(
        run_id TEXT, combination TEXT, fold INTEGER, resolved INTEGER, wins INTEGER, success_rate REAL, baseline_rate REAL, lift REAL, delta_pp REAL, stocks INTEGER,
        PRIMARY KEY(run_id,combination,fold))""")
    con.execute("""CREATE TABLE IF NOT EXISTS replay_consensus_combos(
        run_id TEXT, market TEXT, combination TEXT, families TEXT, discovery_n INTEGER, discovery_success REAL, discovery_lift REAL,
        selector_n INTEGER, selector_success REAL, selector_lift REAL, final_n INTEGER, final_success REAL, final_lift REAL, status TEXT,
        PRIMARY KEY(run_id,market,combination))""")
    con.execute("""CREATE TABLE IF NOT EXISTS replay_consensus_gates(
        run_id TEXT, market TEXT, gate TEXT, resolved INTEGER, wins INTEGER, success_rate REAL, baseline_rate REAL, lift REAL, delta_pp REAL, expectancy_r REAL, meaning TEXT,
        PRIMARY KEY(run_id,market,gate))""")
    con.execute("""CREATE TABLE IF NOT EXISTS regular_signature_cache(
        market TEXT PRIMARY KEY, saved_epoch REAL, completed_label TEXT, version TEXT, config_json TEXT, radar_json TEXT)""")
    con.execute("""CREATE TABLE IF NOT EXISTS signal_memory(
        ticker TEXT PRIMARY KEY, market TEXT, original_signal_ts TEXT, original_signal_stage TEXT, original_signal_price REAL,
        original_trigger_price REAL, original_trigger_time TEXT, original_target1 REAL, original_invalidation REAL,
        source TEXT, active INTEGER, updated_ts TEXT, signal_id TEXT, trigger_locked_ts TEXT)""")
    con.execute("""CREATE TABLE IF NOT EXISTS valuation_cache(
        ticker TEXT PRIMARY KEY, fetched_at REAL, payload_json TEXT)""")
    con.execute("""CREATE TABLE IF NOT EXISTS catalyst_cache(
        ticker TEXT PRIMARY KEY, fetched_at REAL, payload_json TEXT)""")
    # V6.3.9.60: durable last-completed Scanner snapshot. The single-row cache
    # lives inside the same portable Feedback DB, so it survives Streamlit restarts
    # and is included in the existing backup / optional GitHub persistence flow.
    con.execute("""CREATE TABLE IF NOT EXISTS scanner_last_completed(
        cache_key TEXT PRIMARY KEY, finished_at REAL, completed_label TEXT, app_version TEXT,
        payload_blob BLOB, updated_ts TEXT)""")
    # V6.3.9.57 signal-memory integrity migration.
    _sm_existing={r[1] for r in con.execute('PRAGMA table_info(signal_memory)').fetchall()}
    for _col,_typ in [('signal_id','TEXT'),('trigger_locked_ts','TEXT')]:
        if _col not in _sm_existing:
            try:con.execute(f'ALTER TABLE signal_memory ADD COLUMN {_col} {_typ}')
            except Exception:pass
    # V6.1.1 migration: persist live gate evidence so Feedback can learn which
    # confirmations are adding lift in the CURRENT market. Existing DBs are upgraded in place.
    existing={r[1] for r in con.execute('PRAGMA table_info(snapshots)').fetchall()}
    for col,typ in [('entry_state','TEXT'),('confirmation_pct','REAL'),('daily_setup','INTEGER'),('fresh_signal','INTEGER'),('hourly_entry','INTEGER'),('volume_flow','INTEGER'),('no_chase','INTEGER'),('extension_guard','INTEGER'),('chase_risk_score','REAL'),('chase_risk_label','TEXT'),('session_move_pct','REAL'),('since_trigger_pct','REAL'),('volume_trend','TEXT'),('trigger_anchor_price','REAL'),('market_regime','TEXT'),('market_regime_ok','INTEGER'),('optimized_stage','TEXT'),('optimized_score','REAL'),('optimized_match','REAL'),('optimized_model_status','TEXT'),('optimized_model_id','TEXT'),('optimized_model_scope','TEXT'),('optimized_model_horizon','REAL'),('optimized_oos_lift','REAL'),('optimized_hourly_match','REAL'),('optimized_hourly_horizon','TEXT'),('model_disagreement','TEXT'),('scan_mode','TEXT'),('pre_move_stage','TEXT'),('pre_move_score','REAL'),('pre_move_probability','REAL'),('pre_move_families','TEXT'),('pre_move_features','TEXT'),('pre_move_best_lift','REAL'),('pre_move_freshness','TEXT'),('regular_target_pct','REAL'),('regular_lead_window','TEXT'),('regular_timeframe','TEXT'),('regular_score','REAL'),('regular_hit_rate','REAL'),('regular_baseline','REAL'),('regular_lift','REAL'),('regular_signature','TEXT'),('regular_setup_score','REAL'),('regular_freshness','TEXT'),('regular_funnel_stage','TEXT'),('regular_funnel_final_n','REAL'),('regular_funnel_final_hit_rate','REAL'),('regular_funnel_final_baseline','REAL'),('regular_funnel_final_lift','REAL'),('regular_live_layer','TEXT'),('raw_entry_state','TEXT'),('entry_action_state','TEXT'),('setup_confirmed','INTEGER'),('price_actionable','INTEGER'),('rr_actionable','INTEGER'),('confirmed_entry_gate','INTEGER'),('entry_distance_pct','REAL'),('actionability_missing','TEXT'),('evidence_confirmation_gate','TEXT'),('armed_timing_class','TEXT'),('armed_timing_reason','TEXT'),('move_consumed_before_trigger','REAL'),('target1_progress_pct','REAL'),('live_rr_t1','REAL'),('live_rr_t2','REAL'),('regular_move_consumed_pct','REAL'),('snapshot_source','TEXT'),('app_version','TEXT'),('target_pct','REAL'),('valuation_score','REAL'),('valuation_label','TEXT'),('valuation_discount_pct','REAL'),('valuation_fair_low','REAL'),('valuation_fair_high','REAL'),('valuation_evidence','TEXT'),('valuation_archetype','TEXT'),('valuation_metric_count','REAL'),('valuation_peer_count','REAL'),('valuation_currency','TEXT'),('valuation_method','TEXT'),('money_flow_score','REAL'),('money_flow_label','TEXT'),('money_flow_evidence','TEXT'),('inflow_pressure','REAL'),('inflow_label','TEXT'),('outflow_pressure','REAL'),('outflow_label','TEXT'),('net_flow_balance','REAL'),('net_flow_score','REAL'),('net_flow_label','TEXT'),('flow_pressure_evidence','TEXT'),('market_cycle_score','REAL'),('market_cycle_stage','TEXT'),('market_cycle_reason','TEXT'),('catalyst_score','REAL'),('catalyst_label','TEXT'),('catalyst_evidence','TEXT'),('catalyst_headline','TEXT'),('catalyst_event_risk','TEXT'),('decision_rank_score','REAL'),('decision_rank_core','REAL'),('decision_rank_reason','TEXT'),('decision_rank_version','TEXT'),('legacy_global_rank','REAL'),('legacy_trade_priority_rank','REAL'),('event_id','TEXT'),('event_role','TEXT'),('event_origin_snapshot_id','INTEGER'),('event_origin_ts_utc','TEXT'),('independent_event','INTEGER'),('plan_geometry_valid','INTEGER'),('plan_geometry_reason','TEXT'),('trade_learning_eligible','INTEGER'),('setup_origin_time','TEXT'),('trigger_anchor_time','TEXT'),('decision_board_stage','TEXT'),('original_signal_time','TEXT'),('original_signal_stage','TEXT'),('original_signal_price','REAL'),('original_trigger_price','REAL'),('original_trigger_time','TEXT'),('original_target1','REAL'),('original_invalidation','REAL'),('original_progress_t1_pct','REAL'),('original_move_since_signal_pct','REAL'),('original_signal_memory_source','TEXT'),('pre_breakout_accumulation_score','REAL'),('pre_breakout_accumulation_stage','TEXT'),('pre_breakout_accumulation_reason','TEXT'),('pre_move_confirmed','INTEGER'),('pre_move_confidence_tier','TEXT'),('pre_move_family_count','REAL'),('pre_move_family_signature','TEXT'),('pre_move_baseline_guard','INTEGER'),('effective_volume_shock_ratio','REAL'),('pre_move_shock_recovery','INTEGER'),('pre_move_flow_confirmation','INTEGER'),('pre_move_momentum_confirmation','INTEGER'),('pre_move_baseline_turnover','REAL'),('volume_regime_ratio','REAL'),('volume_shock_ratio','REAL'),('volume_shock_date','TEXT'),('volume_shock_return_pct','REAL'),('absorption_candidate','INTEGER'),('volume_persistence_ratio','REAL'),('price_retention_since_volume_shock_pct','REAL'),('pre_breakout_higher_low_count','REAL'),('pre_breakout_regime_shift','INTEGER'),('original_signal_id','TEXT'),('original_memory_integrity','TEXT'),('original_trigger_locked','INTEGER'),('current_trigger_price','REAL'),('current_trigger_time','TEXT'),('current_target1','REAL'),('current_progress_t1_pct','REAL'),('original_equals_current_trigger','INTEGER'),('pre_move_pattern_strength','TEXT'),('pre_move_actionable_now','INTEGER'),('pre_move_actionability_state','TEXT'),('pre_move_actionability_reason','TEXT'),('session_calendar_source','TEXT'),('session_calendar_reason','TEXT'),('session_freshness_verified','INTEGER'),('decision_display_stage','TEXT'),('effective_decision_stage','TEXT'),('recommendation_type','TEXT'),('recommendation_text','TEXT'),('entry_path','TEXT'),('continuation_entry_state','TEXT'),('retest_status','TEXT'),('pre_move_radar_status','TEXT')]:
        if col not in existing:
            try:con.execute(f'ALTER TABLE snapshots ADD COLUMN {col} {typ}')
            except Exception:pass
    replay_existing={r[1] for r in con.execute('PRAGMA table_info(replay_events)').fetchall()}
    replay_cols=[
        ('candidate','INTEGER'),('legacy_candidate','INTEGER'),('candidate_v2','INTEGER'),('high_confidence','INTEGER'),
        ('family_signature','TEXT'),('family_count','INTEGER'),('freshness_state','TEXT'),('move_consumed_pct','REAL'),
        ('extension_atr','REAL'),('distribution_risk','INTEGER'),('setup_score_v2','REAL'),('meta_probability','REAL'),
        ('meta_sample','INTEGER'),('meta_lift','REAL'),('r_multiple','REAL'),('recent_2d_return','REAL'),
        ('core_momentum','INTEGER'),('core_volume_flow','INTEGER'),('candidate_rule_version','TEXT'),
        ('combo_phase','TEXT'),('combo_candidate_v3','INTEGER'),('combo_high_confidence_v3','INTEGER'),('combo_70_research','INTEGER'),
        ('combo_match_count','INTEGER'),('combo_best_signature','TEXT'),('combo_best_discovery_rate','REAL'),('combo_best_discovery_lift','REAL'),
        ('consensus_phase_v634','TEXT'),('consensus_match_count_v634','INTEGER'),('consensus_family_count_v634','INTEGER'),('consensus_candidate_v634','INTEGER')
    ]
    for col,typ in replay_cols:
        if col not in replay_existing:
            try:con.execute(f'ALTER TABLE replay_events ADD COLUMN {col} {typ}')
            except Exception:pass
    try:
        con.execute("UPDATE snapshots SET app_version='LEGACY ≤6.3.9.23' WHERE app_version IS NULL OR TRIM(app_version)=''")
    except Exception:pass
    con.commit()
    return con


def _scan_snapshot_persist_v63960(snapshot):
    """Persist only the most recent *successful* Scanner result in the Feedback DB."""
    if not isinstance(snapshot,dict) or snapshot.get('status')!='completed':
        return False
    result=snapshot.get('result')
    if not isinstance(result,pd.DataFrame):
        return False
    con=None
    try:
        try:
            payload=gzip.compress(pickle.dumps(snapshot,protocol=pickle.HIGHEST_PROTOCOL),compresslevel=6)
        except Exception:
            # Optimizer/model objects are not required to *display* the saved scan.
            # Drop any exotic non-picklable config members rather than losing the cache.
            slim=dict(snapshot);cfg=dict(slim.get('config') or {})
            cfg.pop('optimizer_model',None);slim['config']=cfg
            payload=gzip.compress(pickle.dumps(slim,protocol=pickle.HIGHEST_PROTOCOL),compresslevel=6)
        con=_feedback_conn_v600()
        con.execute("INSERT OR REPLACE INTO scanner_last_completed(cache_key,finished_at,completed_label,app_version,payload_blob,updated_ts) VALUES(?,?,?,?,?,?)",
                    ('LAST',float(snapshot.get('finished_at',time_module.time()) or time_module.time()),str(snapshot.get('completed_label','') or ''),APP_VERSION,sqlite3.Binary(payload),datetime.utcnow().replace(microsecond=0).isoformat()+'Z'))
        con.commit();con.close();con=None
        _feedback_schedule_remote_push_v630()
        return True
    except Exception:
        try:
            if con is not None:con.close()
        except Exception:pass
        return False

def _scan_snapshot_load_v63960():
    """Restore the last successful Scanner result after app/server restart."""
    con=None
    try:
        con=_feedback_conn_v600()
        row=con.execute("SELECT payload_blob FROM scanner_last_completed WHERE cache_key='LAST'").fetchone()
        con.close();con=None
        if not row or row[0] is None:return None
        snap=pickle.loads(gzip.decompress(bytes(row[0])))
        if not isinstance(snap,dict) or snap.get('status')!='completed':return None
        if not isinstance(snap.get('result'),pd.DataFrame):return None
        snap['restored_from_persistent_cache']=True
        return snap
    except Exception:
        try:
            if con is not None:con.close()
        except Exception:pass
        return None


# -----------------------------------------------------------------------------
# V6.3.9.3 research-only Valuation / Undervaluation Overlay
# -----------------------------------------------------------------------------
_VALUATION_TTL_SECONDS_V6393=6*3600
_VALUATION_FETCH_WORKERS_V6393=10


def _valuation_num_v6393(v):
    try:
        x=float(v)
        return x if np.isfinite(x) else np.nan
    except Exception:
        return np.nan


def _valuation_cache_get_v6393(ticker,max_age=_VALUATION_TTL_SECONDS_V6393):
    con=None
    try:
        con=_feedback_conn_v600();row=con.execute('SELECT fetched_at,payload_json FROM valuation_cache WHERE ticker=?',(str(ticker).upper(),)).fetchone()
        if not row:return None
        age=time_module.time()-float(row[0] or 0)
        if age>float(max_age):return None
        payload=json.loads(row[1] or '{}');payload['_cache_age_seconds']=age
        return payload
    except Exception:return None
    finally:
        try:
            if con is not None:con.close()
        except Exception:pass


def _valuation_cache_set_v6393(ticker,payload):
    con=None
    try:
        con=_feedback_conn_v600();con.execute('INSERT OR REPLACE INTO valuation_cache(ticker,fetched_at,payload_json) VALUES(?,?,?)',(str(ticker).upper(),time_module.time(),json.dumps(payload,ensure_ascii=False,default=str)));con.commit()
    except Exception:pass
    finally:
        try:
            if con is not None:con.close()
        except Exception:pass


def _valuation_fetch_raw_v6393(ticker):
    """Best-effort fundamentals snapshot. Research only; failures never block Scanner."""
    t=str(ticker).upper().strip();cached=_valuation_cache_get_v6393(t)
    if cached is not None:return cached
    payload={'Ticker':t,'FundamentalsStatus':'NO DATA','FundamentalsError':'','FetchedAtUTC':datetime.utcnow().replace(microsecond=0).isoformat()+'Z'}
    try:
        info=yf.Ticker(t).get_info() or {}
        price=_valuation_num_v6393(info.get('currentPrice',info.get('regularMarketPrice',info.get('previousClose'))))
        mcap=_valuation_num_v6393(info.get('marketCap'))
        fcf=_valuation_num_v6393(info.get('freeCashflow'))
        payload.update({
            'FundamentalsStatus':'OK' if info else 'NO DATA','Currency':str(info.get('currency','') or ''),'FundamentalSector':str(info.get('sector','') or ''),'Industry':str(info.get('industry','') or ''),
            'InfoPrice':price,'MarketCap':mcap,'TrailingPE':_valuation_num_v6393(info.get('trailingPE')),'ForwardPE':_valuation_num_v6393(info.get('forwardPE')),
            'PriceToSales':_valuation_num_v6393(info.get('priceToSalesTrailing12Months')),'PriceToBook':_valuation_num_v6393(info.get('priceToBook')),
            'EVToEBITDA':_valuation_num_v6393(info.get('enterpriseToEbitda')),'EVToRevenue':_valuation_num_v6393(info.get('enterpriseToRevenue')),
            'PEGRatio':_valuation_num_v6393(info.get('pegRatio',info.get('trailingPegRatio'))),'RevenueGrowth':_valuation_num_v6393(info.get('revenueGrowth')),
            'EarningsGrowth':_valuation_num_v6393(info.get('earningsGrowth')),'ReturnOnEquity':_valuation_num_v6393(info.get('returnOnEquity')),
            'ProfitMargins':_valuation_num_v6393(info.get('profitMargins')),'FreeCashflow':fcf,
            'FCFYieldPct':(100.0*fcf/mcap) if np.isfinite(fcf) and np.isfinite(mcap) and mcap>0 else np.nan,
        })
    except Exception as e:
        payload['FundamentalsError']=f'{type(e).__name__}: {e}'[:300]
    _valuation_cache_set_v6393(t,payload)
    return payload


def _valuation_archetype_v6393(r):
    sector=str(r.get('FundamentalSector',r.get('Sector','')) or '').lower();industry=str(r.get('Industry','') or '').lower()
    pe=_valuation_num_v6393(r.get('TrailingPE'));rev_g=_valuation_num_v6393(r.get('RevenueGrowth'))
    if 'financial' in sector or any(k in industry for k in ('bank','insurance','credit services','capital markets')):return 'FINANCIAL'
    if 'real estate' in sector or 'reit' in industry:return 'REAL ESTATE PROXY'
    if (not np.isfinite(pe) or pe<=0) and np.isfinite(rev_g) and rev_g>0:return 'GROWTH / NON-PROFITABLE'
    return 'PROFITABLE / GENERAL'


def _valuation_metric_weights_v6393(archetype):
    if archetype=='FINANCIAL':return {'PriceToBook':.40,'ForwardPE':.25,'TrailingPE':.20,'PriceToSales':.15}
    if archetype=='REAL ESTATE PROXY':return {'PriceToBook':.30,'PriceToSales':.20,'ForwardPE':.15,'FCFYieldPct':.35}
    if archetype=='GROWTH / NON-PROFITABLE':return {'PriceToSales':.30,'EVToRevenue':.25,'ForwardPE':.15,'PEGRatio':.15,'FCFYieldPct':.15}
    return {'ForwardPE':.25,'TrailingPE':.20,'EVToEBITDA':.20,'FCFYieldPct':.15,'PriceToSales':.10,'PriceToBook':.10}


def _valuation_peer_series_v6393(df,row_idx,metric):
    """V6.3.9.30 hierarchical comparable selection.

    Prefer true Industry peers, then FundamentalSector, then the app Sector, and
    only broaden to market/universe when the narrower peer group is too small.
    """
    r=df.loc[row_idx];market=str(r.get('Market',''));app_sector=str(r.get('Sector',''))
    fund_sector=str(r.get('FundamentalSector','') or '').strip();industry=str(r.get('Industry','') or '').strip()
    vals=pd.to_numeric(df.get(metric,pd.Series(np.nan,index=df.index)),errors='coerce')
    good=vals.where(vals>0)
    same_market=df.get('Market',pd.Series('',index=df.index)).astype(str).eq(market)
    scopes=[]
    if industry:
        same_industry=df.get('Industry',pd.Series('',index=df.index)).fillna('').astype(str).str.strip().str.casefold().eq(industry.casefold())
        scopes.append(('MARKET + INDUSTRY',same_market & same_industry))
    if fund_sector:
        same_fsector=df.get('FundamentalSector',pd.Series('',index=df.index)).fillna('').astype(str).str.strip().str.casefold().eq(fund_sector.casefold())
        scopes.append(('MARKET + FUNDAMENTAL SECTOR',same_market & same_fsector))
    if app_sector:
        same_app_sector=df.get('Sector',pd.Series('',index=df.index)).fillna('').astype(str).eq(app_sector)
        scopes.append(('MARKET + APP SECTOR',same_market & same_app_sector))
    scopes.extend([('MARKET',same_market),('SCAN UNIVERSE',pd.Series(True,index=df.index))])
    peers=pd.Series(dtype=float);peer_scope='SCAN UNIVERSE'
    for scope,mask in scopes:
        peers=good[mask].dropna();peer_scope=scope
        if len(peers)>=5:break
    return peers,peer_scope


def _valuation_enrich_scan_v6393(df,progress_callback=None):
    """Attach a peer-relative valuation overlay without changing any trading score."""
    if df is None or not isinstance(df,pd.DataFrame) or df.empty:return df
    z=df.copy();tickers=z['Ticker'].astype(str).str.upper().tolist() if 'Ticker' in z else []
    raw={};total=len(tickers)
    if total:
        from concurrent.futures import as_completed
        with ThreadPoolExecutor(max_workers=min(_VALUATION_FETCH_WORKERS_V6393,max(1,total)),thread_name_prefix='valuation') as ex:
            fut={ex.submit(_valuation_fetch_raw_v6393,t):t for t in tickers}
            done=0
            for f in as_completed(fut):
                t=fut[f]
                try:raw[t]=f.result()
                except Exception as e:raw[t]={'Ticker':t,'FundamentalsStatus':'NO DATA','FundamentalsError':f'{type(e).__name__}: {e}'}
                done+=1
                if progress_callback:
                    try:progress_callback(done,total,t)
                    except Exception:pass
    fundamentals=pd.DataFrame([raw.get(t,{'Ticker':t,'FundamentalsStatus':'NO DATA'}) for t in tickers])
    if fundamentals.empty:return z
    # Prevent duplicate columns if a cached/legacy payload already contains valuation fields.
    z=z.drop(columns=[c for c in fundamentals.columns if c!='Ticker' and c in z.columns],errors='ignore').merge(fundamentals,on='Ticker',how='left')
    z['ValuationArchetype']=z.apply(_valuation_archetype_v6393,axis=1)
    out=[]
    for idx,r in z.iterrows():
        price=_valuation_num_v6393(r.get('Price')); info_price=_valuation_num_v6393(r.get('InfoPrice'));weights=_valuation_metric_weights_v6393(str(r.get('ValuationArchetype')))
        # V6.3.9.30: fundamentals sometimes arrive on an unadjusted/split scale.
        # If the market price and fundamentals provider price materially disagree,
        # suppress valuation rather than manufacturing a false discount/premium.
        price_mismatch=False;price_mismatch_pct=np.nan
        if np.isfinite(price) and price>0 and np.isfinite(info_price) and info_price>0:
            price_mismatch_pct=100.0*abs(info_price/price-1.0)
            price_mismatch=bool(price_mismatch_pct>35.0)
        comps=[];peer_counts=[];scopes=[]
        for metric,w in weights.items():
            v=_valuation_num_v6393(r.get(metric))
            if not np.isfinite(v) or v<=0:continue
            peers,scope=_valuation_peer_series_v6393(z,idx,metric)
            # Exclude the current row when there are enough peers; leave it in tiny universes to avoid zero evidence.
            try:
                peers=peers.drop(index=idx,errors='ignore')
            except Exception:pass
            if len(peers)<4:continue
            med=float(peers.median())
            if not np.isfinite(med) or med<=0:continue
            # Lower multiple = cheaper. Higher FCF yield = cheaper.
            mult=(v/med) if metric=='FCFYieldPct' else (med/v)
            mult=float(np.clip(mult,.50,1.80))
            comps.append((metric,float(w),mult));peer_counts.append(int(len(peers)));scopes.append(scope)
        if price_mismatch:
            fair_mid=fair_low=fair_high=discount=score=np.nan;min_peers=min(peer_counts) if peer_counts else 0;metric_n=len(comps);evidence='BLOCKED';label='PRICE/FUNDAMENTALS MISMATCH'
            method=f'Valuation suppressed • scan price {price:.4f} vs fundamentals price {info_price:.4f} ({price_mismatch_pct:.1f}% mismatch)'
        elif np.isfinite(price) and price>0 and len(comps)>=2:
            wsum=sum(w for _,w,_ in comps);wm=sum(w*m for _,w,m in comps)/max(wsum,1e-9)
            multipliers=np.array([m for _,_,m in comps],dtype=float)
            fair_mid=price*wm
            q25=price*float(np.quantile(multipliers,.25));q75=price*float(np.quantile(multipliers,.75))
            # Guarantee Low <= Mid <= High even when the weighted midpoint lies
            # outside the unweighted interquartile multiplier range.
            fair_low=min(q25,fair_mid);fair_high=max(q75,fair_mid)
            discount=100.0*(fair_mid/price-1.0);score=float(np.clip(50.0+1.5*discount,0,100))
            min_peers=min(peer_counts) if peer_counts else 0;metric_n=len(comps)
            evidence='HIGH' if metric_n>=4 and min_peers>=8 else ('MEDIUM' if metric_n>=3 and min_peers>=5 else 'LOW')
            label='DEEPLY UNDERVALUED' if discount>=25 else ('UNDERVALUED' if discount>=10 else ('FAIR / NEAR PEERS' if discount>-10 else ('PREMIUM' if discount>-25 else 'EXPENSIVE VS PEERS')))
            method=f"Peer-relative {r.get('ValuationArchetype','GENERAL')} multiples • {', '.join(dict.fromkeys(scopes))}"
        else:
            fair_mid=fair_low=fair_high=discount=score=np.nan;min_peers=min(peer_counts) if peer_counts else 0;metric_n=len(comps);evidence='NO DATA' if metric_n<2 else 'LOW';label='INSUFFICIENT DATA';method='Peer-relative multiples • insufficient comparable fundamentals'
        out.append({'ValuationScore':score,'ValuationLabel':label,'EstimatedDiscountPct':discount,'FairValueMid':fair_mid,'FairValueLow':fair_low,'FairValueHigh':fair_high,'ValuationEvidence':evidence,'ValuationMetricCount':metric_n,'ValuationPeerCount':min_peers,'ValuationPeerScope':' / '.join(dict.fromkeys(scopes)) if scopes else '—','ValuationMethod':method,'ValuationResearchOnly':True,'ValuationPriceMismatch':bool(price_mismatch),'ValuationPriceMismatchPct':price_mismatch_pct})
    od=pd.DataFrame(out,index=z.index)
    for c in od.columns:z[c]=od[c]
    return z



# -----------------------------------------------------------------------------
# V6.3.9.4 Decision Intelligence Overlay (retained in V6.3.9.5)
# Money Flow + Market Cycle are derived from already-computed live evidence.
# Catalyst is a cached, best-effort Yahoo news/calendar research layer for the
# highest-priority candidates. None of these fields changes ranking or Entry.
# -----------------------------------------------------------------------------
_CATALYST_TTL_SECONDS_V6394=45*60
_CATALYST_FETCH_WORKERS_V6394=6
_CATALYST_TOP_N_V6394=12


def _num_v6394(v,default=np.nan):
    try:
        x=float(v);return x if np.isfinite(x) else default
    except Exception:return default


def _money_flow_fields_v6394(r):
    """Transparent 0..100 direction-aware money-flow composite.

    This deliberately does not reward high volume by itself. Relative volume
    only helps when bullish price/flow evidence is stronger than bearish
    distribution evidence; it hurts when the opposite is true.
    """
    inst=_num_v6394(r.get('InstitutionalFlowScore'),50.0)
    bull=_num_v6394(r.get('BullishVolumeEvidence'),np.nan)
    bear=_num_v6394(r.get('BearishVolumeEvidence'),np.nan)
    rvol=_num_v6394(r.get('LiveIntradayRVOL',r.get('TimeAdjustedRVOL',r.get('DailyRobustRVOL'))),np.nan)
    accel=_num_v6394(r.get('VolumeAccel'),np.nan)
    exit_p=_num_v6394(r.get('ExitPressure'),50.0)
    if not np.isfinite(bull):bull=50.0
    if not np.isfinite(bear):bear=50.0
    direction=float(np.clip(50.0+0.62*(bull-bear),0,100))
    sign=1.0 if bull>bear+5 else (-1.0 if bear>bull+5 else 0.0)
    volume_support=50.0
    if np.isfinite(rvol):
        volume_support += sign*min(28.0,max(0.0,(rvol-0.85)*20.0))
    if np.isfinite(accel):
        volume_support += sign*min(12.0,max(0.0,(accel-1.0)*20.0))
    volume_support=float(np.clip(volume_support,0,100))
    exit_safety=float(np.clip(100.0-exit_p,0,100))
    score=float(np.clip(.50*inst+.25*direction+.15*volume_support+.10*exit_safety,0,100))
    if score>=72 and bull>bear:label='STRONG INFLOW'
    elif score>=58 and bull>=bear:label='INFLOW / ACCUMULATION'
    elif score<=35 and bear>bull:label='STRONG OUTFLOW'
    elif score<=45 and bear>bull:label='OUTFLOW / DISTRIBUTION'
    else:label='MIXED / NEUTRAL'
    evidence=f"Inst {inst:.0f} • Bull {bull:.0f} • Bear {bear:.0f}"+(f" • RVOL {rvol:.2f}x" if np.isfinite(rvol) else '')
    return round(score,1),label,evidence


def _market_cycle_fields_v6394(r,money_score=None):
    """Classify the setup into a causal market-cycle stage.

    The stage is descriptive/research-only. CycleScore is long-entry
    favorability, not a maturity percentage; EXTENDED therefore scores lower
    than EARLY BREAKOUT even though it is later in the cycle.
    """
    money=_num_v6394(money_score,_num_v6394(r.get('MoneyFlowScore'),50.0))
    exit_p=_num_v6394(r.get('ExitPressure'),0.0)
    chase=_num_v6394(r.get('ChaseRiskScore'),0.0)
    consumed=_num_v6394(r.get('MoveConsumedBeforeTriggerPct'),np.nan)
    move=_num_v6394(r.get('MoveScore'),0.0)
    explosive=_num_v6394(r.get('ExplosiveScore'),0.0)
    fresh=bool(r.get('FreshSignalCheck',False))
    stage=str(r.get('EntryTriggerState',r.get('TradeStage','WAIT')) or 'WAIT')
    volctx=str(r.get('VolumeContext','') or '').upper()
    bull=_num_v6394(r.get('BullishVolumeEvidence'),50.0);bear=_num_v6394(r.get('BearishVolumeEvidence'),50.0)
    if exit_p>=55 and (bear>bull or 'EXIT' in str(r.get('ExitStage','')).upper()):
        cyc='DISTRIBUTION';base=16;reason=f'Exit pressure {exit_p:.0f} with bearish flow'
    elif chase>=45 or (np.isfinite(consumed) and consumed>=72) or stage in ('EXTENDED — DO NOT CHASE','TOO LATE / CHASE'):
        cyc='EXTENDED';base=34;reason=f'Extension/chase risk {chase:.0f}'+(f' • {consumed:.0f}% move consumed' if np.isfinite(consumed) else '')
    elif fresh and stage in ('WATCH','ARMED','CONFIRMED ENTRY') and money>=52 and chase<35 and (not np.isfinite(consumed) or consumed<=55):
        cyc='EARLY BREAKOUT';base=84;reason='Fresh transition + constructive flow before material extension'
    elif max(move,explosive)>=62 and money>=54 and exit_p<45:
        cyc='EXPANSION';base=72;reason=f'Momentum expansion {max(move,explosive):.0f} with flow {money:.0f}'
    elif money>=57 and ('ACCUMULATION' in volctx or bull>=bear+8) and max(move,explosive)<68:
        cyc='ACCUMULATION';base=63;reason='Positive flow building before full momentum expansion'
    else:
        cyc='NEUTRAL / BASE';base=48;reason='No clean accumulation, breakout, extension or distribution regime'
    score=float(np.clip(base+.16*(money-50)-.12*max(0,exit_p-35),0,100))
    return round(score,1),cyc,reason


def _flow_pressure_fields_v63922(r):
    """Independent buy/sell pressure scores plus directional balance.

    Inflow and Outflow are not complements: both may be high during a genuine
    high-volume battle. NetFlowBalance answers which side is dominant. Ranking
    V3.5 keeps using the existing single MoneyFlowScore family, so the new
    diagnostics do not introduce a hidden ranking-weight change.
    """
    inst=_num_v6394(r.get('InstitutionalFlowScore'),50.0)
    bull=_num_v6394(r.get('BullishVolumeEvidence'),50.0)
    bear=_num_v6394(r.get('BearishVolumeEvidence'),50.0)
    exit_p=_num_v6394(r.get('ExitPressure'),0.0)
    rvol=_num_v6394(r.get('LiveIntradayRVOL',r.get('TimeAdjustedRVOL',r.get('DailyRobustRVOL'))),np.nan)
    accel=_num_v6394(r.get('VolumeAccel'),np.nan)
    move=_num_v6394(r.get('SessionMovePct',r.get('RegularSessionMovePct')),np.nan)
    vwap_atr=_num_v6394(r.get('VWAPDistanceATR'),np.nan)
    rvol_mag=0.0 if not np.isfinite(rvol) else float(np.clip((rvol-0.80)/1.70*100.0,0,100))
    accel_mag=0.0 if not np.isfinite(accel) else float(np.clip((accel-1.0)/1.25*100.0,0,100))
    pos_price=50.0;neg_price=50.0
    if np.isfinite(move):
        pos_price=float(np.clip(50.0+10.0*move,0,100));neg_price=float(np.clip(50.0-10.0*move,0,100))
    if np.isfinite(vwap_atr):
        pos_price=float(np.clip(pos_price+18.0*vwap_atr,0,100));neg_price=float(np.clip(neg_price-18.0*vwap_atr,0,100))
    inflow=float(np.clip(.42*bull+.23*inst+.15*rvol_mag*(bull/100.0)+.10*accel_mag*(bull/100.0)+.10*pos_price,0,100))
    outflow=float(np.clip(.40*bear+.25*exit_p+.15*(100.0-inst)+.10*rvol_mag*(bear/100.0)+.10*neg_price,0,100))
    balance=float(np.clip(inflow-outflow,-100,100));balance_score=float(np.clip(50.0+balance/2.0,0,100))
    return {'InflowPressure':round(inflow,1),'InflowLabel':_inflow_label_v63922(inflow),'OutflowPressure':round(outflow,1),'OutflowLabel':_outflow_label_v63921(outflow),'NetFlowBalance':round(balance,1),'NetFlowScore':round(balance_score,1),'NetFlowLabel':_net_flow_label_v63922(balance),'FlowPressureEvidence':f"Bull {bull:.0f} • Bear {bear:.0f} • Inst {inst:.0f} • Exit {exit_p:.0f}"+(f" • RVOL {rvol:.2f}x" if np.isfinite(rvol) else '')}


def _decision_intelligence_enrich_v6394(df):
    if df is None or not isinstance(df,pd.DataFrame) or df.empty:return df
    z=df.copy();vals=[]
    for _,r in z.iterrows():
        mf,mfl,mfe=_money_flow_fields_v6394(r);cs,cst,csr=_market_cycle_fields_v6394(r,mf);flow=_flow_pressure_fields_v63922(r)
        vals.append({'MoneyFlowScore':mf,'MoneyFlowLabel':mfl,'MoneyFlowEvidence':mfe,**flow,'MarketCycleScore':cs,'MarketCycleStage':cst,'MarketCycleReason':csr,'DecisionIntelligenceResearchOnly':True})
    od=pd.DataFrame(vals,index=z.index)
    for c in od.columns:z[c]=od[c]
    return z


def _catalyst_cache_get_v6394(ticker,max_age=_CATALYST_TTL_SECONDS_V6394):
    con=None
    try:
        con=_feedback_conn_v600();row=con.execute('SELECT fetched_at,payload_json FROM catalyst_cache WHERE ticker=?',(str(ticker).upper(),)).fetchone()
        if not row:return None
        age=time_module.time()-float(row[0] or 0)
        if age>float(max_age):return None
        payload=json.loads(row[1] or '{}');payload['_cache_age_seconds']=age;return payload
    except Exception:return None
    finally:
        try:
            if con is not None:con.close()
        except Exception:pass


def _catalyst_cache_set_v6394(ticker,payload):
    con=None
    try:
        con=_feedback_conn_v600();con.execute('INSERT OR REPLACE INTO catalyst_cache(ticker,fetched_at,payload_json) VALUES(?,?,?)',(str(ticker).upper(),time_module.time(),json.dumps(payload,ensure_ascii=False,default=str)));con.commit()
    except Exception:pass
    finally:
        try:
            if con is not None:con.close()
        except Exception:pass


def _news_item_fields_v6394(item):
    d=item if isinstance(item,dict) else {};content=d.get('content') if isinstance(d.get('content'),dict) else d
    title=str(content.get('title') or d.get('title') or '').strip()
    summary=str(content.get('summary') or content.get('description') or d.get('summary') or '').strip()
    raw_time=content.get('pubDate',d.get('providerPublishTime',d.get('published_at')))
    dt=None
    try:
        if isinstance(raw_time,(int,float,np.integer,np.floating)):dt=datetime.fromtimestamp(float(raw_time),tz=timezone.utc)
        elif raw_time:
            ts=pd.to_datetime(raw_time,utc=True,errors='coerce');dt=None if pd.isna(ts) else ts.to_pydatetime()
    except Exception:dt=None
    return title,summary,dt


def _earnings_risk_v6394(calendar_obj):
    vals=[]
    try:
        if isinstance(calendar_obj,dict):
            vals=calendar_obj.get('Earnings Date',calendar_obj.get('EarningsDate',[]))
        elif isinstance(calendar_obj,pd.DataFrame) and not calendar_obj.empty:
            if 'Earnings Date' in calendar_obj.index:vals=calendar_obj.loc['Earnings Date'].tolist()
            elif 'Earnings Date' in calendar_obj.columns:vals=calendar_obj['Earnings Date'].tolist()
        if not isinstance(vals,(list,tuple,pd.Series,np.ndarray)):vals=[vals]
        now=pd.Timestamp.now(tz='UTC')
        days=[]
        for v in vals:
            ts=pd.to_datetime(v,utc=True,errors='coerce')
            if not pd.isna(ts):
                d=(ts-now).total_seconds()/86400.0
                if d>=-0.5:days.append(d)
        if not days:return 'NONE KNOWN'
        d=min(days)
        if d<=3:return f'EARNINGS ≤3D ({d:.1f}d)'
        if d<=14:return f'EARNINGS ≤14D ({d:.1f}d)'
        return f'EARNINGS {d:.0f}D'
    except Exception:return 'UNKNOWN'


def _catalyst_fetch_raw_v6394(ticker):
    """Recent-news catalyst heuristic. Research only, never a trading gate."""
    t=str(ticker).upper().strip();cached=_catalyst_cache_get_v6394(t)
    if cached is not None:return cached
    payload={'Ticker':t,'CatalystScore':np.nan,'CatalystLabel':'NO DATA','CatalystEvidence':'NO DATA','CatalystTopHeadline':'','CatalystRecentNewsCount':0,'CatalystEventRisk':'UNKNOWN','CatalystMethod':'Recent Yahoo headlines keyword/recency heuristic • research only','CatalystError':''}
    positive=('beats','beat estimates','raises guidance','raised guidance','upgrade','upgraded','approval','approved','contract','partnership','partners with','launches','launch','buyback','record revenue','record sales','wins','award','expands','expansion','strong demand','positive trial','fda approves','clearance')
    negative=('misses','missed estimates','cuts guidance','lowers guidance','downgrade','downgraded','investigation','lawsuit','recall','delay','delayed','rejection','rejected','offering','dilution','dilutive','weak demand','warning','fraud','probe','complete response letter','crl')
    try:
        tk=yf.Ticker(t)
        try:news=tk.news or []
        except Exception:news=[]
        try:cal=tk.calendar
        except Exception:cal=None
        now=datetime.now(timezone.utc);rows=[]
        for it in list(news)[:20]:
            title,summary,dt=_news_item_fields_v6394(it)
            if not title:continue
            age_days=((now-dt).total_seconds()/86400.0) if dt is not None else np.nan
            if np.isfinite(age_days) and (age_days<-.25 or age_days>7.0):continue
            text=(title+' '+summary).lower()
            pc=sum(1 for k in positive if k in text);nc=sum(1 for k in negative if k in text)
            weight=1.0 if not np.isfinite(age_days) else (1.0 if age_days<=1 else .75 if age_days<=3 else .45)
            rows.append((title,pc,nc,weight,age_days))
        event_risk=_earnings_risk_v6394(cal)
        if rows:
            delta=sum(10.0*w*(pc-nc) for _,pc,nc,w,_ in rows)
            score=float(np.clip(50.0+delta,0,100));pos=sum(pc for _,pc,_,_,_ in rows);neg=sum(nc for _,_,nc,_,_ in rows)
            if score>=68 and pos>neg:label='POSITIVE CATALYST'
            elif score>=58 and pos>neg:label='POSITIVE BIAS'
            elif score<=32 and neg>pos:label='NEGATIVE CATALYST'
            elif score<=42 and neg>pos:label='NEGATIVE BIAS'
            elif pos and neg:label='MIXED CATALYSTS'
            else:label='NEUTRAL / NO CLEAR CATALYST'
            n=len(rows);evidence='HIGH' if n>=5 else ('MEDIUM' if n>=2 else 'LOW')
            payload.update({'CatalystScore':round(score,1),'CatalystLabel':label,'CatalystEvidence':evidence,'CatalystTopHeadline':rows[0][0][:220],'CatalystRecentNewsCount':n,'CatalystEventRisk':event_risk})
        else:
            payload['CatalystEventRisk']=event_risk
    except Exception as e:payload['CatalystError']=f'{type(e).__name__}: {e}'[:300]
    _catalyst_cache_set_v6394(t,payload);return payload


def _catalyst_enrich_top_v6394(df,top_n=_CATALYST_TOP_N_V6394,progress_callback=None):
    if df is None or not isinstance(df,pd.DataFrame) or df.empty:return df
    z=df.copy();z['CatalystCoverage']=f'TOP {int(top_n)} RESEARCH ONLY'
    if 'TradePriorityRank' in z.columns:
        chosen=z.sort_values(['TradePriorityRank','TopScore'],ascending=[True,False]).head(int(top_n))['Ticker'].astype(str).str.upper().tolist()
    else:chosen=z.sort_values('TopScore',ascending=False).head(int(top_n))['Ticker'].astype(str).str.upper().tolist()
    raw={}
    if chosen:
        from concurrent.futures import as_completed
        with ThreadPoolExecutor(max_workers=min(_CATALYST_FETCH_WORKERS_V6394,len(chosen)),thread_name_prefix='catalyst') as ex:
            fut={ex.submit(_catalyst_fetch_raw_v6394,t):t for t in chosen};done=0
            for f in as_completed(fut):
                t=fut[f]
                try:raw[t]=f.result()
                except Exception as e:raw[t]={'Ticker':t,'CatalystScore':np.nan,'CatalystLabel':'NO DATA','CatalystEvidence':'NO DATA','CatalystError':str(e)}
                done+=1
                if progress_callback:
                    try:progress_callback(done,len(chosen),t)
                    except Exception:pass
    if raw:
        od=pd.DataFrame(list(raw.values())).drop_duplicates('Ticker',keep='first')
        z['Ticker']=z['Ticker'].astype(str).str.upper();z=z.drop(columns=[c for c in od.columns if c!='Ticker' and c in z.columns],errors='ignore').merge(od,on='Ticker',how='left')
    for c,default in [('CatalystLabel','NOT FETCHED'),('CatalystEvidence','NO DATA'),('CatalystTopHeadline',''),('CatalystEventRisk','UNKNOWN'),('CatalystMethod','Top-candidate recent-news research overlay')]:
        if c not in z:z[c]=default
        else:z[c]=z[c].fillna(default)
    if 'CatalystRecentNewsCount' not in z:z['CatalystRecentNewsCount']=0
    return z


def _synchronize_recommended_action_v63931(row):
    """Make RecommendedAction obey the final Decision lane/qualification.

    Entry remains the raw timing engine. This final presentation guard prevents a
    positive-looking ARMED/CONFIRMED action from contradicting RESEARCH/BLOCKED or
    a failed CurrentOpportunityQualified gate. The raw Entry recommendation is kept
    separately as RawRecommendedAction for audit.
    """
    raw=str(row.get('RawRecommendedAction',row.get('RecommendedAction','')) or '').strip()
    lane=str(row.get('DecisionLane','RESEARCH / BLOCKED') or 'RESEARCH / BLOCKED').upper()
    stage=str(row.get('TradeStage',row.get('EntryTriggerState','WAIT')) or 'WAIT').upper()
    timing=str(row.get('TimingQualification','') or '').upper()
    data=str(row.get('DataFreshnessQualification','') or '').upper()
    qual=str(row.get('CurrentOpportunityQualification','') or '').strip()
    _cur=row.get('CurrentOpportunityQualified',False);_val=row.get('ValidatedOpportunityEligible',False)
    try:current=False if pd.isna(_cur) else bool(_cur)
    except Exception:current=bool(_cur)
    try:validated=False if pd.isna(_val) else bool(_val)
    except Exception:validated=bool(_val)

    # Preserve explicit safety/late states from the Entry engine and make the block
    # impossible to misread as an invitation to enter now.
    if not bool(row.get('LiquidityHardGateOK',True)):
        return 'LIQUIDITY BLOCK — RESEARCH ONLY / NO ENTRY'
    if 'TIMING DATA INCOMPLETE' in timing:
        return 'TIMING DATA INCOMPLETE — NOT QUALIFIED FOR ENTRY'
    if ('TOO LATE' in timing) or ('RETEST ONLY' in timing) or ('DO NOT CHASE' in raw.upper()):
        base='TOO LATE / CHASE' if 'TOO LATE' in timing else 'RETEST ONLY / LATE'
        return base+' — NOT QUALIFIED FOR ENTRY'
    if ('STALE' in data) or ('DATA QUALITY' in data and 'CURRENT SESSION' not in data):
        return 'DATA BLOCK — NOT QUALIFIED FOR ENTRY'
    if stage=='INVALIDATED':
        return 'INVALIDATED — NO ENTRY'

    if validated and current and lane=='VALIDATED OPPORTUNITY':
        return raw or (stage+' — CURRENT OPPORTUNITY QUALIFIED')

    # A strong live setup may remain ARMED as a *setup* state, but never as a trade
    # recommendation when the final current-opportunity gate failed.
    armed_like=(stage in ('ARMED','CONFIRMED ENTRY')) or any(x in raw.upper() for x in ('ARMED','CONFIRMED ENTRY','ENTRY CONDITIONS CONFIRMED'))
    if lane=='EMERGING SETUP':
        base='SETUP ARMED' if armed_like else 'WATCH SETUP'
        return base+' — RESEARCH ONLY / LOW-SAMPLE EVIDENCE'
    if not current:
        base='SETUP ARMED — NOT QUALIFIED FOR ENTRY' if armed_like else 'NOT QUALIFIED FOR ENTRY'
        detail=qual.replace('CURRENT WAIT —','').strip(' •-')
        return base+(f' • {detail}' if detail else '')
    if lane.startswith('EVIDENCE VALIDATED'):
        return 'WATCH — EVIDENCE VALIDATED, ENTRY NOT QUALIFIED'
    if lane=='RESEARCH / BLOCKED':
        return 'RESEARCH / BLOCKED — NOT QUALIFIED FOR ENTRY'
    return raw or stage


# -----------------------------------------------------------------------------
# V6.3.9.44 Decision Ranking Engine V3.13 — evidence maturity + 1y history cleanup
#
# V2 was transparent, but some information could still enter the final rank more
# than once (Entry/Hourly through Opportunity/TOP and again directly; Market Cycle
# also reused Money Flow, momentum and late/exit inputs).  V3 keeps all legacy
# research columns for audit/backward compatibility, but final Scanner rank uses
# five independent positive families exactly once:
#   35% Setup/Momentum + 25% Entry Timing + 15% Money Flow
#   + 15% Evidence/Reliability + 10% R:R
# Then ONE combined Late/Chase/Exit risk penalty is applied.  Market Cycle,
# Catalyst, Valuation, TOP and Opportunity stay visible as research/legacy context
# and do not add a second weight. Hourly remains visible as a timing diagnostic;
# its effect is already represented inside the Entry engine and is not weighted
# again. Production Entry gates, trade-plan geometry and Actionable Now are unchanged.
# -----------------------------------------------------------------------------



def _wire_timing_completeness_v63937(df):
    """Wire causal timing completeness onto the FINAL scanner/analyze stage.

    V6.3.9.36 calculated timing completeness inside the Entry engine, but downstream
    stage/evidence normalization can still leave a final ARMED/TRIGGERED row with no
    measurable MoveConsumedBeforeTriggerPct.  This dataframe-level guard runs before
    Decision Ranking so the final stage, E#/Q# eligibility and Excel export all use
    the same timing state.  WAIT/WATCH rows are not blocked merely for lacking a
    causal trigger event.
    """
    if df is None or not isinstance(df,pd.DataFrame) or df.empty:
        return df
    z=df.copy()

    def _f(v):
        try:
            x=float(v);return x if np.isfinite(x) else np.nan
        except Exception:return np.nan

    for idx,r in z.iterrows():
        stage=str(r.get('TradeStage',r.get('EntryTriggerState','WAIT')) or 'WAIT').upper().strip()
        requires=(stage in ('ARMED','CONFIRMED ENTRY') or 'TRIGGERED' in stage)
        consumed=_f(r.get('MoveConsumedBeforeTriggerPct',np.nan))
        source=str(r.get('TimingDataSource','') or '').strip()
        reason=str(r.get('TimingDataReason','') or '').strip()

        anchor=_f(r.get('TriggerAnchorPrice',np.nan))
        origin=_f(r.get('SetupOriginPrice',np.nan))
        current=_f(r.get('Price',np.nan))
        anchor_quality=str(r.get('TriggerAnchorQuality','NONE') or 'NONE').upper().strip()
        anchor_present=bool(np.isfinite(anchor) or anchor_quality not in ('','NONE','NO DATA','NAN'))

        # Last-chance dataframe fallback.  It is deliberately causal and accepted
        # only for a monotonic long setup leg: origin <= trigger <= current.
        if requires and not np.isfinite(consumed):
            if (np.isfinite(origin) and origin>0 and np.isfinite(anchor) and anchor>=origin and
                    np.isfinite(current) and current>=anchor and current>origin):
                total=(current/origin-1.0)*100.0
                before=(anchor/origin-1.0)*100.0
                if np.isfinite(total) and total>0 and np.isfinite(before):
                    consumed=float(np.clip(100.0*max(0.0,before)/total,0.0,100.0))
                    z.at[idx,'MoveConsumedBeforeTriggerPct']=consumed
                    z.at[idx,'TimingDataComplete']=True
                    z.at[idx,'TimingDataSource']='FINAL_STAGE_CAUSAL_FALLBACK'
                    z.at[idx,'TimingDataReason']='Recovered before Decision Ranking from setup origin -> trigger anchor / setup origin -> current move'
                    if consumed<45:label='EARLY'
                    elif consumed<70:label='MID'
                    elif consumed<80:label='AGING'
                    elif consumed<100:label='RETEST ONLY / LATE'
                    else:label='TOO LATE / MOVE CONSUMED'
                    z.at[idx,'TriggerEfficiencyLabel']=label
                    z.at[idx,'TimingConsumedHardBlock']=bool(consumed>=80.0)
                    continue

        if requires and not np.isfinite(consumed):
            # Strict final-stage rule: an ARMED/TRIGGERED row without measurable
            # consumed timing is incomplete even if an upstream default said True.
            z.at[idx,'TimingDataComplete']=False
            z.at[idx,'TimingDataSource']='UNAVAILABLE'
            z.at[idx,'TimingDataReason']=(
                'Final '+stage+' stage has no measurable MoveConsumedBeforeTriggerPct; '
                + ('causal trigger anchor exists but fallback failed' if anchor_present else 'causal trigger anchor/origin data is insufficient for fallback')
            )
            if 'TimingConsumedHardBlock' not in z.columns or pd.isna(z.at[idx,'TimingConsumedHardBlock']):
                z.at[idx,'TimingConsumedHardBlock']=False
            if 'TriggerEfficiencyLabel' not in z.columns or not str(z.at[idx,'TriggerEfficiencyLabel'] or '').strip():
                z.at[idx,'TriggerEfficiencyLabel']='NO DATA'
        else:
            if 'TimingDataComplete' not in z.columns or pd.isna(z.at[idx,'TimingDataComplete']):
                z.at[idx,'TimingDataComplete']=True
            if not source:
                z.at[idx,'TimingDataSource']='SESSION_MOVE' if np.isfinite(consumed) else 'NOT REQUIRED'
            if not reason:
                z.at[idx,'TimingDataReason']='Measured move-consumed timing' if np.isfinite(consumed) else 'Timing completeness not required for current stage'
            if np.isfinite(consumed):
                z.at[idx,'TimingConsumedHardBlock']=bool(consumed>=80.0)

        # V6.3.9.50 final-stage coherence: a late/incomplete causal timing guard can
        # never coexist with ConfirmedEntryGateOK/ActionableNow=True. This closes the
        # RAVD-style contradiction found in the V6.3.9.49 live scan.
        _hard=bool(np.isfinite(consumed) and consumed>=80.0)
        _complete=bool(z.at[idx,'TimingDataComplete']) if 'TimingDataComplete' in z.columns and pd.notna(z.at[idx,'TimingDataComplete']) else True
        if _hard or (requires and not _complete):
            for _c in ('ConfirmedEntryGateOK','ActionableNow','PriceActionableNow'):
                if _c in z.columns:z.at[idx,_c]=False
            if _hard:
                if 'ActionabilityMissing' in z.columns:
                    _old=str(z.at[idx,'ActionabilityMissing'] or '')
                    _msg=f'Trigger timing hard block — {consumed:.0f}% of move occurred before causal trigger'
                    z.at[idx,'ActionabilityMissing']=(_old+' • '+_msg).strip(' •') if _old and _old!='None' else _msg
                for _c in ('TradeStage','EntryTriggerState'):
                    if _c in z.columns and str(z.at[idx,_c] or '').upper()=='CONFIRMED ENTRY':z.at[idx,_c]='RETEST ONLY / LATE'
    return z

def _apply_decision_ranking_v63919(df,scan_mode='Production 151'):
    """Ranking V3.13: V3.11 semantics plus consistent TimingDataSource/Reason audit wording.

    Positive information is still counted once. Evidence, lateness and freshness
    now also act as *qualification guards*. V3.4 additionally separates historical
    Evidence validation from whether the stock is a strong current opportunity, so a
    low-Setup WAIT name cannot become Q#1 merely because its Evidence is trade-grade.
    """
    if df is None or not isinstance(df,pd.DataFrame) or df.empty:return df
    z=_wire_timing_completeness_v63937(df.copy())
    if 'LegacyGlobalRank' not in z.columns and 'GlobalRank' in z.columns:z['LegacyGlobalRank']=z['GlobalRank']
    if 'LegacyTradePriorityRank' not in z.columns and 'TradePriorityRank' in z.columns:z['LegacyTradePriorityRank']=z['TradePriorityRank']

    def n(r,key,default=50.0):
        try:
            v=float(r.get(key,np.nan));return float(np.clip(v,0,100)) if np.isfinite(v) else float(default)
        except Exception:return float(default)

    def rr_quality(r):
        try:v=float(r.get('LiveRR_T1',np.nan))
        except Exception:v=np.nan
        if not np.isfinite(v):return 45.0
        return float(np.clip((v-0.80)/(3.00-0.80)*100.0,0,100))

    def accel_quality(r):
        try:a1=float(r.get('Accel1D',0) or 0)
        except Exception:a1=0.0
        try:a2=float(r.get('Accel2D',0) or 0)
        except Exception:a2=0.0
        return _clip100(50.0+2.0*a1+1.5*a2)

    def consumed_value(r):
        try:v=float(r.get('MoveConsumedBeforeTriggerPct',np.nan))
        except Exception:v=np.nan
        return v if np.isfinite(v) else np.nan

    def consumed_risk(r):
        v=consumed_value(r)
        if not np.isfinite(v):return 0.0
        return float(np.clip((v-35.0)/65.0*100.0,0,100))

    def evidence_qualification(r,evidence):
        p=_evidence_profile_v63916(r)
        state=str(p.get('EvidenceState','UNPROVEN'))
        ok=bool(p.get('EvidenceGuardOK',True))
        n=int(p.get('EvidenceSampleN',0) or 0)
        lift=p.get('EvidenceLiftX',np.nan)
        # Rank caps are qualification controls, not a second evidence weight.
        # Reliability remains the single 15% positive family in the core score.
        # V3.5: Evidence qualification is a gate, not an extra score penalty/cap.
        # Evidence already contributes exactly once as the 15% Reliability family.
        # The legacy cap value is retained only as audit context for older exports.
        if ok:
            return state,0.0,100.0,True,p
        return state,0.0,42.0,False,p

    def timing_qualification(r,late,chase,exit_risk):
        consumed=consumed_value(r)
        retest_ok=bool(r.get('RetestActionable',False)) or (
            bool(r.get('ContinuationBaseCandidate',False)) and bool(r.get('EntryZoneCheck',False))
        )
        extension_ok=bool(r.get('ExtensionGuardCheck',True)) and not bool(r.get('CarryoverHardVeto',False))
        status='FRESH / QUALIFIED';cap=100.0;eligible=True

        # V6.3.9.39 timing semantics: a missing move-consumed value is not the same
        # thing as a fresh timing signal when the current stage does not require it.
        # Keep safety blocks visible, but use explicit N/A / NOT REQUIRED wording for
        # non-trigger stages instead of the misleading FRESH / QUALIFIED default.
        _semantic_stage=str(r.get('TradeStage',r.get('EntryTriggerState','WAIT')) or 'WAIT').upper().strip()

        # V6.3.9.36 completeness is separate from lateness safety. ARMED/TRIGGERED
        # setups with a causal anchor must have a measurable move-consumed value
        # (primary session ratio or the engine's setup-origin fallback) before they
        # can qualify as a current/Q opportunity. They may remain research/Emerging.
        _stage=str(r.get('TradeStage',r.get('EntryTriggerState','WAIT')) or 'WAIT').upper()
        _requires_complete=(_stage in ('ARMED','CONFIRMED ENTRY') or 'TRIGGERED' in _stage)
        try:_ap=float(r.get('TriggerAnchorPrice',np.nan))
        except Exception:_ap=np.nan
        _aq=str(r.get('TriggerAnchorQuality','NONE') or 'NONE').upper()
        _anchor_present=bool(np.isfinite(_ap) or _aq not in ('','NONE','NO DATA'))
        _tdc_raw=r.get('TimingDataComplete',np.nan)
        try:
            _tdc_explicit=None if pd.isna(_tdc_raw) else bool(_tdc_raw)
        except Exception:_tdc_explicit=bool(_tdc_raw)
        timing_data_complete=bool(_tdc_explicit if _tdc_explicit is not None else not (_requires_complete and _anchor_present and not np.isfinite(consumed)))
        timing_data_source=str(r.get('TimingDataSource','SESSION_MOVE' if np.isfinite(consumed) else 'UNAVAILABLE') or 'UNAVAILABLE')
        timing_data_reason=str(r.get('TimingDataReason','') or '')
        if not timing_data_complete:
            status='TIMING DATA INCOMPLETE'
            cap=min(cap,50.0)
            if not timing_data_reason:
                timing_data_reason='ARMED/TRIGGERED has a causal trigger anchor but move-consumed timing is unavailable'

        if np.isfinite(consumed) and consumed>=80.0:
            eligible=False
            if consumed>=100.0:
                status='TOO LATE — MOVE FULLY CONSUMED';cap=min(cap,35.0)
            elif retest_ok:
                status='RETEST ONLY — PRIOR MOVE CONSUMED';cap=min(cap,58.0)
            else:
                status='RETEST ONLY / LATE';cap=min(cap,45.0)
        elif np.isfinite(consumed) and consumed>=70.0:
            status='AGING — WATCH RETEST'

        no_chase_raw=r.get('NoChaseCheck',True)
        try:no_chase_ok=True if pd.isna(no_chase_raw) else bool(no_chase_raw)
        except Exception:no_chase_ok=bool(no_chase_raw)
        if not no_chase_ok:
            eligible=False
            _nr=str(r.get('NoChaseReason','No-Chase guard failed') or 'No-Chase guard failed')
            _nr=_nr.replace('BLOCK — ','')
            status=('NO-CHASE BLOCK — '+_nr) if status=='FRESH / QUALIFIED' else status+' + NO-CHASE BLOCK'
            cap=min(cap,45.0)

        if chase>=70.0:
            eligible=False;status='HIGH CHASE RISK' if status=='FRESH / QUALIFIED' else status+' + CHASE'
            cap=min(cap,45.0)
        if not extension_ok:
            eligible=False;status='EXTENSION BLOCK' if status=='FRESH / QUALIFIED' else status+' + EXTENSION BLOCK'
            cap=min(cap,40.0)
        if exit_risk>=72.0:
            eligible=False;status='EXIT TRIGGER' if status=='FRESH / QUALIFIED' else status+' + EXIT'
            cap=min(cap,35.0)
        elif exit_risk>=55.0:
            eligible=False;status='EXIT ARMED' if status=='FRESH / QUALIFIED' else status+' + EXIT'
            cap=min(cap,45.0)

        # Stage-aware wording is applied last so genuine safety blocks remain visible.
        # INVALIDATED is never a live timing assessment. WAIT/WATCH with no measured
        # move-consumed timing is neutral/not-required, but only when no stronger
        # chase/extension/exit warning replaced the default status above.
        if _semantic_stage=='INVALIDATED':
            status='NOT APPLICABLE — INVALIDATED'
            timing_data_source='NOT REQUIRED — ALREADY BLOCKED'
            timing_data_reason='Setup is INVALIDATED; live move-consumed timing is not required because entry is already blocked'
        elif (_semantic_stage in ('WAIT','WATCH')) and (not np.isfinite(consumed)):
            # V6.3.9.40: Timing may be neutral/not-required even when another layer
            # (EXIT / NO-CHASE / EXTENSION) correctly replaced the default status.
            # Keep that safety status visible, but do not call the missing consumed
            # measurement UNAVAILABLE when it is not needed for the live decision.
            if status=='FRESH / QUALIFIED':
                status=f'NOT REQUIRED — {_semantic_stage}'
                timing_data_source='NOT REQUIRED'
                timing_data_reason=f'Move-consumed timing is not required for {_semantic_stage} state until a causal trigger event exists'
            else:
                timing_data_source='NOT REQUIRED — ALREADY BLOCKED'
                timing_data_reason=f'Move-consumed timing is not required because current {_semantic_stage} entry is already blocked by {status}'
        elif (not np.isfinite(consumed)) and _semantic_stage in ('EXTENDED — DO NOT CHASE','TOO LATE / CHASE','RETEST ONLY / LATE'):
            timing_data_source='NOT REQUIRED — ALREADY BLOCKED'
            timing_data_reason=f'Move-consumed timing is not required because TradeStage {_semantic_stage} already blocks entry'

        return status,cap,eligible,extension_ok,timing_data_complete,timing_data_source,timing_data_reason

    def row_score(r):
        move=n(r,'MoveScore',0); explosive=n(r,'ExplosiveScore',0); pred=n(r,'Prediction',0); accel=accel_quality(r)
        setup=float(np.clip(.28*move+.32*explosive+.25*pred+.15*accel,0,100))
        entry=n(r,'LiveActionabilityScore',n(r,'EntryScore',50))
        money=n(r,'MoneyFlowScore',50)
        evidence=n(r,'Reliability',0)
        rrq=rr_quality(r)
        core=.35*setup+.25*entry+.15*money+.15*evidence+.10*rrq

        late=consumed_risk(r)
        chase=n(r,'ChaseRiskScore',0)
        exit_risk=n(r,'ExitPressure',0)
        risk_score=max(exit_risk,max(late,chase))
        risk_penalty=min(15.0,max(0.0,risk_score-25.0)*0.20)

        ev_status,ev_penalty,ev_cap,ev_eligible,ev_profile=evidence_qualification(r,evidence)
        timing_status,timing_cap,timing_eligible,extension_ok,timing_data_complete,timing_data_source,timing_data_reason=timing_qualification(r,late,chase,exit_risk)

        model_mod=0.0
        try:optimized=float(r.get('OptimizedScore',np.nan))
        except Exception:optimized=np.nan
        if str(scan_mode) in ('Optimized 151','Discovery','OOS OPTIMIZED') and np.isfinite(optimized):
            model_mod=float(np.clip((optimized-50.0)*0.10,-5.0,5.0))

        data_quality=str(r.get('DataQuality','OK') or 'OK')
        session_fresh=bool(r.get('SessionDataFresh',True))
        data_ok=(data_quality=='OK') and session_fresh
        liquidity_ok=bool(r.get('LiquidityHardGateOK',True))
        liquidity_reason=str(r.get('LiquidityBlockReason','LOW LIQUIDITY / EXECUTION BLOCK') or 'LOW LIQUIDITY / EXECUTION BLOCK')
        data_penalty=0.0 if data_ok else 20.0
        data_cap=100.0 if data_ok else 35.0
        data_status='CURRENT SESSION DATA' if data_ok else (
            str(r.get('PriceFreshnessStatus','STALE / DATA QUALITY BLOCK')) if not session_fresh else f'DATA QUALITY {data_quality}'
        )

        invalid=str(r.get('TradeStage',r.get('EntryTriggerState',''))).upper()=='INVALIDATED'
        invalid_penalty=20.0 if invalid else 0.0
        invalid_cap=30.0 if invalid else 100.0

        # V3.5: the numeric Decision Score is the real score, not a guard-capped number.
        # Evidence/timing/freshness/invalidation determine eligibility and lane separately.
        raw_final=core+model_mod-risk_penalty-data_penalty-invalid_penalty
        qualification_cap=100.0  # compatibility field; no longer applied to the score
        final=float(np.clip(raw_final,0,100))

        # V6.3.9.19 keeps two different questions separate:
        #   1) Is the historical Evidence trade-grade?
        #   2) Is there a strong current opportunity NOW?
        # Previous builds called (1) a VALIDATED PICK even when Setup/Entry were weak
        # and TradeStage was WAIT.  Q-rank now requires BOTH.
        guard_eligible=bool(ev_eligible and timing_eligible and timing_data_complete and data_ok and liquidity_ok and extension_ok and not invalid)
        evidence_validated=bool(ev_profile.get('EvidenceTradeGrade',False))
        trade_stage_now=str(r.get('TradeStage',r.get('EntryTriggerState','WAIT')) or 'WAIT').upper()
        current_setup_ok=bool(setup >= 55.0)
        current_entry_ok=bool(entry >= 55.0)
        current_rank_ok=bool(final >= 55.0)
        current_stage_ok=trade_stage_now in ('WATCH','ARMED','CONFIRMED ENTRY')
        current_opportunity_ok=bool(current_setup_ok and current_entry_ok and current_rank_ok and current_stage_ok and timing_data_complete and liquidity_ok)
        validated_opportunity=bool(guard_eligible and evidence_validated and current_opportunity_ok)

        _opp_missing=[]
        if not current_setup_ok:_opp_missing.append(f'Setup {setup:.1f}<55')
        if not current_entry_ok:_opp_missing.append(f'Timing {entry:.1f}<55')
        if not current_rank_ok:_opp_missing.append(f'Rank {final:.1f}<55')
        if not current_stage_ok:_opp_missing.append(f'Stage {trade_stage_now}')
        if not timing_data_complete:_opp_missing.append('Timing data incomplete')
        if not liquidity_ok:_opp_missing.append('Liquidity blocked')
        current_qualification='CURRENT OPPORTUNITY' if current_opportunity_ok else ('CURRENT WAIT — '+', '.join(_opp_missing))

        qparts=[]
        if not data_ok:qparts.append('STALE/DATA BLOCK')
        if not liquidity_ok:qparts.append(liquidity_reason)
        if not ev_eligible:qparts.append(ev_status)
        elif not evidence_validated:qparts.append('EVIDENCE WARNING — '+ev_status)
        if (not timing_eligible) or (not timing_data_complete):qparts.append(timing_status)
        if invalid:qparts.append('INVALIDATED')
        if not current_opportunity_ok:qparts.append(current_qualification)
        qualification='VALIDATED OPPORTUNITY' if validated_opportunity else ' • '.join(qparts)

        _evn=int(ev_profile.get('EvidenceSampleN',0) or 0); _evlift=ev_profile.get('EvidenceLiftX',np.nan)
        _evlift_txt=f'{float(_evlift):.2f}x' if np.isfinite(float(_evlift)) else '—'

        # V6.3.9.19: the research-only Emerging lane keeps technically strong low-sample
        # setups visible without mixing them with validated opportunities. This score omits
        # Evidence on purpose: it answers only "how strong is the live technical setup?"
        # and is never allowed to create CONFIRMED/ACTIONABLE status.
        emerging_score=float(np.clip(.45*setup+.30*entry+.15*money+.10*rrq+model_mod-risk_penalty,0,100))
        low_sample_only=(not evidence_validated) and bool(ev_eligible) and (_evn < 12) and any(k in ev_status for k in ('UNPROVEN','PROVISIONAL','BUILDING'))

        # V6.3.9.25: Emerging must never contradict the live Entry engine.
        # A technically strong/low-sample setup cannot receive E# when Entry has
        # already declared it too late, extended/do-not-chase, or invalidated.
        # NoChaseCheck is an explicit hard guard as well. This changes eligibility
        # only; the Emerging Score formula and Ranking V3.9 weights are unchanged.
        _no_chase_raw=r.get('NoChaseCheck',True)
        no_chase_ok=True if pd.isna(_no_chase_raw) else bool(_no_chase_raw)
        _entry_action_state=str(r.get('EntryActionabilityState','') or '').upper()
        _entry_guard_text=' | '.join([trade_stage_now,_entry_action_state])
        entry_hard_block=any(k in _entry_guard_text for k in ('TOO LATE','DO NOT CHASE','INVALIDATED','RETEST ONLY / LATE'))
        emerging_ok=bool(low_sample_only and timing_eligible and data_ok and extension_ok and (not invalid) and no_chase_ok and (not entry_hard_block) and exit_risk < 55.0 and emerging_score >= 55.0)
        if emerging_ok:
            emerging_reason=f'Strong technical setup {emerging_score:.1f}/100, but Evidence is low-sample ({ev_status}, N={_evn})'
            if not timing_data_complete:
                emerging_reason+=' • TIMING DATA INCOMPLETE — research only until timing is recovered'
        elif not low_sample_only:
            emerging_reason='Not a low-sample emerging case'
        elif not no_chase_ok:
            _ncr=str(r.get('NoChaseReason','NoChaseCheck failed') or 'NoChaseCheck failed')
            emerging_reason=f'Entry guard: {_ncr} — do not promote to Emerging'
        elif entry_hard_block:
            emerging_reason=f'Entry guard: {trade_stage_now if trade_stage_now else _entry_action_state} — do not promote to Emerging'
        elif not timing_eligible:
            emerging_reason=f'Timing guard: {timing_status}'
        elif not data_ok:
            emerging_reason=f'Data guard: {data_status}'
        elif emerging_score < 55.0:
            emerging_reason=f'Technical setup {emerging_score:.1f}/100 below emerging threshold 55'
        else:
            emerging_reason='Blocked by risk/invalidation guard'
        if validated_opportunity:
            lane='VALIDATED OPPORTUNITY'
        elif evidence_validated:
            lane='EVIDENCE VALIDATED / WAIT' if (timing_eligible and timing_data_complete and data_ok and liquidity_ok and extension_ok and not invalid) else 'EVIDENCE VALIDATED / BLOCKED'
        elif emerging_ok:
            lane='EMERGING SETUP'
        else:
            lane='RESEARCH / BLOCKED'

        reason=(f'Setup {setup:.1f} • Entry {entry:.1f} • Flow {money:.1f} • Evidence {evidence:.1f} '
                f'({ev_status}, N={_evn}, Lift={_evlift_txt}) • R:R {rrq:.1f} • Risk {risk_score:.1f} (-{risk_penalty:.1f})')
        if model_mod:reason+=f' • OOS model {model_mod:+.1f}'
        if data_penalty:reason+=f' • data -{data_penalty:.0f}'
        if invalid_penalty:reason+=f' • invalid -{invalid_penalty:.0f}'

        return pd.Series({
            'SetupQualityScore':round(setup,1),
            'EntryTimingScore':round(entry,1),
            'DecisionEvidenceScore':round(evidence,1),
            'DecisionRiskScore':round(risk_score,1),
            'DecisionRankScore':round(final,1),
            'DecisionRankCore':round(core,1),
            'DecisionRankSetupQuality':round(setup,1),
            'DecisionRankEntryTiming':round(entry,1),
            'DecisionRankMoneyFlow':round(money,1),
            'DecisionRankEvidence':round(evidence,1),
            'DecisionRankRRQuality':round(rrq,1),
            'DecisionRankRiskPenalty':round(risk_penalty,1),
            'DecisionRankEvidencePenalty':round(ev_penalty,1),
            'DecisionRankQualificationCap':round(qualification_cap,1),
            'DecisionRankModelModifier':round(model_mod,1),
            'DecisionRankDataPenalty':round(data_penalty+invalid_penalty,1),
            'DecisionRankEligible':validated_opportunity,
            'ValidatedOpportunityEligible':validated_opportunity,
            'EvidenceValidated':evidence_validated,
            'CurrentOpportunityQualified':current_opportunity_ok,
            'CurrentOpportunityQualification':current_qualification,
            'ValidatedOpportunityReason':qualification,
            'DecisionRankQualification':qualification,
            'DecisionLane':lane,
            'EmergingSetupEligible':emerging_ok,
            'EmergingSetupScore':round(emerging_score,1),
            'EmergingSetupReason':emerging_reason,
            'EvidenceQualification':ev_status,
            'EvidenceQualificationReason':str(ev_profile.get('EvidenceQualificationReason','')),
            'EvidenceTradeGrade':bool(ev_profile.get('EvidenceTradeGrade',False)),
            'EvidenceSampleN':int(ev_profile.get('EvidenceSampleN',0) or 0),
            'EvidenceLiftX':ev_profile.get('EvidenceLiftX',np.nan),
            'TimingQualification':timing_status,
            'TimingDataComplete':bool(timing_data_complete),
            'TimingDataSource':timing_data_source,
            'TimingDataReason':timing_data_reason,
            'DataFreshnessQualification':data_status,
            # Compatibility/audit diagnostics. They are not each subtracted from rank.
            'DecisionRankStageModifier':0.0,
            'DecisionRankTimingPenalty':round(late,1),
            'DecisionRankChasePenalty':round(chase,1),
            'DecisionRankExitPenalty':round(exit_risk,1),
            'DecisionRankReason':reason,
            'DecisionRankVersion':'V3.13',
        })

    rank_fields=z.apply(row_score,axis=1)
    for c in rank_fields.columns:z[c]=rank_fields[c]

    # V6.3.9.65 — final execution-liquidity integrity guard. Keep the raw numeric
    # DecisionRankScore for research, but a failed liquidity hard gate can never
    # remain in Q/E/current-opportunity lanes even if an upstream overlay supplied
    # stale eligibility flags. EvidenceValidated stays historical/audit-only.
    _liq_exec=z.get('LiquidityHardGateOK',pd.Series(True,index=z.index)).fillna(False).astype(bool)
    _liq_block=~_liq_exec
    if bool(_liq_block.any()):
        for _c in ('DecisionRankEligible','ValidatedOpportunityEligible','CurrentOpportunityQualified','EmergingSetupEligible'):
            if _c in z.columns:z.loc[_liq_block,_c]=False
        if 'DecisionLane' in z.columns:z.loc[_liq_block,'DecisionLane']='RESEARCH / BLOCKED'
        if 'CurrentOpportunityQualification' in z.columns:
            z.loc[_liq_block,'CurrentOpportunityQualification']=z.loc[_liq_block].apply(lambda r:'CURRENT WAIT — '+str(r.get('LiquidityBlockReason','LIQUIDITY BLOCK')),axis=1)
        if 'ValidatedOpportunityReason' in z.columns:
            z.loc[_liq_block,'ValidatedOpportunityReason']=z.loc[_liq_block].apply(lambda r:str(r.get('LiquidityBlockReason','LIQUIDITY BLOCK'))+' • EXECUTION BLOCK',axis=1)
        if 'DecisionRankQualification' in z.columns:
            z.loc[_liq_block,'DecisionRankQualification']=z.loc[_liq_block].apply(lambda r:str(r.get('LiquidityBlockReason','LIQUIDITY BLOCK'))+' • EXECUTION BLOCK',axis=1)
        if 'EmergingSetupReason' in z.columns:
            z.loc[_liq_block,'EmergingSetupReason']=z.loc[_liq_block].apply(lambda r:str(r.get('LiquidityBlockReason','LIQUIDITY BLOCK'))+' • not eligible for Emerging NOW',axis=1)

    # V6.3.9.31 final decision/action consistency guard. Keep the Entry engine's
    # original recommendation for audit, then synchronize the visible action with
    # CurrentOpportunityQualified + DecisionLane + timing/data safety guards.
    if 'RecommendedAction' in z.columns:
        if 'RawRecommendedAction' not in z.columns:z['RawRecommendedAction']=z['RecommendedAction'].astype(str)
        z['RecommendedAction']=z.apply(_synchronize_recommended_action_v63931,axis=1)
        z['RecommendedActionReason']=z['CurrentOpportunityQualification'].astype(str)+' • '+z['DecisionLane'].astype(str)

    # Overall rank remains the raw V3.4 score across the complete scan.  Q-rank is
    # now reserved for VALIDATED OPPORTUNITIES (Evidence + current strength).
    # EvidenceRank separately tracks names whose historical Evidence is validated
    # but whose current setup may still be WAIT/BLOCKED.
    z=z.sort_values(['DecisionRankScore','SetupQualityScore','EntryTimingScore'],ascending=[False,False,False]).reset_index(drop=True)
    z['DecisionScoreRank']=np.arange(1,len(z)+1)
    z['QualifiedRank']=np.nan
    z['EmergingRank']=np.nan
    z['EvidenceRank']=np.nan
    _qm=z['ValidatedOpportunityEligible'].fillna(False).astype(bool)
    _em=z['EmergingSetupEligible'].fillna(False).astype(bool)
    _vm=z['EvidenceValidated'].fillna(False).astype(bool)
    _qidx=z[_qm].sort_values(['DecisionRankScore','SetupQualityScore','EntryTimingScore'],ascending=[False,False,False]).index.tolist()

    # V6.3.9.36: Emerging is a NOW ranking, so freshness must outrank raw setup
    # strength inside the E lane. Priority: FRESH+ARMED/CONFIRMED -> FRESH WAIT/WATCH
    # -> AGING/RETEST -> anything else. Score remains the tie-breaker inside a tier.
    def _emerging_freshness_tier35(r):
        timing=str(r.get('TimingQualification','') or '').upper()
        stage=str(r.get('TradeStage',r.get('EntryTriggerState','WAIT')) or 'WAIT').upper()
        if 'TIMING DATA INCOMPLETE' in timing:return 4
        if timing.startswith('FRESH'):
            return 0 if stage in ('ARMED','CONFIRMED ENTRY') else 1
        if timing.startswith('NOT REQUIRED —') and stage in ('WAIT','WATCH'):
            return 1
        if 'AGING' in timing:return 2
        if 'RETEST' in timing:return 3
        return 4
    z['EmergingFreshnessTier']=z.apply(_emerging_freshness_tier35,axis=1)
    _eidx=z[_em].sort_values(['EmergingFreshnessTier','EmergingSetupScore','EntryTimingScore','SetupQualityScore'],ascending=[True,False,False,False]).index.tolist()
    _vidx=z[_vm].sort_values(['DecisionEvidenceScore','EvidenceSampleN','DecisionRankScore'],ascending=[False,False,False]).index.tolist()
    for _pos,_idx in enumerate(_qidx,1):z.at[_idx,'QualifiedRank']=_pos
    for _pos,_idx in enumerate(_eidx,1):z.at[_idx,'EmergingRank']=_pos
    for _pos,_idx in enumerate(_vidx,1):z.at[_idx,'EvidenceRank']=_pos

    # V6.3.9.33 Ranking Semantics Fix.
    # Q# and E# are CURRENT opportunity lanes. EV# is deliberately historical-only:
    # it ranks validated OOS Evidence inside the Evidence view, but it no longer gets
    # a special promotion inside TradePriorityRank. This prevents an INVALIDATED,
    # TOO-LATE or otherwise safety-blocked EV#1 name from appearing near the top of
    # the live trade-priority list merely because its historical Evidence is strong.
    def _bool33(v, default=True):
        try:
            if pd.isna(v):return default
        except Exception:pass
        try:return bool(v)
        except Exception:return default

    def _priority_class33(r):
        lane=str(r.get('DecisionLane','RESEARCH / BLOCKED') or 'RESEARCH / BLOCKED').upper()
        stage=str(r.get('TradeStage',r.get('EntryTriggerState','WAIT')) or 'WAIT').upper()
        timing=str(r.get('TimingQualification','') or '').upper()
        data=str(r.get('DataFreshnessQualification','') or '').upper()
        liquidity_ok=_bool33(r.get('LiquidityHardGateOK',True),True)
        q=_bool33(r.get('ValidatedOpportunityEligible',False),False) and _bool33(r.get('CurrentOpportunityQualified',False),False) and liquidity_ok
        e=_bool33(r.get('EmergingSetupEligible',False),False) and liquidity_ok
        hard_consumed=_bool33(r.get('TimingConsumedHardBlock',False),False)
        no_chase=_bool33(r.get('NoChaseCheck',True),True)
        extension_ok=_bool33(r.get('ExtensionGuardCheck',True),True)
        evidence_lane_block=lane.startswith('EVIDENCE VALIDATED') and lane.endswith('/ BLOCKED')
        safety_block=((not liquidity_ok) or stage=='INVALIDATED' or hard_consumed or (not no_chase) or (not extension_ok)
                      or evidence_lane_block
                      or any(k in timing for k in ('TOO LATE','RETEST ONLY','VERY LATE','DO NOT CHASE','TIMING DATA INCOMPLETE'))
                      or any(k in data for k in ('STALE','DATA BLOCK','DATA QUALITY BLOCK')))
        if q:return 0,'Q — QUALIFIED NOW',True
        if e:return 1,'E — EMERGING NOW',True
        if not liquidity_ok:return 3,'BLOCKED / LOW LIQUIDITY',False
        if safety_block:return 3,'BLOCKED / HISTORICAL ONLY',False
        return 2,'CURRENT WATCH / RESEARCH',True

    _pc=z.apply(_priority_class33,axis=1)
    z['TradePriorityBucket']=[int(x[0]) for x in _pc]
    z['TradePriorityClass']=[x[1] for x in _pc]
    z['TradePriorityCurrentEligible']=[bool(x[2]) for x in _pc]

    # Preserve the explicit Q/E ordering. Everything else is ranked by current
    # Decision strength inside CURRENT WATCH first and safety-blocked names last.
    # EvidenceRank does not participate in this ordering.
    _used=set(_qidx)|set(_eidx)
    _watch=[i for i in z.index if i not in _used and int(z.at[i,'TradePriorityBucket'])==2]
    _blocked=[i for i in z.index if i not in _used and int(z.at[i,'TradePriorityBucket'])==3]
    _sort_key=lambda i:(-float(z.at[i,'DecisionRankScore']),-float(z.at[i,'SetupQualityScore']),-float(z.at[i,'EntryTimingScore']))
    _watch=sorted(_watch,key=_sort_key)
    _blocked=sorted(_blocked,key=_sort_key)
    _priority=_qidx+_eidx+_watch+_blocked
    _pr={idx:i+1 for i,idx in enumerate(_priority)}
    z['TradePriorityRank']=[_pr[i] for i in z.index]
    # V6.3.9.34 Rank Unification: there is one user-facing current rank.  The old
    # raw Decision-score ordering is retained as DecisionScoreRank for audit only.
    z['GlobalRank']=z['TradePriorityRank'].astype(int)
    z['TradePriorityVersion']='V3.13-EVIDENCE-MATURITY'
    if 'Market' in z.columns:z['MarketRank']=z.groupby('Market')['TradePriorityRank'].rank(method='first',ascending=True).astype(int)
    if 'Market' in z.columns and 'Sector' in z.columns:z['SectorRank']=z.groupby(['Market','Sector'])['TradePriorityRank'].rank(method='first',ascending=True).astype(int)
    return z


def _ensure_decision_ranking_v63919(df, scan_mode='Production 151'):
    """Backfill current Ranking V3.13 and final-stage timing/audit guards into cached snapshots.

    Legacy cached scans did not carry a verifiable session-date freshness field.
    Closed/pre-open Daily-reference rows are therefore treated conservatively until
    the Scanner is rerun under the current build.
    """
    if df is None or not isinstance(df,pd.DataFrame) or df.empty:return df
    z=df.copy()
    if 'SessionDataFresh' not in z.columns:
        _phase=z.get('MarketPhase',pd.Series('UNKNOWN',index=z.index)).astype(str)
        _src=z.get('PriceSource',pd.Series('',index=z.index)).astype(str)
        _ts=z.get('PriceTimestamp',pd.Series('',index=z.index)).astype(str)
        _legacy_uncertain=_phase.isin(['CLOSED','PRE-OPEN']) & (
            _src.str.contains('Daily reference|live unavailable|official',case=False,regex=True) |
            _ts.isin(['','—','nan','None'])
        )
        z['SessionDataFresh']=~_legacy_uncertain
        z['PriceFreshnessStatus']=np.where(_legacy_uncertain,'LEGACY SNAPSHOT — RERUN SCANNER','LEGACY SNAPSHOT — FRESHNESS UNVERIFIED')
        z['PriceSessionDate']=None;z['ExpectedSessionDate']=None
        if 'DataQuality' not in z:z['DataQuality']='OK'
        z.loc[_legacy_uncertain & z['DataQuality'].eq('OK'),'DataQuality']='STALE_SESSION'
    # Refresh the evidence profile even for a cached V6.3.9.15 scan so old
    # QUALIFIED labels cannot survive when N/lift are not trade-grade.
    try:
        _ep=z.apply(lambda r: pd.Series(_evidence_profile_v63916(r)),axis=1)
        for _c in _ep.columns:z[_c]=_ep[_c].values
        if 'RawEntryTriggerState' not in z.columns:
            if 'EntryTriggerState' in z.columns:z['RawEntryTriggerState']=z['EntryTriggerState'].fillna('WAIT').astype(str)
            else:z['RawEntryTriggerState']=z.get('TradeStage',pd.Series('WAIT',index=z.index)).fillna('WAIT').astype(str)
        if 'TradeStage' not in z.columns:z['TradeStage']=z['RawEntryTriggerState'].copy()
        z['EvidenceConfirmationGate']=z.get('EvidenceConfirmationGate',pd.Series('OK',index=z.index)).fillna('OK').astype(str)
        _evblock=z['TradeStage'].eq('CONFIRMED ENTRY') & (~z['EvidenceGuardOK'].fillna(False).astype(bool))
        if _evblock.any():
            z.loc[_evblock,'EvidenceConfirmationGate']=z.loc[_evblock].apply(lambda r:f"{r.get('EvidenceState','UNPROVEN')} — CONFIRMATION BLOCKED",axis=1)
            z.loc[_evblock,'TradeStage']='ARMED'
            if 'EntryTriggerState' in z.columns:z.loc[_evblock,'EntryTriggerState']='ARMED'
            if 'EntryActionabilityState' in z.columns:z.loc[_evblock,'EntryActionabilityState']='SETUP CONFIRMED — EVIDENCE BLOCK'
        if 'ActionableNow' in z.columns:z.loc[~z['EvidenceGuardOK'].fillna(False).astype(bool),'ActionableNow']=False
    except Exception:pass
    di_cols=('MoneyFlowScore','MarketCycleScore')
    if any(c not in z.columns for c in di_cols):
        try:z=_decision_intelligence_enrich_v6394(z)
        except Exception:pass
    return _apply_decision_ranking_v63919(z,scan_mode)


def _feedback_anchor_text_v63934(v):
    """Normalize an event anchor without inventing one from future data."""
    try:
        if v is None or pd.isna(v):return ''
    except Exception:pass
    t=str(v).strip()
    if not t or t.lower() in ('nan','none','nat') or t in ('—','-'):return ''
    try:
        q=pd.to_datetime(t,errors='coerce',utc=True)
        if pd.notna(q):return q.floor('min').isoformat()
    except Exception:pass
    return t[:80]


def _feedback_event_id_v63934(r, ts_utc=None):
    """Deterministic causal event id.

    Prefer the setup-origin/trigger-anchor already visible at scan time.  Legacy
    snapshots that predate those fields fall back to ticker + exchange session
    date, which collapses repeated same-session scans instead of pretending they
    are independent observations.
    """
    ticker=str(r.get('Ticker',r.get('ticker','')) or '').upper().strip()
    market=_feedback_market_key_v612(r.get('Market',r.get('market','')),ticker)
    setup=_feedback_anchor_text_v63934(r.get('SetupOriginTime',r.get('setup_origin_time','')))
    # TriggerAnchorTime can legitimately advance/re-resolve during the same live
    # setup, so it is stored for audit but is not allowed to split one event into
    # multiple statistical observations. A stable SetupOriginTime may span sessions;
    # otherwise the exchange session date is the conservative de-dup boundary.
    if setup: anchor='SETUP:'+setup
    else:
        stamp=ts_utc if ts_utc is not None else r.get('ts_utc')
        try: session=str(_snapshot_market_date_v612(stamp,market,ticker))
        except Exception:
            q=pd.to_datetime(stamp,errors='coerce',utc=True);session=str(q.date()) if pd.notna(q) else 'UNKNOWN'
        anchor='SESSION:'+session
    raw=f'{market}|{ticker}|{anchor}'
    return 'EVT-'+hashlib.sha1(raw.encode('utf-8','ignore')).hexdigest()[:16].upper()


def _feedback_plan_geometry_v63934(r):
    """Audit whether a stored LONG trade plan was geometrically valid at snapshot time."""
    def n(*keys):
        for k in keys:
            try:
                v=float(r.get(k,np.nan))
                if np.isfinite(v):return v
            except Exception:pass
        return np.nan
    px=n('Price','price');lo=n('EntryLow','entry_low');hi=n('EntryHigh','entry_high');trig=n('BreakoutTrigger','trigger');inv=n('Invalidation','invalidation');t1=n('Target1','target1');t2=n('Target2','target2')
    reasons=[]
    if not np.isfinite(px) or px<=0:reasons.append('missing/invalid snapshot price')
    if np.isfinite(lo) and np.isfinite(hi) and lo>hi:reasons.append('EntryLow > EntryHigh')
    if not np.isfinite(inv):reasons.append('missing invalidation')
    elif np.isfinite(px) and inv>=px:reasons.append('Invalidation >= snapshot price')
    if not np.isfinite(t1):reasons.append('missing Target1')
    elif np.isfinite(px) and t1<=px:reasons.append('Target1 <= snapshot price')
    if np.isfinite(t2) and np.isfinite(t1) and t2<=t1:reasons.append('Target2 <= Target1')
    if np.isfinite(trig) and np.isfinite(inv) and trig<=inv:reasons.append('Breakout trigger <= invalidation')
    return (len(reasons)==0, 'OK' if not reasons else ' • '.join(reasons))


def _feedback_apply_event_integrity_v63934(sn):
    """Annotate raw snapshots with independent-event and plan-integrity fields.

    Stored V6.3.9.34 rows already carry EventID/role.  Legacy rows are rebuilt
    deterministically using the same causal fallback so old duplicate scans stop
    inflating N immediately, without rewriting or deleting the historical DB.
    """
    if sn is None or not isinstance(sn,pd.DataFrame) or sn.empty:return sn
    z=sn.copy()
    if 'event_id' not in z:z['event_id']=''
    missing=z['event_id'].fillna('').astype(str).str.strip().eq('')
    if missing.any():
        z.loc[missing,'event_id']=z.loc[missing].apply(lambda r:_feedback_event_id_v63934(r,r.get('ts_utc')),axis=1)
    z['_event_ts']=pd.to_datetime(z.get('ts_utc'),errors='coerce',utc=True)
    z=z.sort_values(['_event_ts','id'],ascending=[True,True],na_position='last')
    first_ids=z.groupby('event_id',dropna=False)['id'].transform('first')
    first_ts=z.groupby('event_id',dropna=False)['_event_ts'].transform('first')
    z['event_origin_snapshot_id']=pd.to_numeric(first_ids,errors='coerce')
    z['event_origin_ts_utc']=first_ts.astype(str)
    z['event_role']=np.where(z['id'].eq(first_ids),'ORIGIN','TRACKING')
    z['independent_event']=z['event_role'].eq('ORIGIN').astype(int)
    geom=z.apply(_feedback_plan_geometry_v63934,axis=1)
    z['plan_geometry_valid']=[int(bool(x[0])) for x in geom]
    z['plan_geometry_reason']=[x[1] for x in geom]
    z['trade_learning_eligible']=((z['independent_event']==1)&(z['plan_geometry_valid']==1)).astype(int)
    return z.drop(columns=['_event_ts'],errors='ignore').sort_values('id',ascending=False).reset_index(drop=True)


def _feedback_independent_rows_v63934(x, require_valid_plan=False):
    """One causal observation per EventID (+ horizon when present)."""
    if x is None or not isinstance(x,pd.DataFrame) or x.empty:return pd.DataFrame()
    z=x.copy()
    if 'event_id' not in z:
        z['event_id']=z.apply(lambda r:_feedback_event_id_v63934(r,r.get('ts_utc')),axis=1)
    else:
        miss=z['event_id'].fillna('').astype(str).str.strip().eq('')
        if miss.any():z.loc[miss,'event_id']=z.loc[miss].apply(lambda r:_feedback_event_id_v63934(r,r.get('ts_utc')),axis=1)
    if 'plan_geometry_valid' not in z:
        z['plan_geometry_valid']=[int(_feedback_plan_geometry_v63934(r)[0]) for _,r in z.iterrows()]
    z['_event_ts']=pd.to_datetime(z.get('ts_utc'),errors='coerce',utc=True)
    keys=['event_id']+(['horizon'] if 'horizon' in z.columns else [])
    z=z.sort_values(['_event_ts']+(['id'] if 'id' in z.columns else []),ascending=True,na_position='last').drop_duplicates(subset=keys,keep='first')
    z['event_role']='ORIGIN';z['independent_event']=1
    if require_valid_plan:z=z[pd.to_numeric(z['plan_geometry_valid'],errors='coerce').fillna(0).eq(1)].copy()
    return z.drop(columns=['_event_ts'],errors='ignore').reset_index(drop=True)


def _feedback_movement_summary_v63934(primary):
    """Movement truth is separate from trade-plan truth: MFE +3/+5 vs Target1-first."""
    if primary is None or not isinstance(primary,pd.DataFrame) or primary.empty:return pd.DataFrame()
    p=_feedback_independent_rows_v63934(primary,require_valid_plan=False)
    if p.empty:return pd.DataFrame()
    mfe=100*pd.to_numeric(p.get('max_favorable'),errors='coerce');mae=100*pd.to_numeric(p.get('max_adverse'),errors='coerce');endr=100*pd.to_numeric(p.get('end_return'),errors='coerce')
    p=p[np.isfinite(mfe)].copy();p['_mfe']=mfe.loc[p.index];p['_mae']=mae.loc[p.index];p['_end']=endr.loc[p.index]
    if p.empty:return pd.DataFrame()
    base3=float((p['_mfe']>=3).mean());base5=float((p['_mfe']>=5).mean())
    masks=[('ALL INDEPENDENT EVENTS',pd.Series(True,index=p.index))]
    for col,label in [('daily_setup','Daily Setup'),('hourly_entry','Hourly / 15m'),('volume_flow','Volume / Flow')]:
        if col in p:masks.append((label,pd.to_numeric(p[col],errors='coerce').fillna(0).eq(1)))
    if 'money_flow_score' in p:masks.append(('Money Flow ≥65',pd.to_numeric(p['money_flow_score'],errors='coerce').ge(65)))
    if 'daily_setup' in p and 'volume_flow' in p:masks.append(('Daily + Flow',pd.to_numeric(p['daily_setup'],errors='coerce').fillna(0).eq(1)&pd.to_numeric(p['volume_flow'],errors='coerce').fillna(0).eq(1)))
    if 'daily_setup' in p and 'money_flow_score' in p:masks.append(('Daily + Money Flow ≥65',pd.to_numeric(p['daily_setup'],errors='coerce').fillna(0).eq(1)&pd.to_numeric(p['money_flow_score'],errors='coerce').ge(65)))
    rows=[]
    for label,mask in masks:
        g=p[mask.reindex(p.index,fill_value=False)].copy();n=len(g)
        if not n:continue
        h3=float((g['_mfe']>=3).mean());h5=float((g['_mfe']>=5).mean())
        rows.append({'Feature / Cohort':label,'Independent Event N':n,'Hit +3% %':100*h3,'Lift +3% x':h3/base3 if base3>0 else np.nan,'Hit +5% %':100*h5,'Lift +5% x':h5/base5 if base5>0 else np.nan,'Avg MFE %':float(g['_mfe'].mean()),'Avg MAE %':float(g['_mae'].mean()),'Avg End Return %':float(g['_end'].mean()),'Evidence':('OK' if n>=12 else ('BUILDING EVIDENCE' if n>=8 else ('PROVISIONAL EVIDENCE' if n>=6 else 'LOW SAMPLE')))})
    return pd.DataFrame(rows)


def _feedback_integrity_summary_v63934(sn, primary=None):
    if sn is None or not isinstance(sn,pd.DataFrame) or sn.empty:return pd.DataFrame()
    z=_feedback_apply_event_integrity_v63934(sn);p=_feedback_independent_rows_v63934(primary,False) if isinstance(primary,pd.DataFrame) and not primary.empty else pd.DataFrame()
    return pd.DataFrame([{
        'Raw snapshots':len(z),'Independent events':int(pd.to_numeric(z.get('independent_event'),errors='coerce').fillna(0).sum()),
        'Tracking snapshots':int(z.get('event_role',pd.Series(dtype=str)).astype(str).eq('TRACKING').sum()),
        'Duplicate inflation removed':max(0,len(z)-int(pd.to_numeric(z.get('independent_event'),errors='coerce').fillna(0).sum())),
        'Independent primary outcomes':len(p),'Invalid-plan primary events':int(pd.to_numeric(p.get('plan_geometry_valid'),errors='coerce').fillna(0).eq(0).sum()) if not p.empty else 0,
        'Trade-learning eligible primary events':int(pd.to_numeric(p.get('plan_geometry_valid'),errors='coerce').fillna(0).eq(1).sum()) if not p.empty else 0,
        'Event rule':'ORIGIN only; later same-event scans are TRACKING','Trade rule':'ORIGIN + valid long-plan geometry only','Movement rule':'ORIGIN; MFE +3%/+5% independent of trade-plan geometry'
    }])


def _feedback_recommendation_profile_v63962(r):
    """Snapshot-time decision labels used for recommendation-aware Feedback.

    Decision stage remains separate from research layers such as Pre-Move and
    Continuation, so one event can be audited without double-counting it.
    """
    stage=_decision_stage_canonical_v63961(r.get('EffectiveDecisionStage',r.get('DecisionDisplayStage',r.get('DecisionBoardStage','WAIT'))))
    cont=str(r.get('ContinuationEntryState','N/A') or 'N/A').upper()
    pm=str(r.get('PreMovePatternStrength','NONE') or 'NONE').upper()
    pm_action=bool(r.get('PreMoveActionableNow',False))
    ret=str(r.get('RetestStatus','') or '')
    if stage in ('ENTRY NOW','LAST SESSION ENTRY'):
        entry_path='CONTINUATION READY' if cont=='READY' else 'PRIMARY ENTRY'
    elif stage=='RETEST': entry_path='RETEST'
    elif stage=='ARMED': entry_path='ARMED'
    elif stage=='BUILDING SETUP': entry_path='BUILDING SETUP'
    elif stage=='ARMED BLOCKED': entry_path='ARMED BLOCKED'
    elif stage=='TOO LATE': entry_path='TOO LATE'
    else: entry_path=stage
    if pm=='HIGH' and pm_action: research='PRE-MOVE HIGH • ACTIONABLE'
    elif pm=='HIGH': research='PRE-MOVE HIGH • PATTERN ONLY'
    elif pm=='WATCH': research='PRE-MOVE WATCH'
    else: research=pm
    return {'decision_stage':stage,'entry_path':entry_path,'research_layer':research,'continuation':cont,'retest':ret}

def _feedback_store_analyze_v63962(decision_df,horizon,target):
    """Persist one Analyze event into the same Feedback DB without double-counting.

    Repeated Analyze runs for the same EventID overwrite one ANALYZE row. If a
    Scanner snapshot already exists for that event, Analyze is stored as TRACKING
    and therefore cannot inflate independent-event N.
    """
    try:
        if decision_df is None or not isinstance(decision_df,pd.DataFrame) or decision_df.empty:return {'saved':False,'reason':'NO ANALYZE ROW'}
        z=decision_df.copy();r=z.iloc[0].to_dict();ts=datetime.utcnow().replace(microsecond=0).isoformat()+'Z'
        eid=_feedback_event_id_v63934(r,ts);scan_id='ANALYZE|'+eid
        cfg={'horizon':int(horizon),'target':float(target),'scan_mode':'ANALYZE','_snapshot_source':'ANALYZE','_snapshot_ts_utc':ts,'_app_version':APP_VERSION}
        _feedback_store_scan_v600(scan_id,z,cfg)
        con=_feedback_conn_v600();q=con.execute('SELECT id,event_id,event_role,snapshot_source FROM snapshots WHERE scan_id=? AND ticker=? LIMIT 1',(scan_id,str(r.get('Ticker','')))).fetchone();con.close()
        if not q:return {'saved':False,'reason':'STORE FAILED','event_id':eid}
        return {'saved':True,'snapshot_id':int(q[0]),'event_id':str(q[1] or eid),'event_role':str(q[2] or 'TRACKING'),'source':str(q[3] or 'ANALYZE')}
    except Exception as e:return {'saved':False,'reason':f'{type(e).__name__}: {e}'}

def _feedback_recommendation_summary_v63962(merged):
    """Compare realized price paths with the recommendation that existed at snapshot time."""
    if merged is None or not isinstance(merged,pd.DataFrame) or merged.empty:return pd.DataFrame()
    z=_feedback_independent_rows_v63934(merged,require_valid_plan=False)
    if z.empty:return pd.DataFrame()
    if 'recommendation_type' not in z.columns:z['recommendation_type']=z.get('decision_board_stage',z.get('trade_stage','WAIT'))
    if 'entry_path' not in z.columns:z['entry_path']=z['recommendation_type']
    z['Recommendation']=z['recommendation_type'].fillna('WAIT').astype(str).map(_decision_stage_canonical_v63961)
    z['Entry Path']=z['entry_path'].fillna('').astype(str)
    z['_mfe']=100*pd.to_numeric(z.get('max_favorable'),errors='coerce');z['_mae']=100*pd.to_numeric(z.get('max_adverse'),errors='coerce');z['_end']=100*pd.to_numeric(z.get('end_return'),errors='coerce')
    z['_t1win']=z.get('first_event',pd.Series('',index=z.index)).astype(str).str.startswith('TARGET1 FIRST').astype(float)
    z['_hit3']=pd.to_numeric(z['_mfe'],errors='coerce').ge(3).astype(float);z['_hit5']=pd.to_numeric(z['_mfe'],errors='coerce').ge(5).astype(float);z['_hit10']=pd.to_numeric(z['_mfe'],errors='coerce').ge(10).astype(float)
    keys=['horizon','Recommendation','Entry Path']
    g=z.groupby(keys,dropna=False).agg(Events=('snapshot_id','count'),Target1_First=('_t1win','mean'),Hit_3=('_hit3','mean'),Hit_5=('_hit5','mean'),Hit_10=('_hit10','mean'),Avg_MFE=('_mfe','mean'),Avg_MAE=('_mae','mean'),Avg_End=('_end','mean')).reset_index()
    for c in ['Target1_First','Hit_3','Hit_5','Hit_10']:g[c+' %']=100*g.pop(c)
    g=g.rename(columns={'Avg_MFE':'Avg MFE %','Avg_MAE':'Avg MAE %','Avg_End':'Avg End Return %','horizon':'Horizon'})
    def rule(r):
        st=str(r['Recommendation']).upper();path=str(r['Entry Path']).upper()
        if st in ('ENTRY NOW','LAST SESSION ENTRY') or 'CONTINUATION READY' in path:return 'Trade audit: Target1 before Invalidation + MFE/MAE'
        if st=='ARMED':return 'Readiness audit: did price achieve +3%/+5% after ARMED?'
        if st=='BUILDING SETUP':return 'Early setup audit: did price achieve +3%/+5% before the setup expired?'
        if st=='RETEST':return 'Retest audit proxy: MFE/MAE shown; exact pullback sequence remains audit-only'
        if st=='TOO LATE':return 'False-negative audit: how often price still added +3%/+5%/+10% after TOO LATE'
        return 'Movement audit: realized +3%/+5%/+10% and drawdown'
    g['Interpretation']=g.apply(rule,axis=1)
    return g.sort_values(['Horizon','Recommendation','Entry Path']).reset_index(drop=True)

def _feedback_store_scan_v600(scan_id,df,config):
    if df is None or not isinstance(df,pd.DataFrame) or df.empty:return
    try:
        # Persist the research-radar layer together with live scans. Historical
        # workbook imports already contain the original snapshot columns and must
        # not be overwritten by today's cached research model.
        if bool(config.get('_preserve_imported_fields',False)):
            df=df.copy()
        else:
            try: df=_attach_regular_signature_overlay_v638(_attach_pre_move_overlay_v628(df))
            except Exception: df=df.copy()
        con=_feedback_conn_v600(); ts=str(config.get('_snapshot_ts_utc') or (datetime.utcnow().replace(microsecond=0).isoformat()+'Z'))
        def num(v):
            try:return float(v) if pd.notna(v) and np.isfinite(float(v)) else None
            except:return None
        def bit(v):
            try:
                if pd.isna(v):return None
                if isinstance(v,str):
                    vv=v.strip().lower()
                    if vv in ('false','0','no','n','off',''):return 0
                    if vv in ('true','1','yes','y','on'):return 1
                return int(bool(v))
            except:return None
        for _,r in df.iterrows():
            prod=str(r.get('EntryTriggerState',r.get('EntryStatus','')))
            opt=str(r.get('OptimizedStage',''))
            pconf=prod=='CONFIRMED ENTRY';oconf=opt=='OPTIMIZED CONFIRMED'
            disagreement='BOTH CONFIRMED' if pconf and oconf else ('OPTIMIZED ONLY' if oconf else ('PRODUCTION ONLY' if pconf else 'NEITHER'))
            _event_id=_feedback_event_id_v63934(r,ts)
            _existing=con.execute('SELECT id,event_role,event_origin_snapshot_id,event_origin_ts_utc FROM snapshots WHERE scan_id=? AND ticker=? LIMIT 1',(str(scan_id),str(r.get('Ticker','')))).fetchone()
            if _existing:
                _origin_id=int(_existing[2]) if _existing[2] is not None else int(_existing[0]);_origin_ts=str(_existing[3] or ts);_event_role=str(_existing[1] or 'ORIGIN')
            else:
                _prior=con.execute('SELECT id,ts_utc,event_id FROM snapshots WHERE event_id=? ORDER BY id ASC LIMIT 1',(_event_id,)).fetchone()
                # If an early scan had no SetupOriginTime but a later scan discovers
                # one, keep the same same-session event instead of splitting N.
                if not _prior:
                    _cur_mkt=_feedback_market_key_v612(str(r.get('Market','')),str(r.get('Ticker','')))
                    try:_cur_session=str(_snapshot_market_date_v612(ts,_cur_mkt,str(r.get('Ticker',''))))
                    except Exception:_cur_session=''
                    _recent=con.execute('SELECT id,ts_utc,event_id FROM snapshots WHERE ticker=? AND market=? ORDER BY id DESC LIMIT 24',(str(r.get('Ticker','')),str(r.get('Market','')))).fetchall()
                    for _rr in _recent:
                        try:_same=str(_snapshot_market_date_v612(_rr[1],_cur_mkt,str(r.get('Ticker',''))))==_cur_session
                        except Exception:_same=False
                        if _same:
                            _event_id=str(_rr[2] or _feedback_event_id_v63934({'ticker':r.get('Ticker',''),'market':r.get('Market','')},_rr[1]));_prior=con.execute('SELECT id,ts_utc,event_id FROM snapshots WHERE event_id=? ORDER BY id ASC LIMIT 1',(_event_id,)).fetchone() or _rr;break
                if _prior:_origin_id=int(_prior[0]);_origin_ts=str(_prior[1]);_event_role='TRACKING'
                else:_origin_id=None;_origin_ts=ts;_event_role='ORIGIN'
            _geom_ok,_geom_reason=_feedback_plan_geometry_v63934(r)
            rec={
                'scan_id':scan_id,'ts_utc':ts,'ticker':str(r.get('Ticker','')),'market':str(r.get('Market','')),'price':num(r.get('Price')),
                'top_score':num(r.get('TopScore')),'opportunity':num(r.get('OpportunityScore')),'trade_stage':str(r.get('TradeStage','')),'movement_stage':str(r.get('MovementStage','')),
                'prediction':num(r.get('Prediction')),'move_score':num(r.get('MoveScore')),'explosive':num(r.get('ExplosiveScore')),'entry_score':num(r.get('EntryScore')),
                'hourly':num(r.get('HourlyConfirm')),'exit_pressure':num(r.get('ExitPressure')),'global_rank':int(r.get('GlobalRank')) if pd.notna(r.get('GlobalRank')) else None,
                'market_rank':int(r.get('MarketRank')) if pd.notna(r.get('MarketRank')) else None,'session_status':str(r.get('SessionStatus','')),
                'entry_low':num(r.get('EntryLow')),'entry_high':num(r.get('EntryHigh')),'trigger':num(r.get('BreakoutTrigger')),'invalidation':num(r.get('Invalidation')),
                'target1':num(r.get('Target1')),'target2':num(r.get('Target2')),'horizon_days':int(config.get('horizon',5)),'target_pct':(float(config.get('target',0))*100.0 if abs(float(config.get('target',0) or 0))<=1.0 else float(config.get('target',0) or 0)),'app_version':str(config.get('_app_version',APP_VERSION) or APP_VERSION),'entry_state':prod,
                'confirmation_pct':num(r.get('EntryConfirmationPct')),'daily_setup':bit(r.get('DailySetupCheck')),'fresh_signal':bit(r.get('FreshSignalCheck')),
                'hourly_entry':bit(r.get('HourlyEntryCheck')),'volume_flow':bit(r.get('VolumeFlowCheck')),'no_chase':bit(r.get('NoChaseCheck')),
                'extension_guard':bit(r.get('ExtensionGuardCheck')),'chase_risk_score':num(r.get('ChaseRiskScore')),'chase_risk_label':str(r.get('ChaseRiskLabel','LOW')),'session_move_pct':num(r.get('SessionMovePct')),'since_trigger_pct':num(r.get('SinceTriggerPct')),'volume_trend':str(r.get('VolumeTrend','NO DATA')),'trigger_anchor_price':num(r.get('TriggerAnchorPrice')),
                'market_regime':str(r.get('MarketRegime','NEUTRAL')),'market_regime_ok':bit(r.get('MarketRegimeCheck')),
                'optimized_stage':opt,'optimized_score':num(r.get('OptimizedScore')),'optimized_match':num(r.get('OptimizedMatchPct')),
                'optimized_model_status':str(r.get('OptimizedModelStatus','')),'optimized_model_id':str(r.get('OptimizedModelID','')),
                'optimized_model_scope':str(r.get('OptimizedModelScope','')),'optimized_model_horizon':num(r.get('OptimizedModelHorizon')),'optimized_oos_lift':num(r.get('OptimizedModelOOSLift')),
                'optimized_hourly_match':num(r.get('HourlyOptimizedMatchPct')),'optimized_hourly_horizon':str(r.get('HourlyOptimizedHorizon','')),
                'model_disagreement':disagreement,'scan_mode':str(config.get('scan_mode','Production 151')),
                'pre_move_stage':str(r.get('PreMoveStage','')),'pre_move_score':num(r.get('PreMoveScore')),
                'pre_move_probability':num(r.get('PreMoveProbabilityPct')),'pre_move_families':str(r.get('PreMoveIndependentFamilies','')),
                'pre_move_features':str(r.get('PreMoveStrongestFeatures','')),'pre_move_best_lift':num(r.get('PreMoveBestOOSLiftX')),
                'pre_move_freshness':str(r.get('PreMoveFreshness','')),
                'regular_target_pct':num(r.get('RegularRadarTargetPct')),'regular_lead_window':str(r.get('RegularRadarLeadWindow','')),'regular_timeframe':str(r.get('RegularRadarTimeframe','')),
                'regular_score':num(r.get('RegularRadarScore')),'regular_hit_rate':num(r.get('RegularRadarHitRatePct')),'regular_baseline':num(r.get('RegularRadarBaselinePct')),'regular_lift':num(r.get('RegularRadarLiftX')),'regular_signature':str(r.get('RegularRadarBestSignature','')),
                'regular_setup_score':num(r.get('RegularRadarSetupScore')),'regular_freshness':str(r.get('RegularRadarFreshness','')),'regular_funnel_stage':str(r.get('RegularFunnelStage','')),
                'regular_funnel_final_n':num(r.get('RegularFunnelFinalN')),'regular_funnel_final_hit_rate':num(r.get('RegularFunnelFinalHitRatePct')),'regular_funnel_final_baseline':num(r.get('RegularFunnelFinalBaselinePct')),'regular_funnel_final_lift':num(r.get('RegularFunnelFinalLiftX')),'regular_live_layer':str(r.get('RegularFunnelLiveLayer','')),
                'raw_entry_state':str(r.get('RawEntryTriggerState',r.get('EntryTriggerState',''))),'entry_action_state':str(r.get('EntryActionabilityState','')),
                'setup_confirmed':bit(r.get('SetupConfirmed')),'price_actionable':bit(r.get('PriceActionableNow')),'rr_actionable':bit(r.get('RRActionable')),'confirmed_entry_gate':bit(r.get('ConfirmedEntryGateOK')),'entry_distance_pct':num(r.get('EntryDistancePct')),'actionability_missing':str(r.get('ActionabilityMissing','')),
                'evidence_confirmation_gate':str(r.get('EvidenceConfirmationGate','OK')),'armed_timing_class':str(r.get('ArmedTimingClass','N/A')),'armed_timing_reason':str(r.get('ArmedTimingReason','')),
                'move_consumed_before_trigger':num(r.get('MoveConsumedBeforeTriggerPct')),'target1_progress_pct':num(r.get('Target1ProgressPct')),'live_rr_t1':num(r.get('LiveRR_T1')),'live_rr_t2':num(r.get('LiveRR_T2')),'regular_move_consumed_pct':num(r.get('RegularRadarMoveConsumedPct')),'snapshot_source':str(config.get('_snapshot_source','LIVE SCANNER')),'valuation_score':num(r.get('ValuationScore')),'valuation_label':str(r.get('ValuationLabel','')),'valuation_discount_pct':num(r.get('EstimatedDiscountPct')),'valuation_fair_low':num(r.get('FairValueLow')),'valuation_fair_high':num(r.get('FairValueHigh')),'valuation_evidence':str(r.get('ValuationEvidence','')),'valuation_archetype':str(r.get('ValuationArchetype','')),'valuation_metric_count':num(r.get('ValuationMetricCount')),'valuation_peer_count':num(r.get('ValuationPeerCount')),'valuation_currency':str(r.get('Currency','')),'valuation_method':str(r.get('ValuationMethod','')),'money_flow_score':num(r.get('MoneyFlowScore')),'money_flow_label':str(r.get('MoneyFlowLabel','')),'money_flow_evidence':str(r.get('MoneyFlowEvidence','')),'inflow_pressure':num(r.get('InflowPressure')),'inflow_label':str(r.get('InflowLabel','')),'outflow_pressure':num(r.get('OutflowPressure')),'outflow_label':str(r.get('OutflowLabel','')),'net_flow_balance':num(r.get('NetFlowBalance')),'net_flow_score':num(r.get('NetFlowScore')),'net_flow_label':str(r.get('NetFlowLabel','')),'flow_pressure_evidence':str(r.get('FlowPressureEvidence','')),'market_cycle_score':num(r.get('MarketCycleScore')),'market_cycle_stage':str(r.get('MarketCycleStage','')),'market_cycle_reason':str(r.get('MarketCycleReason','')),'catalyst_score':num(r.get('CatalystScore')),'catalyst_label':str(r.get('CatalystLabel','')),'catalyst_evidence':str(r.get('CatalystEvidence','')),'catalyst_headline':str(r.get('CatalystTopHeadline','')),'catalyst_event_risk':str(r.get('CatalystEventRisk','')),'decision_rank_score':num(r.get('DecisionRankScore')),'decision_rank_core':num(r.get('DecisionRankCore')),'decision_rank_reason':str(r.get('DecisionRankReason','')),'decision_rank_version':str(r.get('DecisionRankVersion','')),'legacy_global_rank':num(r.get('LegacyGlobalRank')),'legacy_trade_priority_rank':num(r.get('LegacyTradePriorityRank')),
                'event_id':_event_id,'event_role':_event_role,'event_origin_snapshot_id':_origin_id,'event_origin_ts_utc':_origin_ts,'independent_event':1 if _event_role=='ORIGIN' else 0,
                'plan_geometry_valid':1 if _geom_ok else 0,'plan_geometry_reason':_geom_reason,'trade_learning_eligible':1 if (_event_role=='ORIGIN' and _geom_ok) else 0,
                'setup_origin_time':str(r.get('SetupOriginTime','')),'trigger_anchor_time':str(r.get('TriggerAnchorTime','')),
                'decision_board_stage':str(r.get('DecisionBoardStage','')),'original_signal_time':str(r.get('OriginalSignalTime','')),'original_signal_stage':str(r.get('OriginalSignalStage','')),'original_signal_price':num(r.get('OriginalSignalPrice')),'original_trigger_price':num(r.get('OriginalTriggerPrice')),'original_trigger_time':str(r.get('OriginalTriggerTime','')),'original_target1':num(r.get('OriginalTarget1')),'original_invalidation':num(r.get('OriginalInvalidation')),'original_progress_t1_pct':num(r.get('OriginalProgressToT1Pct')),'original_move_since_signal_pct':num(r.get('OriginalMoveSinceSignalPct')),'original_signal_memory_source':str(r.get('OriginalSignalMemorySource','')),'original_signal_id':str(r.get('OriginalSignalId','')),'original_memory_integrity':str(r.get('OriginalMemoryIntegrity','')),'original_trigger_locked':bit(r.get('OriginalTriggerLocked')),'current_trigger_price':num(r.get('CurrentTriggerPrice')),'current_trigger_time':str(r.get('CurrentTriggerTime','')),'current_target1':num(r.get('CurrentTarget1')),'current_progress_t1_pct':num(r.get('CurrentProgressToT1Pct')),'original_equals_current_trigger':bit(r.get('OriginalEqualsCurrentTrigger')),
                'pre_breakout_accumulation_score':num(r.get('PreBreakoutAccumulationScore')),'pre_breakout_accumulation_stage':str(r.get('PreBreakoutAccumulationStage','')),'pre_breakout_accumulation_reason':str(r.get('PreBreakoutAccumulationReason','')),'pre_move_confirmed':bit(r.get('PreMoveConfirmed')),'pre_move_confidence_tier':str(r.get('PreMoveConfidenceTier','')),'pre_move_family_count':num(r.get('PreMoveFamilyCount')),'pre_move_family_signature':str(r.get('PreMoveFamilySignature','')),'pre_move_baseline_guard':bit(r.get('PreMoveBaselineGuardOK')),'effective_volume_shock_ratio':num(r.get('EffectiveVolumeShockRatio')),'pre_move_shock_recovery':bit(r.get('PreMoveShockRecoveryOK')),'pre_move_flow_confirmation':bit(r.get('PreMoveFlowConfirmation')),'pre_move_momentum_confirmation':bit(r.get('PreMoveMomentumConfirmation')),'pre_move_baseline_turnover':num(r.get('PreMoveBaselineTurnover')),'volume_regime_ratio':num(r.get('VolumeRegimeRatio')),'volume_shock_ratio':num(r.get('VolumeShockRatio')),'volume_shock_date':str(r.get('VolumeShockDate','')),'volume_shock_return_pct':num(r.get('VolumeShockReturnPct')),'absorption_candidate':bit(r.get('AbsorptionCandidate')),'volume_persistence_ratio':num(r.get('VolumePersistenceRatio')),'price_retention_since_volume_shock_pct':num(r.get('PriceRetentionSinceVolumeShockPct')),'pre_breakout_higher_low_count':num(r.get('PreBreakoutHigherLowCount')),'pre_breakout_regime_shift':bit(r.get('PreBreakoutRegimeShift')),'pre_move_pattern_strength':str(r.get('PreMovePatternStrength','')),'pre_move_actionable_now':bit(r.get('PreMoveActionableNow')),'pre_move_actionability_state':str(r.get('PreMoveActionabilityState','')),'pre_move_actionability_reason':str(r.get('PreMoveActionabilityReason','')),'session_calendar_source':str(r.get('SessionCalendarSource','')),'session_calendar_reason':str(r.get('SessionCalendarReason','')),'session_freshness_verified':bit(r.get('SessionFreshnessVerified')),
            }
            _prof=_feedback_recommendation_profile_v63962(r)
            rec.update({'decision_display_stage':str(r.get('DecisionDisplayStage',_prof['decision_stage'])),'effective_decision_stage':str(r.get('EffectiveDecisionStage',_prof['decision_stage'])),'recommendation_type':_prof['decision_stage'],'recommendation_text':str(r.get('RecommendedAction','')),'entry_path':_prof['entry_path'],'continuation_entry_state':_prof['continuation'],'retest_status':_prof['retest'],'pre_move_radar_status':str(r.get('PreMoveRadarStatus',_prof['research_layer']))})
            cols=list(rec.keys());vals=[rec[c] for c in cols];ph=','.join(['?']*len(cols))
            con.execute(f"INSERT OR REPLACE INTO snapshots({','.join(cols)}) VALUES({ph})",vals)
            _signal_memory_persist_v63955(con,r,ts)
            if _event_role=='ORIGIN' and _origin_id is None:
                _rid=con.execute('SELECT id FROM snapshots WHERE scan_id=? AND ticker=? LIMIT 1',(str(scan_id),str(r.get('Ticker','')))).fetchone()
                if _rid:con.execute('UPDATE snapshots SET event_origin_snapshot_id=? WHERE id=?',(int(_rid[0]),int(_rid[0])))
        con.commit();con.close();_feedback_schedule_remote_push_v630()
    except Exception:
        pass


def _feedback_import_scanner_workbook_v639(uploaded):
    """Import an exported Scanner workbook as an idempotent Feedback snapshot.

    This is a recovery path for users who kept Scanner XLSX files but lost the
    ephemeral Streamlit host database. Original workbook fields are preserved.
    """
    try:
        name=str(getattr(uploaded,'name','scanner.xlsx') or 'scanner.xlsx')
        raw=uploaded.getvalue() if hasattr(uploaded,'getvalue') else bytes(uploaded)
        xls=pd.ExcelFile(BytesIO(raw))
        if 'Scanner Results' not in xls.sheet_names:
            return False,f'{name}: missing Scanner Results sheet',0
        df=pd.read_excel(xls,'Scanner Results')
        if df is None or df.empty or 'Ticker' not in df.columns:
            return False,f'{name}: no Scanner rows found',0
        meta={}
        if 'About' in xls.sheet_names:
            ab=pd.read_excel(xls,'About')
            if {'Field','Value'}.issubset(ab.columns):
                meta={str(k).strip():v for k,v in zip(ab['Field'],ab['Value'])}
        generated=meta.get('Generated')
        ts=pd.to_datetime(generated,errors='coerce') if generated is not None else pd.NaT
        if pd.isna(ts):
            # Filename fallback: ..._YYYYMMDD_HHMM.xlsx. Scanner exports are
            # generated on the Streamlit host; historical project files used UTC.
            import re
            m=re.search(r'(20\d{6})[_-](\d{4})',name)
            ts=pd.to_datetime((m.group(1)+m.group(2)) if m else None,format='%Y%m%d%H%M',errors='coerce')
        if pd.isna(ts):ts=pd.Timestamp.utcnow()
        if getattr(ts,'tzinfo',None) is None:ts=ts.tz_localize('UTC')
        else:ts=ts.tz_convert('UTC')
        ts_utc=ts.floor('s').isoformat().replace('+00:00','Z')
        def meta_num(key,default):
            try:
                v=float(meta.get(key,default));return v if np.isfinite(v) else default
            except Exception:return default
        horizon=int(round(meta_num('Forecast horizon days',5)))
        target_pct=meta_num('Target %',6.0)
        scan_mode=str(meta.get('Scan mode','IMPORTED SCANNER') or 'IMPORTED SCANNER')
        scan_id=f"import::{name}::{ts_utc}"
        # Recreate V6.3.9 research timing tags when older exports predate them,
        # while never changing the original historical TradeStage.
        if 'Market' not in df.columns:df['Market']=df['Ticker'].map(lambda x:_market_for_ticker_v612(x))
        if 'RawEntryTriggerState' not in df.columns:df['RawEntryTriggerState']=df.get('EntryTriggerState',df.get('TradeStage','WAIT'))
        if 'EntryTriggerState' not in df.columns:df['EntryTriggerState']=df.get('TradeStage','WAIT')
        if 'TradeStage' not in df.columns:df['TradeStage']=df['EntryTriggerState']
        if 'EntryActionabilityState' not in df.columns:
            df['EntryActionabilityState']=df['TradeStage']
        if 'EvidenceConfirmationGate' not in df.columns:df['EvidenceConfirmationGate']='LEGACY / NOT RECORDED'
        if 'ArmedTimingClass' not in df.columns or 'ArmedTimingReason' not in df.columns:
            tags=df.apply(_armed_timing_class_v639,axis=1,result_type='expand');tags.columns=['_armed_class','_armed_reason']
            if 'ArmedTimingClass' not in df.columns:df['ArmedTimingClass']=tags['_armed_class']
            if 'ArmedTimingReason' not in df.columns:df['ArmedTimingReason']=tags['_armed_reason']
        cfg={'horizon':horizon,'target':target_pct/100.0,'scan_mode':scan_mode,'_snapshot_ts_utc':ts_utc,'_snapshot_source':f'IMPORTED XLSX: {name}','_app_version':str(meta.get('Version','LEGACY / UNKNOWN') or 'LEGACY / UNKNOWN'),'_preserve_imported_fields':True}
        con=_feedback_conn_v600();before=int(con.execute('SELECT COUNT(*) FROM snapshots WHERE scan_id=?',(scan_id,)).fetchone()[0]);con.close()
        _feedback_store_scan_v600(scan_id,df,cfg)
        con=_feedback_conn_v600();after=int(con.execute('SELECT COUNT(*) FROM snapshots WHERE scan_id=?',(scan_id,)).fetchone()[0]);con.close()
        added=max(0,after-before)
        note='' if 'Forecast horizon days' in meta else ' • legacy file had no saved forecast horizon; imported as 5D'
        return True,f'{name}: {after} snapshot rows available ({added} newly added){note}',added
    except Exception as e:
        return False,f'{getattr(uploaded,"name","scanner.xlsx")}: {type(e).__name__}: {e}',0


def _resolve_first_event_intraday_v610(ticker,event_date,target1,invalidation):
    """Resolve target-vs-invalidation order inside an ambiguous daily candle.
    Prefer 15m; fall back to 1h. If both levels occur in one intraday bar, remain ambiguous.
    """
    for interval in ('15m','1h'):
        try:
            q=confirmed_intraday_bars(fetch_ohlcv(str(ticker),'1mo',interval))
            if q is None or q.empty:continue
            idx=pd.DatetimeIndex(q.index)
            mask=np.array([x.date()==event_date for x in idx])
            day=q.loc[mask]
            if day.empty:continue
            for _,bar in day.iterrows():
                ht=bool(np.isfinite(target1) and float(bar.High)>=target1)
                hi=bool(np.isfinite(invalidation) and float(bar.Low)<=invalidation)
                if ht and hi:return f'AMBIGUOUS SAME {interval.upper()} BAR'
                if hi:return f'INVALIDATION FIRST ({interval})'
                if ht:return f'TARGET1 FIRST ({interval})'
        except Exception:
            continue
    return 'AMBIGUOUS SAME DAY — INTRADAY UNAVAILABLE'


def _feedback_evaluate_due_v600(max_snapshots=30):
    """Evaluate due 1D/2D/3D/5D outcomes. Runs safely in the background after scans."""
    try:
        con=_feedback_conn_v600(); snap=pd.read_sql_query("SELECT s.* FROM snapshots s LEFT JOIN outcomes o ON o.snapshot_id=s.id GROUP BY s.id HAVING COUNT(DISTINCT o.horizon)<4 ORDER BY s.id ASC LIMIT 50000",con)
        # V6.1.1 migration: revisit old daily-ambiguous outcomes and resolve event order
        # with 15m/1h bars when those bars are still available from the provider.
        try:
            amb=pd.read_sql_query("SELECT o.snapshot_id,o.horizon,o.first_event,s.ticker,s.target1,s.invalidation,s.ts_utc FROM outcomes o JOIN snapshots s ON s.id=o.snapshot_id WHERE o.first_event LIKE 'AMBIGUOUS SAME DAY%' ORDER BY o.evaluated_at DESC LIMIT 120",con)
            for _,ar in amb.iterrows():
                try:
                    market0=_market_for_ticker_v612(str(ar.ticker)); scan_date=_snapshot_market_date_v612(ar.ts_utc,market0,str(ar.ticker)); d0=fetch_ohlcv(str(ar.ticker),'1mo','1d')
                    if d0 is None or d0.empty:continue
                    z0=d0.copy(); future0=_completed_future_daily_bars_v612(z0,scan_date,market0,int(ar.horizon))
                    t1=float(ar.target1) if pd.notna(ar.target1) else np.nan; inv=float(ar.invalidation) if pd.notna(ar.invalidation) else np.nan
                    for _,bar0 in future0.iterrows():
                        ht=bool(np.isfinite(t1) and float(bar0.High)>=t1); hi=bool(np.isfinite(inv) and float(bar0.Low)<=inv)
                        if ht and hi:
                            resolved=_resolve_first_event_intraday_v610(str(ar.ticker),pd.Timestamp(bar0.name).date(),t1,inv)
                            con.execute('UPDATE outcomes SET first_event=? WHERE snapshot_id=? AND horizon=?',(resolved,int(ar.snapshot_id),int(ar.horizon)));break
                        if hi:
                            con.execute('UPDATE outcomes SET first_event=? WHERE snapshot_id=? AND horizon=?',('INVALIDATION FIRST (daily)',int(ar.snapshot_id),int(ar.horizon)));break
                        if ht:
                            con.execute('UPDATE outcomes SET first_event=? WHERE snapshot_id=? AND horizon=?',('TARGET1 FIRST (daily)',int(ar.snapshot_id),int(ar.horizon)));break
                except Exception:continue
            con.commit()
        except Exception:pass
        done=pd.read_sql_query('SELECT snapshot_id,horizon FROM outcomes',con)
        done_set=set(zip(done.snapshot_id.astype(int),done.horizon.astype(int))) if not done.empty else set()
        evaluated=0
        for _,r in snap.iterrows():
            if evaluated>=max_snapshots:break
            market=_feedback_market_key_v612(r.get('market',''),str(r.ticker))
            scan_date=_snapshot_market_date_v612(r.ts_utc,market,str(r.ticker))
            pending_h=[h for h in (1,2,3,5) if (int(r.id),h) not in done_set]
            if not pending_h:continue
            # Source of truth is the number of COMPLETE future exchange daily bars, not
            # elapsed calendar days. This prevents Saturday/Sunday/holidays from maturing 1D.
            d=fetch_ohlcv(str(r.ticker),'1mo','1d')
            if d is None or d.empty:continue
            z=d.copy(); completed=_completed_future_daily_bars_v612(z,scan_date,market)
            if completed is None or completed.empty:continue
            due=[h for h in pending_h if len(completed)>=h]
            if not due:continue
            for h in due:
                future=completed.head(h)
                if len(future)<h:continue
                base=float(r.price) if pd.notna(r.price) else np.nan
                if not np.isfinite(base) or base<=0:continue
                endret=float(future.Close.iloc[-1]/base-1); mfe=float(future.High.max()/base-1); mae=float(future.Low.min()/base-1)
                t1=float(r.target1) if pd.notna(r.target1) else np.nan; t2=float(r.target2) if pd.notna(r.target2) else np.nan; inv=float(r.invalidation) if pd.notna(r.invalidation) else np.nan
                t1h=bool(np.isfinite(t1) and (future.High>=t1).any()); t2h=bool(np.isfinite(t2) and (future.High>=t2).any()); invh=bool(np.isfinite(inv) and (future.Low<=inv).any())
                first='NONE'
                for _,bar in future.iterrows():
                    hit_t=bool(np.isfinite(t1) and float(bar.High)>=t1); hit_i=bool(np.isfinite(inv) and float(bar.Low)<=inv)
                    if hit_t and hit_i:first=_resolve_first_event_intraday_v610(str(r.ticker),pd.Timestamp(bar.name).date(),t1,inv); break
                    if hit_i:first='INVALIDATION FIRST (daily)'; break
                    if hit_t:first='TARGET1 FIRST (daily)'; break
                con.execute('INSERT OR REPLACE INTO outcomes VALUES(?,?,?,?,?,?,?,?,?,?)',(int(r.id),h,datetime.utcnow().replace(microsecond=0).isoformat()+'Z',endret,mfe,mae,int(t1h),int(t2h),int(invh),first))
                con.commit(); evaluated+=1; done_set.add((int(r.id),h))
                if evaluated>=max_snapshots:break
        con.close()
        if evaluated:_feedback_schedule_remote_push_v630()
        return evaluated
    except Exception:return 0


def _feedback_frames_v600():
    try:
        con=_feedback_conn_v600(); sn=pd.read_sql_query('SELECT * FROM snapshots ORDER BY id DESC',con); oc=pd.read_sql_query('SELECT * FROM outcomes ORDER BY evaluated_at DESC',con); con.close(); sn=_feedback_apply_event_integrity_v63934(sn); return sn,oc
    except Exception:return pd.DataFrame(),pd.DataFrame()


def _feedback_replay_active_indicators_v630(r):
    """Causal DAILY indicator states used by Historical Replay.

    V6.3.1 keeps each state observable at the historical signal close.  These are
    research features only; unavailable historical 15m/1h confirmations are never
    fabricated.
    """
    def fin(k,default=np.nan):
        try:
            x=float(r.get(k,default));return x if np.isfinite(x) else default
        except Exception:return default
    p=fin('Close');e9=fin('ema9');e20=fin('ema20');vw=fin('vwap');mh=fin('macd_hist');ms=fin('macd_hist_slope')
    rv=fin('time_adjusted_rvol',fin('robust_volume_ratio'));va=fin('vol_accel');cmf=fin('cmf20');obv=fin('obv_slope5');ad=fin('ad_slope5');rs=fin('rs20');rsi=fin('rsi14');cl=fin('close_location');adx=fin('adx14');br=fin('breakout20_pct');ft=fin('fresh_transition_count',0)
    try:dv=directional_volume_row(r) or {}
    except Exception:dv={}
    bull=float(dv.get('bullish',0) or 0);bear=float(dv.get('bearish',0) or 0)
    states=[
        ('EMA9/20 bullish cross',fin('ema9_cross_up',0)>0),
        ('MACD bullish cross',fin('macd_cross_up',0)>0),
        ('MACD histogram turn positive',fin('macd_hist_turn_pos',0)>0),
        ('VWAP reclaim',fin('vwap_cross_up',0)>0),
        ('EMA9 > EMA20',np.isfinite(e9) and np.isfinite(e20) and e9>e20),
        ('Price > EMA20',np.isfinite(p) and np.isfinite(e20) and p>e20),
        ('Price > VWAP',np.isfinite(p) and np.isfinite(vw) and p>vw),
        ('MACD histogram positive',np.isfinite(mh) and mh>0),
        ('MACD strengthening',np.isfinite(ms) and ms>0),
        ('RSI 50-70',np.isfinite(rsi) and 50<=rsi<=70),
        ('RVOL >= 1.20',np.isfinite(rv) and rv>=1.20),
        ('Volume acceleration',np.isfinite(va) and va>=1.08),
        ('Directional bullish volume',bull>=.22 and bull>bear),
        ('CMF > 0',np.isfinite(cmf) and cmf>0),
        ('OBV accumulating',np.isfinite(obv) and obv>0),
        ('A/D accumulating',np.isfinite(ad) and ad>0),
        ('Relative strength positive',np.isfinite(rs) and rs>0),
        ('Near 20D breakout',np.isfinite(br) and -3.0<=br<=2.0),
        ('Strong close location',np.isfinite(cl) and cl>=.70),
        ('ADX >= 25',np.isfinite(adx) and adx>=25),
        ('Squeeze release',bool(fin('squeeze_release',0)>0)),
        ('Fresh transitions >= 2',ft>=2),
    ]
    return [name for name,on in states if bool(on)]


def _feedback_replay_setup_v631(r, target_pct, recent_2d_return=np.nan):
    """Daily-only proxy of the live two-layer logic, with correlated signals de-duped.

    No future bar is consulted.  It approximates Independent Families + Freshness +
    Already-Moved/Extension + directional distribution using only the signal close.
    """
    def fin(k,default=np.nan):
        try:
            x=float(r.get(k,default));return x if np.isfinite(x) else default
        except Exception:return default
    active=_feedback_replay_active_indicators_v630(r); aset=set(active)
    try:dv=directional_volume_row(r) or {}
    except Exception:dv={}
    bull=float(dv.get('bullish',0) or 0);bear=float(dv.get('bearish',0) or 0)
    p=fin('Close');e9=fin('ema9');e20=fin('ema20');vw=fin('vwap');atrp=fin('atr_pct');ret1=fin('ret1',0);rv=fin('time_adjusted_rvol',fin('robust_volume_ratio'));cl=fin('close_location',.5);cmf=fin('cmf20',0);obv=fin('obv_slope5',0);ad=fin('ad_slope5',0);ft=fin('fresh_transition_count',0)
    momentum=bool({'MACD bullish cross','MACD histogram turn positive','MACD strengthening','MACD histogram positive'} & aset)
    volume=bool({'RVOL >= 1.20','Volume acceleration'} & aset)
    flow=bool('Directional bullish volume' in aset or sum(x in aset for x in ('CMF > 0','OBV accumulating','A/D accumulating'))>=2)
    relative=bool('Relative strength positive' in aset)
    trend=bool(('EMA9 > EMA20' in aset and 'Price > EMA20' in aset) or 'ADX >= 25' in aset)
    structure=bool({'VWAP reclaim','Price > VWAP','Near 20D breakout','Strong close location','Squeeze release'} & aset)
    transition=bool(ft>=2 or {'EMA9/20 bullish cross','MACD bullish cross','MACD histogram turn positive','VWAP reclaim'} & aset)
    fam={'MOMENTUM':momentum,'VOLUME':volume,'FLOW':flow,'RELATIVE_STRENGTH':relative,'TREND':trend,'STRUCTURE':structure,'TRANSITION_BREADTH':transition}
    families=[k for k,v in fam.items() if v];family_count=len(families)
    target=max(float(target_pct),1e-6)
    recent2=float(recent_2d_return) if np.isfinite(recent_2d_return) else 0.0
    consumed=100.0*max(0.0,ret1,recent2)/target
    atr_abs=p*atrp/100.0 if np.isfinite(p) and np.isfinite(atrp) and atrp>0 else np.nan
    ext=[]
    if np.isfinite(atr_abs) and atr_abs>0:
        for ref in (e9,e20,vw):
            if np.isfinite(ref):ext.append(max(0.0,(p-ref)/atr_abs))
    extension=max(ext) if ext else np.nan
    if consumed>=100 or (np.isfinite(extension) and extension>=1.80):fresh='ALREADY MOVED'
    elif consumed>=60 or (np.isfinite(extension) and extension>=1.10):fresh='LATE'
    elif transition or 'Squeeze release' in aset:fresh='FRESH'
    else:fresh='DEVELOPING'
    distribution=bool((bear>=.22 and bear>bull) or ((ret1<0 and np.isfinite(rv) and rv>=1.20 and cl<.45) and (cmf<0 or obv<0 or ad<0)))
    core_momentum=momentum
    core_volume_flow=bool(volume or flow)
    score=12.0*family_count
    score+=8 if core_momentum else 0
    score+=8 if core_volume_flow else 0
    score+=8 if transition else 0
    score+=5 if relative else 0
    score+=5 if structure else 0
    if fresh=='FRESH':score+=8
    elif fresh=='LATE':score-=22
    elif fresh=='ALREADY MOVED':score-=38
    if distribution:score-=28
    score=float(np.clip(score,0,100))
    candidate_v2=bool(score>=62 and family_count>=3 and core_momentum and core_volume_flow and fresh in ('FRESH','DEVELOPING') and not distribution and consumed<60 and (not np.isfinite(extension) or extension<1.10))
    return {'active':active,'families':families,'family_signature':' + '.join(families),'family_count':family_count,'freshness_state':fresh,'move_consumed_pct':consumed,'extension_atr':extension,'distribution_risk':distribution,'setup_score_v2':score,'candidate_v2':candidate_v2,'core_momentum':core_momentum,'core_volume_flow':core_volume_flow}



def _feedback_replay_indicator_family_v633(name):
    """Map correlated DAILY indicators to one independent research family."""
    m={
        'MACD bullish cross':'MOMENTUM','MACD histogram turn positive':'MOMENTUM','MACD histogram positive':'MOMENTUM','MACD strengthening':'MOMENTUM','RSI 50-70':'MOMENTUM',
        'RVOL >= 1.20':'VOLUME','Volume acceleration':'VOLUME',
        'Directional bullish volume':'FLOW','CMF > 0':'FLOW','OBV accumulating':'FLOW','A/D accumulating':'FLOW',
        'Relative strength positive':'RELATIVE_STRENGTH',
        'EMA9 > EMA20':'TREND','Price > EMA20':'TREND','ADX >= 25':'TREND',
        'VWAP reclaim':'STRUCTURE','Price > VWAP':'STRUCTURE','Near 20D breakout':'STRUCTURE','Strong close location':'STRUCTURE','Squeeze release':'STRUCTURE',
        'EMA9/20 bullish cross':'TRANSITION_BREADTH','Fresh transitions >= 2':'TRANSITION_BREADTH',
    }
    return m.get(str(name),'OTHER')


def _feedback_replay_combination_discovery_v633(events, discovery_fraction=.70, max_discovered=250):
    """Discovery-only combination search + untouched chronological OOS validation.

    Candidate combinations are selected only from the first 70% of signal dates.
    The final 30% is never used for selection and is split into three chronological
    validation folds. Correlated indicators from the same family cannot coexist in
    one combination. This is research-only and never changes Production Entry.
    """
    e=events.copy() if isinstance(events,pd.DataFrame) else pd.DataFrame()
    empty=(pd.DataFrame(),pd.DataFrame(),pd.DataFrame(),e)
    if e.empty:return empty
    ren={'CleanOutcome':'clean_outcome','Indicators':'indicators','Ticker':'ticker','SignalDate':'signal_date','CandidateV2':'candidate_v2','RMultiple':'r_multiple',
         'FreshnessState':'freshness_state','MoveConsumedPct':'move_consumed_pct','ExtensionATR':'extension_atr','DistributionRisk':'distribution_risk'}
    for a,b in ren.items():
        if a in e and b not in e:e[b]=e[a]
    e['_date']=pd.to_datetime(e.get('signal_date'),errors='coerce')
    e['_win']=e.get('clean_outcome',pd.Series('',index=e.index)).astype(str).map({'WIN':1.0,'LOSS':0.0})
    dates=sorted(pd.Series(e.loc[e['_date'].notna(),'_date'].dt.normalize().unique()).dropna().tolist())
    if len(dates)<8:return empty
    split=max(1,min(len(dates)-1,int(math.floor(len(dates)*float(discovery_fraction)))))
    cutoff=pd.Timestamp(dates[split-1]);val_dates=[pd.Timestamp(x) for x in dates[split:]]
    e['ComboPhase']=np.where(e['_date'].dt.normalize()<=cutoff,'DISCOVERY','OOS VALIDATION')
    fresh=e.get('freshness_state',pd.Series('',index=e.index)).fillna('').astype(str).isin(['FRESH','DEVELOPING'])
    consumed=pd.to_numeric(e.get('move_consumed_pct',np.nan),errors='coerce')
    ext=pd.to_numeric(e.get('extension_atr',np.nan),errors='coerce')
    dist=pd.to_numeric(e.get('distribution_risk',0),errors='coerce').fillna(0).eq(1)
    clean=np.isfinite(pd.to_numeric(e['_win'],errors='coerce'))
    eligible=clean & fresh & (~dist) & ((~np.isfinite(consumed)) | (consumed<60)) & ((~np.isfinite(ext)) | (ext<1.10))
    disc=eligible & e['ComboPhase'].eq('DISCOVERY'); val=eligible & e['ComboPhase'].eq('OOS VALIDATION')
    dn=int(disc.sum());vn=int(val.sum())
    if dn<100 or vn<40:return empty
    dbase=float(e.loc[disc,'_win'].mean());vbase=float(e.loc[val,'_win'].mean())

    def split_ind(txt):return [x.strip() for x in str(txt or '').split(' | ') if x.strip() and x.strip().lower()!='nan']
    ind_sets=[set(split_ind(x)) for x in e.get('indicators',pd.Series('',index=e.index)).fillna('').astype(str)]
    disc_idx=np.where(disc.to_numpy())[0];val_idx=np.where(val.to_numpy())[0]
    names=sorted({x for i in disc_idx for x in ind_sets[i] if _feedback_replay_indicator_family_v633(x)!='OTHER'})
    arrays={name:np.fromiter((name in ss for ss in ind_sets),dtype=bool,count=len(e)) for name in names}
    # Discovery-only pool reduction: sufficient occurrence, then at most the three
    # strongest univariate representatives per independent family. Validation is
    # never consulted while building this pool.
    uni=[]
    for name in names:
        m=disc.to_numpy() & arrays[name];n=int(m.sum())
        if n<35:continue
        rate=float(e.loc[m,'_win'].mean());delta=rate-dbase
        uni.append((name,_feedback_replay_indicator_family_v633(name),n,rate,delta,float(delta*math.log1p(n))))
    pool=[]
    for fam in sorted({x[1] for x in uni}):
        cand=sorted([x for x in uni if x[1]==fam],key=lambda x:(x[5],x[2]),reverse=True)[:3]
        pool.extend([x[0] for x in cand])
    pool=sorted(set(pool))
    if len(pool)<2:return empty

    min_disc=max(40,int(.0025*dn)); discovered=[]
    disc_np=disc.to_numpy();val_np=val.to_numpy();wins=e['_win'].to_numpy(float)
    tick=e.get('ticker',pd.Series('',index=e.index)).fillna('').astype(str).to_numpy()
    for k in (2,3,4):
        for combo in combinations(pool,k):
            fams=[_feedback_replay_indicator_family_v633(x) for x in combo]
            if len(set(fams))<k:continue
            m=disc_np.copy()
            for name in combo:m &= arrays[name]
            n=int(m.sum())
            if n<min_disc:continue
            rate=float(np.nanmean(wins[m]));lift=rate/dbase if dbase>0 else np.nan;delta=rate-dbase
            stocks=len(set(tick[m]))
            if stocks<8 or not np.isfinite(lift) or lift<1.08 or delta<.04:continue
            score=float((100*delta)*math.log1p(n)*(1+.08*(k-2)))
            discovered.append({'combo':combo,'families':fams,'n':n,'wins':int(np.nansum(wins[m])),'rate':rate,'lift':lift,'delta':delta,'stocks':stocks,'score':score})
    discovered=sorted(discovered,key=lambda x:(x['score'],x['n']),reverse=True)[:int(max_discovered)]
    if not discovered:return (pd.DataFrame(),pd.DataFrame(),pd.DataFrame([{'Gate':'OOS ELIGIBLE BASELINE','Resolved':vn,'Wins':int(np.nansum(wins[val_np])),'Losses':vn-int(np.nansum(wins[val_np])),'Success Rate %':100*vbase,'Lift vs OOS baseline x':1.0,'Expectancy R':pd.to_numeric(e.loc[val,'r_multiple'],errors='coerce').mean(),'Meaning':'Fresh/not-extended/no-distribution OOS rows'}]),e.drop(columns=['_date','_win'],errors='ignore'))

    # Three untouched chronological OOS folds.
    fold_groups=[list(x) for x in np.array_split(np.array(val_dates,dtype='datetime64[ns]'),3) if len(x)]
    combo_rows=[];fold_rows=[]
    top_candidate=discovered[:25]
    hc_discovery=[x for x in discovered if x['n']>=60 and x['rate']>=max(.60,dbase+.08) and x['lift']>=1.15 and x['stocks']>=10]
    tier70=[x for x in discovered if x['n']>=40 and x['rate']>=.70 and x['lift']>=1.25 and x['stocks']>=8]
    row_match=np.zeros(len(e),dtype=int);row_hc=np.zeros(len(e),dtype=bool);row_70=np.zeros(len(e),dtype=bool)
    best_rate=np.full(len(e),np.nan);best_lift=np.full(len(e),np.nan);best_sig=np.array(['']*len(e),dtype=object)

    def cmask(combo,base_mask=None):
        m=np.ones(len(e),dtype=bool) if base_mask is None else base_mask.copy()
        for name in combo:m &= arrays[name]
        return m
    top_set={x['combo'] for x in top_candidate};hc_set={x['combo'] for x in hc_discovery};tier70_set={x['combo'] for x in tier70}
    for rank,x in enumerate(discovered,1):
        m_all=cmask(x['combo']);mv=val_np & m_all;n=int(mv.sum());wr=int(np.nansum(wins[mv])) if n else 0;rate=float(np.nanmean(wins[mv])) if n else np.nan
        lift=rate/vbase if n and vbase>0 else np.nan;delta=rate-vbase if n else np.nan;vstocks=len(set(tick[mv])) if n else 0
        pos=0;usable=0
        sig=' + '.join(x['combo'])
        for fi,fd in enumerate(fold_groups,1):
            fd_norm={pd.Timestamp(q).normalize() for q in fd}
            fm=val_np & e['_date'].dt.normalize().isin(fd_norm).to_numpy();fbn=int(fm.sum());fb=float(np.nanmean(wins[fm])) if fbn else np.nan
            mm=fm & m_all;fn=int(mm.sum());fw=int(np.nansum(wins[mm])) if fn else 0;fr=float(np.nanmean(wins[mm])) if fn else np.nan;fl=fr/fb if fn and np.isfinite(fb) and fb>0 else np.nan;dd=fr-fb if fn and np.isfinite(fb) else np.nan
            if fn>=10:
                usable+=1
                if np.isfinite(fl) and fl>=1.03 and np.isfinite(dd) and dd>0:pos+=1
            fold_rows.append({'Combination':sig,'Fold':fi,'Resolved':fn,'Wins':fw,'Success Rate %':100*fr if np.isfinite(fr) else np.nan,'Fold Baseline %':100*fb if np.isfinite(fb) else np.nan,'Lift x':fl,'Delta pp':100*dd if np.isfinite(dd) else np.nan,'Stocks':len(set(tick[mm])) if fn else 0})
        gap=100*abs(rate-x['rate']) if n and np.isfinite(rate) else np.nan
        if n<25:status='LOW SAMPLE'
        elif np.isfinite(lift) and lift>=1.15 and delta>=.05 and pos>=2:status='OOS STRONG'
        elif np.isfinite(lift) and lift>=1.08 and delta>=.03 and pos>=2:status='OOS POSITIVE'
        elif np.isfinite(lift) and (lift<=.95 or delta<=-.02):status='FAILED'
        else:status='OOS MIXED'
        tier='70% DISCOVERY TIER' if x['combo'] in tier70_set else ('HIGH-CONFIDENCE DISCOVERY' if x['combo'] in hc_set else 'DISCOVERED')
        combo_rows.append({'Discovery Rank':rank,'Combination':sig,'Size':len(x['combo']),'Families':' + '.join(x['families']),'Discovery N':x['n'],'Discovery Wins':x['wins'],'Discovery Success %':100*x['rate'],'Discovery Baseline %':100*dbase,'Discovery Lift x':x['lift'],'Discovery Delta pp':100*x['delta'],'Discovery Stocks':x['stocks'],'Discovery Score':x['score'],'Validation N':n,'Validation Wins':wr,'Validation Success %':100*rate if np.isfinite(rate) else np.nan,'Validation Baseline %':100*vbase,'Validation Lift x':lift,'Validation Delta pp':100*delta if np.isfinite(delta) else np.nan,'Validation Stocks':vstocks,'Positive Validation Folds':pos,'Usable Validation Folds':usable,'Stability Gap pp':gap,'Research Tier':tier,'OOS Status':status})
        if x['combo'] in top_set:
            match=val_np & m_all;row_match[match]+=1
            better=match & ((~np.isfinite(best_rate)) | (100*x['rate']>best_rate))
            best_rate[better]=100*x['rate'];best_lift[better]=x['lift'];best_sig[better]=sig
        if x['combo'] in hc_set:row_hc |= (val_np & m_all)
        if x['combo'] in tier70_set:row_70 |= (val_np & m_all)

    e['ComboCandidateV3']=val_np & (row_match>0);e['ComboHighConfidenceV3']=row_hc;e['Combo70Research']=row_70;e['ComboMatchCount']=row_match;e['ComboBestSignature']=best_sig;e['ComboBestDiscoveryRate']=best_rate;e['ComboBestDiscoveryLift']=best_lift
    # OOS gate comparison uses only the untouched validation section.
    def gate(label,mask,meaning):
        m=val_np & mask;n=int(m.sum());w=int(np.nansum(wins[m])) if n else 0;rate=float(np.nanmean(wins[m])) if n else np.nan
        rr=pd.to_numeric(e.loc[m,'r_multiple'],errors='coerce').mean() if n else np.nan
        return {'Gate':label,'Resolved':n,'Wins':w,'Losses':n-w,'Success Rate %':100*rate if np.isfinite(rate) else np.nan,'Lift vs OOS baseline x':rate/vbase if np.isfinite(rate) and vbase>0 else np.nan,'Delta vs OOS baseline pp':100*(rate-vbase) if np.isfinite(rate) else np.nan,'Expectancy R':rr,'Meaning':meaning}
    v2=pd.to_numeric(e.get('candidate_v2',0),errors='coerce').fillna(0).eq(1).to_numpy()
    gate_rows=[gate('OOS ELIGIBLE BASELINE',np.ones(len(e),bool),'Fresh/not-extended/no-distribution rows in untouched final 30%'),gate('OOS V2 CANDIDATE',v2,'Existing V2 gate, evaluated only in untouched final 30%'),gate('OOS COMBO V3',row_match>0,'Top 25 combinations selected only in Discovery'),gate('OOS COMBO HIGH CONFIDENCE',row_hc,'Discovery-only >=60% / lift >=1.15 / sample+breadth gate'),gate('OOS 70% RESEARCH TIER',row_70,'Combinations that reached >=70% in Discovery; OOS result is not used to select them')]
    combo_df=pd.DataFrame(combo_rows)
    if not combo_df.empty:
        order={'OOS STRONG':0,'OOS POSITIVE':1,'OOS MIXED':2,'FAILED':3,'LOW SAMPLE':4};combo_df['_o']=combo_df['OOS Status'].map(order).fillna(9);combo_df=combo_df.sort_values(['_o','Validation Lift x','Validation N','Discovery Rank'],ascending=[True,False,False,True]).drop(columns=['_o']).reset_index(drop=True)
    return combo_df,pd.DataFrame(fold_rows),pd.DataFrame(gate_rows),e.drop(columns=['_date','_win'],errors='ignore')


def _feedback_replay_market_consensus_v634(events):
    """Market-specific nested 60/20/20 consensus research.

    The first 60% of dates discover independent-family combinations.  The next
    20% is the *selector* period used to decide which combinations are stable.
    The final 20% remains untouched until the consensus gate is evaluated.
    Therefore the final holdout is not used either to discover or promote a
    combination.  This is research-only and never changes Production Entry.
    """
    e=events.copy() if isinstance(events,pd.DataFrame) else pd.DataFrame()
    if e.empty:return pd.DataFrame(),pd.DataFrame(),e
    ren={'CleanOutcome':'clean_outcome','Indicators':'indicators','Ticker':'ticker','SignalDate':'signal_date','Market':'market','RMultiple':'r_multiple',
         'FreshnessState':'freshness_state','MoveConsumedPct':'move_consumed_pct','ExtensionATR':'extension_atr','DistributionRisk':'distribution_risk'}
    for a,b in ren.items():
        if a in e and b not in e:e[b]=e[a]
    e['_date634']=pd.to_datetime(e.get('signal_date'),errors='coerce')
    e['_win634']=e.get('clean_outcome',pd.Series('',index=e.index)).astype(str).map({'WIN':1.0,'LOSS':0.0})
    fresh=e.get('freshness_state',pd.Series('',index=e.index)).fillna('').astype(str).isin(['FRESH','DEVELOPING'])
    consumed=pd.to_numeric(e.get('move_consumed_pct',np.nan),errors='coerce');ext=pd.to_numeric(e.get('extension_atr',np.nan),errors='coerce')
    dist=pd.to_numeric(e.get('distribution_risk',0),errors='coerce').fillna(0).eq(1)
    clean=np.isfinite(pd.to_numeric(e['_win634'],errors='coerce'))
    eligible=clean & fresh & (~dist) & ((~np.isfinite(consumed)) | (consumed<60)) & ((~np.isfinite(ext)) | (ext<1.10))
    e['ConsensusPhaseV634']='NOT USED';e['ConsensusMatchCountV634']=0;e['ConsensusFamilyCountV634']=0;e['ConsensusCandidateV634']=False

    def split_ind(txt):return [x.strip() for x in str(txt or '').split(' | ') if x.strip() and x.strip().lower()!='nan']
    ind_sets=[set(split_ind(x)) for x in e.get('indicators',pd.Series('',index=e.index)).fillna('').astype(str)]
    wins=e['_win634'].to_numpy(float);tick=e.get('ticker',pd.Series('',index=e.index)).fillna('').astype(str).to_numpy()
    market_series=e.get('market',pd.Series('',index=e.index)).fillna('').astype(str)
    markets=[x for x in market_series.unique().tolist() if x]
    if not markets:markets=['ALL']
    combo_rows=[];gate_rows=[]
    for market in markets:
        mm=np.ones(len(e),dtype=bool) if market=='ALL' else market_series.eq(market).to_numpy()
        date_ser=e.loc[mm & eligible,'_date634'].dropna().dt.normalize()
        dates=sorted(pd.Series(date_ser.unique()).dropna().tolist())
        if len(dates)<15:continue
        i60=max(1,min(len(dates)-2,int(math.floor(.60*len(dates)))));i80=max(i60+1,min(len(dates)-1,int(math.floor(.80*len(dates)))))
        d60=pd.Timestamp(dates[i60-1]);d80=pd.Timestamp(dates[i80-1])
        disc=mm & eligible.to_numpy() & (e['_date634'].dt.normalize()<=d60).to_numpy()
        selector=mm & eligible.to_numpy() & (e['_date634'].dt.normalize()>d60).to_numpy() & (e['_date634'].dt.normalize()<=d80).to_numpy()
        final=mm & eligible.to_numpy() & (e['_date634'].dt.normalize()>d80).to_numpy()
        dn,sn,fn=int(disc.sum()),int(selector.sum()),int(final.sum())
        if dn<80 or sn<25 or fn<25:continue
        db=float(np.nanmean(wins[disc]));sb=float(np.nanmean(wins[selector]));fb=float(np.nanmean(wins[final]))
        names=sorted({x for i in np.where(disc)[0] for x in ind_sets[i] if _feedback_replay_indicator_family_v633(x)!='OTHER'})
        arrays={name:np.fromiter((name in ss for ss in ind_sets),dtype=bool,count=len(e)) for name in names}
        uni=[]
        for name in names:
            m=disc & arrays[name];n=int(m.sum())
            if n<max(20,int(.004*dn)):continue
            rate=float(np.nanmean(wins[m]));delta=rate-db
            uni.append((name,_feedback_replay_indicator_family_v633(name),n,rate,delta,delta*math.log1p(n)))
        pool=[]
        for fam in sorted({x[1] for x in uni}):
            pool += [x[0] for x in sorted([q for q in uni if q[1]==fam],key=lambda q:(q[5],q[2]),reverse=True)[:2]]
        pool=sorted(set(pool)); discovered=[]
        for k in (2,3):
            for combo in combinations(pool,k):
                fams=tuple(_feedback_replay_indicator_family_v633(x) for x in combo)
                if len(set(fams))<k:continue
                m=disc.copy()
                for name in combo:m &= arrays[name]
                n=int(m.sum())
                if n<max(25,int(.003*dn)):continue
                rate=float(np.nanmean(wins[m]));lift=rate/db if db>0 else np.nan;delta=rate-db;stocks=len(set(tick[m]))
                if stocks<5 or not np.isfinite(lift) or lift<1.08 or delta<.035:continue
                discovered.append({'combo':combo,'families':fams,'dn':n,'dr':rate,'dl':lift,'score':delta*math.log1p(n),'stocks':stocks})
        discovered=sorted(discovered,key=lambda x:(x['score'],x['dn']),reverse=True)[:120]
        promoted=[]
        for x in discovered:
            m=selector.copy()
            for name in x['combo']:m &= arrays[name]
            n=int(m.sum());rate=float(np.nanmean(wins[m])) if n else np.nan;lift=rate/sb if n and sb>0 else np.nan;delta=rate-sb if n else np.nan
            if n>=12 and np.isfinite(lift) and lift>=1.08 and delta>=.03:
                z=dict(x);z.update({'sn':n,'sr':rate,'sl':lift,'sdelta':delta});promoted.append(z)
        promoted=sorted(promoted,key=lambda x:((x['sr']-sb)*math.log1p(x['sn']),x['sn']),reverse=True)
        # De-correlate by independent family signature: at most one promoted combo
        # per exact family set. This prevents three MACD variants from masquerading
        # as three independent votes.
        selected=[];seen_fams=set()
        for x in promoted:
            fs=tuple(sorted(x['families']))
            if fs in seen_fams:continue
            selected.append(x);seen_fams.add(fs)
            if len(selected)>=12:break
        final_count=np.zeros(len(e),dtype=int);final_family_sets=[set() for _ in range(len(e))]
        for x in selected:
            m=np.ones(len(e),dtype=bool)
            for name in x['combo']:m &= arrays[name]
            fm=final & m;n=int(fm.sum());rate=float(np.nanmean(wins[fm])) if n else np.nan;lift=rate/fb if n and fb>0 else np.nan
            status='FINAL STRONG' if n>=15 and np.isfinite(lift) and lift>=1.15 and rate-fb>=.05 else ('FINAL POSITIVE' if n>=10 and np.isfinite(lift) and lift>=1.05 and rate-fb>0 else ('LOW SAMPLE' if n<10 else 'FINAL MIXED'))
            combo_rows.append({'Market':market,'Combination':' + '.join(x['combo']),'Families':' + '.join(x['families']),'Discovery N':x['dn'],'Discovery Success %':100*x['dr'],'Discovery Lift x':x['dl'],'Selector N':x['sn'],'Selector Success %':100*x['sr'],'Selector Lift x':x['sl'],'Final Holdout N':n,'Final Holdout Success %':100*rate if np.isfinite(rate) else np.nan,'Final Holdout Lift x':lift,'Status':status})
            for idx in np.where(fm)[0]:
                final_count[idx]+=1;final_family_sets[idx].update(x['families'])
        for idx in np.where(final)[0]:
            e.at[e.index[idx],'ConsensusPhaseV634']='FINAL 20% HOLDOUT';e.at[e.index[idx],'ConsensusMatchCountV634']=int(final_count[idx]);e.at[e.index[idx],'ConsensusFamilyCountV634']=len(final_family_sets[idx]);e.at[e.index[idx],'ConsensusCandidateV634']=bool(final_count[idx]>=2 and len(final_family_sets[idx])>=3)
        for idx in np.where(disc)[0]:e.at[e.index[idx],'ConsensusPhaseV634']='DISCOVERY 60%'
        for idx in np.where(selector)[0]:e.at[e.index[idx],'ConsensusPhaseV634']='SELECTOR 20%'
        def gate(label,mask,meaning):
            m=final & mask;n=int(m.sum());w=int(np.nansum(wins[m])) if n else 0;rate=float(np.nanmean(wins[m])) if n else np.nan
            rr=pd.to_numeric(e.loc[m,'r_multiple'],errors='coerce').mean() if n else np.nan
            return {'Market':market,'Gate':label,'Resolved':n,'Wins':w,'Losses':n-w,'Success Rate %':100*rate if np.isfinite(rate) else np.nan,'Final Baseline %':100*fb,'Lift x':rate/fb if np.isfinite(rate) and fb>0 else np.nan,'Delta pp':100*(rate-fb) if np.isfinite(rate) else np.nan,'Expectancy R':rr,'Stable combos selected':len(selected),'Meaning':meaning}
        gate_rows.append(gate('FINAL HOLDOUT BASELINE',np.ones(len(e),dtype=bool),'Untouched final 20% eligible rows'))
        gate_rows.append(gate('MARKET CONSENSUS 1+',final_count>=1,'At least one combo promoted on the middle selector period'))
        gate_rows.append(gate('MARKET CONSENSUS 2+',final_count>=2,'At least two promoted family-signature-distinct combinations agree'))
        gate_rows.append(gate('MARKET CONSENSUS 3+',final_count>=3,'At least three promoted family-signature-distinct combinations agree'))
    return pd.DataFrame(combo_rows),pd.DataFrame(gate_rows),e.drop(columns=['_date634','_win634'],errors='ignore')


def _explosive_benchmark_tables_v634(feat,ticker,target_pct=.15,horizons=(1,2,3,5)):
    """Causal single-stock +15% benchmark. No future information enters features."""
    f=feat.copy().dropna(subset=['Close']) if isinstance(feat,pd.DataFrame) else pd.DataFrame()
    if f.empty:return (pd.DataFrame(),)*6
    max_h=max(int(x) for x in horizons);rows=[]
    start=70
    for i in range(start,max(start,len(f)-max_h)):
        r=f.iloc[i];p=float(r.get('Close',np.nan))
        if not np.isfinite(p) or p<=0:continue
        recent2=float(p/float(f.iloc[i-2].Close)-1) if i>=2 and float(f.iloc[i-2].Close)>0 else np.nan
        setup=_feedback_replay_setup_v631(r,float(target_pct),recent2)
        sigdate=pd.Timestamp(f.index[i]);
        for h in horizons:
            future=f.iloc[i+1:i+1+int(h)]
            if len(future)<int(h):continue
            threshold=p*(1+float(target_pct));hit_rows=future[future['High']>=threshold]
            hit=not hit_rows.empty;hit_date=pd.Timestamp(hit_rows.index[0]) if hit else pd.NaT
            lead=None
            if hit:
                try:lead=int(list(future.index).index(hit_rows.index[0])+1)
                except Exception:lead=np.nan
            rows.append({'Ticker':str(ticker),'SignalDate':sigdate.date().isoformat(),'HorizonD':int(h),'TargetPct':100*float(target_pct),'Price':p,'Hit':int(hit),'HitDate':hit_date.date().isoformat() if hit else '',
                         'LeadSessions':lead,'MFEPct':100*float(future.High.max()/p-1),'EndReturnPct':100*float(future.Close.iloc[-1]/p-1),'Indicators':' | '.join(setup['active']),'Families':setup['family_signature'],
                         'IndependentFamilyCount':setup['family_count'],'FreshnessState':setup['freshness_state'],'MoveConsumedPct':setup['move_consumed_pct'],'ExtensionATR':setup['extension_atr'],'DistributionRisk':setup['distribution_risk'],'SetupScoreV2':setup['setup_score_v2']})
    ev=pd.DataFrame(rows)
    if ev.empty:return (pd.DataFrame(),)*6
    summary=[];ind_rows=[];combo_rows=[]
    def split_ind(txt):return [x.strip() for x in str(txt or '').split(' | ') if x.strip() and x.strip().lower()!='nan']
    for h,g in ev.groupby('HorizonD'):
        base=float(g.Hit.mean());summary.append({'Ticker':ticker,'HorizonD':int(h),'Sampled Dates':len(g),'Explosive Hits':int(g.Hit.sum()),'Base Hit Rate %':100*base,'Target %':100*float(target_pct)})
        names=sorted({x for txt in g.Indicators.fillna('').astype(str) for x in split_ind(txt)})
        for name in names:
            m=g.Indicators.fillna('').astype(str).apply(lambda txt:name in split_ind(txt));n=int(m.sum())
            if n<10:continue
            rate=float(g.loc[m,'Hit'].mean());lift=rate/base if base>0 else np.nan
            ind_rows.append({'HorizonD':int(h),'Indicator':name,'N':n,'Hits':int(g.loc[m,'Hit'].sum()),'Hit Rate %':100*rate,'Baseline %':100*base,'Lift x':lift,'Delta pp':100*(rate-base),'Family':_feedback_replay_indicator_family_v633(name),'Status':'PROMISING' if n>=15 and np.isfinite(lift) and lift>=1.30 and rate-base>=.03 else ('WEAK' if np.isfinite(lift) and lift<.90 else 'MIXED')})
    # Combo discovery is evaluated on the 5D horizon (or largest available) with a 70/30 split.
    h=max(int(x) for x in horizons);g=ev[ev.HorizonD.eq(h)].copy().sort_values('SignalDate').reset_index(drop=True)
    n=len(g);cut=max(1,min(n-1,int(.70*n)));disc=g.iloc[:cut].copy();val=g.iloc[cut:].copy();db=float(disc.Hit.mean()) if len(disc) else np.nan;vb=float(val.Hit.mean()) if len(val) else np.nan
    names=sorted({x for txt in disc.Indicators.fillna('').astype(str) for x in split_ind(txt)})
    sets=[set(split_ind(x)) for x in g.Indicators.fillna('').astype(str)];arrays={name:np.array([name in z for z in sets],dtype=bool) for name in names}
    uni=[]
    for name in names:
        m=arrays[name][:cut];nn=int(m.sum())
        if nn<12:continue
        rate=float(disc.loc[m,'Hit'].mean());uni.append((name,_feedback_replay_indicator_family_v633(name),nn,rate,(rate-db)*math.log1p(nn)))
    pool=[]
    for fam in sorted({x[1] for x in uni}):pool += [x[0] for x in sorted([u for u in uni if u[1]==fam],key=lambda q:(q[4],q[2]),reverse=True)[:2]]
    found=[]
    for k in (2,3):
        for combo in combinations(sorted(set(pool)),k):
            fams=[_feedback_replay_indicator_family_v633(x) for x in combo]
            if len(set(fams))<k:continue
            m=np.ones(cut,dtype=bool)
            for name in combo:m &= arrays[name][:cut]
            nn=int(m.sum())
            if nn<10:continue
            rate=float(disc.loc[m,'Hit'].mean());lift=rate/db if db>0 else np.nan
            if int(disc.loc[m,'Hit'].sum())<2 or not np.isfinite(lift) or lift<1.35:continue
            found.append((combo,fams,nn,rate,lift,(rate-db)*math.log1p(nn)))
    for combo,fams,nn,rate,lift,score in sorted(found,key=lambda x:(x[5],x[2]),reverse=True)[:60]:
        m=np.ones(len(val),dtype=bool)
        for name in combo:m &= arrays[name][cut:]
        vn=int(m.sum());vr=float(val.loc[m,'Hit'].mean()) if vn else np.nan;vl=vr/vb if vn and vb>0 else np.nan
        status='OOS PROMISING' if vn>=6 and np.isfinite(vl) and vl>=1.25 and vr-vb>=.03 else ('LOW SAMPLE' if vn<6 else 'OOS MIXED')
        combo_rows.append({'Combination':' + '.join(combo),'Families':' + '.join(fams),'Discovery N':nn,'Discovery Hit Rate %':100*rate,'Discovery Baseline %':100*db,'Discovery Lift x':lift,'Validation N':vn,'Validation Hit Rate %':100*vr if np.isfinite(vr) else np.nan,'Validation Baseline %':100*vb if np.isfinite(vb) else np.nan,'Validation Lift x':vl,'Status':status})
    # Cluster overlapping 5D hit rows into explosive episodes by hit-date proximity.
    hit5=g[g.Hit.eq(1)].copy();episodes=[]
    if not hit5.empty:
        hit5['_hd']=pd.to_datetime(hit5.HitDate,errors='coerce');hit5=hit5.dropna(subset=['_hd']).sort_values(['_hd','SignalDate'])
        grp=[];last=None;eid=0
        for _,r in hit5.iterrows():
            hd=pd.Timestamp(r['_hd'])
            if last is None or (hd-last).days>7:
                if grp:
                    eid+=1;gg=pd.DataFrame(grp);ear=gg.sort_values('SignalDate').iloc[0];best=gg.sort_values(['IndependentFamilyCount','SetupScoreV2'],ascending=False).iloc[0]
                    episodes.append({'Episode':eid,'Earliest Warning':ear.SignalDate,'Hit Date':ear.HitDate,'Lead Sessions':ear.LeadSessions,'Start Price':ear.Price,'Best Pre-Move Families':best.Families,'Best Pre-Move Indicators':best.Indicators,'Best Setup Score':best.SetupScoreV2,'Precursor Dates':len(gg)})
                grp=[]
            grp.append(r.to_dict());last=hd
        if grp:
            eid+=1;gg=pd.DataFrame(grp);ear=gg.sort_values('SignalDate').iloc[0];best=gg.sort_values(['IndependentFamilyCount','SetupScoreV2'],ascending=False).iloc[0]
            episodes.append({'Episode':eid,'Earliest Warning':ear.SignalDate,'Hit Date':ear.HitDate,'Lead Sessions':ear.LeadSessions,'Start Price':ear.Price,'Best Pre-Move Families':best.Families,'Best Pre-Move Indicators':best.Indicators,'Best Setup Score':best.SetupScoreV2,'Precursor Dates':len(gg)})
    ep=pd.DataFrame(episodes)
    recent=pd.DataFrame()
    if not ep.empty:
        hd=pd.to_datetime(ep['Hit Date'],errors='coerce');max_year=int(hd.dt.year.max()) if hd.notna().any() else None
        if max_year:recent=ep[(hd.dt.year.eq(max_year)) & (hd.dt.month.isin([8,9]))].copy()
    return pd.DataFrame(summary),pd.DataFrame(ind_rows),pd.DataFrame(combo_rows),ep,recent,ev


def _explosive_benchmark_worker_v634_legacy(runtime,jid,cfg):
    try:
        ticker=str(cfg.get('ticker','1196.HK')).strip().upper();history=str(cfg.get('history','1y'));target=float(cfg.get('target_pct',.15));horizons=tuple(int(x) for x in cfg.get('horizons',(1,2,3,5)))
        _lab_update_v603(runtime,jid,0,4,ticker,'Explosive Benchmark • fetching daily history');_lab_check_v603(runtime,jid)
        d=fetch_ohlcv(ticker,history,'1d')
        if d is None or len(d)<120:raise ValueError('Need at least 120 daily bars for Explosive Benchmark')
        f=compute_features(d).dropna(subset=['Close']).copy()
        if len(f)>1:f=f.iloc[:-1].copy()
        _lab_update_v603(runtime,jid,1,4,ticker,'Explosive Benchmark • causal +15% labels');_lab_check_v603(runtime,jid)
        summary,inds,combos,episodes,recent,events=_explosive_benchmark_tables_v634(f,ticker,target,horizons)
        _lab_update_v603(runtime,jid,2,4,ticker,'Explosive Benchmark • August/September audit');_lab_check_v603(runtime,jid)
        meta={'Tab':'Explosive Benchmark Lab','Version':APP_VERSION,'Ticker':ticker,'History':history,'TargetPct':100*target,'Horizons':'/'.join(str(x)+'D' for x in horizons),'Causality':'Features use signal-date close only; target labels use future bars afterward','ResearchOnly':'YES — single-stock benchmark; never promotes Production rules automatically'}
        _lab_update_v603(runtime,jid,3,4,ticker,'Explosive Benchmark • building workbook');_lab_check_v603(runtime,jid)
        excel=_feedback_workbook_v629({'Benchmark Summary':summary,'Explosive Episodes':episodes,'Aug-Sep Audit':recent,'Indicator Lift':inds,'Combination Discovery':combos,'All Causal Samples':events},meta)
        _lab_update_v603(runtime,jid,4,4,ticker,'Completed');_lab_publish_v603(runtime,jid,{'summary':summary,'indicators':inds,'combinations':combos,'episodes':episodes,'recent':recent,'events':events,'excel':excel,'ticker':ticker})
    except _LabCancelled:_lab_publish_v603(runtime,jid,None,'stopped')
    except Exception as ex:_lab_fail_v603(runtime,jid,ex)



def _explosive_prepare_features_v635(raw_daily,ticker):
    """Split-aware continuous OHLCV for explosive research.

    The live provider normally returns adjusted history, but some corporate actions
    can temporarily leave a multiplicative price-scale break.  For research labels
    we normalize only confirmed/very-high-confidence split-like breaks, recompute all
    indicators on the continuous series, and quarantine unexplained giant gaps.
    """
    d=raw_daily.copy() if isinstance(raw_daily,pd.DataFrame) else pd.DataFrame()
    if d.empty:return pd.DataFrame(),pd.DataFrame()
    need=['Open','High','Low','Close','Volume']
    if any(c not in d.columns for c in need):return pd.DataFrame(),pd.DataFrame()
    d=d[need].copy().sort_index()
    for c in need:d[c]=pd.to_numeric(d[c],errors='coerce')
    d=d.dropna(subset=['Open','High','Low','Close'])
    if d.empty:return pd.DataFrame(),pd.DataFrame()
    explicit=[]
    try: explicit=fetch_recent_split_events(str(ticker).upper(),1500) or []
    except Exception: explicit=[]
    exp=[]
    for x in explicit:
        try: exp.append((pd.Timestamp(x.get('date')).date(),float(x.get('ratio',np.nan))))
        except Exception: pass
    close=d['Close'].to_numpy(float); n=len(d)
    factors=np.array([0.1,0.2,0.25,1/3,0.5,2,3,4,5,10],dtype=float)
    price_scale=np.ones(n,dtype=float); action=np.zeros(n,dtype=bool); suspect=np.zeros(n,dtype=bool); reason=['']*n
    scale=1.0
    for i in range(1,n):
        r=close[i]/close[i-1] if np.isfinite(close[i]) and np.isfinite(close[i-1]) and close[i-1]>0 else np.nan
        nearest=np.nan; near=False
        if np.isfinite(r) and r>0:
            nearest=float(factors[np.argmin(np.abs(np.log(factors)-np.log(r)))])
            near=abs(r/nearest-1.0)<=0.10 and abs(r-1.0)>=0.35
        dt=pd.Timestamp(d.index[i]).date()
        explicit_match=False; explicit_ratio=np.nan
        for ed,er in exp:
            if abs((dt-ed).days)<=2:
                explicit_match=True;explicit_ratio=er;break
        # Exact/near split metadata is strongest evidence.  Without metadata we
        # only auto-normalize very large 3x+ or <=1/3 scale breaks; 2x real moves
        # are quarantined instead of silently rewritten.
        high_conf_heuristic=bool(near and (nearest>=3 or nearest<=1/3))
        if near and (explicit_match or high_conf_heuristic):
            scale/=nearest;action[i]=True
            reason[i]=f"split-scale normalized observed={r:.4g} factor={nearest:g}" + (f" metadata={explicit_ratio:g}" if np.isfinite(explicit_ratio) else '')
        elif np.isfinite(r) and (r>=1.80 or r<=0.55):
            suspect[i]=True;reason[i]=f"unexplained giant close gap {100*(r-1):.1f}%"
        price_scale[i]=scale
    # forward-fill cumulative scale
    for i in range(1,n):
        if price_scale[i]==1.0 and price_scale[i-1]!=1.0 and not action[i]:price_scale[i]=price_scale[i-1]
    norm=d.copy()
    for c in ('Open','High','Low','Close'):norm[c]=d[c].to_numpy(float)*price_scale
    # Share volume moves inversely to price scale on a split.
    inv=np.where(np.abs(price_scale)>1e-12,1.0/price_scale,1.0)
    norm['Volume']=d['Volume'].to_numpy(float)*inv
    feat=compute_features(norm).copy()
    feat['RawOpen']=d['Open'].reindex(feat.index)
    feat['RawHigh']=d['High'].reindex(feat.index)
    feat['RawLow']=d['Low'].reindex(feat.index)
    feat['RawClose']=d['Close'].reindex(feat.index)
    sc=pd.Series(price_scale,index=d.index).reindex(feat.index).ffill().fillna(1.0)
    ac=pd.Series(action,index=d.index).reindex(feat.index).fillna(False).astype(bool)
    su=pd.Series(suspect,index=d.index).reindex(feat.index).fillna(False).astype(bool)
    rs=pd.Series(reason,index=d.index).reindex(feat.index).fillna('')
    feat['ExplosivePriceScale']=sc;feat['ExplosiveCorporateActionNormalized']=ac.astype('int8');feat['ExplosiveIntegritySuspect']=su.astype('int8');feat['ExplosiveIntegrityReason']=rs
    audit=pd.DataFrame({'Date':[pd.Timestamp(x).date().isoformat() for x in feat.index],
                        'RawClose':pd.to_numeric(feat['RawClose'],errors='coerce').to_numpy(),
                        'NormalizedClose':pd.to_numeric(feat['Close'],errors='coerce').to_numpy(),
                        'PriceScale':pd.to_numeric(feat['ExplosivePriceScale'],errors='coerce').to_numpy(),
                        'CorporateActionNormalized':feat['ExplosiveCorporateActionNormalized'].astype(int).to_numpy(),
                        'IntegritySuspect':feat['ExplosiveIntegritySuspect'].astype(int).to_numpy(),
                        'Reason':feat['ExplosiveIntegrityReason'].astype(str).to_numpy()})
    return feat,audit


def _explosive_benchmark_tables_v635(feat,ticker,target_pct=.15,horizons=(1,2,3,5)):
    """Causal explosive benchmark on a split-normalized feature frame."""
    f=feat.copy().dropna(subset=['Close']) if isinstance(feat,pd.DataFrame) else pd.DataFrame()
    if f.empty:return (pd.DataFrame(),)*6
    max_h=max(int(x) for x in horizons);rows=[];start=70
    for i in range(start,max(start,len(f)-max_h)):
        r=f.iloc[i];p=float(r.get('Close',np.nan));rawp=float(r.get('RawClose',p))
        if not np.isfinite(p) or p<=0:continue
        recent2=float(p/float(f.iloc[i-2].Close)-1) if i>=2 and float(f.iloc[i-2].Close)>0 else np.nan
        setup=_feedback_replay_setup_v631(r,float(target_pct),recent2);sigdate=pd.Timestamp(f.index[i])
        for h in horizons:
            future=f.iloc[i+1:i+1+int(h)]
            if len(future)<int(h):continue
            suspect=bool(int(r.get('ExplosiveIntegritySuspect',0) or 0)) or bool(pd.to_numeric(future.get('ExplosiveIntegritySuspect',0),errors='coerce').fillna(0).astype(int).gt(0).any())
            threshold=p*(1+float(target_pct));hit_rows=future[future['High']>=threshold] if not suspect else future.iloc[0:0]
            hit=not hit_rows.empty;hit_date=pd.Timestamp(hit_rows.index[0]) if hit else pd.NaT
            lead=None
            if hit:
                try:lead=int(list(future.index).index(hit_rows.index[0])+1)
                except Exception:lead=np.nan
            crossed_action=bool(pd.to_numeric(future.get('ExplosiveCorporateActionNormalized',0),errors='coerce').fillna(0).astype(int).gt(0).any())
            mfe=100*float(future.High.max()/p-1) if not suspect else np.nan
            endret=100*float(future.Close.iloc[-1]/p-1) if not suspect else np.nan
            rows.append({'Ticker':str(ticker),'SignalDate':sigdate.date().isoformat(),'HorizonD':int(h),'TargetPct':100*float(target_pct),'Price':p,'RawPrice':rawp,
                         'Hit':int(hit) if not suspect else np.nan,'HitDate':hit_date.date().isoformat() if hit else '','LeadSessions':lead,'MFEPct':mfe,'EndReturnPct':endret,
                         'Indicators':' | '.join(setup['active']),'Families':setup['family_signature'],'IndependentFamilyCount':setup['family_count'],'FreshnessState':setup['freshness_state'],
                         'MoveConsumedPct':setup['move_consumed_pct'],'ExtensionATR':setup['extension_atr'],'DistributionRisk':setup['distribution_risk'],'SetupScoreV2':setup['setup_score_v2'],
                         'LearnEligible':int(not suspect),'CorporateActionCrossed':int(crossed_action),'IntegrityStatus':'EXCLUDED — DATA QUALITY' if suspect else ('SPLIT-NORMALIZED' if crossed_action else 'OK')})
    ev=pd.DataFrame(rows)
    if ev.empty:return (pd.DataFrame(),)*6
    summary=[];ind_rows=[];combo_rows=[]
    def split_ind(txt):return [x.strip() for x in str(txt or '').split(' | ') if x.strip() and x.strip().lower()!='nan']
    eligible=ev[pd.to_numeric(ev.get('LearnEligible',1),errors='coerce').fillna(0).eq(1)].copy()
    for h,g in eligible.groupby('HorizonD'):
        base=float(pd.to_numeric(g.Hit,errors='coerce').mean());summary.append({'Ticker':ticker,'HorizonD':int(h),'Sampled Dates':len(g),'Explosive Hits':int(pd.to_numeric(g.Hit,errors='coerce').fillna(0).sum()),'Base Hit Rate %':100*base,'Target %':100*float(target_pct),'Excluded Integrity Samples':int((ev.HorizonD.eq(h)&ev.LearnEligible.eq(0)).sum())})
        names=sorted({x for txt in g.Indicators.fillna('').astype(str) for x in split_ind(txt)})
        for name in names:
            m=g.Indicators.fillna('').astype(str).apply(lambda txt:name in split_ind(txt));nn=int(m.sum())
            if nn<10:continue
            rate=float(pd.to_numeric(g.loc[m,'Hit'],errors='coerce').mean());lift=rate/base if base>0 else np.nan
            ind_rows.append({'HorizonD':int(h),'Indicator':name,'N':nn,'Hits':int(pd.to_numeric(g.loc[m,'Hit'],errors='coerce').fillna(0).sum()),'Hit Rate %':100*rate,'Baseline %':100*base,'Lift x':lift,'Delta pp':100*(rate-base),'Family':_feedback_replay_indicator_family_v633(name),'Status':'PROMISING' if nn>=15 and np.isfinite(lift) and lift>=1.30 and rate-base>=.03 else ('WEAK' if np.isfinite(lift) and lift<.90 else 'MIXED')})
    h=max(int(x) for x in horizons);g=eligible[eligible.HorizonD.eq(h)].copy().sort_values('SignalDate').reset_index(drop=True)
    if g.empty:return pd.DataFrame(summary),pd.DataFrame(ind_rows),pd.DataFrame(),pd.DataFrame(),pd.DataFrame(),ev
    n=len(g);cut=max(1,min(n-1,int(.70*n)));disc=g.iloc[:cut].copy();val=g.iloc[cut:].copy();db=float(pd.to_numeric(disc.Hit,errors='coerce').mean()) if len(disc) else np.nan;vb=float(pd.to_numeric(val.Hit,errors='coerce').mean()) if len(val) else np.nan
    names=sorted({x for txt in disc.Indicators.fillna('').astype(str) for x in split_ind(txt)});sets=[set(split_ind(x)) for x in g.Indicators.fillna('').astype(str)];arrays={name:np.array([name in z for z in sets],dtype=bool) for name in names}
    uni=[]
    for name in names:
        m=arrays[name][:cut];nn=int(m.sum())
        if nn<12:continue
        rate=float(pd.to_numeric(disc.loc[m,'Hit'],errors='coerce').mean());uni.append((name,_feedback_replay_indicator_family_v633(name),nn,rate,(rate-db)*math.log1p(nn)))
    pool=[]
    for fam in sorted({x[1] for x in uni}):pool += [x[0] for x in sorted([u for u in uni if u[1]==fam],key=lambda q:(q[4],q[2]),reverse=True)[:2]]
    found=[]
    for k in (2,3):
        for combo in combinations(sorted(set(pool)),k):
            fams=[_feedback_replay_indicator_family_v633(x) for x in combo]
            if len(set(fams))<k:continue
            m=np.ones(cut,dtype=bool)
            for name in combo:m &= arrays[name][:cut]
            nn=int(m.sum())
            if nn<10:continue
            rate=float(pd.to_numeric(disc.loc[m,'Hit'],errors='coerce').mean());lift=rate/db if db>0 else np.nan
            if int(pd.to_numeric(disc.loc[m,'Hit'],errors='coerce').fillna(0).sum())<2 or not np.isfinite(lift) or lift<1.35:continue
            found.append((combo,fams,nn,rate,lift,(rate-db)*math.log1p(nn)))
    for combo,fams,nn,rate,lift,score in sorted(found,key=lambda x:(x[5],x[2]),reverse=True)[:60]:
        m=np.ones(len(val),dtype=bool)
        for name in combo:m &= arrays[name][cut:]
        vn=int(m.sum());vr=float(pd.to_numeric(val.loc[m,'Hit'],errors='coerce').mean()) if vn else np.nan;vl=vr/vb if vn and vb>0 else np.nan
        status='OOS PROMISING' if vn>=6 and np.isfinite(vl) and vl>=1.25 and vr-vb>=.03 else ('LOW SAMPLE' if vn<6 else 'OOS MIXED')
        combo_rows.append({'Combination':' + '.join(combo),'Families':' + '.join(fams),'Discovery N':nn,'Discovery Hit Rate %':100*rate,'Discovery Baseline %':100*db,'Discovery Lift x':lift,'Validation N':vn,'Validation Hit Rate %':100*vr if np.isfinite(vr) else np.nan,'Validation Baseline %':100*vb if np.isfinite(vb) else np.nan,'Validation Lift x':vl,'Status':status})
    hit5=g[pd.to_numeric(g.get('Hit',np.nan),errors='coerce').eq(1)].copy()
    # Independent realized legs. Find the earliest anchor whose next max_h sessions
    # reach the explosive target. After its first hit, lock the detector until a
    # >=5% reset from the post-hit peak or five full sessions of cool-off. This
    # avoids the old "bridging labels" problem where overlapping 5D windows could
    # merge separate August and September moves into one episode.
    episodes=[];idx_pos={pd.Timestamp(x).date():i for i,x in enumerate(f.index)}
    search=max(start,0);last_start=max(start,len(f)-max_h)
    while search < last_start:
        anchor=None;hitpos=None
        for i in range(search,last_start):
            p0=float(f.iloc[i].Close)
            if not np.isfinite(p0) or p0<=0 or int(f.iloc[i].get('ExplosiveIntegritySuspect',0) or 0):continue
            fut=f.iloc[i+1:i+1+max_h]
            if len(fut)<max_h or pd.to_numeric(fut.get('ExplosiveIntegritySuspect',0),errors='coerce').fillna(0).astype(int).gt(0).any():continue
            hh=pd.to_numeric(fut.High,errors='coerce').to_numpy(float);where=np.where(hh>=p0*(1+float(target_pct)))[0]
            if len(where):anchor=i;hitpos=i+1+int(where[0]);break
        if anchor is None or hitpos is None:break
        anchor_date=pd.Timestamp(f.index[anchor]).date();hit_date=pd.Timestamp(f.index[hitpos]).date()
        cand=hit5.copy()
        if not cand.empty:
            cand['_sp']=pd.to_datetime(cand.SignalDate,errors='coerce').dt.date.map(idx_pos);cand['_hp']=pd.to_datetime(cand.HitDate,errors='coerce').dt.date.map(idx_pos)
            cand=cand[(pd.to_numeric(cand['_sp'],errors='coerce')>=anchor) & (pd.to_numeric(cand['_sp'],errors='coerce')<hitpos) & (pd.to_numeric(cand['_hp'],errors='coerce')<=hitpos)]
        if cand.empty:
            rr=g[(pd.to_datetime(g.SignalDate,errors='coerce').dt.date==anchor_date) & pd.to_numeric(g.Hit,errors='coerce').eq(1)].copy()
            cand=rr
        if not cand.empty:
            ear=cand.sort_values(['SignalDate','HitDate']).iloc[0];best=cand.sort_values(['IndependentFamilyCount','SetupScoreV2'],ascending=False).iloc[0]
            episodes.append({'Episode':len(episodes)+1,'Earliest Warning':ear.SignalDate,'Hit Date':pd.Timestamp(f.index[hitpos]).date().isoformat(),'Lead Sessions':int(hitpos-idx_pos.get(pd.Timestamp(ear.SignalDate).date(),anchor)),'Start Price':ear.Price,'Raw Start Price':ear.RawPrice,'Best Pre-Move Families':best.Families,'Best Pre-Move Indicators':best.Indicators,'Best Setup Score':best.SetupScoreV2,'Precursor Dates':len(cand),'Integrity':'CLEAN / SPLIT-NORMALIZED'})
        # unlock only after a real reset or five sessions after the hit
        unlock=hitpos+1;peak=float(f.iloc[hitpos].High)
        while unlock<last_start:
            peak=max(peak,float(f.iloc[unlock].High))
            close_u=float(f.iloc[unlock].Close);gap=unlock-hitpos
            if gap>=5 or (np.isfinite(peak) and peak>0 and np.isfinite(close_u) and close_u/peak-1<=-0.05):break
            unlock+=1
        search=max(unlock,hitpos+1)
    ep=pd.DataFrame(episodes);recent=pd.DataFrame()
    if not ep.empty:
        hd=pd.to_datetime(ep['Hit Date'],errors='coerce');max_year=int(hd.dt.year.max()) if hd.notna().any() else None
        if max_year:recent=ep[(hd.dt.year.eq(max_year)) & (hd.dt.month.isin([8,9]))].copy()
    return pd.DataFrame(summary),pd.DataFrame(ind_rows),pd.DataFrame(combo_rows),ep,recent,ev


def _explosive_benchmark_worker_v635(runtime,jid,cfg):
    try:
        ticker=str(cfg.get('ticker','1196.HK')).strip().upper();history=str(cfg.get('history','1y'));target=float(cfg.get('target_pct',.15));horizons=tuple(int(x) for x in cfg.get('horizons',(1,2,3,5)))
        _lab_update_v603(runtime,jid,0,5,ticker,'Explosive Integrity • fetching daily history');_lab_check_v603(runtime,jid)
        d=fetch_ohlcv(ticker,history,'1d')
        if d is None or len(d)<120:raise ValueError('Need at least 120 daily bars for Explosive Benchmark')
        _lab_update_v603(runtime,jid,1,5,ticker,'Explosive Integrity • split/corporate-action normalization');_lab_check_v603(runtime,jid)
        f,audit=_explosive_prepare_features_v635(d,ticker)
        if f is None or len(f)<120:raise ValueError('Could not build split-normalized research frame')
        _lab_update_v603(runtime,jid,2,5,ticker,'Explosive Benchmark • causal target labels');_lab_check_v603(runtime,jid)
        summary,inds,combos,episodes,recent,events=_explosive_benchmark_tables_v635(f,ticker,target,horizons)
        _lab_update_v603(runtime,jid,3,5,ticker,'Explosive Benchmark • independent legs + Aug/Sep audit');_lab_check_v603(runtime,jid)
        meta={'Tab':'Explosive Benchmark Lab V6.3.5','Version':APP_VERSION,'Ticker':ticker,'History':history,'TargetPct':100*target,'Horizons':'/'.join(str(x)+'D' for x in horizons),'Integrity':'Split/corporate-action normalized before indicators and future labels; unexplained giant gaps excluded','EpisodeLogic':'Independent explosive legs require post-hit cool-off/reset','Causality':'Features use signal-date close only; target labels use future bars afterward','ResearchOnly':'YES — benchmark/radar evidence; never promotes Production rules automatically'}
        _lab_update_v603(runtime,jid,4,5,ticker,'Explosive Benchmark • building workbook');_lab_check_v603(runtime,jid)
        excel=_feedback_workbook_v629({'Benchmark Summary':summary,'Explosive Episodes':episodes,'Aug-Sep Audit':recent,'Indicator Lift':inds,'Combination Discovery':combos,'Integrity Audit':audit,'All Causal Samples':events},meta)
        _lab_update_v603(runtime,jid,5,5,ticker,'Completed');_lab_publish_v603(runtime,jid,{'summary':summary,'indicators':inds,'combinations':combos,'episodes':episodes,'recent':recent,'events':events,'integrity':audit,'excel':excel,'ticker':ticker})
    except _LabCancelled:_lab_publish_v603(runtime,jid,None,'stopped')
    except Exception as ex:_lab_fail_v603(runtime,jid,ex)


def _explosive_current_radar_row_v635(ticker,feat,events,combos,target_pct=.15):
    if feat is None or len(feat)<80:return None
    market=_market_for_ticker_v612(ticker);phase=_market_phase(market)
    cf=feat.iloc[:-1].copy() if phase=='OPEN' and len(feat)>1 else feat.copy()
    if cf.empty:return None
    r=cf.iloc[-1];p=float(r.get('Close',np.nan));rawp=float(r.get('RawClose',p))
    recent2=float(p/float(cf.iloc[-3].Close)-1) if len(cf)>=3 and float(cf.iloc[-3].Close)>0 else np.nan
    setup=_feedback_replay_setup_v631(r,float(target_pct),recent2);active=set(setup['active']);families=set(setup['families'])
    g=events.copy() if isinstance(events,pd.DataFrame) else pd.DataFrame()
    g=g[(pd.to_numeric(g.get('HorizonD',0),errors='coerce').eq(5)) & (pd.to_numeric(g.get('LearnEligible',1),errors='coerce').fillna(0).eq(1))].copy() if not g.empty else g
    baseline=float(pd.to_numeric(g.get('Hit',np.nan),errors='coerce').mean()) if not g.empty else np.nan
    def famset(x):return {z.strip() for z in str(x or '').split(' + ') if z.strip()}
    analog_n=0;analog_rate=np.nan;analog_lift=np.nan
    if not g.empty and families:
        need=max(2,min(3,len(families)))
        mask=g.get('Families',pd.Series('',index=g.index)).apply(lambda x:len(famset(x)&families)>=need)
        mask &= g.get('FreshnessState',pd.Series('',index=g.index)).fillna('').astype(str).isin(['FRESH','DEVELOPING'])
        mask &= ~pd.to_numeric(g.get('DistributionRisk',0),errors='coerce').fillna(0).astype(bool)
        analog_n=int(mask.sum())
        if analog_n:
            analog_rate=float(pd.to_numeric(g.loc[mask,'Hit'],errors='coerce').mean());analog_lift=analog_rate/baseline if np.isfinite(baseline) and baseline>0 else np.nan
    best_combo='';best_vn=0;best_rate=np.nan;best_lift=np.nan
    if isinstance(combos,pd.DataFrame) and not combos.empty:
        for _,cr in combos.iterrows():
            parts={x.strip() for x in str(cr.get('Combination','')).split(' + ') if x.strip()}
            if not parts or not parts.issubset(active):continue
            vl=float(cr.get('Validation Lift x',np.nan));vn=int(cr.get('Validation N',0) or 0);vr=float(cr.get('Validation Hit Rate %',np.nan))
            if str(cr.get('Status',''))=='OOS PROMISING' and (not np.isfinite(best_lift) or (np.isfinite(vl) and vl>best_lift)):
                best_combo=str(cr.get('Combination',''));best_vn=vn;best_rate=vr;best_lift=vl
    fresh=str(setup['freshness_state']);cons=float(setup['move_consumed_pct']) if np.isfinite(setup['move_consumed_pct']) else np.nan;dist=bool(setup['distribution_risk']);fc=int(setup['family_count'])
    integrity='OK'
    if int(r.get('ExplosiveIntegritySuspect',0) or 0):integrity='DATA QUALITY BLOCK'
    elif int(r.get('ExplosiveCorporateActionNormalized',0) or 0):integrity='SPLIT-NORMALIZED'
    score=12*min(fc,5)
    if np.isfinite(analog_lift):score+=min(20,max(0,(analog_lift-1)*35))
    if np.isfinite(best_lift):score+=min(15,max(0,(best_lift-1)*30))
    if fresh=='FRESH':score+=10
    elif fresh=='DEVELOPING':score+=5
    elif fresh in ('LATE','ALREADY MOVED'):score-=25
    if dist:score-=25
    if np.isfinite(cons) and cons>=80:score-=20
    score=float(np.clip(score,0,100))
    status='WATCH'
    if integrity=='DATA QUALITY BLOCK':status='BLOCKED — DATA QUALITY'
    elif fresh in ('LATE','ALREADY MOVED') or (np.isfinite(cons) and cons>=100):status='LATE / ALREADY MOVED'
    elif fc>=4 and analog_n>=15 and np.isfinite(analog_lift) and analog_lift>=1.35 and np.isfinite(best_lift) and best_lift>=1.25 and best_vn>=6 and not dist and fresh in ('FRESH','DEVELOPING'):status='STRONG EXPLOSIVE CANDIDATE'
    elif fc>=3 and analog_n>=10 and np.isfinite(analog_lift) and analog_lift>=1.20 and not dist and fresh in ('FRESH','DEVELOPING'):status='EXPLOSIVE CANDIDATE'
    elif fc>=3 and fresh in ('FRESH','DEVELOPING') and not dist:status='BUILDING'
    return {'Ticker':ticker,'Market':market,'Explosive Radar Score':round(score,1),'Status':status,'Raw Close':rawp,'Signal Date':pd.Timestamp(cf.index[-1]).date().isoformat(),'Freshness':fresh,'Move Consumed %':cons,'Independent Families':fc,'Families':setup['family_signature'],'Active Indicators':' | '.join(setup['active']),'Historical 5D Baseline %':100*baseline if np.isfinite(baseline) else np.nan,'Analog N':analog_n,'Analog Hit Rate %':100*analog_rate if np.isfinite(analog_rate) else np.nan,'Analog Lift x':analog_lift,'Best OOS Combo':best_combo,'Best Combo Validation N':best_vn,'Best Combo Validation Hit Rate %':best_rate,'Best Combo Validation Lift x':best_lift,'Distribution Risk':dist,'Integrity':integrity}


def _explosive_universe_worker_v635(runtime,jid,cfg):
    try:
        scope=str(cfg.get('scope','HONG KONG'));count=int(cfg.get('max_tickers',100));history=str(cfg.get('history','1y'));target=float(cfg.get('target_pct',.15))
        tickers=_research_validator_universe_v624(scope,count);total=max(1,len(tickers));rows=[];skipped=[]
        for i,t in enumerate(tickers,1):
            _lab_check_v603(runtime,jid);_lab_update_v603(runtime,jid,i-1,total+2,t,'Explosive Universe Radar • split-safe historical analogs')
            try:
                d=fetch_ohlcv(t,history,'1d')
                if d is None or len(d)<120:raise ValueError('not enough daily history')
                f,audit=_explosive_prepare_features_v635(d,t)
                if f is None or len(f)<120:raise ValueError('integrity frame unavailable')
                _,_,combos,_,_,events=_explosive_benchmark_tables_v635(f,t,target,(1,2,3,5))
                rr=_explosive_current_radar_row_v635(t,f,events,combos,target)
                if rr:rows.append(rr)
            except Exception as e:skipped.append({'Ticker':str(t),'Reason':f'{type(e).__name__}: {e}'})
        _lab_update_v603(runtime,jid,total,total+2,'Ranking','Explosive Universe Radar • ranking current candidates');_lab_check_v603(runtime,jid)
        df=pd.DataFrame(rows)
        if not df.empty:
            order={'STRONG EXPLOSIVE CANDIDATE':0,'EXPLOSIVE CANDIDATE':1,'BUILDING':2,'WATCH':3,'LATE / ALREADY MOVED':4,'BLOCKED — DATA QUALITY':5}
            df['_ord']=df.Status.map(order).fillna(9);df=df.sort_values(['_ord','Explosive Radar Score','Analog N'],ascending=[True,False,False]).drop(columns='_ord').reset_index(drop=True)
        summary=pd.DataFrame([{'Scope':scope,'Requested':len(tickers),'Successful':len(df),'Skipped':len(skipped),'Target %':100*target,'History':history,'Strong Candidates':int(df.Status.eq('STRONG EXPLOSIVE CANDIDATE').sum()) if not df.empty else 0,'Candidates':int(df.Status.eq('EXPLOSIVE CANDIDATE').sum()) if not df.empty else 0,'Building':int(df.Status.eq('BUILDING').sum()) if not df.empty else 0,'ResearchOnly':'YES — daily early-warning radar; confirm timing in Analyze/Scanner'}])
        _lab_update_v603(runtime,jid,total+1,total+2,'Excel','Explosive Universe Radar • workbook');_lab_check_v603(runtime,jid)
        excel=_feedback_workbook_v629({'Radar Summary':summary,'Current Explosive Radar':df,'Skipped':pd.DataFrame(skipped)},{'Tab':'Explosive Universe Radar','Version':APP_VERSION,'Scope':scope,'History':history,'TargetPct':100*target,'Method':'Current daily fingerprint vs split-safe historical +15% analogs and OOS-promising combinations','ResearchOnly':'YES — no automatic Production promotion'})
        _lab_update_v603(runtime,jid,total+2,total+2,'Completed','Completed');_lab_publish_v603(runtime,jid,{'summary':summary,'radar':df,'skipped':pd.DataFrame(skipped),'excel':excel})
    except _LabCancelled:_lab_publish_v603(runtime,jid,None,'stopped')
    except Exception as ex:_lab_fail_v603(runtime,jid,ex)


# ========================= V6.3.6 Explosive Continuation Engine =========================
def _explosive_continuation_state_v636(feat,pos,target_pct=.15):
    """Causal daily state machine for first-leg and continuation explosive setups.

    The state at bar ``pos`` uses bars up to and including that bar only.  A stock
    that already moved is *not* automatically rejected if it has subsequently
    formed a tight, high-retention base with constructive volume/flow and can
    re-accelerate from that reset.
    """
    f=feat if isinstance(feat,pd.DataFrame) else pd.DataFrame()
    if f.empty or pos<0 or pos>=len(f):return {'state':'NO DATA','state_score':0.0,'prior_impulse_pct':np.nan,'base_range_pct':np.nan,'base_range_atr':np.nan,'base_volume_dryup':np.nan,'retention_pct':np.nan,'base_high':np.nan,'base_low':np.nan,'reacceleration':False,'reset_valid':False,'reason':'insufficient data'}
    r=f.iloc[pos];p=float(pd.to_numeric(pd.Series([r.get('Close',np.nan)]),errors='coerce').iloc[0])
    if not np.isfinite(p) or p<=0:return {'state':'NO DATA','state_score':0.0,'prior_impulse_pct':np.nan,'base_range_pct':np.nan,'base_range_atr':np.nan,'base_volume_dryup':np.nan,'retention_pct':np.nan,'base_high':np.nan,'base_low':np.nan,'reacceleration':False,'reset_valid':False,'reason':'invalid close'}
    recent2=float(p/float(f.iloc[pos-2].Close)-1) if pos>=2 and np.isfinite(float(f.iloc[pos-2].Close)) and float(f.iloc[pos-2].Close)>0 else np.nan
    setup=_feedback_replay_setup_v631(r,float(target_pct),recent2)
    def val(k,default=np.nan):
        try:
            x=float(r.get(k,default));return x if np.isfinite(x) else default
        except Exception:return default
    atrpct=val('atr_pct');e20=val('ema20');vw=val('vwap');cl=val('close_location',.5);rv=val('time_adjusted_rvol',val('robust_volume_ratio'));va=val('vol_accel')
    # Prior impulse: a large advance from a causal local low into the recent peak.
    w0=max(0,pos-12);hist=f.iloc[w0:pos+1]
    prior=f.iloc[max(0,pos-12):max(1,pos-2)] if pos>=3 else f.iloc[0:0]
    recent_peak=float(pd.to_numeric(hist.get('High',pd.Series(dtype=float)),errors='coerce').max()) if len(hist) else np.nan
    prior_low=float(pd.to_numeric(prior.get('Low',pd.Series(dtype=float)),errors='coerce').min()) if len(prior) else np.nan
    prior_imp=100*(recent_peak/prior_low-1) if np.isfinite(recent_peak) and np.isfinite(prior_low) and prior_low>0 else np.nan
    retention=100*p/recent_peak if np.isfinite(recent_peak) and recent_peak>0 else np.nan
    # A continuation base is measured *before* the current bar so the current bar
    # can be a genuine causal breakout/re-acceleration observation.
    b=f.iloc[max(0,pos-3):pos]
    b_high=float(pd.to_numeric(b.get('High',pd.Series(dtype=float)),errors='coerce').max()) if len(b)>=2 else np.nan
    b_low=float(pd.to_numeric(b.get('Low',pd.Series(dtype=float)),errors='coerce').min()) if len(b)>=2 else np.nan
    b_mid=float(pd.to_numeric(b.get('Close',pd.Series(dtype=float)),errors='coerce').mean()) if len(b)>=2 else np.nan
    brange=100*(b_high/b_low-1) if np.isfinite(b_high) and np.isfinite(b_low) and b_low>0 else np.nan
    brange_atr=brange/atrpct if np.isfinite(brange) and np.isfinite(atrpct) and atrpct>0 else np.nan
    vbase=f.iloc[max(0,pos-13):max(0,pos-3)]
    bvol=float(pd.to_numeric(b.get('Volume',pd.Series(dtype=float)),errors='coerce').mean()) if len(b)>=2 else np.nan
    vref=float(pd.to_numeric(vbase.get('Volume',pd.Series(dtype=float)),errors='coerce').mean()) if len(vbase)>=4 else np.nan
    dry=bvol/vref if np.isfinite(bvol) and np.isfinite(vref) and vref>0 else np.nan
    impulse_min=max(7.0,100*float(target_pct)*.45)
    tight_limit=max(4.5,1.65*atrpct) if np.isfinite(atrpct) and atrpct>0 else 6.0
    has_imp=bool(np.isfinite(prior_imp) and prior_imp>=impulse_min)
    high_ret=bool(np.isfinite(retention) and retention>=90.0)
    tight=bool(np.isfinite(brange) and brange<=tight_limit)
    dry_ok=bool((not np.isfinite(dry)) or dry<=1.05)
    hold=bool((np.isfinite(e20) and p>=e20*.99) or (np.isfinite(vw) and p>=vw*.99))
    reset_valid=bool(has_imp and high_ret and tight and dry_ok and hold and not setup['distribution_risk'])
    # Breakout of the causal base plus renewed momentum/volume-flow.  We accept a
    # close just under the base high only when the bar traded through it and closed
    # strongly, which handles fast HK names without fabricating intraday data.
    crossed=bool(np.isfinite(b_high) and (p>=b_high*1.001 or (val('High',p)>=b_high*1.002 and cl>=.70)))
    renewed=bool(setup['core_momentum'] and setup['core_volume_flow'] and (rv>=1.10 if np.isfinite(rv) else False or va>=1.04 if np.isfinite(va) else False))
    # Python conditional precedence is awkward in one-liners; preserve a second
    # explicit volume acceleration check.
    renewed=bool(setup['core_momentum'] and setup['core_volume_flow'] and ((np.isfinite(rv) and rv>=1.10) or (np.isfinite(va) and va>=1.04) or setup['family_count']>=4))
    reacc=bool(reset_valid and crossed and renewed)
    if reacc:state='RE-ACCELERATION'
    elif reset_valid:state='CONTINUATION BASE'
    elif setup['freshness_state'] in ('FRESH','DEVELOPING') and setup['family_count']>=2 and not setup['distribution_risk']:state='PRE-EXPLOSIVE'
    elif setup['freshness_state'] in ('LATE','ALREADY MOVED'):state='EXTENDED / NO RESET'
    else:state='WATCH'
    score=10*min(int(setup['family_count']),5)
    score += 18 if state=='RE-ACCELERATION' else (12 if state=='CONTINUATION BASE' else (8 if state=='PRE-EXPLOSIVE' else 0))
    if high_ret:score+=6
    if tight:score+=6
    if dry_ok and has_imp:score+=5
    if setup['distribution_risk']:score-=25
    score=float(np.clip(score,0,100))
    reason=f"impulse {prior_imp:.1f}% • retention {retention:.1f}% • base {brange:.1f}% • dry-up {dry:.2f}x" if all(np.isfinite(x) for x in (prior_imp,retention,brange,dry)) else state
    return {'state':state,'state_score':score,'prior_impulse_pct':prior_imp,'base_range_pct':brange,'base_range_atr':brange_atr,'base_volume_dryup':dry,'retention_pct':retention,'base_high':b_high,'base_low':b_low,'reacceleration':reacc,'reset_valid':reset_valid,'reason':reason,'setup':setup}


def _explosive_enrich_events_v636(feat,events,target_pct=.15):
    e=events.copy() if isinstance(events,pd.DataFrame) else pd.DataFrame()
    if e.empty:return e
    posmap={pd.Timestamp(x).date():i for i,x in enumerate(feat.index)}
    # Each signal date appears once per horizon.  Compute the causal continuation
    # state once per date and reuse it across 1D/2D/3D/5D rows; this keeps HK100 /
    # NASDAQ200 radar runs practical instead of doing the same state work 4x.
    cache={}
    for d0 in pd.to_datetime(e.get('SignalDate'),errors='coerce').dropna().dt.date.unique():
        pos=posmap.get(d0)
        if pos is not None:cache[d0]=_explosive_continuation_state_v636(feat,int(pos),target_pct)
    missing={'state':'NO DATA','state_score':0.0,'prior_impulse_pct':np.nan,'base_range_pct':np.nan,'base_range_atr':np.nan,'base_volume_dryup':np.nan,'retention_pct':np.nan,'base_high':np.nan,'base_low':np.nan,'reacceleration':False,'reset_valid':False,'reason':'date not found'}
    out=[]
    for _,row in e.iterrows():
        d=pd.to_datetime(row.get('SignalDate'),errors='coerce');stt=cache.get(d.date(),missing) if pd.notna(d) else missing
        z=row.to_dict();z.update({'ExplosiveState':stt['state'],'ExplosiveStateScore':stt['state_score'],'PriorImpulsePct':stt['prior_impulse_pct'],'ContinuationBaseRangePct':stt['base_range_pct'],'ContinuationBaseRangeATR':stt['base_range_atr'],'ContinuationVolumeDryup':stt['base_volume_dryup'],'ContinuationRetentionPct':stt['retention_pct'],'ContinuationBaseHigh':stt['base_high'],'ContinuationBaseLow':stt['base_low'],'ContinuationResetValid':int(bool(stt['reset_valid'])),'ReaccelerationTrigger':int(bool(stt['reacceleration'])),'StateReason':stt['reason']})
        out.append(z)
    return pd.DataFrame(out)


def _explosive_state_stats_v636(events):
    e=events.copy() if isinstance(events,pd.DataFrame) else pd.DataFrame()
    if e.empty:return pd.DataFrame()
    e=e[pd.to_numeric(e.get('LearnEligible',1),errors='coerce').fillna(0).eq(1)].copy()
    rows=[]
    for h,g in e.groupby('HorizonD'):
        base=float(pd.to_numeric(g.get('Hit',np.nan),errors='coerce').mean()) if len(g) else np.nan
        for state,sg in g.groupby('ExplosiveState'):
            n=len(sg);rate=float(pd.to_numeric(sg.get('Hit',np.nan),errors='coerce').mean()) if n else np.nan
            rows.append({'HorizonD':int(h),'Explosive State':state,'N':n,'Hits':int(pd.to_numeric(sg.get('Hit',0),errors='coerce').fillna(0).sum()),'Hit Rate %':100*rate if np.isfinite(rate) else np.nan,'Baseline %':100*base if np.isfinite(base) else np.nan,'Lift x':rate/base if np.isfinite(rate) and np.isfinite(base) and base>0 else np.nan,'Delta pp':100*(rate-base) if np.isfinite(rate) and np.isfinite(base) else np.nan})
    return pd.DataFrame(rows)


def _explosive_independent_legs_v636(feat,events,target_pct=.15,horizons=(1,2,3,5)):
    """Independent first legs *and* second-leg continuation explosions.

    A new leg may unlock after a normal cool-off/reset OR as soon as a causal
    CONTINUATION BASE / RE-ACCELERATION state forms after the prior hit.  Early
    warning is reported only when >=3 independent families are present and no
    distribution/data-quality block exists.
    """
    f=feat.copy();e=events.copy() if isinstance(events,pd.DataFrame) else pd.DataFrame()
    if f.empty or e.empty:return pd.DataFrame(),pd.DataFrame()
    max_h=max(int(x) for x in horizons);start=70;last=max(start,len(f)-max_h);idx_pos={pd.Timestamp(x).date():i for i,x in enumerate(f.index)}
    h5=e[(pd.to_numeric(e.get('HorizonD',0),errors='coerce').eq(max_h)) & (pd.to_numeric(e.get('Hit',np.nan),errors='coerce').eq(1)) & (pd.to_numeric(e.get('LearnEligible',1),errors='coerce').fillna(0).eq(1))].copy()
    if h5.empty:return pd.DataFrame(),pd.DataFrame()
    h5['_sp']=pd.to_datetime(h5.SignalDate,errors='coerce').dt.date.map(idx_pos);h5['_hp']=pd.to_datetime(h5.HitDate,errors='coerce').dt.date.map(idx_pos)
    episodes=[];search=start;prev_hit=None
    while search<last:
        anchor=None;hitpos=None
        # Prefer a valid continuation/re-acceleration anchor once a prior leg has
        # occurred; otherwise take the earliest causal +target anchor.
        for i in range(search,last):
            if int(f.iloc[i].get('ExplosiveIntegritySuspect',0) or 0):continue
            p0=float(f.iloc[i].Close);fut=f.iloc[i+1:i+1+max_h]
            if not np.isfinite(p0) or p0<=0 or len(fut)<max_h:continue
            if pd.to_numeric(fut.get('ExplosiveIntegritySuspect',0),errors='coerce').fillna(0).astype(int).gt(0).any():continue
            stt=_explosive_continuation_state_v636(f,i,target_pct)
            if prev_hit is not None and i>prev_hit+1 and stt['state'] in ('CONTINUATION BASE','RE-ACCELERATION'):
                pass
            elif prev_hit is not None and i<prev_hit+5:
                continue
            hh=pd.to_numeric(fut.High,errors='coerce').to_numpy(float);wh=np.where(hh>=p0*(1+float(target_pct)))[0]
            if len(wh):anchor=i;hitpos=i+1+int(wh[0]);break
        if anchor is None or hitpos is None:break
        cand=h5[(pd.to_numeric(h5['_sp'],errors='coerce')>=anchor) & (pd.to_numeric(h5['_sp'],errors='coerce')<hitpos) & (pd.to_numeric(h5['_hp'],errors='coerce')<=hitpos)].copy()
        if cand.empty:search=anchor+1;continue
        qualified=cand[(pd.to_numeric(cand.get('IndependentFamilyCount',0),errors='coerce').fillna(0)>=3) & (~pd.to_numeric(cand.get('DistributionRisk',0),errors='coerce').fillna(0).astype(bool)) & cand.get('ExplosiveState',pd.Series('',index=cand.index)).isin(['PRE-EXPLOSIVE','CONTINUATION BASE','RE-ACCELERATION'])]
        use=qualified if not qualified.empty else cand
        ear=use.sort_values(['SignalDate','ExplosiveStateScore'],ascending=[True,False]).iloc[0];best=use.sort_values(['IndependentFamilyCount','ExplosiveStateScore','SetupScoreV2'],ascending=False).iloc[0]
        epos=int(idx_pos.get(pd.Timestamp(ear.SignalDate).date(),anchor));etype='CONTINUATION LEG' if str(ear.get('ExplosiveState','')).startswith(('CONTINUATION','RE-ACCELERATION')) else 'FIRST / PRE-EXPLOSIVE LEG'
        episodes.append({'Episode':len(episodes)+1,'Episode Type':etype,'Earliest Warning':ear.SignalDate,'Earliest State':ear.get('ExplosiveState',''),'Hit Date':pd.Timestamp(f.index[hitpos]).date().isoformat(),'Lead Sessions':int(hitpos-epos),'Start Price':ear.Price,'Raw Start Price':ear.RawPrice,'Prior Impulse %':ear.get('PriorImpulsePct',np.nan),'Base Range %':ear.get('ContinuationBaseRangePct',np.nan),'Base Dry-Up x':ear.get('ContinuationVolumeDryup',np.nan),'Retention %':ear.get('ContinuationRetentionPct',np.nan),'Best Pre-Move Families':best.Families,'Best Pre-Move Indicators':best.Indicators,'Best Setup Score':best.SetupScoreV2,'Best State Score':best.get('ExplosiveStateScore',np.nan),'Precursor Dates':len(qualified),'Qualified Warning':int(not qualified.empty),'Integrity':'CLEAN / SPLIT-NORMALIZED'})
        prev_hit=hitpos
        # Search immediately after the hit; the loop itself only accepts an early
        # restart when a real continuation reset has formed. Otherwise it waits five
        # sessions, so overlapping windows cannot create duplicate legs.
        search=hitpos+2
    ep=pd.DataFrame(episodes);recent=pd.DataFrame()
    if not ep.empty:
        hd=pd.to_datetime(ep['Hit Date'],errors='coerce');yr=int(hd.dt.year.max()) if hd.notna().any() else None
        if yr:recent=ep[(hd.dt.year.eq(yr)) & (hd.dt.month.isin([8,9]))].copy()
    return ep,recent


def _explosive_benchmark_tables_v636(feat,ticker,target_pct=.15,horizons=(1,2,3,5)):
    summary,inds,combos,_,_,events=_explosive_benchmark_tables_v635(feat,ticker,target_pct,horizons)
    events=_explosive_enrich_events_v636(feat,events,target_pct)
    episodes,recent=_explosive_independent_legs_v636(feat,events,target_pct,horizons)
    states=_explosive_state_stats_v636(events)
    return summary,inds,combos,episodes,recent,events,states


def _explosive_benchmark_worker_v636(runtime,jid,cfg):
    try:
        ticker=str(cfg.get('ticker','1196.HK')).strip().upper();history=str(cfg.get('history','1y'));target=float(cfg.get('target_pct',.15));horizons=tuple(int(x) for x in cfg.get('horizons',(1,2,3,5)))
        _lab_update_v603(runtime,jid,0,6,ticker,'Explosive Continuation • fetching daily history');_lab_check_v603(runtime,jid)
        d=fetch_ohlcv(ticker,history,'1d')
        if d is None or len(d)<120:raise ValueError('Need at least 120 daily bars for Explosive Benchmark')
        _lab_update_v603(runtime,jid,1,6,ticker,'Explosive Continuation • split/corporate-action normalization');_lab_check_v603(runtime,jid)
        f,audit=_explosive_prepare_features_v635(d,ticker)
        if f is None or len(f)<120:raise ValueError('Could not build split-normalized research frame')
        _lab_update_v603(runtime,jid,2,6,ticker,'Explosive Continuation • causal target labels + states');_lab_check_v603(runtime,jid)
        summary,inds,combos,episodes,recent,events,states=_explosive_benchmark_tables_v636(f,ticker,target,horizons)
        _lab_update_v603(runtime,jid,3,6,ticker,'Explosive Continuation • independent first + second legs');_lab_check_v603(runtime,jid)
        _lab_update_v603(runtime,jid,4,6,ticker,'Explosive Continuation • state evidence');_lab_check_v603(runtime,jid)
        meta={'Tab':'Explosive Benchmark Lab V6.3.6','Version':APP_VERSION,'Ticker':ticker,'History':history,'TargetPct':100*target,'Horizons':'/'.join(str(x)+'D' for x in horizons),'Integrity':'Split/corporate-action normalized before indicators and future labels; unexplained giant gaps excluded','ContinuationLogic':'PRE-EXPLOSIVE / CONTINUATION BASE / RE-ACCELERATION are causal daily states. A valid reset can start a new explosive leg even after a prior move.','Causality':'Features and continuation state use signal-date-and-prior bars only; future bars are labels only','ResearchOnly':'YES — benchmark/radar evidence; Production Entry and regular Pre-Move +5%/3D are unchanged'}
        _lab_update_v603(runtime,jid,5,6,ticker,'Explosive Continuation • building workbook');_lab_check_v603(runtime,jid)
        excel=_feedback_workbook_v629({'Benchmark Summary':summary,'Explosive Episodes':episodes,'Aug-Sep Audit':recent,'Explosive State Evidence':states,'Indicator Lift':inds,'Combination Discovery':combos,'Integrity Audit':audit,'All Causal Samples':events},meta)
        _lab_update_v603(runtime,jid,6,6,ticker,'Completed');_lab_publish_v603(runtime,jid,{'summary':summary,'indicators':inds,'combinations':combos,'episodes':episodes,'recent':recent,'events':events,'states':states,'integrity':audit,'excel':excel,'ticker':ticker})
    except _LabCancelled:_lab_publish_v603(runtime,jid,None,'stopped')
    except Exception as ex:_lab_fail_v603(runtime,jid,ex)


def _explosive_current_radar_row_v636(ticker,feat,events,combos,target_pct=.15):
    if feat is None or len(feat)<80:return None
    market=_market_for_ticker_v612(ticker);phase=_market_phase(market);cf=feat.iloc[:-1].copy() if phase=='OPEN' and len(feat)>1 else feat.copy()
    if cf.empty:return None
    pos=len(cf)-1;r=cf.iloc[-1];p=float(r.get('Close',np.nan));rawp=float(r.get('RawClose',p));stt=_explosive_continuation_state_v636(cf,pos,target_pct);setup=stt.get('setup') or _feedback_replay_setup_v631(r,target_pct,np.nan)
    active=set(setup['active']);families=set(setup['families']);state=stt['state'];g=events.copy() if isinstance(events,pd.DataFrame) else pd.DataFrame()
    g=g[(pd.to_numeric(g.get('HorizonD',0),errors='coerce').eq(5)) & (pd.to_numeric(g.get('LearnEligible',1),errors='coerce').fillna(0).eq(1))].copy() if not g.empty else g
    baseline=float(pd.to_numeric(g.get('Hit',np.nan),errors='coerce').mean()) if not g.empty else np.nan
    def famset(x):return {z.strip() for z in str(x or '').split(' + ') if z.strip()}
    analog_n=0;analog_rate=np.nan;analog_lift=np.nan;analog_mode='STATE + FAMILY'
    if not g.empty and families:
        need=max(2,min(3,len(families)));mask=g.get('Families',pd.Series('',index=g.index)).apply(lambda x:len(famset(x)&families)>=need)
        mask &= ~pd.to_numeric(g.get('DistributionRisk',0),errors='coerce').fillna(0).astype(bool)
        if state in ('PRE-EXPLOSIVE','CONTINUATION BASE','RE-ACCELERATION'):
            smask=g.get('ExplosiveState',pd.Series('',index=g.index)).fillna('').astype(str).eq(state);candidate=mask & smask
            if int(candidate.sum())>=6:mask=candidate
            else:analog_mode='FAMILY FALLBACK'
        analog_n=int(mask.sum())
        if analog_n:
            analog_rate=float(pd.to_numeric(g.loc[mask,'Hit'],errors='coerce').mean());analog_lift=analog_rate/baseline if np.isfinite(baseline) and baseline>0 else np.nan
    best_combo='';best_vn=0;best_rate=np.nan;best_lift=np.nan
    if isinstance(combos,pd.DataFrame) and not combos.empty:
        for _,cr in combos.iterrows():
            parts={x.strip() for x in str(cr.get('Combination','')).split(' + ') if x.strip()}
            if not parts or not parts.issubset(active):continue
            vl=float(cr.get('Validation Lift x',np.nan));vn=int(cr.get('Validation N',0) or 0);vr=float(cr.get('Validation Hit Rate %',np.nan))
            if str(cr.get('Status',''))=='OOS PROMISING' and (not np.isfinite(best_lift) or (np.isfinite(vl) and vl>best_lift)):
                best_combo=str(cr.get('Combination',''));best_vn=vn;best_rate=vr;best_lift=vl
    fc=int(setup['family_count']);dist=bool(setup['distribution_risk']);integrity='DATA QUALITY BLOCK' if int(r.get('ExplosiveIntegritySuspect',0) or 0) else ('SPLIT-NORMALIZED' if int(r.get('ExplosiveCorporateActionNormalized',0) or 0) else 'OK')
    setup_score=float(setup.get('setup_score_v2',0) or 0);state_score=float(stt['state_score'])
    # Geometric mean deliberately requires BOTH setup quality and current-state
    # quality.  A 95/30 pair cannot look as strong as an 80/80 pair.
    setup_state_consensus=float(np.sqrt(max(0.0,setup_score)*max(0.0,state_score)))
    score=state_score;score+=min(22,max(0,(analog_lift-1)*40)) if np.isfinite(analog_lift) else 0;score+=min(15,max(0,(best_lift-1)*30)) if np.isfinite(best_lift) else 0;score=float(np.clip(score,0,100))
    status='WATCH'
    if integrity=='DATA QUALITY BLOCK':status='BLOCKED — DATA QUALITY'
    elif state=='RE-ACCELERATION':
        if fc>=4 and analog_n>=10 and np.isfinite(analog_lift) and analog_lift>=1.25 and (not np.isfinite(best_lift) or best_lift>=1.15) and not dist:status='STRONG RE-ACCELERATION CANDIDATE'
        else:status='RE-ACCELERATION CANDIDATE'
    elif state=='CONTINUATION BASE':
        if fc>=3 and analog_n>=8 and np.isfinite(analog_lift) and analog_lift>=1.18 and not dist:status='CONTINUATION BASE CANDIDATE'
        else:status='CONTINUATION BASE / WATCH'
    elif state=='PRE-EXPLOSIVE':
        if fc>=4 and analog_n>=15 and np.isfinite(analog_lift) and analog_lift>=1.35 and np.isfinite(best_lift) and best_lift>=1.25 and best_vn>=6 and not dist:status='STRONG PRE-EXPLOSIVE CANDIDATE'
        elif fc>=3 and analog_n>=10 and np.isfinite(analog_lift) and analog_lift>=1.20 and not dist:status='PRE-EXPLOSIVE CANDIDATE'
        elif fc>=3 and not dist:status='BUILDING'
    elif state=='EXTENDED / NO RESET':status='LATE / NO RESET'
    return {'Ticker':ticker,'Market':market,'Setup Score':round(setup_score,1),'State Score':round(state_score,1),'Setup×State Consensus':round(setup_state_consensus,1),'Explosive Radar Score':round(score,1),'Status':status,'Explosive State':state,'Raw Close':rawp,'Signal Date':pd.Timestamp(cf.index[-1]).date().isoformat(),'Freshness':setup['freshness_state'],'Move Consumed %':setup['move_consumed_pct'],'Prior Impulse %':stt['prior_impulse_pct'],'Continuation Base Range %':stt['base_range_pct'],'Continuation Base Range ATR':stt['base_range_atr'],'Continuation Volume Dry-Up x':stt['base_volume_dryup'],'Continuation Retention %':stt['retention_pct'],'Reset Valid':bool(stt['reset_valid']),'Reacceleration Trigger':bool(stt['reacceleration']),'Independent Families':fc,'Families':setup['family_signature'],'Active Indicators':' | '.join(setup['active']),'Historical 5D Baseline %':100*baseline if np.isfinite(baseline) else np.nan,'Analog Mode':analog_mode,'Analog N':analog_n,'Analog Hit Rate %':100*analog_rate if np.isfinite(analog_rate) else np.nan,'Analog Lift x':analog_lift,'Best OOS Combo':best_combo,'Best Combo Validation N':best_vn,'Best Combo Validation Hit Rate %':best_rate,'Best Combo Validation Lift x':best_lift,'Distribution Risk':dist,'Integrity':integrity}


def _explosive_universe_worker_v636(runtime,jid,cfg):
    try:
        scope=str(cfg.get('scope','HONG KONG'));count=int(cfg.get('max_tickers',100));history=str(cfg.get('history','1y'));target=float(cfg.get('target_pct',.15));tickers=_research_validator_universe_v624(scope,count);total=max(1,len(tickers));rows=[];skipped=[]
        for i,t in enumerate(tickers,1):
            _lab_check_v603(runtime,jid);_lab_update_v603(runtime,jid,i-1,total+2,t,'Explosive Radar V3 • four-score first-leg + continuation analogs')
            try:
                d=fetch_ohlcv(t,history,'1d')
                if d is None or len(d)<120:raise ValueError('not enough daily history')
                f,audit=_explosive_prepare_features_v635(d,t)
                if f is None or len(f)<120:raise ValueError('integrity frame unavailable')
                _,_,combos,_,_,events,_=_explosive_benchmark_tables_v636(f,t,target,(1,2,3,5));rr=_explosive_current_radar_row_v636(t,f,events,combos,target)
                if rr:rows.append(rr)
            except Exception as ex:skipped.append({'Ticker':str(t),'Reason':f'{type(ex).__name__}: {ex}'})
        _lab_update_v603(runtime,jid,total,total+2,'Ranking','Explosive Radar V3 • ranking causal states');_lab_check_v603(runtime,jid)
        df=pd.DataFrame(rows)
        if not df.empty:
            order={'STRONG RE-ACCELERATION CANDIDATE':0,'STRONG PRE-EXPLOSIVE CANDIDATE':1,'RE-ACCELERATION CANDIDATE':2,'CONTINUATION BASE CANDIDATE':3,'PRE-EXPLOSIVE CANDIDATE':4,'BUILDING':5,'CONTINUATION BASE / WATCH':6,'WATCH':7,'LATE / NO RESET':8,'BLOCKED — DATA QUALITY':9}
            df['_ord']=df.Status.map(order).fillna(10);df=df.sort_values(['_ord','Setup×State Consensus','Explosive Radar Score','Analog N'],ascending=[True,False,False,False]).drop(columns='_ord').reset_index(drop=True)
        counts=df.Status.value_counts().to_dict() if not df.empty else {}
        summary=pd.DataFrame([{'Scope':scope,'Requested':len(tickers),'Successful':len(df),'Skipped':len(skipped),'Target %':100*target,'History':history,'Strong Re-Acceleration':counts.get('STRONG RE-ACCELERATION CANDIDATE',0),'Re-Acceleration':counts.get('RE-ACCELERATION CANDIDATE',0),'Continuation Base':counts.get('CONTINUATION BASE CANDIDATE',0),'Strong Pre-Explosive':counts.get('STRONG PRE-EXPLOSIVE CANDIDATE',0),'Pre-Explosive':counts.get('PRE-EXPLOSIVE CANDIDATE',0),'ResearchOnly':'YES — Explosive Radar V3 is separate from regular Pre-Move research and from Production Entry'}])
        state_summary=(df.groupby(['Explosive State','Status'],dropna=False).size().reset_index(name='Stocks') if not df.empty else pd.DataFrame())
        _lab_update_v603(runtime,jid,total+1,total+2,'Excel','Explosive Radar V3 • workbook');_lab_check_v603(runtime,jid)
        excel=_feedback_workbook_v629({'Radar Summary':summary,'Current Explosive Radar V3':df,'Current State Summary':state_summary,'Skipped':pd.DataFrame(skipped)},{'Tab':'Explosive Universe Radar V3','Version':APP_VERSION,'Scope':scope,'History':history,'TargetPct':100*target,'Method':'Four-score ranking: Setup + State + geometric Setup×State consensus + historical analog/OOS Radar evidence; split-safe PRE-EXPLOSIVE / CONTINUATION BASE / RE-ACCELERATION states','RegularPreMove':'UNCHANGED — +5%/3D Pre-Move Discovery remains a separate normal-rise channel','ResearchOnly':'YES — no automatic Production promotion'})
        _lab_update_v603(runtime,jid,total+2,total+2,'Completed','Completed');_lab_publish_v603(runtime,jid,{'summary':summary,'radar':df,'state_summary':state_summary,'skipped':pd.DataFrame(skipped),'excel':excel})
    except _LabCancelled:_lab_publish_v603(runtime,jid,None,'stopped')
    except Exception as ex:_lab_fail_v603(runtime,jid,ex)



# -----------------------------------------------------------------------------
# V6.3.7 Regular Pre-Move Signature Lab
# Finds what is common BEFORE ordinary +2/+3/+5/+8% moves at 1H/2H and
# 1D/2D/3D/5D horizons.  Discovery is chronological 70%; the final 30% is
# untouched OOS validation.  This is research-only and does not change live entry.
# -----------------------------------------------------------------------------
def _regular_signature_indicator_names_v637():
    return [
        'EMA9 > EMA20','EMA9/20 bullish cross','MACD bullish cross','MACD histogram turn positive',
        'MACD histogram positive','MACD strengthening','RSI 50-70','Price > VWAP','VWAP reclaim',
        'RVOL >= 1.20','Volume acceleration','Directional bullish volume','CMF > 0','OBV accumulating',
        'A/D accumulating','Relative strength positive','Price > EMA20','Near 20D breakout',
        'Strong close location','ADX >= 25','Squeeze release','Fresh transitions >= 2'
    ]


def _regular_signature_mask_v637(active, names, idx):
    aset=set(active or []);m=0
    for n in aset:
        j=idx.get(n)
        if j is not None:m |= (1<<j)
    return int(m)


def _regular_signature_records_v637(feat,ticker,market,targets,horizons,timeframe='DAILY',sample_every=1):
    if feat is None or len(feat)<50:return [],None
    names=_regular_signature_indicator_names_v637();idx={n:i for i,n in enumerate(names)};maxh=max(horizons);rows=[]
    start=55;stop=max(start,len(feat)-maxh);step=max(1,int(sample_every))
    ca=pd.to_numeric(feat.get('corporate_action_flag',pd.Series(0,index=feat.index)),errors='coerce').fillna(0).to_numpy()
    for pos in range(start,stop,step):
        try:
            p=float(feat.iloc[pos].get('Close',np.nan))
            if not np.isfinite(p) or p<=0:continue
            if np.nansum(ca[pos:pos+maxh+1])>0:continue
            active=_feedback_replay_active_indicators_v630(feat.iloc[pos]);mask=_regular_signature_mask_v637(active,names,idx)
            if mask==0:continue
            d=pd.Timestamp(feat.index[pos])
            setup=_feedback_replay_setup_v631(feat.iloc[pos],.05,np.nan)
            for h in horizons:
                fut=pd.to_numeric(feat.iloc[pos+1:pos+1+h].get('High',pd.Series(dtype=float)),errors='coerce')
                if len(fut)<h:continue
                peak=float(fut.max())
                for target in targets:
                    hit=int(np.isfinite(peak) and peak>=p*(1+target))
                    rows.append((d,str(ticker),str(market),str(timeframe),int(h),float(target),mask,hit,float(setup.get('setup_score_v2',0) or 0),str(setup.get('freshness_state','')),bool(setup.get('distribution_risk',False)),int(setup.get('family_count',0) or 0),float(setup.get('move_consumed_pct',np.nan)) if np.isfinite(float(setup.get('move_consumed_pct',np.nan))) else np.nan))
        except Exception:
            continue
    # Current fully-known snapshot is deliberately excluded from historical labels
    # and used only after OOS evidence has been selected.
    cur=None
    try:
        rr=feat.iloc[-1];active=_feedback_replay_active_indicators_v630(rr);setup=_feedback_replay_setup_v631(rr,.05,np.nan)
        cur={'Ticker':str(ticker),'Market':str(market),'Timeframe':str(timeframe),'SignalDate':pd.Timestamp(feat.index[-1]),'Mask':_regular_signature_mask_v637(active,names,idx),'Setup Score':float(setup.get('setup_score_v2',0) or 0),'Active Indicators':' | '.join(active),'Families':setup.get('family_signature',''),'Freshness':setup.get('freshness_state',''),'Distribution Risk':bool(setup.get('distribution_risk',False)),'Independent Family Count':int(setup.get('family_count',0) or 0),'Move Consumed %':float(setup.get('move_consumed_pct',np.nan)) if np.isfinite(float(setup.get('move_consumed_pct',np.nan))) else np.nan}
    except Exception:pass
    return rows,cur


def _regular_signature_analyze_bucket_v637(df,names):
    if df.empty:return [],[],{}
    x=df.sort_values('Date').reset_index(drop=True);dates=sorted(pd.to_datetime(x.Date,errors='coerce').dropna().dt.normalize().unique())
    if len(dates)<12:return [],[],{}
    cut=max(1,min(len(dates)-1,int(math.floor(.70*len(dates)))));cutdate=pd.Timestamp(dates[cut-1])
    disc=(pd.to_datetime(x.Date).dt.normalize()<=cutdate).to_numpy();val=~disc
    hit=pd.to_numeric(x.Hit,errors='coerce').fillna(0).to_numpy(float);masks=pd.to_numeric(x.Mask,errors='coerce').fillna(0).astype(object).to_numpy()
    dbase=float(np.mean(hit[disc])) if disc.any() else np.nan;vbase=float(np.mean(hit[val])) if val.any() else np.nan
    target=float(x.Target.iloc[0]);lead=str(x.Lead.iloc[0]);tf=str(x.Timeframe.iloc[0]);market=str(x.Market.iloc[0]);dn=int(disc.sum());vn=int(val.sum())
    inds=[];uni=[]
    for j,name in enumerate(names):
        bit=1<<j;md=np.fromiter(((int(z)&bit)!=0 for z in masks),dtype=bool,count=len(x));nd=int((disc&md).sum());nv=int((val&md).sum())
        if nd<max(25,int(.003*dn)):continue
        dr=float(np.mean(hit[disc&md]));dl=dr/dbase if np.isfinite(dbase) and dbase>0 else np.nan
        vr=float(np.mean(hit[val&md])) if nv else np.nan;vl=vr/vbase if nv and np.isfinite(vbase) and vbase>0 else np.nan
        fam=_feedback_replay_indicator_family_v633(name);delta=(dr-dbase) if np.isfinite(dbase) else np.nan
        uni.append((name,fam,nd,dr,dl,delta))
        status='LOW SAMPLE' if nv<15 else ('OOS STRONG' if np.isfinite(vl) and vl>=1.15 and vr-vbase>=.04 else ('OOS POSITIVE' if np.isfinite(vl) and vl>=1.08 and vr-vbase>=.02 else ('FAILED' if np.isfinite(vl) and (vl<=.95 or vr-vbase<=-.02) else 'OOS MIXED')))
        inds.append({'Market':market,'Target %':100*target,'Lead Window':lead,'Timeframe':tf,'Indicator':name,'Family':fam,'Discovery N':nd,'Discovery Hit Rate %':100*dr,'Discovery Baseline %':100*dbase,'Discovery Lift x':dl,'Validation N':nv,'Validation Hit Rate %':100*vr if np.isfinite(vr) else np.nan,'Validation Baseline %':100*vbase,'Validation Lift x':vl,'Validation Delta pp':100*(vr-vbase) if np.isfinite(vr) and np.isfinite(vbase) else np.nan,'Status':status})
    # Discovery pool: max two signals per independent family, selected ONLY in discovery.
    pool=[]
    for fam in sorted({q[1] for q in uni if q[1]!='OTHER'}):
        qs=[q for q in uni if q[1]==fam and np.isfinite(q[4]) and q[4]>=1.03 and q[5]>0]
        qs=sorted(qs,key=lambda q:((q[3]-dbase)*math.log1p(q[2]),q[2]),reverse=True)[:2];pool.extend([q[0] for q in qs])
    pool=list(dict.fromkeys(pool))[:14];comb=[]
    nidx={n:i for i,n in enumerate(names)}
    for k in (2,3):
        for combo in combinations(pool,k):
            fams=[_feedback_replay_indicator_family_v633(n) for n in combo]
            if len(set(fams))<k:continue
            bits=[1<<nidx[n] for n in combo];mc=np.fromiter((all((int(z)&b)!=0 for b in bits) for z in masks),dtype=bool,count=len(x))
            nd=int((disc&mc).sum())
            if nd<max(25,int(.0025*dn)):continue
            dr=float(np.mean(hit[disc&mc]));dl=dr/dbase if dbase>0 else np.nan
            if not np.isfinite(dl) or dl<1.08 or dr-dbase<.025:continue
            nv=int((val&mc).sum());vr=float(np.mean(hit[val&mc])) if nv else np.nan;vl=vr/vbase if nv and vbase>0 else np.nan
            if nv<15:status='LOW SAMPLE'
            elif np.isfinite(vl) and vl>=1.18 and vr-vbase>=.05:status='OOS STRONG'
            elif np.isfinite(vl) and vl>=1.10 and vr-vbase>=.025:status='OOS POSITIVE'
            elif np.isfinite(vl) and (vl<=.95 or vr-vbase<=-.02):status='FAILED'
            else:status='OOS MIXED'
            comb.append({'Market':market,'Target %':100*target,'Lead Window':lead,'Timeframe':tf,'Combination':' + '.join(combo),'Families':' + '.join(fams),'Discovery N':nd,'Discovery Hit Rate %':100*dr,'Discovery Baseline %':100*dbase,'Discovery Lift x':dl,'Validation N':nv,'Validation Hit Rate %':100*vr if np.isfinite(vr) else np.nan,'Validation Baseline %':100*vbase,'Validation Lift x':vl,'Validation Delta pp':100*(vr-vbase) if np.isfinite(vr) and np.isfinite(vbase) else np.nan,'Status':status})
    meta={'Market':market,'Target %':100*target,'Lead Window':lead,'Timeframe':tf,'Discovery N':dn,'Validation N':vn,'Discovery Baseline %':100*dbase if np.isfinite(dbase) else np.nan,'Validation Baseline %':100*vbase if np.isfinite(vbase) else np.nan,'OOS Positive Combos':sum(1 for z in comb if z['Status'] in ('OOS STRONG','OOS POSITIVE'))}
    return inds,comb,meta



# -----------------------------------------------------------------------------
# V6.3.8 Market-specific Regular High-Confidence Funnel
# Broad signatures still use 70/30 discovery/OOS.  This second, stricter layer
# uses 60% discovery -> 20% selector -> 20% FINAL HOLDOUT so the final funnel
# is not scored on the same rows that promoted its combinations.
# -----------------------------------------------------------------------------
def _regular_signature_nested_funnel_v638(df,names):
    if df is None or df.empty:return [],[],{}
    x=df.sort_values('Date').reset_index(drop=True).copy()
    dates=sorted(pd.to_datetime(x.Date,errors='coerce').dropna().dt.normalize().unique())
    if len(dates)<20:return [],[],{}
    c1=max(1,min(len(dates)-2,int(math.floor(.60*len(dates)))))
    c2=max(c1+1,min(len(dates)-1,int(math.floor(.80*len(dates)))))
    d1=pd.Timestamp(dates[c1-1]);d2=pd.Timestamp(dates[c2-1]);dd=pd.to_datetime(x.Date).dt.normalize()
    disc=(dd<=d1).to_numpy();selector=((dd>d1)&(dd<=d2)).to_numpy();final=(dd>d2).to_numpy()
    hit=pd.to_numeric(x.Hit,errors='coerce').fillna(0).to_numpy(float);masks=pd.to_numeric(x.Mask,errors='coerce').fillna(0).astype(object).to_numpy()
    target=float(x.Target.iloc[0]);lead=str(x.Lead.iloc[0]);tf=str(x.Timeframe.iloc[0]);market=str(x.Market.iloc[0])
    bases={k:(float(np.mean(hit[m])) if m.any() else np.nan) for k,m in [('Discovery',disc),('Selector',selector),('Final',final)]}
    nidx={n:i for i,n in enumerate(names)}
    # Discovery-only pool: at most two representatives per independent family.
    uni=[]
    dn=int(disc.sum())
    for j,name in enumerate(names):
        bit=1<<j;md=np.fromiter(((int(z)&bit)!=0 for z in masks),dtype=bool,count=len(x));nd=int((disc&md).sum())
        if nd<max(20,int(.0025*max(1,dn))):continue
        dr=float(np.mean(hit[disc&md]));dl=dr/bases['Discovery'] if np.isfinite(bases['Discovery']) and bases['Discovery']>0 else np.nan
        fam=_feedback_replay_indicator_family_v633(name);uni.append((name,fam,nd,dr,dl,dr-bases['Discovery']))
    pool=[]
    for fam in sorted({q[1] for q in uni if q[1]!='OTHER'}):
        qs=[q for q in uni if np.isfinite(q[4]) and q[4]>=1.04 and q[5]>.01 and q[1]==fam]
        qs=sorted(qs,key=lambda q:((q[3]-bases['Discovery'])*math.log1p(q[2]),q[2]),reverse=True)[:2];pool.extend(q[0] for q in qs)
    pool=list(dict.fromkeys(pool))[:14]
    discovered=[]
    for k in (2,3):
        for combo in combinations(pool,k):
            fams=[_feedback_replay_indicator_family_v633(n) for n in combo]
            if len(set(fams))<k:continue
            bits=[1<<nidx[n] for n in combo];mc=np.fromiter((all((int(z)&b)!=0 for b in bits) for z in masks),dtype=bool,count=len(x))
            nd=int((disc&mc).sum())
            if nd<max(20,int(.002*max(1,dn))):continue
            dr=float(np.mean(hit[disc&mc]));dl=dr/bases['Discovery'] if bases['Discovery']>0 else np.nan
            if not np.isfinite(dl) or dl<1.08 or dr-bases['Discovery']<.02:continue
            sn=int((selector&mc).sum());sr=float(np.mean(hit[selector&mc])) if sn else np.nan;sl=sr/bases['Selector'] if sn and np.isfinite(bases['Selector']) and bases['Selector']>0 else np.nan
            promoted=bool(sn>=10 and np.isfinite(sl) and sl>=1.08 and sr-bases['Selector']>=.015)
            discovered.append({'Market':market,'Target %':100*target,'Lead Window':lead,'Timeframe':tf,'Combination':' + '.join(combo),'Families':' + '.join(fams),'Discovery N':nd,'Discovery Hit Rate %':100*dr,'Discovery Baseline %':100*bases['Discovery'],'Discovery Lift x':dl,'Selector N':sn,'Selector Hit Rate %':100*sr if np.isfinite(sr) else np.nan,'Selector Baseline %':100*bases['Selector'] if np.isfinite(bases['Selector']) else np.nan,'Selector Lift x':sl,'Promoted':promoted})
    promoted=[z for z in discovered if z['Promoted']]
    # Final holdout is touched only after promotion has finished.
    final_rows=x.loc[final].copy();fbase=bases['Final'];stage_rows=[]
    if len(final_rows):
        match_counts=[];family_counts=[]
        for _,r in final_rows.iterrows():
            mask=int(r.Mask or 0);matched=[];famset=set()
            for z in promoted:
                parts=[q.strip() for q in str(z['Combination']).split(' + ') if q.strip()];bits=[1<<nidx[q] for q in parts if q in nidx]
                if bits and all((mask&b)!=0 for b in bits):matched.append(z);famset.update(str(z.get('Families','')).split(' + '))
            match_counts.append(len(matched));family_counts.append(len([f for f in famset if f]))
        final_rows['_PromotedMatches']=match_counts;final_rows['_PromotedFamilies']=family_counts
        setup=pd.to_numeric(final_rows.get('SetupScore',0),errors='coerce').fillna(0)
        fresh=final_rows.get('FreshnessState',pd.Series('',index=final_rows.index)).astype(str).isin(['FRESH','DEVELOPING'])
        dist=final_rows.get('DistributionRisk',pd.Series(False,index=final_rows.index)).astype(bool)
        famcnt=pd.to_numeric(final_rows.get('FamilyCount',0),errors='coerce').fillna(0)
        consumed=pd.to_numeric(final_rows.get('MoveConsumedPct',np.nan),errors='coerce')
        not_late=consumed.isna() | (consumed<60)
        gates=[
            ('ANY PROMOTED COMBO',final_rows['_PromotedMatches']>=1),
            ('CONSENSUS 2+',final_rows['_PromotedMatches']>=2),
            ('+ SETUP >= 70',(final_rows['_PromotedMatches']>=2)&(setup>=70)),
            ('+ FRESH / NOT LATE',(final_rows['_PromotedMatches']>=2)&(setup>=70)&fresh&not_late),
            ('RESEARCH HIGH CONFIDENCE',(final_rows['_PromotedMatches']>=2)&(setup>=70)&fresh&not_late&(~dist)&(famcnt>=3)),
        ]
        for stage,m in gates:
            n=int(m.sum());hr=float(pd.to_numeric(final_rows.loc[m,'Hit'],errors='coerce').mean()) if n else np.nan;lift=hr/fbase if n and np.isfinite(fbase) and fbase>0 else np.nan;delta=hr-fbase if n and np.isfinite(fbase) else np.nan
            if n<20:status='LOW SAMPLE'
            elif np.isfinite(hr) and hr>=.70 and n>=30 and np.isfinite(lift) and lift>=1.20:status='70% RESEARCH TIER'
            elif np.isfinite(lift) and lift>=1.20 and delta>=.05:status='FINAL STRONG'
            elif np.isfinite(lift) and lift>=1.08 and delta>=.02:status='FINAL POSITIVE'
            elif np.isfinite(lift) and (lift<=.95 or delta<=-.02):status='FINAL FAILED'
            else:status='FINAL MIXED'
            stage_rows.append({'Market':market,'Target %':100*target,'Lead Window':lead,'Timeframe':tf,'Funnel Stage':stage,'Final Holdout N':n,'Final Hit Rate %':100*hr if np.isfinite(hr) else np.nan,'Final Baseline %':100*fbase if np.isfinite(fbase) else np.nan,'Final Lift x':lift,'Final Delta pp':100*delta if np.isfinite(delta) else np.nan,'Status':status,'Promoted Combinations':len(promoted)})
    positive={'FINAL STRONG','FINAL POSITIVE','70% RESEARCH TIER'}
    best_stage=None
    for row in stage_rows:
        if row['Status'] in positive:best_stage=row
    model={'Market':market,'Target %':100*target,'Lead Window':lead,'Timeframe':tf,'Promoted':promoted,'StageEvidence':stage_rows,'BestValidatedStage':best_stage or {},'FinalBaselinePct':100*fbase if np.isfinite(fbase) else np.nan}
    return stage_rows,discovered,model


def _regular_current_funnel_v638(cr,model,names):
    if not model:return {'stage':'NO VALIDATED FUNNEL','matches':0,'families':0,'evidence':{}}
    mask=int(cr.get('Mask',0) or 0);nidx={n:i for i,n in enumerate(names)};matched=[];famset=set()
    for z in model.get('Promoted',[]):
        parts=[q.strip() for q in str(z.get('Combination','')).split(' + ') if q.strip()];bits=[1<<nidx[q] for q in parts if q in nidx]
        if bits and all((mask&b)!=0 for b in bits):matched.append(z);famset.update(str(z.get('Families','')).split(' + '))
    m=len(matched);fams=len([f for f in famset if f]);setup=float(cr.get('Setup Score',0) or 0);fresh=str(cr.get('Freshness',''));dist=bool(cr.get('Distribution Risk',False));cons=pd.to_numeric(pd.Series([cr.get('Move Consumed %',np.nan)]),errors='coerce').iloc[0];not_late=(not np.isfinite(cons)) or cons<60
    conditions=[('ANY PROMOTED COMBO',m>=1),('CONSENSUS 2+',m>=2),('+ SETUP >= 70',m>=2 and setup>=70),('+ FRESH / NOT LATE',m>=2 and setup>=70 and fresh in ('FRESH','DEVELOPING') and not_late),('RESEARCH HIGH CONFIDENCE',m>=2 and setup>=70 and fresh in ('FRESH','DEVELOPING') and not_late and not dist and int(cr.get('Independent Family Count',0) or 0)>=3)]
    reached='NO CURRENT FUNNEL MATCH'
    for st,ok in conditions:
        if ok:reached=st
        else:break
    ev={r['Funnel Stage']:r for r in model.get('StageEvidence',[])}.get(reached,{})
    # Do not label a present-day row High Confidence unless that exact gate was positive on untouched final holdout.
    if reached=='RESEARCH HIGH CONFIDENCE' and ev.get('Status') not in ('FINAL STRONG','FINAL POSITIVE','70% RESEARCH TIER'):
        reached='FRESH QUALIFIED — HC NOT VALIDATED'
    return {'stage':reached,'matches':m,'families':fams,'evidence':ev}


def _regular_signature_worker_v637(runtime,jid,cfg):
    try:
        scope=str(cfg.get('scope','NASDAQ'));count=int(cfg.get('max_tickers',100));history=str(cfg.get('history','1y'));hour_history=str(cfg.get('hour_history','6mo'));sample_every=int(cfg.get('sample_every',2));use_hourly=bool(cfg.get('use_hourly',True))
        targets=(.02,.03,.05,.08);daily_h=(1,2,3,5);hour_h=(1,2);tickers=_research_validator_universe_v624(scope,count);total=max(1,len(tickers));records=[];current=[];skipped=[]
        for i,t in enumerate(tickers,1):
            _lab_check_v603(runtime,jid);_lab_update_v603(runtime,jid,i-1,total+3,t,'Regular Signature Lab • daily + hourly precursor snapshots')
            market=_market_for_ticker_v612(t);ok_any=False
            try:
                d=fetch_ohlcv(t,history,'1d')
                if d is not None and len(d)>=90:
                    fd=compute_features(d);phase=_market_phase(market);fd_use=fd.iloc[:-1].copy() if phase=='OPEN' and len(fd)>1 else fd;rr,cur=_regular_signature_records_v637(fd_use,t,market,targets,daily_h,'DAILY',sample_every);records.extend(rr);current.extend([cur] if cur else []);ok_any=True
                else:raise ValueError('not enough daily history')
            except Exception as ex:skipped.append({'Ticker':str(t),'Timeframe':'DAILY','Reason':f'{type(ex).__name__}: {ex}'})
            if use_hourly:
                try:
                    h=fetch_ohlcv(t,hour_history,'60m')
                    if h is not None and len(h)>=100:
                        try:h=confirmed_intraday_bars(h)
                        except Exception:pass
                        fh=compute_features(h,intraday=True);rr,cur=_regular_signature_records_v637(fh,t,market,targets,hour_h,'HOURLY',max(1,sample_every));records.extend(rr);current.extend([cur] if cur else []);ok_any=True
                    else:raise ValueError('not enough 60m history')
                except Exception as ex:skipped.append({'Ticker':str(t),'Timeframe':'HOURLY','Reason':f'{type(ex).__name__}: {ex}'})
        _lab_update_v603(runtime,jid,total,total+3,'Discovery','Regular Signature Lab • 70/30 chronological discovery/OOS');_lab_check_v603(runtime,jid)
        names=_regular_signature_indicator_names_v637();cols=['Date','Ticker','Market','Timeframe','Horizon','Target','Mask','Hit','SetupScore','FreshnessState','DistributionRisk','FamilyCount','MoveConsumedPct'];raw=pd.DataFrame(records,columns=cols)
        if not raw.empty:
            raw['Lead']=raw.apply(lambda r:f"{int(r.Horizon)}H" if r.Timeframe=='HOURLY' else f"{int(r.Horizon)}D",axis=1)
        inds=[];combs=[];summary=[];funnel_rows=[];promoted_rows=[];funnel_models={}
        if not raw.empty:
            for _,g in raw.groupby(['Market','Target','Lead','Timeframe'],sort=True):
                ii,cc,mm=_regular_signature_analyze_bucket_v637(g,names);inds.extend(ii);combs.extend(cc);summary.append(mm);ff,pp,fm=_regular_signature_nested_funnel_v638(g,names);funnel_rows.extend(ff);promoted_rows.extend(pp);funnel_models[(str(mm.get('Market')),float(mm.get('Target %')),str(mm.get('Lead Window')),str(mm.get('Timeframe')))]=fm
        ind_df=pd.DataFrame(inds);combo_df=pd.DataFrame(combs);summary_df=pd.DataFrame(summary);funnel_df=pd.DataFrame(funnel_rows);promoted_df=pd.DataFrame(promoted_rows)
        _lab_update_v603(runtime,jid,total+1,total+3,'Current radar','Regular Signature Lab • matching current snapshots to OOS-positive signatures');_lab_check_v603(runtime,jid)
        current_df=pd.DataFrame([x for x in current if x]);radar=[]
        if not current_df.empty and not combo_df.empty:
            nidx={n:i for i,n in enumerate(names)}
            good=combo_df[combo_df.Status.isin(['OOS STRONG','OOS POSITIVE'])].copy()
            for _,cr in current_df.iterrows():
                mask=int(cr.get('Mask',0) or 0);tf=str(cr.get('Timeframe',''))
                for (target,lead),gg in good[good.Timeframe.eq(tf) & good.Market.eq(str(cr.Market))].groupby(['Target %','Lead Window']):
                    matched=[]
                    for _,z in gg.iterrows():
                        parts=[q.strip() for q in str(z.Combination).split(' + ') if q.strip()];bits=[1<<nidx[q] for q in parts if q in nidx]
                        if bits and all((mask&b)!=0 for b in bits):matched.append(z)
                    if not matched:continue
                    mg=pd.DataFrame(matched);best=mg.sort_values(['Validation Lift x','Validation N'],ascending=[False,False]).iloc[0];cnt=len(mg);lift=float(best.get('Validation Lift x',np.nan));hr=float(best.get('Validation Hit Rate %',np.nan));base=float(best.get('Validation Baseline %',np.nan));score=float(np.clip(35+10*min(cnt,4)+20*max(0,(lift-1)) if np.isfinite(lift) else 35+10*min(cnt,4),0,100))
                    fm=funnel_models.get((str(cr.Market),float(target),str(lead),str(tf)),{});fr=_regular_current_funnel_v638(cr,fm,names);fe=fr.get('evidence') or {}
                    radar.append({'Ticker':cr.Ticker,'Market':cr.Market,'Target %':target,'Lead Window':lead,'Timeframe':tf,'Regular Signature Score':round(score,1),'OOS Positive Matches':cnt,'Best OOS Hit Rate %':hr,'Best OOS Baseline %':base,'Best OOS Lift x':lift,'Best Signature':best.Combination,'Setup Score':cr.get('Setup Score',np.nan),'Freshness':cr.get('Freshness',''),'Distribution Risk':cr.get('Distribution Risk',False),'Independent Family Count':cr.get('Independent Family Count',0),'Move Consumed %':cr.get('Move Consumed %',np.nan),'Funnel Stage':fr.get('stage','NO VALIDATED FUNNEL'),'Funnel Promoted Matches':fr.get('matches',0),'Funnel Family Count':fr.get('families',0),'Final Holdout N':fe.get('Final Holdout N',np.nan),'Final Holdout Hit Rate %':fe.get('Final Hit Rate %',np.nan),'Final Holdout Baseline %':fe.get('Final Baseline %',np.nan),'Final Holdout Lift x':fe.get('Final Lift x',np.nan),'Final Holdout Status':fe.get('Status',''),'Best Validated Funnel Stage':(fm.get('BestValidatedStage') or {}).get('Funnel Stage','NONE'),'Active Indicators':cr.get('Active Indicators','')})
        radar_df=pd.DataFrame(radar)
        if not radar_df.empty:
            _fo={'RESEARCH HIGH CONFIDENCE':0,'FRESH QUALIFIED — HC NOT VALIDATED':1,'+ FRESH / NOT LATE':2,'+ SETUP >= 70':3,'CONSENSUS 2+':4,'ANY PROMOTED COMBO':5,'NO VALIDATED FUNNEL':6,'NO CURRENT FUNNEL MATCH':7};radar_df['_funnel_ord']=radar_df['Funnel Stage'].map(_fo).fillna(8);radar_df=radar_df.sort_values(['_funnel_ord','Final Holdout Lift x','Regular Signature Score','Best OOS Lift x'],ascending=[True,False,False,False]).drop(columns='_funnel_ord').reset_index(drop=True)
        top_df=combo_df[combo_df.Status.isin(['OOS STRONG','OOS POSITIVE'])].copy() if not combo_df.empty else pd.DataFrame()
        if not top_df.empty:top_df=top_df.sort_values(['Validation Lift x','Validation N'],ascending=[False,False]).reset_index(drop=True)
        _lab_update_v603(runtime,jid,total+2,total+3,'Excel','Regular Signature Lab • workbook');_lab_check_v603(runtime,jid)
        meta={'Tab':'Regular Pre-Move Signature Lab','Version':APP_VERSION,'Scope':scope,'RequestedStocks':len(tickers),'DailyHistory':history,'HourlyHistory':hour_history if use_hourly else 'OFF','Targets':'2% / 3% / 5% / 8%','LeadWindows':'1H / 2H / 1D / 2D / 3D / 5D','DiscoverySplit':'70% chronological','ValidationSplit':'30% untouched OOS','SampleEvery':sample_every,'Meaning':'At each causal snapshot, tests whether the target is reached within the stated future window. No future feature is used.','NestedFunnel':'60% discovery / 20% selector / 20% untouched FINAL HOLDOUT','ResearchOnly':'YES — does not change Production Entry automatically'}
        excel=_feedback_workbook_v629({'Signature Summary':summary_df,'High Confidence Funnel':funnel_df,'Promoted Signatures 60-20':promoted_df,'Top OOS Signatures':top_df,'Combination Signatures':combo_df,'Indicator Signatures':ind_df,'Current Regular Radar':radar_df,'Skipped':pd.DataFrame(skipped)},meta);_persist_regular_signature_overlay_v638(radar_df,cfg)
        _lab_update_v603(runtime,jid,total+3,total+3,'Completed','Completed');_lab_publish_v603(runtime,jid,{'summary':summary_df,'funnel':funnel_df,'promoted':promoted_df,'top':top_df,'combinations':combo_df,'indicators':ind_df,'radar':radar_df,'skipped':pd.DataFrame(skipped),'excel':excel})
    except _LabCancelled:_lab_publish_v603(runtime,jid,None,'stopped')
    except Exception as ex:_lab_fail_v603(runtime,jid,ex)


def _feedback_replay_apply_meta_v631(df):
    """Strict-date rolling empirical-Bayes meta probability.

    V6.3.2 keeps the V6.3.1 mathematics but replaces the quadratic replay
    implementation with cumulative sufficient statistics.  Every probability
    for date D still uses clean outcomes from dates strictly before D, so
    same-day cross-sectional outcomes cannot leak into one another.
    """
    if df is None or not isinstance(df,pd.DataFrame) or df.empty:return df
    z=df.copy();z['_date']=pd.to_datetime(z['SignalDate'],errors='coerce');z=z.sort_values(['_date','Ticker']).reset_index(drop=True)
    for c,v in [('MetaProbability',np.nan),('MetaSample',0),('MetaLift',np.nan),('HighConfidence',False)]:z[c]=v

    # Pre-compute the exact keys used by V6.3.1.  We then maintain cumulative
    # (count, wins) dictionaries and update them only after a complete signal
    # date has been scored.  This is O(N) instead of repeatedly rebuilding and
    # filtering the entire prior history for every replay row.
    z['_meta_family_signature']=z.get('FamilySignature',pd.Series('',index=z.index)).fillna('').astype(str)
    z['_meta_freshness']=z.get('FreshnessState',pd.Series('',index=z.index)).fillna('').astype(str)
    z['_meta_score_bucket']=(pd.to_numeric(z.get('SetupScoreV2',0),errors='coerce').fillna(0)//10).astype(int)
    cm=z.get('CoreMomentum',pd.Series(False,index=z.index)).fillna(False).astype(bool)
    cv=z.get('CoreVolumeFlow',pd.Series(False,index=z.index)).fillna(False).astype(bool)
    z['_meta_core_pattern']=cm.astype(int).astype(str)+cv.astype(int).astype(str)

    # V6.3.1 attempted to include a 'FamilyCount' meta feature, but the replay
    # frame exposes 'IndependentFamilyCount'; therefore that feature was never
    # active in the published V6.3.1 probabilities.  Keep it out here so this
    # hotfix is performance-only and reproduces prior results exactly.
    key_cols=('_meta_family_signature','_meta_freshness','_meta_score_bucket','_meta_core_pattern')
    stats={c:{} for c in key_cols}
    global_n=0;global_wins=0.0

    for _,idxs in z.groupby('_date',sort=True,dropna=False).groups.items():
        idxs=list(idxs)
        n=int(global_n)
        if n:
            gw=float(global_wins/n);global_p=float((global_wins+8*.50)/(n+8))
        else:
            gw=np.nan;global_p=.50

        for idx in idxs:
            r=z.loc[idx];estimates=[];supports=[]
            if n:
                for col in key_cols:
                    key=r.get(col)
                    nn,wwins=stats[col].get(key,(0,0.0))
                    if nn:
                        pp=float((wwins+12*global_p)/(nn+12));estimates.append(pp);supports.append(int(nn))
            if estimates:
                weights=np.asarray([min(80,max(5,x)) for x in supports],float)
                p=float((np.dot(weights,np.asarray(estimates,float))+20*global_p)/(weights.sum()+20))
                support=int(max(supports))
            else:
                p=float(global_p);support=int(n)
            z.at[idx,'MetaProbability']=100*p;z.at[idx,'MetaSample']=support;z.at[idx,'MetaLift']=p/gw if np.isfinite(gw) and gw>0 else np.nan
            hc=bool(r.get('CandidateV2',False) and float(r.get('SetupScoreV2',0))>=72 and int(r.get('IndependentFamilyCount',0) or 0)>=4 and str(r.get('FreshnessState',''))=='FRESH' and float(r.get('MoveConsumedPct',999))<45 and not bool(r.get('DistributionRisk',False)) and support>=50 and p>=.65)
            z.at[idx,'HighConfidence']=hc

        # Strict-date causality: today's outcomes become available only after every
        # row on this date has received its probability.
        for idx in idxs:
            outcome=str(z.at[idx,'CleanOutcome'])
            if outcome not in ('WIN','LOSS'):continue
            win=1.0 if outcome=='WIN' else 0.0
            global_n+=1;global_wins+=win
            for col in key_cols:
                key=z.at[idx,col];nn,wwins=stats[col].get(key,(0,0.0));stats[col][key]=(nn+1,wwins+win)

    return z.drop(columns=['_date',*key_cols],errors='ignore')


def _feedback_store_replay_v630(run_id,rows,cfg,successful_tickers,combinations_df=None,combo_folds_df=None,consensus_combos_df=None,consensus_gates_df=None):
    con=_feedback_conn_v600()
    try:
        con.execute('DELETE FROM replay_events WHERE run_id=?',(str(run_id),))
        cols=['run_id','ticker','market','signal_date','price','quant_score','early_score','entry_score','atr_pct','target1','invalidation','end_return','max_favorable','max_adverse','first_event','clean_outcome','indicators','candidate','legacy_candidate','candidate_v2','high_confidence','family_signature','family_count','freshness_state','move_consumed_pct','extension_atr','distribution_risk','setup_score_v2','meta_probability','meta_sample','meta_lift','r_multiple','recent_2d_return','core_momentum','core_volume_flow','candidate_rule_version','combo_phase','combo_candidate_v3','combo_high_confidence_v3','combo_70_research','combo_match_count','combo_best_signature','combo_best_discovery_rate','combo_best_discovery_lift','consensus_phase_v634','consensus_match_count_v634','consensus_family_count_v634','consensus_candidate_v634']
        vals=[]
        for r in rows:
            vals.append((str(run_id),str(r.get('Ticker','')),str(r.get('Market','')),str(r.get('SignalDate','')),r.get('Price'),r.get('QuantScore'),r.get('EarlyScore'),r.get('EntryScore'),r.get('ATRPct'),r.get('Target1'),r.get('Invalidation'),r.get('EndReturn'),r.get('MFE'),r.get('MAE'),str(r.get('FirstEvent','')),str(r.get('CleanOutcome','')),str(r.get('Indicators','')),int(bool(r.get('CandidateV2',r.get('Candidate',False)))),int(bool(r.get('LegacyCandidate',False))),int(bool(r.get('CandidateV2',False))),int(bool(r.get('HighConfidence',False))),str(r.get('FamilySignature','')),int(r.get('IndependentFamilyCount',0) or 0),str(r.get('FreshnessState','')),r.get('MoveConsumedPct'),r.get('ExtensionATR'),int(bool(r.get('DistributionRisk',False))),r.get('SetupScoreV2'),r.get('MetaProbability'),int(r.get('MetaSample',0) or 0),r.get('MetaLift'),r.get('RMultiple'),r.get('Recent2DReturn'),int(bool(r.get('CoreMomentum',False))),int(bool(r.get('CoreVolumeFlow',False))),str(r.get('CandidateRuleVersion','V6.3.4')),str(r.get('ComboPhase','')),int(bool(r.get('ComboCandidateV3',False))),int(bool(r.get('ComboHighConfidenceV3',False))),int(bool(r.get('Combo70Research',False))),int(r.get('ComboMatchCount',0) or 0),str(r.get('ComboBestSignature','')),r.get('ComboBestDiscoveryRate'),r.get('ComboBestDiscoveryLift'),str(r.get('ConsensusPhaseV634','')),int(r.get('ConsensusMatchCountV634',0) or 0),int(r.get('ConsensusFamilyCountV634',0) or 0),int(bool(r.get('ConsensusCandidateV634',False)))))
        if vals:
            q=','.join(['?']*len(cols));con.executemany(f"INSERT OR REPLACE INTO replay_events({','.join(cols)}) VALUES({q})",vals)
        con.execute('DELETE FROM replay_combinations WHERE run_id=?',(str(run_id),))
        con.execute('DELETE FROM replay_combo_folds WHERE run_id=?',(str(run_id),))
        con.execute('DELETE FROM replay_consensus_combos WHERE run_id=?',(str(run_id),))
        con.execute('DELETE FROM replay_consensus_gates WHERE run_id=?',(str(run_id),))
        if isinstance(combinations_df,pd.DataFrame) and not combinations_df.empty:
            for _,r in combinations_df.iterrows():
                con.execute("INSERT OR REPLACE INTO replay_combinations VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(
                    str(run_id),str(r.get('Combination','')),int(r.get('Size',0) or 0),str(r.get('Families','')),int(r.get('Discovery Rank',0) or 0),float(r.get('Discovery Score',np.nan)) if pd.notna(r.get('Discovery Score')) else None,
                    int(r.get('Discovery N',0) or 0),int(r.get('Discovery Wins',0) or 0),float(r.get('Discovery Success %',np.nan)) if pd.notna(r.get('Discovery Success %')) else None,float(r.get('Discovery Baseline %',np.nan)) if pd.notna(r.get('Discovery Baseline %')) else None,float(r.get('Discovery Lift x',np.nan)) if pd.notna(r.get('Discovery Lift x')) else None,float(r.get('Discovery Delta pp',np.nan)) if pd.notna(r.get('Discovery Delta pp')) else None,int(r.get('Discovery Stocks',0) or 0),
                    int(r.get('Validation N',0) or 0),int(r.get('Validation Wins',0) or 0),float(r.get('Validation Success %',np.nan)) if pd.notna(r.get('Validation Success %')) else None,float(r.get('Validation Baseline %',np.nan)) if pd.notna(r.get('Validation Baseline %')) else None,float(r.get('Validation Lift x',np.nan)) if pd.notna(r.get('Validation Lift x')) else None,float(r.get('Validation Delta pp',np.nan)) if pd.notna(r.get('Validation Delta pp')) else None,int(r.get('Validation Stocks',0) or 0),
                    int(r.get('Positive Validation Folds',0) or 0),int(r.get('Usable Validation Folds',0) or 0),float(r.get('Stability Gap pp',np.nan)) if pd.notna(r.get('Stability Gap pp')) else None,str(r.get('Research Tier','')),str(r.get('OOS Status',''))))
        if isinstance(combo_folds_df,pd.DataFrame) and not combo_folds_df.empty:
            for _,r in combo_folds_df.iterrows():
                con.execute("INSERT OR REPLACE INTO replay_combo_folds VALUES(?,?,?,?,?,?,?,?,?,?)",(
                    str(run_id),str(r.get('Combination','')),int(r.get('Fold',0) or 0),int(r.get('Resolved',0) or 0),int(r.get('Wins',0) or 0),float(r.get('Success Rate %',np.nan)) if pd.notna(r.get('Success Rate %')) else None,float(r.get('Fold Baseline %',np.nan)) if pd.notna(r.get('Fold Baseline %')) else None,float(r.get('Lift x',np.nan)) if pd.notna(r.get('Lift x')) else None,float(r.get('Delta pp',np.nan)) if pd.notna(r.get('Delta pp')) else None,int(r.get('Stocks',0) or 0)))
        if isinstance(consensus_combos_df,pd.DataFrame) and not consensus_combos_df.empty:
            for _,r in consensus_combos_df.iterrows():
                con.execute("INSERT OR REPLACE INTO replay_consensus_combos VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(
                    str(run_id),str(r.get('Market','')),str(r.get('Combination','')),str(r.get('Families','')),int(r.get('Discovery N',0) or 0),float(r.get('Discovery Success %',np.nan)) if pd.notna(r.get('Discovery Success %')) else None,float(r.get('Discovery Lift x',np.nan)) if pd.notna(r.get('Discovery Lift x')) else None,
                    int(r.get('Selector N',0) or 0),float(r.get('Selector Success %',np.nan)) if pd.notna(r.get('Selector Success %')) else None,float(r.get('Selector Lift x',np.nan)) if pd.notna(r.get('Selector Lift x')) else None,
                    int(r.get('Final Holdout N',0) or 0),float(r.get('Final Holdout Success %',np.nan)) if pd.notna(r.get('Final Holdout Success %')) else None,float(r.get('Final Holdout Lift x',np.nan)) if pd.notna(r.get('Final Holdout Lift x')) else None,str(r.get('Status',''))))
        if isinstance(consensus_gates_df,pd.DataFrame) and not consensus_gates_df.empty:
            for _,r in consensus_gates_df.iterrows():
                con.execute("INSERT OR REPLACE INTO replay_consensus_gates VALUES(?,?,?,?,?,?,?,?,?,?,?)",(
                    str(run_id),str(r.get('Market','')),str(r.get('Gate','')),int(r.get('Resolved',0) or 0),int(r.get('Wins',0) or 0),float(r.get('Success Rate %',np.nan)) if pd.notna(r.get('Success Rate %')) else None,float(r.get('Final Baseline %',np.nan)) if pd.notna(r.get('Final Baseline %')) else None,float(r.get('Lift x',np.nan)) if pd.notna(r.get('Lift x')) else None,float(r.get('Delta pp',np.nan)) if pd.notna(r.get('Delta pp')) else None,float(r.get('Expectancy R',np.nan)) if pd.notna(r.get('Expectancy R')) else None,str(r.get('Meaning',''))))
        clean=sum(1 for r in rows if str(r.get('CleanOutcome')) in ('WIN','LOSS'))
        con.execute('INSERT OR REPLACE INTO replay_runs(run_id,created_at,scope,history,target_pct,horizon_days,sample_every,requested_tickers,successful_tickers,event_rows,clean_rows) VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                    (str(run_id),datetime.utcnow().replace(microsecond=0).isoformat()+'Z',str(cfg.get('scope','')),str(cfg.get('history','')),float(cfg.get('target_pct',.05)),int(cfg.get('horizon_days',3)),int(cfg.get('sample_every',5)),len(cfg.get('tickers',[])),int(successful_tickers),len(rows),clean))
        old_runs=[x[0] for x in con.execute('SELECT run_id FROM replay_runs ORDER BY created_at DESC LIMIT -1 OFFSET 5').fetchall()]
        for old_id in old_runs:
            con.execute('DELETE FROM replay_events WHERE run_id=?',(str(old_id),));con.execute('DELETE FROM replay_combinations WHERE run_id=?',(str(old_id),));con.execute('DELETE FROM replay_combo_folds WHERE run_id=?',(str(old_id),));con.execute('DELETE FROM replay_consensus_combos WHERE run_id=?',(str(old_id),));con.execute('DELETE FROM replay_consensus_gates WHERE run_id=?',(str(old_id),));con.execute('DELETE FROM replay_runs WHERE run_id=?',(str(old_id),))
        con.commit()
    finally:con.close()
    _feedback_schedule_remote_push_v630()


def _feedback_replay_frames_v630(latest_only=True):
    try:
        con=_feedback_conn_v600();runs=pd.read_sql_query('SELECT * FROM replay_runs ORDER BY created_at DESC',con)
        if latest_only and not runs.empty:
            rid=str(runs.iloc[0]['run_id']);ev=pd.read_sql_query('SELECT * FROM replay_events WHERE run_id=? ORDER BY signal_date DESC,ticker',con,params=(rid,))
        else:ev=pd.read_sql_query('SELECT * FROM replay_events ORDER BY signal_date DESC,ticker',con)
        con.close();return runs,ev
    except Exception:return pd.DataFrame(),pd.DataFrame()



def _feedback_replay_combo_frames_v633(latest_only=True):
    try:
        con=_feedback_conn_v600();runs=pd.read_sql_query('SELECT * FROM replay_runs ORDER BY created_at DESC',con)
        if latest_only and not runs.empty:
            rid=str(runs.iloc[0]['run_id']);c=pd.read_sql_query('SELECT * FROM replay_combinations WHERE run_id=? ORDER BY discovery_rank',con,params=(rid,));f=pd.read_sql_query('SELECT * FROM replay_combo_folds WHERE run_id=? ORDER BY combination,fold',con,params=(rid,))
        else:
            c=pd.read_sql_query('SELECT * FROM replay_combinations ORDER BY run_id,discovery_rank',con);f=pd.read_sql_query('SELECT * FROM replay_combo_folds ORDER BY run_id,combination,fold',con)
        con.close()
        ren={'combination':'Combination','combo_size':'Size','families':'Families','discovery_rank':'Discovery Rank','discovery_score':'Discovery Score','discovery_n':'Discovery N','discovery_wins':'Discovery Wins','discovery_success':'Discovery Success %','discovery_baseline':'Discovery Baseline %','discovery_lift':'Discovery Lift x','discovery_delta':'Discovery Delta pp','discovery_stocks':'Discovery Stocks','validation_n':'Validation N','validation_wins':'Validation Wins','validation_success':'Validation Success %','validation_baseline':'Validation Baseline %','validation_lift':'Validation Lift x','validation_delta':'Validation Delta pp','validation_stocks':'Validation Stocks','positive_folds':'Positive Validation Folds','usable_folds':'Usable Validation Folds','stability_gap':'Stability Gap pp','research_tier':'Research Tier','oos_status':'OOS Status'}
        if not c.empty:c=c.rename(columns=ren)
        fren={'combination':'Combination','fold':'Fold','resolved':'Resolved','wins':'Wins','success_rate':'Success Rate %','baseline_rate':'Fold Baseline %','lift':'Lift x','delta_pp':'Delta pp','stocks':'Stocks'}
        if not f.empty:f=f.rename(columns=fren)
        return c,f
    except Exception:return pd.DataFrame(),pd.DataFrame()


def _feedback_replay_consensus_frames_v634(latest_only=True):
    try:
        con=_feedback_conn_v600();runs=pd.read_sql_query('SELECT * FROM replay_runs ORDER BY created_at DESC',con)
        if latest_only and not runs.empty:
            rid=str(runs.iloc[0]['run_id']);c=pd.read_sql_query('SELECT * FROM replay_consensus_combos WHERE run_id=? ORDER BY market,selector_lift DESC',con,params=(rid,));g=pd.read_sql_query('SELECT * FROM replay_consensus_gates WHERE run_id=? ORDER BY market,gate',con,params=(rid,))
        else:
            c=pd.read_sql_query('SELECT * FROM replay_consensus_combos ORDER BY run_id,market,selector_lift DESC',con);g=pd.read_sql_query('SELECT * FROM replay_consensus_gates ORDER BY run_id,market,gate',con)
        con.close()
        if not c.empty:c=c.rename(columns={'market':'Market','combination':'Combination','families':'Families','discovery_n':'Discovery N','discovery_success':'Discovery Success %','discovery_lift':'Discovery Lift x','selector_n':'Selector N','selector_success':'Selector Success %','selector_lift':'Selector Lift x','final_n':'Final Holdout N','final_success':'Final Holdout Success %','final_lift':'Final Holdout Lift x','status':'Status'})
        if not g.empty:g=g.rename(columns={'market':'Market','gate':'Gate','resolved':'Resolved','wins':'Wins','success_rate':'Success Rate %','baseline_rate':'Final Baseline %','lift':'Lift x','delta_pp':'Delta pp','expectancy_r':'Expectancy R','meaning':'Meaning'})
        return c,g
    except Exception:return pd.DataFrame(),pd.DataFrame()

def _feedback_replay_scorecards_v631(events):
    """V6.3.1: baseline, V2 gate, High Confidence, indicators, stocks, calibration."""
    e=events.copy() if isinstance(events,pd.DataFrame) else pd.DataFrame()
    if e.empty:return (pd.DataFrame(),)*5
    # Normalize either live worker column names or SQLite snake_case names.
    ren={'CleanOutcome':'clean_outcome','Indicators':'indicators','Ticker':'ticker','MFE':'max_favorable','MAE':'max_adverse','EndReturn':'end_return','CandidateV2':'candidate_v2','LegacyCandidate':'legacy_candidate','HighConfidence':'high_confidence','RMultiple':'r_multiple','MetaProbability':'meta_probability','MetaSample':'meta_sample','FamilySignature':'family_signature','IndependentFamilyCount':'family_count','FreshnessState':'freshness_state','SetupScoreV2':'setup_score_v2'}
    for a,b in ren.items():
        if a in e and b not in e:e[b]=e[a]
    clean=e[e.get('clean_outcome',pd.Series('',index=e.index)).astype(str).isin(['WIN','LOSS'])].copy();clean['Win']=clean['clean_outcome'].eq('WIN').astype(float) if not clean.empty else np.nan
    def bitcol(name):return pd.to_numeric(e.get(name,0),errors='coerce').fillna(0).eq(1)
    all_clean=clean
    legacy=clean[pd.to_numeric(clean.get('legacy_candidate',0),errors='coerce').fillna(0).eq(1)] if not clean.empty else clean
    cand=clean[pd.to_numeric(clean.get('candidate_v2',clean.get('candidate',0)),errors='coerce').fillna(0).eq(1)] if not clean.empty else clean
    high=clean[pd.to_numeric(clean.get('high_confidence',0),errors='coerce').fillna(0).eq(1)] if not clean.empty else clean
    def stats(g):
        n=len(g);w=int(g['Win'].sum()) if n else 0;rate=100*w/n if n else np.nan;er=float(pd.to_numeric(g.get('r_multiple'),errors='coerce').mean()) if n and 'r_multiple' in g else np.nan
        return n,w,n-w,rate,er
    bn,bw,bl,br,be=stats(all_clean);ln,lw,ll,lr,le=stats(legacy);cn,cw,cl,cr,ce=stats(cand);hn,hw,hl,hr,he=stats(high)
    headline=pd.DataFrame([{
        'All Clean Baseline %':br,'All Clean N':bn,
        'Legacy Candidate %':lr,'Legacy Resolved':ln,'Legacy Lift x':lr/br if np.isfinite(lr) and np.isfinite(br) and br>0 else np.nan,
        'V2 Candidate Success %':cr,'V2 Candidate Resolved':cn,'V2 Wins':cw,'V2 Losses':cl,'V2 Lift x':cr/br if np.isfinite(cr) and np.isfinite(br) and br>0 else np.nan,'V2 Delta pp':cr-br if np.isfinite(cr) and np.isfinite(br) else np.nan,'V2 Expectancy R':ce,
        'High Confidence Success %':hr,'High Confidence Resolved':hn,'HC Wins':hw,'HC Losses':hl,'HC Lift x':hr/br if np.isfinite(hr) and np.isfinite(br) and br>0 else np.nan,'HC Delta pp':hr-br if np.isfinite(hr) and np.isfinite(br) else np.nan,'HC Expectancy R':he,
        'Definition':'Causal DAILY replay V2. High Confidence requires independent families + fresh/not-extended + no distribution + >=65% causal meta probability with >=50 prior matching observations.'
    }])
    gates=pd.DataFrame([
        {'Gate':'ALL CLEAN BASELINE','Resolved':bn,'Wins':bw,'Losses':bl,'Success Rate %':br,'Lift vs All x':1.0 if bn else np.nan,'Expectancy R':be,'Meaning':'All sampled historical rows'},
        {'Gate':'LEGACY V6.3.0','Resolved':ln,'Wins':lw,'Losses':ll,'Success Rate %':lr,'Lift vs All x':lr/br if np.isfinite(lr) and np.isfinite(br) and br>0 else np.nan,'Expectancy R':le,'Meaning':'Old score-only candidate rule for audit'},
        {'Gate':'V2 CANDIDATE','Resolved':cn,'Wins':cw,'Losses':cl,'Success Rate %':cr,'Lift vs All x':cr/br if np.isfinite(cr) and np.isfinite(br) and br>0 else np.nan,'Expectancy R':ce,'Meaning':'Independent families + freshness + extension/distribution guards'},
        {'Gate':'HIGH CONFIDENCE','Resolved':hn,'Wins':hw,'Losses':hl,'Success Rate %':hr,'Lift vs All x':hr/br if np.isfinite(hr) and np.isfinite(br) and br>0 else np.nan,'Expectancy R':he,'Meaning':'V2 + strictly-prior causal Meta Probability >=65%; quality over quantity'},
    ])
    indicators=[];base=float(all_clean['Win'].mean()) if not all_clean.empty else np.nan
    if not all_clean.empty and 'indicators' in all_clean:
        def split_ind(txt):return [x.strip() for x in str(txt or '').split(' | ') if x.strip() and x.strip().lower()!='nan']
        names=sorted({z for txt in all_clean['indicators'].fillna('').astype(str) for z in split_ind(txt)})
        for name in names:
            mask=all_clean['indicators'].fillna('').astype(str).apply(lambda txt:name in split_ind(txt));g=all_clean[mask];n=len(g)
            if n<5:continue
            rate=float(g['Win'].mean());lift=rate/base if np.isfinite(base) and base>0 else np.nan;delta=100*(rate-base) if np.isfinite(base) else np.nan
            status='LOW SAMPLE' if n<20 else ('WORKED' if np.isfinite(lift) and lift>=1.05 and delta>=2 else ('FAILED' if np.isfinite(lift) and lift<=.95 and delta<=-2 else 'MIXED'))
            indicators.append({'Type':'Indicator','Indicator / Family':name,'Resolved':n,'Success Rate %':100*rate,'All-row Baseline %':100*base if np.isfinite(base) else np.nan,'Lift x':lift,'Delta pp':delta,'Status':status})
    if not all_clean.empty and 'family_signature' in all_clean:
        fam_names=['MOMENTUM','VOLUME','FLOW','RELATIVE_STRENGTH','TREND','STRUCTURE','TRANSITION_BREADTH']
        fs=all_clean['family_signature'].fillna('').astype(str)
        for fam in fam_names:
            g=all_clean[fs.str.contains(fam,regex=False)];n=len(g)
            if n<5:continue
            rate=float(g['Win'].mean());lift=rate/base if np.isfinite(base) and base>0 else np.nan;delta=100*(rate-base) if np.isfinite(base) else np.nan
            status='LOW SAMPLE' if n<20 else ('WORKED' if np.isfinite(lift) and lift>=1.05 and delta>=2 else ('FAILED' if np.isfinite(lift) and lift<=.95 and delta<=-2 else 'MIXED'))
            indicators.append({'Type':'Independent Family','Indicator / Family':fam,'Resolved':n,'Success Rate %':100*rate,'All-row Baseline %':100*base if np.isfinite(base) else np.nan,'Lift x':lift,'Delta pp':delta,'Status':status})
    ind=pd.DataFrame(indicators)
    if not ind.empty:
        order={'WORKED':0,'MIXED':1,'FAILED':2,'LOW SAMPLE':3};ind['_o']=ind.Status.map(order).fillna(9);ind=ind.sort_values(['_o','Lift x','Resolved'],ascending=[True,False,False]).drop(columns=['_o']).reset_index(drop=True)
    stocks=[]
    cand_all=e[pd.to_numeric(e.get('candidate_v2',e.get('candidate',0)),errors='coerce').fillna(0).eq(1)].copy()
    if not cand_all.empty:
        for t,g in cand_all.groupby('ticker'):
            gc=g[g['clean_outcome'].isin(['WIN','LOSS'])].copy();n=len(gc);w=int((gc['clean_outcome']=='WIN').sum());rate=100*w/n if n else np.nan
            status='LOW SAMPLE / WAITING' if n<5 else ('SUCCESS' if rate>=55 else ('FAILURE' if rate<=45 else 'MIXED'))
            stocks.append({'Ticker':str(t),'V2 Candidate Rows':len(g),'Resolved':n,'Wins':w,'Losses':n-w,'Success Rate %':rate,'High Confidence Rows':int(pd.to_numeric(g.get('high_confidence',0),errors='coerce').fillna(0).eq(1).sum()),'Avg Meta Probability %':pd.to_numeric(g.get('meta_probability'),errors='coerce').mean(),'Avg MFE %':100*pd.to_numeric(g.get('max_favorable'),errors='coerce').mean(),'Avg MAE %':100*pd.to_numeric(g.get('max_adverse'),errors='coerce').mean(),'Model Status':status})
    stocks=pd.DataFrame(stocks)
    cal=[]
    if not clean.empty and 'meta_probability' in clean:
        mp=pd.to_numeric(clean['meta_probability'],errors='coerce');ms=pd.to_numeric(clean.get('meta_sample',0),errors='coerce').fillna(0)
        valid=clean[np.isfinite(mp) & (ms>=20)].copy();valid['_p']=pd.to_numeric(valid['meta_probability'],errors='coerce')
        for lo,hi in [(0,50),(50,55),(55,60),(60,65),(65,70),(70,80),(80,101)]:
            g=valid[(valid['_p']>=lo)&(valid['_p']<hi)];n=len(g)
            if not n:continue
            cal.append({'Meta Probability Bucket':f'{lo}-{hi if hi<=100 else 100}%','Resolved':n,'Predicted Avg %':float(g['_p'].mean()),'Actual Success %':100*float(g['Win'].mean()),'Calibration Error pp':100*float(g['Win'].mean())-float(g['_p'].mean()),'Avg Prior Support':pd.to_numeric(g.get('meta_sample'),errors='coerce').mean()})
    return headline,ind,stocks,gates,pd.DataFrame(cal)


def _feedback_replay_scorecards_v630(events):
    # Compatibility wrapper for older callers; V6.3.1 callers use the extended function.
    h,i,s,_,_=_feedback_replay_scorecards_v631(events);return h,i,s


def _feedback_learning_v611(merged, half_life_days=60):
    """Recency-weighted live feedback. Recent resolved observations matter more,
    but low-sample rows are explicitly marked and never auto-promote production."""
    if merged is None or merged.empty:return pd.DataFrame(),pd.DataFrame()
    x=_feedback_independent_rows_v63934(merged,require_valid_plan=True);x['ts_dt']=pd.to_datetime(x.get('ts_utc'),errors='coerce',utc=True)
    now=pd.Timestamp.now(tz='UTC');age=(now-x['ts_dt']).dt.total_seconds()/86400.0
    x['RecencyWeight']=np.exp(-np.log(2)*age.clip(lower=0)/max(float(half_life_days),1.0))
    x['ResolvedWin']=x.get('first_event','').astype(str).map(lambda v:1.0 if v.startswith('TARGET1 FIRST') else (0.0 if v.startswith('INVALIDATION FIRST') else np.nan))
    clean=x[np.isfinite(pd.to_numeric(x['ResolvedWin'],errors='coerce'))].copy()
    if 'optimized_stage' in clean:clean['optimized_confirmed']=clean['optimized_stage'].astype(str).eq('OPTIMIZED CONFIRMED').astype(int)
    if 'entry_state' in clean:clean['production_confirmed']=clean['entry_state'].astype(str).eq('CONFIRMED ENTRY').astype(int)
    if clean.empty:return pd.DataFrame(),pd.DataFrame()
    def wmean(g,col):
        v=pd.to_numeric(g[col],errors='coerce');w=pd.to_numeric(g['RecencyWeight'],errors='coerce');m=np.isfinite(v)&np.isfinite(w)&(w>0)
        return float(np.average(v[m],weights=w[m])) if m.any() else np.nan
    summaries=[]
    for keys,g in clean.groupby(['market','horizon'],dropna=False):
        wr=wmean(g,'ResolvedWin'); summaries.append({'Market':keys[0],'Horizon':keys[1],'Resolved':len(g),'Effective recent N':float(g.RecencyWeight.sum()),'Raw win rate %':100*float(g.ResolvedWin.mean()),'Recency-weighted win rate %':100*wr})
    feature_rows=[]
    feature_map={'daily_setup':'Daily Setup','fresh_signal':'Fresh Signal','hourly_entry':'Hourly / 15m','volume_flow':'Volume / Flow','no_chase':'No-Chase','market_regime_ok':'Market Regime','production_confirmed':'Production Confirmed','optimized_confirmed':'Optimized Confirmed'}
    for (market,horizon),g in clean.groupby(['market','horizon'],dropna=False):
        base=wmean(g,'ResolvedWin')
        for col,label in feature_map.items():
            if col not in g:continue
            gg=g[pd.to_numeric(g[col],errors='coerce')==1]
            if len(gg)<3:continue
            hr=wmean(gg,'ResolvedWin'); feature_rows.append({'Market':market,'Horizon':horizon,'Feature':label,'Resolved signals':len(gg),'Effective recent N':float(gg.RecencyWeight.sum()),'Weighted win rate %':100*hr if np.isfinite(hr) else np.nan,'Weighted baseline %':100*base if np.isfinite(base) else np.nan,'Recent Lift x':hr/base if np.isfinite(hr) and np.isfinite(base) and base>0 else np.nan,'Evidence':('OK' if float(gg.RecencyWeight.sum())>=12 else ('BUILDING EVIDENCE' if float(gg.RecencyWeight.sum())>=8 else ('PROVISIONAL EVIDENCE' if float(gg.RecencyWeight.sum())>=6 else 'LOW SAMPLE')))})
        # V6.3.9.4 research layers: learn from forward outcomes before ever
        # allowing these scores to affect Production ranking or entry gates.
        research_masks=[]
        if 'money_flow_score' in g:research_masks.append(('Money Flow ≥65 (research)',pd.to_numeric(g['money_flow_score'],errors='coerce').ge(65)))
        if 'market_cycle_stage' in g:
            cyc=g['market_cycle_stage'].fillna('').astype(str)
            research_masks.extend([('Cycle EARLY BREAKOUT (research)',cyc.eq('EARLY BREAKOUT')),('Cycle ACCUMULATION/EXPANSION (research)',cyc.isin(['ACCUMULATION','EXPANSION']))])
        if 'catalyst_score' in g:research_masks.append(('Catalyst ≥60 (Top-N research)',pd.to_numeric(g['catalyst_score'],errors='coerce').ge(60)))
        for label,mask in research_masks:
            gg=g[mask.fillna(False)]
            if len(gg)<3:continue
            hr=wmean(gg,'ResolvedWin'); feature_rows.append({'Market':market,'Horizon':horizon,'Feature':label,'Resolved signals':len(gg),'Effective recent N':float(gg.RecencyWeight.sum()),'Weighted win rate %':100*hr if np.isfinite(hr) else np.nan,'Weighted baseline %':100*base if np.isfinite(base) else np.nan,'Recent Lift x':hr/base if np.isfinite(hr) and np.isfinite(base) and base>0 else np.nan,'Evidence':('OK' if float(gg.RecencyWeight.sum())>=12 else ('BUILDING EVIDENCE' if float(gg.RecencyWeight.sum())>=8 else ('PROVISIONAL EVIDENCE' if float(gg.RecencyWeight.sum())>=6 else 'LOW SAMPLE')))})
    return pd.DataFrame(summaries),pd.DataFrame(feature_rows).sort_values(['Recent Lift x','Effective recent N'],ascending=[False,False]) if feature_rows else pd.DataFrame()


def _feedback_primary_rows_v629(merged):
    """One primary outcome row per snapshot, avoiding 1D/2D/3D/5D double-counting.

    If a scan used 7D/10D, Feedback currently evaluates up to 5D, so the nearest
    supported horizon (5D) is used and exposed in the table.
    """
    if merged is None or not isinstance(merged,pd.DataFrame) or merged.empty:return pd.DataFrame()
    x=merged.copy();allowed=(1,2,3,5)
    cfg=pd.to_numeric(x.get('horizon_days',5),errors='coerce').fillna(5)
    x['Primary Feedback Horizon']=cfg.map(lambda v:min(allowed,key=lambda h:abs(float(v)-h)))
    hh=pd.to_numeric(x.get('horizon'),errors='coerce')
    x=x[hh==pd.to_numeric(x['Primary Feedback Horizon'],errors='coerce')].copy()
    return _feedback_independent_rows_v63934(x,require_valid_plan=False)


def _feedback_horizon_progress_v63926(sn, oc):
    """Early progress by horizon with raw snapshots separated from independent events."""
    cols=['Horizon','Raw Evaluated','Independent Events','Trade Eligible Events','Resolved','Wins','Losses','Open / None','Ambiguous','Clean Trade Win Rate %']
    if sn is None or oc is None or not isinstance(sn,pd.DataFrame) or not isinstance(oc,pd.DataFrame) or sn.empty or oc.empty:
        return pd.DataFrame([{'Horizon':f'{h}D','Raw Evaluated':0,'Independent Events':0,'Trade Eligible Events':0,'Resolved':0,'Wins':0,'Losses':0,'Open / None':0,'Ambiguous':0,'Clean Trade Win Rate %':np.nan} for h in (1,2,3,5)],columns=cols)
    try:
        raw=oc.merge(sn,left_on='snapshot_id',right_on='id',how='left')
        raw['Clean Outcome']=raw.get('first_event','').astype(str).map(lambda v:'WIN' if v.startswith('TARGET1 FIRST') else ('LOSS' if v.startswith('INVALIDATION FIRST') else ('AMBIGUOUS' if v.startswith('AMBIGUOUS') else 'OPEN/NONE')))
        hh=pd.to_numeric(raw.get('horizon'),errors='coerce');rows=[]
        for h in (1,2,3,5):
            rg=raw[hh.eq(float(h))].copy();g=_feedback_independent_rows_v63934(rg,False);tg=_feedback_independent_rows_v63934(rg,True)
            wins=int(tg['Clean Outcome'].eq('WIN').sum()) if not tg.empty else 0;losses=int(tg['Clean Outcome'].eq('LOSS').sum()) if not tg.empty else 0;resolved=wins+losses
            opened=int(tg['Clean Outcome'].eq('OPEN/NONE').sum()) if not tg.empty else 0;amb=int(tg['Clean Outcome'].eq('AMBIGUOUS').sum()) if not tg.empty else 0
            rows.append({'Horizon':f'{h}D','Raw Evaluated':len(rg),'Independent Events':len(g),'Trade Eligible Events':len(tg),'Resolved':resolved,'Wins':wins,'Losses':losses,'Open / None':opened,'Ambiguous':amb,'Clean Trade Win Rate %':100*wins/resolved if resolved else np.nan})
        return pd.DataFrame(rows,columns=cols)
    except Exception:
        return pd.DataFrame([{'Horizon':f'{h}D','Raw Evaluated':0,'Independent Events':0,'Trade Eligible Events':0,'Resolved':0,'Wins':0,'Losses':0,'Open / None':0,'Ambiguous':0,'Clean Trade Win Rate %':np.nan} for h in (1,2,3,5)],columns=cols)

def _feedback_horizon_detail_v63928(sn, oc, horizon):
    """Per-event result table: movement truth and trade-plan truth are separate."""
    if sn is None or oc is None or not isinstance(sn,pd.DataFrame) or not isinstance(oc,pd.DataFrame) or sn.empty or oc.empty:return pd.DataFrame()
    try:
        h=int(horizon);raw=oc[pd.to_numeric(oc.get('horizon'),errors='coerce').eq(float(h))].merge(sn,left_on='snapshot_id',right_on='id',how='left')
        x=_feedback_independent_rows_v63934(raw,False)
        if x.empty:return pd.DataFrame()
        x['Trade Result']=x.get('first_event','').astype(str).map(lambda v:'WIN' if v.startswith('TARGET1 FIRST') else ('LOSS' if v.startswith('INVALIDATION FIRST') else ('AMBIGUOUS' if v.startswith('AMBIGUOUS') else 'OPEN / NONE')))
        x['End Return %']=100*pd.to_numeric(x.get('end_return'),errors='coerce');x['MFE %']=100*pd.to_numeric(x.get('max_favorable'),errors='coerce');x['MAE %']=100*pd.to_numeric(x.get('max_adverse'),errors='coerce')
        x['Movement +3%']=np.where(pd.to_numeric(x['MFE %'],errors='coerce').ge(3),'HIT','MISS');x['Movement +5%']=np.where(pd.to_numeric(x['MFE %'],errors='coerce').ge(5),'HIT','MISS')
        x['Plan Geometry']=np.where(pd.to_numeric(x.get('plan_geometry_valid'),errors='coerce').fillna(0).eq(1),'VALID','EXCLUDED')
        x['Snapshot']=pd.to_datetime(x.get('ts_utc'),utc=True,errors='coerce');x['Evaluated At']=pd.to_datetime(x.get('evaluated_at'),utc=True,errors='coerce')
        x['Version']=x.get('app_version',pd.Series('LEGACY',index=x.index)).fillna('LEGACY').astype(str);x['Primary']=pd.to_numeric(x.get('horizon_days'),errors='coerce').map(lambda v:f'{int(v)}D' if pd.notna(v) else '—')
        rename={'event_id':'EventID','ticker':'Ticker','market':'Market','trade_stage':'Trade Stage','entry_action_state':'Entry State','decision_rank_score':'Decision Score','entry_score':'Entry Score','move_consumed_before_trigger':'Consumed %','chase_risk_score':'Chase','inflow_pressure':'Inflow','outflow_pressure':'Outflow','net_flow_balance':'Net Flow','first_event':'First Event','plan_geometry_reason':'Plan Geometry Reason'}
        x=x.rename(columns=rename)
        cols=['EventID','Snapshot','Evaluated At','Version','Ticker','Market','Primary','Trade Stage','Entry State','Decision Score','Entry Score','Consumed %','Chase','Inflow','Outflow','Net Flow','Plan Geometry','Plan Geometry Reason','End Return %','MFE %','MAE %','Movement +3%','Movement +5%','Trade Result','First Event']
        out=x[[c for c in cols if c in x.columns]].copy()
        for c in ['Decision Score','Entry Score','Consumed %','Chase','Inflow','Outflow','Net Flow','End Return %','MFE %','MAE %']:
            if c in out:out[c]=pd.to_numeric(out[c],errors='coerce').round(2)
        return out.sort_values('Evaluated At',ascending=False,na_position='last').reset_index(drop=True) if 'Evaluated At' in out else out.reset_index(drop=True)
    except Exception:return pd.DataFrame()

def _feedback_improvement_tables_v63924(sn, oc, current_version=None):
    """Forward-only model-improvement audit for the simple Feedback dashboard.

    Historical Replay is intentionally excluded. Success is the same clean live
    definition used elsewhere: Target1 before Invalidation at the scan's primary
    feedback horizon. Version comparison is secondary; the shadow Production vs
    Optimized comparison is useful because both models are observed in the same
    market period.
    """
    current_version=str(current_version or APP_VERSION)
    empty={'primary':pd.DataFrame(),'clean':pd.DataFrame(),'version':pd.DataFrame(),'market':pd.DataFrame(),'shadow':pd.DataFrame(),
           'current_n':0,'current_wins':0,'current_rate':np.nan,'baseline_n':0,'baseline_rate':np.nan,'delta_pp':np.nan,
           'status':'COLLECTING FORWARD OUTCOMES','status_detail':'No resolved primary outcomes for the current version yet.'}
    if sn is None or oc is None or not isinstance(sn,pd.DataFrame) or not isinstance(oc,pd.DataFrame) or sn.empty or oc.empty:
        return empty
    try:
        merged=oc.merge(sn,left_on='snapshot_id',right_on='id',how='left')
        merged['Clean Outcome']=merged.get('first_event','').astype(str).map(lambda x:'WIN' if x.startswith('TARGET1 FIRST') else ('LOSS' if x.startswith('INVALIDATION FIRST') else ('AMBIGUOUS' if x.startswith('AMBIGUOUS') else 'OPEN/NONE')))
        primary=_feedback_primary_rows_v629(merged)
        if primary.empty:return {**empty,'primary':primary}
        if 'app_version' not in primary:primary['app_version']='LEGACY ≤6.3.9.23'
        primary['app_version']=primary['app_version'].fillna('LEGACY ≤6.3.9.23').astype(str)
        clean=primary[primary['Clean Outcome'].isin(['WIN','LOSS']) & pd.to_numeric(primary.get('plan_geometry_valid',1),errors='coerce').fillna(0).eq(1)].copy()
        if clean.empty:return {**empty,'primary':primary,'clean':clean}
        clean['Clean Win']=clean['Clean Outcome'].eq('WIN').astype(float)
        clean['MFE %']=100*pd.to_numeric(clean.get('max_favorable'),errors='coerce')
        clean['MAE %']=100*pd.to_numeric(clean.get('max_adverse'),errors='coerce')
        clean['End Return %']=100*pd.to_numeric(clean.get('end_return'),errors='coerce')
        versions=[]
        for ver,g in clean.groupby('app_version',dropna=False):
            n=len(g);wins=int(g['Clean Win'].sum());rate=float(g['Clean Win'].mean()) if n else np.nan
            versions.append({'Version':ver,'Resolved':n,'Wins':wins,'Losses':n-wins,'Clean Win Rate %':100*rate if np.isfinite(rate) else np.nan,
                             'Avg MFE %':float(g['MFE %'].mean()),'Avg MAE %':float(g['MAE %'].mean()),'Avg End Return %':float(g['End Return %'].mean()),
                             'Markets':int(g.get('market',pd.Series(dtype=str)).nunique()) if 'market' in g else np.nan})
        version_df=pd.DataFrame(versions).sort_values('Version',ascending=False) if versions else pd.DataFrame()
        market_rows=[]
        for (ver,mkt,hor),g in clean.groupby(['app_version','market','horizon'],dropna=False):
            n=len(g);rate=float(g['Clean Win'].mean()) if n else np.nan
            market_rows.append({'Version':ver,'Market':mkt,'Horizon':hor,'Resolved':n,'Clean Win Rate %':100*rate if np.isfinite(rate) else np.nan,
                                'Avg MFE %':float(g['MFE %'].mean()),'Avg MAE %':float(g['MAE %'].mean())})
        market_df=pd.DataFrame(market_rows)
        cur=clean[clean['app_version'].eq(current_version)].copy();prior=clean[~clean['app_version'].eq(current_version)].copy()
        # Match the prior baseline to market+horizon strata actually present in the current version.
        matched_prior=[]
        if not cur.empty and not prior.empty:
            for (mkt,hor),cg in cur.groupby(['market','horizon'],dropna=False):
                pg=prior[(prior['market']==mkt)&(pd.to_numeric(prior['horizon'],errors='coerce')==float(hor))]
                if not pg.empty:matched_prior.append(pg)
        base=pd.concat(matched_prior,ignore_index=True).drop_duplicates(subset=['snapshot_id','horizon']) if matched_prior else prior
        cn=len(cur);cw=int(cur['Clean Win'].sum()) if cn else 0;cr=float(cur['Clean Win'].mean()) if cn else np.nan
        bn=len(base);br=float(base['Clean Win'].mean()) if bn else np.nan;delta=(cr-br)*100 if np.isfinite(cr) and np.isfinite(br) else np.nan
        status='COLLECTING FORWARD OUTCOMES';detail=f'Current version has {cn} clean resolved primary outcome(s).'
        if cn>=12 and bn>=20 and np.isfinite(cr) and np.isfinite(br):
            se=math.sqrt(max(1e-12,cr*(1-cr)/cn + br*(1-br)/bn))
            z=(cr-br)/se if se>0 else 0.0
            if cn<30:
                status='EARLY EVIDENCE';detail=f'{delta:+.1f} pp vs matched prior baseline • more resolved outcomes needed before a strong conclusion.'
            elif z>=1.96:
                status='IMPROVEMENT EVIDENCE';detail=f'{delta:+.1f} pp vs matched prior baseline • 95% normal-approximation separation.'
            elif z<=-1.96:
                status='DECLINE EVIDENCE';detail=f'{delta:+.1f} pp vs matched prior baseline • 95% normal-approximation separation.'
            else:
                status='NOT YET CLEAR';detail=f'{delta:+.1f} pp vs matched prior baseline • difference is not yet statistically clear.'
        # Same-period shadow A/B from the stored disagreement labels.
        shadow_rows=[]
        if 'model_disagreement' in clean:
            dg=clean['model_disagreement'].fillna('').astype(str)
            masks={
                'PRODUCTION':dg.isin(['BOTH CONFIRMED','PRODUCTION ONLY']),
                'OPTIMIZED SHADOW':dg.isin(['BOTH CONFIRMED','OPTIMIZED ONLY']),
                'BOTH CONFIRMED':dg.eq('BOTH CONFIRMED'),
                'PRODUCTION ONLY':dg.eq('PRODUCTION ONLY'),
                'OPTIMIZED ONLY':dg.eq('OPTIMIZED ONLY'),
            }
            for label,mask in masks.items():
                g=clean[mask]
                if g.empty:continue
                shadow_rows.append({'Lane':label,'Resolved':len(g),'Wins':int(g['Clean Win'].sum()),'Clean Win Rate %':100*float(g['Clean Win'].mean()),
                                    'Avg MFE %':float(g['MFE %'].mean()),'Avg MAE %':float(g['MAE %'].mean())})
        return {'primary':primary,'clean':clean,'version':version_df,'market':market_df,'shadow':pd.DataFrame(shadow_rows),
                'current_n':cn,'current_wins':cw,'current_rate':100*cr if np.isfinite(cr) else np.nan,
                'baseline_n':bn,'baseline_rate':100*br if np.isfinite(br) else np.nan,'delta_pp':delta,'status':status,'status_detail':detail}
    except Exception as e:
        return {**empty,'status':'AUDIT ERROR','status_detail':f'{type(e).__name__}: {str(e)[:180]}'}


def _feedback_early_entry_validation_v639(primary):
    """Forward validation for EARLY/MID/LATE ARMED vs confirmed entry.

    Uses only already-matured primary live-feedback outcomes. No replay rows and
    no automatic production promotion are allowed here.
    """
    if primary is None or not isinstance(primary,pd.DataFrame) or primary.empty:return pd.DataFrame()
    p=primary.copy()
    if 'Clean Outcome' not in p:
        p['Clean Outcome']=p.get('first_event','').astype(str).map(lambda x:'WIN' if x.startswith('TARGET1 FIRST') else ('LOSS' if x.startswith('INVALIDATION FIRST') else ('AMBIGUOUS' if x.startswith('AMBIGUOUS') else 'OPEN/NONE')))
    p=p[p['Clean Outcome'].isin(['WIN','LOSS']) & pd.to_numeric(p.get('plan_geometry_valid',1),errors='coerce').fillna(0).eq(1)].copy()
    if p.empty:return pd.DataFrame()
    p['Clean Win']=p['Clean Outcome'].eq('WIN').astype(float)
    armed=p.get('armed_timing_class',pd.Series('N/A',index=p.index)).fillna('N/A').astype(str)
    stage=p.get('trade_stage',pd.Series('WAIT',index=p.index)).fillna('WAIT').astype(str)
    p['Early Entry Class']=np.where(armed.isin(['EARLY ARMED','MID ARMED','LATE ARMED','CONFIRMED ENTRY']),armed,np.where(stage.eq('CONFIRMED ENTRY'),'CONFIRMED ENTRY','OTHER'))
    p=p[p['Early Entry Class'].isin(['EARLY ARMED','MID ARMED','LATE ARMED','CONFIRMED ENTRY'])].copy()
    if p.empty:return pd.DataFrame()
    rows=[]
    _bp=primary[primary.get('Clean Outcome',pd.Series('',index=primary.index)).isin(['WIN','LOSS']) & pd.to_numeric(primary.get('plan_geometry_valid',1),errors='coerce').fillna(0).eq(1)].copy()
    for (market,horizon),allg in _bp.groupby(['market','horizon'],dropna=False):
        b=float(allg['Clean Outcome'].eq('WIN').mean()) if len(allg) else np.nan
        sub=p[(p['market']==market)&(pd.to_numeric(p['horizon'],errors='coerce')==float(horizon))]
        for cls,g in sub.groupby('Early Entry Class',dropna=False):
            n=len(g);wins=int(g['Clean Win'].sum());rate=float(g['Clean Win'].mean()) if n else np.nan
            mfe=100*pd.to_numeric(g.get('max_favorable'),errors='coerce');mae=100*pd.to_numeric(g.get('max_adverse'),errors='coerce');endr=100*pd.to_numeric(g.get('end_return'),errors='coerce')
            lift=rate/b if np.isfinite(rate) and np.isfinite(b) and b>0 else np.nan
            if n<5:status='LOW SAMPLE'
            elif n>=12 and np.isfinite(lift) and lift>=1.10:status='POSITIVE'
            elif n>=12 and np.isfinite(lift) and lift<=.90:status='NEGATIVE'
            else:status='MIXED'
            rows.append({'Market':market,'Horizon':horizon,'Early Entry Class':cls,'Resolved':n,'Wins':wins,'Losses':n-wins,'Clean Win Rate %':100*rate if np.isfinite(rate) else np.nan,'Market/Horizon Baseline %':100*b if np.isfinite(b) else np.nan,'Lift x':lift,'Hit +3% MFE %':100*float((mfe>=3).mean()) if n else np.nan,'Hit +5% MFE %':100*float((mfe>=5).mean()) if n else np.nan,'Avg End Return %':float(endr.mean()) if n else np.nan,'Avg MFE %':float(mfe.mean()) if n else np.nan,'Avg MAE %':float(mae.mean()) if n else np.nan,'Evidence':status})
    out=pd.DataFrame(rows)
    if out.empty:return out
    order={'EARLY ARMED':0,'MID ARMED':1,'LATE ARMED':2,'CONFIRMED ENTRY':3}
    out['_o']=out['Early Entry Class'].map(order).fillna(9)
    return out.sort_values(['Market','Horizon','_o']).drop(columns=['_o']).reset_index(drop=True)


def _feedback_scorecards_v629(sn, primary):
    """Simple Hebrew-friendly success, indicator and stock scorecards.

    Success = Target1 was reached before invalidation among clean resolved primary
    outcomes. OPEN / ambiguous rows are shown separately and never hidden inside
    the percentage.
    """
    p=primary.copy() if isinstance(primary,pd.DataFrame) else pd.DataFrame()
    if not p.empty and 'Clean Outcome' not in p:
        p['Clean Outcome']=p.get('first_event','').astype(str).map(lambda x:'WIN' if x.startswith('TARGET1 FIRST') else ('LOSS' if x.startswith('INVALIDATION FIRST') else ('AMBIGUOUS' if x.startswith('AMBIGUOUS') else 'OPEN/NONE')))
    _plan_ok=pd.to_numeric(p.get('plan_geometry_valid',pd.Series(1,index=p.index)),errors='coerce').fillna(0).eq(1) if not p.empty else pd.Series(dtype=bool)
    clean=p[p.get('Clean Outcome',pd.Series('',index=p.index)).isin(['WIN','LOSS']) & _plan_ok].copy() if not p.empty else pd.DataFrame()
    if not clean.empty:clean['Clean Win']=clean['Clean Outcome'].eq('WIN').astype(float)
    wins=int((clean.get('Clean Outcome',pd.Series(dtype=str))=='WIN').sum()) if not clean.empty else 0
    losses=int((clean.get('Clean Outcome',pd.Series(dtype=str))=='LOSS').sum()) if not clean.empty else 0
    trade_p=p[_plan_ok].copy() if not p.empty else pd.DataFrame()
    resolved=wins+losses; evaluated=len(trade_p)
    amb=int((trade_p.get('Clean Outcome',pd.Series(dtype=str))=='AMBIGUOUS').sum()) if not trade_p.empty else 0
    opened=int((trade_p.get('Clean Outcome',pd.Series(dtype=str))=='OPEN/NONE').sum()) if not trade_p.empty else 0
    success=100*wins/resolved if resolved else np.nan
    coverage=100*resolved/evaluated if evaluated else np.nan
    headline=pd.DataFrame([{
        'אחוז הצלחה':success,'הצלחות':wins,'כשלונות':losses,'מקרים נקיים שהוכרעו':resolved,
        'נבדקו בפועל':evaluated,'אירועים עצמאיים':len(p),'תוכניות לא חוקיות שהוצאו':int((~_plan_ok).sum()) if len(_plan_ok) else 0,'לא הוכרעו / פתוחים':opened,'דו-משמעיים':amb,'כיסוי הכרעה %':coverage,
        'הגדרה':'Independent Event ORIGIN + valid plan: Target 1 before Invalidation at primary horizon'
    }])

    base=float(clean['Clean Win'].mean()) if not clean.empty else np.nan
    indicator_rows=[]
    feature_map={
        'daily_setup':'Daily Setup','fresh_signal':'Fresh Signal / Transition','hourly_entry':'Hourly / 15m confirmation',
        'volume_flow':'Volume / Flow','no_chase':'No-Chase','extension_guard':'Extension Guard OK',
        'market_regime_ok':'Market Regime OK'
    }
    def add_indicator(label,mask,kind='Live gate'):
        if clean.empty:return
        try:g=clean.loc[mask.reindex(clean.index,fill_value=False)]
        except Exception:return
        n=len(g)
        if n==0:return
        hr=float(g['Clean Win'].mean());lift=hr/base if np.isfinite(base) and base>0 else np.nan
        delta=100*(hr-base) if np.isfinite(base) else np.nan
        if n<5:status='LOW SAMPLE'
        elif np.isfinite(lift) and lift>=1.05 and delta>=2:status='WORKED'
        elif np.isfinite(lift) and lift<=.95 and delta<=-2:status='FAILED'
        else:status='MIXED'
        indicator_rows.append({'סוג':kind,'אינדיקטור / תנאי':label,'מקרים שהוכרעו':n,'אחוז הצלחה %':100*hr,'בסיס כללי %':100*base if np.isfinite(base) else np.nan,'Lift x':lift,'פער מול בסיס (נק׳ %)':delta,'סטטוס':status})
    for col,label in feature_map.items():
        if col in clean:add_indicator(label,pd.to_numeric(clean[col],errors='coerce').fillna(0).eq(1))
    if 'pre_move_stage' in clean:
        add_indicator('Pre-Move Candidate',clean['pre_move_stage'].astype(str).isin(['PRE-MOVE CANDIDATE','STRONG PRE-MOVE CANDIDATE']),'Research radar')
    fams=['MOMENTUM','VOLUME','FLOW','RELATIVE_STRENGTH','TREND','STRUCTURE','TRANSITION_BREADTH']
    if 'pre_move_families' in clean:
        fs=clean['pre_move_families'].fillna('').astype(str)
        for fam in fams:add_indicator('Pre-Move family: '+fam,fs.str.contains(fam,regex=False),'Pre-Move family')
    # Exact strongest Pre-Move combinations are also tracked; require >=3 clean outcomes.
    if 'pre_move_features' in clean:
        rows=[]
        for idx,r in clean[['pre_move_features','Clean Win']].iterrows():
            for sig in [x.strip() for x in str(r.get('pre_move_features','')).split(' | ') if x.strip() and x.strip().lower()!='nan']:
                rows.append((sig,float(r['Clean Win'])))
        if rows:
            tmp=pd.DataFrame(rows,columns=['Signal','Win'])
            for sig,g in tmp.groupby('Signal'):
                if len(g)<3:continue
                hr=float(g.Win.mean());lift=hr/base if np.isfinite(base) and base>0 else np.nan;delta=100*(hr-base) if np.isfinite(base) else np.nan
                status='LOW SAMPLE' if len(g)<5 else ('WORKED' if np.isfinite(lift) and lift>=1.05 and delta>=2 else ('FAILED' if np.isfinite(lift) and lift<=.95 and delta<=-2 else 'MIXED'))
                indicator_rows.append({'סוג':'Pre-Move signal','אינדיקטור / תנאי':sig,'מקרים שהוכרעו':len(g),'אחוז הצלחה %':100*hr,'בסיס כללי %':100*base if np.isfinite(base) else np.nan,'Lift x':lift,'פער מול בסיס (נק׳ %)':delta,'סטטוס':status})
    indicators=pd.DataFrame(indicator_rows)
    if not indicators.empty:
        order={'WORKED':0,'MIXED':1,'FAILED':2,'LOW SAMPLE':3}
        indicators['_o']=indicators['סטטוס'].map(order).fillna(9);indicators=indicators.sort_values(['_o','Lift x','מקרים שהוכרעו'],ascending=[True,False,False]).drop(columns=['_o']).reset_index(drop=True)

    # All tickers that have ever been snapshotted are shown, even before outcomes mature.
    stock_base=pd.DataFrame({'Ticker':sorted(set(sn.get('ticker',pd.Series(dtype=str)).dropna().astype(str)))}) if isinstance(sn,pd.DataFrame) and not sn.empty else pd.DataFrame(columns=['Ticker'])
    if not p.empty:
        stock_stats=[]
        for ticker,g in p.groupby('ticker',dropna=False):
            gc=g[g['Clean Outcome'].isin(['WIN','LOSS']) & pd.to_numeric(g.get('plan_geometry_valid',1),errors='coerce').fillna(0).eq(1)].copy();w=int((gc['Clean Outcome']=='WIN').sum());l=int((gc['Clean Outcome']=='LOSS').sum());n=w+l
            hr=100*w/n if n else np.nan
            avg=float(pd.to_numeric(g.get('End Return %'),errors='coerce').mean()) if 'End Return %' in g else np.nan
            mfe=float(pd.to_numeric(g.get('MFE %'),errors='coerce').mean()) if 'MFE %' in g else np.nan
            mae=float(pd.to_numeric(g.get('MAE %'),errors='coerce').mean()) if 'MAE %' in g else np.nan
            if n<3:status='LOW SAMPLE / WAITING'
            elif hr>=55:status='SUCCESS'
            elif hr<=45:status='FAILURE'
            else:status='MIXED'
            stock_stats.append({'Ticker':str(ticker),'Resolved':n,'Wins':w,'Losses':l,'Success Rate %':hr,'Avg End Return %':avg,'Avg MFE %':mfe,'Avg MAE %':mae,'Model Status':status})
        ss=pd.DataFrame(stock_stats);stocks=stock_base.merge(ss,on='Ticker',how='left')
    else:stocks=stock_base.copy()
    if not stocks.empty:
        # V6.3.9.1 hotfix: Feedback must remain renderable before the first
        # forward outcomes mature.  Some restored/imported snapshot sets have
        # no resolved stock statistics yet, so create every sort/display column
        # explicitly instead of assuming the merge produced it.
        stocks['Snapshots']=stocks['Ticker'].map(sn.groupby('ticker').size() if isinstance(sn,pd.DataFrame) and not sn.empty else {}).fillna(0).astype(int)
        for c in ['Resolved','Wins','Losses']:
            if c not in stocks.columns:stocks[c]=0
            stocks[c]=pd.to_numeric(stocks[c],errors='coerce').fillna(0).astype(int)
        for c in ['Success Rate %','Avg End Return %','Avg MFE %','Avg MAE %']:
            if c not in stocks.columns:stocks[c]=np.nan
            stocks[c]=pd.to_numeric(stocks[c],errors='coerce')
        if 'Model Status' not in stocks.columns:
            stocks['Model Status']='WAITING FOR OUTCOME'
        else:
            stocks['Model Status']=stocks['Model Status'].astype(object).where(stocks['Model Status'].notna(),'WAITING FOR OUTCOME')
        stocks['Model Status']=stocks['Model Status'].astype(str).replace({'nan':'WAITING FOR OUTCOME','None':'WAITING FOR OUTCOME','':'WAITING FOR OUTCOME'})
        order={'SUCCESS':0,'MIXED':1,'FAILURE':2,'LOW SAMPLE / WAITING':3,'WAITING FOR OUTCOME':4}
        status_series=stocks['Model Status'] if 'Model Status' in stocks.columns else pd.Series('WAITING FOR OUTCOME',index=stocks.index,dtype=object)
        stocks['_o']=status_series.map(order).fillna(9)
        stocks=stocks.sort_values(['_o','Success Rate %','Resolved'],ascending=[True,False,False],na_position='last').drop(columns=['_o']).reset_index(drop=True)
    return headline,indicators,stocks


def _feedback_color_table_v629(df,status_col):
    if df is None or not isinstance(df,pd.DataFrame) or df.empty:return df
    def row_style(row):
        v=str(row.get(status_col,''))
        if v in ('WORKED','SUCCESS','OOS STRONG','OOS POSITIVE','FINAL STRONG','FINAL POSITIVE','PROMISING','OOS PROMISING','STRONG EXPLOSIVE CANDIDATE','EXPLOSIVE CANDIDATE','STRONG RE-ACCELERATION CANDIDATE','RE-ACCELERATION CANDIDATE','CONTINUATION BASE CANDIDATE','STRONG PRE-EXPLOSIVE CANDIDATE','PRE-EXPLOSIVE CANDIDATE'):style='background-color: rgba(53,212,154,.20); color: #b7f7dd; font-weight: 700'
        elif v in ('FAILED','FAILURE','WEAK','LATE / ALREADY MOVED','BLOCKED — DATA QUALITY'):style='background-color: rgba(255,100,124,.20); color: #ffc0ca; font-weight: 700'
        elif v in ('MIXED','BUILDING'):style='background-color: rgba(246,200,95,.16); color: #ffe7a8'
        else:style='color: #9aa7bb'
        return [style]*len(row)
    try:return df.style.apply(row_style,axis=1)
    except Exception:return df


def _feedback_workbook_v629(sheets,meta=None):
    """Feedback Excel with the same green/red scorecard semantics as the UI."""
    raw=workbook_bytes(sheets,meta)
    try:
        from openpyxl import load_workbook
        from openpyxl.styles import PatternFill, Font
        bio=BytesIO(raw);wb=load_workbook(bio)
        colors={'WORKED':'C6EFCE','SUCCESS':'C6EFCE','OOS STRONG':'C6EFCE','OOS POSITIVE':'C6EFCE','FINAL STRONG':'C6EFCE','FINAL POSITIVE':'C6EFCE','PROMISING':'C6EFCE','OOS PROMISING':'C6EFCE','FAILED':'FFC7CE','FAILURE':'FFC7CE','WEAK':'FFC7CE','MIXED':'FFEB9C','OOS MIXED':'FFEB9C','FINAL MIXED':'FFEB9C','STRONG EXPLOSIVE CANDIDATE':'C6EFCE','EXPLOSIVE CANDIDATE':'C6EFCE','STRONG RE-ACCELERATION CANDIDATE':'C6EFCE','RE-ACCELERATION CANDIDATE':'C6EFCE','CONTINUATION BASE CANDIDATE':'C6EFCE','STRONG PRE-EXPLOSIVE CANDIDATE':'C6EFCE','PRE-EXPLOSIVE CANDIDATE':'C6EFCE','BUILDING':'FFEB9C','LATE / ALREADY MOVED':'FFC7CE','BLOCKED — DATA QUALITY':'FFC7CE'}
        for sheet,status_header in [('Indicator Summary','סטטוס'),('Stock Summary','Model Status'),('Replay Indicators','Status'),('Replay Stocks','Model Status'),('Combination Discovery','OOS Status'),('Market Consensus Combos','Status'),('Indicator Lift','Status'),('Combination Discovery','Status'),('Current Explosive Radar','Status'),('Current Explosive Radar V3','Status'),('Top OOS Signatures','Status'),('Combination Signatures','Status'),('Indicator Signatures','Status')]:
            if sheet not in wb.sheetnames:continue
            ws=wb[sheet];headers={c.value:i for i,c in enumerate(ws[1],1)};ci=headers.get(status_header)
            if not ci:continue
            for r in range(2,ws.max_row+1):
                status=str(ws.cell(r,ci).value or '')
                color=colors.get(status)
                if not color:continue
                fill=PatternFill('solid',fgColor=color)
                for c in range(1,ws.max_column+1):ws.cell(r,c).fill=fill
        out=BytesIO();wb.save(out);return out.getvalue()
    except Exception:return raw

def _optimizer_workbook_bytes_v63943(sheets, meta=None):
    """Low-memory write-only XLSX writer used by the heavy OOS Optimizer.

    openpyxl's normal worksheet mode stores every cell object in RAM.  The
    Optimizer can export tens of thousands of research rows, so V6.3.9.43 uses
    write_only mode and streams rows directly.  This changes export mechanics
    only; optimizer calculations and model thresholds are untouched.
    """
    from openpyxl import Workbook
    from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
    wb=Workbook(write_only=True)
    # A write-only workbook starts without a usable default sheet.
    used=set()
    def safe(v):
        try:
            if isinstance(v,np.generic):v=v.item()
        except Exception:pass
        try:
            if pd.isna(v):return None
        except Exception:pass
        if isinstance(v,(float,np.floating)) and not np.isfinite(float(v)):return None
        if isinstance(v,pd.Timestamp):
            try:
                if v.tz is not None:v=v.tz_localize(None)
            except Exception:pass
            return v.to_pydatetime()
        if isinstance(v,datetime):
            try:
                if v.tzinfo is not None:v=v.replace(tzinfo=None)
            except Exception:pass
            return v
        if isinstance(v,(dict,list,tuple,set)):
            try:v=json.dumps(v,default=str,ensure_ascii=False)
            except Exception:v=str(v)
        if isinstance(v,str):return ILLEGAL_CHARACTERS_RE.sub('',v)
        return v
    for raw_name,obj in (sheets or {}).items():
        if obj is None:continue
        name=''.join(ch for ch in str(raw_name) if ch not in '[]:*?/\\')[:31] or 'Sheet'
        base=name;n=2
        while name in used:
            suffix=f'_{n}';name=(base[:31-len(suffix)]+suffix);n+=1
        used.add(name);ws=wb.create_sheet(title=name)
        if isinstance(obj,pd.DataFrame):
            ws.append([safe(c) for c in obj.columns])
            for row in obj.itertuples(index=False,name=None):ws.append([safe(v) for v in row])
        elif isinstance(obj,dict):
            keys=list(obj.keys());ws.append([safe(k) for k in keys]);ws.append([safe(obj.get(k)) for k in keys])
        elif isinstance(obj,list):
            if not obj:continue
            if isinstance(obj[0],dict):
                keys=list(obj[0].keys());ws.append([safe(k) for k in keys])
                for rec in obj:ws.append([safe(rec.get(k)) for k in keys])
            else:
                for row in obj:
                    if isinstance(row,(list,tuple)):ws.append([safe(v) for v in row])
                    else:ws.append([safe(row)])
        else:
            try:
                df=pd.DataFrame(obj);ws.append([safe(c) for c in df.columns])
                for row in df.itertuples(index=False,name=None):ws.append([safe(v) for v in row])
            except Exception:continue
    ws=wb.create_sheet(title='About')
    about={'Version':APP_VERSION,'Generated':datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
    if meta:about.update(meta)
    ws.append(['Field','Value'])
    for k,v in about.items():ws.append([safe(k),safe(v)])
    bio=BytesIO();wb.save(bio);return bio.getvalue()


def workbook_bytes(sheets, meta=None):
    """Build a safe multi-sheet Excel workbook for any tab."""
    bio=BytesIO()
    with pd.ExcelWriter(bio,engine="openpyxl") as writer:
        used=set()
        for raw_name,obj in (sheets or {}).items():
            if obj is None:
                continue
            if isinstance(obj,dict):
                obj=pd.DataFrame([obj])
            elif isinstance(obj,list):
                obj=pd.DataFrame(obj)
            elif not isinstance(obj,pd.DataFrame):
                try: obj=pd.DataFrame(obj)
                except Exception: continue
            name=''.join(ch for ch in str(raw_name) if ch not in '[]:*?/\\')[:31] or 'Sheet'
            base=name; n=2
            while name in used:
                suffix=f'_{n}'; name=(base[:31-len(suffix)]+suffix); n+=1
            used.add(name)
            _excel_safe_df(obj).to_excel(writer,index=False,sheet_name=name)
        about={"Version":APP_VERSION,"Generated":datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
        if meta: about.update(meta)
        pd.DataFrame({"Field":list(about.keys()),"Value":list(about.values())}).to_excel(writer,index=False,sheet_name="About")
    return bio.getvalue()

def tab_download(key,label,filename_prefix):
    if key in st.session_state:
        st.download_button(label,data=st.session_state[key],file_name=f"{filename_prefix}_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",use_container_width=True,key=f"dl_{key}")

def _fmt_seconds(seconds):
    try:
        seconds=max(0,int(float(seconds)))
    except Exception:
        return "—"
    m,s=divmod(seconds,60); h,m=divmod(m,60)
    return f"{h:d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"

class _ScannerCancelled(Exception):
    """Internal cooperative-cancel signal for the background scanner."""


@st.cache_resource(show_spinner=False)
def _scanner_runtime_v599():
    # V6.3.9.60 restores the last successful scan from the portable Feedback DB,
    # so refresh/restart never empties the Scanner before a new successful run.
    try:_persisted=_scan_snapshot_load_v63960()
    except Exception:_persisted=None
    return {
        'lock':threading.RLock(),
        'executor':None,
        'active':None,
        'last_completed':_persisted,
    }

def _scanner_progress_percent(stage,i,total):
    if stage=='discovery':
        return int(np.clip(12*max(0,i-1)/max(1,total),0,12))
    if stage=='stage1':
        return int(np.clip(12+46*max(0,i-1)/max(1,total),12,58))
    if stage=='stage2':
        return int(np.clip(58+32*max(0,i-1)/max(1,total),58,90))
    if stage=='valuation':
        return int(np.clip(90+6*max(0,i)/max(1,total),90,96))
    if stage=='catalyst':
        return int(np.clip(96+3*max(0,i)/max(1,total),96,99))
    return 99

def _scanner_worker_v599(runtime,job_id,config):
    started=time_module.time()
    skipped=[]
    def progress(stage,i,total,ticker_name):
        now=time_module.time()
        with runtime['lock']:
            job=runtime.get('active')
            if not job or job.get('id')!=job_id:
                raise _ScannerCancelled()
            if job.get('cancel_requested') or job.get('status') in ('stopping','stopped'):
                raise _ScannerCancelled()
            if job.get('stage')!=stage:
                job['stage_started_at']=now
                job['stage_samples']=[]
            else:
                prev=job.get('last_callback_at')
                if prev and job.get('last_stage')==stage:
                    dt=max(0.01,now-prev)
                    samples=list(job.get('stage_samples',[])); samples.append(dt); job['stage_samples']=samples[-8:]
            job['stage']=stage; job['last_stage']=stage; job['last_callback_at']=now
            job['index']=int(i); job['total']=int(total); job['ticker']=ticker_name
            job['market']=_market_for_ticker_v612(ticker_name)
            job['progress']=_scanner_progress_percent(stage,i,total)
            job['elapsed']=now-started
            samples=job.get('stage_samples',[])
            avg=float(np.mean(samples)) if samples else (job['elapsed']/max(1,i))
            if stage=='discovery':
                rem=None
            elif stage=='stage1':
                rem=max(0,total-i+1)*avg
                # Deep analysis is heavier than daily prefilter. This is intentionally approximate.
                rem += min(int(config.get('prefilter_top',120)),max(1,total))*max(avg*2.3,2.0)
            else:
                rem=max(0,total-i+1)*avg
            job['eta']=rem
    try:
        run_config=dict(config);scan_tickers=list(config.get('tickers') or []);discovery_meta={};discovery_frame=pd.DataFrame()
        # V6.3.9.58 core reserve applies to MARKET DISCOVERY and curated SMART scans.
        _core_reserved_base=_core_reserved_deep_tickers_v63958(config.get('markets') or [])
        if scan_tickers:_core_reserved_base={t for t in _core_reserved_base if t in set(map(str,scan_tickers))}
        _priority_base=set(str(x).upper().strip() for x in (config.get('priority_deep_tickers') or []) if str(x).strip())
        run_config['mandatory_deep_tickers']=sorted(_core_reserved_base|_priority_base)
        if bool(config.get('market_discovery',False)):
            scan_tickers,discovery_meta,discovery_frame=_market_discovery_candidates_v63948(config.get('markets') or ['US','HONG KONG','TEL AVIV'],progress_callback=progress)
            if not scan_tickers:
                raise RuntimeError('Market Discovery returned no candidates and no fallback universe')
            # V6.3.9.56: preserve active Original Signals across scans/versions.
            # They are added to Stage-0 and receive reserved Deep slots until the
            # move reaches T1, invalidates, or ages out.
            _active_signal_tickers=set(_active_signal_deep_tickers_v63956())
            _requested_markets=set(str(x).upper() for x in (config.get('markets') or []))
            def _active_market_allowed(_t):
                if not _requested_markets:return True
                _m=str(_market_for_ticker_v612(_t) or '').upper()
                if _m in ('NASDAQ','NYSE'): _m='US'
                return _m in _requested_markets
            _active_signal_tickers={t for t in _active_signal_tickers if _active_market_allowed(t)}
            scan_tickers=list(dict.fromkeys(list(scan_tickers)+sorted(_active_signal_tickers)))
            run_config['tickers']=scan_tickers
            # Reserved Deep slots are intentionally narrow. Any active/parallel
            # temporary-counter bridge (1196↔2922 today) is guaranteed analysis;
            # users can add explicit priority_deep_tickers without reserving all
            # curated names and destroying discovery capacity.
            _core_reserved=_core_reserved_deep_tickers_v63958(config.get('markets') or [])
            _reserved=set(str(x).upper().strip() for x in (run_config.get('mandatory_deep_tickers') or []) if str(x).strip())
            _reserved.update(_core_reserved)
            _reserved.update(_active_signal_tickers)
            for _t in scan_tickers:
                try:
                    if temporary_counter_info(_t):_reserved.add(str(_t).upper().strip())
                except Exception:pass
            run_config['mandatory_deep_tickers']=sorted(_reserved)
            discovery_meta['reserved_deep_anchors']=sorted(_reserved);discovery_meta['reserved_active_original_signals']=sorted(_active_signal_tickers);discovery_meta['reserved_core_deep']=sorted(_core_reserved)
            # SMART = deep analysis of a balanced subset; FULL = every Stage-0 candidate.
            if str(config.get('scan_depth','SMART')).upper()=='FULL':
                run_config['prefilter_top']=len(scan_tickers)
            else:
                nmk=max(1,len(config.get('markets') or []));run_config['prefilter_top']=min(len(scan_tickers),int(config.get('discovery_deep_cap',55+35*nmk)))
            with runtime['lock']:
                job=runtime.get('active')
                if job and job.get('id')==job_id:
                    job['discovery_meta']=discovery_meta;job['index']=0;job['total']=len(scan_tickers);job['ticker']='Stage-0 complete';job['market']='MARKET DISCOVERY'
        res=_v544_scan_universe_dynamic(
            scan_tickers,run_config['history'],True,'1mo',run_config['horizon'],run_config['target'],0,
            run_config['threshold'],run_config['prefilter_top'],progress_callback=progress,optimizer_model=run_config.get('optimizer_model'),mandatory_deep_tickers=run_config.get('mandatory_deep_tickers'))
        # A stop can be requested while the final network/data call is still in flight.
        # Re-check before publishing/storing a completed result.
        with runtime['lock']:
            job=runtime.get('active')
            if (not job or job.get('id')!=job_id or job.get('cancel_requested') or job.get('status') in ('stopping','stopped')):
                raise _ScannerCancelled()
        meta=dict(getattr(res,'attrs',{}).get('scan_meta',{})) if isinstance(res,pd.DataFrame) else {}
        meta.update({'forecast_horizon_days':int(run_config.get('horizon',5)),'target_pct':100.0*float(run_config.get('target',0.06)),'scan_mode':str(run_config.get('scan_mode','Production 151')),'universe_mode':str(run_config.get('universe_mode','ALL')),'universe_size':len(scan_tickers),'market_discovery':bool(run_config.get('market_discovery',False))})
        if discovery_meta:meta['discovery']=discovery_meta
        # V6.3.9.49 Discovery Audit: preserve the full funnel so a later review can
        # answer why any broad-market ticker did or did not reach deep analysis.
        if bool(run_config.get('market_discovery',False)) and isinstance(discovery_frame,pd.DataFrame) and not discovery_frame.empty:
            try:
                _aud=discovery_frame.copy()
                _active_reserved=set(map(str,(meta.get('discovery') or {}).get('reserved_active_original_signals') or []))
                _existing_aud=set(_aud['Ticker'].astype(str)) if 'Ticker' in _aud else set()
                _missing_active=sorted(_active_reserved-_existing_aud)
                if _missing_active:
                    _extra=pd.DataFrame({'Ticker':_missing_active,'Market':[_market_for_ticker_v612(t) for t in _missing_active],'DiscoverySource':['ACTIVE SIGNAL MEMORY']*len(_missing_active),'DiscoveryScore':[np.nan]*len(_missing_active),'Turnover':[np.nan]*len(_missing_active),'DiscoveryMandatoryAnchor':[False]*len(_missing_active),'DiscoveryEarlyVolumePriority':[False]*len(_missing_active)})
                    _aud=pd.concat([_aud,_extra],ignore_index=True,sort=False)
                _stage0=set(map(str,scan_tickers))
                _daily=set(map(str,meta.get('daily_success_tickers') or []))
                _deep_sel=set(map(str,meta.get('deep_selected_tickers') or []))
                _deep_ok=set(map(str,meta.get('deep_success_tickers') or ([] if not isinstance(res,pd.DataFrame) else res.get('Ticker',pd.Series(dtype=str)).astype(str).tolist())))
                _skipped=meta.get('skipped') or []
                _skip_map={(str(x.get('Ticker')),str(x.get('Stage'))):str(x.get('Reason','')) for x in _skipped if isinstance(x,dict)}
                _aud['Stage0Selected']=_aud['Ticker'].astype(str).isin(_stage0)
                _aud['DailyOK']=_aud['Ticker'].astype(str).isin(_daily)
                _aud['DeepSelected']=_aud['Ticker'].astype(str).isin(_deep_sel)
                _aud['DeepOK']=_aud['Ticker'].astype(str).isin(_deep_ok)
                _reserved_deep=set(map(str,run_config.get('mandatory_deep_tickers') or []))
                _aud['ReservedDeepAnchor']=_aud['Ticker'].astype(str).isin(_reserved_deep)
                _core_reserved_aud=set(map(str,(meta.get('discovery') or {}).get('reserved_core_deep') or []))
                _aud['ReservedCoreDeep']=_aud['Ticker'].astype(str).isin(_core_reserved_aud)
                _aud['ReservedActiveOriginalSignal']=_aud['Ticker'].astype(str).isin(_active_reserved)
                if 'InstrumentType' not in _aud.columns:_aud['InstrumentType']='COMMON STOCK / CURATED'
                def _drop_reason(r):
                    t=str(r.get('Ticker'))
                    if not bool(r.get('Stage0Selected')):return 'BROAD ONLY — below Stage-0 shortlist'
                    if not bool(r.get('DailyOK')):return 'DAILY REJECT — '+(_skip_map.get((t,'Daily')) or 'daily data/eligibility failed')
                    if not bool(r.get('DeepSelected')):
                        if bool(r.get('ReservedDeepAnchor')):return 'ERROR — RESERVED DEEP ANCHOR WAS NOT SELECTED'
                        return 'SMART DEPTH CUTOFF — market-balanced deep quota'
                    if not bool(r.get('DeepOK')):return 'DEEP REJECT — '+(_skip_map.get((t,'Deep')) or _skip_map.get((t,'Stage2')) or 'deep analysis failed')
                    return 'DEEP ANALYZED'
                _aud['DropReason']=_aud.apply(_drop_reason,axis=1)
                _aud['ProviderBridge']=np.where(_aud['Ticker'].astype(str).eq('1196.HK'),'1196.HK ↔ 2922.HK','')
                _aud=_aud.sort_values(['Market','Stage0Selected','DeepOK','DiscoveryScore'],ascending=[True,False,False,False],na_position='last').reset_index(drop=True)
                meta['discovery_audit']=_aud
                meta['discovery_funnel']={'broad_scanned':int(len(_aud)),'stage0_selected':int(_aud['Stage0Selected'].sum()),'daily_ok':int(_aud['DailyOK'].sum()),'deep_selected':int(_aud['DeepSelected'].sum()),'deep_ok':int(_aud['DeepOK'].sum())}
            except Exception as _e:
                meta['discovery_audit_error']=f'{type(_e).__name__}: {_e}'
        if isinstance(res,pd.DataFrame) and not res.empty:
            res=add_market_and_opportunity(res);res=_wire_timing_completeness_v63937(res);res=_apply_optimized_model_v612(res,config.get('optimizer_model'))
            res=_decision_intelligence_enrich_v6394(res)
            try: res=_attach_regular_signature_overlay_v638(_attach_pre_move_overlay_v628(res))
            except Exception: pass
            if bool(config.get('valuation_overlay',True)):
                def valuation_progress(i,total,ticker_name):
                    now=time_module.time()
                    with runtime['lock']:
                        job=runtime.get('active')
                        if not job or job.get('id')!=job_id or job.get('cancel_requested') or job.get('status') in ('stopping','stopped'):raise _ScannerCancelled()
                        job['stage']='valuation';job['last_stage']='valuation';job['index']=int(i);job['total']=int(total);job['ticker']=ticker_name;job['market']=_market_for_ticker_v612(ticker_name);job['progress']=_scanner_progress_percent('valuation',i,total);job['elapsed']=now-started
                try:res=_valuation_enrich_scan_v6393(res,progress_callback=valuation_progress)
                except _ScannerCancelled:raise
                except Exception:pass
            if bool(config.get('catalyst_overlay',True)):
                def catalyst_progress(i,total,ticker_name):
                    now=time_module.time()
                    with runtime['lock']:
                        job=runtime.get('active')
                        if not job or job.get('id')!=job_id or job.get('cancel_requested') or job.get('status') in ('stopping','stopped'):raise _ScannerCancelled()
                        job['stage']='catalyst';job['last_stage']='catalyst';job['index']=int(i);job['total']=int(total);job['ticker']=ticker_name;job['market']=_market_for_ticker_v612(ticker_name);job['progress']=_scanner_progress_percent('catalyst',i,total);job['elapsed']=now-started
                try:res=_catalyst_enrich_top_v6394(res,top_n=int(config.get('catalyst_top_n',_CATALYST_TOP_N_V6394)),progress_callback=catalyst_progress)
                except _ScannerCancelled:raise
                except Exception:pass
            # V6.3.9.8: final Top-5 / Scanner order uses the transparent
            # de-duplicated Decision Ranking V3.13. Optimized mode contributes only
            # a bounded OOS modifier; overlapping decision families are not reweighted twice.
            res=_apply_decision_ranking_v63919(res,run_config.get('scan_mode','Production 151'))
            res=_decision_board_enrich_v63948(res)
            res=_signal_memory_enrich_v63955(res)
        finished=time_module.time()
        try:
            _feedback_store_scan_v600(job_id,res,run_config)
            threading.Thread(target=_feedback_evaluate_due_v600,kwargs={'max_snapshots':80},daemon=True).start()
        except Exception:
            pass
        snapshot={
            'id':job_id,'status':'completed','result':res,'meta':meta,'started_at':started,'finished_at':finished,
            'duration':finished-started,'completed_label':datetime.fromtimestamp(finished,ZoneInfo('Asia/Jerusalem')).strftime('%Y-%m-%d %H:%M:%S'),
            'requested':int(discovery_meta.get('broad_scanned',len(scan_tickers))) if discovery_meta else len(scan_tickers),'config':run_config,
        }
        # Persist only after the scan completed successfully. Stopped/failed runs
        # never overwrite the last known-good snapshot.
        snapshot['persistent_cache_saved']=True
        try:
            if not _scan_snapshot_persist_v63960(snapshot):snapshot['persistent_cache_saved']=False
        except Exception:snapshot['persistent_cache_saved']=False
        with runtime['lock']:
            runtime['last_completed']=snapshot
            if runtime.get('active') and runtime['active'].get('id')==job_id:
                runtime['active'].update({'status':'completed','progress':100,'elapsed':finished-started,'eta':0,'result':res,'meta':meta,'finished_at':finished,'cancel_requested':False})
    except _ScannerCancelled:
        finished=time_module.time()
        with runtime['lock']:
            if runtime.get('active') and runtime['active'].get('id')==job_id:
                runtime['active'].update({'status':'stopped','finished_at':finished,'elapsed':finished-started,'eta':0,'ticker':'—','market':'—','cancel_requested':True})
    except Exception as e:
        finished=time_module.time()
        with runtime['lock']:
            if runtime.get('active') and runtime['active'].get('id')==job_id:
                runtime['active'].update({'status':'failed','error':f'{type(e).__name__}: {e}','finished_at':finished,'elapsed':finished-started,'eta':0,'cancel_requested':False})

def _start_scanner_job_v599(config):
    runtime=_scanner_runtime_v599()
    with runtime['lock']:
        active=runtime.get('active')
        if active and active.get('status')=='running':
            return False,'A scan is already running.'
        if runtime.get('executor') is None:
            runtime['executor']=ThreadPoolExecutor(max_workers=1,thread_name_prefix='stock-hunter-scan')
        job_id=f"scan-{int(time_module.time()*1000)}"
        runtime['active']={
            'id':job_id,'status':'running','stage':'starting','index':0,'total':len(config['tickers']),
            'ticker':'—','market':'—','progress':0,'started_at':time_module.time(),'elapsed':0,'eta':None,
            'stage_started_at':time_module.time(),'stage_samples':[],'last_callback_at':None,'last_stage':None,
            'config':config,'cancel_requested':False,
        }
        runtime['executor'].submit(_scanner_worker_v599,runtime,job_id,config)
    return True,job_id

def _request_scanner_stop_v601():
    runtime=_scanner_runtime_v599()
    with runtime['lock']:
        active=runtime.get('active')
        if not active or active.get('status') not in ('running','stopping'):
            return False,'No scan is currently running.'
        if active.get('status')=='stopping':
            return True,'Stop already requested.'
        active['cancel_requested']=True
        active['status']='stopping'
        active['eta']=0
        return True,'Stop requested. Finishing the current data call safely…'

def _scanner_status_v601():
    runtime=_scanner_runtime_v599()
    with runtime['lock']:
        active=runtime.get('active')
        return str(active.get('status','idle')) if active else 'idle'

def _filter_scanner_results_v599(df,show_mode,market_filter="ALL",timing_filter="ALL",quality_filter="ALL",risk_filter="ALL"):
    if df is None or not isinstance(df,pd.DataFrame) or df.empty:
        return pd.DataFrame()
    show_mode=_decision_stage_internal_v63960(show_mode)
    z=df.copy()
    market_name={'HONG KONG 50':'HONG KONG','HONG KONG 101':'HONG KONG','HONG KONG ALL':'HONG KONG','TEL AVIV 50':'TEL AVIV','TEL AVIV ALL':'TEL AVIV'}.get(market_filter)
    if market_filter=='US 51' and 'Ticker' in z:z=z[z.Ticker.astype(str).isin(set(US_51.split(',')))]
    elif market_filter=='US ALL' and 'Market' in z:z=z[z.Market.astype(str).isin(['NASDAQ','NYSE','US'])]
    elif market_name and 'Market' in z:z=z[z.Market.eq(market_name)]

    # V6.3.9.22: when a market filter is active, E#/Q#/EV# are local to the
    # market currently being viewed. Preserve the original cross-market lane
    # rank for audit/details so a Hong Kong view reads E#1, E#2, E#3... rather
    # than E#1, E#15, E#19.
    _market_scoped = market_filter not in ('ALL 151','ALL','')
    if _market_scoped and not z.empty:
        for _src,_bak in [('QualifiedRank','GlobalQualifiedRank'),('EmergingRank','GlobalEmergingRank'),('EvidenceRank','GlobalEvidenceRank')]:
            if _src in z.columns and _bak not in z.columns:z[_bak]=z[_src]
        if 'ValidatedOpportunityEligible' in z.columns:
            z['QualifiedRank']=np.nan
            _m=z['ValidatedOpportunityEligible'].fillna(False).astype(bool)
            _idx=z[_m].sort_values(['DecisionRankScore','SetupQualityScore','EntryTimingScore'],ascending=[False,False,False]).index.tolist()
            for _pos,_idx0 in enumerate(_idx,1):z.at[_idx0,'QualifiedRank']=_pos
        if 'EmergingSetupEligible' in z.columns:
            z['EmergingRank']=np.nan
            _m=z['EmergingSetupEligible'].fillna(False).astype(bool)
            _idx=z[_m].sort_values(['EmergingSetupScore','EntryTimingScore','SetupQualityScore'],ascending=[False,False,False]).index.tolist()
            for _pos,_idx0 in enumerate(_idx,1):z.at[_idx0,'EmergingRank']=_pos
        if 'EvidenceValidated' in z.columns:
            z['EvidenceRank']=np.nan
            _m=z['EvidenceValidated'].fillna(False).astype(bool)
            _idx=z[_m].sort_values(['DecisionEvidenceScore','EvidenceSampleN','DecisionRankScore'],ascending=[False,False,False]).index.tolist()
            for _pos,_idx0 in enumerate(_idx,1):z.at[_idx0,'EvidenceRank']=_pos
    if show_mode=='BUILDING SETUP':
        _st=z.get('EffectiveDecisionStage',z.get('DecisionBoardStage',pd.Series('',index=z.index))).astype(str).map(_decision_stage_canonical_v63961)
        z=z[_st.eq('BUILDING SETUP')]
    elif show_mode=='ARMED':
        z=z[z.get('EffectiveDecisionStage',z.get('DecisionBoardStage',pd.Series('',index=z.index))).astype(str).map(_decision_stage_canonical_v63961).eq('ARMED')]
    elif show_mode=='ARMED BLOCKED':
        z=z[z.get('EffectiveDecisionStage',z.get('DecisionBoardStage',pd.Series('',index=z.index))).astype(str).map(_decision_stage_canonical_v63961).eq('ARMED BLOCKED')]
    elif show_mode=='ENTRY NOW':
        z=z[z.get('EffectiveDecisionStage',z.get('DecisionBoardStage',pd.Series('',index=z.index))).eq('ENTRY NOW')]
    elif show_mode=='LAST SESSION ENTRY':
        z=z[z.get('EffectiveDecisionStage',z.get('DecisionBoardStage',pd.Series('',index=z.index))).eq('LAST SESSION ENTRY')]
    elif show_mode=='RETEST':
        z=z[z.get('EffectiveDecisionStage',z.get('DecisionBoardStage',pd.Series('',index=z.index))).eq('RETEST')]
    elif show_mode=='TOO LATE':
        z=z[z.get('EffectiveDecisionStage',z.get('DecisionBoardStage',pd.Series('',index=z.index))).eq('TOO LATE')]
    elif show_mode=='STRONG PRE-MOVE CANDIDATE':
        _ps=z.get('PreMovePatternStrength',pd.Series('',index=z.index)).astype(str).str.upper();_legacy=z.get('PreMoveStage',pd.Series('',index=z.index)).astype(str)
        z=z[_ps.eq('HIGH') | _legacy.eq('STRONG PRE-MOVE CANDIDATE')]
    elif show_mode=='PRE-MOVE CANDIDATE':
        _ps=z.get('PreMovePatternStrength',pd.Series('',index=z.index)).astype(str).str.upper();_legacy=z.get('PreMoveStage',pd.Series('',index=z.index)).astype(str)
        z=z[_ps.isin(['HIGH','WATCH']) | _legacy.isin(['STRONG PRE-MOVE CANDIDATE','PRE-MOVE CANDIDATE'])]
    elif show_mode=='REGULAR HIGH CONFIDENCE':
        z=z[z.get('RegularFunnelStage',pd.Series('',index=z.index)).eq('RESEARCH HIGH CONFIDENCE')]
    elif show_mode=='REGULAR RADAR':
        z=z[z.get('RegularRadarScore',pd.Series(np.nan,index=z.index)).notna()]
    elif show_mode=='UNDERVALUED (RESEARCH)':
        vs=pd.to_numeric(z.get('ValuationScore',pd.Series(np.nan,index=z.index)),errors='coerce')
        z=z[vs.ge(65) & z.get('ValuationLabel',pd.Series('',index=z.index)).astype(str).isin(['UNDERVALUED','DEEPLY UNDERVALUED'])]
    elif show_mode=='CONFIRMED ENTRY':
        z=z[z.get('EntryTriggerState',pd.Series('',index=z.index)).eq('CONFIRMED ENTRY')]
    elif show_mode=='OPTIMIZED CONFIRMED':
        z=z[z.get('OptimizedStage',pd.Series('',index=z.index)).eq('OPTIMIZED CONFIRMED')]
    elif show_mode=='OPTIMIZED ARMED':
        z=z[z.get('OptimizedStage',pd.Series('',index=z.index)).eq('OPTIMIZED ARMED')]
    elif show_mode=='ARMED':
        z=z[z.get('EntryTriggerState',pd.Series('',index=z.index)).eq('ARMED')]
    elif show_mode=='EXTENDED / RETEST':
        z=z[z.get('EntryTriggerState',pd.Series('',index=z.index)).eq('EXTENDED — DO NOT CHASE')]
    elif show_mode in ('VALIDATED OPPORTUNITIES','VALIDATED PICKS'):
        _qual=z.get('ValidatedOpportunityEligible',z.get('DecisionRankEligible',pd.Series(False,index=z.index))).fillna(False).astype(bool)
        z=z[_qual]
    elif show_mode=='EVIDENCE VALIDATED':
        _ev=z.get('EvidenceValidated',pd.Series(False,index=z.index)).fillna(False).astype(bool)
        z=z[_ev]
    elif show_mode=='EMERGING SETUPS':
        _em=z.get('EmergingSetupEligible',pd.Series(False,index=z.index)).fillna(False).astype(bool)
        z=z[_em]
    elif show_mode=='TOP OPPORTUNITIES':
        # Legacy strict view retained for compatibility; main UI now calls out
        # VALIDATED OPPORTUNITIES and EMERGING SETUPS separately.
        _rank=pd.to_numeric(z.get('DecisionRankScore',pd.Series(np.nan,index=z.index)),errors='coerce')
        _qual=z.get('ValidatedOpportunityEligible',z.get('DecisionRankEligible',pd.Series(False,index=z.index))).fillna(False).astype(bool)
        z=z[_rank.ge(68) & _qual]
    elif show_mode=='RESEARCH ALL':
        _pm=z.get('PreMoveStage',pd.Series('',index=z.index)).astype(str).isin(['STRONG PRE-MOVE CANDIDATE','PRE-MOVE CANDIDATE'])
        _rr=pd.to_numeric(z.get('RegularRadarScore',pd.Series(np.nan,index=z.index)),errors='coerce').notna()
        _vs=pd.to_numeric(z.get('ValuationScore',pd.Series(np.nan,index=z.index)),errors='coerce').notna()
        z=z[_pm|_rr|_vs]
    elif show_mode=='ACTIONABLE NOW':
        if 'ActionableNow' in z: z=z[z.ActionableNow.astype(bool)]
    elif show_mode=='WATCHLIST':
        z=z[z.get('EntryTriggerState',z.OpportunityStage).isin(['WATCH','ARMED','EXTENDED — DO NOT CHASE'])]
    # Secondary decision-board filters.
    if timing_filter!='ALL' and not z.empty:
        tc=z.get('TimingContext',pd.Series('NO DATA',index=z.index)).astype(str)
        if timing_filter=='NOT EXTENDED':z=z[~tc.eq('EXTENDED')]
        else:z=z[tc.eq(timing_filter)]
    if quality_filter!='ALL' and not z.empty:
        n=pd.to_numeric(z.get('EvidenceSampleN',z.get('BacktestN',pd.Series(0,index=z.index))),errors='coerce').fillna(0)
        if quality_filter=='EVIDENCE 6+':z=z[n>=6]
        elif quality_filter=='EVIDENCE 12+':z=z[n>=12]
    if risk_filter!='ALL' and not z.empty:
        if risk_filter=='NO CHASE':
            z=z[z.get('ChaseRiskLabel',pd.Series('',index=z.index)).astype(str).eq('LOW') & z.get('ExtensionGuardCheck',pd.Series(True,index=z.index)).fillna(True).astype(bool)]
        elif risk_filter=='R:R ≥ 1.5':
            rr=pd.to_numeric(z.get('LiveRRDisplayT1',pd.Series(np.nan,index=z.index)),errors='coerce');z=z[rr>=1.5]

    if show_mode=='ALL':
        _stage_order={'ENTRY NOW':0,'ARMED':1,'BUILDING SETUP':2,'ARMED BLOCKED':3,'LAST SESSION ENTRY':4,'RETEST':5,'WAIT':6,'TOO LATE':7}
        z['_BoardOrder']=z.get('EffectiveDecisionStage',z.get('DecisionBoardStage',pd.Series('WAIT',index=z.index))).astype(str).map(_stage_order).fillna(5)
        # V6.3.9.53 rank integrity: render the exact Action Queue order that the card labels show.
        # OverallStrengthRank is only a tie-breaker; a queue #1 may never render behind queue #2.
        if 'ActionQueueRank' in z.columns:
            _cols=[c for c in ['_BoardOrder','ActionQueueRank','OverallStrengthRank','DecisionRankScore'] if c in z.columns]
            _asc=[True,True,True,False][:len(_cols)]
        else:
            _cols=[c for c in ['_BoardOrder','DecisionRankScore','EntryTimingScore'] if c in z.columns];_asc=[True]+[False]*(len(_cols)-1)
        z=z.sort_values(_cols,ascending=_asc,na_position='last',kind='stable') if _cols else z
        if '_BoardOrder' in z:z=z.drop(columns=['_BoardOrder'])
    elif show_mode in ('BUILDING SETUP','ARMED','ARMED BLOCKED','ENTRY NOW','LAST SESSION ENTRY','RETEST','TOO LATE'):
        if 'ActionQueueRank' in z.columns:
            _cols=[c for c in ['ActionQueueRank','OverallStrengthRank','DecisionRankScore'] if c in z.columns]
            _asc=[True,True,False][:len(_cols)]
            z=z.sort_values(_cols,ascending=_asc,na_position='last',kind='stable') if _cols else z
        elif show_mode=='ARMED':
            _ord={'EARLY':0,'MID':1,'EXTENDED':2,'NO DATA':3};z['_TimingOrder']=z.get('TimingContext',pd.Series('NO DATA',index=z.index)).astype(str).map(_ord).fillna(3)
            _cols=[c for c in ['_TimingOrder','DecisionRankScore','EntryTimingScore'] if c in z.columns];_asc=[True]+[False]*(len(_cols)-1);z=z.sort_values(_cols,ascending=_asc,na_position='last',kind='stable') if _cols else z
            if '_TimingOrder' in z:z=z.drop(columns=['_TimingOrder'])
        elif show_mode=='RETEST':
            _cols=[c for c in ['PullbackNeededPct','DecisionRankScore'] if c in z.columns];z=z.sort_values(_cols,ascending=[True,False][:len(_cols)],na_position='last',kind='stable') if _cols else z
        else:
            _cols=[c for c in ['DecisionRankScore','EntryTimingScore','SetupQualityScore'] if c in z.columns];z=z.sort_values(_cols,ascending=[False]*len(_cols),na_position='last',kind='stable') if _cols else z
    elif show_mode in ('VALIDATED OPPORTUNITIES','VALIDATED PICKS') and 'QualifiedRank' in z.columns:
        z=z.sort_values(['QualifiedRank','DecisionRankScore'],ascending=[True,False],na_position='last')
    elif show_mode=='EMERGING SETUPS' and 'EmergingRank' in z.columns:
        z=z.sort_values(['EmergingRank','EmergingSetupScore'],ascending=[True,False],na_position='last')
    elif show_mode=='EVIDENCE VALIDATED' and 'EvidenceRank' in z.columns:
        z=z.sort_values(['EvidenceRank','DecisionEvidenceScore'],ascending=[True,False],na_position='last')
    elif show_mode in ('STRONG PRE-MOVE CANDIDATE','PRE-MOVE CANDIDATE') and 'PreMoveRadarRank' in z.columns:
        z=z.sort_values(['PreMoveRadarRank','PreBreakoutAccumulationScore','PreMoveFamilyCount'],ascending=[True,False,False],na_position='last',kind='stable')
    elif 'TradePriorityRank' in z.columns:
        z=z.sort_values(['TradePriorityRank','DecisionRankScore'],ascending=[True,False])
    z=z.reset_index(drop=True)
    if 'Rank' in z.columns: z=z.drop(columns=['Rank'])
    z.insert(0,'Rank',range(1,len(z)+1))
    return z

def _session_badges_html_v599(r):
    phase=str(r.get('MarketPhase','UNKNOWN')); stage=str(r.get('OpportunityStage','WAIT')); live=str(r.get('LiveStage',stage))
    if phase=='PRE-MARKET':
        conf=str(r.get('PMConfirmation','N/A')); ch=r.get('PMChangePct',np.nan)
        status='DATA UNAVAILABLE' if conf=='N/A' else conf
        c='good' if conf=='CONFIRMED' else ('bad' if 'WEAKENED' in conf else 'warn')
        mv=f" ({float(ch):+.2f}%)" if pd.notna(ch) else ''
        return f"<span class='{c}'>PRE-MARKET: {status}{mv}</span><br><span class='warn'>Previous session: {stage}</span>"
    if phase=='AFTER-MARKET':
        conf=str(r.get('AHConfirmation','N/A')); ch=r.get('AHChangePct',np.nan)
        status='DATA UNAVAILABLE' if conf=='N/A' else conf
        c='good' if conf=='CONFIRMED' else ('bad' if 'WEAKENED' in conf else 'warn')
        mv=f" ({float(ch):+.2f}%)" if pd.notna(ch) else ''
        return f"<span class='{c}'>AFTER-MARKET: {status}{mv}</span><br><span class='warn'>Regular session: {stage}</span>"
    if phase=='OPEN':
        c='good' if live=='CONFIRMED ENTRY — LIVE' else ('bad' if 'WEAKENED' in live else 'warn')
        return f"<span class='{c}'>OPEN: {live}</span>"
    if phase=='PRE-OPEN': return f"<span class='warn'>PRE-OPEN • Previous session: {stage}</span>"
    if phase=='CLOSED': return f"<span class='warn'>CLOSED • Previous session: {stage}</span>"
    return f"<span class='warn'>{phase}: {stage}</span>"

def _live_levels_html_v599(r):
    if str(r.get('MarketPhase',''))!='OPEN' or str(r.get('LiveStage',''))!='CONFIRMED ENTRY — LIVE':
        return ''
    vals={k:pd.to_numeric(pd.Series([r.get(k,np.nan)]),errors='coerce').iloc[0] for k in ['EntryLow','EntryHigh','Invalidation','Target1','Target2']}
    if not all(np.isfinite(vals[k]) for k in vals): return ''
    entry=(vals['EntryLow']+vals['EntryHigh'])/2.0; risk=entry-vals['Invalidation']
    if risk<=0:return ''
    rr1=max(0,(vals['Target1']-entry)/risk); rr2=max(0,(vals['Target2']-entry)/risk)
    return (f"<div style='margin-top:12px;padding:12px 14px;border:1px solid #284a3d;border-radius:14px;background:rgba(39,190,120,.06)'>"
            f"<b class='good'>🟢 LIVE TRADE LEVELS</b><br>"
            f"Entry Zone <b>{vals['EntryLow']:.3f}–{vals['EntryHigh']:.3f}</b> • "
            f"<span class='bad'>Stop / Invalidation <b>{vals['Invalidation']:.3f}</b></span><br>"
            f"Target 1 <b>{vals['Target1']:.3f}</b> • Target 2 <b>{vals['Target2']:.3f}</b> • "
            f"R/R <b>1:{rr1:.1f} / 1:{rr2:.1f}</b> (T1/T2)"
            f"</div>")

def _scanner_stage_guide_v599():
    with st.expander("ℹ️ Decision Board — stage guide", expanded=False):
        st.markdown("**PRE-MOVE RADAR** → **BUILDING SETUP** → **ARMED** → **ENTRY NOW** → **RETEST / TOO LATE**  *(ARMED BLOCKED is an incomplete-data side lane, not a higher-priority action state)*")
        st.caption("PRE-MOVE RADAR is a separate discovery layer: abnormal volume / absorption / accumulation can appear before a normal trade setup exists. BUILDING SETUP means the trade setup itself has started to form, but it is not mature enough for qualified ARMED or ENTRY NOW yet. ARMED BLOCKED means the setup looks mature but timing/data/plan integrity is incomplete.")
        st.caption("ARMED = setup is mature and close to an entry window • ENTRY NOW = setup + price + R:R are actionable now • RETEST = a valid setup needs a better price • TOO LATE = invalidated / chase state.")
        st.caption("Recent rise describes the broader 3D/5D/10D move and is context only. Trigger Timing says whether the causal trigger arrived early/mid/late. Progress Trigger → T1 says how much of the planned post-trigger path is already used.")

def _render_scanner_results_v599(show_mode,market_filter="ALL",timing_filter="ALL",quality_filter="ALL",risk_filter="ALL"):
    # V6.3.9.54 hotfix: helpers must exist before the completion banner is rendered.
    # In V6.3.9.53 these helpers were defined later inside the card loop, which made
    # Python treat them as locals across the whole function and caused an
    # UnboundLocalError when the SCAN COMPLETED banner called _e6395 first.
    def _e6395(v):
        return html_lib.escape(str(v if v is not None else '—'))
    def _num6395(v):
        return pd.to_numeric(pd.Series([v]),errors='coerce').iloc[0]
    def _fmt6395(v,dec=0,suffix=''):
        x=_num6395(v)
        return f"{x:.{dec}f}{suffix}" if np.isfinite(x) else '—'

    runtime=_scanner_runtime_v599()
    with runtime['lock']:
        active=dict(runtime['active']) if runtime.get('active') else None
        last=runtime.get('last_completed')
    if active and active.get('status') in ('running','stopping'):
        pct=int(active.get('progress',0))
        elapsed=active.get('elapsed',time_module.time()-active.get('started_at',time_module.time()))
        eta=active.get('eta')
        if active.get('status')=='stopping':
            st.progress(max(0,min(100,pct)),text=f"Stopping safely… • {pct}% • waiting for current data call to finish")
        else:
            st.progress(max(0,min(100,pct)),text=f"Scanning • {pct}% • {active.get('stage','').upper()} • {active.get('market','—')} • {active.get('ticker','—')}")
        c1,c2,c3=st.columns(3)
        c1.metric("Current",f"{active.get('index',0)}/{active.get('total',0)}")
        c2.metric("Elapsed",_fmt_seconds(elapsed))
        c3.metric("Estimated remaining","Stopping…" if active.get('status')=='stopping' else (f"~{_fmt_seconds(eta)}" if eta is not None else "Calculating…"))
        st.caption("The scan runs on the Streamlit server. Stop is cooperative: it cancels before the next ticker after the current provider/data call returns.")
        st.caption("The last successfully completed results remain visible below until this new scan finishes successfully.")
    if active and active.get('status')=='stopped':
        st.info(f"Scan stopped by user after {_fmt_seconds(active.get('elapsed',0))}.")
    if active and active.get('status')=='failed':
        st.error("Scan failed: "+str(active.get('error','Unknown error')))
    if not last:
        try:
            last=_scan_snapshot_load_v63960()
            if last:
                with runtime['lock']:runtime['last_completed']=last
        except Exception:pass
    if not last:
        st.info("No completed scan is stored yet. Run Scanner once; future refreshes/restarts will keep the last successful result.")
        return
    full=_attach_regular_signature_overlay_v638(_attach_pre_move_overlay_v628(last.get('result')))
    # V6.3.9.22 migration: an older cached last_completed scan may survive a code
    # redeploy and therefore have no Ranking V3.13 decision-lane columns. Backfill and re-sort the
    # FULL snapshot before filtering so cached V2 ranks cannot leak into the new UI.
    # 
    _rank_version_ok=(
        isinstance(full,pd.DataFrame) and not full.empty and
        'DecisionRankScore' in full.columns and
        pd.to_numeric(full['DecisionRankScore'],errors='coerce').notna().all() and
        'DecisionRankVersion' in full.columns and
        full['DecisionRankVersion'].astype(str).eq('V3.13').all()
    )
    if not _rank_version_ok:
        full=_ensure_decision_ranking_v63919(full,str((last.get('config') or {}).get('scan_mode','Production 151')))
        # Persist the migrated snapshot in the server runtime so the 1-second UI
        # fragment does not recompute it every refresh.
        try:
            with runtime['lock']:
                if runtime.get('last_completed') is last:
                    runtime['last_completed']['result']=full
        except Exception:pass
    full=_decision_board_enrich_v63948(full)
    res=_filter_scanner_results_v599(full,show_mode,market_filter,timing_filter,quality_filter,risk_filter)
    try:
        _nr=full.get('NeedsOpenRevalidation',pd.Series(False,index=full.index)).fillna(False).astype(bool)
        _us=full.get('Market',pd.Series('',index=full.index)).astype(str).isin(['NASDAQ','NYSE','US'])
        if bool((_nr&_us).any()):
            st.warning('US OPEN REVALIDATION REQUIRED • this completed snapshot was created before the current US regular session. Re-run Scanner to refresh 15m/1H, RVOL, Flow and Entry decisions. Pre-open scores are not treated as live ENTRY NOW.')
    except Exception:pass
    meta=last.get('meta') or {}
    skipped=meta.get('skipped') or []
    requested=int(last.get('requested',meta.get('requested',0)) or 0)
    daily_ok=int(meta.get('daily_success',0) or 0)
    deep_ok=int(meta.get('deep_success',len(full) if isinstance(full,pd.DataFrame) else 0) or 0)
    _disc=meta.get('discovery') or {}
    # V6.3.9.53 — compact completion banner in exact Israel time. The long raw
    # discovery/source dictionaries are hidden under Scan diagnostics.
    try:
        _finished_epoch=float(last.get('finished_at',np.nan))
        _completed_il=datetime.fromtimestamp(_finished_epoch,ZoneInfo('Asia/Jerusalem')) if np.isfinite(_finished_epoch) else datetime.now(ZoneInfo('Asia/Jerusalem'))
        _completed_il_txt=_completed_il.strftime('%d/%m/%Y • %H:%M:%S')
    except Exception:
        _completed_il_txt=str(last.get('completed_label','—'))
    _restored=bool(last.get('restored_from_persistent_cache',False))
    _persisted_ok=bool(_restored or last.get('persistent_cache_saved',False))
    try:_age_sec=max(0.0,time_module.time()-float(last.get('finished_at',time_module.time())))
    except Exception:_age_sec=0.0
    _age_txt=_fmt_seconds(_age_sec)
    _saved_note=' • SAVED' if _persisted_ok else ' • SESSION CACHE'
    st.markdown(f"<div class='scan-complete-banner'>● LAST COMPLETED SCAN <span class='scan-time'>{_e6395(_completed_il_txt)}</span><span class='scan-tz'>ISRAEL{_saved_note}</span></div>",unsafe_allow_html=True)
    if _restored or _age_sec>3600:
        st.caption(f"Showing the last successful saved scan • age {_age_txt}. A stopped or failed scan never replaces it.")
    _broad=int(_disc.get('broad_scanned',requested) or requested) if _disc else requested
    _stage0=int(_disc.get('candidates',0) or 0) if _disc else requested
    st.markdown(
        "<div class='scan-summary-grid'>"+
        f"<div class='scan-summary-card'><span class='n'>{_broad:,}</span><span class='l'>SCANNED</span></div>"+
        f"<div class='scan-summary-card'><span class='n'>{_stage0:,}</span><span class='l'>CANDIDATES</span></div>"+
        f"<div class='scan-summary-card'><span class='n'>{daily_ok:,}</span><span class='l'>DAILY OK</span></div>"+
        f"<div class='scan-summary-card'><span class='n'>{deep_ok:,}</span><span class='l'>DEEP</span></div>"+
        f"<div class='scan-summary-card'><span class='n'>{len(skipped):,}</span><span class='l'>ERRORS / SKIPPED</span></div>"+
        "</div>",unsafe_allow_html=True)
    if isinstance(full,pd.DataFrame) and not full.empty:
        _bs=full.get('EffectiveDecisionStage',full.get('DecisionBoardStage',pd.Series('WAIT',index=full.index))).astype(str)
        _bs=_bs.map(_decision_stage_canonical_v63961)
        _bc={k:int((_bs==k).sum()) for k in ['BUILDING SETUP','ARMED','ARMED BLOCKED','ENTRY NOW','LAST SESSION ENTRY','RETEST','TOO LATE']}
        st.markdown(
            "<div class='top5-detail-line'><b>Decision Board:</b> "+
            f"BUILDING SETUP <span class='warn'>{_bc['BUILDING SETUP']}</span> • ARMED <span class='good'>{_bc['ARMED']}</span> • ARMED BLOCKED <span class='bad'>{_bc['ARMED BLOCKED']}</span> • ENTRY NOW <span class='good'>{_bc['ENTRY NOW']}</span> • LAST SESSION <span class='warn'>{_bc['LAST SESSION ENTRY']}</span> • RETEST <span class='warn'>{_bc['RETEST']}</span> • TOO LATE <span class='bad'>{_bc['TOO LATE']}</span></div>",unsafe_allow_html=True)
        _pms=full.get('PreMovePatternStrength',pd.Series('NONE',index=full.index)).fillna('NONE').astype(str).str.upper()
        _pma=full.get('PreMoveActionableNow',pd.Series(False,index=full.index)).fillna(False).astype(bool)
        st.markdown(f"<div class='top5-detail-line'><b>Pre-Move Radar:</b> HIGH <span class='good'>{int((_pms=='HIGH').sum())}</span> • WATCH <span class='warn'>{int((_pms=='WATCH').sum())}</span> • ACTIONABLE EARLY <span class='good'>{int(_pma.sum())}</span></div>",unsafe_allow_html=True)
        _mem_stage=full.get('EffectiveDecisionStage',full.get('DecisionBoardStage',pd.Series('WAIT',index=full.index))).astype(str)
        _mem_stage=_mem_stage.map(_decision_stage_canonical_v63961)
        _mem_relevant=_mem_stage.isin(['BUILDING SETUP','ARMED','ARMED BLOCKED','ENTRY NOW','LAST SESSION ENTRY','RETEST','TOO LATE']) | _pms.isin(['HIGH','WATCH'])
        _mem_available=full.get('OriginalMemoryAvailable',pd.Series(False,index=full.index)).fillna(False).astype(bool)
        _mem_den=int(_mem_relevant.sum());_mem_num=int((_mem_relevant&_mem_available).sum())
        _mem_missing=max(0,_mem_den-_mem_num)
        st.markdown(f"<div class='top5-detail-line'><b>Original Signal Memory:</b> <span class='good'>{_mem_num}</span> / {_mem_den} covered • <span class='warn'>{_mem_missing} missing</span> • statuses: BACKFILLED / NEW / PERSISTED / MISSING</div>",unsafe_allow_html=True)
        if _mem_missing:
            st.caption('Missing historical memory is never invented. Older Scanner XLSX files can still be imported once in Feedback → Import prior Scanner workbooks; verified legacy migrations such as 1780 are backfilled automatically.')
    with st.expander('Scan diagnostics',expanded=False):
        st.caption(f"Completed {_completed_il_txt} Israel • Duration {_fmt_seconds(last.get('duration',0))} • Requested/Broad {_broad} • Stage-0 {_stage0} • Daily OK {daily_ok} • Deep {deep_ok} • Skipped/errors {len(skipped)}")
        if _disc:
            _bm=_disc.get('by_market') or {}
            _parts=[]
            for _mk,_mv in _bm.items():
                if isinstance(_mv,dict):_parts.append(f"{_mk}: scanned {int(_mv.get('scanned',0) or 0)}, candidates {int(_mv.get('candidates',0) or 0)}, anchors {int(_mv.get('mandatory_anchors',0) or 0)}")
                else:_parts.append(f"{_mk}: {_mv}")
            if _parts:st.caption(' • '.join(_parts))
            st.caption(f"Discovery source: {_disc.get('source','—')}")
            st.caption('Instrument guard: COMMON STOCKS ONLY in broad discovery • exchange-traded notes/bonds/preferreds/warrants/units/ETFs are excluded before Stage-0 when identifiable.')
            _rc=len(_disc.get('reserved_core_deep') or [])
            if _rc:st.caption(f"Core Deep reserve: {_rc} liquid US core names (includes NVDA) • active-signal/bridge reserves remain separate")
            st.caption('Stage-0 only shortlists candidates; final cards use the normal Daily + 1H + 15m decision engine.')
    if res is None or res.empty:
        st.warning("The selected Show filter has no matching stocks in the last completed scan.")
    else:
        if show_mode=='ALL':
            # V6.3.9.59: two distinct headline queues. Current trade actionability and
            # early Pre-Move discovery are intentionally not forced into one ranking.
            _act_stage=res.get('EffectiveDecisionStage',res.get('DecisionBoardStage',pd.Series('WAIT',index=res.index))).astype(str)
            _act_stage=_act_stage.map(_decision_stage_canonical_v63961)
            _actionable=res[_act_stage.isin(['ENTRY NOW','ARMED','BUILDING SETUP','ARMED BLOCKED','LAST SESSION ENTRY','RETEST'])].head(5).copy()
            if _actionable.empty:_actionable=res.head(5).copy()
            _actionable['_TopSectionV63959']='ACTION';_actionable['_TopSectionRankV63959']=range(1,len(_actionable)+1)
            _pm=res[res.get('PreMovePatternDetected',res.get('PreMoveRadarEligible',pd.Series(False,index=res.index))).fillna(False).astype(bool)].copy()
            if not _pm.empty:
                _tier=_pm.get('PreMovePatternStrength',pd.Series('WATCH',index=_pm.index)).astype(str).str.upper().map({'HIGH':0,'WATCH':1}).fillna(9)
                _pm['_PMTierV63959']=_tier
                _pm['_PMActionV63959']=_pm.get('PreMoveRadarActionable',_pm.get('PreMoveActionableNow',pd.Series(False,index=_pm.index))).fillna(False).astype(bool).astype(int)
                _pm['_PMScoreV63959']=pd.to_numeric(_pm.get('PreBreakoutAccumulationScore',pd.Series(np.nan,index=_pm.index)),errors='coerce').fillna(-1)
                _pm['_PMFamV63959']=pd.to_numeric(_pm.get('PreMoveFamilyCount',pd.Series(0,index=_pm.index)),errors='coerce').fillna(0)
                _pm['_PMFlowV63959']=pd.to_numeric(_pm.get('NetFlowBalance',_pm.get('MoneyFlowScore',pd.Series(0,index=_pm.index))),errors='coerce').fillna(0)
                _pm=_pm.sort_values(['_PMTierV63959','_PMActionV63959','_PMScoreV63959','_PMFamV63959','_PMFlowV63959'],ascending=[True,False,False,False,False],na_position='last',kind='stable')
                _shown=set(_actionable.get('Ticker',pd.Series(dtype=str)).astype(str))
                _pm=_pm[~_pm.get('Ticker',pd.Series('',index=_pm.index)).astype(str).isin(_shown)].head(5).copy()
                _pm['_TopSectionV63959']='PREMOVE';_pm['_TopSectionRankV63959']=range(1,len(_pm)+1)
                _pm=_pm.drop(columns=['_PMTierV63959','_PMActionV63959','_PMScoreV63959','_PMFamV63959','_PMFlowV63959'],errors='ignore')
            topcards=pd.concat([_actionable,_pm],ignore_index=True,sort=False) if not _pm.empty else _actionable
        elif show_mode in ('BUILDING SETUP','ARMED','ARMED BLOCKED','ENTRY NOW','LAST SESSION ENTRY','RETEST','TOO LATE'):
            topcards=res.head(5).copy();topcards['_TopSectionV63959']='FILTERED';topcards['_TopSectionRankV63959']=range(1,len(topcards)+1)
        elif show_mode=='EMERGING SETUPS' and 'EmergingRank' in res.columns:
            topcards=res.sort_values(['EmergingRank','EmergingSetupScore'],ascending=[True,False],na_position='last').head(5).copy();topcards['_TopSectionV63959']='FILTERED';topcards['_TopSectionRankV63959']=range(1,len(topcards)+1)
        elif show_mode in ('VALIDATED OPPORTUNITIES','VALIDATED PICKS') and 'QualifiedRank' in res.columns:
            topcards=res.sort_values(['QualifiedRank','DecisionRankScore'],ascending=[True,False],na_position='last').head(5).copy();topcards['_TopSectionV63959']='FILTERED';topcards['_TopSectionRankV63959']=range(1,len(topcards)+1)
        elif show_mode=='EVIDENCE VALIDATED' and 'EvidenceRank' in res.columns:
            topcards=res.sort_values(['EvidenceRank','DecisionEvidenceScore'],ascending=[True,False],na_position='last').head(5).copy();topcards['_TopSectionV63959']='FILTERED';topcards['_TopSectionRankV63959']=range(1,len(topcards)+1)
        else:
            topcards=res.head(5).copy();topcards['_TopSectionV63959']='FILTERED';topcards['_TopSectionRankV63959']=range(1,len(topcards)+1)
        # Ensure the five cards actually shown have catalyst context even when a
        # view/filter surfaces a stock outside the scan-time Top-N catalyst pass.
        # Preserve exact render order across merge/enrichment so queue #1 stays first.
        topcards=topcards.copy();topcards['_RenderPositionV63953']=range(1,len(topcards)+1)
        try:
            if bool((last.get('config') or {}).get('catalyst_overlay',True)):
                _cv=pd.to_numeric(topcards.get('CatalystScore',pd.Series(np.nan,index=topcards.index)),errors='coerce')
                if _cv.isna().any():topcards=_catalyst_enrich_top_v6394(topcards,top_n=min(10,len(topcards)))
        except Exception:pass
        if '_RenderPositionV63953' in topcards.columns:
            topcards=topcards.sort_values('_RenderPositionV63953',kind='stable').drop(columns=['_RenderPositionV63953'])
        # V6.3.9.59: ALL shows a current-action queue and a separate Pre-Move
        # radar queue. A HIGH historical pattern therefore stays visible even if
        # current entry timing is already TOO LATE.
        _last_top_section=None
        for _,r in topcards.iterrows():
            _top_section=str(r.get('_TopSectionV63959','FILTERED') or 'FILTERED')
            if _top_section!=_last_top_section:
                if _top_section=='ACTION':
                    st.markdown("### ⚡ Top Action / Decision Queue")
                    st.caption("Current trade-action order: live ENTRY NOW first, then qualified ARMED / BUILDING SETUP / ARMED BLOCKED / last-session / RETEST. This is separate from the early-pattern radar below.")
                elif _top_section=='PREMOVE':
                    st.markdown("### 📡 Top Pre-Move Radar")
                    st.caption("Pattern-discovery order: HIGH before WATCH. A strong pattern remains visible here even when the current trade is already TOO LATE.")
                _last_top_section=_top_section
            with st.container(border=True):
                rank=int(r.get('TradePriorityRank',r.get('Rank',0)) or 0)
                _global_rank=int(_num6395(r.get('GlobalRank',0)) or 0)
                _qrank=_num6395(r.get('QualifiedRank',np.nan));_erank=_num6395(r.get('EmergingRank',np.nan));_vrank=_num6395(r.get('EvidenceRank',np.nan))
                _lane=str(r.get('DecisionLane','RESEARCH / BLOCKED') or 'RESEARCH / BLOCKED')
                _board_view=show_mode in ('ALL','BUILDING SETUP','ARMED','ARMED BLOCKED','ENTRY NOW','LAST SESSION ENTRY','RETEST','TOO LATE')
                _premove_top_card=(_top_section=='PREMOVE')
                _view_rank=int(_num6395(r.get('Rank',0)) or 0)
                _aqrank=_num6395(r.get('ActionQueueRank',np.nan));_osrank=_num6395(r.get('OverallStrengthRank',np.nan));_bstage=str(r.get('EffectiveDecisionStage',r.get('DecisionBoardStage','WAIT')) or 'WAIT');_bdisplay=_decision_stage_display_v63960(r.get('DecisionDisplayStage',_bstage) or _bstage)
                _pm_local_rank=_num6395(r.get('_TopSectionRankV63959',r.get('PreMoveRadarRank',np.nan)))
                if _premove_top_card:_rank_label=(f"PRE-MOVE #{int(_pm_local_rank)}" if np.isfinite(_pm_local_rank) else 'PRE-MOVE')
                elif _board_view:_rank_label=(f"{_bdisplay} #{int(_aqrank)}" if np.isfinite(_aqrank) else f"#{_view_rank or rank}")
                elif np.isfinite(_qrank):_rank_label=f"Q#{int(_qrank)}"
                elif np.isfinite(_erank):_rank_label=f"E#{int(_erank)}"
                elif np.isfinite(_vrank):_rank_label=f"EV#{int(_vrank)}"
                else:_rank_label=f"G#{_global_rank or rank}"
                ticker=_e6395(r.get('Ticker','—'))
                trade_stage=str(r.get('TradeStageDisplay',r.get('TradeStage','—')))
                exit_pressure=float(r.get('ExitPressure',0) or 0)
                exit_stage=str(r.get('ExitStage','CLEAR'))
                trade_cls='good' if _decision_stage_canonical_v63961(r.get('EffectiveDecisionStage','WAIT'))=='ENTRY NOW' else 'warn'
                exit_cls='bad' if exit_pressure>=55 else ('warn' if exit_pressure>=35 else 'good')
                _drs=_num_v6394(r.get('DecisionRankScore'),np.nan)
                _emscore=_num_v6394(r.get('EmergingSetupScore'),np.nan)
                _evidence=_num_v6394(r.get('DecisionEvidenceScore',r.get('Reliability')))

                # Refresh the displayed price for every visible card.
                _logical_ticker=str(r.get('Ticker','') or '').upper().strip()
                _bridge=temporary_counter_info(_logical_ticker)
                _scan_px=_num6395(r.get('Price',np.nan))
                _px=np.nan;_px_ts='';_px_source='Current price unavailable';_provider=_logical_ticker
                try:_live_px=_top5_current_price_v63915(_logical_ticker)
                except Exception:_live_px={}
                _live_val=_num6395((_live_px or {}).get('price',np.nan))
                if (_live_px or {}).get('display_current') and np.isfinite(_live_val) and _live_val>0:
                    _px=float(_live_val)
                    _px_source=str((_live_px or {}).get('source','Current/delayed quote') or 'Current/delayed quote')
                    _px_ts=str((_live_px or {}).get('timestamp_label','') or '')
                    _provider=str((_live_px or {}).get('provider_symbol',_logical_ticker) or _logical_ticker)
                elif not (_bridge and _bridge.get('active_primary')) and np.isfinite(_scan_px):
                    # Visible fallback is explicitly labelled as scan price below.
                    _px=float(_scan_px);_px_source='Scan snapshot'
                _px_txt=(f"{_px:.3f}" if np.isfinite(_px) and abs(_px)<10 else (f"{_px:.2f}" if np.isfinite(_px) else '—'))
                _ccy=str(r.get('Currency','') or '').strip().upper()
                if not _ccy:
                    _mkt=str(r.get('Market',_market_for_ticker_v612(r.get('Ticker','')))).upper()
                    _ccy='HKD' if 'HONG KONG' in _mkt else ('USD' if _mkt in ('US','NASDAQ','NYSE') else ('ILA' if 'TEL AVIV' in _mkt else ''))
                _ccy_html=f"<span class='ccy'>{_e6395(_ccy)}</span>" if _ccy else ''

                # Decision Board views use one comparable decision headline; legacy
                # Q/E/EV lane headlines remain available inside Research views.
                if _premove_top_card:
                    _headline_label='PRE-MOVE';_headline_score=_num_v6394(r.get('PreBreakoutAccumulationScore'),np.nan)
                elif _board_view:
                    _headline_label='DECISION';_headline_score=_drs
                elif np.isfinite(_erank):
                    _headline_label='EMERGING';_headline_score=_emscore
                elif np.isfinite(_qrank):
                    _headline_label='VALIDATED';_headline_score=_drs
                elif np.isfinite(_vrank):
                    _headline_label='EVIDENCE';_headline_score=_evidence
                else:
                    _headline_label='SCORE';_headline_score=_drs
                _headline_txt=f"{_headline_score:.1f}" if np.isfinite(_headline_score) else '—'
                st.markdown(
                    f"<div class='top5-head'><div class='top5-name'>{_rank_label} {ticker}</div>"
                    f"<div class='top5-score'><small>{_headline_label}</small> {_headline_txt}<span class='den'>/100</span></div></div>",
                    unsafe_allow_html=True,
                )
                if _premove_top_card:
                    _pm_status=str(r.get('PreMoveRadarStatus',r.get('PreMoveActionabilityState','PRE-MOVE WATCH')) or 'PRE-MOVE WATCH')
                    _pm_cls='good' if 'ACTIONABLE EARLY' in _pm_status else ('bad' if 'TOO LATE' in _pm_status or 'LATE NOW' in _pm_status else 'warn')
                    st.markdown(f"<div class='top5-detail-line'><b>Pre-Move radar:</b> <span class='{_pm_cls}'>{_e6395(_pm_status)}</span> • <b>Decision now:</b> {_e6395(_bdisplay)}{(' #'+str(int(_aqrank))) if np.isfinite(_aqrank) else ''}</div>",unsafe_allow_html=True)
                elif _board_view and np.isfinite(_osrank):
                    st.markdown(f"<div class='top5-detail-line'><b>Overall strength:</b> #{int(_osrank)} • <b>Action queue:</b> {_e6395(_bdisplay)} #{int(_aqrank) if np.isfinite(_aqrank) else '—'}</div>",unsafe_allow_html=True)

                # One compact status line: price + market phase + trade state + exit.
                _phase=str(r.get('MarketPhase','UNKNOWN') or 'UNKNOWN')
                _session_extra=''
                if _phase=='AFTER-MARKET':
                    _ah=str(r.get('AHConfirmation','N/A') or 'N/A');_ahc=_num6395(r.get('AHChangePct',np.nan))
                    _session_extra=f" {_e6395(_ah)}"+(f" ({_ahc:+.2f}%)" if np.isfinite(_ahc) else '')
                elif _phase=='PRE-MARKET':
                    _pm=str(r.get('PMConfirmation','N/A') or 'N/A');_pmc=_num6395(r.get('PMChangePct',np.nan))
                    _session_extra=f" {_e6395(_pm)}"+(f" ({_pmc:+.2f}%)" if np.isfinite(_pmc) else '')
                _scan_badge=" • <span class='muted'>SCAN PRICE</span>" if _px_source=='Scan snapshot' else ''
                _bridge_badge=f" • <span class='muted'>TEMP {_e6395(_bridge.get('temporary_symbol',''))}</span>" if _bridge and _bridge.get('active_primary') else ''
                _inflow=_num_v6394(r.get('InflowPressure',r.get('MoneyFlowScore',50)),50)
                _inflow_label=str(r.get('InflowLabel',_inflow_label_v63922(_inflow)) or _inflow_label_v63922(_inflow))
                _outflow=_num_v6394(r.get('OutflowPressure',r.get('BearishVolumeEvidence',r.get('ExitPressure',0))),0)
                _outflow_label=str(r.get('OutflowLabel',_outflow_label_v63921(_outflow)) or _outflow_label_v63921(_outflow))
                _net=_num_v6394(r.get('NetFlowBalance',_inflow-_outflow),_inflow-_outflow)
                _net_label=str(r.get('NetFlowLabel',_net_flow_label_v63922(_net)) or _net_flow_label_v63922(_net))
                _outflow_cls='bad' if _outflow>=60 else ('warn' if _outflow>=40 else 'good')
                _inflow_cls='good' if _inflow>=60 else ('warn' if _inflow>=40 else '')
                _net_cls='good' if _net>=8 else ('bad' if _net<=-8 else 'warn')
                _rvol,_rvol_band,_rvol_mode=_rvol_display_v63929(r,_phase)
                _rvol_txt=f"{_rvol:.2f}×" if np.isfinite(_rvol) else '—'
                _raw_board,_opp_window,_opp_reason,_timing_ctx=_decision_board_state_v63948(r)
                _board_stage=str(r.get('EffectiveDecisionStage',_raw_board) or _raw_board)
                _display_board,_display_window,_display_reason=_decision_display_semantics_v63953(r,_board_stage,_opp_window,r.get('EffectiveDecisionReason',_opp_reason))
                _display_board=_decision_stage_display_v63960(_display_board)
                _board_cls='good' if _display_board in ('ENTRY NOW','LAST SESSION ENTRY') else ('warn' if _decision_stage_canonical_v63961(_board_stage) in ('BUILDING SETUP','ARMED','ARMED BLOCKED','RETEST') else ('bad' if _board_stage=='TOO LATE' else ''))
                _window_cls='good' if _display_window=='OPEN' else ('warn' if _display_window in ('BUILDING','NEAR','WAIT','RECHECK AT OPEN') else ('bad' if _display_window=='CLOSED' else ''))
                st.markdown(
                    f"<div class='top5-status'><b>{_px_txt}{_ccy_html}</b>{_scan_badge}{_bridge_badge} • {_e6395(_phase)}{_session_extra} • "
                    f"Decision <span class='top5-pill {_board_cls}'>{_e6395(_display_board)}</span> • Window <span class='{_window_cls}'><b>{_e6395(_display_window)}</b></span> • Exit <span class='{exit_cls}'><b>{_e6395(exit_stage)}</b></span></div>",
                    unsafe_allow_html=True,
                )
                _action_txt=str(r.get('RecommendedAction',r.get('OpportunityWindowReason',_opp_reason)) or _opp_reason)
                if _action_txt and _action_txt not in ('—','None'):
                    st.markdown(f"<div class='top5-detail-line'><b>Action:</b> {_e6395(_action_txt)}</div>",unsafe_allow_html=True)

                _cm=_render_core_grid_v63948(r,_phase)
                _setupq=_cm['setup'];_entry=_cm['entry'];_mf=_num_v6394(r.get('MoneyFlowScore'))
                _cons=_cm['consumed'];_te_short=_cm['trigger_timing'];_recent_run=_cm['recent'];_recent_atr=_cm['recent_atr'];_recent_window=_cm['recent_window'];_recent_label=_cm['recent_label'];_post_cons=_cm['post'];_post_label=_cm['post_label']
                _cr=_cm['chase_score'];_chase=_cm['chase'];_hour=_cm['hour'];_hour_sub=_cm['hour_sub'];_rr1=_cm['rr1'];_rr2=_cm['rr2'];_rr_txt=_cm['rr1_txt'];_rr_sub=_cm['rr2_txt']
                _inflow=_cm['inflow'];_outflow=_cm['outflow'];_net=_cm['net'];_inflow_label=_cm['inflow_label'];_outflow_label=_cm['outflow_label'];_net_label=_cm['net_label']
                _rvol=_cm['rvol'];_rvol_band=_cm['rvol_band'];_rvol_mode=_cm['rvol_mode']
                _mbt=_num6395(r.get('MoveBeforeTriggerPct',np.nan));_st=_num6395(r.get('SinceTriggerPct',np.nan))
                _cons_txt=f"{_cons:.0f}%" if np.isfinite(_cons) else '—';_recent_txt=f"+{_recent_run:.1f}%" if np.isfinite(_recent_run) else '—';_post_txt=f"{_post_cons:.0f}%" if np.isfinite(_post_cons) else '—'
                _ev_n=_cm['ev_n'];_ev_lift=_cm['ev_lift'];_ev_lift_txt=f'{_ev_lift:.2f}x' if np.isfinite(_ev_lift) else '—';_ev_qual=_cm['ev_q'];_ev_progress=f"{_ev_n}/12" if _ev_n<12 else f"{_ev_n}/12 ✓"
                timing_risk=(np.isfinite(_cons) and _cons>=70) or _chase!='LOW' or not bool(r.get('ExtensionGuardCheck',True))
                if np.isfinite(_cons) and _cons>=80:
                    st.markdown(f"<div class='top5-alert'>⛔ <b>TIMING HARD BLOCK</b> • {_cons_txt} consumed before trigger in current session • RETEST ONLY / DO NOT CHASE</div>",unsafe_allow_html=True)
                elif timing_risk:
                    st.markdown(f"<div class='top5-alert'>⚠️ <b>TIMING RISK</b> • session pre-trigger {_cons_txt} • Chase {_e6395(_chase)}</div>",unsafe_allow_html=True)
                if _recent_label in ('LATE CONTEXT','EXTENDED CONTEXT'):
                    st.markdown(f"<div class='top5-alert'>⚠️ <b>MULTI-DAY CONTEXT</b> • {_recent_txt} over {_e6395(_recent_window)} • {_e6395(_recent_label)} • a fresh session trigger does not mean the overall move is early</div>",unsafe_allow_html=True)
                _evq=str(r.get('EvidenceQualification','UNPROVEN') or 'UNPROVEN')
                _ev_trade=bool(r.get('EvidenceTradeGrade',False));_ev_guard=bool(r.get('EvidenceGuardOK',True))
                if not _ev_trade and _ev_guard:
                    st.markdown(f"<div class='top5-alert'>⚠️ <b>UNVALIDATED • WARNING ONLY</b> • Evidence {_ev_n}/12 • {_e6395(_evq)}</div>",unsafe_allow_html=True)
                elif not _ev_guard:
                    st.markdown(f"<div class='top5-alert'>⛔ <b>EVIDENCE HARD GUARD</b> • Evidence {_ev_n}/12 • {_e6395(_evq)}</div>",unsafe_allow_html=True)
                if _ev_trade and not bool(r.get('ValidatedOpportunityEligible',r.get('DecisionRankEligible',False))):
                    _opp_reason=_e6395(r.get('CurrentOpportunityQualification','CURRENT WAIT'))
                    st.markdown(f"<div class='top5-alert'>ℹ️ <b>EVIDENCE VALIDATED</b> • {_opp_reason}</div>",unsafe_allow_html=True)
                if not bool(r.get('SessionDataFresh',True)) or str(r.get('DataQuality','OK'))!='OK':
                    _fs=_e6395(r.get('PriceFreshnessStatus',r.get('DataQuality','STALE DATA')))
                    st.markdown(f"<div class='top5-alert'>⚠️ <b>STALE DATA</b> • {_fs}</div>",unsafe_allow_html=True)

                if bool(r.get('PlanValid',False)) and str(r.get('MarketPhase',''))=='OPEN' and str(r.get('LiveStage',''))=='CONFIRMED ENTRY — LIVE':
                    vals={k:_num6395(r.get(k,np.nan)) for k in ['EntryLow','EntryHigh','Invalidation','Target1','Target2']}
                    if all(np.isfinite(vals[k]) for k in vals):
                        st.markdown(
                            f"<div class='top5-plan'><b>🟢 LIVE PLAN</b> • Entry <b>{vals['EntryLow']:.3f}–{vals['EntryHigh']:.3f}</b> • Stop <b>{vals['Invalidation']:.3f}</b> • T1 <b>{vals['Target1']:.3f}</b> • T2 <b>{vals['Target2']:.3f}</b></div>",
                            unsafe_allow_html=True,
                        )
                _retest_context=('RETEST' in str(r.get('TradeStage','')).upper() or 'RETEST' in str(r.get('TimingQualification','')).upper() or (np.isfinite(_cons) and _cons>=60.0) or not bool(r.get('ExtensionGuardCheck',True)))
                if _retest_context:
                    _rv={k:_num6395(r.get(k,np.nan)) for k in ['RetestEntryLow','RetestEntryHigh','RetestInvalidation','RetestTarget1','RetestTarget2','RetestRR_T1']}
                    if bool(r.get('RetestPlanValid',False)) and all(np.isfinite(_rv[k]) for k in ['RetestEntryLow','RetestEntryHigh','RetestInvalidation','RetestTarget1','RetestTarget2']):
                        _rrt=f" • R:R T1 <b>{_rv['RetestRR_T1']:.2f}x</b>" if np.isfinite(_rv['RetestRR_T1']) else ''
                        st.markdown(f"<div class='top5-plan'><b>🟡 RETEST PLAN • RECONFIRM REQUIRED</b> • Entry <b>{_rv['RetestEntryLow']:.3f}–{_rv['RetestEntryHigh']:.3f}</b> • Stop <b>{_rv['RetestInvalidation']:.3f}</b> • T1 <b>{_rv['RetestTarget1']:.3f}</b> • T2 <b>{_rv['RetestTarget2']:.3f}</b>{_rrt}</div>",unsafe_allow_html=True)
                    elif str(r.get('RetestStatus','—')) not in ('','—','NO RELIABLE RETEST LEVEL'):
                        st.caption(f"Retest: {r.get('RetestStatus')} • {r.get('RetestPlanReason','No qualified retest plan — reassess geometry before entry')}")

                with st.expander("Details / Why?",expanded=False):
                    _render_decision_why_v63953(r,_phase)
                with st.expander("Advanced diagnostics",expanded=False):
                    pm_stage=str(r.get('PreMoveStage','NO CURRENT PRE-MOVE CANDIDATE'))
                    live_entry=str(r.get('TradeStageDisplay',r.get('EntryTriggerState',r.get('TradeStage','—'))))
                    if pm_stage!='NO CURRENT PRE-MOVE CANDIDATE':
                        st.markdown(f"**Research radar:** **{pm_stage}** • **Live entry:** **{live_entry}**")
                        st.caption(f"Pre-Move score {safe(r.get('PreMoveScore'),1)} • OOS empirical hit {safe(r.get('PreMoveProbabilityPct'),1)}% • Best lift {safe(r.get('PreMoveBestOOSLiftX'),2)}x • Freshness {r.get('PreMoveFreshness','—')} • Families {int(r.get('PreMoveIndependentFamilyCount',0) or 0)} • Research only")
                    else:
                        st.caption(f"Research radar: no current Pre-Move candidate • Live entry: {live_entry}")
                    if pd.notna(r.get('RegularRadarScore',np.nan)):
                        st.markdown(f"**Regular radar:** **+{safe(r.get('RegularRadarTargetPct'),0)}% / {r.get('RegularRadarLeadWindow','—')}** • **{r.get('RegularFunnelStage','RESEARCH EDGE')}** • live layer **{r.get('RegularFunnelLiveLayer','RESEARCH / WAIT')}**")
                        st.caption(f"Signature score {safe(r.get('RegularRadarScore'),1)} • OOS hit {safe(r.get('RegularRadarHitRatePct'),1)}% vs baseline {safe(r.get('RegularRadarBaselinePct'),1)}% • lift {safe(r.get('RegularRadarLiftX'),2)}x • FINAL funnel {safe(r.get('RegularFunnelFinalHitRatePct'),1)}% vs {safe(r.get('RegularFunnelFinalBaselinePct'),1)}% • N {safe(r.get('RegularFunnelFinalN'),0)} • setup {safe(r.get('RegularRadarSetupScore'),1)} • {r.get('RegularRadarFreshness','—')} • research only")
                    st.caption(f"Entry gates {int(r.get('EntryConfirmedConditions',0) or 0)}/{int(r.get('EntryTotalConditions',6) or 6)} ({float(r.get('EntryConfirmationPct',0) or 0):.0f}%) • Why now: {r.get('EntryWhyNow','—')}")
                    _chead=str(r.get('CatalystTopHeadline','') or '').strip();_cer=str(r.get('CatalystEventRisk','UNKNOWN') or 'UNKNOWN')
                    st.caption(f"Flow: In {_inflow:.0f}/100 {_inflow_label} • Out {_outflow:.0f}/100 {_outflow_label} • Net {_net:+.0f} {_net_label} • {r.get('FlowPressureEvidence',r.get('MoneyFlowEvidence','—'))} • Cycle: {r.get('MarketCycleReason','—')}")
                    if _chead:st.caption(f"Catalyst evidence {r.get('CatalystEvidence','NO DATA')} • {_cer} • {_chead}")
                    else:st.caption(f"Catalyst: {r.get('CatalystEvidence','NO DATA')} / {_cer}")
                    if str(r.get('ArmedTimingClass','N/A'))!='N/A':st.caption(f"Early-entry validation: {r.get('ArmedTimingClass')} • {r.get('ArmedTimingReason','—')} • Actionability: {r.get('EntryActionabilityState',r.get('TradeStage','—'))}")
                    st.caption(f"Trigger timing: {_te_short} • consumed {f'{_cons:.1f}%' if np.isfinite(_cons) else '—'} • before trigger {f'{_mbt:+.2f}%' if np.isfinite(_mbt) else '—'} • since trigger {f'{_st:+.2f}%' if np.isfinite(_st) else '—'}")
                    if np.isfinite(float(r.get('OptimizedScore',np.nan))):st.caption(f"{r.get('OptimizedStage','OPTIMIZED WAIT')} • Optimized {float(r.get('OptimizedScore')):.1f} • Match {float(r.get('OptimizedMatchPct',np.nan)):.0f}% • Δ vs TOP {float(r.get('OptimizedDelta',np.nan)):+.1f} • Institutional Flow {float(r.get('InstitutionalFlowScore',np.nan)):.0f} ({r.get('InstitutionalFlowLabel','—')})")
                    if str(r.get('EntryMissingChecks','')) not in ('','None'):st.caption("Still missing: "+str(r.get('EntryMissingChecks')))
                    _vs=_num6395(r.get('ValuationScore',np.nan));_vd=_num6395(r.get('EstimatedDiscountPct',np.nan));_fl=_num6395(r.get('FairValueLow',np.nan));_fh=_num6395(r.get('FairValueHigh',np.nan))
                    if np.isfinite(_vs):
                        _curr=str(r.get('Currency','') or '').strip();_range=f"{_fl:.2f}–{_fh:.2f}" if np.isfinite(_fl) and np.isfinite(_fh) else '—';_disc=f"{_vd:+.1f}%" if np.isfinite(_vd) else '—'
                        st.markdown(f"**Valuation (research):** **{_vs:.0f}/100 • {r.get('ValuationLabel','—')}** • Estimated discount {_disc} • Fair-value range {_range} {_curr} • Evidence {r.get('ValuationEvidence','NO DATA')}")
                        st.caption(f"{r.get('ValuationArchetype','—')} • {int(r.get('ValuationMetricCount',0) or 0)} usable multiples • ≥{int(r.get('ValuationPeerCount',0) or 0)} peers • informational only; does not change Entry/ARMED/CONFIRMED")
                    st.caption(f"Decision Score {safe(r.get('DecisionRankScore'),1)}/100 • model V3.13 • {r.get('DecisionRankReason','—')}")
                    st.caption(f"Legacy research context only: TOP {safe(r.get('TopScore'),1)} • Opportunity {safe(r.get('OpportunityScore'),1)} • Market Cycle {r.get('MarketCycleStage','—')} ({safe(r.get('MarketCycleScore'),1)})")
                    st.caption(f"Prediction {safe(r.get('Prediction'),1)} • Hourly {safe(r.get('HourlyConfirm'),1)} • Evidence {r.get('EvidenceQuality','LOW')} • R:R {_rr_txt} ({_rr_sub})")
                    st.caption(f"Move {safe(r.get('MoveScore'),1)} • Explosive {safe(r.get('ExplosiveScore'),1)} • Volume {r.get('VolumeContext','N/A')} • Live RVOL {safe(r.get('LiveIntradayRVOL',r.get('TimeAdjustedRVOL')))}x • Daily RVOL {safe(r.get('DailyRobustRVOL'))}x • Priority #{int(r.get('TradePriorityRank',r.get('GlobalRank',0)) or 0)} • Score-rank #{int(r.get('DecisionScoreRank',0) or 0)} • Qualified {('#'+str(int(r.get('QualifiedRank')))) if pd.notna(r.get('QualifiedRank',np.nan)) else '—'} • Emerging {('#'+str(int(r.get('EmergingRank')))) if pd.notna(r.get('EmergingRank',np.nan)) else '—'} • Historical EV Rank {('#'+str(int(r.get('EvidenceRank')))) if pd.notna(r.get('EvidenceRank',np.nan)) else '—'} • {r.get('Market','—')} #{int(r.get('MarketRank',0) or 0)} • Sector #{int(r.get('SectorRank',0) or 0)}")
                    n=int(r.get('BacktestN',0) or 0);bt_txt=(f"{safe(r.get('EmpiricalHitRate'),1)}% ({n} signals) • " + ('VALIDATED' if n>=12 else ('BUILDING' if n>=8 else 'PROVISIONAL'))) if n>=6 else f"LOW SAMPLE — {n} signals"
                    st.caption(f"Evidence {r.get('EvidenceQuality','LOW')} • Reliability {safe(r.get('Reliability'),1)} • Backtest {bt_txt} • Lift {safe(r.get('SignalLift'))}x • RSI {safe(r.get('RSI14'),1)} • Data quality {r.get('DataQuality','OK')}{' • Split adjusted' if bool(r.get('SplitAdjusted',False)) else ''}")
        _scanner_stage_guide_v599()
        # Clear ranking table:
        # Rank = position inside the CURRENT selected view/filter.
        # GlobalRank = current-first TradePriorityRank across the full scan; DecisionScoreRank is raw score research order.
        # MarketRank = position only inside the stock's exchange (NASDAQ / NYSE / Hong Kong / Tel Aviv).
        cols=['Ticker','Rank','LiquidityScore','LiquidityLabel','LiquidityHardGateOK','LiquidityBlockReason','MedianDailyTurnover60','AvgDailyTurnover20','LiquidityTurnoverCurrency','DecisionBoardStage','RawDecisionBoardStage','EffectiveDecisionStage','DecisionDisplayStage','DecisionStageLabel','EffectiveDecisionReason','EntryNowHardGateOK','EntryNowHardGateReason','ArmedQualified','ArmedQualificationState','ArmedQualificationReason','NeedsOpenRevalidation','CurrentMarketPhaseNow','OpportunityWindow','OpportunityWindowReason','TimingContext','TriggerTimingDisplay','RecentRunPct','RecentRunATR','RecentRunWindow','RecentRunLabel','PostTriggerConsumedPct','PostTriggerConsumedLabel','RecentRunRetestContext','MoveConsumedBeforeTriggerPct','RegularFunnelStage','RegularFunnelLiveLayer','RegularRadarTargetPct','RegularRadarLeadWindow','RegularRadarTimeframe','RegularRadarScore','RegularRadarHitRatePct','RegularRadarBaselinePct','RegularRadarLiftX','RegularRadarBestSignature','RegularRadarSetupScore','RegularRadarFreshness','RegularRadarMoveConsumedPct','RegularFunnelMatches','RegularFunnelFamilyCount','RegularFunnelFinalN','RegularFunnelFinalHitRatePct','RegularFunnelFinalBaselinePct','RegularFunnelFinalLiftX','RegularFunnelFinalStatus','RegularModelMarket','RegularModelRunCompleted','RegularModelAgeHours','PreMoveStage','PreMoveScore','PreMoveProbabilityPct','PreMoveFreshness','PreMoveMoveConsumedPct','PreMovePatternStrength','PreMovePatternDetected','PreMoveActionableNow','PreMoveRadarActionable','PreMovePatternOnly','PreMoveRadarRank','PreMoveRadarStatus','PreMoveIndependentFamilyCount','PreMovePositiveOOSFamilyCount','PreMoveCoreConfirmed','PreMoveBestOOSLiftX','PreMoveStrongestFeatures','PreMoveTargetHorizon','PreMoveRunCompleted','PreMoveRunAgeHours','TradePriorityRank','TradePriorityClass','TradePriorityCurrentEligible','TradePriorityBucket','TradePriorityVersion','QualifiedRank','EmergingRank','EmergingFreshnessTier','EvidenceRank','DecisionLane','EmergingSetupEligible','EmergingSetupScore','EmergingSetupReason','DecisionRankScore','DecisionRankCore','DecisionScoreRank','DecisionRankRRQuality','DecisionRankRiskPenalty','DecisionRankEvidencePenalty','DecisionRankQualificationCap','DecisionRankEligible','ValidatedOpportunityEligible','EvidenceValidated','CurrentOpportunityQualified','CurrentOpportunityQualification','ValidatedOpportunityReason','DecisionRankQualification','EvidenceQualification','EvidenceQualificationReason','EvidenceTradeGrade','EvidenceSampleN','EvidenceLiftX','TimingQualification','TimingDataComplete','TimingDataSource','TimingDataReason','DataFreshnessQualification','DecisionRankStageModifier','DecisionRankTimingPenalty','DecisionRankChasePenalty','DecisionRankExitPenalty','DecisionRankReason','DecisionRankVersion','LegacyTradePriorityRank','LegacyGlobalRank','OptimizedStage','OptimizedScore','OptimizedMatchPct','OptimizedDelta','OptimizedModelStatus','OptimizedModelID','OptimizedModelScope','OptimizedModelHorizon','OptimizedModelOOSLift','HourlyOptimizedScore','HourlyOptimizedMatchPct','HourlyOptimizedStatus','HourlyOptimizedHorizon','InstitutionalFlowScore','InstitutionalFlowLabel','MoneyFlowScore','MoneyFlowLabel','MoneyFlowEvidence','InflowPressure','InflowLabel','OutflowPressure','OutflowLabel','NetFlowBalance','NetFlowScore','NetFlowLabel','FlowPressureEvidence','MarketCycleScore','MarketCycleStage','MarketCycleReason','CatalystScore','CatalystLabel','CatalystEvidence','CatalystTopHeadline','CatalystRecentNewsCount','CatalystEventRisk','CatalystCoverage','GlobalRank','MarketRank','SectorRank','Market','Sector','ValuationScore','ValuationLabel','EstimatedDiscountPct','FairValueLow','FairValueHigh','Currency','ValuationEvidence','ValuationArchetype','ValuationMetricCount','ValuationPeerCount','ValuationPeerScope','ValuationMethod','ValuationPriceMismatch','ValuationPriceMismatchPct','MarketPhase','SessionStatus','LiveStage','ActionableNow','TradeStage','TradeStageDisplay','RawEntryTriggerState','EntryTriggerState','EntryActionabilityState','ArmedTimingClass','ArmedTimingReason','EvidenceConfirmationGate','SetupConfirmed','PriceActionableNow','RRActionable','ConfirmedEntryGateOK','EntryDistancePct','ActionabilityMissing','SessionEntryState','RegularSessionEntryState','EntryConfirmationPct','DailySetupCheck','FreshSignalCheck','HourlyEntryCheck','VolumeFlowCheck','NoChaseCheck','RawNoChaseCheck','NoChaseConsistencyOverride','NoChaseReason','ExtensionGuardCheck','ChaseRiskScore','ChaseRiskLabel','SessionMovePct','MoveBeforeTriggerPct','RegularSessionMovePct','AfterHoursMovePct','AfterHoursPrice','AfterHoursPriceSource','AfterHoursVolumeStrength','TotalMoveIncludingAHPct','SessionMoveATR','SessionMovePercentile','SinceTriggerPct','GapPct','VWAPDistanceATR','Target1ProgressPct','LiveRR_T1','LiveRR_T2','LiveRRDisplayT1','LiveRRDisplayT2','LiveRRDisplayStatus','VolumeTrend','VolumeTrend15m','VolumeTrend1H','MomentumState','MomentumState15m','MomentumState1H','PostSpikeState','PostSpikeDistributionRisk','ContinuationBaseCandidate','ContinuationBaseStatus','ContinuationBaseQuality','ContinuationSessionPeak','ContinuationBreakoutTrigger','ContinuationBreakoutReference','TriggerAnchorPrice','TriggerAnchorTimeframe','TriggerAnchorQuality','TriggerAnchorAgeBars','RetestZoneLow','RetestZoneHigh','PullbackNeededPct','RetestStatus','RetestEntryLow','RetestEntryHigh','RetestInvalidation','RetestTarget1','RetestTarget2','RetestRR_T1','RetestRR_T2','RetestPlanValid','RetestPlanReason','RawRecommendedAction','RecommendedAction','RecommendedActionReason','MarketRegime','EntryWhyNow','EntryMissingChecks','MovementStage','WhyNotTradeTrigger','TopScore','OpportunityScore','Reliability','EvidenceQuality','EvidenceState','EvidenceGuardOK','ExitPressure','ExitStage','VolumeContext','BullishVolumeEvidence','BearishVolumeEvidence','IntradayCumulativeRVOL','LiveIntradayRVOL','FullSessionRVOL','DailyRobustRVOL','TimeAdjustedRVOL','MoveScore','ExplosiveScore','EntryScore','LiveActionabilityScore','SetupEntryScore','PlanValid','PlanReason','EntryLow','EntryHigh','BreakoutTrigger','Invalidation','Target1','Target2','Accel1D','Accel2D','Accel3D','HourlyConfirm','Signal','Prediction','DynamicQuant','DynamicEarly','EntryStatus','ExplosiveStage','P5_5D','P10_5D','P15_5D','P15_5D_N','SignalLift','CalibrationConfidence','Price','LivePriceFresh','SessionDataFresh','PriceSessionDate','ExpectedSessionDate','PriceFreshnessStatus','PriceSource','PriceTimestamp','RSI14','EmpiricalHitRate','BacktestN','SplitAdjusted','DataQuality','PMConfirmation','PMChangePct','PMVolumeStrength','AHConfirmation','AHChangePct','AHVolumeStrength']
        table=res[[c for c in cols if c in res]].copy()
        table=table.rename(columns={
            'Rank':'View Rank',
            'DecisionRankScore':'Decision Score V3.13','DecisionRankCore':'Decision Core','DecisionScoreRank':'Decision Score Rank (research)','GlobalRank':'Current Global Rank',
            'MarketRank':'Market Rank','SectorRank':'Sector Rank','TradePriorityRank':'Current Trade Priority','TradePriorityClass':'Trade Priority Class','QualifiedRank':'Qualified Opportunity Rank (Q#)','EmergingRank':'Emerging Rank (E#)','EvidenceRank':'Historical Evidence Rank (EV#)','EmergingFreshnessTier':'Emerging Freshness Tier',
        })
        if 'BacktestN' in table:
            _bn=pd.to_numeric(table['BacktestN'],errors='coerce').fillna(0)
            if 'EvidenceTradeGrade' in table:
                _tg=table['EvidenceTradeGrade'].fillna(False).astype(bool)
                _eq=table.get('EvidenceQualification',pd.Series('UNPROVEN',index=table.index)).astype(str)
                table['Backtest Quality']=np.where(_tg,'TRADE GRADE',np.where(_bn>=12,_eq,np.where(_bn>=8,'BUILDING EVIDENCE',np.where(_bn>=6,'PROVISIONAL EVIDENCE',np.where(_bn>0,'LOW SAMPLE','NO SAMPLE')))))
            else:
                table['Backtest Quality']=np.select([_bn>=12,_bn>=8,_bn>=6,_bn>0],['EVIDENCE REVIEW','BUILDING EVIDENCE','PROVISIONAL EVIDENCE','LOW SAMPLE'],default='NO SAMPLE')
            if 'EmpiricalHitRate' in table:table.loc[_bn<6,'EmpiricalHitRate']=np.nan
        if set(res.get('Market',pd.Series(dtype=str)).astype(str).unique()).isdisjoint({'NASDAQ','NYSE'}):
            table=table.drop(columns=[c for c in table.columns if c.startswith('PM') or c.startswith('AH')],errors='ignore')
        st.caption("E# = Emerging order • Q# = validated opportunity order • EV# = evidence-validated order. Full model diagnostics are available in Details / Why?.")
        st.dataframe(table,use_container_width=True,hide_index=True)
    if skipped:
        with st.expander(f"Skipped / error details ({len(skipped)})"):
            st.dataframe(pd.DataFrame(skipped),use_container_width=True,hide_index=True)

if hasattr(st,'fragment'):
    @st.fragment(run_every="1s")
    def _scanner_live_fragment_v599(show_mode,market_filter="ALL",timing_filter="ALL",quality_filter="ALL",risk_filter="ALL"):
        _render_scanner_results_v599(show_mode,market_filter,timing_filter,quality_filter,risk_filter)
        # V6.0.1: the 1-second fragment exists ONLY while a scan is active.
        # Once a terminal state is reached, force one full rerun so the fragment
        # is removed from the page. This stops Streamlit's stop/rerun icon from
        # blinking forever after the scan has finished.
        if _scanner_status_v601() not in ('running','stopping'):
            try:
                st.rerun(scope='app')
            except TypeError:
                st.rerun()
else:
    def _scanner_live_fragment_v599(show_mode,market_filter="ALL",timing_filter="ALL",quality_filter="ALL",risk_filter="ALL"):
        _render_scanner_results_v599(show_mode,market_filter,timing_filter,quality_filter,risk_filter)



# -----------------------------------------------------------------------------
# V6.0.2 server-side Research job runtime
# Research now follows the Scanner control model: it runs in a cached server-side
# worker, can be cooperatively stopped, and keeps running if the browser/app is
# backgrounded as long as the Streamlit server process itself remains alive.
# -----------------------------------------------------------------------------
class _ResearchCancelled(Exception):
    """Internal cooperative-cancel signal for the background Research worker."""


@st.cache_resource(show_spinner=False)
def _research_runtime_v602():
    return {
        'lock': threading.RLock(),
        'executor': None,
        'active': None,
        'last_completed': None,
    }


def _research_check_cancel_v602(runtime, job_id):
    with runtime['lock']:
        job = runtime.get('active')
        if not job or job.get('id') != job_id:
            raise _ResearchCancelled()
        if job.get('cancel_requested') or job.get('status') in ('stopping', 'stopped'):
            raise _ResearchCancelled()


def _research_update_v602(runtime, job_id, completed, total, ticker='—', phase='Researching'):
    now = time_module.time()
    with runtime['lock']:
        job = runtime.get('active')
        if not job or job.get('id') != job_id:
            raise _ResearchCancelled()
        job['completed'] = int(completed)
        job['total'] = int(total)
        job['ticker'] = str(ticker)
        job['market'] = _market_for_ticker_v612(ticker) if ticker not in (None, '—') else '—'
        job['phase'] = str(phase)
        job['progress'] = int(np.clip(100 * completed / max(1, total), 0, 99 if completed < total else 100))
        elapsed = now - float(job.get('started_at', now))
        job['elapsed'] = elapsed
        if completed > 0:
            avg = elapsed / completed
            job['eta'] = max(0.0, (total - completed) * avg)
        else:
            job['eta'] = None


def _research_payload_v602(research_rows, opt_all, atr_all, timeline_samples, premove_all, accel_all, skipped, config, partial=False):
    summary = pd.DataFrame(research_rows)
    if not summary.empty:
        summary = summary.sort_values(['Median Lift', 'Signals'], ascending=[False, False]).reset_index(drop=True)
    timeline_df = pd.concat(timeline_samples, ignore_index=True) if timeline_samples else pd.DataFrame()
    if not timeline_df.empty:
        topk_parts = [
            topk_daily_validation(timeline_df, score_col='Move Score'),
            topk_daily_validation(timeline_df, score_col='Explosive Score'),
        ]
        topk = pd.concat(topk_parts, ignore_index=True)
    else:
        topk = pd.DataFrame()
    premove_df = pd.concat(premove_all, ignore_index=True) if premove_all else pd.DataFrame()
    sheets = {
        'Adaptive Summary': summary,
        'Threshold Grid': pd.concat(opt_all, ignore_index=True) if opt_all else pd.DataFrame(),
        'ATR Validation': pd.concat(atr_all, ignore_index=True) if atr_all else pd.DataFrame(),
        'Pre-Move Study': premove_df,
        'Acceleration Validation': pd.concat(accel_all, ignore_index=True) if accel_all else pd.DataFrame(),
        'Top-K Validation': topk,
        'Historical Timeline': timeline_df,
        'Skipped': pd.DataFrame(skipped),
    }
    excel = workbook_bytes(sheets, {
        'Tab': 'Research 151',
        'Version': APP_VERSION,
        'History': config['history'],
        'Universe': len(config['tickers']),
        'MinimumSignals': config['minimum_signals'],
        'Method': 'Causal scores; future data labels only',
        'Status': 'PARTIAL / STOPPED' if partial else 'COMPLETED',
    })
    return {
        'summary': summary,
        'premove': premove_df,
        'topk': topk,
        'skipped': pd.DataFrame(skipped),
        'excel': excel,
        'partial': bool(partial),
    }


def _research_worker_v602(runtime, job_id, config):
    started = time_module.time()
    research_rows, opt_all, atr_all = [], [], []
    timeline_samples, premove_all, accel_all, skipped = [], [], [], []
    completed = 0
    current_ticker = '—'
    try:
        total = len(config['tickers'])
        for idx, tkr in enumerate(config['tickers'], start=1):
            current_ticker = tkr
            _research_check_cancel_v602(runtime, job_id)
            _research_update_v602(runtime, job_id, completed, total, tkr, 'Downloading daily history')
            try:
                dd = fetch_ohlcv(tkr, config['history'], '1d')
                _research_check_cancel_v602(runtime, job_id)
                if dd is None or len(dd) < 120:
                    skipped.append({'Ticker': tkr, 'Reason': '<120 daily rows'})
                else:
                    _research_update_v602(runtime, job_id, completed, total, tkr, 'Computing causal features')
                    ff = compute_features(dd)
                    _research_check_cancel_v602(runtime, job_id)

                    _research_update_v602(runtime, job_id, completed, total, tkr, 'Optimizing historical thresholds')
                    exo = threshold_optimization(ff, score_kind='explosive')
                    mvo = threshold_optimization(ff, score_kind='move')
                    both = pd.concat([exo, mvo], ignore_index=True)
                    both.insert(0, 'Ticker', tkr)
                    opt_all.append(both)
                    best = adaptive_target_horizon_v2(both, int(config['minimum_signals']))
                    if best:
                        research_rows.append({
                            'Ticker': tkr,
                            'Market': _market_for_ticker_v612(tkr),
                            'Sector': SECTOR_MAP.get(tkr, 'Other'),
                            **best,
                        })
                    _research_check_cancel_v602(runtime, job_id)

                    _research_update_v602(runtime, job_id, completed, total, tkr, 'Validating ATR / pre-move / acceleration')
                    av = atr_target_validation(ff, threshold=int(best.get('Threshold', 60)) if best else 60)
                    av.insert(0, 'Ticker', tkr)
                    atr_all.append(av)
                    tl_full = historical_signal_timeline(ff)
                    pm = pre_move_study(tl_full)
                    pm.insert(0, 'Ticker', tkr)
                    premove_all.append(pm)
                    avl = acceleration_validation(tl_full) if callable(acceleration_validation) else pd.DataFrame()
                    if not avl.empty:
                        avl.insert(0, 'Ticker', tkr)
                        accel_all.append(avl)
                    tl = tl_full.tail(260)
                    tl.insert(0, 'Ticker', tkr)
                    timeline_samples.append(tl)
                    _research_check_cancel_v602(runtime, job_id)
            except _ResearchCancelled:
                raise
            except Exception as e:
                skipped.append({'Ticker': tkr, 'Reason': str(e)[:180]})
            completed = idx
            _research_update_v602(runtime, job_id, completed, total, tkr, 'Ticker complete')

        _research_update_v602(runtime, job_id, completed, total, '—', 'Building Research workbook')
        _research_check_cancel_v602(runtime, job_id)
        payload = _research_payload_v602(
            research_rows, opt_all, atr_all, timeline_samples, premove_all, accel_all, skipped, config, partial=False
        )
        # If Stop was pressed while the workbook was being assembled, honor it
        # before publishing a completed result.
        _research_check_cancel_v602(runtime, job_id)
        finished = time_module.time()
        snapshot = {
            'id': job_id,
            'status': 'completed',
            'payload': payload,
            'started_at': started,
            'finished_at': finished,
            'duration': finished - started,
            'completed_label': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'config': config,
            'completed': completed,
            'total': len(config['tickers']),
        }
        with runtime['lock']:
            runtime['last_completed'] = snapshot
            if runtime.get('active') and runtime['active'].get('id') == job_id:
                runtime['active'].update({
                    'status': 'completed', 'progress': 100, 'elapsed': finished - started, 'eta': 0,
                    'ticker': '—', 'market': '—', 'phase': 'Completed', 'payload': payload,
                    'finished_at': finished, 'cancel_requested': False, 'completed': completed,
                })
    except _ResearchCancelled:
        finished = time_module.time()
        # Keep the already-finished tickers available as a clearly marked partial result.
        try:
            payload = _research_payload_v602(
                research_rows, opt_all, atr_all, timeline_samples, premove_all, accel_all, skipped, config, partial=True
            )
        except Exception:
            payload = None
        with runtime['lock']:
            if runtime.get('active') and runtime['active'].get('id') == job_id:
                runtime['active'].update({
                    'status': 'stopped', 'finished_at': finished, 'elapsed': finished - started, 'eta': 0,
                    'ticker': current_ticker, 'phase': 'Stopped safely', 'cancel_requested': True,
                    'payload': payload, 'completed': completed,
                })
    except Exception as e:
        finished = time_module.time()
        with runtime['lock']:
            if runtime.get('active') and runtime['active'].get('id') == job_id:
                runtime['active'].update({
                    'status': 'failed', 'error': f'{type(e).__name__}: {e}', 'finished_at': finished,
                    'elapsed': finished - started, 'eta': 0, 'cancel_requested': False,
                    'phase': 'Failed', 'completed': completed,
                })


def _start_research_job_v602(config):
    runtime = _research_runtime_v602()
    with runtime['lock']:
        active = runtime.get('active')
        if active and active.get('status') in ('running', 'stopping'):
            return False, 'Research is already running.'
        if runtime.get('executor') is None:
            runtime['executor'] = ThreadPoolExecutor(max_workers=1, thread_name_prefix='stock-hunter-research')
        job_id = f"research-{int(time_module.time()*1000)}"
        runtime['active'] = {
            'id': job_id, 'status': 'running', 'progress': 0, 'completed': 0,
            'total': len(config['tickers']), 'ticker': '—', 'market': '—', 'phase': 'Starting',
            'started_at': time_module.time(), 'elapsed': 0, 'eta': None, 'config': config,
            'cancel_requested': False,
        }
        runtime['executor'].submit(_research_worker_v602, runtime, job_id, config)
    return True, job_id


def _request_research_stop_v602():
    runtime = _research_runtime_v602()
    with runtime['lock']:
        active = runtime.get('active')
        if not active or active.get('status') not in ('running', 'stopping'):
            return False, 'No Research job is currently running.'
        if active.get('status') == 'stopping':
            return True, 'Stop already requested.'
        active['cancel_requested'] = True
        active['status'] = 'stopping'
        active['eta'] = 0
        active['phase'] = 'Stop requested — finishing the current safe step'
        return True, 'Stop requested. Research will stop safely after the current data/calculation step.'


def _research_status_v602():
    runtime = _research_runtime_v602()
    with runtime['lock']:
        active = runtime.get('active')
        return str(active.get('status', 'idle')) if active else 'idle'


def _render_research_payload_v602(snapshot, label='Research results', download_key='research_download_v602'):
    if not snapshot or not snapshot.get('payload'):
        return
    payload = snapshot['payload']
    partial = bool(payload.get('partial'))
    cfg = snapshot.get('config', {})
    status_text = 'PARTIAL — stopped' if partial else 'COMPLETED'
    st.caption(
        f"{label} • {status_text} • {snapshot.get('completed', 0)}/{snapshot.get('total', len(cfg.get('tickers', [])))} tickers"
        + (f" • {snapshot.get('completed_label')}" if snapshot.get('completed_label') else '')
    )
    if payload.get('excel'):
        suffix = 'PARTIAL' if partial else 'Research151'
        st.download_button(
            '⬇️ Download Research to Excel' + (' (partial)' if partial else ''),
            data=payload['excel'],
            file_name=f"AI_Stock_Hunter_V{APP_VERSION}_{suffix}_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
            mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            use_container_width=True,
            key=download_key,
        )
    summary = payload.get('summary', pd.DataFrame())
    if isinstance(summary, pd.DataFrame) and not summary.empty:
        st.dataframe(summary, use_container_width=True, hide_index=True)
        st.metric('Stocks with qualified adaptive setup', f"{len(summary)}/{snapshot.get('total', len(cfg.get('tickers', [])))}")
    else:
        st.warning('No setup passed the minimum-sample/fold filters in the completed portion of this run.')
    premove = payload.get('premove', pd.DataFrame())
    topk = payload.get('topk', pd.DataFrame())
    if isinstance(premove, pd.DataFrame) and not premove.empty:
        st.markdown('#### Pre-Move Study')
        st.dataframe(premove.head(200), use_container_width=True, hide_index=True)
    if isinstance(topk, pd.DataFrame) and not topk.empty:
        st.markdown('#### Top-K Validation')
        st.dataframe(topk, use_container_width=True, hide_index=True)
    skipped = payload.get('skipped', pd.DataFrame())
    if isinstance(skipped, pd.DataFrame) and not skipped.empty:
        with st.expander(f"Skipped / error details ({len(skipped)})"):
            st.dataframe(skipped, use_container_width=True, hide_index=True)


def _render_research_status_v602():
    runtime = _research_runtime_v602()
    with runtime['lock']:
        active = dict(runtime.get('active') or {})
        last_completed = runtime.get('last_completed')
    status = active.get('status', 'idle')
    if status in ('running', 'stopping'):
        pct = int(active.get('progress', 0))
        completed = int(active.get('completed', 0)); total = int(active.get('total', 0))
        phase = active.get('phase', 'Researching')
        ticker = active.get('ticker', '—'); market = active.get('market', '—')
        st.progress(pct / 100.0, text=f"{phase} • {ticker} • {completed}/{total} ({pct}%)")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric('Status', 'STOPPING' if status == 'stopping' else 'RUNNING')
        c2.metric('Current', f"{ticker} · {market}")
        c3.metric('Elapsed', _fmt_seconds(active.get('elapsed', 0)))
        c4.metric('ETA', '—' if status == 'stopping' or active.get('eta') is None else _fmt_seconds(active.get('eta')))
        st.info('Research is running server-side. You can switch to another app or tab and return later; the job continues while the Streamlit server process remains alive.')
        if last_completed:
            with st.expander('Last completed Research', expanded=False):
                _render_research_payload_v602(last_completed, 'Last completed Research', 'research_download_last_v602')
    elif status == 'completed':
        st.success(f"Research complete • {active.get('completed', 0)}/{active.get('total', 0)} tickers • {_fmt_seconds(active.get('elapsed', 0))}")
        _render_research_payload_v602(active, 'Current Research', 'research_download_current_v602')
    elif status == 'stopped':
        st.warning(f"Research stopped safely after {active.get('completed', 0)}/{active.get('total', 0)} tickers. Completed work is kept as a partial result.")
        if active.get('payload'):
            _render_research_payload_v602(active, 'Partial Research', 'research_download_partial_v602')
    elif status == 'failed':
        st.error('Research failed: ' + str(active.get('error', 'Unknown error')))
        if last_completed:
            with st.expander('Last completed Research', expanded=True):
                _render_research_payload_v602(last_completed, 'Last completed Research', 'research_download_failed_last_v602')
    elif last_completed:
        _render_research_payload_v602(last_completed, 'Last completed Research', 'research_download_idle_last_v602')


if hasattr(st, 'fragment'):
    @st.fragment(run_every='1s')
    def _research_live_fragment_v602():
        _render_research_status_v602()
        if _research_status_v602() not in ('running', 'stopping'):
            try:
                st.rerun(scope='app')
            except TypeError:
                st.rerun()
else:
    def _research_live_fragment_v602():
        _render_research_status_v602()




# -----------------------------------------------------------------------------
# V6.0.3 unified server-side Lab jobs
# Backtest / Validate / Entry / Explosive / Feedback use the same cooperative
# background model as Scanner + Research. Jobs continue if the phone/browser is
# backgrounded while the Streamlit server stays alive. Stop is cooperative.
# -----------------------------------------------------------------------------
class _LabCancelled(Exception):
    pass


@st.cache_resource(show_spinner=False)
def _lab_runtimes_v603(build_id):
    # Key the in-memory Lab runtime by build so hot-reloads cannot reuse payloads
    # created by an older app structure. This prevents stale-object AttributeErrors
    # after deploys while preserving server-side background jobs within the same build.
    names=('analyze','backtest','validate','entry','explosive','feedback','research_validator','pre_move','historical_replay','explosive_benchmark','explosive_universe','regular_signature')
    return {name:{'lock':threading.RLock(),'executor':None,'active':None,'last_completed':None} for name in names}


def _lab_runtime_v603(name):
    # V6.2.6: tolerate newly-added Lab names even if a future UI block is added
    # before the static registry tuple is updated. This prevents a page-level
    # KeyError such as the V6.2.5 Pre-Move runtime crash.
    runtimes=_lab_runtimes_v603(APP_BUILD_ID)
    if name not in runtimes:
        runtimes[name]={'lock':threading.RLock(),'executor':None,'active':None,'last_completed':None}
    return runtimes[name]


def _lab_check_v603(runtime,job_id):
    with runtime['lock']:
        j=runtime.get('active')
        if not j or j.get('id')!=job_id or j.get('cancel_requested') or j.get('status') in ('stopping','stopped'):
            raise _LabCancelled()


def _lab_update_v603(runtime,job_id,completed,total,item='—',phase='Running',progress_override=None,eta_override=None,eta_unknown=False):
    now=time_module.time()
    with runtime['lock']:
        j=runtime.get('active')
        if not j or j.get('id')!=job_id: raise _LabCancelled()
        j.update({'completed':int(completed),'total':int(total),'item':str(item),'phase':str(phase)})
        if progress_override is None:
            j['progress']=int(np.clip(100*completed/max(1,total),0,99 if completed<total else 100))
        else:
            j['progress']=int(np.clip(float(progress_override),0,100))
        elapsed=now-float(j.get('started_at',now)); j['elapsed']=elapsed
        if eta_unknown:j['eta']=None
        elif eta_override is not None:j['eta']=max(0,float(eta_override))
        else:j['eta']=max(0,(total-completed)*(elapsed/max(1,completed))) if completed else None


def _lab_publish_v603(runtime,job_id,payload,status='completed'):
    finished=time_module.time()
    with runtime['lock']:
        j=runtime.get('active')
        if not j or j.get('id')!=job_id:return
        _il_now=datetime.now(ZoneInfo('Asia/Jerusalem'));snap={**j,'status':status,'payload':payload,'finished_at':finished,'duration':finished-float(j.get('started_at',finished)),'completed_label':_il_now.strftime('%Y-%m-%d %H:%M:%S'),'completed_label_israel':_il_now.strftime('%d/%m/%Y %H:%M:%S')}
        if status=='completed':runtime['last_completed']=snap
        j.update(snap)
        j['progress']=100 if status=='completed' else j.get('progress',0)
        j['eta']=0


def _lab_fail_v603(runtime,job_id,e):
    finished=time_module.time()
    with runtime['lock']:
        j=runtime.get('active')
        if j and j.get('id')==job_id:
            j.update({'status':'failed','error':f'{type(e).__name__}: {e}','finished_at':finished,'elapsed':finished-float(j.get('started_at',finished)),'eta':0,'phase':'Failed'})


def _start_lab_v603(name,worker,config,total=1):
    runtime=_lab_runtime_v603(name)
    with runtime['lock']:
        a=runtime.get('active')
        if a and a.get('status') in ('running','stopping'):return False,f'{name.title()} is already running.'
        if runtime.get('executor') is None:
            runtime['executor']=ThreadPoolExecutor(max_workers=1,thread_name_prefix=f'stock-hunter-{name}')
        jid=f'{name}-{int(time_module.time()*1000)}'
        runtime['active']={'id':jid,'status':'running','progress':0,'completed':0,'total':int(total),'item':'—','phase':'Starting','started_at':time_module.time(),'elapsed':0,'eta':None,'config':config,'cancel_requested':False}
        runtime['executor'].submit(worker,runtime,jid,config)
    return True,jid


def _stop_lab_v603(name):
    runtime=_lab_runtime_v603(name)
    with runtime['lock']:
        a=runtime.get('active')
        if not a or a.get('status') not in ('running','stopping'):return False,f'No {name} job is running.'
        if a.get('status')=='stopping':return True,'Stop already requested.'
        a['cancel_requested']=True;a['status']='stopping';a['phase']='Stop requested — finishing current safe step';a['eta']=0
        return True,'Stop requested. The current safe calculation/data step will finish first.'


def _lab_snapshot_v603(name):
    runtime=_lab_runtime_v603(name)
    with runtime['lock']:
        a=dict(runtime['active']) if runtime.get('active') else None
        last=dict(runtime['last_completed']) if runtime.get('last_completed') else None
    return a,last


def _render_lab_status_v603(name):
    a,last=_lab_snapshot_v603(name)
    if a and a.get('status') in ('running','stopping'):
        status='STOPPING' if a.get('status')=='stopping' else 'RUNNING'
        st.progress(int(a.get('progress',0)),text=f"{status} • {a.get('phase','')} • {a.get('item','—')} • {a.get('completed',0)}/{a.get('total',0)}")
        c1,c2,c3=st.columns(3);c1.metric('Elapsed',_fmt_seconds(a.get('elapsed',0)));c2.metric('ETA',_fmt_seconds(a.get('eta')) if a.get('eta') is not None else '—');c3.metric('Progress',f"{a.get('progress',0)}%")
        st.caption('Server-side background run: you can switch apps/tabs and return later. A Streamlit host restart/sleep can still end an in-memory job.')
    elif a and a.get('status')=='failed':
        st.error('Run failed: '+str(a.get('error','Unknown error')))
    elif a and a.get('status')=='stopped':
        st.warning(f"Run stopped safely • {a.get('completed',0)}/{a.get('total',0)} steps completed")
    elif a and a.get('status')=='completed':
        if name=='analyze':
            _ct=a.get('completed_label_israel',a.get('completed_label','—'))
            st.markdown(f"<div class='analyze-complete-il'>✅ COMPLETED • Israel time {_e6395(_ct)} • {_fmt_seconds(a.get('duration',a.get('elapsed',0)))}</div>",unsafe_allow_html=True)
        else:st.success(f"Run completed • {_fmt_seconds(a.get('duration',a.get('elapsed',0)))}")
    elif last:
        if name=='analyze':
            _ct=last.get('completed_label_israel',last.get('completed_label','—'))
            st.markdown(f"<div class='analyze-complete-il'>✅ LAST COMPLETED • Israel time {_e6395(_ct)} • {_fmt_seconds(last.get('duration',0))}</div>",unsafe_allow_html=True)
        else:st.caption(f"Last completed run • {last.get('completed_label','—')} • {_fmt_seconds(last.get('duration',0))}")


if hasattr(st,'fragment'):
    @st.fragment(run_every=1.0)
    def _lab_live_fragment_v603(name):
        _render_lab_status_v603(name)
        a,_=_lab_snapshot_v603(name)
        if not a or a.get('status') not in ('running','stopping'):
            try:st.rerun(scope='app')
            except TypeError:st.rerun()
else:
    def _lab_live_fragment_v603(name):
        _render_lab_status_v603(name)


def _analyze_worker_v603(runtime,jid,cfg):
    try:
        t=cfg['ticker'];hist=cfg['history'];horizon=int(cfg['horizon']);target=float(cfg['target'])
        _lab_update_v603(runtime,jid,0,8,t,'Downloading daily history')
        d=fetch_ohlcv(t,hist,'1d');_lab_check_v603(runtime,jid)
        if d is None or len(d)<35:raise ValueError('Not enough market data.')

        _lab_update_v603(runtime,jid,1,8,t,'Current-session 1m/5m price + corporate action check')
        live_snapshot=fetch_live_intraday_snapshot(t,d);_lab_check_v603(runtime,jid)

        _lab_update_v603(runtime,jid,2,8,t,'Confirmed 1H / 15m + split normalization')
        h=confirmed_intraday_bars(fetch_ohlcv(t,'1mo','1h'));m15=confirmed_intraday_bars(fetch_ohlcv(t,'60d','15m'))
        _an_daily_recon={'used':False,'source':'PROVIDER DAILY','status':'NO RECONSTRUCTION','bars':0}
        try:
            d,_an_daily_recon=_reconstruct_completed_daily_from_intraday_v63924(t,d,_market_for_ticker_v612(t),intraday=m15)
        except Exception:
            pass
        # V6.0.5 hard gate: a stale/prior-session quote is NEVER a normalization anchor.
        safe_anchor=live_snapshot.get('price',np.nan) if bool(live_snapshot.get('anchor_eligible')) and not bool(live_snapshot.get('scale_suspect')) else np.nan
        d,h,m15,ca_report=normalize_cross_timeframes(
            d,h,m15,
            anchor_price=safe_anchor,
            split_ratio=live_snapshot.get('split_ratio',np.nan),
            split_date=live_snapshot.get('split_date'),
        );_lab_check_v603(runtime,jid)
        if live_snapshot.get('split_detected'):
            ca_report=dict(ca_report);ca_report['split_detected']=True
            ca_report['split_ratio']=live_snapshot.get('split_ratio',np.nan);ca_report['split_date']=live_snapshot.get('split_date')
        _phase_detail=_market_status_detail_v612(_market_for_ticker_v612(t))
        phase_now=_phase_detail.get('phase','UNKNOWN')
        _market_date=_phase_detail.get('local_date')
        live_snapshot=resolve_current_market_snapshot(t,d,h,m15,live_snapshot,market_open=(phase_now=='OPEN'),market_phase=phase_now,market_date=_market_date)
        _an_market=_market_for_ticker_v612(t)
        _session_fresh=_session_freshness_v63915(d,_an_market)
        _session_data_fresh=bool(_session_fresh.get('ok',False))
        # During an OPEN local cash session the provider's daily endpoint may lag
        # the live/intraday stream. A verified same-session 15m/1H bar is allowed
        # to establish freshness; a prior-session daily candle is not.
        if phase_now=='OPEN' and not _session_data_fresh:
            _expected=_session_fresh.get('expected')
            for _ifr,_src in ((m15,'15M SAME-SESSION'),(h,'1H SAME-SESSION')):
                try:_ild=_frame_latest_session_date_v63915(_ifr,_an_market)
                except Exception:_ild=None
                if _expected is not None and _ild==_expected:
                    _session_data_fresh=True;_session_fresh=dict(_session_fresh);_session_fresh['ok']=True;_session_fresh['latest']=_ild;_session_fresh['status']=f'CURRENT THROUGH {_ild} • VERIFIED {_src}';break
        if phase_now=='OPEN' and not _session_data_fresh and bool(live_snapshot.get('trade_fresh',False)):
            try:_ld=pd.to_datetime(live_snapshot.get('analysis_session_date') or live_snapshot.get('price_session_date')).date()
            except Exception:_ld=None
            if _session_fresh.get('expected') is not None and _ld==_session_fresh.get('expected'):
                _session_data_fresh=True;_session_fresh=dict(_session_fresh);_session_fresh['ok']=True;_session_fresh['latest']=_ld;_session_fresh['status']=f'CURRENT THROUGH {_ld} • VERIFIED LIVE QUOTE'
        if bool((_an_daily_recon or {}).get('used')) and _session_data_fresh:
            _session_fresh=dict(_session_fresh);_session_fresh['status']=str(_an_daily_recon.get('status') or _session_fresh.get('status'))
        live_snapshot=dict(live_snapshot)
        live_snapshot['session_data_fresh']=_session_data_fresh
        live_snapshot['price_session_date']=str(_session_fresh.get('latest')) if _session_fresh.get('latest') else None
        live_snapshot['expected_session_date']=str(_session_fresh.get('expected')) if _session_fresh.get('expected') else None
        live_snapshot['freshness_status']=_session_fresh.get('status','UNRESOLVED')
        live_snapshot['session_reconstructed']=bool((_an_daily_recon or {}).get('used'))
        live_snapshot['session_reconstruction_source']=str((_an_daily_recon or {}).get('source','PROVIDER DAILY'))
        if not _session_data_fresh:
            ca_report=dict(ca_report);ca_report['data_quality']='STALE_SESSION'
            ca_report.setdefault('details',[])
            ca_report['details']=list(ca_report.get('details') or [])+[str(_session_fresh.get('status','STALE SESSION'))]
        # V6.1.4 AH-aware: keep extended-hours price/volume separate from regular-session
        # indicators. The AH snapshot can affect chase/extension risk, but it cannot by
        # itself turn regular-session technicals into an ActionableNow entry.
        ah_snapshot={}
        if phase_now=='AFTER-MARKET' and _market_for_ticker_v612(t) in ('NASDAQ','NYSE','US'):
            try: ah_snapshot=fetch_aftermarket_snapshots([t]).get(str(t).upper(),{}) or {}
            except Exception: ah_snapshot={}
            # Yahoo's 5m prepost endpoint occasionally omits AH rows even when the
            # fresher 1m/current-session quote is valid. In that case use the live
            # quote only for AH price/change context; volume strength stays unavailable.
            if not np.isfinite(float(ah_snapshot.get('AHPrice',np.nan))):
                try:
                    _lp=float(live_snapshot.get('price',np.nan)); _rc=float(live_snapshot.get('fallback_price',np.nan))
                except Exception:
                    _lp=_rc=np.nan
                if bool(live_snapshot.get('display_current')) and bool(live_snapshot.get('trade_fresh')) and np.isfinite(_lp) and np.isfinite(_rc) and _rc>0:
                    ah_snapshot={
                        'AHPrice':_lp,'RegularClose':_rc,'AHChangePct':(_lp/_rc-1.0)*100.0,
                        'AHVolume':np.nan,'AHVolumeStrength':np.nan,'AHData':'LIVE QUOTE FALLBACK',
                        'AHLastTime':live_snapshot.get('timestamp_label','—'),'AHAgeMinutes':live_snapshot.get('age_minutes',np.nan),
                        'AHFresh':True,'AHPriceSource':str(live_snapshot.get('source','live quote fallback'))
                    }
            elif ah_snapshot:
                ah_snapshot['AHPriceSource']=ah_snapshot.get('AHData','REAL 5M')

        _lab_update_v603(runtime,jid,3,8,t,'Quant + Early features on normalized data')
        f=compute_features(d);latest=score_latest(f,0);dyn=dynamic_scores(f,target/100,0);_lab_check_v603(runtime,jid)
        _liq_profile=_liquidity_profile_v63964(f,t)
        hfeat=compute_features(h,True) if h is not None and len(h)>=30 else None;m15feat=compute_features(m15,True) if m15 is not None and len(m15)>=30 else None
        hs=he=np.nan
        if hfeat is not None:
            hl=score_latest(hfeat,0);hs=hl['score'];he=hl['early_score']
        qscore=latest['score'] if not np.isfinite(hs) else .78*latest['score']+.22*hs;escore=latest['early_score'] if not np.isfinite(he) else .70*latest['early_score']+.30*he

        _lab_update_v603(runtime,jid,4,8,t,'Historical evidence')
        auto_threshold,auto_table=_auto_backtest_threshold(f,horizon,target/100);buy_threshold=int(auto_threshold);bt=normalize_backtest_confidence(backtest_signal(f,horizon,target/100,buy_threshold,0));cmp=compare_static_dynamic_backtest(f,horizon,target/100,buy_threshold,0);sb,db=cmp.get('static',{}),cmp.get('dynamic',{});analysis_conf=float(dyn.get('early_calibration',{}).get('confidence',0)+dyn.get('quant_calibration',{}).get('confidence',0))/2.0;_lab_check_v603(runtime,jid)

        _lab_update_v603(runtime,jid,5,8,t,'Entry + live timing')
        _ah_price=float(ah_snapshot.get('AHPrice',np.nan)) if np.isfinite(float(ah_snapshot.get('AHPrice',np.nan))) else np.nan
        _live_price=float(live_snapshot.get('price',np.nan)) if bool(live_snapshot.get('display_current')) and np.isfinite(float(live_snapshot.get('price',np.nan))) else np.nan
        current_entry_price=_ah_price if phase_now=='AFTER-MARKET' and np.isfinite(_ah_price) else _live_price
        _regular_close=float(ah_snapshot.get('RegularClose',np.nan)) if np.isfinite(float(ah_snapshot.get('RegularClose',np.nan))) else float(live_snapshot.get('fallback_price',np.nan)) if np.isfinite(float(live_snapshot.get('fallback_price',np.nan))) else np.nan
        regular_ent=None
        if phase_now=='AFTER-MARKET' and np.isfinite(_regular_close):
            regular_ent=entry_timing(f,qscore,escore,hourly_feat=hfeat,m15_feat=m15feat,current_price=_regular_close,market_regime=_market_regime_v610(t),previous_close=live_snapshot.get('prev_close',np.nan),market_phase=phase_now,market_date=_market_date)
        ent=entry_timing(f,qscore,escore,hourly_feat=hfeat,m15_feat=m15feat,current_price=current_entry_price,market_regime=_market_regime_v610(t),previous_close=live_snapshot.get('prev_close',np.nan),market_phase=phase_now,market_date=_market_date)
        ent=dict(ent)
        # Analyze stays on Production Daily/Core logic, but V6.3.9.46 promotes
        # proven 1Y Hourly OOS timing automatically when available.
        active_model=_select_promoted_hourly_model_v63945(_load_model_registry_v613(),3.0)
        if _active_model_has_any_v63945(active_model):
            ent,(hopt_score,hopt_match,hopt_status,hopt_horizon)=_apply_hourly_oos_entry_v63945(ent,t,hfeat,active_model)
            if regular_ent is not None:
                regular_ent,_=_apply_hourly_oos_entry_v63945(regular_ent,t,hfeat,active_model)
        else:
            hopt_score,hopt_match,hopt_status,hopt_horizon=np.nan,np.nan,'NO ELIGIBLE HOURLY MODEL','—'
        ca_report,ent=_split_plan_integrity_guard_v63949(ca_report,ent,current_entry_price,live_snapshot.get('split_ratio',np.nan),t)
        if regular_ent is not None:
            _,regular_ent=_split_plan_integrity_guard_v63949(dict(ca_report),regular_ent,_regular_close,live_snapshot.get('split_ratio',np.nan),t)
        _prev_close=float(live_snapshot.get('prev_close',np.nan)) if np.isfinite(float(live_snapshot.get('prev_close',np.nan))) else np.nan
        _ah_change=float(ah_snapshot.get('AHChangePct',np.nan)) if np.isfinite(float(ah_snapshot.get('AHChangePct',np.nan))) else np.nan
        _regular_move=((_regular_close/_prev_close)-1.0)*100.0 if np.isfinite(_regular_close) and np.isfinite(_prev_close) and _prev_close>0 else np.nan
        _total_extended=((current_entry_price/_prev_close)-1.0)*100.0 if phase_now=='AFTER-MARKET' and np.isfinite(current_entry_price) and np.isfinite(_prev_close) and _prev_close>0 else np.nan
        ent['market_phase']=phase_now; ent['regular_session_close']=_regular_close; ent['regular_session_move_pct']=_regular_move
        ent['after_hours_price']=_ah_price; ent['after_hours_move_pct']=_ah_change; ent['after_hours_volume_strength']=ah_snapshot.get('AHVolumeStrength',np.nan); ent['after_hours_fresh']=bool(ah_snapshot.get('AHFresh',False)); ent['after_hours_price_source']=ah_snapshot.get('AHPriceSource',ah_snapshot.get('AHData','N/A')); ent['total_move_including_ah_pct']=_total_extended
        ent['regular_session_entry_state']=(regular_ent or {}).get('trigger_state',(regular_ent or {}).get('status',ent.get('trigger_state',ent.get('status','WAIT'))))
        ent['regular_session_entry_score']=(regular_ent or {}).get('entry_score',ent.get('entry_score',np.nan))
        ent['regular_session_chase_risk_score']=(regular_ent or {}).get('chase_risk_score',ent.get('chase_risk_score',np.nan))
        if phase_now=='AFTER-MARKET':
            if not bool(ent.get('extension_guard_ok',True)) or ent.get('trigger_state')=='EXTENDED — DO NOT CHASE':
                ent['session_entry_state']='EXTENDED — DO NOT CHASE'
                ent['recommended_action']='WAIT FOR RETEST • RECONFIRM NEXT REGULAR SESSION'
            elif ent.get('trigger_state')=='CONFIRMED ENTRY':
                ent['session_entry_state']='AFTER-MARKET SETUP — RECONFIRM NEXT SESSION'
                ent['recommended_action']='AFTER-MARKET REVIEW • RECONFIRM IN REGULAR SESSION'
            else:
                ent['session_entry_state']='AFTER-MARKET REVIEW — '+str(ent.get('trigger_state',ent.get('status','WAIT')))
                if not ent.get('recommended_action'): ent['recommended_action']='RECONFIRM IN NEXT REGULAR SESSION'
        else:
            ent['session_entry_state']=ent.get('trigger_state',ent.get('status','WAIT'))
        if str(ca_report.get('data_quality','OK'))!='OK':
            # Safety invariant: a cross-timeframe mismatch suppresses the plan AND
            # any live/OOS promotion.  This mirrors Scanner behavior so Analyze
            # cannot show ARMED/CONFIRMED after the plan has been invalidated.
            ent=dict(ent);ent.update({
                'plan_valid':False,
                'plan_reason':'Blocked by cross-timeframe data-quality gate',
                'zone_low':np.nan,'zone_high':np.nan,'trigger':np.nan,
                'invalidation':np.nan,'target1':np.nan,'target2':np.nan,
                'setup_confirmed':False,'confirmed_entry_gate_ok':False,
                'price_actionable_now':False,'rr_actionable':False,
                'status':'WAIT','trigger_state':'WAIT','session_entry_state':'WAIT',
                'recommended_action':'WAIT — DATA QUALITY BLOCK'
            })
        daily_lr=f.dropna(subset=['Close']).iloc[-1];live_f=f.copy()
        if hfeat is not None and len(hfeat):
            try:
                rv=float(hfeat.iloc[-1].get('time_adjusted_rvol',np.nan))
                if np.isfinite(rv):live_f.loc[live_f.index[-1],'robust_volume_ratio']=rv;live_f.loc[live_f.index[-1],'volume_ratio']=rv
            except Exception:pass
        latest_live=score_latest(live_f,0)
        # V6.0.7: display the best current/delayed quote found by the fallback chain,
        # while keeping LIVE confirmation gated by the stricter trade_fresh flag.
        lp=float(live_snapshot.get('price',np.nan)) if bool(live_snapshot.get('display_current')) and np.isfinite(float(live_snapshot.get('price',np.nan))) else np.nan
        fallback_lp=float(live_snapshot.get('fallback_price',np.nan)) if np.isfinite(float(live_snapshot.get('fallback_price',np.nan))) else float(daily_lr.get('Close',np.nan))
        if phase_now=='AFTER-MARKET' and np.isfinite(_ah_price): latest_live['price']=_ah_price
        elif np.isfinite(lp): latest_live['price']=lp
        elif np.isfinite(fallback_lp): latest_live['price']=fallback_lp
        fresh_change=bool(live_snapshot.get('display_current')) or phase_now!='OPEN'
        if phase_now=='AFTER-MARKET' and np.isfinite(_total_extended):
            latest_live['daily_change_pct']=_total_extended
        elif fresh_change and np.isfinite(float(live_snapshot.get('change_pct',np.nan))):
            latest_live['daily_change_pct']=float(live_snapshot.get('change_pct'))
        elif phase_now=='OPEN':
            latest_live['daily_change_pct']=np.nan
        ex=explosive_latest(live_f,hfeat) if callable(explosive_latest) else {};timing=signal_timing_latest(live_f,hfeat) if callable(signal_timing_latest) else {}
        row=pd.DataFrame([{'Ticker':t,'Prediction':dyn.get('final_prediction',0),'EntryScore':ent.get('entry_score',0),'LiveActionabilityScore':ent.get('live_actionability_score',ent.get('entry_score',0)),'SetupEntryScore':ent.get('setup_entry_score_pre_chase',ent.get('entry_score',0)),'EntryStatus':ent.get('status','WAIT'),'EntryTriggerState':ent.get('trigger_state',ent.get('status','WAIT')),'SessionEntryState':ent.get('session_entry_state',ent.get('trigger_state',ent.get('status','WAIT'))),'RegularSessionEntryState':ent.get('regular_session_entry_state',ent.get('trigger_state',ent.get('status','WAIT'))),'RegularSessionClose':ent.get('regular_session_close',np.nan),'RegularSessionMovePct':ent.get('regular_session_move_pct',np.nan),'AfterHoursPrice':ent.get('after_hours_price',np.nan),'AfterHoursMovePct':ent.get('after_hours_move_pct',np.nan),'AfterHoursVolumeStrength':ent.get('after_hours_volume_strength',np.nan),'AfterHoursFresh':ent.get('after_hours_fresh',False),'TotalMoveIncludingAHPct':ent.get('total_move_including_ah_pct',np.nan),'EntryConfirmationPct':ent.get('confirmation_pct',0),'DailySetupCheck':ent.get('daily_setup',False),'FreshSignalCheck':ent.get('fresh_signal',False),'HourlyEntryCheck':ent.get('hourly_entry_ok',False),'VolumeFlowCheck':ent.get('volume_flow_ok',False),'NoChaseCheck':ent.get('no_chase',False),'ExtensionGuardCheck':ent.get('extension_guard_ok',True),'ChaseRiskScore':ent.get('chase_risk_score',0),'ChaseRiskLabel':ent.get('chase_risk_label','LOW'),'SessionMovePct':ent.get('session_move_pct',np.nan),'SessionMoveATR':ent.get('session_move_atr',np.nan),'SessionMovePercentile':ent.get('session_move_percentile',np.nan),'SinceTriggerPct':ent.get('since_trigger_pct',np.nan),'GapPct':ent.get('gap_pct',np.nan),'VWAPDistanceATR':ent.get('vwap_distance_atr',np.nan),'EMA9DistanceATR':ent.get('ema9_distance_atr',np.nan),'EMA20DistanceATR':ent.get('ema20_distance_atr',np.nan),'Target1ProgressPct':ent.get('target1_progress_pct',np.nan),'LiveRR_T1':ent.get('live_rr_t1',np.nan),'LiveRR_T2':ent.get('live_rr_t2',np.nan),'LiveRRGuardOK':ent.get('live_rr_guard_ok',True),'CarryoverExtension':ent.get('carryover_extension',False),'CarryoverHardVeto':ent.get('carryover_hard_veto',False),'PriorSessionMovePct':ent.get('prior_session_move_pct',np.nan),'CarryoverRetentionPct':ent.get('carryover_retention_pct',np.nan),'MoveConsumedBeforeTriggerPct':ent.get('move_consumed_before_trigger_pct',np.nan),'PreBreakoutAccumulationScore':ent.get('pre_breakout_accumulation_score',0.0),'PreBreakoutAccumulationStage':ent.get('pre_breakout_accumulation_stage','NO CURRENT ACCUMULATION SETUP'),'PreBreakoutAccumulationReason':ent.get('pre_breakout_accumulation_reason',''),'PreMoveConfirmed':ent.get('pre_move_confirmed',False),'PreMoveConfidenceTier':ent.get('pre_move_confidence_tier','NONE'),'PreMoveFamilyCount':ent.get('pre_move_family_count',0),'PreMoveFamilySignature':ent.get('pre_move_family_signature','NONE'),'PreMoveBaselineGuardOK':ent.get('pre_move_baseline_guard_ok',False),'PreMoveBaselineVolume':ent.get('pre_move_baseline_volume',np.nan),'PreMoveBaselineTurnover':ent.get('pre_move_baseline_turnover',np.nan),'EffectiveVolumeShockRatio':ent.get('effective_volume_shock_ratio',np.nan),'PreMoveShockRecoveryOK':ent.get('pre_move_shock_recovery_ok',False),'PreMoveFlowConfirmation':ent.get('pre_move_flow_confirmation',False),'PreMoveMomentumConfirmation':ent.get('pre_move_momentum_confirmation',False),'VolumeRegimeRatio':ent.get('volume_regime_ratio',np.nan),'VolumeShockRatio':ent.get('volume_shock_ratio',np.nan),'VolumeShockDate':ent.get('volume_shock_date','—'),'VolumeShockReturnPct':ent.get('volume_shock_return_pct',np.nan),'AbsorptionCandidate':ent.get('absorption_candidate',False),'VolumePersistenceRatio':ent.get('volume_persistence_ratio',np.nan),'PriceRetentionSinceVolumeShockPct':ent.get('price_retention_since_volume_shock_pct',np.nan),'PreBreakoutHigherLowCount':ent.get('pre_breakout_higher_low_count',0),'PreBreakoutRegimeShift':ent.get('pre_breakout_regime_shift',False),'RecentRunPct':ent.get('recent_run_pct',np.nan),'RecentRunATR':ent.get('recent_run_atr',np.nan),'RecentRunWindow':ent.get('recent_run_window','—'),'RecentRunLabel':ent.get('recent_run_label','NO DATA'),'PostTriggerConsumedPct':ent.get('post_trigger_consumed_pct',np.nan),'PostTriggerConsumedLabel':ent.get('post_trigger_consumed_label','NO DATA'),'RecentRunRetestContext':ent.get('recent_run_retest_context',False),'VolumeTrend':ent.get('volume_trend','NO DATA'),'TriggerAnchorPrice':ent.get('trigger_anchor_price',np.nan),'TriggerAnchorTime':ent.get('trigger_anchor_time','—'),'TriggerAnchorTimeframe':ent.get('trigger_anchor_timeframe','—'),'TriggerAnchorQuality':ent.get('trigger_anchor_quality','NONE'),'TriggerAnchorAgeBars':ent.get('trigger_anchor_age_bars',np.nan),'RetestZoneLow':ent.get('retest_zone_low',np.nan),'RetestZoneHigh':ent.get('retest_zone_high',np.nan),'PullbackNeededPct':ent.get('pullback_needed_pct',np.nan),'RetestStatus':ent.get('retest_status','—'),'RecommendedAction':ent.get('recommended_action',''),'MarketRegime':ent.get('market_regime','NEUTRAL'),'EntryWhyNow':ent.get('why_now',''),'EntryMissingChecks':ent.get('missing_checks',''),'MoveScore':timing.get('move_score',0),'ExplosiveScore':ex.get('score',0),'Accel1D':timing.get('accel_1d',0),'Accel2D':timing.get('accel_2d',0),'Accel3D':timing.get('accel_3d',0),'HourlyConfirm':timing.get('hourly_confirmation',ex.get('hourly_confirmation',0)),'CalibrationConfidence':analysis_conf,'BacktestN':int(db.get('n',0) or 0),'EmpiricalHitRate':(round(float(db.get('hit_rate'))*100,1) if db.get('n',0) and np.isfinite(float(db.get('hit_rate',np.nan))) else np.nan),'SignalLift':(float(cmp.get('signal_lift_dynamic')) if np.isfinite(float(cmp.get('signal_lift_dynamic',np.nan))) else 1.0),'ExitPressure':timing.get('exit_pressure',latest_live.get('exit_pressure',0)),'ExitStage':timing.get('exit_stage',latest_live.get('exit_stage','CLEAR')),'TimingStage':timing.get('timing_stage','—'),'PlanValid':ent.get('plan_valid',False),'EntryLow':ent.get('zone_low'),'EntryHigh':ent.get('zone_high'),'BreakoutTrigger':ent.get('trigger'),'Invalidation':ent.get('invalidation'),'Target1':ent.get('target1'),'Target2':ent.get('target2'),'Price':latest_live.get('price'),'VolumeContext':latest_live.get('volume_context','N/A'),'BullishVolumeEvidence':latest_live.get('bullish_volume_evidence',np.nan),'BearishVolumeEvidence':latest_live.get('bearish_volume_evidence',np.nan),'VolumeAccel':daily_lr.get('vol_accel',np.nan),'InstitutionalFlowScore':latest_live.get('institutional_flow_score',np.nan),'InstitutionalFlowLabel':latest_live.get('institutional_flow_label','NEUTRAL'),'HourlyOptimizedScore':hopt_score,'HourlyOptimizedMatchPct':hopt_match,'HourlyOptimizedStatus':hopt_status,'HourlyOptimizedHorizon':hopt_horizon,'HourlyTimingSource':ent.get('hourly_timing_source','BASE TIMING'),'HourlyOOSTimingScore':ent.get('hourly_entry_score',np.nan),'HourlyOOSModelID':ent.get('hourly_oos_model_id','—'),'HourlyOOSScope':ent.get('hourly_oos_scope','—'),'HourlyOOSFold4Lift':ent.get('hourly_oos_fold4_lift',np.nan),'IntradayCumulativeRVOL':(m15feat.iloc[-1].get('intraday_cum_rvol',np.nan) if m15feat is not None and len(m15feat) else (hfeat.iloc[-1].get('intraday_cum_rvol',np.nan) if hfeat is not None and len(hfeat) else np.nan)),'LiveIntradayRVOL':(hfeat.iloc[-1].get('time_adjusted_rvol',np.nan) if hfeat is not None and len(hfeat) else np.nan),'FullSessionRVOL':daily_lr.get('volume_ratio',np.nan),'DailyRobustRVOL':daily_lr.get('robust_volume_ratio',np.nan),'TimeAdjustedRVOL':(hfeat.iloc[-1].get('time_adjusted_rvol',np.nan) if hfeat is not None and len(hfeat) else daily_lr.get('robust_volume_ratio',np.nan)),'RSI14':latest_live.get('rsi14',np.nan),'SplitAdjusted':ca_report.get('split_adjusted',False),'DataQuality':ca_report.get('data_quality','OK'),'LivePriceFresh':bool(live_snapshot.get('trade_fresh')) if phase_now in ('OPEN','AFTER-MARKET') else False,'SessionDataFresh':_session_data_fresh,'PriceSessionDate':live_snapshot.get('price_session_date'),'ExpectedSessionDate':live_snapshot.get('expected_session_date'),'PriceFreshnessStatus':live_snapshot.get('freshness_status','UNRESOLVED'),'SessionCalendarSource':_session_fresh.get('calendar_source',''),'SessionCalendarReason':_session_fresh.get('calendar_reason',''),'SessionFreshnessVerified':bool(_session_data_fresh)}]);
        for _lk,_lv in _liq_profile.items():row[_lk]=_lv
        row['TimingDataComplete']=bool(ent.get('timing_data_complete',True));row['TimingDataSource']=ent.get('timing_data_source','NOT REQUIRED');row['TimingDataReason']=ent.get('timing_data_reason','');row['SetupOriginPrice']=ent.get('setup_origin_price',np.nan);decision_df=add_market_and_opportunity(row);decision_df=_wire_timing_completeness_v63937(decision_df);decision_df=_apply_optimized_model_v612(decision_df,active_model);decision_df=_decision_intelligence_enrich_v6394(decision_df);decision_df=_apply_decision_ranking_v63919(decision_df,'Production 151');decision_df=_decision_board_enrich_v63948(decision_df);decision_df=_signal_memory_enrich_v63955(decision_df);decision=decision_df.iloc[0].to_dict(); _analyze_feedback=_feedback_store_analyze_v63962(decision_df,horizon,target); ent['evidence_state']=decision.get('EvidenceState','UNPROVEN'); ent['evidence_guard_ok']=bool(decision.get('EvidenceGuardOK',True)); ent['raw_recommended_action']=ent.get('recommended_action',''); ent['recommended_action']=decision.get('RecommendedAction',ent.get('recommended_action','')); _lab_check_v603(runtime,jid)

        _lab_update_v603(runtime,jid,6,8,t,'Walk-forward diagnostics + event study')
        comp=pd.DataFrame(latest['components'],columns=['Component','Points','Max']);comp['Strength %']=(100*comp.Points/comp.Max).round();ec=pd.DataFrame(latest['early_components'],columns=['Component','Points','Max']);ec['Strength %']=(100*ec.Points/ec.Max).round();
        def pct(v):return f'{v*100:.1f}%' if v is not None and np.isfinite(v) else '—'
        def num(v):return f'{v:.2f}x' if v is not None and np.isfinite(v) else '—'
        compare_df=pd.DataFrame([{'Model':'Static','Signals':sb.get('n',0),'Hit Rate':pct(sb.get('hit_rate',np.nan)),'Signal Lift':num(cmp.get('signal_lift_static',np.nan)),'Avg Fwd Return':pct(sb.get('avg_return',np.nan)),'Max Drawdown':pct(sb.get('max_drawdown',np.nan)),'Sample Reliability %':round(sb.get('sample_reliability',0),1)},{'Model':'Dynamic','Signals':db.get('n',0),'Hit Rate':pct(db.get('hit_rate',np.nan)),'Signal Lift':num(cmp.get('signal_lift_dynamic',np.nan)),'Avg Fwd Return':pct(db.get('avg_return',np.nan)),'Max Drawdown':pct(db.get('max_drawdown',np.nan)),'Sample Reliability %':round(db.get('sample_reliability',0),1)}])
        ev=early_event_backtest(f,target/100,(1,2,3),0);early_cal,quant_cal,cal_events=component_calibration(f,target/100,(1,2,3),0);_lab_check_v603(runtime,jid)

        _lab_update_v603(runtime,jid,7,8,t,'Building Analyze workbook')
        summary=pd.DataFrame([{'Ticker':t,'Version':APP_VERSION,'History':hist,'ForecastDays':horizon,'TargetPct':target,'HistoricalQuantThreshold':buy_threshold,'ThresholdMode':'AUTO-RESEARCH','Price':latest_live.get('price'),'LivePrice':live_snapshot.get('price',np.nan),'FallbackOfficialClose':live_snapshot.get('fallback_price',np.nan),'DayChangePct':latest_live.get('daily_change_pct',np.nan),'PriceSource':live_snapshot.get('source'),'PriceTimestamp':live_snapshot.get('timestamp_label'),'PriceFresh':live_snapshot.get('fresh'),'SessionDataFresh':live_snapshot.get('session_data_fresh'),'SessionReconstructed':live_snapshot.get('session_reconstructed',False),'SessionReconstructionSource':live_snapshot.get('session_reconstruction_source','PROVIDER DAILY'),'PriceSessionDate':live_snapshot.get('price_session_date'),'ExpectedSessionDate':live_snapshot.get('expected_session_date'),'PriceFreshnessStatus':live_snapshot.get('freshness_status'),'DisplayCurrent':live_snapshot.get('display_current'),'TradeFresh':live_snapshot.get('trade_fresh'),'QuoteStatus':live_snapshot.get('quote_status'),'ProviderTimestampVerified':live_snapshot.get('provider_timestamp_verified'),'StaleProviderPrice':live_snapshot.get('stale_price',np.nan),'StaleProviderTimestamp':live_snapshot.get('stale_timestamp_label','—'),'PreviousOfficialClose':live_snapshot.get('prev_close'),'AnalysisSessionDate':live_snapshot.get('analysis_session_date'),'PreviousSessionDate':live_snapshot.get('previous_session_date'),'SessionContext':live_snapshot.get('session_context'),'FeedbackSnapshotSaved':bool(_analyze_feedback.get('saved')),'FeedbackSnapshotID':_analyze_feedback.get('snapshot_id'),'FeedbackEventID':_analyze_feedback.get('event_id'),'FeedbackEventRole':_analyze_feedback.get('event_role'),'FeedbackSource':_analyze_feedback.get('source','ANALYZE'),'DecisionBoardStage':decision.get('DecisionBoardStage'),'OriginalSignalTime':decision.get('OriginalSignalTime'),'OriginalSignalStage':decision.get('OriginalSignalStage'),'OriginalSignalPrice':decision.get('OriginalSignalPrice'),'OriginalTriggerPrice':decision.get('OriginalTriggerPrice'),'OriginalTriggerTime':decision.get('OriginalTriggerTime'),'OriginalTarget1':decision.get('OriginalTarget1'),'OriginalInvalidation':decision.get('OriginalInvalidation'),'OriginalProgressToT1Pct':decision.get('OriginalProgressToT1Pct'),'OriginalMoveSinceSignalPct':decision.get('OriginalMoveSinceSignalPct'),'OriginalSignalMemorySource':decision.get('OriginalSignalMemorySource'),'OpportunityWindow':decision.get('OpportunityWindow'),'OpportunityWindowReason':decision.get('OpportunityWindowReason'),'TimingContext':decision.get('TimingContext'),'TriggerTimingDisplay':decision.get('TriggerTimingDisplay'),'DecisionRankScore':decision.get('DecisionRankScore'),'DecisionRankCore':decision.get('DecisionRankCore'),'SetupQualityScore':decision.get('SetupQualityScore'),'EntryTimingScore':decision.get('EntryTimingScore'),'MoneyFlowScore':decision.get('MoneyFlowScore'),'InflowPressure':decision.get('InflowPressure'),'InflowLabel':decision.get('InflowLabel'),'OutflowPressure':decision.get('OutflowPressure'),'OutflowLabel':decision.get('OutflowLabel'),'NetFlowBalance':decision.get('NetFlowBalance'),'NetFlowLabel':decision.get('NetFlowLabel'),'DecisionEvidenceScore':decision.get('DecisionEvidenceScore'),'DecisionRiskScore':decision.get('DecisionRiskScore'),'DecisionRankRiskPenalty':decision.get('DecisionRankRiskPenalty'),'DecisionRankEvidencePenalty':decision.get('DecisionRankEvidencePenalty'),'DecisionRankQualificationCap':decision.get('DecisionRankQualificationCap'),'DecisionRankEligible':decision.get('DecisionRankEligible'),'ValidatedOpportunityEligible':decision.get('ValidatedOpportunityEligible'),'EvidenceValidated':decision.get('EvidenceValidated'),'CurrentOpportunityQualified':decision.get('CurrentOpportunityQualified'),'CurrentOpportunityQualification':decision.get('CurrentOpportunityQualification'),'DecisionRankQualification':decision.get('DecisionRankQualification'),'EvidenceQualification':decision.get('EvidenceQualification'),'TimingQualification':decision.get('TimingQualification'),'DecisionRankModelModifier':decision.get('DecisionRankModelModifier'),'DecisionRankVersion':decision.get('DecisionRankVersion'),'TopScore':decision.get('TopScore'),'OpportunityScore':decision.get('OpportunityScore'),'TradeStage':decision.get('TradeStage'),'MovementStage':decision.get('MovementStage'),'ExitPressure':decision.get('ExitPressure'),'ExitStage':decision.get('ExitStage'),'VolumeContext':latest_live.get('volume_context'),'LiveIntradayRVOL':decision.get('LiveIntradayRVOL'),'DailyRobustRVOL':decision.get('DailyRobustRVOL'),'EvidenceQuality':decision.get('EvidenceQuality'),'EvidenceState':decision.get('EvidenceState'),'EvidenceGuardOK':decision.get('EvidenceGuardOK'),'Reliability':decision.get('Reliability'),'DynamicHoldoutSignals':int(db.get('n',0) or 0),'DynamicHoldoutHitRate':db.get('hit_rate',np.nan),'DynamicHoldoutLift':cmp.get('signal_lift_dynamic',np.nan),'WhyNotTradeTrigger':decision.get('WhyNotTradeTrigger'),'SplitDetected':ca_report.get('split_detected'),'SplitRatio':ca_report.get('split_ratio'),'SplitDate':ca_report.get('split_date'),'SplitAdjusted':ca_report.get('split_adjusted'),'DataQuality':ca_report.get('data_quality'),'DataQualityDetails':' | '.join(ca_report.get('details',[])),'DynamicQuant':dyn.get('dynamic_quant'),'DynamicEarly':dyn.get('dynamic_early'),'PredictionScore':dyn.get('final_prediction'),'EntryScore':ent.get('entry_score'),'LiveActionabilityScore':ent.get('live_actionability_score'),'SetupEntryScore':ent.get('setup_entry_score_pre_chase'),'EntryStatus':ent.get('status'),'SessionEntryState':ent.get('session_entry_state'),'RegularSessionEntryState':ent.get('regular_session_entry_state'),'RegularSessionEntryScore':ent.get('regular_session_entry_score'),'MarketPhase':phase_now,'RegularSessionClose':ent.get('regular_session_close'),'RegularSessionMovePct':ent.get('regular_session_move_pct'),'AfterHoursPrice':ent.get('after_hours_price'),'AfterHoursPriceSource':ent.get('after_hours_price_source'),'AfterHoursMovePct':ent.get('after_hours_move_pct'),'AfterHoursVolumeStrength':ent.get('after_hours_volume_strength'),'AfterHoursFresh':ent.get('after_hours_fresh'),'TotalMoveIncludingAHPct':ent.get('total_move_including_ah_pct'),'ChaseRiskScore':ent.get('chase_risk_score'),'ChaseRiskLabel':ent.get('chase_risk_label'),'ExtensionGuardOK':ent.get('extension_guard_ok'),'SessionMovePct':ent.get('session_move_pct'),'SessionMoveATR':ent.get('session_move_atr'),'SessionMovePercentile':ent.get('session_move_percentile'),'MoveBeforeTriggerPct':ent.get('move_before_trigger_pct'),'SinceCurrentTriggerPct':ent.get('since_trigger_pct'),'GapPct':ent.get('gap_pct'),'VWAPDistanceATR':ent.get('vwap_distance_atr'),'Target1ProgressPct':ent.get('target1_progress_pct'),'LiveRR_T1':ent.get('live_rr_t1'),'LiveRR_T2':ent.get('live_rr_t2'),'LiveRRGuardOK':ent.get('live_rr_guard_ok'),'CarryoverExtension':ent.get('carryover_extension'),'CarryoverHardVeto':ent.get('carryover_hard_veto'),'PriorSessionMovePct':ent.get('prior_session_move_pct'),'PriorSessionMoveATR':ent.get('prior_session_move_atr'),'CarryoverRetentionPct':ent.get('carryover_retention_pct'),'CarryoverSourceSessionDate':ent.get('carryover_source_session_date'),'NextSessionCarryoverCandidate':ent.get('next_session_carryover_candidate'),'NextSessionCarryoverHardCandidate':ent.get('next_session_carryover_hard_candidate'),'NextSessionCarryoverReason':ent.get('next_session_carryover_reason'),'OriginToTriggerPct':ent.get('origin_to_trigger_pct'),'TriggerLagMinutes':ent.get('trigger_lag_minutes'),'TriggerLagATR':ent.get('trigger_lag_atr'),'MoveConsumedBeforeTriggerPct':ent.get('move_consumed_before_trigger_pct'),'PreBreakoutAccumulationScore':ent.get('pre_breakout_accumulation_score'),'PreBreakoutAccumulationStage':ent.get('pre_breakout_accumulation_stage'),'PreBreakoutAccumulationReason':ent.get('pre_breakout_accumulation_reason'),'VolumeRegimeRatio':ent.get('volume_regime_ratio'),'VolumeShockRatio':ent.get('volume_shock_ratio'),'VolumeShockDate':ent.get('volume_shock_date'),'VolumeShockReturnPct':ent.get('volume_shock_return_pct'),'AbsorptionCandidate':ent.get('absorption_candidate'),'VolumePersistenceRatio':ent.get('volume_persistence_ratio'),'PriceRetentionSinceVolumeShockPct':ent.get('price_retention_since_volume_shock_pct'),'PreBreakoutHigherLowCount':ent.get('pre_breakout_higher_low_count'),'PreBreakoutRegimeShift':ent.get('pre_breakout_regime_shift'),'RecentRunPct':ent.get('recent_run_pct'),'RecentRunATR':ent.get('recent_run_atr'),'RecentRunWindow':ent.get('recent_run_window'),'RecentRunLabel':ent.get('recent_run_label'),'PostTriggerConsumedPct':ent.get('post_trigger_consumed_pct'),'PostTriggerConsumedLabel':ent.get('post_trigger_consumed_label'),'RecentRunRetestContext':ent.get('recent_run_retest_context',False),'MoveConsumedBeforeSetupOriginPct':ent.get('move_consumed_before_setup_origin_pct'),'TriggerEfficiencyLabel':ent.get('trigger_efficiency_label'),'TimingConsumedHardBlock':ent.get('timing_consumed_hard_block',False),'TimingDataComplete':ent.get('timing_data_complete',True),'TimingDataSource':ent.get('timing_data_source','NOT REQUIRED'),'TimingDataReason':ent.get('timing_data_reason',''),'VolumeTrend':ent.get('volume_trend'),'VolumeTrend15m':ent.get('volume_trend_15m'),'VolumeTrend1H':ent.get('volume_trend_1h'),'TriggerAnchorPrice':ent.get('trigger_anchor_price'),'TriggerAnchorTime':ent.get('trigger_anchor_time'),'TriggerAnchorBarStartTime':ent.get('trigger_anchor_bar_start_time'),'TriggerAnchorTimeframe':ent.get('trigger_anchor_timeframe'),'TriggerAnchorQuality':ent.get('trigger_anchor_quality'),'TriggerAnchorAgeBars':ent.get('trigger_anchor_age_bars'),'SetupOriginPrice':ent.get('setup_origin_price'),'SetupOriginTime':ent.get('setup_origin_time'),'SetupOriginBarStartTime':ent.get('setup_origin_bar_start_time'),'SetupOriginQuality':ent.get('setup_origin_quality'),'MoveBeforeSetupOriginPct':ent.get('move_before_setup_origin_pct'),'SinceSetupOriginPct':ent.get('since_setup_origin_pct'),'MomentumState':ent.get('momentum_state'),'MomentumState15m':ent.get('momentum_state_15m'),'MomentumState1H':ent.get('momentum_state_1h'),'PostSpikeState':ent.get('post_spike_state'),'SessionPeakPrice':ent.get('session_peak_price'),'SessionPeakMovePct':ent.get('session_peak_move_pct'),'HighGivebackPct':ent.get('high_giveback_pct'),'MoveRetentionFromHighPct':ent.get('move_retention_from_high_pct'),'PostSpikeStructureOK':ent.get('post_spike_structure_ok'),'PostSpikeDistributionRisk':ent.get('post_spike_distribution_risk'),'PostSpikeStructurePrice':ent.get('post_spike_structure_price'),'PostSpikeStructureReference':ent.get('post_spike_structure_reference'),'PostSpikeBearishConfirmBars':ent.get('post_spike_bearish_confirm_bars'),'PostSpikeDistributionScore':ent.get('post_spike_distribution_score'),'ContinuationBaseCandidate':ent.get('continuation_base_candidate'),'ContinuationBaseRawCandidate':ent.get('continuation_base_raw_candidate'),'ContinuationResearchEligible':ent.get('continuation_research_eligible'),'ContinuationInvalidationReason':ent.get('continuation_invalidation_reason'),'ContinuationBaseStatus':ent.get('continuation_base_status'),'ContinuationBaseBars':ent.get('continuation_base_bars'),'ContinuationBaseLow':ent.get('continuation_base_low'),'ContinuationBaseHigh':ent.get('continuation_base_high'),'ContinuationBaseRangePct':ent.get('continuation_base_range_pct'),'ContinuationBaseRangeATR':ent.get('continuation_base_range_atr'),'ContinuationVolumeDryupRatio':ent.get('continuation_volume_dryup_ratio'),'ContinuationBreakoutTrigger':ent.get('continuation_breakout_trigger'),'ContinuationBaseQuality':ent.get('continuation_base_quality'),'ContinuationSessionPeak':ent.get('continuation_session_peak'),'ContinuationBreakoutReference':ent.get('continuation_breakout_reference'),'BreakoutContinuationActionable':ent.get('breakout_continuation_actionable',False),'BreakoutContinuationTrigger':ent.get('breakout_continuation_trigger'),'BreakoutContinuationVolumeOK':ent.get('breakout_continuation_volume_ok',False),'BreakoutContinuationMomentumOK':ent.get('breakout_continuation_momentum_ok',False),'BreakoutContinuationFlowOK':ent.get('breakout_continuation_flow_ok',False),'ContinuationEntryState':ent.get('continuation_entry_state','N/A'),'ContinuationEntryWatch':ent.get('continuation_entry_watch',False),'ContinuationEntryReady':ent.get('continuation_entry_ready',False),'ContinuationEntryReason':ent.get('continuation_entry_reason',''),'ContinuationProgressOK':ent.get('continuation_progress_ok',False),'ContinuationTimingOK':ent.get('continuation_timing_ok',False),'ContinuationRROK':ent.get('continuation_rr_ok',False),'ContinuationMomentumOK':ent.get('continuation_momentum_ok',False),'ContinuationFlowOK':ent.get('continuation_flow_ok',False),'ContinuationVolumeOK':ent.get('continuation_volume_ok',False),'ContinuationDistributionOK':ent.get('continuation_distribution_ok',False),'ContinuationLiveRVOL':ent.get('continuation_live_rvol',np.nan),'ContinuationVolumeState':ent.get('continuation_volume_state','NO DATA'),'ContinuationFadingStrongOverride':ent.get('continuation_fading_strong_override',False),'ContinuationDistributionState':ent.get('continuation_distribution_state','NO DATA'),'ContinuationDistributionSoftOverride':ent.get('continuation_distribution_soft_override',False),'ContinuationBearishDistributionConfirmed':ent.get('continuation_bearish_distribution_confirmed',False),'ContinuationDistanceOK':ent.get('continuation_distance_ok',False),'ContinuationHoldOK':ent.get('continuation_hold_ok'),'RetestZoneLow':ent.get('retest_zone_low'),'RetestZoneHigh':ent.get('retest_zone_high'),'PullbackNeededPct':ent.get('pullback_needed_pct'),'RetestStatus':ent.get('retest_status'),'RecommendedAction':ent.get('recommended_action'),'EntryZoneLow':ent.get('zone_low'),'EntryZoneHigh':ent.get('zone_high'),'BreakoutTrigger':ent.get('trigger'),'Invalidation':ent.get('invalidation'),'Target1':ent.get('target1'),'Target2':ent.get('target2'),'ExplosiveScore':ex.get('score',np.nan),'MoveScore':timing.get('move_score',np.nan),'HourlyConfirmation':timing.get('hourly_confirmation',np.nan),'BacktestSignals':bt.get('n',0),'BacktestHitRate':bt.get('hit_rate',np.nan),'BacktestAvgReturn':bt.get('avg_return',np.nan),'BacktestWorstDrawdown':bt.get('max_drawdown',np.nan)}])
        origin_validation=setup_origin_validation_v619(m15feat,target_pct=.02,stop_pct=.015,max_bars=16) if m15feat is not None else pd.DataFrame()
        origin_validation_summary=setup_origin_validation_summary_v620(origin_validation)
        origin_robustness=setup_origin_robustness_v620(m15feat) if m15feat is not None else pd.DataFrame()
        continuation_validation=continuation_base_validation_v621(m15feat,breakout_lookahead=8,target_pct=.02,stop_pct=.015,outcome_bars=16) if m15feat is not None else pd.DataFrame()
        continuation_validation_summary=continuation_base_validation_summary_v621(continuation_validation)
        origin_matched_baseline=setup_origin_matched_baseline_v622(m15feat,target_pct=.02,stop_pct=.015,max_bars=16) if m15feat is not None else pd.DataFrame()
        origin_matched_confidence=setup_origin_matched_confidence_v623(origin_matched_baseline)
        research_evidence_summary=research_evidence_summary_v622(origin_validation_summary,origin_matched_baseline,origin_robustness,continuation_validation_summary)
        entry_audit=pd.DataFrame([{'Ticker':t,'DecisionBoardStage':decision.get('DecisionBoardStage'),'OpportunityWindow':decision.get('OpportunityWindow'),'OpportunityWindowReason':decision.get('OpportunityWindowReason'),'TimingContext':decision.get('TimingContext'),'TriggerTimingDisplay':decision.get('TriggerTimingDisplay'),'EntryScoreLive':ent.get('entry_score'),'LiveActionabilityScore':ent.get('live_actionability_score'),'SetupEntryScorePreChase':ent.get('setup_entry_score_pre_chase'),'EntryStatus':ent.get('status'),'SessionEntryState':ent.get('session_entry_state'),'RegularSessionEntryState':ent.get('regular_session_entry_state'),'RegularSessionEntryScore':ent.get('regular_session_entry_score'),'MarketPhase':phase_now,'RegularSessionMovePct':ent.get('regular_session_move_pct'),'AfterHoursPrice':ent.get('after_hours_price'),'AfterHoursPriceSource':ent.get('after_hours_price_source'),'AfterHoursMovePct':ent.get('after_hours_move_pct'),'AfterHoursVolumeStrength':ent.get('after_hours_volume_strength'),'TotalMoveIncludingAHPct':ent.get('total_move_including_ah_pct'),'ChaseRiskScore':ent.get('chase_risk_score'),'ChaseRiskLabel':ent.get('chase_risk_label'),'SessionMovePct':ent.get('session_move_pct'),'SessionMoveATR':ent.get('session_move_atr'),'SessionMovePercentile':ent.get('session_move_percentile'),'MoveBeforeTriggerPct':ent.get('move_before_trigger_pct'),'SinceCurrentTriggerPct':ent.get('since_trigger_pct'),'GapPct':ent.get('gap_pct'),'TriggerAnchorPrice':ent.get('trigger_anchor_price'),'TriggerAnchorTime':ent.get('trigger_anchor_time'),'TriggerAnchorBarStartTime':ent.get('trigger_anchor_bar_start_time'),'TriggerAnchorTimeframe':ent.get('trigger_anchor_timeframe'),'TriggerAnchorQuality':ent.get('trigger_anchor_quality'),'TriggerAnchorAgeBars':ent.get('trigger_anchor_age_bars'),'TriggerAnchorSelection':ent.get('trigger_anchor_selection'),'TriggerAnchorSignals':ent.get('trigger_anchor_signals'),'SetupOriginPrice':ent.get('setup_origin_price'),'SetupOriginTime':ent.get('setup_origin_time'),'SetupOriginBarStartTime':ent.get('setup_origin_bar_start_time'),'SetupOriginSignals':ent.get('setup_origin_signals'),'SetupOriginQuality':ent.get('setup_origin_quality'),'MoveBeforeSetupOriginPct':ent.get('move_before_setup_origin_pct'),'SinceSetupOriginPct':ent.get('since_setup_origin_pct'),'MomentumState':ent.get('momentum_state'),'MomentumState15m':ent.get('momentum_state_15m'),'MomentumState1H':ent.get('momentum_state_1h'),'PostSpikeState':ent.get('post_spike_state'),'SessionPeakPrice':ent.get('session_peak_price'),'SessionPeakMovePct':ent.get('session_peak_move_pct'),'HighGivebackPct':ent.get('high_giveback_pct'),'MoveRetentionFromHighPct':ent.get('move_retention_from_high_pct'),'PostSpikeStructureOK':ent.get('post_spike_structure_ok'),'PostSpikeDistributionRisk':ent.get('post_spike_distribution_risk'),'PostSpikeStructurePrice':ent.get('post_spike_structure_price'),'PostSpikeStructureReference':ent.get('post_spike_structure_reference'),'PostSpikeBearishConfirmBars':ent.get('post_spike_bearish_confirm_bars'),'PostSpikeDistributionScore':ent.get('post_spike_distribution_score'),'ContinuationBaseCandidate':ent.get('continuation_base_candidate'),'ContinuationBaseRawCandidate':ent.get('continuation_base_raw_candidate'),'ContinuationResearchEligible':ent.get('continuation_research_eligible'),'ContinuationInvalidationReason':ent.get('continuation_invalidation_reason'),'ContinuationBaseStatus':ent.get('continuation_base_status'),'ContinuationBaseBars':ent.get('continuation_base_bars'),'ContinuationBaseLow':ent.get('continuation_base_low'),'ContinuationBaseHigh':ent.get('continuation_base_high'),'ContinuationBaseRangePct':ent.get('continuation_base_range_pct'),'ContinuationBaseRangeATR':ent.get('continuation_base_range_atr'),'ContinuationVolumeDryupRatio':ent.get('continuation_volume_dryup_ratio'),'ContinuationBreakoutTrigger':ent.get('continuation_breakout_trigger'),'ContinuationBaseQuality':ent.get('continuation_base_quality'),'ContinuationSessionPeak':ent.get('continuation_session_peak'),'ContinuationBreakoutReference':ent.get('continuation_breakout_reference'),'BreakoutContinuationActionable':ent.get('breakout_continuation_actionable',False),'BreakoutContinuationTrigger':ent.get('breakout_continuation_trigger'),'BreakoutContinuationVolumeOK':ent.get('breakout_continuation_volume_ok',False),'BreakoutContinuationMomentumOK':ent.get('breakout_continuation_momentum_ok',False),'BreakoutContinuationFlowOK':ent.get('breakout_continuation_flow_ok',False),'ContinuationEntryState':ent.get('continuation_entry_state','N/A'),'ContinuationEntryWatch':ent.get('continuation_entry_watch',False),'ContinuationEntryReady':ent.get('continuation_entry_ready',False),'ContinuationEntryReason':ent.get('continuation_entry_reason',''),'ContinuationProgressOK':ent.get('continuation_progress_ok',False),'ContinuationTimingOK':ent.get('continuation_timing_ok',False),'ContinuationRROK':ent.get('continuation_rr_ok',False),'ContinuationMomentumOK':ent.get('continuation_momentum_ok',False),'ContinuationFlowOK':ent.get('continuation_flow_ok',False),'ContinuationVolumeOK':ent.get('continuation_volume_ok',False),'ContinuationDistributionOK':ent.get('continuation_distribution_ok',False),'ContinuationDistanceOK':ent.get('continuation_distance_ok',False),'ContinuationHoldOK':ent.get('continuation_hold_ok'),'RetestConfirmationNeeded':ent.get('retest_confirmation_needed'),'VWAPDistanceATR':ent.get('vwap_distance_atr'),'EMA9DistanceATR':ent.get('ema9_distance_atr'),'EMA20DistanceATR':ent.get('ema20_distance_atr'),'Target1ProgressPct':ent.get('target1_progress_pct'),'LiveRR_T1':ent.get('live_rr_t1'),'LiveRR_T2':ent.get('live_rr_t2'),'LiveRRGuardOK':ent.get('live_rr_guard_ok'),'CarryoverExtension':ent.get('carryover_extension'),'CarryoverHardVeto':ent.get('carryover_hard_veto'),'PriorSessionMovePct':ent.get('prior_session_move_pct'),'PriorSessionMoveATR':ent.get('prior_session_move_atr'),'CarryoverRetentionPct':ent.get('carryover_retention_pct'),'NextSessionCarryoverCandidate':ent.get('next_session_carryover_candidate'),'NextSessionCarryoverHardCandidate':ent.get('next_session_carryover_hard_candidate'),'NextSessionCarryoverReason':ent.get('next_session_carryover_reason'),'OriginToTriggerPct':ent.get('origin_to_trigger_pct'),'TriggerLagMinutes':ent.get('trigger_lag_minutes'),'TriggerLagATR':ent.get('trigger_lag_atr'),'MoveConsumedBeforeTriggerPct':ent.get('move_consumed_before_trigger_pct'),'PreBreakoutAccumulationScore':ent.get('pre_breakout_accumulation_score'),'PreBreakoutAccumulationStage':ent.get('pre_breakout_accumulation_stage'),'PreBreakoutAccumulationReason':ent.get('pre_breakout_accumulation_reason'),'VolumeRegimeRatio':ent.get('volume_regime_ratio'),'VolumeShockRatio':ent.get('volume_shock_ratio'),'VolumeShockDate':ent.get('volume_shock_date'),'VolumeShockReturnPct':ent.get('volume_shock_return_pct'),'AbsorptionCandidate':ent.get('absorption_candidate'),'VolumePersistenceRatio':ent.get('volume_persistence_ratio'),'PriceRetentionSinceVolumeShockPct':ent.get('price_retention_since_volume_shock_pct'),'PreBreakoutHigherLowCount':ent.get('pre_breakout_higher_low_count'),'PreBreakoutRegimeShift':ent.get('pre_breakout_regime_shift'),'RecentRunPct':ent.get('recent_run_pct'),'RecentRunATR':ent.get('recent_run_atr'),'RecentRunWindow':ent.get('recent_run_window'),'RecentRunLabel':ent.get('recent_run_label'),'PostTriggerConsumedPct':ent.get('post_trigger_consumed_pct'),'PostTriggerConsumedLabel':ent.get('post_trigger_consumed_label'),'RecentRunRetestContext':ent.get('recent_run_retest_context',False),'MoveConsumedBeforeSetupOriginPct':ent.get('move_consumed_before_setup_origin_pct'),'TriggerEfficiencyLabel':ent.get('trigger_efficiency_label'),'TimingConsumedHardBlock':ent.get('timing_consumed_hard_block',False),'TimingDataComplete':ent.get('timing_data_complete',True),'TimingDataSource':ent.get('timing_data_source','NOT REQUIRED'),'TimingDataReason':ent.get('timing_data_reason',''),'RawNoChaseCheck':ent.get('raw_no_chase',ent.get('no_chase')),'NoChaseCheck':ent.get('no_chase'),'NoChaseConsistencyOverride':ent.get('no_chase_consistency_override',False),'NoChaseReason':ent.get('no_chase_reason',''),'RetestZoneLow':ent.get('retest_zone_low'),'RetestZoneHigh':ent.get('retest_zone_high'),'PullbackNeededPct':ent.get('pullback_needed_pct'),'RetestReference':ent.get('retest_reference'),'RetestReferenceLabel':ent.get('retest_reference_label'),'RetestStatus':ent.get('retest_status'),'RetestEntryLow':ent.get('retest_entry_low'),'RetestEntryHigh':ent.get('retest_entry_high'),'RetestInvalidation':ent.get('retest_invalidation'),'RetestTarget1':ent.get('retest_target1'),'RetestTarget2':ent.get('retest_target2'),'RetestRR_T1':ent.get('retest_rr_t1'),'RetestRR_T2':ent.get('retest_rr_t2'),'RetestPlanValid':ent.get('retest_plan_valid'),'RetestPlanReason':ent.get('retest_plan_reason'),'VolumeTrend':ent.get('volume_trend'),'VolumeTrend15m':ent.get('volume_trend_15m'),'VolumeTrend1H':ent.get('volume_trend_1h'),'EvidenceState':decision.get('EvidenceState'),'EvidenceGuardOK':decision.get('EvidenceGuardOK'),'RawRecommendedAction':ent.get('raw_recommended_action'),'RecommendedAction':ent.get('recommended_action'),'BacktestSignals':bt.get('n',0),'BacktestConfidence':bt.get('confidence',0),'DynamicHoldoutLift':cmp.get('signal_lift_dynamic',np.nan)}]);sheets={'Summary':summary,'Entry Audit':entry_audit,'Historical Quant Threshold Evidence':auto_table,'Quant Components':comp,'Early Components':ec,'Static vs Dynamic':compare_df,'Daily Features':f.reset_index(),'Event Study':ev,'Early Calibration':early_cal,'Quant Calibration':quant_cal,'Setup Origin Validation Summary':origin_validation_summary,'Setup Origin Validation':origin_validation,'Setup Origin Robustness':origin_robustness,'Setup Origin Matched Baseline':origin_matched_baseline,'Setup Origin Matched Confidence':origin_matched_confidence,'Research Evidence Summary':research_evidence_summary,'Continuation Validation Summary':continuation_validation_summary,'Continuation Validation':continuation_validation};
        # V6.3.9.57: keep Scanner and Analyze audit semantics identical.
        _integrity_export_fields=['LiquidityScore','LiquidityLabel','LiquidityHardGateOK','LiquidityBlockReason','AvgDailyTurnover20','AvgDailyTurnover60','MedianDailyTurnover20','MedianDailyTurnover60','LiquidityTurnoverCurrency','LiquidityMinTurnover','LiquidityStableDaysPct','LiquiditySampleDays','ArmedQualified','ArmedQualificationState','ArmedQualificationReason','OriginalSignalId','OriginalMemoryIntegrity','OriginalMemoryStatus','OriginalMemoryAvailable','OriginalTriggerLocked','OriginalEqualsCurrentTrigger','CurrentTriggerPrice','CurrentTriggerTime','CurrentTarget1','CurrentProgressToT1Pct','PreMovePatternStrength','PreMoveActionableNow','PreMoveActionabilityState','PreMoveActionabilityReason','PreMoveRadarEligible','PreMoveRadarRank','PreMoveRadarStatus','PreMoveConfirmed','PreMoveConfidenceTier','PreMoveFamilyCount','PreMoveFamilySignature','PreMoveBaselineGuardOK','EffectiveVolumeShockRatio','PreMoveShockRecoveryOK','PreMoveFlowConfirmation','PreMoveMomentumConfirmation']
        for _k in _integrity_export_fields:
            summary[_k]=decision.get(_k,np.nan);entry_audit[_k]=decision.get(_k,np.nan)
        try:
            _cal=_session_freshness_v63915(d,_market_for_ticker_v612(t))
            _cal_source=_cal.get('calendar_source','');_cal_reason=_cal.get('calendar_reason','')
        except Exception:
            _cal_source=('HKEX LOCAL CASH MARKET (NOT STOCK CONNECT)' if str(_market_for_ticker_v612(t)).upper() in ('HONG KONG','HK') else f'{_market_for_ticker_v612(t)} LOCAL EXCHANGE CALENDAR');_cal_reason='LOCAL CASH-MARKET HOLIDAYS ONLY'
        for _dfx in (summary,entry_audit):
            _dfx['SessionCalendarSource']=decision.get('SessionCalendarSource',_cal_source);_dfx['SessionCalendarReason']=decision.get('SessionCalendarReason',_cal_reason);_dfx['SessionFreshnessVerified']=bool(decision.get('SessionFreshnessVerified',decision.get('SessionDataFresh',False)))
        if hfeat is not None and len(hfeat):sheets['Hourly Features']=hfeat.tail(260).reset_index()
        if m15feat is not None and len(m15feat):sheets['15m Features']=m15feat.tail(1100).reset_index()
        if callable(historical_signal_timeline):
            atl=historical_signal_timeline(f);sheets['Signal Timeline']=atl
            if callable(acceleration_validation):sheets['Acceleration Validation']=acceleration_validation(atl)
        if isinstance(dyn.get('early_calibration',{}).get('table'),pd.DataFrame):sheets['Dynamic Early Calibration']=dyn['early_calibration']['table']
        if isinstance(dyn.get('quant_calibration',{}).get('table'),pd.DataFrame):sheets['Dynamic Quant Calibration']=dyn['quant_calibration']['table']
        combos=dyn.get('combinations',pd.DataFrame())
        if isinstance(combos,pd.DataFrame) and not combos.empty:sheets['Combinations']=combos
        excel=None; excel_error=None
        try:
            excel=workbook_bytes(sheets,{'Tab':'Analyze','Ticker':t,'Version':APP_VERSION})
        except Exception as _excel_exc:
            # Excel export must never invalidate an otherwise completed market analysis.
            excel_error=f'{type(_excel_exc).__name__}: {_excel_exc}'
        payload={'ticker':t,'history':hist,'horizon':horizon,'target':target,'f':f,'latest':latest,'dyn':dyn,'hfeat':hfeat,'ent':ent,'latest_live':latest_live,'live_snapshot':live_snapshot,'ah_snapshot':ah_snapshot,'ex':ex,'timing':timing,'decision':decision,'ca_report':ca_report,'bt':bt,'buy_threshold':buy_threshold,'auto_table':auto_table,'comp':comp,'ec':ec,'cmp':cmp,'compare_df':compare_df,'ev':ev,'early_cal':early_cal,'quant_cal':quant_cal,'cal_events':cal_events,'origin_validation_summary':origin_validation_summary,'origin_robustness':origin_robustness,'origin_matched_baseline':origin_matched_baseline,'origin_matched_confidence':origin_matched_confidence,'research_evidence_summary':research_evidence_summary,'continuation_validation_summary':continuation_validation_summary,'continuation_validation':continuation_validation,'feedback_snapshot':_analyze_feedback,'excel':excel,'excel_error':excel_error}
        _lab_update_v603(runtime,jid,8,8,t,'Completed');_lab_publish_v603(runtime,jid,payload)
    except _LabCancelled:_lab_publish_v603(runtime,jid,None,'stopped')
    except Exception as e:_lab_fail_v603(runtime,jid,e)


def _backtest_worker_v603(runtime,jid,cfg):
    try:
        _lab_update_v603(runtime,jid,0,9,cfg['ticker'],'Downloading history')
        d=fetch_ohlcv(cfg['ticker'],cfg['history'],'1d');_lab_check_v603(runtime,jid)
        if d is None or len(d)<35: raise ValueError('Not enough market data')
        f=compute_features(d);rows=[]
        for i,x in enumerate([60,62,64,66,68,70,72,75],1):
            _lab_check_v603(runtime,jid);_lab_update_v603(runtime,jid,i,9,str(x),'Testing historical Quant threshold')
            b=backtest_signal(f,int(cfg['days']),float(cfg['target'])/100,x,0)
            _bn=int(b.get('n',0) or 0); _bq=('STRONG' if _bn>=30 and b.get('confidence_label')=='HIGH' else ('MEDIUM' if _bn>=12 else ('BUILDING' if _bn>=8 else ('PROVISIONAL' if _bn>=6 else 'LOW'))))
            rows.append({'Historical Quant Threshold':x,'Hits':b.get('hits',0),'Signals':_bn,'Hit Rate %':round(b['hit_rate']*100,1) if _bn>=6 else np.nan,'Evidence Quality':_bq,'Avg Return %':round(b['avg_return']*100,2) if _bn else np.nan,'Worst Drawdown %':round(b['max_drawdown']*100,2) if _bn else np.nan,'Confidence Score':b['confidence']})
        df=pd.DataFrame(rows);_lab_update_v603(runtime,jid,9,9,cfg['ticker'],'Building workbook')
        excel=workbook_bytes({'Threshold Backtest':df},{'Tab':'Backtest','Ticker':cfg['ticker'],'History':cfg['history'],'ForecastDays':cfg['days'],'TargetPct':cfg['target'],'Note':'Research only — not Top Score and not Trade Trigger'})
        _lab_publish_v603(runtime,jid,{'table':df,'excel':excel})
    except _LabCancelled:
        _lab_publish_v603(runtime,jid,None,'stopped')
    except Exception as e:_lab_fail_v603(runtime,jid,e)


def _cal_table_v603(feat,ticker,kind,target,fold,phase):
    cal=_v544_calibrate_components(feat,kind,target,(1,2,3),0);tb=cal.get('table',pd.DataFrame());ev=int(cal.get('events',0) or 0);rows=[]
    if tb is not None and not tb.empty:
        for _,r in tb.iterrows():rows.append({'Ticker':ticker,'Fold':fold,'Phase':phase,'Component':r['Component'],'Lift x':float(r.get('Lift x',np.nan)),'Coverage %':float(r.get('Coverage %',np.nan)),'Events':ev,'Stability %':float(r.get('Stability %',np.nan))})
    return ev,rows


def _aggregate_wf_v603(rows):
    z=pd.DataFrame(rows)
    if z.empty:return z
    out=[]
    for comp,g in z.groupby('Component'):
        train=g[g.Phase=='Train'];val=g[g.Phase=='Validation'];keys=set(zip(train.Ticker,train.Fold)).intersection(set(zip(val.Ticker,val.Fold)))
        tr=[];va=[];cov=[];stab=[];stock_pos={};fold_pos={i:[] for i in range(1,5)};events=0
        for ticker,fold in keys:
            ar=train[(train.Ticker==ticker)&(train.Fold==fold)];br=val[(val.Ticker==ticker)&(val.Fold==fold)]
            if ar.empty or br.empty:continue
            tl=float(ar['Lift x'].iloc[0]);vl=float(br['Lift x'].iloc[0])
            if np.isfinite(tl):tr.append(tl)
            if np.isfinite(vl):va.append(vl);stock_pos.setdefault(ticker,[]).append(vl>1.0);fold_pos[fold].append(vl>1.0)
            cv=float(br['Coverage %'].iloc[0]);sv=float(br['Stability %'].iloc[0])
            if np.isfinite(cv):cov.append(cv)
            if np.isfinite(sv):stab.append(sv)
            events+=int(br['Events'].iloc[0] or 0)
        if not va:continue
        tmed=float(np.median(tr)) if tr else np.nan;vmed=float(np.median(va));vmean=float(np.mean(va));pstock=sum(1 for vals in stock_pos.values() if np.mean(vals)>0.5);ns=len(stock_pos);spr=100*pstock/ns if ns else 0;pfold=sum(1 for vals in fold_pos.values() if vals and np.mean(vals)>0.5);nf=sum(1 for vals in fold_pos.values() if vals);fpr=100*pfold/nf if nf else 0;repeat=np.isfinite(tmed) and tmed>1.0 and vmed>1.0
        verdict='ROBUST WF WINNER' if ns>=8 and nf>=3 and repeat and vmed>=1.05 and spr>=60 and fpr>=75 else ('PROMISING' if ns>=8 and repeat and spr>=50 else ('FAILED WF' if ns>=8 and np.isfinite(tmed) and tmed>1.05 and (vmed<0.95 or spr<=40) else 'MIXED / WEAK'))
        out.append({'Component':comp,'Train Median Lift':tmed,'WF Median Lift':vmed,'WF Mean Lift':vmean,'WF Coverage %':float(np.mean(cov)) if cov else np.nan,'Positive stocks':f'{pstock}/{ns}','Positive stocks %':spr,'Positive folds':f'{pfold}/{nf}','Positive folds %':fpr,'WF Stability %':float(np.mean(stab)) if stab else np.nan,'Validation events*':events,'Verdict':verdict})
    out=pd.DataFrame(out)
    if out.empty:return out
    rank={'ROBUST WF WINNER':0,'PROMISING':1,'MIXED / WEAK':2,'FAILED WF':3};out['_r']=out.Verdict.map(rank).fillna(9)
    return out.sort_values(['_r','WF Median Lift','Positive stocks %','Positive folds %'],ascending=[True,False,False,False]).drop(columns='_r').reset_index(drop=True)


def _validate_payload_v603(early_rows,quant_rows,stock_rows,skipped,overlap_frames,cfg,partial=False):
    ea=_aggregate_wf_v603(early_rows);qa=_aggregate_wf_v603(quant_rows);pp=pd.DataFrame()
    if overlap_frames:
        ovall=pd.concat(overlap_frames,ignore_index=True);comp_cols=[c for c in ovall.columns if c.startswith('Early: ') or c.startswith('Quant: ')];corr=ovall[comp_cols].corr(method='spearman');pairs=[]
        for i,a in enumerate(comp_cols):
            for b in comp_cols[i+1:]:
                v=float(corr.loc[a,b]) if a in corr.index and b in corr.columns else np.nan
                if np.isfinite(v):pairs.append({'Component A':a,'Component B':b,'Spearman correlation':v,'Abs correlation':abs(v)})
        if pairs:pp=pd.DataFrame(pairs).sort_values('Abs correlation',ascending=False).head(12).reset_index(drop=True)
    sheets={'Early WF':ea,'Quant WF':qa,'Stock Audit':pd.DataFrame(stock_rows),'Early Raw':pd.DataFrame(early_rows),'Quant Raw':pd.DataFrame(quant_rows)}
    if skipped:sheets['Skipped']=pd.DataFrame(skipped,columns=['Ticker','Reason'])
    if not pp.empty:sheets['Top Overlaps']=pp
    excel=workbook_bytes(sheets,{'Tab':'Validate','History':cfg['history'],'TargetPct':cfg['target'],'MinTrainEvents':cfg['min_events'],'Stocks':len(cfg['tickers']),'Status':'PARTIAL / STOPPED' if partial else 'COMPLETED'})
    return {'early':ea,'quant':qa,'audit':pd.DataFrame(stock_rows),'skipped':pd.DataFrame(skipped,columns=['Ticker','Reason']) if skipped else pd.DataFrame(),'overlaps':pp,'excel':excel,'partial':partial}


def _validate_worker_v603(runtime,jid,cfg):
    early_rows=[];quant_rows=[];stock_rows=[];skipped=[];overlap_frames=[];completed=0
    try:
        folds=[(.40,.55),(.55,.70),(.70,.85),(.85,1.00)];total=len(cfg['tickers'])
        for idx,t in enumerate(cfg['tickers'],1):
            _lab_check_v603(runtime,jid);_lab_update_v603(runtime,jid,completed,total,t,'Walk-forward validation')
            try:
                d=fetch_ohlcv(t,cfg['history'],'1d');_lab_check_v603(runtime,jid)
                if d is None:skipped.append((t,'no price data returned'));completed=idx;continue
                if len(d)<180:skipped.append((t,f'only {len(d)} daily rows; need at least 180'));completed=idx;continue
                f=compute_features(d).dropna(subset=['Close']).copy();accepted=0;tr_events=0;va_events=0;er=[];qr=[]
                for fold,(train_end,test_end) in enumerate(folds,1):
                    _lab_check_v603(runtime,jid);i1=max(80,int(len(f)*train_end));i2=min(len(f),int(len(f)*test_end))
                    if i2-i1<20:continue
                    train=f.iloc[:i1].copy();test=f.iloc[i1:i2].copy();te,ter=_cal_table_v603(train,t,'early',float(cfg['target'])/100,fold,'Train');tq,tqr=_cal_table_v603(train,t,'quant',float(cfg['target'])/100,fold,'Train');ve,ver=_cal_table_v603(test,t,'early',float(cfg['target'])/100,fold,'Validation');vq,vqr=_cal_table_v603(test,t,'quant',float(cfg['target'])/100,fold,'Validation');tev=min(te,tq);vev=min(ve,vq)
                    if tev<int(cfg['min_events']) or vev<1:continue
                    accepted+=1;tr_events+=tev;va_events+=vev;er.extend(ter+ver);qr.extend(tqr+vqr)
                if accepted<2:skipped.append((t,f'only {accepted} usable walk-forward folds'));completed=idx;continue
                early_rows.extend(er);quant_rows.extend(qr);ov=[]
                for dt,r in f.iterrows():
                    rec={'Ticker':t,'Date':dt}
                    for name,pts,mx in early_score_row(r)[1]:rec['Early: '+name]=float(pts)/float(mx) if mx else np.nan
                    for name,pts,mx in score_row(r,0)[1]:rec['Quant: '+name]=float(pts)/float(mx) if mx else np.nan
                    ov.append(rec)
                if ov:overlap_frames.append(pd.DataFrame(ov))
                stock_rows.append({'Ticker':t,'Rows':len(f),'Usable folds':accepted,'Train events*':tr_events,'Validation events':va_events})
            except _LabCancelled:raise
            except Exception as e:
                detail=str(e).strip().replace('\n',' ')[:220]
                skipped.append((t,f"calculation/data error: {type(e).__name__}: {detail}" if detail else f"calculation/data error: {type(e).__name__}"))
            completed=idx;_lab_update_v603(runtime,jid,completed,total,t,'Ticker complete')
        _lab_check_v603(runtime,jid);payload=_validate_payload_v603(early_rows,quant_rows,stock_rows,skipped,overlap_frames,cfg,False);_lab_publish_v603(runtime,jid,payload)
    except _LabCancelled:
        try:payload=_validate_payload_v603(early_rows,quant_rows,stock_rows,skipped,overlap_frames,cfg,True)
        except Exception:payload=None
        _lab_publish_v603(runtime,jid,payload,'stopped')
    except Exception as e:_lab_fail_v603(runtime,jid,e)


def _optimizer_fold_coverage_v63945(audit,min_events=12):
    """Summarize how many stocks actually qualify in each 1Y walk-forward fold."""
    a=pd.DataFrame(audit or [])
    if a.empty:return pd.DataFrame()
    if 'Market' not in a:a['Market']='UNKNOWN'
    rows=[]
    scopes=[('ALL',a)]
    for market,g in a.groupby('Market',dropna=False):scopes.append((str(market),g.copy()))
    for scope,g in scopes:
        assessed=int(len(g));history_ok=int((pd.to_numeric(g.get('Rows',0),errors='coerce').fillna(0)>=180).sum())
        for fold in (1,2,3,4):
            uc=f'Fold{fold} Usable';tc=f'Fold{fold} Train Events';rc=f'Fold{fold} Test Rows'
            usable=int(g.get(uc,pd.Series(False,index=g.index)).fillna(False).astype(bool).sum())
            tev=pd.to_numeric(g.get(tc,pd.Series(0,index=g.index)),errors='coerce').fillna(0)
            trw=pd.to_numeric(g.get(rc,pd.Series(0,index=g.index)),errors='coerce').fillna(0)
            rows.append({'Scope':scope,'Fold':fold,'Assessed Stocks':assessed,'History OK Stocks':history_ok,'Usable Stocks':usable,'Usable % of History-OK':100.0*usable/max(history_ok,1),'Min Training Events':int(min_events),'Median Train Events':float(tev[tev>0].median()) if (tev>0).any() else 0.0,'Total Test Rows':int(trw.sum())})
    return pd.DataFrame(rows)


def _entry_payload_v603(rows,audit,skipped,cfg,partial=False,premove_rows=None,hourly_rows=None,hourly_obs_rows=None,runtime=None,jid=None,ticker_total=None):
    ticker_total=int(ticker_total if ticker_total is not None else len(cfg.get('tickers',[])))
    work_total=ticker_total+5
    hourly_obs_count=len(hourly_obs_rows or [])
    def phase_update(completed,item,phase,frac=None,stage_started=None):
        if runtime is None or jid is None:return
        progress=None
        if frac is not None:
            progress=100.0*(float(completed)+float(np.clip(frac,0,1)))/max(1,work_total)
        eta=None
        if frac is not None and stage_started is not None and frac>0.02:
            spent=max(0,time_module.time()-stage_started);eta=spent*(1-frac)/max(frac,1e-6)
        _lab_update_v603(runtime,jid,completed,work_total,item,phase,progress_override=progress,eta_override=eta,eta_unknown=(eta is None and frac is not None))
    def cancel():
        if runtime is not None and jid is not None:_lab_check_v603(runtime,jid)

    # A stopped run must never re-enter the expensive optimizers while trying
    # to publish its partial diagnostics.
    if partial:
        opt=pd.DataFrame();opt_weights=pd.DataFrame();shadow_model={'version':APP_VERSION,'created':datetime.now().isoformat(timespec='seconds'),'scopes':{}}
        hop=pd.DataFrame();hweights=pd.DataFrame();hmodel={'scopes':{}}
    else:
        cancel();daily_started=time_module.time();phase_update(ticker_total,'Daily OOS','Daily OOS Optimizer • searching candidate weights',0.0,daily_started)
        opt,opt_weights,shadow_model=_entry_optimizer_v611(rows,cancel_check=cancel,progress_cb=lambda msg,frac:phase_update(ticker_total,msg,'Daily OOS Optimizer • searching candidate weights',frac,daily_started))
        phase_update(ticker_total+1,'Daily OOS complete','Daily OOS Optimizer • complete')
        shadow_model['source_universe']=cfg.get('market','CUSTOM') if isinstance(shadow_model,dict) else 'CUSTOM'
        cancel();hourly_started=time_module.time();phase_update(ticker_total+1,'Hourly OOS','Hourly OOS Optimizer • searching candidate weights',0.0,hourly_started)
        hourly_obs_count=len(hourly_obs_rows or [])
        hop,hweights,hmodel=_hourly_optimizer_v613(hourly_obs_rows or [],min_signals=max(60,int(cfg.get('min_events',12))*2),cancel_check=cancel,progress_cb=lambda msg,frac:phase_update(ticker_total+1,msg,'Hourly OOS Optimizer • searching candidate weights',frac,hourly_started),release_input=True)
        phase_update(ticker_total+2,'Hourly OOS complete','Hourly OOS Optimizer • complete')

    if runtime is not None and jid is not None and not partial:cancel()
    phase_update(ticker_total+2,'Model Registry','Finalizing • model registry',0.0)
    registry=_load_model_registry_v613()
    if not partial and isinstance(shadow_model,dict) and ((shadow_model.get('scopes') or {}) or ((hmodel or {}).get('scopes') if isinstance(hmodel,dict) else {})):
        registry=_register_model_v613(shadow_model,cfg,hmodel)
    if runtime is not None and jid is not None and not partial:cancel()
    phase_update(ticker_total+3,'Integrity + summaries','Finalizing • integrity and lift summaries',0.0)
    summary,gate,market_gate=_aggregate_entry_validation(rows)
    pm=pd.DataFrame(premove_rows or []);hl=pd.DataFrame(hourly_rows or [])
    daily_eligible=int((opt.get('Status',pd.Series(dtype=str)).astype(str)=='SHADOW ELIGIBLE').sum()) if isinstance(opt,pd.DataFrame) and not opt.empty else 0
    hourly_eligible=int((hop.get('Status',pd.Series(dtype=str)).astype(str)=='SHADOW ELIGIBLE').sum()) if isinstance(hop,pd.DataFrame) and not hop.empty else 0
    audit_df=pd.DataFrame(audit)
    fold_coverage=_optimizer_fold_coverage_v63945(audit,int(cfg.get('min_events',12)))
    usable_stocks=int(audit_df.loc[pd.to_numeric(audit_df.get('Usable folds',0),errors='coerce').fillna(0)>=2,'Ticker'].nunique()) if not audit_df.empty and 'Ticker' in audit_df else 0
    calc_errors=sum(1 for _,reason in (skipped or []) if str(reason).startswith('calculation/data error:'))
    if partial:run_status='PARTIAL / STOPPED'
    elif daily_eligible>0 and hourly_eligible>0:run_status='COMPLETED — ELIGIBLE DAILY + HOURLY MODELS READY'
    elif daily_eligible>0:run_status='COMPLETED — ELIGIBLE DAILY MODEL READY'
    elif hourly_eligible>0:run_status='COMPLETED — ELIGIBLE HOURLY MODEL READY / DAILY RESEARCH ONLY'
    elif not rows:run_status='FAILED — NO USABLE DAILY OOS OBSERVATIONS'
    elif opt.empty:run_status='COMPLETED — NO DAILY OOS MODEL'
    else:run_status='COMPLETED — NO ELIGIBLE OOS MODEL'
    integrity=pd.DataFrame([{'Run Status':run_status,'Requested Stocks':len(cfg.get('tickers',[])),'Usable Daily Stocks':usable_stocks,'Daily Observation Rows':len(rows),'Daily OOS Scopes':len(opt) if isinstance(opt,pd.DataFrame) else 0,'Eligible Daily Scopes':daily_eligible,'Hourly OOS Scopes':len(hop) if isinstance(hop,pd.DataFrame) else 0,'Eligible Hourly Scopes':hourly_eligible,'Hourly OOS Live Timing Ready':bool(hourly_eligible>0),'Skipped Stocks':len(skipped or []),'Calculation/Data Errors':calc_errors,'Hourly OOS Observations':hourly_obs_count,'Hourly Anchor Cap / Ticker':240,'Hourly Sampling':'DETERMINISTIC EVEN-SPAN (full history preserved)','Min Training Events / Stock Fold':int(cfg.get('min_events',12))}])
    pm_summary=_aggregate_lift_rows_v611(pm,['Indicator','Days Before','Target','Horizon'],'Baseline %') if not pm.empty else pd.DataFrame()
    pm_market=_aggregate_lift_rows_v611(pm,['Market','Indicator','Days Before','Target','Horizon'],'Baseline %') if not pm.empty else pd.DataFrame()
    hl_summary=_aggregate_lift_rows_v611(hl,['Signal','Target','Horizon'],'Matched Baseline %') if not hl.empty else pd.DataFrame()
    hl_market=_aggregate_lift_rows_v611(hl,['Market','Signal','Target','Horizon'],'Matched Baseline %') if not hl.empty else pd.DataFrame()
    active=_select_active_model_v613(registry,int(cfg.get('horizon',3)),float(cfg.get('target',3)),float(cfg.get('hourly_target',3)));regsel=_registry_selection_frame_v613(active);regaudit=_registry_candidate_audit_v63946(registry,int(cfg.get('horizon',3)),float(cfg.get('target',3)),float(cfg.get('hourly_target',3)),active)
    if runtime is not None and jid is not None and not partial:cancel()
    phase_update(ticker_total+4,'Excel','Finalizing • building Optimizer workbook',0.0)
    sheets={'Optimizer Integrity':integrity,'Fold Coverage':fold_coverage,'Entry Summary':summary,'Entry Trigger V4 Gate':gate,'Entry Gate by Market':market_gate,'Daily OOS Optimizer':opt,'Daily OOS Weights':opt_weights,'Hourly OOS Optimizer':hop,'Hourly OOS Weights':hweights,'Registry Selection':regsel,'Registry Candidate Audit':regaudit,'Pre-Move Lift Summary':pm_summary,'Pre-Move by Market':pm_market,'Pre-Move Indicator Lift':pm,'Hourly Lift Summary':hl_summary,'Hourly Lift by Market':hl_market,'Hourly Matched Lift':hl,'Raw Observations':rows,'Stock Audit':audit_df}
    if skipped:sheets['Skipped']=[{'Ticker':t,'Reason':reason} for t,reason in skipped]
    excel=_optimizer_workbook_bytes_v63943(sheets,{'Tab':'Adaptive Entry Optimizer','Market':cfg.get('market','CUSTOM'),'History':cfg['history'],'TargetPct':cfg['target'],'HorizonDays':cfg['horizon'],'HourlyTargetPct':cfg.get('hourly_target',3),'HourlyHorizons':','.join(f'{int(x)}h' for x in cfg.get('hourly_bars',(1,2,4))),'MinTrainEvents':cfg['min_events'],'Status':run_status,'RegistryModels':len(registry.get('models',[])),'EligibleDailyScopes':daily_eligible,'EligibleHourlyScopes':hourly_eligible,'HourlyOOSObservationCount':hourly_obs_count,'HourlyAnchorCapPerTicker':240,'Note':'V6.3.9.46 keeps Fold4 as eligibility-only holdout evidence. Registry selection uses market specificity, newest eligible 1Y run, then inner-validation/stability metrics; Fold4 lift is never used to rank eligible models. 12-event 1Y walk-forward, Hourly OOS production timing, Daily/Core safeguards and final OOS eligibility thresholds are unchanged.'})
    phase_update(ticker_total+5,'Completed','Completed')
    return {'summary':summary,'gate':gate,'market_gate':market_gate,'optimizer':opt,'optimizer_weights':opt_weights,'hourly_optimizer':hop,'hourly_optimizer_weights':hweights,'shadow_model':shadow_model,'model_registry':registry,'registry_selection':regsel,'registry_candidate_audit':regaudit,'premove':pm,'premove_summary':pm_summary,'premove_market':pm_market,'hourly_lift':hl,'hourly_summary':hl_summary,'hourly_market':hl_market,'audit':audit_df,'fold_coverage':fold_coverage,'integrity':integrity,'run_status':run_status,'skipped':pd.DataFrame(skipped,columns=['Ticker','Reason']) if skipped else pd.DataFrame(),'excel':excel,'partial':partial,'observations':len(rows)//2,'hourly_observations':hourly_obs_count}


def _entry_worker_v603(runtime,jid,cfg):
    rows=[];audit=[];skipped=[];premove_rows=[];hourly_rows=[];hourly_obs_rows=[];completed=0;folds=[(.40,.55),(.55,.70),(.70,.85),(.85,1.00)];ticker_total=len(cfg['tickers']);work_total=ticker_total+5
    try:
        _lab_update_v603(runtime,jid,0,work_total,'—','Collecting ticker observations')
        for idx,t in enumerate(cfg['tickers'],1):
            _lab_check_v603(runtime,jid);_lab_update_v603(runtime,jid,completed,work_total,t,'Entry + hourly OOS walk-forward')
            try:
                stock_rows=[];d=fetch_ohlcv(t,cfg['history'],'1d');_lab_check_v603(runtime,jid)
                if d is None:
                    skipped.append((t,'no price data returned'));audit.append({'Ticker':t,'Market':_market_for_ticker_v612(t),'Rows':0,'Usable folds':0,'Test rows':0,'Hourly OOS observations':0,'Fold1 Usable':False,'Fold2 Usable':False,'Fold3 Usable':False,'Fold4 Usable':False,'Fold1 Train Events':0,'Fold2 Train Events':0,'Fold3 Train Events':0,'Fold4 Train Events':0,'Audit Status':'NO PRICE DATA'});completed=idx;_lab_update_v603(runtime,jid,completed,work_total,t,'Ticker skipped');continue
                if len(d)<180:
                    skipped.append((t,f'only {len(d)} daily rows; need at least 180'));audit.append({'Ticker':t,'Market':_market_for_ticker_v612(t),'Rows':len(d),'Usable folds':0,'Test rows':0,'Hourly OOS observations':0,'Fold1 Usable':False,'Fold2 Usable':False,'Fold3 Usable':False,'Fold4 Usable':False,'Fold1 Train Events':0,'Fold2 Train Events':0,'Fold3 Train Events':0,'Fold4 Train Events':0,'Audit Status':'INSUFFICIENT DAILY HISTORY'});completed=idx;_lab_update_v603(runtime,jid,completed,work_total,t,'Ticker skipped');continue
                f=compute_features(d).dropna(subset=['Close']).copy();usable=0;tested=0;hourly_n=0;fold_flags={1:False,2:False,3:False,4:False};fold_train={1:0,2:0,3:0,4:0};fold_test={1:0,2:0,3:0,4:0}
                try:
                    if callable(pre_move_indicator_lift):
                        pm=pre_move_indicator_lift(f,targets=tuple(sorted(set((int(cfg['target']),5,10)))),horizons=(int(cfg['horizon']),),lags=(1,2,3),min_signals=10)
                        if pm is not None and not pm.empty:
                            pm=pm.copy();pm.insert(0,'Market',_market_for_ticker_v612(t));pm.insert(0,'Ticker',t);premove_rows.extend(pm.to_dict('records'))
                except Exception:pass
                try:
                    hraw=fetch_ohlcv(t,'1y','1h')
                    if hraw is None or len(hraw)<120:hraw=fetch_ohlcv(t,'6mo','1h')
                    if hraw is not None and len(hraw)>=80:
                        hf=compute_features(hraw,True)
                        if callable(hourly_lift_study):
                            hs=hourly_lift_study(hf,targets=(int(cfg.get('hourly_target',3)),),horizon_bars=tuple(cfg.get('hourly_bars',(1,2,4))),min_signals=10)
                            if hs is not None and not hs.empty:
                                hs=hs.copy();hs.insert(0,'Market',_market_for_ticker_v612(t));hs.insert(0,'Ticker',t);hourly_rows.extend(hs.to_dict('records'))
                        obs=_hourly_optimizer_observations_v613(hf,t,float(cfg.get('hourly_target',3))/100.0,tuple(cfg.get('hourly_bars',(1,2,4))),max_anchor_rows=240)
                        hourly_obs_rows.extend(obs);hourly_n=len(obs)
                except Exception:pass
                for fold,(train_end,test_end) in enumerate(folds,1):
                    _lab_check_v603(runtime,jid);i1=max(80,int(len(f)*train_end));i2=min(len(f),int(len(f)*test_end))
                    if i2-i1<max(25,int(cfg['horizon'])+5):continue
                    train=f.iloc[:i1].copy();test=f.iloc[i1:i2].copy();ec=_v544_calibrate_components(train,'early',float(cfg['target'])/100,(1,2,3),0);qc=_v544_calibrate_components(train,'quant',float(cfg['target'])/100,(1,2,3),0);train_events=min(int(ec.get('events',0) or 0),int(qc.get('events',0) or 0));fold_train[fold]=int(train_events)
                    if train_events<int(cfg['min_events']):continue
                    hit,ret,mfe,mae,days=_entry_forward_metrics(test,int(cfg['horizon']),float(cfg['target'])/100);fold_rows=0
                    for j in range(len(test)):
                        if not np.isfinite(hit[j]):continue
                        r=test.iloc[j];sq=float(score_row(r,0)[0]);se=float(early_score_row(r)[0]);dq,_=_v544_dynamic_score_row(r,qc,'quant',0);de,_=_v544_dynamic_score_row(r,ec,'early',0);static_entry=_entry_score_from_row(r,sq,se);dynamic_entry=_entry_score_from_row(r,dq,de);common={'Ticker':t,'Market':_market_for_ticker_v612(t),'Fold':fold,'Hit':float(hit[j]),'ForwardReturn':float(ret[j]),'Drawdown':float(mae[j]),'MFE':float(mfe[j]),'MAE':float(mae[j]),'DaysToTarget':float(days[j]) if np.isfinite(days[j]) else np.nan};sg=_entry_research_gate_v610(r,sq,static_entry);dg=_entry_research_gate_v610(r,dq,dynamic_entry);stock_rows.append({**common,'Mode':'Static','EntryScore':static_entry,'QuantScore':sq,'EarlyScore':se,'Bucket':_entry_bucket(static_entry),**sg});stock_rows.append({**common,'Mode':'Dynamic','EntryScore':dynamic_entry,'QuantScore':dq,'EarlyScore':de,'Bucket':_entry_bucket(dynamic_entry),**dg});fold_rows+=1
                    if fold_rows:
                        usable+=1;tested+=fold_rows;fold_flags[fold]=True;fold_test[fold]=int(fold_rows)
                audit_rec={'Ticker':t,'Market':_market_for_ticker_v612(t),'Rows':len(f),'Usable folds':usable,'Test rows':tested,'Hourly OOS observations':hourly_n,'Audit Status':'USABLE' if usable>=2 else 'LOW FOLD COVERAGE'}
                for _fold in (1,2,3,4):
                    audit_rec[f'Fold{_fold} Usable']=bool(fold_flags[_fold]);audit_rec[f'Fold{_fold} Train Events']=int(fold_train[_fold]);audit_rec[f'Fold{_fold} Test Rows']=int(fold_test[_fold])
                audit.append(audit_rec)
                if usable<2:skipped.append((t,f'only {usable} usable walk-forward folds'));completed=idx;_lab_update_v603(runtime,jid,completed,work_total,t,'Ticker skipped');continue
                rows.extend(stock_rows)
            except _LabCancelled:raise
            except Exception as e:
                detail=str(e).strip().replace('\n',' ')[:220];skipped.append((t,f"calculation/data error: {type(e).__name__}: {detail}" if detail else f"calculation/data error: {type(e).__name__}"))
            completed=idx;_lab_update_v603(runtime,jid,completed,work_total,t,'Ticker complete')
            if idx%8==0:gc.collect()
        _lab_check_v603(runtime,jid)
        payload=_entry_payload_v603(rows,audit,skipped,cfg,False,premove_rows,hourly_rows,hourly_obs_rows,runtime,jid,ticker_total)
        _lab_publish_v603(runtime,jid,payload)
    except _LabCancelled:
        try:payload=_entry_payload_v603(rows,audit,skipped,cfg,True,premove_rows,hourly_rows,hourly_obs_rows,None,None,ticker_total)
        except Exception:payload=None
        _lab_publish_v603(runtime,jid,payload,'stopped')
    except Exception as e:_lab_fail_v603(runtime,jid,e)

def _explosive_worker_v603(runtime,jid,cfg):
    try:
        _lab_update_v603(runtime,jid,0,3,cfg['ticker'],'Downloading history');d=fetch_ohlcv(cfg['ticker'],cfg['history'],'1d');_lab_check_v603(runtime,jid)
        if d is None or len(d)<120:raise ValueError('Need at least 120 daily rows for this validation.')
        _lab_update_v603(runtime,jid,1,3,cfg['ticker'],'Computing features');f=compute_features(d);_lab_check_v603(runtime,jid)
        if not callable(explosive_walkforward):raise RuntimeError('quant engine is missing explosive_walkforward()')
        _lab_update_v603(runtime,jid,2,3,cfg['ticker'],'Explosive walk-forward');ewf=explosive_walkforward(f,cfg['threshold']);_lab_check_v603(runtime,jid)
        _lab_update_v603(runtime,jid,3,3,cfg['ticker'],'Building workbook');excel=workbook_bytes({'Explosive WalkForward':ewf},{'Tab':'Explosive Lab','Ticker':cfg['ticker'],'History':cfg['history'],'TriggerThreshold':cfg['threshold']});_lab_publish_v603(runtime,jid,{'table':ewf,'excel':excel})
    except _LabCancelled:_lab_publish_v603(runtime,jid,None,'stopped')
    except Exception as e:_lab_fail_v603(runtime,jid,e)


def _feedback_worker_v603(runtime,jid,cfg):
    try:
        _lab_update_v603(runtime,jid,0,1,'Outcomes','Evaluating due 1D / 2D / 3D / 5D windows');_lab_check_v603(runtime,jid);n=_feedback_evaluate_due_v600(max_snapshots=int(cfg.get('max_snapshots',80)));_lab_check_v603(runtime,jid);_lab_update_v603(runtime,jid,1,1,'Outcomes','Completed');_lab_publish_v603(runtime,jid,{'evaluated':n})
    except _LabCancelled:_lab_publish_v603(runtime,jid,None,'stopped')
    except Exception as e:_lab_fail_v603(runtime,jid,e)


def _historical_replay_worker_v630(runtime,jid,cfg):
    """V6.3.4 causal replay: V3 combinations plus market-specific nested consensus."""
    try:
        tickers=list(cfg.get('tickers') or []);total=len(tickers);history=str(cfg.get('history','1y'));target=float(cfg.get('target_pct',.05));h=int(cfg.get('horizon_days',3));step=max(1,int(cfg.get('sample_every',5)))
        final_steps=6;work_total=max(1,total+final_steps)
        rows=[];skipped=[];successful=0
        for n,t in enumerate(tickers,1):
            _lab_check_v603(runtime,jid);_lab_update_v603(runtime,jid,n-1,work_total,t,'Historical Replay V4 • causal daily evidence')
            try:
                d=fetch_ohlcv(t,history,'1d')
                if d is None or len(d)<100:raise ValueError('Need at least 100 daily bars')
                f=compute_features(d).dropna(subset=['Close']).copy()
                if len(f)>1:f=f.iloc[:-1].copy()
                if len(f)<90+h:raise ValueError('Insufficient completed daily history after feature warm-up')
                successful+=1;start_i=70;last=len(f)-h
                for i in range(start_i,last,step):
                    r=f.iloc[i];p0=float(r.get('Close',np.nan))
                    if not np.isfinite(p0) or p0<=0:continue
                    q=float(score_row(r,0)[0]) if callable(score_row) else np.nan;es=float(early_score_row(r)[0]) if callable(early_score_row) else np.nan;ent=float(_entry_score_from_row(r,q,es))
                    atrp=float(r.get('atr_pct',np.nan)) if pd.notna(r.get('atr_pct',np.nan)) else np.nan;stop_pct=float(np.clip(1.20*(atrp/100.0),.02,.06)) if np.isfinite(atrp) else .03
                    t1=p0*(1+target);inv=p0*(1-stop_pct);future=f.iloc[i+1:i+1+h]
                    if len(future)<h:continue
                    first='NONE'
                    for _,bar in future.iterrows():
                        ht=bool(float(bar.High)>=t1);hi=bool(float(bar.Low)<=inv)
                        if ht and hi:first='AMBIGUOUS SAME DAILY BAR';break
                        if hi:first='INVALIDATION FIRST (daily replay)';break
                        if ht:first='TARGET1 FIRST (daily replay)';break
                    outcome='WIN' if first.startswith('TARGET1 FIRST') else ('LOSS' if first.startswith('INVALIDATION FIRST') else ('AMBIGUOUS' if first.startswith('AMBIGUOUS') else 'OPEN/NONE'))
                    endret=float(future.Close.iloc[-1]/p0-1);mfe=float(future.High.max()/p0-1);mae=float(future.Low.min()/p0-1)
                    recent2=float(p0/float(f.iloc[i-2].Close)-1) if i>=2 and float(f.iloc[i-2].Close)>0 else np.nan
                    setup=_feedback_replay_setup_v631(r,target,recent2)
                    legacy=bool(ent>=55 and (es>=50 or q>=60));r_mult=(target/stop_pct if outcome=='WIN' else (-1.0 if outcome=='LOSS' else np.nan))
                    try:sigdate=str(pd.Timestamp(f.index[i]).date())
                    except Exception:sigdate=str(f.index[i])
                    rows.append({'Ticker':str(t),'Market':_feedback_market_key_v612('',str(t)),'SignalDate':sigdate,'Price':p0,'QuantScore':q,'EarlyScore':es,'EntryScore':ent,'ATRPct':atrp,'Target1':t1,'Invalidation':inv,'EndReturn':endret,'MFE':mfe,'MAE':mae,'FirstEvent':first,'CleanOutcome':outcome,'Indicators':' | '.join(setup['active']),'Candidate':setup['candidate_v2'],'LegacyCandidate':legacy,'CandidateV2':setup['candidate_v2'],'HighConfidence':False,'FamilySignature':setup['family_signature'],'IndependentFamilyCount':setup['family_count'],'FreshnessState':setup['freshness_state'],'MoveConsumedPct':setup['move_consumed_pct'],'ExtensionATR':setup['extension_atr'],'DistributionRisk':setup['distribution_risk'],'SetupScoreV2':setup['setup_score_v2'],'MetaProbability':np.nan,'MetaSample':0,'MetaLift':np.nan,'RMultiple':r_mult,'Recent2DReturn':recent2,'CoreMomentum':setup['core_momentum'],'CoreVolumeFlow':setup['core_volume_flow'],'CandidateRuleVersion':'V6.3.4 DAILY-V2+COMBO+CONSENSUS'})
            except Exception as e:skipped.append({'Ticker':str(t),'Reason':f'{type(e).__name__}: {e}'})
            _lab_update_v603(runtime,jid,n,work_total,t,'Historical Replay V4 • ticker complete')
        _lab_check_v603(runtime,jid);_lab_update_v603(runtime,jid,total,work_total,'Meta model','Finalizing • causal meta probabilities')
        df=_feedback_replay_apply_meta_v631(pd.DataFrame(rows)) if rows else pd.DataFrame()
        _lab_check_v603(runtime,jid);_lab_update_v603(runtime,jid,total+1,work_total,'Combination Discovery','70% discovery • independent-family combinations • untouched 30% OOS')
        combos,combo_folds,combo_gates,df=_feedback_replay_combination_discovery_v633(df)
        _lab_check_v603(runtime,jid);_lab_update_v603(runtime,jid,total+2,work_total,'Market Consensus','60% discovery • 20% selector • untouched final 20%')
        consensus_combos,consensus_gates,df=_feedback_replay_market_consensus_v634(df)
        rows=df.to_dict('records') if not df.empty else []
        _lab_check_v603(runtime,jid);_lab_update_v603(runtime,jid,total+3,work_total,'Replay database','Finalizing • saving replay + combination evidence')
        _feedback_store_replay_v630(jid,rows,cfg,successful,combos,combo_folds,consensus_combos,consensus_gates)
        _lab_check_v603(runtime,jid);_lab_update_v603(runtime,jid,total+4,work_total,'Scorecards','Finalizing • success / lift / nested holdout')
        head,inds,stocks,gates,cal=_feedback_replay_scorecards_v631(df)
        _lab_check_v603(runtime,jid);_lab_update_v603(runtime,jid,total+5,work_total,'Excel','Finalizing • building workbook')
        excel=_feedback_workbook_v629({'Replay Success':head,'Replay Gate Comparison':gates,'V3 OOS Gate Comparison':combo_gates,'Market Consensus Gates':consensus_gates,'Market Consensus Combos':consensus_combos,'Combination Discovery':combos,'WalkForward Folds':combo_folds,'Replay Meta Calibration':cal,'Replay Indicators':inds,'Replay Stocks':stocks,'Replay Events':df,'Skipped':pd.DataFrame(skipped)},{'Tab':'Historical Replay V4','Version':APP_VERSION,'Scope':cfg.get('scope'),'History':history,'TargetPct':100*target,'HorizonDays':h,'SampleEverySessions':step,'RequestedStocks':total,'SuccessfulStocks':successful,'DiscoveryValidation':'V3 = 70/30; V6.3.4 consensus = nested 60% discovery / 20% selector / untouched 20% final holdout, market-specific','ResearchOnly':'YES — market consensus and combination discovery are research-only; no Production Entry rules changed'})
        _lab_publish_v603(runtime,jid,{'events':df,'headline':head,'indicators':inds,'stocks':stocks,'gates':gates,'calibration':cal,'combinations':combos,'combo_folds':combo_folds,'combo_gates':combo_gates,'consensus_combos':consensus_combos,'consensus_gates':consensus_gates,'skipped':pd.DataFrame(skipped),'excel':excel,'successful':successful})
    except _LabCancelled:_lab_publish_v603(runtime,jid,None,'stopped')
    except Exception as e:_lab_fail_v603(runtime,jid,e)


def _research_validator_universe_v624(scope, max_tickers):
    """Deterministic expanded research universe selection (V6.2.9)."""
    def arr(txt): return [x.strip().upper() for x in str(txt).split(',') if x.strip()]
    max_tickers=max(1,int(max_tickers))
    if scope=='NASDAQ': return arr(NASDAQ_200)[:max_tickers]
    if scope=='US': return arr(US_201)[:max_tickers]
    if scope=='HONG KONG': return arr(HK_100)[:max_tickers]
    if scope=='TEL AVIV': return arr(TASE_50)[:max_tickers]
    groups=[arr(NASDAQ_200),arr(HK_100),arr(TASE_50)]; out=[]; k=0
    while len(out)<max_tickers and any(k<len(g) for g in groups):
        for g in groups:
            if k<len(g) and len(out)<max_tickers: out.append(g[k])
        k+=1
    return out


def _research_validator_worker_v624(runtime,jid,cfg):
    """Cross-stock fixed-rule research validator; no production weights change."""
    try:
        tickers=list(cfg.get('tickers') or []); target=float(cfg.get('target_pct',.02)); stop=float(cfg.get('stop_pct',.015)); horizon=int(cfg.get('horizon_bars',16))
        stock_rows=[]; pair_frames=[]; cont_frames=[]; skipped=[]
        total=max(1,len(tickers))
        for i,t in enumerate(tickers,1):
            _lab_check_v603(runtime,jid);_lab_update_v603(runtime,jid,i-1,total,t,'Downloading 60d 15m research history')
            try:
                m15=confirmed_intraday_bars(fetch_ohlcv(t,'60d','15m'))
                if m15 is None or len(m15)<30: raise ValueError('Not enough 15m history')
                f15=compute_features(m15,True)
                pairs=setup_origin_session_pairs_v624(f15,target_pct=target,stop_pct=stop,max_bars=horizon)
                cont=continuation_base_validation_v621(f15,breakout_lookahead=8,target_pct=target,stop_pct=stop,outcome_bars=horizon)
                base=setup_origin_matched_baseline_v622(f15,target_pct=target,stop_pct=stop,max_bars=horizon)
                robust=setup_origin_robustness_v620(f15)
                market=_market_for_ticker_v612(t)
                if pairs is not None and not pairs.empty:
                    pairs=pairs.copy();pairs.insert(0,'Market',market);pairs.insert(0,'Ticker',t);pair_frames.append(pairs)
                if cont is not None and not cont.empty:
                    cont=cont.copy();cont.insert(0,'Market',market);cont.insert(0,'Ticker',t);cont_frames.append(cont)
                clean_pairs=pairs[np.isfinite(pd.to_numeric(pairs.get('SignalWin'),errors='coerce')) & np.isfinite(pd.to_numeric(pairs.get('BaselineHitRatePctLOO'),errors='coerce'))] if isinstance(pairs,pd.DataFrame) and not pairs.empty else pd.DataFrame()
                _sig_hr=100*pd.to_numeric(clean_pairs.get('SignalWin'),errors='coerce').mean() if len(clean_pairs) else np.nan
                _base_hr=pd.to_numeric(clean_pairs.get('BaselineHitRatePctLOO'),errors='coerce').mean() if len(clean_pairs) else np.nan
                _lift=(_sig_hr/_base_hr) if np.isfinite(_sig_hr) and np.isfinite(_base_hr) and _base_hr>0 else np.nan
                _exp_delta=pd.to_numeric(clean_pairs.get('ExpectancyEdgePct'),errors='coerce').mean() if len(clean_pairs) else np.nan
                rvals=pd.to_numeric(robust.get('GrossExpectancyPct'),errors='coerce').dropna() if isinstance(robust,pd.DataFrame) and not robust.empty else pd.Series(dtype=float)
                stock_rows.append({'Ticker':t,'Market':market,'15mBars':len(f15),'MatchedSignals':len(pairs) if isinstance(pairs,pd.DataFrame) else 0,
                                   'CleanMatchedSignals':len(clean_pairs),'SignalHitRatePct':_sig_hr,
                                   'MatchedBaselineHitRatePct':_base_hr,
                                   'MatchedHitRateLiftX':_lift,
                                   'MatchedExpectancyDeltaPct':_exp_delta,
                                   'RobustnessPositiveScenarios':int((rvals>0).sum()) if len(rvals) else 0,'RobustnessScenarios':int(len(rvals)),
                                   'ContinuationCandidates':len(cont) if isinstance(cont,pd.DataFrame) else 0,
                                   'ContinuationClean':int(cont['PostBreakoutOutcome'].isin(['TARGET','STOP']).sum()) if isinstance(cont,pd.DataFrame) and not cont.empty else 0,
                                   'ContinuationTargets':int((cont['PostBreakoutOutcome']=='TARGET').sum()) if isinstance(cont,pd.DataFrame) and not cont.empty else 0})
            except Exception as e:
                skipped.append({'Ticker':t,'Reason':f'{type(e).__name__}: {e}'})
            _lab_update_v603(runtime,jid,i,total,t,'Cross-stock research validation')
        pairs_all=pd.concat(pair_frames,ignore_index=True) if pair_frames else pd.DataFrame()
        cont_all=pd.concat(cont_frames,ignore_index=True) if cont_frames else pd.DataFrame()
        summary_rows=[]
        scopes=['ALL']+sorted(pairs_all['Market'].dropna().astype(str).unique().tolist()) if not pairs_all.empty else ['ALL']
        for scope in scopes:
            sub=pairs_all if scope=='ALL' else pairs_all[pairs_all['Market'].astype(str)==scope]
            boot=cluster_bootstrap_matched_edge_v624(sub,n_boot=int(cfg.get('bootstrap_runs',1200)),seed=624)
            bm=dict(zip(boot['Metric'].astype(str),boot['Value'])) if isinstance(boot,pd.DataFrame) and not boot.empty else {}
            cc=cont_all if scope=='ALL' else (cont_all[cont_all['Market'].astype(str)==scope] if not cont_all.empty else pd.DataFrame())
            clean_cont=cc[cc['PostBreakoutOutcome'].isin(['TARGET','STOP'])] if not cc.empty else pd.DataFrame()
            summary_rows.append({'Scope':scope,'Stocks':int(sub['Ticker'].nunique()) if not sub.empty else 0,'CleanMatchedSignals':bm.get('Clean matched signal N',0),
                                 'ClusteredSessionDates':bm.get('Unique clustered session dates',0),'SignalHitRatePct':bm.get('Signal hit rate %',np.nan),
                                 'MatchedBaselineHitRatePct':bm.get('Mean LOO matched baseline hit rate %',np.nan),'HitRateEdgePP':bm.get('Observed matched hit-rate edge pp',np.nan),
                                 'Bootstrap95LowPP':bm.get('Session-cluster bootstrap 95% low pp',np.nan),'Bootstrap95HighPP':bm.get('Session-cluster bootstrap 95% high pp',np.nan),
                                 'BootstrapPValue':bm.get('Bootstrap two-sided p-value',np.nan),'ExpectancyEdgePct':bm.get('Observed expectancy edge % / signal',np.nan),
                                 'ExpectancyBootstrapLowPct':bm.get('Expectancy edge bootstrap 95% low %',np.nan),'ExpectancyBootstrapHighPct':bm.get('Expectancy edge bootstrap 95% high %',np.nan),
                                 'SetupOriginResearchState':bm.get('Research state','NO SAMPLE'),'ContinuationCleanN':len(clean_cont),
                                 'ContinuationTargets':int((clean_cont['PostBreakoutOutcome']=='TARGET').sum()) if len(clean_cont) else 0,
                                 'ContinuationHitRatePct':100*float((clean_cont['PostBreakoutOutcome']=='TARGET').mean()) if len(clean_cont) else np.nan,
                                 'ProductionImpact':'NONE — RESEARCH ONLY'})
        summary=pd.DataFrame(summary_rows); stocks=pd.DataFrame(stock_rows); skipped_df=pd.DataFrame(skipped)
        sheets={'Cross-Stock Summary':summary,'Stock Evidence':stocks,'Setup Origin Session Pairs':pairs_all,'Continuation Events':cont_all,'Skipped':skipped_df}
        excel=workbook_bytes(sheets,{'Tab':'Cross-Stock Research Validator','Version':APP_VERSION,'Scope':cfg.get('scope'),'RequestedStocks':len(tickers),'SuccessfulStocks':len(stock_rows),'TargetPct':100*target,'StopPct':100*stop,'HorizonBars':horizon,'BootstrapRuns':int(cfg.get('bootstrap_runs',1200)),'ProductionImpact':'NONE'})
        _lab_publish_v603(runtime,jid,{'summary':summary,'stocks':stocks,'pairs':pairs_all,'continuation':cont_all,'skipped':skipped_df,'excel':excel})
    except _LabCancelled:_lab_publish_v603(runtime,jid,None,'stopped')
    except Exception as e:_lab_fail_v603(runtime,jid,e)



def _pre_move_signal_families_v627(signal):
    """Map a discovered signal/pair into independent evidence families.

    The goal is candidate ranking, not feature deletion. Correlated variants such
    as MACD cross / MACD histogram turn-positive belong to one MOMENTUM family,
    so they cannot inflate the live Early Signal Score by being counted repeatedly.
    """
    parts=[x.strip() for x in str(signal).split(' + ') if x.strip()]
    fam=[]
    for part in parts:
        u=part.upper()
        if ('MACD' in u) or ('ROC ' in u) or u.startswith('RSI'):
            f='MOMENTUM'
        elif ('RVOL' in u) or ('VOLUME ACCELERATION' in u) or ('DIRECTIONAL BULLISH VOLUME' in u):
            f='VOLUME'
        elif ('OBV ' in u) or ('A/D ' in u) or ('CMF ' in u):
            f='FLOW'
        elif ('RELATIVE STRENGTH' in u):
            f='RELATIVE_STRENGTH'
        elif ('EMA' in u) or ('ADX' in u) or ('PRICE ABOVE EMA20' in u):
            f='TREND'
        elif ('VWAP' in u) or ('BREAKOUT' in u) or ('SQUEEZE' in u) or ('STRONG CLOSE' in u):
            f='STRUCTURE'
        elif ('FRESH TRANSITIONS' in u):
            f='TRANSITION_BREADTH'
        else:
            f='OTHER'
        if f not in fam:fam.append(f)
    return tuple(sorted(fam))


def _pre_move_evidence_signature_v627(a):
    """Compact signature used to collapse materially duplicated OOS evidence."""
    def q(k,nd=3):
        try:
            v=float(a.get(k,np.nan));return round(v,nd) if np.isfinite(v) else None
        except Exception:return None
    return (q('ValidationHitRatePct',2),q('ValidationMatchedBaselinePct',2),int(float(a.get('ValidationSignals',0) or 0)),q('ValidationLiftX',3),str(a.get('OOSState','')))


def _pre_move_freshness_v627(feat, target_pct):
    """How much of the requested future-move size has already occurred recently.

    This is intentionally transparent: the larger of the latest 1D and 2D close
    move is divided by the research target. It is a freshness/chase guard only;
    it does not alter historical OOS labels or Production Entry logic.
    """
    out={'CurrentDayMovePct':np.nan,'Recent2DMovePct':np.nan,'MoveAlreadyConsumedPct':np.nan,'FreshnessState':'NO DATA'}
    if feat is None or not isinstance(feat,pd.DataFrame) or len(feat)<3:return out
    c=pd.to_numeric(feat.get('Close'),errors='coerce').dropna()
    if len(c)<3:return out
    p=float(c.iloc[-1]);p1=float(c.iloc[-2]);p2=float(c.iloc[-3])
    r1=100*(p/p1-1.0) if p1>0 else np.nan
    r2=100*(p/p2-1.0) if p2>0 else np.nan
    target=100*float(target_pct)
    already=max(0.0,*[x for x in (r1,r2) if np.isfinite(x)]) if any(np.isfinite(x) for x in (r1,r2)) else np.nan
    consumed=100*already/target if np.isfinite(already) and target>0 else np.nan
    if not np.isfinite(consumed):state='NO DATA'
    elif consumed<35:state='FRESH'
    elif consumed<60:state='DEVELOPING'
    elif consumed<100:state='LATE'
    else:state='ALREADY MOVED'
    out.update({'CurrentDayMovePct':r1,'Recent2DMovePct':r2,'MoveAlreadyConsumedPct':consumed,'FreshnessState':state})
    return out


def _pre_move_representatives_v627(active, evidence_map):
    """Greedy de-duplication of active OOS signals for one live candidate.

    Only one representative can contribute from a family signature, and rows with
    the same rounded OOS evidence signature are counted once. This prevents dozens
    of correlated MACD/volume variants from behaving like independent votes.
    """
    rows=[]
    for _,rr in active.iterrows():
        sig=str(rr.get('Signal',''));a=dict(evidence_map.get(sig,{}) or {})
        try:vl=float(a.get('ValidationLiftX',np.nan));vh=float(a.get('ValidationHitRatePct',np.nan));vn=float(a.get('ValidationSignals',0) or 0)
        except Exception:continue
        if not (np.isfinite(vl) and np.isfinite(vh) and vn>0):continue
        fam=_pre_move_signal_families_v627(sig);fsig='+'.join(fam) if fam else 'OTHER'
        rows.append({'Signal':sig,'Families':fam,'FamilySignature':fsig,'ValidationLiftX':vl,'ValidationHitRatePct':vh,'ValidationSignals':vn,
                     'ValidationBaselinePct':a.get('ValidationMatchedBaselinePct',np.nan),'OOSState':str(a.get('OOSState','OOS MIXED')),
                     'EvidenceSignature':_pre_move_evidence_signature_v627(a)})
    rows.sort(key=lambda x:(1 if x['OOSState']=='OOS POSITIVE' else 0,x['ValidationLiftX'],x['ValidationSignals']),reverse=True)
    reps=[];seen_fsig=set();seen_evidence=set();covered_families=set()
    for r in rows:
        famset=set(r['Families'])
        if r['FamilySignature'] in seen_fsig:continue
        if r['EvidenceSignature'] in seen_evidence:continue
        # Once a stronger representative already covers all of this signal's
        # families, the weaker signal adds no independent vote. Multi-family
        # signals can still be kept when they introduce at least one new family.
        if famset and famset.issubset(covered_families):continue
        reps.append(r);seen_fsig.add(r['FamilySignature']);seen_evidence.add(r['EvidenceSignature']);covered_families.update(famset)
    return reps


def _pre_move_discovery_worker_v625(runtime,jid,cfg):
    """Cross-stock pre-move discovery with V6.2.7 independent-family ranking."""
    try:
        tickers=list(cfg.get('tickers') or []); target=float(cfg.get('target_pct',.05)); horizon=int(cfg.get('horizon_days',3)); history=str(cfg.get('history','1y'))
        stock_frames=[]; skipped=[]; latest_meta=[]; feature_map={}; total=max(1,len(tickers))
        for i,t in enumerate(tickers,1):
            _lab_check_v603(runtime,jid);_lab_update_v603(runtime,jid,i-1,total,t,f'Daily pre-move research • {history}')
            try:
                d=fetch_ohlcv(t,history,'1d')
                if d is None or len(d)<140: raise ValueError(f'Only {0 if d is None else len(d)} daily rows')
                f=compute_features(d).dropna(subset=['Close','High','Low']).copy();feature_map[str(t)]=f
                z=pre_move_stock_oos_v625(f,target_pct=target,horizon_days=horizon,discovery_fraction=.70)
                if z is None or z.empty: raise ValueError('Not enough chronological discovery/OOS sample')
                market=_market_for_ticker_v612(t); z=z.copy();z.insert(0,'Market',market);z.insert(0,'Ticker',t);stock_frames.append(z)
                lr=f.iloc[-1]; fresh=_pre_move_freshness_v627(f,target)
                latest_meta.append({'Ticker':t,'Market':market,'Price':float(lr.get('Close',np.nan)),
                                    'DailyChangePct':fresh.get('CurrentDayMovePct',np.nan),'Recent2DMovePct':fresh.get('Recent2DMovePct',np.nan),
                                    'MoveAlreadyConsumedPct':fresh.get('MoveAlreadyConsumedPct',np.nan),'FreshnessState':fresh.get('FreshnessState','NO DATA')})
            except Exception as e: skipped.append({'Ticker':t,'Reason':f'{type(e).__name__}: {e}'})
            _lab_update_v603(runtime,jid,i,total,t,'Pre-move discovery / OOS validation')
        raw=pd.concat(stock_frames,ignore_index=True) if stock_frames else pd.DataFrame()
        min_d=int(cfg.get('min_discovery_signals',25)); min_v=int(cfg.get('min_validation_signals',12)); min_l=float(cfg.get('min_discovery_lift',1.20))
        global_summary=aggregate_pre_move_oos_v625(raw,min_discovery_signals=min_d,min_validation_signals=min_v,min_discovery_lift=min_l)
        summaries=[]
        if not raw.empty:
            for scope,g in [('ALL',raw)]+[(m,raw[raw['Market'].astype(str)==m]) for m in sorted(raw['Market'].dropna().astype(str).unique())]:
                ssum=aggregate_pre_move_oos_v625(g,min_discovery_signals=max(10,min_d if scope=='ALL' else max(10,min_d//2)),min_validation_signals=max(6,min_v if scope=='ALL' else max(6,min_v//2)),min_discovery_lift=min_l)
                if not ssum.empty:ssum.insert(0,'Scope',scope);summaries.append(ssum)
        evidence=pd.concat(summaries,ignore_index=True) if summaries else global_summary.copy()
        if isinstance(evidence,pd.DataFrame) and not evidence.empty:
            evidence=evidence.copy();evidence['SignalFamilies']=evidence['Signal'].map(lambda x:' + '.join(_pre_move_signal_families_v627(x)))
            evidence['FamilySignature']=evidence['Signal'].map(lambda x:'+'.join(_pre_move_signal_families_v627(x)))
        # Current-candidate ranking uses only discovery-selected signals that did not fail OOS.
        accepted=global_summary[global_summary['OOSState'].isin(['OOS POSITIVE','OOS MIXED'])].copy() if isinstance(global_summary,pd.DataFrame) and not global_summary.empty else pd.DataFrame()
        candidates=[];candidate_audit=[];latest_df=pd.DataFrame(latest_meta)
        if not accepted.empty and not raw.empty:
            amap=accepted.set_index('Signal').to_dict('index')
            accepted_set=set(amap)
            for t,g in raw.groupby('Ticker'):
                active=g[(g['CurrentActive']==True)&g['Signal'].isin(accepted_set)].copy()
                if active.empty:continue
                reps=_pre_move_representatives_v627(active,amap)
                if not reps:continue
                fam_union=sorted(set(f for r in reps for f in r['Families']))
                positive_fam=sorted(set(f for r in reps if r['OOSState']=='OOS POSITIVE' for f in r['Families']))
                positive_reps=[r for r in reps if r['OOSState']=='OOS POSITIVE']
                vals=[]
                for r in reps:
                    factor=1.0 if r['OOSState']=='OOS POSITIVE' else .40
                    w=max(.03,r['ValidationLiftX']-1.0)*max(1.0,math.sqrt(max(1.0,r['ValidationSignals'])))*factor
                    vals.append((r,w))
                wsum=sum(w for _,w in vals);prob=sum(r['ValidationHitRatePct']*w for r,w in vals)/wsum if wsum>0 else np.nan
                best=max(r['ValidationLiftX'] for r in reps); sample=sum(r['ValidationSignals'] for r in reps[:5]); fam_n=len(fam_union);pos_fam_n=len(positive_fam)
                raw_active=int(len(active));rep_n=len(reps);dup_removed=max(0,raw_active-rep_n)
                lift_comp=min(1,max(0,(best-1)/.8));sample_comp=min(1,math.log1p(sample)/math.log1p(160));breadth_comp=min(1,fam_n/4);pos_comp=min(1,pos_fam_n/3)
                raw_score=100*(.35*lift_comp+.20*sample_comp+.30*breadth_comp+.15*pos_comp)
                meta=latest_df[latest_df['Ticker'].astype(str)==str(t)];m=meta.iloc[-1].to_dict() if not meta.empty else {}
                consumed=float(m.get('MoveAlreadyConsumedPct',np.nan)) if np.isfinite(float(m.get('MoveAlreadyConsumedPct',np.nan))) else np.nan
                freshness=str(m.get('FreshnessState','NO DATA'))
                freshness_mult=1.0 if freshness=='FRESH' else (.88 if freshness=='DEVELOPING' else (.55 if freshness=='LATE' else (.30 if freshness=='ALREADY MOVED' else .75)))
                score=float(raw_score*freshness_mult)
                core=bool('MOMENTUM' in fam_union and ('VOLUME' in fam_union or 'FLOW' in fam_union))
                strong_positive=bool(pos_fam_n>=2 and len(positive_reps)>=2)
                if freshness in ('LATE','ALREADY MOVED'):
                    stage='LATE / ALREADY MOVED'
                elif score>=72 and fam_n>=3 and pos_fam_n>=3 and core and best>=1.30:
                    stage='STRONG PRE-MOVE CANDIDATE'
                elif score>=58 and fam_n>=2 and strong_positive and (core or fam_n>=3) and best>=1.20:
                    stage='PRE-MOVE CANDIDATE'
                elif score>=35 and fam_n>=2:
                    stage='BUILDING'
                else:
                    stage='WATCH'
                strongest=' | '.join(r['Signal'] for r in reps[:4])
                candidates.append({'Ticker':t,'Market':m.get('Market',g.iloc[0].get('Market','')),'Price':m.get('Price',np.nan),
                                   'CurrentDayMovePct':m.get('DailyChangePct',np.nan),'Recent2DMovePct':m.get('Recent2DMovePct',np.nan),
                                   'MoveAlreadyConsumedPct':round(consumed,1) if np.isfinite(consumed) else np.nan,'FreshnessState':freshness,
                                   'RawPreMoveScore':round(float(raw_score),1),'PreMoveScore':round(float(score),1),'PreMoveStage':stage,
                                   'RawEarlySignalScore':round(float(raw_score),1),'EarlySignalScore':round(float(score),1),'EarlyStage':stage,
                                   'PreMoveProbabilityPct':round(float(prob),1) if np.isfinite(prob) else np.nan,
                                   'RawActiveValidatedSignals':raw_active,'RepresentativeSignals':rep_n,'DuplicateCorrelatedSignalsRemoved':dup_removed,
                                   'IndependentFamilyCount':fam_n,'PositiveOOSFamilyCount':pos_fam_n,'CoreMomentumVolumeConfirmed':core,
                                   'IndependentFamilies':' | '.join(fam_union),'BestOOSLiftX':round(float(best),2),'OOSValidationSignalNTop5':int(sample),
                                   'StrongestIndependentFeatures':strongest,'TargetHorizon':f'+{100*target:g}% within {horizon}D','ResearchOnly':True})
                for rank,r in enumerate(reps,1):
                    candidate_audit.append({'Ticker':t,'RepresentativeRank':rank,'Signal':r['Signal'],'FamilySignature':r['FamilySignature'],
                                            'Families':' | '.join(r['Families']),'OOSState':r['OOSState'],'ValidationLiftX':r['ValidationLiftX'],
                                            'ValidationHitRatePct':r['ValidationHitRatePct'],'ValidationBaselinePct':r.get('ValidationBaselinePct',np.nan),
                                            'ValidationSignals':r['ValidationSignals'],'UsedInLiveCandidateScore':True})
        cand=pd.DataFrame(candidates)
        if not cand.empty:
            stage_order={'STRONG PRE-MOVE CANDIDATE':0,'PRE-MOVE CANDIDATE':1,'BUILDING':2,'WATCH':3,'LATE / ALREADY MOVED':4}
            cand['_ord']=cand['EarlyStage'].map(stage_order).fillna(9)
            cand=cand.sort_values(['_ord','EarlySignalScore','BestOOSLiftX','IndependentFamilyCount'],ascending=[True,False,False,False]).drop(columns=['_ord']).reset_index(drop=True)
        audit_df=pd.DataFrame(candidate_audit);skipped_df=pd.DataFrame(skipped)
        sheets={'Pre-Move OOS Evidence':evidence,'Current Candidates':cand,'Candidate Family Audit':audit_df,'Per-Stock Signal Audit':raw,'Skipped':skipped_df}
        excel=workbook_bytes(sheets,{'Tab':'Pre-Move OOS Discovery','Version':APP_VERSION,'Scope':cfg.get('scope'),'History':history,'RequestedStocks':len(tickers),'SuccessfulStocks':len(stock_frames),'TargetPct':100*target,'HorizonDays':horizon,'DiscoverySplit':'70%','ValidationSplit':'30%','MinDiscoverySignals':min_d,'MinValidationSignals':min_v,'MinDiscoveryLiftX':min_l,'CandidateRanking':'Independent families + correlated-signal de-dup + recent-move freshness guard + research-stage naming','ProductionImpact':'NONE — RESEARCH ONLY; Scanner/Analyze live entry remains separate'})
        _persist_pre_move_overlay_v628(cand,cfg)
        _lab_publish_v603(runtime,jid,{'evidence':evidence,'global_summary':global_summary,'candidates':cand,'candidate_audit':audit_df,'raw':raw,'skipped':skipped_df,'excel':excel})
    except _LabCancelled:_lab_publish_v603(runtime,jid,None,'stopped')
    except Exception as e:_lab_fail_v603(runtime,jid,e)


# -----------------------------------------------------------------------------
# V6.3.8 Market-specific Regular Radar -> Scanner overlay
# Each completed Regular Signature Lab stores the latest radar by exchange.  The
# Scanner merges the strongest validated row per ticker beside Pre-Move and live
# Entry.  This remains research evidence; it never bypasses production gates.
# -----------------------------------------------------------------------------
_REGULAR_SIG_CACHE_PATH_V638=Path('regular_signature_latest_v638.json')


def _persist_regular_signature_overlay_v638(radar,cfg):
    try:
        db={}
        if _REGULAR_SIG_CACHE_PATH_V638.exists():
            db=json.loads(_REGULAR_SIG_CACHE_PATH_V638.read_text(encoding='utf-8')) or {}
        r=radar.copy() if isinstance(radar,pd.DataFrame) else pd.DataFrame(radar)
        if r.empty:return
        for market,g in r.groupby('Market'):
            clean=g.replace({np.nan:None}).to_dict('records')
            db[str(market)]={'version':APP_VERSION,'saved_epoch':time_module.time(),'completed_label':datetime.now().strftime('%Y-%m-%d %H:%M:%S'),'config':dict(cfg or {}),'radar':clean}
        _REGULAR_SIG_CACHE_PATH_V638.write_text(json.dumps(db,ensure_ascii=False,default=str),encoding='utf-8')
        try:
            con=_feedback_conn_v600()
            for market,entry in db.items():
                con.execute('INSERT OR REPLACE INTO regular_signature_cache(market,saved_epoch,completed_label,version,config_json,radar_json) VALUES(?,?,?,?,?,?)',(str(market),float(entry.get('saved_epoch',time_module.time())),str(entry.get('completed_label','—')),str(entry.get('version',APP_VERSION)),json.dumps(entry.get('config') or {},ensure_ascii=False,default=str),json.dumps(entry.get('radar') or [],ensure_ascii=False,default=str)))
            con.commit();con.close();_feedback_schedule_remote_push_v630()
        except Exception:pass
    except Exception:pass


def _latest_regular_signature_registry_v638():
    db={}
    try:
        con=_feedback_conn_v600();rows=con.execute('SELECT market,saved_epoch,completed_label,version,config_json,radar_json FROM regular_signature_cache').fetchall();con.close()
        for market,saved,completed,version,cfgj,radj in rows:
            try:db[str(market)]={'version':version,'saved_epoch':float(saved),'completed_label':completed,'config':json.loads(cfgj or '{}'),'radar':json.loads(radj or '[]')}
            except Exception:continue
    except Exception:pass
    try:
        if _REGULAR_SIG_CACHE_PATH_V638.exists():
            local=json.loads(_REGULAR_SIG_CACHE_PATH_V638.read_text(encoding='utf-8')) or {}
            for market,entry in local.items():
                if market not in db or float(entry.get('saved_epoch',0) or 0)>float(db[market].get('saved_epoch',0) or 0):db[market]=entry
    except Exception:pass
    # Prefer/merge the latest completed in-memory run as well.
    try:
        active,last=_lab_snapshot_v603('regular_signature');snap=last if last and last.get('payload') else (active if active and active.get('payload') and active.get('status')=='completed' else None)
        if snap and snap.get('payload'):
            rr=snap['payload'].get('radar');rr=rr.copy() if isinstance(rr,pd.DataFrame) else pd.DataFrame(rr)
            cfg=dict(snap.get('config') or {})
            if not rr.empty:
                for market,g in rr.groupby('Market'):
                    db[str(market)]={'version':APP_VERSION,'saved_epoch':float(snap.get('finished_at') or time_module.time()),'completed_label':snap.get('completed_label','—'),'config':cfg,'radar':g.replace({np.nan:None}).to_dict('records')}
    except Exception:pass
    return db


def _regular_stage_order_v638(x):
    return {'RESEARCH HIGH CONFIDENCE':0,'FRESH QUALIFIED — HC NOT VALIDATED':1,'+ FRESH / NOT LATE':2,'+ SETUP >= 70':3,'CONSENSUS 2+':4,'ANY PROMOTED COMBO':5,'NO VALIDATED FUNNEL':6,'NO CURRENT FUNNEL MATCH':7}.get(str(x),8)


def _attach_regular_signature_overlay_v638(df):
    if df is None or not isinstance(df,pd.DataFrame) or df.empty:return df
    z=df.copy();old=[c for c in z.columns if str(c).startswith('RegularRadar') or str(c).startswith('RegularFunnel') or str(c).startswith('RegularModel')]
    if old:z=z.drop(columns=old,errors='ignore')
    db=_latest_regular_signature_registry_v638();frames=[]
    for market,entry in db.items():
        rr=pd.DataFrame(entry.get('radar') or [])
        if rr.empty:continue
        rr['_saved_epoch']=float(entry.get('saved_epoch',np.nan));rr['_completed']=entry.get('completed_label','—');frames.append(rr)
    if not frames:
        z.attrs['regular_signature_markets']=[];return z
    r=pd.concat(frames,ignore_index=True);r['Ticker']=r['Ticker'].astype(str).str.upper();r['_ord']=r.get('Funnel Stage',pd.Series('',index=r.index)).map(_regular_stage_order_v638)
    for c in ['Final Holdout Lift x','Regular Signature Score','Best OOS Lift x']:r[c]=pd.to_numeric(r.get(c,np.nan),errors='coerce')
    r=r.sort_values(['Ticker','_ord','Final Holdout Lift x','Regular Signature Score','Best OOS Lift x'],ascending=[True,True,False,False,False]).drop_duplicates('Ticker',keep='first')
    out=pd.DataFrame({'Ticker':r.Ticker})
    mapping={'Target %':'RegularRadarTargetPct','Lead Window':'RegularRadarLeadWindow','Timeframe':'RegularRadarTimeframe','Regular Signature Score':'RegularRadarScore','OOS Positive Matches':'RegularRadarOOSMatches','Best OOS Hit Rate %':'RegularRadarHitRatePct','Best OOS Baseline %':'RegularRadarBaselinePct','Best OOS Lift x':'RegularRadarLiftX','Best Signature':'RegularRadarBestSignature','Setup Score':'RegularRadarSetupScore','Freshness':'RegularRadarFreshness','Distribution Risk':'RegularRadarDistributionRisk','Independent Family Count':'RegularRadarFamilyCount','Move Consumed %':'RegularRadarMoveConsumedPct','Funnel Stage':'RegularFunnelStage','Funnel Promoted Matches':'RegularFunnelMatches','Funnel Family Count':'RegularFunnelFamilyCount','Final Holdout N':'RegularFunnelFinalN','Final Holdout Hit Rate %':'RegularFunnelFinalHitRatePct','Final Holdout Baseline %':'RegularFunnelFinalBaselinePct','Final Holdout Lift x':'RegularFunnelFinalLiftX','Final Holdout Status':'RegularFunnelFinalStatus','Best Validated Funnel Stage':'RegularFunnelBestValidatedStage','Market':'RegularModelMarket'}
    for src,dst in mapping.items():
        if src in r.columns:out[dst]=r[src].values
    out['RegularModelRunCompleted']=r['_completed'].values;out['RegularModelAgeHours']=[max(0,(time_module.time()-float(v))/3600) if np.isfinite(float(v)) else np.nan for v in r['_saved_epoch']]
    z['Ticker']=z['Ticker'].astype(str).str.upper();z=z.merge(out,on='Ticker',how='left')
    # Live confirmation is deliberately separate from the historical research funnel.
    research=z.get('RegularFunnelStage',pd.Series('',index=z.index)).astype(str)
    entry=z.get('EntryTriggerState',pd.Series('',index=z.index)).astype(str);hourly=z.get('HourlyEntryCheck',pd.Series(False,index=z.index)).fillna(False).astype(bool);flow=z.get('VolumeFlowCheck',pd.Series(False,index=z.index)).fillna(False).astype(bool);nochase=z.get('NoChaseCheck',pd.Series(False,index=z.index)).fillna(False).astype(bool);ext=z.get('ExtensionGuardCheck',pd.Series(True,index=z.index)).fillna(True).astype(bool);rr=z.get('LiveRRGuardOK',pd.Series(True,index=z.index)).fillna(True).astype(bool)
    z['RegularFunnelLiveLayer']=np.where(research.eq('RESEARCH HIGH CONFIDENCE') & entry.eq('CONFIRMED ENTRY'),'RESEARCH HC + LIVE CONFIRMED',np.where(research.isin(['RESEARCH HIGH CONFIDENCE','FRESH QUALIFIED — HC NOT VALIDATED']) & hourly & flow & nochase & ext & rr,'RESEARCH STRONG + LIVE GATES','RESEARCH / WAIT'))
    z.attrs['regular_signature_markets']=sorted(db.keys());return z


def _render_regular_signature_overlay_status_v638():
    db=_latest_regular_signature_registry_v638()
    if not db:
        st.caption('📡 Regular market-specific radar: not loaded. Run Feedback → Regular Pre-Move Signature Lab for each market you want available in Scanner.')
        return
    parts=[]
    for m,e in sorted(db.items()):
        age=max(0,(time_module.time()-float(e.get('saved_epoch',time_module.time())))/3600);parts.append(f"{m} ({age:.1f}h old)")
    st.caption('📡 Regular market-specific radar loaded: '+ ' • '.join(parts) + '. Historical funnel evidence is separate from live Entry confirmation.')

# -----------------------------------------------------------------------------
# V6.2.8 Pre-Move -> Scanner two-layer overlay
# The Pre-Move lab is a research radar, never a trade trigger. The latest completed
# candidate table is merged into Scanner at render/export time so the user can see
# "research setup" and "live entry state" side by side without changing Production
# ranking, Entry Trigger, Chase Guard, or Live R:R.
# -----------------------------------------------------------------------------
_PREMOVE_CACHE_PATH_V628 = Path("pre_move_latest_v628.json")


def _persist_pre_move_overlay_v628(candidates, cfg, completed_label=None):
    try:
        c = candidates.copy() if isinstance(candidates, pd.DataFrame) else pd.DataFrame(candidates)
        c = c.replace({np.nan: None})
        payload = {
            'version': APP_VERSION,
            'completed_label': completed_label or datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'saved_epoch': time_module.time(),
            'config': dict(cfg or {}),
            'candidates': c.to_dict('records'),
        }
        _PREMOVE_CACHE_PATH_V628.write_text(json.dumps(payload, ensure_ascii=False, default=str), encoding='utf-8')
    except Exception:
        pass


def _latest_pre_move_snapshot_v628():
    # Prefer the in-memory completed job because it is guaranteed to match this build.
    try:
        active, last = _lab_snapshot_v603('pre_move')
        snap = last if last and last.get('payload') else (active if active and active.get('payload') and active.get('status') == 'completed' else None)
        if snap and snap.get('payload'):
            cand = snap['payload'].get('candidates')
            cand = cand.copy() if isinstance(cand, pd.DataFrame) else pd.DataFrame(cand)
            cfg = dict(snap.get('config') or {})
            finished = snap.get('finished_at')
            age_h = max(0.0, (time_module.time()-float(finished))/3600.0) if finished else np.nan
            return cand, {
                'source':'LAST COMPLETED PRE-MOVE RUN',
                'completed_label':snap.get('completed_label','—'),
                'age_hours':age_h,
                'scope':cfg.get('scope','—'),
                'target_pct':100*float(cfg.get('target_pct',np.nan)) if cfg.get('target_pct') is not None else np.nan,
                'horizon_days':cfg.get('horizon_days',np.nan),
                'history':cfg.get('history','—'),
            }
    except Exception:
        pass
    # Small best-effort local cache survives normal Streamlit reruns/process refreshes.
    try:
        if _PREMOVE_CACHE_PATH_V628.exists():
            p=json.loads(_PREMOVE_CACHE_PATH_V628.read_text(encoding='utf-8'))
            cand=pd.DataFrame(p.get('candidates') or [])
            cfg=dict(p.get('config') or {})
            saved=float(p.get('saved_epoch',np.nan))
            age_h=max(0.0,(time_module.time()-saved)/3600.0) if np.isfinite(saved) else np.nan
            return cand, {
                'source':'LOCAL PRE-MOVE CACHE',
                'completed_label':p.get('completed_label','—'),
                'age_hours':age_h,
                'scope':cfg.get('scope','—'),
                'target_pct':100*float(cfg.get('target_pct',np.nan)) if cfg.get('target_pct') is not None else np.nan,
                'horizon_days':cfg.get('horizon_days',np.nan),
                'history':cfg.get('history','—'),
            }
    except Exception:
        pass
    return pd.DataFrame(), {}


def _attach_pre_move_overlay_v628(df):
    if df is None or not isinstance(df,pd.DataFrame) or df.empty:
        return df
    z=df.copy()
    # Remove any older overlay columns before attaching the newest research snapshot.
    old=[c for c in z.columns if str(c).startswith('PreMove')]
    if old:z=z.drop(columns=old,errors='ignore')
    cand,meta=_latest_pre_move_snapshot_v628()
    if cand is None or not isinstance(cand,pd.DataFrame) or cand.empty or 'Ticker' not in cand.columns:
        z.attrs['pre_move_meta']=meta
        return z
    rename={
        'PreMoveStage':'PreMoveStage','EarlyStage':'PreMoveStage',
        'PreMoveScore':'PreMoveScore','EarlySignalScore':'PreMoveScore',
        'PreMoveProbabilityPct':'PreMoveProbabilityPct','FreshnessState':'PreMoveFreshness',
        'MoveAlreadyConsumedPct':'PreMoveMoveConsumedPct','IndependentFamilyCount':'PreMoveIndependentFamilyCount',
        'PositiveOOSFamilyCount':'PreMovePositiveOOSFamilyCount','CoreMomentumVolumeConfirmed':'PreMoveCoreConfirmed',
        'IndependentFamilies':'PreMoveIndependentFamilies','BestOOSLiftX':'PreMoveBestOOSLiftX',
        'OOSValidationSignalNTop5':'PreMoveOOSSignalNTop5','StrongestIndependentFeatures':'PreMoveStrongestFeatures',
        'TargetHorizon':'PreMoveTargetHorizon','ResearchOnly':'PreMoveResearchOnly'
    }
    # Prefer the new V6.2.8 names when both legacy and new aliases exist.
    keep=['Ticker']
    for src,dst in rename.items():
        if src in cand.columns and dst not in [rename.get(k) for k in keep]:
            keep.append(src)
    pm=cand[keep].copy()
    # Resolve duplicate source columns that rename to the same destination.
    ordered=['Ticker','PreMoveStage','PreMoveScore','PreMoveProbabilityPct','PreMoveFreshness','PreMoveMoveConsumedPct',
             'PreMoveIndependentFamilyCount','PreMovePositiveOOSFamilyCount','PreMoveCoreConfirmed','PreMoveIndependentFamilies',
             'PreMoveBestOOSLiftX','PreMoveOOSSignalNTop5','PreMoveStrongestFeatures','PreMoveTargetHorizon','PreMoveResearchOnly']
    out=pd.DataFrame({'Ticker':pm['Ticker'].astype(str).str.upper()})
    for dst in ordered[1:]:
        sources=[src for src,d in rename.items() if d==dst and src in pm.columns]
        if sources:
            series=pm[sources[0]]
            for src in sources[1:]:series=series.where(series.notna(),pm[src])
            out[dst]=series.values
    out=out.drop_duplicates('Ticker',keep='first')
    out['PreMoveRunCompleted']=meta.get('completed_label','—')
    out['PreMoveRunAgeHours']=meta.get('age_hours',np.nan)
    out['PreMoveModelScope']=meta.get('scope','—')
    out['PreMoveModelTargetPct']=meta.get('target_pct',np.nan)
    out['PreMoveModelHorizonDays']=meta.get('horizon_days',np.nan)
    out['PreMoveModelHistory']=meta.get('history','—')
    z['Ticker']=z['Ticker'].astype(str).str.upper()
    z=z.merge(out,on='Ticker',how='left')
    if 'PreMoveStage' in z:
        z['PreMoveStage']=z['PreMoveStage'].fillna('NO CURRENT PRE-MOVE CANDIDATE')
    z.attrs['pre_move_meta']=meta
    return z


def _render_pre_move_overlay_status_v628():
    cand,meta=_latest_pre_move_snapshot_v628()
    if cand is None or not isinstance(cand,pd.DataFrame) or cand.empty:
        st.caption('🔭 Pre-Move research radar: no completed candidate run is loaded. Run Optimizer → Pre-Move OOS Discovery to add the research layer to Scanner.')
        return
    tgt=meta.get('target_pct',np.nan); hor=meta.get('horizon_days',np.nan); age=meta.get('age_hours',np.nan)
    tgt_txt=f'+{float(tgt):g}%' if pd.notna(tgt) else '—'; hor_txt=f'{int(hor)}D' if pd.notna(hor) else '—'; age_txt=f'{float(age):.1f}h old' if pd.notna(age) else 'age unknown'
    st.caption(f"🔭 Pre-Move research radar loaded • {meta.get('scope','—')} • {tgt_txt} within {hor_txt} • run {meta.get('completed_label','—')} ({age_txt}). Research radar ≠ live trade trigger.")

def _coerce_dataframe_v608(obj):
    """Normalize cached/legacy payload objects before UI rendering."""
    if isinstance(obj, pd.DataFrame):
        return obj
    if obj is None:
        return pd.DataFrame()
    if isinstance(obj, pd.Series):
        return obj.to_frame()
    if isinstance(obj, dict):
        try:
            return pd.DataFrame(obj)
        except ValueError:
            return pd.DataFrame([obj])
    try:
        return pd.DataFrame(obj)
    except Exception:
        return pd.DataFrame()


def _render_dataframe_safe_v608(obj, empty_message):
    """Render a DataFrame without allowing a legacy/cached object to crash Analyze."""
    df = _coerce_dataframe_v608(obj)
    if df.empty:
        st.info(empty_message)
        return
    try:
        st.dataframe(df, use_container_width=True, hide_index=True)
    except AttributeError:
        # Last-resort rendering path for Streamlit/Pandas compatibility edge cases.
        st.markdown(df.to_html(index=False, escape=True), unsafe_allow_html=True)


def _render_scanner_top_excel_v624(slot, show_mode, market_filter, timing_filter="ALL", quality_filter="ALL", risk_filter="ALL"):
    runtime=_scanner_runtime_v599()
    with runtime['lock']:
        last=runtime.get('last_completed')
    with slot.container():
        if not last or not isinstance(last.get('result'),pd.DataFrame):
            st.caption('⬇️ Excel download will appear here after the first completed scan.')
            return
        full=_attach_regular_signature_overlay_v638(_attach_pre_move_overlay_v628(last.get('result')));full=_ensure_decision_ranking_v63919(full,str((last.get('config') or {}).get('scan_mode','Production 151')));full=_decision_board_enrich_v63948(full);full=_signal_memory_enrich_v63955(full);res=_filter_scanner_results_v599(full,show_mode,market_filter,timing_filter,quality_filter,risk_filter);meta=last.get('meta') or {}
        if res is None or res.empty:
            st.caption('⬇️ Excel: current Scanner filter has no rows to export.')
            return
        st.download_button('⬇️ Download Scanner Excel',data=scanner_excel_bytes(res,meta),file_name=f"AI_Stock_Hunter_V{APP_VERSION}_scan_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',use_container_width=True,key='scanner_excel_top_v624')


def _render_optimizer_top_excel_v625(slot):
    _,entry_last=_lab_snapshot_v603('entry');entry_active,_=_lab_snapshot_v603('entry')
    _,rv_last=_lab_snapshot_v603('research_validator');rv_active,_=_lab_snapshot_v603('research_validator')
    _,pm_last=_lab_snapshot_v603('pre_move');pm_active,_=_lab_snapshot_v603('pre_move')
    ep=(entry_active.get('payload') if entry_active and entry_active.get('payload') else (entry_last.get('payload') if entry_last else None))
    rp=(rv_active.get('payload') if rv_active and rv_active.get('payload') else (rv_last.get('payload') if rv_last else None))
    pp=(pm_active.get('payload') if pm_active and pm_active.get('payload') else (pm_last.get('payload') if pm_last else None))
    with slot.container():
        available=[]
        if ep and ep.get('excel'):
            _ers=str(ep.get('run_status','COMPLETED'))
            available.append(('Optimizer Diagnostics' if _ers.startswith('FAILED') else 'Optimizer',ep.get('excel')))
        if rp and rp.get('excel'):available.append(('Cross-Stock Research',rp.get('excel')))
        if pp and pp.get('excel'):available.append(('Pre-Move Discovery',pp.get('excel')))
        if not available:
            st.caption('⬇️ Excel downloads will appear here after a completed Optimizer, Cross-Stock Research or Pre-Move run.')
            return
        cols=st.columns(len(available))
        for c,(label,data) in zip(cols,available):
            with c:st.download_button(f'⬇️ {label} Excel',data=data,file_name=f"AI_Stock_Hunter_V{APP_VERSION}_{label.replace(' ','_')}_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',use_container_width=True,key=f"top_opt_{label}_v625")


tab_scan,tab_analyze,tab_optimizer,tab_feedback=st.tabs(['🔎 Scanner','📈 Analyze','🧠 Optimizer','🔄 Feedback'])
with tab_scan:
    st.markdown("<div class='section'>🔎 Scanner — live opportunity discovery</div>",unsafe_allow_html=True)
    scanner_excel_top=st.empty()
    _render_market_status_badges_v612()
    st.caption("Session badges use each exchange's local clock. OPEN/PRE/AFTER status is shown separately from the model's entry signal.")
    _render_pre_move_overlay_status_v628();_render_regular_signature_overlay_status_v638()
    m1,m2=st.columns(2)
    model_mode=m1.radio("Decision model",["PRODUCTION","OOS OPTIMIZED"],horizontal=True,key="decision_model_v63948")
    scan_depth=m2.radio("Scan depth",["SMART","FULL"],horizontal=True,key="scan_depth_v63948",help="SMART = broad Stage-0 discovery, then market-balanced deep analysis of the strongest candidates. FULL = deep-analyze every Stage-0 candidate selected by discovery / every requested curated ticker.")
    scan_mode="Production 151" if model_mode=="PRODUCTION" else "Optimized 151"
    coverage=st.selectbox("Coverage",["MARKET DISCOVERY","CURATED 352","CORE 151","CUSTOM","ADVANCED PRESET"],0,key="scanner_coverage_v63948",help="MARKET DISCOVERY starts from a broad live market list instead of the fixed curated universe. The cheap Stage-0 shortlist is research/pre-filter only; all final decisions still use the normal Daily + 1H + 15m engine.")
    markets_to_scan=st.multiselect("Markets to scan",["US","HONG KONG","TEL AVIV"],default=["US","HONG KONG","TEL AVIV"],key="scanner_markets_v63948")
    universe_mode=st.radio("Display market",["ALL","US","HONG KONG","TEL AVIV"],horizontal=True,key="scanner_market_v63948")
    def _join_uni_v63948(parts):
        return ','.join(dict.fromkeys(x for part in parts for x in str(part).split(',') if x))
    _parts=[]
    if coverage=="CURATED 352":
        if "US" in markets_to_scan:_parts.append(US_201)
        if "HONG KONG" in markets_to_scan:_parts.append(HK_101)
        if "TEL AVIV" in markets_to_scan:_parts.append(TASE_50)
        scan_universe=_join_uni_v63948(_parts)
    elif coverage=="CORE 151":
        if "US" in markets_to_scan:_parts.append(US_51)
        if "HONG KONG" in markets_to_scan:_parts.append(HK_50)
        if "TEL AVIV" in markets_to_scan:_parts.append(TASE_50)
        scan_universe=_join_uni_v63948(_parts)
    elif coverage=="CUSTOM":
        scan_universe=st.text_area("Custom tickers",DEFAULT_TICKERS,height=100,key="custom_scanner_v63948")
    elif coverage=="ADVANCED PRESET":
        _adv=st.selectbox("Advanced universe preset",["NASDAQ 50","NASDAQ 100","NASDAQ 200","US 201","HONG KONG 50","HONG KONG 101","TEL AVIV 50","ALL 352"],key="scanner_advanced_universe_v63948")
        scan_universe={"NASDAQ 50":NASDAQ_50,"NASDAQ 100":NASDAQ_100,"NASDAQ 200":NASDAQ_200,"US 201":US_201,"HONG KONG 50":HK_50,"HONG KONG 101":HK_101,"TEL AVIV 50":TASE_50,"ALL 352":VALIDATION_352}[_adv]
    else:
        scan_universe=''
    market_discovery=(coverage=="MARKET DISCOVERY")
    if market_discovery:
        _disc_cap=55+35*max(1,len(markets_to_scan))
        prefilter_top=_disc_cap if scan_depth=="SMART" else 999999
        st.caption(f"MARKET DISCOVERY • broad Stage-0 list for {', '.join(markets_to_scan) if markets_to_scan else 'no markets selected'} • {('SMART deep cap ≈ '+str(_disc_cap)) if scan_depth=='SMART' else 'FULL deep analysis of every Stage-0 candidate'}. Stage-0 is market-wide discovery, not the old fixed 352-name list.")
    else:
        universe_n=len([x for x in scan_universe.split(',') if x.strip()])
        prefilter_top=universe_n if scan_depth=="FULL" else min(universe_n,max(40,min(160,int(math.ceil(universe_n*.60)))))
        st.caption(f"{coverage} • requested {universe_n} • deep analysis {prefilter_top} ({scan_depth}).")
    c1,c2,c3=st.columns(3);sh=c1.selectbox("History",["3mo","6mo","1y"],1,key="sh_v613");ho=c2.selectbox("Forecast horizon",[1,2,3,5,7,10],2,key="ho_v613");ta=c3.selectbox("Target %",[1,2,3,4,5,6,8,10],2,key="ta_v613")
    registry=_load_model_registry_v613();model_horizon=None;model={}
    promoted_hourly_model=_select_promoted_hourly_model_v63945(registry,3.0)
    if model_mode=="PRODUCTION" and _active_model_has_any_v63945(promoted_hourly_model):
        _hm=sorted((promoted_hourly_model.get('selected_hourly_models',{}) or {}).keys())
        st.info("Production Daily/Core + promoted 1Y Hourly OOS timing active"+(" for: "+", ".join(_hm) if _hm else "")+". Only SHADOW ELIGIBLE hourly models are used.")
    if model_mode=="OOS OPTIMIZED":
        model_horizon_choice=st.selectbox("Optimized model horizon",["AUTO VALIDATED BY MARKET","MATCH FORECAST HORIZON"],0,key="optimized_horizon_v63915",help="AUTO uses the newest SHADOW ELIGIBLE 1Y run in the most-specific market tier. Fold4 lift is eligibility-only and is not used to rank models.")
        model_horizon=None if model_horizon_choice.startswith('AUTO') else int(ho);model=_select_active_model_v613(registry,model_horizon,float(ta))
        sel=_registry_selection_frame_v613(model);hlabel='AUTO VALIDATED BY MARKET' if model_horizon is None else f'{int(ho)}D'
        if _active_model_has_any_v63945(model):
            st.caption(f"Model Registry: {len(registry.get('models',[]))} saved optimization run(s). V6.3.9.46 activates eligible Hourly OOS timing independently; Daily/Core weights change only where a Daily SHADOW ELIGIBLE model exists for +{float(ta):g}% / {hlabel}.")
            if not sel.empty:st.dataframe(sel,use_container_width=True,hide_index=True)
            hourly_only=[m for m in ('NASDAQ','HONG KONG','TEL AVIV') if m in model.get('hourly_scopes',{}) and m not in model.get('scopes',{})]
            if hourly_only:st.info("Hourly-only OOS timing active for: "+", ".join(hourly_only)+". Daily/Core scoring stays on Production weights for those markets.")
            missing=[m for m in ('NASDAQ','HONG KONG','TEL AVIV') if m not in model.get('scopes',{}) and m not in model.get('hourly_scopes',{})]
            if missing:st.warning("No eligible Daily or Hourly OOS model for: "+", ".join(missing)+". Those markets use Production timing/scoring.")
        else:
            st.error(f"No SHADOW ELIGIBLE Daily or Hourly OOS model is available. Run/import Optimizer evidence or use PRODUCTION.")
    primary_show=st.selectbox("Decision stage",["ALL","BUILDING SETUP","ARMED","ARMED BLOCKED","ENTRY NOW","LAST SESSION ENTRY","RETEST","TOO LATE","RESEARCH"],key="show_primary_v63948")
    if primary_show=="RESEARCH":
        show_mode=st.selectbox("Research view",["RESEARCH ALL","VALIDATED OPPORTUNITIES","EMERGING SETUPS","EVIDENCE VALIDATED","UNDERVALUED (RESEARCH)","REGULAR HIGH CONFIDENCE","REGULAR RADAR","STRONG PRE-MOVE CANDIDATE","PRE-MOVE CANDIDATE"],key="research_view_v63948")
    else:show_mode=primary_show
    f1,f2,f3=st.columns(3)
    timing_filter=f1.selectbox("Timing context",["ALL","EARLY","MID","EXTENDED","NOT EXTENDED"],0,key="timing_filter_v63948")
    quality_filter=f2.selectbox("Evidence",["ALL","EVIDENCE 6+","EVIDENCE 12+"],0,key="quality_filter_v63948")
    risk_filter=f3.selectbox("Risk / geometry",["ALL","NO CHASE","R:R ≥ 1.5"],0,key="risk_filter_v63948")
    with st.expander("Research overlays (optional)",expanded=False):
        valuation_overlay=st.checkbox("Valuation / underpricing overlay",value=True,key="valuation_overlay_v63948",help="Research only. Does not change Ranking V3.13 or Entry gates.")
        catalyst_overlay=st.checkbox(f"Catalyst overlay for Top {_CATALYST_TOP_N_V6394}",value=False,key="catalyst_overlay_v63948",help="Research only. News/earnings context is shown in Details but does not change Ranking V3.13 or Entry.")
    st.caption("Pre-Move Radar and BUILDING SETUP are different: Pre-Move looks for abnormal accumulation before a normal setup exists; BUILDING SETUP means the trade setup has already started forming but is not ARMED yet. Action Queue answers what is actionable now; Pre-Move Radar answers what may be developing before the move.")
    scanner_status=_scanner_status_v601();scanner_busy=scanner_status in ('running','stopping');b1,b2=st.columns([2,1])
    with b1:
        _no_markets=market_discovery and not markets_to_scan
        disabled=scanner_busy or _no_markets or (model_mode=="OOS OPTIMIZED" and not _active_model_has_any_v63945(model))
        if st.button("▶ Start Scan",key="scanner_start_v63948",use_container_width=True,disabled=disabled):
            ts=[x.strip().upper() for x in scan_universe.split(',') if x.strip()]
            live_oos_model=model if model_mode=="OOS OPTIMIZED" else (promoted_hourly_model if _active_model_has_any_v63945(promoted_hourly_model) else None)
            config={'tickers':ts,'history':sh,'horizon':int(ho),'target':float(ta)/100,'threshold':66,'prefilter_top':int(prefilter_top),'universe_mode':universe_mode,'scan_mode':scan_mode,'scan_depth':scan_depth,'optimizer_model':live_oos_model,'valuation_overlay':bool(valuation_overlay),'catalyst_overlay':bool(catalyst_overlay),'catalyst_top_n':_CATALYST_TOP_N_V6394,'market_discovery':bool(market_discovery),'markets':list(markets_to_scan),'discovery_deep_cap':int(55+35*max(1,len(markets_to_scan)))}
            ok,msg=_start_scanner_job_v599(config)
            if ok:
                _scope=("MARKET DISCOVERY • "+", ".join(markets_to_scan)) if market_discovery else f"{coverage} • {len(ts)} tickers"
                st.success(f"{model_mode} / {scan_depth} started server-side • {_scope}.");st.rerun()
            else:st.warning(msg)
    with b2:
        if st.button("■ Stop Scan",key="scanner_stop_v63948",use_container_width=True,disabled=not scanner_busy or scanner_status=='stopping'):
            ok,msg=_request_scanner_stop_v601();st.warning(msg) if ok else st.info(msg);st.rerun()
    market_filter={'ALL':'ALL','US':'US ALL','HONG KONG':'HONG KONG ALL','TEL AVIV':'TEL AVIV ALL'}[universe_mode]
    _render_scanner_top_excel_v624(scanner_excel_top,show_mode,market_filter,timing_filter,quality_filter,risk_filter)
    if _scanner_status_v601() in ('running','stopping'):_scanner_live_fragment_v599(show_mode,market_filter,timing_filter,quality_filter,risk_filter)
    else:_render_scanner_results_v599(show_mode,market_filter,timing_filter,quality_filter,risk_filter)

with tab_analyze:
    st.markdown("<div class='section'>📈 Analyze — single-stock decision cockpit</div>",unsafe_allow_html=True)
    analyze_excel_top=st.empty()
    c1,c2,c3,c4=st.columns([1.35,1,1,1]);ticker=c1.text_input("Ticker","1196.HK",key="a603_ticker");hist=c2.selectbox("History",["3mo","6mo","1y"],1,key="a603_hist");horizon=c3.selectbox("Forecast days",[3,5,7,10],1,key="a603_horizon");target=c4.selectbox("Target %",[3,4,5,6,8,10,15,20],3,key="a603_target")
    st.caption("Live decisions do not use a Quant buy threshold. Historical Quant thresholds are research-only evidence.")
    required_engine_api=["fetch_ohlcv","compute_features","score_latest","backtest_signal","entry_timing","score_row","early_score_row"];missing_engine_api=[name for name in required_engine_api if not hasattr(qe,name)];engine_ver=getattr(qe,"ENGINE_VERSION",None);engine_build=getattr(qe,"ENGINE_BUILD_ID",None)
    if missing_engine_api:st.error("Quant engine is incompatible. Missing: "+", ".join(missing_engine_api)+". Upload all 4 files from the matching ZIP.")
    elif engine_ver is not None and str(engine_ver)!=APP_VERSION:st.warning(f"Version mismatch detected: app V{APP_VERSION} / engine {engine_ver}. Upload all 4 files from the same ZIP before trusting results.")
    elif engine_ver is not None:st.caption(f"✓ App and quant engine synced: V{APP_VERSION}"+(f" • {engine_build}" if engine_build else ""))
    a,_=_lab_snapshot_v603('analyze');busy=bool(a and a.get('status') in ('running','stopping'));b1,b2=st.columns([2,1])
    with b1:
        if st.button(f"▶ Start V{APP_VERSION} Analyze",key="an603_start",use_container_width=True,disabled=busy or bool(missing_engine_api)):
            cfg={'ticker':ticker.strip().upper(),'history':hist,'horizon':int(horizon),'target':float(target)};ok,msg=_start_lab_v603('analyze',_analyze_worker_v603,cfg,total=8)
            if ok:st.success("Analyze started server-side. You can switch apps and return later.");st.rerun()
            else:st.warning(msg)
    with b2:
        if st.button("■ Stop Analyze",key="an603_stop",use_container_width=True,disabled=not busy or (a and a.get('status')=='stopping')):
            ok,msg=_stop_lab_v603('analyze');st.warning(msg) if ok else st.info(msg);st.rerun()
    if busy:_lab_live_fragment_v603('analyze')
    else:_render_lab_status_v603('analyze')
    a,last=_lab_snapshot_v603('analyze');snap=a if a and a.get('payload') else last
    if not (snap and snap.get('payload')):
        with analyze_excel_top.container():st.caption('⬇️ Excel download will appear here after a completed Analyze run.')
    if snap and snap.get('payload'):
        pay=snap['payload'];t=pay['ticker'];f=pay['f'];dyn=pay['dyn'];ent=pay['ent'];latest_live=pay['latest_live'];live_snapshot=pay.get('live_snapshot',{});ah_snapshot=pay.get('ah_snapshot',{});ex=pay['ex'];timing=pay['timing'];decision=pay['decision'];ca_report=pay['ca_report'];bt=pay['bt'];buy_threshold=pay['buy_threshold'];comp=pay['comp'];ec=pay['ec'];cmp=pay['cmp'];compare_df=pay['compare_df'];ev=pay['ev'];early_cal=pay['early_cal'];quant_cal=pay['quant_cal'];target_run=pay['target'];horizon_run=pay['horizon']
        phase=str(decision.get('MarketPhase','UNKNOWN'));ch=latest_live.get('daily_change_pct',np.nan);currency='HKD' if t.endswith('.HK') else ('ILA' if t.endswith('.TA') else 'USD')
        market_name=str(decision.get('Market',_market_for_ticker_v612(t)))
        mdet=_market_status_detail_v612(market_name); mphase=mdet.get('phase',phase); micon=_market_phase_icon_v612(mphase)
        mreason=f" • {mdet.get('reason')}" if mdet.get('reason') else ''
        st.markdown(f"### {t} · {market_name} · {micon} {mphase}")
        st.caption(f"Exchange local time {mdet.get('local_time','—')}{mreason}")
        price_fresh=bool(live_snapshot.get('fresh'));display_current=bool(live_snapshot.get('display_current'));trade_fresh=bool(live_snapshot.get('trade_fresh'));live_px=float(live_snapshot.get('price',np.nan)) if np.isfinite(float(live_snapshot.get('price',np.nan))) else np.nan;fallback_px=float(live_snapshot.get('fallback_price',np.nan)) if np.isfinite(float(live_snapshot.get('fallback_price',np.nan))) else np.nan
        quote_status=str(live_snapshot.get('quote_status','UNAVAILABLE'))
        if phase=='AFTER-MARKET' and np.isfinite(float(ah_snapshot.get('AHPrice',np.nan))):
            cur=float(ah_snapshot.get('AHPrice')); price_label='After-hours price'
        elif display_current and np.isfinite(live_px):cur=live_px;price_label='Current price' if trade_fresh else 'Current / delayed price'
        else:cur=fallback_px if np.isfinite(fallback_px) else latest_live.get('price',np.nan);price_label='Last official close' if np.isfinite(cur) else 'Live price unavailable'
        _metric_delta=float(ah_snapshot.get('AHChangePct',np.nan)) if phase=='AFTER-MARKET' and np.isfinite(float(ah_snapshot.get('AHChangePct',np.nan))) else ch
        st.markdown("<div class='section'>Decision cockpit</div>",unsafe_allow_html=True)
        _an_drs=_num_v6394(decision.get('DecisionRankScore'),np.nan);_an_em=_num_v6394(decision.get('EmergingSetupScore'),np.nan);_an_ev=_num_v6394(decision.get('DecisionEvidenceScore',decision.get('Reliability')),0)
        if bool(decision.get('ValidatedOpportunityEligible',False)):_an_head='VALIDATED';_an_score=_an_drs
        elif bool(decision.get('EmergingSetupEligible',False)):_an_head='EMERGING';_an_score=_an_em
        elif bool(decision.get('EvidenceValidated',False)):_an_head='EVIDENCE';_an_score=_an_ev
        else:_an_head='DECISION';_an_score=_an_drs
        _an_score_txt=f"{_an_score:.1f}" if np.isfinite(_an_score) else '—'
        st.markdown(f"<div class='top5-head'><div class='top5-name'>{_e6395(t)}</div><div class='top5-score'><small>{_an_head}</small> {_an_score_txt}<span class='den'>/100</span></div></div>",unsafe_allow_html=True)
        _an_entry=str(ent.get('session_entry_state',ent.get('trigger_state',ent.get('status','WAIT'))) or 'WAIT');_an_exit=str(decision.get('ExitStage','CLEAR') or 'CLEAR');_an_exitp=_num_v6394(decision.get('ExitPressure'),0)
        _an_trade_cls='good' if 'CONFIRMED' in _an_entry else ('bad' if ('EXTENDED' in _an_entry or 'INVALID' in _an_entry) else 'warn');_an_exit_cls='bad' if _an_exitp>=55 else ('warn' if _an_exitp>=35 else 'good')
        _an_px=(f"{cur:.3f}" if np.isfinite(cur) and abs(cur)<10 else (f"{cur:.2f}" if np.isfinite(cur) else '—'))
        _an_card=dict(decision)
        _an_card.update({
            'TradeStage':_an_entry,'EntryTriggerState':_an_entry,'RecommendedAction':ent.get('recommended_action',''),
            'RetestStatus':ent.get('retest_status','—'),'RetestEntryLow':ent.get('retest_entry_low',np.nan),'RetestEntryHigh':ent.get('retest_entry_high',np.nan),'RetestInvalidation':ent.get('retest_invalidation',np.nan),'RetestTarget1':ent.get('retest_target1',np.nan),'RetestTarget2':ent.get('retest_target2',np.nan),'RetestRR_T1':ent.get('retest_rr_t1',np.nan),'RetestRR_T2':ent.get('retest_rr_t2',np.nan),'RetestPlanValid':ent.get('retest_plan_valid',False),'RetestPlanReason':ent.get('retest_plan_reason',''),'RecentRunRetestContext':ent.get('recent_run_retest_context',False),
            'BreakoutContinuationActionable':ent.get('breakout_continuation_actionable',False),'BreakoutContinuationTrigger':ent.get('breakout_continuation_trigger',np.nan),
            'BreakoutContinuationVolumeOK':ent.get('breakout_continuation_volume_ok',False),'BreakoutContinuationMomentumOK':ent.get('breakout_continuation_momentum_ok',False),'BreakoutContinuationFlowOK':ent.get('breakout_continuation_flow_ok',False),
            'ContinuationEntryState':ent.get('continuation_entry_state','N/A'),'ContinuationEntryWatch':ent.get('continuation_entry_watch',False),'ContinuationEntryReady':ent.get('continuation_entry_ready',False),'ContinuationEntryReason':ent.get('continuation_entry_reason',''),
            'ContinuationProgressOK':ent.get('continuation_progress_ok',False),'ContinuationTimingOK':ent.get('continuation_timing_ok',False),'ContinuationRROK':ent.get('continuation_rr_ok',False),'ContinuationDistributionOK':ent.get('continuation_distribution_ok',False),
            'ContinuationLiveRVOL':ent.get('continuation_live_rvol',np.nan),'ContinuationVolumeState':ent.get('continuation_volume_state','NO DATA'),'ContinuationFadingStrongOverride':ent.get('continuation_fading_strong_override',False),
            'ContinuationDistributionState':ent.get('continuation_distribution_state','NO DATA'),'ContinuationDistributionSoftOverride':ent.get('continuation_distribution_soft_override',False),'ContinuationBearishDistributionConfirmed':ent.get('continuation_bearish_distribution_confirmed',False),
            'ConfirmedEntryGateOK':ent.get('confirmed_entry_gate_ok',False),'ActionableNow':decision.get('ActionableNow',False),
            'TimingDataComplete':ent.get('timing_data_complete',True),'TimingConsumedHardBlock':ent.get('timing_consumed_hard_block',False),
            'PriceActionableNow':ent.get('price_actionable_now',False),'RRActionable':ent.get('rr_actionable',False),'SetupConfirmed':ent.get('setup_confirmed',False),
            'SessionDataFresh':decision.get('SessionDataFresh',live_snapshot.get('session_data_fresh',False)),'LivePriceFresh':bool(live_snapshot.get('trade_fresh',live_snapshot.get('fresh',False))),
            'DataQuality':decision.get('DataQuality','OK'),'PlanValid':decision.get('PlanValid',ent.get('plan_valid',True)),'EvidenceGuardOK':decision.get('EvidenceGuardOK',True),'ExitPressure':decision.get('ExitPressure',0),
            'MarketPhase':phase,'Market':market_name,'PMConfirmation':decision.get('PMConfirmation','N/A'),
            'FreshSignalCheck':ent.get('fresh_signal',False),'ActionabilityMissing':ent.get('actionability_missing',''),
            'EntryConfirmedConditions':ent.get('confirmed_conditions',0),'EntryTotalConditions':ent.get('total_conditions',6),
            'EntryTimingScore':decision.get('EntryTimingScore',ent.get('live_actionability_score',ent.get('entry_score',0))),
            'LiveActionabilityScore':ent.get('live_actionability_score',ent.get('entry_score',0)),
            'HourlyTimingSource':decision.get('HourlyTimingSource',ent.get('hourly_timing_source','BASE TIMING')),
            'HourlyOOSTimingScore':decision.get('HourlyOOSTimingScore',ent.get('hourly_entry_score',np.nan)),
            'HourlyConfirm':decision.get('HourlyConfirm',timing.get('hourly_confirmation',np.nan)),
            'MoveConsumedBeforeTriggerPct':ent.get('move_consumed_before_trigger_pct',np.nan),
            'TriggerEfficiencyLabel':ent.get('trigger_efficiency_label','NO DATA'),
            'PreBreakoutAccumulationScore':ent.get('pre_breakout_accumulation_score',0.0),'PreBreakoutAccumulationStage':ent.get('pre_breakout_accumulation_stage','NO CURRENT ACCUMULATION SETUP'),'PreBreakoutAccumulationReason':ent.get('pre_breakout_accumulation_reason',''),'PreMoveConfirmed':ent.get('pre_move_confirmed',False),'PreMoveConfidenceTier':ent.get('pre_move_confidence_tier','NONE'),'PreMoveFamilyCount':ent.get('pre_move_family_count',0),'PreMoveFamilySignature':ent.get('pre_move_family_signature','NONE'),'PreMoveBaselineGuardOK':ent.get('pre_move_baseline_guard_ok',False),'PreMoveBaselineVolume':ent.get('pre_move_baseline_volume',np.nan),'PreMoveBaselineTurnover':ent.get('pre_move_baseline_turnover',np.nan),'EffectiveVolumeShockRatio':ent.get('effective_volume_shock_ratio',np.nan),'PreMoveShockRecoveryOK':ent.get('pre_move_shock_recovery_ok',False),'PreMoveFlowConfirmation':ent.get('pre_move_flow_confirmation',False),'PreMoveMomentumConfirmation':ent.get('pre_move_momentum_confirmation',False),'VolumeRegimeRatio':ent.get('volume_regime_ratio',np.nan),'VolumeShockRatio':ent.get('volume_shock_ratio',np.nan),'VolumeShockDate':ent.get('volume_shock_date','—'),'VolumeShockReturnPct':ent.get('volume_shock_return_pct',np.nan),'AbsorptionCandidate':ent.get('absorption_candidate',False),'VolumePersistenceRatio':ent.get('volume_persistence_ratio',np.nan),'PriceRetentionSinceVolumeShockPct':ent.get('price_retention_since_volume_shock_pct',np.nan),'PreBreakoutHigherLowCount':ent.get('pre_breakout_higher_low_count',0),'PreBreakoutRegimeShift':ent.get('pre_breakout_regime_shift',False),'RecentRunPct':ent.get('recent_run_pct',np.nan),'RecentRunATR':ent.get('recent_run_atr',np.nan),
            'RecentRunWindow':ent.get('recent_run_window','—'),'RecentRunLabel':ent.get('recent_run_label','NO DATA'),
            'PostTriggerConsumedPct':ent.get('post_trigger_consumed_pct',np.nan),'PostTriggerConsumedLabel':ent.get('post_trigger_consumed_label','NO DATA'),
            'ChaseRiskScore':ent.get('chase_risk_score',0),'ChaseRiskLabel':ent.get('chase_risk_label','LOW'),
            'ExtensionGuardCheck':ent.get('extension_guard_ok',True),'LiveRR_T1':ent.get('live_rr_t1',np.nan),'LiveRR_T2':ent.get('live_rr_t2',np.nan),
            'LiquidityScore':decision.get('LiquidityScore',_liq_profile.get('LiquidityScore',0)),'LiquidityLabel':decision.get('LiquidityLabel',_liq_profile.get('LiquidityLabel','NO DATA')),'LiquidityHardGateOK':decision.get('LiquidityHardGateOK',_liq_profile.get('LiquidityHardGateOK',False)),'LiquidityBlockReason':decision.get('LiquidityBlockReason',_liq_profile.get('LiquidityBlockReason','')),'MedianDailyTurnover60':decision.get('MedianDailyTurnover60',_liq_profile.get('MedianDailyTurnover60',np.nan)),'AvgDailyTurnover20':decision.get('AvgDailyTurnover20',_liq_profile.get('AvgDailyTurnover20',np.nan)),'LiquidityTurnoverCurrency':decision.get('LiquidityTurnoverCurrency',_liq_profile.get('LiquidityTurnoverCurrency','')),'LiquidityStableDaysPct':decision.get('LiquidityStableDaysPct',_liq_profile.get('LiquidityStableDaysPct',np.nan)),
        })
        _an_raw_board,_an_window,_an_board_reason,_an_timing_ctx=_decision_board_state_v63948(_an_card)
        _an_eff,_an_disp0,_an_eff_reason,_an_reval,_an_gate_reason=_effective_decision_stage_v63958(_an_card,_an_raw_board)
        _an_gate_ok,_an_gate_reason2=_entry_now_hard_gate_v63958(_an_card)
        _an_armed_ok,_an_armed_reason=_armed_qualification_v63961(_an_card)
        _an_card.update({'RawDecisionBoardStage':_decision_stage_canonical_v63961(_an_raw_board),'DecisionBoardStage':_decision_stage_canonical_v63961(_an_raw_board),'EffectiveDecisionStage':_decision_stage_canonical_v63961(_an_eff),'DecisionDisplayStage':_decision_stage_canonical_v63961(_an_disp0),'EffectiveDecisionReason':_an_eff_reason,'NeedsOpenRevalidation':_an_reval,'EntryNowHardGateOK':_an_gate_ok,'EntryNowHardGateReason':_an_gate_reason2,'ArmedQualified':_an_armed_ok,'ArmedQualificationState':'QUALIFIED' if _an_armed_ok else 'BLOCKED / INCOMPLETE','ArmedQualificationReason':_an_armed_reason})
        _an_prev=bool(_decision_stage_canonical_v63961(_an_eff)=='LAST SESSION ENTRY' or (_an_entry.upper()=='CONFIRMED ENTRY' and phase.upper() in ('CLOSED','AFTER-MARKET','PRE-OPEN')))
        _an_card['TradeStageDisplay']='PREVIOUS SESSION CONFIRMED ENTRY' if _an_prev else _an_entry
        _an_rr_base=bool(ent.get('price_actionable_now',False)) and bool(_an_card.get('SessionDataFresh',False)) and bool(_an_card.get('LivePriceFresh',False)) and phase.upper() in ('OPEN','PRE-MARKET') and not _an_prev and bool(_an_card.get('PlanValid',True))
        _an_liq_ok=bool(_an_card.get('LiquidityHardGateOK',False))
        _an_rr_ctx=bool(_an_rr_base and _an_liq_ok)
        _an_rr_research=bool(_an_rr_base and not _an_liq_ok)
        _an_card['LiveRRDisplayT1']=ent.get('live_rr_t1',np.nan) if (_an_rr_ctx or _an_rr_research) else np.nan;_an_card['LiveRRDisplayT2']=ent.get('live_rr_t2',np.nan) if (_an_rr_ctx or _an_rr_research) else np.nan
        if _an_rr_ctx and np.isfinite(_num6395(ent.get('live_rr_t1',np.nan))):_an_card['LiveRRDisplayStatus']='LIVE R:R'
        elif _an_rr_research and np.isfinite(_num6395(ent.get('live_rr_t1',np.nan))):_an_card['LiveRRDisplayStatus']='RESEARCH R:R — LIQUIDITY BLOCK'
        elif not bool(ent.get('price_actionable_now',False)):_an_card['LiveRRDisplayStatus']='N/A — PRICE OUTSIDE ENTRY CONTEXT'
        elif not bool(_an_card.get('PlanValid',True)):_an_card['LiveRRDisplayStatus']='N/A — PLAN INVALID'
        else:_an_card['LiveRRDisplayStatus']='N/A — LIVE DATA NOT QUALIFIED'
        _aps,_apa,_apst,_apr=_pre_move_actionability_v63957(_an_card,_an_raw_board);_an_card.update({'PreMovePatternStrength':_aps,'PreMoveActionableNow':_apa,'PreMoveActionabilityState':_apst,'PreMoveActionabilityReason':_apr,'PreMovePatternDetected':_aps in ('HIGH','WATCH'),'PreMoveRadarActionable':bool(_apa and _aps in ('HIGH','WATCH'))})
        _an_board=_an_eff
        _an_display_board,_an_display_window,_an_display_reason=_decision_display_semantics_v63953(_an_card,_an_board,_an_window,_an_eff_reason)
        _an_display_board=_decision_stage_display_v63960(_an_display_board)
        _an_board_cls='good' if _an_display_board=='ENTRY NOW' else ('warn' if _an_display_board=='LAST SESSION ENTRY' or _decision_stage_canonical_v63961(_an_board) in ('BUILDING SETUP','ARMED','ARMED BLOCKED','RETEST') else ('bad' if _an_board=='TOO LATE' else ''))
        _an_window_cls='good' if _an_display_window=='OPEN' else ('warn' if _an_display_window in ('BUILDING','NEAR','WAIT','RECHECK AT OPEN') else ('bad' if _an_display_window=='CLOSED' else ''))
        st.markdown(f"<div class='top5-status'><b>{_an_px} <span class='ccy'>{currency}</span></b> • {_e6395(phase)} • Decision <span class='top5-pill {_an_board_cls}'>{_e6395(_an_display_board)}</span> • Window <span class='{_an_window_cls}'><b>{_e6395(_an_display_window)}</b></span> • Exit <span class='{_an_exit_cls}'><b>{_e6395(_an_exit)}</b></span></div>",unsafe_allow_html=True)
        _an_action=str(ent.get('recommended_action',_an_board_reason) or _an_board_reason)
        if _an_action and _an_action not in ('—','None'):
            st.markdown(f"<div class='top5-detail-line'><b>Action:</b> {_e6395(_an_action)}</div>",unsafe_allow_html=True)
        _acm=_render_core_grid_v63948(_an_card,phase)
        _an_setup=_acm['setup'];_an_entry_score=_acm['entry'];_an_hour=_acm['hour'];_an_hour_sub=_acm['hour_sub']
        _an_in=_acm['inflow'];_an_out=_acm['outflow'];_an_net=_acm['net'];_an_inlab=_acm['inflow_label'];_an_outlab=_acm['outflow_label'];_an_netlab=_acm['net_label']
        _an_rvol=_acm['rvol'];_an_rvol_band=_acm['rvol_band'];_an_rvol_mode=_acm['rvol_mode']
        _an_cons=_acm['consumed'];_an_timing=_acm['trigger_timing'];_an_recent=_acm['recent'];_an_recent_atr=_acm['recent_atr'];_an_recent_window=_acm['recent_window'];_an_recent_label=_acm['recent_label'];_an_post=_acm['post'];_an_post_label=_acm['post_label']
        _an_cr=_acm['chase_score'];_an_chase=_acm['chase'];_an_rr1=_acm['rr1'];_an_rr2=_acm['rr2'];_an_evn=_acm['ev_n'];_an_evq=_acm['ev_q']
        _an_cons_txt=f"{_an_cons:.0f}%" if np.isfinite(_an_cons) else '—';_an_recent_txt=f"+{_an_recent:.1f}%" if np.isfinite(_an_recent) else '—';_an_post_txt=f"{_an_post:.0f}%" if np.isfinite(_an_post) else '—'
        _an_rr1_txt=_acm['rr1_txt'];_an_rr2_txt=_acm['rr2_txt'];_an_evprog=f"{_an_evn}/12" if _an_evn<12 else f"{_an_evn}/12 ✓"
        if _an_recent_label in ('LATE CONTEXT','EXTENDED CONTEXT'):
            st.markdown(f"<div class='top5-alert'>⚠️ <b>MULTI-DAY CONTEXT</b> • {_an_recent_txt} over {_e6395(_an_recent_window)} • {_e6395(_an_recent_label)} • fresh session timing does not mean the whole move is early</div>",unsafe_allow_html=True)
        if not bool(decision.get('EvidenceTradeGrade',False)):
            if bool(decision.get('EvidenceGuardOK',True)):st.markdown(f"<div class='top5-alert'>⚠️ <b>UNVALIDATED • WARNING ONLY</b> • Evidence {_an_evn}/12 • {_e6395(_an_evq)}</div>",unsafe_allow_html=True)
            else:st.markdown(f"<div class='top5-alert'>⛔ <b>EVIDENCE HARD GUARD</b> • Evidence {_an_evn}/12 • {_e6395(_an_evq)}</div>",unsafe_allow_html=True)
        if not bool(decision.get('TimingDataComplete',ent.get('timing_data_complete',True))):
            st.markdown(f"<div class='top5-alert'>⛔ <b>TIMING DATA INCOMPLETE</b> • {_e6395(decision.get('TimingDataReason',ent.get('timing_data_reason','Move-consumed timing unavailable')))}</div>",unsafe_allow_html=True)
        quote_stamp=live_snapshot.get('timestamp_label','—');quote_age=live_snapshot.get('age_minutes',np.nan);age_txt=f" • age {float(quote_age):.0f}m" if np.isfinite(float(quote_age)) else '';quote_source=live_snapshot.get('source','unavailable')
        st.caption(f"{phase} • {decision.get('Market','—')} • {quote_status} • {quote_source} @ {quote_stamp}{age_txt}")
        if phase=='AFTER-MARKET':
            _ahc=float(ah_snapshot.get('AHChangePct',np.nan)); _ahr=float(ent.get('regular_session_move_pct',np.nan)); _aht=float(ent.get('total_move_including_ah_pct',np.nan)); _ahv=float(ah_snapshot.get('AHVolumeStrength',np.nan)); _ahts=ah_snapshot.get('AHLastTime','—'); _ahage=float(ah_snapshot.get('AHAgeMinutes',np.nan));
            st.warning("AFTER-MARKET MODE — regular-session 15m/1H indicators are frozen. After-hours price/volume are used as confirmation and chase-risk context only; Actionable Now is blocked until the next regular session reconfirms the setup.")
            st.caption(f"Regular session move {f'{_ahr:+.2f}%' if np.isfinite(_ahr) else '—'} • After-hours move {f'{_ahc:+.2f}%' if np.isfinite(_ahc) else '—'} • Total vs prior close {f'{_aht:+.2f}%' if np.isfinite(_aht) else '—'} • AH volume strength {f'{_ahv:.2f}x' if np.isfinite(_ahv) else '—'} • AH quote {_ahts} • source {ent.get('after_hours_price_source','N/A')}{f' • age {_ahage:.0f}m' if np.isfinite(_ahage) else ''}")
        if live_snapshot.get('temporary_counter_active'):
            temp=str(live_snapshot.get('temporary_counter','')).replace('.HK','');under=str(live_snapshot.get('underlying_symbol',t)).replace('.HK','')
            st.info(f"HKEX CORPORATE-ACTION COUNTER: current quote is read from temporary counter {temp} for permanent ticker {under}. Historical research remains on {under}.")
        if phase=='OPEN' and not display_current:
            stale_ts=live_snapshot.get('stale_timestamp_label','—');stale_px=live_snapshot.get('stale_price',np.nan);stale_note=f" Last rejected provider bar: {float(stale_px):.3f} @ {stale_ts}." if np.isfinite(float(stale_px)) else ''
            st.error("CURRENT PRICE UNAVAILABLE — no trustworthy current-session quote from the fallback chain. The number above is the last official close only. CONFIRMED ENTRY — LIVE and Actionable Now are blocked."+stale_note)
        elif phase=='OPEN' and display_current and not trade_fresh:
            st.warning("CURRENT/DELAYED PRICE FOUND — shown for price reference, but the feed is not timestamp-fresh enough for CONFIRMED ENTRY — LIVE or Actionable Now.")
        if ca_report.get('split_detected'):
            sr=ca_report.get('split_ratio',np.nan);sd=ca_report.get('split_date') or live_snapshot.get('split_date') or 'recent';ratio_txt=f"1→{float(sr):g} subdivision" if np.isfinite(float(sr)) and float(sr)>=1 else (f"split ratio {float(sr):g}" if np.isfinite(float(sr)) else 'split')
            adj=(' • price scales normalized' if ca_report.get('split_adjusted') else (' • integrity check BLOCKED' if ca_report.get('data_quality')!='OK' else ' • provider frames appear consistent'))
            st.info(f"Corporate Action detected: {ratio_txt} split/subdivision ({sd}){adj}.")
        elif ca_report.get('split_adjusted'):st.info("Corporate Action / split-like scale difference detected — Daily / 1H / 15m were normalized to the current intraday scale.")
        if ca_report.get('data_quality')!='OK':
            _dqmsg='SPLIT SCALE MISMATCH — trade plan blocked because price/trigger/target levels are not on one verified scale.' if ca_report.get('data_quality')=='SPLIT_SCALE_MISMATCH' else 'DATA QUALITY CHECK — unexplained cross-timeframe price mismatch remains after normalization.'
            st.error(_dqmsg+' PlanValid is forced FALSE and all Trade Plan levels are suppressed.')
        _display_entry_state=ent.get('session_entry_state',ent.get('trigger_state',ent.get('status','WAIT')))
        if phase=='AFTER-MARKET': st.caption(f"Regular-session close state: {ent.get('regular_session_entry_state','—')} • regular entry score {float(ent.get('regular_session_entry_score',np.nan)):.1f}" if np.isfinite(float(ent.get('regular_session_entry_score',np.nan))) else f"Regular-session close state: {ent.get('regular_session_entry_state','—')}")
        _cr=float(ent.get('chase_risk_score',0) or 0);_sm=float(ent.get('session_move_pct',np.nan));_sa=float(ent.get('session_move_atr',np.nan));_sp=float(ent.get('session_move_percentile',np.nan));_pre=float(ent.get('move_before_trigger_pct',np.nan));_st=float(ent.get('since_trigger_pct',np.nan));_va=float(ent.get('vwap_distance_atr',np.nan));_tp=float(ent.get('target1_progress_pct',np.nan))
        _risk_line=f"Chase Risk {ent.get('chase_risk_label','LOW')} ({_cr:.0f}/100) • Session {f'{_sm:+.1f}%' if np.isfinite(_sm) else '—'} / {f'{_sa:.2f} ATR' if np.isfinite(_sa) else '—'} • Session pctile {f'{_sp:.0f}' if np.isfinite(_sp) else '—'} • Before trigger {f'{_pre:+.1f}%' if np.isfinite(_pre) else '—'} • Since trigger {f'{_st:+.1f}%' if np.isfinite(_st) else '—'} • VWAP distance {f'{_va:.2f} ATR' if np.isfinite(_va) else '—'} • Volume {ent.get('volume_trend','NO DATA')}"
        if not bool(ent.get('extension_guard_ok',True)):st.warning(_risk_line+" • WAIT FOR RETEST")
        _rr1=ent.get('live_rr_t1',np.nan);_rr2=ent.get('live_rr_t2',np.nan);_act=ent.get('live_actionability_score',np.nan)
        _rr_live_ctx=bool(ent.get('price_actionable_now',False)) and bool(decision.get('SessionDataFresh',True)) and bool(decision.get('LivePriceFresh',trade_fresh)) and phase in ('OPEN','PRE-MARKET')
        if np.isfinite(float(_act)) if _act is not None else False:
            if _rr_live_ctx and np.isfinite(float(_rr1)) and np.isfinite(float(_rr2)):st.caption(f"Live actionability {float(_act):.1f}/100 • R:R T1 {float(_rr1):.2f}x • R:R T2 {float(_rr2):.2f}x")
            else:st.caption(f"Live actionability {float(_act):.1f}/100 • R:R N/A — PRICE OUTSIDE ENTRY CONTEXT / LIVE DATA NOT QUALIFIED")
        else:st.caption(_risk_line)
        _ta=ent.get('trigger_anchor_time','—'); _tb=ent.get('trigger_anchor_bar_start_time','—'); _tf=ent.get('trigger_anchor_timeframe','—')
        _so=ent.get('setup_origin_time','—'); _sop=float(ent.get('setup_origin_price',np.nan)); _mbs=float(ent.get('move_before_setup_origin_pct',np.nan)); _sss=float(ent.get('since_setup_origin_pct',np.nan))
        st.caption(f"Causal trigger audit: {_tf} signal confirmed {_ta} (bar start {_tb}) • Momentum {ent.get('momentum_state','NO DATA')} [15m {ent.get('momentum_state_15m','NO DATA')} / 1H {ent.get('momentum_state_1h','NO DATA')}]")
        if np.isfinite(_sop):st.caption(f"Research-only setup origin: {_sop:.3f} confirmed {_so} • move before origin {f'{_mbs:+.1f}%' if np.isfinite(_mbs) else '—'} • since origin {f'{_sss:+.1f}%' if np.isfinite(_sss) else '—'} • not an actionable trigger until OOS validated")
        _otl=float(ent.get('origin_to_trigger_pct',np.nan)); _tlm=float(ent.get('trigger_lag_minutes',np.nan)); _mct=float(ent.get('move_consumed_before_trigger_pct',np.nan))
        if np.isfinite(_otl) or np.isfinite(_tlm) or np.isfinite(_mct):st.caption(f"Trigger efficiency: {ent.get('trigger_efficiency_label','NO DATA')} • origin→trigger {f'{_otl:+.2f}%' if np.isfinite(_otl) else '—'} • lag {f'{_tlm:.0f} min' if np.isfinite(_tlm) else '—'} • {f'{_mct:.0f}% of observed session move occurred before causal trigger' if np.isfinite(_mct) else 'move-consumption —'} • 80%+ activates the hard timing gate")
        if bool(ent.get('next_session_carryover_candidate',False)):st.info('Next-session extension memory candidate: '+str(ent.get('next_session_carryover_reason','today’s move should carry forward'))+'. The next regular session must not reset this setup to fresh just because its day change starts near 0%.')
        if ent.get('missing_checks') and ent.get('missing_checks')!='None':st.caption("Still missing: "+str(ent.get('missing_checks')))
        _fb=pay.get('feedback_snapshot',{}) or {}
        if _fb.get('saved'):
            _role=str(_fb.get('event_role','TRACKING'))
            st.caption(f"Feedback snapshot saved automatically • ANALYZE • Event {_fb.get('event_id','—')} • {_role} • repeated Scanner/Analyze observations do not inflate independent-event N")
        else:
            st.caption(f"Feedback snapshot not stored: {_fb.get('reason','unavailable')}")
        with st.expander("Details / Why?",expanded=False):
            _render_decision_why_v63953(_an_card,phase)
        with st.expander("Advanced diagnostics",expanded=False):
            st.caption(f"Why now: {ent.get('why_now','—')} • Movement {decision.get('MovementStage','—')} • Prediction {dyn.get('final_prediction',np.nan):.1f}/100 • Move {timing.get('move_score',np.nan):.1f} • Explosive {ex.get('score',np.nan):.1f}")
            st.caption(f"Flow: In {_an_in:.0f}/100 {_an_inlab} • Out {_an_out:.0f}/100 {_an_outlab} • Net {_an_net:+.0f} {_an_netlab} • {decision.get('FlowPressureEvidence',decision.get('MoneyFlowEvidence','—'))}")
            _lrvol=decision.get('IntradayCumulativeRVOL',decision.get('LiveIntradayRVOL',np.nan));_drvol=decision.get('FullSessionRVOL',decision.get('DailyRobustRVOL',np.nan))
            st.caption(f"Intraday cumulative RVOL {float(_lrvol):.2f}x" if np.isfinite(float(_lrvol)) else 'Intraday cumulative RVOL —')
            st.caption(f"Final/full-session RVOL {float(_drvol):.2f}x • Reliability {decision.get('Reliability',0):.1f} • Evidence {decision.get('EvidenceState','UNPROVEN')}" if np.isfinite(float(_drvol)) else f"Final/full-session RVOL — • Reliability {decision.get('Reliability',0):.1f} • Evidence {decision.get('EvidenceState','UNPROVEN')}")
            if np.isfinite(float(decision.get('InstitutionalFlowScore',np.nan))):st.caption(f"Institutional Flow {float(decision.get('InstitutionalFlowScore',np.nan)):.0f} ({decision.get('InstitutionalFlowLabel','—')}) • Optimized {float(decision.get('OptimizedScore',np.nan)):.1f} / Match {float(decision.get('OptimizedMatchPct',np.nan)):.0f}% • OOS {float(decision.get('OptimizedModelOOSLift',np.nan)):.3f}x • Hourly match {float(decision.get('HourlyOptimizedMatchPct',np.nan)):.0f}% ({decision.get('HourlyOptimizedHorizon','—')})")
            st.caption(f"Exit engine: {decision.get('ExitStage','CLEAR')} • EXIT WATCH is an early warning; ARMED/TRIGGER require persistent distribution/breakdown.")
        bt_value,bt_sample=backtest_display(bt);b1,b2,b3,b4=st.columns(4);b1.metric("Backtest evidence",bt_value);b2.metric("Sample",f"{int(bt.get('n',0))} signals");b3.metric("Historical Quant threshold",f"{buy_threshold} • research only");b4.metric("Worst historical drawdown",f"{bt.get('max_drawdown',np.nan)*100:.2f}%" if int(bt.get('n',0) or 0) else '—')
        if int(bt.get('n',0) or 0)<12:st.caption("LOW SAMPLE: hit-rate is de-emphasized and its influence on Reliability is capped.")
        st.markdown("<div class='section'>Precision entry / risk plan</div>",unsafe_allow_html=True)
        if bool(ent.get('plan_valid',False)) and ca_report.get('data_quality')=='OK':
            z1,z2,z3,z4=st.columns(4);z1.metric("Entry zone",f"{ent['zone_low']:.3f} – {ent['zone_high']:.3f}");z2.metric("Trade trigger",f"> {ent['trigger']:.3f}");z3.metric("Invalidation",f"< {ent['invalidation']:.3f}");z4.metric("Targets",f"{ent['target1']:.3f} / {ent['target2']:.3f}");st.caption(f"Entry Trigger V4: {ent.get('status','—')} • Anchor {ent.get('trigger_anchor_quality','NONE')} / {ent.get('trigger_anchor_timeframe','—')} @ {ent.get('trigger_anchor_price',np.nan):.3f} • age {ent.get('trigger_anchor_age_bars','—')} bars • Chase/Extension Guard can hard-block a late entry even at 6/6 gates.");
            _an_retest_context=(not bool(ent.get('extension_guard_ok',True)) or float(ent.get('move_consumed_before_trigger_pct',0) or 0)>=60.0 or 'RETEST' in str(ent.get('status','')).upper())
            if _an_retest_context and bool(ent.get('retest_plan_valid',False)):
                st.info(f"Retest-specific plan — RECONFIRM REQUIRED: Entry {float(ent.get('retest_entry_low')):.3f}–{float(ent.get('retest_entry_high')):.3f} • Stop {float(ent.get('retest_invalidation')):.3f} • T1 {float(ent.get('retest_target1')):.3f} • T2 {float(ent.get('retest_target2')):.3f} • R:R T1 {float(ent.get('retest_rr_t1')):.2f}x • {ent.get('retest_status','WAIT FOR RETEST')}")
            elif _an_retest_context:
                st.warning(f"Retest only, but no qualified retest trade plan: {ent.get('retest_status','REASSESS')} • {ent.get('retest_plan_reason','geometry/R:R not qualified')}")
            st.caption(f"Post-spike: {ent.get('post_spike_state','NO DATA')} • peak {safe(ent.get('session_peak_move_pct'),1)}% • giveback {safe(ent.get('high_giveback_pct'),1)}% • retained {safe(ent.get('move_retention_from_high_pct'),1)}% • distribution risk {ent.get('post_spike_distribution_risk','NO DATA')}")
            if ent.get('breakout_continuation_actionable',False):st.success(f"Breakout continuation: STRICTLY CONFIRMED • trigger {safe(ent.get('breakout_continuation_trigger'),3)} • accelerating 15m volume + strengthening momentum + bullish flow verified • standard setup/R:R gates still apply")
            elif ent.get('continuation_base_candidate',False):st.info(f"Continuation base watch: base {safe(ent.get('continuation_base_low'),2)}–{safe(ent.get('continuation_base_high'),2)} • {int(ent.get('continuation_base_bars',0) or 0)} bars • {ent.get('continuation_base_quality','NO DATA')} compression • breakout reference {safe(ent.get('continuation_breakout_trigger'),2)} • not actionable until strict confirmation")
            _ovs=pay.get('origin_validation_summary')
            if isinstance(_ovs,pd.DataFrame) and not _ovs.empty:
                try:
                    _om=dict(zip(_ovs['Metric'].astype(str),_ovs['Value']))
                    st.caption(f"Origin validation (research only): {int(float(_om.get('Clean outcomes',0) or 0))} clean outcomes • hit rate {safe(_om.get('Clean target-before-stop hit rate %'),1)}% • 95% Wilson {safe(_om.get('Hit-rate Wilson 95% low %'),1)}–{safe(_om.get('Hit-rate Wilson 95% high %'),1)}% • {_om.get('Research sample state','LOW SAMPLE — RESEARCH ONLY')}")
                except Exception: pass
            _omb=pay.get('origin_matched_baseline')
            if isinstance(_omb,pd.DataFrame) and not _omb.empty:
                try:
                    _w=_omb[_omb['OpeningBarOrdinal'].astype(str)=='WEIGHTED']
                    if not _w.empty:
                        _wr=_w.iloc[-1]
                        st.caption(f"Origin matched baseline: signal HR {safe(_wr.get('SignalHitRatePct'),1)}% vs same-opening-slot baseline {safe(_wr.get('BaselineHitRatePct'),1)}% • lift {safe(_wr.get('HitRateLiftX'),2)}x • expectancy delta {safe(_wr.get('ExpectancyDeltaPct'),2)}% • research only")
                        _omc=pay.get('origin_matched_confidence')
                        if isinstance(_omc,pd.DataFrame) and not _omc.empty:
                            _mm=dict(zip(_omc['Metric'].astype(str),_omc['Value']))
                            st.caption(f"Matched-edge uncertainty: ΔHR {safe(_mm.get('Hit-rate delta percentage points'),2)} pp • approx 95% CI {safe(_mm.get('Hit-rate delta approx 95% low pp'),1)} to {safe(_mm.get('Hit-rate delta approx 95% high pp'),1)} pp • p≈{safe(_mm.get('Approx two-sided p-value'),3)} • {_mm.get('Matched edge confidence','RESEARCH ONLY')}")
                except Exception: pass
            _cvs=pay.get('continuation_validation_summary')
            if isinstance(_cvs,pd.DataFrame) and not _cvs.empty:
                try:
                    _cm=dict(zip(_cvs['Metric'].astype(str),_cvs['Value']))
                    st.caption(f"Continuation validation (research only): {int(float(_cm.get('Continuation base candidates',0) or 0))} candidates • {int(float(_cm.get('Breakout touched candidates',0) or 0))} breakouts • clean hit rate {safe(_cm.get('Clean post-breakout hit rate %'),1)}% • {_cm.get('Research sample state','LOW SAMPLE — RESEARCH ONLY')}")
                except Exception: pass
        else:st.warning("Trade plan suppressed: "+str(ent.get('plan_reason','data-quality validation failed')))
        st.markdown("<div class='section'>Dynamic Calibration — current ticker</div>",unsafe_allow_html=True);st.caption(f"Prediction Score = {dyn.get('quant_weight',0)*100:.0f}% Dynamic Quant + {dyn.get('early_weight',0)*100:.0f}% Dynamic Early. Small samples cannot take over the model.")
        dc1,dc2=st.columns(2)
        with dc1:
            st.markdown("#### Early dynamic weights");et=dyn.get('early_calibration',{}).get('table',pd.DataFrame()).copy()
            if not et.empty:st.dataframe(et,use_container_width=True,hide_index=True)
        with dc2:
            st.markdown("#### Quant dynamic weights");qt=dyn.get('quant_calibration',{}).get('table',pd.DataFrame()).copy()
            if not qt.empty:st.dataframe(qt,use_container_width=True,hide_index=True)
        combos=dyn.get('combinations',pd.DataFrame())
        if isinstance(combos,pd.DataFrame) and not combos.empty:st.markdown("#### Strong Early + Quant combinations");st.dataframe(combos.head(8),use_container_width=True,hide_index=True)
        left,right=st.columns(2)
        with left:st.markdown("#### Quant components");st.dataframe(comp,use_container_width=True,hide_index=True)
        with right:st.markdown("#### Early Prediction components");st.dataframe(ec,use_container_width=True,hide_index=True)
        st.markdown("<div class='section'>Static vs Dynamic holdout</div>",unsafe_allow_html=True);st.dataframe(compare_df,use_container_width=True,hide_index=True);st.caption(f"Calibration uses earlier {cmp.get('train_rows',0)} rows; holdout compares on later {cmp.get('test_rows',0)} eligible rows. Tiny samples do not prove Dynamic superiority.")
        st.markdown("<div class='section'>Early Prediction event study</div>",unsafe_allow_html=True)
        if ev is None or ev.empty:st.info(f"No qualifying +{target_run}% single-day events in this history window.")
        else:
            evshow=ev.copy();evshow['EventDate']=pd.to_datetime(evshow['EventDate']).dt.strftime('%Y-%m-%d');st.dataframe(evshow,use_container_width=True,hide_index=True)
            if 'EventQuality' in evshow and (evshow['EventQuality']=='OUTLIER REVIEW').any():st.warning("Extreme one-day moves are flagged OUTLIER REVIEW and are excluded from dynamic calibration to reduce corporate-action/anomaly contamination.")
        st.markdown("#### Component calibration")
        cc1,cc2=st.columns(2)
        with cc1:
            st.caption("Early components")
            _render_dataframe_safe_v608(early_cal, "Insufficient Early evidence")
        with cc2:
            st.caption("Quant components")
            _render_dataframe_safe_v608(quant_cal, "Insufficient Quant evidence")
        if pay.get('excel'):
            with analyze_excel_top.container():st.download_button("⬇️ Download Analyze Excel",data=pay['excel'],file_name=f"AI_Stock_Hunter_V{APP_VERSION}_Analyze_{t}_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",use_container_width=True,key="analyze_excel_top_v624")
        elif pay.get('excel_error'):
            with analyze_excel_top.container():st.warning("Analyze completed, but Excel export failed: "+str(pay.get('excel_error'))+". The analysis below is still valid.")
        st.markdown("<div class='section'>📊 Price chart</div>",unsafe_allow_html=True);chart_period=st.radio("Range",["5D","1M","3M","6M","1Y","MAX"],horizontal=True,index=2,key=f"simple_period_{t}");chart_tf="1D" if chart_period in ("3M","6M","1Y","MAX") else "1H";chart_layers=["EMA20","EMA50","Volume"];chart_rsi=False;chart_macd=False
        with st.expander("Advanced chart",expanded=False):
            chart_tf=st.selectbox("Timeframe",["15m","1H","1D","1W"],2,key=f"adv_tf_{t}");chart_layers=st.multiselect("Layers",["EMA9","EMA20","EMA50","VWAP","Volume"],default=["EMA20","EMA50","Volume"],key=f"adv_layers_{t}");ac1,ac2=st.columns(2);chart_rsi=ac1.checkbox("RSI",False,key=f"adv_rsi_{t}");chart_macd=ac2.checkbox("MACD",False,key=f"adv_macd_{t}")
        chart_interval,chart_fetch_period,chart_capped=chart_request(chart_tf,chart_period);cd=fetch_ohlcv(t,chart_fetch_period,chart_interval)
        if cd is not None and len(cd)>0:
            cf=compute_features(cd,intraday=chart_interval in ("5m","15m","30m","1h"));st.plotly_chart(chart(cf,f"{t} • {chart_tf} • {chart_period}",chart_layers,chart_rsi,chart_macd,trade_plan=ent if ca_report.get('data_quality')=='OK' else None,current_price=latest_live.get('price')),use_container_width=True,config=CHART_CONFIG,key=f"main_chart_{t}_{chart_tf}_{chart_period}")
            if chart_capped:st.caption("Intraday display history is provider-capped. This affects the chart only, not model calculations.")

with tab_optimizer:
    st.markdown("<div class='section'>🧠 Optimizer — is the candidate model actually better?</div>",unsafe_allow_html=True)
    optimizer_excel_top=st.empty()
    _opt_reg=_load_model_registry_v613();_opt_models=list((_opt_reg or {}).get('models',[]) or [])
    _opt_daily_eligible=sum(1 for m in _opt_models for sc in (m.get('scopes',{}) or {}).values() if str((sc or {}).get('status',''))=='SHADOW ELIGIBLE')
    _opt_hourly_eligible=sum(1 for m in _opt_models for scope in (m.get('hourly_scopes',{}) or {}).values() for sc in (scope or {}).values() if str((sc or {}).get('status',''))=='SHADOW ELIGIBLE')
    _oc1,_oc2,_oc3=st.columns(3);_oc1.metric('Saved OOS runs',len(_opt_models));_oc2.metric('Eligible daily models',_opt_daily_eligible);_oc3.metric('Eligible hourly models',_opt_hourly_eligible)
    st.caption("Simple rule: Optimizer is for proving a better model out-of-sample. V6.3.9.46 keeps Fold 4 as a final eligibility test only: registry selection never ranks models by Fold4 lift. The newest eligible 1Y run wins within the most specific market tier, and Hourly horizon choice inside that run uses inner validation/stability only. Daily/Core weights remain Production unless a Daily model passes and OOS OPTIMIZED is selected.")
    with st.expander("Import prior V6.1.2 Optimizer workbooks into Model Registry"):
        imported_files=st.file_uploader("Optimizer .xlsx files",type=["xlsx"],accept_multiple_files=True,key="optimizer_import_v613")
        if st.button("⬆️ Import selected workbooks",key="optimizer_import_btn_v613",use_container_width=True,disabled=not imported_files):
            msgs=[]
            for uf in imported_files or []:
                ok,msg=_import_optimizer_workbook_v613(uf);msgs.append((ok,uf.name,msg))
            for ok,name,msg in msgs:
                (st.success if ok else st.warning)(f"{name}: {msg}")
            if any(x[0] for x in msgs):st.rerun()
        reg_now=_load_model_registry_v613();st.caption(f"Registry currently stores {len(reg_now.get('models',[]))} optimization run(s). V6.3.9.46 imports both Daily and Hourly OOS sheets, including inner-validation metadata used for holdout-isolated registry selection. A prior V6.3.9.45 workbook can repopulate the proven models after redeploy.")
    o_market=st.radio("Optimization universe",["ALL 151","ALL 352","US 51","US 201","HONG KONG 50","HONG KONG 101","TEL AVIV 50"],horizontal=True,key="o_market_v612")
    o_hist=st.selectbox("History",["1y","5y"],0,key="o_hist_v63944")
    c1,c2,c3,c4=st.columns(4);o_horizon=c1.selectbox("Daily horizon",[1,2,3,5],2,key="o_horizon_v612");o_target=c2.selectbox("Daily target %",[3,5,10,15],0,key="o_target_v612");o_htarget=c3.selectbox("Hourly target %",[1,2,3],2,key="o_htarget_v612");o_min=c4.number_input("Min training events",6,150,12,1,key="o_min_v63945",help="1Y walk-forward default: 12 training events. This controls per-stock fold eligibility; final SHADOW ELIGIBLE OOS safeguards are unchanged.")
    o_hours=st.multiselect("Hourly horizons",["1h","2h","4h"],default=["1h","2h","4h"],key="o_hours_v612");hour_map={'1h':1,'2h':2,'4h':4}
    a,_=_lab_snapshot_v603('entry');busy=bool(a and a.get('status') in ('running','stopping'));c1,c2=st.columns([2,1])
    with c1:
        if st.button("▶ Run Entry Optimization",key="entry612_start",use_container_width=True,disabled=busy):
            uni={'ALL 151':VALIDATION_151,'ALL 352':VALIDATION_352,'US 51':US_51,'US 201':US_201,'HONG KONG 50':HK_50,'HONG KONG 101':HK_101,'TEL AVIV 50':TASE_50}[o_market]
            cfg={'tickers':[x for x in uni.split(',') if x],'market':o_market,'history':o_hist,'target':float(o_target),'horizon':int(o_horizon),'min_events':int(o_min),'hourly_target':int(o_htarget),'hourly_bars':tuple(hour_map[x] for x in o_hours) or (1,2,4)}
            ok,msg=_start_lab_v603('entry',_entry_worker_v603,cfg,total=len(cfg['tickers']))
            if ok:st.success("Optimizer started server-side. You can leave this tab and return later.");st.rerun()
            else:st.warning(msg)
    with c2:
        if st.button("■ Stop Optimizer",key="entry612_stop",use_container_width=True,disabled=not busy or (a and a.get('status')=='stopping')):
            ok,msg=_stop_lab_v603('entry');st.warning(msg) if ok else st.info(msg);st.rerun()
    if busy:_lab_live_fragment_v603('entry')
    else:_render_lab_status_v603('entry')
    a,last=_lab_snapshot_v603('entry');snap=a if a and a.get('payload') else last
    if snap and snap.get('payload'):
        pay=snap['payload'];opt=_coerce_dataframe_v608(pay.get('optimizer'));weights=_coerce_dataframe_v608(pay.get('optimizer_weights'));hop=_coerce_dataframe_v608(pay.get('hourly_optimizer'));hweights=_coerce_dataframe_v608(pay.get('hourly_optimizer_weights'));regsel=_coerce_dataframe_v608(pay.get('registry_selection'));regaudit=_coerce_dataframe_v608(pay.get('registry_candidate_audit'));pm=_coerce_dataframe_v608(pay.get('premove_summary'));hl=_coerce_dataframe_v608(pay.get('hourly_summary'));integrity=_coerce_dataframe_v608(pay.get('integrity'));fold_coverage=_coerce_dataframe_v608(pay.get('fold_coverage'))
        if not integrity.empty:
            st.markdown("#### Optimizer Integrity")
            st.dataframe(integrity,use_container_width=True,hide_index=True)
            _run_status=str(integrity.iloc[0].get('Run Status',''))
            _eligible_daily=int(float(integrity.iloc[0].get('Eligible Daily Scopes',0) or 0));_eligible_hourly=int(float(integrity.iloc[0].get('Eligible Hourly Scopes',0) or 0))
            if _run_status.startswith('FAILED') and _eligible_hourly<=0:
                st.error("Optimizer produced no usable Daily OOS observations and no eligible Hourly OOS model. Inspect Skipped diagnostics.")
            elif _eligible_daily<=0 and _eligible_hourly>0:
                st.success(f"Hourly OOS timing ready: {_eligible_hourly} SHADOW ELIGIBLE scope(s). Daily/Core weights stay on Production until Daily OOS passes.")
            elif _eligible_daily>0:
                st.success(f"OOS models ready: {_eligible_daily} Daily SHADOW ELIGIBLE scope(s) and {_eligible_hourly} Hourly scope(s).")
            else:
                st.warning("Optimizer finished, but no OOS scope reached SHADOW ELIGIBLE. Production weights/timing remain active.")
        if not fold_coverage.empty:
            st.markdown("#### 1Y Walk-Forward Fold Coverage")
            st.caption("Shows how many stocks actually met the per-stock training-event requirement in each chronological fold. This diagnoses sample loss before model selection.")
            st.dataframe(fold_coverage.round(2),use_container_width=True,hide_index=True)
        if not opt.empty:
            st.markdown("#### Learned Entry Model — OOS first");show=opt.copy()
            for c in ['Inner median OOS lift','Inner worst OOS lift','Final Fold4 OOS lift']:
                if c in show:show[c]=show[c].map(lambda x:f"{float(x):.3f}x ({(float(x)-1)*100:+.1f}%)" if pd.notna(x) else '—')
            st.dataframe(show,use_container_width=True,hide_index=True)
        if not hop.empty:
            st.markdown("#### Hourly Timing Model — matched-hour OOS");hshow=hop.copy()
            for c in ['Inner median OOS lift','Inner worst OOS lift','Fold4 matched OOS lift']:
                if c in hshow:hshow[c]=hshow[c].map(lambda x:f"{float(x):.3f}x ({(float(x)-1)*100:+.1f}%)" if pd.notna(x) else '—')
            st.dataframe(hshow,use_container_width=True,hide_index=True)
        with st.expander("Details — weights, registry, lift and diagnostics",expanded=False):
            if not weights.empty:
                st.markdown("#### Daily learned weights");st.dataframe(weights.round(3),use_container_width=True,hide_index=True)
            if not hweights.empty:
                st.markdown("#### Hourly learned weights");st.dataframe(hweights.round(3),use_container_width=True,hide_index=True)
            if not regsel.empty:
                st.markdown("#### Model Registry — holdout-isolated active selection")
                st.caption("Fold4 is pass/fail evidence only. It is not used to rank eligible models. Selection = market specificity → newest eligible 1Y run → inner validation/stability.")
                st.dataframe(regsel,use_container_width=True,hide_index=True)
            if not regaudit.empty:
                st.markdown("#### Registry Candidate Audit")
                st.caption("All eligible candidates considered by the registry. 'Selected' shows the live choice; Fold4 lift is displayed only for audit.")
                st.dataframe(regaudit,use_container_width=True,hide_index=True)
            if not pm.empty:
                st.markdown("#### Pre-Move Lift — what appears before the move");st.dataframe(pm.round(3),use_container_width=True,hide_index=True)
            if not hl.empty:
                st.markdown("#### Hourly Lift — matched against the same hour baseline");st.dataframe(hl.round(3),use_container_width=True,hide_index=True)
            _render_dataframe_safe_v608(pay.get('summary'),"No Entry Score diagnostics.");_render_dataframe_safe_v608(pay.get('market_gate'),"No market gate diagnostics.")

    with st.expander("🧪 Advanced Research — Cross-Stock Validator + Pre-Move Discovery",expanded=False):
        st.markdown("#### 🧪 Cross-Stock Research Validator — fixed rule, session-cluster bootstrap")
        st.caption("Research only. Uses the unchanged Setup-Origin rule, a leave-one-session-out same-ticker/same-opening-slot baseline, and a calendar-session cluster bootstrap across stocks. No production weights, thresholds, ranks or Entry gates are changed.")
        rv1,rv2=st.columns(2)
        rv_scope=rv1.selectbox("Research scope",["ALL","NASDAQ","US","HONG KONG","TEL AVIV"],0,key="rv624_scope")
        rv_cap=rv2.selectbox("Stocks to test",[12,25,50,100,200,350],1,key="rv624_cap")
        rv_tickers=_research_validator_universe_v624(rv_scope,int(rv_cap))
        st.caption(f"Fixed research spec: +2.0% target / -1.5% stop / 16×15m forward bars • {len(rv_tickers)} ticker(s) • 60d intraday history when provider permits.")
        rva,_=_lab_snapshot_v603('research_validator');rv_busy=bool(rva and rva.get('status') in ('running','stopping'));rvc1,rvc2=st.columns([2,1])
        with rvc1:
            if st.button("▶ Run Cross-Stock Research Validator",key="rv624_start",use_container_width=True,disabled=rv_busy):
                cfg={'tickers':rv_tickers,'scope':rv_scope,'target_pct':.02,'stop_pct':.015,'horizon_bars':16,'bootstrap_runs':1200}
                ok,msg=_start_lab_v603('research_validator',_research_validator_worker_v624,cfg,total=len(rv_tickers))
                if ok:st.success("Cross-stock validator started server-side. You can leave the app and return later.");st.rerun()
                else:st.warning(msg)
        with rvc2:
            if st.button("■ Stop Research Validator",key="rv624_stop",use_container_width=True,disabled=not rv_busy or (rva and rva.get('status')=='stopping')):
                ok,msg=_stop_lab_v603('research_validator');st.warning(msg) if ok else st.info(msg);st.rerun()
        if rv_busy:_lab_live_fragment_v603('research_validator')
        else:_render_lab_status_v603('research_validator')
        rva,rvlast=_lab_snapshot_v603('research_validator');rvsnap=rva if rva and rva.get('payload') else rvlast
        if rvsnap and rvsnap.get('payload'):
            rvp=rvsnap['payload'];rvsum=_coerce_dataframe_v608(rvp.get('summary'));rvstocks=_coerce_dataframe_v608(rvp.get('stocks'));rvskip=_coerce_dataframe_v608(rvp.get('skipped'))
            if not rvsum.empty:
                st.markdown("##### Cross-stock matched-edge evidence");st.dataframe(rvsum.round(3),use_container_width=True,hide_index=True)
            if not rvstocks.empty:
                with st.expander("Per-stock research audit",expanded=False):st.dataframe(rvstocks.round(3),use_container_width=True,hide_index=True)
            if not rvskip.empty:
                with st.expander(f"Skipped / provider errors ({len(rvskip)})",expanded=False):st.dataframe(rvskip,use_container_width=True,hide_index=True)
        st.markdown("#### 🔭 Pre-Move OOS Discovery — find strong indicators before the rise")
        st.caption("Research only. The first 70% of each stock's history discovers singles/pairs; the later 30% is untouched OOS validation. V6.2.8 separates the research radar from the trade trigger: correlated signals are de-duplicated into independent families, late/already-moved names are blocked, and research stages are WATCH / BUILDING / PRE-MOVE CANDIDATE / STRONG PRE-MOVE CANDIDATE. Trade confirmation remains in Scanner/Analyze.")
        pm1,pm2,pm3,pm4=st.columns(4)
        pm_scope=pm1.selectbox("Pre-Move scope",["NASDAQ","US","HONG KONG","TEL AVIV","ALL"],0,key="pm625_scope")
        pm_cap=pm2.selectbox("Stocks",[12,25,50,100,200,350],1,key="pm625_cap")
        pm_hist=pm3.selectbox("Research history",["1y","5y"],0,key="pm63944_hist")
        pm_target=pm4.selectbox("Future move target %",[3,5,8],1,key="pm625_target")
        pm5,pm6=st.columns(2)
        pm_horizon=pm5.selectbox("Future horizon (days)",[1,2,3,5],2,key="pm625_horizon")
        pm_min_lift=pm6.selectbox("Discovery minimum lift",[1.10,1.20,1.30],1,key="pm625_min_lift")
        pm_tickers=_research_validator_universe_v624(pm_scope,int(pm_cap))
        st.caption(f"Causal target: +{pm_target}% within the next {pm_horizon} daily bars • chronological 70% discovery / 30% validation • singles + automatically discovered indicator pairs • {len(pm_tickers)} ticker(s).")
        pma,_=_lab_snapshot_v603('pre_move');pm_busy=bool(pma and pma.get('status') in ('running','stopping'));pmc1,pmc2=st.columns([2,1])
        with pmc1:
            if st.button("▶ Run Pre-Move OOS Discovery",key="pm625_start",use_container_width=True,disabled=pm_busy):
                cfg={'tickers':pm_tickers,'scope':pm_scope,'history':pm_hist,'target_pct':float(pm_target)/100.0,'horizon_days':int(pm_horizon),'min_discovery_signals':25,'min_validation_signals':12,'min_discovery_lift':float(pm_min_lift)}
                ok,msg=_start_lab_v603('pre_move',_pre_move_discovery_worker_v625,cfg,total=len(pm_tickers))
                if ok:st.success("Pre-Move discovery started server-side. You can leave the app and return later.");st.rerun()
                else:st.warning(msg)
        with pmc2:
            if st.button("■ Stop Pre-Move",key="pm625_stop",use_container_width=True,disabled=not pm_busy or (pma and pma.get('status')=='stopping')):
                ok,msg=_stop_lab_v603('pre_move');st.warning(msg) if ok else st.info(msg);st.rerun()
        if pm_busy:_lab_live_fragment_v603('pre_move')
        else:_render_lab_status_v603('pre_move')
        pma,pmlast=_lab_snapshot_v603('pre_move');pmsnap=pma if pma and pma.get('payload') else pmlast
        if pmsnap and pmsnap.get('payload'):
            pmp=pmsnap['payload'];pmcand=_coerce_dataframe_v608(pmp.get('candidates'));pmev=_coerce_dataframe_v608(pmp.get('evidence'));pmskip=_coerce_dataframe_v608(pmp.get('skipped'))
            if not pmcand.empty:
                st.markdown("##### Current Pre-Move research radar — not trade triggers")
                st.dataframe(pmcand.head(30),use_container_width=True,hide_index=True)
                st.caption("PreMoveProbabilityPct is an empirical OOS hit rate of de-duplicated representative signals, not a guaranteed market probability. PreMoveScore is freshness-adjusted; a Pre-Move Candidate is research radar only and is never the same thing as a live Trade Trigger.")
            else:st.info("No current stock has enough active discovery-selected signals that survived OOS validation for this run.")
            if not pmev.empty:
                with st.expander("OOS indicator / pair evidence",expanded=False):st.dataframe(pmev.head(250).round(3),use_container_width=True,hide_index=True)
            if not pmskip.empty:
                with st.expander(f"Skipped / provider errors ({len(pmskip)})",expanded=False):st.dataframe(pmskip,use_container_width=True,hide_index=True)
    _render_optimizer_top_excel_v625(optimizer_excel_top)

with tab_feedback:
    st.markdown("<div class='section'>↺ Feedback — is the model getting better?</div>",unsafe_allow_html=True)
    feedback_excel_top=st.empty()
    st.caption("The main score uses forward LIVE Scanner outcomes only. Historical Replay stays separate. Success = Target 1 before Invalidation at the scan's primary feedback horizon.")
    _fb_sn0,_fb_oc0=_feedback_frames_v600();_fb_imp=_feedback_improvement_tables_v63924(_fb_sn0,_fb_oc0,APP_VERSION);_fb_progress=_feedback_horizon_progress_v63926(_fb_sn0,_fb_oc0);_fb_horizon_tables={h:_feedback_horizon_detail_v63928(_fb_sn0,_fb_oc0,h) for h in (1,2,3,5)}

    st.markdown("#### ⏱ Outcome progress — early results, not the official score")
    _hp_cols=st.columns(4)
    for _hc,_h in zip(_hp_cols,(1,2,3,5)):
        _hr=_fb_progress[_fb_progress['Horizon'].eq(f'{_h}D')]
        _r=_hr.iloc[0] if not _hr.empty else pd.Series(dtype=object)
        _resolved=int(_r.get('Resolved',0) or 0);_wins=int(_r.get('Wins',0) or 0);_losses=int(_r.get('Losses',0) or 0);_wr=_r.get('Clean Win Rate %',np.nan)
        with _hc:
            st.metric(f"{_h}D resolved",_resolved)
            st.caption(f"{_wins}W / {_losses}L"+(f" • {float(_wr):.1f}% clean WR" if np.isfinite(_wr) else " • no clean result yet"))
    st.caption("These horizon rows are progress indicators. The official success KPI below still uses each scan's configured primary horizon, so an early 1D result never substitutes for a 3D scan target.")

    st.markdown("#### 📋 Outcome results by horizon — visible as soon as they mature")
    _fb_table_h=st.radio("Results table horizon",["1D","2D","3D","5D"],horizontal=True,index=0,key="feedback_results_horizon_v63928")
    _fb_table_hn=int(_fb_table_h[:-1]);_fb_table=_fb_horizon_tables.get(_fb_table_hn,pd.DataFrame())
    if isinstance(_fb_table,pd.DataFrame) and not _fb_table.empty:
        _fb_clean_n=int(_fb_table.get('Result',pd.Series(dtype=str)).isin(['WIN','LOSS']).sum());_fb_open_n=int(_fb_table.get('Result',pd.Series(dtype=str)).eq('OPEN / NONE').sum())
        st.caption(f"{_fb_table_h}: {len(_fb_table)} evaluated rows • {_fb_clean_n} clean resolved • {_fb_open_n} open/none. This is an early-horizon audit table, not a replacement for the official primary-horizon KPI.")
        st.dataframe(_fb_table,use_container_width=True,hide_index=True,height=460)
    else:
        st.info(f"No {_fb_table_h} outcome rows have matured yet.")

    st.markdown("#### 🎯 Official model success — primary horizon only")
    _fi1,_fi2,_fi3,_fi4=st.columns(4)
    _fi1.metric(f"V{APP_VERSION} primary resolved",int(_fb_imp.get('current_n',0)))
    _cr=_fb_imp.get('current_rate',np.nan);_br=_fb_imp.get('baseline_rate',np.nan);_dp=_fb_imp.get('delta_pp',np.nan)
    _fi2.metric("Current win rate",f"{float(_cr):.1f}%" if np.isfinite(_cr) else '—')
    _fi3.metric("Matched prior baseline",f"{float(_br):.1f}%" if np.isfinite(_br) else '—')
    _fi4.metric("Improvement",f"{float(_dp):+.1f} pp" if np.isfinite(_dp) else '—')

    _cv=_fb_sn0[_fb_sn0.get('app_version',pd.Series('',index=_fb_sn0.index)).fillna('').astype(str).eq(APP_VERSION)].copy() if isinstance(_fb_sn0,pd.DataFrame) and not _fb_sn0.empty else pd.DataFrame()
    if _cv.empty:
        st.info(f"No V{APP_VERSION} Scanner/Analyze snapshot has been stored yet. Run Scanner or Analyze on this version; early 1D/2D outcomes will then appear above as they mature, while the official KPI waits for the configured primary horizon.")
    elif int(_fb_imp.get('current_n',0))==0:
        _ph=pd.to_numeric(_cv.get('horizon_days'),errors='coerce').dropna().round().astype(int) if 'horizon_days' in _cv else pd.Series(dtype=int)
        _ph_txt=', '.join(f'{int(h)}D' for h in sorted(_ph.unique())) if not _ph.empty else 'configured primary horizon'
        st.info(f"V{APP_VERSION} snapshots are being collected. Early outcomes may already exist above, but the official model score is waiting for clean resolved primary-horizon outcomes ({_ph_txt}).")
    _fb_status=str(_fb_imp.get('status','COLLECTING FORWARD OUTCOMES'))
    if _fb_status=='IMPROVEMENT EVIDENCE':st.success(f"{_fb_status} • {_fb_imp.get('status_detail','')}")
    elif _fb_status=='DECLINE EVIDENCE':st.error(f"{_fb_status} • {_fb_imp.get('status_detail','')}")
    elif _fb_status in ('EARLY EVIDENCE','NOT YET CLEAR'):st.warning(f"{_fb_status} • {_fb_imp.get('status_detail','')}")
    else:st.info(f"{_fb_status} • {_fb_imp.get('status_detail','')}")
    st.caption("Best proof of improvement: forward live outcomes + same-period Production vs Optimized shadow comparison. We do not promote a model because of Historical Replay alone or a tiny sample.")
    _fb_shadow=_fb_imp.get('shadow',pd.DataFrame())
    if isinstance(_fb_shadow,pd.DataFrame) and not _fb_shadow.empty:
        with st.expander("Production vs Optimized — same-period shadow A/B",expanded=False):st.dataframe(_fb_shadow.round(2),use_container_width=True,hide_index=True)
    _fb_versions=_fb_imp.get('version',pd.DataFrame())
    if isinstance(_fb_versions,pd.DataFrame) and not _fb_versions.empty:
        with st.expander("Performance by app/model version",expanded=False):st.dataframe(_fb_versions.round(2),use_container_width=True,hide_index=True)

    # V6.3.0 Persistence Hub: portable DB backup/restore always works; optional
    # GitHub persistence survives Streamlit redeploys when a token is configured
    # in secrets. The token itself is never shown in the UI or exported.
    try:_feedback_conn_v600().close()
    except Exception:pass
    p_cfg=_feedback_persistence_cfg_v630()
    with st.expander("💾 Persistent Feedback DB — backup / restore",expanded=False):
        pc1,pc2,pc3=st.columns(3)
        pc1.metric("Storage", "GitHub + local" if p_cfg.get('enabled') else "Local + portable backup")
        pc2.metric("DB size",f"{len(_feedback_db_bytes_v630())/1024:.0f} KB")
        pc3.metric("Remote sync", "Configured" if p_cfg.get('enabled') else "Not configured")
        st.download_button("⬇️ Download Feedback DB backup",data=_feedback_db_bytes_v630(),file_name=f"AI_Stock_Hunter_V{APP_VERSION}_Feedback_DB_{datetime.now().strftime('%Y%m%d_%H%M')}.sqlite3",mime="application/octet-stream",use_container_width=True,key="feedback_db_backup_v630")
        restore_file=st.file_uploader("Restore Feedback DB backup (.sqlite3)",type=["sqlite3","db"],key="feedback_db_restore_file_v630")
        rc1,rc2,rc3=st.columns(3)
        with rc1:
            if st.button("♻️ Restore uploaded DB",key="feedback_db_restore_btn_v630",use_container_width=True,disabled=restore_file is None):
                ok,msg=_feedback_restore_bytes_v630(restore_file.getvalue(),push_remote=bool(p_cfg.get('enabled')))
                (st.success if ok else st.error)(msg)
                if ok:st.rerun()
        with rc2:
            if st.button("☁️ Sync DB now",key="feedback_db_push_btn_v630",use_container_width=True,disabled=not p_cfg.get('enabled')):
                ok,msg=_feedback_remote_push_v630();(st.success if ok else st.warning)(msg)
        with rc3:
            if st.button("⬇️ Restore from remote",key="feedback_db_pull_btn_v630",use_container_width=True,disabled=not p_cfg.get('enabled')):
                ok,msg=_feedback_remote_pull_v630(force=True);(st.success if ok else st.warning)(msg)
                if ok:st.rerun()
        if p_cfg.get('enabled'):
            st.caption(f"Durable store: {p_cfg.get('repo')} • {p_cfg.get('branch')} • {p_cfg.get('path')} • automatic sync runs after completed scans, replay runs and newly evaluated outcomes.")
        else:
            st.caption("Portable mode is active. Download the DB backup before redeploying/upgrading and periodically thereafter. Without remote persistence, the Streamlit host's local SQLite file is not guaranteed to survive a host reset/redeploy.")

        st.markdown("**Recover prior Scanner exports into Feedback**")
        scan_imports=st.file_uploader("Import prior Scanner workbooks (.xlsx)",type=["xlsx"],accept_multiple_files=True,key="feedback_scan_import_v639")
        if st.button("📥 Import Scanner snapshots",key="feedback_scan_import_btn_v639",use_container_width=True,disabled=not scan_imports):
            imported_total=0
            for uf in scan_imports or []:
                ok,msg,n=_feedback_import_scanner_workbook_v639(uf)
                imported_total+=int(n or 0)
                (st.success if ok else st.warning)(msg)
            if imported_total and p_cfg.get('enabled'):_feedback_schedule_remote_push_v630()
        st.caption("Import is idempotent: importing the same workbook again does not create duplicate scan/ticker snapshots. Legacy Scanner files that did not save Forecast horizon are recovered as 5D and marked by the import message.")

    with st.expander("🧪 Advanced Research Labs — Replay, Regular Signature, Explosive",expanded=False):
        st.markdown("#### 🧬 Historical Replay V4 — Market-Specific Consensus + Nested Holdout")
        st.caption("V6.3.6 keeps the V3 70/30 combination audit and the stricter market-specific 60/20/20 test: 60% discovers combinations, the next 20% promotes only stable combinations, and the final 20% is untouched until the consensus gate is scored. Two or more family-signature-distinct combinations must agree for the main consensus candidate. Production Entry is unchanged.")
        rp1,rp2,rp3,rp4,rp5=st.columns(5)
        replay_scope=rp1.selectbox("Replay market",["NASDAQ","HONG KONG","TEL AVIV","ALL"],0,key="replay_scope_v630")
        replay_cap=rp2.selectbox("Replay stocks",[25,50,100,200,350],1,key="replay_cap_v630")
        replay_hist=rp3.selectbox("Replay history",["6mo","1y"],1,key="replay_hist_v63944")
        replay_target=rp4.selectbox("Replay target %",[3,5,8],1,key="replay_target_v630")
        replay_horizon=rp5.selectbox("Replay horizon D",[1,2,3,5],2,key="replay_horizon_v630")
        replay_step=st.selectbox("Sample every N trading sessions",[1,3,5,10],2,key="replay_step_v630",help="5 is a balanced default. 1 creates many highly correlated observations; replay keeps them separate from Live Feedback regardless.")
        replay_tickers=_research_validator_universe_v624(replay_scope,int(replay_cap))
        ra,_=_lab_snapshot_v603('historical_replay');replay_busy=bool(ra and ra.get('status') in ('running','stopping'));rr1,rr2=st.columns([2,1])
        with rr1:
            if st.button("▶ Run Historical Replay",key="historical_replay_start_v630",use_container_width=True,disabled=replay_busy):
                rcfg={'tickers':replay_tickers,'scope':replay_scope,'history':replay_hist,'target_pct':float(replay_target)/100.0,'horizon_days':int(replay_horizon),'sample_every':int(replay_step)}
                ok,msg=_start_lab_v603('historical_replay',_historical_replay_worker_v630,rcfg,total=len(replay_tickers)+6)
                if ok:st.success("Historical Replay started server-side. You can leave the app and return later.");st.rerun()
                else:st.warning(msg)
        with rr2:
            if st.button("■ Stop Replay",key="historical_replay_stop_v630",use_container_width=True,disabled=not replay_busy or (ra and ra.get('status')=='stopping')):
                ok,msg=_stop_lab_v603('historical_replay');st.warning(msg) if ok else st.info(msg);st.rerun()
        if replay_busy:_lab_live_fragment_v603('historical_replay')
        else:_render_lab_status_v603('historical_replay')
        replay_runs,replay_events=_feedback_replay_frames_v630(latest_only=True)
        replay_head,replay_ind,replay_stocks,replay_gates,replay_cal=_feedback_replay_scorecards_v631(replay_events)
        if not replay_runs.empty:
            latest_run=replay_runs.iloc[0]
            st.caption(f"Latest replay: {latest_run.get('scope','')} • {latest_run.get('history','')} • +{100*float(latest_run.get('target_pct',0)):.0f}% / {int(latest_run.get('horizon_days',0))}D • {int(latest_run.get('event_rows',0))} sampled rows • {int(latest_run.get('successful_tickers',0))}/{int(latest_run.get('requested_tickers',0))} stocks with usable history.")
        if not replay_head.empty:
            rh=replay_head.iloc[0];rm1,rm2,rm3,rm4=st.columns(4)
            rm1.metric("All-row baseline",f"{float(rh['All Clean Baseline %']):.1f}%" if pd.notna(rh['All Clean Baseline %']) else "—")
            rm2.metric("V2 candidate success",f"{float(rh['V2 Candidate Success %']):.1f}%" if pd.notna(rh['V2 Candidate Success %']) else "—")
            rm3.metric("HIGH CONFIDENCE",f"{float(rh['High Confidence Success %']):.1f}%" if pd.notna(rh['High Confidence Success %']) else "—")
            rm4.metric("HC resolved",int(rh['High Confidence Resolved']))
            st.caption(f"V2 resolved: {int(rh['V2 Candidate Resolved'])} • V2 lift: {float(rh['V2 Lift x']):.2f}x" if pd.notna(rh['V2 Lift x']) else f"V2 resolved: {int(rh['V2 Candidate Resolved'])}. High Confidence is deliberately selective and may return zero cases rather than force a 70% result.")
            if not replay_gates.empty:st.dataframe(replay_gates.round(3),use_container_width=True,hide_index=True)
            if not replay_cal.empty:
                with st.expander("Causal Meta-Probability calibration",expanded=False):st.dataframe(replay_cal.round(2),use_container_width=True,hide_index=True)
        combo_latest,combo_folds_latest=_feedback_replay_combo_frames_v633(latest_only=True)
        # V6.3.4: prefer the already-built workbook kept in the completed background
        # job. This avoids rebuilding a multi-megabyte Excel file during the final
        # Streamlit rerun, which was the main reason the top Stop icon could linger
        # even after 'Run completed'.
        ra_now,rlast_now=_lab_snapshot_v603('historical_replay')
        replay_payload=(ra_now or {}).get('payload') if ra_now and ra_now.get('status')=='completed' else ((rlast_now or {}).get('payload') if rlast_now else None)
        if not combo_latest.empty:
            strong=int(combo_latest['OOS Status'].astype(str).isin(['OOS STRONG','OOS POSITIVE']).sum()) if 'OOS Status' in combo_latest else 0
            target70=int(combo_latest['Research Tier'].astype(str).eq('70% DISCOVERY TIER').sum()) if 'Research Tier' in combo_latest else 0
            valid70=combo_latest[(combo_latest.get('Research Tier','').astype(str)=='70% DISCOVERY TIER') & (combo_latest.get('Validation N',0)>=25)] if 'Research Tier' in combo_latest else pd.DataFrame()
            best_oos=pd.to_numeric(combo_latest.get('Validation Success %'),errors='coerce').max() if 'Validation Success %' in combo_latest else np.nan
            cm1,cm2,cm3=st.columns(3);cm1.metric('OOS-positive combinations',strong);cm2.metric('70% discovery candidates',target70);cm3.metric('Best OOS combination',f"{best_oos:.1f}%" if pd.notna(best_oos) else '—')
            st.caption('Green combinations survived the untouched final 30% and chronological folds. A 70% Discovery combination is only a hypothesis until its OOS column also holds up.')
            with st.expander('Combination Discovery — 70% Discovery / 30% untouched OOS',expanded=True):st.dataframe(_feedback_color_table_v629(combo_latest.head(100).round(3),'OOS Status'),use_container_width=True,hide_index=True,height=520)
            if not combo_folds_latest.empty:
                with st.expander('Walk-Forward OOS folds',expanded=False):st.dataframe(combo_folds_latest.head(500).round(3),use_container_width=True,hide_index=True,height=420)
        consensus_latest,consensus_gates_latest=_feedback_replay_consensus_frames_v634(latest_only=True)
        # Prefer in-memory payload from the just-completed run because it also keeps
        # exact unrounded values before a database round-trip.
        if isinstance(replay_payload,dict):
            if isinstance(replay_payload.get('consensus_combos'),pd.DataFrame):consensus_latest=replay_payload['consensus_combos']
            if isinstance(replay_payload.get('consensus_gates'),pd.DataFrame):consensus_gates_latest=replay_payload['consensus_gates']
        if not consensus_gates_latest.empty:
            two=consensus_gates_latest[consensus_gates_latest['Gate'].astype(str).eq('MARKET CONSENSUS 2+')]
            if not two.empty:
                cg=two.iloc[0];cc1,cc2,cc3=st.columns(3);cc1.metric('Consensus 2+ final success',f"{float(cg['Success Rate %']):.1f}%" if pd.notna(cg['Success Rate %']) else '—');cc2.metric('Final holdout N',int(cg['Resolved']));cc3.metric('Lift',f"{float(cg['Lift x']):.2f}x" if pd.notna(cg['Lift x']) else '—')
            st.caption('Market Consensus uses a stricter nested holdout: final 20% is never used to discover or promote combinations. This is the cleaner test for whether multiple independent patterns really agree.')
            with st.expander('Market-Specific Consensus — 60/20/20 final holdout',expanded=True):st.dataframe(_feedback_color_table_v629(consensus_gates_latest.round(3),'Gate'),use_container_width=True,hide_index=True)
            if not consensus_latest.empty:
                with st.expander('Stable combinations promoted by selector period',expanded=False):st.dataframe(_feedback_color_table_v629(consensus_latest.round(3),'Status'),use_container_width=True,hide_index=True,height=430)
        if not replay_ind.empty:
            with st.expander("Historical Replay indicator summary",expanded=False):st.dataframe(_feedback_color_table_v629(replay_ind.round(3),'Status'),use_container_width=True,hide_index=True)
        if not replay_stocks.empty:
            with st.expander("Historical Replay stock summary",expanded=False):st.dataframe(_feedback_color_table_v629(replay_stocks.round(2),'Model Status'),use_container_width=True,hide_index=True,height=420)
        if not replay_events.empty:
            replay_excel=(replay_payload or {}).get('excel') if isinstance(replay_payload,dict) else None
            if not replay_excel:
                replay_excel=_feedback_workbook_v629({'Replay Success':replay_head,'Replay Gate Comparison':replay_gates,'Market Consensus Gates':consensus_gates_latest,'Market Consensus Combos':consensus_latest,'Combination Discovery':combo_latest,'WalkForward Folds':combo_folds_latest,'Replay Meta Calibration':replay_cal,'Replay Indicators':replay_ind,'Replay Stocks':replay_stocks,'Replay Events':replay_events},{'Tab':'Historical Replay V4','Version':APP_VERSION,'ResearchOnly':'YES — nested market consensus + V3 70/30; separate from Live Feedback'})
            st.download_button("⬇️ Download Historical Replay Excel",data=replay_excel,file_name=f"AI_Stock_Hunter_V{APP_VERSION}_Historical_Replay_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',use_container_width=True,key='replay_excel_v630')

        st.markdown("#### 🔎 Regular Pre-Move Signature Lab — what appears before +2% / +3% / +5% / +8%")
        st.caption("V6.3.8 research-only lab. Broad signatures still use 70/30 discovery/OOS. A stricter High-Confidence Funnel then uses a separate 60% discovery → 20% selector → 20% untouched FINAL HOLDOUT, so any move toward 60–70% must survive data that did not select the signatures. Completed market runs are also loaded into Scanner as a market-specific Regular Radar.")
        rs1,rs2,rs3,rs4=st.columns(4)
        rs_scope=rs1.selectbox("Signature market",["NASDAQ","HONG KONG","TEL AVIV","ALL"],0,key="regular_sig_scope_v637")
        rs_count=rs2.selectbox("Signature stocks",[50,100,200,350],1,key="regular_sig_count_v637")
        rs_hist=rs3.selectbox("Daily history",["1y"],0,key="regular_sig_hist_v63944")
        rs_hour=rs4.selectbox("Hourly history",["60d","6mo","1y"],1,key="regular_sig_hour_v637")
        rr1,rr2=st.columns(2)
        rs_sample=rr1.selectbox("Sample every N bars/sessions",[1,2,5],1,key="regular_sig_sample_v637",help="2 is a good balance between sample size and correlation between adjacent snapshots.")
        rs_use_hour=rr2.checkbox("Include 1H + 2H precursor research",value=True,key="regular_sig_use_hour_v637")
        rsa,_=_lab_snapshot_v603('regular_signature');rs_busy=bool(rsa and rsa.get('status') in ('running','stopping'));rsc1,rsc2=st.columns([2,1])
        with rsc1:
            if st.button("▶ Run Regular Signature Lab",key="regular_sig_start_v637",use_container_width=True,disabled=rs_busy):
                ok,msg=_start_lab_v603('regular_signature',_regular_signature_worker_v637,{'scope':rs_scope,'max_tickers':int(rs_count),'history':rs_hist,'hour_history':rs_hour,'sample_every':int(rs_sample),'use_hourly':bool(rs_use_hour)},total=max(1,int(rs_count)+3))
                if ok:st.success("Regular Signature Lab started server-side. It is testing what appears before +2/+3/+5/+8% moves.");st.rerun()
                else:st.warning(msg)
        with rsc2:
            if st.button("■ Stop Signature Lab",key="regular_sig_stop_v637",use_container_width=True,disabled=not rs_busy or (rsa and rsa.get('status')=='stopping')):
                ok,msg=_stop_lab_v603('regular_signature');st.warning(msg) if ok else st.info(msg);st.rerun()
        if rs_busy:_lab_live_fragment_v603('regular_signature')
        else:_render_lab_status_v603('regular_signature')
        rsa,rslast=_lab_snapshot_v603('regular_signature');rssnap=rsa if rsa and rsa.get('payload') else rslast;rspay=rssnap.get('payload') if rssnap and isinstance(rssnap.get('payload'),dict) else None
        if rspay:
            rss=rspay.get('summary',pd.DataFrame());rsf=rspay.get('funnel',pd.DataFrame());rsp=rspay.get('promoted',pd.DataFrame());rst=rspay.get('top',pd.DataFrame());rsr=rspay.get('radar',pd.DataFrame())
            if isinstance(rss,pd.DataFrame) and not rss.empty:st.dataframe(rss.round(3),use_container_width=True,hide_index=True,height=300)
            if isinstance(rsf,pd.DataFrame) and not rsf.empty:
                _eligible=rsf[pd.to_numeric(rsf.get('Final Holdout N'),errors='coerce').fillna(0)>=20].copy();_best=pd.to_numeric(_eligible.get('Final Hit Rate %'),errors='coerce').max() if not _eligible.empty else np.nan;_hc=int(rsf.get('Funnel Stage',pd.Series(dtype=str)).astype(str).eq('RESEARCH HIGH CONFIDENCE').sum());_tier70=int(rsf.get('Status',pd.Series(dtype=str)).astype(str).eq('70% RESEARCH TIER').sum())
                fc1,fc2,fc3=st.columns(3);fc1.metric('Best FINAL holdout',f'{_best:.1f}%' if pd.notna(_best) else '—');fc2.metric('HC funnel rows',_hc);fc3.metric('70% research tiers',_tier70)
                st.caption('The FINAL 20% is untouched until after signatures are selected. A high percentage with a tiny N stays LOW SAMPLE and is not promoted.')
                with st.expander('High-Confidence Funnel — 60/20/20 FINAL holdout',expanded=True):st.dataframe(_feedback_color_table_v629(rsf.round(3),'Status'),use_container_width=True,hide_index=True,height=420)
            if isinstance(rsp,pd.DataFrame) and not rsp.empty:
                with st.expander('Promoted signatures — Discovery → Selector',expanded=False):st.dataframe(rsp[rsp.get('Promoted',False).astype(bool)].head(150).round(3) if 'Promoted' in rsp else rsp.head(150).round(3),use_container_width=True,hide_index=True,height=380)
            if isinstance(rst,pd.DataFrame) and not rst.empty:
                st.markdown("##### Strongest common signatures that survived OOS")
                st.dataframe(_feedback_color_table_v629(rst.head(80).round(3),'Status'),use_container_width=True,hide_index=True,height=400)
            if isinstance(rsr,pd.DataFrame) and not rsr.empty:
                st.markdown("##### Current regular-rise research radar")
                st.caption("This is research evidence, not a live trade trigger. V6.3.8 also reports the nested final-holdout funnel; Scanner/Analyze still controls live timing, Chase, R:R and distribution risk.")
                st.dataframe(rsr.head(100).round(3),use_container_width=True,hide_index=True,height=430)
            if rspay.get('excel'):
                st.download_button("⬇️ Download Regular Signature Lab Excel",data=rspay['excel'],file_name=f"AI_Stock_Hunter_V{APP_VERSION}_Regular_Signature_Lab_{rs_scope.replace(' ','_')}_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',use_container_width=True,key='regular_sig_excel_v637')

        st.markdown("#### 🚀 Explosive Benchmark Lab — catch the move before +15%")
        st.caption("V6.3.6 research-only benchmark. In addition to split-safe independent explosive legs, it now separates PRE-EXPLOSIVE, CONTINUATION BASE and RE-ACCELERATION states so a valid reset can warn about a second +15% leg instead of being rejected as already moved. Regular Pre-Move +5%/3D remains a separate, unchanged channel.")
        xb1,xb2,xb3=st.columns(3)
        xb_ticker=xb1.text_input("Benchmark ticker","1196.HK",key="explosive_benchmark_ticker_v634").strip().upper()
        xb_hist=xb2.selectbox("Benchmark history",["1y"],0,key="explosive_benchmark_hist_v63944")
        xb_target=xb3.selectbox("Explosive target %",[10,15,20],1,key="explosive_benchmark_target_v634")
        xa,_=_lab_snapshot_v603('explosive_benchmark');xb_busy=bool(xa and xa.get('status') in ('running','stopping'));xbc1,xbc2=st.columns([2,1])
        with xbc1:
            if st.button("▶ Run Explosive Benchmark",key="explosive_benchmark_start_v636",use_container_width=True,disabled=xb_busy):
                ok,msg=_start_lab_v603('explosive_benchmark',_explosive_benchmark_worker_v636,{'ticker':xb_ticker,'history':xb_hist,'target_pct':float(xb_target)/100.0,'horizons':(1,2,3,5)},total=6)
                if ok:st.success("Explosive Benchmark started server-side. You can leave the app and return later.");st.rerun()
                else:st.warning(msg)
        with xbc2:
            if st.button("■ Stop Benchmark",key="explosive_benchmark_stop_v636",use_container_width=True,disabled=not xb_busy or (xa and xa.get('status')=='stopping')):
                ok,msg=_stop_lab_v603('explosive_benchmark');st.warning(msg) if ok else st.info(msg);st.rerun()
        if xb_busy:_lab_live_fragment_v603('explosive_benchmark')
        else:_render_lab_status_v603('explosive_benchmark')
        xa,xlast=_lab_snapshot_v603('explosive_benchmark');xsnap=xa if xa and xa.get('payload') else xlast
        xpay=xsnap.get('payload') if xsnap and isinstance(xsnap.get('payload'),dict) else None
        if xpay:
            xs=xpay.get('summary',pd.DataFrame());xi=xpay.get('indicators',pd.DataFrame());xc=xpay.get('combinations',pd.DataFrame());xe=xpay.get('episodes',pd.DataFrame());xr=xpay.get('recent',pd.DataFrame())
            if isinstance(xs,pd.DataFrame) and not xs.empty:st.dataframe(xs.round(3),use_container_width=True,hide_index=True)
            if isinstance(xr,pd.DataFrame) and not xr.empty:
                st.success("August/September explosive episodes found in the latest history year — inspect the causal warnings below.")
                st.dataframe(xr,use_container_width=True,hide_index=True)
            if isinstance(xe,pd.DataFrame) and not xe.empty:
                with st.expander("Explosive episodes — earliest causal warning before the hit",expanded=True):st.dataframe(xe,use_container_width=True,hide_index=True,height=340)
            xstate=xpay.get('states',pd.DataFrame())
            if isinstance(xstate,pd.DataFrame) and not xstate.empty:
                with st.expander("Explosive state evidence — PRE / CONTINUATION / RE-ACCELERATION",expanded=True):st.dataframe(xstate.round(3),use_container_width=True,hide_index=True,height=330)
            if isinstance(xc,pd.DataFrame) and not xc.empty:
                with st.expander("+15% combination discovery — 70/30 single-stock benchmark",expanded=False):st.dataframe(_feedback_color_table_v629(xc.round(3),'Status'),use_container_width=True,hide_index=True,height=400)
            if isinstance(xi,pd.DataFrame) and not xi.empty:
                with st.expander("Indicator lift before explosive moves",expanded=False):st.dataframe(_feedback_color_table_v629(xi.round(3),'Status'),use_container_width=True,hide_index=True,height=400)
            if xpay.get('excel'):
                st.download_button("⬇️ Download Explosive Benchmark Excel",data=xpay['excel'],file_name=f"AI_Stock_Hunter_V{APP_VERSION}_Explosive_Benchmark_{xpay.get('ticker',xb_ticker)}_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',use_container_width=True,key='explosive_benchmark_excel_v636')
            xaudit=xpay.get('integrity',pd.DataFrame())
            if isinstance(xaudit,pd.DataFrame) and not xaudit.empty:
                n_adj=int(pd.to_numeric(xaudit.get('CorporateActionNormalized',0),errors='coerce').fillna(0).sum());n_bad=int(pd.to_numeric(xaudit.get('IntegritySuspect',0),errors='coerce').fillna(0).sum())
                st.caption(f"Integrity audit: {n_adj} corporate-action scale breaks normalized • {n_bad} unexplained giant-gap bars quarantined.")

        st.markdown("#### 🌐 Explosive Universe Radar V3 — four-score view + continuation/re-acceleration")
        st.caption("Research-only daily early-warning radar. V6.3.7 shows four separate numbers for every stock: Setup Score (quality of preparation), State Score (strength of the current phase), Setup×State Consensus (requires both to be strong), and Explosive Radar Score (state + historical analog/OOS evidence). A score of 100 is a ranking score, not a 100% probability.")
        er1,er2,er3,er4=st.columns(4)
        er_scope=er1.selectbox("Radar market",["HONG KONG","NASDAQ","TEL AVIV","ALL"],0,key="explosive_radar_scope_v635")
        er_count=er2.selectbox("Radar stocks",[50,100,200,350],1,key="explosive_radar_count_v635")
        er_hist=er3.selectbox("Radar history",["1y"],0,key="explosive_radar_hist_v63944")
        er_target=er4.selectbox("Explosive target %",[10,15,20],1,key="explosive_radar_target_v635")
        era,_=_lab_snapshot_v603('explosive_universe');er_busy=bool(era and era.get('status') in ('running','stopping'));erc1,erc2=st.columns([2,1])
        with erc1:
            if st.button("▶ Run Explosive Universe Radar",key="explosive_radar_start_v636",use_container_width=True,disabled=er_busy):
                ok,msg=_start_lab_v603('explosive_universe',_explosive_universe_worker_v636,{'scope':er_scope,'max_tickers':int(er_count),'history':er_hist,'target_pct':float(er_target)/100.0},total=max(1,int(er_count)+2))
                if ok:st.success("Explosive Universe Radar started server-side. You can leave the app and return later.");st.rerun()
                else:st.warning(msg)
        with erc2:
            if st.button("■ Stop Explosive Radar",key="explosive_radar_stop_v636",use_container_width=True,disabled=not er_busy or (era and era.get('status')=='stopping')):
                ok,msg=_stop_lab_v603('explosive_universe');st.warning(msg) if ok else st.info(msg);st.rerun()
        if er_busy:_lab_live_fragment_v603('explosive_universe')
        else:_render_lab_status_v603('explosive_universe')
        era,erlast=_lab_snapshot_v603('explosive_universe');ersnap=era if era and era.get('payload') else erlast;erpay=ersnap.get('payload') if ersnap and isinstance(ersnap.get('payload'),dict) else None
        if erpay:
            ers=erpay.get('summary',pd.DataFrame());erd=erpay.get('radar',pd.DataFrame())
            if isinstance(ers,pd.DataFrame) and not ers.empty:st.dataframe(ers,use_container_width=True,hide_index=True)
            if isinstance(erd,pd.DataFrame) and not erd.empty:
                strong=int(erd.Status.astype(str).str.startswith('STRONG').sum());reacc=int(erd.Status.astype(str).str.contains('RE-ACCELERATION CANDIDATE',regex=False).sum());cont=int(erd.Status.eq('CONTINUATION BASE CANDIDATE').sum());pre=int(erd.Status.astype(str).str.contains('PRE-EXPLOSIVE CANDIDATE',regex=False).sum())
                st.info(f"Current radar V3: {strong} STRONG • {reacc} re-acceleration • {cont} continuation-base • {pre} pre-explosive candidates. Compare Setup, State, Setup×State Consensus and Radar side by side; Radar 100 is not 100% probability.")
                st.dataframe(_feedback_color_table_v629(erd.round(3),'Status'),use_container_width=True,hide_index=True,height=480)
            if erpay.get('excel'):
                st.download_button("⬇️ Download Explosive Universe Radar Excel",data=erpay['excel'],file_name=f"AI_Stock_Hunter_V{APP_VERSION}_Explosive_Radar_{er_scope.replace(' ','_')}_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',use_container_width=True,key='explosive_radar_excel_v636')

    st.markdown("#### 📡 Live Feedback — forward outcomes")
    fb1,fb2=st.columns(2)
    fb_half_life=fb1.selectbox("Recent-feedback half-life (days)",[30,60,90],1,key="feedback_half_life_v611",help="Lower = recent outcomes adapt faster; higher = more stable. This changes analytics only, never production weights automatically.")
    fb_batch=fb2.selectbox("Max outcome windows per refresh",[80,250,500],1,key="feedback_batch_v629",help="Larger universes create more pending outcomes. 250 is a good default; 500 is useful after several large scans.")
    a,_=_lab_snapshot_v603('feedback');busy=bool(a and a.get('status') in ('running','stopping'));c1,c2=st.columns([2,1])
    with c1:
        if st.button("▶ Refresh due outcomes",key="feedback603_start",use_container_width=True,disabled=busy):
            ok,msg=_start_lab_v603('feedback',_feedback_worker_v603,{'max_snapshots':int(fb_batch)},total=1)
            if ok:st.success("Feedback refresh started server-side. You can switch apps and return later.");st.rerun()
            else:st.warning(msg)
    with c2:
        if st.button("■ Stop Feedback refresh",key="feedback603_stop",use_container_width=True,disabled=not busy or (a and a.get('status')=='stopping')):
            ok,msg=_stop_lab_v603('feedback');st.warning(msg) if ok else st.info(msg);st.rerun()
    if busy:_lab_live_fragment_v603('feedback')
    else:_render_lab_status_v603('feedback')
    a,last=_lab_snapshot_v603('feedback');snap=a if a and a.get('payload') else last
    if snap and snap.get('payload') and 'evaluated' in snap['payload']:st.success(f"Evaluated {snap['payload']['evaluated']} due outcome windows in the last refresh.")
    sn,oc=_feedback_frames_v600()
    done={(int(r.snapshot_id),int(r.horizon)) for _,r in oc.iterrows()} if not oc.empty else set()
    pending={h:0 for h in (1,2,3,5)}
    next_windows=[];now_utc=pd.Timestamp.now(tz='UTC');due_now=0
    if not sn.empty:
        for _,r in sn.iterrows():
            for h in (1,2,3,5):
                if (int(r.id),h) not in done:
                    pending[h]+=1
                    try:
                        eta=_feedback_due_at_v612(r.ts_utc,r.get('market',''),h,str(r.get('ticker','')))
                        if eta<=now_utc:due_now+=1
                        next_windows.append((eta,str(r.get('market','')),str(r.get('ticker','')),h))
                    except Exception:pass
    f1,f2,f3,f4,f5,f6=st.columns(6);f1.metric("Snapshots",len(sn));f2.metric("Evaluated",len(oc));f3.metric("Pending 1D",pending[1]);f4.metric("Pending 2D",pending[2]);f5.metric("Pending 3D",pending[3]);f6.metric("Pending 5D",pending[5])
    if next_windows:
        future=[x for x in next_windows if x[0]>now_utc]
        if future:
            nd,mkt,tk,hh=min(future,key=lambda x:x[0])
            st.caption(f"Next trading-session evaluation window: approximately {nd.strftime('%Y-%m-%d %H:%M')} UTC • {mkt} • {hh}D • DB: {_feedback_db_path_v600().name}")
        elif due_now:
            st.caption(f"{due_now} pending window(s) are calendar-eligible now; evaluation still waits for complete provider trading bars. • DB: {_feedback_db_path_v600().name}")
        else:st.caption(f"DB: {_feedback_db_path_v600().name}")
    else:st.caption(f"DB: {_feedback_db_path_v600().name}")
    st.caption("Feedback horizons are trading-session aware: weekends and exchange holidays do not count as 1D/2D/3D/5D. A window is evaluated only after the required number of completed daily bars exists for that ticker.")
    # V6.1.2 Feedback export hotfix: export is always available, even before the
    # first outcome window matures. This lets snapshots/pending windows be audited
    # immediately instead of hiding the Excel button until oc is non-empty.
    stage=pd.DataFrame();disagreement=pd.DataFrame();recent_summary=pd.DataFrame();recent_features=pd.DataFrame();early_entry_validation=pd.DataFrame();merged=pd.DataFrame();primary=pd.DataFrame();headline=pd.DataFrame();indicator_summary=pd.DataFrame();stock_summary=pd.DataFrame();integrity_summary=pd.DataFrame();movement_summary=pd.DataFrame();recommendation_summary=pd.DataFrame();source_audit=pd.DataFrame()
    pending_summary=pd.DataFrame([{'Horizon':h,'Pending':int(pending[h])} for h in (1,2,3,5)])
    if sn.empty:
        st.info("No live Scanner/Analyze snapshots yet. Run Scanner or Analyze; completed decisions are recorded automatically.")
    elif oc.empty:
        st.info("Scanner/Analyze snapshots are being collected. 1D/2D/3D/5D outcome rows will appear when enough future market data exists.")
        st.dataframe(sn.head(30),use_container_width=True,hide_index=True)
    else:
        merged=oc.merge(sn,left_on='snapshot_id',right_on='id',how='left');merged['End Return %']=100*pd.to_numeric(merged.end_return,errors='coerce');merged['MFE %']=100*pd.to_numeric(merged.max_favorable,errors='coerce');merged['MAE %']=100*pd.to_numeric(merged.max_adverse,errors='coerce')
        st.markdown("#### Live-signal audit")
        merged['Clean Outcome']=merged['first_event'].astype(str).map(lambda x:'WIN' if x.startswith('TARGET1 FIRST') else ('LOSS' if x.startswith('INVALIDATION FIRST') else ('AMBIGUOUS' if x.startswith('AMBIGUOUS') else 'OPEN/NONE'))); learning_merged=_feedback_independent_rows_v63934(merged,require_valid_plan=True); clean=learning_merged[learning_merged['Clean Outcome'].isin(['WIN','LOSS'])].copy(); clean['Clean Win']=clean['Clean Outcome'].eq('WIN').astype(float); stage=learning_merged.groupby(['market','horizon','trade_stage'],dropna=False).agg(Signals=('snapshot_id','count'),Avg_End_Return=('End Return %','mean'),Avg_MFE=('MFE %','mean'),Avg_MAE=('MAE %','mean'),Ambiguous=('Clean Outcome',lambda x:int((x=='AMBIGUOUS').sum()))).reset_index(); cw=clean.groupby(['market','horizon','trade_stage'],dropna=False)['Clean Win'].agg(['mean','count']).reset_index().rename(columns={'mean':'Clean Win Rate','count':'Clean Resolved'});stage=stage.merge(cw,on=['market','horizon','trade_stage'],how='left');stage['Clean Win Rate %']=100*stage.pop('Clean Win Rate')
        for c in ['Avg_End_Return','Avg_MFE','Avg_MAE','Clean Win Rate %']:
            if c in stage: stage[c]=pd.to_numeric(stage[c],errors='coerce').round(2)
        primary=_feedback_primary_rows_v629(merged);headline,indicator_summary,stock_summary=_feedback_scorecards_v629(sn,primary);early_entry_validation=_feedback_early_entry_validation_v639(primary)
        integrity_summary=_feedback_integrity_summary_v63934(sn,primary);movement_summary=_feedback_movement_summary_v63934(primary);recommendation_summary=_feedback_recommendation_summary_v63962(merged);source_audit=sn.groupby(['snapshot_source','event_role'],dropna=False).size().reset_index(name='Snapshots') if 'snapshot_source' in sn.columns and 'event_role' in sn.columns else pd.DataFrame()
        st.markdown("#### 🧬 Feedback Integrity — independent events")
        if not integrity_summary.empty:st.dataframe(integrity_summary,use_container_width=True,hide_index=True)
        st.caption("V6.3.9.34: one EventID contributes one ORIGIN observation. Later scans of the same event are TRACKING only. Invalid historical trade-plan geometry is excluded from trade learning, but remains available for movement learning/audit.")
        if not movement_summary.empty:
            st.markdown("#### 📈 Movement Outcome — separate from Trade Outcome")
            st.dataframe(movement_summary.round(3),use_container_width=True,hide_index=True)
            st.caption("Movement asks whether price achieved +3%/+5% MFE. Trade Outcome separately asks whether Target1 was reached before Invalidation. These are no longer mixed.")
        if not recommendation_summary.empty:
            st.markdown("#### 🧭 Decision Outcome Validation — recommendation vs reality")
            st.dataframe(recommendation_summary.round(3),use_container_width=True,hide_index=True)
            st.caption("This table audits what actually happened after the recommendation that existed at snapshot time. ENTRY NOW/Continuation emphasize Target1-first; BUILDING/ARMED emphasize subsequent +3%/+5% movement; TOO LATE tracks false negatives (+3/+5/+10 after the warning).")
        if not source_audit.empty:
            st.markdown("#### 🔁 Scanner + Analyze Feedback sources")
            st.dataframe(source_audit,use_container_width=True,hide_index=True)
            st.caption("Analyze snapshots are stored automatically. EventID integrity keeps repeated Scanner/Analyze observations as TRACKING so they do not inflate independent-event learning.")
        st.markdown("#### 🎯 Official Primary-Horizon Success — independent trade-eligible events")
        if not headline.empty:
            h=headline.iloc[0];m1,m2,m3,m4=st.columns(4)
            m1.metric("אחוז הצלחה",f"{float(h['אחוז הצלחה']):.1f}%" if pd.notna(h['אחוז הצלחה']) else "—")
            m2.metric("הצלחות",int(h['הצלחות']));m3.metric("כשלונות",int(h['כשלונות']));m4.metric("מקרים נקיים",int(h['מקרים נקיים שהוכרעו']))
            if pd.notna(h['כיסוי הכרעה %']):
                st.caption(f"Official success = Target 1 before Invalidation among clean resolved cases at each scan's PRIMARY horizon. Open/unresolved: {int(h['לא הוכרעו / פתוחים'])} • ambiguous: {int(h['דו-משמעיים'])} • resolution coverage: {float(h['כיסוי הכרעה %']):.1f}%")
            else:
                _early_res=int(pd.to_numeric(_fb_progress.get('Resolved',pd.Series(dtype=float)),errors='coerce').fillna(0).sum()) if isinstance(_fb_progress,pd.DataFrame) else 0
                if _early_res>0:st.info(f"There are already {_early_res} clean early-horizon outcomes, but none has matured at its scan's official primary horizon yet. See Outcome progress above.")
                else:st.info("No clean outcomes have matured yet. Run Refresh due outcomes after future trading sessions complete.")
        with st.expander("Detailed live feedback — indicators, stocks, stages and recent lift",expanded=False):
            if not indicator_summary.empty:
                st.markdown("#### 🟢🔴 אינדיקטורים ותנאים — מה עובד ומה עדיין לא")
                st.dataframe(_feedback_color_table_v629(indicator_summary.round(2),'סטטוס'),use_container_width=True,hide_index=True)
                st.caption("ירוק = עבד במדגם הנוכחי מול בסיס הפידבק; אדום = פיגר אחרי הבסיס; צהוב = מעורב; LOW SAMPLE לא מקבל מסקנה.")
            if not stock_summary.empty:
                st.markdown("#### 🟢🔴 סיכום כל המניות שנאספו בפידבק")
                st.dataframe(_feedback_color_table_v629(stock_summary.round(2),'Model Status'),use_container_width=True,hide_index=True,height=520)
                st.caption("SUCCESS/FAILURE דורשים לפחות 3 תוצאות נקיות. מניה עם פחות מזה נשארת LOW SAMPLE / WAITING ולא נצבעת כאילו כבר הוכחה.")
            if not early_entry_validation.empty:
                st.markdown("#### 🧭 Early Entry Validation — ARMED timing vs CONFIRMED")
                st.dataframe(_feedback_color_table_v629(early_entry_validation.round(3),'Evidence'),use_container_width=True,hide_index=True)
                st.caption("Forward live outcomes only. EARLY/MID/LATE ARMED are research buckets reconstructed from the snapshot that existed at scan time; they do not promote a stock to a trade entry. LOW SAMPLE is deliberately left inconclusive.")
            st.markdown("#### Live-signal audit by market / horizon / stage")
            st.dataframe(stage,use_container_width=True,hide_index=True)
            if 'model_disagreement' in merged:
                dg=learning_merged.copy();dg['ResolvedWin']=dg['Clean Outcome'].map({'WIN':1.0,'LOSS':0.0});dgc=dg[np.isfinite(pd.to_numeric(dg['ResolvedWin'],errors='coerce'))]
                if not dgc.empty:
                    dgkeys=['market','horizon']+(['optimized_model_horizon'] if 'optimized_model_horizon' in dgc else [])+['model_disagreement'];disagreement=dgc.groupby(dgkeys,dropna=False).agg(Resolved=('snapshot_id','count'),Win_Rate=('ResolvedWin','mean'),Avg_MFE=('MFE %','mean'),Avg_MAE=('MAE %','mean')).reset_index();disagreement['Win Rate %']=100*disagreement.pop('Win_Rate')
                    st.markdown("#### Production vs Optimized — disagreement tracker");st.dataframe(disagreement.round(2),use_container_width=True,hide_index=True)
                    st.caption("OPTIMIZED ONLY vs PRODUCTION ONLY is a natural live A/B test. Promotion decisions should wait for enough resolved outcomes, not a few recent examples.")
            recent_summary,recent_features=_feedback_learning_v611(merged,half_life_days=int(fb_half_life))
            if recent_summary is not None and not recent_summary.empty:
                st.markdown(f"#### 🧠 Recent-market learning — {int(fb_half_life)}-day half-life");st.dataframe(recent_summary.round(2),use_container_width=True,hide_index=True)
            if recent_features is not None and not recent_features.empty:
                st.markdown("#### Recent Lift by live confirmation / Decision Intelligence research");st.dataframe(recent_features.round(3),use_container_width=True,hide_index=True)
                st.caption("Recent data receives more weight, but LOW SAMPLE rows never change production weights automatically. Candidate changes must run in shadow first.")
            st.markdown("#### Recent evaluated snapshots");showcols=['event_id','event_role','snapshot_source','recommendation_type','entry_path','decision_display_stage','continuation_entry_state','pre_move_pattern_strength','pre_move_radar_status','plan_geometry_valid','plan_geometry_reason','trade_learning_eligible','ticker','market','horizon','scan_mode','snapshot_source','valuation_score','valuation_label','valuation_discount_pct','valuation_fair_low','valuation_fair_high','valuation_evidence','valuation_archetype','valuation_metric_count','valuation_peer_count','valuation_currency','raw_entry_state','entry_action_state','armed_timing_class','armed_timing_reason','setup_confirmed','price_actionable','rr_actionable','confirmed_entry_gate','entry_distance_pct','actionability_missing','evidence_confirmation_gate','move_consumed_before_trigger','target1_progress_pct','live_rr_t1','live_rr_t2','regular_move_consumed_pct','regular_target_pct','regular_lead_window','regular_timeframe','regular_score','regular_hit_rate','regular_baseline','regular_lift','regular_funnel_stage','regular_funnel_final_hit_rate','regular_funnel_final_lift','regular_live_layer','trade_stage','entry_state','optimized_stage','model_disagreement','optimized_score','optimized_match','optimized_model_id','optimized_model_scope','optimized_model_horizon','optimized_oos_lift','optimized_hourly_match','optimized_hourly_horizon','confirmation_pct','daily_setup','fresh_signal','hourly_entry','volume_flow','no_chase','extension_guard','chase_risk_score','chase_risk_label','session_move_pct','since_trigger_pct','volume_trend','market_regime','movement_stage','top_score','opportunity','decision_rank_score','entry_score','hourly','exit_pressure','global_rank','End Return %','MFE %','MAE %','first_event','Clean Outcome'];st.dataframe(merged[[c for c in showcols if c in merged]].head(100),use_container_width=True,hide_index=True)
    excel_feedback=_feedback_workbook_v629({'Success Summary':headline,'Outcome Progress by Horizon':_fb_progress,'Outcome Results 1D':_fb_horizon_tables.get(1,pd.DataFrame()),'Outcome Results 2D':_fb_horizon_tables.get(2,pd.DataFrame()),'Outcome Results 3D':_fb_horizon_tables.get(3,pd.DataFrame()),'Outcome Results 5D':_fb_horizon_tables.get(5,pd.DataFrame()),'Model Version Improvement':_fb_imp.get('version',pd.DataFrame()),'Improvement by Market':_fb_imp.get('market',pd.DataFrame()),'Production vs Optimized Shadow':_fb_imp.get('shadow',pd.DataFrame()),'Indicator Summary':indicator_summary,'Stock Summary':stock_summary,'Early Entry Validation':early_entry_validation,'Snapshots':sn,'Outcomes':oc,'Pending Summary':pending_summary,'Primary Outcomes':primary,'Merged Audit':merged,'Stage Summary':stage,'Production vs Optimized':disagreement,'Feedback Integrity':integrity_summary,'Movement Outcomes':movement_summary,'Decision Outcome Validation':recommendation_summary,'Feedback Source Audit':source_audit,'Recent Weighted Summary':recent_summary,'Recent Feature Lift':recent_features,'Replay Runs':replay_runs,'Replay Success':replay_head,'Replay Indicators':replay_ind,'Replay Stocks':replay_stocks},{'Tab':'Feedback','Version':APP_VERSION,'RecencyHalfLifeDays':int(fb_half_life),'Snapshots':len(sn),'EvaluatedWindows':len(oc),'SuccessDefinition':'Independent Event ORIGIN + valid plan: Target1 before invalidation on each scan primary feedback horizon','OutcomeProgress':'1D/2D/3D/5D early progress plus per-stock horizon tables are displayed as soon as each horizon matures; they never replace the official primary-horizon KPI','ImprovementRule':'Forward live current-version outcomes vs matched prior market/horizon baseline; 30+ clean current outcomes plus separation required for strong evidence','ShadowAB':'Production vs Optimized uses same-period stored disagreement labels','EarlyEntryValidation':'Forward live independent events only; ARMED timing buckets are research-only and never auto-promote Production','EventIntegrity':'EventID de-duplicates same-event scans; ORIGIN learns, TRACKING audits','MovementVsTrade':'Movement +3/+5 MFE is separated from Target1-before-invalidation trade outcome','AnalyzeFeedback':'Analyze snapshots auto-save into the same EventID system; repeated Scanner/Analyze observations are TRACKING and do not inflate independent N','DecisionOutcomeValidation':'Recommendation-stage audit reports realized +3/+5/+10, Target1-first, MFE/MAE by horizon','ReplaySeparation':'Historical Replay is research-only and excluded from Live Feedback success %'})
    with feedback_excel_top.container():st.download_button('⬇️ Download Feedback Excel',data=excel_feedback,file_name=f"AI_Stock_Hunter_V{APP_VERSION}_Feedback_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',use_container_width=True,key='feedback_excel_top_v624')
    st.caption("V6.3.9.64 feedback integrity: EventID de-duplicates same-event scans; ORIGIN learns and TRACKING audits; invalid trade-plan geometry is excluded from trade learning. Snapshot safety retained from V6.3.9.28: successfully completed Scanner runs remain in the same SQLite Feedback DB and the schema migrates in place. Scanner XLSX exports can now be re-imported as recovery snapshots. With [feedback_persistence] GitHub secrets the DB is auto-synced; otherwise download a portable DB backup before redeploys. Historical Replay remains separate and never inflates Live Feedback success %.")

