#!/usr/bin/env python3
"""
Taiwan Stock Dashboard Generator
- Reads stock list from config.json
- Fetches live data from Yahoo Finance (TWSE tickers append .TW)
- Scores each stock across 4 dimensions using available financial data
- Writes index.html

To add a new stock: edit config.json only.
"""

import json, math, sys, datetime
from pathlib import Path

try:
    import yfinance as yf
except ImportError:
    print("Run: pip install yfinance")
    sys.exit(1)

# ─── Load config ──────────────────────────────────────────────────────────────
config = json.loads(Path("config.json").read_text())
stocks_cfg = config["stocks"]
updated_at = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).strftime("%Y-%m-%d %H:%M TST")

# ─── Fetch data from Yahoo Finance ────────────────────────────────────────────
def fetch_stock(cfg):
    symbol = cfg["ticker"] + ".TW"
    try:
        t = yf.Ticker(symbol)
        info = t.info
        hist = t.history(period="3mo")

        price     = info.get("currentPrice") or info.get("regularMarketPrice") or 0
        prev      = info.get("regularMarketPreviousClose") or price
        change    = round(price - prev, 2)
        change_pct= round((change / prev * 100) if prev else 0, 2)
        mkt_cap   = info.get("marketCap", 0)
        pe        = info.get("trailingPE") or info.get("forwardPE") or 0
        pb        = info.get("priceToBook") or 0
        roe       = round((info.get("returnOnEquity") or 0) * 100, 1)
        eps       = info.get("trailingEps") or 0
        div_yield = round((info.get("dividendYield") or 0) * 100, 2)
        rev_growth= round((info.get("revenueGrowth") or 0) * 100, 1)
        gross_margin = round((info.get("grossMargins") or 0) * 100, 1)
        debt_equity = info.get("debtToEquity") or 0
        current_ratio = info.get("currentRatio") or 0
        vol       = info.get("volume") or 0
        avg_vol   = info.get("averageVolume") or 1
        week52_high = info.get("fiftyTwoWeekHigh") or price
        week52_low  = info.get("fiftyTwoWeekLow") or price

        # ── Scoring (0-100 each dimension) ───────────────────────────────────
        # Financial score: ROE, gross margin, current ratio, debt/equity
        fin = 50
        fin += min(20, roe * 0.8)                           # ROE contribution
        fin += min(15, gross_margin * 0.3)                  # gross margin
        fin += min(10, current_ratio * 5)                   # liquidity
        fin -= min(15, debt_equity * 0.05)                  # debt penalty
        fin = max(30, min(100, round(fin)))

        # Technical score: price vs 52w range, volume vs avg
        price_range = week52_high - week52_low
        price_position = ((price - week52_low) / price_range * 100) if price_range else 50
        vol_ratio = (vol / avg_vol) if avg_vol else 1
        tech = 40 + price_position * 0.3 + min(15, vol_ratio * 5)
        tech = max(30, min(100, round(tech)))

        # Chips/institutional score: approximate from vol pattern + div yield
        chips = 55
        chips += min(15, div_yield * 2)
        chips += min(10, vol_ratio * 3)
        chips = max(30, min(100, round(chips)))

        # Growth score: revenue growth, EPS trend
        growth = 55
        growth += min(30, rev_growth * 0.8) if rev_growth > 0 else max(-20, rev_growth * 0.5)
        growth += min(10, max(-10, roe * 0.2))
        growth = max(30, min(100, round(growth)))

        # AI composite score (weighted)
        ai = round(fin * 0.25 + tech * 0.25 + chips * 0.20 + growth * 0.30)
        radar = [ai, fin, tech, chips, growth, round((fin + growth) / 2)]

        # Tag
        if ai >= 82:   tag = "buy"
        elif ai >= 72: tag = "hold"
        elif ai >= 60: tag = "watch"
        else:          tag = "avoid"

        # Market cap formatted
        if mkt_cap >= 1e12:
            cap_str = f"{mkt_cap/1e12:.1f}兆"
        elif mkt_cap >= 1e8:
            cap_str = f"{mkt_cap/1e8:.0f}億"
        else:
            cap_str = f"{mkt_cap/1e6:.0f}百萬" if mkt_cap else "—"

        return {
            **cfg,
            "price": round(price, 2),
            "change": change,
            "changePct": change_pct,
            "mktCap": cap_str,
            "pe": round(pe, 1),
            "pb": round(pb, 2),
            "roe": roe,
            "eps": round(eps, 2),
            "div": div_yield,
            "revGrowth": rev_growth,
            "grossMargin": gross_margin,
            "ai": ai, "fin": fin, "tech": tech, "chips": chips, "growth": growth,
            "radar": radar,
            "tag": tag,
            "ok": True
        }
    except Exception as e:
        print(f"  ⚠ {cfg['ticker']}: {e}")
        return {**cfg, "price":0,"change":0,"changePct":0,"mktCap":"—",
                "pe":0,"pb":0,"roe":0,"eps":0,"div":0,"revGrowth":0,"grossMargin":0,
                "ai":0,"fin":0,"tech":0,"chips":0,"growth":0,"radar":[0]*6,"tag":"—","ok":False}

print("Fetching stock data...")
stocks = []
for cfg in stocks_cfg:
    print(f"  {cfg['ticker']} {cfg['name']}...")
    stocks.append(fetch_stock(cfg))

# ─── HTML Template ────────────────────────────────────────────────────────────
def score_class(s):
    if s >= 80: return 'a'
    if s >= 70: return 'b'
    if s >= 60: return 'c'
    return 'd'

def tag_html(t):
    m = {'buy':'買入','hold':'持有','watch':'觀望','avoid':'迴避','—':'—'}
    return f'<span class="tag tag-{t}">{m.get(t,t)}</span>'

def score_bar(s):
    c = score_class(s)
    return f'''<div class="score-bar-wrap">
      <div class="score-bar"><div class="score-fill fill-{c}" style="width:{s}%"></div></div>
      <span class="score-num score-{c}">{s}</span>
    </div>'''

def mini_bar(s):
    c = score_class(s)
    return f'''<div class="score-bar-wrap">
      <div class="score-bar" style="width:60px"><div class="score-fill fill-{c}" style="width:{s}%"></div></div>
      <span class="score-num score-{c}" style="font-size:12px">{s}</span>
    </div>'''

def change_html(v, pct):
    cls = 'change-pos' if v >= 0 else 'change-neg'
    sign = '+' if v >= 0 else ''
    return f'<span class="{cls}">{sign}{v:.2f} ({sign}{pct:.2f}%)</span>'

def table_rows(stock_list):
    rows = ''
    for s in stock_list:
        rows += f'''<tr data-type="{s['type']}" data-tag="{s['tag']}">
          <td>
            <span class="company-name">{s['name']}</span>
            <span class="ticker">{s['ticker']}</span>
            <div style="color:var(--muted);font-size:10px;margin-top:2px;">{s['sector']}</div>
          </td>
          <td>{score_bar(s['ai'])}</td>
          <td>{mini_bar(s['fin'])}</td>
          <td>{mini_bar(s['tech'])}</td>
          <td>{mini_bar(s['chips'])}</td>
          <td>{mini_bar(s['growth'])}</td>
          <td style="font-weight:600;">NT${s['price']:.2f}</td>
          <td>{change_html(s['change'], s['changePct'])}</td>
          <td style="color:var(--muted);font-size:12px;">{s['mktCap']}</td>
          <td>{tag_html(s['tag'])}</td>
          <td><button class="drill-btn" onclick="openDetail('{s['ticker']}')">詳情 →</button></td>
        </tr>'''
    return rows

main_stocks  = [s for s in stocks if s['type'] == 'main']
watch_stocks = [s for s in stocks if s['type'] == 'watch']

stocks_json = json.dumps(stocks, ensure_ascii=False)

html = f'''<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>台股AI研究儀表板</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
  :root {{
    --bg:#0d1117;--bg2:#161b22;--bg3:#21262d;--border:#30363d;
    --text:#e6edf3;--muted:#8b949e;--green:#3fb950;--red:#f85149;
    --yellow:#d29922;--blue:#58a6ff;--purple:#bc8cff;--orange:#ffa657;
    --accent:#1f6feb;
  }}
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{background:var(--bg);color:var(--text);font-family:'Segoe UI',system-ui,sans-serif;font-size:14px}}
  nav{{background:var(--bg2);border-bottom:1px solid var(--border);padding:0 24px;display:flex;align-items:center;gap:8px;height:52px;position:sticky;top:0;z-index:100}}
  nav .logo{{font-size:16px;font-weight:700;color:var(--blue);margin-right:16px;white-space:nowrap}}
  nav .tab{{padding:6px 14px;border-radius:6px;cursor:pointer;color:var(--muted);font-size:13px;transition:all .15s;border:1px solid transparent}}
  nav .tab:hover{{color:var(--text);background:var(--bg3)}}
  nav .tab.active{{color:var(--blue);background:rgba(88,166,255,.1);border-color:rgba(88,166,255,.3)}}
  nav .spacer{{flex:1}}
  main{{padding:20px 24px}}
  .section-header{{display:flex;align-items:center;gap:12px;margin-bottom:16px}}
  .section-header h2{{font-size:16px;font-weight:600}}
  .badge{{padding:2px 8px;border-radius:4px;font-size:11px;font-weight:600}}
  .badge-main{{background:rgba(63,185,80,.15);color:var(--green);border:1px solid rgba(63,185,80,.3)}}
  .badge-watch{{background:rgba(210,153,34,.15);color:var(--yellow);border:1px solid rgba(210,153,34,.3)}}
  .filter-bar{{display:flex;gap:8px;margin-bottom:20px;flex-wrap:wrap;align-items:center}}
  .filter-btn{{padding:5px 12px;border-radius:20px;border:1px solid var(--border);background:var(--bg2);color:var(--muted);cursor:pointer;font-size:12px;transition:all .15s}}
  .filter-btn:hover{{border-color:var(--blue);color:var(--blue)}}
  .filter-btn.active{{background:var(--accent);border-color:var(--accent);color:#fff}}
  .scorecard-wrap{{background:var(--bg2);border:1px solid var(--border);border-radius:10px;overflow:hidden;margin-bottom:28px}}
  .scorecard-wrap table{{width:100%;border-collapse:collapse}}
  .scorecard-wrap th{{background:var(--bg3);color:var(--muted);font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:.5px;padding:10px 14px;text-align:left;border-bottom:1px solid var(--border)}}
  .scorecard-wrap td{{padding:11px 14px;border-bottom:1px solid var(--border);vertical-align:middle}}
  .scorecard-wrap tr:last-child td{{border-bottom:none}}
  .scorecard-wrap tr:hover td{{background:rgba(255,255,255,.03)}}
  .company-name{{font-weight:600;font-size:13px}}
  .ticker{{color:var(--muted);font-size:11px;margin-left:6px}}
  .score-bar-wrap{{display:flex;align-items:center;gap:8px}}
  .score-bar{{height:6px;border-radius:3px;background:var(--bg3);width:80px;overflow:hidden}}
  .score-fill{{height:100%;border-radius:3px}}
  .score-num{{font-size:13px;font-weight:700;min-width:28px}}
  .score-a{{color:var(--green)}}.fill-a{{background:var(--green)}}
  .score-b{{color:var(--blue)}}.fill-b{{background:var(--blue)}}
  .score-c{{color:var(--yellow)}}.fill-c{{background:var(--yellow)}}
  .score-d{{color:var(--red)}}.fill-d{{background:var(--red)}}
  .change-pos{{color:var(--green)}}.change-neg{{color:var(--red)}}
  .tag{{display:inline-block;padding:2px 7px;border-radius:4px;font-size:10px;font-weight:700}}
  .tag-buy{{background:rgba(63,185,80,.2);color:var(--green)}}
  .tag-hold{{background:rgba(88,166,255,.2);color:var(--blue)}}
  .tag-watch{{background:rgba(210,153,34,.2);color:var(--yellow)}}
  .tag-avoid{{background:rgba(248,81,73,.2);color:var(--red)}}
  .drill-btn{{padding:4px 10px;border-radius:5px;border:1px solid var(--border);background:transparent;color:var(--muted);font-size:11px;cursor:pointer;transition:all .15s}}
  .drill-btn:hover{{border-color:var(--blue);color:var(--blue);background:rgba(88,166,255,.08)}}
  .metrics-grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(155px,1fr));gap:12px;margin-bottom:20px}}
  .metric-card{{background:var(--bg2);border:1px solid var(--border);border-radius:8px;padding:14px}}
  .metric-label{{color:var(--muted);font-size:11px;margin-bottom:6px}}
  .metric-value{{font-size:18px;font-weight:700}}
  .metric-sub{{color:var(--muted);font-size:11px;margin-top:3px}}
  .charts-row{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:16px;margin-bottom:20px}}
  .chart-card{{background:var(--bg2);border:1px solid var(--border);border-radius:8px;padding:16px}}
  .chart-card h3{{font-size:13px;color:var(--muted);margin-bottom:12px;font-weight:600}}
  .chart-container{{position:relative;height:180px}}
  .ai-analysis{{background:var(--bg2);border:1px solid var(--border);border-radius:8px;padding:16px;margin-bottom:16px}}
  .ai-analysis h3{{font-size:13px;font-weight:600;margin-bottom:12px}}
  .ai-grid{{display:grid;grid-template-columns:1fr 1fr;gap:12px}}
  .ai-item{{padding:10px 12px;background:var(--bg3);border-radius:6px}}
  .ai-item-label{{color:var(--muted);font-size:11px;margin-bottom:4px}}
  .ai-item-text{{font-size:12px;line-height:1.6}}
  .back-btn{{padding:6px 14px;border-radius:6px;border:1px solid var(--border);background:var(--bg2);color:var(--text);cursor:pointer;font-size:13px;display:inline-flex;align-items:center;gap:6px;transition:all .15s}}
  .back-btn:hover{{border-color:var(--blue);color:var(--blue)}}
  .radar-grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:16px;margin-bottom:20px}}
  .radar-card{{background:var(--bg2);border:1px solid var(--border);border-radius:8px;padding:16px}}
  .radar-card h3{{font-size:13px;font-weight:600;margin-bottom:4px}}
  ::-webkit-scrollbar{{width:6px;height:6px}}
  ::-webkit-scrollbar-track{{background:var(--bg)}}
  ::-webkit-scrollbar-thumb{{background:var(--border);border-radius:3px}}
  @media(max-width:900px){{.charts-row{{grid-template-columns:1fr 1fr}}}}
  @media(max-width:600px){{.charts-row{{grid-template-columns:1fr}};main{{padding:14px}};nav{{padding:0 14px}}}}
</style>
</head>
<body>
<nav>
  <div class="logo">📊 台股AI研究</div>
  <div class="tab active" onclick="showPanel('overview')">總覽</div>
  <div class="tab" onclick="showPanel('comparison')">雷達比較</div>
  <div class="spacer"></div>
  <div style="color:var(--muted);font-size:11px;">資料更新：{updated_at}</div>
</nav>
<main>

<div id="overview-panel">
  <div class="filter-bar">
    <span style="color:var(--muted);font-size:12px;">篩選：</span>
    <button class="filter-btn active" onclick="filterStocks('all',this)">全部</button>
    <button class="filter-btn" onclick="filterStocks('main',this)">主要持股</button>
    <button class="filter-btn" onclick="filterStocks('watch',this)">觀望清單</button>
    <button class="filter-btn" onclick="filterStocks('buy',this)">建議買入</button>
    <button class="filter-btn" onclick="filterStocks('hold',this)">持有</button>
    <span style="margin-left:auto;color:var(--muted);font-size:12px;">點擊「詳情」查看個股深度分析</span>
  </div>

  <div class="section-header">
    <h2>主要持股</h2>
    <span class="badge badge-main">{len(main_stocks)} 檔</span>
  </div>
  <div class="scorecard-wrap">
    <table><thead><tr>
      <th>代號 / 名稱</th><th>AI 評分</th><th>財務</th><th>技術面</th>
      <th>籌碼</th><th>成長性</th><th>現價</th><th>漲跌</th><th>市值</th><th>建議</th><th></th>
    </tr></thead>
    <tbody id="main-tbody">{table_rows(main_stocks)}</tbody></table>
  </div>

  <div class="section-header">
    <h2>觀望清單</h2>
    <span class="badge badge-watch">{len(watch_stocks)} 檔</span>
  </div>
  <div class="scorecard-wrap">
    <table><thead><tr>
      <th>代號 / 名稱</th><th>AI 評分</th><th>財務</th><th>技術面</th>
      <th>籌碼</th><th>成長性</th><th>現價</th><th>漲跌</th><th>市值</th><th>建議</th><th></th>
    </tr></thead>
    <tbody id="watch-tbody">{table_rows(watch_stocks)}</tbody></table>
  </div>
</div>

<div id="comparison-panel" style="display:none">
  <div class="section-header" style="margin-bottom:20px">
    <h2>AI 雷達評分比較</h2>
    <span class="badge badge-main">全部持股</span>
  </div>
  <div class="radar-grid" id="radar-grid"></div>
</div>

<div id="detail-panel" style="display:none">
  <button class="back-btn" onclick="closeDetail()">← 返回總覽</button>
  <div id="detail-content" style="margin-top:20px"></div>
</div>

</main>

<script>
const stocks = {stocks_json};

function scoreClass(s){{return s>=80?'a':s>=70?'b':s>=60?'c':'d'}}
function tagHtml(t){{const m={{buy:'買入',hold:'持有',watch:'觀望',avoid:'迴避','—':'—'}};return`<span class="tag tag-${{t}}">${{m[t]||t}}</span>`}}
function changeHtml(v,p){{const cl=v>=0?'change-pos':'change-neg',s=v>=0?'+':'';return`<span class="${{cl}}">${{s}}${{v.toFixed(2)}} (${{s}}${{p.toFixed(2)}}%)</span>`}}
function scoreBarHtml(s){{const c=scoreClass(s);return`<div class="score-bar-wrap"><div class="score-bar"><div class="score-fill fill-${{c}}" style="width:${{s}}%"></div></div><span class="score-num score-${{c}}">${{s}}</span></div>`}}
function miniBar(s){{const c=scoreClass(s);return`<div class="score-bar-wrap"><div class="score-bar" style="width:60px"><div class="score-fill fill-${{c}}" style="width:${{s}}%"></div></div><span class="score-num score-${{c}}" style="font-size:12px">${{s}}</span></div>`}}

function filterStocks(type,btn){{
  document.querySelectorAll('.filter-btn').forEach(b=>b.classList.remove('active'));
  btn.classList.add('active');
  const all = stocks;
  let main = all.filter(s=>s.type==='main');
  let watch = all.filter(s=>s.type==='watch');
  if(type==='main') watch=[];
  else if(type==='watch') main=[];
  else if(type==='buy'){{main=main.filter(s=>s.tag==='buy');watch=watch.filter(s=>s.tag==='buy')}}
  else if(type==='hold'){{main=main.filter(s=>s.tag==='hold');watch=watch.filter(s=>s.tag==='hold')}}
  renderTbody('main-tbody',main);
  renderTbody('watch-tbody',watch);
}}

function renderTbody(id,list){{
  const tb=document.getElementById(id);
  if(!list.length){{tb.innerHTML='<tr><td colspan="11" style="text-align:center;color:var(--muted);padding:24px">無符合條件</td></tr>';return}}
  tb.innerHTML=list.map(s=>`<tr>
    <td><span class="company-name">${{s.name}}</span><span class="ticker">${{s.ticker}}</span><div style="color:var(--muted);font-size:10px;margin-top:2px;">${{s.sector}}</div></td>
    <td>${{scoreBarHtml(s.ai)}}</td><td>${{miniBar(s.fin)}}</td><td>${{miniBar(s.tech)}}</td>
    <td>${{miniBar(s.chips)}}</td><td>${{miniBar(s.growth)}}</td>
    <td style="font-weight:600;">NT$${{s.price.toFixed(2)}}</td>
    <td>${{changeHtml(s.change,s.changePct)}}</td>
    <td style="color:var(--muted);font-size:12px;">${{s.mktCap}}</td>
    <td>${{tagHtml(s.tag)}}</td>
    <td><button class="drill-btn" onclick="openDetail('${{s.ticker}}')">詳情 →</button></td>
  </tr>`).join('');
}}

function showPanel(name){{
  document.querySelectorAll('nav .tab').forEach((t,i)=>t.classList.toggle('active',['overview','comparison'][i]===name));
  document.getElementById('overview-panel').style.display=name==='overview'?'block':'none';
  document.getElementById('comparison-panel').style.display=name==='comparison'?'block':'none';
  document.getElementById('detail-panel').style.display='none';
  if(name==='comparison')renderRadarGrid();
}}

let radarDone=false;
function renderRadarGrid(){{
  if(radarDone)return; radarDone=true;
  const grid=document.getElementById('radar-grid');
  const colMap={{a:'rgba(63,185,80',b:'rgba(88,166,255',c:'rgba(210,153,34',d:'rgba(248,81,73'}};
  stocks.forEach(s=>{{
    const c=scoreClass(s.ai),col=colMap[c];
    const div=document.createElement('div');div.className='radar-card';
    div.innerHTML=`<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;">
      <div><h3>${{s.name}} <span style="color:var(--muted);font-size:11px;">${{s.ticker}}</span></h3>
      <div style="color:var(--muted);font-size:11px;">${{s.sector}} · <span class="score-num score-${{c}}">${{s.ai}}</span></div></div>
      ${{tagHtml(s.tag)}}</div>
      <canvas id="rc-${{s.ticker}}" height="200"></canvas>`;
    grid.appendChild(div);
    setTimeout(()=>{{
      new Chart(document.getElementById('rc-'+s.ticker).getContext('2d'),{{
        type:'radar',
        data:{{labels:['AI評分','財務','技術面','籌碼','成長性','質化'],
               datasets:[{{data:s.radar,backgroundColor:col+',0.15)',borderColor:col+',0.8)',pointBackgroundColor:col+',1)',borderWidth:2,pointRadius:3}}]}},
        options:{{responsive:true,scales:{{r:{{min:40,max:100,ticks:{{display:false}},grid:{{color:'rgba(255,255,255,.08)'}},pointLabels:{{color:'#8b949e',font:{{size:10}}}}}}}},plugins:{{legend:{{display:false}}}}}}
      }});
    }},50);
  }});
}}

function openDetail(ticker){{
  const s=stocks.find(x=>x.ticker===ticker); if(!s)return;
  document.getElementById('overview-panel').style.display='none';
  document.getElementById('comparison-panel').style.display='none';
  document.getElementById('detail-panel').style.display='block';
  document.querySelectorAll('nav .tab').forEach(t=>t.classList.remove('active'));
  const c=scoreClass(s.ai);
  const colMap={{a:'rgba(63,185,80',b:'rgba(88,166,255',c:'rgba(210,153,34',d:'rgba(248,81,73'}};
  const col=colMap[c];
  const typeLabel=s.type==='main'?'<span class="badge badge-main">主要持股</span>':'<span class="badge badge-watch">觀望</span>';
  const gradeLetter={{a:'A',b:'B',c:'C',d:'D'}}[c];
  const roe_color=s.roe>=15?'var(--green)':'var(--text)';
  const growthColor=s.revGrowth>0?'var(--green)':'var(--red)';
  const growthSign=s.revGrowth>0?'+':'';

  document.getElementById('detail-content').innerHTML=`
    <div style="display:flex;align-items:flex-start;justify-content:space-between;flex-wrap:wrap;gap:12px;margin-bottom:20px;">
      <div>
        <div style="display:flex;align-items:center;gap:10px;margin-bottom:4px;">
          <h1 style="font-size:22px;font-weight:700;">${{s.name}}</h1>
          <span style="color:var(--muted);font-size:16px;">${{s.ticker}}</span>
          ${{typeLabel}} ${{tagHtml(s.tag)}}
        </div>
        <div style="color:var(--muted);font-size:12px;">${{s.sector}}</div>
      </div>
      <div style="text-align:right;">
        <div style="font-size:28px;font-weight:700;">NT$ ${{s.price.toFixed(2)}}</div>
        <div style="font-size:13px;">${{changeHtml(s.change,s.changePct)}}</div>
      </div>
    </div>
    <div class="metrics-grid">
      <div class="metric-card"><div class="metric-label">AI 綜合評分</div><div class="metric-value score-${{c}}">${{s.ai}}</div><div class="metric-sub">${{gradeLetter}} 級評等</div></div>
      <div class="metric-card"><div class="metric-label">市值</div><div class="metric-value">${{s.mktCap}}</div><div class="metric-sub">TWSE</div></div>
      <div class="metric-card"><div class="metric-label">本益比 P/E</div><div class="metric-value">${{s.pe>0?s.pe+'x':'—'}}</div><div class="metric-sub">行業均值 18x</div></div>
      <div class="metric-card"><div class="metric-label">股價淨值比 P/B</div><div class="metric-value">${{s.pb>0?s.pb+'x':'—'}}</div></div>
      <div class="metric-card"><div class="metric-label">ROE 股東權益報酬率</div><div class="metric-value" style="color:${{roe_color}}">${{s.roe>0?s.roe+'%':'—'}}</div><div class="metric-sub">TTM</div></div>
      <div class="metric-card"><div class="metric-label">每股盈餘 EPS</div><div class="metric-value">${{s.eps>0?'NT$'+s.eps:'—'}}</div><div class="metric-sub">TTM</div></div>
      <div class="metric-card"><div class="metric-label">殖利率</div><div class="metric-value" style="color:var(--green)">${{s.div>0?s.div+'%':'—'}}</div></div>
      <div class="metric-card"><div class="metric-label">毛利率</div><div class="metric-value" style="color:${{growthColor}}">${{s.grossMargin>0?s.grossMargin+'%':'—'}}</div><div class="metric-sub">營收成長 ${{growthSign}}${{s.revGrowth}}%</div></div>
    </div>
    <div class="charts-row">
      <div class="chart-card"><h3>AI 六維雷達圖</h3><div class="chart-container"><canvas id="dr-${{ticker}}"></canvas></div></div>
      <div class="chart-card"><h3>各項評分細項</h3><div class="chart-container"><canvas id="db-${{ticker}}"></canvas></div></div>
      <div class="chart-card"><h3>評分組合 vs 全部均值</h3><div class="chart-container"><canvas id="da-${{ticker}}"></canvas></div></div>
    </div>
    <div class="ai-analysis">
      <h3 style="display:flex;align-items:center;gap:6px;">🤖 AI 研究摘要</h3>
      <p style="color:var(--muted);font-size:12px;margin-bottom:12px;line-height:1.7;">${{s.notes || '—'}}</p>
      <div style="display:flex;flex-direction:column;gap:8px;">
        ${{[['財務健康度',s.fin],['技術面強度',s.tech],['籌碼面',s.chips],['成長性',s.growth]].map(([l,v])=>`
          <div style="display:flex;align-items:center;gap:10px;">
            <span style="color:var(--muted);font-size:12px;width:90px;">${{l}}</span>
            <div class="score-bar" style="flex:1;height:8px;width:auto;"><div class="score-fill fill-${{scoreClass(v)}}" style="width:${{v}}%"></div></div>
            <span class="score-num score-${{scoreClass(v)}}">${{v}}</span>
          </div>`).join('')}}
      </div>
    </div>
  `;

  setTimeout(()=>{{
    // Radar
    new Chart(document.getElementById('dr-'+ticker).getContext('2d'),{{
      type:'radar',
      data:{{labels:['AI評分','財務','技術面','籌碼','成長性','質化'],
             datasets:[{{data:s.radar,backgroundColor:col+',0.15)',borderColor:col+',0.85)',pointBackgroundColor:col+',1)',borderWidth:2,pointRadius:4}}]}},
      options:{{responsive:true,maintainAspectRatio:false,scales:{{r:{{min:40,max:100,ticks:{{display:false}},grid:{{color:'rgba(255,255,255,.08)'}},pointLabels:{{color:'#8b949e',font:{{size:10}}}}}}}},plugins:{{legend:{{display:false}}}}}}
    }});
    // Bar
    new Chart(document.getElementById('db-'+ticker).getContext('2d'),{{
      type:'bar',
      data:{{labels:['財務','技術面','籌碼面','成長性'],
             datasets:[{{data:[s.fin,s.tech,s.chips,s.growth],backgroundColor:[col+',0.7)',col+',0.7)',col+',0.7)',col+',0.7)'],borderRadius:5}}]}},
      options:{{responsive:true,maintainAspectRatio:false,scales:{{y:{{min:40,max:100,grid:{{color:'rgba(255,255,255,.05)'}},ticks:{{color:'#8b949e'}}}},x:{{grid:{{display:false}},ticks:{{color:'#8b949e'}}}}}},plugins:{{legend:{{display:false}}}}}}
    }});
    // Avg comparison
    const avg=(k)=>Math.round(stocks.reduce((a,x)=>a+x[k],0)/stocks.length);
    new Chart(document.getElementById('da-'+ticker).getContext('2d'),{{
      type:'bar',
      data:{{labels:['財務','技術面','籌碼','成長性'],
             datasets:[
               {{label:s.name,data:[s.fin,s.tech,s.chips,s.growth],backgroundColor:col+',0.7)',borderRadius:5}},
               {{label:'全部均值',data:[avg('fin'),avg('tech'),avg('chips'),avg('growth')],backgroundColor:'rgba(139,148,158,0.4)',borderRadius:5}}
             ]}},
      options:{{responsive:true,maintainAspectRatio:false,scales:{{y:{{min:40,max:100,grid:{{color:'rgba(255,255,255,.05)'}},ticks:{{color:'#8b949e'}}}},x:{{grid:{{display:false}},ticks:{{color:'#8b949e'}}}}}},plugins:{{legend:{{labels:{{color:'#8b949e',font:{{size:10}}}}}}}}}}
    }});
  }},80);
}}

function closeDetail(){{
  document.getElementById('detail-panel').style.display='none';
  document.getElementById('overview-panel').style.display='block';
  document.querySelectorAll('nav .tab')[0].classList.add('active');
}}
</script>
</body>
</html>'''

Path("index.html").write_text(html, encoding='utf-8')
print(f"\n✅ index.html generated successfully ({updated_at})")
print(f"   {len(stocks)} stocks processed ({len(main_stocks)} main, {len(watch_stocks)} watch)")
