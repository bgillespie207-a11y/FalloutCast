"""The package must carry its own data.

The curated target deck used to live at the repo root (`data/`) and be found
by walking up from `__file__`. That works in a source checkout and nowhere
else: once pip-installed, the walk lands in site-packages/ and every
deck-backed endpoint raises FileNotFoundError. It went unnoticed because the
test suite and the dev server both run from the checkout -- it surfaced only
when the container image was actually run.

These are structural tests (this repo's rule): they assert where the file
lives and that the build is told to ship it. They do not validate the deck's
contents, which test_dataset.py covers.
"""

import tomllib
from importlib import resources
from pathlib import Path

from falloutcast import targets

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_deck_resolves_inside_the_package():
    """Not next to it, and not above it -- inside, so it travels with the
    wheel wherever the package is installed."""
    deck = targets._packaged_deck()
    assert deck.is_file(), f"packaged deck missing: {deck}"

    package_dir = Path(str(resources.files("falloutcast")))
    assert package_dir in deck.parents


def test_no_repo_root_data_directory_reappears():
    """A `data/` at the repo root is the shape of the original bug: it would
    load fine in the checkout and be absent from any installed copy."""
    assert not (REPO_ROOT / "data").exists()


def test_build_is_told_to_ship_the_deck():
    """Declaring the package alone is not enough -- setuptools omits non-.py
    files from the wheel unless package-data names them."""
    cfg = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text())
    patterns = cfg["tool"]["setuptools"]["package-data"]["falloutcast"]
    assert any(p.endswith(".geojson") for p in patterns), patterns


def test_load_targets_needs_no_path_argument():
    """The API calls load_targets() with no arguments, so the default path is
    the one that has to work in production."""
    loaded = targets.load_targets()
    assert len(loaded) > 0
    assert all(t.id and t.name for t in loaded)
