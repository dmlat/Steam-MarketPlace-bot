"""Streamlit dashboard for Steam Market Research Scanner."""

from __future__ import annotations

import sys
from decimal import Decimal
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from sqlalchemy import desc, func

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from steam_scanner.analytics.fee_engine import build_fee_table
from steam_scanner.analytics.scoring import ScoringEngine
from steam_scanner.config import CARD_PRICE_TIERS
from steam_scanner.db.models import (
    App,
    CurrencyAnalysis,
    MarketItem,
    OpportunityScore,
    OrderbookSnapshot,
    PriceSnapshot,
)
from steam_scanner.db.session import get_session

st.set_page_config(
    page_title="Steam Market Research Scanner",
    layout="wide",
)


@st.cache_data(ttl=300)
def load_overview_stats() -> dict:
    with get_session() as session:
        return {
            "apps": session.query(func.count(App.appid)).scalar() or 0,
            "items": session.query(func.count(MarketItem.id)).scalar() or 0,
            "cards": session.query(func.count(MarketItem.id)).filter(MarketItem.is_card.is_(True)).scalar() or 0,
            "above_1": (
                session.query(func.count(MarketItem.id.distinct()))
                .join(PriceSnapshot, MarketItem.id == PriceSnapshot.market_item_id)
                .filter(PriceSnapshot.currency_code == "USD", PriceSnapshot.lowest_price >= 1.0)
                .scalar() or 0
            ),
            "positive_spread": (
                session.query(func.count(OpportunityScore.id.distinct()))
                .filter(OpportunityScore.net_spread_pct > 0)
                .scalar() or 0
            ),
            "liquid": (
                session.query(func.count(PriceSnapshot.market_item_id.distinct()))
                .filter(PriceSnapshot.volume >= 10)
                .scalar() or 0
            ),
        }


@st.cache_data(ttl=300)
def load_cards_df(
    game: str | None,
    min_price: float,
    max_price: float | None,
    foil_only: bool,
    min_volume: int,
) -> pd.DataFrame:
    with get_session() as session:
        subq = (
            session.query(
                PriceSnapshot.market_item_id,
                func.max(PriceSnapshot.captured_at).label("max_at"),
            )
            .filter(PriceSnapshot.currency_code == "USD")
            .group_by(PriceSnapshot.market_item_id)
            .subquery()
        )

        q = (
            session.query(MarketItem, PriceSnapshot, OpportunityScore)
            .join(PriceSnapshot, MarketItem.id == PriceSnapshot.market_item_id)
            .join(subq, (PriceSnapshot.market_item_id == subq.c.market_item_id)
                  & (PriceSnapshot.captured_at == subq.c.max_at))
            .outerjoin(OpportunityScore, MarketItem.id == OpportunityScore.market_item_id)
            .filter(MarketItem.is_card.is_(True))
            .filter(PriceSnapshot.lowest_price >= min_price)
        )

        if max_price:
            q = q.filter(PriceSnapshot.lowest_price < max_price)
        if game:
            q = q.filter(MarketItem.game_name.ilike(f"%{game}%"))
        if foil_only:
            q = q.filter(MarketItem.is_foil.is_(True))
        if min_volume:
            q = q.filter(PriceSnapshot.volume >= min_volume)

        rows = q.limit(500).all()

        data = []
        for item, price, score in rows:
            data.append({
                "game": item.game_name,
                "card": item.market_hash_name,
                "foil": item.is_foil,
                "lowest": float(price.lowest_price) if price.lowest_price else None,
                "median": float(price.median_price) if price.median_price else None,
                "volume": price.volume,
                "highest_buy": score.highest_buy_order if score else None,
                "lowest_sell": score.lowest_sell_price if score else None,
                "net_spread_pct": score.net_spread_pct if score else None,
                "score": score.opportunity_score if score else None,
                "risk": ", ".join(score.risk_flags or []) if score else "",
            })
        return pd.DataFrame(data)


@st.cache_data(ttl=300)
def load_orderbook_item(item_id: int) -> dict | None:
    with get_session() as session:
        ob = (
            session.query(OrderbookSnapshot)
            .filter(OrderbookSnapshot.market_item_id == item_id)
            .order_by(desc(OrderbookSnapshot.captured_at))
            .first()
        )
        item = session.get(MarketItem, item_id)
        if not ob or not item:
            return None
        return {
            "name": item.market_hash_name,
            "buy_graph": ob.buy_order_graph or [],
            "sell_graph": ob.sell_order_graph or [],
            "metrics": ob.metrics or {},
        }


@st.cache_data(ttl=300)
def load_currency_df() -> pd.DataFrame:
    with get_session() as session:
        rows = (
            session.query(CurrencyAnalysis, MarketItem)
            .join(MarketItem, CurrencyAnalysis.market_item_id == MarketItem.id)
            .limit(500)
            .all()
        )
        data = [{
            "item": item.market_hash_name,
            "usd": curr.price_usd,
            "eur": curr.price_eur,
            "rub": curr.price_rub,
            "implied_usd_eur": curr.implied_usd_eur,
            "implied_usd_rub": curr.implied_usd_rub,
            "anomaly": curr.rounding_anomaly,
        } for curr, item in rows]
        return pd.DataFrame(data)


def plot_orderbook(buy_graph: list, sell_graph: list, title: str):
    fig = go.Figure()
    if sell_graph:
        prices = [e[0] for e in sell_graph]
        cum_qty = [e[2] if len(e) > 2 else e[1] for e in sell_graph]
        fig.add_trace(go.Scatter(x=cum_qty, y=prices, name="Sell", line=dict(color="red")))
    if buy_graph:
        prices = [e[0] for e in buy_graph]
        cum_qty = [e[2] if len(e) > 2 else e[1] for e in buy_graph]
        fig.add_trace(go.Scatter(x=cum_qty, y=prices, name="Buy", line=dict(color="green")))
    fig.update_layout(title=title, xaxis_title="Cumulative quantity", yaxis_title="Price")
    return fig


def tab_overview():
    st.header("Market Overview")
    stats = load_overview_stats()
    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("Apps researched", stats["apps"])
    c2.metric("Market items", stats["items"])
    c3.metric("Trading cards", stats["cards"])
    c4.metric("Items > $1", stats["above_1"])
    c5.metric("Positive net spread", stats["positive_spread"])
    c6.metric("Liquid items (vol≥10)", stats["liquid"])


def tab_cards():
    st.header("Cards Research")
    col1, col2, col3 = st.columns(3)
    with col1:
        tier = st.selectbox(
            "Price tier",
            ["All"] + [t[0] for t in CARD_PRICE_TIERS],
        )
        game = st.text_input("Game filter", "")
    with col2:
        foil_only = st.checkbox("Foil only")
        min_volume = st.number_input("Min volume", min_value=0, value=10)
    with col3:
        min_score = st.slider("Min opportunity score", -10.0, 20.0, -5.0)

    min_price, max_price = 0.10, None
    if tier != "All":
        for name, lo, hi in CARD_PRICE_TIERS:
            if name == tier:
                min_price = float(lo)
                max_price = float(hi) if hi else None

    df = load_cards_df(game or None, min_price, max_price, foil_only, min_volume)
    if not df.empty and min_score > -5:
        df = df[df["score"].fillna(-999) >= min_score]
    st.dataframe(df, use_container_width=True)


def tab_orderbooks():
    st.header("Order Books")
    with get_session() as session:
        items_with_ob = (
            session.query(MarketItem.id, MarketItem.market_hash_name)
            .join(OrderbookSnapshot, MarketItem.id == OrderbookSnapshot.market_item_id)
            .distinct()
            .limit(200)
            .all()
        )

    if not items_with_ob:
        st.info("No order book data yet. Run orderbook scan first.")
        return

    options = {name: iid for iid, name in items_with_ob}
    selected = st.selectbox("Select item", list(options.keys()))
    data = load_orderbook_item(options[selected])
    if not data:
        st.warning("No order book found")
        return

    col1, col2 = st.columns(2)
    with col1:
        st.plotly_chart(plot_orderbook(data["buy_graph"], [], f"Buy orders — {data['name']}"))
    with col2:
        st.plotly_chart(plot_orderbook([], data["sell_graph"], f"Sell listings — {data['name']}"))

    st.subheader("Metrics")
    st.json(data["metrics"])


def tab_currency():
    st.header("Currency Analysis")
    df = load_currency_df()
    if df.empty:
        st.info("No currency data yet.")
        return
    st.dataframe(df, use_container_width=True)
    anomalies = df[df["anomaly"] == True]
    if not anomalies.empty:
        st.subheader("Rounding anomalies")
        st.dataframe(anomalies)


def tab_fee():
    st.header("Fee Model")
    df = pd.DataFrame(build_fee_table())
    st.dataframe(df, use_container_width=True)
    st.line_chart(df.set_index("buyer_pays")["effective_fee_pct"])


def tab_opportunities():
    st.header("Opportunities")
    opps = ScoringEngine.get_top_opportunities(100)
    if not opps:
        st.info("No scored opportunities yet.")
        return
    df = pd.DataFrame(opps)
    st.dataframe(df, use_container_width=True)


def main():
    st.title("Steam Market Research Scanner")
    st.caption("Read-only research tool — no automated trading")

    tabs = st.tabs([
        "Market Overview",
        "Cards Research",
        "Order Books",
        "Currency Analysis",
        "Fee Model",
        "Opportunities",
    ])

    with tabs[0]:
        tab_overview()
    with tabs[1]:
        tab_cards()
    with tabs[2]:
        tab_orderbooks()
    with tabs[3]:
        tab_currency()
    with tabs[4]:
        tab_fee()
    with tabs[5]:
        tab_opportunities()


if __name__ == "__main__":
    main()
