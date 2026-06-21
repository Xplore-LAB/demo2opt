from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable
from xml.etree import ElementTree as ET


REPO_ROOT = Path(__file__).resolve().parents[1]
KNOWLEDGE_DIR = REPO_ROOT / "docs" / "knowledge"
RAW_BOOKS_DIR = KNOWLEDGE_DIR / "\u4e09\u672c\u4e66"
OUTPUT_DIR = KNOWLEDGE_DIR / "clean_books"

SHENLENG_PREFIX = "\u300a\u6df1\u51b7\u6280\u672f\u300b"
ISSUE_PATTERN = re.compile(
    r"\u300a\u6df1\u51b7\u6280\u672f\u300b(?P<year>\d{4})\u5e74\u7b2c(?P<issue>\d{2})\u671f\.md$"
)

BROKEN_IMAGE_PATTERN = re.compile(r"(?m)^[ \t]*!\[[^\]]*\]\([^)]+\)[ \t]*\n?")
TRAILING_SPACE_PATTERN = re.compile(r"[ \t]+\n")
MULTI_BLANK_PATTERN = re.compile(r"\n{3,}")
PAGE_ARTIFACT_PATTERN = re.compile(r"\u8def\s*\d+\s*\u8def")

ARTICLE_ANCHOR_PATTERNS = (
    re.compile(r"^\s*[\u6458\u8981]{2}[:\uff1a]?"),
    re.compile(r"^\s*\u6536\u7a3f\u65e5\u671f[:\uff1a]?"),
    re.compile(r"^\s*\u4f5c\u8005\u7b80\u4ecb[:\uff1a]?"),
)

ARTICLE_HEADER_PATTERN = re.compile(r"^\s*(?:# |\* ).+")
ARTICLE_HEADER_EXCLUDE_PATTERN = re.compile(
    r"\u6df1\u51b7\u6280\u672f|\u76ee\u5f55|\u76ee\u6b21|Contents|\u90d1\u91cd\u58f0\u660e|CIP|\u56fe\u4e66\u5728\u7248\u7f16\u76ee"
)

ISSUE_DROP_PATTERNS = (
    re.compile(r"^\s*\u56fe\u4e66\u5728\u7248\u7f16\u76ee.*$"),
    re.compile(r"^\s*\u4e2d\u56fd\u7248\u672c\u56fe\u4e66\u9986CIP.*$"),
    re.compile(r"^\s*(?:\u76ee\u5f55|\u76ee\u6b21|Contents)\s*$"),
    re.compile(r".*\u6b22\u8fce\u8ba2\u9605.*" + re.escape(SHENLENG_PREFIX) + r".*"),
    re.compile(r".*\u6b22\u8fce\u8ba2\u9605.*"),
    re.compile(r".*\u5e7f\u544a\u7d22\u5f15.*"),
    re.compile(r".*(?:\u7eed\u8ba2|\u589e\u8ba2).*"),
    re.compile(r".*\u6b22\u8fce\u6765\u7a3f.*"),
    re.compile(r".*\u6b22\u8fce\u6279\u8bc4.*"),
    re.compile(r".*\u6b22\u8fce\u5229\u7528.*"),
    re.compile(r"^\s*(?:\u8def)?\d+(?:\u8def)?\s*$"),
)

SKIP_ISSUES = {
    "\u300a\u6df1\u51b7\u6280\u672f\u300b2011\u5e74\u7b2c05\u671f.md",
    "\u300a\u6df1\u51b7\u6280\u672f\u300b2011\u5e74\u7b2c06\u671f.md",
    "\u300a\u6df1\u51b7\u6280\u672f\u300b2011\u5e74\u7b2c07\u671f.md",
}

DOCX_OUTPUTS = {
    "\u5236\u6c27\u6280\u672f\uff08\u7b2c\u4e8c\u7248\uff09.docx": "02_\u5236\u6c27\u6280\u672f\uff08\u7b2c\u4e8c\u7248\uff09_\u6e05\u7406\u7a3f.md",
    "\u65b0\u7f16\u5236\u6c27\u5de5\u95ee\u7b54.docx": "03_\u65b0\u7f16\u5236\u6c27\u5de5\u95ee\u7b54_\u6e05\u7406\u7a3f.md",
    "\u73b0\u4ee3\u7a7a\u5206\u8bbe\u5907\u6280\u672f\u4e0e\u64cd\u4f5c\u539f\u7406.docx": "04_\u73b0\u4ee3\u7a7a\u5206\u8bbe\u5907\u6280\u672f\u4e0e\u64cd\u4f5c\u539f\u7406_\u6e05\u7406\u7a3f.md",
}

BOOK_START_PATTERNS = {
    "\u5236\u6c27\u6280\u672f\uff08\u7b2c\u4e8c\u7248\uff09.docx": (
        re.compile(r"^\s*\u5185\u5bb9\u63d0\u8981\s*$"),
        re.compile(r"^\s*\u524d\s*\u8a00\s*$"),
    ),
    "\u65b0\u7f16\u5236\u6c27\u5de5\u95ee\u7b54.docx": (
        re.compile(r"^\s*1[. \u3001].*"),
    ),
    "\u73b0\u4ee3\u7a7a\u5206\u8bbe\u5907\u6280\u672f\u4e0e\u64cd\u4f5c\u539f\u7406.docx": (
        re.compile(r"^\s*\u7b2c\u4e00\u7ae0.*"),
    ),
}

BOOK_DROP_PATTERNS = {
    "\u5236\u6c27\u6280\u672f\uff08\u7b2c\u4e8c\u7248\uff09.docx": (
        re.compile(r"^\s*\u56fe\u4e66\u5728\u7248\u7f16\u76ee.*$"),
        re.compile(r"^\s*\u4e2d\u56fd\u7248\u672c\u56fe\u4e66\u9986CIP.*$"),
        re.compile(r"^\s*ISBN\b.*$"),
        re.compile(r"^\s*\u51fa\u7248\u8005.*$"),
        re.compile(r"^\s*\u5730\u5740\s+.*$"),
        re.compile(r"^\s*\u7535\u8bdd\s+.*$"),
        re.compile(r"^\s*\u8d23\u4efb\u7f16\u8f91.*$"),
        re.compile(r"^\s*\u8d23\u4efb\u6821\u5bf9.*$"),
        re.compile(r"^\s*\u8d23\u4efb\u5370\u5236.*$"),
        re.compile(r"^\s*\u7f8e\u672f\u7f16\u8f91.*$"),
        re.compile(r"^\s*\u7248\u5f0f\u8bbe\u8ba1.*$"),
        re.compile(r"^\s*\uff08\u672c\u4e66\u5982\u6709\u5370\u88c5\u8d28\u91cf\u95ee\u9898.*$"),
        re.compile(r"^\s*[IVXLCDM]+\s*$"),
    ),
    "\u65b0\u7f16\u5236\u6c27\u5de5\u95ee\u7b54.docx": (),
    "\u73b0\u4ee3\u7a7a\u5206\u8bbe\u5907\u6280\u672f\u4e0e\u64cd\u4f5c\u539f\u7406.docx": (),
}

W_NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}

RETRIEVAL_SCAFFOLD = [
    "## \u68c0\u7d22\u5bfc\u822a",
    "",
    "### \u4f7f\u7528\u8bf4\u660e",
    "\u5982\u679c\u4f60\u5728 Dify \u6216\u5176\u4ed6 RAG \u5e73\u53f0\u4e2d\u68c0\u7d22\u672c\u6587\u6863\uff0c\u5efa\u8bae\u5728\u95ee\u9898\u4e2d\u5c3d\u91cf\u540c\u65f6\u5199\u51fa\u201c\u8bbe\u5907/\u90e8\u4f4d + \u73b0\u8c61 + \u573a\u666f\u201d\uff0c\u4f8b\u5982\uff1a\u201c\u4e3b\u6362\u70ed\u5668\u51b7\u635f\u504f\u5927\u600e\u4e48\u6392\u67e5\u201d\u3001\u201c\u5206\u5b50\u7b5b\u518d\u751f\u4e0d\u5145\u5206\u6709\u54ea\u4e9b\u8868\u73b0\u201d\u3002",
    "",
    "### \u4e13\u9898\u5bfc\u822a",
    "- \u7a7a\u5206\u6d41\u7a0b\uff1a\u7a7a\u5206\u8bbe\u5907\uff0c\u5236\u6c27\uff0c\u5236\u6c2e\uff0c\u5236\u6c29\uff0c\u5185\u538b\u7f29\u6d41\u7a0b\uff0c\u5916\u538b\u7f29\u6d41\u7a0b\uff0c\u5168\u4f4e\u538b\u6d41\u7a0b\uff0c\u7cbe\u998f\uff0c\u4e0b\u5854\uff0c\u4e0a\u5854\uff0c\u4e3b\u51b7\uff0c\u6db2\u7a7a\uff0c\u6db2\u6c27\uff0c\u6db2\u6c2e\uff0c\u6db2\u6c29",
    "- \u6838\u5fc3\u8bbe\u5907\uff1a\u4e3b\u6362\u70ed\u5668\uff0c\u677f\u7fc5\u5f0f\u6362\u70ed\u5668\uff0c\u900f\u5e73\u81a8\u80c0\u673a\uff0c\u589e\u538b\u673a\uff0c\u6c27\u538b\u673a\uff0c\u6db2\u6c27\u6cf5\uff0c\u6db2\u6c2e\u6cf5\uff0c\u51b7\u5374\u5854\uff0c\u5206\u5b50\u7b5b\uff0c\u5438\u9644\u5668\uff0c\u7cbe\u998f\u5854",
    "- \u5f00\u8f66\u4e0e\u8fd0\u884c\uff1a\u51b7\u5f00\u8f66\uff0c\u79ef\u6db2\uff0c\u8c03\u7eaf\uff0c\u52a0\u6e29\uff0c\u89e3\u51bb\uff0c\u5207\u6362\uff0c\u518d\u751f\uff0c\u505c\u8f66\uff0c\u590d\u4ea7\uff0c\u53d8\u8d1f\u8377\uff0c\u8c03\u8bd5",
    "- \u6545\u969c\u4e0e\u5b89\u5168\uff1a\u51b0\u5835\uff0c\u5806\u5805\uff0c\u5835\u585e\uff0c\u632f\u52a8\uff0c\u51b7\u635f\uff0c\u6cc4\u6f0f\uff0c\u8df3\u505c\uff0c\u7eaf\u5ea6\u4e0d\u8db3\uff0c\u6db2\u4f4d\u6ce2\u52a8\uff0c\u8bef\u64cd\u4f5c\uff0c\u5b89\u5168\u9600\uff0c\u7206\u70b8\uff0c\u8d77\u706b",
    "- \u8282\u80fd\u4e0e\u4f18\u5316\uff1a\u80fd\u8017\uff0c\u7535\u8017\uff0c\u63d0\u53d6\u7387\uff0c\u6c27\u6c14\u6210\u672c\uff0c\u6d41\u7a0b\u4f18\u5316\uff0c\u8bbe\u5907\u6539\u9020\uff0c\u6269\u80fd\uff0c\u964d\u8017",
    "- \u4ea7\u54c1\u4e0e\u5e94\u7528\uff1a\u533b\u7528\u6c27\uff0c\u9ad8\u7eaf\u6c2e\uff0c\u6c27\u6c14\u6807\u51c6\uff0c\u7a00\u6709\u6c14\u4f53\uff0c\u6c34\u51b6\u91d1\uff0c\u5316\u5de5\uff0c\u6cb9\u7530\uff0c\u71c3\u6599",
    "",
    "### \u672f\u8bed\u522b\u540d\u8868",
    "- \u7a7a\u5206\u8bbe\u5907 = \u7a7a\u5206\u88c5\u7f6e = ASU = air separation unit",
    "- \u4e3b\u6362\u70ed\u5668 = \u4e3b\u6362 = \u4e3b\u70ed\u4ea4\u6362\u5668 = \u677f\u7fc5\u5f0f\u6362\u70ed\u5668",
    "- \u900f\u5e73\u81a8\u80c0\u673a = \u81a8\u80c0\u673a = \u900f\u5e73\u673a = \u81a8\u80c0\u900f\u5e73\u673a",
    "- \u6db2\u6c27\u6cf5 = LOX \u6cf5\uff0c\u6db2\u6c2e\u6cf5 = LIN \u6cf5\uff0c\u6db2\u7a7a = LA",
    "- \u5206\u5b50\u7b5b\u7cfb\u7edf = \u7eaf\u5316\u7cfb\u7edf = \u5438\u9644\u7cfb\u7edf = \u9884\u7eaf\u5316\u7cfb\u7edf",
    "- \u4e3b\u51b7 = \u4e3b\u51b7\u51dd\u84b8\u53d1\u5668 = \u51b7\u51dd\u84b8\u53d1\u5668",
    "- \u7eaf\u5ea6 = \u7eaf\u51c0\u5ea6\uff0c\u63d0\u53d6\u7387 = \u56de\u6536\u7387\uff0c\u80fd\u8017 = \u7535\u8017",
    "",
    "### \u5e38\u89c1\u63d0\u95ee\u5199\u6cd5",
    "- \u4e3b\u6362\u70ed\u5668\u51b7\u635f\u504f\u5927\u7684\u5e38\u89c1\u539f\u56e0\u662f\u4ec0\u4e48",
    "- \u900f\u5e73\u81a8\u80c0\u673a\u8df3\u505c\u6216\u6548\u7387\u4e0b\u964d\u600e\u4e48\u6392\u67e5",
    "- \u5206\u5b50\u7b5b\u7eaf\u5316\u7cfb\u7edf\u518d\u751f\u4e0d\u5f7b\u5e95\u4f1a\u5f15\u8d77\u4ec0\u4e48\u95ee\u9898",
    "- \u6db2\u6c27\u6cf5\u3001\u6db2\u6c2e\u6cf5\u8fdb\u53e3\u8fc7\u6ee4\u5668\u5835\u585e\u600e\u4e48\u5904\u7406",
    "- \u7a7a\u5206\u8bbe\u5907\u51b7\u5f00\u8f66\u600e\u6837\u52a0\u5feb\u79ef\u6db2\u548c\u8c03\u7eaf",
    "- \u5185\u538b\u7f29\u6d41\u7a0b\u4e0e\u5916\u538b\u7f29\u6d41\u7a0b\u7684\u533a\u522b\u662f\u4ec0\u4e48",
    "- \u533b\u7528\u6c27\u6216\u9ad8\u7eaf\u6c2e\u7eaf\u5ea6\u4e0d\u8fbe\u6807\u53ef\u80fd\u662f\u54ea\u4e9b\u73af\u8282\u5bfc\u81f4",
    "- \u7a7a\u5206\u8bbe\u5907\u600e\u6837\u505a\u8282\u80fd\u964d\u8017\u548c\u6269\u80fd\u6539\u9020",
    "",
]


@dataclass(frozen=True)
class IssueFile:
    path: Path
    year: int
    issue: int


def normalize_text(text: str) -> str:
    cleaned = text.replace("\ufeff", "")
    cleaned = cleaned.replace("\x00", "")
    cleaned = cleaned.replace("\r\n", "\n").replace("\r", "\n")
    cleaned = PAGE_ARTIFACT_PATTERN.sub("", cleaned)
    cleaned = BROKEN_IMAGE_PATTERN.sub("", cleaned)
    cleaned = TRAILING_SPACE_PATTERN.sub("\n", cleaned)
    cleaned = MULTI_BLANK_PATTERN.sub("\n\n", cleaned)
    return cleaned.strip() + "\n"


def normalize_lines(lines: Iterable[str]) -> list[str]:
    text = normalize_text("\n".join(lines))
    return text.splitlines()


def line_matches_any(line: str, patterns: Iterable[re.Pattern[str]]) -> bool:
    return any(pattern.search(line) for pattern in patterns)


def find_issue_files() -> list[IssueFile]:
    issues: list[IssueFile] = []
    for path in KNOWLEDGE_DIR.glob(f"{SHENLENG_PREFIX}*.md"):
        match = ISSUE_PATTERN.match(path.name)
        if not match:
            continue
        issues.append(
            IssueFile(
                path=path,
                year=int(match.group("year")),
                issue=int(match.group("issue")),
            )
        )
    issues.sort(key=lambda item: (item.year, item.issue))
    return issues


def find_first_anchor(lines: list[str]) -> int | None:
    for index, line in enumerate(lines):
        if line_matches_any(line, ARTICLE_ANCHOR_PATTERNS):
            return index
    return None


def find_issue_start(lines: list[str]) -> int:
    anchor_index = find_first_anchor(lines)
    if anchor_index is None:
        return 0

    search_start = max(0, anchor_index - 20)
    candidate: int | None = None
    for index in range(search_start, anchor_index):
        line = lines[index].strip()
        if not line:
            continue
        if not ARTICLE_HEADER_PATTERN.search(line):
            continue
        if ARTICLE_HEADER_EXCLUDE_PATTERN.search(line):
            continue
        if candidate is None:
            candidate = index
            break

    if candidate is not None:
        return candidate
    return max(0, anchor_index - 8)


def clean_issue_lines(lines: list[str]) -> list[str]:
    start = find_issue_start(lines)
    trimmed = lines[start:]
    filtered: list[str] = []
    for line in trimmed:
        if line_matches_any(line, ISSUE_DROP_PATTERNS):
            continue
        filtered.append(line)
    return normalize_lines(filtered)


def merge_shenleng_book(issue_files: Iterable[IssueFile]) -> str:
    kept: list[IssueFile] = []
    skipped: list[str] = []
    for issue_file in issue_files:
        if issue_file.path.name in SKIP_ISSUES:
            skipped.append(issue_file.path.name)
            continue
        kept.append(issue_file)

    parts: list[str] = [
        "# \u6df1\u51b7\u6280\u672f\u5408\u7f16\u6e05\u7406\u7a3f\uff081994-2017\uff09",
        "",
        f"\u6784\u5efa\u65f6\u95f4\uff1a{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "\u8bf4\u660e\uff1a\u672c\u6587\u4ef6\u7531\u300a\u6df1\u51b7\u6280\u672f\u300b\u671f\u520a Markdown \u5408\u5e76\u751f\u6210\uff0c\u5df2\u53bb\u9664\u5931\u6548\u56fe\u7247\u5f15\u7528\u3001NUL \u5b57\u8282\uff0c\u5e76\u5c3d\u91cf\u5254\u9664\u5c01\u9762\u3001CIP\u3001\u76ee\u5f55\u4e0e\u8ba2\u9605\u5e7f\u544a\u7b49\u68c0\u7d22\u566a\u58f0\u3002",
    ]
    if skipped:
        parts.append("\u5254\u9664\u7684\u5f02\u5e38\u5377\u518c\uff1a" + "\u3001".join(skipped))
    parts.append("")
    parts.extend(RETRIEVAL_SCAFFOLD)

    current_year: int | None = None
    for issue_file in kept:
        if issue_file.year != current_year:
            current_year = issue_file.year
            parts.append(f"## {issue_file.year}\u5e74")
            parts.append("")

        raw_text = issue_file.path.read_text(encoding="utf-8", errors="replace")
        cleaned_lines = clean_issue_lines(normalize_text(raw_text).splitlines())

        parts.append(f"### \u7b2c{issue_file.issue:02d}\u671f")
        parts.append(f"\u539f\u59cb\u6587\u4ef6\uff1a{issue_file.path.name}")
        parts.append("")
        parts.extend(cleaned_lines)
        parts.append("")

    return normalize_text("\n".join(parts))


def extract_docx_blocks(docx_path: Path) -> list[str]:
    with zipfile.ZipFile(docx_path) as archive:
        document_xml = archive.read("word/document.xml")

    root = ET.fromstring(document_xml)
    body = root.find("w:body", W_NS)
    if body is None:
        return []

    blocks: list[str] = []
    for child in body:
        tag = child.tag.rsplit("}", 1)[-1]
        if tag == "p":
            paragraph = paragraph_text(child).strip()
            if paragraph:
                blocks.append(paragraph)
        elif tag == "tbl":
            blocks.extend(table_text(child))
    return blocks


def paragraph_text(node: ET.Element) -> str:
    fragments: list[str] = []
    for item in node.iter():
        tag = item.tag.rsplit("}", 1)[-1]
        if tag == "t":
            fragments.append(item.text or "")
        elif tag == "tab":
            fragments.append("\t")
        elif tag in {"br", "cr"}:
            fragments.append("\n")
    text = "".join(fragments)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{2,}", "\n", text)
    return text.strip()


def table_text(node: ET.Element) -> list[str]:
    rows: list[str] = []
    for row in node.findall("w:tr", W_NS):
        cells: list[str] = []
        for cell in row.findall("w:tc", W_NS):
            paragraphs = [paragraph_text(paragraph) for paragraph in cell.findall("w:p", W_NS)]
            cell_text = " ".join(part for part in paragraphs if part).strip()
            cells.append(cell_text)
        if any(cell.strip() for cell in cells):
            rows.append("| " + " | ".join(cells) + " |")
    return rows


def find_book_start(blocks: list[str], docx_name: str) -> int:
    patterns = BOOK_START_PATTERNS.get(docx_name, ())
    for index, block in enumerate(blocks):
        if line_matches_any(block, patterns):
            return index
    return 0


def clean_book_blocks(blocks: list[str], docx_name: str) -> list[str]:
    if docx_name == "\u5236\u6c27\u6280\u672f\uff08\u7b2c\u4e8c\u7248\uff09.docx":
        return clean_oxygen_technology_blocks(blocks)

    start = find_book_start(blocks, docx_name)
    trimmed = blocks[start:]
    drop_patterns = BOOK_DROP_PATTERNS.get(docx_name, ())

    filtered: list[str] = []
    for block in trimmed:
        if line_matches_any(block, drop_patterns):
            continue
        filtered.append(block)
    return normalize_lines(filtered)


def first_index(blocks: list[str], patterns: Iterable[re.Pattern[str]], start: int = 0) -> int | None:
    for index in range(start, len(blocks)):
        if line_matches_any(blocks[index], patterns):
            return index
    return None


def clean_oxygen_technology_blocks(blocks: list[str]) -> list[str]:
    summary_idx = first_index(
        blocks,
        (re.compile(r"^\s*\u5185\u5bb9\u63d0\u8981\s*$"),),
    )
    preface_idx = first_index(
        blocks,
        (re.compile(r"^\s*\u524d\s*\u8a00\s*$"),),
        start=summary_idx or 0,
    )
    body_idx = find_oxygen_body_start(blocks, preface_idx or 0)

    kept: list[str] = []
    if summary_idx is not None:
        kept.extend(blocks[summary_idx : min(summary_idx + 3, len(blocks))])
    if preface_idx is not None and body_idx is not None and body_idx > preface_idx:
        kept.extend(blocks[preface_idx:body_idx])
    if body_idx is not None:
        kept.extend(blocks[body_idx:])
    elif preface_idx is not None:
        kept.extend(blocks[preface_idx:])
    elif summary_idx is not None:
        kept.extend(blocks[summary_idx:])
    else:
        kept.extend(blocks)

    filtered: list[str] = []
    toc_mode = False
    for block in kept:
        if line_matches_any(block, BOOK_DROP_PATTERNS["\u5236\u6c27\u6280\u672f\uff08\u7b2c\u4e8c\u7248\uff09.docx"]):
            continue
        if re.fullmatch(r"\s*\u76ee\s*\u5f55\s*", block):
            toc_mode = True
            continue
        if toc_mode:
            if re.match(r"^\s*(?:\u7eea\s*\u8bba|\u7b2c[\u4e00\u4e8c\u4e09\u56db\u4e94\u516d\u4e03\u516b\u4e5d\u5341]+[\u7ae0\u8282]|1\s+\u6c14\u4f53)", block):
                toc_mode = False
            else:
                continue
        filtered.append(block)
    return normalize_lines(filtered)


def compact_text(text: str) -> str:
    return re.sub(r"\s+", "", text)


def looks_like_toc_entry(block: str) -> bool:
    compact = compact_text(block)
    if not compact:
        return False
    if re.fullmatch(r"\d+", compact):
        return True
    if len(compact) <= 48 and re.search(r"\d+$", compact):
        return True
    if len(compact) <= 24 and re.match(r"^(?:\u7eea\u8bba|\d+(?:\.\d+)*|\u7b2c[\u4e00\u4e8c\u4e09\u56db\u4e94\u516d\u4e03\u516b\u4e5d\u5341]+[\u7ae0\u8282])", compact):
        return True
    return False


def find_oxygen_body_start(blocks: list[str], start: int) -> int | None:
    for index in range(start, len(blocks)):
        compact = compact_text(blocks[index])
        if len(compact) < 60:
            continue
        window = blocks[max(start, index - 12) : index]
        toc_hits = sum(1 for item in window if looks_like_toc_entry(item))
        if toc_hits < 5:
            continue

        for candidate in range(max(start, index - 3), index):
            if looks_like_toc_entry(blocks[candidate]) and not re.fullmatch(r"\d+", compact_text(blocks[candidate])):
                return candidate
        return index

    fallback_patterns = (
        re.compile(r"^\s*\u7eea\s*\u8bba\s*$"),
        re.compile(r"^\s*\u7b2c[\u4e00\u4e8c\u4e09\u56db\u4e94\u516d\u4e03\u516b\u4e5d\u5341]+[\u7ae0\u8282].*"),
        re.compile(r"^\s*1\s+\u6c14\u4f53.*"),
    )
    return first_index(blocks, fallback_patterns, start=start)


def docx_to_markdown(docx_path: Path, title: str) -> str:
    cleaned_blocks = clean_book_blocks(extract_docx_blocks(docx_path), docx_path.name)
    parts: list[str] = [
        f"# {title}",
        "",
        f"\u6784\u5efa\u65f6\u95f4\uff1a{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"\u539f\u59cb\u6587\u4ef6\uff1a{docx_path.name}",
        "\u8bf4\u660e\uff1a\u672c\u6587\u4ef6\u7531 docx \u63d0\u53d6\u4e3a Markdown\uff0c\u5e76\u5254\u9664\u4e86\u5c01\u9762\u3001CIP \u548c\u51fa\u7248\u4fe1\u606f\u7b49\u68c0\u7d22\u566a\u58f0\u3002",
        "",
    ]
    parts.extend(cleaned_blocks)
    return normalize_text("\n".join(parts))


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def build() -> list[Path]:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    written_files: list[Path] = []

    shenleng_output = OUTPUT_DIR / "01_\u6df1\u51b7\u6280\u672f\u5408\u7f16\u6e05\u7406\u7a3f_1994-2017.md"
    write_text(shenleng_output, merge_shenleng_book(find_issue_files()))
    written_files.append(shenleng_output)

    for source_name, output_name in DOCX_OUTPUTS.items():
        source_path = RAW_BOOKS_DIR / source_name
        write_text(OUTPUT_DIR / output_name, docx_to_markdown(source_path, source_path.stem))
        written_files.append(OUTPUT_DIR / output_name)

    return written_files


def main() -> None:
    print("Generated files:")
    for path in build():
        print(f"- {path}")


if __name__ == "__main__":
    main()
