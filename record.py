import asyncio
import json
import subprocess
import threading
from pathlib import Path
from typing import Callable, Optional

import websockets

FPS = 15
POLL_INTERVAL_MS = 1000 / FPS
FFMPEG_INPUT_FORMAT = "mjpeg"


class VideoRecorder:
    def __init__(self, output_path: str) -> None:
        self.output_path = str(Path(output_path))
        self._lock = threading.Lock()
        self._process: Optional[subprocess.Popen] = None

    def start(self) -> None:
        with self._lock:
            if self._process is not None:
                return

            self._process = subprocess.Popen(
                [
                    "ffmpeg",
                    "-y",
                    "-loglevel",
                    "error",
                    "-f",
                    "image2pipe",
                    "-vcodec",
                    FFMPEG_INPUT_FORMAT,
                    "-r",
                    str(FPS),
                    "-i",
                    "-",
                    "-c:v",
                    "libx264",
                    "-pix_fmt",
                    "yuv420p",
                    self.output_path,
                ],
                stdin=subprocess.PIPE,
            )

    def write_frame(self, frame_bytes: bytes) -> None:
        with self._lock:
            if self._process is None or self._process.stdin is None:
                return

            self._process.stdin.write(frame_bytes)
            self._process.stdin.flush()

    def stop(self) -> None:
        with self._lock:
            if self._process is None:
                return

            if self._process.stdin is not None:
                self._process.stdin.close()

            self._process.wait(timeout=5)
            self._process = None


async def stream_printer_video(
    printer_ip: str,
    on_frame: Callable[[bytes], None],
    stop_requested: Callable[[], bool],
    on_error: Optional[Callable[[Exception], None]] = None,
) -> None:
    try:
        async with websockets.connect(
            f"ws://{printer_ip}:8084/"
        ) as websocket:
            async def poll() -> None:
                while not stop_requested():
                    await websocket.send(
                        json.dumps({"action": "start"})
                    )
                    await asyncio.sleep(POLL_INTERVAL_MS / 1000)

            async def receive() -> None:
                while not stop_requested():
                    data = await websocket.recv()

                    if isinstance(data, str):
                        continue

                    on_frame(data)

            await asyncio.gather(poll(), receive())
    except Exception as exc:
        if on_error is not None and not stop_requested():
            on_error(exc)


def run_printer_video_stream(
    printer_ip: str,
    on_frame: Callable[[bytes], None],
    stop_requested: Callable[[], bool],
    on_error: Optional[Callable[[Exception], None]] = None,
) -> None:
    asyncio.run(
        stream_printer_video(
            printer_ip=printer_ip,
            on_frame=on_frame,
            stop_requested=stop_requested,
            on_error=on_error,
        )
    )


if __name__ == "__main__":
    def print_frame_info(frame_bytes: bytes) -> None:
        print(f"Received frame: {len(frame_bytes)} bytes")

    run_printer_video_stream(
        printer_ip="10.120.8.38",
        on_frame=print_frame_info,
        stop_requested=lambda: False,
    )
