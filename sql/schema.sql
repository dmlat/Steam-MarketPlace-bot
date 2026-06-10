-- Steam Market Research Scanner schema

CREATE TABLE IF NOT EXISTS apps (
    appid BIGINT PRIMARY KEY,
    name TEXT,
    has_trading_cards BOOLEAN DEFAULT FALSE,
    is_excluded BOOLEAN DEFAULT FALSE,
    exclude_reason TEXT,
    source TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS market_items (
    id BIGSERIAL PRIMARY KEY,
    appid BIGINT,
    market_appid BIGINT DEFAULT 753,
    market_hash_name TEXT NOT NULL,
    item_name TEXT,
    item_type TEXT,
    game_name TEXT,
    category_game_tag TEXT,
    marketable BOOLEAN,
    tradable BOOLEAN,
    commodity BOOLEAN,
    is_card BOOLEAN DEFAULT FALSE,
    is_foil BOOLEAN DEFAULT FALSE,
    is_booster BOOLEAN DEFAULT FALSE,
    is_background BOOLEAN DEFAULT FALSE,
    is_emoticon BOOLEAN DEFAULT FALSE,
    item_nameid TEXT,
    market_url TEXT,
    data_quality_status TEXT DEFAULT 'PENDING',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE (market_appid, market_hash_name)
);

CREATE INDEX IF NOT EXISTS idx_market_items_appid ON market_items(appid);
CREATE INDEX IF NOT EXISTS idx_market_items_is_card ON market_items(is_card);
CREATE INDEX IF NOT EXISTS idx_market_items_game ON market_items(game_name);

CREATE TABLE IF NOT EXISTS price_snapshots (
    id BIGSERIAL PRIMARY KEY,
    market_item_id BIGINT REFERENCES market_items(id) ON DELETE CASCADE,
    currency_code TEXT NOT NULL,
    country_code TEXT NOT NULL,
    lowest_price NUMERIC,
    median_price NUMERIC,
    volume INTEGER,
    raw_response JSONB,
    captured_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_price_snapshots_item ON price_snapshots(market_item_id);
CREATE INDEX IF NOT EXISTS idx_price_snapshots_captured ON price_snapshots(captured_at);

CREATE TABLE IF NOT EXISTS orderbook_snapshots (
    id BIGSERIAL PRIMARY KEY,
    market_item_id BIGINT REFERENCES market_items(id) ON DELETE CASCADE,
    currency_code TEXT NOT NULL,
    country_code TEXT NOT NULL,
    highest_buy_order NUMERIC,
    lowest_sell_order NUMERIC,
    buy_order_count INTEGER,
    sell_order_count INTEGER,
    buy_order_graph JSONB,
    sell_order_graph JSONB,
    metrics JSONB,
    raw_response JSONB,
    captured_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_orderbook_snapshots_item ON orderbook_snapshots(market_item_id);

CREATE TABLE IF NOT EXISTS fee_calculations (
    id BIGSERIAL PRIMARY KEY,
    market_item_id BIGINT REFERENCES market_items(id) ON DELETE CASCADE,
    currency_code TEXT NOT NULL,
    buyer_pays NUMERIC,
    seller_receives NUMERIC,
    steam_fee NUMERIC,
    publisher_fee NUMERIC,
    total_fee NUMERIC,
    effective_fee_pct NUMERIC,
    break_even_sell_price NUMERIC,
    minimum_profitable_sell_price NUMERIC,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS opportunity_scores (
    id BIGSERIAL PRIMARY KEY,
    market_item_id BIGINT REFERENCES market_items(id) ON DELETE CASCADE,
    currency_code TEXT NOT NULL,
    lowest_sell_price NUMERIC,
    highest_buy_order NUMERIC,
    net_spread_abs NUMERIC,
    net_spread_pct NUMERIC,
    volume_score NUMERIC,
    depth_score NUMERIC,
    competition_score NUMERIC,
    volatility_score NUMERIC,
    opportunity_score NUMERIC,
    risk_flags TEXT[],
    data_quality_status TEXT,
    calculated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_opportunity_scores_score ON opportunity_scores(opportunity_score DESC);

CREATE TABLE IF NOT EXISTS pipeline_runs (
    id BIGSERIAL PRIMARY KEY,
    stage TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'running',
    last_appid BIGINT,
    last_item_id BIGINT,
    requests_made INTEGER DEFAULT 0,
    metadata JSONB,
    started_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    completed_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS currency_analysis (
    id BIGSERIAL PRIMARY KEY,
    market_item_id BIGINT REFERENCES market_items(id) ON DELETE CASCADE,
    base_currency TEXT DEFAULT 'USD',
    price_usd NUMERIC,
    price_eur NUMERIC,
    price_rub NUMERIC,
    price_gbp NUMERIC,
    price_brl NUMERIC,
    price_cny NUMERIC,
    implied_usd_eur NUMERIC,
    implied_usd_rub NUMERIC,
    implied_usd_gbp NUMERIC,
    implied_usd_brl NUMERIC,
    implied_usd_cny NUMERIC,
    rounding_anomaly BOOLEAN DEFAULT FALSE,
    anomaly_details JSONB,
    calculated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_currency_analysis_item ON currency_analysis(market_item_id);
