from __future__ import annotations

import re
from dataclasses import dataclass
from io import BytesIO

from pypdf import PdfReader

SECTION_RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"^(教育经历|教育背景|教育)(education.*)?$", re.I), "教育经历"),
    (re.compile(r"^(education|educationalbackground)(教育.*)?$", re.I), "教育经历"),
    (re.compile(r"^(工作经历|工作经验|任职经历|职业经历)(workexperience|experience|employment.*)?$", re.I), "工作经历"),
    (re.compile(r"^(experience|workexperience|professionalexperience|employmenthistory)$", re.I), "工作经历"),
    (re.compile(r"^(项目经历|项目经验|项目)(projects?)?$", re.I), "项目经历"),
    (re.compile(r"^(projects?|projectexperience)$", re.I), "项目经历"),
    (re.compile(r"^(实习经历|实习)(intern.*)?$", re.I), "实习经历"),
    (re.compile(r"^(internships?)$", re.I), "实习经历"),
    (re.compile(r"^(专业技能|技能|技术栈)(skills?|tech.*)?$", re.I), "专业技能"),
    (re.compile(r"^(skills?|technicalskills|techstack)$", re.I), "专业技能"),
    (re.compile(r"^(自我评价|个人总结)(summary|profile)?$", re.I), "自我评价"),
    (re.compile(r"^(summary|profile|aboutme|selfassessment)$", re.I), "自我评价"),
    (re.compile(r"^(获奖|荣誉|证书)(awards?|honors?|cert.*)?$", re.I), "荣誉证书"),
    (re.compile(r"^(awards?|honors?|certificates?|certifications?)$", re.I), "荣誉证书"),
    (re.compile(r"^(基本信息|个人信息|个人资料)(contact|personal.*)?$", re.I), "基本信息"),
    (re.compile(r"^(contact|personalinformation|contactinfo)$", re.I), "基本信息"),
    (re.compile(r"^(校园经历|社团|学生工作)(campus|activit.*)?$", re.I), "校园经历"),
    (re.compile(r"^(campus|extracurricular|activities|leadership)$", re.I), "校园经历"),
]

# 子块：中英文标点、顿号、斜线、间隔符，以及空格/换行。
# 不按 . 切开，避免拆碎 2023.06、Node.js。
FRAGMENT_SPLIT = re.compile(r"[，。；：、！？!?;:|/\\·•●]+|\s+")
LATIN_TOKEN = re.compile(r"^[A-Za-z][A-Za-z0-9+#]*$")
LATIN_PREFIX = frozenset(
    {
        "Spring",
        "Node",
        "React",
        "Vue",
        "Next",
        "Nest",
        "Apache",
        "Google",
        "Microsoft",
        "Visual",
        "Express",
        "Fast",
        "Open",
        "Elastic",
        "SQL",
        "My",
        "Mongo",
        "Maria",
        "Redis",
        "Rabbit",
        "Kafka",
    }
)
LATIN_SUFFIX = frozenset(
    {
        "Boot",
        "Native",
        "JS",
        "Js",
        "js",
        "Studio",
        "Server",
        "OS",
        "UI",
        "API",
        "Cloud",
        "DB",
        "SQL",
        "MQ",
    }
)
LONE_MARKERS = frozenset("-—–/|·*~")
STOP_FRAGMENTS = frozenset({"与", "及", "和", "或", "的", "等", "以及"})
FALLBACK_PARENT = "正文"


class PdfExtractError(ValueError):
    pass


@dataclass
class ExtractResult:
    anchored_text: str
    layout: str
    page_count: int
    sentence_count: int
    section_count: int
    fallback_sentence_count: int
    fallback_ratio: float


def extract_anchored_text(pdf_bytes: bytes) -> str:
    return extract_resume(pdf_bytes).anchored_text


def extract_resume(pdf_bytes: bytes) -> ExtractResult:
    try:
        reader = PdfReader(BytesIO(pdf_bytes))
    except Exception as exc:
        raise PdfExtractError("PDF 无法解析，请确认文件未损坏") from exc

    pages: list[str] = []
    two_column = False
    for page in reader.pages:
        text, layout = _extract_page(page)
        pages.append(text)
        if layout == "two_column":
            two_column = True
    raw = "\n".join(pages).strip()
    if not raw:
        raise PdfExtractError("无法从 PDF 提取文本，请上传文本型 PDF（扫描件暂不支持 OCR）")

    anchored, sentence_count, section_count, fallback_count = _annotate(raw)
    ratio = (fallback_count / sentence_count) if sentence_count else 0.0
    return ExtractResult(
        anchored_text=anchored,
        layout="two_column" if two_column else "single",
        page_count=len(reader.pages),
        sentence_count=sentence_count,
        section_count=section_count,
        fallback_sentence_count=fallback_count,
        fallback_ratio=round(ratio, 4),
    )


def _text_position(cm: list[float] | tuple[float, ...], tm: list[float] | tuple[float, ...]) -> tuple[float, float]:
    x, y = float(tm[4]), float(tm[5])
    a, b, c, d, e, f = (float(v) for v in cm[:6])
    return a * x + c * y + e, b * x + d * y + f


def _collect_spans(page) -> list[tuple[float, float, str]]:
    spans: list[tuple[float, float, str]] = []

    def visitor(text: object, cm: object, tm: object, _font: object, _size: object) -> None:
        piece = str(text or "")
        if not piece.strip():
            return
        try:
            px, py = _text_position(cm, tm)  # type: ignore[arg-type]
        except (TypeError, ValueError, IndexError):
            return
        spans.append((py, px, piece))

    try:
        page.extract_text(visitor_text=visitor)
    except Exception:
        return []
    return spans


def _split_x(spans: list[tuple[float, float, str]]) -> float | None:
    xs = sorted(px for _, px, text in spans if text.strip())
    if len(xs) < 12:
        return None
    lo, hi = xs[0], xs[-1]
    width = hi - lo
    if width < 180:
        return None
    mid_lo, mid_hi = lo + width * 0.28, lo + width * 0.72
    best_gap = 0.0
    split_at = None
    for left, right in zip(xs, xs[1:]):
        if left < mid_lo or right > mid_hi:
            continue
        gap = right - left
        if gap > best_gap:
            best_gap = gap
            split_at = (left + right) / 2
    if split_at is None or best_gap < 36:
        return None
    left_chars = sum(len(text) for _, px, text in spans if px < split_at)
    right_chars = sum(len(text) for _, px, text in spans if px >= split_at)
    total = left_chars + right_chars
    if total == 0:
        return None
    if min(left_chars, right_chars) / total < 0.12:
        return None
    return split_at


def _group_lines(spans: list[tuple[float, float, str]]) -> list[str]:
    if not spans:
        return []
    ordered = sorted(spans, key=lambda item: (-round(item[0], 1), item[1]))
    lines: list[list[tuple[float, float, str]]] = []
    current: list[tuple[float, float, str]] = [ordered[0]]
    for span in ordered[1:]:
        prev_y = current[-1][0]
        if abs(span[0] - prev_y) <= 4.5:
            current.append(span)
            continue
        lines.append(current)
        current = [span]
    lines.append(current)

    result: list[str] = []
    for group in lines:
        group.sort(key=lambda item: item[1])
        parts: list[str] = []
        last_x = None
        for _y, x, text in group:
            if last_x is not None and x - last_x > 8 and parts and not parts[-1].endswith((" ", "\t")):
                parts.append(" ")
            parts.append(text)
            last_x = x
        line = _normalize_line("".join(parts))
        if line:
            result.append(line)
    return result


def _extract_page(page) -> tuple[str, str]:
    spans = _collect_spans(page)
    if not spans:
        fallback = page.extract_text() or ""
        return fallback, "single"
    split_at = _split_x(spans)
    if split_at is None:
        return "\n".join(_group_lines(spans)), "single"
    left = [span for span in spans if span[1] < split_at]
    right = [span for span in spans if span[1] >= split_at]
    lines = _group_lines(left) + _group_lines(right)
    return "\n".join(lines), "two_column"


def _normalize_line(line: str) -> str:
    return re.sub(r"\s+", " ", line).strip()


def _detect_section(line: str) -> str | None:
    compact = re.sub(r"[\s:：|·\-—_/\\]+", "", line)
    if not compact or len(compact) > 48:
        return None
    for pattern, name in SECTION_RULES:
        if pattern.match(compact):
            return name
    return None


def _split_fragments(text: str) -> list[str]:
    fragments: list[str] = []
    for part in FRAGMENT_SPLIT.split(text):
        piece = part.strip().strip(".")
        if not piece or piece in LONE_MARKERS or piece in STOP_FRAGMENTS:
            continue
        if fragments and LATIN_TOKEN.match(fragments[-1].split()[-1]) and LATIN_TOKEN.match(piece):
            prev = fragments[-1].split()[-1]
            if prev in LATIN_PREFIX or piece in LATIN_SUFFIX:
                fragments[-1] = f"{fragments[-1]} {piece}"
                continue
        if fragments and len(piece) == 1 and piece.isascii() and piece.isalnum():
            fragments[-1] += piece
            continue
        fragments.append(piece)
    return fragments


def _annotate(raw: str) -> tuple[str, int, int, int]:
    """按简历标题切父块，父块内再按标点/空白切子块。"""
    lines = [_normalize_line(line) for line in raw.splitlines() if _normalize_line(line)]
    parent = FALLBACK_PARENT
    counters: dict[str, int] = {}
    annotated: list[str] = []
    opened: set[str] = set()

    def _emit_parent(name: str) -> None:
        if name not in opened:
            annotated.append(f"\n## {name}")
            opened.add(name)

    for line in lines:
        maybe_section = _detect_section(line)
        if maybe_section:
            parent = maybe_section
            _emit_parent(parent)
            continue
        _emit_parent(parent)
        for fragment in _split_fragments(line):
            counters[parent] = counters.get(parent, 0) + 1
            n = counters[parent]
            annotated.append(f"[{parent}-{n}] {fragment}")

    text = "\n".join(line for line in annotated if line.strip()).strip()
    sentence_count = sum(1 for line in text.splitlines() if line.startswith("["))
    section_count = sum(1 for line in text.splitlines() if line.startswith("## "))
    fallback_count = sum(1 for line in text.splitlines() if line.startswith(f"[{FALLBACK_PARENT}-"))
    return text, sentence_count, section_count, fallback_count
