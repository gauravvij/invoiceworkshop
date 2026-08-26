from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from growth_daily_monitor import detect_signals  # noqa: E402


def state(*, impressions=0, sessions=100, index="PASS", queries=None):
    return {
        "sources": {
            "gsc": {"totals": {"clicks": 0, "impressions": impressions}},
            "ga4": {"totals": {
                "sessions": sessions, "users": sessions, "pageviews": sessions,
                "tool_started": 10, "pdf_downloaded": 1,
            }},
            "sitemap": {"totals": {"errors": 0, "warnings": 0}},
            "health": {"totals": {"healthy": 9, "checked": 9}},
        },
        "index": {"https://invoiceworkshop.com/": {
            "verdict": index, "coverage_state": index, "error": None,
        }},
        "breakdowns": queries or {},
        "placements": {},
    }


class DailySignalTests(unittest.TestCase):
    def signals(self, before, after, status="ok", errors=None):
        return detect_signals(
            before,
            after,
            collection_status=status,
            collection_errors=errors or [],
            gsc_absolute=10,
            gsc_percent=25,
            ga_absolute=10,
            ga_percent=50,
        )

    def test_small_routine_delta_does_not_trigger_reasoning(self):
        self.assertEqual(self.signals(state(sessions=100), state(sessions=105)), [])

    def test_meaningful_search_index_and_failure_changes_trigger(self):
        signals = self.signals(
            state(impressions=0, index="NEUTRAL"),
            state(impressions=15, index="PASS"),
            status="partial",
            errors=["gsc: HTTP 500"],
        )
        types = {item["type"] for item in signals}
        self.assertEqual(
            types,
            {"measurement_failure", "gsc_delta", "index_state_changes"},
        )

    def test_new_query_and_ranking_movement_trigger(self):
        old = state(queries={
            ("query", "invoice maker"): {"clicks": 0, "impressions": 5, "position": 20.0}
        })
        new = state(queries={
            ("query", "invoice maker"): {"clicks": 0, "impressions": 8, "position": 15.0},
            ("query", "free invoice"): {"clicks": 0, "impressions": 2, "position": 30.0},
        })
        types = {item["type"] for item in self.signals(old, new)}
        self.assertEqual(types, {"new_gsc_queries", "ranking_movement"})


if __name__ == "__main__":
    unittest.main()
