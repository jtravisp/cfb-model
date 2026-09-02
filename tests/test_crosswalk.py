"""Tests for crosswalk loading, sources metadata, and SourceNotInCrosswalkError."""

import pytest

from cfb.errors import UnmappedTeamError
from cfb_model.crosswalk import load
from cfb_model.exceptions import SourceNotInCrosswalkError


def test_crosswalk_sources_metadata_historical(tmp_path) -> None:
    # 1. Create a mock historical YAML with sources: [cfbd]
    yaml_content = """
season: 2017
sources:
  - cfbd
teams:
  alabama:
    cfbd: "Alabama"
    division: "FBS"
  clemson:
    cfbd: "Clemson"
    division: "FBS"
"""
    yaml_file = tmp_path / "teams-2017.yaml"
    yaml_file.write_text(yaml_content, encoding="utf-8")

    # Load mock crosswalk
    cw = load(2017, data_dir=tmp_path)

    assert cw.season == 2017
    assert cw.sources == ["cfbd"]

    # Request valid team from valid source -> should succeed
    assert cw.from_cfbd("Alabama") == "alabama"

    # Request valid team from omitted source -> should raise SourceNotInCrosswalkError
    with pytest.raises(SourceNotInCrosswalkError, match="Source 'sagarin' is not declared"):
        cw.from_sagarin("Alabama")

    # Request missing team from valid source -> should raise UnmappedTeamError
    with pytest.raises(UnmappedTeamError, match="unmapped cfbd team name 'Ohio State'"):
        cw.from_cfbd("Ohio State")


def test_crosswalk_legacy_fallback(tmp_path) -> None:
    # 2. Create a mock legacy YAML with no metadata fields (pure team dict)
    yaml_content = """
alabama:
  cfbd: "Alabama"
  sagarin: "ALABAMA"
  division: "FBS"
"""
    yaml_file = tmp_path / "teams-2016.yaml"
    yaml_file.write_text(yaml_content, encoding="utf-8")

    # Load legacy crosswalk
    cw = load(2016, data_dir=tmp_path)

    # Should fallback to both cfbd and sagarin as sources
    assert set(cw.sources) == {"cfbd", "sagarin"}

    # Both lookups should succeed
    assert cw.from_cfbd("Alabama") == "alabama"
    assert cw.from_sagarin("ALABAMA") == "alabama"

    # Missing team lookup on valid source still raises UnmappedTeamError
    with pytest.raises(UnmappedTeamError, match="unmapped sagarin team name"):
        cw.from_sagarin("OHIO STATE")
