"""A model response cannot hold admission forever by sending keep-alive bytes."""
from contextlib import contextmanager
import socket
from threading import Event, Timer
from time import monotonic

import httpx


@contextmanager
def model_client(timeout):
    deadline = monotonic() + timeout
    expired = Event()
    timers = []

    def on_response(response):
        stream = response.extensions.get('network_stream')
        connection = stream.get_extra_info('socket') if stream is not None else None

        def interrupt():
            expired.set()
            if connection is not None:
                try:
                    connection.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass

        remaining = deadline - monotonic()
        if remaining <= 0:
            interrupt()
            raise httpx.ReadTimeout('模型请求达到总等待时限。')
        timer = Timer(remaining, interrupt)
        timer.daemon = True
        timers.append(timer)
        timer.start()

    # Header/connect waits are bounded too; a response hook handles bodies that
    # keep the ordinary inactivity timeout alive by sending whitespace.
    limits = httpx.Timeout(timeout, connect=min(timeout, 10), write=min(timeout, 10), pool=min(timeout, 10))
    try:
        with httpx.Client(timeout=limits, event_hooks={'response': [on_response]}) as client:
            try:
                yield client
            except (httpx.HTTPError, OSError, ValueError) as exc:
                if expired.is_set():
                    raise httpx.ReadTimeout('模型请求达到总等待时限。') from exc
                raise
    finally:
        for timer in timers:
            timer.cancel()
