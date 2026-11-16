"""Run ClaudeTeacher through the real anthropic SDK against a local stub server.

Checks the exact HTTP request the SDK sends (no network, no API key, no cost).
"""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

anthropic = pytest.importorskip("anthropic")

from bot_v.teacher.claude import ClaudeTeacher  # noqa: E402


@pytest.fixture
def stub():
    captured, replies = [], []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            captured.append({"path": self.path, "headers": {k.lower(): v for k, v in self.headers.items()},
                             "body": body})
            data = json.dumps(replies.pop(0)).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}", captured, replies
    server.shutdown()


def message(text, stop="end_turn"):
    return {"id": "msg_1", "type": "message", "role": "assistant", "model": "claude-opus-5-5",
            "content": [{"type": "text", "text": text}], "stop_reason": stop, "stop_sequence": None,
            "usage": {"input_tokens": 3, "output_tokens": 2}}


def test_answer_and_review_over_http(stub):
    base_url, captured, replies = stub
    client = anthropic.Anthropic(api_key="test-key", base_url=base_url, max_retries=0)
    teacher = ClaudeTeacher(client=client)

    replies.append(message("Улаанбаатар"))
    assert teacher.answer("Монголын нийслэл?").text == "Улаанбаатар"
    req = captured[-1]
    assert req["path"].startswith("/v1/messages")
    assert "server-side-fallback-2026-07-01" in req["headers"].get("anthropic-beta", "")
    assert req["body"]["fallbacks"] == "default"
    assert req["body"]["model"] == "claude-opus-5-5"
    assert req["body"]["output_config"] == {"effort": "high"}

    replies.append(message(json.dumps(
        {"score": 9, "verdict": "good", "problems": [], "improved_answer": "Улаанбаатар"})))
    review = teacher.review("Монголын нийслэл?", "Улаанбаатар")
    assert review.verdict == "good" and review.score == 9
    assert captured[-1]["body"]["output_config"]["format"]["type"] == "json_schema"
