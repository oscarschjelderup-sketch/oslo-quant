"""Tests never touch the network or the real store: each one gets an empty home in a temp directory."""

from __future__ import annotations

import pytest

import osloquant.domain  # noqa: F401  registers schemas and recorders
import osloquant.factors  # noqa: F401
import osloquant.trader  # noqa: F401
from osloquant import init_env
from osloquant.contract.storage import dispose_engines


@pytest.fixture(autouse=True)
def home(tmp_path):
    init_env(tmp_path)
    yield tmp_path
    dispose_engines()
