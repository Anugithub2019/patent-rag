import json
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from backend.contract import ContractError, make_job_result, parse_analysis_response, validate_analysis, validate_contract


FIXTURES = Path(__file__).parent / "fixtures"


def fixture(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class ContractTests(unittest.TestCase):
    def test_complete_analysis_and_all_job_states_validate(self):
        analysis = validate_analysis(fixture("analysis-v2.valid.json"))
        for result in (
            make_job_result("pending"),
            make_job_result("complete", data=analysis),
            make_job_result("failed", error="upstream unavailable"),
            make_job_result(
                "failed",
                error="invalid report",
                debug={"validation_error": "missing feature ID", "upstream_response": {"features": []}},
            ),
        ):
            validate_contract(result, "jobResult")

    def test_answer_json_and_fenced_json_are_accepted(self):
        analysis = fixture("analysis-v2.valid.json")
        self.assertEqual(parse_analysis_response({"answer": json.dumps(analysis)}), analysis)
        self.assertEqual(parse_analysis_response({"answer": f"```json\n{json.dumps(analysis)}\n```"}), analysis)

    def test_nullable_optional_fields_are_omitted_and_incomplete_matches_are_dropped(self):
        upstream = fixture("analysis-v2.valid.json")
        complete_match = upstream["features"][0]["matches"][0]
        complete_match["source_url"] = None
        complete_match["evidence"][0]["location"] = None
        incomplete_match = json.loads(json.dumps(complete_match))
        incomplete_match["reference_id"] = None
        upstream["features"][1]["matches"] = [incomplete_match]
        snapshot = json.loads(json.dumps(upstream))

        normalized = parse_analysis_response(upstream)

        self.assertNotIn("source_url", normalized["features"][0]["matches"][0])
        self.assertNotIn("location", normalized["features"][0]["matches"][0]["evidence"][0])
        self.assertEqual(normalized["features"][1]["matches"], [])
        self.assertEqual(upstream, snapshot)

    def test_missing_or_narrative_upstream_answer_is_rejected(self):
        for response in ({}, {"answer": "This is a narrative response."}, []):
            with self.subTest(response=response), self.assertRaises(ContractError):
                parse_analysis_response(response)

    def test_invalid_enum_and_duplicate_id_are_rejected(self):
        for name in ("analysis-v2.invalid-enum.json", "analysis-v2.invalid-duplicate.json"):
            with self.subTest(name=name), self.assertRaises(ContractError):
                validate_analysis(fixture(name))

    def test_empty_match_list_is_valid(self):
        analysis = fixture("analysis-v2.valid.json")
        analysis["features"] = [analysis["features"][1]]
        validate_analysis(analysis)

    def test_feature_id_must_be_a_positive_integer(self):
        for invalid_feature_id in ("F1", 0, 1.5, True):
            analysis = fixture("analysis-v2.valid.json")
            analysis["features"][0]["feature_id"] = invalid_feature_id
            with self.subTest(feature_id=invalid_feature_id), self.assertRaisesRegex(
                ContractError, "positive integer"
            ):
                validate_analysis(analysis)


class FlaskFlowTests(unittest.TestCase):
    def test_blank_query_is_rejected(self):
        import servers.flask_server as server

        client = server.app.test_client()
        response = client.post("/api/query", json={"text": "   "})
        self.assertEqual(response.status_code, 400)

    def test_submit_then_poll_complete_report(self):
        import servers.flask_server as server

        analysis = fixture("analysis-v2.valid.json")
        stored = {}
        fake_redis = Mock()
        fake_redis.setex.side_effect = lambda key, ttl, value: stored.__setitem__(key, value.encode())
        fake_redis.get.side_effect = lambda key: stored.get(key)
        fake_task = Mock()
        fake_tasks_module = types.ModuleType("backend.tasks")
        fake_tasks_module.process_query = fake_task

        with patch.object(server, "redis_client", fake_redis), patch.dict(sys.modules, {"backend.tasks": fake_tasks_module}):
            client = server.app.test_client()
            accepted = client.post("/api/query", json={"text": "A controller and two contacts"})
            self.assertEqual(accepted.status_code, 202)
            job_id = accepted.get_json()["job_id"]
            fake_task.delay.assert_called_once_with(job_id, "A controller and two contacts")

            pending = client.get(f"/api/result/{job_id}")
            self.assertEqual(pending.get_json(), {"status": "pending"})

            stored[f"job:{job_id}"] = json.dumps(make_job_result("complete", data=analysis)).encode()
            complete = client.get(f"/api/result/{job_id}")
            self.assertEqual(complete.status_code, 200)
            self.assertEqual(complete.get_json()["data"], analysis)

            stored[f"job:{job_id}"] = json.dumps({"status": "complete", "data": {"schema_version": 2}}).encode()
            corrupt = client.get(f"/api/result/{job_id}")
            self.assertEqual(corrupt.status_code, 500)
            self.assertIn("violates the API contract", corrupt.get_json()["error"])


if __name__ == "__main__":
    unittest.main()
