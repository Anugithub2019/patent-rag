import json
import os
import socket
import subprocess
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
VALID_ANALYSIS = json.loads(
    (ROOT / "tests" / "fixtures" / "analysis-v2.valid.json").read_text(encoding="utf-8")
)
RAW_HASHTAG_RESPONSE = {
    "answer": json.dumps(VALID_ANALYSIS),
    "info": {"mode": "graph_vector_fulltext", "retrieved_nodes": 3},
}


class HashtagStubHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", "0"))
        self.rfile.read(content_length)
        body = json.dumps(RAW_HASHTAG_RESPONSE).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args):
        pass


class NodeDebugRawResponseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.hashtag_stub = ThreadingHTTPServer(("127.0.0.1", 0), HashtagStubHandler)
        cls.hashtag_thread = threading.Thread(target=cls.hashtag_stub.serve_forever, daemon=True)
        cls.hashtag_thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.hashtag_stub.shutdown()
        cls.hashtag_stub.server_close()
        cls.hashtag_thread.join(timeout=2)

    def start_node_server(self, *, debug):
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]

        environment = os.environ.copy()
        environment.update(
            {
                "PORT": str(port),
                "HASHTAG_API_KEY": "test-key",
                "HASHTAG_BASE_URL": f"http://127.0.0.1:{self.hashtag_stub.server_port}",
                "HASHTAG_NAMESPACE": "test-namespace",
                "HASHTAG_CORPUS_NAME": "test-corpus",
                "DEBUG_INVALID_REPORTS": "true" if debug else "false",
            }
        )
        process = subprocess.Popen(
            ["node", "servers/node_server.mjs"],
            cwd=ROOT,
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        self.addCleanup(self.stop_process, process)

        health_url = f"http://127.0.0.1:{port}/api/health"
        for _ in range(100):
            if process.poll() is not None:
                output = process.stdout.read() if process.stdout else ""
                self.fail(f"Node server exited during startup:\n{output}")
            try:
                with urlopen(health_url, timeout=0.2) as response:
                    if response.status == 200:
                        return port
            except (HTTPError, URLError, TimeoutError):
                time.sleep(0.02)

        self.fail("Node server did not become ready")

    @staticmethod
    def stop_process(process):
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2)
        if process.stdout:
            process.stdout.close()

    def submit_and_wait(self, port):
        request = Request(
            f"http://127.0.0.1:{port}/api/query",
            data=json.dumps({"text": "A controller and two contacts"}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=2) as response:
            job_id = json.load(response)["job_id"]

        result_url = f"http://127.0.0.1:{port}/api/result/{job_id}"
        for _ in range(100):
            with urlopen(result_url, timeout=2) as response:
                result = json.load(response)
            if result["status"] != "pending":
                return job_id, result
            time.sleep(0.02)
        self.fail("Node query did not complete")

    def test_debug_mode_exposes_raw_success_response_without_changing_job_contract(self):
        port = self.start_node_server(debug=True)
        job_id, result = self.submit_and_wait(port)

        self.assertEqual(set(result), {"status", "data"})
        self.assertEqual(result["status"], "complete")
        with urlopen(f"http://127.0.0.1:{port}/api/result/{job_id}/raw", timeout=2) as response:
            raw_result = json.load(response)
        self.assertEqual(raw_result, {"upstream_response": RAW_HASHTAG_RESPONSE})

    def test_normal_mode_hides_raw_response_route(self):
        port = self.start_node_server(debug=False)
        job_id, result = self.submit_and_wait(port)

        self.assertEqual(result["status"], "complete")
        with self.assertRaises(HTTPError) as raised:
            urlopen(f"http://127.0.0.1:{port}/api/result/{job_id}/raw", timeout=2)
        self.assertEqual(raised.exception.code, 404)


if __name__ == "__main__":
    unittest.main()
