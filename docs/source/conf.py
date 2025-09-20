import os
import sys
from datetime import datetime

# Add project root to path so autodoc can import your Django apps
sys.path.insert(0, os.path.abspath("../../code"))
sys.path.insert(0, os.path.abspath("../../code/apps"))

# Setup Django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings.development")
try:
    import django

    django.setup()
except Exception as e:
    print(f"Warning: Django setup failed: {e}")
    # Continue without Django setup for basic documentation build

project = "Theory Orchestrator"
author = "Theory"
copyright = f"{datetime.now().year}, {author}"
html_title = "Theory Orchestrator"
html_theme = "furo"

extensions = [
    "myst_parser",
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx.ext.autosectionlabel",
    "sphinx.ext.intersphinx",
    "sphinxcontrib.mermaid",
]

autodoc_default_options = {
    "members": True,
    "undoc-members": False,
    "show-inheritance": True,
}

myst_enable_extensions = [
    "colon_fence",
    "deflist",
    "substitution",
]

# Treat .md as MyST (Markdown)
source_suffix = {
    ".md": "markdown",
}

templates_path = ["_templates"]
exclude_patterns = ["_build", "_generated/**/_raw/*"]

html_static_path = ["_static"]

# Cross-links to Python/Django docs
intersphinx_mapping = {
    "python": ("https://docs.python.org/3", {}),
    "django": ("https://docs.djangoproject.com/en/5.2/", "https://docs.djangoproject.com/en/5.2/objects.inv"),
}

# Make autosectionlabel targets unique across files by prefixing with document path
autosectionlabel_prefix_document = True
# Only create labels for H1/H2 to reduce surface area
autosectionlabel_maxdepth = 2

# Mermaid defaults
mermaid_version = "10.9.1"
