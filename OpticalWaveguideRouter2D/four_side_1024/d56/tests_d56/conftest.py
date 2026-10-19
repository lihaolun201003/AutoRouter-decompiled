"""pytest fixtures for the independent D56 validator test suite.

The suite runs from the ``OpticalWaveguideRouter2D`` project root with::

    .venv\\Scripts\\python.exe -m pytest four_side_1024\\d56\\tests_d56 -v
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

TESTS_DIR = Path(__file__).resolve().parent
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))

from d56_helpers import (  # noqa: E402
    build_generated_routes,
    load_dataset,
    load_free_526,
    load_legacy_80,
)


@pytest.fixture(scope="session")
def dataset():
    return load_dataset()


@pytest.fixture(scope="session")
def generated_routes():
    return build_generated_routes()


@pytest.fixture(scope="session")
def legacy_80():
    return load_legacy_80()


@pytest.fixture(scope="session")
def free_526():
    return load_free_526()
