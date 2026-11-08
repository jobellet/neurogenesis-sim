"""Sphinx configuration for the neurogenesis-sim documentation (Read the Docs theme, Markdown via MyST).

Build locally:  pip install -r docs/requirements.txt && sphinx-build -b html docs docs/_build/html
"""
import os
import sys

sys.path.insert(0, os.path.abspath(".."))
os.environ.setdefault("JAX_PLATFORMS", "cpu")

project = "neurogenesis-sim"
author = "Joachim Bellet and contributors"
copyright = "2026, Joachim Bellet and contributors"
release = "0.1"

extensions = [
    "myst_parser",
    "sphinx.ext.autodoc",
    "sphinx.ext.autosummary",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
    "sphinx.ext.mathjax",
    "sphinx_copybutton",
]
myst_enable_extensions = ["colon_fence", "deflist", "dollarmath", "tasklist", "attrs_inline"]
myst_heading_anchors = 3
source_suffix = {".md": "markdown", ".rst": "restructuredtext"}
exclude_patterns = ["_build", "_scripts", "_templates", "**/__pycache__", "ROADMAP.md",
                    "EXTENDING.md", "NEURON_MODELS.md", "PROJECT_FORMAT.md", "THIRD_PARTY.md",
                    "DEVELOPMENTAL_NEUROSCIENCE_QUESTIONS.md", "STAGES.md"]
suppress_warnings = ["myst.xref_missing", "myst.header", "autosummary", "misc.highlighting_failure"]

autodoc_member_order = "bysource"
autodoc_default_options = {"members": True, "undoc-members": False, "show-inheritance": True}
autosummary_generate = False

html_theme = "sphinx_rtd_theme"
html_theme_options = {"navigation_depth": 3, "collapse_navigation": False, "style_external_links": True}
html_static_path = ["_static"]
html_css_files = ["custom.css"]
html_js_files = ["retinothalamic_carousel.js", "catalogue_search.js"]
html_title = "neurogenesis-sim documentation"
html_context = {"display_github": True, "github_user": "jobellet", "github_repo": "neurogenesis-sim",
                "github_version": "main", "conf_py_path": "/docs/"}
