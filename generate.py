#!/usr/bin/env python3
"""
Taiwan Stock AI Scoring Dashboard — v2.2
Scoring: 獲利品質(20)+成長動能(20)+估值(15)+財務(15)+市場面(10)+風險修正(-10)+類型加成(+5)
Total 0-100. ≥70=買入 | 58-69=觀望 | 45-57=保留 | <45=迴避
"""
import json, sys, datetime
from pathlib import Path
try:
    import yfinance as yf
except ImportError:
    print("Run: pip3 install yfinance"); sys.exit(1)

config     = json.loads(Path("config.json").read_text())
stocks_cfg = config["stocks"]
updated_at = datetime.datetime.now(
    datetime.timezone(datetime.timedelta(hours=8))
).strftime("%Y-%m-%d %H:%M TST")

def score_stock(info, cfg):
    stype = cfg.get("stock_type", "general")
    roe      = (info.get("returnOnEquity")    or 0)*100
    gross_m  = (info.get("grossMargins")      or 0)*100
    op_m     = (info.get("operatingMargins")  or 0)*100
    net_m    = (info.get("profitMargins")     or 0)*100
    rev_gr   = (info.get("revenueGrowth")     or 0)*100
    earn_gr  = (info.get("earningsGrowth")    or 0)*100
    t_pe     = info.get("trailingPE")  or 0
    f_pe     = info.get("forwardPE")   or 0
    pb       = info.get("priceToBook") or 0
    peg      = info.get("pegRatio")    or 0
    debt_eq  = info.get("debtToEquity")      or 0
    curr_r   = info.get("currentRatio")      or 0
    fcf      = info.get("freeCashflow")      or 0
    op_cf    = info.get("operatingCashflow") or 0
    t_cash   = info.get("totalCash")         or 0
    t_debt   = info.get("totalDebt")         or 0
    beta     = info.get("beta")              or 1
    w52c     = info.get("52WeekChange")      or 0
    sp52c    = info.get("SandP52WeekChange") or 0
    vol      = info.get("volume")            or 0
    avg_vol  = info.get("averageVolume")     or 1
    price    = info.get("currentPrice") or info.get("regularMarketPrice") or 0
    w52_hi   = info.get("fiftyTwoWeekHigh")  or price
    w52_lo   = info.get("fiftyTwoWeekLow")   or price
    _dy      = info.get("dividendYield")     or 0
    div_y    = min(_dy if _dy>1 else _dy*100, 25)
    peak     = stype=="cyclical" and roe>20 and gross_m>30
    bd       = {}

    # 1. 獲利品質 (0-20)
    p = 0
    if stype=="growth":
        p += 6 if roe>=15 else 4 if roe>=10 else 2 if roe>=7 else 1 if roe>0 else 0
    else:
        p += 6 if roe>=20 else 4 if roe>=15 else 2 if roe>=10 else 1 if roe>0 else 0
    p += 6 if gross_m>=35 else 4 if gross_m>=25 else 2 if gross_m>=15 else 1 if gross_m>0 else 0
    p += 5 if op_m>=15 else 3 if op_m>=10 else 1 if op_m>=5 else 0
    p += 3 if net_m>=10 else 2 if net_m>=5 else 1 if net_m>0 else 0
    if peak: p=round(p*0.70)
    if stype=="turnaround" and op_m>0 and gross_m>15: p=min(20,p+2)
    bd["profit"]=p=min(20,max(0,p))

    # 2. 成長動能 (0-20)
    g=0
    rv_max=9 if stype=="growth" else 8
    if   rev_gr>=30: g+=rv_max
    elif rev_gr>=20: g+=round(rv_max*0.78)
    elif rev_gr>=10: g+=round(rv_max*0.50)
    elif rev_gr>=5:  g+=round(rv_max*0.25)
    elif rev_gr>=0:  g+=1
    elif rev_gr>=-8 and stype in("value","dividend"): g+=1  # mild decline ok for dividend stocks
    if   earn_gr>=30: g+=7
    elif earn_gr>=15: g+=5
    elif earn_gr>=5:  g+=4
    elif earn_gr>=0:  g+=1
    if f_pe>0 and t_pe>0:
        imp=(t_pe-f_pe)/t_pe*100
        g+=4 if imp>=20 else 3 if imp>=10 else 2 if imp>=0 else 0
    else:
        if   rev_gr>=25 and earn_gr>=0: g+=4
        elif rev_gr>=15 and earn_gr>=0: g+=3
        elif rev_gr>=10:                g+=2
        elif rev_gr>=0:                 g+=1
    if peak: g=round(g*0.70)
    if stype=="turnaround" and rev_gr>0: g=min(20,g+2)
    bd["growth"]=g=min(20,max(0,g))

    # 3. 估值吸引力 (0-15)
    v=0
    pe=t_pe
    # Normalise bad PEG values (Yahoo sometimes returns 40+ for TW stocks)
    if peg>10 or peg<0: peg=0
    # Calculate PEG when missing: prefer forwardPE/rev_gr, fall back to t_pe/rev_gr
    if peg<=0 and rev_gr>0:
        if f_pe>0: peg=f_pe/rev_gr
        elif t_pe>0: peg=t_pe/rev_gr
    if stype=="growth":
        v+=5 if 0<pe<=20 else 4 if pe<=30 else 3 if pe<=40 else 1 if pe<=55 else 0
        v+=4 if 0<pb<=2  else 3 if pb<=4  else 1 if pb<=6  else 0
        v+=6 if 0<peg<0.8 else 5 if peg<1 else 4 if peg<1.3 else 2 if peg<1.7 else 0
    elif stype=="cyclical":
        # Cyclicals in recovery have distorted trailing PE; use forwardPE as primary
        pe_v=f_pe if f_pe>0 else t_pe
        peg_v=pe_v/rev_gr if pe_v>0 and rev_gr>0 else 0
        v+=6 if 0<pb<=1.0 else 5 if pb<=1.5 else 3 if pb<=2.5 else 1 if pb<=4 else 0
        v+=5 if 0<pe_v<=8 else 3 if pe_v<=12 else 2 if pe_v<=18 else 1 if pe_v<=25 else 0
        v+=4 if 0<peg_v<1  else 2 if peg_v<1.5 else 0
    elif stype=="turnaround":
        v+=5 if 0<pb<=1.5 else 4 if pb<=2.5 else 2 if pb<=4 else 0
        if f_pe>0 and (t_pe<=0 or f_pe<t_pe*0.8): v+=5
        elif rev_gr>0 and earn_gr>0: v+=4
        elif rev_gr>0: v+=2
        v+=5 if 0<peg<0.8 else 3 if peg<1.5 else 0
    else:
        v+=6 if 0<pe<=12 else 5 if pe<=15 else 3 if pe<=20 else 2 if pe<=28 else 1 if pe<=35 else 0
        v+=5 if 0<pb<=1 and roe>=10 else 4 if pb<=1.5 else 3 if pb<=2.5 else 1 if pb<=4 else 0
        v+=4 if 0<peg<0.8 else 3 if peg<1 else 2 if peg<1.5 else 1 if peg<2 else 0
    bd["valuation"]=v=min(15,max(0,v))

    # 4. 財務體質 (0-15)
    f=0
    f+=4 if debt_eq<=30 else 3 if debt_eq<=60 else 2 if debt_eq<=100 else 1 if debt_eq<=150 else 0
    f+=3 if curr_r>=2.5 else 2 if curr_r>=1.5 else 1 if curr_r>=1.0 else 0
    if   fcf>0 and op_cf>0: f+=4
    elif op_cf>0:            f+=2
    elif fcf>0:              f+=1
    if   t_debt==0 or t_cash>=t_debt*1.5: f+=4
    elif t_cash>=t_debt:                   f+=3
    elif t_cash>=t_debt*0.5:               f+=2
    elif t_cash>=t_debt*0.25:              f+=1
    bd["financial"]=f=min(15,max(0,f))

    # 5. 市場面 (0-10)
    m=0
    rng=w52_hi-w52_lo
    if rng>0:
        pos=(price-w52_lo)/rng
        m+=3 if pos>=0.7 else 2 if pos>=0.4 else 1 if pos>=0.2 else 0
    m+=2 if 0.5<=beta<=1.3 else 1 if 0.3<=beta<=1.8 else 0
    vr=vol/avg_vol if avg_vol>0 else 1
    m+=3 if vr>=1.5 else 2 if vr>=1.0 else 1 if vr>=0.6 else 0
    m+=2 if w52c>sp52c+0.10 else 1 if w52c>sp52c else 0
    bd["market"]=m=min(10,max(0,m))

    # 6. 風險修正 (-10 to 0)
    r=0
    if peak:                          r-=4
    if   debt_eq>200:                 r-=3
    elif debt_eq>150:                 r-=2
    elif debt_eq>100:                 r-=1
    if 0<pe<10 and rev_gr<0:                          r-=3
    if pe>50 and rev_gr<15 and stype!="cyclical":    r-=2
    if fcf<0 and debt_eq>100:         r-=2
    if div_y>10 and earn_gr<0:        r-=1
    bd["risk"]=r=max(-10,r)

    # 7. 類型加成 (0-5)
    t=0
    if stype=="growth":
        if   rev_gr>=30 and gross_m>=30 and op_m>=10: t=5
        elif rev_gr>=20 and gross_m>=25:               t=3
        elif rev_gr>=10:                               t=1
    elif stype=="turnaround":
        if   rev_gr>0 and op_m>0 and earn_gr>0: t=4
        elif rev_gr>0 and op_m>0:               t=2
    elif stype in("value","dividend"):
        if   div_y>=5 and debt_eq<=80 and curr_r>=1.5: t=5
        elif div_y>=4 and debt_eq<=80:                  t=3
        elif div_y>=3:                                   t=1
    bd["type_adj"]=t

    total=max(0,min(100,round(p+g+v+f+m+r+t)))
    bd["total"]=total
    tag="buy" if total>=70 else "watch" if total>=58 else "hold" if total>=45 else "avoid"
    return total,tag,bd

def make_ring(score, tag):
    """SVG circular progress ring for the AI total score (44×44px)."""
    tag_colors = {"buy": "#16a34a", "watch": "#2563eb", "hold": "#d97706", "avoid": "#dc2626"}
    col = tag_colors.get(tag, "#78716c")
    circ = 113.1  # 2π×18
    dash_len = round(score / 100 * circ, 1)
    gap_len  = round(circ - dash_len, 1)
    return (
        f'<div style="position:relative;width:44px;height:44px;flex-shrink:0;">'
        f'<svg width="44" height="44" style="transform:rotate(-90deg)">'
        f'<circle cx="22" cy="22" r="18" fill="none" stroke="#e5ded5" stroke-width="3.5"/>'
        f'<circle cx="22" cy="22" r="18" fill="none" stroke="{col}" stroke-width="3.5"'
        f' stroke-linecap="round"'
        f' stroke-dasharray="{dash_len} {gap_len}"/>'
        f'</svg>'
        f'<span style="position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);'
        f'font-size:13px;font-weight:700;color:{col};">{score}</span>'
        f'</div>'
    )

def make_bar(val, max_val):
    """Score cell with 'val /max' notation and thin coloured bar underneath."""
    pct = round(val / max_val * 100) if max_val > 0 else 0
    if   pct >= 70: col = "#16a34a"
    elif pct >= 58: col = "#2563eb"
    elif pct >= 45: col = "#d97706"
    else:           col = "#dc2626"
    return (
        f'<div style="text-align:center;min-width:46px;">'
        f'<div style="white-space:nowrap;">'
        f'<span style="color:{col};font-weight:700;font-size:12px;">{val}</span>'
        f'<span style="color:#78716c;font-size:11px;"> /{max_val}</span>'
        f'</div>'
        f'<div style="height:3px;border-radius:2px;background:#e5ded5;margin-top:3px;overflow:hidden;">'
        f'<div style="width:{pct}%;height:100%;background:{col};border-radius:2px;"></div>'
        f'</div>'
        f'</div>'
    )

def fetch_stock(cfg):
    symbol=cfg["ticker"]+".TW"
    try:
        tk=yf.Ticker(symbol)
        info=tk.info
        price=info.get("currentPrice") or info.get("regularMarketPrice") or 0
        prev =info.get("regularMarketPreviousClose") or price
        change=round(price-prev,2)
        chg_pct=round((change/prev*100) if prev else 0,2)
        mc=info.get("marketCap",0)
        _dy=info.get("dividendYield") or 0
        div=round(_dy if _dy>1 else _dy*100,2)
        if   mc>=1e12: cap=f"{mc/1e12:.1f}兆"
        elif mc>=1e8:  cap=f"{mc/1e8:.0f}億"
        elif mc>=1e6:  cap=f"{mc/1e6:.0f}百萬"
        else:           cap="—"
        ai,tag,bd=score_stock(info,cfg)
        # Fetch 6-month daily price history for the detail chart
        try:
            import math as _math
            hist=tk.history(period="6mo")
            if not hist.empty:
                pairs=[(d.strftime("%m/%d"),round(float(c),2))
                       for d,c in zip(hist.index,hist["Close"])
                       if not _math.isnan(float(c)) and float(c)>0]
                price_dates=[p[0] for p in pairs]
                price_closes=[p[1] for p in pairs]
            else:
                price_dates=[]; price_closes=[]
        except Exception:
            price_dates=[]; price_closes=[]
        return {
            **cfg,
            "price":round(price,2),"change":change,"changePct":chg_pct,"mktCap":cap,
            "pe":round(info.get("trailingPE") or 0,1),
            "pb":round(info.get("priceToBook") or 0,2),
            "roe":round((info.get("returnOnEquity") or 0)*100,1),
            "eps":round(info.get("trailingEps") or 0,2),
            "div":div,
            "revGrowth":round((info.get("revenueGrowth") or 0)*100,1),
            "grossMargin":round((info.get("grossMargins") or 0)*100,1),
            "opMargin":round((info.get("operatingMargins") or 0)*100,1),
            "ai":ai,"tag":tag,
            "fin":bd["profit"],"growth_s":bd["growth"],"valuation":bd["valuation"],
            "financial":bd["financial"],"market":bd["market"],
            "risk":bd["risk"],"typeAdj":bd["type_adj"],
            "radar":[ai,
                     round(bd["profit"]/20*100),
                     round(bd["growth"]/20*100),
                     round(bd["valuation"]/15*100),
                     round(bd["financial"]/15*100),
                     round(bd["market"]/10*100)],
            "price_dates":price_dates,
            "price_closes":price_closes,
            "ai_ring":    make_ring(ai, tag),
            "ai_bar":     make_bar(ai,               100),
            "fin_bar":    make_bar(bd["profit"],       20),
            "growth_bar": make_bar(bd["growth"],       20),
            "val_bar":    make_bar(bd["valuation"],    15),
            "financial_bar": make_bar(bd["financial"], 15),
            "market_bar": make_bar(bd["market"],       10),
            "ok":True,
        }
    except Exception as e:
        print(f"  ⚠ {cfg['ticker']}: {e}")
        return {**cfg,"price":0,"change":0,"changePct":0,"mktCap":"—",
                "pe":0,"pb":0,"roe":0,"eps":0,"div":0,"revGrowth":0,"grossMargin":0,"opMargin":0,
                "ai":0,"tag":"—","fin":0,"growth_s":0,"valuation":0,"financial":0,"market":0,
                "risk":0,"typeAdj":0,"radar":[0]*6,
                "price_dates":[],"price_closes":[],
                "ai_ring":make_ring(0,"avoid"),
                "ai_bar":make_bar(0,100),"fin_bar":make_bar(0,20),"growth_bar":make_bar(0,20),
                "val_bar":make_bar(0,15),"financial_bar":make_bar(0,15),"market_bar":make_bar(0,10),
                "ok":False}

print("Fetching stock data...")
stocks=[]
for cfg in stocks_cfg:
    print(f"  {cfg['ticker']} {cfg['name']}...")
    stocks.append(fetch_stock(cfg))

main_s  =[s for s in stocks if s["type"]=="main"]
watch_s =[s for s in stocks if s["type"]=="watch"]
combined=main_s+watch_s

def sc(s): return "a" if s>=80 else "b" if s>=70 else "c" if s>=60 else "d"
def tag_html(t):
    labels = {"buy":"買入","watch":"觀望","hold":"保留","avoid":"迴避","—":"—"}
    styles = {
        "buy":   ("dcfce7","16a34a"),
        "watch": ("dbeafe","2563eb"),
        "hold":  ("fef3c7","d97706"),
        "avoid": ("fee2e2","dc2626"),
    }
    label = labels.get(t, t)
    if t in styles:
        bg, col = styles[t]
        return (f'<span style="padding:3px 10px;border-radius:20px;background:#{bg};'
                f'color:#{col};font-size:11px;font-weight:600;">● {label}</span>')
    return f'<span style="padding:3px 10px;border-radius:20px;background:#f0ebe3;color:#78716c;font-size:11px;font-weight:600;">{label}</span>'
def ch_html(v,p):
    c="pos" if v>=0 else "neg";s="+" if v>=0 else ""
    return f'<span class="ch-{c}">{s}{v:.2f} ({s}{p:.2f}%)</span>'
def s_bar(s,w=80):
    c=sc(s)
    return(f'<div class="sbw"><div class="sb" style="width:{w}px">'
           f'<div class="sf fill-{c}" style="width:{s}%"></div></div>'
           f'<span class="sn score-{c}">{s}</span></div>')
def type_badge(t):
    m={"growth":"成長股","value":"價值股","cyclical":"循環股",
       "turnaround":"轉型股","dividend":"存股型","general":"一般型"}
    return f'<span class="tbadge tb-{t}">{m.get(t,"—")}</span>'
def cfg_act_btns(ticker, cur_type):
    """Compact move & delete buttons for config.json (static) rows."""
    s = 'padding:2px 7px;border-radius:5px;border:1px solid '
    mv = lambda label, to, col: (
        f'<button onclick="moveConfig(\'{ticker}\',\'{to}\')" '
        f'style="{s}{col};background:transparent;color:{col};'
        f'font-size:10px;cursor:pointer;white-space:nowrap;">{label}</button>')
    rm = (f'<button onclick="removeConfig(\'{ticker}\')" title="移除" '
          f'style="{s}var(--border);background:transparent;color:var(--muted);'
          f'font-size:10px;cursor:pointer;">✕</button>')
    if cur_type == "main":
        btns = f'{mv("↓觀望","watch","var(--blue)")} {mv("↓學習","learning","var(--muted)")} {rm}'
    elif cur_type == "watch":
        btns = f'{mv("↑持股","main","var(--green)")} {mv("↓學習","learning","var(--muted)")} {rm}'
    else:
        btns = f'{mv("↑觀望","watch","var(--blue)")} {mv("↑持股","main","var(--green)")} {rm}'
    return f'<div style="display:flex;gap:3px;margin-top:4px;flex-wrap:wrap;">{btns}</div>'

def table_rows(lst):
    rows=""
    for s in lst:
        acts = cfg_act_btns(s["ticker"], s.get("type","watch"))
        rows+=f'''<tr data-cfg="{s["ticker"]}">
          <td><span class="cn">{s["name"]}</span><span class="tic">{s["ticker"]}</span>
            <div style="margin-top:3px;display:flex;gap:4px;align-items:center;">
              {type_badge(s.get("stock_type","general"))}
              <span style="color:var(--muted);font-size:10px;">&nbsp;{s["sector"]}</span>
            </div></td>
          <td>{s["ai_ring"]}</td><td>{s["fin_bar"]}</td>
          <td>{s["growth_bar"]}</td><td>{s["val_bar"]}</td>
          <td>{s["financial_bar"]}</td><td>{s["market_bar"]}</td>
          <td style="font-weight:600;">NT${s["price"]:.2f}</td>
          <td>{ch_html(s["change"],s["changePct"])}</td>
          <td style="color:var(--muted);font-size:12px;">{s["mktCap"]}</td>
          <td>{tag_html(s["tag"])}</td>
          <td><button class="drill" onclick="openDetail('{s["ticker"]}')">詳情 →</button>{acts}</td>
        </tr>'''
    return rows

stocks_json=json.dumps(stocks,ensure_ascii=False)

html=f'''<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate">
<meta http-equiv="Pragma" content="no-cache"><meta http-equiv="Expires" content="0">
<title>台股AI研究儀表板</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2"></script>
<style>
:root{{--bg:#f7f3ed;--bg2:#ffffff;--bg3:#f0ebe3;--border:#e5ded5;--text:#1c1917;
      --fg:#1c1917;--muted:#78716c;--green:#16a34a;--red:#dc2626;--yellow:#d97706;
      --blue:#2563eb;--purple:#7c3aed;--accent:#2563eb}}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:var(--bg);color:var(--text);font-family:'Segoe UI',system-ui,sans-serif;font-size:14px}}
nav{{background:var(--bg2);border-bottom:1px solid var(--border);padding:0 24px;
     display:flex;align-items:center;gap:8px;height:52px;position:sticky;top:0;z-index:100}}
.logo{{font-size:16px;font-weight:700;color:var(--blue);margin-right:12px;white-space:nowrap}}
.ntab{{padding:6px 14px;border-radius:6px;cursor:pointer;color:var(--muted);font-size:13px;
       border:1px solid transparent;transition:all .15s}}
.ntab:hover{{color:var(--text);background:var(--bg3)}}
.ntab.active{{color:var(--blue);background:rgba(37,99,235,.1);border-color:rgba(37,99,235,.3)}}
.spacer{{flex:1}}
main{{padding:20px 24px}}
.sh{{display:flex;align-items:center;gap:10px;margin-bottom:14px}}
.sh h2{{font-size:16px;font-weight:600}}
.badge{{padding:2px 8px;border-radius:4px;font-size:11px;font-weight:600}}
.bm{{background:rgba(22,163,74,.12);color:var(--green);border:1px solid rgba(22,163,74,.3)}}
.bw{{background:rgba(37,99,235,.12);color:var(--blue);border:1px solid rgba(37,99,235,.3)}}
.fbar{{display:flex;gap:8px;margin-bottom:18px;flex-wrap:wrap;align-items:center}}
.fbtn{{padding:5px 12px;border-radius:20px;border:1px solid var(--border);
       background:var(--bg2);color:var(--muted);cursor:pointer;font-size:12px;transition:all .2s}}
.fbtn:hover{{border-color:var(--blue);color:var(--blue)}}
.fbtn.active{{background:var(--accent);border-color:var(--accent);color:#fff}}
.fbtn.active-buy{{background:rgba(22,163,74,.1);border-color:rgba(22,163,74,.5);color:#16a34a;
  box-shadow:0 0 8px rgba(22,163,74,.25)}}
.fbtn.active-watch{{background:rgba(37,99,235,.1);border-color:rgba(37,99,235,.5);color:#2563eb;
  box-shadow:0 0 8px rgba(37,99,235,.25)}}
.fbtn.active-hold{{background:rgba(217,119,6,.1);border-color:rgba(217,119,6,.5);color:#d97706;
  box-shadow:0 0 8px rgba(217,119,6,.25)}}
.sw{{background:var(--bg2);border:1px solid var(--border);border-radius:10px;
     overflow:hidden;margin-bottom:28px;overflow-x:auto}}
.sw table{{width:100%;border-collapse:collapse;min-width:860px}}
.sw table td:last-child,.sw table th:last-child{{position:sticky;right:0;
  background:var(--bg2);box-shadow:-4px 0 8px rgba(0,0,0,.06);z-index:1}}
.sw table tr:hover td:last-child{{background:var(--bg3)}}
.sw th{{background:#f0ebe3;color:var(--muted);font-size:10px;font-weight:600;
        text-transform:uppercase;letter-spacing:.4px;padding:9px 12px;
        text-align:left;border-bottom:1px solid var(--border)}}
.sw td{{padding:10px 12px;border-bottom:1px solid var(--border);vertical-align:middle;background:#ffffff}}
.sw tr:last-child td{{border-bottom:none}}
.sw tr:hover td{{background:#faf8f5}}
.cn{{font-weight:600;font-size:13px}}.tic{{color:var(--muted);font-size:11px;margin-left:5px}}
.tbadge{{padding:1px 6px;border-radius:3px;font-size:10px;font-weight:600}}
.tb-growth{{background:rgba(37,99,235,.1);color:var(--blue)}}
.tb-value{{background:rgba(22,163,74,.1);color:var(--green)}}
.tb-cyclical{{background:rgba(217,119,6,.1);color:var(--yellow)}}
.tb-turnaround{{background:rgba(124,58,237,.1);color:var(--purple)}}
.tb-dividend,.tb-general{{background:rgba(120,113,108,.1);color:var(--muted)}}
.sbw{{border-radius:5px;padding:4px 8px;min-width:90px}}
.score-a{{color:#16a34a}}.score-b{{color:#2563eb}}.score-c{{color:#d97706}}.score-d{{color:#dc2626}}
.score-buy{{color:#16a34a}}.score-watch{{color:#2563eb}}.score-hold{{color:#d97706}}.score-avoid{{color:#dc2626}}
.sn{{font-size:13px;font-weight:700;white-space:nowrap}}.sn-max{{font-size:10px;font-weight:400;opacity:.6}}
.ch-pos{{color:var(--green)}}.ch-neg{{color:var(--red)}}
.tag{{display:inline-block;padding:3px 10px;border-radius:20px;font-size:11px;font-weight:600}}
.tag-buy{{background:#dcfce7;color:#16a34a}}
.tag-watch{{background:#dbeafe;color:#2563eb}}
.tag-hold{{background:#fef3c7;color:#d97706}}
.tag-avoid{{background:#fee2e2;color:#dc2626}}
.tag-empty{{background:#f0ebe3;color:#78716c}}
.drill{{padding:4px 10px;border-radius:5px;border:1px solid var(--border);
        background:var(--bg3);color:var(--muted);font-size:11px;cursor:pointer;transition:all .15s}}
.drill:hover{{border-color:var(--blue);color:var(--blue);background:rgba(37,99,235,.06)}}
.mgrid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(148px,1fr));gap:12px;margin-bottom:20px}}
.mc{{background:var(--bg2);border:1px solid var(--border);border-radius:8px;padding:14px}}
.ml{{color:var(--muted);font-size:11px;margin-bottom:5px}}
.mv{{font-size:18px;font-weight:700}}.ms{{color:var(--muted);font-size:11px;margin-top:3px}}
.sbc{{background:var(--bg2);border:1px solid var(--border);border-radius:8px;padding:16px;margin-bottom:16px}}
.sbc h3{{font-size:13px;font-weight:600;margin-bottom:14px}}
.sbi{{display:flex;align-items:center;gap:10px;margin-bottom:10px}}
.sbi-label{{color:var(--muted);font-size:12px;width:90px;flex-shrink:0}}
.sbi-bar{{flex:1;height:8px;background:var(--bg3);border-radius:4px;overflow:hidden}}
.sbi-fill{{height:100%;border-radius:4px}}
.sbi-score{{font-size:13px;font-weight:700;width:28px;text-align:right}}
.sbi-max{{color:var(--muted);font-size:10px;width:28px}}
.sbi-note{{color:var(--muted);font-size:10px;margin-left:4px;flex:1}}
.crow{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:16px;margin-bottom:20px}}
.cc{{background:var(--bg2);border:1px solid var(--border);border-radius:8px;padding:16px}}
.cc h3{{font-size:13px;color:var(--muted);margin-bottom:12px;font-weight:600}}
.ch{{position:relative;height:200px}}
.rgrid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:16px}}
.rc{{background:var(--bg2);border:1px solid var(--border);border-radius:8px;padding:16px}}
.ain{{background:#ffffff;border:1px solid var(--border);border-radius:8px;padding:16px;margin-bottom:16px}}
.ain h3{{font-size:13px;font-weight:600;margin-bottom:8px}}
.tleg{{display:flex;gap:16px;flex-wrap:wrap;margin-bottom:18px}}
.tleg-i{{display:flex;align-items:center;gap:6px;font-size:12px;color:var(--muted)}}
.tdot{{width:10px;height:10px;border-radius:50%}}
.back{{padding:6px 14px;border-radius:6px;border:1px solid var(--border);background:#ffffff;
       color:var(--text);cursor:pointer;font-size:13px;display:inline-flex;align-items:center;gap:6px}}
.back:hover{{border-color:var(--blue);color:var(--blue)}}
::-webkit-scrollbar{{width:6px;height:6px}}
::-webkit-scrollbar-track{{background:var(--bg3)}}
::-webkit-scrollbar-thumb{{background:var(--border);border-radius:3px}}
@media(max-width:900px){{.crow{{grid-template-columns:1fr 1fr}}}}
@media(max-width:600px){{.crow{{grid-template-columns:1fr}};main{{padding:14px}};nav{{padding:0 12px}}}}
</style>
</head>
<body>
<nav>
  <div class="logo">📊 台股AI研究</div>
  <div class="ntab active" onclick="show('overview')">總覽</div>
  <div class="ntab" onclick="show('comparison')">雷達比較</div>
  <div class="ntab" onclick="show('legend')">評分說明</div>
  <div class="spacer"></div>
  <div style="position:relative;display:flex;align-items:center;">
    <span style="position:absolute;left:9px;color:var(--muted);font-size:13px;pointer-events:none;">🔍</span>
    <input id="srch" type="text" placeholder="代號 / 名稱" autocomplete="off"
      oninput="doSearch(this.value)"
      onkeydown="if(event.key==='Escape'){{this.value='';doSearch('')}}"
      style="background:var(--bg);border:1px solid var(--border);border-radius:20px;
             padding:5px 12px 5px 28px;font-size:12px;color:var(--fg);width:160px;
             outline:none;transition:border-color .15s;"
      onfocus="this.style.borderColor='var(--blue)'"
      onblur="this.style.borderColor='var(--border)'">
  </div>
  <div style="color:var(--muted);font-size:11px;margin-left:14px;">更新：{updated_at}</div>
</nav>
<main>
<div id="p-overview">
  <div class="tleg">
    <div class="tleg-i"><div class="tdot" style="background:var(--green)"></div>≥70 買入</div>
    <div class="tleg-i"><div class="tdot" style="background:var(--blue)"></div>58–69 觀望</div>
    <div class="tleg-i"><div class="tdot" style="background:var(--yellow)"></div>45–57 保留</div>
    <div class="tleg-i"><div class="tdot" style="background:var(--red)"></div>&lt;45 迴避</div>
    <div class="tleg-i" style="margin-left:10px;padding-left:10px;border-left:1px solid var(--border);">
      <span class="tbadge tb-growth">成長股</span>&nbsp;
      <span class="tbadge tb-value">價值股</span>&nbsp;
      <span class="tbadge tb-cyclical">循環股</span>&nbsp;
      <span class="tbadge tb-turnaround">轉型股</span>
    </div>
  </div>
  <div class="fbar">
    <span style="color:var(--muted);font-size:12px;">篩選：</span>
    <button class="fbtn active" onclick="filt('all',this)">全部 {len(combined)}</button>
    <button class="fbtn" onclick="filt('main',this)">主要持股 {len(main_s)}</button>
    <button class="fbtn" onclick="filt('watch',this)">觀望清單 {len(watch_s)}</button>
    <button class="fbtn" onclick="filt('buy',this)" data-glow="active-buy">
      <span style="display:inline-block;width:7px;height:7px;border-radius:50%;background:#16a34a;margin-right:5px;vertical-align:middle;"></span>買入 ≥70</button>
    <button class="fbtn" onclick="filt('wtag',this)" data-glow="active-watch">
      <span style="display:inline-block;width:7px;height:7px;border-radius:50%;background:#2563eb;margin-right:5px;vertical-align:middle;"></span>觀望 58-69</button>
    <button class="fbtn" onclick="filt('hold',this)" data-glow="active-hold">
      <span style="display:inline-block;width:7px;height:7px;border-radius:50%;background:#d97706;margin-right:5px;vertical-align:middle;"></span>保留/迴避</button>
    <span style="margin-left:auto;color:var(--muted);font-size:12px;">點擊「詳情」查看評分細項</span>
  </div>
  <div class="sh"><h2>主要持股</h2><span class="badge bm">{len(main_s)} 檔</span></div>
  <div class="sw"><table>
    <thead><tr><th>代號／名稱</th><th>AI總分</th><th>獲利品質</th><th>成長動能</th>
      <th>估值</th><th>財務</th><th>市場面</th><th>現價</th><th>漲跌</th><th>市值</th><th>建議</th><th></th></tr></thead>
    <tbody id="tb-main">{table_rows(main_s)}</tbody>
    <tbody id="tb-main-local"></tbody>
  </table></div>
  <div class="sh"><h2>觀望清單</h2><span class="badge bw">{len(watch_s)} 檔</span></div>
  <div class="sw"><table>
    <thead><tr><th>代號／名稱</th><th>AI總分</th><th>獲利品質</th><th>成長動能</th>
      <th>估值</th><th>財務</th><th>市場面</th><th>現價</th><th>漲跌</th><th>市值</th><th>建議</th><th></th></tr></thead>
    <tbody id="tb-watch">{table_rows(watch_s)}</tbody>
    <tbody id="tb-watch-local"></tbody>
  </table></div>
  <div class="sh">
    <h2>學習清單</h2>
    <span class="badge" id="badge-learning" style="background:rgba(161,161,169,.15);color:#a1a1a9;">0 檔</span>
    <button onclick="toggleAddBox()" id="add-btn"
      style="margin-left:auto;padding:5px 14px;border-radius:20px;border:1px solid var(--blue);
             background:rgba(88,166,255,.1);color:var(--blue);font-size:12px;cursor:pointer;">
      ＋ 新增學習股
    </button>
  </div>
  <div id="add-box" style="display:none;background:var(--bg2);border:1px solid var(--border);
       border-radius:10px;padding:14px 16px;margin-bottom:16px;">
    <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;">
      <div style="position:relative;flex:1;min-width:180px;max-width:320px;">
        <span style="position:absolute;left:9px;top:50%;transform:translateY(-50%);
                     color:var(--muted);pointer-events:none;font-size:13px;">🔍</span>
        <input id="add-srch" type="text" placeholder="輸入代號或名稱…" autocomplete="off"
          oninput="addFilter(this.value)"
          onkeydown="if(event.key==='Escape')toggleAddBox()"
          style="width:100%;background:var(--bg);border:1px solid var(--border);border-radius:8px;
                 padding:7px 12px 7px 30px;font-size:13px;color:var(--fg);box-sizing:border-box;outline:none;"
          onfocus="this.style.borderColor='var(--blue)'" onblur="this.style.borderColor='var(--border)'">
      </div>
      <span style="color:var(--muted);font-size:12px;">或直接輸入台股代號</span>
      <button onclick="toggleAddBox()"
        style="padding:5px 12px;border-radius:8px;border:1px solid var(--border);
               background:transparent;color:var(--muted);font-size:12px;cursor:pointer;">✕ 關閉</button>
    </div>
    <div id="add-results" style="margin-top:10px;display:flex;flex-wrap:wrap;gap:8px;"></div>
  </div>
  <div class="sw"><table>
    <thead><tr><th>代號／名稱</th><th>AI總分</th><th>獲利品質</th><th>成長動能</th>
      <th>估值</th><th>財務</th><th>市場面</th><th>現價</th><th>漲跌</th><th>市值</th><th>建議</th><th></th></tr></thead>
    <tbody id="tb-learning"><tr><td colspan="12" style="text-align:center;color:var(--muted);padding:24px;font-size:13px;">
      暫無學習股 — 點擊「＋ 新增學習股」開始探索</td></tr></tbody>
  </table></div>
</div>

<div id="p-comparison" style="display:none">
  <div class="sh" style="margin-bottom:4px"><h2>AI 六維雷達比較</h2></div>
  <div id="radar-sec-main">
    <div class="sw-hdr" style="margin:16px 0 10px;">
      <span style="font-weight:600;font-size:14px;">主要持股</span>
      <span class="badge bm" id="rc-badge-main" style="margin-left:8px;">—</span>
    </div>
    <div class="rgrid" id="radar-main"></div>
  </div>
  <div id="radar-sec-watch">
    <div class="sw-hdr" style="margin:20px 0 10px;">
      <span style="font-weight:600;font-size:14px;">觀望清單</span>
      <span class="badge bw" id="rc-badge-watch" style="margin-left:8px;">—</span>
    </div>
    <div class="rgrid" id="radar-watch"></div>
  </div>
  <div id="radar-sec-learn">
    <div class="sw-hdr" style="margin:20px 0 10px;">
      <span style="font-weight:600;font-size:14px;">學習清單</span>
      <span class="badge" style="background:#f0ebe3;color:#78716c;padding:2px 8px;border-radius:4px;font-size:11px;font-weight:600;margin-left:8px;" id="rc-badge-learn">—</span>
    </div>
    <div class="rgrid" id="radar-learn"></div>
  </div>
</div>

<div id="p-legend" style="display:none">
  <div class="sh" style="margin-bottom:20px"><h2>📐 AI 評分邏輯說明</h2></div>
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;max-width:920px;">
    <div class="ain"><h3>1. 獲利品質（滿分 20）</h3><p style="color:var(--muted);font-size:12px;line-height:1.9;margin-top:8px;">
      ROE（6分）成長股≥15%滿分；一般股≥20%滿分<br>毛利率（6分）≥35%→6；≥25%→4；≥15%→2<br>
      營業利益率（5分）≥15%→5；≥10%→3<br>淨利率（3分）≥10%→3；≥5%→2<br>
      <span style="color:var(--yellow)">⚠ 循環股景氣高峰整體打7折</span><br>
      <span style="color:var(--purple)">✦ 轉型股本業轉正加+2趨勢分</span></p></div>
    <div class="ain"><h3>2. 成長動能（滿分 20）</h3><p style="color:var(--muted);font-size:12px;line-height:1.9;margin-top:8px;">
      營收年增率（9分）≥30%→9；≥20%→7；≥10%→4<br>EPS年增率（7分）≥30%→7；≥15%→5；≥5%→4<br>
      前瞻動能（4分）預估PE可得則直接計算；否則以高營收+正EPS替代<br>
      <span style="color:var(--purple)">✦ 轉型股三指標改善加+2分</span></p></div>
    <div class="ain"><h3>3. 估值吸引力（滿分 15）</h3><p style="color:var(--muted);font-size:12px;line-height:1.9;margin-top:8px;">
      成長股：以PEG為主（PEG&lt;1→高分），允許高PE<br>循環股：以P/B為主，低PE在高峰期是陷阱<br>
      轉型股：P/B支撐＋預估獲利改善趨勢<br>價值股：PE＋PB＋PEG三指標並重</p></div>
    <div class="ain"><h3>4. 財務體質（滿分 15）</h3><p style="color:var(--muted);font-size:12px;line-height:1.9;margin-top:8px;">
      負債比（4分）≤30%→4；≤60%→3；≤100%→2<br>流動比率（3分）≥2.5→3；≥1.5→2<br>
      自由現金流（4分）FCF+OpCF皆正→4；OpCF正→2<br>現金覆蓋率（4分）現金≥負債1.5倍→4</p></div>
    <div class="ain"><h3>5. 市場面（滿分 10）</h3><p style="color:var(--muted);font-size:12px;line-height:1.9;margin-top:8px;">
      52週區間位置（3分）靠近高點=動能強<br>Beta穩定性（2分）0.5–1.3最佳<br>
      成交量vs均量（3分）放量=市場關注<br>相對大盤超額報酬（2分）</p></div>
    <div class="ain"><h3>6. 風險扣分（-10）＋類型加成（+5）</h3><p style="color:var(--muted);font-size:12px;line-height:1.9;margin-top:8px;">
      <span style="color:var(--red)">循環高峰-4 ／估值陷阱-3 ／過度槓桿-2~3</span><br>
      <span style="color:var(--green)">成長股高品質確認+3~+5</span><br>
      <span style="color:var(--purple)">轉型三指標同步改善+4</span><br>
      <span style="color:var(--green)">高殖利率防禦型+1~+3</span></p></div>
  </div>
  <div class="ain" style="max-width:920px;margin-top:4px;"><h3>📊 分數門檻</h3>
    <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-top:12px;">
      <div style="background:#dcfce7;border:1px solid rgba(22,163,74,.3);border-radius:6px;padding:12px;">
        <div style="font-size:20px;font-weight:700;color:#16a34a;">≥70</div>
        <div style="font-weight:600;margin:4px 0;">🟢 買入</div>
        <div style="color:var(--muted);font-size:11px;">體質優良，值得積極布局</div></div>
      <div style="background:#dbeafe;border:1px solid rgba(37,99,235,.3);border-radius:6px;padding:12px;">
        <div style="font-size:20px;font-weight:700;color:#2563eb;">58–69</div>
        <div style="font-weight:600;margin:4px 0;">🔵 觀望</div>
        <div style="color:var(--muted);font-size:11px;">有亮點但需等待催化劑</div></div>
      <div style="background:#fef3c7;border:1px solid rgba(217,119,6,.3);border-radius:6px;padding:12px;">
        <div style="font-size:20px;font-weight:700;color:#d97706;">45–57</div>
        <div style="font-weight:600;margin:4px 0;">🟡 保留</div>
        <div style="color:var(--muted);font-size:11px;">普通，低優先追蹤</div></div>
      <div style="background:#fee2e2;border:1px solid rgba(220,38,38,.3);border-radius:6px;padding:12px;">
        <div style="font-size:20px;font-weight:700;color:#dc2626;">&lt;45</div>
        <div style="font-weight:600;margin:4px 0;">🔴 迴避</div>
        <div style="color:var(--muted);font-size:11px;">風險大於機會</div></div>
    </div>
  </div>
  <div class="ain" style="max-width:920px;margin-top:4px;">
    <h3>🗂 資料來源與計算週期</h3>
    <div style="margin-top:12px;display:grid;grid-template-columns:1fr 1fr;gap:12px;">
      <div style="background:var(--bg3);border:1px solid var(--border);border-radius:8px;padding:14px;">
        <div style="font-size:11px;font-weight:700;color:var(--blue);letter-spacing:.5px;margin-bottom:10px;">📡 搜尋資料庫</div>
        <div style="font-size:12px;color:var(--muted);line-height:1.9;">
          <span style="color:var(--text)">來源：</span>Supabase（本地資料庫）<br>
          <span style="color:var(--text)">內容：</span>TWSE 上市 ＋ TPEX 上櫃約 39,000 檔<br>
          <span style="color:var(--text)">更新：</span>手動重新爬取（靜態快照）<br>
          <span style="color:var(--text)">原始來源：</span>isin.twse.com.tw 官方 ISIN 頁面
        </div>
      </div>
      <div style="background:var(--bg3);border:1px solid var(--border);border-radius:8px;padding:14px;">
        <div style="font-size:11px;font-weight:700;color:var(--green);letter-spacing:.5px;margin-bottom:10px;">💹 現價 ／ 估值倍數</div>
        <div style="font-size:12px;color:var(--muted);line-height:1.9;">
          <span style="color:var(--text)">來源：</span>TWSE 官方 API（即時）<br>
          <span style="color:var(--text)">現價、漲跌：</span>當月每日收盤（STOCK_DAY）<br>
          <span style="color:var(--text)">P/E、P/B、殖利率：</span>TTM，TWSE BWIBBU_d<br>
          <span style="color:var(--text)">更新：</span>每次新增股票時即時拉取
        </div>
      </div>
      <div style="background:var(--bg3);border:1px solid var(--border);border-radius:8px;padding:14px;">
        <div style="font-size:11px;font-weight:700;color:var(--yellow);letter-spacing:.5px;margin-bottom:10px;">📊 獲利 ／ 成長 ／ 財務指標</div>
        <div style="font-size:12px;color:var(--muted);line-height:1.9;">
          <span style="color:var(--text)">來源：</span>FinMind API（finmindtrade.com）<br>
          <span style="color:var(--text)">ROE、毛利率、營業利益率、淨利率：</span><br>
          　最新完整年度（12/31）財報<br>
          <span style="color:var(--text)">營收 ／ EPS 成長率：</span>最新年 vs 前一年（YoY）<br>
          <span style="color:var(--text)">負債比、流動比率、現金：</span>最新季度資產負債表<br>
          <span style="color:var(--text)">現金流：</span>最新可用期間現金流量表<br>
          <span style="color:var(--yellow)">⚠ 免費版每小時限約 30 次請求</span>
        </div>
      </div>
      <div style="background:var(--bg3);border:1px solid var(--border);border-radius:8px;padding:14px;">
        <div style="font-size:11px;font-weight:700;color:var(--purple);letter-spacing:.5px;margin-bottom:10px;">⚡ 重要限制說明</div>
        <div style="font-size:12px;color:var(--muted);line-height:1.9;">
          台灣公司採季報制，財報有約 <span style="color:var(--text)">45 天公告延遲</span><br>
          若 Q4 尚未申報，「最新年度」可能為前一年度<br>
          市場面指標僅反映<span style="color:var(--text)">當月</span>交易資料（非完整52週）<br>
          P/E 為空值時，成長動能前瞻分以營收替代<br>
          所有評分<span style="color:var(--red)">不代表買賣建議</span>，僅供研究參考
        </div>
      </div>
    </div>
  </div>
</div>

<div id="p-detail" style="display:none">
  <button class="back" onclick="show('overview')">← 返回總覽</button>
  <div id="detail-content" style="margin-top:20px"></div>
</div>
</main>
<script>
const stocks={stocks_json};
const inPortfolio=new Set(stocks.map(s=>s.ticker));
const COL={{growth:'rgba(37,99,235',value:'rgba(22,163,74',cyclical:'rgba(217,119,6',
            turnaround:'rgba(124,58,237',dividend:'rgba(22,163,74',general:'rgba(120,113,108'}};
function sc(s){{return s>=70?'a':s>=58?'b':s>=45?'c':'d'}}
function tagHtml(t){{
  const labels={{buy:'買入',watch:'觀望',hold:'保留',avoid:'迴避','—':'—'}};
  const styles={{
    buy:  {{bg:'#dcfce7',col:'#16a34a'}},
    watch:{{bg:'#dbeafe',col:'#2563eb'}},
    hold: {{bg:'#fef3c7',col:'#d97706'}},
    avoid:{{bg:'#fee2e2',col:'#dc2626'}},
  }};
  const label=labels[t]||t;
  const s=styles[t];
  if(s)return`<span style="padding:3px 10px;border-radius:20px;background:${{s.bg}};color:${{s.col}};font-size:11px;font-weight:600;">● ${{label}}</span>`;
  return`<span style="padding:3px 10px;border-radius:20px;background:#f0ebe3;color:#78716c;font-size:11px;font-weight:600;">${{label}}</span>`;
}}
function chHtml(v,p){{return`<span class="ch-${{v>=0?'pos':'neg'}}">${{v>=0?'+':''}}${{v.toFixed(2)}} (${{v>=0?'+':''}}${{p.toFixed(2)}}%)</span>`;}}
function sBar(s,w,mx){{
  mx=mx||100;
  const pct=Math.round(s/mx*100);
  const clr=pct>=70?'22,163,74':pct>=50?'37,99,235':pct>=30?'217,119,6':'220,38,38';
  const bg=`linear-gradient(to right,rgba(${{clr}},.15) ${{pct}}%,rgba(229,222,213,.5) ${{pct}}%)`;
  const label=mx===100?`${{s}}`:`${{s}}<span class="sn-max">/${{mx}}</span> <span class="sn-max" style="opacity:.7">${{pct}}%</span>`;
  const txtclr=pct>=70?'var(--green)':pct>=50?'var(--blue)':pct>=30?'var(--yellow)':'var(--red)';
  return`<div class="sbw" style="background:${{bg}}"><span class="sn" style="color:${{txtclr}}">${{label}}</span></div>`;
}}
function tBadge(t){{const m={{growth:'成長股',value:'價值股',cyclical:'循環股',turnaround:'轉型股',dividend:'存股型',general:'一般型'}};return`<span class="tbadge tb-${{t}}">${{m[t]||t}}</span>`;}}
function renderTbody(id,list){{
  const tb=document.getElementById(id);
  if(!list.length){{tb.innerHTML='<tr><td colspan="12" style="text-align:center;color:var(--muted);padding:24px">無符合條件</td></tr>';return;}}
  tb.innerHTML=list.map(s=>`<tr>
    <td><span class="cn">${{s.name}}</span><span class="tic">${{s.ticker}}</span>
        <div style="margin-top:3px;display:flex;gap:4px;align-items:center;">${{tBadge(s.stock_type||'general')}}&nbsp;<span style="color:var(--muted);font-size:10px;">${{s.sector}}</span></div></td>
    <td>${{makeRingJS(s.ai,s.tag)}}</td><td>${{s.fin_bar}}</td><td>${{s.growth_bar}}</td>
    <td>${{s.val_bar}}</td><td>${{s.financial_bar}}</td><td>${{s.market_bar}}</td>
    <td style="font-weight:600;">NT$${{s.price.toFixed(2)}}</td><td>${{chHtml(s.change,s.changePct)}}</td>
    <td style="color:var(--muted);font-size:12px;">${{s.mktCap}}</td>
    <td>${{tagHtml(s.tag)}}</td><td><button class="drill" onclick="openDetail('${{s.ticker}}')">詳情 →</button></td>
  </tr>`).join('');
}}
function filt(type,btn){{
  document.querySelectorAll('.fbtn').forEach(b=>b.classList.remove('active','active-buy','active-watch','active-hold'));
  const glowCls=btn.dataset.glow;
  btn.classList.add(glowCls||'active');
  document.getElementById('srch').value='';
  let m=stocks.filter(s=>s.type==='main'),w=stocks.filter(s=>s.type==='watch');
  if(type==='main') w=[];else if(type==='watch') m=[];
  else if(type==='buy'){{m=m.filter(s=>s.tag==='buy');w=w.filter(s=>s.tag==='buy');}}
  else if(type==='wtag'){{m=m.filter(s=>s.tag==='watch');w=w.filter(s=>s.tag==='watch');}}
  else if(type==='hold'){{m=m.filter(s=>s.tag==='hold'||s.tag==='avoid');w=w.filter(s=>s.tag==='hold'||s.tag==='avoid');}}
  renderTbody('tb-main',m);renderTbody('tb-watch',w);
}}
function doSearch(q){{
  q=q.trim().toLowerCase();
  if(!q){{
    // restore active filter
    const active=document.querySelector('.fbtn.active,.fbtn.active-buy,.fbtn.active-watch,.fbtn.active-hold');
    if(active){{active.click();return;}}
    renderTbody('tb-main',stocks.filter(s=>s.type==='main'));
    renderTbody('tb-watch',stocks.filter(s=>s.type==='watch'));
    return;
  }}
  // deactivate filter buttons while searching
  document.querySelectorAll('.fbtn').forEach(b=>b.classList.remove('active'));
  const hit=stocks.filter(s=>s.ticker.includes(q)||s.name.toLowerCase().includes(q)||s.sector.toLowerCase().includes(q));
  renderTbody('tb-main',hit.filter(s=>s.type==='main'));
  renderTbody('tb-watch',hit.filter(s=>s.type==='watch'));
  // if exactly one match, auto-open detail
  if(hit.length===1)openDetail(hit[0].ticker);
}}
function show(name){{
  ['overview','comparison','legend','detail'].forEach(p=>document.getElementById('p-'+p).style.display='none');
  document.getElementById('p-'+name).style.display='block';
  document.querySelectorAll('.ntab').forEach((t,i)=>t.classList.toggle('active',['overview','comparison','legend'][i]===name));
  if(name==='comparison')renderRadar();
}}

// ── Supabase client ───────────────────────────────────────────────────────
const SB_URL='https://tzhdqtdluzstmougrsul.supabase.co';
const SB_KEY='eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InR6aGRxdGRsdXpzdG1vdWdyc3VsIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODA0NTQzNDMsImV4cCI6MjA5NjAzMDM0M30.U3btm9GluHMZ9dDtr1nqVyGaQtflkmCDZvimoam4Aow';
const sb=supabase.createClient(SB_URL,SB_KEY);

// ── Candidate Watch List (localStorage) ──────────────────────────────────
// ── Anonymous session identity ────────────────────────────────────────────
let SESSION_ID=localStorage.getItem('tw_session_id');
if(!SESSION_ID){{
  SESSION_ID=(crypto.randomUUID?crypto.randomUUID():Math.random().toString(36).slice(2)+Date.now().toString(36));
  localStorage.setItem('tw_session_id',SESSION_ID);
}}

// ── Local watchlist (localStorage as fast cache, Supabase as source of truth) ──
let localWatch=JSON.parse(localStorage.getItem('tw_local_watch')||'[]');

// Write to localStorage immediately; Supabase upsert fires in background
function saveLocal(){{
  localStorage.setItem('tw_local_watch',JSON.stringify(localWatch));
  _sbFlush().catch(e=>console.warn('[SB] save failed:',e));
}}

async function _sbFlush(){{
  if(!localWatch.length)return;
  const rows=localWatch.map(u=>{{
    const {{t,ticker,_table,...cache}}=u;
    return {{session_id:SESSION_ID,ticker:ticker||t,watch_table:_table||'learning',score_cache:cache}};
  }});
  await sb.from('user_watchlist').upsert(rows,{{onConflict:'session_id,ticker'}});
}}

// Load from Supabase on startup and merge with localStorage
async function _sbLoad(){{
  try{{
    const {{data,error}}=await sb.from('user_watchlist')
      .select('ticker,watch_table,score_cache,added_at')
      .eq('session_id',SESSION_ID)
      .order('added_at',{{ascending:true}});
    if(error)throw error;
    if(data&&data.length>0){{
      // Supabase is the source of truth for which stocks exist and which table they're in
      const lsMap=new Map(localWatch.map(u=>[u.ticker||u.t,u]));
      const merged=data.map(r=>{{
        const local=lsMap.get(r.ticker)||{{}};
        // Prefer local score if freshly scored (ok:true) and SB cache is empty or stale
        const sbCache=r.score_cache||{{}};
        const cache=(local.ok&&!sbCache.ok)?{{...local}}:{{...sbCache}};
        return {{...cache,t:r.ticker,ticker:r.ticker,_table:r.watch_table}};
      }});
      // Include any localStorage items not yet in Supabase (race: just added)
      const sbTickers=new Set(data.map(r=>r.ticker));
      for(const u of localWatch){{
        const tid=u.ticker||u.t;
        if(!sbTickers.has(tid))merged.push(u);
      }}
      localWatch=merged;
      localStorage.setItem('tw_local_watch',JSON.stringify(localWatch));
      // Rebuild cfgOverrides from Supabase (cross-device sync for config moves)
      data.forEach(r=>{{
        if(r.score_cache&&r.score_cache._cfg_override&&r.watch_table)
          cfgOverrides[r.ticker]=r.watch_table;
      }});
      localStorage.setItem('tw_cfg_overrides',JSON.stringify(cfgOverrides));
      applyCfgHides();
      renderAllLocalRows();
      // Re-run radar in case comparison tab was open before load completed
      if(document.getElementById('p-comparison').style.display!=='none')renderRadar();
    }}else if(localWatch.length>0){{
      // Supabase empty but localStorage has data — first-time migration
      _sbFlush().catch(()=>{{}});
    }}
  }}catch(e){{
    console.warn('[SB] load failed, using localStorage:',e);
  }}
}}

function toggleAddBox(){{
  const box=document.getElementById('add-box');
  const open=box.style.display==='none';
  box.style.display=open?'block':'none';
  if(open){{document.getElementById('add-srch').focus();addFilter('');}}
}}

let _filterTimer=null;
function addFilter(q){{
  clearTimeout(_filterTimer);
  q=q.trim();
  const res=document.getElementById('add-results');
  if(!q){{
    res.innerHTML='<span style="color:var(--muted);font-size:12px;">開始輸入代號或名稱…</span>';
    return;
  }}
  res.innerHTML='<span style="color:var(--muted);font-size:12px;">搜尋中…</span>';
  _filterTimer=setTimeout(()=>_doSearch(q),200);
}}

async function _doSearch(q){{
  const res=document.getElementById('add-results');
  const taken=new Set([...inPortfolio,...localWatch.map(x=>x.t)]);
  try{{
    // Ticker prefix search for any digit-only input (1+ digits), name search otherwise
    const isDigits=/^\d+$/.test(q);
    const isTickerQuery=/^\d{{4,6}}$/.test(q); // used only for freeOk button
    let data=[];
    if(isDigits){{
      // Prefix match on ticker (covers partial input like "53", "233", "2330")
      const {{data:d1}}=await sb.from('companies')
        .select('ticker,name,english_name,market,industry')
        .ilike('ticker',q+'%')
        .limit(20);
      data=d1||[];
    }}
    if(data.length<10){{
      // Name search (Chinese or English)
      const {{data:d2}}=await sb.from('companies')
        .select('ticker,name,english_name,market,industry')
        .or(`name.ilike.%${{q}}%,english_name.ilike.%${{q}}%`)
        .limit(20-data.length);
      // Merge, dedup by ticker
      const seen=new Set(data.map(x=>x.ticker));
      for(const r of (d2||[])){{ if(!seen.has(r.ticker)){{data.push(r);seen.add(r.ticker);}} }}
    }}
    // Filter out already-tracked tickers
    const matches=data.filter(u=>!taken.has(u.ticker));
    const freeOk=isTickerQuery&&q.length===4&&!taken.has(q)&&!matches.find(u=>u.ticker===q);
    let html=matches.map(u=>`
      <button onclick="addToWatch('${{u.ticker}}','${{u.name}}','${{u.industry||u.market}}')"
        style="padding:6px 14px;border-radius:20px;border:1px solid var(--border);
               background:var(--bg3);color:var(--text);font-size:12px;cursor:pointer;text-align:left;">
        <span style="color:var(--blue);font-weight:600;">${{u.ticker}}</span> ${{u.name}}
        ${{u.english_name?`<span style="color:var(--muted);font-size:10px;">${{u.english_name}}</span>`:''}}
        <span style="color:var(--muted);font-size:11px;">· ${{u.industry||u.market}}</span>
      </button>`).join('');
    if(freeOk) html+=`
      <button onclick="addToWatch('${{q}}','${{q}}','—')"
        style="padding:6px 14px;border-radius:20px;border:1px dashed var(--blue);
               background:rgba(88,166,255,.08);color:var(--blue);font-size:12px;cursor:pointer;">
        ＋ 直接加入代號 ${{q}}
      </button>`;
    if(!html) html='<span style="color:var(--muted);font-size:12px;">查無結果，可輸入4位代號直接加入</span>';
    res.innerHTML=html;
  }}catch(e){{
    res.innerHTML='<span style="color:var(--muted);font-size:12px;">搜尋失敗，請稍後重試</span>';
    console.error('Supabase search error:',e);
  }}
}}

// ── JS helpers mirroring Python functions ────────────────────────────────
function makeBarJS(val,mx){{
  const pct=mx>0?Math.round(val/mx*100):0;
  const col=pct>=70?'#16a34a':pct>=58?'#2563eb':pct>=45?'#d97706':'#dc2626';
  return `<div style="text-align:center;min-width:46px;">`
    +`<div style="white-space:nowrap;">`
    +`<span style="color:${{col}};font-weight:700;font-size:12px;">${{val}}</span>`
    +`<span style="color:#78716c;font-size:11px;"> /${{mx}}</span></div>`
    +`<div style="height:3px;border-radius:2px;background:#e5ded5;margin-top:3px;overflow:hidden;">`
    +`<div style="width:${{pct}}%;height:100%;background:${{col}};border-radius:2px;"></div></div></div>`;
}}
function makeRingJS(score,tag){{
  const tagColors={{buy:'#16a34a',watch:'#2563eb',hold:'#d97706',avoid:'#dc2626'}};
  const col=tagColors[tag]||'#78716c';
  const circ=113.1,dash=Math.round(score/100*circ*10)/10,gap=Math.round((circ-dash)*10)/10;
  return `<div style="position:relative;width:44px;height:44px;flex-shrink:0;">`
    +`<svg width="44" height="44" style="transform:rotate(-90deg)">`
    +`<circle cx="22" cy="22" r="18" fill="none" stroke="#e5ded5" stroke-width="3.5"/>`
    +`<circle cx="22" cy="22" r="18" fill="none" stroke="${{col}}" stroke-width="3.5"`
    +` stroke-linecap="round" stroke-dasharray="${{dash}} ${{gap}}"/></svg>`
    +`<span style="position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);`
    +`font-size:13px;font-weight:700;color:${{col}};">${{score}}</span></div>`;
}}
function fmtCap(v){{
  if(!v)return'—';
  if(v>=1e12)return(v/1e12).toFixed(1)+'兆';
  if(v>=1e8)return Math.round(v/1e8)+'億';
  return Math.round(v/1e4)+'萬';
}}
function g(o){{return o?.raw??o??0;}}  // unwrap Yahoo {{raw:x}} or plain value

function scoreStockJS(info,stype){{
  stype=stype||'general';
  const roe=g(info.returnOnEquity)*100, grossM=g(info.grossMargins)*100;
  const opM=g(info.operatingMargins)*100, netM=g(info.profitMargins)*100;
  const revGr=g(info.revenueGrowth)*100, earnGr=g(info.earningsGrowth)*100;
  const tPE=g(info.trailingPE), fPE=g(info.forwardPE), pb=g(info.priceToBook);
  let peg=g(info.pegRatio);
  const debtEq=g(info.debtToEquity), currR=g(info.currentRatio);
  const fcf=g(info.freeCashflow), opCF=g(info.operatingCashflow);
  const tCash=g(info.totalCash), tDebt=g(info.totalDebt);
  const beta=g(info.beta)||1, w52c=g(info['52WeekChange']), sp52c=g(info.SandP52WeekChange);
  const vol=g(info.regularMarketVolume), avgVol=g(info.averageVolume)||1;
  const price=g(info.regularMarketPrice)||g(info.currentPrice);
  const w52Hi=g(info.fiftyTwoWeekHigh)||price, w52Lo=g(info.fiftyTwoWeekLow)||price;
  const dy=g(info.dividendYield), divY=Math.min(dy>1?dy:dy*100,25);
  const peak=stype==='cyclical'&&roe>20&&grossM>30;

  // 1. 獲利品質 (0-20)
  let p=0;
  p+=stype==='growth'?(roe>=15?6:roe>=10?4:roe>=7?2:roe>0?1:0):(roe>=20?6:roe>=15?4:roe>=10?2:roe>0?1:0);
  p+=grossM>=35?6:grossM>=25?4:grossM>=15?2:grossM>0?1:0;
  p+=opM>=15?5:opM>=10?3:opM>=5?1:0;
  p+=netM>=10?3:netM>=5?2:netM>0?1:0;
  if(peak)p=Math.round(p*0.70);
  if(stype==='turnaround'&&opM>0&&grossM>15)p=Math.min(20,p+2);
  p=Math.min(20,Math.max(0,p));

  // 2. 成長動能 (0-20)
  let gx=0; const rvMax=stype==='growth'?9:8;
  gx+=revGr>=30?rvMax:revGr>=20?Math.round(rvMax*.78):revGr>=10?Math.round(rvMax*.5):revGr>=5?Math.round(rvMax*.25):revGr>=0?1:(revGr>=-8&&(stype==='value'||stype==='dividend'))?1:0;
  gx+=earnGr>=30?7:earnGr>=15?5:earnGr>=5?4:earnGr>=0?1:0;
  if(fPE>0&&tPE>0){{const imp=(tPE-fPE)/tPE*100;gx+=imp>=20?4:imp>=10?3:imp>=0?2:0;}}
  else gx+=revGr>=25&&earnGr>=0?4:revGr>=15&&earnGr>=0?3:revGr>=10?2:revGr>=0?1:0;
  if(peak)gx=Math.round(gx*0.70);
  if(stype==='turnaround'&&revGr>0)gx=Math.min(20,gx+2);
  gx=Math.min(20,Math.max(0,gx));

  // 3. 估值吸引力 (0-15)
  let v=0;
  if(peg>10||peg<0)peg=0;
  if(peg<=0&&revGr>0)peg=fPE>0?fPE/revGr:tPE>0?tPE/revGr:0;
  if(stype==='growth'){{
    v+=tPE>0&&tPE<=20?5:tPE<=30?4:tPE<=40?3:tPE<=55?1:0;
    v+=pb>0&&pb<=2?4:pb<=4?3:pb<=6?1:0;
    v+=peg>0&&peg<1?6:peg<1.5?4:peg<2?2:0;
  }}else if(stype==='dividend'){{
    v+=divY>=6?7:divY>=4?5:divY>=3?3:divY>=1.5?1:0;
    v+=tPE>0&&tPE<=12?4:tPE<=18?3:tPE<=25?2:tPE<=35?1:0;
    v+=pb>0&&pb<=1.5?4:pb<=2.5?2:0;
  }}else if(stype==='cyclical'){{
    const peV=fPE>0?fPE:tPE, pegV=peV>0&&revGr>0?peV/revGr:0;
    v+=pb>0&&pb<=1?6:pb<=1.5?5:pb<=2.5?3:pb<=4?1:0;
    v+=peV>0&&peV<=8?5:peV<=12?3:peV<=18?2:peV<=25?1:0;
    v+=pegV>0&&pegV<1?4:pegV<1.5?2:0;
  }}else if(stype==='turnaround'){{
    v+=pb>0&&pb<=1?7:pb<=1.5?5:pb<=2.5?3:pb<=4?1:0;
    v+=tPE>0&&tPE<=15?5:tPE<=25?3:tPE<=40?1:0;
    v+=peg>0&&peg<1.5?3:0;
  }}else{{
    v+=tPE>0&&tPE<=12?5:tPE<=18?3:tPE<=25?2:tPE<=35?1:0;
    v+=pb>0&&pb<=1?5:pb<=1.5?3:pb<=2.5?2:pb<=4?1:0;
    v+=peg>0&&peg<1?5:peg<1.5?3:peg<2?1:0;
  }}
  v=Math.min(15,Math.max(0,v));

  // 4. 財務體質 (0-15)
  let f=0;
  f+=debtEq<=30?4:debtEq<=60?3:debtEq<=100?2:1;
  f+=currR>=2.5?3:currR>=1.5?2:currR>=1?1:0;
  f+=fcf>0&&opCF>0?4:opCF>0?2:0;
  f+=tDebt>0&&tCash>=tDebt*1.5?4:tCash>tDebt?2:0;
  f=Math.min(15,Math.max(0,f));

  // 5. 市場面 (0-10)
  let m=0;
  const rng=w52Hi>w52Lo?(price-w52Lo)/(w52Hi-w52Lo):0;
  m+=rng>=.75?3:rng>=.5?2:rng>=.25?1:0;
  m+=(beta>=.5&&beta<=1.3)?2:1;
  const vr=vol/avgVol; m+=vr>=2?3:vr>=1.3?2:vr>=.8?1:0;
  m+=(w52c-sp52c)>=.1?2:(w52c-sp52c)>=0?1:0;
  m=Math.min(10,Math.max(0,m));

  // 6. 風險 + 7. 類型加成
  let r=0;
  if(peak)r-=4; else if(tPE>50&&revGr<15&&stype!=='cyclical')r-=2;
  if(debtEq>200)r-=3; else if(debtEq>150)r-=2;
  if(pb>8&&tPE>60)r-=2; if(beta>1.8)r-=1;
  r=Math.max(-10,r);
  let ta=0;
  if(stype==='growth'&&roe>=15&&revGr>=15&&grossM>=30)ta=earnGr>=25?5:3;
  else if(stype==='turnaround'&&opM>0&&revGr>0&&pb<=2)ta=4;
  else if(stype==='dividend'&&divY>=4&&debtEq<=80&&opCF>0)ta=divY>=6?3:1;

  const total=Math.min(100,Math.max(0,p+gx+v+f+m+r+ta));
  const tag=total>=70?'buy':total>=58?'watch':total>=45?'hold':'avoid';
  return {{profit:p,growth:gx,valuation:v,financial:f,market:m,risk:r,typeAdj:ta,total,tag}};
}}

async function addToWatch(t,n,s){{
  if(localWatch.find(x=>x.t===t))return;
  localWatch.push({{t,n,s,_loading:true}});
  saveLocal(); renderAllLocalRows();
  toggleAddBox(); document.getElementById('add-srch').value='';

  try{{
    // Fetch all data in parallel: TWSE for price/valuation + Finmind for fundamentals + price history
    const start2y='2022-01-01';
    const d6m=new Date(); d6m.setMonth(d6m.getMonth()-6);
    const start6m=d6m.toISOString().slice(0,10);
    const [dayData,valData,fsData,bsData,cfData,priceHist]=await Promise.all([
      fetch(`https://www.twse.com.tw/rwd/zh/afterTrading/STOCK_DAY?stockNo=${{t}}&response=json`).then(r=>r.json()),
      fetch(`https://www.twse.com.tw/rwd/zh/afterTrading/BWIBBU_d?response=json`).then(r=>r.json()),
      fetch(`https://api.finmindtrade.com/api/v4/data?dataset=TaiwanStockFinancialStatements&data_id=${{t}}&start_date=${{start2y}}`).then(r=>r.json()),
      fetch(`https://api.finmindtrade.com/api/v4/data?dataset=TaiwanStockBalanceSheet&data_id=${{t}}&start_date=${{start2y}}`).then(r=>r.json()),
      fetch(`https://api.finmindtrade.com/api/v4/data?dataset=TaiwanStockCashFlowsStatement&data_id=${{t}}&start_date=${{start2y}}`).then(r=>r.json()),
      fetch(`https://api.finmindtrade.com/api/v4/data?dataset=TaiwanStockPrice&data_id=${{t}}&start_date=${{start6m}}`).then(r=>r.json()).catch(()=>({{data:[]}})),
    ]);

    // --- Price & momentum from STOCK_DAY ---
    // fields: 日期,成交股數,成交金額,開盤價,最高價,最低價,收盤價,漲跌價差,成交筆數
    const lastRow=dayData.data?.[dayData.data.length-1];
    if(!lastRow)throw new Error('no price data');
    const price=parseFloat(lastRow[6].replace(/,/g,''))||0;
    const change=parseFloat(lastRow[7].replace(/[+,]/g,''))||0;
    const changePct=(price>0&&price!==change)?change/(price-change)*100:0;
    const allPrices=dayData.data.map(r=>parseFloat(r[6].replace(/,/g,''))||0).filter(v=>v>0);
    const monthHi=Math.max(...allPrices)||price, monthLo=Math.min(...allPrices)||price;
    const momo=allPrices[0]>0?(price-allPrices[0])/allPrices[0]:0;
    const vols=dayData.data.map(r=>parseInt(r[1].replace(/,/g,''),10)||0);
    const avgVol=vols.reduce((a,b)=>a+b,0)/vols.length||1;
    const curVol=vols[vols.length-1]||0;

    // --- Valuation from BWIBBU_d ---
    // fields: 證券代號,證券名稱,收盤價,殖利率(%),股利年度,本益比,股價淨值比,財報年/季
    const valRow=valData.data?.find(r=>r[0]===t);
    const pe=valRow?parseFloat(valRow[5])||0:0;
    const pb=valRow?parseFloat(valRow[6])||0:0;
    const div=valRow?parseFloat(valRow[3])||0:0;

    // --- Fundamentals from Finmind ---
    const getV=(data,type,date)=>{{const r=data.find(r=>r.type===type&&r.date===date);return r?r.value:0;}};
    const getDates=(data)=>[...new Set(data.map(r=>r.date))].sort((a,b)=>b.localeCompare(a));

    // Income statement — prefer annual (Dec 31) for clean YoY comparison
    const fsDates=getDates(fsData.data);
    const annFS=fsDates.filter(d=>d.includes('-12-'));
    const d0=annFS[0]||fsDates[0];
    const d1=annFS[1]||fsDates[Math.min(4,fsDates.length-1)];

    const rev0=getV(fsData.data,'Revenue',d0);
    const rev1=getV(fsData.data,'Revenue',d1);
    const gp0=getV(fsData.data,'GrossProfit',d0);
    const oi0=getV(fsData.data,'OperatingIncome',d0);
    const ni0=getV(fsData.data,'IncomeAfterTaxes',d0);
    const eps0=getV(fsData.data,'EPS',d0);
    const eps1=getV(fsData.data,'EPS',d1);

    // Balance sheet — most recent quarter
    const bsDates=getDates(bsData.data);
    const bsD=bsDates[0];
    const tlEq=getV(bsData.data,'TotalLiabilitiesEquity',bsD);
    const eq=getV(bsData.data,'Equity',bsD);
    const ca=getV(bsData.data,'CurrentAssets',bsD);
    const cl=getV(bsData.data,'CurrentLiabilities',bsD);
    const cashVal=getV(bsData.data,'CashAndCashEquivalents',bsD);
    const tLiab=tlEq-eq;

    // Cash flow — most recent period
    const cfDates=getDates(cfData.data);
    const cfD=cfDates[0];
    const opCFval=getV(cfData.data,'CashFlowsFromOperatingActivities',cfD)||
                  getV(cfData.data,'NetCashInflowFromOperatingActivities',cfD);

    // Compute ratios (as fractions/percentages matching scoreStockJS expectations)
    const grossM=rev0>0?gp0/rev0:0;       // fraction → scoreStockJS does *100
    const opMval=rev0>0?oi0/rev0:0;
    const netMval=rev0>0?ni0/rev0:0;
    const roeVal=eq>0?ni0/eq:0;
    const revGrVal=rev1>0?(rev0-rev1)/rev1:0;
    const earnGrVal=eps1!==0?(eps0-eps1)/Math.abs(eps1):0;
    const deqVal=eq>0?tLiab/eq*100:0;     // % form (scoreStockJS uses directly)
    const currRval=cl>0?ca/cl:0;
    const mktCapVal=pb>0&&eq>0?fmtCap(eq*pb):'—';

    // Assemble info object exactly as scoreStockJS expects (Yahoo Finance field names)
    const info={{
      returnOnEquity:roeVal, grossMargins:grossM,
      operatingMargins:opMval, profitMargins:netMval,
      revenueGrowth:revGrVal, earningsGrowth:earnGrVal,
      trailingPE:pe, priceToBook:pb,
      dividendYield:div/100,   // BWIBBU_d gives %, scoreStockJS expects fraction
      debtToEquity:deqVal, currentRatio:currRval,
      operatingCashflow:opCFval, freeCashflow:opCFval,
      totalCash:cashVal, totalDebt:tLiab,
      beta:1,
      '52WeekChange':momo, SandP52WeekChange:0,
      regularMarketVolume:curVol, averageVolume:avgVol,
      regularMarketPrice:price, currentPrice:price,
      fiftyTwoWeekHigh:monthHi, fiftyTwoWeekLow:monthLo,
    }};

    const sc=scoreStockJS(info,'general');
    const existingTable=localWatch.find(x=>x.t===t||x.ticker===t)?._table||'learning';
    const stock={{
      t,n,s,ticker:t,name:n,sector:s,type:'watch',stock_type:'general',
      _table:existingTable,
      price,change,changePct,mktCap:mktCapVal,
      // Valuation & fundamental metrics for openDetail()
      pe,pb,div,
      roe:Math.round(roeVal*1000)/10,          // fraction → % with 1 decimal
      eps:Math.round(eps0*100)/100,
      grossMargin:Math.round(grossM*1000)/10,  // fraction → % with 1 decimal
      opMargin:Math.round(opMval*1000)/10,
      radar:[sc.total,
             Math.round(sc.profit/20*100),
             Math.round(sc.growth/20*100),
             Math.round(sc.valuation/15*100),
             Math.round(sc.financial/15*100),
             Math.round(sc.market/10*100)],
      ai:sc.total,tag:sc.tag,
      fin:sc.profit,growth_s:sc.growth,
      valuation:sc.valuation,financial:sc.financial,market:sc.market,
      risk:sc.risk,typeAdj:sc.typeAdj,
      ai_bar:makeBarJS(sc.total,100),fin_bar:makeBarJS(sc.profit,20),
      growth_bar:makeBarJS(sc.growth,20),val_bar:makeBarJS(sc.valuation,15),
      financial_bar:makeBarJS(sc.financial,15),market_bar:makeBarJS(sc.market,10),
      ai_ring:makeRingJS(sc.total,sc.tag),
      price_dates:(priceHist.data||[]).map(r=>r.date.slice(5).replace('-','/')),
      price_closes:(priceHist.data||[]).map(r=>r.close),
      ok:true
    }};
    const idx=localWatch.findIndex(x=>x.t===t);
    if(idx>=0)localWatch[idx]=stock; else localWatch.push(stock);
  }}catch(e){{
    // Finmind failed — fall back to TWSE-only partial row
    try{{
      const [dayResp,valResp]=await Promise.all([
        fetch(`https://www.twse.com.tw/rwd/zh/afterTrading/STOCK_DAY?stockNo=${{t}}&response=json`),
        fetch(`https://www.twse.com.tw/rwd/zh/afterTrading/BWIBBU_d?response=json`)
      ]);
      const dayData=await dayResp.json(),valData=await valResp.json();
      const lastRow=dayData.data?.[dayData.data.length-1];
      const price=lastRow?parseFloat(lastRow[6].replace(/,/g,''))||0:0;
      const change=lastRow?parseFloat(lastRow[7].replace(/[+,]/g,''))||0:0;
      const changePct=(price>0&&price!==change)?change/(price-change)*100:0;
      const valRow=valData.data?.find(r=>r[0]===t);
      const pe=valRow?parseFloat(valRow[5])||0:0;
      const pb=valRow?parseFloat(valRow[6])||0:0;
      const div=valRow?parseFloat(valRow[3])||0:0;
      const stock={{t,n,s,ticker:t,name:n,sector:s,price,change,changePct,pe,pb,div,_partial:true}};
      const idx=localWatch.findIndex(x=>x.t===t);
      if(idx>=0)localWatch[idx]=stock; else localWatch.push(stock);
    }}catch(e2){{
      const idx=localWatch.findIndex(x=>x.t===t);
      if(idx>=0)localWatch[idx]={{t,n,s,_failed:true}};
    }}
  }}
  saveLocal(); renderAllLocalRows();
}}

function removeLocal(t){{
  localWatch=localWatch.filter(x=>x.t!==t&&x.ticker!==t);
  // Remove from stocks array too so openDetail doesn't find stale data
  const si=stocks.findIndex(s=>s.ticker===t);
  if(si>=0&&stocks[si]._local)stocks.splice(si,1);
  saveLocal();renderAllLocalRows();
  // Delete from Supabase
  sb.from('user_watchlist').delete()
    .eq('session_id',SESSION_ID).eq('ticker',t)
    .then(()=>{{}}).catch(e=>console.warn('[SB] delete failed:',e));
}}
function moveLocal(t,toTable){{
  const idx=localWatch.findIndex(x=>(x.t||x.ticker)===t);
  if(idx<0)return;
  localWatch[idx]._table=toTable;
  saveLocal();renderAllLocalRows();
}}

// ── Config stock overrides (move / delete for server-generated rows) ──────
let cfgOverrides=JSON.parse(localStorage.getItem('tw_cfg_overrides')||'{{}}');
// {{ticker: 'main'|'watch'|'learning'|'deleted'}}

function saveCfgOverrides(){{
  localStorage.setItem('tw_cfg_overrides',JSON.stringify(cfgOverrides));
  // Mirror to Supabase so overrides persist cross-device
  const rows=Object.entries(cfgOverrides).map(([ticker,tbl])=>
    ({{session_id:SESSION_ID,ticker,watch_table:tbl==='deleted'?'deleted':tbl,
      score_cache:{{_cfg_override:true}}}}));
  if(rows.length)sb.from('user_watchlist').upsert(rows,{{onConflict:'session_id,ticker'}})
    .catch(e=>console.warn('[SB] cfg override save failed:',e));
}}
function applyCfgHides(){{
  Object.entries(cfgOverrides).forEach(([ticker,tbl])=>{{
    document.querySelectorAll(`tr[data-cfg="${{ticker}}"]`).forEach(r=>r.style.display='none');
  }});
}}
function moveConfig(t,toTable){{
  cfgOverrides[t]=toTable;
  saveCfgOverrides();
  // Copy stock data to localWatch so it shows up in the new table
  const s=stocks.find(x=>x.ticker===t);
  if(s){{
    const entry={{...s,_table:toTable,t,ticker:t,_local:true,_cfg_override:true}};
    const idx=localWatch.findIndex(x=>(x.ticker||x.t)===t);
    if(idx>=0)localWatch[idx]=entry; else localWatch.push(entry);
    saveLocal();
  }}
  applyCfgHides();
  renderAllLocalRows();
}}
function removeConfig(t){{
  cfgOverrides[t]='deleted';
  saveCfgOverrides();
  // Remove from localWatch if present
  localWatch=localWatch.filter(x=>x.t!==t&&x.ticker!==t);
  const si=stocks.findIndex(s=>s.ticker===t&&s._local);
  if(si>=0)stocks.splice(si,1);
  saveLocal();renderAllLocalRows();
  applyCfgHides();
  sb.from('user_watchlist').delete()
    .eq('session_id',SESSION_ID).eq('ticker',t)
    .then(()=>{{}}).catch(e=>console.warn('[SB] cfg delete failed:',e));
}}

function localRowHtml(u, tbl){{
  const tid=u.ticker||u.t;
  const bs='padding:2px 7px;border-radius:5px;font-size:10px;cursor:pointer;white-space:nowrap;background:transparent;border:1px solid ';
  const rmBtn=`<button onclick="removeLocal('${{tid}}')" title="移除" style="${{bs}}var(--border);color:var(--muted);">✕</button>`;
  const mvBtn=(label,to,col)=>`<button onclick="moveLocal('${{tid}}','${{to}}')"
    style="${{bs}}${{col}};color:${{col}};">${{label}}</button>`;
  const emptyBar=(w,h,r)=>`<div style="display:flex;align-items:center;gap:6px;white-space:nowrap;">
    <div style="width:${{w}}px;height:${{h}}px;border-radius:${{r}}px;background:#e5ded5;flex-shrink:0;opacity:.6;"></div>
    <span style="color:var(--muted);font-size:11px;">-</span></div>`;

  // Action buttons depend on which table the row lives in
  let acts;
  if(tbl==='main')
    acts=`${{mvBtn('↓觀望','watch','var(--blue)')}} ${{mvBtn('↓學習','learning','var(--muted)')}} ${{rmBtn}}`;
  else if(tbl==='watch')
    acts=`${{mvBtn('↑持股','main','var(--green)')}} ${{mvBtn('↓學習','learning','var(--muted)')}} ${{rmBtn}}`;
  else
    acts=`${{mvBtn('↑觀望','watch','var(--blue)')}} ${{mvBtn('↑持股','main','var(--green)')}} ${{rmBtn}}`;

  if(u._loading) return`<tr>
    <td><span class="cn">${{u.n}}</span><span class="tic">${{u.t}}</span>
      <div style="color:var(--muted);font-size:10px;margin-top:3px;">${{u.s||''}}</div></td>
    <td colspan="10" style="color:var(--muted);font-size:12px;">⏳ 正在取得資料…</td>
    <td style="white-space:nowrap;">${{rmBtn}}</td></tr>`;

  if(u._failed) return`<tr>
    <td><span class="cn">${{u.n}}</span><span class="tic">${{u.t}}</span>
      <div style="color:var(--muted);font-size:10px;margin-top:3px;">${{u.s||''}}</div></td>
    <td colspan="10" style="color:#f85149;font-size:12px;">⚠ 無法取得資料（請確認股票代碼）</td>
    <td style="white-space:nowrap;">${{rmBtn}}</td></tr>`;

  if(u._partial){{
    const metas=[];
    if(u.pe)  metas.push(`本益比 ${{u.pe.toFixed(1)}}`);
    if(u.pb)  metas.push(`淨值比 ${{u.pb.toFixed(2)}}x`);
    if(u.div) metas.push(`殖利率 ${{u.div.toFixed(1)}}%`);
    return`<tr>
      <td><span class="cn">${{u.name||u.n}}</span><span class="tic">${{u.ticker||u.t}}</span>
        <div style="margin-top:3px;display:flex;gap:4px;align-items:center;">
          ${{tBadge(u.stock_type||'general')}}
          <span style="color:var(--muted);font-size:10px;">${{u.sector||u.s}}</span>
        </div>
        ${{metas.length?`<div style="margin-top:3px;color:var(--muted);font-size:10px;">${{metas.join(' · ')}}</div>`:''}}
      </td>
      ${{[emptyBar(68,6,3),emptyBar(50,4,2),emptyBar(50,4,2),emptyBar(50,4,2),emptyBar(50,4,2),emptyBar(50,4,2)].map(b=>`<td>${{b}}</td>`).join('')}}
      <td style="font-weight:600;">${{u.price?'NT$'+u.price.toFixed(2):'-'}}</td>
      <td>${{u.price?chHtml(u.change,u.changePct):'-'}}</td>
      <td style="color:var(--muted);font-size:12px;">-</td>
      <td>${{tagHtml('—')}}</td>
      <td style="white-space:nowrap;">${{acts}}</td></tr>`;
  }}

  // Full scored row
  const detailBtn=`<button class="drill" onclick="openDetail('${{tid}}')">詳情→</button>`;
  return`<tr>
    <td><span class="cn">${{u.name||u.n}}</span><span class="tic">${{u.ticker||u.t}}</span>
      <div style="margin-top:3px;display:flex;gap:4px;align-items:center;">
        ${{tBadge(u.stock_type||'general')}}&nbsp;<span style="color:var(--muted);font-size:10px;">${{u.sector||u.s}}</span>
      </div></td>
    <td>${{makeRingJS(u.ai,u.tag)}}</td>
    <td>${{makeBarJS(u.fin||0,20)}}</td><td>${{makeBarJS(u.growth_s||0,20)}}</td>
    <td>${{makeBarJS(u.valuation||0,15)}}</td><td>${{makeBarJS(u.financial||0,15)}}</td><td>${{makeBarJS(u.market||0,10)}}</td>
    <td style="font-weight:600;">NT$${{(u.price||0).toFixed(2)}}</td>
    <td>${{chHtml(u.change||0,u.changePct||0)}}</td>
    <td style="color:var(--muted);font-size:12px;">${{u.mktCap||'—'}}</td>
    <td>${{tagHtml(u.tag)}}</td>
    <td>${{detailBtn}}<div style="display:flex;gap:3px;margin-top:4px;flex-wrap:wrap;">${{acts}}</div></td></tr>`;
}}

function renderAllLocalRows(){{
  const main=localWatch.filter(u=>u._table==='main');
  const watch=localWatch.filter(u=>u._table==='watch');
  const learn=localWatch.filter(u=>!u._table||u._table==='learning');

  const sectionHdr=(label,col)=>`<tr><td colspan="12" style="padding:5px 12px;
    background:rgba(${{col}},.06);color:var(--muted);font-size:11px;
    border-top:2px solid rgba(${{col}},.25);">▸ ${{label}}（本機儲存）</td></tr>`;

  const el=(id)=>document.getElementById(id);
  if(el('tb-main-local')) el('tb-main-local').innerHTML=
    main.length?sectionHdr('自選持股','88,166,255')+main.map(u=>localRowHtml(u,'main')).join(''):'';
  if(el('tb-watch-local')) el('tb-watch-local').innerHTML=
    watch.length?sectionHdr('自選觀望','88,166,255')+watch.map(u=>localRowHtml(u,'watch')).join(''):'';

  const tbL=el('tb-learning');
  const badge=el('badge-learning');
  if(badge) badge.textContent=learn.length+' 檔';
  if(tbL) tbL.innerHTML=learn.length
    ?learn.map(u=>localRowHtml(u,'learning')).join('')
    :`<tr><td colspan="12" style="text-align:center;color:var(--muted);padding:24px;font-size:13px;">
       暫無學習股 — 點擊「＋ 新增學習股」開始探索</td></tr>`;

  // Register all local watch stocks in stocks[] so openDetail() + radar work
  // Include ok:false/undefined entries too so they show up in the radar grid
  localWatch.filter(u=>u.ticker||u.t).forEach(u=>{{
    const tid=u.ticker||u.t;
    const merged={{...u,ticker:tid,type:u._table||'learning',_local:true}};
    const idx=stocks.findIndex(s=>s.ticker===tid);
    if(idx<0) stocks.push(merged);
    else if(stocks[idx]._local) stocks[idx]=merged; // refresh with latest data
  }});
  // If comparison tab visible, render any new stocks added since last render
  if(document.getElementById('p-comparison')&&document.getElementById('p-comparison').style.display!=='none')
    renderRadar();
}}
const radarRendered=new Set();
function renderRadar(){{
  // Incremental: only add cards for stocks not yet rendered
  stocks.forEach(s=>{{
    if(radarRendered.has(s.ticker))return;
    // Must have at minimum a ticker; skip truly empty placeholder rows
    if(!s.ticker||(!s.ai&&!s.name))return;
    radarRendered.add(s.ticker);
    const col=COL[s.stock_type||'general'];
    // Determine which section this stock belongs to
    const isMain=s.type==='main'&&!s._local;
    const isLearn=s._table==='learning'||s._local||(s.type==='learning');
    const gridId=isMain?'radar-main':isLearn?'radar-learn':'radar-watch';
    const g=document.getElementById(gridId);
    if(!g)return;
    const hasRadar=s.radar&&Array.isArray(s.radar)&&s.radar.some(v=>v>0);
    const d=document.createElement('div');d.className='rc';
    d.innerHTML=`<div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:8px;">
      <div><div style="font-size:13px;font-weight:600;">${{s.name||s.ticker}} <span style="color:var(--muted);font-size:11px;">${{s.ticker}}</span></div>
      <div style="margin-top:3px;display:flex;gap:4px;">${{tBadge(s.stock_type||'general')}}&nbsp;<span style="color:var(--muted);font-size:10px;">${{s.sector||''}}</span></div></div>
      <div style="text-align:right;"><div class="sn score-${{sc(s.ai||0)}}" style="font-size:20px;">${{s.ai||'—'}}</div>${{tagHtml(s.tag||'—')}}</div>
    </div>
    ${{hasRadar
      ?`<canvas id="rc-${{s.ticker}}" height="210"></canvas>`
      :`<div style="height:210px;display:flex;align-items:center;justify-content:center;flex-direction:column;gap:8px;color:var(--muted);">
          <div style="font-size:24px;">📊</div>
          <div style="font-size:12px;">開啟詳情頁可載入雷達資料</div>
          <button onclick="openDetail('${{s.ticker}}')" style="margin-top:4px;padding:5px 14px;border-radius:6px;border:1px solid var(--border);background:var(--bg2);color:var(--blue);font-size:12px;cursor:pointer;">詳情 →</button>
        </div>`
    }}`;
    g.appendChild(d);
    if(hasRadar)setTimeout(()=>{{
      const cvs=document.getElementById('rc-'+s.ticker);
      if(!cvs)return;
      new Chart(cvs,{{type:'radar',
        data:{{labels:['總分','獲利','成長','估值','財務','市場'],datasets:[{{data:s.radar,
          backgroundColor:col+',0.12)',borderColor:col+',0.8)',pointBackgroundColor:col+',1)',borderWidth:2,pointRadius:3}}]}},
        options:{{responsive:true,scales:{{r:{{min:0,max:100,ticks:{{display:false}},grid:{{color:'rgba(0,0,0,.07)'}},
          pointLabels:{{color:'#78716c',font:{{size:10}}}}}}}},plugins:{{legend:{{display:false}}}}}}
      }});
    }},60);
  }});
  // Update section badges
  const bMain=document.getElementById('rc-badge-main');
  const bWatch=document.getElementById('rc-badge-watch');
  const bLearn=document.getElementById('rc-badge-learn');
  if(bMain)bMain.textContent=document.getElementById('radar-main').children.length+' 檔';
  if(bWatch)bWatch.textContent=document.getElementById('radar-watch').children.length+' 檔';
  if(bLearn)bLearn.textContent=document.getElementById('radar-learn').children.length+' 檔';
}}
function openDetail(ticker){{
  const s=stocks.find(x=>x.ticker===ticker);if(!s)return;
  show('detail');
  const col=COL[s.stock_type||'general'];
  const grade=s.ai>=70?'A':s.ai>=58?'B':s.ai>=45?'C':'D';
  const gradeDesc=s.ai>=70?'體質優良，值得積極研究布局':s.ai>=58?'有亮點，持續追蹤等待訊號':s.ai>=45?'普通，等待催化劑確認':'暫時迴避，風險大於機會';
  const typeLabel=s.type==='main'?'<span class="badge bm">主要持股</span>':'<span class="badge bw">觀望</span>';
  const dims=[['獲利品質','fin',20,'ROE/毛利率/營業利益率/淨利率'],['成長動能','growth_s',20,'營收成長/EPS成長/前瞻動能'],
              ['估值吸引力','valuation',15,'PE/PB/PEG依股票類型調整'],['財務體質','financial',15,'負債比/流動比率/現金流'],['市場面','market',10,'動能/量能/相對大盤']];
  const dimRows=dims.map(([label,key,max,note])=>{{
    const val=s[key]||0,pct=Math.round(val/max*100),c=sc(pct);
    return`<div class="sbi"><div class="sbi-label">${{label}}</div>
      <div class="sbi-bar"><div class="sbi-fill fill-${{c}}" style="width:${{pct}}%"></div></div>
      <div class="sbi-score score-${{c}}">${{val}}</div><div class="sbi-max">/${{max}}</div><div class="sbi-note">${{note}}</div></div>`;
  }}).join('');
  const riskRow=s.risk<0?`<div class="sbi" style="margin-top:6px;border-top:1px solid var(--border);padding-top:8px;">
    <div class="sbi-label" style="color:var(--red)">風險扣分</div><div style="flex:1"></div>
    <div class="sbi-score" style="color:var(--red)">${{s.risk}}</div><div class="sbi-max">/0</div>
    <div class="sbi-note" style="color:var(--red)">${{s.stock_type==='cyclical'&&s.risk<=-4?'景氣循環高峰':s.risk<=-3?'估值陷阱或高槓桿':'財務或估值風險'}}</div></div>`:'';
  const typeRow=s.typeAdj>0?`<div class="sbi" style="margin-top:4px;">
    <div class="sbi-label" style="color:var(--green)">類型加成</div><div style="flex:1"></div>
    <div class="sbi-score" style="color:var(--green)">+${{s.typeAdj}}</div><div class="sbi-max">/5</div>
    <div class="sbi-note" style="color:var(--green)">${{s.stock_type==='growth'?'高品質成長確認':s.stock_type==='turnaround'?'轉型動能確認':'高殖利率防禦'}}</div></div>`:'';
  document.getElementById('detail-content').innerHTML=`
    <div style="display:flex;flex-wrap:wrap;gap:12px;justify-content:space-between;align-items:flex-start;margin-bottom:20px;">
      <div><div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin-bottom:6px;">
        <h1 style="font-size:22px;font-weight:700;">${{s.name}}</h1>
        <span style="color:var(--muted);font-size:16px;">${{s.ticker}}</span>
        ${{typeLabel}} ${{tBadge(s.stock_type||'general')}} ${{tagHtml(s.tag)}}</div>
        <div style="color:var(--muted);font-size:12px;">${{s.sector}}</div></div>
      <div style="text-align:right;">
        <div style="font-size:28px;font-weight:700;">NT$ ${{s.price.toFixed(2)}}</div>
        <div style="font-size:13px;margin-top:3px;">${{chHtml(s.change,s.changePct)}}</div></div>
    </div>
    <div class="mgrid">
      <div class="mc"><div class="ml">AI 總分</div><div class="mv score-${{sc(s.ai)}}" style="font-size:26px;">${{s.ai}}</div><div class="ms">${{grade}}級·${{gradeDesc}}</div></div>
      <div class="mc"><div class="ml">本益比 P/E</div><div class="mv">${{s.pe>0?s.pe+'x':'—'}}</div><div class="ms">TTM</div></div>
      <div class="mc"><div class="ml">股價淨值比 P/B</div><div class="mv">${{s.pb>0?s.pb+'x':'—'}}</div></div>
      <div class="mc"><div class="ml">ROE</div><div class="mv" style="color:${{s.roe>=15?'var(--green)':'var(--text)'}}">${{s.roe>0?s.roe+'%':'—'}}</div><div class="ms">股東權益報酬率</div></div>
      <div class="mc"><div class="ml">EPS</div><div class="mv">${{s.eps>0?'NT$'+s.eps:'—'}}</div></div>
      <div class="mc"><div class="ml">毛利率</div><div class="mv" style="color:${{s.grossMargin>=30?'var(--green)':s.grossMargin>=15?'var(--text)':'var(--red)'}}">${{s.grossMargin>0?s.grossMargin+'%':'—'}}</div></div>
      <div class="mc"><div class="ml">營業利益率</div><div class="mv">${{s.opMargin>0?s.opMargin+'%':'—'}}</div></div>
      <div class="mc"><div class="ml">殖利率</div><div class="mv" style="color:${{s.div>=4?'var(--green)':'var(--text)'}}">${{s.div>0?s.div+'%':'—'}}</div></div>
    </div>
    ${{s.price_dates&&s.price_dates.length>10?`
    <div class="sbc" style="margin-bottom:16px;" id="price-chart-sec-${{ticker}}">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;flex-wrap:wrap;gap:8px;">
        <h3>📈 近6個月價格走勢</h3>
        <div style="display:flex;gap:12px;font-size:12px;color:var(--muted);">
          <span>🟢 最高點</span><span>🔴 最低點</span>
        </div>
      </div>
      <div style="height:200px;"><canvas id="dp-${{ticker}}"></canvas></div>
      <div id="price-stats-${{ticker}}" style="display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-top:12px;"></div>
    </div>`:'<div></div>'}}
    <div class="sbc"><h3>🔬 AI 評分細項拆解</h3>
      ${{dimRows}}${{riskRow}}${{typeRow}}
      <div style="border-top:1px solid var(--border);margin-top:10px;padding-top:10px;display:flex;align-items:center;gap:10px;">
        <div style="font-weight:600;font-size:13px;">總分</div><div style="flex:1"></div>
        <div class="sn score-${{sc(s.ai)}}" style="font-size:20px;">${{s.ai}} / 100</div>
        <div style="margin-left:6px;">${{tagHtml(s.tag)}}</div></div></div>
    <div class="crow">
      <div class="cc"><h3>六維雷達圖</h3><div class="ch"><canvas id="dr-${{ticker}}"></canvas></div></div>
      <div class="cc"><h3>評分 vs 全部均值</h3><div class="ch"><canvas id="db-${{ticker}}"></canvas></div></div>
      <div class="cc"><h3>各維度達成率</h3><div class="ch"><canvas id="dd-${{ticker}}"></canvas></div></div>
    </div>
    <div class="ain"><h3>📝 研究備註</h3>
      <p style="color:var(--muted);font-size:12px;line-height:1.8;margin-top:8px;">${{s.notes||'—'}}</p>
      <div style="display:flex;gap:16px;flex-wrap:wrap;margin-top:12px;padding-top:10px;border-top:1px solid var(--border);font-size:11px;color:var(--muted);">
        <span>⚡ 資料：Yahoo Finance（每日自動更新）</span><span>⚡ 不代表買賣建議</span><span>⚡ 循環股高峰期評分自動折扣</span>
      </div></div>`;
  setTimeout(()=>{{
    // ── Price history chart ──────────────────────────────────────────────
    if(s.price_dates&&s.price_dates.length>10){{
      // Filter out any NaN/null values (yfinance occasionally returns them for partial days)
      const rawDates=s.price_dates||[], rawCloses=s.price_closes||[];
      const pd=[],pc=[];
      for(let i=0;i<rawDates.length;i++){{
        const v=rawCloses[i];
        if(typeof v==='number'&&!isNaN(v)&&v>0){{pd.push(rawDates[i]);pc.push(v);}}
      }}
      const hi=Math.max(...pc), lo=Math.min(...pc);
      const hiIdx=pc.indexOf(hi), loIdx=pc.indexOf(lo);
      const cur=s.price||pc[pc.length-1]||0;
      const hiDist=hi>0?((cur-hi)/hi*100).toFixed(1):'—';
      const loDist=lo>0?((cur-lo)/lo*100).toFixed(1):'—';
      const hiDistNum=hi>0?(cur-hi)/hi*100:0;
      const loDistNum=lo>0?(cur-lo)/lo*100:0;
      new Chart(document.getElementById('dp-'+ticker),{{
        type:'line',
        data:{{
          labels:pd,
          datasets:[
            {{label:'收盤價',data:pc,borderColor:'#2563eb',
              backgroundColor:'rgba(37,99,235,0.07)',borderWidth:2,
              fill:true,pointRadius:0,pointHoverRadius:4,tension:0.3}},
            {{label:'6M最高',data:pc.map((v,i)=>i===hiIdx?v:null),
              borderColor:'#16a34a',backgroundColor:'#16a34a',
              pointRadius:7,pointStyle:'circle',showLine:false,
              pointBorderWidth:2,pointBorderColor:'#fff'}},
            {{label:'6M最低',data:pc.map((v,i)=>i===loIdx?v:null),
              borderColor:'#dc2626',backgroundColor:'#dc2626',
              pointRadius:7,pointStyle:'circle',showLine:false,
              pointBorderWidth:2,pointBorderColor:'#fff'}}
          ]
        }},
        options:{{responsive:true,maintainAspectRatio:false,
          scales:{{
            x:{{grid:{{display:false}},ticks:{{color:'#78716c',font:{{size:10}},maxTicksLimit:8}}}},
            y:{{position:'right',grid:{{color:'rgba(0,0,0,.04)'}},
               ticks:{{color:'#78716c',font:{{size:10}},callback:v=>'$'+v}}}}
          }},
          plugins:{{
            legend:{{display:false}},
            tooltip:{{callbacks:{{
              label:ctx=>{{
                if(ctx.datasetIndex===1)return`🟢 6M最高 NT$${{ctx.parsed.y}}`;
                if(ctx.datasetIndex===2)return`🔴 6M最低 NT$${{ctx.parsed.y}}`;
                return`NT$${{ctx.parsed.y}}`;
              }}
            }}}}
          }}
        }}
      }});
      // Stats row below chart
      const statCard=(label,val,sub,col)=>
        `<div style="background:var(--bg3);border:1px solid var(--border);border-radius:8px;padding:10px 12px;">
          <div style="font-size:10px;color:var(--muted);margin-bottom:4px;">${{label}}</div>
          <div style="font-size:16px;font-weight:700;color:${{col}}">NT$${{val}}</div>
          <div style="font-size:11px;color:var(--muted);margin-top:2px;">${{sub}}</div>
        </div>`;
      const pctCard=(label,pct,col,note)=>
        `<div style="background:var(--bg3);border:1px solid var(--border);border-radius:8px;padding:10px 12px;">
          <div style="font-size:10px;color:var(--muted);margin-bottom:4px;">${{label}}</div>
          <div style="font-size:16px;font-weight:700;color:${{col}}">${{pct>=0?'+':''}}${{pct}}%</div>
          <div style="font-size:11px;color:var(--muted);margin-top:2px;">${{note}}</div>
        </div>`;
      if(pd.length>0)document.getElementById('price-stats-'+ticker).innerHTML=
        statCard('6個月最高價',hi.toFixed(2),'📅 '+pd[hiIdx],'#16a34a')+
        statCard('6個月最低價',lo.toFixed(2),'📅 '+pd[loIdx],'#dc2626')+
        pctCard('距離高點',hiDist,hiDistNum<=-20?'#16a34a':hiDistNum<=-10?'#d97706':'#78716c','越負越接近買點')+
        pctCard('距離低點',loDist,loDistNum>=20?'#dc2626':loDistNum>=10?'#d97706':'#78716c','越正越遠離底部');
    }}
    // ── Radar / bar charts ───────────────────────────────────────────────
    new Chart(document.getElementById('dr-'+ticker),{{type:'radar',
      data:{{labels:['總分','獲利','成長','估值','財務','市場'],datasets:[{{data:s.radar,
        backgroundColor:col+',0.12)',borderColor:col+',0.85)',pointBackgroundColor:col+',1)',borderWidth:2,pointRadius:4}}]}},
      options:{{responsive:true,maintainAspectRatio:false,
        scales:{{r:{{min:0,max:100,ticks:{{display:false}},grid:{{color:'rgba(0,0,0,.07)'}},pointLabels:{{color:'#78716c',font:{{size:10}}}}}}}},
        plugins:{{legend:{{display:false}}}}}}
    }});
    const avg=k=>Math.round(stocks.reduce((a,x)=>a+(x[k]||0),0)/stocks.length);
    new Chart(document.getElementById('db-'+ticker),{{type:'bar',
      data:{{labels:['獲利','成長','估值','財務','市場'],datasets:[
        {{label:s.name,data:[s.fin,s.growth_s,s.valuation,s.financial,s.market],
          backgroundColor:col+',0.85)',borderColor:col+',1)',borderWidth:1,borderRadius:5}},
        {{label:'全部均值',data:[avg('fin'),avg('growth_s'),avg('valuation'),avg('financial'),avg('market')],
          backgroundColor:'rgba(0,0,0,0.06)',borderColor:'rgba(0,0,0,0.2)',borderWidth:1,borderRadius:5}}]}},
      options:{{responsive:true,maintainAspectRatio:false,
        scales:{{y:{{min:0,max:22,grid:{{color:'rgba(0,0,0,.05)'}},ticks:{{color:'#78716c',font:{{size:10}}}}}},
                 x:{{grid:{{display:false}},ticks:{{color:'#78716c',font:{{size:10}}}}}}}},
        plugins:{{legend:{{labels:{{color:'#1c1917',font:{{size:11}},boxWidth:12,padding:16}}}}}}}}
    }});
    // 各維度達成率 — horizontal bar chart with distinct colours per dimension
    const dimColors=['#16a34a','#2563eb','#d97706','#7c3aed','#0891b2'];
    const dimMax=[20,20,15,15,10];
    const dimVals=[s.fin,s.growth_s,s.valuation,s.financial,s.market];
    const dimPct=dimVals.map((v,i)=>Math.round(v/dimMax[i]*100));
    new Chart(document.getElementById('dd-'+ticker),{{type:'bar',
      data:{{labels:['獲利品質','成長動能','估值吸引力','財務體質','市場面'],datasets:[
        {{label:'達成率',data:dimPct,
          backgroundColor:dimColors.map(c=>c+'bb'),
          borderColor:dimColors,borderWidth:1,borderRadius:6,barThickness:18}}]}},
      options:{{indexAxis:'y',responsive:true,maintainAspectRatio:false,
        scales:{{x:{{min:0,max:100,grid:{{color:'rgba(0,0,0,.05)'}},
                    ticks:{{color:'#78716c',font:{{size:10}},callback:v=>v+'%'}}}},
                 y:{{grid:{{display:false}},ticks:{{color:'#1c1917',font:{{size:11}}}}}}}},
        plugins:{{legend:{{display:false}},
                  tooltip:{{callbacks:{{label:ctx=>`${{ctx.parsed.x}}%（${{dimVals[ctx.dataIndex]}} / ${{dimMax[ctx.dataIndex]}}）`}}}}}}}}
    }});
  }},80);
}}
// init local watch rows on page load, then sync from Supabase
applyCfgHides();   // hide any config rows that were previously moved/deleted
renderAllLocalRows();
_sbLoad();
</script>
</body>
</html>'''

Path("index.html").write_text(html,encoding="utf-8")
print(f"\n✅ index.html generated  ({updated_at})")
print(f"   {len(stocks)} stocks | main={len(main_s)} watch={len(watch_s)}")
print(f"\n   Score summary (v2.1 scoring):")
for s in sorted(stocks,key=lambda x:-x["ai"]):
    bar="█"*(s["ai"]//10)+"░"*(10-s["ai"]//10)
    icon="🟢" if s["tag"]=="buy" else "🟡" if s["tag"]=="watch" else "🔵" if s["tag"]=="hold" else "🔴"
    print(f"   {s['ticker']} {s['name']:<8} {bar} {s['ai']:>3}  {icon} {s['tag']:<6} ({s.get('stock_type','—')})")
