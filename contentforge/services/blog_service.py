import logging
import re
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

KROKI_MERMAID_PNG = "https://kroki.io/mermaid/png"
MERMAID_BLOCK_RE = re.compile(r"```mermaid\s*\n([\s\S]*?)```", re.IGNORECASE)
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
    text = mermaid_source.strip()
    if not text:
        return False
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
                "Kroki mermaid render failed status=%s body=%s",
                r.status_code,
                (r.text or "")[:300],
            )
            return False
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(r.content)
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
