"""Smoke tests for cfb-model environment and dependencies."""

import numpy as np
import pandas as pd
import sklearn

import cfb


def test_dependencies_importable() -> None:
    assert cfb is not None
    assert np.__version__ is not None
    assert pd.__version__ is not None
    assert sklearn.__version__ is not None
