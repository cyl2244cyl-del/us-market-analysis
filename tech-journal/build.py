#!/usr/bin/env python3
"""Build dated Markdown market and event records from reviewed inputs."""
from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from html import escape
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


def signed(value, unit="%"):
    return ("+" if value > 0 else "−" if value < 0 else "") + f"{abs(value):.2f}" + unit


def slug(title):
    return re.sub(r"[^\w\- ]", "", title.lower()).replace(" ", "-")


def source_link(publisher, url):
    return f"[\\[{publisher}\\]]({url})"


def write_heatmap(day, stocks):
    cells = []
    for i, stock in enumerate(stocks):
        x, y = 12 + (i % 5) * 198, 12 + (i // 5) * 108
        weight = min(abs(stock["change_pct"]), 7) / 7
        target = (162, 203, 187) if stock["change_pct"] >= 0 else (235, 180, 184)
        color = "#" + "".join(f"{round(246 + (c - 246) * weight):02x}" for c in target)
        label = escape(stock["ticker"] + " " + signed(stock["change_pct"]))
        cells.append(
            f'<g><title>{label}</title><rect x="{x}" y="{y}" width="186" height="96" rx="8" fill="{color}"/>'
            f'<text x="{x+15}" y="{y+29}" font-size="17" font-weight="700">{escape(stock["ticker"])}</text>'
            f'<text x="{x+15}" y="{y+70}" font-size="26" font-weight="600">{escape(signed(stock["change_pct"]))}</text></g>'
        )
    image = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="1002" height="336" viewBox="0 0 1002 336" role="img" aria-labelledby="title desc">'
        f'<title id="title">{day} stock returns</title><desc id="desc">15 equal-size cells; green gains, red losses. Color scale capped at 7 percent.</desc>'
        '<rect width="1002" height="336" fill="white"/><g fill="#23392c" font-family="Arial, sans-serif">'
        + "".join(cells) + '</g></svg>\n'
    )
    (ROOT / "market" / f"{day}.heatmap.svg").write_text(image, encoding="utf-8")


def write_markdown(day, market, event_doc, archive_dates, case_history):
    event_labels = {"nvidia-leadership": "CEO 교체", "nebius-capacity": "네비우스", "microsoft-365-outage": "365 장애", "spacex-tesla-merger": "합병 협상"}
    lines = [f"# {day} 시장 현황", "", f"미국 정규장 마감 기준 · [사건 기록](../events/{day}.md)", "", "## 지수", "", "| 지수 | 종가 | 등락률 |", "| --- | ---: | ---: |"]
    lines.extend(f"| {x['label']} | {x['close']:,.2f} | {signed(x['change_pct'])} |" for x in market["indices"])
    lines += [""]
    lines.extend(source_link(x["source_label"], x["source_url"]) + " " + x["text"] + "\n" for x in market["overview"])
    lines += ["| ETF | 종가($) | 등락률 |", "| --- | ---: | ---: |"]
    lines.extend(f"| [{x['ticker']}]({x['source_url']}) | {x['close']:,.2f} | {signed(x['change_pct'])} |" for x in market["benchmark_quotes"])
    lines += ["", "## 히트맵", "", f"![{day} 관심 종목 15개 등락률]({day}.heatmap.svg)", "", "## 종목별 현황", "", "| 종목 | 종가($) | 등락률 | QQQ 대비 | 20일선($) · 이격률 | RSI 14 | 거래량 배수 | 사건 |", "| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |"]
    for stock in market["stocks"]:
        links = ", ".join(
            f"[{event_labels.get(e['case_id'], e['title'])}](../events/{day}.md#{slug(e['title'])})" + (" 연계" if e["relation"] == "연계" else "")
            for e in stock["events"]
        ) or "—"
        lines.append(
            f"| [{stock['ticker']}]({stock['source_url']}) | {stock['close']:,.2f} | {signed(stock['change_pct'])} | "
            f"{signed(stock['relative_to_qqq_pp'], '%p')} | {stock['sma20']:,.2f} · {signed(stock['distance_to_sma20_pct'])} | "
            f"{stock['rsi14']:.1f} | {stock['volume_ratio']:.2f}× | {links} |"
        )
    lines += ["", "가격·거래량: 각 종목 링크의 Stock Analysis 이력. 거래량 배수는 직전 20거래일 평균 대비.", "", "QQQ 대비는 당일 등락률 차이(%p). 20일선은 당일 포함 20거래일 평균. RSI 14는 확보한 49거래일의 종가로 계산한 Wilder 방식."]
    (ROOT / "market" / f"{day}.md").write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")

    start, end = (datetime.fromisoformat(event_doc[k]) for k in ("window_start_exclusive", "window_end_inclusive"))
    period = f"{start.month}/{start.day} 장 마감 후 ~ {end.month}/{end.day} 정규장 마감"
    lines = [f"# {day} 사건 기록", "", f"{period} · 미국 동부시간 · [시장 현황](../market/{day}.md)", ""]
    for i, event in enumerate(event_doc["events"]):
        if i:
            lines += ["---", ""]
        direct = event.get("external_tickers", []) + event["primary_tickers"]
        metadata = [event["period"]] + direct
        if event["related_tickers"]:
            metadata.append("연계: " + ", ".join(event["related_tickers"]))
        lines += [f"## {event['title']}", "", " · ".join(metadata), ""]
        sources = {s["id"]: s for s in event["sources"]}
        for paragraph in event["paragraphs"]:
            source = sources[paragraph["source_id"]]
            lines += [source_link(source["publisher"], source["url"]) + " " + paragraph["text"], ""]
        previous = [h for h in case_history[event["case_id"]] if h["trading_date"] != day]
        if previous:
            lines += ["연계 기록: " + " · ".join(f"[{h['trading_date']}]({h['trading_date']}.md#{slug(h['title'])})" for h in previous), ""]
    (ROOT / "events" / f"{day}.md").write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")

    index = ["# 기술주 일지", "", "| 날짜 | 시장 현황 | 사건 기록 |", "| --- | --- | --- |"]
    index.extend(f"| {d} | [시장 현황](market/{d}.md) | [사건 기록](events/{d}.md) |" for d in reversed(archive_dates))
    (ROOT / "README.md").write_text("\n".join(index) + "\n", encoding="utf-8")
    for folder, title in (("market", "시장 현황"), ("events", "사건 기록")):
        index = [f"# {title}", ""] + [f"- [{d}]({d}.md)" for d in reversed(archive_dates)]
        (ROOT / folder / "README.md").write_text("\n".join(index) + "\n", encoding="utf-8")


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
    write_heatmap(day, stocks)
    write_markdown(day, market, event_doc, archive_dates, case_history)
    return market, event_doc


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("date", help="US trading date: YYYY-MM-DD")
    args = parser.parse_args()
    market, events = build(args.date)
    print(f"Built {args.date}: {len(market['stocks'])} stocks, {len(events['events'])} event blocks, Markdown reports.")
