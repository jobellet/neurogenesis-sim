"""The README and the stage reference must not lag behind the code (static checks; nothing is imported).

- every `neurogenesis.*` module the README names exists, and every public module is named there (or listed as
  internal below);
- nothing the README's status block calls planned / in progress / not yet is already done: no roadmap task marked
  done, no registered stage, CLI command or module that exists;
- every registered stage is documented in docs/STAGES.md.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
README = (ROOT / "README.md").read_text(encoding="utf-8")
ROADMAP = (ROOT / "docs" / "ROADMAP.md").read_text(encoding="utf-8")
PKG = ROOT / "neurogenesis"

# Infrastructure modules that users reach through others; a new top-level module must be added to the README's
# "What exists today" table, or here with a reason.
INTERNAL = {
    "cli", "__main__",          # the command line, documented in the README's commands
    "params", "expressions",    # Param sources and the restricted expression evaluator, used by every stage
    "tissue", "spatial",        # the developing tissue and the cell list behind the stages
    "project",                  # Project schema and I/O, documented in docs/PROJECT_FORMAT.md
    "performance",              # CI benchmark helpers
}


def _module_exists(dotted: str) -> bool:
    path = ROOT.joinpath(*dotted.split("."))
    return path.with_suffix(".py").exists() or (path / "__init__.py").exists()


def _stages():
    return set(re.findall(r'@register_stage\("([\w-]+)"\)', "".join(
        p.read_text(encoding="utf-8") for p in PKG.rglob("*.py"))))


def _cli_commands():
    return set(re.findall(r'add_parser\("([\w-]+)"', (PKG / "cli.py").read_text(encoding="utf-8")))


def _done_tasks():
    """Roadmap task ids marked done, from status tables ('| C4 | done ...') and status lines under '**ID. ...**'."""
    done = set(re.findall(r"^\| ([A-Z]-?\d+[a-z]?) \| done\b", ROADMAP, re.M))
    for m in re.finditer(r"\*\*([A-Z]-?\d+[a-z]?)\.[^\n]*", ROADMAP):
        block = ROADMAP[m.end():].split("\n**", 1)[0][:1500]
        if re.search(r"Status:\**\s*done\b", m.group(0) + block):
            done.add(m.group(1))
    return done


def _expand(ids_text):
    """'C16–C24' or 'C16-C24' -> C16 ... C24; 'K4' -> K4."""
    out = set()
    for a, b in re.findall(r"\b([A-Z]-?\d+[a-z]?)(?:\s*[–-]\s*(?:[A-Z]-?)?(\d+))?\b", ids_text):
        if b:
            prefix, start = re.match(r"([A-Z]-?)(\d+)", a).groups()
            out |= {f"{prefix}{k}" for k in range(int(start), int(b) + 1)}
        else:
            out.add(a)
    return out


def _status_block():
    m = re.search(r"\*\*Status \([^)]*\)\.\*\*(.*?)\n\n", README, re.S)
    assert m, "the README has no '**Status (date).**' paragraph"
    return m.group(1)


def test_readme_names_existing_modules_only():
    named = set(re.findall(r"`(neurogenesis(?:\.\w+)+)`", README))
    missing = sorted(n for n in named if not _module_exists(n))
    assert not missing, f"README names modules that do not exist: {missing}"


def test_every_public_module_is_in_the_readme():
    tops = {p.stem for p in PKG.glob("*.py")} | {p.parent.name for p in PKG.glob("*/__init__.py")}
    tops -= {"__init__"} | INTERNAL
    absent = sorted(t for t in tops if not re.search(rf"neurogenesis\.{t}\b", README))
    assert not absent, (f"modules missing from the README's 'What exists today' table: {absent} "
                        "(add a row or mention, or list them as INTERNAL in this test with a reason)")


def _pending_sentences():
    sentences = re.split(r"(?<=[.;])\s+", _status_block())
    return [s for s in sentences if re.search(r"\b(planned|in progress|not yet|to do|future)\b", s, re.I)]


def test_status_block_cites_task_ids_for_open_work():
    """Open work in the status block names its roadmap tasks, so that the next test can check them."""
    untracked = [s for s in _pending_sentences() if not _expand(s)]
    assert not untracked, f"README status sentences about open work without roadmap task ids: {untracked}"


def test_status_block_does_not_call_done_work_planned():
    pending = " ".join(_pending_sentences())
    done = _done_tasks()
    stale = sorted(t for t in _expand(pending) if t in done)
    assert not stale, f"README status calls roadmap tasks planned that the roadmap marks done: {stale}"
    names = set(re.findall(r"`([\w.-]+)`", pending))
    existing = (_stages() | _cli_commands()) & names
    existing |= {n for n in names if n.startswith("neurogenesis.") and _module_exists(n)}
    assert not existing, f"README status calls existing stages / commands / modules planned: {sorted(existing)}"


def test_every_registered_stage_is_documented():
    stages_doc = (ROOT / "docs" / "STAGES.md").read_text(encoding="utf-8")
    undocumented = sorted(s for s in _stages() if f"`{s}`" not in stages_doc)
    assert not undocumented, f"stages missing from docs/STAGES.md: {undocumented}"
