from __future__ import annotations

import html
import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


BASE_DIR = Path(__file__).resolve().parent
DATA_PATH = BASE_DIR / "earnings_calendar.json"
INDEX_PATH = BASE_DIR / "index.html"
TICKER_DIR = BASE_DIR / "tickers"

STATUS_LABELS = {
    "confirmed": ("일정 확정", "confirmed"),
    "estimated": ("예상 일정", "estimated"),
}
RESULT_LABELS = {
    "waiting": ("발표 대기", "waiting"),
    "released": ("자료 수집 중", "released"),
    "complete": ("분석 완료", "complete"),
}

CSS = """
:root {
  color-scheme: light;
  --bg: #f4f6f8;
  --panel: #ffffff;
  --text: #172033;
  --muted: #667085;
  --line: #dfe4ea;
  --navy: #17385f;
  --blue: #2f6f9f;
  --gold: #a87834;
  --olive: #6f7f3f;
  --rose: #a85f72;
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--text); font-family: -apple-system, BlinkMacSystemFont, "Apple SD Gothic Neo", "Noto Sans KR", sans-serif; line-height: 1.6; letter-spacing: 0; }
a { color: #245f96; text-underline-offset: 3px; }
.topbar { border-top: 4px solid var(--navy); border-bottom: 1px solid var(--line); background: #fff; }
.topbar-inner { width: min(1180px, calc(100% - 40px)); margin: 0 auto; padding: 16px 0; display: flex; align-items: center; justify-content: space-between; gap: 18px; }
.brand { color: var(--navy); font-weight: 850; text-decoration: none; }
.nav { display: flex; align-items: center; gap: 16px; font-size: .84rem; }
.nav a { color: #526174; text-decoration: none; }
.nav a[aria-current="page"] { color: var(--navy); font-weight: 800; }
.page { width: min(1180px, calc(100% - 40px)); margin: 0 auto; padding: 38px 0 72px; }
.eyebrow { margin-bottom: 7px; color: var(--gold); font-size: .76rem; font-weight: 850; }
h1, h2, h3 { color: var(--navy); letter-spacing: 0; }
h1 { margin: 0; font-size: 2.08rem; line-height: 1.2; }
h2 { margin: 40px 0 12px; padding-top: 24px; border-top: 1px solid var(--line); font-size: 1.35rem; }
h3 { margin: 0 0 7px; font-size: 1rem; }
.lede { max-width: 850px; margin: 12px 0 0; color: #536176; }
.summary-strip { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; margin: 22px 0 8px; }
.summary-item { padding: 12px 13px; border: 1px solid var(--line); border-radius: 6px; background: #fff; }
.summary-item span { display: block; color: var(--muted); font-size: .76rem; }
.summary-item strong { display: block; margin-top: 2px; color: var(--navy); font-size: 1.18rem; }
.table-wrap { overflow-x: auto; border: 1px solid var(--line); border-radius: 6px; background: #fff; }
table { width: 100%; min-width: 760px; border-collapse: collapse; font-variant-numeric: tabular-nums; }
th, td { padding: 10px 12px; border-bottom: 1px solid var(--line); text-align: left; }
th { background: var(--navy); color: #fff; font-size: .8rem; }
td { font-size: .86rem; }
tbody tr:nth-child(even) { background: #f8fafb; }
tbody tr:last-child td { border-bottom: 0; }
.ticker-link { color: var(--navy); font-weight: 850; text-decoration: none; }
.badge { display: inline-flex; align-items: center; gap: 5px; white-space: nowrap; font-size: .74rem; font-weight: 800; }
.badge::before { width: 7px; height: 7px; border-radius: 50%; background: currentColor; content: ""; }
.confirmed, .complete { color: var(--olive); }
.estimated, .waiting { color: var(--gold); }
.released { color: var(--blue); }
.ticker-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; }
.ticker-card { min-width: 0; padding: 16px; border: 1px solid var(--line); border-radius: 6px; background: #fff; color: var(--text); text-decoration: none; }
.ticker-card:hover { border-color: #9eb5ca; background: #fbfcfd; }
.ticker-card-head { display: flex; align-items: start; justify-content: space-between; gap: 12px; }
.ticker-symbol { color: var(--navy); font-size: 1.15rem; font-weight: 900; }
.company { margin-top: 1px; color: var(--muted); font-size: .8rem; }
.event-date { margin-top: 18px; color: var(--navy); font-weight: 800; font-variant-numeric: tabular-nums; }
.event-meta { color: var(--muted); font-size: .78rem; }
.card-footer { display: flex; align-items: center; justify-content: space-between; gap: 10px; margin-top: 13px; padding-top: 11px; border-top: 1px solid var(--line); }
.arrow { color: var(--gold); font-weight: 900; }
.back-link { display: inline-block; margin-bottom: 18px; font-size: .84rem; font-weight: 750; text-decoration: none; }
.company-title { display: flex; align-items: end; justify-content: space-between; gap: 18px; padding-bottom: 18px; border-bottom: 2px solid var(--navy); }
.company-title h1 { font-size: 2.25rem; }
.company-name { margin-top: 4px; color: var(--muted); }
.event-band { display: grid; grid-template-columns: 1.2fr 1fr 1fr; gap: 1px; margin-top: 18px; overflow: hidden; border: 1px solid var(--line); border-radius: 6px; background: var(--line); }
.event-band > div { padding: 13px 14px; background: #fff; }
.event-band span { display: block; color: var(--muted); font-size: .74rem; }
.event-band strong { display: block; margin-top: 3px; color: var(--navy); font-size: .94rem; }
.content-grid { display: grid; grid-template-columns: 1.15fr .85fr; gap: 20px; align-items: start; }
.section-stack { display: grid; gap: 20px; }
.report-section { padding-top: 18px; border-top: 1px solid var(--line); }
.report-section h2 { margin: 0 0 11px; padding: 0; border: 0; font-size: 1.2rem; }
.empty { min-height: 116px; padding: 18px; border: 1px dashed #b9c2cd; border-radius: 6px; background: #f9fafb; color: var(--muted); display: flex; align-items: center; }
.metric-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 8px; }
.metric { padding: 11px 12px; border-left: 3px solid var(--blue); background: #fff; }
.metric span { color: var(--muted); font-size: .75rem; }
.metric strong { display: block; color: var(--navy); }
.note-list { margin: 0; padding-left: 20px; }
.note-list li { margin: 7px 0; }
.reaction { padding: 15px; border-left: 3px solid var(--gold); background: #fbf7f0; }
.source-list { display: grid; gap: 7px; }
.source-list a { word-break: break-word; }
.footnote { margin-top: 34px; padding-top: 15px; border-top: 1px solid var(--line); color: var(--muted); font-size: .78rem; }
@media (max-width: 880px) {
  .ticker-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .content-grid { grid-template-columns: 1fr; }
}
@media (max-width: 620px) {
  .topbar-inner, .page { width: min(100% - 20px, 1180px); }
  .nav a:not([aria-current="page"]) { display: none; }
  h1 { font-size: 1.65rem; }
  .summary-strip, .ticker-grid, .event-band { grid-template-columns: 1fr; }
  .company-title { align-items: start; flex-direction: column; }
  .company-title h1 { font-size: 2rem; }
}
"""


def load_data() -> dict:
    return json.loads(DATA_PATH.read_text(encoding="utf-8"))


def esc(value: object) -> str:
    return html.escape(str(value))


def badge(status: str, labels: dict[str, tuple[str, str]]) -> str:
    label, class_name = labels.get(status, (status, "waiting"))
    return f'<span class="badge {class_name}">{esc(label)}</span>'


def page_shell(title: str, body: str, prefix: str, active: str) -> str:
    daily_current = ' aria-current="page"' if active == "daily" else ""
    earnings_current = ' aria-current="page"' if active == "earnings" else ""
    return f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="color-scheme" content="light">
  <title>{esc(title)}</title>
  <style>{CSS}</style>
</head>
<body>
  <header class="topbar"><div class="topbar-inner">
    <a class="brand" href="{prefix}index.html">미장분석</a>
    <nav class="nav" aria-label="리포트 이동">
      <a href="{prefix}일일리포트/나스닥_통합_리포트.html"{daily_current}>일일 리포트</a>
      <a href="{prefix}실적리포트/index.html"{earnings_current}>실적 트래커</a>
    </nav>
  </div></header>
  <main class="page">{body}</main>
</body>
</html>
"""


def schedule_date(item: dict) -> str:
    date = item.get("event_date_us") or "미정"
    return f"{date} (미국)"


def build_index(data: dict) -> str:
    tickers = sorted(data["tickers"], key=lambda item: item.get("event_date_us") or "9999")
    confirmed = sum(item["schedule_status"] == "confirmed" for item in tickers)
    complete = sum(item["result_status"] == "complete" for item in tickers)

    rows = []
    cards = []
    for item in tickers:
        ticker = esc(item["ticker"])
        ticker_href = f"tickers/{ticker}.html"
        rows.append(
            "<tr>"
            f'<td><a class="ticker-link" href="{ticker_href}">{ticker}</a></td>'
            f"<td>{esc(item['company'])}</td>"
            f"<td>{esc(item['fiscal_period'])}</td>"
            f"<td>{esc(schedule_date(item))}</td>"
            f"<td>{esc(item.get('event_datetime_kst') or '미정')}</td>"
            f"<td>{badge(item['schedule_status'], STATUS_LABELS)}</td>"
            f"<td>{badge(item['result_status'], RESULT_LABELS)}</td>"
            "</tr>"
        )
        cards.append(
            f'<a class="ticker-card" href="{ticker_href}">'
            '<div class="ticker-card-head"><div>'
            f'<div class="ticker-symbol">{ticker}</div>'
            f'<div class="company">{esc(item["company"])}</div>'
            f'</div>{badge(item["schedule_status"], STATUS_LABELS)}</div>'
            f'<div class="event-date">{esc(schedule_date(item))}</div>'
            f'<div class="event-meta">한국 {esc(item.get("event_datetime_kst") or "미정")} · {esc(item["fiscal_period"])}</div>'
            f'<div class="card-footer">{badge(item["result_status"], RESULT_LABELS)}<span class="arrow">→</span></div>'
            "</a>"
        )

    body = f"""
    <div class="eyebrow">EARNINGS WATCH · 9 COMPANIES</div>
    <h1>{esc(data['season'])} 트래커</h1>
    <p class="lede">{esc(data['season_note'])} 확정 일정과 시장 캘린더 예상일을 구분하며, 발표 자료가 확인되면 종목별 핵심 내용과 시장 반응을 채웁니다.</p>
    <div class="summary-strip">
      <div class="summary-item"><span>추적 종목</span><strong>{len(tickers)}</strong></div>
      <div class="summary-item"><span>회사 확정 일정</span><strong>{confirmed}</strong></div>
      <div class="summary-item"><span>분석 완료</span><strong>{complete}</strong></div>
    </div>
    <h2>발표 일정</h2>
    <div class="table-wrap"><table>
      <thead><tr><th>종목</th><th>회사</th><th>회사 표기 분기</th><th>미국 발표일</th><th>한국 시각</th><th>일정</th><th>리포트</th></tr></thead>
      <tbody>{''.join(rows)}</tbody>
    </table></div>
    <h2>종목별 실적 노트</h2>
    <div class="ticker-grid">{''.join(cards)}</div>
    <div class="footnote">일정 기준일: {esc(data['as_of'])} · 확정 일정은 회사 IR, 예상 일정은 시장 캘린더 기준이며 자동 점검 시 갱신됩니다.</div>
    """
    return page_shell("미장분석 실적 트래커", body, "../", "earnings")


def render_metrics(results: dict) -> str:
    metrics = results.get("metrics", [])
    if not metrics:
        return '<div class="empty">발표 자료 확인 후 매출, EPS, 핵심 KPI와 예상치 대비 결과가 채워집니다.</div>'
    items = []
    for metric in metrics:
        comparison = metric.get("comparison")
        detail = f" · {esc(comparison)}" if comparison else ""
        items.append(
            '<div class="metric">'
            f'<span>{esc(metric.get("label", "지표"))}</span>'
            f'<strong>{esc(metric.get("actual", "N/A"))}{detail}</strong>'
            "</div>"
        )
    return f'<div class="metric-grid">{"".join(items)}</div>'


def render_notes(items: list[dict], empty_text: str) -> str:
    if not items:
        return f'<div class="empty">{esc(empty_text)}</div>'
    rows = []
    for item in items:
        text = esc(item.get("text", ""))
        url = item.get("source_url")
        source = (
            f' <a href="{esc(url)}" target="_blank" rel="noopener noreferrer">근거</a>'
            if url
            else ""
        )
        rows.append(f"<li>{text}{source}</li>")
    return f'<ul class="note-list">{"".join(rows)}</ul>'


def render_reaction(results: dict) -> str:
    reaction = results.get("market_reaction", {})
    if not reaction:
        return '<div class="empty">발표 직후 시간외 흐름과 다음 정규장 반응을 구분해 기록합니다.</div>'
    moves = []
    for label, key in [("시간외", "after_hours_change_pct"), ("다음 정규장", "regular_change_pct")]:
        value = reaction.get(key)
        if value is not None:
            moves.append(f"{label} {float(value):+.2f}%")
    move_text = " · ".join(moves)
    summary = esc(reaction.get("summary", ""))
    return f'<div class="reaction"><strong>{esc(move_text)}</strong><p>{summary}</p></div>'


def build_ticker_page(data: dict, item: dict) -> str:
    results = item.get("results") or {}
    updated_at = results.get("updated_at")
    sources = [
        {
            "label": "실적 일정 근거",
            "url": item["schedule_source_url"],
        },
        {"label": "회사 IR", "url": item["ir_url"]},
        *results.get("sources", []),
    ]
    source_links = "".join(
        f'<a href="{esc(source["url"])}" target="_blank" rel="noopener noreferrer">{esc(source.get("label", "자료"))}</a>'
        for source in sources
        if source.get("url")
    )
    verdict = results.get("verdict")
    verdict_html = (
        f'<div class="reaction"><strong>한줄 판단</strong><p>{esc(verdict)}</p></div>'
        if verdict
        else '<div class="empty">실적 발표 전입니다. 발표 자료가 확인되면 한줄 판단과 핵심 변화가 채워집니다.</div>'
    )

    body = f"""
    <a class="back-link" href="../index.html">← 전체 일정</a>
    <div class="company-title">
      <div><div class="eyebrow">EARNINGS NOTE · {esc(item['fiscal_period'])}</div><h1>{esc(item['ticker'])}</h1><div class="company-name">{esc(item['company'])}</div></div>
      <div>{badge(item['result_status'], RESULT_LABELS)}</div>
    </div>
    <div class="event-band">
      <div><span>발표 일정</span><strong>{esc(schedule_date(item))} · {esc(item['timing'])}</strong></div>
      <div><span>한국 시각</span><strong>{esc(item.get('event_datetime_kst') or '미정')}</strong></div>
      <div><span>일정 신뢰도</span><strong>{badge(item['schedule_status'], STATUS_LABELS)}</strong></div>
    </div>
    <p class="lede">{esc(item['schedule_note'])}</p>
    <h2>실적 요약</h2>
    {verdict_html}
    <div class="content-grid">
      <div class="section-stack">
        <section class="report-section"><h2>핵심 지표</h2>{render_metrics(results)}</section>
        <section class="report-section"><h2>주요 내용</h2>{render_notes(results.get('highlights', []), '발표 자료와 경영진 코멘트의 핵심 내용을 정리할 자리입니다.')}</section>
        <section class="report-section"><h2>가이던스와 체크포인트</h2>{render_notes(results.get('guidance', []), '다음 분기 가이던스와 핵심 KPI 변화가 발표 후 채워집니다.')}</section>
      </div>
      <div class="section-stack">
        <section class="report-section"><h2>시장 반응</h2>{render_reaction(results)}</section>
        <section class="report-section"><h2>근거 자료</h2><div class="source-list">{source_links}</div></section>
      </div>
    </div>
    <div class="footnote">마지막 분석 갱신: {esc(updated_at or '발표 대기')} · 일정 기준일: {esc(data['as_of'])}</div>
    """
    return page_shell(
        f"{item['ticker']} 실적 노트",
        body,
        "../../",
        "earnings",
    )


def main() -> int:
    data = load_data()
    TICKER_DIR.mkdir(parents=True, exist_ok=True)
    INDEX_PATH.write_text(build_index(data), encoding="utf-8")
    for item in data["tickers"]:
        output = TICKER_DIR / f"{item['ticker']}.html"
        output.write_text(build_ticker_page(data, item), encoding="utf-8")

    generated_at = datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d %H:%M KST")
    print(f"saved: {INDEX_PATH}")
    print(f"ticker pages: {len(data['tickers'])}; generated: {generated_at}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
