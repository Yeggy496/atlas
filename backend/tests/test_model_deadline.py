from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from time import monotonic, sleep

import httpx
import pytest

from app.llm.model_http import model_client


class KeepAlive(BaseHTTPRequestHandler):
    def do_POST(self):
        self.rfile.read(int(self.headers.get('Content-Length', '0')))
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        try:
            for _ in range(60):
                self.wfile.write(b' ')
                self.wfile.flush()
                sleep(.02)
            self.wfile.write(b'{"ok":true}')
        except (BrokenPipeError, ConnectionResetError):
            pass

    def log_message(self, *args):
        pass


def test_keepalive_bytes_do_not_extend_the_model_deadline():
    server = ThreadingHTTPServer(('127.0.0.1', 0), KeepAlive)
    server.daemon_threads = True
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        started = monotonic()
        with pytest.raises(httpx.TimeoutException):
            with model_client(.2) as client:
                client.post(f'http://127.0.0.1:{server.server_port}', json={'request': 'test'})
        assert monotonic() - started < 1, 'Periodic keep-alive bytes must not hold the slot indefinitely'
        # A subsequent fresh request still works: the timer closes only its own socket.
        with model_client(3) as client:
            assert client.post(f'http://127.0.0.1:{server.server_port}', json={}).json() == {'ok': True}
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
