from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parent.parent
CALENDAR_PATH = ROOT / "실적리포트" / "earnings_calendar.json"
FOCUS_PATH = ROOT / "config" / "earnings_focus.json"
DEFAULT_REPORT_ROOT = ROOT / "reports" / "earnings"

STAGE_LABELS = {
    "scheduled": "일정 확정",
    "preview_ready": "프리뷰 완료",
    "release_captured": "발표 수치 반영",
    "call_reviewed": "콘퍼런스콜 분석 완료",
    "regular_close_recorded": "다음 정규장 반응 완료",
    "five_day_reviewed": "5거래일 회고 완료",
}

LEGACY_STAGE_MAP = {
    "numbers_released": "release_captured",
    "reaction_final": "regular_close_recorded",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build GitHub-rendered earnings season Markdown notes."
    )
    parser.add_argument(
        "--as-of",
        help="KST freeze time (YYYY-MM-DD or ISO datetime). Defaults to now.",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=DEFAULT_REPORT_ROOT,
        help="Directory containing season folders.",
    )
    parser.add_argument(
        "--force-ticker",
        action="append",
        default=[],
        help="Generate a ticker note even when it is outside the preview window.",
    )
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def parse_freeze_time(raw: str | None, timezone: ZoneInfo) -> datetime:
    if not raw:
        return datetime.now(timezone)
    parsed = datetime.fromisoformat(raw)
    if parsed.tzinfo is None:
        if "T" not in raw and " " not in raw:
            parsed = parsed.replace(hour=12)
        return parsed.replace(tzinfo=timezone)
    return parsed.astimezone(timezone)


def event_time(item: dict[str, Any], timezone: ZoneInfo, date_only_time: str) -> datetime:
    raw = item.get("event_datetime_kst") or item["event_date_us"]
    if len(raw) == 10:
        raw = f"{raw} {date_only_time}"
    return datetime.fromisoformat(raw).replace(tzinfo=timezone)


def infer_stage(
    item: dict[str, Any], focus: dict[str, Any], freeze: datetime, event: datetime
) -> str:
    results = item.get("results") or {}
    explicit = results.get("document_stage") or results.get("analysis_stage")
    explicit = LEGACY_STAGE_MAP.get(explicit, explicit)
    if explicit in STAGE_LABELS:
        return explicit

    reaction = results.get("market_reaction") or {}
    checkpoints = {
        str(checkpoint.get("window")): checkpoint
        for checkpoint in reaction.get("checkpoints", [])
        if isinstance(checkpoint, dict) and checkpoint.get("window")
    }
    if checkpoints.get("five_day", {}).get("change_pct") is not None:
        return "five_day_reviewed"
    if reaction.get("regular_change_pct") is not None:
        return "regular_close_recorded"
    if checkpoints.get("next_regular_close", {}).get("change_pct") is not None:
        return "regular_close_recorded"
    if results.get("call_answers"):
        return "call_reviewed"
    if item.get("result_status") == "complete":
        return "regular_close_recorded"
    if item.get("result_status") == "released" or results:
        return "release_captured"

    preview_hours = float(focus.get("preview_window_hours", 48))
    hours_to_event = (event - freeze).total_seconds() / 3600
    # Once the preview window opens, a late or delayed upstream result must not
    # regress the document to `scheduled` merely because the event time passed.
    if hours_to_event <= preview_hours:
        return "preview_ready"
    return "scheduled"


def should_generate(
    ticker: str,
    stage: str,
    ticker_focus: dict[str, Any],
    output_path: Path,
    forced: set[str],
) -> bool:
    return bool(
        stage != "scheduled"
        or ticker_focus.get("force_generate")
        or ticker in forced
        or output_path.exists()
    )


def scalar(value: Any, default: str = "—") -> str:
    if value is None or value == "":
        return default
    return str(value).replace("\n", " ").replace("|", "\\|")


def pct(value: Any) -> str:
    if value is None or value == "":
        return "—"
    try:
        return f"{float(value):+.2f}%"
    except (TypeError, ValueError):
        return scalar(value)


def list_lines(items: list[Any], empty: str = "- 아직 확인되지 않았습니다.") -> list[str]:
    if not items:
        return [empty]
    lines: list[str] = []
    for item in items:
        if isinstance(item, dict):
            title = item.get("title") or item.get("label")
            detail = item.get("detail") or item.get("text") or item.get("answer")
            if title and detail:
                lines.append(f"- **{scalar(title)}:** {scalar(detail)}")
            else:
                lines.append(f"- {scalar(detail or title or item)}")
        else:
            lines.append(f"- {scalar(item)}")
    return lines


def scorecard_rows(
    results: dict[str, Any], focus: dict[str, Any], ticker_focus: dict[str, Any]
) -> list[str]:
    metrics = results.get("metrics") or []
    if not metrics:
        metrics = [dict(metric) for metric in focus.get("default_scorecard_metrics", [])]
        for item in ticker_focus.get("focus_items", []):
            if item.get("id") not in {metric.get("id") for metric in metrics}:
                metrics.append({"id": item.get("id"), "label": item.get("label")})

    rows = []
    for metric in metrics:
        assessment = metric.get("assessment") or metric.get("comparison")
        rows.append(
            "| "
            + " | ".join(
                [
                    scalar(metric.get("label") or metric.get("id") or "지표"),
                    scalar(metric.get("previous")),
                    scalar(metric.get("consensus")),
                    scalar(metric.get("actual")),
                    scalar(metric.get("delta")),
                    scalar(assessment),
                ]
            )
            + " |"
        )
    return rows


def question_sections(
    ticker_focus: dict[str, Any], results: dict[str, Any]
) -> tuple[list[str], list[str]]:
    answers = {
        str(item.get("id")): item
        for item in results.get("call_answers", [])
        if isinstance(item, dict) and item.get("id")
    }
    preview_lines: list[str] = []
    call_lines: list[str] = []
    for number, item in enumerate(ticker_focus.get("focus_items", []), start=1):
        item_id = str(item.get("id", number))
        preview_lines.extend(
            [
                f"### {number}. {scalar(item.get('label') or item_id)}",
                "",
                f"- 질문: {scalar(item.get('question'))}",
                "- 발표 전 판단: 확인 대기",
                "",
            ]
        )
        answer = answers.get(item_id, {})
        call_lines.extend(
            [
                f"### {scalar(item.get('label') or item_id)}",
                "",
                f"- 경영진 답변: {scalar(answer.get('answer'), '아직 확인되지 않았습니다.')}",
                f"- 이전 분기 대비 변화: {scalar(answer.get('change'))}",
                f"- 판단: {scalar(answer.get('assessment'))}",
                "",
            ]
        )
    return preview_lines, call_lines


def reaction_rows(results: dict[str, Any]) -> list[str]:
    reaction = results.get("market_reaction") or {}
    checkpoints = {
        str(item.get("window")): item
        for item in reaction.get("checkpoints", [])
        if isinstance(item, dict) and item.get("window")
    }
    fallback = {
        "after_hours_close": reaction.get("after_hours_change_pct"),
        "next_regular_close": reaction.get("regular_change_pct"),
    }
    windows = [
        ("release_30m", "발표 30분 후"),
        ("after_hours_close", "시간외 종료"),
        ("next_regular_close", "다음 정규장 종가"),
        ("five_day", "5거래일 후"),
    ]
    rows = []
    for key, label in windows:
        item = checkpoints.get(key, {})
        move = item.get("change_pct", fallback.get(key))
        relative = item.get("qqq_relative_pct")
        timestamp = item.get("observed_at")
        rows.append(
            f"| {label} | {pct(move)} | {pct(relative)} | {scalar(timestamp)} |"
        )
    return rows


def source_lines(item: dict[str, Any], results: dict[str, Any]) -> list[str]:
    sources: list[dict[str, Any]] = [
        {"label": "실적 일정 근거", "url": item.get("schedule_source_url")},
        {"label": "회사 IR", "url": item.get("ir_url")},
        *results.get("sources", []),
    ]
    seen = set()
    lines = []
    for source in sources:
        url = source.get("url")
        if not url or url in seen:
            continue
        seen.add(url)
        lines.append(f"- [{scalar(source.get('label') or '자료')}]({url})")
    return lines or ["- 아직 등록된 근거 자료가 없습니다."]


def build_ticker_note(
    item: dict[str, Any],
    focus: dict[str, Any],
    ticker_focus: dict[str, Any],
    stage: str,
    freeze: datetime,
) -> str:
    results = item.get("results") or {}
    preview_seed = ticker_focus.get("preview_seed") or {}
    verdict = results.get("verdict") or preview_seed.get("verdict")
    if not verdict:
        verdict = "발표 전 핵심 질문을 준비했으며 공식 결과와 콘퍼런스콜 확인 전까지 판단을 보류합니다."

    factors = (
        results.get("stock_moving_factors")
        or results.get("highlights")
        or preview_seed.get("stock_moving_factors")
        or []
    )
    next_checks = results.get("next_checks") or preview_seed.get("next_checks") or []
    thesis = results.get("thesis_update") or {}
    preview_lines, call_lines = question_sections(ticker_focus, results)

    lines = [
        f"# {item['ticker']} {item['fiscal_period']} 실적",
        "",
        f"- 상태: **{STAGE_LABELS.get(stage, stage)}**",
        f"- 발표: {item.get('event_datetime_kst') or item.get('event_date_us')} KST",
        f"- 문서 동결 시각: {freeze.strftime('%Y-%m-%d %H:%M KST')}",
        "",
        "## 30초 결론",
        "",
        scalar(verdict),
        "",
        "## 1. 발표 전 중요했던 질문",
        "",
        *preview_lines,
        "## 2. 실적 점수판",
        "",
        "| 지표 | 이전 분기 | 시장 기대 | 실제 | 차이 | 판정 |",
        "| --- | ---: | ---: | ---: | ---: | --- |",
        *scorecard_rows(results, focus, ticker_focus),
        "",
        "시장 기대치는 신뢰할 수 있는 동일 기준 비교치가 확보된 경우에만 기록합니다.",
        "",
        "## 3. 주가를 움직인 핵심 요인",
        "",
        *list_lines(factors),
        "",
        "## 4. 콘퍼런스콜 답변",
        "",
        *call_lines,
        "## 5. 시장 반응",
        "",
        "| 시점 | 종목 반응 | QQQ 대비 | 관측 시각 |",
        "| --- | ---: | ---: | --- |",
        *reaction_rows(results),
        "",
        scalar((results.get("market_reaction") or {}).get("summary"), "시장 반응은 관측 구간이 끝난 뒤 확정합니다."),
        "",
        "## 6. 투자 논리 변화",
        "",
        f"- 전체 판단: **{scalar(thesis.get('overall'))}**",
        f"- 강화된 근거: {scalar(thesis.get('strengthened'))}",
        f"- 약화된 근거: {scalar(thesis.get('weakened'))}",
        f"- 다음 반증 조건: {scalar(thesis.get('next_falsifier'))}",
        "",
        "## 7. 다음에 확인할 것",
        "",
        *list_lines(next_checks),
        "",
        "## 근거 자료",
        "",
        *source_lines(item, results),
        "",
    ]
    return "\n".join(lines).rstrip() + "\n"


def build_season_index(
    calendar: dict[str, Any],
    rows: list[dict[str, Any]],
    freeze: datetime,
) -> str:
    lines = [
        f"# {calendar['season']}",
        "",
        calendar.get("season_note", ""),
        "",
        f"- 마지막 점검: {freeze.strftime('%Y-%m-%d %H:%M KST')}",
        "- 상세 문서는 프리뷰가 준비되거나 공식 결과가 확인된 종목만 생성합니다.",
        "",
        "| 종목 | 회사 | 발표(KST) | 단계 | 문서 |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        link = f"[{row['ticker']}]({row['ticker']}.md)" if row["generated"] else row["ticker"]
        lines.append(
            f"| {link} | {scalar(row['company'])} | {scalar(row['event'])} | {STAGE_LABELS.get(row['stage'], row['stage'])} | {'열기' if row['generated'] else '준비 전'} |"
        )
    lines.extend(
        [
            "",
            "## 문서 작성 원칙",
            "",
            "- 회사별로 다른 핵심 질문을 사용합니다.",
            "- 회사·SEC·IR 사실, 시장 기대, 외부 해석과 자동화 판단을 구분합니다.",
            "- 발표 전 질문을 보존하고 결과·콜·주가 반응을 같은 문서에 누적합니다.",
            "- 신뢰할 수 있는 비교치가 없으면 beat/miss를 만들지 않습니다.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    args = parse_args()
    calendar = load_json(CALENDAR_PATH)
    focus = load_json(FOCUS_PATH)
    timezone = ZoneInfo(focus.get("timezone", "Asia/Seoul"))
    freeze = parse_freeze_time(args.as_of, timezone)
    season_dir = args.output_root.resolve() / focus["season_slug"]
    season_dir.mkdir(parents=True, exist_ok=True)
    forced = {ticker.upper() for ticker in args.force_ticker}

    rows = []
    generated = []
    for item in sorted(
        calendar["tickers"], key=lambda value: value.get("event_datetime_kst") or "9999"
    ):
        ticker = item["ticker"]
        ticker_focus = focus["tickers"].get(ticker, {"focus_items": []})
        event = event_time(
            item, timezone, focus.get("date_only_default_time_kst", "06:00")
        )
        stage = infer_stage(item, focus, freeze, event)
        output_path = season_dir / f"{ticker}.md"
        create = should_generate(ticker, stage, ticker_focus, output_path, forced)
        if create:
            output_path.write_text(
                build_ticker_note(item, focus, ticker_focus, stage, freeze),
                encoding="utf-8",
            )
            generated.append(ticker)
        rows.append(
            {
                "ticker": ticker,
                "company": item["company"],
                "event": item.get("event_datetime_kst") or item.get("event_date_us"),
                "stage": stage,
                "generated": create,
            }
        )

    (season_dir / "README.md").write_text(
        build_season_index(calendar, rows, freeze), encoding="utf-8"
    )
    print(f"season index: {season_dir / 'README.md'}")
    print(f"ticker notes: {', '.join(generated) if generated else 'none'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
