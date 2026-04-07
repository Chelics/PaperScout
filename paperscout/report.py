from __future__ import annotations

import os
import re


def write_report(content: str, output_path: str) -> None:
    output_path = os.path.abspath(output_path)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)


def _strip_arxiv_version(arxiv_id: str) -> str:
    return re.sub(r"v\d+$", "", arxiv_id)


def _extract_arxiv_id(text: str) -> str | None:
    text = text.strip()
    m = re.search(r"arxiv\.org/(?:abs|pdf)/([^)\s?#]+)", text, re.IGNORECASE)
    if m:
        raw = m.group(1)
        raw = re.sub(r"\.pdf$", "", raw, flags=re.IGNORECASE)
        return _strip_arxiv_version(raw)
    m = re.search(r"\b(\d{4}\.\d{4,5})(?:v\d+)?\b", text)
    if m:
        return m.group(1)
    m = re.search(r"\b([a-z-]+(?:\.[A-Za-z-]+)?/\d{7})(?:v\d+)?\b", text)
    if m:
        return _strip_arxiv_version(m.group(1))
    return None


def _strip_preface(lines: list[str]) -> list[str]:
    idx = None
    for i, line in enumerate(lines):
        if re.match(r"^#\s+Research Report:\s+", line):
            idx = i
            break
    if idx is None:
        while lines and not lines[0].strip():
            lines = lines[1:]
        return lines
    lines = lines[idx:]
    while lines and not lines[0].strip():
        lines = lines[1:]
    return lines


def _ensure_papers_section_strict(lines: list[str]) -> list[str]:
    if any(re.match(r"^##\s+Papers\s*$", line) for line in lines):
        return lines

    summary_idx = None
    for i, line in enumerate(lines):
        if re.match(r"^##\s+Summary\s*$", line):
            summary_idx = i
            break
    if summary_idx is None:
        return lines

    insert_idx = None
    for i in range(summary_idx + 1, len(lines)):
        line = lines[i]
        if re.match(r"^##\s+", line):
            insert_idx = i
            break
        if re.match(r"^---\s*$", line) or re.match(r"^###\s+", line) or re.match(r"^####\s+", line):
            insert_idx = i
            break
    if insert_idx is None:
        insert_idx = len(lines)

    new_lines = lines[:insert_idx]
    while new_lines and not new_lines[-1].strip():
        new_lines.pop()
    new_lines.extend(["", "## Papers", ""])
    new_lines.extend(lines[insert_idx:])
    return new_lines


def _has_evidence_marker(text: str) -> bool:
    lowered = text.lower()
    return ("证据" in text) or ("evidence" in lowered)


def _downgrade_evidence_sections_strict(lines: list[str]) -> list[str]:
    def find_section(header: str) -> tuple[int | None, int | None]:
        start = None
        for i, line in enumerate(lines):
            if re.match(rf"^##\s+{re.escape(header)}\s*$", line):
                start = i
                break
        if start is None:
            return None, None
        end = len(lines)
        for j in range(start + 1, len(lines)):
            if re.match(r"^##\s+", lines[j]):
                end = j
                break
        return start, end

    rl_start, rl_end = find_section("Field Overview & Connections")
    if rl_start is None or rl_end is None:
        rl_start, rl_end = find_section("Research Lineage")
    if rl_start is not None and rl_end is not None:
        body_lines = lines[rl_start + 1 : rl_end]
        body = "\n".join(body_lines).strip()
        if body and not _has_evidence_marker(body):
            note = "注：以下为基于标题/摘要片段的推断，未逐条标注“证据”。请谨慎使用。"
            new_body_lines: list[str] = []
            inserted = False
            for ln in body_lines:
                if not inserted and ln.strip():
                    new_body_lines.extend([note, ""])
                    inserted = True
                if ln.strip().startswith("- ") and not _has_evidence_marker(ln):
                    new_body_lines.append(ln.rstrip() + "（未标注证据）")
                else:
                    new_body_lines.append(ln)
            if not inserted:
                new_body_lines = ["", note, ""] + body_lines
            lines = lines[: rl_start + 1] + new_body_lines + lines[rl_end:]

    kt_start, kt_end = find_section("Key Themes")
    if kt_start is not None and kt_end is not None:
        body_lines = lines[kt_start + 1 : kt_end]
        bullets = [ln for ln in body_lines if ln.strip().startswith("- ")]
        if bullets:
            note = "注：以下主题为基于标题/摘要片段的归纳；未标注“证据”的条目请谨慎使用。"
            new_body_lines: list[str] = []
            inserted = False
            for ln in body_lines:
                if not inserted and ln.strip():
                    new_body_lines.extend([note, ""])
                    inserted = True
                if ln.strip().startswith("- ") and not _has_evidence_marker(ln):
                    new_body_lines.append(ln.rstrip() + "（未标注证据）")
                else:
                    new_body_lines.append(ln)
            if not inserted:
                new_body_lines = ["", note, ""] + body_lines
            lines = lines[: kt_start + 1] + new_body_lines + lines[kt_end:]

    return lines


def normalize_report_markdown(content: str, report_mode: str = "strict") -> str:
    mode = (report_mode or "strict").strip().lower()
    is_strict = mode == "strict"

    lines = _strip_preface(content.splitlines())

    out: list[str] = []
    seen_arxiv = False

    for line in lines:
        if re.match(r"^####\s+\d+\.\s+", line):
            seen_arxiv = False
            out.append(line)
            continue

        if "arxiv.org" in line:
            line = re.sub(r"https?://www\.arxiv\.org", "https://arxiv.org", line)
            line = re.sub(r"http://arxiv\.org", "https://arxiv.org", line)

        m = re.match(r"^- \*\*arXiv:\*\*\s*(.*)$", line)
        if m:
            if seen_arxiv:
                continue
            seen_arxiv = True

            rest = m.group(1).strip()
            link_match = re.match(r"^\[([^\]]+)\]\(([^)]+)\)$", rest)
            if link_match:
                arxiv_id = _extract_arxiv_id(link_match.group(1)) or _extract_arxiv_id(link_match.group(2))
            else:
                arxiv_id = _extract_arxiv_id(rest)

            if arxiv_id:
                canonical_url = f"https://arxiv.org/abs/{arxiv_id}"
                out.append(f"- **arXiv:** [{arxiv_id}]({canonical_url})")
            else:
                out.append(f"- **arXiv:** {rest}")
            continue

        m = re.match(r"^- \*\*Categories:\*\*\s*(.*)$", line)
        if m:
            raw = m.group(1).strip()
            cleaned = raw.translate(str.maketrans({"[": " ", "]": " ", "'": " ", '"': " "}))
            parts = [p.strip() for p in cleaned.split(",")]
            if len(parts) == 1:
                parts = [p.strip() for p in cleaned.split()]
            cats: list[str] = []
            seen: set[str] = set()
            for p in parts:
                if not p:
                    continue
                if p not in seen:
                    seen.add(p)
                    cats.append(p)
            out.append("- **Categories:** " + ", ".join(cats))
            continue

        out.append(line)

    if is_strict:
        out = _ensure_papers_section_strict(out)
        out = _downgrade_evidence_sections_strict(out)

    return "\n".join(out).rstrip() + "\n"


def _cite_key(paper: dict) -> str:
    authors = paper.get("authors", [])
    lastname = re.sub(r"[^a-z0-9]", "", authors[0].split()[-1].lower()) if authors else "unknown"
    year = paper.get("published", "0000")[:4]
    words = re.sub(r"[^a-z0-9 ]", "", paper.get("title", "").lower()).split()
    word = words[0] if words else "paper"
    return f"{lastname}{year}{word}"


def _arxiv_id(url: str) -> str:
    m = re.search(r"/abs/([^v/]+)", url)
    return m.group(1) if m else url


def generate_bibtex(papers: list) -> str:
    entries = []
    key_counts: dict = {}
    for paper in papers:
        base = _cite_key(paper)
        count = key_counts.get(base, 0)
        key_counts[base] = count + 1
        key = base if count == 0 else f"{base}{count}"

        authors = " and ".join(paper.get("authors", []))
        year = paper.get("published", "")[:4]
        arxiv_id = _arxiv_id(paper.get("arxiv_url", ""))
        primary = paper.get("primary_category", "")
        url = paper.get("arxiv_url", "")
        title = paper.get("title", "")
        entry = (
            f"@misc{{{key},\n"
            f"  title         = {{{title}}},\n"
            f"  author        = {{{authors}}},\n"
            f"  year          = {{{year}}},\n"
            f"  eprint        = {{{arxiv_id}}},\n"
            f"  archivePrefix = {{arXiv}},\n"
            f"  primaryClass  = {{{primary}}},\n"
            f"  url           = {{{url}}}\n"
            f"}}"
        )
        entries.append(entry)

    return "\n\n".join(entries) + "\n"


def write_bibtex(papers: list, output_path: str) -> None:
    output_path = os.path.abspath(output_path)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(generate_bibtex(papers))
