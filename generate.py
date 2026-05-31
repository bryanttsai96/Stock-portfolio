#!/usr/bin/env python3
"""
Taiwan Stock AI Scoring Dashboard — v2.2
Scoring: 獲利品質(20)+成長動能(20)+估值(15)+財務(15)+市場面(10)+風險修正(-10)+類型加成(+5)
Total 0-100. ≥70=買入 | 58-69=觀望 | 45-57=持有 | <45=迴避
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

def fetch_stock(cfg):
    symbol=cfg["ticker"]+".TW"
    try:
        info=yf.Ticker(symbol).info
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
            "radar":[ai,bd["profit"],bd["growth"],bd["valuation"],bd["financial"],bd["market"]],
            "ok":True,
        }
    except Exception as e:
        print(f"  ⚠ {cfg['ticker']}: {e}")
        return {**cfg,"price":0,"change":0,"changePct":0,"mktCap":"—",
                "pe":0,"pb":0,"roe":0,"eps":0,"div":0,"revGrowth":0,"grossMargin":0,"opMargin":0,
                "ai":0,"tag":"—","fin":0,"growth_s":0,"valuation":0,"financial":0,"market":0,
                "risk":0,"typeAdj":0,"radar":[0]*6,"ok":False}

print("Fetching stock data...")
stocks=[]
for cfg in stocks_cfg:
    print(f"  {cfg['ticker']} {cfg['name']}...")
    stocks.append(fetch_stock(cfg))

main_s =[s for s in stocks if s["type"]=="main"]
watch_s=[s for s in stocks if s["type"]=="watch"]

def sc(s): return "a" if s>=80 else "b" if s>=70 else "c" if s>=60 else "d"
def tag_html(t):
    m={"buy":"買入","watch":"觀望","hold":"持有","avoid":"迴避","—":"—"}
    return f'<span class="tag tag-{t}">{m.get(t,t)}</span>'
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
def table_rows(lst):
    rows=""
    for s in lst:
        rows+=f'''<tr>
          <td><span class="cn">{s["name"]}</span><span class="tic">{s["ticker"]}</span>
            <div style="margin-top:3px;display:flex;gap:4px;align-items:center;">
              {type_badge(s.get("stock_type","general"))}
              <span style="color:var(--muted);font-size:10px;">&nbsp;{s["sector"]}</span>
            </div></td>
          <td>{s_bar(s["ai"])}</td><td>{s_bar(s["fin"],65)}</td>
          <td>{s_bar(s["growth_s"],65)}</td><td>{s_bar(s["valuation"],65)}</td>
          <td>{s_bar(s["financial"],65)}</td><td>{s_bar(s["market"],65)}</td>
          <td style="font-weight:600;">NT${s["price"]:.2f}</td>
          <td>{ch_html(s["change"],s["changePct"])}</td>
          <td style="color:var(--muted);font-size:12px;">{s["mktCap"]}</td>
          <td>{tag_html(s["tag"])}</td>
          <td><button class="drill" onclick="openDetail('{s["ticker"]}')">詳情 →</button></td>
        </tr>'''
    return rows

stocks_json=json.dumps(stocks,ensure_ascii=False)

html=f'''<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>台股AI研究儀表板</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
:root{{--bg:#0d1117;--bg2:#161b22;--bg3:#21262d;--border:#30363d;--text:#e6edf3;
      --muted:#8b949e;--green:#3fb950;--red:#f85149;--yellow:#d29922;
      --blue:#58a6ff;--purple:#bc8cff;--accent:#1f6feb}}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{background:var(--bg);color:var(--text);font-family:'Segoe UI',system-ui,sans-serif;font-size:14px}}
nav{{background:var(--bg2);border-bottom:1px solid var(--border);padding:0 24px;
     display:flex;align-items:center;gap:8px;height:52px;position:sticky;top:0;z-index:100}}
.logo{{font-size:16px;font-weight:700;color:var(--blue);margin-right:12px;white-space:nowrap}}
.ntab{{padding:6px 14px;border-radius:6px;cursor:pointer;color:var(--muted);font-size:13px;
       border:1px solid transparent;transition:all .15s}}
.ntab:hover{{color:var(--text);background:var(--bg3)}}
.ntab.active{{color:var(--blue);background:rgba(88,166,255,.1);border-color:rgba(88,166,255,.3)}}
.spacer{{flex:1}}
main{{padding:20px 24px}}
.sh{{display:flex;align-items:center;gap:10px;margin-bottom:14px}}
.sh h2{{font-size:16px;font-weight:600}}
.badge{{padding:2px 8px;border-radius:4px;font-size:11px;font-weight:600}}
.bm{{background:rgba(63,185,80,.15);color:var(--green);border:1px solid rgba(63,185,80,.3)}}
.bw{{background:rgba(210,153,34,.15);color:var(--yellow);border:1px solid rgba(210,153,34,.3)}}
.fbar{{display:flex;gap:8px;margin-bottom:18px;flex-wrap:wrap;align-items:center}}
.fbtn{{padding:5px 12px;border-radius:20px;border:1px solid var(--border);
       background:var(--bg2);color:var(--muted);cursor:pointer;font-size:12px;transition:all .15s}}
.fbtn:hover{{border-color:var(--blue);color:var(--blue)}}
.fbtn.active{{background:var(--accent);border-color:var(--accent);color:#fff}}
.sw{{background:var(--bg2);border:1px solid var(--border);border-radius:10px;
     overflow:hidden;margin-bottom:28px;overflow-x:auto}}
.sw table{{width:100%;border-collapse:collapse;min-width:920px}}
.sw th{{background:var(--bg3);color:var(--muted);font-size:10px;font-weight:600;
        text-transform:uppercase;letter-spacing:.4px;padding:9px 12px;
        text-align:left;border-bottom:1px solid var(--border)}}
.sw td{{padding:10px 12px;border-bottom:1px solid var(--border);vertical-align:middle}}
.sw tr:last-child td{{border-bottom:none}}
.sw tr:hover td{{background:rgba(255,255,255,.025)}}
.cn{{font-weight:600;font-size:13px}}.tic{{color:var(--muted);font-size:11px;margin-left:5px}}
.tbadge{{padding:1px 6px;border-radius:3px;font-size:10px;font-weight:600}}
.tb-growth{{background:rgba(88,166,255,.15);color:var(--blue)}}
.tb-value{{background:rgba(63,185,80,.15);color:var(--green)}}
.tb-cyclical{{background:rgba(210,153,34,.15);color:var(--yellow)}}
.tb-turnaround{{background:rgba(188,140,255,.15);color:var(--purple)}}
.tb-dividend,.tb-general{{background:rgba(139,148,158,.15);color:var(--muted)}}
.sbw{{display:flex;align-items:center;gap:6px}}
.sb{{height:6px;border-radius:3px;background:var(--bg3);overflow:hidden}}
.sf{{height:100%;border-radius:3px}}
.score-a{{color:var(--green)}}.fill-a{{background:var(--green)}}
.score-b{{color:var(--blue)}} .fill-b{{background:var(--blue)}}
.score-c{{color:var(--yellow)}}.fill-c{{background:var(--yellow)}}
.score-d{{color:var(--red)}}  .fill-d{{background:var(--red)}}
.sn{{font-size:13px;font-weight:700;min-width:26px}}
.ch-pos{{color:var(--green)}}.ch-neg{{color:var(--red)}}
.tag{{display:inline-block;padding:2px 7px;border-radius:4px;font-size:10px;font-weight:700}}
.tag-buy{{background:rgba(63,185,80,.2);color:var(--green)}}
.tag-watch{{background:rgba(210,153,34,.2);color:var(--yellow)}}
.tag-hold{{background:rgba(88,166,255,.2);color:var(--blue)}}
.tag-avoid{{background:rgba(248,81,73,.2);color:var(--red)}}
.drill{{padding:4px 10px;border-radius:5px;border:1px solid var(--border);
        background:transparent;color:var(--muted);font-size:11px;cursor:pointer;transition:all .15s}}
.drill:hover{{border-color:var(--blue);color:var(--blue);background:rgba(88,166,255,.08)}}
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
.ain{{background:var(--bg2);border:1px solid var(--border);border-radius:8px;padding:16px;margin-bottom:16px}}
.ain h3{{font-size:13px;font-weight:600;margin-bottom:8px}}
.tleg{{display:flex;gap:16px;flex-wrap:wrap;margin-bottom:18px}}
.tleg-i{{display:flex;align-items:center;gap:6px;font-size:12px;color:var(--muted)}}
.tdot{{width:10px;height:10px;border-radius:50%}}
.back{{padding:6px 14px;border-radius:6px;border:1px solid var(--border);background:var(--bg2);
       color:var(--text);cursor:pointer;font-size:13px;display:inline-flex;align-items:center;gap:6px}}
.back:hover{{border-color:var(--blue);color:var(--blue)}}
::-webkit-scrollbar{{width:6px;height:6px}}
::-webkit-scrollbar-track{{background:var(--bg)}}
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
  <div style="color:var(--muted);font-size:11px;">更新：{updated_at}</div>
</nav>
<main>
<div id="p-overview">
  <div class="tleg">
    <div class="tleg-i"><div class="tdot" style="background:var(--green)"></div>≥70 買入</div>
    <div class="tleg-i"><div class="tdot" style="background:var(--yellow)"></div>58–69 觀望</div>
    <div class="tleg-i"><div class="tdot" style="background:var(--blue)"></div>45–57 持有</div>
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
    <button class="fbtn active" onclick="filt('all',this)">全部</button>
    <button class="fbtn" onclick="filt('main',this)">主要持股</button>
    <button class="fbtn" onclick="filt('watch',this)">觀望清單</button>
    <button class="fbtn" onclick="filt('buy',this)">🟢 買入 ≥70</button>
    <button class="fbtn" onclick="filt('wtag',this)">🟡 觀望 58-69</button>
    <button class="fbtn" onclick="filt('hold',this)">🔵 持有/迴避</button>
    <span style="margin-left:auto;color:var(--muted);font-size:12px;">點擊「詳情」查看評分細項</span>
  </div>
  <div class="sh"><h2>主要持股</h2><span class="badge bm">{len(main_s)} 檔</span></div>
  <div class="sw"><table>
    <thead><tr><th>代號／名稱</th><th>AI總分</th><th>獲利品質</th><th>成長動能</th>
      <th>估值</th><th>財務</th><th>市場面</th><th>現價</th><th>漲跌</th><th>市值</th><th>建議</th><th></th></tr></thead>
    <tbody id="tb-main">{table_rows(main_s)}</tbody>
  </table></div>
  <div class="sh"><h2>觀望清單</h2><span class="badge bw">{len(watch_s)} 檔</span></div>
  <div class="sw"><table>
    <thead><tr><th>代號／名稱</th><th>AI總分</th><th>獲利品質</th><th>成長動能</th>
      <th>估值</th><th>財務</th><th>市場面</th><th>現價</th><th>漲跌</th><th>市值</th><th>建議</th><th></th></tr></thead>
    <tbody id="tb-watch">{table_rows(watch_s)}</tbody>
  </table></div>
</div>

<div id="p-comparison" style="display:none">
  <div class="sh" style="margin-bottom:20px"><h2>AI 六維雷達比較</h2></div>
  <div class="rgrid" id="radar-grid"></div>
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
      <div style="background:rgba(63,185,80,.08);border:1px solid rgba(63,185,80,.2);border-radius:6px;padding:12px;">
        <div style="font-size:20px;font-weight:700;color:var(--green);">≥70</div>
        <div style="font-weight:600;margin:4px 0;">🟢 買入</div>
        <div style="color:var(--muted);font-size:11px;">體質優良，值得積極布局</div></div>
      <div style="background:rgba(210,153,34,.08);border:1px solid rgba(210,153,34,.2);border-radius:6px;padding:12px;">
        <div style="font-size:20px;font-weight:700;color:var(--yellow);">58–69</div>
        <div style="font-weight:600;margin:4px 0;">🟡 觀望</div>
        <div style="color:var(--muted);font-size:11px;">有亮點但需等待催化劑</div></div>
      <div style="background:rgba(88,166,255,.08);border:1px solid rgba(88,166,255,.2);border-radius:6px;padding:12px;">
        <div style="font-size:20px;font-weight:700;color:var(--blue);">45–57</div>
        <div style="font-weight:600;margin:4px 0;">🔵 持有</div>
        <div style="color:var(--muted);font-size:11px;">普通，低優先追蹤</div></div>
      <div style="background:rgba(248,81,73,.08);border:1px solid rgba(248,81,73,.2);border-radius:6px;padding:12px;">
        <div style="font-size:20px;font-weight:700;color:var(--red);">&lt;45</div>
        <div style="font-weight:600;margin:4px 0;">🔴 迴避</div>
        <div style="color:var(--muted);font-size:11px;">風險大於機會</div></div>
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
const COL={{growth:'rgba(88,166,255',value:'rgba(63,185,80',cyclical:'rgba(210,153,34',
            turnaround:'rgba(188,140,255',dividend:'rgba(63,185,80',general:'rgba(139,148,158'}};
function sc(s){{return s>=80?'a':s>=70?'b':s>=60?'c':'d'}}
function tagHtml(t){{const m={{buy:'買入',watch:'觀望',hold:'持有',avoid:'迴避','—':'—'}};return`<span class="tag tag-${{t}}">${{m[t]||t}}</span>`;}}
function chHtml(v,p){{return`<span class="ch-${{v>=0?'pos':'neg'}}">${{v>=0?'+':''}}${{v.toFixed(2)}} (${{v>=0?'+':''}}${{p.toFixed(2)}}%)</span>`;}}
function sBar(s,w,mx){{mx=mx||100;const pct=Math.round(s/mx*100);const c=sc(pct);w=w||80;const lbl=mx===100?`${{s}}`:`${{s}}<span style="color:var(--muted);font-size:10px;font-weight:400;">/${{mx}}</span>`;return`<div class="sbw"><div class="sb" style="width:${{w}}px"><div class="sf fill-${{c}}" style="width:${{pct}}%"></div></div><span class="sn score-${{c}}">${{lbl}}</span></div>`;}}
function tBadge(t){{const m={{growth:'成長股',value:'價值股',cyclical:'循環股',turnaround:'轉型股',dividend:'存股型',general:'一般型'}};return`<span class="tbadge tb-${{t}}">${{m[t]||t}}</span>`;}}
function renderTbody(id,list){{
  const tb=document.getElementById(id);
  if(!list.length){{tb.innerHTML='<tr><td colspan="12" style="text-align:center;color:var(--muted);padding:24px">無符合條件</td></tr>';return;}}
  tb.innerHTML=list.map(s=>`<tr>
    <td><span class="cn">${{s.name}}</span><span class="tic">${{s.ticker}}</span>
        <div style="margin-top:3px;display:flex;gap:4px;align-items:center;">${{tBadge(s.stock_type||'general')}}&nbsp;<span style="color:var(--muted);font-size:10px;">${{s.sector}}</span></div></td>
    <td>${{sBar(s.ai)}}</td><td>${{sBar(s.fin,70,20)}}</td><td>${{sBar(s.growth_s,70,20)}}</td>
    <td>${{sBar(s.valuation,70,15)}}</td><td>${{sBar(s.financial,70,15)}}</td><td>${{sBar(s.market,70,10)}}</td>
    <td style="font-weight:600;">NT$${{s.price.toFixed(2)}}</td><td>${{chHtml(s.change,s.changePct)}}</td>
    <td style="color:var(--muted);font-size:12px;">${{s.mktCap}}</td>
    <td>${{tagHtml(s.tag)}}</td><td><button class="drill" onclick="openDetail('${{s.ticker}}')">詳情 →</button></td>
  </tr>`).join('');
}}
function filt(type,btn){{
  document.querySelectorAll('.fbtn').forEach(b=>b.classList.remove('active'));btn.classList.add('active');
  let m=stocks.filter(s=>s.type==='main'),w=stocks.filter(s=>s.type==='watch');
  if(type==='main') w=[];else if(type==='watch') m=[];
  else if(type==='buy'){{m=m.filter(s=>s.tag==='buy');w=w.filter(s=>s.tag==='buy');}}
  else if(type==='wtag'){{m=m.filter(s=>s.tag==='watch');w=w.filter(s=>s.tag==='watch');}}
  else if(type==='hold'){{m=m.filter(s=>s.tag==='hold'||s.tag==='avoid');w=w.filter(s=>s.tag==='hold'||s.tag==='avoid');}}
  renderTbody('tb-main',m);renderTbody('tb-watch',w);
}}
function show(name){{
  ['overview','comparison','legend','detail'].forEach(p=>document.getElementById('p-'+p).style.display='none');
  document.getElementById('p-'+name).style.display='block';
  document.querySelectorAll('.ntab').forEach((t,i)=>t.classList.toggle('active',['overview','comparison','legend'][i]===name));
  if(name==='comparison')renderRadar();
}}
let radarDone=false;
function renderRadar(){{
  if(radarDone)return;radarDone=true;
  const g=document.getElementById('radar-grid');
  stocks.forEach(s=>{{
    const col=COL[s.stock_type||'general'];
    const d=document.createElement('div');d.className='rc';
    d.innerHTML=`<div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:8px;">
      <div><div style="font-size:13px;font-weight:600;">${{s.name}} <span style="color:var(--muted);font-size:11px;">${{s.ticker}}</span></div>
      <div style="margin-top:3px;display:flex;gap:4px;">${{tBadge(s.stock_type||'general')}}&nbsp;<span style="color:var(--muted);font-size:10px;">${{s.sector}}</span></div></div>
      <div style="text-align:right;"><div class="sn score-${{sc(s.ai)}}" style="font-size:20px;">${{s.ai}}</div>${{tagHtml(s.tag)}}</div>
    </div><canvas id="rc-${{s.ticker}}" height="210"></canvas>`;
    g.appendChild(d);
    setTimeout(()=>new Chart(document.getElementById('rc-'+s.ticker),{{type:'radar',
      data:{{labels:['總分','獲利','成長','估值','財務','市場'],datasets:[{{data:s.radar,
        backgroundColor:col+',0.12)',borderColor:col+',0.8)',pointBackgroundColor:col+',1)',borderWidth:2,pointRadius:3}}]}},
      options:{{responsive:true,scales:{{r:{{min:0,max:100,ticks:{{display:false}},grid:{{color:'rgba(255,255,255,.07)'}},
        pointLabels:{{color:'#8b949e',font:{{size:10}}}}}}}},plugins:{{legend:{{display:false}}}}}}
    }}),60);
  }});
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
    new Chart(document.getElementById('dr-'+ticker),{{type:'radar',
      data:{{labels:['總分','獲利','成長','估值','財務','市場'],datasets:[{{data:s.radar,
        backgroundColor:col+',0.12)',borderColor:col+',0.85)',pointBackgroundColor:col+',1)',borderWidth:2,pointRadius:4}}]}},
      options:{{responsive:true,maintainAspectRatio:false,
        scales:{{r:{{min:0,max:100,ticks:{{display:false}},grid:{{color:'rgba(255,255,255,.07)'}},pointLabels:{{color:'#8b949e',font:{{size:10}}}}}}}},
        plugins:{{legend:{{display:false}}}}}}
    }});
    const avg=k=>Math.round(stocks.reduce((a,x)=>a+(x[k]||0),0)/stocks.length);
    new Chart(document.getElementById('db-'+ticker),{{type:'bar',
      data:{{labels:['獲利','成長','估值','財務','市場'],datasets:[
        {{label:s.name,data:[s.fin,s.growth_s,s.valuation,s.financial,s.market],backgroundColor:col+',0.75)',borderRadius:4}},
        {{label:'全部均值',data:[avg('fin'),avg('growth_s'),avg('valuation'),avg('financial'),avg('market')],backgroundColor:'rgba(139,148,158,0.35)',borderRadius:4}}]}},
      options:{{responsive:true,maintainAspectRatio:false,
        scales:{{y:{{min:0,max:22,grid:{{color:'rgba(255,255,255,.05)'}},ticks:{{color:'#8b949e',font:{{size:10}}}}}},x:{{grid:{{display:false}},ticks:{{color:'#8b949e',font:{{size:10}}}}}}}},
        plugins:{{legend:{{labels:{{color:'#8b949e',font:{{size:10}}}}}}}}}}
    }});
    const mx=[20,20,15,15,10],vl=[s.fin,s.growth_s,s.valuation,s.financial,s.market];
    new Chart(document.getElementById('dd-'+ticker),{{type:'doughnut',
      data:{{labels:['獲利','成長','估值','財務','市場'],datasets:[
        {{data:vl,backgroundColor:[col+',0.8)',col+',0.65)',col+',0.5)',col+',0.38)',col+',0.25)'],borderWidth:1,borderColor:'rgba(0,0,0,.2)'}},
        {{data:mx.map((m,i)=>m-vl[i]),backgroundColor:Array(5).fill('rgba(33,38,45,.9)'),borderWidth:0}}]}},
      options:{{responsive:true,maintainAspectRatio:false,cutout:'58%',
        plugins:{{legend:{{position:'right',labels:{{color:'#8b949e',font:{{size:10}},boxWidth:10}}}}}}}}
    }});
  }},80);
}}
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
