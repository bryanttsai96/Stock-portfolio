-- =============================================================================
-- Taiwan Stock Research Dashboard — Supabase Schema
-- Run this in the Supabase SQL editor (Dashboard → SQL Editor → New query)
-- =============================================================================

-- ---------------------------------------------------------------------------
-- Extensions
-- ---------------------------------------------------------------------------
CREATE EXTENSION IF NOT EXISTS pg_trgm;        -- trigram similarity for fuzzy search
CREATE EXTENSION IF NOT EXISTS unaccent;        -- accent-insensitive search


-- ===========================================================================
-- TABLE: companies
-- Master universe of TWSE + TPEX listed companies
-- ===========================================================================
CREATE TABLE IF NOT EXISTS companies (
    ticker              TEXT        PRIMARY KEY,                -- e.g. "2330", "3008"
    name                TEXT        NOT NULL,                   -- 公司名稱 (Traditional Chinese)
    short_name          TEXT,                                   -- shortened / common Chinese name
    english_name        TEXT,                                   -- official English name from TWSE OpenAPI
    market              TEXT        NOT NULL                    -- "TWSE" | "TPEX"
                            CHECK (market IN ('TWSE', 'TPEX')),
    industry            TEXT,                                   -- industry label from ISIN source (Chinese)
    sector              TEXT,                                   -- normalised sector bucket (optional override)
    listed_date         DATE,                                   -- 上市 / 上櫃 date
    website             TEXT,                                   -- company website from t187ap03_L
    shares_issued       BIGINT,                                 -- 已發行股數 (shares)
    paid_in_capital     BIGINT,                                 -- 實收資本額 (NTD)
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE  companies                IS 'Master universe of all TWSE and TPEX listed companies.';
COMMENT ON COLUMN companies.ticker         IS 'Stock ticker code (4-5 digits).';
COMMENT ON COLUMN companies.market         IS 'Exchange: TWSE (上市) or TPEX (上櫃/OTC).';
COMMENT ON COLUMN companies.industry       IS 'Raw industry classification text scraped from TWSE/TPEX ISIN pages.';
COMMENT ON COLUMN companies.shares_issued  IS 'Total shares issued (units, not thousands).';
COMMENT ON COLUMN companies.paid_in_capital IS 'Paid-in capital in New Taiwan Dollars.';

-- Full-text search column (updated via trigger)
ALTER TABLE companies
    ADD COLUMN IF NOT EXISTS search_vector TSVECTOR
        GENERATED ALWAYS AS (
            setweight(to_tsvector('simple', coalesce(ticker, '')),       'A') ||
            setweight(to_tsvector('simple', coalesce(name, '')),         'B') ||
            setweight(to_tsvector('simple', coalesce(english_name, '')), 'C') ||
            setweight(to_tsvector('simple', coalesce(short_name, '')),   'C')
        ) STORED;

-- Indexes
CREATE INDEX IF NOT EXISTS idx_companies_market        ON companies (market);
CREATE INDEX IF NOT EXISTS idx_companies_industry      ON companies (industry);
CREATE INDEX IF NOT EXISTS idx_companies_listed_date   ON companies (listed_date);
CREATE INDEX IF NOT EXISTS idx_companies_search_vector ON companies USING GIN (search_vector);

-- Trigram indexes for partial / fuzzy text matching
CREATE INDEX IF NOT EXISTS idx_companies_name_trgm    ON companies USING GIN (name          gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_companies_en_trgm      ON companies USING GIN (english_name  gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_companies_ticker_trgm  ON companies USING GIN (ticker        gin_trgm_ops);

-- Auto-update updated_at
CREATE OR REPLACE FUNCTION trigger_set_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS set_companies_updated_at ON companies;
CREATE TRIGGER set_companies_updated_at
    BEFORE UPDATE ON companies
    FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at();


-- ===========================================================================
-- TABLE: aliases
-- Alternate names: English abbreviations, short names, common nicknames
-- e.g. ticker=2330 → "TSMC", "台積電", "積電"
-- ===========================================================================
CREATE TABLE IF NOT EXISTS aliases (
    id          BIGSERIAL   PRIMARY KEY,
    ticker      TEXT        NOT NULL REFERENCES companies (ticker) ON DELETE CASCADE,
    alias       TEXT        NOT NULL,
    alias_type  TEXT        NOT NULL DEFAULT 'common'
                    CHECK (alias_type IN ('english', 'short', 'common', 'ticker_intl')),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (ticker, alias)
);

COMMENT ON TABLE  aliases            IS 'Alternate / common names for companies to aid search.';
COMMENT ON COLUMN aliases.alias_type IS 'english=official EN name, short=abbreviated CN, common=market nickname, ticker_intl=ADR/overseas ticker.';

CREATE INDEX IF NOT EXISTS idx_aliases_ticker  ON aliases (ticker);
CREATE INDEX IF NOT EXISTS idx_aliases_alias   ON aliases (alias);
CREATE INDEX IF NOT EXISTS idx_aliases_trgm    ON aliases USING GIN (alias gin_trgm_ops);


-- ===========================================================================
-- TABLE: concepts
-- Investment themes / sectors used for portfolio grouping
-- ===========================================================================
CREATE TABLE IF NOT EXISTS concepts (
    id          BIGSERIAL   PRIMARY KEY,
    name        TEXT        NOT NULL UNIQUE,
    description TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE concepts IS 'Investment themes and sector concepts for grouping stocks.';

-- Pre-seed concepts
INSERT INTO concepts (name, description) VALUES
    ('AI',          'Artificial Intelligence — broad beneficiaries including chips, servers, software'),
    ('CoWoS',       'Chip-on-Wafer-on-Substrate advanced packaging supply chain'),
    ('HBM',         'High Bandwidth Memory — DRAM stacked for AI accelerators'),
    ('AI伺服器',    'AI server ODM/OEM and component suppliers'),
    ('ASIC',        'Application-Specific Integrated Circuit design and foundry'),
    ('機器人',      'Robotics and automation — hardware, motors, sensors, software'),
    ('電動車',      'Electric vehicle supply chain — batteries, power electronics, connectors'),
    ('半導體設備',  'Semiconductor capital equipment and spare parts'),
    ('先進封裝',    'Advanced IC packaging: CoWoS, SoIC, Fan-Out'),
    ('高速運算',    'High-performance computing: HPC, GPU clusters, networking'),
    ('散熱',        'Thermal management — heat pipes, vapor chambers, liquid cooling'),
    ('網通',        'Networking and communications equipment'),
    ('儲能',        'Energy storage — batteries, BMS, grid-scale systems')
ON CONFLICT (name) DO NOTHING;


-- ===========================================================================
-- TABLE: concept_mappings
-- Many-to-many join between companies and concepts
-- ===========================================================================
CREATE TABLE IF NOT EXISTS concept_mappings (
    id          BIGSERIAL   PRIMARY KEY,
    ticker      TEXT        NOT NULL REFERENCES companies   (ticker)  ON DELETE CASCADE,
    concept_id  BIGINT      NOT NULL REFERENCES concepts   (id)      ON DELETE CASCADE,
    confidence  SMALLINT    NOT NULL DEFAULT 80
                    CHECK (confidence BETWEEN 0 AND 100),  -- 0-100 relevance score
    source      TEXT        DEFAULT 'manual',               -- 'manual' | 'auto'
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (ticker, concept_id)
);

COMMENT ON TABLE  concept_mappings            IS 'Many-to-many mapping of companies to investment themes.';
COMMENT ON COLUMN concept_mappings.confidence IS 'How strongly the company belongs to this concept (0-100).';

CREATE INDEX IF NOT EXISTS idx_concept_mappings_ticker     ON concept_mappings (ticker);
CREATE INDEX IF NOT EXISTS idx_concept_mappings_concept_id ON concept_mappings (concept_id);


-- ===========================================================================
-- TABLE: user_watchlist
-- Replaces browser localStorage; keyed by anonymous session_id for now.
-- When auth is added later, replace session_id with auth.uid().
-- ===========================================================================
CREATE TABLE IF NOT EXISTS user_watchlist (
    id           BIGSERIAL   PRIMARY KEY,
    session_id   TEXT        NOT NULL,                   -- anonymous session token from client
    ticker       TEXT        NOT NULL REFERENCES companies (ticker) ON DELETE CASCADE,
    watch_table  TEXT        NOT NULL DEFAULT 'learning'
                     CHECK (watch_table IN ('learning', 'watch', 'main')),
    notes        TEXT,                                   -- freeform user notes
    score_cache  JSONB       DEFAULT '{}'::JSONB,        -- cached AI scores, updated periodically
    added_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (session_id, ticker)
);

COMMENT ON TABLE  user_watchlist             IS 'Per-session watchlist replacing browser localStorage.';
COMMENT ON COLUMN user_watchlist.session_id  IS 'Anonymous client-generated UUID; replace with auth.uid() when auth is enabled.';
COMMENT ON COLUMN user_watchlist.watch_table IS 'learning=研究中, watch=觀察中, main=主力持股.';
COMMENT ON COLUMN user_watchlist.score_cache IS 'Cached computed AI scores; schema mirrors stock_daily score columns.';

CREATE INDEX IF NOT EXISTS idx_watchlist_session_id  ON user_watchlist (session_id);
CREATE INDEX IF NOT EXISTS idx_watchlist_ticker      ON user_watchlist (ticker);
CREATE INDEX IF NOT EXISTS idx_watchlist_watch_table ON user_watchlist (session_id, watch_table);

DROP TRIGGER IF EXISTS set_watchlist_updated_at ON user_watchlist;
CREATE TRIGGER set_watchlist_updated_at
    BEFORE UPDATE ON user_watchlist
    FOR EACH ROW EXECUTE FUNCTION trigger_set_updated_at();

-- Row Level Security — enabled but permissive until auth is wired up
ALTER TABLE user_watchlist ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "allow_all_watchlist" ON user_watchlist;
CREATE POLICY "allow_all_watchlist"
    ON user_watchlist
    FOR ALL
    USING (true)
    WITH CHECK (true);


-- ===========================================================================
-- TABLE: stock_daily
-- Daily snapshot: prices, computed AI scores, valuation metrics
-- ===========================================================================
CREATE TABLE IF NOT EXISTS stock_daily (
    ticker              TEXT        NOT NULL REFERENCES companies (ticker) ON DELETE CASCADE,
    score_date          DATE        NOT NULL,

    -- AI composite scores (0-100 scale)
    ai_total            NUMERIC(5,2),
    profit_score        NUMERIC(5,2),
    growth_score        NUMERIC(5,2),
    valuation_score     NUMERIC(5,2),
    financial_score     NUMERIC(5,2),
    market_score        NUMERIC(5,2),
    risk_adj            NUMERIC(5,2),  -- risk adjustment factor
    type_adj            NUMERIC(5,2),  -- stock-type adjustment (growth/value/cyclical etc.)

    -- Classification tag derived from scores
    tag                 TEXT,          -- e.g. "績優成長", "價值低估", "景氣循環"

    -- Market data (from BWIBBU_d or yfinance fallback)
    price               NUMERIC(10,2),
    change_pct          NUMERIC(7,4),  -- daily % change
    market_cap_text     TEXT,          -- formatted string e.g. "1.2兆"
    pe                  NUMERIC(8,2),  -- Price/Earnings
    pb                  NUMERIC(8,2),  -- Price/Book
    dividend_yield      NUMERIC(6,4),  -- decimal (0.05 = 5%)

    -- Full score breakdown for transparency / debugging
    score_breakdown     JSONB          DEFAULT '{}'::JSONB,

    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    PRIMARY KEY (ticker, score_date)
);

COMMENT ON TABLE  stock_daily               IS 'Daily snapshot of prices, AI scores, and valuation metrics per stock.';
COMMENT ON COLUMN stock_daily.ai_total      IS 'Composite AI score 0-100.';
COMMENT ON COLUMN stock_daily.tag           IS 'Human-readable classification label derived from score profile.';
COMMENT ON COLUMN stock_daily.score_breakdown IS 'Full JSON breakdown of sub-scores for UI tooltip display.';

CREATE INDEX IF NOT EXISTS idx_stock_daily_ticker     ON stock_daily (ticker);
CREATE INDEX IF NOT EXISTS idx_stock_daily_date       ON stock_daily (score_date DESC);
CREATE INDEX IF NOT EXISTS idx_stock_daily_ai_total   ON stock_daily (score_date DESC, ai_total DESC NULLS LAST);


-- ===========================================================================
-- FUNCTION: search_companies
-- Full-text + trigram search across ticker, name, english_name, and aliases.
-- Returns ranked results with similarity score.
-- ===========================================================================
CREATE OR REPLACE FUNCTION search_companies(query TEXT, result_limit INT DEFAULT 20)
RETURNS TABLE (
    ticker          TEXT,
    name            TEXT,
    short_name      TEXT,
    english_name    TEXT,
    market          TEXT,
    industry        TEXT,
    rank            FLOAT4
)
LANGUAGE sql STABLE AS $$
    -- Full-text search via tsvector
    SELECT
        c.ticker,
        c.name,
        c.short_name,
        c.english_name,
        c.market,
        c.industry,
        ts_rank(c.search_vector, websearch_to_tsquery('simple', query))::FLOAT4 AS rank
    FROM companies c
    WHERE c.search_vector @@ websearch_to_tsquery('simple', query)

    UNION

    -- Trigram similarity on name / english_name / ticker for partial matches
    SELECT
        c.ticker,
        c.name,
        c.short_name,
        c.english_name,
        c.market,
        c.industry,
        GREATEST(
            similarity(c.ticker,       query),
            similarity(c.name,         query),
            similarity(coalesce(c.english_name, ''), query),
            similarity(coalesce(c.short_name,   ''), query)
        )::FLOAT4 AS rank
    FROM companies c
    WHERE
        c.ticker       %  query OR
        c.name         %  query OR
        c.english_name %  query OR
        c.short_name   %  query

    UNION

    -- Alias search
    SELECT
        c.ticker,
        c.name,
        c.short_name,
        c.english_name,
        c.market,
        c.industry,
        similarity(a.alias, query)::FLOAT4 AS rank
    FROM aliases a
    JOIN companies c ON c.ticker = a.ticker
    WHERE a.alias % query

    ORDER BY rank DESC
    LIMIT result_limit;
$$;

COMMENT ON FUNCTION search_companies IS
    'Search companies by ticker, Chinese name, English name, or alias. '
    'Uses full-text tsvector ranking + trigram similarity. '
    'Example: SELECT * FROM search_companies(''台積'');';


-- ===========================================================================
-- FUNCTION: get_latest_scores
-- Convenience view helper — returns most recent stock_daily row per ticker
-- ===========================================================================
CREATE OR REPLACE VIEW v_latest_scores AS
SELECT DISTINCT ON (sd.ticker)
    sd.*,
    c.name,
    c.market,
    c.industry
FROM stock_daily sd
JOIN companies c ON c.ticker = sd.ticker
ORDER BY sd.ticker, sd.score_date DESC;

COMMENT ON VIEW v_latest_scores IS 'Most recent stock_daily row for each ticker, joined with company metadata.';


-- ===========================================================================
-- FUNCTION: get_watchlist_with_scores
-- Returns a session's watchlist enriched with latest scores
-- ===========================================================================
CREATE OR REPLACE FUNCTION get_watchlist_with_scores(p_session_id TEXT)
RETURNS TABLE (
    ticker          TEXT,
    name            TEXT,
    market          TEXT,
    industry        TEXT,
    watch_table     TEXT,
    notes           TEXT,
    added_at        TIMESTAMPTZ,
    ai_total        NUMERIC,
    price           NUMERIC,
    pe              NUMERIC,
    pb              NUMERIC,
    dividend_yield  NUMERIC,
    tag             TEXT,
    score_date      DATE
)
LANGUAGE sql STABLE AS $$
    SELECT
        w.ticker,
        c.name,
        c.market,
        c.industry,
        w.watch_table,
        w.notes,
        w.added_at,
        s.ai_total,
        s.price,
        s.pe,
        s.pb,
        s.dividend_yield,
        s.tag,
        s.score_date
    FROM user_watchlist w
    JOIN companies c ON c.ticker = w.ticker
    LEFT JOIN LATERAL (
        SELECT ai_total, price, pe, pb, dividend_yield, tag, score_date
        FROM stock_daily
        WHERE ticker = w.ticker
        ORDER BY score_date DESC
        LIMIT 1
    ) s ON true
    WHERE w.session_id = p_session_id
    ORDER BY w.watch_table, w.added_at DESC;
$$;

COMMENT ON FUNCTION get_watchlist_with_scores IS
    'Returns a session watchlist with the latest score snapshot per ticker. '
    'Example: SELECT * FROM get_watchlist_with_scores(''my-session-uuid'');';
