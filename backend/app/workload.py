"""Bound expensive work on the small single-process deployment; no job queue."""
from contextlib import contextmanager
import os
from .config import env
from threading import BoundedSemaphore

from fastapi import HTTPException


def _limit(name, default=2):
    try:
        return max(1, min(8, int(env(name, str(default)))))
    except ValueError:
        return default


SOLVER_SLOTS = BoundedSemaphore(_limit('OPTIDAY_CONCURRENT_SOLVES'))
MODEL_SLOTS = BoundedSemaphore(_limit('OPTIDAY_CONCURRENT_MODEL_CALLS'))


@contextmanager
def admitted(slots, label):
    if not slots.acquire(blocking=False):
        raise HTTPException(429, f'{label}正在处理其他请求，请稍后重试。当前输入与计划会保留。',
                            headers={'Retry-After': '3'})
    try:
        yield
    finally:
        slots.release()
