from __future__ import annotations

import base64
import html
import io
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

import matplotlib

matplotlib.use("Agg")

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from matplotlib import font_manager
import numpy as np
import pandas as pd
import seaborn as sns


REPORT_DIR = Path(__file__).resolve().parent
BASE_DIR = REPORT_DIR.parent
DB_PATH = BASE_DIR / "nasdaq_prices.db"
OUTPUT_PATH = REPORT_DIR / "나스닥_통합_리포트.html"
DAILY_OUTPUT_DIR = REPORT_DIR / "reports"
REPORT_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}\.md$")
LINK_PATTERN = re.compile(r"\[([^]]+)\]\(([^)]+)\)")
CHART_PATTERN = re.compile(r"^<!-- CHART:([A-Z_]+) -->$")
TICKER_ORDER = ["NVDA", "AAPL", "MSFT", "GOOGL", "AMZN", "AVGO", "META", "SPCX", "MU"]
TICKER_COLORS = {
    "NVDA": "#2f6f9f",
    "AAPL": "#d08c3f",
    "MSFT": "#6f7f3f",
    "GOOGL": "#b65f78",
    "AMZN": "#5c4f8f",
    "AVGO": "#2f8c82",
    "META": "#8b5d3b",
    "SPCX": "#64748b",
    "MU": "#a85f42",
}
LINE_STYLES = ["-", "--", "-.", ":"]
MARKERS = ["o", "s", "^", "D", "v", "P", "X", "h", "*"]


BASE_CSS = """
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
  --rose: #b65f78;
  --positive-soft: #eaf2f8;
  --negative-soft: #f8efe5;
}
* { box-sizing: border-box; }
html { scroll-behavior: smooth; }
body {
  margin: 0;
  color: var(--text);
  background: var(--bg);
  font-family: -apple-system, BlinkMacSystemFont, "Apple SD Gothic Neo", "Noto Sans KR", sans-serif;
  line-height: 1.62;
  letter-spacing: 0;
  -webkit-font-smoothing: antialiased;
}
a { color: #245f96; text-underline-offset: 3px; }
code { padding: 1px 5px; border: 1px solid var(--line); border-radius: 4px; background: #f7f8fa; }
.topbar { background: #ffffff; border-top: 4px solid var(--navy); border-bottom: 1px solid var(--line); }
.topbar-inner { width: min(1240px, calc(100% - 40px)); margin: 0 auto; padding: 18px 0; display: flex; align-items: center; justify-content: space-between; gap: 18px; }
.brand { color: var(--navy); font-weight: 850; text-decoration: none; }
.topbar-links { display: flex; align-items: center; gap: 16px; }
.topbar-links a { color: #526174; font-size: .84rem; font-weight: 750; text-decoration: none; }
.topbar-meta { color: var(--muted); font-size: .86rem; }
.page { width: min(1240px, calc(100% - 40px)); margin: 0 auto; padding: 34px 0 72px; }
.report-body { padding: 4px 0 48px; counter-reset: report-section; }
.report-label { margin-bottom: 8px; color: var(--gold); font-size: .76rem; font-weight: 800; }
h1, h2, h3, h4 { color: var(--navy); letter-spacing: 0; }
h1 { margin: 0 0 12px; padding-bottom: 17px; border-bottom: 2px solid var(--navy); font-size: 2.05rem; line-height: 1.2; }
h2 { margin: 42px 0 12px; padding-top: 24px; border-top: 1px solid var(--line); font-size: 1.38rem; }
.report-body > h2 { counter-increment: report-section; display: flex; align-items: baseline; gap: 10px; }
.report-body > h2::before { content: counter(report-section, decimal-leading-zero); color: var(--gold); font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: .76rem; font-weight: 800; }
h3 { margin: 24px 0 8px; font-size: 1.08rem; }
h4 { margin: 18px 0 6px; font-size: 1rem; }
p { margin: 8px 0 14px; }
ul { padding-left: 20px; }
li { margin: 5px 0; }
.report-body > h1 + ul { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 8px; margin: 18px 0 8px; padding: 0; list-style: none; }
.report-body > h1 + ul li { margin: 0; padding: 9px 10px; border: 1px solid var(--line); border-radius: 6px; background: #f8fafb; color: #49566a; font-size: .86rem; }
.section-note { margin: 0 0 14px; color: #4f5d72; }
.caveat { margin-top: 13px; padding: 10px 12px; border-left: 3px solid var(--gold); background: #fbf7f0; color: #5c5142; font-size: .88rem; }
.kpi-strip { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; margin: 14px 0 16px; }
.kpi { min-width: 0; padding: 12px 13px; border: 1px solid var(--line); border-radius: 6px; background: #f8fafb; }
.kpi span { display: block; color: var(--muted); font-size: .78rem; }
.kpi strong { display: block; margin-top: 2px; color: var(--navy); font-size: 1.22rem; font-variant-numeric: tabular-nums; }
.chart-grid { display: grid; gap: 16px; align-items: start; }
.chart-grid.two-up { grid-template-columns: repeat(2, minmax(0, 1fr)); }
.chart-grid.three-up { grid-template-columns: repeat(3, minmax(0, 1fr)); }
.daily-overview-grid { display: grid; grid-template-columns: minmax(330px, .82fr) minmax(0, 1.18fr); gap: 16px; align-items: stretch; margin-top: 16px; }
.daily-overview-table, .daily-overview-chart { min-width: 0; }
.daily-overview-table .table-wrap { height: 100%; margin: 0; background: #fff; }
.daily-overview-table table { min-width: 0; }
.daily-overview-chart .chart-frame { display: flex; height: 100%; flex-direction: column; }
.daily-overview-chart .chart-frame img { flex: 1; min-height: 0; object-fit: contain; }
.chart-frame { min-width: 0; margin: 0; padding: 12px; border: 1px solid var(--line); border-radius: 6px; background: #ffffff; }
.chart-frame h3 { margin: 0 0 8px; font-size: .98rem; }
.chart-frame img { display: block; width: 100%; height: auto; }
.chart-frame figcaption { margin-top: 7px; color: var(--muted); font-size: .78rem; text-align: center; }
.series-legend { display: flex; flex-wrap: wrap; gap: 7px 13px; margin: 10px 0 4px; color: #475467; font-size: .78rem; }
.series-legend span { display: inline-flex; align-items: center; gap: 5px; }
.series-legend i { width: 9px; height: 9px; border-radius: 50%; display: inline-block; }
.table-wrap { overflow-x: auto; margin: 13px 0 22px; border: 1px solid var(--line); border-radius: 6px; }
table { width: 100%; border-collapse: collapse; min-width: 480px; font-variant-numeric: tabular-nums; }
th, td { padding: 9px 12px; text-align: left; border-bottom: 1px solid var(--line); }
th { color: #ffffff; background: var(--navy); font-size: .84rem; }
td { font-size: .89rem; }
tbody tr:nth-child(even) { background: #f8fafb; }
tbody tr:last-child td { border-bottom: 0; }
.movement-up { color: #245f96; font-weight: 750; }
.movement-down { color: #9a5d24; font-weight: 750; }
.report-footer { margin-top: 34px; padding-top: 16px; border-top: 1px solid var(--line); color: var(--muted); font-size: .82rem; }
.index-header { padding: 8px 0 24px; }
.index-header h1 { margin-bottom: 6px; }
.index-header p { color: var(--muted); }
.latest-link { display: inline-flex; margin-top: 8px; padding: 9px 13px; border-radius: 6px; background: var(--navy); color: #fff; font-weight: 800; text-decoration: none; }
.month-section { margin-top: 26px; }
.month-section h2 { margin: 0 0 9px; padding: 0; border: 0; }
.report-list { display: grid; gap: 8px; }
.report-link { display: grid; grid-template-columns: 130px 1fr auto; align-items: center; gap: 14px; padding: 13px 14px; border: 1px solid var(--line); border-radius: 6px; background: #fff; color: var(--text); text-decoration: none; }
.report-link:hover { border-color: #9eb5ca; background: #f9fbfd; }
.report-date { color: var(--navy); font-weight: 850; }
.report-summary { color: #4d5b70; font-size: .88rem; }
.report-arrow { color: var(--gold); font-weight: 900; }
@media (max-width: 900px) {
  .daily-overview-grid { grid-template-columns: 1fr; }
  .chart-grid.three-up { grid-template-columns: 1fr; }
  .report-body > h1 + ul, .kpi-strip { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (max-width: 720px) {
  .topbar-inner, .page { width: min(100% - 20px, 1240px); }
  .report-body { padding: 2px 0 34px; }
  h1 { font-size: 1.62rem; }
  h2 { font-size: 1.25rem; }
  .chart-grid.two-up { grid-template-columns: 1fr; }
  .report-link { grid-template-columns: 1fr auto; gap: 3px 10px; }
  .report-summary { grid-column: 1 / -1; }
}
@media (max-width: 480px) {
  .report-body > h1 + ul, .kpi-strip { grid-template-columns: 1fr; }
  .topbar-meta { display: none; }
}
@media print {
  body { background: #fff; }
  .topbar { display: none; }
  .page { width: 100%; padding: 0; }
  .report-body { padding: 0; }
  .daily-overview-grid { grid-template-columns: minmax(300px, .82fr) minmax(0, 1.18fr); }
  .chart-grid.two-up { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .chart-grid.three-up { grid-template-columns: repeat(3, minmax(0, 1fr)); }
}
"""


def configure_plot_style() -> None:
    for family in ["Apple SD Gothic Neo", "AppleGothic", "Arial Unicode MS"]:
        try:
            font_manager.findfont(family, fallback_to_default=False)
        except ValueError:
            continue
        plt.rcParams["font.family"] = family
        break
    plt.rcParams.update(
        {
            "axes.unicode_minus": False,
            "axes.edgecolor": "#98a2b3",
            "axes.labelcolor": "#344054",
            "axes.titlecolor": "#17385f",
            "axes.titlesize": 11,
            "axes.labelsize": 9,
            "xtick.color": "#667085",
            "ytick.color": "#667085",
            "xtick.labelsize": 8,
            "ytick.labelsize": 8,
            "figure.facecolor": "white",
            "axes.facecolor": "white",
            "grid.color": "#e5e9ef",
            "grid.linewidth": 0.7,
        }
    )


def load_market_data() -> pd.DataFrame:
    with sqlite3.connect(DB_PATH) as conn:
        return pd.read_sql_query(
            """
            SELECT ticker, date, close, per, pbr, psr
            FROM daily_prices
            ORDER BY date, ticker
            """,
            conn,
            parse_dates=["date"],
        )


def inline_markdown(value: str) -> str:
    parts: list[str] = []
    cursor = 0
    for match in LINK_PATTERN.finditer(value):
        parts.append(html.escape(value[cursor : match.start()]))
        label = html.escape(match.group(1))
        href = html.escape(match.group(2), quote=True)
        external = (
            ' target="_blank" rel="noopener noreferrer"'
            if href.startswith(("http://", "https://"))
            else ""
        )
        parts.append(f'<a href="{href}"{external}>{label}</a>')
        cursor = match.end()
    parts.append(html.escape(value[cursor:]))
    rendered = "".join(parts)
    rendered = re.sub(r"`([^`]+)`", r"<code>\1</code>", rendered)
    rendered = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", rendered)
    return rendered


def table_cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def movement_class(value: str) -> str:
    if re.fullmatch(r"\+\d+(?:\.\d+)?%", value):
        return "movement-up"
    if re.fullmatch(r"-\d+(?:\.\d+)?%", value):
        return "movement-down"
    return ""


def parse_markdown_table(
    lines: list[str], start: int
) -> Optional[tuple[list[str], list[list[str]], int]]:
    if start + 1 >= len(lines) or not lines[start].strip().startswith("|"):
        return None
    divider = lines[start + 1].strip()
    if not divider.startswith("|") or not all(
        re.fullmatch(r":?-{3,}:?", cell) for cell in table_cells(divider)
    ):
        return None

    headers = table_cells(lines[start].strip())
    index = start + 2
    rows: list[list[str]] = []
    while index < len(lines) and lines[index].strip().startswith("|"):
        rows.append(table_cells(lines[index]))
        index += 1
    return headers, rows, index


def render_markdown_table(headers: list[str], rows: list[list[str]]) -> str:
    rendered = ['<div class="table-wrap"><table><thead><tr>']
    rendered.extend(f"<th>{inline_markdown(cell)}</th>" for cell in headers)
    rendered.append("</tr></thead><tbody>")
    for row in rows:
        rendered.append("<tr>")
        for cell in row:
            class_name = movement_class(cell)
            class_attr = f' class="{class_name}"' if class_name else ""
            rendered.append(f"<td{class_attr}>{inline_markdown(cell)}</td>")
        rendered.append("</tr>")
    rendered.append("</tbody></table></div>")
    return "".join(rendered)


def markdown_to_html(markdown_text: str, chart_blocks: dict[str, str]) -> str:
    lines = markdown_text.splitlines()
    rendered: list[str] = []
    index = 0
    in_list = False

    def close_list() -> None:
        nonlocal in_list
        if in_list:
            rendered.append("</ul>")
            in_list = False

    while index < len(lines):
        line = lines[index].strip()
        if not line:
            close_list()
            index += 1
            continue

        chart_match = CHART_PATTERN.match(line)
        if chart_match:
            close_list()
            chart_name = chart_match.group(1)
            if chart_name == "DAILY_RETURN_BAR":
                table_index = index + 1
                while table_index < len(lines) and not lines[table_index].strip():
                    table_index += 1
                parsed_table = parse_markdown_table(lines, table_index)
                if parsed_table:
                    headers, rows, next_index = parsed_table
                    daily_table = render_markdown_table(headers, rows)
                    rendered.append(
                        chart_blocks.get(chart_name, "").replace(
                            "<!-- DAILY_TABLE_SLOT -->", daily_table
                        )
                    )
                    index = next_index
                    continue
            rendered.append(
                chart_blocks.get(chart_name, "").replace(
                    "<!-- DAILY_TABLE_SLOT -->", ""
                )
            )
            index += 1
            continue

        if line.startswith("<!--"):
            index += 1
            continue

        if line.startswith("|") and index + 1 < len(lines):
            parsed_table = parse_markdown_table(lines, index)
            if parsed_table:
                close_list()
                headers, rows, index = parsed_table
                rendered.append(render_markdown_table(headers, rows))
                continue

        heading_match = re.match(r"^(#{1,6})\s+(.+)$", line)
        if heading_match:
            close_list()
            level = len(heading_match.group(1))
            rendered.append(
                f"<h{level}>{inline_markdown(heading_match.group(2))}</h{level}>"
            )
            index += 1
            continue

        if line.startswith("- "):
            if not in_list:
                rendered.append("<ul>")
                in_list = True
            rendered.append(f"<li>{inline_markdown(line[2:])}</li>")
            index += 1
            continue

        close_list()
        rendered.append(f"<p>{inline_markdown(line)}</p>")
        index += 1

    close_list()
    return "\n".join(rendered)


def figure_data_uri(figure: plt.Figure) -> str:
    buffer = io.BytesIO()
    figure.savefig(buffer, format="png", dpi=125, bbox_inches="tight", facecolor="white")
    plt.close(figure)
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def chart_figure(title: str, data_uri: str, alt: str, caption: str) -> str:
    return (
        '<figure class="chart-frame">'
        f"<h3>{html.escape(title)}</h3>"
        f'<img src="{data_uri}" alt="{html.escape(alt, quote=True)}">'
        f"<figcaption>{html.escape(caption)}</figcaption>"
        "</figure>"
    )


def ticker_legend(tickers: list[str]) -> str:
    items = "".join(
        f'<span><i style="background:{TICKER_COLORS[ticker]}"></i>{ticker}</span>'
        for ticker in tickers
    )
    return f'<div class="series-legend" aria-label="종목 색상 범례">{items}</div>'


def plot_daily_change(change_pct: pd.Series) -> str:
    ordered = change_pct.sort_values()
    colors = ["#a87834" if value < 0 else "#2f6f9f" for value in ordered]
    figure, axis = plt.subplots(figsize=(7.0, 4.1))
    bars = axis.barh(ordered.index, ordered.values, color=colors, edgecolor="#ffffff")
    axis.axvline(0, color="#344054", linewidth=0.9)
    axis.grid(axis="x")
    axis.grid(axis="y", visible=False)
    axis.set_xlabel("전 거래일 대비 등락률 (%)")
    axis.set_ylabel("")
    max_abs = max(float(ordered.abs().max()), 1.0)
    axis.set_xlim(-max_abs * 1.3, max_abs * 1.3)
    for bar, value in zip(bars, ordered.values):
        x_pos = value + (0.06 * max_abs if value >= 0 else -0.06 * max_abs)
        axis.text(
            x_pos,
            bar.get_y() + bar.get_height() / 2,
            f"{value:+.2f}%",
            va="center",
            ha="left" if value >= 0 else "right",
            fontsize=8,
            color="#344054",
        )
    sns.despine(ax=axis, left=True)
    figure.tight_layout()
    return figure_data_uri(figure)


def plot_return_heatmap(returns_pct: pd.DataFrame) -> str:
    display = returns_pct.copy()
    display.index = display.index.strftime("%m-%d")
    max_abs = max(float(display.abs().max().max()), 1.0)
    height = min(max(3.8, 0.36 * len(display) + 1.7), 7.3)
    figure, axis = plt.subplots(figsize=(8.4, height))
    sns.heatmap(
        display,
        annot=True,
        fmt=".1f",
        cmap="coolwarm",
        center=0,
        vmin=-max_abs,
        vmax=max_abs,
        linewidths=0.35,
        cbar_kws={"label": "%", "shrink": 0.78},
        ax=axis,
    )
    axis.set_xlabel("")
    axis.set_ylabel("")
    figure.tight_layout()
    return figure_data_uri(figure)


def plot_correlation_heatmap(correlation: pd.DataFrame) -> str:
    figure, axis = plt.subplots(figsize=(6.4, 5.8))
    sns.heatmap(
        correlation,
        annot=True,
        fmt=".2f",
        cmap="coolwarm",
        vmin=-1,
        vmax=1,
        square=True,
        linewidths=0.4,
        cbar_kws={"label": "상관계수", "shrink": 0.75},
        ax=axis,
    )
    axis.set_xlabel("")
    axis.set_ylabel("")
    figure.tight_layout()
    return figure_data_uri(figure)


def style_time_axis(axis: plt.Axes) -> None:
    locator = mdates.AutoDateLocator(minticks=4, maxticks=7)
    axis.xaxis.set_major_locator(locator)
    axis.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d"))
    axis.grid(axis="y")
    axis.grid(axis="x", visible=False)
    axis.tick_params(axis="x", rotation=0)
    sns.despine(ax=axis)


def plot_time_series_lines(
    values: pd.DataFrame,
    ylabel: str,
    compact: bool = False,
    reference_value: Optional[float] = None,
    start_at_zero: bool = False,
) -> str:
    figure_size = (4.2, 3.35) if compact else (10.4, 5.1)
    figure, axis = plt.subplots(figsize=figure_size)
    tickers = [ticker for ticker in TICKER_ORDER if ticker in values.columns]
    for position, ticker in enumerate(tickers):
        series = values[ticker].dropna()
        if series.empty:
            continue
        axis.plot(
            series.index,
            series.values,
            color=TICKER_COLORS[ticker],
            linestyle=LINE_STYLES[position % len(LINE_STYLES)],
            marker=MARKERS[position % len(MARKERS)],
            markersize=2.8 if compact else 3.5,
            linewidth=1.35 if compact else 1.8,
            markevery=max(len(series) - 1, 1),
            label=ticker,
        )
    if reference_value is not None:
        axis.axhline(reference_value, color="#667085", linewidth=0.9, linestyle="--")
    if start_at_zero:
        axis.set_ylim(bottom=0)
    axis.set_ylabel(ylabel)
    axis.set_xlabel("")
    style_time_axis(axis)
    figure.tight_layout()
    return figure_data_uri(figure)


def valuation_table(latest: pd.DataFrame) -> str:
    rows = []
    for ticker in [ticker for ticker in TICKER_ORDER if ticker in latest.index]:
        row = latest.loc[ticker]
        cells = []
        for metric in ["per", "pbr", "psr"]:
            value = row.get(metric)
            cells.append("N/A" if pd.isna(value) else f"{float(value):.2f}x")
        rows.append(
            f"<tr><td><strong>{ticker}</strong></td>"
            + "".join(f"<td>{cell}</td>" for cell in cells)
            + "</tr>"
        )
    return (
        '<div class="table-wrap"><table><thead><tr>'
        "<th>종목</th><th>PER</th><th>PBR</th><th>PSR</th>"
        "</tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table></div>"
    )


def build_chart_blocks(report_date: pd.Timestamp, market_data: pd.DataFrame) -> tuple[dict[str, str], int]:
    history = market_data[market_data["date"] <= report_date].copy()
    prices = history.pivot(index="date", columns="ticker", values="close").sort_index()
    prices = prices[[ticker for ticker in TICKER_ORDER if ticker in prices.columns]]
    if len(prices) < 2:
        raise ValueError(f"{report_date.date()}: at least two trading dates are required")

    returns_pct = prices.pct_change().dropna(how="all") * 100
    change_pct = returns_pct.iloc[-1].dropna()
    correlation = returns_pct.corr()
    upper_triangle = correlation.where(np.triu(np.ones(correlation.shape), k=1).astype(bool)).stack()
    mean_correlation = float(upper_triangle.mean()) if not upper_triangle.empty else float("nan")
    breadth_up = int((change_pct > 0).sum())
    breadth_down = int((change_pct < 0).sum())
    average_change = float(change_pct.mean())
    dispersion = float(change_pct.max() - change_pct.min())
    top_ticker = str(change_pct.idxmax())
    bottom_ticker = str(change_pct.idxmin())

    kpis = (
        '<div class="kpi-strip">'
        f'<div class="kpi"><span>상승 / 하락</span><strong>{breadth_up} / {breadth_down}</strong></div>'
        f'<div class="kpi"><span>평균 등락률</span><strong>{average_change:+.2f}%</strong></div>'
        f'<div class="kpi"><span>평균 종목 상관</span><strong>{mean_correlation:.2f}</strong></div>'
        f'<div class="kpi"><span>당일 변동폭</span><strong>{dispersion:.2f}%p</strong></div>'
        "</div>"
    )
    daily_change_chart = chart_figure(
        "당일 종목별 등락률",
        plot_daily_change(change_pct),
        "전 거래일 대비 종목별 등락률 막대그래프",
        "파란색은 상승, 금색은 하락을 나타냅니다.",
    )
    daily_block = (
        kpis
        + f'<p class="section-note"><strong>{top_ticker}</strong>가 가장 강했고 '
        f'<strong>{bottom_ticker}</strong>가 가장 약했습니다. 평균값과 종목별 분산을 함께 보면 '
        "지수 방향보다 내부 확산 정도를 빠르게 확인할 수 있습니다.</p>"
        + '<div class="daily-overview-grid">'
        + '<div class="daily-overview-table"><!-- DAILY_TABLE_SLOT --></div>'
        + '<div class="daily-overview-chart">'
        + daily_change_chart
        + "</div></div>"
    )

    heatmap_block = (
        '<p class="section-note">왼쪽은 거래일별 등락률, 오른쪽은 같은 기간 종목 수익률의 상관관계입니다. '
        "상관이 높을수록 개별 종목보다 시장 공통 흐름의 영향이 컸다고 볼 수 있습니다.</p>"
        '<div class="chart-grid two-up">'
        + chart_figure(
            "날짜별 등락률",
            plot_return_heatmap(returns_pct),
            "날짜와 종목별 종가 등락률 히트맵",
            "단위: %, 파란색은 하락, 붉은색은 상승",
        )
        + chart_figure(
            "종목 간 수익률 상관",
            plot_correlation_heatmap(correlation),
            "종목별 수익률 상관계수 히트맵",
            "분석 기간 내 일간 수익률 기준",
        )
        + "</div>"
    )

    indexed_prices = prices / prices.iloc[0] * 100
    price_block = (
        '<p class="section-note">첫 거래일을 100으로 맞춰 가격대가 다른 종목도 같은 기준에서 비교했습니다. '
        "선의 높이는 절대 주가가 아니라 누적 상대 성과를 뜻합니다.</p>"
        + chart_figure(
            "기준일 대비 정규화 종가",
            plot_time_series_lines(
                indexed_prices, "첫날 = 100", reference_value=100
            ),
            "종목별 정규화 종가 변화 추이",
            f"{prices.index[0].strftime('%Y-%m-%d')} = 100",
        )
        + ticker_legend(list(indexed_prices.columns))
    )

    valuation_frames = {}
    for metric in ["per", "pbr", "psr"]:
        frame = history.pivot(index="date", columns="ticker", values=metric).sort_index()
        frame = frame[[ticker for ticker in TICKER_ORDER if ticker in frame.columns]]
        valuation_frames[metric] = frame.astype(float)

    valuation_figures = []
    for metric, label in [("per", "PER"), ("pbr", "PBR"), ("psr", "PSR")]:
        valuation_figures.append(
            chart_figure(
                f"{label} 원배수",
                plot_time_series_lines(
                    valuation_frames[metric],
                    "배수 (x)",
                    compact=True,
                    start_at_zero=True,
                ),
                f"종목별 {label} 변화 추이",
                "단위: 배수(x), 정규화하지 않은 값",
            )
        )

    latest_valuations = (
        history[history["date"] == report_date]
        .set_index("ticker")[["per", "pbr", "psr"]]
    )
    valuation_block = (
        '<p class="section-note">PER·PBR·PSR을 정규화하지 않은 원배수로 표시했습니다. '
        "패널마다 세로축 범위가 다르므로 종목 간 절대 수준은 같은 패널 안에서 비교하고, "
        "정확한 최신 값은 아래 표에서 확인할 수 있습니다.</p>"
        '<div class="chart-grid three-up">'
        + "".join(valuation_figures)
        + "</div>"
        + ticker_legend([ticker for ticker in TICKER_ORDER if ticker in latest_valuations.index])
        + "<h3>당일 밸류에이션 배수</h3>"
        + valuation_table(latest_valuations)
        + '<p class="caveat">PER은 최근 12개월 이익이 없거나 원천 데이터가 제공되지 않으면 N/A입니다. '
        "과거 PSR은 현재 TTM 매출 기준으로 과거 종가에 맞춰 역산한 값이므로 가격 변화 추이를 보는 용도이며, "
        "당시 발표 시점의 재무제표를 완전히 재현한 값은 아닙니다.</p>"
    )

    return (
        {
            "DAILY_RETURN_BAR": daily_block,
            "HEATMAPS": heatmap_block,
            "PRICE_TREND": price_block,
            "VALUATION_TRENDS": valuation_block,
        },
        7,
    )


def daily_document(report_date: str, report_html: str, generated_at: str) -> str:
    return f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="color-scheme" content="light">
  <title>미장 일일 리포트 - {report_date}</title>
  <style>{BASE_CSS}</style>
</head>
<body>
  <header class="topbar"><div class="topbar-inner">
    <a class="brand" href="../../../나스닥_통합_리포트.html">미장분석 / 일일리포트</a>
    <div class="topbar-links"><a href="../../../../실적리포트/index.html">실적 트래커</a><span class="topbar-meta">{report_date} · US EQUITIES</span></div>
  </div></header>
  <main class="page">
    <article class="report-body"><div class="report-label">US EQUITY · DAILY NOTE</div>{report_html}
      <footer class="report-footer">데이터: 로컬 SQLite <code>daily_prices</code> · 원천: yfinance · HTML 생성: {generated_at}</footer>
    </article>
  </main>
</body>
</html>
"""


def daily_summary(report_date: pd.Timestamp, market_data: pd.DataFrame) -> str:
    prices = (
        market_data[market_data["date"] <= report_date]
        .pivot(index="date", columns="ticker", values="close")
        .sort_index()
    )
    if len(prices) < 2:
        return "비교 데이터 부족"
    change = (prices.iloc[-1] / prices.iloc[-2] - 1) * 100
    up = int((change > 0).sum())
    down = int((change < 0).sum())
    strongest = str(change.idxmax())
    weakest = str(change.idxmin())
    return f"상승 {up} · 하락 {down} · 강세 {strongest} · 약세 {weakest}"


def index_document(entries: list[dict[str, str]], generated_at: str) -> str:
    grouped: dict[str, list[dict[str, str]]] = {}
    for entry in entries:
        grouped.setdefault(entry["month"], []).append(entry)

    sections = []
    for month, month_entries in grouped.items():
        links = "".join(
            '<a class="report-link" href="{href}">'
            '<span class="report-date">{date}</span>'
            '<span class="report-summary">{summary}</span>'
            '<span class="report-arrow">→</span>'
            "</a>".format(**entry)
            for entry in month_entries
        )
        year, month_number = month.split("-")
        sections.append(
            f'<section class="month-section"><h2>{year}년 {int(month_number)}월</h2>'
            f'<div class="report-list">{links}</div></section>'
        )

    latest = entries[0]
    return f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="color-scheme" content="light">
  <title>미장분석 일일리포트</title>
  <style>{BASE_CSS}</style>
</head>
<body>
  <header class="topbar"><div class="topbar-inner">
    <a class="brand" href="../index.html">미장분석 / 일일리포트</a>
    <div class="topbar-links"><a href="../실적리포트/index.html">실적 트래커</a><span class="topbar-meta">마지막 갱신 {generated_at}</span></div>
  </div></header>
  <main class="page">
    <section class="index-header">
      <h1>날짜별 시장 리포트</h1>
      <p>날짜를 선택하면 당일 등락률, 히트맵, 가격 및 밸류에이션 추이, 주요 변동 원인을 한 파일에서 확인할 수 있습니다.</p>
      <a class="latest-link" href="{latest['href']}">최신 리포트 {latest['date']} 열기</a>
    </section>
    {''.join(sections)}
  </main>
</body>
</html>
"""


def build_html() -> tuple[str, int, int]:
    configure_plot_style()
    market_data = load_market_data()
    report_paths = sorted(
        (path for path in REPORT_DIR.iterdir() if REPORT_PATTERN.fullmatch(path.name)),
        reverse=True,
    )
    if not report_paths:
        raise SystemExit("ERROR: no daily Markdown reports found")

    generated_at = datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d %H:%M KST")
    entries = []
    total_charts = 0
    for report_path in report_paths:
        report_date = pd.Timestamp(report_path.stem)
        chart_blocks, chart_count = build_chart_blocks(report_date, market_data)
        report_html = markdown_to_html(
            report_path.read_text(encoding="utf-8"), chart_blocks
        )
        output_dir = DAILY_OUTPUT_DIR / report_date.strftime("%Y") / report_date.strftime("%m")
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"{report_path.stem}.html"
        output_path.write_text(
            daily_document(report_path.stem, report_html, generated_at),
            encoding="utf-8",
        )
        entries.append(
            {
                "date": report_path.stem,
                "month": report_date.strftime("%Y-%m"),
                "href": output_path.relative_to(REPORT_DIR).as_posix(),
                "summary": daily_summary(report_date, market_data),
            }
        )
        total_charts += chart_count

    OUTPUT_PATH.write_text(index_document(entries, generated_at), encoding="utf-8")
    return str(OUTPUT_PATH), len(report_paths), total_charts


def main() -> int:
    output_path, report_count, chart_count = build_html()
    print(f"saved: {output_path}")
    print(f"reports: {report_count}; embedded charts: {chart_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
