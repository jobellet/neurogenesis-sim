"""Automated validation tests for community catalogue circuit cards (Track 3).

Every card in catalogue/ must:
1. Conform to the neurogenesis-card/1 schema (validate_card).
2. Contain valid author ORCIDs and paper DOIs.
3. Re-grow deterministically on validation seeds [1000, 1001, 1002] reproducing stored metrics.
4. Support the pull -> perturb -> grow remix loop.
"""
from __future__ import annotations

import json
from pathlib import Path
import pytest
import numpy as np

from neurogenesis.data.catalogue import (
    CARD_FORMAT,
    CardError,
    load_card,
    pull,
    validate_card,
)
from neurogenesis.data.targets import TARGETS
from neurogenesis.stages.base import run_schedule

CATALOGUE_DIR = Path(__file__).resolve().parents[1] / "catalogue"


def get_catalogue_cards():
    if not CATALOGUE_DIR.exists():
        return []
    cards = []
    seen_ids = set()
    for p in sorted(CATALOGUE_DIR.glob("*.json")):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            if isinstance(data, dict) and data.get("format") == CARD_FORMAT:
                cid = data.get("id")
                # Deduplicate if both kebab-case and snake_case files exist for same card id
                if cid not in seen_ids:
                    seen_ids.add(cid)
                    cards.append(p)
        except Exception:
            cards.append(p)
    return cards


@pytest.mark.parametrize("card_path", get_catalogue_cards())
def test_catalogue_card_schema_and_determinism(card_path):
    """Test that each catalogue card validates and deterministically reproduces recorded target metrics."""
    card = load_card(card_path)
    validate_card(card)

    assert card["format"] == CARD_FORMAT
    assert "id" in card and card["id"]
    assert "version" in card

    # Validate provenance
    authors = card["provenance"]["authors"]
    assert len(authors) > 0
    for a in authors:
        assert "name" in a and "orcid" in a

    # Validate compute cost declaration
    cost = card["compute_cost"]
    assert cost["memory_bytes"] > 0
    assert cost["ops_per_tick"] > 0
    assert isinstance(cost["verdict"], str)

    # Re-grow on validation seeds and check deterministic target metric reproduction
    val = card["validation"]
    seeds = val["seeds"]
    assert set(seeds) >= {1000, 1001, 1002}
    stored_scores = val["scores"]

    project_data = card["project"]
    genome = card["genome"]
    targets = card.get("targets", [])

    for idx, s in enumerate(seeds):
        tissue = run_schedule(project_data, genome, seed=s)
        assert len(tissue.alive) > 0

        # Evaluate targets and check reproducibility against stored values
        if idx < len(stored_scores):
            expected = stored_scores[idx]
            for tgt in targets:
                metric = tgt.get("metric")
                if metric in expected:
                    if metric in TARGETS:
                        actual = TARGETS[metric](tissue, tgt)
                    elif metric == "cell_count":
                        actual = float(len(tissue.alive))
                    else:
                        continue
                    np.testing.assert_allclose(actual, expected[metric], rtol=1e-3, atol=1e-3,
                                               err_msg=f"Seed {s} metric {metric} diverged")


@pytest.mark.parametrize("card_path", get_catalogue_cards())
def test_catalogue_card_remix_loop(card_path):
    """Test the one-line loader pull() and remix loop on each catalogue card."""
    card = load_card(card_path)
    proj = pull(card["id"])

    assert proj.metadata.get("card") == card["id"]
    assert proj.version == "1.2.0"

    # Perturb genome
    if "drugs" in proj.genome and isinstance(proj.genome["drugs"], dict):
        orig_dose = proj.genome["drugs"].get("dose", 1.0)
        proj.genome["drugs"]["dose"] = orig_dose * 2.0
    else:
        proj.genome["drug_dose"] = 2.5

    # Re-grow perturbed tissue
    tissue = run_schedule(proj.to_dict(), proj.genome, seed=1000)
    assert len(tissue.alive) > 0


def test_catalogue_markdown_and_html_cards():
    """Verify that catalogue cards are formatted without indentation issues and that built HTML renders all 6 cards."""
    cat_md = Path(__file__).resolve().parents[1] / "docs" / "catalogue.md"
    assert cat_md.exists()
    content = cat_md.read_text(encoding="utf-8")

    # Verify no raw unescaped LaTeX math inside HTML
    assert "$R \\ge 0.65$" not in content
    assert "$\\sigma \\approx 1.0$" not in content
    assert "<i>R</i> &ge; 0.65" in content
    assert "&sigma; &approx; 1.0" in content

    # Verify 3D viewer links across cards point to viewer/index.html?preset=...
    assert "_static/viewer/index.html?preset=microcircuit_100" in content
    assert "_static/viewer/index.html?preset=column_unsaturated_500" in content
    assert "_static/viewer/index.html?preset=cortical_column_1000" in content
    assert "_static/viewer/index.html?preset=test_column_500" in content
    assert "_static/viewer/index.html?preset=layered_sheets_600" in content

    # If Sphinx build artifact exists, verify rendered HTML structure
    built_html = Path(__file__).resolve().parents[1] / "docs" / "_build" / "html" / "catalogue.html"
    if built_html.exists():
        html_text = built_html.read_text(encoding="utf-8")
        # Ensure cards are not swallowed inside <pre><code>
        assert "&lt;div class=&quot;catalogue-card&quot;" not in html_text
        assert "&lt;!-- Card 2:" not in html_text
        # Ensure all 6 catalogue-card DOM elements are present
        card_count = html_text.count('class="catalogue-card"')
        assert card_count == 6, f"Expected 6 catalogue-card elements in catalogue.html, found {card_count}"


def test_viewer_static_redirect_and_bundle():
    """Verify that docs/_static/viewer.html redirect shim exists and forwards query params to viewer/index.html."""
    repo_root = Path(__file__).resolve().parents[1]
    viewer_html = repo_root / "docs" / "_static" / "viewer.html"
    assert viewer_html.exists(), "docs/_static/viewer.html redirect shim must exist"
    viewer_content = viewer_html.read_text(encoding="utf-8")
    assert "viewer/index.html" in viewer_content
    assert "window.location.search" in viewer_content

    viewer_index = repo_root / "docs" / "_static" / "viewer" / "index.html"
    assert viewer_index.exists(), "docs/_static/viewer/index.html must exist"

    # Verify presets are chunked and present in assets
    assets_dir = repo_root / "docs" / "_static" / "viewer" / "assets"
    assert assets_dir.exists()
    preset_chunks = list(assets_dir.glob("microcircuit_100-*.js"))
    assert len(preset_chunks) > 0, "microcircuit_100 chunk must be present in viewer/assets"

