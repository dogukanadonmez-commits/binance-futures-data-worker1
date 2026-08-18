
import json, math, os, time
from datetime import datetime, timezone
from pathlib import Path
import requests
import pandas as pd
import numpy as np

OUT = Path("public")
OUT.mkdir(exist_ok=True)
S = requests.Session()
S.headers.update({"User-Agent":"Mozilla/5.0 github-actions-market-worker/1.0"})
TIMEOUT = 15

BINANCE = "https://fapi.binance.com"
BYBIT = "https://api.bybit.com"
TF_BINANCE = {"15m":"15m","1h":"1h","4h":"4h","1d":"1d"}
TF_BYBIT = {"15m":"15","1h":"60","4h":"240","1d":"D"}
STABLE_BASES = {"USDT","USDC","FDUSD","TUSD","DAI","USDE","USDP","BUSD"}

def get_json(url, params=None):
    r = S.get(url, params=params, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()

def safe_num(x):
    try:
        return float(x)
    except Exception:
        return None

def binance_universe():
    data = get_json(BINANCE + "/fapi/v1/exchangeInfo")
    syms = []
    for x in data.get("symbols", []):
        if (x.get("contractType") == "PERPETUAL"
            and x.get("status") == "TRADING"
            and x.get("quoteAsset") == "USDT"
            and x.get("symbol") != "BTCUSDT"
            and x.get("baseAsset") not in STABLE_BASES):
            syms.append(x["symbol"])
    return syms

def binance_tickers():
    arr = get_json(BINANCE + "/fapi/v1/ticker/24hr")
    out = {}
    for x in arr:
        s = x.get("symbol")
        out[s] = {
            "symbol": s,
            "last": safe_num(x.get("lastPrice")),
            "quoteVolume": safe_num(x.get("quoteVolume")),
            "changePct": safe_num(x.get("priceChangePercent")),
        }
    # bid/ask from bookTicker batch
    try:
        books = get_json(BINANCE + "/fapi/v1/ticker/bookTicker")
        for b in books:
            s = b.get("symbol")
            if s in out:
                out[s]["bid"] = safe_num(b.get("bidPrice"))
                out[s]["ask"] = safe_num(b.get("askPrice"))
    except Exception:
        pass
    return out

def bybit_tickers():
    data = get_json(BYBIT + "/v5/market/tickers", {"category":"linear"})
    out = {}
    for x in data.get("result",{}).get("list",[]):
        s = x.get("symbol")
        out[s] = {
            "symbol":s,
            "last":safe_num(x.get("lastPrice")),
            "quoteVolume":safe_num(x.get("turnover24h")),
            "changePct": (safe_num(x.get("price24hPcnt")) or 0) * 100 if x.get("price24hPcnt") is not None else None,
            "bid":safe_num(x.get("bid1Price")),
            "ask":safe_num(x.get("ask1Price")),
            "openInterest":safe_num(x.get("openInterestValue") or x.get("openInterest")),
            "fundingRate":safe_num(x.get("fundingRate"))
        }
    return out

def klines_binance(symbol, tf, limit=120):
    arr = get_json(BINANCE + "/fapi/v1/klines", {"symbol":symbol,"interval":TF_BINANCE[tf],"limit":limit})
    rows = []
    for k in arr:
        rows.append([int(k[0]), float(k[1]), float(k[2]), float(k[3]), float(k[4]), float(k[5])])
    return pd.DataFrame(rows, columns=["ts","open","high","low","close","volume"])

def klines_bybit(symbol, tf, limit=120):
    data = get_json(BYBIT + "/v5/market/kline", {"category":"linear","symbol":symbol,"interval":TF_BYBIT[tf],"limit":limit})
    arr = data.get("result",{}).get("list",[])
    rows = [[int(k[0]),float(k[1]),float(k[2]),float(k[3]),float(k[4]),float(k[5])] for k in arr]
    rows.sort(key=lambda x:x[0])
    return pd.DataFrame(rows, columns=["ts","open","high","low","close","volume"])

def ema(s,n): return s.ewm(span=n, adjust=False).mean()
def rsi(s,n=14):
    d=s.diff()
    up=d.clip(lower=0).ewm(alpha=1/n, adjust=False).mean()
    dn=(-d.clip(upper=0)).ewm(alpha=1/n, adjust=False).mean()
    rs=up/dn.replace(0,np.nan)
    return 100-(100/(1+rs))
def atr(df,n=14):
    pc=df.close.shift(1)
    tr=pd.concat([(df.high-df.low).abs(),(df.high-pc).abs(),(df.low-pc).abs()],axis=1).max(axis=1)
    return tr.ewm(alpha=1/n, adjust=False).mean()
def adx(df,n=14):
    up=df.high.diff()
    down=-df.low.diff()
    plus_dm=pd.Series(np.where((up>down)&(up>0),up,0.0), index=df.index)
    minus_dm=pd.Series(np.where((down>up)&(down>0),down,0.0), index=df.index)
    a=atr(df,n)
    plus_di=100*(plus_dm.ewm(alpha=1/n,adjust=False).mean()/a.replace(0,np.nan))
    minus_di=100*(minus_dm.ewm(alpha=1/n,adjust=False).mean()/a.replace(0,np.nan))
    dx=100*((plus_di-minus_di).abs()/(plus_di+minus_di).replace(0,np.nan))
    return dx.ewm(alpha=1/n,adjust=False).mean()
def obv(df):
    direction=np.sign(df.close.diff()).fillna(0)
    return (direction*df.volume).cumsum()
def indicators(df):
    if len(df) < 100: raise ValueError("need >=100 candles")
    c=df.close
    e20,e50=ema(c,20),ema(c,50)
    ma99=c.rolling(99).mean()
    rr=rsi(c)
    macd=ema(c,12)-ema(c,26); signal=ema(macd,9)
    aa=atr(df); ax=adx(df)
    mid=c.rolling(20).mean(); sd=c.rolling(20).std()
    upper=mid+2*sd; lower=mid-2*sd
    oo=obv(df)
    typical=(df.high+df.low+df.close)/3
    vwap=(typical*df.volume).cumsum()/df.volume.cumsum().replace(0,np.nan)
    last=-1
    return {
        "candles": int(len(df)),
        "close": float(c.iloc[last]),
        "ma99": float(ma99.iloc[last]),
        "ema20": float(e20.iloc[last]),
        "ema50": float(e50.iloc[last]),
        "rsi14": float(rr.iloc[last]),
        "macd": float(macd.iloc[last]),
        "macdSignal": float(signal.iloc[last]),
        "adx14": float(ax.iloc[last]),
        "atr14": float(aa.iloc[last]),
        "bbUpper": float(upper.iloc[last]),
        "bbMid": float(mid.iloc[last]),
        "bbLower": float(lower.iloc[last]),
        "obv": float(oo.iloc[last]),
        "vwap": float(vwap.iloc[last]),
        "volume": float(df.volume.iloc[last]),
        "volumeAvg20": float(df.volume.rolling(20).mean().iloc[last]),
        "high20": float(df.high.rolling(20).max().iloc[last]),
        "low20": float(df.low.rolling(20).min().iloc[last])
    }

def market_rank(t):
    q=t.get("quoteVolume") or 0
    ch=abs(t.get("changePct") or 0)
    bid=t.get("bid"); ask=t.get("ask")
    spread=999
    if bid and ask and bid>0:
        spread=(ask-bid)/((ask+bid)/2)*10000
    # favor liquidity, movement; penalize wide spreads
    return math.log10(max(q,1))*10 + min(ch,30)*1.5 - min(spread,100)*0.2

def main():
    now=datetime.now(timezone.utc).isoformat()
    health={"generatedAt":now,"universe":False,"batch":False,"ohlcv":False,"source":None,"errors":[]}
    universe=[]
    tick={}
    try:
        universe=binance_universe()
        health["universe"]=len(universe)>0
    except Exception as e:
        health["errors"].append("binance_universe:"+repr(e))
    try:
        tick=binance_tickers()
        health["batch"]=bool(tick)
        health["source"]="binance"
    except Exception as e:
        health["errors"].append("binance_batch:"+repr(e))
        try:
            tick=bybit_tickers()
            health["batch"]=bool(tick)
            health["source"]="bybit"
        except Exception as e2:
            health["errors"].append("bybit_batch:"+repr(e2))
    if not universe and tick:
        universe=[s for s in tick if s.endswith("USDT") and s!="BTCUSDT"]
    ranked=[]
    for s in universe:
        if s in tick and (tick[s].get("quoteVolume") or 0)>0:
            ranked.append((market_rank(tick[s]),s))
    ranked.sort(reverse=True)
    candidates=[s for _,s in ranked[:8]]

    # BTC regime and candidate 4TF, Binance first then Bybit
    deep={}
    for s in ["BTCUSDT"]+candidates:
        tfdata={}
        used=None
        for provider in ("binance","bybit"):
            try:
                for tf in ("1d","4h","1h","15m"):
                    df=klines_binance(s,tf,120) if provider=="binance" else klines_bybit(s,tf,120)
                    tfdata[tf]=indicators(df)
                used=provider
                break
            except Exception as e:
                tfdata={}
                health["errors"].append(f"{s}:{provider}_ohlcv:"+repr(e))
        if tfdata:
            deep[s]={"source":used,"timeframes":tfdata}
    health["ohlcv"]=any(s!="BTCUSDT" for s in deep)
    health["green"]=bool(health["universe"] and health["batch"] and health["ohlcv"] and "BTCUSDT" in deep)
    health["universeCount"]=len(universe)
    health["candidateCount"]=len(candidates)
    health["deepCount"]=sum(1 for s in deep if s!="BTCUSDT")

    result={
        "generatedAt":now,
        "health":health,
        "universeCount":len(universe),
        "preselected":candidates,
        "tickerSource":health["source"],
        "tickers":{s:tick.get(s) for s in candidates if s in tick},
        "btc":deep.get("BTCUSDT"),
        "candidates":{s:deep[s] for s in candidates if s in deep}
    }
    (OUT/"health.json").write_text(json.dumps(health,ensure_ascii=False,indent=2))
    (OUT/"scan.json").write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print(json.dumps(health,indent=2))
    if not health["green"]:
        raise SystemExit(2)

if __name__=="__main__":
    main()
