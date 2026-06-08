import datetime
import os
import sys
import types
import unittest
from unittest.mock import patch


os.environ.setdefault("ZIP_CODE", "0000AA")
os.environ.setdefault("GAD_BAG_ID", "test-bag-id")
os.environ.setdefault("HOUSE_NUMBER", "1")
os.environ.setdefault("BRIDGE_IP", "127.0.0.1")


def install_stub_module(name, module):
    if name not in sys.modules:
        sys.modules[name] = module


try:
    import phue  # noqa: F401
except ImportError:
    phue = types.ModuleType("phue")
    phue.Bridge = object
    install_stub_module("phue", phue)


import bins
import gad
import main


RUN_DATE = datetime.date(2026, 6, 11)
PICKUP_DATE = datetime.datetime(2026, 6, 12)


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


def fake_gad_get(streams, pickup_dates):
    def _fake_get(url, timeout):
        if url.endswith("/afvalstromen"):
            return FakeResponse(streams)
        if url.endswith("/ophaaldata"):
            return FakeResponse(pickup_dates)
        raise AssertionError(f"Unexpected URL: {url}")

    return _fake_get


class GadParsingTests(unittest.TestCase):
    def assert_tomorrow_bin(self, next_bins, expected_bin):
        self.assertEqual(next_bins, {PICKUP_DATE: expected_bin})
        self.assertEqual(
            main.get_tomorrow_bins(next_bins, today=RUN_DATE),
            [expected_bin],
        )

    def test_gad_api_id_matching_prefers_enum(self):
        with patch.object(
            gad.requests,
            "get",
            fake_gad_get(
                streams=[{"id": 3, "title": "A changed paper label"}],
                pickup_dates=[{"afvalstroom_id": 3, "ophaaldatum": "2026-06-12"}],
            ),
        ):
            next_bins = gad.get_next_bins_api()

        self.assert_tomorrow_bin(next_bins, bins.Bin.PAPER)

    def test_gad_title_alias_fallback_when_api_id_is_unknown(self):
        def fail_llm(*args, **kwargs):
            self.fail("LLM should not be called when title aliases match")

        with patch.object(gad, "reconcile_bin_with_llm", fail_llm), patch.object(
            gad.requests,
            "get",
            fake_gad_get(
                streams=[{"id": 999, "title": "GFE+T (etensresten + klein tuinafval)"}],
                pickup_dates=[{"afvalstroom_id": 999, "ophaaldatum": "2026-06-12"}],
            ),
        ):
            next_bins = gad.get_next_bins_api()

        self.assert_tomorrow_bin(next_bins, bins.Bin.PLANTS)

    def test_ollama_fallback_when_api_id_and_title_aliases_are_unknown(self):
        ollama_calls = []

        def fake_post(url, json, timeout):
            ollama_calls.append({"url": url, "json": json, "timeout": timeout})
            return FakeResponse({"response": '{"bin": "REST_PMD"}'})

        with patch.object(
            gad.requests,
            "get",
            fake_gad_get(
                streams=[{"id": 999, "title": "Nieuwe onbekende afvalstroom"}],
                pickup_dates=[{"afvalstroom_id": 999, "ophaaldatum": "2026-06-12"}],
            ),
        ), patch.object(bins.requests, "post", fake_post):
            next_bins = gad.get_next_bins_api()

        self.assert_tomorrow_bin(next_bins, bins.Bin.REST_PMD)
        self.assertEqual(len(ollama_calls), 1)
        self.assertTrue(ollama_calls[0]["url"].endswith("/api/generate"))
        self.assertIn('"REST_PMD": 27', ollama_calls[0]["json"]["prompt"])
        self.assertIn("Nieuwe onbekende afvalstroom", ollama_calls[0]["json"]["prompt"])

    def test_get_next_bins_returns_api_result_directly(self):
        with patch.object(gad, "get_next_bins_api", lambda: {}):
            next_bins = gad.get_next_bins()

        self.assertEqual(next_bins, {})


if __name__ == "__main__":
    unittest.main()
