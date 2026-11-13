"""Tests for core.instance — one desktop app per user."""

from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from pathlib import Path
import subprocess
import sys
import threading
import time

import pytest

from core import instance

_REPO_ROOT = Path(__file__).parent.parent.parent


class TestAcquire:
    def test_the_first_caller_owns_the_app(self, tmp_path: Path):
        lock = instance.acquire(tmp_path)
        assert lock is not None
        lock.release()

    def test_a_second_caller_is_refused_while_the_first_holds_it(self, tmp_path: Path):
        first = instance.acquire(tmp_path)
        try:
            assert instance.acquire(tmp_path) is None
        finally:
            first.release()

    def test_release_lets_the_next_launch_own_it(self, tmp_path: Path):
        instance.acquire(tmp_path).release()
        again = instance.acquire(tmp_path)
        assert again is not None
        again.release()

    def test_a_killed_owner_leaves_no_stale_lock(self, tmp_path: Path):
        """An OS lock dies with its process; a crash must not block the next start."""
        code = (
            "import sys, time; sys.path.insert(0, sys.argv[1]);"
            "from pathlib import Path; from core import instance;"
            "lock = instance.acquire(Path(sys.argv[2])); print('locked' if lock else 'refused', flush=True);"
            "time.sleep(60)"
        )
        owner = subprocess.Popen(
            [sys.executable, "-c", code, str(_REPO_ROOT), str(tmp_path)], stdout=subprocess.PIPE, text=True
        )
        try:
            assert owner.stdout.readline().strip() == "locked"
            assert instance.acquire(tmp_path) is None
        finally:
            owner.kill()
            owner.wait()
        # Windows frees a dead process's locks asynchronously, within a moment.
        deadline = time.monotonic() + 5.0
        survivor = instance.acquire(tmp_path)
        while survivor is None and time.monotonic() < deadline:
            time.sleep(0.05)
            survivor = instance.acquire(tmp_path)
        assert survivor is not None
        survivor.release()


class TestRecord:
    def test_publish_records_the_port_and_release_removes_it(self, tmp_path: Path):
        lock = instance.acquire(tmp_path)
        lock.publish(57201)
        assert json.loads((tmp_path / "instance.json").read_text(encoding="utf-8"))["port"] == 57201
        lock.release()
        assert not (tmp_path / "instance.json").exists()


@pytest.fixture
def owner_server():
    """A loopback HTTP server standing in for the running app's show endpoint."""
    calls: list[str] = []
    answer = {"app": instance.APP_ID, "ok": True}

    class _Handler(BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802
            calls.append(self.path)
            body = json.dumps(answer).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_args):
            pass

    server = HTTPServer(("127.0.0.1", 0), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield server.server_address[1], calls, answer
    server.shutdown()


class TestShowRunningInstance:
    def test_asks_the_owner_on_its_recorded_port(self, tmp_path: Path, owner_server):
        port, calls, _ = owner_server
        (tmp_path / "instance.json").write_text(json.dumps({"pid": 1, "port": port}), encoding="utf-8")
        assert instance.show_running_instance(tmp_path, wait=0) is True
        assert calls == [instance.SHOW_PATH]

    def test_something_else_on_that_port_is_not_the_app(self, tmp_path: Path, owner_server):
        port, _, answer = owner_server
        answer["app"] = "someone-else"
        (tmp_path / "instance.json").write_text(json.dumps({"pid": 1, "port": port}), encoding="utf-8")
        assert instance.show_running_instance(tmp_path, wait=0) is False

    def test_no_record_means_no_answer(self, tmp_path: Path):
        assert instance.show_running_instance(tmp_path, wait=0) is False

    def test_waits_for_an_owner_that_is_still_starting(self, tmp_path: Path, owner_server):
        """A double-click launches twice; the first may not have published yet."""
        port, _, _ = owner_server
        timer = threading.Timer(
            0.3,
            lambda: (tmp_path / "instance.json").write_text(json.dumps({"pid": 1, "port": port}), encoding="utf-8"),
        )
        timer.start()
        try:
            assert instance.show_running_instance(tmp_path, wait=5.0, poll=0.05) is True
        finally:
            timer.cancel()
