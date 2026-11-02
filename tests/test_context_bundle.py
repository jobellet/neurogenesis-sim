"""scripts/build_context.py: the whole documentation as one Markdown file for AI assistants."""
import importlib.util
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("build_context", ROOT / "scripts" / "build_context.py")
bc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bc)


def test_bundle_is_plain_markdown_with_every_page():
    full, brief = bc.build(open_prs=[{"number": 7, "title": "A test PR", "headRefName": "x", "isDraft": True}])
    assert "```{" not in full and not bc.ROLE.search(full)                   # no Sphinx-only syntax left
    pages = [p for p in bc.toctree_order((bc.DOCS / "index.md").resolve()) if p != (bc.DOCS / "index.md").resolve()]
    assert len(pages) > 30
    for p in pages:
        assert f"# Page: {p.relative_to(bc.DOCS)}" in full
    for needed in ("# 1. Project status (generated)", "## Not done yet", "#7 (draft) A test PR", "# README",
                   "# Package map", "Stage, geometry and field reference"):
        assert needed in full
    assert len(brief) < 80_000 < len(full)                                  # the brief fits small context windows


def test_includes_and_directives_are_converted(tmp_path):
    inc = tmp_path / "inc.md"
    inc.write_text("# Included\ntext {doc}`a page <../x>`\n")
    page = tmp_path / "page.md"
    page.write_text("# Title\n```{admonition} PLACEHOLDER\n:class: placeholder\nLater.\n```\n"
                    "```{figure} img.png\n:width: 50%\n\nA caption.\n```\n```{include} inc.md\n```\n"
                    "```python\n# a comment, not a heading\n```\n")
    out = bc.convert(page, depth=1)
    assert "## Title" in out and "> **PLACEHOLDER.** Later." in out and "*[Figure: A caption.]*" in out
    assert "## Included" in out and "text a page" in out and "\n# a comment, not a heading" in out
    assert not re.search(r"```\{", out)
