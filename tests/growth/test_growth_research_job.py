from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[2] / "scripts"
sys.path.insert(0, str(SCRIPTS))

from growth_research_job import _extract_payload, _validated_batch  # noqa: E402


def prospect(domain: str = "example.org") -> dict:
    return {
        "page_url": f"https://{domain}/resources/invoicing",
        "source_url": f"https://{domain}/resources/invoicing",
        "prospect_type": "resource",
        "opportunity_score": 75,
        "risk": "low",
        "why_fit": "The page curates tools for independent businesses.",
        "audience": "The page identifies freelancers as its audience.",
        "contact_method": f"https://{domain}/editorial-guidelines",
        "requires_account": False,
        "requires_payment": False,
        "link_type": "editorial",
        "direct_competitor": False,
    }


class ResearchJobTests(unittest.TestCase):
    def test_extracts_only_marked_payload(self):
        payload = _extract_payload(
            'RESEARCH_BATCH_JSON_START\n{"candidates_examined":8,"prospects":[]}\n'
            'RESEARCH_BATCH_JSON_END'
        )
        self.assertEqual(payload["candidates_examined"], 8)

    def test_rejects_known_competitor_and_paid_opportunity(self):
        competitor = prospect("freshbooks.com")
        paid = prospect("paid.example")
        paid["requires_payment"] = True
        retained, rejected = _validated_batch(
            {"candidates_examined": 10, "prospects": [prospect(), competitor, paid]}
        )
        self.assertEqual(len(retained), 1)
        self.assertEqual(rejected, 2)
        self.assertNotIn("direct_competitor", retained[0])


if __name__ == "__main__":
    unittest.main()
