import logging
import re
import unicodedata
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

KROKI_MERMAID_PNG = "https://kroki.io/mermaid/png"
# Allow ``` mermaid (space), same-line start, or strict newline after mermaid.
MERMAID_BLOCK_RE = re.compile(
    r"```\s*mermaid(?:\s*\n|\s+)([\s\S]*?)```",
    re.IGNORECASE,
)

_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"

# First meaningful line: diagram type declaration (not body lines like participant / A-->B).
_MERMAID_START_LINE = re.compile(
    r"^(flowchart|graph|sequenceDiagram|stateDiagram-v2|stateDiagram|erDiagram|"
    r"classDiagram|journey|gantt|pie|gitgraph|mindmap|timeline|block-beta|quadrantChart|"
    r"sankey-beta|treemap|requirementDiagram|C4Context|C4Container|C4Component|C4Dynamic)\b",
    re.IGNORECASE,
)

# Lines that belong to sequence diagrams but are not a top-level "sequenceDiagram" keyword.
# Avoid bare "note" / "end" — they match English prose; use specific Mermaid forms only.
_SEQUENCE_BODY_START = re.compile(
    r"^(participant|box|autonumber|title|loop|alt|opt|par|and|else|critical|break)\b|"
    r"^note\s+(left|right|over)\b|"
    r"^rect\s+rgb\b|"
    r"^end\s*$",
    re.IGNORECASE,
)


def _line_looks_like_mermaid_line(s: str) -> bool:
    sl = s.strip()
    if not sl:
        return False
    if _MERMAID_START_LINE.match(sl):
        return True
    if _SEQUENCE_BODY_START.match(sl):
        return True
    if re.match(r"^subgraph\s", sl, re.IGNORECASE):
        return True
    if re.match(r"^direction\s+(TB|BT|LR|RL)\b", sl, re.IGNORECASE):
        return True
    if "-->" in sl or "-.->" in sl or "~~~>" in sl:
        return True
    if re.search(r"\[[^\]]*\]\s*--", sl):
        return True
    if re.match(r"^[\w.]+\s*\[[^\]]+\]", sl):
        return True
    if re.match(r"^[\w.]+\s*\(\(", sl):
        return True
    if re.match(r"^[\w.]+\s*\(\[", sl):
        return True
    return False


def _line_looks_like_prose(s: str) -> bool:
    """Heuristic: markdown or sentence-like lines LLMs often paste inside mermaid fences."""
    sl = s.strip()
    if not sl:
        return False
    if _line_looks_like_mermaid_line(sl):
        return False
    if sl.startswith("#"):
        return True
    if sl.startswith("**") or sl.startswith("* ") or sl.startswith("- "):
        return True
    if re.match(r"^\*\*[^*]+\*\*\s*$", sl):
        return True
    if (
        re.match(r"^[A-Za-z].*[.!?]\s*$", sl)
        and len(sl) > 15
        and "[" not in sl
        and "-->" not in sl
        and not re.match(r"^[\w.]+\s*[\[\(]", sl)
    ):
        return True
    if len(sl) > 90 and "[" not in sl and "(" not in sl and "-->" not in sl:
        return True
    return False


def _trim_to_mermaid_start(lines: list[str]) -> list[str]:
    """Drop leading prose/headings so the block starts at a diagram type or real Mermaid statement."""
    i = 0
    while i < len(lines):
        s = lines[i].strip()
        if not s or s.startswith("%%"):
            i += 1
            continue
        if _MERMAID_START_LINE.match(s) or _line_looks_like_mermaid_line(s):
            return lines[i:]
        if _line_looks_like_prose(s):
            logger.info("mermaid: dropped prose line inside fence: %r", s[:100])
            i += 1
            continue
        return lines[i:]
    return []


def _infer_wrap_prefix(first_line: str) -> str:
    """When there is no explicit diagram keyword, choose sequence vs flowchart wrapper."""
    s = first_line.strip()
    if _SEQUENCE_BODY_START.match(s):
        return "sequenceDiagram"
    return "flowchart TD"


def sanitize_mermaid_source(raw: str) -> str:
    """
    Normalize LLM output so Kroki/Mermaid is more likely to parse: unicode quotes, stray fences, preamble prose.
    """
    t = unicodedata.normalize("NFKC", (raw or "").strip())
    for a, b in (
        ("\u201c", '"'),
        ("\u201d", '"'),
        ("\u2018", "'"),
        ("\u2019", "'"),
        ("\u00ab", '"'),
        ("\u00bb", '"'),
        ("\u00a0", " "),
    ):
        t = t.replace(a, b)
    for ch in ("\u200b", "\u200c", "\u200d", "\ufeff", "\u2028", "\u2029"):
        t = t.replace(ch, "")

    # Drop accidental inner markdown fences (common LLM mistake).
    lines_out: list[str] = []
    for line in t.splitlines():
        stripped = line.strip()
        if stripped.startswith("```") and "mermaid" not in stripped.lower():
            continue
        lines_out.append(line.rstrip())
    t = "\n".join(lines_out).strip()

    while t.startswith("```"):
        t = re.sub(r"^```\w*\s*", "", t, count=1).strip()
    if t.endswith("```"):
        t = t.rsplit("```", 1)[0].strip()

    lines = _trim_to_mermaid_start(t.splitlines())
    return "\n".join(lines).strip() if lines else ""


def _mermaid_first_decl_line(text: str) -> str | None:
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("%%"):
            continue
        return s
    return None
# Level-2 headings only (### is inside a section, not a split point).
_H2_HEADING_START = re.compile(r"^##\s+[^#\n].*$", re.MULTILINE)


def split_h2_sections(markdown: str) -> list[str]:
    """
    Split markdown into blocks: preamble (before first ## heading), then each ## section through the next ##.
    ### subheadings stay inside their parent ## block.
    """
    md = (markdown or "").replace("\r\n", "\n")
    if not md.strip():
        return [md]
    matches = list(_H2_HEADING_START.finditer(md))
    if not matches:
        return [md]
    parts: list[str] = []
    parts.append(md[: matches[0].start()])
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(md)
        parts.append(md[m.start() : end])
    return parts


def replace_h2_section(markdown: str, section_index: int, new_block: str) -> str:
    parts = split_h2_sections(markdown)
    if section_index < 0 or section_index >= len(parts):
        raise ValueError("section_index out of range")
    parts[section_index] = new_block.strip("\n")
    return join_h2_sections(parts)


def join_h2_sections(parts: list[str]) -> str:
    out: list[str] = []
    for p in parts:
        s = p.strip("\n")
        if s:
            out.append(s)
    return ("\n\n".join(out) + "\n") if out else ""


def section_infos_for_api(markdown: str) -> list[dict[str, str | int]]:
    blocks = split_h2_sections(markdown)
    infos: list[dict[str, str | int]] = []
    for i, block in enumerate(blocks):
        stripped = block.strip()
        first_line = stripped.split("\n", 1)[0].strip() if stripped else ""
        label = (first_line[:100] or f"Section {i}").replace("#", "").strip() or f"Section {i}"
        flat = " ".join(stripped.split())
        preview = flat[:140] + ("…" if len(flat) > 140 else "")
        infos.append({"index": i, "label": label, "preview": preview})
    return infos


def clear_blog_diagram_pngs(item_id: int, data_root: Path) -> None:
    d = data_root / "blog" / str(item_id)
    if not d.is_dir():
        return
    for f in d.glob("diagram_*.png"):
        try:
            f.unlink()
        except OSError:
            logger.warning("Could not remove %s", f)


def find_mermaid_blocks(markdown: str) -> list[str]:
    return [m.group(1).strip() for m in MERMAID_BLOCK_RE.finditer(markdown)]


def render_mermaid_to_png(mermaid_source: str, dest: Path) -> bool:
    """Render Mermaid source to PNG via Kroki (public HTTPS). Returns False on failure."""
    text = sanitize_mermaid_source(mermaid_source)
    if not text:
        return False
    first = _mermaid_first_decl_line(text)
    if first and not _MERMAID_START_LINE.match(first):
        prefix = _infer_wrap_prefix(first)
        text = f"{prefix}\n{text}"
        logger.warning(
            "mermaid: no diagram keyword on first line (got %r); wrapping with %s",
            first[:80],
            prefix,
        )

    try:
        timeout = httpx.Timeout(connect=15.0, read=90.0, write=30.0, pool=10.0)
        with httpx.Client(timeout=timeout) as client:
            r = client.post(
                KROKI_MERMAID_PNG,
                content=text.encode("utf-8"),
                headers={"Content-Type": "text/plain"},
            )
        if r.status_code != 200:
            logger.warning(
                "Kroki mermaid render failed status=%s body=%s source_head=%r",
                r.status_code,
                (r.text or "")[:400],
                text[:220],
            )
            return False
        body = r.content
        if len(body) < 32 or not body.startswith(_PNG_MAGIC):
            logger.warning(
                "Kroki returned non-PNG body (len=%s head=%r) source_head=%r",
                len(body),
                body[:40],
                text[:220],
            )
            return False
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(body)
        return True
    except httpx.HTTPError as e:
        logger.warning("Kroki request failed: %s", e)
        return False


def process_blog_markdown(
    *,
    item_id: int,
    raw_markdown: str,
    data_root: Path,
) -> tuple[str, list[str]]:
    """
    Replace ```mermaid``` blocks with ![...](diagram_N.png) when Kroki succeeds.
    Returns (updated_markdown, list of relative paths under data_root).
    """
    blocks = find_mermaid_blocks(raw_markdown)
    if not blocks:
        return raw_markdown.strip(), []

    blog_dir = data_root / "blog" / str(item_id)
    blog_dir.mkdir(parents=True, exist_ok=True)

    rendered_flags: list[bool] = []
    rel_paths: list[str] = []
    for i, code in enumerate(blocks):
        rel = f"blog/{item_id}/diagram_{i}.png"
        dest = data_root / rel
        ok = render_mermaid_to_png(code, dest)
        rendered_flags.append(ok)
        if ok:
            rel_paths.append(rel)

    out_parts: list[str] = []
    last_end = 0
    idx = 0
    for m in MERMAID_BLOCK_RE.finditer(raw_markdown):
        out_parts.append(raw_markdown[last_end : m.start()])
        if idx < len(rendered_flags) and rendered_flags[idx]:
            out_parts.append(f"![Diagram {idx + 1}](diagram_{idx}.png)")
        else:
            out_parts.append(m.group(0))
        last_end = m.end()
        idx += 1
    out_parts.append(raw_markdown[last_end:])
    return "".join(out_parts).strip(), rel_paths
