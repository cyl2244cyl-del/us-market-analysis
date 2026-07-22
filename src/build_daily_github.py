from __future__ import annotations

import argparse
import re
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SOURCE_DIR = ROOT / "일일리포트"
DEFAULT_OUTPUT_DIR = ROOT / ".runtime" / "github" / "reports" / "daily"
REPORT_PATTERN = re.compile(r"^(\d{4})-(\d{2})-(\d{2})\.md$")


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
    return parser.parse_args()


def report_files() -> list[tuple[str, str, str, Path]]:
    reports: list[tuple[str, str, str, Path]] = []
    for path in SOURCE_DIR.glob("*.md"):
        match = REPORT_PATTERN.fullmatch(path.name)
        if match:
            reports.append((*match.groups(), path))
    return sorted(reports, reverse=True)


def build_index(reports: list[tuple[str, str, str, Path]]) -> str:
    lines = [
        "# 일일 시장 리포트",
        "",
        "로컬 자동화가 검증한 날짜별 시장 기록입니다. 가격 데이터베이스와 중간 차트는 로컬에 유지하고, 사람이 읽을 Markdown만 이 프로젝트에 누적합니다.",
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
    reports = report_files()
    output_dir.mkdir(parents=True, exist_ok=True)

    for year, month, _, source in reports:
        target_dir = output_dir / year / month
        target_dir.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target_dir / source.name)

    index_path = output_dir / "README.md"
    index_path.write_text(build_index(reports), encoding="utf-8")

    print(f"staged daily reports: {len(reports)}")
    print(f"index: {index_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
