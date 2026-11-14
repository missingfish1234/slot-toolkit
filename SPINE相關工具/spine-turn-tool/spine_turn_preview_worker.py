"""One background raster worker; UI requests never wait for image generation.

Only the newest pending request is kept. Every completed image is still a real
render at its requested full resolution. No Tk object is used on this thread.
"""
from __future__ import annotations

from dataclasses import dataclass
import threading
import time
from typing import Any


@dataclass(frozen=True)
class PreviewResult:
    serial: int
    view_key: tuple
    angle: float
    image: Any = None
    error: str | None = None
    render_seconds: float = 0


class LatestPreviewWorker:
    def __init__(self, renderer):
        self._renderer = renderer
        self._condition = threading.Condition()
        self._pending = None
        self._completed = None
        self._serial = 0
        self._closed = False
        self._thread = threading.Thread(target=self._run, name='SpinePreview', daemon=True)
        self._thread.start()

    def submit(self, view_key, angle, args, kwargs):
        with self._condition:
            if self._closed:
                return self._serial
            self._serial += 1
            self._pending = (self._serial, view_key, angle, args, dict(kwargs))
            self._condition.notify()
            return self._serial

    def take_result(self):
        with self._condition:
            result, self._completed = self._completed, None
            return result

    def close(self):
        with self._condition:
            self._closed = True
            self._pending = self._completed = None
            self._condition.notify()

    def _run(self):
        while True:
            with self._condition:
                while not self._closed and self._pending is None:
                    self._condition.wait()
                if self._closed:
                    return
                serial, key, angle, args, kwargs = self._pending
                self._pending = None
            started = time.perf_counter()
            try:
                result = PreviewResult(serial, key, angle,
                    image=self._renderer(*args, **kwargs),
                    render_seconds=time.perf_counter() - started)
            except Exception as exc:
                result = PreviewResult(serial, key, angle, error=str(exc),
                    render_seconds=time.perf_counter() - started)
            with self._condition:
                if self._closed:
                    return
                self._completed = result
