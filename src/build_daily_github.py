from __future__ import annotations

import argparse
import base64
import binascii
import re
from html.parser import HTMLParser
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SOURCE_DIR = ROOT / "일일리포트"
DEFAULT_OUTPUT_DIR = ROOT / ".runtime" / "github" / "reports" / "daily"
REPORT_PATTERN = re.compile(r"^(\d{4})-(\d{2})-(\d{2})\.md$")
IMAGE_LINK_PATTERN = re.compile(r"!\[[^]]*\]\((assets/[^)]+\.png)\)")
PNG_PREFIX = "data:image/png;base64,"

CHART_SPECS = {
    "전 거래일 대비 종목별 등락률 막대그래프": (
        "DAILY_RETURN_BAR",
        "daily-return",
        "당일 종목별 등락률",
    ),
    "날짜와 종목별 종가 등락률 히트맵": (
        "HEATMAPS",
        "return-heatmap",
        "날짜별 등락률 히트맵",
    ),
    "종목별 수익률 상관계수 히트맵": (
        "HEATMAPS",
        "correlation-heatmap",
        "종목 간 수익률 상관 히트맵",
    ),
    "종목별 정규화 종가 변화 추이": (
        "PRICE_TREND",
        "normalized-price",
        "기준일 대비 정규화 종가",
    ),
    "종목별 PER 변화 추이": (
        "VALUATION_TRENDS",
        "per",
        "PER 변화 추이",
    ),
    "종목별 PBR 변화 추이": (
        "VALUATION_TRENDS",
        "pbr",
        "PBR 변화 추이",
    ),
    "종목별 PSR 변화 추이": (
        "VALUATION_TRENDS",
        "psr",
        "PSR 변화 추이",
    ),
}


class EmbeddedChartParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.images: list[tuple[str, str]] = []
        self.chart_figure_depth = 0

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        attributes = dict(attrs)
        if tag == "figure" and "chart-frame" in (attributes.get("class") or "").split():
            self.chart_figure_depth += 1
            return
        if tag != "img":
            return
        if self.chart_figure_depth == 0:
            return
        source = attributes.get("src") or ""
        alt = attributes.get("alt") or ""
        if source.startswith(PNG_PREFIX):
            self.images.append((alt, source.removeprefix(PNG_PREFIX)))

    def handle_endtag(self, tag: str) -> None:
        if tag == "figure" and self.chart_figure_depth:
            self.chart_figure_depth -= 1


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Stage daily Markdown reports for the organized GitHub project."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Local staging directory. Defaults to .runtime/github/reports/daily.",
    )
    parser.add_argument(
        "--date",
        action="append",
        default=[],
        help="Stage only this YYYY-MM-DD report. Repeat for multiple dates.",
    )
    return parser.parse_args()


def report_files() -> list[tuple[str, str, str, Path]]:
    reports: list[tuple[str, str, str, Path]] = []
    for path in SOURCE_DIR.glob("*.md"):
        match = REPORT_PATTERN.fullmatch(path.name)
        if match:
            reports.append((*match.groups(), path))
    return sorted(reports, reverse=True)


def decode_png(encoded: str, label: str) -> bytes:
    try:
        image = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as error:
        raise ValueError(f"invalid embedded PNG for {label}") from error
    if not image.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError(f"embedded image is not PNG for {label}")
    if not image.endswith(b"IEND\xaeB`\x82"):
        raise ValueError(f"embedded PNG is truncated for {label}")
    return image


def extract_charts(html_path: Path) -> dict[str, bytes]:
    parser = EmbeddedChartParser()
    parser.feed(html_path.read_text(encoding="utf-8"))
    charts: dict[str, bytes] = {}
    for alt, encoded in parser.images:
        if alt not in CHART_SPECS:
            raise ValueError(f"unexpected embedded chart in {html_path}: {alt}")
        if alt in charts:
            raise ValueError(f"duplicate embedded chart in {html_path}: {alt}")
        charts[alt] = decode_png(encoded, alt)
    missing = set(CHART_SPECS) - set(charts)
    if missing or len(charts) != len(CHART_SPECS):
        raise ValueError(
            f"{html_path}: expected 7 charts; missing {', '.join(sorted(missing)) or 'none'}"
        )
    return charts


def write_if_changed(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_bytes() == content:
        return
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_bytes(content)
    temporary.replace(path)


def stage_chart_assets(
    report_date: str, html_path: Path, target_dir: Path
) -> dict[str, list[tuple[str, str]]]:
    charts = extract_charts(html_path)
    blocks: dict[str, list[tuple[str, str]]] = {}
    asset_dir = target_dir / "assets"
    for alt, (block, slug, title) in CHART_SPECS.items():
        filename = f"{report_date}-{slug}.png"
        write_if_changed(asset_dir / filename, charts[alt])
        blocks.setdefault(block, []).append((title, filename))
    return blocks


def chart_markdown(title: str, filename: str) -> str:
    relative_path = f"assets/{filename}"
    return "\n".join(
        [
            f"### {title}",
            "",
            f"[![{title}]({relative_path})]({relative_path})",
        ]
    )


def inject_chart_links(
    markdown_text: str, blocks: dict[str, list[tuple[str, str]]]
) -> str:
    rendered = markdown_text
    for block in [
        "DAILY_RETURN_BAR",
        "HEATMAPS",
        "PRICE_TREND",
        "VALUATION_TRENDS",
    ]:
        marker = f"<!-- CHART:{block} -->"
        if rendered.count(marker) != 1:
            raise ValueError(f"expected exactly one Markdown marker: {marker}")
        replacement = "\n\n".join(
            chart_markdown(title, filename) for title, filename in blocks[block]
        )
        rendered = rendered.replace(marker, replacement)
    if "<!-- CHART:" in rendered:
        raise ValueError("unresolved chart marker remains in staged Markdown")
    return rendered.rstrip() + "\n"


def validate_staged_markdown(path: Path, report_date: str) -> None:
    markdown_text = path.read_text(encoding="utf-8")
    image_links = IMAGE_LINK_PATTERN.findall(markdown_text)
    if len(image_links) != len(CHART_SPECS) or len(set(image_links)) != len(CHART_SPECS):
        raise ValueError(f"{path}: expected 7 unique Markdown chart images")
    expected_prefix = f"assets/{report_date}-"
    for relative_path in image_links:
        if not relative_path.startswith(expected_prefix):
            raise ValueError(f"{path}: chart points to another report date: {relative_path}")
        image_path = path.parent / relative_path
        if not image_path.exists() or image_path.stat().st_size < 1024:
            raise ValueError(f"{path}: missing or invalid chart asset: {relative_path}")


def build_index(reports: list[tuple[str, str, str, Path]]) -> str:
    lines = [
        "# 일일 시장 리포트",
        "",
        "로컬 자동화가 검증한 날짜별 시장 기록입니다. 가격 데이터베이스는 로컬에 유지하고, 사람이 읽을 Markdown과 차트를 이 프로젝트에 누적합니다.",
        "",
    ]
    if reports:
        year, month, day, _ = reports[0]
        latest = f"{year}-{month}-{day}"
        lines.extend(
            [
                f"- 최근 데이터: **{latest}**",
                f"- [최신 리포트 열기]({year}/{month}/{latest}.md)",
                "",
                "## 날짜별 기록",
                "",
            ]
        )
        current_month = None
        for report_year, report_month, report_day, _ in reports:
            month_key = (report_year, report_month)
            if month_key != current_month:
                if current_month is not None:
                    lines.append("")
                lines.append(f"### {report_year}년 {int(report_month)}월")
                lines.append("")
                current_month = month_key
            date_text = f"{report_year}-{report_month}-{report_day}"
            lines.append(
                f"- [{date_text}]({report_year}/{report_month}/{date_text}.md)"
            )
    else:
        lines.append("아직 생성된 일일 리포트가 없습니다.")
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    args = parse_args()
    output_dir = args.output_dir.resolve()
    all_reports = report_files()
    requested_dates = set(args.date)
    reports = [
        report
        for report in all_reports
        if not requested_dates or "-".join(report[:3]) in requested_dates
    ]
    found_dates = {"-".join(report[:3]) for report in reports}
    missing_dates = requested_dates - found_dates
    if missing_dates:
        raise FileNotFoundError(
            f"missing source Markdown for: {', '.join(sorted(missing_dates))}"
        )
    output_dir.mkdir(parents=True, exist_ok=True)

    image_count = 0
    for year, month, day, source in reports:
        report_date = f"{year}-{month}-{day}"
        target_dir = output_dir / year / month
        target_dir.mkdir(parents=True, exist_ok=True)
        html_path = SOURCE_DIR / "reports" / year / month / f"{report_date}.html"
        if not html_path.exists():
            raise FileNotFoundError(f"missing validated HTML report: {html_path}")
        blocks = stage_chart_assets(report_date, html_path, target_dir)
        staged_markdown = inject_chart_links(
            source.read_text(encoding="utf-8"), blocks
        )
        staged_path = target_dir / source.name
        staged_path.write_text(staged_markdown, encoding="utf-8")
        validate_staged_markdown(staged_path, report_date)
        image_count += sum(len(images) for images in blocks.values())

    index_path = output_dir / "README.md"
    index_path.write_text(build_index(all_reports), encoding="utf-8")

    print(f"staged daily reports: {len(reports)}")
    print(f"staged chart images: {image_count}")
    print(f"index: {index_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
