# 台股AI研究儀表板

Live dashboard: https://YOUR-USERNAME.github.io/taiwan-stocks/

## Setup (one-time, ~5 minutes)

### 1. Create GitHub repo
1. Go to https://github.com/new
2. Name it `taiwan-stocks`
3. Set to **Public** (required for free GitHub Pages)
4. Click **Create repository**

### 2. Upload this folder
```bash
cd /Users/bryant/Desktop/taiwan-stocks
git init
git add .
git commit -m "init"
git remote add origin https://github.com/YOUR-USERNAME/taiwan-stocks.git
git push -u origin main
```

### 3. Enable GitHub Pages
1. Go to repo → **Settings** → **Pages**
2. Source: **Deploy from a branch**
3. Branch: `main`, folder: `/ (root)`
4. Click **Save**
5. Your URL: `https://YOUR-USERNAME.github.io/taiwan-stocks/`

### 4. Run first build
1. Go to repo → **Actions** tab
2. Click **Daily Stock Update** → **Run workflow**
3. Wait ~2 minutes → refresh your Pages URL

After that, it runs automatically every weekday at 6:05pm Taiwan time.

## Adding a new stock

Edit `config.json` — add an entry to the `stocks` array:
```json
{
  "ticker": "XXXX",
  "name": "公司名稱",
  "type": "main",     ← "main" or "watch"
  "sector": "產業別",
  "notes": "簡短研究備註"
}
```
Commit the change → GitHub Actions will pick it up on the next run (or trigger manually).

## Local preview
```bash
pip install yfinance
python generate.py
open index.html
```
