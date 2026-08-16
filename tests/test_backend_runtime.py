import os
import unittest
from copy import deepcopy
from unittest.mock import patch


os.environ.setdefault("HASHTAG_API_KEY", "test-key")

from backend.celery_app import app as celery_app
from servers.flask_server import app as flask_app


VALID_ANALYSIS = {
    "schema_version": 2,
    "overall_assessment": {
        "status": "inconclusive",
        "summary": "The retrieved context is insufficient.",
    },
    "features": [
        {
            "feature_id": 1,
            "feature_text": "A controller coupled to two contacts.",
            "matches": [],
        }
    ],
}


class CeleryTaskRegistrationTests(unittest.TestCase):
    def test_worker_default_imports_register_process_query(self):
        self.assertIn("backend.tasks", celery_app.conf.include)

        celery_app.loader.import_default_modules()

        self.assertIn("backend.tasks.process_query", celery_app.tasks)


class FlaskLegacySearchTests(unittest.TestCase):
    @patch("backend.hashtag_client.requests.post")
    def test_search_uses_shared_structured_query_client(self, mock_post):
        upstream = deepcopy(VALID_ANALYSIS)
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = upstream

        client = flask_app.test_client()
        response = client.post(
            "/api/search",
            json={"text": "  A controller coupled to two contacts.  "},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), VALID_ANALYSIS)
        mock_post.assert_called_once()
        request_kwargs = mock_post.call_args.kwargs
        self.assertEqual(request_kwargs["timeout"], 120)
        self.assertIn("Return ONLY valid JSON", request_kwargs["json"]["question"])
        self.assertTrue(
            request_kwargs["json"]["question"].endswith(
                "Technology disclosure:\nA controller coupled to two contacts."
            )
        )

    def test_search_rejects_blank_text_before_calling_upstream(self):
        client = flask_app.test_client()

        with patch("backend.hashtag_client.requests.post") as mock_post:
            response = client.post("/api/search", json={"text": "   "})

        self.assertEqual(response.status_code, 400)
        mock_post.assert_not_called()


if __name__ == "__main__":
    unittest.main()
