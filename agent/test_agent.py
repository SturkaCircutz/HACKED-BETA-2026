"""No-key, no-network regression tests: python -m unittest agent.test_agent -v."""
import asyncio
import json
import os
import unittest
from unittest.mock import AsyncMock, patch
from urllib.parse import parse_qs

import httpx
from pydantic import ValidationError

from agent import Decision, ReportInput, analyze_report, analyze_report_sync
from api import BOUNDARY_URL, EPL_URL, ORS_URL, OVERPASS_URL, CityAPI
from database import Store


class FakeCity:
    def __init__(self, status="inside"):
        self.status, self.nearby_calls, self.service_calls = status, 0, 0

    async def jurisdiction(self, lat, lng):
        return {"status": self.status, "city": "Edmonton", "source_url": BOUNDARY_URL, "warnings": []}

    async def service_catalog(self):
        self.service_calls += 1
        return {"available": True, "services": [{"service_code": "real-123", "service_name": "Illegal dumping"}],
                "reason": None, "sources": [], "warnings": []}

    async def nearby_places(self, lat, lng):
        self.nearby_calls += 1
        return {"places": [{"name": "Mapped bin", "kind": "public_bin", "address": "", "lat": lat, "lng": lng,
                            "distance_m": 100, "distance_basis": "straight_line", "bin_status": "mapped_bin",
                            "route_verified": False, "walking_minutes": None, "walking_minutes_estimate": 2,
                            "within_10_min_walk": None, "maps_url": "https://www.google.com/maps/", "source_url": EPL_URL,
                            "note": "Small ordinary litter only."}], "warnings": [], "sources": []}


class AgentTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {"GROQ_API_KEY": "", "ORS_API_KEY": "", "OPEN311_API_KEY": "", "ECO311_OFFLINE": "0"})
        self.env.start()
        self.store = Store(":memory:")

    def tearDown(self):
        self.store.close()
        self.env.stop()

    async def report(self, story, city=None, **kwargs):
        return await analyze_report(story, 53.54136, -113.5172, store=self.store, city_client=city or FakeCity(), **kwargs)

    async def test_dumped_furniture_gets_report_not_bin_walk(self):
        result = await self.report("Three mattresses and a couch dumped behind a public community hall.")
        self.assertEqual(result["category"], "illegal_dumping")
        self.assertTrue(result["reporting"]["reportable"])
        self.assertEqual(result["reporting"]["phone"], "311")
        self.assertFalse(result["reporting"]["submitted"])
        self.assertFalse(result["reporting"]["direct_submission_enabled"])
        self.assertEqual(result["reporting"]["service_candidates"][0]["service_code"], "real-123")
        self.assertEqual(result["nearby_places"], [])

    async def test_negated_hazards_stay_litter(self):
        result = await self.report("Two plastic cups, no needles or broken glass on the sidewalk.")
        self.assertEqual(result["category"], "litter")
        self.assertEqual(result["priority"], "routine")
        self.assertEqual(len(result["nearby_places"]), 1)

    async def test_later_positive_hazard_is_preserved(self):
        result = await self.report("No needles here, but a syringe by the public playground.")
        self.assertEqual(result["category"], "needle")
        self.assertEqual(result["nearby_places"], [])
        self.assertEqual(result["priority"], "urgent")

    async def test_old_burnt_item_is_not_active_fire(self):
        for story in ("An old burnt couch dumped here", "A broken fire extinguisher beside the bin", "Trash beside a fire hydrant"):
            result = await self.report(story)
            self.assertNotEqual(result["priority"], "emergency")

    async def test_active_fire_preempts_bin_suggestions(self):
        city = FakeCity()
        result = await self.report("The bin is on fire with active flames.", city)
        self.assertEqual(result["priority"], "emergency")
        self.assertEqual(result["reporting"]["phone"], "911")
        self.assertFalse(result["reporting"]["reportable"])
        self.assertEqual(city.nearby_calls, 0)

    async def test_private_needles_use_verified_private_contact(self):
        result = await self.report("Used needles in my yard on private property")
        self.assertEqual(result["reporting"]["phone"], "780-426-0500")
        self.assertEqual(result["reporting"]["contact_name"], "Hiregood")
        self.assertFalse(result["reporting"]["reportable"])
        self.assertEqual(result["nearby_places"], [])

    async def test_unknown_boundary_is_not_outside(self):
        result = await self.report("Garbage on the sidewalk", FakeCity("unknown"))
        self.assertIsNone(result["reporting"]["reportable"])
        self.assertIsNone(result["reporting"]["phone"])
        self.assertEqual(result["jurisdiction"]["status"], "unknown")

    async def test_outside_city_avoids_edmonton_contacts(self):
        city = FakeCity("outside")
        result = await self.report("Litter here", city)
        self.assertIsNone(result["reporting"]["url"])
        self.assertIsNone(result["reporting"]["phone"])
        self.assertEqual(city.service_calls, 0)

    async def test_own_bulky_waste_has_no_library_disposal(self):
        result = await self.report("Where can I dispose of my old mattress?")
        self.assertEqual(result["category"], "disposal")
        self.assertFalse(result["reporting"]["reportable"])
        self.assertEqual(result["nearby_places"], [])

    async def test_hazard_materials_never_get_bin_recommendations(self):
        for story in ("Batteries and paint cans scattered with trash on the sidewalk", "Where can I dispose of a propane tank?",
                      "Where can I dispose of an old refrigerator?", "Where can I dispose of motor oil?"):
            result = await self.report(story)
            self.assertEqual(result["nearby_places"], [], story)

    async def test_extinguished_fire_is_not_an_emergency(self):
        for story in ("The trash bin is no longer on fire; there is only cold ash now.",
                      "The fire is out, and there are no active flames now."):
            result = await self.report(story)
            self.assertNotEqual(result["priority"], "emergency", story)

    async def test_review_clarification_controls_contact_and_is_in_draft(self):
        note = "Correction: it is a needle on my private driveway, not a park."
        result = await self.report("Some trash in a public park.", review_feedback=note)
        self.assertEqual(result["reporting"]["phone"], "780-426-0500")
        self.assertIn(note, result["reporting"]["report_text"])

    async def test_model_corrected_litter_gets_nearby_lookup(self):
        model, city = AsyncMock(), FakeCity()
        model.ainvoke.return_value = Decision(category="litter", priority="routine", summary="A few wrappers",
                                             private_property=False, clarification=None)
        result = await self.report("Someone dumped a few small wrappers on the pavement.", city, model=model)
        self.assertEqual(city.nearby_calls, 1)
        self.assertEqual(len(result["nearby_places"]), 1)

    async def test_llm_cannot_downgrade_observed_needle(self):
        model = AsyncMock()
        model.ainvoke.return_value = Decision(category="litter", priority="routine", summary="Small litter",
                                             private_property=None, clarification=None)
        result = await self.report("A syringe on the sidewalk", model=model)
        self.assertTrue(result["meta"]["llm_used"])
        self.assertEqual(result["category"], "needle")
        self.assertEqual(result["reporting"]["phone"], "311")
        self.assertEqual(model.ainvoke.await_count, 1)

    async def test_llm_failure_returns_useful_result_without_error_secret(self):
        model = AsyncMock()
        model.ainvoke.side_effect = RuntimeError("SECRET-KEY-SHOULD-NOT-APPEAR")
        result = await self.report("Plastic cups on a sidewalk", model=model)
        self.assertFalse(result["meta"]["llm_used"])
        self.assertNotIn("SECRET-KEY", json.dumps(result))
        self.assertTrue(result["steps"])

    async def test_user_markdown_does_not_inject_links(self):
        result = await self.report("Litter. [Official portal](https://attacker.invalid) <script>alert(1)</script>")
        self.assertNotIn("[Official portal](https://attacker.invalid)", result["markdown"])
        self.assertNotIn("<script>", result["markdown"])
        self.assertFalse(result["reporting"]["submitted"])

    async def test_request_results_are_independent(self):
        one, two = await asyncio.gather(
            self.report("Plastic cups on sidewalk", report_id="one"),
            self.report("A dumped sofa", report_id="two"))
        self.assertEqual(one["report_id"], "one")
        self.assertEqual(two["report_id"], "two")
        self.assertNotEqual(one["category"], two["category"])

    async def test_sync_wrapper_refuses_running_event_loop(self):
        with self.assertRaisesRegex(RuntimeError, "await analyze_report"):
            analyze_report_sync("Plastic cups", 53.54, -113.51)


class ClientTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.store = Store(":memory:")
        self.env = patch.dict(os.environ, {"ORS_API_KEY": "", "OPEN311_API_KEY": "", "ECO311_OFFLINE": "0"})
        self.env.start()

    def tearDown(self):
        self.store.close()
        self.env.stop()

    async def use(self, handler, method, *args):
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler), trust_env=False) as client:
            async with CityAPI(self.store, client=client) as api:
                result = await getattr(api, method)(*args)
            self.assertFalse(client.is_closed)
            return result

    async def test_boundary_query_has_correct_coordinate_order(self):
        def handle(request):
            self.assertIn("POINT(-113.517200 53.541360)", request.url.params["$where"])
            return httpx.Response(200, json=[{"id": "1"}])
        self.assertEqual((await self.use(handle, "jurisdiction", 53.54136, -113.5172))["status"], "inside")

    async def test_boundary_provider_failure_yields_unknown(self):
        result = await self.use(lambda _: httpx.Response(503), "jurisdiction", 53.54, -113.51)
        self.assertEqual(result["status"], "unknown")

    async def test_denied_open311_cached_without_claiming_submission(self):
        calls = []
        def handle(request):
            calls.append(request)
            return httpx.Response(403)
        result = await self.use(handle, "service_catalog")
        again = await self.use(handle, "service_catalog")
        self.assertFalse(result["available"])
        self.assertEqual(len(calls), 1)
        self.assertIn("website protection", again["reason"])

    async def test_retry_after_blocks_other_paths_on_same_provider(self):
        calls = []
        def handle(request):
            calls.append(request)
            return httpx.Response(429, headers={"Retry-After": "120"})
        await self.use(handle, "service_catalog")
        other = await self.use(handle, "request_status", "valid-123")
        self.assertEqual(len(calls), 1)
        self.assertIn("cooldown", other["reason"])
        self.assertEqual(self.store.cache_get("provider:cooldown:311.edmonton.ca")["retry_after_seconds"], 120)

    async def test_empty_catalog_is_not_claimed_usable(self):
        result = await self.use(lambda _: httpx.Response(200, json=[]), "service_catalog")
        self.assertFalse(result["available"])
        self.assertIn("no service catalog entries", result["reason"])

    async def test_invalid_status_id_never_reaches_network(self):
        result = await self.use(lambda _: self.fail("network should not be called"), "request_status", "../../evil")
        self.assertFalse(result["available"])

    def place_handler(self, request):
        if request.url.host == "data.edmonton.ca":
            return httpx.Response(200, json=[{"branch_id": "1", "branch": "Test Library", "address": "123 Street",
                                              "latitude": 53.5415, "longitude": -113.5172}])
        if request.url.host == "overpass-api.de":
            return httpx.Response(200, json={"elements": [
                {"type": "node", "id": 2, "lat": 53.5418, "lon": -113.5172, "tags": {"amenity": "waste_basket"}},
                {"type": "node", "id": 3, "lat": 53.5416, "lon": -113.5172, "tags": {"amenity": "waste_basket", "waste": "dog_excrement"}},
                {"type": "node", "id": 4, "lat": 53.5416, "lon": -113.5172, "tags": {"amenity": "waste_basket", "access": "private"}}]})
        self.fail("Unexpected network destination")

    async def test_two_real_options_not_padded_and_library_not_bin(self):
        result = await self.use(self.place_handler, "nearby_places", 53.54136, -113.5172)
        self.assertEqual(len(result["places"]), 2)
        for place in result["places"]:
            self.assertIsNone(place["within_10_min_walk"])
            self.assertIsNone(place["walking_minutes"])
            self.assertFalse(place["route_verified"])
        library = next(p for p in result["places"] if p["kind"] == "library")
        self.assertEqual(library["bin_status"], "not_verified")

    async def test_colocated_library_departments_are_one_destination(self):
        def handle(request):
            if request.url.host == "data.edmonton.ca":
                rows = [{"branch_id": code, "branch": name, "latitude": 53.5415, "longitude": -113.5172}
                        for code, name in [("EPLMNJ", "Shelley Milner Children's Library"), ("EPLMNA", "Stanley A. Milner (Downtown)")]]
                return httpx.Response(200, json=rows)
            self.assertIn("out body center 40", parse_qs(request.content.decode())["data"][0])
            return httpx.Response(200, json={"elements": []})
        result = await self.use(handle, "nearby_places", 53.54136, -113.5172)
        self.assertEqual(len(result["places"]), 1)
        self.assertEqual(result["places"][0]["name"], "Stanley A. Milner (Downtown)")

    async def test_null_route_excluded_not_replaced_by_guess(self):
        os.environ["ORS_API_KEY"] = "test-key-not-real"
        def handle(request):
            if request.url.host == "api.openrouteservice.org":
                self.assertEqual(json.loads(request.content)["locations"][0], [-113.5172, 53.54136])
                return httpx.Response(200, json={"durations": [[None, 600]], "distances": [[None, 700]]})
            return self.place_handler(request)
        result = await self.use(handle, "nearby_places", 53.54136, -113.5172)
        self.assertEqual(len(result["places"]), 1)
        self.assertTrue(result["places"][0]["within_10_min_walk"])
        self.assertEqual(result["places"][0]["walking_minutes"], 10)

    async def test_route_over_ten_minutes_excluded(self):
        os.environ["ORS_API_KEY"] = "test-key-not-real"
        def handle(request):
            if request.url.host == "api.openrouteservice.org":
                return httpx.Response(200, json={"durations": [[601, 900]], "distances": [[900, 1300]]})
            return self.place_handler(request)
        self.assertEqual((await self.use(handle, "nearby_places", 53.54136, -113.5172))["places"], [])

    async def test_snap_access_distance_counts_towards_ten_minutes(self):
        os.environ["ORS_API_KEY"] = "test-key-not-real"
        def handle(request):
            if request.url.host == "api.openrouteservice.org":
                return httpx.Response(200, json={"durations": [[590, 590]], "distances": [[700, 700]],
                    "sources": [{"snapped_distance": 20}], "destinations": [{"snapped_distance": 0}, {"snapped_distance": 0}]})
            return self.place_handler(request)
        self.assertEqual((await self.use(handle, "nearby_places", 53.54136, -113.5172))["places"], [])

    async def test_groq_structured_output_adapter_mock_provider(self):
        # No API key or network is required; assert the real provider path is used.
        from agent import Decision
        mocked = Decision(category="litter", priority="routine", summary="Two paper cups",
                          private_property=False, clarification=None)
        with patch.dict(os.environ, {"GROQ_API_KEY": "gsk-test-not-real", "ECO311_MODEL": "openai/gpt-oss-20b"}):
            with patch("langchain_groq.ChatGroq") as make_model:
                chain = make_model.return_value.with_structured_output.return_value
                chain.ainvoke = AsyncMock(return_value=mocked)
                result = await self.report("Two paper cups on the sidewalk")
        self.assertTrue(result["meta"]["llm_used"])
        self.assertEqual(result["summary"], "Two paper cups")
        self.assertEqual(make_model.call_args.kwargs["model"], "openai/gpt-oss-20b")
        self.assertEqual(make_model.call_args.kwargs["reasoning_effort"], "low")
        self.assertEqual(make_model.call_args.kwargs["max_retries"], 0)
        make_model.return_value.with_structured_output.assert_called_once_with(
            Decision, method="json_schema", strict=True
        )
        chain.ainvoke.assert_awaited_once()

    async def test_openai_key_alone_does_not_enable_groq(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-not-used", "GROQ_API_KEY": ""}):
            result = await self.report("Plastic cups on a sidewalk")
        self.assertFalse(result["meta"]["llm_used"])

    async def test_api_endpoint_shape_and_validation(self):
        from api.main import app
        with patch.dict(os.environ, {"ECO311_API_KEY": "local-test"}), patch("api.main.analyze_report", new_callable=AsyncMock) as fn:
            fn.return_value = {"summary": "ok", "reporting": {"submitted": False}}
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://local.test", trust_env=False) as client:
                body = {"story": "Plastic litter", "lat": 53.54, "lng": -113.51}
                self.assertEqual((await client.post("/api/agent/analyze", json=body)).status_code, 401)
                headers = {"X-Eco311-Key": "local-test"}
                valid = await client.post("/api/agent/analyze", json=body, headers=headers)
                self.assertEqual(valid.status_code, 200)
                self.assertIn("ai_response", valid.json())
                self.assertEqual((await client.post("/api/agent/analyze", json={**body, "lat": 153}, headers=headers)).status_code, 422)


class StoreAndInputTests(unittest.TestCase):
    def test_coordinates_and_blank_story_rejected(self):
        for changes in ({"lat": float("nan")}, {"lng": float("inf")}, {"story": "   "}):
            with self.assertRaises(ValidationError):
                ReportInput(**{"story": "Waste here", "lat": 53.54, "lng": -113.51, **changes})

    def test_fts_handles_untrusted_query_and_ranks_relevant_document(self):
        db = Store(":memory:")
        try:
            self.assertIn("needle", [d["id"] for d in db.retrieve('syringe needle " OR 1=1 --')])
            self.assertEqual(db.document("needle")["private_phone"], "780-426-0500")
            db.cache_set("x", {"safe": 1}, 10)
            self.assertEqual(db.cache_get("x"), {"safe": 1})
            db.cache_set("x", {}, 0)
            self.assertIsNone(db.cache_get("x"))
        finally:
            db.close()

    def test_sync_entrypoint_can_be_called_twice(self):
        db = Store(":memory:")
        try:
            with patch.dict(os.environ, {"GROQ_API_KEY": "", "ECO311_OFFLINE": "1"}):
                for _ in range(2):
                    result = analyze_report_sync("Ordinary litter on sidewalk", 53.54, -113.51, store=db, city_client=FakeCity())
                    self.assertFalse(result["reporting"]["submitted"])
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main()
