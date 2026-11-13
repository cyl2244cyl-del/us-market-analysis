#!/usr/bin/env python3
"""Build frozen, offline daily views from reviewed inputs; performs no network writes."""
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from statistics import fmean

ROOT = Path(__file__).resolve().parent


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def pct(current, previous):
    return (current / previous - 1) * 100


def rsi14(closes):
    changes = [b - a for a, b in zip(closes, closes[1:])]
    if len(changes) < 14:
        return None
    gain = fmean(max(x, 0) for x in changes[:14])
    loss = fmean(max(-x, 0) for x in changes[:14])
    for change in changes[14:]:
        gain = (gain * 13 + max(change, 0)) / 14
        loss = (loss * 13 + max(-change, 0)) / 14
    if loss == 0:
        return 100.0 if gain else 50.0
    return 100 - 100 / (1 + gain / loss)


def build(day):
    config = load(ROOT / "watchlist.json")
    inputs = load(ROOT / "market" / f"{day}.inputs.json")
    event_doc = load(ROOT / "events" / f"{day}.json")
    overview = load(ROOT / "market" / f"{day}.overview.json")
    start = datetime.fromisoformat(event_doc["window_start_exclusive"])
    end = datetime.fromisoformat(event_doc["window_end_inclusive"])
    assert event_doc["trading_date"] == day
    assert start < end
    assert len(set(e["case_id"] for e in event_doc["events"])) == len(event_doc["events"]), "Merge connected same-day events"
    for event in event_doc["events"]:
        refs = {s["id"] for s in event["sources"]}
        assert all(p["source_id"] in refs for p in event["paragraphs"])
        for source in event["sources"]:
            assert source["url"].startswith("https://")
            if source.get("published_at"):
                assert start < datetime.fromisoformat(source["published_at"]) <= end, source["id"]
            else:
                assert source["published_date"] == day and source["session_evidence"]
            for field in ("updated_at", "used_version_at"):
                if field in source:
                    assert datetime.fromisoformat(source[field]) <= end, source["id"]

    def checked_history(ticker):
        data = inputs[ticker]
        hist = data["history"]
        dates = [r["date"] for r in hist]
        assert dates == sorted(set(dates))
        assert dates[-1] == day and data["latest"]["date"] == day
        assert all(d <= day for d in dates)
        assert len(hist) >= 21
        assert all(r["close"] > 0 and r["volume"] >= 0 for r in hist)
        assert hist[-1]["close"] == data["latest"]["close"]
        return hist

    benchmark = config["relative_benchmark"]
    qhist = checked_history(benchmark)
    benchmark_change = pct(qhist[-1]["close"], qhist[-2]["close"])
    stocks = []
    names = {
        "MSFT": "마이크로소프트", "AMZN": "아마존", "GOOGL": "알파벳", "ORCL": "오라클",
        "CRWV": "코어위브", "NVDA": "엔비디아", "AVGO": "브로드컴", "MU": "마이크론",
        "SNDK": "샌디스크", "MRVL": "마벨", "AMD": "AMD", "ARM": "Arm", "META": "메타",
        "PLTR": "팔란티어", "SPCX": "스페이스X"
    }
    for ticker in config["tickers"]:
        h = checked_history(ticker)
        close = h[-1]["close"]
        change = pct(close, h[-2]["close"])
        sma = fmean(r["close"] for r in h[-20:])
        vol_avg = fmean(r["volume"] for r in h[-21:-1])
        links = []
        for event in event_doc["events"]:
            if ticker in event["primary_tickers"]:
                links.append({"id": event["id"], "case_id": event["case_id"], "title": event["title"], "relation": "직접"})
            elif ticker in event["related_tickers"]:
                links.append({"id": event["id"], "case_id": event["case_id"], "title": event["title"], "relation": "연계"})
        stocks.append({
            "ticker": ticker, "name": names[ticker], "close": close,
            "previous_close": h[-2]["close"], "change_pct": change,
            "relative_to_qqq_pp": change - benchmark_change,
            "sma20": sma, "distance_to_sma20_pct": pct(close, sma),
            "rsi14": rsi14([r["close"] for r in h]),
            "volume": h[-1]["volume"], "previous_20_volume_average": vol_avg,
            "volume_ratio": h[-1]["volume"] / vol_avg if vol_avg else None,
            "source_url": inputs[ticker]["source_url"], "history_count": len(h),
            "rsi_seed_start": h[0]["date"], "events": links
        })
    indices = []
    for index in overview["indices"]:
        index = dict(index)
        index["previous_close"] = index["close"] - index["point_change"]
        index["change_pct"] = pct(index["close"], index["previous_close"])
        indices.append(index)
    benchmark_quotes = []
    for ticker in ["QQQ", "SPY"]:
        h = checked_history(ticker)
        benchmark_quotes.append({"ticker": ticker, "close": h[-1]["close"], "change_pct": pct(h[-1]["close"], h[-2]["close"]), "source_url": inputs[ticker]["source_url"]})
    market = {
        "trading_date": day, "timezone": config["timezone"], "currency": "USD",
        "price_as_of": day + "T16:00:00-05:00", "benchmark": benchmark,
        "benchmark_change_pct": benchmark_change, "indices": indices,
        "benchmark_quotes": benchmark_quotes, "stocks": stocks,
        "overview": overview["summary"], "index_source": overview["source"],
        "methods": {
            "change_pct": "(당일 정규장 종가 / 전 거래일 정규장 종가 - 1) × 100",
            "relative_to_qqq_pp": "종목 당일 등락률 - QQQ 당일 등락률. 업종 초과수익률이 아닌 공통 벤치마크 대비 %p.",
            "sma20": "당일을 포함한 최근 20거래일 Close의 단순평균",
            "distance_to_sma20_pct": "(당일 종가 / SMA20 - 1) × 100",
            "rsi14": "Wilder 14. 확보된 49거래일의 첫 14개 변화로 평균 상승·하락을 초기화하고 이후 (이전 평균×13+당일 변화)/14. 시작일 2026-09-04. 더 긴 이력을 쓰는 서비스와 값이 다를 수 있음.",
            "volume_ratio": "당일 거래량 / 직전 20거래일 평균 거래량. 평균에서 당일은 제외.",
            "price_basis": "Stock Analysis 역사 표의 Close. 해당 제공자는 주식분할 조정을 명시. Adj. Close 기반 총수익률을 사용하지 않음.",
            "heatmap": "15개 종목 동일 면적. 배경은 일간 등락률이며 색 농도 상한 ±7%. 셀 수치는 실제 등락률.",
            "coverage": "지표와 종가에 11월 13일 자료를 사용하지 않음. 60일선은 확보한 49거래일 범위를 넘어 포함하지 않음."
        }
    }
    write_json(ROOT / "market" / f"{day}.json", market)
    archive_dates = sorted(
        p.stem for p in (ROOT / "events").glob("????-??-??.json")
        if p.stem <= day and (ROOT / "market" / f"{p.stem}.json").exists()
    )
    case_history = {}
    for archive_day in archive_dates:
        for event in load(ROOT / "events" / f"{archive_day}.json")["events"]:
            case_history.setdefault(event["case_id"], []).append({
                "trading_date": archive_day, "event_id": event["id"],
                "title": event["title"], "sources": event["sources"]
            })
    payload = {"market": market, "days": archive_dates, "event_document": event_doc, "case_history": case_history}
    template = (ROOT / "template.html").read_text(encoding="utf-8")
    serialized = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")
    for relative_path, initial_tab in [("index.html", "market"), (f"market/{day}.html", "market"), (f"events/{day}.html", "events")]:
        label = f"{int(day[5:7])}월 {int(day[8:10])}일"
        start_label = f"{int(start.strftime('%m'))}/{int(start.strftime('%d'))} 장 마감 후"
        end_label = f"{int(end.strftime('%m'))}/{int(end.strftime('%d'))} 정규장 마감"
        html = (template.replace("__PAYLOAD__", serialized)
                .replace("__INITIAL_TAB__", initial_tab)
                .replace("__TRADING_DATE__", day)
                .replace("__DAY_LABEL__", label)
                .replace("__WINDOW_LABEL__", start_label + " ~ " + end_label)
                .replace("__ARCHIVE_BASE__", "." if relative_path == "index.html" else ".."))
        (ROOT / relative_path).write_text(html, encoding="utf-8")
    return market, event_doc


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("date", help="US trading date: YYYY-MM-DD")
    args = parser.parse_args()
    market, events = build(args.date)
    print(f"Built {args.date}: {len(market['stocks'])} stocks, {len(events['events'])} connected event blocks, 3 offline HTML views.")
