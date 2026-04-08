from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from paperscout.venues import (
    CCFLevel,
    Venue,
    VenueRegistry,
    get_registry,
    lookup_venue,
    match_paper_venues,
    top_venues_by_level,
)


@pytest.fixture(autouse=True)
def reset_singleton():
    VenueRegistry._instance = None
    VenueRegistry._loaded = False
    yield
    VenueRegistry._instance = None
    VenueRegistry._loaded = False


@pytest.fixture
def sample_venues_file(tmp_path):
    data = {
        "version": "1.0",
        "venues": [
            {
                "name": "Conference on Computer Vision and Pattern Recognition",
                "short_name": "CVPR",
                "alias": ["IEEE/CVF Conference on Computer Vision and Pattern Recognition"],
                "ccf_level": "A",
                "category": "CV",
                "homepage": "https://cvpr.thecvf.com/",
                "publisher": "IEEE/CVF",
                "keywords": ["computer vision", "pattern recognition", "object detection"],
            },
            {
                "name": "International Conference on Machine Learning",
                "short_name": "ICML",
                "alias": [],
                "ccf_level": "A",
                "category": "AI",
                "homepage": "https://icml.cc/",
                "publisher": "PMLR",
                "keywords": ["machine learning", "optimization", "theory"],
            },
            {
                "name": "European Conference on Computer Vision",
                "short_name": "ECCV",
                "alias": [],
                "ccf_level": "B",
                "category": "CV",
                "homepage": "https://eccv.ecva.net/",
                "publisher": "Springer",
                "keywords": ["computer vision", "image analysis"],
            },
            {
                "name": "COLING - International Conference on Computational Linguistics",
                "short_name": "COLING",
                "alias": [],
                "ccf_level": "B",
                "category": "NLP",
                "homepage": "https://coling2025.org/",
                "publisher": "ACL",
                "keywords": ["computational linguistics", "dialogue systems"],
            },
        ],
    }
    p = tmp_path / "venues.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


class TestVenue:
    def test_frozen_dataclass(self):
        v = Venue(name="Test Conf", short_name="TC", ccf_level="A", keywords=["test"])
        with pytest.raises(Exception):
            v.name = "changed"

    def test_matches_text_keyword_hit(self):
        v = Venue(name="CVPR", short_name="CVPR", keywords=["computer vision", "object detection"])
        assert v.matches_text("This paper studies computer vision tasks")
        assert v.matches_text("object detection in images")
        assert not v.matches_text("This is about database systems")

    def test_repr(self):
        v = Venue(name="CVPR", short_name="CVPR", ccf_level="A")
        assert "CVPR" in repr(v)
        assert "A" in repr(v)


class TestVenueRegistry:
    def test_load_parses_all_fields(self, sample_venues_file):
        reg = VenueRegistry()
        reg.load(sample_venues_file)
        assert len(reg) == 4
        cvpr = reg.lookup("CVPR")
        assert cvpr is not None
        assert cvpr.name == "Conference on Computer Vision and Pattern Recognition"
        assert cvpr.ccf_level == "A"
        assert cvpr.category == "CV"

    def test_load_idempotent(self, sample_venues_file):
        reg = VenueRegistry()
        reg.load(sample_venues_file)
        first_count = len(reg)
        reg.load(sample_venues_file)
        assert len(reg) == first_count

    def test_load_tolerates_missing_file(self):
        reg = VenueRegistry()
        reg.load(Path("/nonexistent/venues.json"))
        assert len(reg) == 0

    def test_lookup_by_short_name(self, sample_venues_file):
        reg = VenueRegistry()
        reg.load(sample_venues_file)
        v = reg.lookup("CVPR")
        assert v is not None
        assert v.short_name == "CVPR"

    def test_lookup_case_insensitive(self, sample_venues_file):
        reg = VenueRegistry()
        reg.load(sample_venues_file)
        v = reg.lookup("cvpr")
        assert v is not None
        assert v.short_name == "CVPR"

    def test_lookup_by_alias(self, sample_venues_file):
        reg = VenueRegistry()
        reg.load(sample_venues_file)
        v = reg.lookup("IEEE/CVF Conference on Computer Vision and Pattern Recognition")
        assert v is not None
        assert v.short_name == "CVPR"

    def test_lookup_unknown_returns_none(self, sample_venues_file):
        reg = VenueRegistry()
        reg.load(sample_venues_file)
        assert reg.lookup("NeurIPS") is None

    def test_filter_by_level(self, sample_venues_file):
        reg = VenueRegistry()
        reg.load(sample_venues_file)
        a_venues = reg.filter_by_level("A")
        assert len(a_venues) == 2
        assert all(v.ccf_level == "A" for v in a_venues)

        b_venues = reg.filter_by_level("B")
        assert len(b_venues) == 2

        multiple = reg.filter_by_level("A", "B")
        assert len(multiple) == 4

    def test_filter_by_category(self, sample_venues_file):
        reg = VenueRegistry()
        reg.load(sample_venues_file)
        cv_venues = reg.filter_by_category("CV")
        assert len(cv_venues) == 2
        assert all(v.category == "CV" for v in cv_venues)

    def test_match_venue_exact_short_name(self, sample_venues_file):
        reg = VenueRegistry()
        reg.load(sample_venues_file)
        results = reg.match_venue("CVPR 2025 Survey", "")
        assert len(results) > 0
        top = results[0]
        assert top[0].short_name == "CVPR"
        assert top[1] >= 2.0

    def test_match_venue_alias_hit(self, sample_venues_file):
        reg = VenueRegistry()
        reg.load(sample_venues_file)
        results = reg.match_venue(
            "IEEE/CVF Conference on Computer Vision and Pattern Recognition Workshop",
            "",
        )
        assert len(results) > 0
        assert results[0][0].short_name == "CVPR"
        assert results[0][1] >= 1.5

    def test_match_venue_keyword_hit(self, sample_venues_file):
        reg = VenueRegistry()
        reg.load(sample_venues_file)
        results = reg.match_venue(
            "Advances in Visual Object Detection",
            "We study object detection using deep learning methods.",
        )
        top = results[0]
        assert top[0].short_name == "CVPR"
        assert top[1] > 0

    def test_match_venue_no_match(self, sample_venues_file):
        reg = VenueRegistry()
        reg.load(sample_venues_file)
        results = reg.match_venue(
            "Ancient Greek Poetry and Rhythmic Meter in Oral Tradition",
            "",
        )
        assert len(results) == 0

    def test_match_venue_sorted_by_score(self, sample_venues_file):
        reg = VenueRegistry()
        reg.load(sample_venues_file)
        results = reg.match_venue(
            "CVPR and ICML Joint Workshop on Machine Learning for Computer Vision",
            "",
        )
        scores = [s for _, s in results]
        assert scores == sorted(scores, reverse=True)


class TestPreferredVenues:
    def test_preferred_all_when_env_empty(self, sample_venues_file, monkeypatch):
        monkeypatch.delenv("PAPERSCOUT_PREFERRED_VENUES", raising=False)
        reg = VenueRegistry()
        reg.load(sample_venues_file)
        preferred = reg.preferred_venues()
        assert len(preferred) == 4

    def test_preferred_by_ccf_level(self, sample_venues_file, monkeypatch):
        monkeypatch.setenv("PAPERSCOUT_PREFERRED_VENUES", "CCF-A")
        reg = VenueRegistry()
        reg.load(sample_venues_file)
        preferred = reg.preferred_venues()
        assert len(preferred) == 2
        assert all(v.ccf_level == "A" for v in preferred)

    def test_preferred_mixed_ccf_and_name(self, sample_venues_file, monkeypatch):
        monkeypatch.setenv("PAPERSCOUT_PREFERRED_VENUES", "CCF-B,CVPR")
        reg = VenueRegistry()
        reg.load(sample_venues_file)
        preferred = reg.preferred_venues()
        names = {v.short_name for v in preferred}
        assert "ECCV" in names
        assert "COLING" in names
        assert "CVPR" in names

    def test_preferred_unknown_name_skipped(self, sample_venues_file, monkeypatch):
        monkeypatch.setenv("PAPERSCOUT_PREFERRED_VENUES", "CCF-A,UnknownConf,NeurIPS")
        reg = VenueRegistry()
        reg.load(sample_venues_file)
        preferred = reg.preferred_venues()
        names = {v.short_name for v in preferred}
        assert "UnknownConf" not in names


class TestModuleLevelFunctions:
    def test_lookup_venue(self, sample_venues_file, monkeypatch):
        monkeypatch.setenv("PAPERSCOUT_VENUES_FILE", str(sample_venues_file))
        VenueRegistry._instance = None
        VenueRegistry._loaded = False
        v = lookup_venue("CVPR")
        assert v is not None
        assert v.short_name == "CVPR"

    def test_match_paper_venues(self, sample_venues_file, monkeypatch):
        monkeypatch.setenv("PAPERSCOUT_VENUES_FILE", str(sample_venues_file))
        VenueRegistry._instance = None
        VenueRegistry._loaded = False
        venues = match_paper_venues("Object Detection in Computer Vision", "We study detection.")
        assert len(venues) > 0
        assert venues[0].short_name == "CVPR"

    def test_top_venues_by_level(self, sample_venues_file, monkeypatch):
        monkeypatch.setenv("PAPERSCOUT_VENUES_FILE", str(sample_venues_file))
        VenueRegistry._instance = None
        VenueRegistry._loaded = False
        venues = top_venues_by_level(["A"])
        assert len(venues) == 2
