from __future__ import annotations

import argparse
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


REPORT_DIR = Path(__file__).resolve().parent
BASE_DIR = REPORT_DIR.parent
DB_PATH = BASE_DIR / "nasdaq_prices.db"
MOVER_THRESHOLD = 3.0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a daily stock report markdown page.")
    parser.add_argument("--date", help="Report date, YYYY-MM-DD. Defaults to latest DB date.")
    return parser.parse_args()


def load_prices() -> pd.DataFrame:
    conn = sqlite3.connect(DB_PATH)
    try:
        return pd.read_sql_query(
            """
            SELECT ticker, date, close
            FROM daily_prices
            ORDER BY date, ticker
            """,
            conn,
            parse_dates=["date"],
        )
    finally:
        conn.close()


def markdown_table(df: pd.DataFrame) -> str:
    if df.empty:
        return "데이터 없음.\n"

    header = "| " + " | ".join(df.columns) + " |"
    divider = "| " + " | ".join(["---"] * len(df.columns)) + " |"
    rows = []
    for _, row in df.iterrows():
        rows.append("| " + " | ".join(str(row[col]) for col in df.columns) + " |")
    return "\n".join([header, divider, *rows]) + "\n"


def preserved_cause_section(existing_report: str, ticker: str) -> str | None:
    pattern = re.compile(
        rf"<!-- CAUSE:{re.escape(ticker)}:START -->.*?<!-- CAUSE:{re.escape(ticker)}:END -->",
        re.DOTALL,
    )
    match = pattern.search(existing_report)
    if not match:
        return None
    section = match.group(0)
    if "자동화가 웹/뉴스 확인 후 채울 자리" in section:
        return None
    return section


def main() -> int:
    args = parse_args()
    df = load_prices()
    if df.empty:
        print("ERROR: daily_prices is empty")
        return 1

    prices = df.pivot(index="date", columns="ticker", values="close").sort_index()
    dates = list(prices.index)
    report_date = pd.Timestamp(args.date) if args.date else dates[-1]
    if report_date not in prices.index:
        print(f"ERROR: {report_date.date().isoformat()} not found in DB")
        return 1

    date_pos = dates.index(report_date)
    if date_pos == 0:
        print("ERROR: report date has no previous trading day for change calculation")
        return 1

    prev_date = dates[date_pos - 1]
    change_pct = ((prices.loc[report_date] / prices.loc[prev_date]) - 1) * 100

    summary = pd.DataFrame(
        {
            "ticker": change_pct.index,
            "close": prices.loc[report_date].round(2).values,
            "change_pct": change_pct.round(2).values,
        }
    ).sort_values("change_pct", ascending=False)

    movers = summary[summary["change_pct"].abs() >= MOVER_THRESHOLD].copy()
    movers["close"] = movers["close"].map(lambda value: f"{value:.2f}")
    movers["change_pct"] = movers["change_pct"].map(lambda value: f"{value:+.2f}%")

    all_changes = summary.copy()
    all_changes["close"] = all_changes["close"].map(lambda value: f"{value:.2f}")
    all_changes["change_pct"] = all_changes["change_pct"].map(lambda value: f"{value:+.2f}%")

    report_date_str = report_date.strftime("%Y-%m-%d")
    prev_date_str = prev_date.strftime("%Y-%m-%d")
    output = REPORT_DIR / f"{report_date_str}.md"
    existing_report = output.read_text(encoding="utf-8") if output.exists() else ""

    cause_sections = []
    if movers.empty:
        cause_sections.append("3% 이상 변동 종목 없음.\n")
    else:
        for _, row in movers.iterrows():
            ticker = row["ticker"]
            change = row["change_pct"]
            cause_body = preserved_cause_section(existing_report, ticker)
            if cause_body is None:
                cause_body = "\n".join(
                    [
                        f"<!-- CAUSE:{ticker}:START -->",
                        "- 원인: 자동화가 웹/뉴스 확인 후 채울 자리.",
                        "- 근거 링크: 조사 필요.",
                        f"<!-- CAUSE:{ticker}:END -->",
                    ]
                )
            cause_sections.append(
                "\n".join(
                    [
                        f"### {ticker} ({change})",
                        cause_body,
                        "",
                    ]
                )
            )

    generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    mover_table = movers[["ticker", "close", "change_pct"]].rename(
        columns={"ticker": "종목", "close": "종가", "change_pct": "등락률"}
    )
    all_changes_table = all_changes[["ticker", "close", "change_pct"]].rename(
        columns={"ticker": "종목", "close": "종가", "change_pct": "등락률"}
    )
    report = "\n".join(
        [
            f"# 나스닥 일일 주가 리포트 - {report_date_str}",
            "",
            f"- 데이터 날짜: {report_date_str}",
            f"- 비교 기준일: {prev_date_str}",
            f"- 생성 시각(UTC): {generated_at}",
            f"- 3% 이상 변동 기준: abs(change_pct) >= {MOVER_THRESHOLD:.1f}%",
            "",
            "## 전체 종목 변화율",
            "",
            "<!-- CHART:DAILY_RETURN_BAR -->",
            "",
            markdown_table(all_changes_table),
            "",
            "## 시장 흐름 히트맵",
            "",
            "<!-- CHART:HEATMAPS -->",
            "",
            "## 종목별 변화 추이",
            "",
            "<!-- CHART:PRICE_TREND -->",
            "",
            "## PER·PBR·PSR 변화 추이",
            "",
            "<!-- CHART:VALUATION_TRENDS -->",
            "",
            "## 3% 이상 변동 종목",
            "",
            markdown_table(mover_table),
            "",
            "## 원인 메모",
            "",
            "\n".join(cause_sections),
        ]
    )

    output.write_text(report, encoding="utf-8")
    print(f"saved: {output}")
    print(f"movers: {', '.join(movers['ticker']) if not movers.empty else 'none'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
