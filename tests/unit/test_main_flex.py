"""Unit tests for _build_night_variants in main.py."""

from __future__ import annotations

import sys
from pathlib import Path

# main.py is at the project root, not in the src package
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from main import _build_night_variants


class TestBuildNightVariants:
    def test_no_flex_returns_target_only(self):
        assert _build_night_variants(7, 0) == [7]

    def test_flex_one_returns_five_variants(self):
        assert _build_night_variants(7, 1) == [6, 7, 8]

    def test_flex_two_returns_five_variants(self):
        assert _build_night_variants(7, 2) == [5, 6, 7, 8, 9]

    def test_minimum_night_is_one(self):
        # target=1, flex=3 → would produce -2,-1,0,1,2,3,4 but all < 1 are clamped to 1
        result = _build_night_variants(1, 3)
        assert all(n >= 1 for n in result)

    def test_clamping_deduplicates(self):
        # target=2, flex=3 → raw: -1,0,1,2,3,4,5 → clamped: 1,1,1,2,3,4,5 → deduped: 1,2,3,4,5
        result = _build_night_variants(2, 3)
        assert result == [1, 2, 3, 4, 5]

    def test_no_duplicates_in_result(self):
        result = _build_night_variants(5, 2)
        assert len(result) == len(set(result))

    def test_result_is_sorted_ascending(self):
        result = _build_night_variants(10, 3)
        assert result == sorted(result)

    def test_large_flex(self):
        result = _build_night_variants(7, 7)
        assert result == list(range(1, 15))  # 1..14 (0 clamped to 1)
