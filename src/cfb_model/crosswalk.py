"""Crosswalk implementation supporting sources metadata (SPEC-phase2 §3.4)."""

from pathlib import Path
from typing import Literal

import yaml

from cfb.errors import UnmappedTeamError
from cfb_model.exceptions import SourceNotInCrosswalkError


class Crosswalk:
    """A season's team mapping supporting source metadata filtering."""

    def __init__(
        self,
        season: int,
        sources: list[str],
        entries: dict[str, dict],
        path: Path,
    ) -> None:
        self.season = season
        self.sources = [s.lower() for s in sources]
        self.entries = entries
        self._path = path

        # Pre-build lookup indexes
        self._by_cfbd = {}
        self._by_sagarin = {}

        for canonical, entry in entries.items():
            # Index CFBD names
            if "cfbd" in self.sources and entry:
                cfbd_name = entry.get("cfbd")
                if cfbd_name:
                    self._by_cfbd[cfbd_name] = canonical
                for alias in entry.get("cfbd_aliases", []):
                    self._by_cfbd[alias] = canonical

            # Index Sagarin names
            if "sagarin" in self.sources and entry:
                sag_name = entry.get("sagarin")
                if sag_name:
                    self._by_sagarin[sag_name] = canonical
                for alias in entry.get("sagarin_aliases", []):
                    self._by_sagarin[alias] = canonical

    def from_cfbd(self, name: str) -> str:
        """Resolve a CFBD team name to its canonical slug, or raise errors."""
        if "cfbd" not in self.sources:
            raise SourceNotInCrosswalkError(
                f"Source 'cfbd' is not declared in the crosswalk for season {self.season} "
                f"at {self._path.name}."
            )
        try:
            return self._by_cfbd[name]
        except KeyError:
            raise UnmappedTeamError(
                f"unmapped cfbd team name {name!r} for season {self.season}.\n"
                f"Add it to {self._path}."
            ) from None

    def from_sagarin(self, name: str) -> str:
        """Resolve a Sagarin team name to its canonical slug, or raise errors."""
        if "sagarin" not in self.sources:
            raise SourceNotInCrosswalkError(
                f"Source 'sagarin' is not declared in the crosswalk for season {self.season} "
                f"at {self._path.name}."
            )
        try:
            return self._by_sagarin[name]
        except KeyError:
            raise UnmappedTeamError(
                f"unmapped sagarin team name {name!r} for season {self.season}.\n"
                f"Add it to {self._path}."
            ) from None

    def display_name(self, canonical_id: str) -> str:
        """Return display name (CFBD name) for a canonical ID."""
        return self._entry(canonical_id).get("cfbd", canonical_id)

    def division(self, canonical_id: str) -> Literal["FBS", "FCS"]:
        div = self._entry(canonical_id).get("division", "FBS")
        return "FBS" if div == "FBS" else "FCS"

    def _entry(self, canonical_id: str) -> dict:
        entry = self.entries.get(canonical_id)
        if entry is None:
            raise UnmappedTeamError(
                f"no crosswalk entry with canonical id {canonical_id!r} for season "
                f"{self.season} in {self._path.name}"
            )
        return entry


def load(season: int, *, data_dir: Path = Path("data/crosswalk")) -> Crosswalk:
    """Load the YAML crosswalk for a given season, parsing either legacy or metadata format."""
    path = data_dir / f"teams-{season}.yaml"
    if not path.is_file():
        raise UnmappedTeamError(f"no crosswalk for season {season} at {path}.")

    raw = yaml.safe_load(path.read_bytes())
    if not isinstance(raw, dict) or not raw:
        raise UnmappedTeamError(f"crosswalk at {path} is empty or invalid.")

    # Check for metadata-driven format vs legacy dict format
    if "teams" in raw and "sources" in raw:
        # Metadata-driven format (SPEC-phase2 §3.4)
        sources = raw["sources"]
        teams = raw["teams"] or {}
    else:
        # Legacy format: the entire file is a dictionary of canonical -> entry
        sources = ["cfbd", "sagarin"]
        teams = raw

    return Crosswalk(season, sources, teams, path=path)
