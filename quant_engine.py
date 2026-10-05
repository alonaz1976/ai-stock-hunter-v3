from __future__ import annotations
import math
import numpy as np
import pandas as pd
import yfinance as yf
import json as _json
import urllib.request as _urlrequest
import urllib.error as _urlerror
import urllib.parse as _urlparse
import time as _time
import threading as _threading

AI_STOCK_HUNTER_ENGINE_BUILD = "6.3.9.65"

ENGINE_VERSION = "6.3.9.65"
ENGINE_BUILD_ID = "V63965-LIQUIDITY-RANK-RR-PREMOVE-CREDIT-20261005-A"

def get_engine_version():
    return ENGINE_VERSION


def _finite(value, default=np.nan):
    """Return a finite float or a caller-supplied default."""
    try:
        x=float(value)
        return x if np.isfinite(x) else default
    except Exception:
        return default


def _series1d(obj, index=None, name=None):
    if isinstance(obj, pd.DataFrame):
        if obj.shape[1] == 0:
            idx = index if index is not None else obj.index
            return pd.Series(np.full(len(idx), np.nan), index=idx, name=name, dtype='float64')
        obj = obj.iloc[:, 0]
    if isinstance(obj, pd.Series):
        idx = obj.index if index is None else index
        vals = pd.to_numeric(obj, errors='coerce').to_numpy(dtype='float64', na_value=np.nan)
        return pd.Series(vals.reshape(-1), index=idx, name=name, dtype='float64')
    arr = np.asarray(obj, dtype='float64').reshape(-1)
    if index is None or len(index) != len(arr):
        index = pd.RangeIndex(len(arr))
    return pd.Series(arr, index=index, name=name, dtype='float64')


def _canonical_ohlcv(df: pd.DataFrame, ticker: str | None = None):
    if df is None or not isinstance(df, pd.DataFrame) or df.empty:
        return None
    required = ['Open', 'High', 'Low', 'Close', 'Volume']
    cols = list(df.columns)
    ticker_u = str(ticker).upper() if ticker else None

    def parts(col):
        return [str(x) for x in col] if isinstance(col, tuple) else [str(col)]

    chosen = {}
    for field in required:
        matches = []
        for pos, col in enumerate(cols):
            pp = parts(col)
            if any(x.lower() == field.lower() for x in pp):
                ticker_match = bool(ticker_u and any(x.upper() == ticker_u for x in pp))
                matches.append((0 if ticker_match else 1, pos))
        if not matches:
            return None
        matches.sort()
        chosen[field] = matches[0][1]

    out = pd.DataFrame(index=df.index.copy())
    for field in required:
        s = _series1d(df.iloc[:, chosen[field]], index=df.index, name=field)
        out[field] = s.to_numpy(dtype='float64')
    out = out.replace([np.inf, -np.inf], np.nan)
    out = out.dropna(subset=required)
    return out if not out.empty else None


# Temporary HKEX counter bridge.  Realord Technology (1196.HK) trades only on
# temporary counter 2922.HK from 14-Sep-2026 until the original 1196 counter
# reopens on 28-Sep-2026.  During that window the app keeps the logical ticker
# 1196.HK everywhere in the UI/database, but current market data is sourced from
# 2922.HK.  Historical 1196 data is stitched to the temporary-counter bars on a
# split-consistent scale so indicators keep their history.
_TEMP_COUNTER_BRIDGES = {
    '1196.HK': {
        'temporary_symbol': '2922.HK',
        'start_date': '2026-09-14',
        'original_reopen_date': '2026-09-28',
        'parallel_end_date': '2026-10-20',
        'subdivision_ratio': 4.0,
    }
}

def _hk_today():
    try:
        return pd.Timestamp.now(tz='Asia/Hong_Kong').date()
    except Exception:
        return pd.Timestamp.utcnow().date()

def temporary_counter_info(ticker: str, on_date=None):
    """Return active temporary-counter metadata for a logical ticker.

    `active_primary` is True only while the original counter is closed.  The
    temporary counter can continue in parallel afterwards, but production data
    automatically returns to the original ticker on its official reopen date.
    """
    t=str(ticker or '').upper().strip()
    cfg=_TEMP_COUNTER_BRIDGES.get(t)
    if not cfg:return None
    try:
        d=pd.Timestamp(on_date).date() if on_date is not None else _hk_today()
        start=pd.Timestamp(cfg['start_date']).date()
        reopen=pd.Timestamp(cfg['original_reopen_date']).date()
        parallel_end=pd.Timestamp(cfg['parallel_end_date']).date()
        if d < start or d > parallel_end:return None
        out=dict(cfg);out.update({'logical_symbol':t,'date':d,'active_primary':bool(start <= d < reopen),'parallel':bool(reopen <= d <= parallel_end)})
        return out
    except Exception:
        return None

def _market_data_symbol(ticker: str, on_date=None):
    info=temporary_counter_info(ticker,on_date)
    if info and info.get('active_primary'):
        return str(info['temporary_symbol']).upper()
    return str(ticker or '').upper().strip()

def _download_ohlcv_symbol(symbol: str, period='6mo', interval='1d'):
    try:
        raw=yf.download(symbol,period=period,interval=interval,auto_adjust=True,progress=False,threads=False,group_by='column')
        return _canonical_ohlcv(raw,ticker=symbol)
    except Exception:
        return None

def _provider_reference_close(symbol: str, ref_date=None, current_price=np.nan, split_ratio=np.nan):
    """Best-effort previous close from the *same provider symbol* as the live quote.

    This matters for temporary/reopened HK counters: historical logical history can be
    stitched across counters for indicators, but session return must compare the live
    quote with the provider counter's own reference close. Known split-ratio variants
    are normalized only when they materially improve scale coherence.
    """
    candidates=[]
    try:
        d=pd.Timestamp(ref_date).date() if ref_date is not None else _hk_today()
    except Exception:
        d=_hk_today()
    try:
        z=_download_ohlcv_symbol(str(symbol).upper(),period='10d',interval='1d')
        if z is not None and not z.empty:
            z=_hk_index(z).dropna(subset=['Close'])
            prior=z.loc[[pd.Timestamp(x).date()<d for x in z.index]]
            if not prior.empty:candidates.append((float(prior['Close'].iloc[-1]),pd.Timestamp(prior.index[-1]).date(),'provider daily'))
    except Exception:pass
    try:
        fi=yf.Ticker(str(symbol).upper()).fast_info
        for key in ('previous_close','regular_market_previous_close'):
            try:
                v=float(fi.get(key,np.nan)) if hasattr(fi,'get') else float(getattr(fi,key,np.nan))
                if np.isfinite(v) and v>0:candidates.append((v,None,'provider fast_info'))
            except Exception:pass
    except Exception:pass
    try:
        info=yf.Ticker(str(symbol).upper()).info
        for key in ('regularMarketPreviousClose','previousClose'):
            try:
                v=float(info.get(key,np.nan))
                if np.isfinite(v) and v>0:candidates.append((v,None,'provider quote info'))
            except Exception:pass
    except Exception:pass
    if not candidates:return np.nan,None,'UNAVAILABLE'
    p=_finite(current_price,np.nan);sr=_finite(split_ratio,np.nan)
    expanded=[]
    for v,dt,src in candidates:
        vals=[(v,dt,src)]
        if np.isfinite(sr) and sr>1:
            vals.extend([(v/sr,dt,src+' / split-normalized'),(v*sr,dt,src+' / split-normalized')])
        expanded.extend([(x,dt,src) for x,dt,src in vals if np.isfinite(x) and x>0])
    if np.isfinite(p) and p>0:
        # Reject absurd scale variants and prefer the reference closest to the live counter.
        plausible=[x for x in expanded if 0.45 <= p/x[0] <= 1.80]
        pool=plausible or expanded
        best=min(pool,key=lambda x:abs(p/x[0]-1.0))
    else:
        best=expanded[0]
    return float(best[0]),best[1],best[2]

def _hk_index(df):
    if df is None or not isinstance(df,pd.DataFrame) or df.empty or not isinstance(df.index,pd.DatetimeIndex):
        return df
    z=df.copy();idx=pd.DatetimeIndex(z.index)
    try:
        if idx.tz is None:idx=idx.tz_localize('Asia/Hong_Kong',ambiguous='NaT',nonexistent='shift_forward')
        else:idx=idx.tz_convert('Asia/Hong_Kong')
        z.index=idx;z=z[~z.index.isna()]
    except Exception:pass
    return z

def _stitch_temporary_counter_history(logical_df,temp_df,ratio=4.0,reopen_date=None):
    """Build one split-consistent logical history across temporary-counter periods.

    Before reopen: legacy original history + temporary counter.
    From reopen onward: the reopened original counter takes priority again.
    Only the pre-temporary legacy segment is rescaled when the observed boundary
    confirms the known subdivision ratio; reopened bars are never divided twice.
    """
    old=_hk_index(logical_df);new=_hk_index(temp_df)
    if old is None or old.empty:return new
    if new is None or new.empty:return old
    old=old.copy();new=new.copy()
    first_new=new.index.min();r=float(ratio) if np.isfinite(_finite(ratio,np.nan)) else 1.0
    legacy=old[old.index < first_new].copy(); resumed=old[old.index >= first_new].copy()
    try:
        if not legacy.empty:
            old_last=float(legacy['Close'].dropna().iloc[-1]);new_first=float(new['Close'].dropna().iloc[0]);obs=old_last/new_first if new_first>0 else np.nan
            if np.isfinite(obs) and r>1 and (0.60*r <= obs <= 1.45*r):
                for c in ('Open','High','Low','Close'):legacy[c]=pd.to_numeric(legacy[c],errors='coerce')/r
                legacy['Volume']=pd.to_numeric(legacy['Volume'],errors='coerce')*r
    except Exception:pass
    if reopen_date is not None:
        try:
            rd=pd.Timestamp(reopen_date).date()
            temp_mid=new.loc[[pd.Timestamp(x).date()<rd for x in new.index]].copy()
            resumed=old.loc[[pd.Timestamp(x).date()>=rd for x in old.index]].copy()
        except Exception:
            temp_mid=new
    else:temp_mid=new
    try:
        z=pd.concat([legacy,temp_mid,resumed],axis=0).sort_index();z=z[~z.index.duplicated(keep='last')]
        z=z.replace([np.inf,-np.inf],np.nan).dropna(subset=['Open','High','Low','Close','Volume'])
        z.attrs['temporary_counter_bridge']='1196.HK->2922.HK';return z if not z.empty else None
    except Exception:return old


def fetch_ohlcv(ticker: str, period='6mo', interval='1d'):
    logical=str(ticker or '').upper().strip();info=temporary_counter_info(logical)
    # During the closure AND the parallel-counter period, reconstruct the missing
    # history through 2922 while allowing reopened 1196 bars to take priority from
    # the official reopen date onward.
    if info and (info.get('active_primary') or info.get('parallel')):
        old=_download_ohlcv_symbol(logical,period,interval);temp=_download_ohlcv_symbol(info['temporary_symbol'],period,interval)
        return _stitch_temporary_counter_history(old,temp,info.get('subdivision_ratio',4.0),info.get('original_reopen_date'))
    return _download_ohlcv_symbol(logical,period,interval)




def _market_timezone_for_ticker(ticker: str):
    t=str(ticker or '').upper()
    if t.endswith('.HK'):
        return 'Asia/Hong_Kong'
    if t.endswith('.TA'):
        return 'Asia/Jerusalem'
    return 'America/New_York'


def fetch_recent_split_events(ticker: str, lookback_days: int = 45):
    """Best-effort recent split metadata from the market-data provider.

    Returns a list of dicts with date/ratio.  Failure is non-fatal because some
    providers expose adjusted prices before their corporate-action endpoint is
    refreshed.
    """
    try:
        ser=yf.Ticker(str(ticker).upper()).splits
        if ser is None or len(ser)==0:
            return []
        out=[]
        now=pd.Timestamp.now(tz='UTC')
        for idx,val in ser.items():
            try:
                ts_local=pd.Timestamp(idx)
                event_date=ts_local.date().isoformat()
                if ts_local.tzinfo is None:
                    ts_utc=ts_local.tz_localize('UTC')
                else:
                    ts_utc=ts_local.tz_convert('UTC')
                ratio=float(val)
                if np.isfinite(ratio) and ratio>0 and (now-ts_utc).days <= int(lookback_days):
                    out.append({'date':event_date,'ratio':ratio})
            except Exception:
                continue
        return sorted(out,key=lambda x:x['date'])
    except Exception:
        return []


def _daily_reference_close(daily, ticker: str, ref_date=None):
    """Return the most recent official/adjusted Daily close before ref_date.

    If the provider already contains a row stamped with ref_date (for example a
    still-forming Daily candle), that row is deliberately excluded when looking
    for the *previous official close* used by live day-change calculations.
    """
    d=_canonical_ohlcv(daily,ticker=ticker) if daily is not None else None
    if d is None or d.empty:
        return np.nan, None
    try:
        tz=_market_timezone_for_ticker(ticker)
        ref_date=ref_date or pd.Timestamp.now(tz=tz).date()
        dates=[pd.Timestamp(x).date() for x in d.index]
        candidates=[i for i,dt in enumerate(dates) if dt < ref_date]
        if candidates:
            i=candidates[-1]
            return float(d['Close'].iloc[i]), dates[i]
        if len(d):
            return float(d['Close'].iloc[-1]), dates[-1]
    except Exception:
        pass
    return np.nan, None


def _latest_daily_close(daily, ticker: str):
    d=_canonical_ohlcv(daily,ticker=ticker) if daily is not None else None
    if d is None or d.empty:
        return np.nan, None
    try:
        return float(d['Close'].iloc[-1]), pd.Timestamp(d.index[-1]).date()
    except Exception:
        return np.nan, None


def _session_reference_close_v623(daily, ticker: str, market_phase=None, market_date=None):
    """Resolve previous official close for the analysis session, not the calendar day.

    After exchange-date rollover/weekends, the latest Daily bar is still the
    session being audited. PRE-market instead belongs to the upcoming exchange day.
    Returns (previous_close, previous_session_date, active_session_date, context).
    """
    d=_canonical_ohlcv(daily,ticker=ticker) if daily is not None else None
    if d is None or d.empty:
        return np.nan, None, None, 'NO DAILY DATA'
    try:
        tz=_market_timezone_for_ticker(ticker)
        md=pd.Timestamp(market_date).date() if market_date is not None else pd.Timestamp.now(tz=tz).date()
        dates=[pd.Timestamp(x).date() for x in d.index]
        last_date=dates[-1]
        phase=str(market_phase or '').upper().strip()
        if phase in ('PRE-MARKET','PRE-OPEN'):
            return float(d['Close'].iloc[-1]),last_date,md,'UPCOMING SESSION / PRE-OPEN'
        if phase=='CLOSED':
            if len(d)>=2:
                return float(d['Close'].iloc[-2]),dates[-2],last_date,'LAST COMPLETED SESSION'
            return np.nan,None,last_date,'LAST COMPLETED SESSION'
        prev,prev_date=_daily_reference_close(daily,ticker,ref_date=md)
        return prev,prev_date,md,'CURRENT SESSION'
    except Exception:
        return np.nan,None,None,'UNRESOLVED'


def _align_current_quote_to_daily(price, daily, ticker: str, split_ratio=np.nan):
    """Protect the current quote from mixed pre/post-split provider scales.

    A fresh quote is never blindly trusted as the scale anchor when it is far
    from the newest Daily scale.  With explicit recent split metadata we may
    transform the quote by that ratio.  Without metadata, a >55% scale gap is
    treated as suspicious and the quote is not allowed to anchor other frames.
    """
    out={'price':_finite(price,np.nan),'adjusted':False,'scale_suspect':False,'details':[]}
    p=out['price']
    ref,_=_latest_daily_close(daily,ticker)
    if not (np.isfinite(p) and p>0 and np.isfinite(ref) and ref>0):
        return out
    r=p/ref
    if 0.45 <= r <= 1.55:
        return out
    sr=_finite(split_ratio,np.nan)
    if np.isfinite(sr) and sr>0:
        candidates=[('divide',p/sr),('multiply',p*sr)]
        best=None
        for mode,val in candidates:
            if not (np.isfinite(val) and val>0):
                continue
            err=abs(val/ref-1.0)
            if best is None or err<best[0]:
                best=(err,mode,val)
        if best is not None and best[0] <= 0.45:
            out['price']=float(best[2]); out['adjusted']=True
            out['details'].append(f'fresh quote split-normalized ({best[1]} by {sr:g})')
            return out
    out['scale_suspect']=True
    out['details'].append(f'fresh quote scale {r:.3f}x vs latest Daily; no safe corporate-action normalization')
    return out


def frame_price_snapshot(ticker: str, frame, max_age_minutes: float=60.0):
    """Summarize the newest bar of an already-fetched intraday frame.

    `fresh` is intentionally strict: the newest bar must belong to the current
    local market date *and* be recent enough.  This prevents an old pre-split
    15m/1H candle from being presented as today's online price.
    """
    out={'price':np.nan,'timestamp':None,'timestamp_label':'—','age_minutes':np.nan,
         'same_session_date':False,'fresh':False,'source':'unavailable'}
    x=_canonical_ohlcv(frame,ticker=ticker) if frame is not None else None
    if x is None or x.empty or not isinstance(x.index,pd.DatetimeIndex):
        return out
    try:
        tz=_market_timezone_for_ticker(ticker)
        idx=pd.DatetimeIndex(x.index)
        if idx.tz is None:
            idx=idx.tz_localize(tz,ambiguous='NaT',nonexistent='shift_forward')
        else:
            idx=idx.tz_convert(tz)
        x=x.copy(); x.index=idx; x=x[~x.index.isna()].dropna(subset=['Close'])
        if x.empty:return out
        ts=pd.Timestamp(x.index[-1]); now=pd.Timestamp.now(tz=tz)
        age=max(0.0,(now-ts).total_seconds()/60.0); same=ts.date()==now.date()
        out.update({'price':float(x['Close'].iloc[-1]),'timestamp':ts.isoformat(),
                    'timestamp_label':ts.strftime('%Y-%m-%d %H:%M'),'age_minutes':age,
                    'same_session_date':bool(same),'fresh':bool(same and age<=float(max_age_minutes))})
    except Exception:
        pass
    return out


def _quote_timestamp_local(value, ticker: str):
    """Convert provider epoch/datetime to the exchange-local timestamp."""
    if value is None:
        return None
    try:
        if isinstance(value, (int, float, np.integer, np.floating)) and np.isfinite(float(value)):
            ts=pd.to_datetime(float(value),unit='s',utc=True)
        else:
            ts=pd.Timestamp(value)
            if ts.tzinfo is None:
                ts=ts.tz_localize('UTC')
        return ts.tz_convert(_market_timezone_for_ticker(ticker))
    except Exception:
        return None


def _quote_age_snapshot(price, ts, ticker: str, source: str, max_age_minutes: float=35.0,
                        trade_age_minutes: float=8.0, latency_hint: str='DELAYED/CURRENT-SESSION'):
    """Build a timestamp-verified current-session quote candidate."""
    out={'price':_finite(price,np.nan),'timestamp':None,'timestamp_label':'—','age_minutes':np.nan,
         'same_session_date':False,'fresh':False,'display_current':False,'trade_fresh':False,
         'anchor_eligible':False,'provider_timestamp_verified':False,'source':source,
         'quote_status':latency_hint}
    p=out['price']; local=_quote_timestamp_local(ts,ticker)
    if not (np.isfinite(p) and p>0 and local is not None):
        return out
    try:
        tz=_market_timezone_for_ticker(ticker); now=pd.Timestamp.now(tz=tz)
        age=max(0.0,(now-local).total_seconds()/60.0); same=local.date()==now.date()
        current=bool(same and age<=float(max_age_minutes))
        trade_ok=bool(current and age<=float(trade_age_minutes))
        status='LIVE/NEAR-REALTIME' if trade_ok else ('DELAYED/CURRENT-SESSION' if current else 'STALE')
        out.update({'timestamp':local.isoformat(),'timestamp_label':local.strftime('%Y-%m-%d %H:%M'),
                    'age_minutes':age,'same_session_date':same,'fresh':current,
                    'display_current':current,'trade_fresh':trade_ok,'anchor_eligible':current,
                    'provider_timestamp_verified':True,'quote_status':status})
    except Exception:
        pass
    return out


def _fetch_yahoo_direct_quote(ticker: str):
    """Direct Yahoo quote endpoint with exchange timestamp, independent of bar history."""
    try:
        symbol=_urlparse.quote(str(ticker).upper(),safe='')
        url=f'https://query1.finance.yahoo.com/v7/finance/quote?symbols={symbol}'
        req=_urlrequest.Request(url,headers={'Accept':'application/json','User-Agent':'Mozilla/5.0 (AI Stock Hunter quote fallback)'})
        with _urlrequest.urlopen(req,timeout=6) as resp:
            obj=_json.loads(resp.read().decode('utf-8','replace'))
        rows=((obj or {}).get('quoteResponse') or {}).get('result') or []
        if not rows:return {'price':np.nan,'display_current':False,'fresh':False,'trade_fresh':False,'anchor_eligible':False}
        r=rows[0] if isinstance(rows[0],dict) else {}
        cand=_quote_age_snapshot(r.get('regularMarketPrice',np.nan),r.get('regularMarketTime'),ticker,
                                 'Yahoo direct quote',35.0,8.0)
        cand['provider_prev_close']=_finite(r.get('regularMarketPreviousClose',np.nan),np.nan)
        cand['market_state']=r.get('marketState')
        return cand
    except Exception:
        return {'price':np.nan,'display_current':False,'fresh':False,'trade_fresh':False,'anchor_eligible':False}


def _fetch_yahoo_metadata_quote(ticker: str):
    """Second Yahoo path: quote/history metadata instead of intraday-bar download."""
    try:
        tk=yf.Ticker(str(ticker).upper())
        meta=tk.get_history_metadata() if hasattr(tk,'get_history_metadata') else {}
        if not isinstance(meta,dict):meta={}
        price=meta.get('regularMarketPrice',meta.get('currentPrice',np.nan))
        ts=meta.get('regularMarketTime')
        return _quote_age_snapshot(price,ts,ticker,'Yahoo quote metadata',35.0,8.0)
    except Exception:
        return {'price':np.nan,'display_current':False,'fresh':False,'trade_fresh':False,'anchor_eligible':False}


def _fetch_yahoo_info_quote(ticker: str):
    """Third Yahoo path: quoteSummary/info. Slower, so used only after metadata fails."""
    try:
        tk=yf.Ticker(str(ticker).upper())
        info=tk.get_info() if hasattr(tk,'get_info') else getattr(tk,'info',{})
        if not isinstance(info,dict):info={}
        price=info.get('regularMarketPrice',info.get('currentPrice',np.nan))
        ts=info.get('regularMarketTime')
        return _quote_age_snapshot(price,ts,ticker,'Yahoo quote info',35.0,8.0)
    except Exception:
        return {'price':np.nan,'display_current':False,'fresh':False,'trade_fresh':False,'anchor_eligible':False}


# V6.3.9.27 — live top-of-book (L1) pressure.
# This is deliberately a timing/confirmation diagnostic only. It does NOT
# change MACD/RSI/RVOL, Money Flow, Opportunity, Decision Rank or base Top Score.
_ORDER_BOOK_CACHE_V63927={}
_ORDER_BOOK_LOCK_V63927=_threading.RLock()

def fetch_order_book_pressure(ticker: str, ttl_seconds: float=20.0):
    """Best-effort L1 bid/ask-size imbalance for live timing.

    This is *top of book* only, not full Level-2 depth.  When the provider does
    not expose trustworthy bid/ask sizes the function returns NO DATA rather
    than synthesizing order-book pressure from price/volume indicators.
    """
    logical=str(ticker or '').upper().strip()
    base={'state':'NO DATA','imbalance_pct':np.nan,'buy_pressure_pct':np.nan,
          'sell_pressure_pct':np.nan,'bid':np.nan,'ask':np.nan,'bid_size':np.nan,
          'ask_size':np.nan,'spread_pct':np.nan,'source':'UNAVAILABLE',
          'timestamp_label':'—','age_minutes':np.nan,'market_state':'UNKNOWN',
          'available':False,'timing_eligible':False,'level':'L1 TOP OF BOOK'}
    if not logical:return base
    now_epoch=_time.time()
    with _ORDER_BOOK_LOCK_V63927:
        cached=_ORDER_BOOK_CACHE_V63927.get(logical)
        if cached and now_epoch-float(cached.get('_cached_at',0))<=float(ttl_seconds):
            return dict(cached.get('payload',base))
    try:
        try:
            tz=_market_timezone_for_ticker(logical);now_local=pd.Timestamp.now(tz=tz)
            provider=_market_data_symbol(logical,now_local.date())
        except Exception:
            provider=logical
        row={}
        # Fast path: Yahoo quote endpoint normally exposes bid/ask and sizes.
        try:
            symbol=_urlparse.quote(str(provider).upper(),safe='')
            url=f'https://query1.finance.yahoo.com/v7/finance/quote?symbols={symbol}'
            req=_urlrequest.Request(url,headers={'Accept':'application/json','User-Agent':'Mozilla/5.0 (AI Stock Hunter L1 book)'})
            with _urlrequest.urlopen(req,timeout=5) as resp:
                obj=_json.loads(resp.read().decode('utf-8','replace'))
            rows=((obj or {}).get('quoteResponse') or {}).get('result') or []
            if rows and isinstance(rows[0],dict):row=rows[0]
        except Exception:
            row={}
        # Slower fallback. Do not derive pressure unless actual size fields exist.
        if not row:
            try:
                tk=yf.Ticker(str(provider).upper())
                info=tk.get_info() if hasattr(tk,'get_info') else getattr(tk,'info',{})
                if isinstance(info,dict):row=info
            except Exception:
                row={}
        bid=_finite(row.get('bid'),np.nan);ask=_finite(row.get('ask'),np.nan)
        bid_sz=_finite(row.get('bidSize'),np.nan);ask_sz=_finite(row.get('askSize'),np.nan)
        ts=_quote_timestamp_local(row.get('regularMarketTime'),logical)
        market_state=str(row.get('marketState','UNKNOWN') or 'UNKNOWN').upper()
        age=np.nan;same=False
        if ts is not None:
            try:
                now=pd.Timestamp.now(tz=_market_timezone_for_ticker(logical));age=max(0.0,(now-ts).total_seconds()/60.0);same=(ts.date()==now.date())
            except Exception:pass
        if np.isfinite(bid_sz) and np.isfinite(ask_sz) and bid_sz>=0 and ask_sz>=0 and (bid_sz+ask_sz)>0:
            imbalance=float(np.clip(100.0*(bid_sz-ask_sz)/(bid_sz+ask_sz),-100,100))
            if imbalance>=15:state='BULLISH'
            elif imbalance<=-15:state='BEARISH'
            else:state='NEUTRAL'
            buy=max(0.0,imbalance);sell=max(0.0,-imbalance)
            spread=np.nan
            if np.isfinite(bid) and np.isfinite(ask) and bid>0 and ask>=bid:
                mid=(bid+ask)/2.0
                if mid>0:spread=100.0*(ask-bid)/mid
            # Only current regular-session L1 is eligible as a live timing confirmation.
            timing_ok=bool(same and (not np.isfinite(age) or age<=10.0) and market_state in ('REGULAR','OPEN'))
            payload={'state':state,'imbalance_pct':round(imbalance,1),'buy_pressure_pct':round(buy,1),
                     'sell_pressure_pct':round(sell,1),'bid':bid,'ask':ask,'bid_size':bid_sz,'ask_size':ask_sz,
                     'spread_pct':round(spread,3) if np.isfinite(spread) else np.nan,
                     'source':'Yahoo L1 bid/ask sizes','timestamp_label':ts.strftime('%Y-%m-%d %H:%M') if ts is not None else '—',
                     'age_minutes':age,'market_state':market_state,'available':True,
                     'timing_eligible':timing_ok,'level':'L1 TOP OF BOOK'}
        else:
            payload={**base,'bid':bid,'ask':ask,'bid_size':bid_sz,'ask_size':ask_sz,
                     'timestamp_label':ts.strftime('%Y-%m-%d %H:%M') if ts is not None else '—',
                     'age_minutes':age,'market_state':market_state,'source':'Yahoo L1 — sizes unavailable'}
    except Exception:
        payload=base
    with _ORDER_BOOK_LOCK_V63927:
        _ORDER_BOOK_CACHE_V63927[logical]={'_cached_at':now_epoch,'payload':dict(payload)}
    return payload


def _tradingview_route(ticker: str):
    """Map Yahoo-style symbols to TradingView scanner symbols/endpoints."""
    t=str(ticker or '').upper().strip()
    if t.endswith('.HK'):
        raw=t[:-3]
        try:raw=str(int(raw))
        except Exception:raw=raw.lstrip('0') or '0'
        return 'https://scanner.tradingview.com/hongkong/scan',f'HKEX:{raw}'
    if t.endswith('.TA'):
        return 'https://scanner.tradingview.com/israel/scan',f'TASE:{t[:-3]}'
    if t == 'ITT':
        return 'https://scanner.tradingview.com/america/scan','NYSE:ITT'
    if t and all(ch.isalnum() or ch in '.-' for ch in t):
        return 'https://scanner.tradingview.com/america/scan',f'NASDAQ:{t}'
    return None,None


def _fetch_tradingview_display_quote(ticker: str, daily=None, split_ratio=np.nan):
    """Best-effort second-provider DISPLAY quote.

    TradingView's scanner response does not reliably expose an exchange trade
    timestamp, so this candidate is never trade-grade and never anchors split
    normalization. It may still be shown as a clearly labelled delayed/current
    price reference when its scale is plausible versus the latest adjusted Daily.
    """
    url,symbol=_tradingview_route(ticker)
    if not url:return {'price':np.nan,'display_current':False,'fresh':False,'trade_fresh':False,'anchor_eligible':False}
    try:
        payload={'symbols':{'tickers':[symbol],'query':{'types':[]}},
                 'columns':['close','change','volume','update_mode']}
        body=_json.dumps(payload).encode('utf-8')
        req=_urlrequest.Request(url,data=body,method='POST',headers={
            'Content-Type':'application/json','Accept':'application/json',
            'User-Agent':'Mozilla/5.0 (AI Stock Hunter quote fallback)',
            'Origin':'https://www.tradingview.com','Referer':'https://www.tradingview.com/'})
        with _urlrequest.urlopen(req,timeout=6) as resp:
            obj=_json.loads(resp.read().decode('utf-8','replace'))
        rows=obj.get('data',[]) if isinstance(obj,dict) else []
        if not rows:return {'price':np.nan,'display_current':False,'fresh':False,'trade_fresh':False,'anchor_eligible':False}
        vals=rows[0].get('d',[]) if isinstance(rows[0],dict) else []
        if not vals:return {'price':np.nan,'display_current':False,'fresh':False,'trade_fresh':False,'anchor_eligible':False}
        raw=_finite(vals[0],np.nan); change=_finite(vals[1],np.nan) if len(vals)>1 else np.nan
        mode=str(vals[3]) if len(vals)>3 and vals[3] is not None else 'delayed/unknown'
        aligned=_align_current_quote_to_daily(raw,daily,ticker,split_ratio)
        price=_finite(aligned.get('price'),np.nan)
        ref,_=_latest_daily_close(daily,ticker)
        # Without a provider timestamp, reject implausible >25% gaps. This also
        # catches many stale pre-split prints that can otherwise look current.
        if not (np.isfinite(price) and price>0):
            return {'price':np.nan,'display_current':False,'fresh':False,'trade_fresh':False,'anchor_eligible':False}
        if np.isfinite(ref) and ref>0 and abs(price/ref-1.0)>0.25:
            return {'price':np.nan,'display_current':False,'fresh':False,'trade_fresh':False,'anchor_eligible':False,
                    'details':[f'TradingView fallback rejected: {price/ref:.3f}x vs latest Daily']}
        tz=_market_timezone_for_ticker(ticker); now=pd.Timestamp.now(tz=tz)
        return {'price':float(price),'change_pct':change,'timestamp':None,
                'timestamp_label':now.strftime('%Y-%m-%d %H:%M')+' fetch',
                'age_minutes':np.nan,'same_session_date':True,'fresh':False,
                'display_current':True,'trade_fresh':False,'anchor_eligible':False,
                'provider_timestamp_verified':False,
                'source':f'TradingView fallback ({mode})','quote_status':'DELAYED/UNVERIFIED TIMESTAMP',
                'quote_split_adjusted':bool(aligned.get('adjusted',False)),
                'scale_suspect':bool(aligned.get('scale_suspect',False)),
                'details':list(aligned.get('details',[]))}
    except Exception as e:
        return {'price':np.nan,'display_current':False,'fresh':False,'trade_fresh':False,'anchor_eligible':False,
                'details':[f'TradingView fallback unavailable: {type(e).__name__}']}


def fetch_live_intraday_snapshot(ticker: str, daily=None):
    """Current-price resolver with hard stale gates and multiple quote paths.

    V6.0.6 priority:
      1) Yahoo 1m current-session bar
      2) Yahoo 5m current-session bar
      3) Yahoo direct quote endpoint with regularMarketTime
      4) Yahoo quote metadata with regularMarketTime
      5) Yahoo quote info with regularMarketTime
      6) TradingView display-only fallback (never trade-grade without timestamp)

    A prior-session bar is diagnostic only. A fallback without a verifiable trade
    timestamp can be displayed as delayed/current reference, but cannot enable a
    LIVE TRIGGER or anchor corporate-action normalization.
    """
    out={'price':np.nan,'prev_close':np.nan,'change_pct':np.nan,'timestamp':None,
         'timestamp_label':'—','source':'LIVE PRICE UNAVAILABLE','fresh':False,
         'display_current':False,'trade_fresh':False,'anchor_eligible':False,
         'provider_timestamp_verified':False,'quote_status':'UNAVAILABLE',
         'same_session_date':False,'age_minutes':np.nan,'split_ratio':np.nan,
         'split_date':None,'split_detected':False,'quote_split_adjusted':False,
         'scale_suspect':False,'details':[],'stale_price':np.nan,
         'stale_timestamp_label':'—','stale_age_minutes':np.nan}
    try:
        events=fetch_recent_split_events(ticker,45)
        if events:
            ev=events[-1]
            out.update({'split_ratio':float(ev.get('ratio',np.nan)),
                        'split_date':ev.get('date'),'split_detected':True})
        tz=_market_timezone_for_ticker(ticker); now=pd.Timestamp.now(tz=tz)
        provider_ticker=_market_data_symbol(ticker,now.date())
        bridge_info=temporary_counter_info(ticker,now.date())
        bridge_note=(f' • TEMP {provider_ticker} for {str(ticker).upper()}' if provider_ticker!=str(ticker).upper() else '')
        out['provider_symbol']=provider_ticker
        out['temporary_counter_bridge']=bool(provider_ticker!=str(ticker).upper())
        best_stale=None
        attempts=[('1m','1d',15.0,6.0),('5m','5d',35.0,10.0)]
        for interval,period,max_age,trade_age in attempts:
            try:
                raw=yf.download(provider_ticker,period=period,interval=interval,prepost=True,
                                auto_adjust=True,progress=False,threads=False,group_by='column')
                q=_canonical_ohlcv(raw,ticker=provider_ticker)
                if q is None or q.empty or not isinstance(q.index,pd.DatetimeIndex):continue
                idx=pd.DatetimeIndex(q.index)
                if idx.tz is None:idx=idx.tz_localize(tz,ambiguous='NaT',nonexistent='shift_forward')
                else:idx=idx.tz_convert(tz)
                q=q.copy();q.index=idx;q=q[~q.index.isna()].dropna(subset=['Close'])
                if q.empty:continue
                ts=pd.Timestamp(q.index[-1]);raw_price=float(q['Close'].iloc[-1])
                age=max(0.0,(now-ts).total_seconds()/60.0);same=ts.date()==now.date()
                diag={'price':raw_price,'timestamp_label':ts.strftime('%Y-%m-%d %H:%M'),'age_minutes':age}
                if best_stale is None or ts>best_stale[0]:best_stale=(ts,diag)
                if not (same and age<=max_age):continue
                aligned=_align_current_quote_to_daily(raw_price,daily,ticker,out.get('split_ratio',np.nan))
                if aligned.get('scale_suspect'):
                    out['scale_suspect']=True;out['details'].extend(aligned.get('details',[]));continue
                price=float(aligned['price']);prev_close,prev_date=_daily_reference_close(daily,ticker,ref_date=now.date())
                # V6.3.9.52: while a temporary/reopened counter bridge exists, session
                # change must use the same provider counter as the live quote. The
                # stitched logical daily series remains valid for indicators/history.
                _bridge_ratio=_finite((bridge_info or {}).get('subdivision_ratio',out.get('split_ratio',np.nan)),np.nan)
                if bridge_info:
                    _pc,_pc_date,_pc_src=_provider_reference_close(provider_ticker,now.date(),price,_bridge_ratio)
                    if np.isfinite(_pc) and _pc>0:
                        prev_close,prev_date=_pc,_pc_date
                        out['provider_prev_close_source']=_pc_src
                sr=_finite(out.get('split_ratio'),np.nan)
                if np.isfinite(prev_close) and prev_close>0 and np.isfinite(sr) and sr>0 and out.get('split_date') and prev_date is not None:
                    try:
                        sdate=pd.Timestamp(out['split_date']).date()
                        if prev_date < sdate <= now.date():
                            options=[prev_close,prev_close/sr,prev_close*sr]
                            prev_close=min([v for v in options if np.isfinite(v) and v>0],key=lambda v:abs(price/v-1.0))
                    except Exception:pass
                change=(price/prev_close-1.0)*100.0 if np.isfinite(prev_close) and prev_close>0 else np.nan
                out.update({'price':price,'prev_close':prev_close,'change_pct':change,
                            'timestamp':ts.isoformat(),'timestamp_label':ts.strftime('%Y-%m-%d %H:%M'),
                            'source':f'Yahoo {interval} current-session feed{bridge_note}','fresh':True,
                            'display_current':True,'trade_fresh':bool(age<=trade_age),'anchor_eligible':True,
                            'provider_timestamp_verified':True,
                            'quote_status':'LIVE/NEAR-REALTIME' if age<=trade_age else 'DELAYED/CURRENT-SESSION',
                            'same_session_date':True,'age_minutes':age,
                            'quote_split_adjusted':bool(aligned.get('adjusted',False))})
                out['details'].extend(aligned.get('details',[]));return out
            except Exception:continue

        # Preserve the rejected bar as diagnostics even when a later fallback succeeds.
        if best_stale is not None:
            _,diag=best_stale
            out.update({'stale_price':diag['price'],'stale_timestamp_label':diag['timestamp_label'],
                        'stale_age_minutes':diag['age_minutes']})

        # Separate Yahoo quote endpoints can stay current even when history bars
        # temporarily lag around a split/corporate action.
        for getter in (_fetch_yahoo_direct_quote,_fetch_yahoo_metadata_quote,_fetch_yahoo_info_quote):
            cand=getter(provider_ticker)
            if provider_ticker!=str(ticker).upper() and cand.get('source'):
                cand['source']=str(cand.get('source'))+bridge_note
            if not cand.get('display_current'):continue
            aligned=_align_current_quote_to_daily(cand.get('price'),daily,ticker,out.get('split_ratio',np.nan))
            if aligned.get('scale_suspect'):
                out['details'].extend(aligned.get('details',[]));continue
            price=_finite(aligned.get('price'),np.nan)
            if not (np.isfinite(price) and price>0):continue
            prev_close,prev_date=_daily_reference_close(daily,ticker,ref_date=now.date())
            _bridge_ratio=_finite((bridge_info or {}).get('subdivision_ratio',out.get('split_ratio',np.nan)),np.nan)
            if bridge_info:
                _pc,_pc_date,_pc_src=_provider_reference_close(provider_ticker,now.date(),price,_bridge_ratio)
                if np.isfinite(_pc) and _pc>0:
                    prev_close,prev_date=_pc,_pc_date;out['provider_prev_close_source']=_pc_src
            sr=_finite(out.get('split_ratio'),np.nan)
            if np.isfinite(prev_close) and prev_close>0 and np.isfinite(sr) and sr>0 and out.get('split_date') and prev_date is not None:
                try:
                    sdate=pd.Timestamp(out['split_date']).date()
                    if prev_date < sdate <= now.date():
                        options=[prev_close,prev_close/sr,prev_close*sr]
                        prev_close=min([v for v in options if np.isfinite(v) and v>0],key=lambda v:abs(price/v-1.0))
                except Exception:pass
            change=(price/prev_close-1.0)*100.0 if np.isfinite(prev_close) and prev_close>0 else np.nan
            out.update(cand);out.update({'price':price,'prev_close':prev_close,'change_pct':change,
                                        'quote_split_adjusted':bool(aligned.get('adjusted',False)),
                                        'scale_suspect':False})
            out['details'].extend(aligned.get('details',[]));return out

        tv=_fetch_tradingview_display_quote(provider_ticker,daily,out.get('split_ratio',np.nan))
        if provider_ticker!=str(ticker).upper() and tv.get('source'):
            tv['source']=str(tv.get('source'))+bridge_note
        if tv.get('display_current'):
            price=_finite(tv.get('price'),np.nan);prev_close,_=_daily_reference_close(daily,ticker,ref_date=now.date())
            if bridge_info:
                _bridge_ratio=_finite((bridge_info or {}).get('subdivision_ratio',out.get('split_ratio',np.nan)),np.nan)
                _pc,_pc_date,_pc_src=_provider_reference_close(provider_ticker,now.date(),price,_bridge_ratio)
                if np.isfinite(_pc) and _pc>0:
                    prev_close=_pc;out['provider_prev_close_source']=_pc_src
            change=_finite(tv.get('change_pct'),np.nan)
            if not np.isfinite(change) and np.isfinite(prev_close) and prev_close>0:
                change=(price/prev_close-1.0)*100.0
            out.update(tv);out.update({'prev_close':prev_close,'change_pct':change})
            return out

        if best_stale is not None:
            _,diag=best_stale
            out.update({'stale_price':diag['price'],'stale_timestamp_label':diag['timestamp_label'],
                        'stale_age_minutes':diag['age_minutes']})
        return out
    except Exception:
        return out

def resolve_current_market_snapshot(ticker: str, daily=None, hourly=None, m15=None,
                                    primary=None, market_open: bool=False, market_phase=None, market_date=None):
    """Choose the best current display price without relaxing live-trade safety.

    V6.0.6 separates two ideas:
      * display_current: good enough to show as the current/delayed market price
      * trade_fresh: timestamp-fresh enough to enable LIVE TRIGGER / Actionable Now

    A second-provider quote without a verifiable trade timestamp may be displayed
    with an explicit DELAYED/UNVERIFIED label, but it can never enable live trading
    logic or anchor split normalization.
    """
    p=dict(primary or {})
    base={'price':np.nan,'fallback_price':np.nan,'prev_close':np.nan,'change_pct':np.nan,
          'timestamp':None,'timestamp_label':'—','source':'LIVE PRICE UNAVAILABLE','fresh':False,
          'display_current':False,'trade_fresh':False,'anchor_eligible':False,
          'provider_timestamp_verified':False,'quote_status':'UNAVAILABLE',
          'same_session_date':False,'age_minutes':np.nan,'split_ratio':p.get('split_ratio',np.nan),
          'split_date':p.get('split_date'),'split_detected':bool(p.get('split_detected',False)),
          'quote_split_adjusted':bool(p.get('quote_split_adjusted',False)),
          'scale_suspect':bool(p.get('scale_suspect',False)),'details':list(p.get('details',[])),
          'stale_price':p.get('stale_price',np.nan),'stale_timestamp_label':p.get('stale_timestamp_label','—'),
          'stale_age_minutes':p.get('stale_age_minutes',np.nan),
          'analysis_session_date':None,'previous_session_date':None,'session_context':'UNRESOLVED'}
    daily_last,daily_date=_latest_daily_close(daily,ticker);base['fallback_price']=daily_last
    tz=_market_timezone_for_ticker(ticker);today=pd.Timestamp(market_date).date() if market_date is not None else pd.Timestamp.now(tz=tz).date()
    ctx_prev,ctx_prev_date,ctx_active_date,ctx_label=_session_reference_close_v623(
        daily,ticker,market_phase=market_phase,market_date=today)
    base.update({'analysis_session_date':str(ctx_active_date) if ctx_active_date else None,
                 'previous_session_date':str(ctx_prev_date) if ctx_prev_date else None,
                 'session_context':ctx_label})

    candidates=[]
    # Primary may be timestamp-verified Yahoo OR display-only TradingView fallback.
    if p.get('display_current') and np.isfinite(_finite(p.get('price'),np.nan)) and not p.get('scale_suspect'):
        candidates.append(('primary',p))

    ms=frame_price_snapshot(ticker,m15,45.0);ms.update({
        'source':'15m current-session confirmed bar','display_current':bool(ms.get('fresh')),
        'trade_fresh':False,'anchor_eligible':False,'provider_timestamp_verified':True,
        'quote_status':'DELAYED/CONFIRMED 15m'})
    hs=frame_price_snapshot(ticker,hourly,110.0);hs.update({
        'source':'1H current-session confirmed bar','display_current':bool(hs.get('fresh')),
        'trade_fresh':False,'anchor_eligible':False,'provider_timestamp_verified':True,
        'quote_status':'DELAYED/CONFIRMED 1H'})
    if ms.get('display_current'):candidates.append(('15m',ms))
    if hs.get('display_current'):candidates.append(('1H',hs))

    if candidates:
        _,sel=candidates[0]
        price=_finite(sel.get('price'),np.nan)
        prev_close,prev_date=ctx_prev,ctx_prev_date
        if not (np.isfinite(prev_close) and prev_close>0):
            prev_close,prev_date=_daily_reference_close(daily,ticker,ref_date=today)
        _bridge=temporary_counter_info(ticker,ctx_active_date or today)
        if _bridge:
            try:
                _provider=_market_data_symbol(ticker,ctx_active_date or today)
                _ratio=_finite(_bridge.get('subdivision_ratio',base.get('split_ratio',np.nan)),np.nan)
                _pc,_pc_date,_pc_src=_provider_reference_close(_provider,ctx_active_date or today,price,_ratio)
                if np.isfinite(_pc) and _pc>0:
                    prev_close,prev_date=_pc,_pc_date;base['provider_prev_close_source']=_pc_src;base['provider_symbol']=_provider
            except Exception:pass
        sr=_finite(base.get('split_ratio'),np.nan)
        if np.isfinite(prev_close) and prev_close>0 and np.isfinite(sr) and sr>0 and base.get('split_date') and prev_date is not None:
            try:
                sdate=pd.Timestamp(base['split_date']).date()
                if prev_date < sdate <= today:
                    options=[prev_close,prev_close/sr,prev_close*sr]
                    prev_close=min([v for v in options if np.isfinite(v) and v>0],key=lambda v:abs(price/v-1.0))
            except Exception:pass
        change=_finite(sel.get('change_pct'),np.nan)
        if not np.isfinite(change):
            change=(price/prev_close-1.0)*100.0 if np.isfinite(prev_close) and prev_close>0 else np.nan
        base.update({'price':price,'prev_close':prev_close,'change_pct':change,
                     'timestamp':sel.get('timestamp'),'timestamp_label':sel.get('timestamp_label','—'),
                     'source':sel.get('source','current-session quote'),
                     'fresh':bool(sel.get('fresh',False)),
                     'display_current':bool(sel.get('display_current',True)),
                     'trade_fresh':bool(sel.get('trade_fresh',False)),
                     'anchor_eligible':bool(sel.get('anchor_eligible',False)),
                     'provider_timestamp_verified':bool(sel.get('provider_timestamp_verified',False)),
                     'quote_status':sel.get('quote_status','CURRENT/DELAYED'),
                     'same_session_date':bool(sel.get('same_session_date',True)),
                     'age_minutes':sel.get('age_minutes',np.nan)})
        return base

    if market_open:
        base['source']='LIVE PRICE UNAVAILABLE — using last official close only as reference'
        return base

    # Closed/pre-open: latest official Daily close is a safe reference, not a live quote.
    if np.isfinite(daily_last) and daily_last>0:
        d=_canonical_ohlcv(daily,ticker=ticker);prev=_finite(ctx_prev,np.nan)
        if not (np.isfinite(prev) and prev>0) and d is not None and len(d)>=2:prev=float(d['Close'].iloc[-2])
        change=(daily_last/prev-1.0)*100.0 if np.isfinite(prev) and prev>0 else np.nan
        base.update({'price':daily_last,'prev_close':prev,'change_pct':change,
                     'timestamp_label':str(daily_date) if daily_date else '—',
                     'source':'latest official Daily close','fresh':False,
                     'display_current':False,'trade_fresh':False,
                     'same_session_date':bool(daily_date==today),'age_minutes':np.nan,
                     'quote_status':'OFFICIAL CLOSE'})
    return base


def fetch_premarket_snapshots(tickers):
    """Return real US pre-market snapshots from Yahoo intraday extended-hours data.

    The volume-strength ratio compares today's cumulative pre-market volume with
    prior available pre-market sessions through the same clock time.  Non-US
    tickers are intentionally left to the UI as N/A rather than fabricating an
    auction/pre-open equivalent.
    """
    from datetime import datetime, time as dtime
    from zoneinfo import ZoneInfo

    names=[str(t).upper().strip() for t in tickers if str(t).strip()]
    if not names:
        return {}
    out={}
    try:
        raw=yf.download(names, period='5d', interval='5m', prepost=True,
                        auto_adjust=False, progress=False, threads=True, group_by='ticker')
    except Exception:
        return out
    if raw is None or raw.empty:
        return out

    now=datetime.now(ZoneInfo('America/New_York'))
    today=now.date(); cutoff=now.time().replace(tzinfo=None)
    for tkr in names:
        try:
            if len(names)==1:
                q=raw.copy()
            elif isinstance(raw.columns,pd.MultiIndex):
                if tkr in raw.columns.get_level_values(0): q=raw[tkr].copy()
                elif tkr in raw.columns.get_level_values(-1): q=raw.xs(tkr,axis=1,level=-1).copy()
                else: continue
            else:
                continue
            if q.empty: continue
            idx=pd.DatetimeIndex(q.index)
            if idx.tz is None: idx=idx.tz_localize('UTC')
            idx=idx.tz_convert('America/New_York'); q.index=idx
            close=pd.to_numeric(q.get('Close'),errors='coerce'); vol=pd.to_numeric(q.get('Volume'),errors='coerce').fillna(0)
            dates=pd.Series(q.index.date,index=q.index)
            times=pd.Series(q.index.time,index=q.index)
            pm_mask=(dates==today) & (times>=dtime(4,0)) & (times<dtime(9,30)) & (times<=cutoff)
            pm=q.loc[pm_mask]
            if pm.empty: continue
            pm_close=pd.to_numeric(pm['Close'],errors='coerce').dropna()
            if pm_close.empty: continue
            last_price=float(pm_close.iloc[-1]); pm_volume=float(pd.to_numeric(pm['Volume'],errors='coerce').fillna(0).sum())
            regular=(times>=dtime(9,30)) & (times<dtime(16,0)) & (dates<today)
            prev=q.loc[regular]
            if prev.empty: continue
            prev_dates=sorted(set(prev.index.date))
            prev_day=prev_dates[-1]; prev_day_rows=prev[prev.index.date==prev_day]
            prev_close_series=pd.to_numeric(prev_day_rows['Close'],errors='coerce').dropna()
            if prev_close_series.empty: continue
            prev_close=float(prev_close_series.iloc[-1])
            change=(last_price/prev_close-1.0)*100.0 if prev_close else np.nan

            hist=[]
            for d in sorted(set(q.index.date)):
                if d>=today: continue
                m=(q.index.date==d) & (q.index.time>=dtime(4,0)) & (q.index.time<dtime(9,30)) & (q.index.time<=cutoff)
                v=float(pd.to_numeric(q.loc[m,'Volume'],errors='coerce').fillna(0).sum())
                if v>0: hist.append(v)
            baseline=float(np.median(hist)) if hist else np.nan
            strength=(pm_volume/baseline) if baseline and np.isfinite(baseline) and baseline>0 else np.nan
            out[tkr]={'PMPrice':last_price,'PMChangePct':change,'PMVolume':pm_volume,'PMVolumeStrength':strength,'PMData':'REAL 5M'}
        except Exception:
            continue
    return out


def fetch_aftermarket_snapshots(tickers):
    """Return real US after-hours snapshots from Yahoo 5-minute extended-hours data.

    AH volume strength compares cumulative after-hours volume through the current
    clock time with prior available sessions through the same elapsed AH window.
    """
    from datetime import datetime, time as dtime
    from zoneinfo import ZoneInfo
    names=[str(t).upper().strip() for t in tickers if str(t).strip()]
    if not names: return {}
    out={}
    try:
        raw=yf.download(names, period='5d', interval='5m', prepost=True,
                        auto_adjust=False, progress=False, threads=True, group_by='ticker')
    except Exception:
        return out
    if raw is None or raw.empty: return out
    now=datetime.now(ZoneInfo('America/New_York')); today=now.date(); cutoff=now.time().replace(tzinfo=None)
    for tkr in names:
        try:
            if len(names)==1: q=raw.copy()
            elif isinstance(raw.columns,pd.MultiIndex):
                if tkr in raw.columns.get_level_values(0): q=raw[tkr].copy()
                elif tkr in raw.columns.get_level_values(-1): q=raw.xs(tkr,axis=1,level=-1).copy()
                else: continue
            else: continue
            if q.empty: continue
            idx=pd.DatetimeIndex(q.index)
            if idx.tz is None: idx=idx.tz_localize('UTC')
            idx=idx.tz_convert('America/New_York'); q.index=idx
            ah=q[(q.index.date==today) & (q.index.time>=dtime(16,0)) & (q.index.time<dtime(20,0)) & (q.index.time<=cutoff)]
            if ah.empty: continue
            ah_close=pd.to_numeric(ah['Close'],errors='coerce').dropna()
            if ah_close.empty: continue
            last_price=float(ah_close.iloc[-1]); ah_volume=float(pd.to_numeric(ah['Volume'],errors='coerce').fillna(0).sum())
            reg=q[(q.index.date==today) & (q.index.time>=dtime(9,30)) & (q.index.time<dtime(16,0))]
            if reg.empty: continue
            reg_close=pd.to_numeric(reg['Close'],errors='coerce').dropna()
            if reg_close.empty: continue
            close=float(reg_close.iloc[-1]); change=(last_price/close-1.0)*100.0 if close else np.nan
            hist=[]
            for d in sorted(set(q.index.date)):
                if d>=today: continue
                m=(q.index.date==d) & (q.index.time>=dtime(16,0)) & (q.index.time<dtime(20,0)) & (q.index.time<=cutoff)
                v=float(pd.to_numeric(q.loc[m,'Volume'],errors='coerce').fillna(0).sum())
                if v>0: hist.append(v)
            baseline=float(np.median(hist)) if hist else np.nan
            strength=(ah_volume/baseline) if baseline and np.isfinite(baseline) and baseline>0 else np.nan
            last_ts=pd.Timestamp(ah_close.index[-1])
            age=max(0.0,(pd.Timestamp.now(tz='America/New_York')-last_ts).total_seconds()/60.0)
            out[tkr]={
                'AHPrice':last_price,'RegularClose':close,'AHChangePct':change,
                'AHVolume':ah_volume,'AHVolumeStrength':strength,'AHData':'REAL 5M',
                'AHLastTime':last_ts.strftime('%Y-%m-%d %H:%M'),'AHAgeMinutes':age,
                'AHFresh':bool(age<=15.0),
            }
        except Exception: continue
    return out


def ema(s, span):
    s = _series1d(s)
    return s.ewm(span=span, adjust=False, min_periods=span).mean()


def rsi(close, n=14):
    c = _series1d(close, name='Close')
    d = c.diff()
    gain = d.clip(lower=0.0)
    loss = -d.clip(upper=0.0)
    ag = gain.ewm(alpha=1.0/float(n), adjust=False, min_periods=int(n)).mean()
    al = loss.ewm(alpha=1.0/float(n), adjust=False, min_periods=int(n)).mean()
    num = ag.to_numpy(dtype='float64')
    den = al.to_numpy(dtype='float64')
    rs = np.full(len(num), np.nan, dtype='float64')
    np.divide(num, den, out=rs, where=np.isfinite(den) & (den != 0.0))
    out = 100.0 - (100.0 / (1.0 + rs))
    out[(den == 0.0) & np.isfinite(num) & (num > 0.0)] = 100.0
    return pd.Series(out, index=c.index, dtype='float64')


def true_range(df):
    high = _series1d(df['High'], index=df.index)
    low = _series1d(df['Low'], index=df.index)
    close = _series1d(df['Close'], index=df.index)
    prev = close.shift(1)
    arr = np.vstack([
        (high-low).to_numpy(),
        (high-prev).abs().to_numpy(),
        (low-prev).abs().to_numpy(),
    ])
    return pd.Series(np.nanmax(arr, axis=0), index=df.index, dtype='float64')


def _wilder(series, n):
    s = _series1d(series)
    return s.ewm(alpha=1.0/float(n), adjust=False, min_periods=int(n)).mean()


def adx(df, n=14):
    high = _series1d(df['High'], index=df.index)
    low = _series1d(df['Low'], index=df.index)
    up = high.diff()
    down = -low.diff()
    pdm = pd.Series(np.where((up > down) & (up > 0), up, 0.0), index=df.index, dtype='float64')
    mdm = pd.Series(np.where((down > up) & (down > 0), down, 0.0), index=df.index, dtype='float64')
    atr = _wilder(true_range(df), n)
    atr_arr = atr.to_numpy(dtype='float64')
    pnum = 100 * _wilder(pdm, n).to_numpy(dtype='float64')
    mnum = 100 * _wilder(mdm, n).to_numpy(dtype='float64')
    pdi = np.full(len(atr), np.nan)
    mdi = np.full(len(atr), np.nan)
    np.divide(pnum, atr_arr, out=pdi, where=np.isfinite(atr_arr) & (atr_arr != 0))
    np.divide(mnum, atr_arr, out=mdi, where=np.isfinite(atr_arr) & (atr_arr != 0))
    den = pdi + mdi
    dx = np.full(len(den), np.nan)
    np.divide(100*np.abs(pdi-mdi), den, out=dx, where=np.isfinite(den) & (den != 0))
    return _wilder(pd.Series(dx, index=df.index), n)


def _clamp(v, lo=0, hi=100):
    return max(lo, min(hi, v))





def confirmed_intraday_bars(df: pd.DataFrame):
    """Return only bars that are very likely closed.

    Yahoo can include the currently-forming 15m/1h candle. Using it as if it were
    final makes Entry/Hourly scores jump around. We infer the bar interval from
    recent timestamps and drop the last row when it is still inside that interval.
    """
    x=_canonical_ohlcv(df)
    if x is None or len(x)<3 or not isinstance(x.index,pd.DatetimeIndex):
        return x
    try:
        idx=x.index
        recent=idx[-min(12,len(idx)):]
        deltas=pd.Series(recent[1:]-recent[:-1]).dt.total_seconds()
        sec=float(deltas[deltas>0].median())
        if not np.isfinite(sec) or sec<=0:return x
        last=pd.Timestamp(idx[-1])
        now=pd.Timestamp.now(tz=last.tz) if last.tz is not None else pd.Timestamp.now()
        age=(now-last).total_seconds()
        # Most providers timestamp a bar at its opening time. A 10% grace handles latency.
        if -60 <= age < sec*0.90:
            return x.iloc[:-1].copy() if len(x)>3 else x
    except Exception:
        pass
    return x


def normalize_cross_timeframes(daily, hourly=None, m15=None, anchor_price=None, split_ratio=None, split_date=None):
    """Normalize Daily/1H/15m to one current price scale + internal split history.

    V6.3.9.49 adds an internal-history guard. Last prices can agree while older
    pre-split bars are still on a different scale; that corrupts ATR/resistance and
    can create absurd targets. Known or obvious split discontinuities are adjusted
    before feature calculation. Unresolved scale conflicts are hard-blocked.
    """
    d=_canonical_ohlcv(daily);h=_canonical_ohlcv(hourly) if hourly is not None else None;m=_canonical_ohlcv(m15) if m15 is not None else None
    sr=_finite(split_ratio,np.nan)
    report={'split_adjusted':False,'split_detected':bool(np.isfinite(sr) and sr>1.05),'split_ratio':sr,'split_date':split_date,
            'data_quality':'OK','details':[],'anchor_source':'daily','scale_integrity_ok':True,'internal_split_adjusted':False}
    if d is None or d.empty:return d,h,m,report

    generic=[2.0,3.0,4.0,5.0,10.0]
    if np.isfinite(sr) and sr>1.05:generic.append(sr)
    factors=np.array(sorted(set(generic)),dtype=float)

    def internal_fix(frame,label):
        nonlocal report
        if frame is None or len(frame)<3:return frame
        z=frame.copy();cl=pd.to_numeric(z['Close'],errors='coerce')
        # Prefer explicit corporate-action date when available; otherwise locate a
        # very large adjacent price jump close to a common split factor.
        cut=None;fac=None
        if split_date is not None:
            try:
                sd=pd.Timestamp(split_date).date();pos=[i for i,x in enumerate(z.index) if pd.Timestamp(x).date()>=sd]
                if pos and pos[0]>0:
                    i=pos[0];a=_finite(cl.iloc[i-1]);b=_finite(cl.iloc[i]);obs=(a/b) if np.isfinite(a) and np.isfinite(b) and b>0 else np.nan
                    if np.isfinite(obs):
                        near=float(factors[np.argmin(np.abs(np.log(factors)-np.log(max(obs,1e-9))))])
                        if abs(obs/near-1.0)<=0.22:cut=i;fac=near
            except Exception:pass
        if cut is None:
            vals=cl.to_numpy(dtype=float)
            for i in range(max(1,len(vals)-90),len(vals)):
                a,b=vals[i-1],vals[i]
                if not (np.isfinite(a) and np.isfinite(b) and a>0 and b>0):continue
                obs=a/b
                if obs<1:obs=1/obs
                near=float(factors[np.argmin(np.abs(np.log(factors)-np.log(obs)))])
                if obs>=1.8 and abs(obs/near-1.0)<=0.12:
                    cut=i;fac=near;break
        if cut is not None and fac and fac>1:
            pre=z.iloc[:cut].copy();post=z.iloc[cut:].copy()
            # Determine direction: subdivision usually means old price / new price ≈ factor.
            a=_finite(pre['Close'].iloc[-1]);b=_finite(post['Close'].iloc[0]);old_high=bool(np.isfinite(a) and np.isfinite(b) and a>b)
            mult=(1.0/fac) if old_high else fac
            for c in ('Open','High','Low','Close'):pre[c]=pd.to_numeric(pre[c],errors='coerce')*mult
            pre['Volume']=pd.to_numeric(pre['Volume'],errors='coerce')/mult
            z=pd.concat([pre,post],axis=0).sort_index();report['split_adjusted']=True;report['split_detected']=True;report['internal_split_adjusted']=True
            report['details'].append(f'{label} internal split history normalized x{mult:.6g} before boundary')
        return z

    d=internal_fix(d,'Daily');h=internal_fix(h,'1H');m=internal_fix(m,'15m')
    def lp(frame):
        try:return float(frame['Close'].iloc[-1]) if frame is not None and len(frame) else np.nan
        except Exception:return np.nan
    dp,hp,mp=lp(d),lp(h),lp(m);ap=_finite(anchor_price,np.nan)
    if np.isfinite(ap) and ap>0:anchor=ap;report['anchor_source']='5m intraday'
    elif np.isfinite(dp) and dp>0:anchor=dp;report['anchor_source']='daily'
    elif np.isfinite(mp) and mp>0:anchor=mp;report['anchor_source']='15m fallback'
    else:anchor=hp;report['anchor_source']='1H fallback'
    scale_factors=[0.1,0.2,0.25,1/3,0.5,2,3,4,5,10]
    if np.isfinite(sr) and sr>0:scale_factors.extend([sr,1.0/sr])
    sf=np.array(sorted(set(float(x) for x in scale_factors if np.isfinite(x) and x>0)),dtype=float)
    def fix(frame,label,is_daily=False):
        nonlocal report
        if frame is None or frame.empty:return frame
        p=lp(frame)
        if not (np.isfinite(anchor) and anchor>0 and np.isfinite(p) and p>0):return frame
        ratio=anchor/p;normal_tol=0.35 if is_daily else 0.20
        if abs(ratio-1.0)<=normal_tol:return frame
        nearest=float(sf[np.argmin(np.abs(np.log(sf)-np.log(ratio)))]);err=abs(ratio/nearest-1.0)
        if err<=0.14:
            z=frame.copy()
            for c in ('Open','High','Low','Close'):z[c]=pd.to_numeric(z[c],errors='coerce')*nearest
            z['Volume']=pd.to_numeric(z['Volume'],errors='coerce')/nearest
            report['split_adjusted']=True;report['split_detected']=True;report['details'].append(f'{label} current-scale normalized x{nearest:.6g} (observed {ratio:.4g}x)');return z
        if (not is_daily) or abs(ratio-1.0)>0.55:
            report['data_quality']='MISMATCH';report['scale_integrity_ok']=False;report['details'].append(f'{label} unexplained scale mismatch {ratio:.3f}x')
        return frame
    d=fix(d,'Daily',True);h=fix(h,'1H',False);m=fix(m,'15m',False)
    hp2,mp2=lp(h),lp(m)
    if np.isfinite(hp2) and hp2>0 and np.isfinite(mp2) and mp2>0 and abs(hp2/mp2-1.0)>0.18:
        report['data_quality']='MISMATCH';report['scale_integrity_ok']=False;report['details'].append(f'1H/15m remain inconsistent ({hp2/mp2:.3f}x)')
    return d,h,m,report


def _volume_direction_context(r):
    """Directional interpretation of volume. High volume is evidence, not direction.

    Returns bullish support and bearish distribution pressure on a 0..1 scale.
    """
    ret=_finite(r.get('ret1',np.nan),0.0)
    cl=_finite(r.get('close_location',np.nan),0.5)
    c=_finite(r.get('Close',np.nan)); vw=_finite(r.get('vwap',np.nan))
    cmf=_finite(r.get('cmf20',np.nan),0.0); obv=_finite(r.get('obv_slope5',np.nan),0.0); ad=_finite(r.get('ad_slope5',np.nan),0.0)
    mh=_finite(r.get('macd_hist',np.nan),0.0); ms=_finite(r.get('macd_hist_slope',np.nan),0.0)
    bullish=0.0; bearish=0.0
    bullish += 0.22 if ret>0.002 else (0.10 if ret>=-0.002 else 0.0)
    bearish += 0.25 if ret<-0.012 else (0.16 if ret<-0.003 else 0.0)
    bullish += 0.18 if cl>=0.65 else (0.08 if cl>=0.50 else 0.0)
    bearish += 0.20 if cl<=0.30 else (0.10 if cl<=0.45 else 0.0)
    if np.isfinite(c) and np.isfinite(vw):
        bullish += 0.16 if c>=vw else 0.0
        bearish += 0.16 if c<vw else 0.0
    bullish += 0.14 if cmf>0.05 else (0.06 if cmf>0 else 0.0)
    bearish += 0.14 if cmf<-0.05 else (0.06 if cmf<0 else 0.0)
    bullish += 0.10 if obv>0 else 0.0; bearish += 0.10 if obv<0 else 0.0
    bullish += 0.08 if ad>0 else 0.0; bearish += 0.08 if ad<0 else 0.0
    bullish += 0.12 if mh>0 and ms>=0 else (0.05 if mh>0 else 0.0)
    bearish += 0.12 if mh<0 and ms<=0 else (0.05 if mh<0 else 0.0)
    return min(1.0,bullish),min(1.0,bearish)


def directional_volume_row(r):
    """Return volume magnitude plus direction-aware bullish/bearish evidence."""
    rr=_finite(r.get('time_adjusted_rvol',r.get('robust_volume_ratio',r.get('volume_ratio',np.nan))))
    vz=_finite(r.get('volume_z',np.nan)); va=_finite(r.get('vol_accel',np.nan))
    mag=0.0
    if np.isfinite(rr): mag=1.0 if rr>=2.5 else 0.85 if rr>=1.8 else 0.65 if rr>=1.35 else 0.40 if rr>=1.10 else 0.15 if rr>=0.85 else 0.0
    if np.isfinite(vz) and vz>=2:mag=min(1.0,mag+0.12)
    if np.isfinite(va) and va>=1.25:mag=min(1.0,mag+0.10)
    bull,bear=_volume_direction_context(r)
    bullish=mag*bull
    bearish=mag*bear
    label='ACCUMULATION' if bullish>=0.45 and bullish>bearish*1.15 else ('DISTRIBUTION' if bearish>=0.45 and bearish>bullish*1.15 else 'MIXED / NEUTRAL')
    return {'magnitude':mag,'bullish':bullish,'bearish':bearish,'label':label,'rvol':rr}


def institutional_flow_row(r):
    """Institutional-flow proxy (0..100), not proof of institutional ownership.

    Uses only causal price/volume evidence available in OHLCV-derived features:
    directional relative volume, CMF/OBV/AD accumulation, VWAP/close-location,
    turnover expansion and absorption-like high-volume price acceptance.
    """
    dv=directional_volume_row(r)
    cmf=_finite(r.get('cmf20',np.nan),0); obv=_finite(r.get('obv_slope5',np.nan),0); ad=_finite(r.get('ad_slope5',np.nan),0)
    c=_finite(r.get('Close',np.nan)); vw=_finite(r.get('vwap',np.nan)); cl=_finite(r.get('close_location',np.nan),0.5); ret=_finite(r.get('ret1',np.nan),0)
    tr=_finite(r.get('turnover_ratio60',np.nan)); va=_finite(r.get('vol_accel',np.nan)); rr=_finite(r.get('robust_volume_ratio',r.get('volume_ratio',np.nan)))
    parts=[]
    parts.append(('Directional accumulation',30.0*float(dv.get('bullish',0)),30.0))
    flow=0.0
    flow += 7.0 if cmf>=0.10 else 4.0 if cmf>0 else 0.0
    flow += 5.0 if obv>0.04 else 3.0 if obv>0 else 0.0
    flow += 5.0 if ad>0.04 else 3.0 if ad>0 else 0.0
    parts.append(('CMF / OBV / A-D',min(17.0,flow),17.0))
    acceptance=0.0
    if np.isfinite(c) and np.isfinite(vw) and c>=vw:acceptance+=8.0
    if cl>=0.65:acceptance+=7.0
    elif cl>=0.50:acceptance+=3.0
    parts.append(('VWAP / close acceptance',min(15.0,acceptance),15.0))
    expansion=0.0
    if np.isfinite(rr):expansion += 8.0 if rr>=1.5 else 5.0 if rr>=1.2 else 2.0 if rr>=1.0 else 0.0
    if np.isfinite(va):expansion += 6.0 if va>=1.25 else 3.0 if va>=1.08 else 0.0
    if np.isfinite(tr):expansion += 4.0 if tr>=1.4 else 2.0 if tr>=1.1 else 0.0
    parts.append(('Volume / turnover expansion',min(18.0,expansion),18.0))
    absorption=0.0
    if np.isfinite(rr) and rr>=1.2 and ret>=-0.003 and cl>=0.55:absorption=12.0
    elif np.isfinite(rr) and rr>=1.0 and ret>=0 and cl>=0.5:absorption=6.0
    parts.append(('Absorption proxy',absorption,12.0))
    persistence=0.0
    if cmf>0 and obv>0 and ad>0:persistence=8.0
    elif sum([cmf>0,obv>0,ad>0])>=2:persistence=4.0
    parts.append(('Accumulation persistence',persistence,8.0))
    score=float(np.clip(sum(float(x[1]) for x in parts),0,100))
    label='STRONG ACCUMULATION' if score>=68 else ('ACCUMULATION' if score>=52 else ('MIXED' if score>=35 else 'NO CLEAR FLOW'))
    return {'score':round(score,1),'label':label,'components':parts}

def exit_pressure_row(r):
    """0..100 Distribution / Exit Pressure score for long setups.

    V6.1 recalibration: historical weakness alone may raise WATCH evidence, but
    EXIT ARMED / EXIT TRIGGER require *current-session* bearish price action plus
    confirmed outflow/distribution evidence. This prevents old weakness from
    being treated as a live exit command.
    """
    dv=directional_volume_row(r); pts=[]
    c=_finite(r.get('Close',np.nan)); o=_finite(r.get('Open',np.nan)); vw=_finite(r.get('vwap',np.nan)); e20=_finite(r.get('ema20',np.nan)); sup=_finite(r.get('support20',np.nan))
    ret=_finite(r.get('ret1',np.nan),0.0); cl=_finite(r.get('close_location',np.nan),0.5)
    cmf=_finite(r.get('cmf20',np.nan),0); obv=_finite(r.get('obv_slope5',np.nan),0); ad=_finite(r.get('ad_slope5',np.nan),0)
    mh=_finite(r.get('macd_hist',np.nan),0); ms=_finite(r.get('macd_hist_slope',np.nan),0); rs=_finite(r.get('rsi14',np.nan),50)
    persistence=_finite(r.get('distribution_persistence3',np.nan),0)

    present_bearish = bool(
        ret <= -0.003 or
        (np.isfinite(c) and np.isfinite(o) and c < o and cl <= 0.45) or
        (np.isfinite(c) and np.isfinite(vw) and c < vw and ret < 0)
    )
    outflow_confirm = bool(dv['bearish'] >= 0.24 and (cmf < 0 or obv < 0 or ad < 0))

    pts.append(('Bearish volume / distribution',30*dv['bearish'],30))
    struct=0.0
    if np.isfinite(c) and np.isfinite(vw) and c<vw:struct+=8
    if np.isfinite(c) and np.isfinite(e20) and c<e20:struct+=8
    if np.isfinite(c) and np.isfinite(sup) and c<sup:struct+=8
    pts.append(('VWAP / EMA / support loss',min(24,struct),24))
    flow=(8 if cmf<-0.05 else 4 if cmf<0 else 0)+(7 if obv<0 else 0)+(7 if ad<0 else 0)
    pts.append(('Money-flow deterioration',min(22,flow),22))
    mom=(7 if mh<0 else 0)+(7 if ms<0 else 0)+(6 if rs<45 else 3 if rs<50 else 0)
    pts.append(('Momentum deterioration',min(20,mom),20))
    pts.append(('Persistence',min(4,4*persistence),4))
    raw=float(_clamp(sum(float(x[1]) for x in pts)))

    # Key V6.1 change: without present bearish direction and outflow, historical
    # deterioration is context only. It cannot remain a high live Exit Pressure.
    if present_bearish and outflow_confirm:
        score=raw
    elif present_bearish:
        score=min(54.0,raw*0.72)
    else:
        score=min(44.0,raw*0.42)

    armed_confirm = present_bearish and outflow_confirm and persistence >= 0.34 and dv['bearish'] >= 0.30 and (struct >= 8 or flow >= 8)
    trigger_confirm = present_bearish and outflow_confirm and persistence >= 0.67 and dv['bearish'] >= 0.45 and struct >= 16 and flow >= 8
    if score>=72 and trigger_confirm:
        stage='EXIT TRIGGER'
    elif score>=55 and armed_confirm:
        stage='EXIT ARMED'
    elif score>=35 and present_bearish:
        stage='EXIT WATCH'
    else:
        stage='CLEAR'
    return float(round(score,1)),pts,stage


def _smooth01(x, center=0.0, width=1.0):
    if not np.isfinite(x):return 0.0
    w=max(1e-9,float(width))
    return float(1.0/(1.0+np.exp(-(float(x)-center)/w)))


def entry_score_row(r, quant_score=50.0):
    """Continuous production Entry Score with direction-aware volume."""
    p=_finite(r.get('Close',np.nan)); atr=_finite(r.get('atr14',np.nan)); vw=_finite(r.get('vwap',np.nan)); e9=_finite(r.get('ema9',np.nan)); e20=_finite(r.get('ema20',np.nan)); mh=_finite(r.get('macd_hist',np.nan)); ms=_finite(r.get('macd_hist_slope',np.nan)); rs=_finite(r.get('rsi14',np.nan))
    a=atr if np.isfinite(atr) and atr>0 else (p*.02 if np.isfinite(p) else 1.0)
    vwap_part=20*_smooth01((p-vw)/a if np.isfinite(p) and np.isfinite(vw) else np.nan,0,0.35)
    ema_part=18*_smooth01((e9-e20)/a if np.isfinite(e9) and np.isfinite(e20) else np.nan,0,0.25)
    dv=directional_volume_row(r); vol_part=16*dv['bullish']
    macd_part=14*(0.70*(1.0 if np.isfinite(mh) and mh>0 else 0.0)+0.30*(1.0 if np.isfinite(ms) and ms>0 else 0.0))
    if np.isfinite(rs):
        rsi_part=12*max(0.0,1.0-abs(rs-60.0)/18.0)
    else:rsi_part=0.0
    quant_part=20*_smooth01(float(quant_score),62.0,5.5)
    raw=vwap_part+ema_part+vol_part+macd_part+rsi_part+quant_part
    exit_score,_,_=exit_pressure_row(r)
    # Exit pressure can veto a superficially attractive entry without creating negative scores.
    score=raw*(1.0-0.45*exit_score/100.0)
    return float(_clamp(score)), [('VWAP structure',vwap_part,20),('EMA structure',ema_part,18),('Directional volume',vol_part,16),('MACD',macd_part,14),('RSI window',rsi_part,12),('Quant support',quant_part,20)]


def compute_features(df: pd.DataFrame, intraday=False):
    x = _canonical_ohlcv(df)
    if x is None or len(x) == 0:
        raise ValueError('No valid OHLCV rows')
    c = _series1d(x['Close'], index=x.index)
    v = _series1d(x['Volume'], index=x.index)

    x['ret1'] = c.pct_change()
    x['mom3'] = c.pct_change(3)
    x['mom5'] = c.pct_change(5)
    x['mom10'] = c.pct_change(10)
    x['ema9'] = ema(c, 9)
    x['ema20'] = ema(c, 20)
    x['ema50'] = ema(c, 50)

    vm20 = v.rolling(20).mean()
    vs20 = v.rolling(20).std()
    x['volume_ratio'] = v / vm20.replace(0, np.nan)
    x['volume_z'] = (v-vm20) / vs20.replace(0, np.nan)
    x['vol_accel'] = v.rolling(3).mean() / v.rolling(10).mean().replace(0, np.nan)
    # V5.9 robust/transition volume features. Median-based RVOL is intentionally
    # less sensitive to one-off extreme sessions than the ordinary rolling mean.
    vmed20 = v.rolling(20, min_periods=10).median()
    x['robust_volume_ratio'] = v / vmed20.replace(0, np.nan)
    x['volume_reexpansion'] = x['robust_volume_ratio'] / x['robust_volume_ratio'].shift(1).replace(0, np.nan)
    x['volume_dryup'] = (1.0 - v / v.rolling(5, min_periods=2).max().replace(0, np.nan)).clip(0, 1)

    x['rsi14'] = rsi(c, 14)
    macd = ema(c, 12) - ema(c, 26)
    sig = ema(macd, 9)
    x['macd'] = macd
    x['macd_signal'] = sig
    x['macd_hist'] = macd - sig
    x['macd_hist_slope'] = x['macd_hist'].diff(2)
    x['ema9_cross_up'] = ((x['ema9'] > x['ema20']) & (x['ema9'].shift(1) <= x['ema20'].shift(1))).fillna(False).astype('int8')
    x['macd_cross_up'] = ((x['macd'] > x['macd_signal']) & (x['macd'].shift(1) <= x['macd_signal'].shift(1))).fillna(False).astype('int8')
    x['macd_hist_turn_pos'] = ((x['macd_hist'] > 0) & (x['macd_hist'].shift(1) <= 0)).fillna(False).astype('int8')

    tr = true_range(x)
    x['atr14'] = _wilder(tr, 14)
    x['atr_pct'] = x['atr14'] / c * 100
    x['adx14'] = adx(x, 14)

    ph = x['High'].rolling(20).max().shift(1)
    pl = x['Low'].rolling(20).min().shift(1)
    x['breakout20_pct'] = (c/ph - 1) * 100
    x['support20'] = pl
    x['resistance20'] = ph

    rng = (x['High'] - x['Low']).replace(0, np.nan)
    x['close_location'] = (c - x['Low']) / rng
    x['turnover'] = c * v
    x['turnover_median60'] = x['turnover'].rolling(60, min_periods=20).median()
    x['turnover_ratio60'] = x['turnover'] / x['turnover_median60'].replace(0, np.nan)

    direction = np.sign(c.diff()).fillna(0)
    x['obv'] = (direction * v).cumsum()
    basev = (v.rolling(20).mean() * 5).replace(0, np.nan)
    x['obv_slope5'] = x['obv'].diff(5) / basev

    mfm = ((c-x['Low']) - (x['High']-c)) / rng
    mfv = mfm.fillna(0) * v
    x['ad_line'] = mfv.cumsum()
    x['ad_slope5'] = x['ad_line'].diff(5) / basev
    x['cmf20'] = mfv.rolling(20).sum() / v.rolling(20).sum().replace(0, np.nan)

    mid = c.rolling(20).mean()
    sd = c.rolling(20).std()
    bb_u = mid + 2*sd
    bb_l = mid - 2*sd
    kc_u = x['ema20'] + 1.5*x['atr14']
    kc_l = x['ema20'] - 1.5*x['atr14']
    sq = ((bb_u < kc_u) & (bb_l > kc_l)).fillna(False).astype('int8')
    x['squeeze'] = sq
    x['squeeze_release'] = ((sq.shift(1) == 1) & (sq == 0)).fillna(False).astype('int8')

    x['roc5'] = c.pct_change(5)
    x['roc10'] = c.pct_change(10)
    x['roc_accel'] = x['roc5'] - x['roc10']/2
    x['rs20'] = c/c.shift(20) - 1
    x['pv_divergence'] = ((c.pct_change(5) <= 0.02) & (x['obv'].diff(5) > 0)).fillna(False).astype('int8')

    typical = (x['High'] + x['Low'] + x['Close']) / 3
    if intraday and isinstance(x.index, pd.DatetimeIndex):
        dates = pd.Series(x.index.date, index=x.index)
        x['vwap'] = (typical*v).groupby(dates).cumsum() / v.groupby(dates).cumsum().replace(0, np.nan)
    else:
        x['vwap'] = (typical*v).rolling(20).sum() / v.rolling(20).sum().replace(0, np.nan)
    x['vwap_cross_up'] = ((c > x['vwap']) & (c.shift(1) <= x['vwap'].shift(1))).fillna(False).astype('int8')
    # Impulse -> hold -> dry-up -> re-expansion sequence features. All are causal.
    x['impulse_1d'] = x['ret1']
    x['impulse_3d'] = c.pct_change(3)
    x['recent_impulse'] = x['ret1'].rolling(5, min_periods=1).max()
    recent_close_high = c.rolling(5, min_periods=1).max()
    x['post_impulse_retention'] = (c / recent_close_high.replace(0, np.nan)).clip(0, 1.05)
    x['fresh_transition_count'] = (x['ema9_cross_up'] + x['macd_cross_up'] + x['macd_hist_turn_pos'] + x['vwap_cross_up']).astype('float64')

    # Time-of-day normalized intraday RVOL. Compare each bar with the same ordinal
    # bar in prior sessions instead of comparing a partial day with a full day.
    x['time_adjusted_rvol']=x['robust_volume_ratio']
    if intraday and isinstance(x.index,pd.DatetimeIndex) and len(x)>=20:
        try:
            dates=pd.Series(x.index.date,index=x.index)
            ordinal=dates.groupby(dates).cumcount()
            tmp=pd.DataFrame({'v':v.to_numpy(float),'date':dates.to_numpy(),'ord':ordinal.to_numpy()},index=x.index)
            baseline=np.full(len(tmp),np.nan)
            vals=tmp['v'].to_numpy(float); ords=tmp['ord'].to_numpy(int)
            for i in range(len(tmp)):
                prior=np.where((ords[:i]==ords[i]))[0]
                prior=prior[-20:]
                if len(prior)>=3: baseline[i]=float(np.nanmedian(vals[prior]))
            x['time_adjusted_rvol']=v/pd.Series(baseline,index=x.index).replace(0,np.nan)
        except Exception:
            pass

    # V6.3.9.29 display-only cumulative intraday RVOL. This is the simple RVOL
    # shown on Scanner/Analyze cards: accumulated session volume up to the current
    # bar divided by the median accumulated volume at the same ordinal bar across
    # up to 20 prior sessions. It does NOT replace time_adjusted_rvol in model logic.
    x['intraday_cum_rvol']=x['robust_volume_ratio']
    if intraday and isinstance(x.index,pd.DatetimeIndex) and len(x)>=20:
        try:
            dates2=pd.Series(x.index.date,index=x.index)
            ordinal2=dates2.groupby(dates2).cumcount()
            cumv=v.groupby(dates2).cumsum()
            vals2=cumv.to_numpy(float); ords2=ordinal2.to_numpy(int)
            baseline2=np.full(len(x),np.nan)
            for i in range(len(x)):
                prior=np.where(ords2[:i]==ords2[i])[0]
                prior=prior[-20:]
                if len(prior)>=3: baseline2[i]=float(np.nanmedian(vals2[prior]))
            x['intraday_cum_rvol']=cumv/pd.Series(baseline2,index=x.index).replace(0,np.nan)
        except Exception:
            pass

    # Corporate-action guard. auto_adjust normally removes splits; this marks any
    # residual split-like jump so momentum/feedback layers can treat it cautiously.
    ratio=c/c.shift(1)
    factors=np.array([0.1,0.2,0.25,1/3,0.5,2,3,4,5,10],dtype=float)
    ca=[]
    for z in ratio.to_numpy(float):
        if not np.isfinite(z) or z<=0 or abs(z-1)<0.35: ca.append(False); continue
        nearest=float(factors[np.argmin(np.abs(np.log(factors)-np.log(z)))])
        ca.append(abs(z/nearest-1.0)<=0.08)
    x['corporate_action_flag']=pd.Series(ca,index=x.index).fillna(False).astype('int8')
    # Rebuild a synthetic continuous price index for return/momentum features only.
    # This prevents a residual split/reverse-split print from becoming a fake +100%/-50% signal.
    try:
        clean_ret=c.pct_change().copy(); rr_ratio=(c/c.shift(1)).to_numpy(float); ca_mask=x['corporate_action_flag'].astype(bool).to_numpy()
        for i in range(1,len(clean_ret)):
            if not ca_mask[i] or not np.isfinite(rr_ratio[i]) or rr_ratio[i]<=0:continue
            nearest=float(factors[np.argmin(np.abs(np.log(factors)-np.log(rr_ratio[i])))])
            clean_ret.iloc[i]=rr_ratio[i]/nearest-1.0
        clean_price=100.0*(1.0+clean_ret.fillna(0.0)).cumprod()
        x['ret1']=clean_ret
        x['mom3']=clean_price.pct_change(3); x['mom5']=clean_price.pct_change(5); x['mom10']=clean_price.pct_change(10)
        x['roc5']=clean_price.pct_change(5); x['roc10']=clean_price.pct_change(10); x['roc_accel']=x['roc5']-x['roc10']/2
        x['rs20']=clean_price/clean_price.shift(20)-1
        x['impulse_1d']=x['ret1']; x['impulse_3d']=clean_price.pct_change(3); x['recent_impulse']=x['ret1'].rolling(5,min_periods=1).max()
        ch=clean_price.rolling(5,min_periods=1).max(); x['post_impulse_retention']=(clean_price/ch.replace(0,np.nan)).clip(0,1.05)
    except Exception:
        pass

    # Persistence of heavy selling: confirmed negative-price bars with elevated volume.
    dv_bear=[]; dv_bull=[]
    for _,rr in x.iterrows():
        dv=directional_volume_row(rr); dv_bear.append(dv['bearish']); dv_bull.append(dv['bullish'])
    x['bullish_volume_evidence']=pd.Series(dv_bull,index=x.index,dtype=float)
    x['bearish_volume_evidence']=pd.Series(dv_bear,index=x.index,dtype=float)
    x['distribution_persistence3']=(x['bearish_volume_evidence']>=0.35).rolling(3,min_periods=1).mean()
    return x



def explosive_score_row(r):
    """V6.0 Explosive Move fingerprint with direction-aware volume."""
    comps=[]
    imp=max(_finite(r.get('impulse_1d',np.nan),-1),_finite(r.get('impulse_3d',np.nan),-2)/2)
    p=18 if imp>=.08 else 14 if imp>=.045 else 9 if imp>=.025 else 4 if imp>0 else 0
    comps.append(('Impulse strength',p,18))

    dv=directional_volume_row(r)
    p=18*dv['bullish']
    comps.append(('Directional volume shock',p,18))

    ret=_finite(r.get('post_impulse_retention',np.nan)); ri=_finite(r.get('recent_impulse',np.nan))
    p=14 if np.isfinite(ret) and np.isfinite(ri) and ri>=.035 and ret>=.97 else 10 if np.isfinite(ret) and np.isfinite(ri) and ri>=.025 and ret>=.94 else 4 if np.isfinite(ret) and ret>=.92 else 0
    comps.append(('Post-impulse retention',p,14))

    dry=_finite(r.get('volume_dryup',np.nan)); p=10 if np.isfinite(dry) and dry>=.55 and np.isfinite(ret) and ret>=.94 else 7 if np.isfinite(dry) and dry>=.35 and np.isfinite(ret) and ret>=.92 else 0
    comps.append(('Volume dry-up',p,10))

    re=_finite(r.get('volume_reexpansion',np.nan)); p=(10 if re>=1.8 else 7 if re>=1.35 else 3 if re>=1.1 else 0)*max(0.0,min(1.0,dv['bullish']*1.7))
    comps.append(('Bullish volume re-expansion',p,10))

    tr=_finite(r.get('fresh_transition_count',np.nan),0); mh=_finite(r.get('macd_hist_slope',np.nan)); va=_finite(r.get('vol_accel',np.nan))
    p=min(12,(4*int(tr) if np.isfinite(tr) else 0)+(2 if np.isfinite(mh) and mh>0 else 0)+(2 if np.isfinite(va) and va>1.1 and dv['bullish']>=.25 else 0))
    comps.append(('Fresh transitions',p,12))

    atr=_finite(r.get('atr_pct',np.nan)); p=8 if atr>=6 else 6 if atr>=4 else 4 if atr>=2.5 else 1 if np.isfinite(atr) else 0
    comps.append(('ATR move capacity',p,8))

    e9=_finite(r.get('ema9',np.nan)); e20=_finite(r.get('ema20',np.nan)); c=_finite(r.get('Close',np.nan)); vw=_finite(r.get('vwap',np.nan)); rs=_finite(r.get('rsi14',np.nan))
    p=(4 if np.isfinite(e9) and np.isfinite(e20) and e9>=e20 else 0)+(4 if np.isfinite(c) and np.isfinite(vw) and c>=vw else 0)+(2 if np.isfinite(rs) and 48<=rs<=75 else 0)
    comps.append(('Trend/VWAP structure',p,10))

    raw=float(_clamp(sum(float(x[1]) for x in comps)))
    exit_score,_,_=exit_pressure_row(r)
    score=float(_clamp(raw*(1.0-0.35*exit_score/100.0)))
    exhausted=(np.isfinite(rs) and rs>80) or (_finite(r.get('mom5',np.nan),0)>.28)
    if exit_score>=72: stage='DISTRIBUTION'
    elif exhausted and score<82: stage='EXHAUSTED'
    elif score>=82 and p>=6: stage='TRIGGERED'
    elif score>=68: stage='ARMED'
    elif score>=52: stage='BUILDING'
    elif score>=35: stage='RESET'
    else: stage='COLD'
    return score, comps, stage


def hourly_confirmation(feat):
    if feat is None or len(feat)==0:return {'score':np.nan,'status':'NO DATA','exit_pressure':np.nan}
    f=feat.dropna(subset=['Close'])
    if f.empty:return {'score':np.nan,'status':'NO DATA','exit_pressure':np.nan}
    r=f.iloc[-1]
    score=0.0
    c=_finite(r.get('Close',np.nan)); vw=_finite(r.get('vwap',np.nan)); e9=_finite(r.get('ema9',np.nan)); e20=_finite(r.get('ema20',np.nan)); mh=_finite(r.get('macd_hist',np.nan)); rs=_finite(r.get('rsi14',np.nan)); tr=_finite(r.get('fresh_transition_count',0),0)
    dv=directional_volume_row(r)
    if np.isfinite(c) and np.isfinite(vw) and c>=vw:score+=20
    if np.isfinite(e9) and np.isfinite(e20) and e9>=e20:score+=20
    if np.isfinite(mh) and mh>0:score+=16
    if np.isfinite(rs) and 50<=rs<=72:score+=14
    score+=14*dv['bullish']
    score+=min(16,4*tr)
    exit_score,_,exit_stage=exit_pressure_row(r)
    score=float(_clamp(score*(1.0-0.45*exit_score/100.0)))
    return {'score':round(score,1),'status':'CONFIRMED' if score>=70 and exit_score<35 else 'PARTIAL' if score>=50 and exit_score<55 else 'WEAK','exit_pressure':round(exit_score,1),'exit_stage':exit_stage,'volume_context':dv['label']}


def explosive_probabilities(feat, current_score=None, min_sample=8):
    """Empirical, shrinkage-calibrated probabilities from prior causal rows only."""
    f=feat.copy().dropna(subset=['Close'])
    if len(f)<35:return {'sample':0,'threshold':np.nan,'probs':{}}
    scores=np.array([explosive_score_row(r)[0] for _,r in f.iterrows()],dtype=float)
    cs=float(scores[-1] if current_score is None else current_score)
    threshold=max(45.0, cs-10.0)
    out={}
    highs=f['High'].to_numpy(dtype=float); closes=f['Close'].to_numpy(dtype=float)
    for h in (1,3,5):
        for target in (.05,.10,.15):
            vals=[]; base=[]
            for i in range(0,len(f)-h-1):
                hit=1.0 if np.nanmax(highs[i+1:i+1+h])>=closes[i]*(1+target) else 0.0
                base.append(hit)
                if scores[i]>=threshold: vals.append(hit)
            n=len(vals); b=float(np.mean(base)) if base else np.nan
            if n:
                # mild prior toward the unconditional base rate; prevents tiny buckets from reading 0/100%.
                p=(float(np.sum(vals))+4.0*b)/(n+4.0) if np.isfinite(b) else float(np.mean(vals))
            else:p=np.nan
            out[f'p{int(target*100)}_{h}d']={'prob':100*p if np.isfinite(p) else np.nan,'n':n,'baseline':100*b if np.isfinite(b) else np.nan,'reliable':n>=min_sample}
    return {'sample':int(sum(1 for x in scores[:-6] if x>=threshold)),'threshold':round(threshold,1),'probs':out}


def explosive_latest(feat, hourly_feat=None):
    r=feat.dropna(subset=['Close']).iloc[-1]
    score, comps, stage=explosive_score_row(r)
    pr=explosive_probabilities(feat,score)
    hc=hourly_confirmation(hourly_feat) if hourly_feat is not None else {'score':np.nan,'status':'NO DATA'}
    out={'score':round(score,1),'stage':stage,'components':comps,'hourly_confirmation':hc['score'],'hourly_status':hc['status'],'prob_threshold':pr.get('threshold',np.nan),'prob_sample':pr.get('sample',0)}
    for k,v in pr.get('probs',{}).items():
        out[k]=v.get('prob',np.nan); out[k+'_n']=v.get('n',0); out[k+'_reliable']=v.get('reliable',False)
    for k in ['robust_volume_ratio','post_impulse_retention','volume_dryup','volume_reexpansion','fresh_transition_count','atr_pct']:
        val=r.get(k,np.nan); out[k]=float(val) if pd.notna(val) else np.nan
    return out


def explosive_walkforward(feat, threshold=68):
    """Chronological four-fold validation of the static V5.9 fingerprint."""
    f=feat.copy().dropna(subset=['Close'])
    if len(f)<120:return pd.DataFrame()
    scores=np.array([explosive_score_row(r)[0] for _,r in f.iterrows()],dtype=float)
    highs=f['High'].to_numpy(dtype=float); closes=f['Close'].to_numpy(dtype=float)
    rows=[]; specs=[(.40,.55),(.55,.70),(.70,.85),(.85,1.00)]
    for target in (.05,.10,.15):
        for h in (1,3,5):
            fold_lifts=[]; fold_hits=[]; fold_ns=[]
            for fold,(a,b) in enumerate(specs,1):
                i1=int(len(f)*a); i2=min(int(len(f)*b),len(f)-h-1)
                sig=[]; base=[]
                for i in range(i1,i2):
                    hit=1.0 if np.nanmax(highs[i+1:i+1+h])>=closes[i]*(1+target) else 0.0
                    base.append(hit)
                    if scores[i]>=threshold:sig.append(hit)
                n=len(sig); bhr=float(np.mean(base)) if base else np.nan; hr=float(np.mean(sig)) if sig else np.nan
                lift=hr/bhr if np.isfinite(hr) and np.isfinite(bhr) and bhr>0 else np.nan
                if np.isfinite(lift):fold_lifts.append(lift)
                if np.isfinite(hr):fold_hits.append(hr)
                fold_ns.append(n)
            pos=sum(1 for x in fold_lifts if x>1.0)
            rows.append({'Target':f'+{int(target*100)}%','Horizon':f'{h}D','Signals':sum(fold_ns),'Hit Rate %':100*np.average(fold_hits,weights=[max(1,n) for n in fold_ns if n>0]) if fold_hits and len(fold_hits)==sum(1 for n in fold_ns if n>0) else (100*np.mean(fold_hits) if fold_hits else np.nan),'Median Lift':float(np.median(fold_lifts)) if fold_lifts else np.nan,'Positive Folds':f'{pos}/{len(fold_lifts)}'})
    return pd.DataFrame(rows)


# -----------------------------------------------------------------------------
# V5.9.2 Adaptive Target/Horizon Research Layer
# Strictly causal features: scores at row t use row t and earlier only. Forward
# highs are used only as labels after the score has been frozen.
# -----------------------------------------------------------------------------
def move_score_row(r):
    """Short-horizon move score. High volume is bullish only with bullish price/flow context."""
    pts=[]
    dv=directional_volume_row(r)
    p=25*dv['bullish']; pts.append(('Directional volume acceleration',p,25))
    m3=_finite(r.get('mom3',np.nan)); m5=_finite(r.get('mom5',np.nan)); p=0
    if np.isfinite(m3): p += 12 if .01<=m3<=.08 else 7 if m3>0 else 0
    if np.isfinite(m5): p += 8 if .015<=m5<=.12 else 4 if m5>0 else 0
    pts.append(('Near-term momentum',min(20,p),20))
    tr=_finite(r.get('fresh_transition_count',0),0); mh=_finite(r.get('macd_hist_slope',np.nan))
    p=min(20,5*tr + (5 if np.isfinite(mh) and mh>0 else 0)); pts.append(('Fresh transitions',p,20))
    c=_finite(r.get('Close',np.nan)); vw=_finite(r.get('vwap',np.nan)); e9=_finite(r.get('ema9',np.nan)); e20=_finite(r.get('ema20',np.nan))
    p=(8 if np.isfinite(c) and np.isfinite(vw) and c>=vw else 0)+(7 if np.isfinite(e9) and np.isfinite(e20) and e9>=e20 else 0); pts.append(('VWAP/EMA structure',p,15))
    rs=_finite(r.get('rsi14',np.nan)); p=10 if 50<=rs<=72 else 5 if 45<=rs<=78 else 0; pts.append(('RSI window',p,10))
    atr=_finite(r.get('atr_pct',np.nan)); p=10 if atr>=3 else 7 if atr>=2 else 3 if np.isfinite(atr) else 0; pts.append(('Move capacity',p,10))
    raw=float(_clamp(sum(float(x[1]) for x in pts)))
    exit_score,_,_=exit_pressure_row(r)
    return float(_clamp(raw*(1.0-0.40*exit_score/100.0))),pts


def _entry_proxy_row(r, quant=None):
    return entry_score_row(r,50.0 if quant is None else quant)[0]


def historical_signal_timeline(feat):
    f=feat.copy().dropna(subset=['Close'])
    if f.empty:return pd.DataFrame()
    highs=f['High'].to_numpy(float); closes=f['Close'].to_numpy(float)
    rows=[]
    for i,(idx,r) in enumerate(f.iterrows()):
        ex,_,stage=explosive_score_row(r); mv,_=move_score_row(r); q,_=score_row(r,0); en=_entry_proxy_row(r,q)
        xp,_,xs=exit_pressure_row(r); row={'Date':idx,'Close':closes[i],'Move Score':round(mv,1),'Explosive Score':round(ex,1),'Entry Score':round(en,1),'Exit Pressure':round(xp,1),'Exit Stage':xs,'Stage':stage,'Volume Ratio':r.get('robust_volume_ratio',np.nan),'Time Adjusted RVOL':r.get('time_adjusted_rvol',np.nan),'Volume Context':directional_volume_row(r).get('label'),'ATR %':r.get('atr_pct',np.nan)}
        for h in (1,3,5):
            if i+h < len(f):
                row[f'+{h}D Close Return %']=100*(closes[i+h]/closes[i]-1)
                row[f'+{h}D Max Return %']=100*(np.nanmax(highs[i+1:i+1+h])/closes[i]-1)
            else:
                row[f'+{h}D Close Return %']=np.nan; row[f'+{h}D Max Return %']=np.nan
        rows.append(row)
    out=pd.DataFrame(rows)
    # Signal Timing V5.9.4: causal score acceleration. Positive means the score is strengthening now.
    for score in ("Move Score","Explosive Score","Entry Score"):
        for lag in (1,2,3):
            out[f"{score} Accel {lag}D"] = pd.to_numeric(out[score],errors="coerce") - pd.to_numeric(out[score],errors="coerce").shift(lag)
    ex=pd.to_numeric(out["Explosive Score"],errors="coerce")
    out["Explosive Rising 3D"] = ((ex.diff()>0)&(ex.diff().shift(1)>0)&(ex.diff().shift(2)>0))
    out["Signal Acceleration"] = out["Explosive Score Accel 3D"]
    return out

def signal_timing_latest(feat, hourly_feat=None):
    """Movement timing layer. TRIGGER here means Movement Trigger, not Trade Trigger."""
    tl=historical_signal_timeline(feat)
    if tl.empty:return {}
    r=tl.iloc[-1]
    hc=hourly_confirmation(hourly_feat) if hourly_feat is not None and len(hourly_feat) else {'score':np.nan,'status':'NO DATA','exit_pressure':np.nan}
    ex=_finite(r.get('Explosive Score',np.nan)); mv=_finite(r.get('Move Score',np.nan)); en=_finite(r.get('Entry Score',np.nan))
    a1=_finite(r.get('Explosive Score Accel 1D',np.nan)); a2=_finite(r.get('Explosive Score Accel 2D',np.nan)); a3=_finite(r.get('Explosive Score Accel 3D',np.nan))
    rising=bool(r.get('Explosive Rising 3D',False)); hcs=_finite(hc.get('score',np.nan)); xp=_finite(r.get('Exit Pressure',np.nan),0)
    if xp>=72: stage='WEAKENED'
    elif max(ex,mv) < 50: stage='WAIT'
    elif max(ex,mv) < 60 or (np.isfinite(a3) and a3<=0): stage='WATCH'
    elif max(ex,mv)>=60 and en>=55 and (rising or (np.isfinite(a3) and a3>=6)): stage='ARMED'
    else: stage='WATCH'
    if xp<45 and max(ex,mv)>=68 and en>=62 and np.isfinite(a3) and a3>=8 and np.isfinite(hcs) and hcs>=60:
        stage='TRIGGER'
    return {'move_score':round(mv,1),'explosive_score':round(ex,1),'entry_score':round(en,1),
            'accel_1d':round(a1,1) if np.isfinite(a1) else np.nan,'accel_2d':round(a2,1) if np.isfinite(a2) else np.nan,'accel_3d':round(a3,1) if np.isfinite(a3) else np.nan,
            'rising_3d':rising,'hourly_confirmation':round(hcs,1) if np.isfinite(hcs) else np.nan,'hourly_status':hc.get('status','NO DATA'),'timing_stage':stage,
            'movement_stage':'MOVEMENT TRIGGER' if stage=='TRIGGER' else stage,'exit_pressure':round(xp,1),'exit_stage':str(r.get('Exit Stage','CLEAR'))}


def acceleration_validation(timeline, targets=(3,5,10,15), horizons=(1,3,5), accel_thresholds=(0,3,5,8,10,15)):
    """Validate whether score acceleration adds lift; future returns are labels only."""
    if timeline is None or timeline.empty:return pd.DataFrame()
    t=timeline.copy(); rows=[]
    for window in (1,2,3):
      acol=f"Explosive Score Accel {window}D"
      if acol not in t:continue
      a=pd.to_numeric(t[acol],errors="coerce")
      for th in accel_thresholds:
       mask=a>=th
       for target in targets:
        for h in horizons:
         col=f"+{h}D Max Return %"
         if col not in t:continue
         y=pd.to_numeric(t[col],errors="coerce")>=target; valid=pd.to_numeric(t[col],errors="coerce").notna() & a.notna()
         n=int((mask&valid).sum()); base=float(y[valid].mean()) if valid.any() else np.nan; hit=float(y[mask&valid].mean()) if n else np.nan
         lift=hit/base if np.isfinite(hit) and np.isfinite(base) and base>0 else np.nan
         rows.append({"Window":f"{window}D","Accel Threshold":th,"Target":f"+{target}%","Horizon":f"{h}D","Signals":n,"Hit Rate %":100*hit if np.isfinite(hit) else np.nan,"Baseline %":100*base if np.isfinite(base) else np.nan,"Lift":lift})
    return pd.DataFrame(rows)

def threshold_optimization(feat, thresholds=(50,55,60,65,70,75,80), targets=(.03,.05,.10,.15), horizons=(1,3,5), score_kind='explosive'):
    f=feat.copy().dropna(subset=['Close'])
    if len(f)<120:return pd.DataFrame()
    scorer=(lambda r: move_score_row(r)[0]) if score_kind=='move' else (lambda r: explosive_score_row(r)[0])
    scores=np.array([scorer(r) for _,r in f.iterrows()]); highs=f['High'].to_numpy(float); closes=f['Close'].to_numpy(float)
    specs=[(.40,.55),(.55,.70),(.70,.85),(.85,1.00)]; rows=[]
    for th in thresholds:
      for target in targets:
       for h in horizons:
        lifts=[]; ns=[]; hrs=[]; fwds=[]
        for a,b in specs:
          i1=int(len(f)*a); i2=min(int(len(f)*b),len(f)-h)
          base=[]; sig=[]; rets=[]
          for i in range(i1,i2):
            mx=np.nanmax(highs[i+1:i+1+h])/closes[i]-1; hit=float(mx>=target); base.append(hit)
            if scores[i]>=th:sig.append(hit); rets.append(mx)
          if sig:
            hr=float(np.mean(sig)); br=float(np.mean(base)) if base else np.nan; lift=hr/br if br>0 else np.nan
            if np.isfinite(lift):lifts.append(lift)
            hrs.extend(sig); fwds.extend(rets); ns.append(len(sig))
        rows.append({'Score':score_kind.title(),'Threshold':th,'Target':f'+{int(target*100)}%','Horizon':f'{h}D','Signals':sum(ns),'Hit Rate %':100*np.mean(hrs) if hrs else np.nan,'Median Lift':np.median(lifts) if lifts else np.nan,'Positive Folds':f'{sum(x>1 for x in lifts)}/{len(lifts)}','Avg Max Forward %':100*np.mean(fwds) if fwds else np.nan})
    return pd.DataFrame(rows)

def adaptive_target_horizon(opt, min_signals=20, min_positive_fold_ratio=.5):
    if opt is None or opt.empty:return {}
    x=opt.copy(); x['FoldRatio']=x['Positive Folds'].astype(str).apply(lambda z:(float(z.split('/')[0])/float(z.split('/')[1])) if '/' in z and float(z.split('/')[1]) else 0)
    x=x[(x['Signals']>=min_signals)&(x['FoldRatio']>=min_positive_fold_ratio)&pd.notna(x['Median Lift'])]
    if x.empty:return {}
    x=x.assign(RankScore=x['Median Lift']*np.sqrt(x['Signals'].clip(lower=1))*x['FoldRatio'])
    r=x.sort_values(['RankScore','Median Lift'],ascending=False).iloc[0]
    return {'Score':r['Score'],'Threshold':int(r['Threshold']),'Target':r['Target'],'Horizon':r['Horizon'],'Signals':int(r['Signals']),'Median Lift':float(r['Median Lift']),'Positive Folds':r['Positive Folds'],'Avg Max Forward %':float(r['Avg Max Forward %'])}



def reliability_score_row(r, min_signals=20):
    """0-100 research reliability: lift + sample + fold consistency, with explicit penalties for thin folds."""
    try:
        lift=float(r.get('Median Lift', np.nan)); n=int(r.get('Signals',0)); pf=str(r.get('Positive Folds','0/0'))
        a,b=pf.split('/'); pos=float(a); folds=float(b); fr=pos/folds if folds else 0.0
    except Exception:
        return 0.0
    if not np.isfinite(lift) or n<=0 or folds<=0:return 0.0
    lift_component=35*min(1.0,max(0.0,(lift-1.0)/2.0))
    sample_component=25*min(1.0,math.sqrt(n/max(1.0,float(min_signals)*4.0)))
    fold_component=25*fr
    coverage_component=15*min(1.0,folds/4.0)
    penalty=0.55 if folds<2 else (0.82 if folds<3 else 1.0)
    return round(_clamp((lift_component+sample_component+fold_component+coverage_component)*penalty),1)

def adaptive_target_horizon_v2(opt, min_signals=20, min_positive_fold_ratio=.5, min_folds=2, min_reliability=45):
    if opt is None or opt.empty:return {}
    x=opt.copy()
    def parts(z):
        try:
            a,b=str(z).split('/'); return float(a),float(b)
        except:return 0.0,0.0
    pp=x['Positive Folds'].apply(parts); x['PositiveFoldCount']=[z[0] for z in pp]; x['FoldCount']=[z[1] for z in pp]
    x['FoldRatio']=x['PositiveFoldCount']/x['FoldCount'].replace(0,np.nan)
    x['Reliability Score']=x.apply(lambda r: reliability_score_row(r,min_signals),axis=1)
    x=x[(x['Signals']>=min_signals)&(x['FoldCount']>=min_folds)&(x['FoldRatio']>=min_positive_fold_ratio)&(x['Reliability Score']>=min_reliability)&pd.notna(x['Median Lift'])]
    if x.empty:return {}
    # Reliability dominates; lift and sample break ties without allowing a 1-fold anomaly to win.
    x=x.assign(RankScore=x['Reliability Score'] + 8*np.log1p(x['Median Lift'].clip(lower=1)) + 2*np.log1p(x['Signals']))
    r=x.sort_values(['RankScore','Reliability Score','Median Lift','Signals'],ascending=False).iloc[0]
    return {'Score':r['Score'],'Threshold':int(r['Threshold']),'Target':r['Target'],'Horizon':r['Horizon'],'Signals':int(r['Signals']),'Median Lift':float(r['Median Lift']),'Positive Folds':r['Positive Folds'],'Reliability Score':float(r['Reliability Score']),'Avg Max Forward %':float(r['Avg Max Forward %'])}

def pre_move_study(timeline, targets=(5,10,15), horizons=(1,3,5)):
    if timeline is None or timeline.empty:return pd.DataFrame()
    t=timeline.reset_index(drop=True).copy(); rows=[]
    for target in targets:
      for h in horizons:
        col=f'+{h}D Max Return %'
        if col not in t:continue
        events=t.index[pd.to_numeric(t[col],errors='coerce')>=target].tolist()
        for lag in (3,2,1,0):
          ix=[i-lag for i in events if i-lag>=0]
          if not ix:continue
          z=t.loc[ix]
          rows.append({'Target':f'+{target}%','Horizon':f'{h}D','Days Before':lag,'Events':len(z),'Move Score Avg':pd.to_numeric(z['Move Score'],errors='coerce').mean(),'Explosive Score Avg':pd.to_numeric(z['Explosive Score'],errors='coerce').mean(),'Entry Score Avg':pd.to_numeric(z['Entry Score'],errors='coerce').mean(),'Volume Ratio Avg':pd.to_numeric(z['Volume Ratio'],errors='coerce').mean(),'ATR % Avg':pd.to_numeric(z['ATR %'],errors='coerce').mean()})
    return pd.DataFrame(rows)


def _research_indicator_states(r):
    """Causal boolean states used by V6.1.1 pre-move/hourly research."""
    dv=directional_volume_row(r)
    p=_finite(r.get('Close',np.nan)); vw=_finite(r.get('vwap',np.nan)); e9=_finite(r.get('ema9',np.nan)); e20=_finite(r.get('ema20',np.nan))
    rs=_finite(r.get('rsi14',np.nan)); adx=_finite(r.get('adx14',np.nan)); cmf=_finite(r.get('cmf20',np.nan)); mh=_finite(r.get('macd_hist',np.nan)); ms=_finite(r.get('macd_hist_slope',np.nan)); va=_finite(r.get('vol_accel',np.nan)); rr=_finite(r.get('time_adjusted_rvol',r.get('robust_volume_ratio',np.nan)))
    return {
        'EMA9/20 bullish cross': bool(_finite(r.get('ema9_cross_up',0),0)>0),
        'MACD bullish cross': bool(_finite(r.get('macd_cross_up',0),0)>0),
        'MACD histogram turn positive': bool(_finite(r.get('macd_hist_turn_pos',0),0)>0),
        'VWAP reclaim': bool(_finite(r.get('vwap_cross_up',0),0)>0),
        'MACD strengthening': bool(np.isfinite(ms) and ms>0),
        'Volume acceleration': bool(np.isfinite(va) and va>=1.08),
        'Directional bullish volume': bool(float(dv.get('bullish',0))>=.22 and float(dv.get('bullish',0))>float(dv.get('bearish',0))),
        'RVOL >= 1.20': bool(np.isfinite(rr) and rr>=1.20),
        'ADX >= 25': bool(np.isfinite(adx) and adx>=25),
        'RSI 50-70': bool(np.isfinite(rs) and 50<=rs<=70),
        'CMF > 0': bool(np.isfinite(cmf) and cmf>0),
        'Price above EMA20': bool(np.isfinite(p) and np.isfinite(e20) and p>=e20),
        'Price above VWAP': bool(np.isfinite(p) and np.isfinite(vw) and p>=vw),
        'EMA9 above EMA20': bool(np.isfinite(e9) and np.isfinite(e20) and e9>=e20),
        'MACD histogram positive': bool(np.isfinite(mh) and mh>0),
    }


def pre_move_indicator_lift(feat, targets=(3,5,10), horizons=(1,3,5), lags=(1,2,3), min_signals=12):
    """Measure whether an indicator state observed D-1/D-2/D-3 precedes a future move.

    Baseline is computed on the same eligible anchor rows for each target/horizon/lag,
    so Lift answers: how much better was the target hit-rate when the indicator was on?
    """
    if feat is None or len(feat)<80:return pd.DataFrame()
    f=feat.dropna(subset=['Close','High','Low']).copy().reset_index(drop=False)
    closes=f['Close'].to_numpy(float); highs=f['High'].to_numpy(float); lows=f['Low'].to_numpy(float); n=len(f)
    states=[_research_indicator_states(r) for _,r in f.iterrows()]
    rows=[]
    for target in targets:
        tp=float(target)/100.0
        for h in horizons:
            h=int(h)
            future_hit=np.full(n,np.nan); future_mfe=np.full(n,np.nan); future_mae=np.full(n,np.nan)
            for i in range(n-h):
                p=closes[i]
                if not np.isfinite(p) or p<=0:continue
                fh=highs[i+1:i+1+h]; fl=lows[i+1:i+1+h]
                future_mfe[i]=np.nanmax(fh)/p-1.0; future_mae[i]=np.nanmin(fl)/p-1.0; future_hit[i]=float(future_mfe[i]>=tp)
            for lag in lags:
                lag=int(lag); anchors=[i for i in range(lag,n-h) if np.isfinite(future_hit[i])]
                if not anchors:continue
                base=float(np.mean([future_hit[i] for i in anchors]))
                names=states[0].keys() if states else []
                for name in names:
                    sig=[i for i in anchors if states[i-lag].get(name,False)]
                    if len(sig)<int(min_signals):continue
                    hr=float(np.mean([future_hit[i] for i in sig])); lift=hr/base if base>0 else np.nan
                    rows.append({'Indicator':name,'Days Before':f'-{lag}D','Target':f'+{target}%','Horizon':f'{h}D','Signals':len(sig),'Hit Rate %':100*hr,'Baseline %':100*base,'Lift x':lift,'Avg MFE %':100*float(np.nanmean([future_mfe[i] for i in sig])),'Avg MAE %':100*float(np.nanmean([future_mae[i] for i in sig]))})
    z=pd.DataFrame(rows)
    if z.empty:return z
    return z.sort_values(['Lift x','Signals'],ascending=[False,False]).reset_index(drop=True)



def _pre_move_discovery_states_v625(r):
    """Fixed causal state catalog for pre-move discovery.

    The catalog is defined before seeing target outcomes. V6.2.5 may discover PAIRS
    of these states on the 70% discovery sample, but validation is always reported
    on the untouched later 30% sample. Research only.
    """
    base=dict(_research_indicator_states(r))
    ob=_finite(r.get('obv_slope5',np.nan)); ad=_finite(r.get('ad_slope5',np.nan)); rs=_finite(r.get('rs20',np.nan))
    roc=_finite(r.get('roc_accel',np.nan)); br=_finite(r.get('breakout20_pct',np.nan)); cl=_finite(r.get('close_location',np.nan))
    ft=_finite(r.get('fresh_transition_count',np.nan),0); sqr=bool(_finite(r.get('squeeze_release',0),0)>0)
    base.update({
        'OBV accumulating': bool(np.isfinite(ob) and ob>0),
        'A/D accumulating': bool(np.isfinite(ad) and ad>0),
        'Relative strength positive': bool(np.isfinite(rs) and rs>0),
        'ROC accelerating': bool(np.isfinite(roc) and roc>0),
        'Squeeze release': sqr,
        'Near 20D breakout': bool(np.isfinite(br) and -3.0<=br<=2.0),
        'Strong close location': bool(np.isfinite(cl) and cl>=.70),
        'Fresh transitions >= 2': bool(np.isfinite(ft) and ft>=2),
    })
    return base


def pre_move_stock_oos_v625(feat, target_pct=.05, horizon_days=3, discovery_fraction=.70):
    """Per-stock 70/30 causal pre-move signal audit.

    Target is the maximum HIGH reached in the next `horizon_days`, measured from
    the current completed daily close. Discovery and validation are chronological.
    Every single state and every pair from the fixed catalog is audited. Pair
    selection must be performed outside this function using discovery rows only.
    """
    cols=['Signal','Kind','DiscoverySignals','DiscoveryHits','DiscoveryBaselinePct',
          'ValidationSignals','ValidationHits','ValidationBaselinePct','CurrentActive']
    if feat is None or not isinstance(feat,pd.DataFrame): return pd.DataFrame(columns=cols)
    f=feat.dropna(subset=['Close','High','Low']).copy()
    h=max(1,int(horizon_days))
    if len(f)<max(120,h+45): return pd.DataFrame(columns=cols)
    closes=pd.to_numeric(f['Close'],errors='coerce').to_numpy(float)
    highs=pd.to_numeric(f['High'],errors='coerce').to_numpy(float)
    n=len(f); eligible=n-h
    if eligible<80:return pd.DataFrame(columns=cols)
    hit=np.full(eligible,np.nan)
    tp=float(target_pct)
    for i in range(eligible):
        p=closes[i]
        if not np.isfinite(p) or p<=0:continue
        fh=highs[i+1:i+1+h]
        if len(fh): hit[i]=float(np.nanmax(fh)/p-1.0>=tp)
    valid=np.isfinite(hit)
    cut=int(eligible*float(discovery_fraction)); cut=max(50,min(cut,eligible-25))
    disc_idx=np.arange(0,cut)[valid[:cut]]; val_idx=np.arange(cut,eligible)[valid[cut:]]
    if len(disc_idx)<30 or len(val_idx)<15:return pd.DataFrame(columns=cols)
    states=[_pre_move_discovery_states_v625(r) for _,r in f.iloc[:eligible].iterrows()]
    current=_pre_move_discovery_states_v625(f.iloc[-1])
    names=list(states[0].keys()) if states else []
    matrix={name:np.asarray([bool(s.get(name,False)) for s in states],dtype=bool) for name in names}
    disc_base=100.0*float(np.nanmean(hit[disc_idx])) if len(disc_idx) else np.nan
    val_base=100.0*float(np.nanmean(hit[val_idx])) if len(val_idx) else np.nan
    rows=[]
    def add(sig,kind,mask,active):
        di=disc_idx[mask[disc_idx]]; vi=val_idx[mask[val_idx]]
        rows.append({'Signal':sig,'Kind':kind,'DiscoverySignals':int(len(di)),'DiscoveryHits':int(np.nansum(hit[di])) if len(di) else 0,
                     'DiscoveryBaselinePct':disc_base,'ValidationSignals':int(len(vi)),'ValidationHits':int(np.nansum(hit[vi])) if len(vi) else 0,
                     'ValidationBaselinePct':val_base,'CurrentActive':bool(active)})
    for name in names:add(name,'SINGLE',matrix[name],current.get(name,False))
    for i,a in enumerate(names):
        for b in names[i+1:]:
            mask=matrix[a]&matrix[b]
            if int(mask[disc_idx].sum())+int(mask[val_idx].sum())<=0:continue
            add(a+' + '+b,'PAIR',mask,bool(current.get(a,False) and current.get(b,False)))
    return pd.DataFrame(rows,columns=cols)


def aggregate_pre_move_oos_v625(stock_signal_rows, min_discovery_signals=25, min_validation_signals=12, min_discovery_lift=1.20):
    """Aggregate per-stock 70/30 audits without peeking at OOS for selection."""
    outcols=['Signal','Kind','DiscoveryStocks','DiscoverySignals','DiscoveryHitRatePct','DiscoveryMatchedBaselinePct','DiscoveryLiftX','DiscoveryEdgePP',
             'ValidationStocks','ValidationSignals','ValidationHitRatePct','ValidationMatchedBaselinePct','ValidationLiftX','ValidationEdgePP',
             'PositiveValidationStocks','PositiveValidationStockPct','CurrentActiveStocks','DiscoverySelected','OOSState','ResearchOnly']
    if stock_signal_rows is None or not isinstance(stock_signal_rows,pd.DataFrame) or stock_signal_rows.empty:return pd.DataFrame(columns=outcols)
    x=stock_signal_rows.copy(); rows=[]
    for (sig,kind),g in x.groupby(['Signal','Kind'],dropna=False):
        ds=pd.to_numeric(g['DiscoverySignals'],errors='coerce').fillna(0); dh=pd.to_numeric(g['DiscoveryHits'],errors='coerce').fillna(0)
        vs=pd.to_numeric(g['ValidationSignals'],errors='coerce').fillna(0); vh=pd.to_numeric(g['ValidationHits'],errors='coerce').fillna(0)
        db=pd.to_numeric(g['DiscoveryBaselinePct'],errors='coerce'); vb=pd.to_numeric(g['ValidationBaselinePct'],errors='coerce')
        dn=int(ds.sum()); vn=int(vs.sum()); dhr=100*float(dh.sum()/dn) if dn else np.nan; vhr=100*float(vh.sum()/vn) if vn else np.nan
        dbase=float(np.nansum(ds*db)/dn) if dn else np.nan; vbase=float(np.nansum(vs*vb)/vn) if vn else np.nan
        dl=dhr/dbase if np.isfinite(dhr) and np.isfinite(dbase) and dbase>0 else np.nan
        vl=vhr/vbase if np.isfinite(vhr) and np.isfinite(vbase) and vbase>0 else np.nan
        selected=bool(dn>=int(min_discovery_signals) and np.isfinite(dl) and dl>=float(min_discovery_lift) and dhr>dbase)
        vg=g[vs>=3].copy(); pos=0
        if not vg.empty:
            vgn=pd.to_numeric(vg['ValidationSignals'],errors='coerce').fillna(0); vgh=pd.to_numeric(vg['ValidationHits'],errors='coerce').fillna(0); vgb=pd.to_numeric(vg['ValidationBaselinePct'],errors='coerce')
            pos=int(((100*vgh/vgn.replace(0,np.nan))>vgb).sum())
        psp=100*pos/len(vg) if len(vg) else np.nan
        if not selected: state='DISCOVERY REJECTED'
        elif vn<int(min_validation_signals): state='INSUFFICIENT OOS'
        elif np.isfinite(vl) and vl>=1.20 and np.isfinite(psp) and psp>=55 and (vhr-vbase)>=3: state='OOS POSITIVE'
        elif np.isfinite(vl) and vl>=1.05 and (vhr-vbase)>0: state='OOS MIXED'
        else: state='OOS FAILED'
        rows.append({'Signal':sig,'Kind':kind,'DiscoveryStocks':int((ds>0).sum()),'DiscoverySignals':dn,'DiscoveryHitRatePct':dhr,'DiscoveryMatchedBaselinePct':dbase,
                     'DiscoveryLiftX':dl,'DiscoveryEdgePP':dhr-dbase if np.isfinite(dhr) and np.isfinite(dbase) else np.nan,
                     'ValidationStocks':int((vs>0).sum()),'ValidationSignals':vn,'ValidationHitRatePct':vhr,'ValidationMatchedBaselinePct':vbase,
                     'ValidationLiftX':vl,'ValidationEdgePP':vhr-vbase if np.isfinite(vhr) and np.isfinite(vbase) else np.nan,
                     'PositiveValidationStocks':pos,'PositiveValidationStockPct':psp,'CurrentActiveStocks':int(pd.Series(g['CurrentActive']).fillna(False).astype(bool).sum()),
                     'DiscoverySelected':selected,'OOSState':state,'ResearchOnly':True})
    z=pd.DataFrame(rows,columns=outcols)
    if z.empty:return z
    order={'OOS POSITIVE':0,'OOS MIXED':1,'INSUFFICIENT OOS':2,'OOS FAILED':3,'DISCOVERY REJECTED':4}
    z['_ord']=z['OOSState'].map(order).fillna(9)
    return z.sort_values(['_ord','ValidationLiftX','ValidationSignals','DiscoveryLiftX'],ascending=[True,False,False,False],na_position='last').drop(columns=['_ord']).reset_index(drop=True)

def hourly_lift_study(hourly_feat, targets=(1,2,3), horizon_bars=(1,2,4,8), min_signals=12):
    """Intraday signal lift using an hour-of-day matched baseline.

    Each signal is compared with the historical target hit-rate for observations from
    the same clock hour, reducing open/close time-of-day bias.
    """
    if hourly_feat is None or len(hourly_feat)<80:return pd.DataFrame()
    f=hourly_feat.dropna(subset=['Close','High','Low']).copy()
    if not isinstance(f.index,pd.DatetimeIndex):
        try:f.index=pd.to_datetime(f.index)
        except Exception:return pd.DataFrame()
    closes=f['Close'].to_numpy(float); highs=f['High'].to_numpy(float); lows=f['Low'].to_numpy(float); hours=np.array([int(x.hour) for x in f.index]); n=len(f)
    states=[_research_indicator_states(r) for _,r in f.iterrows()]; rows=[]
    for target in targets:
        tp=float(target)/100.0
        for hb in horizon_bars:
            hb=int(hb); hit=np.full(n,np.nan); mfe=np.full(n,np.nan); mae=np.full(n,np.nan)
            for i in range(n-hb):
                p=closes[i]
                if not np.isfinite(p) or p<=0:continue
                fh=highs[i+1:i+1+hb]; fl=lows[i+1:i+1+hb]
                mfe[i]=np.nanmax(fh)/p-1.0; mae[i]=np.nanmin(fl)/p-1.0; hit[i]=float(mfe[i]>=tp)
            valid=np.where(np.isfinite(hit))[0]
            by_hour={hh:float(np.mean(hit[valid[hours[valid]==hh]])) for hh in np.unique(hours[valid]) if np.any(hours[valid]==hh)}
            for name in (states[0].keys() if states else []):
                sig=[i for i in valid if states[i].get(name,False) and hours[i] in by_hour]
                if len(sig)<int(min_signals):continue
                hr=float(np.mean(hit[sig])); mb=float(np.mean([by_hour[hours[i]] for i in sig])); lift=hr/mb if mb>0 else np.nan
                rows.append({'Signal':name,'Target':f'+{target}%','Horizon':f'{hb}h','Signals':len(sig),'Hit Rate %':100*hr,'Matched Baseline %':100*mb,'Lift x':lift,'Avg MFE %':100*float(np.nanmean(mfe[sig])),'Avg MAE %':100*float(np.nanmean(mae[sig]))})
    z=pd.DataFrame(rows)
    if z.empty:return z
    return z.sort_values(['Lift x','Signals'],ascending=[False,False]).reset_index(drop=True)

def topk_daily_validation(timeline_all, k_values=(5,10), horizons=(1,3,5), score_col='Explosive Score'):
    if timeline_all is None or timeline_all.empty or 'Ticker' not in timeline_all:return pd.DataFrame()
    x=timeline_all.copy(); x['Date']=pd.to_datetime(x['Date']); rows=[]
    for k in k_values:
      for h in horizons:
        retcol=f'+{h}D Max Return %'
        if retcol not in x:continue
        top=[]; rest=[]; days=0
        for _,g in x.dropna(subset=[score_col,retcol]).groupby('Date'):
          if len(g)<=k:continue
          g=g.sort_values(score_col,ascending=False); top.extend(g.head(k)[retcol].astype(float)); rest.extend(g.iloc[k:][retcol].astype(float)); days+=1
        if top and rest:
          ta=float(np.mean(top)); ra=float(np.mean(rest)); rows.append({'Score':score_col,'Top K':k,'Horizon':f'{h}D','Days':days,'TopK Avg Max Return %':ta,'Rest Avg Max Return %':ra,'Excess %':ta-ra,'TopK Positive %':100*np.mean(np.array(top)>0)})
    return pd.DataFrame(rows)

def atr_target_validation(feat, threshold=60, atr_multiples=(1.0,1.5,2.0), horizons=(1,3,5)):
    f=feat.copy().dropna(subset=['Close']); rows=[]
    if len(f)<120:return pd.DataFrame()
    scores=np.array([explosive_score_row(r)[0] for _,r in f.iterrows()]); highs=f.High.to_numpy(float); closes=f.Close.to_numpy(float); atrp=f['atr_pct'].to_numpy(float)/100
    for mult in atr_multiples:
      for h in horizons:
        sig=[]; base=[]
        for i in range(int(len(f)*.4),len(f)-h):
          if not np.isfinite(atrp[i]):continue
          hit=float(np.nanmax(highs[i+1:i+1+h])/closes[i]-1 >= mult*atrp[i]); base.append(hit)
          if scores[i]>=threshold:sig.append(hit)
        hr=np.mean(sig) if sig else np.nan; br=np.mean(base) if base else np.nan
        rows.append({'ATR Target':f'+{mult:g} ATR','Horizon':f'{h}D','Signals':len(sig),'Hit Rate %':100*hr if np.isfinite(hr) else np.nan,'Baseline %':100*br if np.isfinite(br) else np.nan,'Lift':hr/br if np.isfinite(hr) and br>0 else np.nan})
    return pd.DataFrame(rows)

def score_row(r, min_turnover=3_000_000):
    comp=[]
    m3=_finite(r.get('mom3',np.nan)); m5=_finite(r.get('mom5',np.nan)); s=0
    if np.isfinite(m3) and np.isfinite(m5):
        s += 5 if m3>0 else 0; s += 4 if m5>0 else 0; s += 3 if m3>.02 else 0; s += 2 if m5>.04 else 0
    s=_clamp(s,0,16); comp.append(('Momentum',s,16))
    dv=directional_volume_row(r); s=20*dv['bullish']; comp.append(('Directional volume',s,20))
    b=_finite(r.get('breakout20_pct',np.nan)); s=0
    if np.isfinite(b):
        if -3<=b<=0:s=9
        elif 0<b<=4:s=14
        elif 4<b<=8:s=10
    comp.append(('20D breakout/proximity',s,14))
    rv=_finite(r.get('rsi14',np.nan)); s=8 if 52<=rv<=67 else 5 if 48<=rv<=72 else 0; comp.append(('RSI',s,8))
    mh=_finite(r.get('macd_hist',np.nan)); ms=_finite(r.get('macd_hist_slope',np.nan)); s=(7 if mh>0 else 0)+(5 if ms>0 else 0); comp.append(('MACD histogram',s,12))
    av=_finite(r.get('adx14',np.nan)); s=10 if av>=30 else 8 if av>=25 else 5 if av>=20 else 0; comp.append(('ADX trend strength',s,10))
    at=_finite(r.get('atr_pct',np.nan)); s=8 if 2<=at<=7 else 5 if 1.2<=at<=10 else 0; comp.append(('ATR / volatility',s,8))
    cl=_finite(r.get('close_location',np.nan)); s=6 if cl>=.75 else 4 if cl>=.55 else 2 if cl>=.4 else 0; comp.append(('Candle strength',s,6))
    tv=_finite(r.get('turnover',np.nan)); tr=_finite(r.get('turnover_ratio60',np.nan));
    if np.isfinite(tv) and min_turnover > 0 and tv < min_turnover:s=0
    elif np.isfinite(tr):s=6 if tr>=1.5 else 4 if tr>=1.2 else 2 if tr>=0.8 else 0
    else:s=0
    comp.append(('Liquidity',s,6))
    raw=float(_clamp(sum(float(p) for _,p,_ in comp)))
    exit_score,_,_=exit_pressure_row(r)
    return float(_clamp(raw*(1.0-0.30*exit_score/100.0))), comp


def early_score_row(r):
    pts=[]
    ob=float(r.get('obv_slope5',np.nan)); pts.append(('OBV accumulation',18 if np.isfinite(ob) and ob>.08 else 12 if np.isfinite(ob) and ob>0 else 0,18))
    cm=float(r.get('cmf20',np.nan)); pts.append(('CMF money flow',18 if np.isfinite(cm) and cm>.12 else 12 if np.isfinite(cm) and cm>0 else 0,18))
    ad=float(r.get('ad_slope5',np.nan)); pts.append(('Accumulation/Distribution',12 if np.isfinite(ad) and ad>.05 else 8 if np.isfinite(ad) and ad>0 else 0,12))
    sq=bool(r.get('squeeze',0)); rel=bool(r.get('squeeze_release',0)); pts.append(('Bollinger/Keltner squeeze',14 if rel else 9 if sq else 0,14))
    rs=float(r.get('rs20',np.nan)); pts.append(('Relative strength',12 if np.isfinite(rs) and rs>.08 else 8 if np.isfinite(rs) and rs>0 else 0,12))
    ra=float(r.get('roc_accel',np.nan)); pts.append(('ROC acceleration',10 if np.isfinite(ra) and ra>.02 else 6 if np.isfinite(ra) and ra>0 else 0,10))
    pts.append(('Price/Volume divergence',10 if bool(r.get('pv_divergence',0)) else 0,10))
    dv=directional_volume_row(r); va=_finite(r.get('vol_accel',np.nan)); pts.append(('Directional Early RVOL',6*dv['bullish'] if np.isfinite(va) and va>1 else 3*dv['bullish'],6))
    return float(_clamp(sum(p for _,p,_ in pts))), pts


def score_latest(feat, min_turnover=3_000_000):
    r=feat.dropna(subset=['Close']).iloc[-1]
    score,components=score_row(r,min_turnover)
    early,early_components=early_score_row(r)
    xp,xpc,xps=exit_pressure_row(r); dv=directional_volume_row(r); inst=institutional_flow_row(r); out={'score':score,'early_score':early,'price':float(r['Close']),'daily_change_pct':float(r.get('ret1',np.nan))*100,'components':components,'early_components':early_components,'exit_pressure':round(xp,1),'exit_stage':xps,'exit_components':xpc,'volume_context':dv['label'],'bullish_volume_evidence':round(100*dv['bullish'],1),'bearish_volume_evidence':round(100*dv['bearish'],1),'institutional_flow_score':inst['score'],'institutional_flow_label':inst['label']}
    for k in ['volume_ratio','rsi14','adx14','atr_pct','cmf20','obv_slope5','ad_slope5','rs20','roc_accel','vwap','ema9','ema20','ema50','support20','resistance20','macd_hist','robust_volume_ratio','post_impulse_retention','volume_dryup','volume_reexpansion','fresh_transition_count','time_adjusted_rvol','distribution_persistence3','corporate_action_flag']:
        val=r.get(k,np.nan); out[k]=float(val) if not pd.isna(val) else np.nan
    return out


def backtest_signal(feat, horizon=5, target_pct=.06, score_threshold=66, min_turnover=3_000_000):
    f=feat.copy(); f['score']=[score_row(r,min_turnover)[0] for _,r in f.iterrows()]
    highs=f['High'].to_numpy(dtype='float64'); lows=f['Low'].to_numpy(dtype='float64'); closes=f['Close'].to_numpy(dtype='float64')
    hits=np.full(len(f),np.nan); rets=np.full(len(f),np.nan); dds=np.full(len(f),np.nan)
    for i in range(len(f)-horizon):
        fh=highs[i+1:i+1+horizon]; fl=lows[i+1:i+1+horizon]; end=closes[i+horizon]
        hits[i]=1. if np.nanmax(fh)>=closes[i]*(1+target_pct) else 0.
        rets[i]=end/closes[i]-1; dds[i]=np.nanmin(fl)/closes[i]-1
    f['hit']=hits; f['fwd_return']=rets; f['drawdown']=dds
    valid=f[(f['score']>=score_threshold)&f['hit'].notna()].copy(); n=len(valid)
    if n==0:return {'n':0,'hits':0,'misses':0,'hit_rate':np.nan,'avg_return':np.nan,'max_drawdown':np.nan,'confidence':0,'confidence_label':'LOW','backtest_performance':0.0,'sample_reliability':0.0}
    hr=float(valid['hit'].mean())
    sample_factor=min(1.,math.sqrt(n/60))
    # V5.3.1: confidence gives more weight to demonstrated hit-rate performance,
    # while sample size remains an explicit reliability adjustment.
    conf=100*(.80*hr+.20*sample_factor)
    label='HIGH' if n>=30 and hr>=.60 else 'MEDIUM' if n>=12 and hr>=.45 else 'LOW'
    hits=int(valid['hit'].sum())
    return {
        'n':int(n),'hits':hits,'misses':int(n-hits),'hit_rate':hr,
        'avg_return':float(valid['fwd_return'].mean()),'max_drawdown':float(valid['drawdown'].min()),
        'confidence':round(conf,1),'confidence_label':label,
        'backtest_performance':round(hr*100,1),'sample_reliability':round(sample_factor*100,1)
    }


def _recent_transition_evidence(feat, bars=4):
    if feat is None or len(feat)==0:
        return {'fresh':False,'count':0.0,'labels':[],'macd_improving':False,'volume_accel':False}
    f=feat.dropna(subset=['Close'])
    if f.empty:return {'fresh':False,'count':0.0,'labels':[],'macd_improving':False,'volume_accel':False}
    tail=f.tail(max(2,int(bars)))
    labels=[]; count=0.0
    checks=[('EMA9/20 cross','ema9_cross_up'),('MACD cross','macd_cross_up'),('MACD histogram turn','macd_hist_turn_pos'),('VWAP reclaim','vwap_cross_up')]
    for label,col in checks:
        if col in tail and pd.to_numeric(tail[col],errors='coerce').fillna(0).gt(0).any():
            labels.append(label);count+=1.0
    last=tail.iloc[-1]
    ms=_finite(last.get('macd_hist_slope',np.nan)); va=_finite(last.get('vol_accel',np.nan)); re=_finite(last.get('volume_reexpansion',np.nan))
    macd_improving=bool(np.isfinite(ms) and ms>0)
    volume_accel=bool((np.isfinite(va) and va>=1.08) or (np.isfinite(re) and re>=1.15))
    if macd_improving:labels.append('MACD strengthening')
    if volume_accel:labels.append('volume acceleration')
    fresh=bool(count>=1 or (macd_improving and volume_accel))
    return {'fresh':fresh,'count':count,'labels':labels,'macd_improving':macd_improving,'volume_accel':volume_accel}



def _ts_utc_v614(value):
    try:
        ts=pd.Timestamp(value)
        return ts.tz_localize('UTC') if ts.tzinfo is None else ts.tz_convert('UTC')
    except Exception:
        return pd.NaT


def _bar_confirmation_v616(idx, timeframe):
    """Return when a completed bar's signal actually became observable.

    Yahoo intraday indices are bar-start timestamps. A 09:30 1H bar is not
    actionable at 09:30; its close-based indicators are only known at 10:30.
    Keeping this distinction prevents trigger-audit timestamps from implying
    look-ahead execution.
    """
    try:
        ts=pd.Timestamp(idx)
        tf=str(timeframe).upper()
        delta=pd.Timedelta(minutes=15) if tf=='15M' else (pd.Timedelta(hours=1) if tf=='1H' else pd.Timedelta(0))
        confirmed=ts+delta
        return confirmed,_ts_utc_v614(confirmed)
    except Exception:
        return idx,_ts_utc_v614(idx)


def _opening_setup_origin_v616(m15):
    """Research/audit-only earliest opening impulse confirmation.

    This does NOT create a buy signal and does NOT replace the validated trigger
    anchor used for trade-plan geometry. It records when a large opening move
    first had price/flow confirmation so Feedback can later test whether this
    feature deserves learned weight.
    """
    if m15 is None or not isinstance(m15,pd.DataFrame) or m15.empty:return None
    f=m15.dropna(subset=['Close']).copy()
    if f.empty:return None
    try:
        day=pd.Timestamp(f.index[-1]).date(); s=f.loc[[pd.Timestamp(x).date()==day for x in f.index]].head(4)
    except Exception:
        s=f.tail(4)
    for idx,r in s.iterrows():
        c=_finite(r.get('Close',np.nan)); vw=_finite(r.get('vwap',np.nan)); e9=_finite(r.get('ema9',np.nan)); e20=_finite(r.get('ema20',np.nan)); mh=_finite(r.get('macd_hist',np.nan))
        ret=_finite(r.get('ret1',np.nan)); imp=_finite(r.get('recent_impulse',np.nan)); rv=_finite(r.get('time_adjusted_rvol',r.get('robust_volume_ratio',np.nan))); bull=_finite(r.get('bullish_volume_evidence',np.nan))
        move=max(ret if np.isfinite(ret) else -9,imp if np.isfinite(imp) else -9)
        structure=bool(np.isfinite(c) and np.isfinite(vw) and c>vw and np.isfinite(e9) and np.isfinite(e20) and e9>e20 and np.isfinite(mh) and mh>0)
        participation=bool(np.isfinite(rv) and rv>=1.25 and np.isfinite(bull) and bull>=0.65)
        if structure and participation and np.isfinite(move) and move>=0.025:
            confirmed,confirm_sort=_bar_confirmation_v616(idx,'15m')
            return {'price':float(c),'bar_start_time':str(idx),'confirmed_time':str(confirmed),'confirm_sort':confirm_sort,'timeframe':'15m',
                    'signals':['Opening impulse','RVOL confirmation','Bullish volume','Above VWAP/EMA structure'],
                    'quality':'RESEARCH','selection':'OPENING IMPULSE ORIGIN — AUDIT ONLY'}
    return None


def _momentum_state_v616(hourly=None,m15=None):
    """Separate momentum *direction* from volume participation. Audit-only in V6.1.6."""
    def one(frame,tf):
        if frame is None or not isinstance(frame,pd.DataFrame) or frame.empty:return {'label':'NO DATA','timeframe':tf}
        q=frame.dropna(subset=['Close']).tail(4)
        if len(q)<2:return {'label':'NO DATA','timeframe':tf}
        r=q.iloc[-1]; p=q.iloc[-2]
        c=_finite(r.get('Close',np.nan)); e20=_finite(r.get('ema20',np.nan)); mh=_finite(r.get('macd_hist',np.nan)); ph=_finite(p.get('macd_hist',np.nan)); sl=_finite(r.get('macd_hist_slope',np.nan)); rs=_finite(r.get('rsi14',np.nan)); prs=_finite(p.get('rsi14',np.nan))
        if np.isfinite(c) and np.isfinite(e20) and c<e20 and np.isfinite(mh) and mh<0: lab='BEARISH'
        elif np.isfinite(mh) and mh>0 and ((np.isfinite(sl) and sl>0) or (np.isfinite(ph) and mh>ph)): lab='STRENGTHENING'
        elif (np.isfinite(mh) and np.isfinite(ph) and mh<ph and (mh<0 or (np.isfinite(sl) and sl<0))) or (np.isfinite(rs) and np.isfinite(prs) and prs>70 and rs<prs-2): lab='COOLING'
        else: lab='STABLE'
        return {'label':lab,'timeframe':tf,'macd_hist':mh,'macd_hist_prev':ph,'rsi14':rs}
    a=one(m15,'15m'); b=one(hourly,'1H'); l15=a['label']; l1=b['label']
    if 'BEARISH' in (l15,l1) and 'STRENGTHENING' in (l15,l1): lab='MIXED'
    elif l15=='COOLING' and l1 in ('STRENGTHENING','STABLE'): lab='SHORT-TERM COOLING'
    elif l15=='COOLING' and l1=='COOLING': lab='COOLING'
    elif 'STRENGTHENING' in (l15,l1) and all(x in ('STRENGTHENING','STABLE','NO DATA') for x in (l15,l1)): lab='STRENGTHENING'
    elif l15=='NO DATA': lab=l1
    elif l1=='NO DATA': lab=l15
    elif l15==l1: lab=l15
    else: lab='MIXED'
    return {'label':lab,'label_15m':l15,'label_1h':l1}



def _post_spike_state_v621(f, hourly=None, m15=None, previous_close=None, current_price=None, momentum_state=None):
    """Session-aware post-spike state audit.

    V6.2.1 fixes an after-hours mismatch from V6.2.0: regular-session VWAP/EMA
    structure is evaluated against the last confirmed regular-session 15m close,
    while the live/AH quote is used only for retention and giveback. Distribution
    now requires persistent/meaningful bearish confirmation rather than a single
    borderline bar. Research only; it never clears the Chase/Extension Guard.
    """
    out={'post_spike_state':'NO DATA','session_peak_price':np.nan,'session_peak_move_pct':np.nan,
         'high_giveback_pct':np.nan,'move_retention_from_high_pct':np.nan,
         'post_spike_structure_ok':False,'post_spike_distribution_risk':'NO DATA',
         'post_spike_structure_price':np.nan,'post_spike_structure_reference':'NO DATA',
         'post_spike_bearish_confirm_bars':0,'post_spike_distribution_score':np.nan}
    if m15 is None or not isinstance(m15,pd.DataFrame) or m15.empty:return out
    q=m15.dropna(subset=['Close']).copy()
    if q.empty:return out
    try:
        day=pd.Timestamp(q.index[-1]).date(); s=q.loc[[pd.Timestamp(x).date()==day for x in q.index]].copy()
    except Exception:
        s=q.tail(26).copy()
    if s.empty:return out
    # m15 is fetched without pre/post rows, so this is the confirmed regular-session
    # structure reference even when current_price is an after-hours live quote.
    structure_price=_finite(s.iloc[-1].get('Close',np.nan))
    p=_finite(current_price,structure_price)
    prev=_finite(previous_close,np.nan)
    high=float(pd.to_numeric(s.get('High',s.get('Close')),errors='coerce').max())
    if not (np.isfinite(p) and p>0 and np.isfinite(high) and high>0):return out
    peak_move=(high/prev-1.0) if np.isfinite(prev) and prev>0 else np.nan
    retention=((p-prev)/(high-prev)) if np.isfinite(prev) and prev>0 and high>prev else np.nan
    giveback=max(0.0,(high-p)/high)
    last=s.iloc[-1]
    vw=_finite(last.get('vwap',np.nan)); e20=_finite(last.get('ema20',np.nan)); e9=_finite(last.get('ema9',np.nan)); atr=_finite(last.get('atr14',np.nan),0)
    # Soft ATR tolerances avoid a one-cent boundary flipping structure to bearish.
    structure=bool((not np.isfinite(vw) or structure_price>=vw-.05*atr) and
                   (not np.isfinite(e20) or structure_price>=e20-.10*atr) and
                   (not np.isfinite(e9) or structure_price>=e9-.15*atr))
    recent=s.tail(3)
    bears=pd.to_numeric(recent.get('bearish_volume_evidence'),errors='coerce').fillna(0.0) if 'bearish_volume_evidence' in recent else pd.Series(dtype=float)
    bear_last=_finite(last.get('bearish_volume_evidence',np.nan),0)
    bear_confirm_bars=int((bears>=.25).sum()) if len(bears) else 0
    dist=_finite(last.get('distribution_persistence3',np.nan),0)
    dist_score=max(float(dist) if np.isfinite(dist) else 0.0, bear_confirm_bars/3.0)
    distribution_confirmed=bool((not structure) and (bear_last>=.35 or bear_confirm_bars>=2 or dist>=.67))
    mlab=str((momentum_state or {}).get('label','NO DATA')).upper()
    if np.isfinite(retention) and retention<.50:
        state='FAILED SPIKE'
    elif (np.isfinite(retention) and retention<.68) or distribution_confirmed:
        state='DISTRIBUTION RISK'
    elif np.isfinite(peak_move) and peak_move>=.05 and np.isfinite(retention) and retention>=.82 and structure and mlab in ('COOLING','SHORT-TERM COOLING','STABLE','MIXED'):
        state='HEALTHY CONSOLIDATION'
    elif np.isfinite(peak_move) and peak_move>=.05 and np.isfinite(retention) and retention>=.86 and structure and mlab=='STRENGTHENING':
        state='CONTINUATION PRESSURE'
    elif np.isfinite(retention) and retention>=.75 and structure:
        state='EXTENDED HOLD'
    else:
        state='NEUTRAL'
    risk='HIGH' if state in ('FAILED SPIKE','DISTRIBUTION RISK') else ('LOW' if state in ('HEALTHY CONSOLIDATION','CONTINUATION PRESSURE') else 'MEDIUM')
    out.update({'post_spike_state':state,'session_peak_price':high,
                'session_peak_move_pct':100*peak_move if np.isfinite(peak_move) else np.nan,
                'high_giveback_pct':100*giveback,
                'move_retention_from_high_pct':100*retention if np.isfinite(retention) else np.nan,
                'post_spike_structure_ok':structure,'post_spike_distribution_risk':risk,
                'post_spike_structure_price':structure_price,
                'post_spike_structure_reference':'LAST CONFIRMED REGULAR 15m CLOSE',
                'post_spike_bearish_confirm_bars':bear_confirm_bars,
                'post_spike_distribution_score':dist_score})
    return out


def _continuation_base_v619(m15, previous_close=None, current_price=None):
    """Research-only high-base / continuation reset detector.

    A stock blocked for being extended may never revisit the old entry zone. This
    detector records a second *research path*: time + compression + volume dry-up
    near the highs, followed later by a fresh breakout. It is deliberately NOT an
    entry gate in V6.1.9; Feedback/OOS must validate it first.
    """
    out={'continuation_base_candidate':False,'continuation_base_status':'RESEARCH • NO BASE',
         'continuation_base_bars':0,'continuation_base_low':np.nan,'continuation_base_high':np.nan,
         'continuation_base_range_pct':np.nan,'continuation_base_range_atr':np.nan,
         'continuation_volume_dryup_ratio':np.nan,'continuation_breakout_trigger':np.nan,
         'continuation_base_quality':'NO DATA','continuation_session_peak':np.nan,'continuation_breakout_reference':'—',
         'continuation_hold_ok':False}
    if m15 is None or not isinstance(m15,pd.DataFrame) or m15.empty:return out
    q=m15.dropna(subset=['Close']).copy()
    if len(q)<8:return out
    try:
        day=pd.Timestamp(q.index[-1]).date(); s=q.loc[[pd.Timestamp(x).date()==day for x in q.index]].copy()
    except Exception:
        s=q.tail(26).copy()
    if len(s)<8:return out
    highs=pd.to_numeric(s.get('High',s['Close']),errors='coerce')
    if highs.dropna().empty:return out
    peak_pos=int(np.nanargmax(highs.to_numpy(dtype=float)))
    after=s.iloc[peak_pos+1:].copy()
    if len(after)<4:return out
    base=after.tail(min(8,len(after))).copy()
    bh=float(pd.to_numeric(base.get('High',base['Close']),errors='coerce').max())
    bl=float(pd.to_numeric(base.get('Low',base['Close']),errors='coerce').min())
    last=base.iloc[-1]; p=_finite(current_price,_finite(last.get('Close',np.nan)))
    iatr=_finite(last.get('atr14',np.nan)); vw=_finite(last.get('vwap',np.nan)); e20=_finite(last.get('ema20',np.nan))
    opening=s.head(min(4,len(s)))
    ov=pd.to_numeric(opening.get('Volume'),errors='coerce').dropna(); bv=pd.to_numeric(base.get('Volume'),errors='coerce').dropna()
    dry=(float(bv.median())/float(ov.median())) if len(ov) and len(bv) and float(ov.median())>0 else np.nan
    rng_pct=(bh/bl-1.0)*100.0 if bl>0 else np.nan
    rng_atr=(bh-bl)/iatr if np.isfinite(iatr) and iatr>0 else np.nan
    hold=bool(np.isfinite(p) and (not np.isfinite(vw) or p>=vw) and (not np.isfinite(e20) or p>=e20))
    prev=_finite(previous_close,np.nan)
    move=(p/prev-1.0) if np.isfinite(prev) and prev>0 and np.isfinite(p) else np.nan
    candidate=bool(len(base)>=4 and hold and np.isfinite(move) and move>=.05 and
                   np.isfinite(rng_pct) and rng_pct<=2.6 and
                   (not np.isfinite(dry) or dry<=.72))
    # A continuation breakout must clear BOTH the base and the session peak.
    # V6.1.9 could produce a trigger a few cents below the actual session high
    # when the post-peak base high sat just under that peak (e.g. COIN).
    session_peak=float(highs.max())
    if np.isfinite(iatr) and iatr>0:
        breakout=max(bh+.10*iatr, session_peak+.05*iatr)
    else:
        breakout=max(bh*1.0015, session_peak*1.0005)
    if np.isfinite(rng_atr):
        quality='TIGHT' if rng_atr<=1.50 else ('MODERATE' if rng_atr<=2.50 else 'LOOSE')
    else:
        quality='UNKNOWN'
    if candidate:
        status=f'RESEARCH • BASE FORMING • {quality} COMPRESSION'
    else:
        status='RESEARCH • HOLDING HIGH' if hold and np.isfinite(move) and move>=.05 else 'RESEARCH • NO BASE'
    out.update({'continuation_base_candidate':candidate,'continuation_base_status':status,
                'continuation_base_bars':int(len(base)),'continuation_base_low':bl,'continuation_base_high':bh,
                'continuation_base_range_pct':rng_pct,'continuation_base_range_atr':rng_atr,
                'continuation_volume_dryup_ratio':dry,'continuation_breakout_trigger':breakout,
                'continuation_base_quality':quality,'continuation_session_peak':session_peak,
                'continuation_breakout_reference':'MAX(base high + 0.10 ATR, session peak + 0.05 ATR)',
                'continuation_hold_ok':hold})
    return out


def setup_origin_validation_v619(m15_feat, target_pct=.02, stop_pct=.015, max_bars=16):
    """Causal intraday validation of the V6.1.6 opening Setup Origin rule.

    Scans each available 15m session, finds the first origin in the first four
    completed bars using the exact research rule, then checks whether +target was
    touched before -stop within the next max_bars. Same-bar target+stop is marked
    AMBIGUOUS and excluded from clean hit/miss rates.
    """
    cols=['SessionDate','OriginBarStart','OriginConfirmed','OriginPrice','BarsAvailable',
          'ForwardMaxPct','ForwardMinPct','TargetPct','StopPct','Outcome','BarsToOutcome']
    if m15_feat is None or not isinstance(m15_feat,pd.DataFrame) or m15_feat.empty:
        return pd.DataFrame(columns=cols)
    f=m15_feat.dropna(subset=['Close']).copy()
    rows=[]
    try: dates=sorted(set(pd.Timestamp(x).date() for x in f.index))
    except Exception:return pd.DataFrame(columns=cols)
    for day in dates:
        try:s=f.loc[[pd.Timestamp(x).date()==day for x in f.index]].copy()
        except Exception:continue
        if len(s)<5:continue
        origin=None; origin_pos=None
        for pos,(idx,r) in enumerate(s.head(4).iterrows()):
            c=_finite(r.get('Close',np.nan)); vw=_finite(r.get('vwap',np.nan)); e9=_finite(r.get('ema9',np.nan)); e20=_finite(r.get('ema20',np.nan)); mh=_finite(r.get('macd_hist',np.nan))
            ret=_finite(r.get('ret1',np.nan)); imp=_finite(r.get('recent_impulse',np.nan)); rv=_finite(r.get('time_adjusted_rvol',r.get('robust_volume_ratio',np.nan))); bull=_finite(r.get('bullish_volume_evidence',np.nan))
            move=max(ret if np.isfinite(ret) else -9,imp if np.isfinite(imp) else -9)
            structure=bool(np.isfinite(c) and np.isfinite(vw) and c>vw and np.isfinite(e9) and np.isfinite(e20) and e9>e20 and np.isfinite(mh) and mh>0)
            participation=bool(np.isfinite(rv) and rv>=1.25 and np.isfinite(bull) and bull>=0.65)
            if structure and participation and np.isfinite(move) and move>=.025:
                origin=(idx,c);origin_pos=pos;break
        if origin is None:continue
        idx,price=origin
        fut=s.iloc[origin_pos+1:origin_pos+1+int(max_bars)].copy()
        if fut.empty:continue
        highs=pd.to_numeric(fut.get('High',fut['Close']),errors='coerce'); lows=pd.to_numeric(fut.get('Low',fut['Close']),errors='coerce')
        fmax=(float(highs.max())/price-1.0)*100.0 if highs.notna().any() else np.nan
        fmin=(float(lows.min())/price-1.0)*100.0 if lows.notna().any() else np.nan
        tgt=price*(1+float(target_pct)); stp=price*(1-float(stop_pct)); outcome='OPEN'; bars_to=np.nan
        for j,(_,rr) in enumerate(fut.iterrows(),start=1):
            hi=_finite(rr.get('High',rr.get('Close',np.nan))); lo=_finite(rr.get('Low',rr.get('Close',np.nan)))
            ht=np.isfinite(hi) and hi>=tgt; hs=np.isfinite(lo) and lo<=stp
            if ht and hs: outcome='AMBIGUOUS';bars_to=j;break
            if ht: outcome='TARGET';bars_to=j;break
            if hs: outcome='STOP';bars_to=j;break
        confirmed,_=_bar_confirmation_v616(idx,'15m')
        rows.append({'SessionDate':str(day),'OriginBarStart':str(idx),'OriginConfirmed':str(confirmed),'OriginPrice':price,
                     'BarsAvailable':int(len(fut)),'ForwardMaxPct':fmax,'ForwardMinPct':fmin,
                     'TargetPct':100*float(target_pct),'StopPct':100*float(stop_pct),'Outcome':outcome,'BarsToOutcome':bars_to})
    return pd.DataFrame(rows,columns=cols)


def setup_origin_validation_summary_v619(events):
    cols=['Metric','Value']
    if events is None or not isinstance(events,pd.DataFrame) or events.empty:
        return pd.DataFrame([{'Metric':'Origin signals','Value':0},{'Metric':'Clean outcomes','Value':0}],columns=cols)
    n=len(events); clean=events[events['Outcome'].isin(['TARGET','STOP'])]
    hit=(clean['Outcome']=='TARGET').mean()*100.0 if len(clean) else np.nan
    amb=(events['Outcome']=='AMBIGUOUS').sum(); open_n=(events['Outcome']=='OPEN').sum()
    avgmax=pd.to_numeric(events['ForwardMaxPct'],errors='coerce').mean(); avgmin=pd.to_numeric(events['ForwardMinPct'],errors='coerce').mean()
    return pd.DataFrame([
        {'Metric':'Origin signals','Value':int(n)},
        {'Metric':'Clean outcomes','Value':int(len(clean))},
        {'Metric':'Clean target-before-stop hit rate %','Value':hit},
        {'Metric':'Ambiguous same-bar outcomes','Value':int(amb)},
        {'Metric':'Open / no touch outcomes','Value':int(open_n)},
        {'Metric':'Average forward max %','Value':avgmax},
        {'Metric':'Average forward min %','Value':avgmin},
    ],columns=cols)


def _wilson_interval_v620(hits, n, z=1.96):
    """95% Wilson interval for a binomial hit rate, returned in percent."""
    try:
        n=int(n); hits=int(hits)
    except Exception:
        return (np.nan,np.nan)
    if n<=0:return (np.nan,np.nan)
    p=hits/n; den=1.0+(z*z/n)
    center=(p+(z*z)/(2.0*n))/den
    half=(z*np.sqrt((p*(1.0-p)/n)+(z*z/(4.0*n*n))))/den
    return (100.0*max(0.0,center-half),100.0*min(1.0,center+half))


def setup_origin_validation_summary_v620(events):
    """Uncertainty-aware summary for the research-only Setup Origin signal.

    The key change versus V6.1.9 is that a tiny hit-rate sample is never allowed
    to look precise.  We show Wilson uncertainty and a simple fixed-payoff gross
    expectancy, but this function does not select thresholds or alter entry gates.
    """
    cols=['Metric','Value']
    if events is None or not isinstance(events,pd.DataFrame) or events.empty:
        return pd.DataFrame([
            {'Metric':'Origin signals','Value':0},
            {'Metric':'Clean outcomes','Value':0},
            {'Metric':'Research sample state','Value':'NO SAMPLE'},
        ],columns=cols)
    n=int(len(events)); clean=events[events['Outcome'].isin(['TARGET','STOP'])].copy()
    cn=int(len(clean)); hits=int((clean['Outcome']=='TARGET').sum()); stops=int((clean['Outcome']=='STOP').sum())
    hit=(100.0*hits/cn) if cn else np.nan
    lo,hi=_wilson_interval_v620(hits,cn)
    amb=int((events['Outcome']=='AMBIGUOUS').sum()); open_n=int((events['Outcome']=='OPEN').sum())
    avgmax=pd.to_numeric(events['ForwardMaxPct'],errors='coerce').mean(); avgmin=pd.to_numeric(events['ForwardMinPct'],errors='coerce').mean()
    medbars=pd.to_numeric(clean.get('BarsToOutcome'),errors='coerce').median() if cn else np.nan
    tgt=pd.to_numeric(clean.get('TargetPct'),errors='coerce').median() if cn else np.nan
    stp=pd.to_numeric(clean.get('StopPct'),errors='coerce').median() if cn else np.nan
    expectancy=((hits/cn)*tgt-(stops/cn)*stp) if cn and np.isfinite(tgt) and np.isfinite(stp) else np.nan
    state='LOW SAMPLE — RESEARCH ONLY' if cn<12 else ('DEVELOPING SAMPLE — RESEARCH ONLY' if cn<30 else 'RESEARCH SAMPLE ≥30 — STILL NOT A PRODUCTION GATE')
    return pd.DataFrame([
        {'Metric':'Origin signals','Value':n},
        {'Metric':'Clean outcomes','Value':cn},
        {'Metric':'Target hits','Value':hits},
        {'Metric':'Stops','Value':stops},
        {'Metric':'Clean target-before-stop hit rate %','Value':hit},
        {'Metric':'Hit-rate Wilson 95% low %','Value':lo},
        {'Metric':'Hit-rate Wilson 95% high %','Value':hi},
        {'Metric':'Fixed-payoff gross expectancy % / clean signal','Value':expectancy},
        {'Metric':'Ambiguous same-bar outcomes','Value':amb},
        {'Metric':'Open / no touch outcomes','Value':open_n},
        {'Metric':'Average forward max %','Value':avgmax},
        {'Metric':'Average forward min %','Value':avgmin},
        {'Metric':'Median bars to clean outcome','Value':medbars},
        {'Metric':'Research sample state','Value':state},
    ],columns=cols)


def setup_origin_robustness_v620(m15_feat):
    """Fixed scenario matrix to test robustness without optimizing to one ticker.

    These scenarios are intentionally pre-declared.  No 'best' row is selected and
    none of these results are fed back into production scoring in V6.2.0.
    """
    scenarios=[
        (0.015,0.010,8),(0.015,0.010,16),
        (0.020,0.015,8),(0.020,0.015,16),
        (0.025,0.015,16),(0.030,0.020,16),
    ]
    rows=[]
    for target,stop,horizon in scenarios:
        ev=setup_origin_validation_v619(m15_feat,target_pct=target,stop_pct=stop,max_bars=horizon)
        if ev is None or ev.empty:
            rows.append({'TargetPct':100*target,'StopPct':100*stop,'HorizonBars':horizon,'Signals':0,'CleanN':0,'Hits':0,'Stops':0,'HitRatePct':np.nan,'Wilson95LowPct':np.nan,'Wilson95HighPct':np.nan,'GrossExpectancyPct':np.nan,'Ambiguous':0,'Open':0,'ResearchOnly':True})
            continue
        clean=ev[ev['Outcome'].isin(['TARGET','STOP'])]
        cn=len(clean); hits=int((clean['Outcome']=='TARGET').sum()); stops=int((clean['Outcome']=='STOP').sum())
        hr=(100.0*hits/cn) if cn else np.nan; lo,hi=_wilson_interval_v620(hits,cn)
        exp=((hits/cn)*(100*target)-(stops/cn)*(100*stop)) if cn else np.nan
        rows.append({'TargetPct':100*target,'StopPct':100*stop,'HorizonBars':horizon,'Signals':int(len(ev)),'CleanN':int(cn),'Hits':hits,'Stops':stops,'HitRatePct':hr,'Wilson95LowPct':lo,'Wilson95HighPct':hi,'GrossExpectancyPct':exp,'Ambiguous':int((ev['Outcome']=='AMBIGUOUS').sum()),'Open':int((ev['Outcome']=='OPEN').sum()),'ResearchOnly':True})
    return pd.DataFrame(rows)



def _opening_origin_signal_pos_v622(session):
    """Return the first causal Setup-Origin bar position (0..3) or None."""
    if session is None or not isinstance(session,pd.DataFrame) or session.empty:
        return None
    for pos,(idx,r) in enumerate(session.head(4).iterrows()):
        c=_finite(r.get('Close',np.nan)); vw=_finite(r.get('vwap',np.nan)); e9=_finite(r.get('ema9',np.nan)); e20=_finite(r.get('ema20',np.nan)); mh=_finite(r.get('macd_hist',np.nan))
        ret=_finite(r.get('ret1',np.nan)); imp=_finite(r.get('recent_impulse',np.nan)); rv=_finite(r.get('time_adjusted_rvol',r.get('robust_volume_ratio',np.nan))); bull=_finite(r.get('bullish_volume_evidence',np.nan))
        move=max(ret if np.isfinite(ret) else -9,imp if np.isfinite(imp) else -9)
        structure=bool(np.isfinite(c) and np.isfinite(vw) and c>vw and np.isfinite(e9) and np.isfinite(e20) and e9>e20 and np.isfinite(mh) and mh>0)
        participation=bool(np.isfinite(rv) and rv>=1.25 and np.isfinite(bull) and bull>=0.65)
        if structure and participation and np.isfinite(move) and move>=.025:
            return pos
    return None


def _forward_fixed_outcome_v622(session, pos, target_pct=.02, stop_pct=.015, max_bars=16):
    """Evaluate from a completed bar close using only subsequent bars."""
    try:
        pos=int(pos)
    except Exception:
        return None
    if session is None or not isinstance(session,pd.DataFrame) or len(session)<=pos+1:
        return None
    price=_finite(session.iloc[pos].get('Close',np.nan))
    if not np.isfinite(price) or price<=0:return None
    fut=session.iloc[pos+1:pos+1+int(max_bars)].copy()
    if fut.empty:return None
    tgt=price*(1+float(target_pct)); stp=price*(1-float(stop_pct)); outcome='OPEN'; bars_to=np.nan
    highs=pd.to_numeric(fut.get('High',fut['Close']),errors='coerce'); lows=pd.to_numeric(fut.get('Low',fut['Close']),errors='coerce')
    fmax=(float(highs.max())/price-1.0)*100.0 if highs.notna().any() else np.nan
    fmin=(float(lows.min())/price-1.0)*100.0 if lows.notna().any() else np.nan
    for j,(_,rr) in enumerate(fut.iterrows(),start=1):
        hi=_finite(rr.get('High',rr.get('Close',np.nan))); lo=_finite(rr.get('Low',rr.get('Close',np.nan)))
        ht=np.isfinite(hi) and hi>=tgt; hs=np.isfinite(lo) and lo<=stp
        if ht and hs: outcome='AMBIGUOUS';bars_to=j;break
        if ht: outcome='TARGET';bars_to=j;break
        if hs: outcome='STOP';bars_to=j;break
    return {'Outcome':outcome,'BarsToOutcome':bars_to,'ForwardMaxPct':fmax,'ForwardMinPct':fmin,
            'TargetPct':100*float(target_pct),'StopPct':100*float(stop_pct)}


def setup_origin_matched_baseline_v622(m15_feat, target_pct=.02, stop_pct=.015, max_bars=16):
    """Matched opening-time baseline for the research-only Setup Origin.

    For each of the first four regular-session 15m bar slots, compare actual
    Setup-Origin signals with the unconditional outcome of entering at the same
    completed bar on every eligible session. The final WEIGHTED row uses the
    observed signal-position mix, so a signal concentrated at 09:45 is not
    compared against a different time-of-day baseline.

    This is descriptive research only. It never changes production entry gates.
    """
    cols=['OpeningBarOrdinal','SignalN','SignalCleanN','SignalHits','SignalHitRatePct','SignalExpectancyPct',
          'BaselineN','BaselineCleanN','BaselineHits','BaselineHitRatePct','BaselineExpectancyPct','HitRateLiftX',
          'ExpectancyDeltaPct','SignalWeightPct','ResearchOnly']
    if m15_feat is None or not isinstance(m15_feat,pd.DataFrame) or m15_feat.empty:
        return pd.DataFrame(columns=cols)
    f=m15_feat.dropna(subset=['Close']).copy()
    try: dates=sorted(set(pd.Timestamp(x).date() for x in f.index))
    except Exception:return pd.DataFrame(columns=cols)
    sessions=[]
    for day in dates:
        try:s=f.loc[[pd.Timestamp(x).date()==day for x in f.index]].copy()
        except Exception:continue
        if len(s)>=5:sessions.append((day,s))
    if not sessions:return pd.DataFrame(columns=cols)
    sig_positions=[]
    for _,s in sessions:
        p=_opening_origin_signal_pos_v622(s)
        if p is not None:sig_positions.append(int(p))
    total_signals=len(sig_positions)
    rows=[]; pos_stats={}
    for pos in range(4):
        signal_out=[]; base_out=[]
        for _,s in sessions:
            if len(s)<=pos+1:continue
            o=_forward_fixed_outcome_v622(s,pos,target_pct,stop_pct,max_bars)
            if o is not None:base_out.append(o)
            if _opening_origin_signal_pos_v622(s)==pos and o is not None:signal_out.append(o)
        def stats(arr):
            clean=[x for x in arr if x['Outcome'] in ('TARGET','STOP')]
            hits=sum(1 for x in clean if x['Outcome']=='TARGET'); stops=sum(1 for x in clean if x['Outcome']=='STOP')
            hr=(100.0*hits/len(clean)) if clean else np.nan
            exp=((hits/len(clean))*(100*float(target_pct))-(stops/len(clean))*(100*float(stop_pct))) if clean else np.nan
            return len(arr),len(clean),hits,hr,exp
        sn,sc,sh,shr,se=stats(signal_out); bn,bc,bh,bhr,be=stats(base_out)
        lift=(shr/bhr) if np.isfinite(shr) and np.isfinite(bhr) and bhr>0 else np.nan
        delta=(se-be) if np.isfinite(se) and np.isfinite(be) else np.nan
        w=(100.0*sn/total_signals) if total_signals else 0.0
        pos_stats[pos]={'sn':sn,'sc':sc,'sh':sh,'shr':shr,'se':se,'bn':bn,'bc':bc,'bh':bh,'bhr':bhr,'be':be,'lift':lift,'delta':delta,'w':w}
        if sn or total_signals==0:
            rows.append({'OpeningBarOrdinal':pos+1,'SignalN':sn,'SignalCleanN':sc,'SignalHits':sh,'SignalHitRatePct':shr,'SignalExpectancyPct':se,
                         'BaselineN':bn,'BaselineCleanN':bc,'BaselineHits':bh,'BaselineHitRatePct':bhr,'BaselineExpectancyPct':be,'HitRateLiftX':lift,
                         'ExpectancyDeltaPct':delta,'SignalWeightPct':w,'ResearchOnly':True})
    if total_signals:
        sw=sum(v['sn'] for v in pos_stats.values())
        def weighted(key):
            vals=[(v['sn'],v[key]) for v in pos_stats.values() if v['sn']>0 and np.isfinite(v[key])]
            den=sum(w for w,_ in vals)
            return sum(w*x for w,x in vals)/den if den else np.nan
        sig_hr=weighted('shr'); sig_exp=weighted('se'); base_hr=weighted('bhr'); base_exp=weighted('be')
        lift=(sig_hr/base_hr) if np.isfinite(sig_hr) and np.isfinite(base_hr) and base_hr>0 else np.nan
        delta=(sig_exp-base_exp) if np.isfinite(sig_exp) and np.isfinite(base_exp) else np.nan
        rows.append({'OpeningBarOrdinal':'WEIGHTED','SignalN':sw,'SignalCleanN':sum(v['sc'] for v in pos_stats.values()),'SignalHits':sum(v['sh'] for v in pos_stats.values()),
                     'SignalHitRatePct':sig_hr,'SignalExpectancyPct':sig_exp,'BaselineN':sum(v['bn'] for v in pos_stats.values() if v['sn']>0),
                     'BaselineCleanN':sum(v['bc'] for v in pos_stats.values() if v['sn']>0),'BaselineHits':sum(v['bh'] for v in pos_stats.values() if v['sn']>0),
                     'BaselineHitRatePct':base_hr,'BaselineExpectancyPct':base_exp,'HitRateLiftX':lift,'ExpectancyDeltaPct':delta,'SignalWeightPct':100.0,'ResearchOnly':True})
    return pd.DataFrame(rows,columns=cols)




def setup_origin_session_pairs_v624(m15_feat, target_pct=.02, stop_pct=.015, max_bars=16):
    """Leave-one-session-out matched pairs for cross-stock Setup-Origin research.

    Each Setup-Origin session is compared with the historical outcome distribution
    from the *same ticker and same completed opening-bar slot*, excluding the
    signal session itself from the baseline.  This keeps the comparison tied to
    the stock's own opening volatility and avoids counting the signal session in
    its own matched baseline.  Research only; never a production gate.
    """
    cols=['SessionDate','OpeningBarOrdinal','SignalOutcome','SignalWin','SignalPayoffPct',
          'BaselineCleanNLOO','BaselineHitRatePctLOO','BaselineExpectancyPctLOO',
          'HitRateEdgePP','ExpectancyEdgePct','TargetPct','StopPct','HorizonBars','ResearchOnly']
    if m15_feat is None or not isinstance(m15_feat,pd.DataFrame) or m15_feat.empty:
        return pd.DataFrame(columns=cols)
    f=m15_feat.dropna(subset=['Close']).copy()
    try: dates=sorted(set(pd.Timestamp(x).date() for x in f.index))
    except Exception:return pd.DataFrame(columns=cols)
    sessions=[]
    for day in dates:
        try:sess=f.loc[[pd.Timestamp(x).date()==day for x in f.index]].copy()
        except Exception:continue
        if len(sess)>=5:sessions.append((str(day),sess))
    if not sessions:return pd.DataFrame(columns=cols)
    cache={}
    for pos in range(4):
        vals=[]
        for day,sess in sessions:
            o=_forward_fixed_outcome_v622(sess,pos,target_pct,stop_pct,max_bars)
            vals.append((day,o))
        cache[pos]=vals
    rows=[]
    for day,sess in sessions:
        pos=_opening_origin_signal_pos_v622(sess)
        if pos is None:continue
        sig=_forward_fixed_outcome_v622(sess,pos,target_pct,stop_pct,max_bars)
        if sig is None:continue
        clean_base=[]
        for other_day,o in cache.get(pos,[]):
            if other_day==day or o is None or o.get('Outcome') not in ('TARGET','STOP'):continue
            clean_base.append(o)
        hits=sum(1 for o in clean_base if o.get('Outcome')=='TARGET')
        bn=len(clean_base)
        bhr=100.0*hits/bn if bn else np.nan
        bexp=((hits/bn)*(100*float(target_pct))-((bn-hits)/bn)*(100*float(stop_pct))) if bn else np.nan
        sout=str(sig.get('Outcome','OPEN'))
        swin=1.0 if sout=='TARGET' else (0.0 if sout=='STOP' else np.nan)
        spay=(100*float(target_pct)) if sout=='TARGET' else ((-100*float(stop_pct)) if sout=='STOP' else np.nan)
        edge=(100.0*swin-bhr) if np.isfinite(swin) and np.isfinite(bhr) else np.nan
        eedge=(spay-bexp) if np.isfinite(spay) and np.isfinite(bexp) else np.nan
        rows.append({'SessionDate':day,'OpeningBarOrdinal':int(pos)+1,'SignalOutcome':sout,'SignalWin':swin,'SignalPayoffPct':spay,
                     'BaselineCleanNLOO':bn,'BaselineHitRatePctLOO':bhr,'BaselineExpectancyPctLOO':bexp,
                     'HitRateEdgePP':edge,'ExpectancyEdgePct':eedge,'TargetPct':100*float(target_pct),'StopPct':100*float(stop_pct),
                     'HorizonBars':int(max_bars),'ResearchOnly':True})
    return pd.DataFrame(rows,columns=cols)


def cluster_bootstrap_matched_edge_v624(pairs, n_boot=1200, seed=624):
    """Cluster bootstrap the matched Setup-Origin edge by calendar session date.

    Rows may contain many stocks from the same date. Resampling entire dates keeps
    cross-sectional co-movement together instead of pretending every stock-signal
    on a market-wide risk-on day is independent.  The baseline for each row is
    already leave-one-session-out within that ticker/slot.
    """
    cols=['Metric','Value']
    if pairs is None or not isinstance(pairs,pd.DataFrame) or pairs.empty:
        return pd.DataFrame([{'Metric':'Research state','Value':'NO SAMPLE'}],columns=cols)
    x=pairs.copy()
    x['SignalWin']=pd.to_numeric(x.get('SignalWin'),errors='coerce')
    x['BaselineHitRatePctLOO']=pd.to_numeric(x.get('BaselineHitRatePctLOO'),errors='coerce')
    x['SignalPayoffPct']=pd.to_numeric(x.get('SignalPayoffPct'),errors='coerce')
    x['BaselineExpectancyPctLOO']=pd.to_numeric(x.get('BaselineExpectancyPctLOO'),errors='coerce')
    clean=x[np.isfinite(x['SignalWin']) & np.isfinite(x['BaselineHitRatePctLOO'])].copy()
    if clean.empty:
        return pd.DataFrame([{'Metric':'Research state','Value':'NO CLEAN MATCHED SAMPLE'}],columns=cols)
    clean['edge_prob']=clean['SignalWin']-clean['BaselineHitRatePctLOO']/100.0
    clean['edge_exp']=clean['SignalPayoffPct']-clean['BaselineExpectancyPctLOO']
    obs=float(clean['edge_prob'].mean()); obs_exp=float(clean['edge_exp'].mean()) if clean['edge_exp'].notna().any() else np.nan
    sig_hr=100.0*float(clean['SignalWin'].mean()); base_hr=float(clean['BaselineHitRatePctLOO'].mean())
    dates=list(pd.Series(clean['SessionDate'].astype(str).unique()).dropna())
    boot=[]; boot_exp=[]
    if dates:
        rng=np.random.default_rng(int(seed)); grouped={d:clean[clean['SessionDate'].astype(str)==d] for d in dates}
        for _ in range(max(200,int(n_boot))):
            draw=rng.choice(dates,size=len(dates),replace=True)
            vals=[]; exps=[]
            for d in draw:
                g=grouped[str(d)]
                vals.extend(pd.to_numeric(g['edge_prob'],errors='coerce').dropna().tolist())
                exps.extend(pd.to_numeric(g['edge_exp'],errors='coerce').dropna().tolist())
            if vals:boot.append(float(np.mean(vals)))
            if exps:boot_exp.append(float(np.mean(exps)))
    lo=hi=pval=np.nan
    if boot:
        a=np.asarray(boot,dtype=float);lo=100*float(np.nanpercentile(a,2.5));hi=100*float(np.nanpercentile(a,97.5))
        ple=float(np.mean(a<=0));pge=float(np.mean(a>=0));pval=min(1.0,2.0*min(ple,pge))
    elo=ehi=np.nan
    if boot_exp:
        ae=np.asarray(boot_exp,dtype=float);elo=float(np.nanpercentile(ae,2.5));ehi=float(np.nanpercentile(ae,97.5))
    state=('POSITIVE BOOTSTRAP CI — RESEARCH ONLY' if len(clean)>=30 and np.isfinite(lo) and lo>0 else
           ('NEGATIVE BOOTSTRAP CI — RESEARCH ONLY' if len(clean)>=30 and np.isfinite(hi) and hi<0 else
            'INCONCLUSIVE — RESEARCH ONLY'))
    return pd.DataFrame([
        {'Metric':'Clean matched signal N','Value':int(len(clean))},
        {'Metric':'Unique clustered session dates','Value':int(len(dates))},
        {'Metric':'Stocks represented','Value':int(clean['Ticker'].nunique()) if 'Ticker' in clean else np.nan},
        {'Metric':'Signal hit rate %','Value':sig_hr},
        {'Metric':'Mean LOO matched baseline hit rate %','Value':base_hr},
        {'Metric':'Observed matched hit-rate edge pp','Value':100*obs},
        {'Metric':'Session-cluster bootstrap 95% low pp','Value':lo},
        {'Metric':'Session-cluster bootstrap 95% high pp','Value':hi},
        {'Metric':'Bootstrap two-sided p-value','Value':pval},
        {'Metric':'Observed expectancy edge % / signal','Value':obs_exp},
        {'Metric':'Expectancy edge bootstrap 95% low %','Value':elo},
        {'Metric':'Expectancy edge bootstrap 95% high %','Value':ehi},
        {'Metric':'Research state','Value':state},
        {'Metric':'Method note','Value':'Leave-one-session-out same-ticker/same-slot baseline; bootstrap clustered by calendar session date; research only'},
    ],columns=cols)


def setup_origin_matched_confidence_v623(matched_baseline):
    """Approximate uncertainty for the weighted matched opening baseline."""
    rows=[]
    try:
        w=matched_baseline[matched_baseline['OpeningBarOrdinal'].astype(str)=='WEIGHTED']
        if w.empty:raise ValueError('no weighted row')
        r=w.iloc[-1]
        n1=int(_finite(r.get('SignalCleanN',0),0)); n2=int(_finite(r.get('BaselineCleanN',0),0))
        p1=_finite(r.get('SignalHitRatePct',np.nan))/100.0; p2=_finite(r.get('BaselineHitRatePct',np.nan))/100.0
        h1=int(_finite(r.get('SignalHits',0),0))
        if not (n1>0 and n2>0 and np.isfinite(p1) and np.isfinite(p2)):raise ValueError('insufficient')
        delta=p1-p2
        se=math.sqrt(max(0.0,p1*(1-p1)/n1 + p2*(1-p2)/n2))
        lo=delta-1.96*se; hi=delta+1.96*se
        pooled=(h1+p2*n2)/(n1+n2)
        se0=math.sqrt(max(1e-12,pooled*(1-pooled)*(1/n1+1/n2)))
        z=delta/se0; pval=math.erfc(abs(z)/math.sqrt(2.0))
        state=('LOW SAMPLE — NO STATISTICAL EVIDENCE' if n1<30 or lo<=0 else
               ('POSITIVE DIFFERENCE — RESEARCH ONLY' if delta>0 else 'NO POSITIVE DIFFERENCE'))
        rows=[
            {'Metric':'Signal clean N','Value':n1},
            {'Metric':'Matched baseline effective clean N','Value':n2},
            {'Metric':'Signal hit rate %','Value':100*p1},
            {'Metric':'Matched baseline hit rate %','Value':100*p2},
            {'Metric':'Hit-rate delta percentage points','Value':100*delta},
            {'Metric':'Hit-rate delta approx 95% low pp','Value':100*lo},
            {'Metric':'Hit-rate delta approx 95% high pp','Value':100*hi},
            {'Metric':'Approx two-sided p-value','Value':pval},
            {'Metric':'Matched edge confidence','Value':state},
            {'Metric':'Method note','Value':'Approximate weighted two-proportion audit; research only, not a production gate'},
        ]
    except Exception:
        rows=[{'Metric':'Matched edge confidence','Value':'NO DATA'}]
    return pd.DataFrame(rows,columns=['Metric','Value'])


def research_evidence_summary_v622(origin_summary, matched_baseline, robustness, continuation_summary):
    """One-page evidence audit. Descriptive only; production impact is NONE."""
    rows=[]
    def metric(df,name,default=np.nan):
        try:
            m=dict(zip(df['Metric'].astype(str),df['Value']))
            return m.get(name,default)
        except Exception:return default
    origin_n=metric(origin_summary,'Clean outcomes',0); origin_hr=metric(origin_summary,'Clean target-before-stop hit rate %',np.nan); origin_exp=metric(origin_summary,'Fixed-payoff gross expectancy % / clean signal',np.nan)
    base_hr=base_exp=lift=delta=np.nan
    try:
        w=matched_baseline[matched_baseline['OpeningBarOrdinal'].astype(str)=='WEIGHTED']
        if not w.empty:
            rr=w.iloc[-1]; base_hr=_finite(rr.get('BaselineHitRatePct',np.nan)); base_exp=_finite(rr.get('BaselineExpectancyPct',np.nan)); lift=_finite(rr.get('HitRateLiftX',np.nan)); delta=_finite(rr.get('ExpectancyDeltaPct',np.nan))
    except Exception:pass
    robust_total=robust_pos=0; robust_min=robust_max=np.nan
    try:
        vals=pd.to_numeric(robustness['GrossExpectancyPct'],errors='coerce').dropna(); robust_total=len(vals); robust_pos=int((vals>0).sum())
        if len(vals):robust_min=float(vals.min());robust_max=float(vals.max())
    except Exception:pass
    cont_n=metric(continuation_summary,'Clean post-breakout outcomes',0); cont_hr=metric(continuation_summary,'Clean post-breakout hit rate %',np.nan); cont_hits=metric(continuation_summary,'Post-breakout target hits',0); cont_cens=metric(continuation_summary,'Right-censored after breakout',0)
    conf=setup_origin_matched_confidence_v623(matched_baseline)
    conf_delta=metric(conf,'Hit-rate delta percentage points',np.nan)
    conf_lo=metric(conf,'Hit-rate delta approx 95% low pp',np.nan)
    conf_hi=metric(conf,'Hit-rate delta approx 95% high pp',np.nan)
    conf_p=metric(conf,'Approx two-sided p-value',np.nan)
    conf_state=metric(conf,'Matched edge confidence','NO DATA')
    if float(origin_n or 0)<12:
        origin_state='LOW SAMPLE • RESEARCH ONLY'
    elif np.isfinite(lift) and lift<=1.0:
        origin_state='NO MATCHED HIT-RATE LIFT • RESEARCH ONLY'
    elif np.isfinite(delta) and delta<=0:
        origin_state='NO MATCHED EXPECTANCY LIFT • RESEARCH ONLY'
    else:
        origin_state='DEVELOPING MATCHED EDGE • RESEARCH ONLY'
    if float(cont_n or 0)<12:
        cont_state='LOW SAMPLE • RESEARCH ONLY'
    else:
        cont_state='RESEARCH SAMPLE • NOT A PRODUCTION GATE'
    if float(cont_hits or 0)==0 and float(cont_n or 0)>0:
        cont_state='NO CLEAN TARGET HITS YET • LOW SAMPLE • RESEARCH ONLY'
    rows.extend([
        {'Metric':'Setup Origin clean N','Value':origin_n},
        {'Metric':'Setup Origin hit rate %','Value':origin_hr},
        {'Metric':'Matched opening baseline hit rate %','Value':base_hr},
        {'Metric':'Setup Origin hit-rate lift vs matched baseline','Value':lift},
        {'Metric':'Setup Origin expectancy %','Value':origin_exp},
        {'Metric':'Matched baseline expectancy %','Value':base_exp},
        {'Metric':'Setup Origin expectancy delta vs baseline %','Value':delta},
        {'Metric':'Setup Origin hit-rate delta pp','Value':conf_delta},
        {'Metric':'Setup Origin hit-rate delta approx 95% CI pp','Value':f'{conf_lo:.2f} to {conf_hi:.2f}' if np.isfinite(conf_lo) and np.isfinite(conf_hi) else '—'},
        {'Metric':'Setup Origin matched-edge approx p-value','Value':conf_p},
        {'Metric':'Setup Origin matched-edge confidence','Value':conf_state},
        {'Metric':'Robustness scenarios positive expectancy','Value':f'{robust_pos}/{robust_total}' if robust_total else '0/0'},
        {'Metric':'Robustness expectancy range %','Value':f'{robust_min:.3f} to {robust_max:.3f}' if np.isfinite(robust_min) and np.isfinite(robust_max) else '—'},
        {'Metric':'Setup Origin evidence state','Value':origin_state},
        {'Metric':'Continuation clean N','Value':cont_n},
        {'Metric':'Continuation clean hit rate %','Value':cont_hr},
        {'Metric':'Continuation target hits','Value':cont_hits},
        {'Metric':'Continuation right-censored','Value':cont_cens},
        {'Metric':'Continuation evidence state','Value':cont_state},
        {'Metric':'Production impact','Value':'NONE — research-only evidence audit'},
    ])
    return pd.DataFrame(rows,columns=['Metric','Value'])


def continuation_base_validation_v620(m15_feat, breakout_lookahead=8, target_pct=.02, stop_pct=.015, outcome_bars=16):
    """Causal historical replay of the same-day Continuation Base Lab.

    For every regular session, build prefixes bar-by-bar and record the *first*
    moment the V6.1.9 continuation-base detector could have known a base existed.
    Then test whether the frozen breakout trigger is touched in the next
    breakout_lookahead bars.  If touched, evaluate +target before -stop only on
    bars AFTER the breakout bar, avoiding unknown intrabar ordering.

    Research only: no result here changes production entry/chase gates.
    """
    cols=['SessionDate','CandidateConfirmed','CandidateClose','BaseBars','BaseLow','BaseHigh','BaseRangePct','BaseRangeATR','BaseQuality','VolumeDryupRatio','SessionPeak','BreakoutTrigger','BreakoutReference','BarsToBreakout','BreakoutTouched','PostBreakoutOutcome','BarsToOutcome','ForwardMaxAfterBreakoutPct','ForwardMinAfterBreakoutPct']
    if m15_feat is None or not isinstance(m15_feat,pd.DataFrame) or m15_feat.empty:return pd.DataFrame(columns=cols)
    f=m15_feat.dropna(subset=['Close']).copy()
    try: dates=sorted(set(pd.Timestamp(x).date() for x in f.index))
    except Exception:return pd.DataFrame(columns=cols)
    session_map={}
    for day in dates:
        try: session_map[day]=f.loc[[pd.Timestamp(x).date()==day for x in f.index]].copy()
        except Exception: pass
    rows=[]
    for di,day in enumerate(dates):
        s=session_map.get(day)
        if s is None or len(s)<9:continue
        prev_close=np.nan
        if di>0:
            ps=session_map.get(dates[di-1])
            if ps is not None and len(ps): prev_close=_finite(ps.iloc[-1].get('Close',np.nan))
        if not np.isfinite(prev_close) or prev_close<=0:continue
        candidate=None; cand_pos=None
        # First causal prefix that qualifies; 8 bars minimum matches live detector.
        for end in range(8,len(s)+1):
            pref=s.iloc[:end].copy(); cp=_finite(pref.iloc[-1].get('Close',np.nan))
            c=_continuation_base_v619(pref,previous_close=prev_close,current_price=cp)
            if bool(c.get('continuation_base_candidate',False)):
                candidate=c; cand_pos=end-1; break
        if candidate is None:continue
        idx=s.index[cand_pos]; close=_finite(s.iloc[cand_pos].get('Close',np.nan)); trig=_finite(candidate.get('continuation_breakout_trigger',np.nan))
        fut=s.iloc[cand_pos+1:cand_pos+1+int(breakout_lookahead)].copy()
        bpos=None
        if np.isfinite(trig):
            for j,(_,rr) in enumerate(fut.iterrows(),start=1):
                hi=_finite(rr.get('High',rr.get('Close',np.nan)))
                if np.isfinite(hi) and hi>=trig: bpos=j; break
        touched=bpos is not None
        outcome='NO BREAKOUT'; bars_to=np.nan; fmax=np.nan; fmin=np.nan
        if touched:
            # Candidate position + bpos gives the breakout bar; start one bar later.
            start=cand_pos+1+bpos
            aft=s.iloc[start:start+int(outcome_bars)].copy()
            if not aft.empty and np.isfinite(trig) and trig>0:
                highs=pd.to_numeric(aft.get('High',aft['Close']),errors='coerce'); lows=pd.to_numeric(aft.get('Low',aft['Close']),errors='coerce')
                fmax=(float(highs.max())/trig-1.0)*100.0 if highs.notna().any() else np.nan
                fmin=(float(lows.min())/trig-1.0)*100.0 if lows.notna().any() else np.nan
                tgt=trig*(1+float(target_pct)); stp=trig*(1-float(stop_pct)); outcome='OPEN'
                for k,(_,rr) in enumerate(aft.iterrows(),start=1):
                    hi=_finite(rr.get('High',rr.get('Close',np.nan))); lo=_finite(rr.get('Low',rr.get('Close',np.nan)))
                    ht=np.isfinite(hi) and hi>=tgt; hs=np.isfinite(lo) and lo<=stp
                    if ht and hs: outcome='AMBIGUOUS'; bars_to=k; break
                    if ht: outcome='TARGET'; bars_to=k; break
                    if hs: outcome='STOP'; bars_to=k; break
        confirmed,_=_bar_confirmation_v616(idx,'15m')
        rows.append({'SessionDate':str(day),'CandidateConfirmed':str(confirmed),'CandidateClose':close,'BaseBars':candidate.get('continuation_base_bars',0),'BaseLow':candidate.get('continuation_base_low',np.nan),'BaseHigh':candidate.get('continuation_base_high',np.nan),'BaseRangePct':candidate.get('continuation_base_range_pct',np.nan),'BaseRangeATR':candidate.get('continuation_base_range_atr',np.nan),'BaseQuality':candidate.get('continuation_base_quality','NO DATA'),'VolumeDryupRatio':candidate.get('continuation_volume_dryup_ratio',np.nan),'SessionPeak':candidate.get('continuation_session_peak',np.nan),'BreakoutTrigger':trig,'BreakoutReference':candidate.get('continuation_breakout_reference','—'),'BarsToBreakout':bpos if touched else np.nan,'BreakoutTouched':bool(touched),'PostBreakoutOutcome':outcome,'BarsToOutcome':bars_to,'ForwardMaxAfterBreakoutPct':fmax,'ForwardMinAfterBreakoutPct':fmin})
    return pd.DataFrame(rows,columns=cols)


def continuation_base_validation_summary_v620(events):
    cols=['Metric','Value']
    if events is None or not isinstance(events,pd.DataFrame) or events.empty:
        return pd.DataFrame([{'Metric':'Continuation base candidates','Value':0},{'Metric':'Research sample state','Value':'NO SAMPLE'}],columns=cols)
    n=len(events); touched=events[events['BreakoutTouched']==True].copy() if 'BreakoutTouched' in events else events.iloc[0:0]
    clean=touched[touched['PostBreakoutOutcome'].isin(['TARGET','STOP'])].copy() if len(touched) else touched
    cn=len(clean); hits=int((clean['PostBreakoutOutcome']=='TARGET').sum()) if cn else 0; stops=int((clean['PostBreakoutOutcome']=='STOP').sum()) if cn else 0
    hr=100.0*hits/cn if cn else np.nan; lo,hi=_wilson_interval_v620(hits,cn)
    br=100.0*len(touched)/n if n else np.nan
    state='LOW SAMPLE — RESEARCH ONLY' if cn<12 else ('DEVELOPING SAMPLE — RESEARCH ONLY' if cn<30 else 'RESEARCH SAMPLE ≥30 — STILL NOT A PRODUCTION GATE')
    return pd.DataFrame([
        {'Metric':'Continuation base candidates','Value':int(n)},
        {'Metric':'Breakout touched candidates','Value':int(len(touched))},
        {'Metric':'Breakout touch rate %','Value':br},
        {'Metric':'Clean post-breakout outcomes','Value':int(cn)},
        {'Metric':'Post-breakout target hits','Value':hits},
        {'Metric':'Post-breakout stops','Value':stops},
        {'Metric':'Clean post-breakout hit rate %','Value':hr},
        {'Metric':'Hit-rate Wilson 95% low %','Value':lo},
        {'Metric':'Hit-rate Wilson 95% high %','Value':hi},
        {'Metric':'Research sample state','Value':state},
    ],columns=cols)


def continuation_base_validation_v621(m15_feat, breakout_lookahead=8, target_pct=.02, stop_pct=.015, outcome_bars=16):
    """Causal continuation replay with right-censoring and breakout-bar ambiguity.

    A touched breakout with insufficient bars is RIGHT-CENSORED, never mislabeled
    NO BREAKOUT. If target/stop is touched on the same 15m breakout bar as the
    trigger, ordering is unknown and the case is AMBIGUOUS_BREAKOUT_BAR.
    """
    cols=['SessionDate','CandidateConfirmed','CandidateClose','BaseBars','BaseLow','BaseHigh','BaseRangePct','BaseRangeATR','BaseQuality','VolumeDryupRatio','SessionPeak','BreakoutTrigger','BreakoutReference','BarsToBreakout','BreakoutTouched','BreakoutBarTargetTouch','BreakoutBarStopTouch','BarsAvailableAfterBreakout','OutcomeWindowComplete','PostBreakoutOutcome','BarsToOutcome','ForwardMaxAfterBreakoutPct','ForwardMinAfterBreakoutPct']
    if m15_feat is None or not isinstance(m15_feat,pd.DataFrame) or m15_feat.empty:return pd.DataFrame(columns=cols)
    f=m15_feat.dropna(subset=['Close']).copy()
    try: dates=sorted(set(pd.Timestamp(x).date() for x in f.index))
    except Exception:return pd.DataFrame(columns=cols)
    session_map={}
    for day in dates:
        try: session_map[day]=f.loc[[pd.Timestamp(x).date()==day for x in f.index]].copy()
        except Exception: pass
    rows=[]
    for di,day in enumerate(dates):
        sday=session_map.get(day)
        if sday is None or len(sday)<9:continue
        prev_close=np.nan
        if di>0:
            ps=session_map.get(dates[di-1])
            if ps is not None and len(ps): prev_close=_finite(ps.iloc[-1].get('Close',np.nan))
        if not np.isfinite(prev_close) or prev_close<=0:continue
        candidate=None; cand_pos=None
        for end in range(8,len(sday)+1):
            pref=sday.iloc[:end].copy(); cp=_finite(pref.iloc[-1].get('Close',np.nan))
            c=_continuation_base_v619(pref,previous_close=prev_close,current_price=cp)
            if bool(c.get('continuation_base_candidate',False)):
                candidate=c; cand_pos=end-1; break
        if candidate is None:continue
        idx=sday.index[cand_pos]; close=_finite(sday.iloc[cand_pos].get('Close',np.nan)); trig=_finite(candidate.get('continuation_breakout_trigger',np.nan))
        fut=sday.iloc[cand_pos+1:cand_pos+1+int(breakout_lookahead)].copy()
        bpos=None; breakout_row=None
        if np.isfinite(trig):
            for j,(_,rr) in enumerate(fut.iterrows(),start=1):
                hi=_finite(rr.get('High',rr.get('Close',np.nan)))
                if np.isfinite(hi) and hi>=trig: bpos=j; breakout_row=rr; break
        touched=bpos is not None
        outcome='NO BREAKOUT'; bars_to=np.nan; fmax=np.nan; fmin=np.nan
        btar=False; bstop=False; bars_available=0; window_complete=False
        if touched:
            tgt=trig*(1+float(target_pct)); stp=trig*(1-float(stop_pct))
            bhi=_finite(breakout_row.get('High',breakout_row.get('Close',np.nan))) if breakout_row is not None else np.nan
            blo=_finite(breakout_row.get('Low',breakout_row.get('Close',np.nan))) if breakout_row is not None else np.nan
            btar=bool(np.isfinite(bhi) and bhi>=tgt); bstop=bool(np.isfinite(blo) and blo<=stp)
            start=cand_pos+1+bpos
            aft=sday.iloc[start:start+int(outcome_bars)].copy()
            bars_available=int(len(aft)); window_complete=bars_available>=int(outcome_bars)
            if not aft.empty and np.isfinite(trig) and trig>0:
                highs=pd.to_numeric(aft.get('High',aft['Close']),errors='coerce'); lows=pd.to_numeric(aft.get('Low',aft['Close']),errors='coerce')
                fmax=(float(highs.max())/trig-1.0)*100.0 if highs.notna().any() else np.nan
                fmin=(float(lows.min())/trig-1.0)*100.0 if lows.notna().any() else np.nan
            if btar or bstop:
                outcome='AMBIGUOUS_BREAKOUT_BAR'; bars_to=0
            else:
                outcome='OPEN' if window_complete else 'RIGHT-CENSORED'
                for k,(_,rr) in enumerate(aft.iterrows(),start=1):
                    hi=_finite(rr.get('High',rr.get('Close',np.nan))); lo=_finite(rr.get('Low',rr.get('Close',np.nan)))
                    ht=np.isfinite(hi) and hi>=tgt; hs=np.isfinite(lo) and lo<=stp
                    if ht and hs: outcome='AMBIGUOUS'; bars_to=k; break
                    if ht: outcome='TARGET'; bars_to=k; break
                    if hs: outcome='STOP'; bars_to=k; break
        confirmed,_=_bar_confirmation_v616(idx,'15m')
        rows.append({'SessionDate':str(day),'CandidateConfirmed':str(confirmed),'CandidateClose':close,'BaseBars':candidate.get('continuation_base_bars',0),'BaseLow':candidate.get('continuation_base_low',np.nan),'BaseHigh':candidate.get('continuation_base_high',np.nan),'BaseRangePct':candidate.get('continuation_base_range_pct',np.nan),'BaseRangeATR':candidate.get('continuation_base_range_atr',np.nan),'BaseQuality':candidate.get('continuation_base_quality','NO DATA'),'VolumeDryupRatio':candidate.get('continuation_volume_dryup_ratio',np.nan),'SessionPeak':candidate.get('continuation_session_peak',np.nan),'BreakoutTrigger':trig,'BreakoutReference':candidate.get('continuation_breakout_reference','—'),'BarsToBreakout':bpos if touched else np.nan,'BreakoutTouched':bool(touched),'BreakoutBarTargetTouch':btar,'BreakoutBarStopTouch':bstop,'BarsAvailableAfterBreakout':bars_available,'OutcomeWindowComplete':bool(window_complete),'PostBreakoutOutcome':outcome,'BarsToOutcome':bars_to,'ForwardMaxAfterBreakoutPct':fmax,'ForwardMinAfterBreakoutPct':fmin})
    return pd.DataFrame(rows,columns=cols)


def continuation_base_validation_summary_v621(events):
    cols=['Metric','Value']
    if events is None or not isinstance(events,pd.DataFrame) or events.empty:
        return pd.DataFrame([{'Metric':'Continuation base candidates','Value':0},{'Metric':'Research sample state','Value':'NO SAMPLE'}],columns=cols)
    n=len(events); touched=events[events['BreakoutTouched']==True].copy() if 'BreakoutTouched' in events else events.iloc[0:0]
    clean=touched[touched['PostBreakoutOutcome'].isin(['TARGET','STOP'])].copy() if len(touched) else touched
    cn=len(clean); hits=int((clean['PostBreakoutOutcome']=='TARGET').sum()) if cn else 0; stops=int((clean['PostBreakoutOutcome']=='STOP').sum()) if cn else 0
    hr=100.0*hits/cn if cn else np.nan; lo,hi=_wilson_interval_v620(hits,cn)
    br=100.0*len(touched)/n if n else np.nan
    amb=int(touched['PostBreakoutOutcome'].isin(['AMBIGUOUS','AMBIGUOUS_BREAKOUT_BAR']).sum()) if len(touched) else 0
    cens=int((touched['PostBreakoutOutcome']=='RIGHT-CENSORED').sum()) if len(touched) else 0
    opened=int((touched['PostBreakoutOutcome']=='OPEN').sum()) if len(touched) else 0
    state='LOW SAMPLE — RESEARCH ONLY' if cn<12 else ('DEVELOPING SAMPLE — RESEARCH ONLY' if cn<30 else 'RESEARCH SAMPLE ≥30 — STILL NOT A PRODUCTION GATE')
    return pd.DataFrame([
        {'Metric':'Continuation base candidates','Value':int(n)},
        {'Metric':'Breakout touched candidates','Value':int(len(touched))},
        {'Metric':'Breakout touch rate %','Value':br},
        {'Metric':'Clean post-breakout outcomes','Value':int(cn)},
        {'Metric':'Post-breakout target hits','Value':hits},
        {'Metric':'Post-breakout stops','Value':stops},
        {'Metric':'Ambiguous breakout/intrabar cases','Value':amb},
        {'Metric':'Right-censored after breakout','Value':cens},
        {'Metric':'Open full-horizon outcomes','Value':opened},
        {'Metric':'Clean post-breakout hit rate %','Value':hr},
        {'Metric':'Hit-rate Wilson 95% low %','Value':lo},
        {'Metric':'Hit-rate Wilson 95% high %','Value':hi},
        {'Metric':'Research sample state','Value':state},
    ],columns=cols)

def _transition_candidates_v614(frame, bars, timeframe):
    """Return bullish transition candidates from a causal recent window.

    V6.1.4 keeps *all* transitions in the active window so anchor selection can
    distinguish the first signal of the current intraday setup from a later
    same-day re-confirmation. This avoids a daily midnight timestamp silently
    beating a more precise 15m/1H trigger.
    """
    if frame is None or not isinstance(frame,pd.DataFrame) or frame.empty:
        return []
    f=frame.dropna(subset=['Close']).tail(max(2,int(bars))).copy()
    if f.empty:return []
    cols=[('EMA9/20 cross','ema9_cross_up'),('MACD cross','macd_cross_up'),('MACD histogram turn','macd_hist_turn_pos'),('VWAP reclaim','vwap_cross_up')]
    out=[]
    n=len(f)
    for pos,(idx,row) in enumerate(f.iterrows()):
        labels=[]
        for label,col in cols:
            try:
                if _finite(row.get(col,0),0)>0:labels.append(label)
            except Exception:pass
        if not labels:continue
        px=_finite(row.get('Close',np.nan))
        if not np.isfinite(px) or px<=0:continue
        ts=_ts_utc_v614(idx); confirmed,confirm_sort=_bar_confirmation_v616(idx,timeframe)
        try:local_date=pd.Timestamp(idx).date()
        except Exception:local_date=None
        out.append({
            'price':float(px),'timestamp':str(idx),'bar_start_time':str(idx),'confirmed_time':str(confirmed),'ts_sort':ts,'confirm_sort':confirm_sort,'date':local_date,
            'timeframe':timeframe,'signals':labels,'vwap':_finite(row.get('vwap',np.nan)),
            'ema9':_finite(row.get('ema9',np.nan)),'ema20':_finite(row.get('ema20',np.nan)),
            'atr14':_finite(row.get('atr14',np.nan)),'age_bars':int(n-1-pos),
            '_pos':int(pos),'_frame':f,
        })
    return out


def _last_intraday_reset_pos_v614(frame):
    """Find the most recent bearish reset inside the latest intraday session.

    A reset starts a new setup episode. Earlier bullish crosses from the same
    session are ignored after a meaningful EMA20/MACD breakdown, preventing a
    stale morning signal from anchoring an afternoon re-entry attempt.
    """
    if frame is None or not isinstance(frame,pd.DataFrame) or frame.empty:return -1
    f=frame.dropna(subset=['Close']).copy()
    if f.empty:return -1
    try:
        latest_date=pd.Timestamp(f.index[-1]).date()
        mask=np.array([pd.Timestamp(x).date()==latest_date for x in f.index],dtype=bool)
        s=f.loc[mask]
    except Exception:
        s=f
    last=-1
    for j,(_,r) in enumerate(s.iterrows()):
        c=_finite(r.get('Close',np.nan)); e9=_finite(r.get('ema9',np.nan)); e20=_finite(r.get('ema20',np.nan)); mh=_finite(r.get('macd_hist',np.nan)); a=_finite(r.get('atr14',np.nan))
        hard=bool(np.isfinite(c) and np.isfinite(e20) and np.isfinite(a) and a>0 and c<e20-.25*a)
        structural=bool(np.isfinite(e9) and np.isfinite(e20) and e9<e20 and np.isfinite(mh) and mh<0)
        if hard or structural:last=j
    return last


def _intraday_setup_anchor_v614(frame,bars,timeframe):
    if frame is None or not isinstance(frame,pd.DataFrame) or frame.empty:return None
    base=frame.dropna(subset=['Close']).tail(max(2,int(bars))).copy()
    if base.empty:return None
    cands=_transition_candidates_v614(base,len(base),timeframe)
    if not cands:return None
    try:latest_date=pd.Timestamp(base.index[-1]).date()
    except Exception:latest_date=None
    today=[c for c in cands if c.get('date')==latest_date]
    if today:
        # Translate the latest-session reset position into the tail frame and keep
        # only transitions after that reset. If none survive, use all today's
        # candidates and mark lower quality rather than inventing an anchor.
        try:
            session=base.loc[[pd.Timestamp(x).date()==latest_date for x in base.index]]
            reset=_last_intraday_reset_pos_v614(base)
            posmap={idx:i for i,idx in enumerate(session.index)}
            after=[c for c in today if posmap.get(next((ix for ix in session.index if str(ix)==c.get('bar_start_time',c.get('timestamp'))),None),-1)>reset]
        except Exception:
            after=today
        usable=after or today
        # Earliest bullish transition in the active setup episode is the original
        # execution trigger; later reclaims are confirmations, not a new clock.
        chosen=min(usable,key=lambda x:x.get('confirm_sort',x.get('ts_sort',pd.Timestamp.max.tz_localize('UTC'))))
        chosen=dict(chosen);chosen['current_session']=True
        chosen['quality']='HIGH' if timeframe=='15m' else 'MEDIUM'
        chosen['selection']='CURRENT SESSION • EARLIEST AFTER RESET'
        return chosen
    # No transition in the latest session: keep the most recent prior intraday
    # transition as a fallback, rather than the oldest item in an arbitrary window.
    chosen=max(cands,key=lambda x:x.get('confirm_sort',x.get('ts_sort',pd.Timestamp.min.tz_localize('UTC'))))
    chosen=dict(chosen);chosen['current_session']=False
    chosen['quality']='MEDIUM' if timeframe=='15m' else 'LOW'
    chosen['selection']='RECENT PRIOR INTRADAY FALLBACK'
    return chosen


def _original_trigger_anchor_v614(daily, hourly=None, m15=None):
    """Session-aware original trigger selection.

    Priority is current-session intraday evidence (15m/1H), then a recent
    intraday fallback, then daily. A same-day daily transition can no longer win
    just because its timestamp is midnight.
    """
    intraday=[]
    for frame,bars,tf in ((m15,40,'15m'),(hourly,12,'1H')):
        x=_intraday_setup_anchor_v614(frame,bars,tf)
        if x:intraday.append(x)
    current=[x for x in intraday if x.get('current_session')]
    if current:
        chosen=min(current,key=lambda x:x.get('confirm_sort',x.get('ts_sort',pd.Timestamp.max.tz_localize('UTC'))))
        # Prefer 15m when timestamps are effectively the same.
        if len(current)>1:
            t0=chosen.get('confirm_sort',chosen.get('ts_sort'))
            close15=[x for x in current if x.get('timeframe')=='15m' and pd.notna(x.get('confirm_sort',x.get('ts_sort'))) and pd.notna(t0) and abs((x.get('confirm_sort',x.get('ts_sort'))-t0).total_seconds())<=3600]
            if close15:chosen=min(close15,key=lambda x:x.get('confirm_sort',x.get('ts_sort')))
        return {k:v for k,v in chosen.items() if not str(k).startswith('_')}
    if intraday:
        chosen=max(intraday,key=lambda x:x.get('confirm_sort',x.get('ts_sort',pd.Timestamp.min.tz_localize('UTC'))))
        return {k:v for k,v in chosen.items() if not str(k).startswith('_')}
    dc=_transition_candidates_v614(daily,5,'1D')
    if dc:
        chosen=max(dc,key=lambda x:x.get('ts_sort',pd.Timestamp.min.tz_localize('UTC')))
        chosen=dict(chosen);chosen['current_session']=False;chosen['quality']='LOW';chosen['selection']='DAILY FALLBACK — INTRADAY TRIGGER UNAVAILABLE'
        return {k:v for k,v in chosen.items() if not str(k).startswith('_')}
    return None


def _volume_trend_v614(hourly=None,m15=None):
    """Multi-timeframe participation trend.

    Time-adjusted RVOL is primary. Raw vol_accel may confirm a rise but can no
    longer override normalized RVOL by itself (important around closing auctions).
    """
    def one(frame,tf):
        if frame is None or not isinstance(frame,pd.DataFrame) or frame.empty:return None
        q=frame.dropna(subset=['Close']).tail(5)
        if len(q)<2:return None
        col='time_adjusted_rvol' if 'time_adjusted_rvol' in q else ('robust_volume_ratio' if 'robust_volume_ratio' in q else ('volume_ratio' if 'volume_ratio' in q else None))
        latest=_finite(q.iloc[-1].get(col,np.nan)) if col else np.nan
        prev=pd.to_numeric(q.iloc[:-1][col],errors='coerce').dropna() if col else pd.Series(dtype=float)
        base=float(prev.tail(3).median()) if len(prev) else np.nan
        va=_finite(q.iloc[-1].get('vol_accel',np.nan))
        ratio=(latest/base) if np.isfinite(latest) and np.isfinite(base) and base>0 else np.nan
        if np.isfinite(ratio):
            if ratio>=1.08: lab='ACCELERATING'
            elif ratio<=0.82: lab='FADING'
            elif ratio>=1.00 and np.isfinite(va) and va>=1.20: lab='ACCELERATING'
            elif ratio<=0.95 and np.isfinite(va) and va<0.80: lab='FADING'
            else: lab='STABLE'
        elif np.isfinite(va):
            lab='ACCELERATING' if va>=1.20 else ('FADING' if va<0.80 else 'STABLE')
        else: lab='NO DATA'
        return {'label':lab,'timeframe':tf,'latest_rvol':latest,'prior_rvol':base,'ratio':ratio,'vol_accel':va}
    s15=one(m15,'15m'); s1=one(hourly,'1H')
    valid=[x for x in (s15,s1) if x and x.get('label')!='NO DATA']
    if not valid:return {'label':'NO DATA','timeframe':'—','latest_rvol':np.nan,'prior_rvol':np.nan,'ratio':np.nan,'label_15m':'NO DATA','label_1h':'NO DATA'}
    l15=(s15 or {}).get('label','NO DATA'); l1=(s1 or {}).get('label','NO DATA')
    if l15!='NO DATA' and l1!='NO DATA' and l15!=l1:
        lab='MIXED'
    else:
        lab=l15 if l15!='NO DATA' else l1
    primary=s15 if s15 and s15.get('label')!='NO DATA' else s1
    return {**primary,'label':lab,'timeframe':'15m+1H' if l15!='NO DATA' and l1!='NO DATA' else primary.get('timeframe','—'),'label_15m':l15,'label_1h':l1}


def _session_move_percentile_v614(f,session_ret):
    if f is None or not isinstance(f,pd.DataFrame) or not np.isfinite(session_ret) or session_ret<=0 or 'ret1' not in f:return np.nan,0
    hist=pd.to_numeric(f['ret1'],errors='coerce').dropna()
    if len(hist)>1:hist=hist.iloc[:-1]
    hist=hist[(hist>0) & np.isfinite(hist)].tail(80)
    if len(hist)<15:return np.nan,int(len(hist))
    return float(100.0*np.mean(hist.to_numpy(float)<=float(session_ret))),int(len(hist))


def _pre_breakout_accumulation_v63956(feat):
    """Selective causal pre-move accumulation detector.

    V6.3.9.56 separates broad/raw accumulation evidence from a much rarer
    HIGH-CONFIDENCE PRE-MOVE state.  A giant volume ratio alone is never enough:
    confirmation must come from independent families (absorption/recovery,
    persistence, price structure and flow+momentum) and a minimum baseline/liquidity
    guard.  The detector remains research/radar only and never bypasses trade gates.
    """
    out={
        'score':0.0,'raw_score':0.0,'stage':'NO CURRENT ACCUMULATION SETUP','reason':'No pre-move accumulation evidence',
        'confirmed_pre_move':False,'confidence_tier':'NONE','family_count':0,'family_signature':'NONE',
        'baseline_guard_ok':False,'baseline_volume':np.nan,'baseline_turnover':np.nan,
        'volume_regime_ratio':np.nan,'volume_shock_ratio':np.nan,'effective_shock_ratio':np.nan,'volume_shock_date':'—',
        'volume_shock_return_pct':np.nan,'volume_shock_close_location':np.nan,
        'absorption_candidate':False,'shock_recovery_ok':False,'volume_persistence_ratio':np.nan,'price_retention_pct':np.nan,
        'higher_low_count':0,'flow_confirmation':False,'momentum_confirmation':False,
        'recent_price_move_pct':np.nan,'regime_shift':False,
    }
    if feat is None or not isinstance(feat,pd.DataFrame) or feat.empty:return out
    q=feat.dropna(subset=['Close','Volume']).copy().tail(40)
    if len(q)<15:return out
    vol=pd.to_numeric(q['Volume'],errors='coerce')
    close=pd.to_numeric(q['Close'],errors='coerce')
    high=pd.to_numeric(q.get('High'),errors='coerce')
    low=pd.to_numeric(q.get('Low'),errors='coerce')
    ret=pd.to_numeric(q.get('ret1'),errors='coerce') if 'ret1' in q else close.pct_change()
    # Robust baseline deliberately excludes newest five bars so the developing
    # regime does not inflate its own denominator.
    hist_vol=vol.iloc[:-5].tail(25)
    hist_close=close.iloc[:-5].tail(25)
    base=float(hist_vol.median()) if len(hist_vol) else np.nan
    base_px=float(hist_close.median()) if len(hist_close) else np.nan
    baseline_turnover=base*base_px if np.isfinite(base) and np.isfinite(base_px) else np.nan
    # A tiny denominator can turn ordinary volume into 100x/500x noise.  The
    # turnover threshold is intentionally modest and in local quote currency;
    # it is a denominator-quality guard, not a trade-liquidity recommendation.
    baseline_guard=bool(np.isfinite(base) and base>=5_000 and np.isfinite(baseline_turnover) and baseline_turnover>=100_000)
    if not np.isfinite(base) or base<=0:return out
    recent5=vol.tail(5)
    regime=float(recent5.median()/base) if len(recent5) else np.nan
    look=q.tail(8); ratios=pd.to_numeric(look['Volume'],errors='coerce')/base
    if ratios.dropna().empty:return out
    shock_label=ratios.idxmax();shock_ratio=float(ratios.loc[shock_label])
    # Cap the ratio's influence.  544x is not treated as 54x stronger than 10x.
    effective_shock=float(min(max(shock_ratio,0.0),25.0))
    try:shock_pos=q.index.get_loc(shock_label)
    except Exception:shock_pos=len(q)-1
    shock_row=q.loc[shock_label]
    shock_ret=float(ret.loc[shock_label])*100.0 if shock_label in ret.index and np.isfinite(ret.loc[shock_label]) else np.nan
    sh=float(shock_row.get('High',np.nan));sl=float(shock_row.get('Low',np.nan));sc=float(shock_row.get('Close',np.nan))
    close_loc=(sc-sl)/(sh-sl) if np.isfinite(sh) and np.isfinite(sl) and sh>sl else np.nan
    absorption=bool(baseline_guard and effective_shock>=3.0 and np.isfinite(shock_ret) and abs(shock_ret)<=3.5 and (not np.isfinite(close_loc) or close_loc>=0.45))
    after=q.iloc[shock_pos:] if shock_pos < len(q) else q.tail(1)
    persist=float(pd.to_numeric(after['Volume'],errors='coerce').median()/base) if len(after) else np.nan
    retention=(float(close.iloc[-1])/sc-1.0)*100.0 if np.isfinite(sc) and sc>0 and np.isfinite(close.iloc[-1]) else np.nan
    lows=pd.to_numeric(q.tail(6).get('Low'),errors='coerce').dropna()
    higher_lows=int((lows.diff().dropna()>0).sum()) if len(lows)>=2 else 0
    recent_move=(float(close.iloc[-1])/float(close.iloc[-6])-1.0)*100.0 if len(close)>=6 and np.isfinite(close.iloc[-6]) and close.iloc[-6]>0 else np.nan
    pre_shock=float(close.iloc[shock_pos-1]) if shock_pos>0 and np.isfinite(close.iloc[shock_pos-1]) else np.nan
    recovery=bool(np.isfinite(shock_ret) and shock_ret<=-5.0 and np.isfinite(retention) and retention>=5.0 and higher_lows>=2 and (not np.isfinite(pre_shock) or float(close.iloc[-1])>=0.98*pre_shock))
    last=q.iloc[-1]
    cmf=_finite(last.get('cmf20',np.nan)); obv=_finite(last.get('obv_slope5',np.nan)); ad=_finite(last.get('ad_slope5',np.nan))
    flow_votes=sum([bool(np.isfinite(cmf) and cmf>=0.05),bool(np.isfinite(obv) and obv>0),bool(np.isfinite(ad) and ad>0)])
    flow_ok=bool(flow_votes>=2 or (np.isfinite(cmf) and cmf>=0.12))
    e20=_finite(last.get('ema20',np.nan)); mh=_finite(last.get('macd_hist',np.nan)); ms=_finite(last.get('macd_hist_slope',np.nan)); rs=_finite(last.get('rsi14',np.nan)); fresh=_finite(last.get('fresh_transition_count',0),0)
    price_now=_finite(last.get('Close',np.nan))
    momentum_ok=bool(np.isfinite(price_now) and np.isfinite(e20) and price_now>=e20 and 47<=rs<=78 and ((np.isfinite(mh) and mh>=0 and np.isfinite(ms) and ms>=0) or fresh>=1))
    volume_family=bool(baseline_guard and effective_shock>=3.0)
    absorption_family=bool(absorption or recovery or (baseline_guard and effective_shock>=3 and np.isfinite(retention) and retention>=-1.0 and (not np.isfinite(close_loc) or close_loc>=0.55) and (not np.isfinite(shock_ret) or shock_ret>-6.0)))
    persistence_family=bool(np.isfinite(regime) and regime>=1.4 and np.isfinite(persist) and persist>=1.4)
    structure_family=bool((higher_lows>=2 and np.isfinite(retention) and retention>=-2.0) or (np.isfinite(price_now) and np.isfinite(e20) and price_now>=e20 and np.isfinite(retention) and retention>=0))
    flow_momentum_family=bool(flow_ok and momentum_ok)
    families={'VOLUME':volume_family,'ABSORB/RECOVER':absorption_family,'PERSISTENCE':persistence_family,'STRUCTURE':structure_family,'FLOW+MOMENTUM':flow_momentum_family}
    family_count=sum(int(v) for v in families.values());signature=' + '.join(k for k,v in families.items() if v) or 'NONE'
    raw=0.0;why=[]
    if effective_shock>=10:raw+=28;why.append(f'volume shock {shock_ratio:.1f}x (capped {effective_shock:.1f}x)')
    elif effective_shock>=5:raw+=24;why.append(f'volume shock {shock_ratio:.1f}x')
    elif effective_shock>=3:raw+=20;why.append(f'volume shock {shock_ratio:.1f}x')
    elif effective_shock>=2:raw+=10;why.append(f'volume shock {shock_ratio:.1f}x')
    if absorption:raw+=20;why.append(f'absorption {shock_ret:+.1f}% on shock day')
    elif recovery:raw+=18;why.append('large down-volume shock recovered with higher lows')
    if persistence_family:raw+=14;why.append(f'persistent volume regime {regime:.1f}x/{persist:.1f}x')
    elif np.isfinite(regime) and regime>=1.4:raw+=7;why.append(f'volume regime {regime:.1f}x')
    if structure_family:raw+=12;why.append(f'price structure/retention confirmed ({retention:+.1f}%)')
    if flow_ok:raw+=10;why.append('multi-source accumulation flow')
    if momentum_ok:raw+=10;why.append('daily momentum confirmation')
    if not baseline_guard:raw-=20;why.append('baseline/liquidity guard failed')
    if np.isfinite(shock_ret) and shock_ret<=-8 and not recovery:raw-=28;why.append(f'unrecovered shock-day loss {shock_ret:+.1f}%')
    elif np.isfinite(shock_ret) and shock_ret<=-5 and not recovery:raw-=16;why.append(f'negative shock-day move {shock_ret:+.1f}% needs recovery')
    score=float(np.clip(raw,0,100))
    if np.isfinite(recent_move) and recent_move>=10:score=max(0.0,score-30)
    elif np.isfinite(recent_move) and recent_move>=7:score=max(0.0,score-18)
    elif np.isfinite(recent_move) and recent_move>=5:score=max(0.0,score-8)
    regime_shift=bool(volume_family or (baseline_guard and np.isfinite(regime) and regime>=1.8))
    still_early=bool(not np.isfinite(recent_move) or recent_move<8.0)
    # High confidence is deliberately demanding: all four core independent
    # families must agree. Persistence is helpful but optional because the best
    # shock-day signals can be visible before several follow-through sessions exist.
    confirmed=bool(still_early and score>=68 and volume_family and absorption_family and structure_family and flow_momentum_family and family_count>=4)
    watch=bool(still_early and baseline_guard and score>=58 and family_count>=3 and volume_family and (absorption_family or structure_family))
    if confirmed:
        stage='HIGH-CONFIDENCE PRE-MOVE';tier='HIGH'
    elif watch:
        stage='PRE-MOVE WATCH';tier='WATCH'
    elif score>=48 and regime_shift and still_early:
        stage='RAW ACCUMULATION';tier='RAW'
    elif score>=55 and regime_shift:
        stage='ACCUMULATION PERSISTS • MOVE ALREADY EXTENDED';tier='EXTENDED'
    else:
        stage='NO CURRENT ACCUMULATION SETUP';tier='NONE'
    out.update({
        'score':round(score,1),'raw_score':round(float(np.clip(raw,0,100)),1),'stage':stage,'reason':' • '.join(why[:8]) if why else out['reason'],
        'confirmed_pre_move':confirmed,'confidence_tier':tier,'family_count':family_count,'family_signature':signature,
        'baseline_guard_ok':baseline_guard,'baseline_volume':base,'baseline_turnover':baseline_turnover,
        'volume_regime_ratio':regime,'volume_shock_ratio':shock_ratio,'effective_shock_ratio':effective_shock,'volume_shock_date':str(pd.Timestamp(shock_label).date()),
        'volume_shock_return_pct':shock_ret,'volume_shock_close_location':close_loc,
        'absorption_candidate':absorption,'shock_recovery_ok':recovery,'volume_persistence_ratio':persist,'price_retention_pct':retention,
        'higher_low_count':higher_lows,'flow_confirmation':flow_ok,'momentum_confirmation':momentum_ok,
        'recent_price_move_pct':recent_move,'regime_shift':regime_shift,
    })
    return out

# Backward-compatible alias for older app code during rolling upgrades.
_pre_breakout_accumulation_v63955 = _pre_breakout_accumulation_v63956

def _latest_intraday_supports_v614(hourly=None,m15=None):
    vals=[]
    for frame,tf in ((m15,'15m'),(hourly,'1H')):
        if frame is None or not isinstance(frame,pd.DataFrame) or frame.empty:continue
        q=frame.dropna(subset=['Close'])
        if q.empty:continue
        r=q.iloc[-1]
        for label,col in [('VWAP','vwap'),('EMA9','ema9'),('EMA20','ema20')]:
            x=_finite(r.get(col,np.nan))
            if np.isfinite(x) and x>0:vals.append((float(x),f'{tf} {label}'))
        if vals:break
    return vals


def _carryover_extension_v623(f,p,a,market_phase=None,market_date=None):
    """Phase-aware extension memory for pre-market/open/after-hours/closed reviews."""
    out={'active':False,'prior_session_move_pct':np.nan,'prior_session_move_atr':np.nan,
         'carryover_retention_pct':np.nan,'carryover_raw_retention_pct':np.nan,
         'carryover_extension_beyond_peak_pct':np.nan,'carryover_base_price':np.nan,
         'carryover_peak_close':np.nan,'hard':False,'reason':'','source_session_date':None}
    if f is None or not isinstance(f,pd.DataFrame) or len(f)<2 or not np.isfinite(p) or p<=0:return out
    q=f.dropna(subset=['Close'])
    if len(q)<2:return out
    try:
        dates=[pd.Timestamp(x).date() for x in q.index]
        md=pd.Timestamp(market_date).date() if market_date is not None else pd.Timestamp.now().date()
    except Exception:
        dates=[None]*len(q); md=None
    phase=str(market_phase or '').upper().strip()
    if phase in ('PRE-MARKET','PRE-OPEN'):
        prev_i,base_i=-1,-2
    elif phase in ('OPEN','AFTER-MARKET'):
        if dates[-1] is not None and md is not None and dates[-1]==md and len(q)>=3:
            prev_i,base_i=-2,-3
        else:
            prev_i,base_i=-1,-2
    elif phase=='CLOSED':
        prev_i,base_i=-1,-2
    else:
        prev_i,base_i=(-2,-3) if len(q)>=3 else (-1,-2)
    if abs(base_i)>len(q):return out
    prev=q.iloc[prev_i]; base=q.iloc[base_i]
    prev_close=_finite(prev.get('Close',np.nan)); base_close=_finite(base.get('Close',np.nan))
    if not (np.isfinite(prev_close) and np.isfinite(base_close) and prev_close>0 and base_close>0):return out
    prior_move=prev_close/base_close-1.0
    prev_atr=_finite(prev.get('atr14',np.nan),a)
    atr_frac=prev_atr/base_close if np.isfinite(prev_atr) and prev_atr>0 else np.nan
    prior_atr=prior_move/atr_frac if np.isfinite(atr_frac) and atr_frac>0 else np.nan
    denom=prev_close-base_close
    retention=(p-base_close)/denom if prior_move>0 and denom>0 else np.nan
    retention_clip=float(np.clip(retention,0,1.5)) if np.isfinite(retention) else np.nan
    candidate_active=bool(
        (prior_move>=.075 and np.isfinite(retention) and retention>=.65) or
        (np.isfinite(prior_atr) and prior_atr>=1.35 and prior_move>=.055 and np.isfinite(retention) and retention>=.75)
    )
    active=bool(candidate_active and phase!='CLOSED')
    hard=bool(active and np.isfinite(retention_clip) and retention_clip>=.80)
    raw_retention_pct=100*retention if np.isfinite(retention) else np.nan
    display_retention_pct=min(100.0,max(0.0,raw_retention_pct)) if np.isfinite(raw_retention_pct) and candidate_active else np.nan
    beyond_peak_pct=max(0.0,(p/prev_close-1.0)*100.0) if np.isfinite(p) and prev_close>0 else np.nan
    reason=''
    if active:
        reason=f'prior session +{100*prior_move:.1f}% • {display_retention_pct:.0f}% retained'
        if np.isfinite(beyond_peak_pct) and beyond_peak_pct>0.25:reason+=f' • +{beyond_peak_pct:.1f}% above prior close'
    elif phase=='CLOSED' and candidate_active:
        reason=f'latest completed session +{100*prior_move:.1f}% • carryover pending next session'
    out.update({'active':active,'hard':hard,'prior_session_move_pct':100*prior_move,
                'prior_session_move_atr':prior_atr,'carryover_retention_pct':display_retention_pct,
                'carryover_raw_retention_pct':raw_retention_pct,
                'carryover_extension_beyond_peak_pct':beyond_peak_pct if active else np.nan,
                'carryover_base_price':base_close,'carryover_peak_close':prev_close,'reason':reason,
                'source_session_date':str(dates[prev_i]) if dates and dates[prev_i] is not None else None})
    return out


def _extension_risk_v614(f,r,p,a,zone_low,zone_high,entry_mid,target1,trigger_anchor=None,hourly_feat=None,m15_feat=None,previous_close=None,invalidation=None,target2=None,market_phase=None,market_date=None):
    """V6.1.4 late-entry guard with volatility normalization and retest planning."""
    close=_finite(r.get('Close',np.nan)); op=_finite(r.get('Open',np.nan)); vw=_finite(r.get('vwap',np.nan)); e9=_finite(r.get('ema9',np.nan)); e20=_finite(r.get('ema20',np.nan))
    prev=_finite(previous_close,np.nan)
    if not np.isfinite(prev) or prev<=0:
        if np.isfinite(close) and close>0 and abs(p/close-1.0)>0.015:prev=close
        elif f is not None and len(f)>=2:prev=_finite(f.iloc[-2].get('Close',np.nan))
    session_ret=(p/prev-1.0) if np.isfinite(prev) and prev>0 else np.nan
    same_daily_bar=bool(np.isfinite(close) and close>0 and abs(p/close-1.0)<=0.015)
    open_ret=(p/op-1.0) if same_daily_bar and np.isfinite(op) and op>0 else np.nan
    gap=(op/prev-1.0) if same_daily_bar and np.isfinite(op) and op>0 and np.isfinite(prev) and prev>0 else np.nan

    anchor_px=_finite((trigger_anchor or {}).get('price',np.nan))
    since_trigger=(p/anchor_px-1.0) if np.isfinite(anchor_px) and anchor_px>0 else np.nan
    before_trigger=(anchor_px/prev-1.0) if np.isfinite(anchor_px) and anchor_px>0 and np.isfinite(prev) and prev>0 else np.nan

    # V6.3.9.47 — make the timing context explicit instead of overloading one
    # "Consumed" number. The legacy MoveConsumedBeforeTriggerPct remains the
    # session-level pre-trigger metric used by the existing 80% hard gate.
    # New fields add broader multi-day extension and post-trigger T1 progress.
    # They are context/audit fields in this build and do not silently change the
    # proven production gate thresholds.
    _recent_candidates=[]
    for _window,_key in (('3D','mom3'),('5D','mom5'),('10D','mom10')):
        _ret=_finite(r.get(_key,np.nan))
        if np.isfinite(_ret) and _ret>0:
            _recent_candidates.append((_ret,_window))
    if _recent_candidates:
        _recent_ret,recent_run_window=max(_recent_candidates,key=lambda z:z[0])
        recent_run_pct=100.0*_recent_ret
    else:
        recent_run_pct=np.nan;recent_run_window='—'
    _atr_pct=(100.0*a/p) if np.isfinite(a) and a>0 and np.isfinite(p) and p>0 else np.nan
    recent_run_atr=(recent_run_pct/_atr_pct) if np.isfinite(recent_run_pct) and np.isfinite(_atr_pct) and _atr_pct>0 else np.nan
    if np.isfinite(recent_run_pct):
        if recent_run_pct>=12.0 or (np.isfinite(recent_run_atr) and recent_run_atr>=3.0):recent_run_label='EXTENDED CONTEXT'
        elif recent_run_pct>=8.0 or (np.isfinite(recent_run_atr) and recent_run_atr>=2.0):recent_run_label='LATE CONTEXT'
        elif recent_run_pct>=4.0 or (np.isfinite(recent_run_atr) and recent_run_atr>=1.0):recent_run_label='MID CONTEXT'
        else:recent_run_label='EARLY CONTEXT'
    else:
        recent_run_label='NO DATA'

    _post_path=(target1-anchor_px) if np.isfinite(target1) and np.isfinite(anchor_px) and target1>anchor_px else np.nan
    post_trigger_consumed_pct=(100.0*max(0.0,p-anchor_px)/_post_path) if np.isfinite(_post_path) and _post_path>0 and np.isfinite(p) else np.nan
    if np.isfinite(post_trigger_consumed_pct):
        if post_trigger_consumed_pct<20.0:post_trigger_consumed_label='FRESH'
        elif post_trigger_consumed_pct<50.0:post_trigger_consumed_label='DEVELOPING'
        elif post_trigger_consumed_pct<75.0:post_trigger_consumed_label='ADVANCED'
        elif post_trigger_consumed_pct<100.0:post_trigger_consumed_label='MOSTLY CONSUMED'
        else:post_trigger_consumed_label='T1 REACHED / PASSED'
    else:
        post_trigger_consumed_label='NO DATA'

    dvwap=(p-vw)/a if np.isfinite(vw) and a>0 else np.nan
    de9=(p-e9)/a if np.isfinite(e9) and a>0 else np.nan
    de20=(p-e20)/a if np.isfinite(e20) and a>0 else np.nan
    tprog=(p-entry_mid)/(target1-entry_mid) if np.isfinite(target1) and np.isfinite(entry_mid) and target1>entry_mid else np.nan
    vt=_volume_trend_v614(hourly_feat,m15_feat)
    atr_frac=(a/prev) if np.isfinite(prev) and prev>0 and np.isfinite(a) and a>0 else np.nan
    session_atr=(session_ret/atr_frac) if np.isfinite(session_ret) and np.isfinite(atr_frac) and atr_frac>0 else np.nan
    move_pctile,move_pctile_n=_session_move_percentile_v614(f,session_ret)
    carry=_carryover_extension_v623(f,p,a,market_phase=market_phase,market_date=market_date)
    inv=_finite(invalidation,np.nan); t2=_finite(target2,np.nan)
    live_risk=(p-inv) if np.isfinite(inv) and p>inv else np.nan
    live_rr_t1=(target1-p)/live_risk if np.isfinite(target1) and np.isfinite(live_risk) and live_risk>0 else np.nan
    live_rr_t2=(t2-p)/live_risk if np.isfinite(t2) and np.isfinite(live_risk) and live_risk>0 else np.nan

    def ramp(x,lo,hi):
        if not np.isfinite(x):return 0.0
        return float(np.clip((x-lo)/max(hi-lo,1e-9),0,1))
    sr=max(0.0,session_ret) if np.isfinite(session_ret) else 0.0
    st=max(0.0,since_trigger) if np.isfinite(since_trigger) else 0.0
    bt=max(0.0,before_trigger) if np.isfinite(before_trigger) else 0.0
    gp=max(0.0,gap) if np.isfinite(gap) else 0.0
    vext=max([x for x in (dvwap,de9,de20) if np.isfinite(x)]+[0.0])
    tp=max(0.0,tprog) if np.isfinite(tprog) else 0.0
    sa=max(0.0,session_atr) if np.isfinite(session_atr) else 0.0
    score=(22*ramp(sr,.03,.10)+16*ramp(st,.02,.08)+12*ramp(bt,.03,.09)+14*ramp(max(0,dvwap) if np.isfinite(dvwap) else 0,.75,2.0)+9*ramp(max(0,de9,de20),.80,2.0)+8*ramp(gp,.02,.07)+9*ramp(tp,.25,.85)+10*ramp(sa,.70,1.80))
    if vt.get('label')=='FADING' and sr>=.04:score+=5
    if bool(carry.get('active')):score+=18
    # V6.3.9.50: multi-day context may not hard-veto a setup by itself. A stock
    # that already travelled far over 3D/5D/10D may read ELEVATED for awareness,
    # but Recent rise is context only; it does not itself force RETEST or block
    # a continuation setup. The established hard extension/veto rules remain authoritative.
    if recent_run_label=='EXTENDED CONTEXT':score=max(score,35.0)
    elif recent_run_label=='LATE CONTEXT':score=max(score,25.0)
    # Reward/risk deterioration is a late-entry property, not a weakness of the setup.
    if np.isfinite(live_rr_t1) and live_rr_t1<1.0:score+=8*ramp(1.0-live_rr_t1,0.0,.75)
    if np.isfinite(live_rr_t2) and live_rr_t2<1.5:score+=6*ramp(1.5-live_rr_t2,0.0,1.0)
    score=float(np.clip(score,0,100))

    rr_hard=bool(np.isfinite(live_rr_t1) and np.isfinite(live_rr_t2) and live_rr_t1<0.80 and live_rr_t2<1.40)
    # Research/audit flag for the next session. This does not alter today's decision;
    # it records whether today's completed/near-completed move is large enough that
    # tomorrow must inherit extension memory rather than resetting to a fresh setup.
    next_carry_candidate=bool(sr>=.075 or (sr>=.055 and sa>=1.35))
    next_carry_hard_candidate=bool(sr>=.10 or (sr>=.075 and sa>=1.25))
    next_carry_reason=(f'current session +{100*sr:.1f}% / {sa:.2f} ATR should carry into next session'
                       if next_carry_candidate and np.isfinite(sa) else
                       (f'current session +{100*sr:.1f}% should carry into next session' if next_carry_candidate else ''))
    hard=bool(
        sr>=.10 or st>=.085 or vext>=2.20 or tp>=.85 or rr_hard or bool(carry.get('hard')) or
        (sr>=.065 and sa>=1.25) or
        (sr>=.055 and np.isfinite(move_pctile) and move_pctile>=93) or
        (sr>=.075 and (gp>=.045 or vext>=1.25)) or
        (bt>=.075 and sr>=.09)
    )
    if hard: score=max(score,70.0)
    score=float(np.clip(score,0,100))
    veto=bool(hard or score>=60)
    label='HIGH' if veto else ('ELEVATED' if score>=35 else 'LOW')
    reasons=[]
    if sr>=.06:reasons.append(f'session +{100*sr:.1f}%')
    if np.isfinite(session_atr) and session_atr>=1.0:reasons.append(f'{session_atr:.2f} ATR session move')
    if bt>=.05:reasons.append(f'+{100*bt:.1f}% before valid trigger')
    if st>=.04:reasons.append(f'+{100*st:.1f}% since trigger')
    if vext>=1.15:reasons.append(f'{vext:.2f} ATR extended')
    if gp>=.035:reasons.append(f'gap +{100*gp:.1f}%')
    if tp>=.60:reasons.append(f'{100*tp:.0f}% of path to T1 already used')
    if np.isfinite(move_pctile) and move_pctile>=90:reasons.append(f'{move_pctile:.0f}th pct positive day')
    if vt.get('label')=='FADING':reasons.append('intraday volume fading')
    if bool(carry.get('active')):reasons.append(carry.get('reason','prior-session extension retained'))
    if recent_run_label in ('LATE CONTEXT','EXTENDED CONTEXT') and np.isfinite(recent_run_pct):
        reasons.append(f'{recent_run_window} recent run +{recent_run_pct:.1f}% • {recent_run_label}')
    if np.isfinite(live_rr_t1) and live_rr_t1<1.0:reasons.append(f'live R:R T1 only {live_rr_t1:.2f}x')
    if np.isfinite(live_rr_t2) and live_rr_t2<1.5:reasons.append(f'live R:R T2 only {live_rr_t2:.2f}x')
    if not reasons and label=='ELEVATED':reasons.append('price extension elevated')

    # Build a transparent retest band from the original entry geometry plus the
    # nearest meaningful intraday support below price. V6.3.9.63 makes this a
    # separate retest plan: the entry band must sit ABOVE its stop, and targets /
    # R:R are recalibrated from the retest geometry. This is guidance for a new
    # confirmation check, never an automatic buy level.
    supports=[]
    if np.isfinite(zone_high) and zone_high<p:supports.append((float(zone_high),'Original entry-zone high'))
    for x,label0 in _latest_intraday_supports_v614(hourly_feat,m15_feat):
        if x<p-max(.20*a,.006*p):supports.append((x,label0))
    retest_entry_low=retest_entry_high=retest_invalidation=retest_target1=retest_target2=np.nan
    retest_rr_t1=retest_rr_t2=np.nan;retest_plan_valid=False;retest_plan_reason='No reliable retest level'
    if supports:
        ref,ref_label=max(supports,key=lambda z:z[0])
        retest_low=max(_finite(zone_low,ref-.18*a),ref-.18*a)
        retest_high=min(p,ref+.12*a)
        # Keep a meaningful entry buffer above the existing structural invalidation.
        # This fixes cases where a nominal retest zone overlapped or fell below Stop.
        _stop_buffer=max(.08*a if np.isfinite(a) and a>0 else 0.0,.0015*p if np.isfinite(p) and p>0 else 0.0)
        if np.isfinite(inv):retest_low=max(retest_low,inv+_stop_buffer)
        # Legacy T1 geometry remains a ceiling, not an entry recommendation. It
        # prevents a retest band from being placed so high that even the existing
        # structural T1 cannot provide 1.20x reward/risk.
        rr_floor_t1=1.20
        rr_cap=(target1+rr_floor_t1*inv)/(1.0+rr_floor_t1) if np.isfinite(target1) and np.isfinite(inv) and target1>inv else np.nan
        if np.isfinite(rr_cap):retest_high=min(retest_high,rr_cap)
        if retest_low<=retest_high and retest_high>0:
            retest_entry_low=float(retest_low);retest_entry_high=float(retest_high)
            _re_mid=.5*(retest_entry_low+retest_entry_high)
            if np.isfinite(inv) and inv<retest_entry_low:
                retest_invalidation=float(inv)
            else:
                _stop_dist=max(.22*a if np.isfinite(a) and a>0 else 0.0,.004*p if np.isfinite(p) and p>0 else 0.0)
                retest_invalidation=max(0.0,retest_entry_low-_stop_dist)
            _re_risk=_re_mid-retest_invalidation if np.isfinite(retest_invalidation) else np.nan
            if np.isfinite(_re_risk) and _re_risk>0:
                # Recalculate retest targets from the NEW entry/stop geometry.
                # Existing structural targets act only as conservative ceilings.
                _vol_t1=_re_mid+max(1.50*_re_risk,.75*a if np.isfinite(a) and a>0 else 1.50*_re_risk)
                _vol_t2=_re_mid+max(2.50*_re_risk,1.25*a if np.isfinite(a) and a>0 else 2.50*_re_risk)
                retest_target1=min(float(target1),_vol_t1) if np.isfinite(target1) and target1>_re_mid else _vol_t1
                retest_target2=min(float(t2),_vol_t2) if np.isfinite(t2) and t2>retest_target1 else _vol_t2
                if retest_target2<=retest_target1:retest_target2=retest_target1+max(.50*_re_risk,.35*a if np.isfinite(a) and a>0 else .50*_re_risk)
                retest_rr_t1=(retest_target1-_re_mid)/_re_risk
                retest_rr_t2=(retest_target2-_re_mid)/_re_risk
                retest_plan_valid=bool(np.isfinite(retest_rr_t1) and retest_rr_t1>=rr_floor_t1 and retest_target1>_re_mid and retest_invalidation<retest_entry_low)
                retest_plan_reason=(f'Retest-specific geometry valid • stop below entry • T1 R:R {retest_rr_t1:.2f}x'
                                    if retest_plan_valid else
                                    f'Retest level found but geometry/R:R insufficient • T1 R:R {retest_rr_t1:.2f}x')
            pullback=max(0.0,(p-retest_entry_high)/p*100.0) if p>0 else np.nan
            if not retest_plan_valid:retest_status='RETEST LEVEL FOUND — PLAN NOT QUALIFIED'
            elif p>retest_entry_high*1.003:retest_status='WAIT FOR PULLBACK'
            elif p>=retest_entry_low:retest_status='IN RETEST ZONE — RECONFIRM'
            else:retest_status='BELOW RETEST ZONE — REASSESS'
            retest_low,retest_high=retest_entry_low,retest_entry_high
        else:
            retest_low=retest_high=pullback=np.nan
            retest_status='NO VALID RETEST GEOMETRY — REASSESS'
            retest_plan_reason='Retest band would overlap/breach invalidation or fail minimum T1 geometry'
    else:
        ref=ref_label=np.nan;retest_low=retest_high=pullback=np.nan;retest_status='NO RELIABLE RETEST LEVEL'

    # V6.3.9.50 — Recent rise is NOT a proxy for progress from Trigger to T1.
    # An EXTENDED 3D/5D/10D context becomes a RETEST requirement only when the
    # live setup also shows genuine lateness/deterioration. This prevents a case
    # such as 1780.HK (+17% recent rise but only ~27% Trigger→T1 progress) from
    # being pushed to RETEST solely because the broader lookback is large.
    _recent_soft_flags=0
    if str(vt.get('label','')).upper()=='FADING':_recent_soft_flags+=1
    if st>=.06:_recent_soft_flags+=1
    if vext>=1.25:_recent_soft_flags+=1
    if tp>=.50:_recent_soft_flags+=1
    _recent_hard_late=bool(
        (np.isfinite(post_trigger_consumed_pct) and post_trigger_consumed_pct>=60.0) or
        tp>=.60 or rr_hard or score>=60.0 or bool(carry.get('hard'))
    )
    recent_run_retest_context=bool(
        recent_run_label=='EXTENDED CONTEXT' and (_recent_hard_late or _recent_soft_flags>=2)
    )

    return {
        'score':round(score,1),'label':label,'veto':veto,'reasons':reasons,
        'session_move_pct':100*session_ret if np.isfinite(session_ret) else np.nan,
        'session_move_atr':session_atr,'session_move_percentile':move_pctile,'session_move_percentile_n':move_pctile_n,
        'open_move_pct':100*open_ret if np.isfinite(open_ret) else np.nan,
        'gap_pct':100*gap if np.isfinite(gap) else np.nan,
        'move_before_trigger_pct':100*before_trigger if np.isfinite(before_trigger) else np.nan,
        'since_trigger_pct':100*since_trigger if np.isfinite(since_trigger) else np.nan,
        'recent_run_pct':recent_run_pct,'recent_run_atr':recent_run_atr,'recent_run_window':recent_run_window,'recent_run_label':recent_run_label,
        'post_trigger_consumed_pct':post_trigger_consumed_pct,'post_trigger_consumed_label':post_trigger_consumed_label,
        'recent_run_retest_context':bool(recent_run_retest_context),
        'vwap_distance_atr':dvwap,'ema9_distance_atr':de9,'ema20_distance_atr':de20,
        'target1_progress_pct':100*tprog if np.isfinite(tprog) else np.nan,
        'live_rr_t1':live_rr_t1,'live_rr_t2':live_rr_t2,'live_rr_guard_ok':not rr_hard,
        'carryover_extension':bool(carry.get('active')),'carryover_hard_veto':bool(carry.get('hard')),'prior_session_move_pct':carry.get('prior_session_move_pct',np.nan),'prior_session_move_atr':carry.get('prior_session_move_atr',np.nan),'carryover_retention_pct':carry.get('carryover_retention_pct',np.nan),
        'carryover_raw_retention_pct':carry.get('carryover_raw_retention_pct',np.nan),'carryover_extension_beyond_peak_pct':carry.get('carryover_extension_beyond_peak_pct',np.nan),'carryover_source_session_date':carry.get('source_session_date'),
        'next_session_carryover_candidate':next_carry_candidate,'next_session_carryover_hard_candidate':next_carry_hard_candidate,'next_session_carryover_reason':next_carry_reason,
        'volume_trend':vt.get('label','NO DATA'),'volume_trend_timeframe':vt.get('timeframe','—'),'volume_trend_15m':vt.get('label_15m','NO DATA'),'volume_trend_1h':vt.get('label_1h','NO DATA'),
        'retest_zone_low':retest_low,'retest_zone_high':retest_high,'pullback_needed_pct':pullback,
        'retest_entry_low':retest_entry_low,'retest_entry_high':retest_entry_high,'retest_invalidation':retest_invalidation,
        'retest_target1':retest_target1,'retest_target2':retest_target2,'retest_rr_t1':retest_rr_t1,'retest_rr_t2':retest_rr_t2,
        'retest_plan_valid':bool(retest_plan_valid),'retest_plan_reason':retest_plan_reason,
        'retest_reference':ref,'retest_reference_label':ref_label,'retest_status':retest_status,
    }


def entry_timing(feat, quant_score, early_score, hourly_feat=None, m15_feat=None, current_price=None, market_regime='NEUTRAL', previous_close=None, market_phase=None, market_date=None):
    """V6.1.4 Entry Trigger Engine V4.

    Adds a session-aware Trigger Anchor V2, volatility-normalized extension risk,
    and a retest plan. The six classic gates remain visible; extension remains an
    independent veto so a strong setup is not confused with a good price *now*.
    """
    f=feat.dropna(subset=['Close']) if feat is not None else pd.DataFrame()
    if f.empty:
        return {'entry_score':0.0,'setup_entry_score_pre_chase':0.0,'status':'WAIT','trigger_state':'WAIT','zone_low':np.nan,'zone_high':np.nan,'trigger':np.nan,'invalidation':np.nan,'target1':np.nan,'target2':np.nan,'plan_valid':False,'plan_reason':'No data','why_now':'No data','missing_checks':'Daily Setup','confirmed_conditions':0,'total_conditions':6,'chase_risk_score':0.0,'chase_risk_label':'LOW','extension_guard_ok':True,'no_chase':False,'raw_no_chase':False,'no_chase_consistency_override':False,'no_chase_reason':'BLOCK — No data','timing_data_complete':True,'timing_data_source':'NOT REQUIRED','timing_data_reason':'No data / timing completeness gate not applicable'}
    r=f.iloc[-1]
    close=float(r['Close']); p=_finite(current_price,close)
    if not np.isfinite(p) or p<=0:p=close
    atr=_finite(r.get('atr14',np.nan)); vwap=_finite(r.get('vwap',np.nan)); e9=_finite(r.get('ema9',np.nan)); e20=_finite(r.get('ema20',np.nan)); res=_finite(r.get('resistance20',np.nan)); sup=_finite(r.get('support20',np.nan)); rs=_finite(r.get('rsi14',np.nan)); mom3=_finite(r.get('mom3',np.nan),0)
    daily_score,_=entry_score_row(r,quant_score)
    a=atr if np.isfinite(atr) and atr>0 else p*.02

    trigger_anchor=_original_trigger_anchor_v614(f,hourly_feat,m15_feat)
    pre_breakout_accum=_pre_breakout_accumulation_v63956(f)
    setup_origin=_opening_setup_origin_v616(m15_feat)
    momentum_state=_momentum_state_v616(hourly_feat,m15_feat)
    post_spike=_post_spike_state_v621(f,hourly_feat,m15_feat,previous_close,p,momentum_state)
    continuation=_continuation_base_v619(m15_feat,previous_close,p)
    # V6.2.1 coherence guard for the research path: a continuation base may be
    # geometrically present, but it is not research-eligible while post-spike
    # evidence is classified as failed/distribution. Preserve the raw candidate.
    continuation=dict(continuation or {})
    continuation['continuation_base_raw_candidate']=bool(continuation.get('continuation_base_candidate',False))
    continuation['continuation_research_eligible']=str(post_spike.get('post_spike_distribution_risk','NO DATA')).upper()!='HIGH'
    continuation['continuation_invalidation_reason']=''
    if continuation['continuation_base_raw_candidate'] and not continuation['continuation_research_eligible']:
        continuation['continuation_base_candidate']=False
        continuation['continuation_base_status']='RESEARCH • INVALIDATED BY DISTRIBUTION RISK'
        continuation['continuation_invalidation_reason']='Post-spike distribution risk is HIGH'
    plan_p=_finite((trigger_anchor or {}).get('price',np.nan),p)
    if not np.isfinite(plan_p) or plan_p<=0 or plan_p<p*.45 or plan_p>p*1.55:plan_p=p;trigger_anchor=None
    avwap=_finite((trigger_anchor or {}).get('vwap',np.nan),vwap)
    ae9=_finite((trigger_anchor or {}).get('ema9',np.nan),e9)
    ae20=_finite((trigger_anchor or {}).get('ema20',np.nan),e20)

    anchors=[plan_p-.35*a]
    for x in (avwap,ae9,ae20):
        if np.isfinite(x) and plan_p-.8*a<=x<=plan_p+.08*a:anchors.append(x)
    zone_low=max(anchors); zone_high=max(plan_p+.10*a,zone_low+.08*a)
    trigger=plan_p+.08*a
    if np.isfinite(res) and plan_p<=res<=plan_p+1.5*a:trigger=max(trigger,res+.08*a)
    supports=[x for x in (sup,ae20,avwap) if np.isfinite(x) and x<plan_p]
    nearest=max(supports) if supports else plan_p-.9*a
    invalid=min(zone_low-.35*a,nearest-.12*a,plan_p-.45*a)
    entry_mid=(zone_low+zone_high)/2.0; risk=max(entry_mid-invalid,0.55*a)
    target1=entry_mid+max(1.35*risk,0.90*a)
    if np.isfinite(res) and res>entry_mid:target1=max(target1,res+0.15*a)
    target2=max(entry_mid+max(2.25*risk,1.75*a),target1+0.60*a)

    xp,_,xs=exit_pressure_row(r)
    daily_setup=bool(
        daily_score>=56 and float(quant_score)>=58 and xp<55 and
        (not np.isfinite(e20) or p>=e20-0.20*a) and
        (not (np.isfinite(e9) and np.isfinite(e20)) or e9>=e20-0.08*a)
    )

    fresh_d=_recent_transition_evidence(f,4)
    fresh_h=_recent_transition_evidence(hourly_feat,12)
    fresh_m=_recent_transition_evidence(m15_feat,40)
    fresh_signal=bool(fresh_d['fresh'] or fresh_h['fresh'] or fresh_m['fresh'])
    fresh_labels=[]
    for obj in (fresh_d,fresh_h,fresh_m):
        for label in obj['labels']:
            if label not in fresh_labels:fresh_labels.append(label)

    hc=hourly_confirmation(hourly_feat) if hourly_feat is not None and len(hourly_feat) else {'score':np.nan,'status':'NO DATA'}
    mc=hourly_confirmation(m15_feat) if m15_feat is not None and len(m15_feat) else {'score':np.nan,'status':'NO DATA'}
    hs=_finite(hc.get('score',np.nan)); ms=_finite(mc.get('score',np.nan))
    if np.isfinite(hs) and np.isfinite(ms):short_score=.65*hs+.35*ms
    elif np.isfinite(hs):short_score=hs
    elif np.isfinite(ms):short_score=ms
    else:short_score=np.nan
    hourly_ok=bool(np.isfinite(short_score) and short_score>=62)

    short_r=None
    for ff in (m15_feat,hourly_feat):
        if ff is not None and len(ff):
            q=ff.dropna(subset=['Close'])
            if len(q):short_r=q.iloc[-1];break
    dv_daily=directional_volume_row(r); dv_short=directional_volume_row(short_r) if short_r is not None else {'bullish':0.0,'bearish':0.0,'label':'NO INTRADAY','rvol':np.nan}
    cmf=_finite((short_r if short_r is not None else r).get('cmf20',np.nan),0); inst=institutional_flow_row(r)
    volume_flow_ok=bool((dv_short['bullish']>=0.22 and dv_short['bullish']>dv_short['bearish']) or (dv_daily['bullish']>=0.24 and cmf>=-0.02) or inst['score']>=62)

    dist_ema=(p-e20)/a if np.isfinite(e20) and a>0 else 0.0
    dist_vwap=(p-vwap)/a if np.isfinite(vwap) and a>0 else 0.0

    # V6.3.9.35 No-Chase consistency audit.  The original gate used four hard
    # thresholds, including a cliff at 1.80 ATR above VWAP.  That could mark a
    # stock as NoChase=False while the newer continuous extension engine still
    # classified chase risk as LOW.  Preserve the legacy result for audit, but
    # allow a narrow consistency override when the ONLY failures are distance
    # thresholds and the independent extension/timing evidence says the setup is
    # not late.  RSI/momentum failures remain hard; extension vetoes remain hard.
    _no_chase_failures=[]
    if dist_ema>1.65:_no_chase_failures.append(('EMA20_DISTANCE',f'EMA20 distance {dist_ema:.2f} ATR > 1.65'))
    if dist_vwap>1.80:_no_chase_failures.append(('VWAP_DISTANCE',f'VWAP distance {dist_vwap:.2f} ATR > 1.80'))
    if np.isfinite(rs) and rs>76:_no_chase_failures.append(('RSI',f'RSI {rs:.1f} > 76'))
    if mom3>0.16:_no_chase_failures.append(('MOM3',f'3D momentum {100*mom3:.1f}% > 16%'))
    raw_no_chase=(len(_no_chase_failures)==0)

    extension=_extension_risk_v614(f,r,p,a,zone_low,zone_high,entry_mid,target1,trigger_anchor,hourly_feat,m15_feat,previous_close,invalid,target2,market_phase=market_phase,market_date=market_date)
    extension_guard_ok=not bool(extension.get('veto'))

    # Calculate move-consumed early so No-Chase and the later timing hard gate use
    # exactly the same causal measurement.
    _session_move_gate=_finite(extension.get('session_move_pct',np.nan))
    _before_trigger_gate=_finite(extension.get('move_before_trigger_pct',np.nan))
    _consumed_gate=(100.0*max(0.0,_before_trigger_gate)/_session_move_gate) if np.isfinite(_session_move_gate) and _session_move_gate>0 and np.isfinite(_before_trigger_gate) else np.nan
    _timing_data_source='SESSION_MOVE' if np.isfinite(_consumed_gate) else 'UNAVAILABLE'
    _timing_data_reason='Primary session move / move-before-trigger ratio' if np.isfinite(_consumed_gate) else 'Primary session move ratio unavailable'

    # V6.3.9.36 Timing Data Completeness fallback. Some closed-session / provider
    # combinations can preserve a valid causal Trigger Anchor while the session
    # baseline needed by move_before_trigger_pct is unavailable or non-positive.
    # In that case, use the causal setup leg itself: setup origin -> trigger as a
    # fraction of setup origin -> current price. This fallback is only accepted
    # when origin <= trigger <= current, so it cannot turn a retracement or a
    # reversed anchor into a false "fresh" measurement.
    if not np.isfinite(_consumed_gate):
        _origin_gate=_finite((setup_origin or {}).get('price',np.nan))
        _anchor_gate=_finite((trigger_anchor or {}).get('price',np.nan))
        if (np.isfinite(_origin_gate) and _origin_gate>0 and np.isfinite(_anchor_gate) and
                _anchor_gate>=_origin_gate and np.isfinite(p) and p>=_anchor_gate and p>_origin_gate):
            _setup_total=(p/_origin_gate-1.0)*100.0
            _setup_before=(_anchor_gate/_origin_gate-1.0)*100.0
            if np.isfinite(_setup_total) and _setup_total>0 and np.isfinite(_setup_before):
                _consumed_gate=float(np.clip(100.0*max(0.0,_setup_before)/_setup_total,0.0,100.0))
                _timing_data_source='SETUP_ORIGIN_FALLBACK'
                _timing_data_reason='Recovered from setup origin -> trigger anchor / setup origin -> current move'
    timing_consumed_hard_block=bool(np.isfinite(_consumed_gate) and _consumed_gate>=80.0)

    _distance_only=bool(_no_chase_failures) and all(code in {'EMA20_DISTANCE','VWAP_DISTANCE'} for code,_ in _no_chase_failures)
    _ext_score=float(extension.get('score',100.0) or 0.0)
    _low_extension=bool(extension_guard_ok and _ext_score<35.0 and str(extension.get('label','')).upper()=='LOW')
    _not_late_by_consumption=bool((not np.isfinite(_consumed_gate)) or _consumed_gate<70.0)
    no_chase_consistency_override=bool((not raw_no_chase) and _distance_only and _low_extension and _not_late_by_consumption)
    no_chase=bool(raw_no_chase or no_chase_consistency_override)
    if raw_no_chase:
        no_chase_reason='PASS — legacy distance/RSI/momentum checks clear'
    elif no_chase_consistency_override:
        no_chase_reason='CONSISTENCY OVERRIDE — '+ ' • '.join(txt for _,txt in _no_chase_failures) + f' • extension {extension.get("label","LOW")} {float(extension.get("score",0)):.1f} • timing not late'
    else:
        no_chase_reason='BLOCK — '+ ' • '.join(txt for _,txt in _no_chase_failures)

    too_late=bool((not no_chase) and p>=trigger-0.10*a)

    regime=str(market_regime or 'NEUTRAL').upper()
    market_regime_ok=regime not in {'RISK-OFF','BLOCKED','BEARISH BLOCK'}
    plan_valid=all(np.isfinite(x) for x in [zone_low,zone_high,trigger,invalid,target1,target2]) and zone_low<=zone_high and invalid<zone_low and trigger>=zone_low and target1>entry_mid and target2>target1
    plan_reason='OK' if plan_valid else 'Invalid trade-plan geometry / data-scale mismatch'
    invalidated=bool(plan_valid and p<=invalid) or xp>=72

    checks={
        'Daily Setup':daily_setup,
        'Fresh Signal':fresh_signal,
        'Hourly / 15m Timing':hourly_ok,
        'Volume / Flow':volume_flow_ok,
        'No Chase':no_chase,
        'Market Regime':market_regime_ok,
    }
    confirmed=sum(bool(v) for v in checks.values()); total=len(checks)

    # V6.3.9: separate SETUP confirmation from whether the current quote is a
    # sensible entry *now*.  This prevents contradictory states such as
    # "CONFIRMED ENTRY" together with "WAIT FOR PULLBACK" or a poor live R:R.
    setup_confirmed=bool(all(checks.values()) and plan_valid and xp<45 and extension_guard_ok)
    _retest_status=str(extension.get('retest_status','') or '')
    entry_zone_check=bool(plan_valid and p>=zone_low*.995 and p<=zone_high*1.003)
    retest_actionable=bool(_retest_status=='IN RETEST ZONE — RECONFIRM')
    _recent_context_retest=bool(extension.get('recent_run_retest_context',False))
    price_actionable_now=bool(entry_zone_check or retest_actionable)
    # V6.3.9.52 — third entry path: CONTINUATION ENTRY.
    # A stock that moved above the primary entry zone does not have to pull back
    # if the causal trigger is still early/mid, less than 40% of Trigger→T1 is
    # consumed, live R:R remains strong, momentum/flow are constructive, and the
    # price is not objectively overextended. Volume fading or HIGH distribution
    # risk keeps it at CONTINUATION WATCH rather than ENTRY NOW. The older strict
    # continuation-base breakout remains available as an additional confirmation.
    _cont_trigger=_finite(continuation.get('continuation_breakout_trigger',np.nan))
    _vol15=str(extension.get('volume_trend_15m','NO DATA') or 'NO DATA').upper();_volall=str(extension.get('volume_trend','NO DATA') or 'NO DATA').upper()
    _mom=str(momentum_state.get('label','NO DATA') or 'NO DATA').upper();_mom15=str(momentum_state.get('label_15m','NO DATA') or 'NO DATA').upper();_mom1h=str(momentum_state.get('label_1h','NO DATA') or 'NO DATA').upper()
    _flow_bull=max(float(dv_daily.get('bullish',0) or 0),float(dv_short.get('bullish',0) or 0));_flow_bear=max(float(dv_daily.get('bearish',0) or 0),float(dv_short.get('bearish',0) or 0))
    _post_progress=_finite(extension.get('post_trigger_consumed_pct',np.nan))
    _cont_timing_ok=bool(np.isfinite(_consumed_gate) and _consumed_gate<70.0 and not timing_consumed_hard_block)
    _cont_progress_ok=bool(np.isfinite(_post_progress) and 0.0<=_post_progress<40.0)
    _cont_rr_ok=bool(np.isfinite(_finite(extension.get('live_rr_t1',np.nan))) and _finite(extension.get('live_rr_t1',np.nan))>=1.50 and ((not np.isfinite(_finite(extension.get('live_rr_t2',np.nan)))) or _finite(extension.get('live_rr_t2',np.nan))>=1.50))
    _cont_momentum_ok=bool(_mom in ('STRENGTHENING','STABLE') and _mom15 not in ('BEARISH','COOLING') and _mom1h not in ('BEARISH','COOLING'))
    _cont_flow_ok=bool(_flow_bull>=.60 and _flow_bear<.45 and volume_flow_ok)

    # V6.3.9.52 — continuation participation/distribution gates use absolute
    # evidence as well as trend direction. "FADING" only means participation is
    # lower than the immediately preceding bars; it is not automatically weak.
    # A still-exceptional absolute RVOL with strong bullish flow + constructive
    # momentum may therefore remain continuation-ready. Likewise, a HIGH
    # post-spike risk created only by giveback/retention is treated as a warning
    # unless bearish volume/flow, broken structure or cooling momentum confirms
    # actual distribution. FAILED SPIKE remains a hard block.
    _cont_live_rvol=_finite((short_r if short_r is not None else {}).get('intraday_cum_rvol',np.nan))
    if not np.isfinite(_cont_live_rvol):_cont_live_rvol=_finite(dv_short.get('rvol',np.nan))
    if not np.isfinite(_cont_live_rvol):_cont_live_rvol=_finite(dv_daily.get('rvol',np.nan))
    _cont_abs_volume_strong=bool(np.isfinite(_cont_live_rvol) and _cont_live_rvol>=1.50)
    _cont_fading_but_strong=bool(
        _volall=='FADING' and _cont_abs_volume_strong and _flow_bull>=.60 and _flow_bear<.30 and
        _mom in ('STRENGTHENING','STABLE') and _mom15 not in ('BEARISH','COOLING') and
        _mom1h not in ('BEARISH','COOLING')
    )
    _cont_volume_ready=bool(
        (_volall!='FADING' and _vol15 in ('ACCELERATING','STABLE','MIXED')) or
        _cont_fading_but_strong
    )
    if _cont_fading_but_strong:
        _cont_volume_state=f'FADING BUT STRONG • RVOL {_cont_live_rvol:.2f}x'
    elif _cont_volume_ready:
        _cont_volume_state=f'{_volall} • 15m {_vol15}'
    else:
        _cont_volume_state=f'WEAK/UNCONFIRMED • {_volall} • 15m {_vol15}'

    _post_state=str(post_spike.get('post_spike_state','NO DATA') or 'NO DATA').upper()
    _post_risk=str(post_spike.get('post_spike_distribution_risk','NO DATA') or 'NO DATA').upper()
    _post_bear_bars=int(_finite(post_spike.get('post_spike_bearish_confirm_bars',0),0) or 0)
    _post_dist_score=_finite(post_spike.get('post_spike_distribution_score',np.nan))
    _post_structure_ok=bool(post_spike.get('post_spike_structure_ok',False))
    _post_retention=_finite(post_spike.get('move_retention_from_high_pct',np.nan))
    _cont_bearish_distribution_confirmed=bool(
        _post_state=='FAILED SPIKE' or
        _post_bear_bars>=2 or
        (np.isfinite(_post_dist_score) and _post_dist_score>=.67) or
        _flow_bear>=.45 or
        (_post_risk=='HIGH' and not _post_structure_ok) or
        (_post_risk=='HIGH' and _mom in ('COOLING','BEARISH'))
    )
    _cont_distribution_soft_override=bool(
        _post_risk=='HIGH' and _post_state=='DISTRIBUTION RISK' and
        not _cont_bearish_distribution_confirmed and _cont_abs_volume_strong and
        _flow_bull>=.60 and _flow_bear<.30 and _cont_momentum_ok
    )
    _cont_distribution_ok=bool(_post_risk!='HIGH' or _cont_distribution_soft_override)
    if _cont_distribution_soft_override:
        _cont_distribution_state='NO CONFIRMED DISTRIBUTION • HIGH-RISK WARNING SOFTENED'
    elif _cont_distribution_ok:
        _cont_distribution_state=f'CLEAR • {_post_risk}'
    else:
        _cont_distribution_state=f'BLOCKED • {_post_state} / {_post_risk}'

    _distances=[_finite(extension.get(k,np.nan)) for k in ('vwap_distance_atr','ema9_distance_atr','ema20_distance_atr')]
    _positive_dist=[max(0.0,x) for x in _distances if np.isfinite(x)]
    _cont_distance_ok=bool((not _positive_dist) or max(_positive_dist)<=1.65)
    _outside_primary=bool(plan_valid and p>zone_high*1.003)
    _continuation_base_ok=bool(setup_confirmed and _outside_primary and extension_guard_ok and not timing_consumed_hard_block and _cont_timing_ok and _cont_progress_ok and _cont_rr_ok and _cont_momentum_ok and _cont_flow_ok and _cont_distance_ok)
    continuation_entry_watch=bool(_continuation_base_ok and (not _cont_volume_ready or not _cont_distribution_ok))
    continuation_entry_ready=bool(_continuation_base_ok and _cont_volume_ready and _cont_distribution_ok)
    _cont_reasons=[]
    if not _cont_progress_ok:_cont_reasons.append(f'Trigger→T1 progress {_post_progress:.0f}% is not <40%' if np.isfinite(_post_progress) else 'Trigger→T1 progress unavailable')
    if not _cont_timing_ok:_cont_reasons.append('Trigger timing is late/unavailable')
    if not _cont_rr_ok:_cont_reasons.append(f'live R:R T1 {_finite(extension.get("live_rr_t1",np.nan)):.2f}x is below 1.50x' if np.isfinite(_finite(extension.get('live_rr_t1',np.nan))) else 'live R:R unavailable')
    if not _cont_momentum_ok:_cont_reasons.append(f'momentum {_mom} (15m {_mom15} / 1H {_mom1h})')
    if not _cont_flow_ok:_cont_reasons.append('flow/volume-flow not strong enough')
    if not _cont_distance_ok:_cont_reasons.append('price too extended from VWAP/EMA structure')
    if _continuation_base_ok and not _cont_volume_ready:_cont_reasons.append(f'volume not confirmed — {_cont_volume_state}')
    if _continuation_base_ok and not _cont_distribution_ok:_cont_reasons.append(f'distribution confirmed — {_cont_distribution_state}')
    if _cont_reasons:
        continuation_entry_reason=' • '.join(_cont_reasons[:4])
    else:
        _cont_ok_notes=[]
        if _cont_fading_but_strong:_cont_ok_notes.append(_cont_volume_state)
        if _cont_distribution_soft_override:_cont_ok_notes.append('no bearish confirmation behind post-spike HIGH warning')
        continuation_entry_reason='Momentum/flow/R:R/timing aligned; continuation price window is valid'+((' • '+' • '.join(_cont_ok_notes)) if _cont_ok_notes else '')
    continuation_entry_state='READY' if continuation_entry_ready else ('WATCH' if continuation_entry_watch else ('BLOCKED' if _outside_primary and setup_confirmed else 'N/A'))

    breakout_continuation_actionable=bool(
        _recent_context_retest and continuation.get('continuation_base_candidate',False) and continuation.get('continuation_hold_ok',False) and
        np.isfinite(_cont_trigger) and p>=_cont_trigger and _vol15=='ACCELERATING' and _volall!='FADING' and
        _mom15=='STRENGTHENING' and _mom1h not in ('BEARISH','COOLING') and _flow_bull>=.65 and _flow_bear<.45 and extension_guard_ok and not timing_consumed_hard_block
    )
    if _recent_context_retest and not (retest_actionable or breakout_continuation_actionable or continuation_entry_ready):
        price_actionable_now=False
    elif breakout_continuation_actionable or continuation_entry_ready:
        price_actionable_now=True
    live_rr_t1=_finite(extension.get('live_rr_t1',np.nan))
    live_rr_t2=_finite(extension.get('live_rr_t2',np.nan))
    rr_t1_ok=bool((not np.isfinite(live_rr_t1)) or live_rr_t1>=1.00)
    rr_t2_ok=bool((not np.isfinite(live_rr_t2)) or live_rr_t2>=1.50)
    rr_actionable=bool(rr_t1_ok and rr_t2_ok)
    confirmed_entry_gate_ok=bool(setup_confirmed and price_actionable_now and rr_actionable and not timing_consumed_hard_block)
    if plan_valid:
        if p>zone_high:entry_distance_pct=100.0*(p/zone_high-1.0)
        elif p<zone_low:entry_distance_pct=100.0*(p/zone_low-1.0)
        else:entry_distance_pct=0.0
    else:entry_distance_pct=np.nan
    actionability_missing=[]
    if setup_confirmed:
        if not price_actionable_now:
            if continuation_entry_watch:
                actionability_missing.append('Continuation WATCH — '+continuation_entry_reason)
            elif _recent_context_retest and not (retest_actionable or breakout_continuation_actionable or continuation_entry_ready):
                actionability_missing.append('Extended multi-day move — require retest OR continuation confirmation before ENTRY NOW')
            elif _retest_status=='WAIT FOR PULLBACK':actionability_missing.append('Price above actionable zone — wait for pullback/retest or continuation confirmation')
            elif _retest_status=='NO RELIABLE RETEST LEVEL':actionability_missing.append('No reliable retest level and price outside entry zone')
            else:actionability_missing.append('Price outside entry/retest zone')
        if not rr_actionable:
            rr_bits=[]
            if np.isfinite(live_rr_t1) and live_rr_t1<1.0:rr_bits.append(f'T1 {live_rr_t1:.2f}x < 1.00x')
            if np.isfinite(live_rr_t2) and live_rr_t2<1.5:rr_bits.append(f'T2 {live_rr_t2:.2f}x < 1.50x')
            actionability_missing.append('Live R:R below entry floor'+((' — '+', '.join(rr_bits)) if rr_bits else ''))

    short_component=short_score if np.isfinite(short_score) else 45.0
    freshness_component=min(100.0,35.0+20.0*len(fresh_labels)) if fresh_signal else 20.0
    flow_component=100.0*max(dv_daily['bullish'],dv_short['bullish'])
    combined=float(_clamp(.42*daily_score+.24*short_component+.17*freshness_component+.17*flow_component))
    combined*=max(0.55,1.0-0.40*xp/100.0)
    pre_chase_combined=float(_clamp(combined))
    combined*=max(0.70,1.0-0.30*float(extension.get('score',0))/100.0)
    actionability=float(_clamp(combined))
    if not extension_guard_ok:actionability*=0.55
    if str(momentum_state.get('label','')).upper()=='COOLING':actionability*=0.90
    if not no_chase:actionability*=0.88
    if setup_confirmed and not confirmed_entry_gate_ok:actionability*=0.82
    actionability=float(_clamp(actionability))

    # V6.3.9.30 hard timing gate. The shared _consumed_gate is calculated
    # above the No-Chase consistency decision in V6.3.9.35 so both guards use the
    # same causal timing measurement.

    if invalidated:state='INVALIDATED'
    elif not extension_guard_ok:state='EXTENDED — DO NOT CHASE'
    elif too_late or (np.isfinite(_consumed_gate) and _consumed_gate>=100.0):state='TOO LATE / CHASE'
    elif timing_consumed_hard_block:state='RETEST ONLY / LATE'
    elif confirmed_entry_gate_ok and combined>=62:state='CONFIRMED ENTRY'
    elif setup_confirmed:state='ARMED'
    elif plan_valid and daily_setup and fresh_signal and xp<55 and confirmed>=4:state='ARMED'
    elif plan_valid and daily_setup and xp<55:state='WATCH'
    else:state='WAIT'

    if not plan_valid:
        zone_low=zone_high=trigger=invalid=target1=target2=np.nan;state='WAIT'
    missing=[k for k,v in checks.items() if not v]
    why=[]
    if state=='EXTENDED — DO NOT CHASE':
        why.extend(extension.get('reasons',[])[:4]);why.append(extension.get('retest_status','WAIT FOR RETEST'))
    else:
        if fresh_signal:why.extend(fresh_labels[:3])
        if hourly_ok:why.append(f'Hourly/15m {short_score:.0f}')
        if volume_flow_ok:why.append('bullish volume/flow')
    why_now=' • '.join(why[:5]) if why else 'Waiting for fresh multi-timeframe confirmation'
    anchor_ts=(trigger_anchor or {}).get('confirmed_time',(trigger_anchor or {}).get('timestamp','—'));anchor_bar_start=(trigger_anchor or {}).get('bar_start_time',(trigger_anchor or {}).get('timestamp','—'));anchor_tf=(trigger_anchor or {}).get('timeframe','—');anchor_signals=' • '.join((trigger_anchor or {}).get('signals',[])) if trigger_anchor else 'None'
    anchor_quality=(trigger_anchor or {}).get('quality','NONE');anchor_age=(trigger_anchor or {}).get('age_bars',np.nan);anchor_selection=(trigger_anchor or {}).get('selection','NO TRIGGER ANCHOR')
    retest_lo=extension.get('retest_zone_low',np.nan);retest_hi=extension.get('retest_zone_high',np.nan)
    origin_px=_finite((setup_origin or {}).get('price',np.nan)); prev_for_origin=_finite(previous_close,np.nan)
    move_before_origin=(origin_px/prev_for_origin-1.0)*100.0 if np.isfinite(origin_px) and origin_px>0 and np.isfinite(prev_for_origin) and prev_for_origin>0 else np.nan
    since_origin=(p/origin_px-1.0)*100.0 if np.isfinite(origin_px) and origin_px>0 and np.isfinite(p) and p>0 else np.nan
    # V6.1.8 research-only trigger efficiency audit. It measures how much price/time
    # was consumed between the earliest observable 15m setup origin and the causal
    # trade trigger. It never upgrades a trade by itself.
    anchor_px_eff=_finite((trigger_anchor or {}).get('price',np.nan))
    origin_to_trigger_pct=(anchor_px_eff/origin_px-1.0)*100.0 if np.isfinite(anchor_px_eff) and anchor_px_eff>0 and np.isfinite(origin_px) and origin_px>0 else np.nan
    trigger_lag_minutes=np.nan
    try:
        _ats=pd.Timestamp((trigger_anchor or {}).get('confirmed_time'))
        _ots=pd.Timestamp((setup_origin or {}).get('confirmed_time'))
        if _ats is not pd.NaT and _ots is not pd.NaT:
            trigger_lag_minutes=max(0.0,(_ats-_ots).total_seconds()/60.0)
    except Exception:
        trigger_lag_minutes=np.nan
    _session_move_eff=_finite(extension.get('session_move_pct',np.nan))
    _before_trigger_eff=_finite(extension.get('move_before_trigger_pct',np.nan))
    _before_origin_eff=_finite(move_before_origin,np.nan)
    # Reuse the shared V6.3.9.36 primary/fallback calculation so the Entry state,
    # No-Chase audit, hard 80% gate and exported audit field cannot disagree.
    move_consumed_before_trigger_pct=_consumed_gate if np.isfinite(_consumed_gate) else np.nan
    move_consumed_before_origin_pct=(100.0*max(0.0,_before_origin_eff)/_session_move_eff) if np.isfinite(_session_move_eff) and _session_move_eff>0 and np.isfinite(_before_origin_eff) else np.nan
    if np.isfinite(move_consumed_before_trigger_pct):
        if move_consumed_before_trigger_pct < 45:
            trigger_efficiency_label='EARLY'
        elif move_consumed_before_trigger_pct < 70:
            trigger_efficiency_label='MID'
        elif move_consumed_before_trigger_pct < 80:
            trigger_efficiency_label='AGING'
        elif move_consumed_before_trigger_pct < 100:
            trigger_efficiency_label='RETEST ONLY / LATE'
        else:
            trigger_efficiency_label='TOO LATE / MOVE CONSUMED'
    else:
        trigger_efficiency_label='NO DATA'

    _timing_requires_complete=state in ('ARMED','CONFIRMED ENTRY') or ('TRIGGERED' in str(state).upper())
    _anchor_present=bool(np.isfinite(anchor_px_eff) or str(anchor_quality or 'NONE').upper() not in ('','NONE','NO DATA'))
    timing_data_complete=bool(not (_timing_requires_complete and _anchor_present and not np.isfinite(move_consumed_before_trigger_pct)))
    if timing_data_complete:
        if np.isfinite(move_consumed_before_trigger_pct):
            timing_data_reason=_timing_data_reason
        elif not _timing_requires_complete:
            # V6.3.9.40 Timing audit cleanup: a missing consumed value is not
            # unavailable data when the FINAL state already makes the measurement
            # unnecessary.  Distinguish neutral WAIT/WATCH from states already
            # blocked by another safety layer so Excel/audit wording is truthful.
            _blocked_states={'INVALIDATED','EXTENDED — DO NOT CHASE','TOO LATE / CHASE','RETEST ONLY / LATE'}
            if str(state).upper() in _blocked_states:
                _timing_data_source='NOT REQUIRED — ALREADY BLOCKED'
                timing_data_reason=f'Move-consumed timing is not required because final TradeStage {state} already blocks entry'
            else:
                _timing_data_source='NOT REQUIRED'
                timing_data_reason=f'Move-consumed timing is not required for {state} state until a causal trigger event exists'
        elif not _anchor_present:
            _timing_data_source='NOT REQUIRED — NO CAUSAL ANCHOR'
            timing_data_reason='No causal trigger anchor yet; timing completeness gate not applicable'
        else:
            timing_data_reason='Complete'
    else:
        _timing_data_source='UNAVAILABLE'
        timing_data_reason='ARMED/TRIGGERED has a causal trigger anchor but move-consumed timing could not be measured or recovered'
    trigger_lag_atr=((anchor_px_eff-origin_px)/a) if np.isfinite(anchor_px_eff) and np.isfinite(origin_px) and np.isfinite(a) and a>0 else np.nan
    if timing_consumed_hard_block:
        if np.isfinite(_finite(retest_lo,np.nan)) and np.isfinite(_finite(retest_hi,np.nan)):
            rec=f"RETEST ONLY — TRIGGER ARRIVED LATE ({move_consumed_before_trigger_pct:.0f}%) • WATCH {float(retest_lo):.3f}–{float(retest_hi):.3f}"
        else:
            rec=f"RETEST ONLY — TRIGGER ARRIVED LATE ({move_consumed_before_trigger_pct:.0f}%) • DO NOT CHASE"
    elif continuation_entry_ready:
        rec='CONTINUATION ENTRY READY — TRIGGER EARLY/MID • <40% TO T1 USED • R:R/MOMENTUM/FLOW OK'
    elif continuation_entry_watch:
        rec='CONTINUATION WATCH — '+continuation_entry_reason
    elif breakout_continuation_actionable:
        rec='BREAKOUT CONTINUATION CONFIRMED — STANDARD SETUP/R:R GATES STILL APPLY'
    elif not extension_guard_ok and np.isfinite(_finite(retest_lo,np.nan)) and np.isfinite(_finite(retest_hi,np.nan)):
        rec=f"WAIT FOR RETEST {float(retest_lo):.3f}–{float(retest_hi):.3f}"
        if bool(continuation.get('continuation_base_candidate',False)):
            rec+=" • CONTINUATION BASE = RESEARCH ONLY"
    elif setup_confirmed and not confirmed_entry_gate_ok:
        rec='SETUP CONFIRMED — WAIT FOR ENTRY'
        if actionability_missing:rec+=' • '+actionability_missing[0]
    else:
        rec='DO NOT ENTER' if state in ('INVALIDATED','TOO LATE / CHASE') else ('ENTRY CONDITIONS CONFIRMED' if state=='CONFIRMED ENTRY' else state)
    return {
        'entry_score':round(float(_clamp(combined)),1),'setup_entry_score_pre_chase':round(pre_chase_combined,1),'live_actionability_score':round(actionability,1),'status':state,'trigger_state':state,
        'zone_low':zone_low,'zone_high':zone_high,'trigger':trigger,'invalidation':invalid,'target1':target1,'target2':target2,
        'plan_valid':bool(plan_valid),'plan_reason':plan_reason,'exit_pressure':round(xp,1),'exit_stage':xs,
        'volume_context':dv_short.get('label',dv_daily.get('label','N/A')),
        'daily_setup':daily_setup,'fresh_signal':fresh_signal,'hourly_entry_ok':hourly_ok,'hourly_entry_score':round(short_score,1) if np.isfinite(short_score) else np.nan,
        'volume_flow_ok':volume_flow_ok,'institutional_flow_score':inst['score'],'institutional_flow_label':inst['label'],'no_chase':no_chase,'raw_no_chase':bool(raw_no_chase),'no_chase_consistency_override':bool(no_chase_consistency_override),'no_chase_reason':no_chase_reason,'market_regime':regime,'market_regime_ok':market_regime_ok,
        'confirmed_conditions':int(confirmed),'total_conditions':int(total),'confirmation_pct':round(100.0*confirmed/total,1),
        'setup_confirmed':bool(setup_confirmed),'entry_zone_check':bool(entry_zone_check),'retest_actionable':bool(retest_actionable),'price_actionable_now':bool(price_actionable_now),'rr_actionable':bool(rr_actionable),'confirmed_entry_gate_ok':bool(confirmed_entry_gate_ok),'entry_distance_pct':entry_distance_pct,
        'actionability_missing':' • '.join(actionability_missing) if actionability_missing else 'None',
        'why_now':why_now,'missing_checks':' • '.join(missing) if missing else 'None','fresh_evidence':' • '.join(fresh_labels[:6]) if fresh_labels else 'None',
        'extension_guard_ok':bool(extension_guard_ok),'chase_risk_score':extension.get('score',0.0),'chase_risk_label':extension.get('label','LOW'),'chase_reasons':' • '.join(extension.get('reasons',[])) if extension.get('reasons') else 'None',
        'session_move_pct':extension.get('session_move_pct',np.nan),'session_move_atr':extension.get('session_move_atr',np.nan),'session_move_percentile':extension.get('session_move_percentile',np.nan),'session_move_percentile_n':extension.get('session_move_percentile_n',0),
        'open_move_pct':extension.get('open_move_pct',np.nan),'gap_pct':extension.get('gap_pct',np.nan),'move_before_trigger_pct':extension.get('move_before_trigger_pct',np.nan),'since_trigger_pct':extension.get('since_trigger_pct',np.nan),
        'recent_run_pct':extension.get('recent_run_pct',np.nan),'recent_run_atr':extension.get('recent_run_atr',np.nan),'recent_run_window':extension.get('recent_run_window','—'),'recent_run_label':extension.get('recent_run_label','NO DATA'),
        'post_trigger_consumed_pct':extension.get('post_trigger_consumed_pct',np.nan),'post_trigger_consumed_label':extension.get('post_trigger_consumed_label','NO DATA'),'recent_run_retest_context':bool(_recent_context_retest),
        'breakout_continuation_actionable':bool(breakout_continuation_actionable),'breakout_continuation_trigger':_cont_trigger,'breakout_continuation_volume_ok':bool(_vol15=='ACCELERATING' and _volall!='FADING'),'breakout_continuation_momentum_ok':bool(_mom15=='STRENGTHENING' and _mom1h not in ('BEARISH','COOLING')),'breakout_continuation_flow_ok':bool(_flow_bull>=.65 and _flow_bear<.45),
        'continuation_entry_state':continuation_entry_state,'continuation_entry_watch':bool(continuation_entry_watch),'continuation_entry_ready':bool(continuation_entry_ready),'continuation_entry_reason':continuation_entry_reason,
        'continuation_progress_ok':bool(_cont_progress_ok),'continuation_timing_ok':bool(_cont_timing_ok),'continuation_rr_ok':bool(_cont_rr_ok),'continuation_momentum_ok':bool(_cont_momentum_ok),'continuation_flow_ok':bool(_cont_flow_ok),'continuation_volume_ok':bool(_cont_volume_ready),'continuation_distribution_ok':bool(_cont_distribution_ok),'continuation_distance_ok':bool(_cont_distance_ok),
        'continuation_live_rvol':_cont_live_rvol,'continuation_volume_state':_cont_volume_state,'continuation_fading_strong_override':bool(_cont_fading_but_strong),'continuation_distribution_state':_cont_distribution_state,'continuation_distribution_soft_override':bool(_cont_distribution_soft_override),'continuation_bearish_distribution_confirmed':bool(_cont_bearish_distribution_confirmed),
        'vwap_distance_atr':extension.get('vwap_distance_atr',np.nan),'ema9_distance_atr':extension.get('ema9_distance_atr',np.nan),'ema20_distance_atr':extension.get('ema20_distance_atr',np.nan),'target1_progress_pct':extension.get('target1_progress_pct',np.nan),
        'live_rr_t1':extension.get('live_rr_t1',np.nan),'live_rr_t2':extension.get('live_rr_t2',np.nan),'live_rr_guard_ok':extension.get('live_rr_guard_ok',True),'carryover_extension':extension.get('carryover_extension',False),'carryover_hard_veto':extension.get('carryover_hard_veto',False),'prior_session_move_pct':extension.get('prior_session_move_pct',np.nan),'prior_session_move_atr':extension.get('prior_session_move_atr',np.nan),'carryover_retention_pct':extension.get('carryover_retention_pct',np.nan),
        'carryover_raw_retention_pct':extension.get('carryover_raw_retention_pct',np.nan),'carryover_extension_beyond_peak_pct':extension.get('carryover_extension_beyond_peak_pct',np.nan),'carryover_source_session_date':extension.get('carryover_source_session_date'),
        'next_session_carryover_candidate':extension.get('next_session_carryover_candidate',False),'next_session_carryover_hard_candidate':extension.get('next_session_carryover_hard_candidate',False),'next_session_carryover_reason':extension.get('next_session_carryover_reason',''),
        'volume_trend':extension.get('volume_trend','NO DATA'),'volume_trend_timeframe':extension.get('volume_trend_timeframe','—'),'volume_trend_15m':extension.get('volume_trend_15m','NO DATA'),'volume_trend_1h':extension.get('volume_trend_1h','NO DATA'),
        'trigger_anchor_price':_finite((trigger_anchor or {}).get('price',np.nan)),'trigger_anchor_time':anchor_ts,'trigger_anchor_bar_start_time':anchor_bar_start,'trigger_anchor_timeframe':anchor_tf,'trigger_anchor_signals':anchor_signals,'trigger_anchor_quality':anchor_quality,'trigger_anchor_age_bars':anchor_age,'trigger_anchor_selection':anchor_selection,
        'setup_origin_price':origin_px,'setup_origin_time':(setup_origin or {}).get('confirmed_time','—'),'setup_origin_bar_start_time':(setup_origin or {}).get('bar_start_time','—'),'setup_origin_signals':' • '.join((setup_origin or {}).get('signals',[])) if setup_origin else 'None','setup_origin_quality':(setup_origin or {}).get('quality','NONE'),'move_before_setup_origin_pct':move_before_origin,'since_setup_origin_pct':since_origin,
        'origin_to_trigger_pct':origin_to_trigger_pct,'trigger_lag_minutes':trigger_lag_minutes,'trigger_lag_atr':trigger_lag_atr,
        'move_consumed_before_trigger_pct':move_consumed_before_trigger_pct,'move_consumed_before_setup_origin_pct':move_consumed_before_origin_pct,'trigger_efficiency_label':trigger_efficiency_label,'timing_consumed_hard_block':bool(timing_consumed_hard_block),
        'timing_data_complete':bool(timing_data_complete),'timing_data_source':_timing_data_source,'timing_data_reason':timing_data_reason,
        'pre_breakout_accumulation_score':pre_breakout_accum.get('score',0.0),'pre_breakout_accumulation_raw_score':pre_breakout_accum.get('raw_score',0.0),'pre_breakout_accumulation_stage':pre_breakout_accum.get('stage','NO CURRENT ACCUMULATION SETUP'),'pre_breakout_accumulation_reason':pre_breakout_accum.get('reason',''),
        'pre_move_confirmed':pre_breakout_accum.get('confirmed_pre_move',False),'pre_move_confidence_tier':pre_breakout_accum.get('confidence_tier','NONE'),'pre_move_family_count':pre_breakout_accum.get('family_count',0),'pre_move_family_signature':pre_breakout_accum.get('family_signature','NONE'),'pre_move_baseline_guard_ok':pre_breakout_accum.get('baseline_guard_ok',False),'pre_move_baseline_volume':pre_breakout_accum.get('baseline_volume',np.nan),'pre_move_baseline_turnover':pre_breakout_accum.get('baseline_turnover',np.nan),'effective_volume_shock_ratio':pre_breakout_accum.get('effective_shock_ratio',np.nan),'pre_move_shock_recovery_ok':pre_breakout_accum.get('shock_recovery_ok',False),'pre_move_flow_confirmation':pre_breakout_accum.get('flow_confirmation',False),'pre_move_momentum_confirmation':pre_breakout_accum.get('momentum_confirmation',False),
        'volume_regime_ratio':pre_breakout_accum.get('volume_regime_ratio',np.nan),'volume_shock_ratio':pre_breakout_accum.get('volume_shock_ratio',np.nan),'volume_shock_date':pre_breakout_accum.get('volume_shock_date','—'),'volume_shock_return_pct':pre_breakout_accum.get('volume_shock_return_pct',np.nan),'volume_shock_close_location':pre_breakout_accum.get('volume_shock_close_location',np.nan),'absorption_candidate':pre_breakout_accum.get('absorption_candidate',False),'volume_persistence_ratio':pre_breakout_accum.get('volume_persistence_ratio',np.nan),'price_retention_since_volume_shock_pct':pre_breakout_accum.get('price_retention_pct',np.nan),'pre_breakout_higher_low_count':pre_breakout_accum.get('higher_low_count',0),'pre_breakout_regime_shift':pre_breakout_accum.get('regime_shift',False),
        'momentum_state':momentum_state.get('label','NO DATA'),'momentum_state_15m':momentum_state.get('label_15m','NO DATA'),'momentum_state_1h':momentum_state.get('label_1h','NO DATA'),
        'post_spike_state':post_spike.get('post_spike_state','NO DATA'),'session_peak_price':post_spike.get('session_peak_price',np.nan),'session_peak_move_pct':post_spike.get('session_peak_move_pct',np.nan),'high_giveback_pct':post_spike.get('high_giveback_pct',np.nan),'move_retention_from_high_pct':post_spike.get('move_retention_from_high_pct',np.nan),'post_spike_structure_ok':post_spike.get('post_spike_structure_ok',False),'post_spike_distribution_risk':post_spike.get('post_spike_distribution_risk','NO DATA'),'post_spike_structure_price':post_spike.get('post_spike_structure_price',np.nan),'post_spike_structure_reference':post_spike.get('post_spike_structure_reference','NO DATA'),'post_spike_bearish_confirm_bars':post_spike.get('post_spike_bearish_confirm_bars',0),'post_spike_distribution_score':post_spike.get('post_spike_distribution_score',np.nan),
        'continuation_base_candidate':continuation.get('continuation_base_candidate',False),'continuation_base_raw_candidate':continuation.get('continuation_base_raw_candidate',continuation.get('continuation_base_candidate',False)),'continuation_research_eligible':continuation.get('continuation_research_eligible',True),'continuation_invalidation_reason':continuation.get('continuation_invalidation_reason',''),'continuation_base_status':continuation.get('continuation_base_status','RESEARCH • NO BASE'),'continuation_base_bars':continuation.get('continuation_base_bars',0),'continuation_base_low':continuation.get('continuation_base_low',np.nan),'continuation_base_high':continuation.get('continuation_base_high',np.nan),'continuation_base_range_pct':continuation.get('continuation_base_range_pct',np.nan),'continuation_base_range_atr':continuation.get('continuation_base_range_atr',np.nan),'continuation_volume_dryup_ratio':continuation.get('continuation_volume_dryup_ratio',np.nan),'continuation_breakout_trigger':continuation.get('continuation_breakout_trigger',np.nan),'continuation_base_quality':continuation.get('continuation_base_quality','NO DATA'),'continuation_session_peak':continuation.get('continuation_session_peak',np.nan),'continuation_breakout_reference':continuation.get('continuation_breakout_reference','—'),'continuation_hold_ok':continuation.get('continuation_hold_ok',False),
        'retest_zone_low':extension.get('retest_zone_low',np.nan),'retest_zone_high':extension.get('retest_zone_high',np.nan),'pullback_needed_pct':extension.get('pullback_needed_pct',np.nan),'retest_reference':extension.get('retest_reference',np.nan),'retest_reference_label':extension.get('retest_reference_label','—'),'retest_status':extension.get('retest_status','—'),
        'retest_entry_low':extension.get('retest_entry_low',np.nan),'retest_entry_high':extension.get('retest_entry_high',np.nan),'retest_invalidation':extension.get('retest_invalidation',np.nan),'retest_target1':extension.get('retest_target1',np.nan),'retest_target2':extension.get('retest_target2',np.nan),'retest_rr_t1':extension.get('retest_rr_t1',np.nan),'retest_rr_t2':extension.get('retest_rr_t2',np.nan),'retest_plan_valid':extension.get('retest_plan_valid',False),'retest_plan_reason':extension.get('retest_plan_reason',''),
        'retest_confirmation_needed':'15m hold/reclaim of retest support + MACD histogram turn up + bullish volume confirmation + extension guard clears',
        'recommended_action':rec,
    }


def scan_universe(tickers,daily_period='6mo',use_hourly=True,hourly_period='1mo',horizon=5,target_pct=.06,min_turnover=3_000_000,buy_threshold=66,prefilter_top=30):
    stage1=[]
    for ticker in tickers:
        try:
            d=fetch_ohlcv(ticker,daily_period,'1d')
            if d is None or len(d)<35: continue
            f=compute_features(d); latest=score_latest(f,min_turnover); pre=.72*latest['score']+.28*latest['early_score']
            stage1.append((pre,ticker,d,f,latest))
        except Exception:
            continue
    if not stage1:return pd.DataFrame()
    stage1.sort(key=lambda z:z[0],reverse=True); finalists=stage1[:max(5,min(int(prefilter_top),len(stage1)))]
    rows=[]
    for pre,ticker,d,f,latest in finalists:
        try:
            hs=he=np.nan; hfeat=m15feat=None
            if use_hourly:
                h=fetch_ohlcv(ticker,hourly_period,'1h')
                if h is not None and len(h)>=30:
                    hfeat=compute_features(h,True); hl=score_latest(hfeat,0); hs=hl['score']; he=hl['early_score']
                m15=fetch_ohlcv(ticker,'1mo','15m')
                if m15 is not None and len(m15)>=30:m15feat=compute_features(m15,True)
            final=latest['score'] if not np.isfinite(hs) else .78*latest['score']+.22*hs
            early=latest['early_score'] if not np.isfinite(he) else .70*latest['early_score']+.30*he
            ent=entry_timing(f,final,early,hourly_feat=hfeat,m15_feat=m15feat,current_price=latest.get('price',np.nan),market_regime='NEUTRAL'); bt=backtest_signal(f,horizon,target_pct,buy_threshold,min_turnover)
            rows.append({'Ticker':ticker,'Score':round(final,1),'EarlyScore':round(early,1),'EntryScore':ent['entry_score'],'EntryStatus':ent['status'],'EntryTriggerState':ent.get('trigger_state',ent['status']),'EntryConfirmationPct':ent.get('confirmation_pct',np.nan),'EntryWhyNow':ent.get('why_now',''),'EntryMissingChecks':ent.get('missing_checks',''),'EntryLow':round(ent['zone_low'],4),'EntryHigh':round(ent['zone_high'],4),'Trigger':round(ent['trigger'],4),'Invalidation':round(ent['invalidation'],4),'Price':round(latest['price'],4),'VolumeRatio':round(latest['volume_ratio'],2) if np.isfinite(latest['volume_ratio']) else np.nan,'RSI14':round(latest['rsi14'],1) if np.isfinite(latest['rsi14']) else np.nan,'ADX14':round(latest['adx14'],1) if np.isfinite(latest['adx14']) else np.nan,'CMF20':round(latest['cmf20'],3) if np.isfinite(latest['cmf20']) else np.nan,'EmpiricalHitRate':round(bt['hit_rate']*100,1) if bt['n'] else np.nan,'BacktestN':bt['n'],'Confidence':bt['confidence_label'],'ConfidenceScore':bt['confidence'],'AvgReturn':round(bt['avg_return']*100,2) if bt['n'] else np.nan,'MaxDrawdown':round(bt['max_drawdown']*100,2) if bt['n'] else np.nan})
        except Exception:
            continue
    return pd.DataFrame(rows).sort_values(['Score','EarlyScore','EntryScore'],ascending=False).reset_index(drop=True) if rows else pd.DataFrame()


def early_event_backtest(feat, event_pct=.06, lookbacks=(1, 2, 3), min_turnover=0):
    """Analyze Quant/Early scores before single-day close-to-close gains >= event_pct.

    This is intentionally a single-ticker diagnostic. An event is a trading day whose
    Close is at least event_pct above the previous trading day's Close. For each event,
    return the Quant and Early scores 1/2/3 trading days before it.
    """
    f = feat.copy()
    if f is None or len(f) == 0:
        return pd.DataFrame()
    f['quant_score_bt'] = [score_row(r, min_turnover)[0] for _, r in f.iterrows()]
    f['early_score_bt'] = [early_score_row(r)[0] for _, r in f.iterrows()]
    f['day_return_bt'] = f['Close'].pct_change()
    rows = []
    for i in range(1, len(f)):
        day_ret = float(f['day_return_bt'].iloc[i]) if pd.notna(f['day_return_bt'].iloc[i]) else np.nan
        if not np.isfinite(day_ret) or day_ret < float(event_pct):
            continue
        row = {
            'EventDate': f.index[i],
            'EventReturnPct': day_ret * 100.0,
            'PrevClose': float(f['Close'].iloc[i-1]),
            'EventClose': float(f['Close'].iloc[i]),
        }
        for lb in lookbacks:
            j = i - int(lb)
            row[f'Quant_D{lb}'] = float(f['quant_score_bt'].iloc[j]) if j >= 0 else np.nan
            row[f'Early_D{lb}'] = float(f['early_score_bt'].iloc[j]) if j >= 0 else np.nan
        rows.append(row)
    return pd.DataFrame(rows)

# ========================= V5.4 Dynamic Calibration =========================

def _component_dict(r, kind='early', min_turnover=0):
    comps = early_score_row(r)[1] if kind == 'early' else score_row(r, min_turnover)[1]
    return {name: (float(pts), float(mx)) for name, pts, mx in comps}


def calibrate_components(feat, kind='early', event_pct=.03, lookbacks=(1,2,3), min_turnover=0):
    """Ticker-specific, evidence-weighted component calibration.

    Calibration uses historical close-to-close up-events. Multipliers are deliberately
    shrunk toward 1.0 when event samples are small and capped to prevent overfitting.
    """
    f = feat.copy()
    if f is None or len(f) < 35:
        return {'events':0, 'confidence':0.0, 'multipliers':{}, 'table':pd.DataFrame()}
    event_ret = f['Close'].pct_change()
    events = [i for i in range(1, len(f)) if pd.notna(event_ret.iloc[i]) and float(event_ret.iloc[i]) >= float(event_pct) and abs(float(event_ret.iloc[i])) <= 0.60]
    sample_rel = min(1.0, math.sqrt(len(events)/30.0)) if events else 0.0
    baseline = {}
    maxima = {}
    for _, r in f.iterrows():
        for name,(pts,mx) in _component_dict(r,kind,min_turnover).items():
            maxima[name]=mx; baseline.setdefault(name,[]).append(pts>0)
    rows=[]; multipliers={}
    for name,mx in maxima.items():
        pre=[]; seen=set(); by_lb={lb:[] for lb in lookbacks}
        for eno,i in enumerate(events):
            for lb in lookbacks:
                j=i-int(lb)
                if j<0: continue
                active=_component_dict(f.iloc[j],kind,min_turnover).get(name,(0,mx))[0] > 0
                pre.append(active); by_lb[lb].append(active)
                if active: seen.add(eno)
        pre_rate=float(np.mean(pre)) if pre else np.nan
        base_rate=float(np.mean(baseline.get(name,[]))) if baseline.get(name) else np.nan
        lift=pre_rate/base_rate if np.isfinite(pre_rate) and np.isfinite(base_rate) and base_rate>0 else 1.0
        coverage=len(seen)/len(events) if events else 0.0
        lb_rates=[float(np.mean(v)) for v in by_lb.values() if v]
        stability=max(0.55, 1.0-(float(np.std(lb_rates))/0.35)) if lb_rates else 0.55
        # Evidence-shrunk multiplier. High lift + coverage + sample quality earns weight;
        # weak/negative lift loses weight. Hard caps keep one ticker from dominating.
        evidence=sample_rel*(0.55+0.45*coverage)*stability
        mult=1.0 + evidence*(lift-1.0)*1.65
        mult=float(np.clip(mult,0.45,1.80))
        multipliers[name]=mult
        rows.append({'Component':name,'Base Weight':mx,'Dynamic Weight':mx*mult,'Lift x':lift,'Coverage %':coverage*100,'Sample Reliability %':sample_rel*100,'Stability %':stability*100,'Multiplier':mult})
    table=pd.DataFrame(rows)
    if not table.empty: table=table.sort_values(['Dynamic Weight','Lift x'],ascending=False).reset_index(drop=True)
    return {'events':len(events),'confidence':sample_rel*100,'multipliers':multipliers,'table':table}


def dynamic_score_row(r, calibration, kind='early', min_turnover=0):
    comps=_component_dict(r,kind,min_turnover); mults=(calibration or {}).get('multipliers',{})
    num=den=0.0; details=[]
    for name,(pts,mx) in comps.items():
        m=float(mults.get(name,1.0)); dw=mx*m
        strength=(pts/mx) if mx>0 else 0.0
        num += strength*dw; den += dw
        details.append((name,pts,mx,dw,m))
    score=100.0*num/den if den>0 else 0.0
    return float(_clamp(score)), details


def calibrate_combinations(feat, event_pct=.03, lookbacks=(1,2,3), min_turnover=0, top_n=12):
    """Find Early+Quant component pairs whose joint activation has historical lift."""
    f=feat.copy()
    if f is None or len(f)<35:return pd.DataFrame()
    er=f['Close'].pct_change(); events=[i for i in range(1,len(f)) if pd.notna(er.iloc[i]) and float(er.iloc[i])>=float(event_pct)]
    if not events:return pd.DataFrame()
    def active_set(r):
        e={f'E:{n}' for n,(p,m) in _component_dict(r,'early',min_turnover).items() if p>0}
        q={f'Q:{n}' for n,(p,m) in _component_dict(r,'quant',min_turnover).items() if p>0}
        return e|q
    sets=[active_set(r) for _,r in f.iterrows()]
    names=sorted(set().union(*sets)); pairs=[]
    for a_i,a in enumerate(names):
        for b in names[a_i+1:]:
            # only cross-family pairs to keep the search interpretable and reduce overfit
            if a[0]==b[0]: continue
            base=np.mean([(a in s and b in s) for s in sets])
            if base<=0: continue
            pre=[]; seen=set()
            for eno,i in enumerate(events):
                for lb in lookbacks:
                    j=i-int(lb)
                    if j<0:continue
                    on=a in sets[j] and b in sets[j]; pre.append(on)
                    if on:seen.add(eno)
            pr=np.mean(pre) if pre else 0; lift=pr/base if base else np.nan; cov=100*len(seen)/len(events)
            if np.isfinite(lift): pairs.append({'Combination':a[2:]+' + '+b[2:],'Lift x':lift,'Coverage %':cov,'Pre-event active %':100*pr,'Baseline active %':100*base})
    z=pd.DataFrame(pairs)
    if z.empty:return z
    return z.sort_values(['Lift x','Coverage %'],ascending=False).head(top_n).reset_index(drop=True)


def dynamic_scores(feat, event_pct=.03, min_turnover=0):
    """Current static vs dynamically calibrated scores for one ticker."""
    r=feat.dropna(subset=['Close']).iloc[-1]
    ec=calibrate_components(feat,'early',event_pct,(1,2,3),min_turnover)
    qc=calibrate_components(feat,'quant',event_pct,(1,2,3),min_turnover)
    se=early_score_row(r)[0]; sq=score_row(r,min_turnover)[0]
    de,ed=dynamic_score_row(r,ec,'early',min_turnover); dq,qd=dynamic_score_row(r,qc,'quant',min_turnover)
    # Dynamic final weighting: base 35% Early, shifted modestly by relative calibration evidence.
    er=float(ec.get('confidence',0))/100; qr=float(qc.get('confidence',0))/100
    early_w=float(np.clip(.35 + .10*(er-qr),.25,.45)); quant_w=1.0-early_w
    pred=quant_w*dq+early_w*de
    return {'static_early':se,'static_quant':sq,'dynamic_early':de,'dynamic_quant':dq,'final_prediction':float(_clamp(pred)),'early_weight':early_w,'quant_weight':quant_w,'early_calibration':ec,'quant_calibration':qc,'combinations':calibrate_combinations(feat,event_pct,(1,2,3),min_turnover)}


def _forward_outcomes(f,horizon,target_pct):
    highs=f['High'].to_numpy(dtype='float64'); lows=f['Low'].to_numpy(dtype='float64'); closes=f['Close'].to_numpy(dtype='float64')
    hit=np.full(len(f),np.nan); ret=np.full(len(f),np.nan); dd=np.full(len(f),np.nan)
    for i in range(len(f)-horizon):
        hit[i]=1. if np.nanmax(highs[i+1:i+1+horizon])>=closes[i]*(1+target_pct) else 0.
        ret[i]=closes[i+horizon]/closes[i]-1; dd[i]=np.nanmin(lows[i+1:i+1+horizon])/closes[i]-1
    return hit,ret,dd


def compare_static_dynamic_backtest(feat,horizon=5,target_pct=.03,score_threshold=66,min_turnover=0,train_fraction=.70):
    """Leakage-reduced holdout comparison: calibrate on earlier history, evaluate later history."""
    f=feat.copy().dropna(subset=['Close'])
    if len(f)<60:return {'static':{},'dynamic':{},'baseline':np.nan,'signal_lift_static':np.nan,'signal_lift_dynamic':np.nan,'train_rows':0,'test_rows':0}
    cut=max(35,min(len(f)-int(horizon)-10,int(len(f)*train_fraction))); train=f.iloc[:cut].copy(); test=f.iloc[cut:].copy()
    ec=calibrate_components(train,'early',target_pct,(1,2,3),min_turnover); qc=calibrate_components(train,'quant',target_pct,(1,2,3),min_turnover)
    hit,ret,dd=_forward_outcomes(f,int(horizon),float(target_pct)); f['_hit']=hit; f['_ret']=ret; f['_dd']=dd
    rows=[]
    for i in range(cut,len(f)):
        if not np.isfinite(hit[i]):continue
        r=f.iloc[i]; ss=score_row(r,min_turnover)[0]; de,_=dynamic_score_row(r,ec,'early',min_turnover); dq,_=dynamic_score_row(r,qc,'quant',min_turnover)
        ew=float(np.clip(.35+.10*((ec.get('confidence',0)-qc.get('confidence',0))/100),.25,.45)); pred=(1-ew)*dq+ew*de
        rows.append((ss,pred,hit[i],ret[i],dd[i]))
    if not rows:return {'static':{},'dynamic':{},'baseline':np.nan,'signal_lift_static':np.nan,'signal_lift_dynamic':np.nan,'train_rows':len(train),'test_rows':0}
    z=pd.DataFrame(rows,columns=['static','dynamic','hit','ret','dd']); baseline=float(z.hit.mean())
    def pack(col):
        v=z[z[col]>=score_threshold]; n=len(v)
        if not n:return {'n':0,'hits':0,'hit_rate':np.nan,'avg_return':np.nan,'max_drawdown':np.nan,'sample_reliability':0.0}
        return {'n':n,'hits':int(v.hit.sum()),'hit_rate':float(v.hit.mean()),'avg_return':float(v.ret.mean()),'max_drawdown':float(v.dd.min()),'sample_reliability':100*min(1.,math.sqrt(n/60))}
    s=pack('static'); d=pack('dynamic')
    return {'static':s,'dynamic':d,'baseline':baseline,'signal_lift_static':(s.get('hit_rate',np.nan)/baseline if baseline>0 and np.isfinite(s.get('hit_rate',np.nan)) else np.nan),'signal_lift_dynamic':(d.get('hit_rate',np.nan)/baseline if baseline>0 and np.isfinite(d.get('hit_rate',np.nan)) else np.nan),'train_rows':len(train),'test_rows':len(z)}

# V5.4.3 dynamic scanner follows.

def scan_universe_dynamic(tickers,daily_period='6mo',use_hourly=True,hourly_period='1mo',horizon=5,target_pct=.03,min_turnover=0,buy_threshold=66,prefilter_top=30):
    """V5.4 scanner: dynamic ticker calibration + prediction rank + entry timing."""
    stage=[]
    for ticker in tickers:
        try:
            d=fetch_ohlcv(ticker,daily_period,'1d')
            if d is None or len(d)<35:continue
            f=compute_features(d); ds=dynamic_scores(f,target_pct,min_turnover)
            # Fast ranking favors calibrated prediction, with a small static anchor.
            pre=.85*ds['final_prediction']+.15*(.72*ds['static_quant']+.28*ds['static_early'])
            stage.append((pre,ticker,f,ds))
        except Exception:continue
    if not stage:return pd.DataFrame()
    stage.sort(key=lambda x:x[0],reverse=True); stage=stage[:max(5,min(int(prefilter_top),len(stage)))]
    rows=[]
    for pre,ticker,f,ds in stage:
        try:
            # Intraday remains a timing/confirmation layer; daily calibration remains the evidence base.
            hfeat=m15feat=None; hq=he=np.nan
            if use_hourly:
                h=fetch_ohlcv(ticker,hourly_period,'1h')
                if h is not None and len(h)>=30:
                    hfeat=compute_features(h,True); hr=hfeat.dropna(subset=['Close']).iloc[-1]
                    hq,_=dynamic_score_row(hr,ds['quant_calibration'],'quant',0); he,_=dynamic_score_row(hr,ds['early_calibration'],'early',0)
                m15=fetch_ohlcv(ticker,'1mo','15m')
                if m15 is not None and len(m15)>=30:m15feat=compute_features(m15,True)
            dq=ds['dynamic_quant'] if not np.isfinite(hq) else .78*ds['dynamic_quant']+.22*hq
            de=ds['dynamic_early'] if not np.isfinite(he) else .70*ds['dynamic_early']+.30*he
            ew=ds['early_weight']; pred=(1-ew)*dq+ew*de
            ent=entry_timing(f,dq,de,hourly_feat=hfeat,m15_feat=m15feat,current_price=float(f.dropna(subset=['Close']).iloc[-1]['Close']),market_regime='NEUTRAL')
            cmp=compare_static_dynamic_backtest(f,horizon,target_pct,buy_threshold,min_turnover)
            db=cmp.get('dynamic',{}); conf=float(ds['early_calibration'].get('confidence',0)+ds['quant_calibration'].get('confidence',0))/2
            lr=f.dropna(subset=['Close']).iloc[-1]
            rows.append({'Ticker':ticker,'Prediction':round(pred,1),'DynamicQuant':round(dq,1),'DynamicEarly':round(de,1),'StaticQuant':round(ds['static_quant'],1),'StaticEarly':round(ds['static_early'],1),'EntryScore':ent['entry_score'],'EntryStatus':ent['status'],'SignalLift':round(cmp.get('signal_lift_dynamic',np.nan),2) if np.isfinite(cmp.get('signal_lift_dynamic',np.nan)) else np.nan,'CalibrationConfidence':round(conf,1),'BacktestN':int(db.get('n',0) or 0),'EmpiricalHitRate':round(float(db.get('hit_rate'))*100,1) if db.get('n',0) and np.isfinite(db.get('hit_rate',np.nan)) else np.nan,'Price':round(float(lr['Close']),4),'VolumeRatio':round(float(lr.get('volume_ratio',np.nan)),2) if np.isfinite(float(lr.get('volume_ratio',np.nan))) else np.nan,'RSI14':round(float(lr.get('rsi14',np.nan)),1) if np.isfinite(float(lr.get('rsi14',np.nan))) else np.nan})
        except Exception:continue
    return pd.DataFrame(rows).sort_values(['Prediction','DynamicEarly','EntryScore'],ascending=False).reset_index(drop=True) if rows else pd.DataFrame()
