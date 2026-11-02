#!/usr/bin/env python3
"""Stack the documentation into single Markdown files that an AI assistant can read in one go.

    python scripts/build_context.py --out context.md --brief-out context-brief.md [--open-prs prs.json]

- `context.md`: a generated status section (what exists, what is not done, open pull requests), the README, every
  documentation page in the order of the site (docs/index.md and its toctrees, includes resolved), and a map of the
  package (each module's first docstring line).
- `context-brief.md`: the status section, the README, core concepts, design principles, the contributor rules, the CLI
  reference and the package map: a short overview for small context windows.
Sphinx-only syntax (toctrees, figures, admonitions, roles, autodoc blocks) is turned into plain Markdown. The script
reads files only (no import of the package), so it runs anywhere. CI publishes both files next to the documentation.
"""
from __future__ import annotations

import argparse
import ast
import datetime as dt
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
FENCE = re.compile(r"^(`{3,}|~{3,})\{([\w-]+)\}\s*(.*)$")
ROLE = re.compile(r"\{(doc|ref|py:\w+|func|class|mod|meth|attr)\}`([^`]*)`")
BRIEF_PAGES = ["getting-started/concepts.md", "background/design-principles.md", "development/agents.md",
               "reference/cli.md"]


def _role(m: re.Match) -> str:
    text = m.group(2)
    label = re.match(r"(.*?)\s*<(.+)>$", text)
    if label:
        return label.group(1)
    text = text.lstrip("~")
    if m.group(1) == "doc":
        return text.split("/")[-1].replace("-", " ")
    return f"`{text.split('.')[-1] if m.group(2).startswith('~') else text}`"


def _directive_body(lines, i, fence):
    """Lines of a directive starting after line i, up to its closing fence; returns (options, body, next index)."""
    opts, body, j = {}, [], i + 1
    while j < len(lines) and re.match(r"^:[\w-]+:", lines[j]):
        k, _, v = lines[j][1:].partition(":")
        opts[k] = v.strip()
        j += 1
    while j < len(lines) and lines[j].rstrip() != fence:
        body.append(lines[j])
        j += 1
    return opts, body, j + 1


def convert(path: Path, depth: int = 0) -> str:
    """One documentation file as plain Markdown (directives converted, includes inlined, headings demoted by depth)."""
    lines = path.read_text(encoding="utf-8").splitlines()
    out, i, in_code = [], 0, None
    while i < len(lines):
        line = lines[i]
        m = FENCE.match(line)
        if in_code is None and m:
            fence, name, arg = m.group(1), m.group(2), m.group(3)
            opts, body, i = _directive_body(lines, i, fence)
            if name == "include":
                target = (path.parent / arg).resolve()
                text = convert(target, depth)
                if "start-line" in opts:
                    text = "\n".join(text.splitlines()[int(opts["start-line"]):])
                out.append(text)
            elif name == "figure":
                caption = " ".join(x.strip() for x in body if x.strip())
                out.append(f"*[Figure: {caption}]*" if caption else "")
            elif name in ("admonition", "note", "warning", "important", "tip"):
                title = arg or name.capitalize()
                text = " ".join(x.strip() for x in body if x.strip())
                out.append(f"> **{title}.** {ROLE.sub(_role, text)}")
            elif name in ("toctree", "eval-rst", "autosummary"):
                pass
            else:
                out.append(f"{fence}{name}\n" + "\n".join(body) + f"\n{fence}")
            continue
        if line.lstrip().startswith(("```", "~~~")):
            tick = line.lstrip()[:3]
            in_code = None if in_code == tick else (tick if in_code is None else in_code)
            out.append(line)
        elif in_code is None:
            if line.startswith("#") and depth:
                line = "#" * depth + line
            line = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", line)
            out.append(ROLE.sub(_role, line))
        else:
            out.append(line)
        i += 1
    return "\n".join(out).strip() + "\n"


def toctree_order(page: Path, seen=None) -> list:
    """Documentation pages in site order: a page, then the pages of its toctrees, recursively."""
    seen = seen if seen is not None else set()
    if page in seen or not page.exists():
        return []
    seen.add(page)
    order, lines, i = [page], page.read_text(encoding="utf-8").splitlines(), 0
    while i < len(lines):
        m = FENCE.match(lines[i])
        if m and m.group(2) == "toctree":
            _, body, i = _directive_body(lines, i, m.group(1))
            for entry in (x.strip() for x in body):
                if entry and not entry.startswith(":"):
                    order += toctree_order((page.parent / entry).with_suffix(".md").resolve(), seen)
            continue
        i += 1
    return order


def package_map() -> str:
    rows = []
    for f in sorted((ROOT / "neurogenesis").rglob("*.py")):
        try:
            doc = ast.get_docstring(ast.parse(f.read_text(encoding="utf-8"))) or ""
        except SyntaxError:
            doc = ""
        first = doc.strip().splitlines()[0] if doc.strip() else ""
        rows.append(f"- `{f.relative_to(ROOT)}`: {first}")
    return "\n".join(rows) + "\n"


def _git(*args) -> str:
    try:
        return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def not_done() -> list:
    """Sentences that say something is missing: roadmap status lines, 'Not implemented' and PLACEHOLDER notes."""
    items = []
    roadmap = (DOCS / "ROADMAP.md").read_text(encoding="utf-8")
    task = ""
    for para in re.split(r"\n(?=\s*(?:[-*]|\*\*|\||#|\d+\.)\s)|\n\s*\n", roadmap):
        text = " ".join(para.split())
        label = re.match(r"\*\*([A-Z]-?\d+[a-z]?)\.\s*([^*]*)", text)
        if label:
            task = f"{label.group(1)} ({label.group(2).strip().rstrip('.')})"
        if text.startswith("|") and re.search(r"\b(partial|not done|Not implemented|pending|planned)\b", text, re.I):
            items.append(("roadmap", text.strip("| ").replace(" | ", ": ")))
        elif "Status:" in text and re.search(r"Status:\**\s*(partial|not done|pending|planned)", text, re.I):
            items.append(("roadmap", f"{task}: " + text.strip("-* ").replace("Status:** ", "").replace("**Status:** ", "")))
    for f in sorted(DOCS.rglob("*.md")):
        text = f.read_text(encoding="utf-8")
        for m in re.finditer(r"```\{admonition\} PLACEHOLDER\n(?::class:[^\n]*\n)?(.*?)```", text, re.S):
            items.append((str(f.relative_to(ROOT)), " ".join(m.group(1).split())))
    stages = DOCS / "STAGES.md"
    if stages.exists():
        for m in re.finditer(r"\*\*Not implemented:\*\*\s*([^\n]*(?:\n(?!\n)[^\n]*)*)", stages.read_text(encoding="utf-8")):
            items.append(("docs/STAGES.md", "Not implemented: " + " ".join(m.group(1).split())))
    return items


def status_section(open_prs) -> str:
    tests = sum(len(re.findall(r"^def test_", f.read_text(encoding="utf-8"), re.M)) for f in (ROOT / "tests").glob("test_*.py"))
    stage_files = sorted(p.stem for p in (ROOT / "neurogenesis" / "stages").glob("*.py") if p.stem not in ("__init__", "base"))
    stages = sorted(set(re.findall(r'@register_stage\("([\w-]+)"\)', "".join(
        (ROOT / "neurogenesis" / "stages" / f"{s}.py").read_text(encoding="utf-8") for s in stage_files))))
    out = ["# 1. Project status (generated)", "",
           f"- Commit `{_git('rev-parse', '--short', 'HEAD')}` of {_git('log', '-1', '--format=%cd', '--date=short')}; "
           f"file generated {dt.date.today().isoformat()}.",
           f"- Registered developmental stages ({len(stages)}): {', '.join(f'`{s}`' for s in stages)}.",
           f"- Test functions: {tests} in `tests/`.", ""]
    if open_prs is not None:
        out += ["## Open pull requests", ""]
        out += [f"- #{p['number']} {'(draft) ' if p.get('isDraft') else ''}{p['title']} (`{p.get('headRefName', '')}`)"
                for p in open_prs] or ["- none"]
        out.append("")
    out += ["## Not done yet (collected from the roadmap, the stage reference and the PLACEHOLDER notes)", ""]
    seen = set()
    for where, text in not_done():
        key = text[:120]
        if key not in seen:
            seen.add(key)
            out.append(f"- ({where}) {ROLE.sub(_role, text)}")
    return "\n".join(out) + "\n"


HEADER = """# neurogenesis-sim: the whole documentation in one file

This file is generated by `scripts/build_context.py` from the repository's documentation, for AI assistants and
readers who want the full picture without browsing the repository. Section 1 is generated from the code and the docs
(state, open work); the rest is the documentation as published, in the order of the site. Code blocks are real
commands and APIs; claims about results are about simulations. Repository: https://github.com/jobellet/neurogenesis-sim
"""


def build(open_prs=None):
    status = status_section(open_prs)
    readme = convert(ROOT / "README.md", depth=1)
    pages = [p for p in toctree_order((DOCS / "index.md").resolve()) if p.name != "index.md" or p.parent != DOCS]
    body = [f"# Page: {p.relative_to(DOCS)}\n\n" + convert(p, depth=1) for p in pages]
    pmap = "# Package map (each module's first docstring line)\n\n" + package_map()
    full = "\n\n".join([HEADER, status, "# README\n\n" + readme, *body, pmap])
    brief_pages = [f"# Page: {b}\n\n" + convert(DOCS / b, depth=1) for b in BRIEF_PAGES if (DOCS / b).exists()]
    brief = "\n\n".join([HEADER.replace("the whole documentation in one file", "a short overview"),
                         status, "# README\n\n" + readme, *brief_pages, pmap])
    return full, brief


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default="neurogenesis-sim-context.md")
    ap.add_argument("--brief-out", default="neurogenesis-sim-brief.md")
    ap.add_argument("--open-prs", help="JSON from `gh pr list --json number,title,headRefName,isDraft`")
    args = ap.parse_args()
    prs = json.loads(Path(args.open_prs).read_text()) if args.open_prs else None
    full, brief = build(prs)
    for path, text in ((args.out, full), (args.brief_out, brief)):
        Path(path).write_text(text, encoding="utf-8")
        print(f"{path}: {len(text):,} characters (about {len(text) // 4:,} tokens)")


if __name__ == "__main__":
    main()
