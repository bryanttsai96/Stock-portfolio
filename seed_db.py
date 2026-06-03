#!/usr/bin/env python3
"""
seed_db.py — Populate the Supabase `companies` table with all TWSE + TPEX
listed companies scraped from official Taiwan exchange sources.

Prerequisites:
    pip install supabase requests beautifulsoup4 lxml

Environment variables required:
    SUPABASE_URL   — e.g. https://xxxxxxxxxxxx.supabase.co
    SUPABASE_KEY   — service_role key (bypasses RLS) or anon key
"""

import os
import re
import sys
import time
import logging
from datetime import datetime
from typing import Optional

import requests
from bs4 import BeautifulSoup
from supabase import create_client, Client

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
ISIN_URL_TWSE  = "https://isin.twse.com.tw/isin/C_public.jsp?strMode=2"   # 上市
ISIN_URL_TPEX  = "https://isin.twse.com.tw/isin/C_public.jsp?strMode=4"   # 上櫃/OTC
OPENAPI_URL    = "https://openapi.twse.com.tw/v1/opendata/t187ap03_L"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
}

# Ticker must be 4-6 digits (TWSE is 4 digits, TPEX can be 5)
TICKER_RE = re.compile(r"^\d{4,6}$")

# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

def clean(value: Optional[str]) -> Optional[str]:
    """Strip whitespace and return None for empty strings."""
    if value is None:
        return None
    value = value.strip()
    return value if value else None


def parse_date(raw: Optional[str]) -> Optional[str]:
    """
    Parse listing date strings from ISIN pages.
    Common formats: "YYYY/MM/DD", "YYYY-MM-DD", empty.
    Returns ISO date string "YYYY-MM-DD" or None.
    """
    if not raw:
        return None
    raw = raw.strip()
    for fmt in ("%Y/%m/%d", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def parse_number(raw: Optional[str]) -> Optional[int]:
    """Parse a comma-separated numeric string into an integer."""
    if not raw:
        return None
    try:
        return int(raw.strip().replace(",", "").replace("，", ""))
    except ValueError:
        return None

# ---------------------------------------------------------------------------
# Step 1 & 2: Scrape ISIN HTML pages
# ---------------------------------------------------------------------------

def scrape_isin_page(url: str, market: str) -> list[dict]:
    """
    Scrape the TWSE ISIN listing page (Big5 / UTF-8 mixed encoding).

    Table row structure (tab-separated cells in HTML):
        Col 0: "股票代號 公司名稱"  (space-separated)
        Col 1: ISIN code
        Col 2: Listing date  (YYYY/MM/DD)
        Col 3: Market type description
        Col 4: Industry classification label (Chinese)

    Section header rows (industry dividers) have an empty ISIN — skip them.
    """
    log.info("Fetching ISIN page: %s", url)

    try:
        resp = requests.get(url, headers=HEADERS, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as exc:
        log.error("Failed to fetch %s: %s", url, exc)
        return []

    # The page declares charset=Big5 but may actually be UTF-8 or mixed.
    # Try UTF-8 first; fall back to Big5 (cp950 on Windows / big5hkscs on Mac).
    for encoding in ("utf-8", "big5hkscs", "cp950"):
        try:
            html = resp.content.decode(encoding)
            break
        except (UnicodeDecodeError, LookupError):
            continue
    else:
        html = resp.content.decode("utf-8", errors="replace")

    soup = BeautifulSoup(html, "lxml")

    # The ISIN pages use a single wide <table> with class "h4" or no class.
    # Find the table that contains the known header text.
    target_table = None
    for table in soup.find_all("table"):
        text = table.get_text()
        if "有價證券代號" in text or "股票代號" in text:
            target_table = table
            break

    if target_table is None:
        log.warning("Could not find data table in %s", url)
        return []

    rows = target_table.find_all("tr")
    companies = []
    current_industry = None

    for row in rows:
        cells = [td.get_text(strip=True) for td in row.find_all("td")]

        if len(cells) < 2:
            continue

        # ---- Section header row ----
        # These rows typically have 1 wide cell with just the industry name
        # OR the first cell has content but ISIN cell is empty.
        if len(cells) >= 2 and not cells[1]:
            # Treat the first non-empty cell as a new industry heading
            candidate = clean(cells[0])
            if candidate and not TICKER_RE.match(candidate.split()[0] if candidate else ""):
                current_industry = candidate
            continue

        # ---- Data row ----
        raw_col0 = clean(cells[0])
        if not raw_col0:
            continue

        # Col 0 is "TICKER 公司名稱" — split on first whitespace
        parts = raw_col0.split(None, 1)   # maxsplit=1
        if len(parts) < 2:
            continue

        ticker, name = parts[0], parts[1]

        if not TICKER_RE.match(ticker):
            # Not a valid ticker — could be a header/footer row
            continue

        isin        = clean(cells[1]) if len(cells) > 1 else None
        listed_date = parse_date(clean(cells[2]) if len(cells) > 2 else None)
        industry    = clean(cells[4]) if len(cells) > 4 else current_industry

        # If industry cell is empty, carry forward the last seen heading
        if not industry and current_industry:
            industry = current_industry
        elif industry:
            current_industry = industry  # update running heading

        companies.append({
            "ticker":      ticker,
            "name":        name,
            "market":      market,
            "industry":    industry,
            "listed_date": listed_date,
        })

    log.info("  → Parsed %d companies from %s (%s)", len(companies), market, url)
    return companies

# ---------------------------------------------------------------------------
# Step 3: Fetch enrichment data from TWSE OpenAPI t187ap03_L
# ---------------------------------------------------------------------------

def fetch_openapi_enrichment() -> dict[str, dict]:
    """
    Fetch t187ap03_L JSON — one record per listed company.

    Relevant fields (field names use Chinese keys from TWSE API):
        公司代號   → ticker
        英文簡稱   → english_name
        公司網址   → website
        已發行普通股數或TDR原股發行股數 → shares_issued
        實收資本額(元) → paid_in_capital
        (field names vary by API version — we try several variants)

    Returns a dict keyed by ticker → enrichment dict.
    """
    log.info("Fetching TWSE OpenAPI enrichment: %s", OPENAPI_URL)

    enrichment: dict[str, dict] = {}

    try:
        resp = requests.get(OPENAPI_URL, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as exc:
        log.error("Failed to fetch OpenAPI data: %s", exc)
        return enrichment
    except ValueError as exc:
        log.error("Failed to parse OpenAPI JSON: %s", exc)
        return enrichment

    if not isinstance(data, list):
        log.warning("Unexpected OpenAPI response format (not a list)")
        return enrichment

    # Field name aliases (TWSE sometimes changes Chinese key names between releases)
    TICKER_KEYS  = ["公司代號", "股票代號"]
    EN_NAME_KEYS = ["英文簡稱", "英文名稱", "英文公司名稱"]
    WEB_KEYS     = ["公司網址", "網址"]
    SHARES_KEYS  = ["已發行普通股數或TDR原股發行股數", "已發行股數", "普通股股數"]
    CAPITAL_KEYS = ["實收資本額(元)", "實收資本額", "資本額"]

    def first_value(record: dict, keys: list[str]) -> Optional[str]:
        for k in keys:
            v = record.get(k)
            if v is not None:
                return str(v).strip() or None
        return None

    for record in data:
        ticker = first_value(record, TICKER_KEYS)
        if not ticker or not TICKER_RE.match(ticker):
            continue

        enrichment[ticker] = {
            "english_name":   first_value(record, EN_NAME_KEYS),
            "website":        first_value(record, WEB_KEYS),
            "shares_issued":  parse_number(first_value(record, SHARES_KEYS)),
            "paid_in_capital": parse_number(first_value(record, CAPITAL_KEYS)),
        }

    log.info("  → Parsed enrichment for %d companies", len(enrichment))
    return enrichment

# ---------------------------------------------------------------------------
# Step 4: Merge and upsert
# ---------------------------------------------------------------------------

def merge_and_upsert(supabase: Client, companies: list[dict], enrichment: dict[str, dict]) -> dict:
    """
    Merge scraped company list with OpenAPI enrichment, then upsert into
    the Supabase `companies` table in batches.

    Returns a summary dict.
    """
    # Apply enrichment
    for company in companies:
        extra = enrichment.get(company["ticker"], {})
        company.update({
            "english_name":    extra.get("english_name"),
            "website":         extra.get("website"),
            "shares_issued":   extra.get("shares_issued"),
            "paid_in_capital": extra.get("paid_in_capital"),
        })

    # Remove None values so Supabase doesn't overwrite existing data with null
    def strip_nones(record: dict) -> dict:
        return {k: v for k, v in record.items() if v is not None}

    records = [strip_nones(c) for c in companies]

    BATCH_SIZE = 200
    total_upserted = 0
    errors = 0

    for i in range(0, len(records), BATCH_SIZE):
        batch = records[i : i + BATCH_SIZE]
        try:
            result = (
                supabase.table("companies")
                .upsert(batch, on_conflict="ticker")
                .execute()
            )
            total_upserted += len(batch)
            log.info("  Upserted rows %d–%d (%d total)", i + 1, i + len(batch), total_upserted)
        except Exception as exc:
            log.error("  Batch %d–%d failed: %s", i + 1, i + len(batch), exc)
            errors += 1
        time.sleep(0.1)  # be polite to the API

    return {"total_upserted": total_upserted, "batch_errors": errors}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    # ---- Load credentials ----
    supabase_url = os.environ.get("SUPABASE_URL", "").strip()
    supabase_key = os.environ.get("SUPABASE_KEY", "").strip()

    if not supabase_url or not supabase_key:
        log.error(
            "Missing environment variables.\n"
            "  export SUPABASE_URL='https://xxxx.supabase.co'\n"
            "  export SUPABASE_KEY='your-service-role-key'"
        )
        sys.exit(1)

    log.info("Connecting to Supabase: %s", supabase_url)
    supabase: Client = create_client(supabase_url, supabase_key)

    # ---- Step 1: Scrape TWSE (上市) ----
    log.info("=" * 60)
    log.info("Step 1/4 — Scraping TWSE (上市) ISIN page")
    twse_companies = scrape_isin_page(ISIN_URL_TWSE, market="TWSE")

    # ---- Step 2: Scrape TPEX (上櫃) ----
    log.info("=" * 60)
    log.info("Step 2/4 — Scraping TPEX (上櫃) ISIN page")
    tpex_companies = scrape_isin_page(ISIN_URL_TPEX, market="TPEX")

    # Combine; TWSE takes precedence if a ticker appears in both (shouldn't happen)
    all_companies: dict[str, dict] = {}
    for company in twse_companies + tpex_companies:
        ticker = company["ticker"]
        if ticker not in all_companies:
            all_companies[ticker] = company
        else:
            log.debug("Duplicate ticker %s — keeping first occurrence", ticker)

    combined = list(all_companies.values())
    log.info("Combined unique companies: %d", len(combined))

    # ---- Step 3: Fetch enrichment ----
    log.info("=" * 60)
    log.info("Step 3/4 — Fetching TWSE OpenAPI enrichment (t187ap03_L)")
    enrichment = fetch_openapi_enrichment()

    # ---- Step 4: Merge and upsert ----
    log.info("=" * 60)
    log.info("Step 4/4 — Merging data and upserting into Supabase")
    result = merge_and_upsert(supabase, combined, enrichment)

    # ---- Step 5: Summary ----
    twse_count = sum(1 for c in combined if c["market"] == "TWSE")
    tpex_count = sum(1 for c in combined if c["market"] == "TPEX")

    log.info("=" * 60)
    log.info("SUMMARY")
    log.info("  TWSE companies scraped : %d", twse_count)
    log.info("  TPEX companies scraped : %d", tpex_count)
    log.info("  Total unique           : %d", len(combined))
    log.info("  Enriched from OpenAPI  : %d", len(enrichment))
    log.info("  Rows upserted          : %d", result["total_upserted"])
    log.info("  Batch errors           : %d", result["batch_errors"])
    log.info("=" * 60)

    if result["batch_errors"] > 0:
        log.warning("Some batches failed — check logs above for details.")
        sys.exit(1)
    else:
        log.info("Done. Database is ready.")


if __name__ == "__main__":
    main()
