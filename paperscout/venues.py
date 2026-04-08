from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class CCFLevel(str, Enum):
    A = "A"
    B = "B"
    C = "C"
    NON_CCF = "NON_CCF"


_VENUES_DIR = Path(__file__).parent / "data"
_DEFAULT_VENUES_FILE = _VENUES_DIR / "top_venues.json"


@dataclass(frozen=True)
class Venue:
    name: str
    short_name: str
    alias: list[str] = field(default_factory=list)
    ccf_level: str = "NON_CCF"
    category: str = ""
    homepage: str = ""
    publisher: str = ""
    keywords: list[str] = field(default_factory=list)

    def matches_text(self, text: str) -> bool:
        text_lower = text.lower()
        for kw in self.keywords:
            if kw.lower() in text_lower:
                return True
        return False

    def __repr__(self) -> str:
        return f"Venue(short_name={self.short_name!r}, ccf_level={self.ccf_level!r})"


class VenueRegistry:
    _instance: VenueRegistry | None = None
    _loaded: bool = False

    def __init__(self) -> None:
        self._venues: dict[str, Venue] = {}
        self._short_names: dict[str, Venue] = {}
        self._alias_index: dict[str, Venue] = {}

    @classmethod
    def get_instance(cls) -> VenueRegistry:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def load(self, path: Path | None = None) -> None:
        if self._loaded:
            return
        src = path or self._resolve_path()
        if not src.exists():
            return
        raw = json.loads(src.read_text(encoding="utf-8"))
        for entry in raw.get("venues", []):
            venue = Venue(
                name=entry["name"],
                short_name=entry["short_name"],
                alias=entry.get("alias", []),
                ccf_level=entry.get("ccf_level", "NON_CCF"),
                category=entry.get("category", ""),
                homepage=entry.get("homepage", ""),
                publisher=entry.get("publisher", ""),
                keywords=entry.get("keywords", []),
            )
            self._venues[venue.short_name] = venue
            self._short_names[venue.short_name.lower()] = venue
            self._alias_index[venue.short_name.lower()] = venue
            for a in venue.alias:
                self._alias_index[a.lower()] = venue
        self._loaded = True

    def _resolve_path(self) -> Path:
        return Path(os.environ.get("PAPERSCOUT_VENUES_FILE", str(_DEFAULT_VENUES_FILE)))

    def lookup(self, name: str) -> Venue | None:
        key = name.strip().lower()
        return self._alias_index.get(key) or self._short_names.get(key)

    def filter_by_level(self, *levels: str) -> list[Venue]:
        return [v for v in self._venues.values() if v.ccf_level in levels]

    def filter_by_category(self, category: str) -> list[Venue]:
        cat_lower = category.strip().lower()
        return [v for v in self._venues.values() if v.category.lower() == cat_lower]

    def match_venue(
        self,
        title: str,
        abstract: str = "",
        authors: list[str] | None = None,
    ) -> list[tuple[Venue, float]]:
        text = " ".join(filter(None, [title, abstract]))
        if not text:
            return []
        scored: list[tuple[Venue, float]] = []
        for venue in self._venues.values():
            score = 0.0
            text_lower = text.lower()
            if venue.short_name.lower() in text_lower:
                score += 2.0
            elif any(alias.lower() in text_lower for alias in venue.alias):
                score += 1.5
            kw_hits = sum(1 for kw in venue.keywords if kw.lower() in text_lower)
            score += kw_hits * 0.3
            if score > 0:
                scored.append((venue, score))
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored

    def preferred_venues(self) -> list[Venue]:
        raw = os.environ.get("PAPERSCOUT_PREFERRED_VENUES", "").strip()
        if not raw:
            return list(self._venues.values())
        result: list[Venue] = []
        for name in raw.split(","):
            name = name.strip()
            if not name:
                continue
            if name.startswith("CCF-"):
                level = name.upper().replace("CCF-", "")
                result.extend(self.filter_by_level(level))
            else:
                v = self.lookup(name)
                if v:
                    result.append(v)
        return result

    def __len__(self) -> int:
        return len(self._venues)

    def __iter__(self):
        return iter(self._venues.values())


def get_registry() -> VenueRegistry:
    reg = VenueRegistry.get_instance()
    reg.load()
    return reg


def lookup_venue(name: str) -> Venue | None:
    return get_registry().lookup(name)


def match_paper_venues(
    title: str,
    abstract: str = "",
    authors: list[str] | None = None,
) -> list[Venue]:
    return [v for v, _ in get_registry().match_venue(title, abstract, authors)]


def top_venues_by_level(levels: list[str]) -> list[Venue]:
    return get_registry().filter_by_level(*levels)
