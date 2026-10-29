"""Exercise the real compile-request method without binding or running tools."""
import ast
import io
import json
from pathlib import Path
import threading
import unittest
from urllib.parse import urlparse

SERVER = Path(__file__).resolve().parents[1] / "src/siliconpilot/server.py"


def request_method():
    tree = ast.parse(SERVER.read_text())
    serve = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "serve")
    handler = next(n for n in serve.body if isinstance(n, ast.ClassDef) and n.name == "Handler")
    post = next(n for n in handler.body if isinstance(n, ast.FunctionDef) and n.name == "do_POST")
    gate = threading.Lock()
    namespace = {"json": json, "urlparse": urlparse, "port": 8791, "gate": gate, "root": Path("synthetic-model-root")}
    exec(compile(ast.Module(body=[post], type_ignores=[]), str(SERVER), "exec"), namespace)
    return namespace["do_POST"], gate


class FakeRequest:
    def __init__(self, body, **headers):
        self.path = "/api/compile"
        self.rfile = io.BytesIO(body)
        self.headers = {"Host": "127.0.0.1:8791", "Content-Length": str(len(body)), **headers}
        self.response = None

    def json_response(self, value, status=200):
        self.response = status, value

    def send_error(self, status):
        self.response = status, None


class CompileJSONTests(unittest.TestCase):
    def test_non_object_json_returns_client_error_and_releases_gate(self):
        for value in (None, True, False, 0, 12.5, "model", [], ["model"]):
            with self.subTest(value=value):
                post, gate = request_method()
                request = FakeRequest(json.dumps(value).encode())
                post(request)
                self.assertEqual(request.response, (400, {"error": "JSON object required"}))
                self.assertFalse(gate.locked())

    def test_object_keeps_existing_unknown_model_error(self):
        post, gate = request_method()
        request = FakeRequest(b'{"model_id":"unknown"}')
        post(request)
        self.assertEqual(request.response, (400, {"error": "Unknown packaged model"}))
        self.assertFalse(gate.locked())

    def test_malformed_json_keeps_client_error_and_releases_gate(self):
        post, gate = request_method()
        request = FakeRequest(b'{')
        post(request)
        self.assertEqual(request.response[0], 400)
        self.assertFalse(gate.locked())

    def test_cross_origin_refusal_precedes_body_read(self):
        post, gate = request_method()
        request = FakeRequest(b'[]', Origin="https://external.invalid")
        post(request)
        self.assertEqual(request.response[0], 403)
        self.assertEqual(request.rfile.tell(), 0)
        self.assertFalse(gate.locked())

    def test_busy_refusal_precedes_body_read(self):
        post, gate = request_method()
        gate.acquire()
        try:
            request = FakeRequest(b'[]')
            post(request)
            self.assertEqual(request.response[0], 409)
            self.assertEqual(request.rfile.tell(), 0)
            self.assertTrue(gate.locked())
        finally:
            gate.release()


if __name__ == "__main__":
    unittest.main()
