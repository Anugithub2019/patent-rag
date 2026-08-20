import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("HASHTAG_API_KEY", "test-key")

from kg_builder import db, uploader


class UploaderConfigurationTests(unittest.TestCase):
    def test_uploader_destination_comes_from_uploader_config(self):
        self.assertEqual(uploader.CORPUS_DESTINATION, "rsongnov/patents_5530")

    @patch("kg_builder.uploader.requests.post")
    def test_upload_uses_configured_destination(self, mock_post):
        mock_post.return_value.status_code = 200

        self.assertTrue(uploader.upload("patent text"))

        self.assertEqual(
            mock_post.call_args.args[0],
            "https://kg-api.hashtag.ai/rsongnov/patents_5530/process",
        )
        self.assertEqual(mock_post.call_args.kwargs["timeout"], 600)

    def test_configured_input_directory_resolves_from_project_root(self):
        self.assertEqual(
            Path(uploader.INPUT_DIR),
            Path(uploader.PROJECT_ROOT) / "data" / "patents_5530",
        )

    @patch("kg_builder.uploader.requests.post")
    def test_upload_uses_corpus_as_url_path(self, mock_post):
        mock_post.return_value.status_code = 200

        self.assertTrue(
            uploader.upload("patent text", corpus="toy_project", namespace="rsongnov")
        )

        self.assertEqual(
            mock_post.call_args.args[0],
            "https://kg-api.hashtag.ai/rsongnov/toy_project/process",
        )

    @patch("kg_builder.uploader.requests.post")
    def test_upload_url_encodes_corpus_name(self, mock_post):
        mock_post.return_value.status_code = 200

        self.assertTrue(
            uploader.upload("patent text", corpus="toy project", namespace="r song")
        )

        self.assertEqual(
            mock_post.call_args.args[0],
            "https://kg-api.hashtag.ai/r%20song/toy%20project/process",
        )


class UploaderWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.input_dir = Path(self.temp_dir.name) / "input"
        self.input_dir.mkdir()
        self.patent_path = self.input_dir / "patent.txt"
        self.patent_text = "A test patent disclosure."
        self.patent_path.write_text(self.patent_text, encoding="utf-8")
        self.original_db_path = db.DB_PATH
        db.DB_PATH = str(Path(self.temp_dir.name) / "upload_records.db")
        db.init_db()

    def tearDown(self):
        db.DB_PATH = self.original_db_path
        self.temp_dir.cleanup()

    @patch("kg_builder.uploader.upload")
    def test_main_posts_only_after_acquiring_claim(self, mock_upload):
        encoded = self.patent_text.encode("utf-8")
        db.claim_upload(
            file_name="patent.txt",
            file_path=str(self.patent_path),
            file_hash=uploader.text_hash(self.patent_text),
            file_size=len(encoded),
            corpus=uploader.CORPUS_DESTINATION,
        )

        with patch.object(uploader, "INPUT_DIR", str(self.input_dir)):
            uploader.main()

        mock_upload.assert_not_called()

    @patch("kg_builder.uploader.upload", return_value=True)
    def test_main_records_successful_claim(self, mock_upload):
        with patch.object(uploader, "INPUT_DIR", str(self.input_dir)):
            uploader.main()

        mock_upload.assert_called_once_with(self.patent_text)
        self.assertTrue(
            db.is_uploaded(
                uploader.text_hash(self.patent_text),
                uploader.CORPUS_DESTINATION,
            )
        )


if __name__ == "__main__":
    unittest.main()
