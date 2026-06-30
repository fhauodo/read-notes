#!/usr/bin/env python3
"""Generate a weekly report from public reading-note sources.

Configuration is read from READING_NOTE_SOURCES_JSON.

Example:
[
  {"name": "豆瓣公开读书笔记", "type": "html", "url": "https://www.douban.com/..."},
  {"name": "读书博客 RSS", "type": "rss", "url": "https://example.com/feed.xml"},
  {"name": "整理好的公开笔记源", "type": "json", "url": "https://example.com/notes.json"}
]
"""

from __future__ import annotations

import datetime as dt
import html
import json
import os
import re
import sys
import textwrap
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Any


OUTPUT_DIR = Path(os.getenv("READING_REPORT_DIR", "reports/reading-notes"))
MAX_ITEMS_PER_SOURCE = int(os.getenv("MAX_ITEMS_PER_SOURCE", "30"))
USER_AGENT = os.getenv(
    "READING_NOTES_USER_AGENT",
    "Mozilla/5.0 (compatible; CursorReadingNotesBot/1.0)",
)


@dataclass
class Note:
    source: str
    title: str
    content: str
    url: str = ""
    created_at: dt.date | None = None


class TextExtractor(HTMLParser):
    """Small dependency-free HTML-to-text extractor for note pages."""

    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        text = re.sub(r"\s+", " ", data).strip()
        if text:
            self.parts.append(text)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"p", "br", "li", "div", "article", "section", "h1", "h2", "h3"}:
            self.parts.append("\n")

    def text(self) -> str:
        raw = " ".join(self.parts)
        raw = html.unescape(raw)
        raw = re.sub(r"[ \t]+", " ", raw)
        raw = re.sub(r"\n\s+", "\n", raw)
        return re.sub(r"\n{3,}", "\n\n", raw).strip()


def main() -> int:
    today = dt.date.today()
    week_start = today - dt.timedelta(days=today.weekday())
    week_end = week_start + dt.timedelta(days=6)
    sources = load_sources()

    notes: list[Note] = []
    errors: list[str] = []

    for source in sources:
        try:
            notes.extend(fetch_source_notes(source, week_start, week_end))
        except Exception as exc:  # noqa: BLE001 - report should continue with other sources.
            name = source.get("name") or source.get("url") or "未命名来源"
            errors.append(f"- {name}: {exc}")

    report_path = write_report(notes, errors, week_start, week_end)
    print(f"Generated weekly reading report: {report_path}")
    return 0


def load_sources() -> list[dict[str, Any]]:
    raw = os.getenv("READING_NOTE_SOURCES_JSON", "").strip()
    if not raw:
        raise SystemExit(
            "Missing READING_NOTE_SOURCES_JSON. Configure it as a GitHub Actions variable or secret."
        )

    try:
        sources = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"READING_NOTE_SOURCES_JSON is not valid JSON: {exc}") from exc

    if not isinstance(sources, list) or not sources:
        raise SystemExit("READING_NOTE_SOURCES_JSON must be a non-empty JSON array.")

    for source in sources:
        if not isinstance(source, dict) or not source.get("url"):
            raise SystemExit("Each source must be an object with at least a url.")

    return sources


def fetch_source_notes(source: dict[str, Any], week_start: dt.date, week_end: dt.date) -> list[Note]:
    source_type = str(source.get("type", "html")).lower()
    url = str(source["url"])
    payload = request_text(url, source)

    if source_type == "json":
        notes = parse_json_notes(payload, source)
    elif source_type == "html":
        notes = parse_html_notes(payload, source)
    elif source_type == "rss":
        notes = parse_rss_notes(payload, source)
    else:
        raise ValueError(f"Unsupported source type: {source_type}")

    filtered = [
        note
        for note in notes
        if note.created_at is None or week_start <= note.created_at <= week_end
    ]
    return filtered[:MAX_ITEMS_PER_SOURCE]


def request_text(url: str, source: dict[str, Any]) -> str:
    headers = {"User-Agent": USER_AGENT}
    headers.update(source.get("headers") or {})

    cookie_env = source.get("cookieEnv")
    if cookie_env:
        cookie = os.getenv(str(cookie_env), "")
        if cookie:
            headers["Cookie"] = cookie

    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            return response.read().decode(charset, errors="replace")
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"HTTP {exc.code} when requesting {url}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Network error when requesting {url}: {exc.reason}") from exc


def parse_json_notes(payload: str, source: dict[str, Any]) -> list[Note]:
    data = json.loads(payload)
    items = data.get("notes", data) if isinstance(data, dict) else data
    if not isinstance(items, list):
        raise ValueError("JSON source must be an array or an object with a notes array.")

    notes: list[Note] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        content = first_present(item, ["content", "note", "abstract", "text", "markText"])
        if not content:
            continue
        notes.append(
            Note(
                source=str(source.get("name", "未命名来源")),
                title=first_present(item, ["title", "book", "bookName"]) or "未命名书目",
                content=clean_text(str(content)),
                url=str(item.get("url") or source.get("url") or ""),
                created_at=parse_date(first_present(item, ["created_at", "createdAt", "date", "time"])),
            )
        )
    return notes


def parse_rss_notes(payload: str, source: dict[str, Any]) -> list[Note]:
    root = ET.fromstring(payload)
    notes: list[Note] = []
    for item in root.findall(".//item"):
        title = text_from_xml(item, "title") or "未命名文章"
        content = (
            text_from_xml(item, "description")
            or text_from_xml(item, "summary")
            or text_from_xml(item, "content")
        )
        link = text_from_xml(item, "link") or str(source.get("url", ""))
        if not content:
            continue
        notes.append(
            Note(
                source=str(source.get("name", "未命名来源")),
                title=clean_text(title),
                content=clean_text(content),
                url=clean_text(link),
                created_at=parse_date(text_from_xml(item, "pubDate") or text_from_xml(item, "published")),
            )
        )
    return notes


def parse_html_notes(payload: str, source: dict[str, Any]) -> list[Note]:
    extractor = TextExtractor()
    extractor.feed(payload)
    text = extractor.text()

    title = extract_title(payload) or str(source.get("name", "网页读书笔记"))
    chunks = split_note_like_chunks(text)
    if not chunks:
        chunks = [text]

    notes: list[Note] = []
    for chunk in chunks:
        cleaned = clean_text(chunk)
        if len(cleaned) < 20:
            continue
        notes.append(
            Note(
                source=str(source.get("name", "未命名来源")),
                title=title,
                content=cleaned,
                url=str(source.get("url", "")),
                created_at=parse_date(cleaned),
            )
        )
    return notes


def text_from_xml(node: ET.Element, tag_name: str) -> str:
    for child in node.iter():
        if child.tag.split("}")[-1] == tag_name and child.text:
            return child.text.strip()
    return ""


def split_note_like_chunks(text: str) -> list[str]:
    candidates = re.split(r"(?:\n\s*){2,}|(?=《[^》]{1,80}》)", text)
    return [candidate.strip() for candidate in candidates if candidate.strip()]


def extract_title(payload: str) -> str:
    match = re.search(r"<title[^>]*>(.*?)</title>", payload, flags=re.I | re.S)
    if not match:
        return ""
    return clean_text(html.unescape(re.sub(r"<[^>]+>", "", match.group(1))))


def first_present(item: dict[str, Any], keys: list[str]) -> Any:
    for key in keys:
        value = item.get(key)
        if value:
            return value
    return None


def parse_date(value: Any) -> dt.date | None:
    if not value:
        return None
    text = str(value)
    match = re.search(r"(20\d{2})[-/.年](\d{1,2})[-/.月](\d{1,2})", text)
    if not match:
        match = re.search(r"(\d{1,2})\s+([A-Za-z]{3,})\s+(20\d{2})", text)
        if not match:
            return None
        day_text, month_text, year_text = match.groups()
        month = month_number(month_text)
        if not month:
            return None
        year, day = int(year_text), int(day_text)
        try:
            return dt.date(year, month, day)
        except ValueError:
            return None
    year, month, day = map(int, match.groups())
    try:
        return dt.date(year, month, day)
    except ValueError:
        return None


def month_number(value: str) -> int | None:
    months = {
        "jan": 1,
        "january": 1,
        "feb": 2,
        "february": 2,
        "mar": 3,
        "march": 3,
        "apr": 4,
        "april": 4,
        "may": 5,
        "jun": 6,
        "june": 6,
        "jul": 7,
        "july": 7,
        "aug": 8,
        "august": 8,
        "sep": 9,
        "sept": 9,
        "september": 9,
        "oct": 10,
        "october": 10,
        "nov": 11,
        "november": 11,
        "dec": 12,
        "december": 12,
    }
    return months.get(value.lower())


def clean_text(value: str) -> str:
    value = html.unescape(value)
    value = re.sub(r"\r\n?", "\n", value)
    value = re.sub(r"[ \t]+", " ", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()


def write_report(notes: list[Note], errors: list[str], week_start: dt.date, week_end: dt.date) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    iso_year, iso_week, _ = week_start.isocalendar()
    path = OUTPUT_DIR / f"{iso_year}-W{iso_week:02d}.md"

    grouped: dict[str, list[Note]] = {}
    for note in notes:
        grouped.setdefault(note.source, []).append(note)

    lines = [
        f"# 读书笔记周报（{week_start.isoformat()} 至 {week_end.isoformat()}）",
        "",
        "## 本周概览",
        "",
        f"- 来源数量：{len(grouped)}",
        f"- 笔记数量：{len(notes)}",
        "",
        "## 笔记汇总",
        "",
    ]

    if not notes:
        lines.extend(["本周未抓取到可汇总的读书笔记。", ""])

    for source, source_notes in grouped.items():
        lines.extend([f"### {source}", ""])
        for index, note in enumerate(source_notes, start=1):
            date_part = f"（{note.created_at.isoformat()}）" if note.created_at else ""
            lines.append(f"{index}. **{note.title}**{date_part}")
            if note.url:
                lines.append(f"   - 原文：{note.url}")
            summary = textwrap.shorten(note.content.replace("\n", " "), width=500, placeholder="...")
            lines.append(f"   - 摘要：{summary}")
            lines.append("")

    if errors:
        lines.extend(["## 抓取异常", ""])
        lines.extend(errors)
        lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8")
    return path


if __name__ == "__main__":
    sys.exit(main())
