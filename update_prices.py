from __future__ import annotations

import argparse
import math
import sqlite3
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import yfinance as yf


BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "nasdaq_prices.db"
TICKERS = ["NVDA", "AAPL", "MSFT", "GOOGL", "AMZN", "AVGO", "META", "SPCX", "MU"]
SOURCE = "yfinance"


def clean(value):
    if value is None:
        return None
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    return value


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Append daily NASDAQ stock data to SQLite.")
    parser.add_argument(
        "--date",
        help="Market date to fetch, YYYY-MM-DD. Defaults to yesterday in Asia/Seoul.",
    )
    parser.add_argument(
        "--backfill-valuations",
        action="store_true",
        help="Fill missing historical PSR values using the current TTM sales basis.",
    )
    return parser.parse_args()


def get_target_date(raw_date: str | None) -> date:
    if raw_date:
        return date.fromisoformat(raw_date)
    today_seoul = datetime.now(ZoneInfo("Asia/Seoul")).date()
    return today_seoul - timedelta(days=1)


def init_db(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS daily_prices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            date TEXT NOT NULL,
            company_name TEXT,
            exchange TEXT,
            currency TEXT,
            open REAL,
            high REAL,
            low REAL,
            close REAL,
            adj_close REAL,
            volume INTEGER,
            per REAL,
            forward_pe REAL,
            market_cap REAL,
            pbr REAL,
            psr REAL,
            dividend_yield REAL,
            source TEXT,
            fetched_at TEXT,
            UNIQUE (ticker, date)
        )
        """
    )


def migrate_db(conn: sqlite3.Connection) -> None:
    columns = {
        row[1] for row in conn.execute("PRAGMA table_info(daily_prices)").fetchall()
    }

    if "pe_ttm" in columns and "per" not in columns:
        conn.execute("ALTER TABLE daily_prices RENAME COLUMN pe_ttm TO per")
        columns.remove("pe_ttm")
        columns.add("per")

    if "price_to_book" in columns and "pbr" not in columns:
        conn.execute("ALTER TABLE daily_prices RENAME COLUMN price_to_book TO pbr")
        columns.remove("price_to_book")
        columns.add("pbr")

    if "psr" not in columns:
        conn.execute("ALTER TABLE daily_prices ADD COLUMN psr REAL")


def backfill_valuations(conn: sqlite3.Connection) -> tuple[int, list[str]]:
    updated = 0
    missing = []

    for ticker in TICKERS:
        stock = yf.Ticker(ticker)
        try:
            info = stock.get_info()
        except Exception as exc:
            missing.append(f"{ticker}: {type(exc).__name__}: {exc}")
            continue

        reference_price = clean(
            info.get("currentPrice")
            or info.get("regularMarketPrice")
            or info.get("previousClose")
        )
        current_psr = clean(info.get("priceToSalesTrailing12Months"))
        total_revenue = clean(info.get("totalRevenue"))

        rows = conn.execute(
            """
            SELECT id, close, market_cap
            FROM daily_prices
            WHERE ticker = ? AND psr IS NULL
            """,
            (ticker,),
        ).fetchall()

        for row_id, close, market_cap in rows:
            psr = None
            if current_psr is not None and reference_price and close is not None:
                psr = float(current_psr) * float(close) / float(reference_price)
            elif total_revenue and market_cap is not None:
                psr = float(market_cap) / float(total_revenue)

            if psr is None:
                missing.append(f"{ticker}: could not calculate PSR for row {row_id}")
                continue

            conn.execute(
                "UPDATE daily_prices SET psr = ? WHERE id = ?",
                (psr, row_id),
            )
            updated += 1

    return updated, missing


def fetch_row(ticker: str, target_date: date, fetched_at: str) -> tuple | None:
    next_date = target_date + timedelta(days=1)
    stock = yf.Ticker(ticker)
    history = stock.history(
        start=target_date.isoformat(),
        end=next_date.isoformat(),
        auto_adjust=False,
    )
    if history.empty:
        return None

    day = history.iloc[-1]
    info = {}
    try:
        info = stock.get_info()
    except Exception as exc:
        print(f"WARN {ticker}: could not fetch metrics: {type(exc).__name__}: {exc}")

    return (
        ticker,
        target_date.isoformat(),
        clean(info.get("longName")),
        clean(info.get("exchange")),
        clean(info.get("currency")),
        clean(float(day.get("Open"))),
        clean(float(day.get("High"))),
        clean(float(day.get("Low"))),
        clean(float(day.get("Close"))),
        clean(float(day.get("Adj Close"))),
        clean(int(day.get("Volume"))),
        clean(info.get("trailingPE")),
        clean(info.get("forwardPE")),
        clean(info.get("marketCap")),
        clean(info.get("priceToBook")),
        clean(info.get("priceToSalesTrailing12Months")),
        clean(info.get("dividendYield")),
        SOURCE,
        fetched_at,
    )


def upsert_rows(conn: sqlite3.Connection, rows: list[tuple]) -> None:
    conn.executemany(
        """
        INSERT INTO daily_prices (
            ticker, date, company_name, exchange, currency,
            open, high, low, close, adj_close, volume,
            per, forward_pe, market_cap, pbr, psr, dividend_yield,
            source, fetched_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(ticker, date) DO UPDATE SET
            company_name = excluded.company_name,
            exchange = excluded.exchange,
            currency = excluded.currency,
            open = excluded.open,
            high = excluded.high,
            low = excluded.low,
            close = excluded.close,
            adj_close = excluded.adj_close,
            volume = excluded.volume,
            per = excluded.per,
            forward_pe = excluded.forward_pe,
            market_cap = excluded.market_cap,
            pbr = excluded.pbr,
            psr = excluded.psr,
            dividend_yield = excluded.dividend_yield,
            source = excluded.source,
            fetched_at = excluded.fetched_at
        """,
        rows,
    )


def main() -> int:
    args = parse_args()

    if args.backfill_valuations:
        conn = sqlite3.connect(DB_PATH)
        try:
            init_db(conn)
            migrate_db(conn)
            updated, missing = backfill_valuations(conn)
            conn.commit()
        finally:
            conn.close()

        print(f"OK valuation backfill: filled {updated} PSR values.")
        for item in missing:
            print("MISSING", item)
        return 0 if not missing else 2

    target_date = get_target_date(args.date)

    if target_date.weekday() >= 5:
        print(f"SKIP {target_date.isoformat()}: weekend date.")
        return 0

    fetched_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    rows = []
    missing = []

    for ticker in TICKERS:
        try:
            row = fetch_row(ticker, target_date, fetched_at)
        except Exception as exc:
            missing.append(f"{ticker}: {type(exc).__name__}: {exc}")
            continue
        if row is None:
            missing.append(f"{ticker}: no market row for {target_date.isoformat()}")
        else:
            rows.append(row)

    if not rows:
        print(f"ERROR no rows fetched for {target_date.isoformat()}")
        for item in missing:
            print("MISSING", item)
        return 1

    conn = sqlite3.connect(DB_PATH)
    try:
        init_db(conn)
        migrate_db(conn)
        upsert_rows(conn, rows)
        conn.commit()
        count = conn.execute(
            "SELECT COUNT(*) FROM daily_prices WHERE date = ?",
            (target_date.isoformat(),),
        ).fetchone()[0]
    finally:
        conn.close()

    print(f"OK {target_date.isoformat()}: upserted {len(rows)} rows; table has {count} rows for date.")
    for item in missing:
        print("MISSING", item)
    return 0 if not missing else 2


if __name__ == "__main__":
    raise SystemExit(main())
