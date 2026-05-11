import asyncio
import json
import subprocess
import threading
import time
from collections import deque
from pathlib import Path
from typing import Callable, Optional

import websockets

from src.video.ffmpeg import resolve_ffmpeg_command


FPS = 15
POLL_INTERVAL_MS = 1000 / FPS
FFMPEG_INPUT_FORMAT = "mjpeg"


class VideoRecorder:
    def __init__(self, output_path: str) -> None:
        self.output_path = str(Path(output_path))
        self._lock = threading.Lock()
        self._process: Optional[subprocess.Popen] = None
        self._ffmpeg_command = resolve_ffmpeg_command()
        self._stderr_lines: deque[str] = deque(maxlen=20)

    def start(self) -> None:
        with self._lock:
            if self._process is not None:
                return

            self._process = subprocess.Popen(
                self._build_command(),
                stdin=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            self._stderr_lines.clear()
            threading.Thread(
                target=self._consume_stderr,
                daemon=True,
            ).start()

            # Fail fast if ffmpeg exits immediately, which is common when the
            # binary is missing dependencies or the chosen encoder is unavailable.
            time.sleep(0.2)
            if self._process.poll() is not None:
                self._process = None
                raise RuntimeError(self._build_process_error())

    def write_frame(self, frame_bytes: bytes) -> None:
        with self._lock:
            if self._process is None or self._process.stdin is None:
                return

            if self._process.poll() is not None:
                self._process = None
                raise RuntimeError(self._build_process_error())

            try:
                self._process.stdin.write(frame_bytes)
                self._process.stdin.flush()
            except BrokenPipeError as exc:
                self._process = None
                raise RuntimeError(self._build_process_error()) from exc

    def stop(self) -> None:
        with self._lock:
            if self._process is None:
                return

            process = self._process

            if process.stdin is not None:
                process.stdin.close()

            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=2)
            finally:
                self._process = None

    def _build_command(self) -> list[str]:
        return [
            self._ffmpeg_command,
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
        ]

    def _consume_stderr(self) -> None:
        process = self._process
        if process is None or process.stderr is None:
            return

        try:
            for line in process.stderr:
                cleaned = line.decode(
                    "utf-8",
                    errors="ignore",
                ).strip()
                if cleaned:
                    self._stderr_lines.append(cleaned)
        except Exception:
            return

    def _build_process_error(self) -> str:
        if self._stderr_lines:
            return "\n".join(self._stderr_lines)
        return "ffmpeg exited before recording could begin."


class VideoStreamer(VideoRecorder):
    def __init__(self, rtmp_url: str, stream_key: str) -> None:
        self._stream_target = self._build_stream_target(
            rtmp_url=rtmp_url,
            stream_key=stream_key,
        )
        super().__init__(self._stream_target)

    def _build_command(self) -> list[str]:
        keyframe_interval = int(FPS * 3)
        return [
            self._ffmpeg_command,
            "-re",
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
            "-f",
            "lavfi",
            "-i",
            "anullsrc=channel_layout=stereo:sample_rate=44100",
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-shortest",
            "-vf",
            "setsar=1",
            "-c:v",
            "libx264",
            "-profile:v",
            "baseline",
            "-level:v",
            "4.0",
            "-pix_fmt",
            "yuv420p",
            "-g",
            str(keyframe_interval),
            "-keyint_min",
            str(keyframe_interval),
            "-sc_threshold",
            "0",
            "-force_key_frames",
            "expr:gte(t,n_forced*3)",
            "-bf",
            "0",
            "-b:v",
            "4000k",
            "-minrate",
            "4000k",
            "-maxrate",
            "4000k",
            "-bufsize",
            "8000k",
            "-x264-params",
            f"nal-hrd=cbr:keyint={keyframe_interval}:min-keyint={keyframe_interval}:scenecut=0",
            "-tune",
            "zerolatency",
            "-c:a",
            "aac",
            "-profile:a",
            "aac_low",
            "-b:a",
            "128k",
            "-ar",
            "44100",
            "-ac",
            "2",
            "-f",
            "flv",
            self.output_path,
        ]

    def _build_process_error(self) -> str:
        if self._stderr_lines:
            return "\n".join(self._stderr_lines)
        return "ffmpeg exited before streaming could begin."

    @staticmethod
    def _build_stream_target(rtmp_url: str, stream_key: str) -> str:
        clean_url = rtmp_url.rstrip("/")
        clean_key = stream_key.lstrip("/")
        return f"{clean_url}/{clean_key}"


async def stream_printer_video(
    printer_ip: str,
    on_frame: Callable[[bytes], None],
    stop_requested: Callable[[], bool],
    on_error: Optional[Callable[[Exception], None]] = None,
) -> None:
    try:
        async with websockets.connect(f"ws://{printer_ip}:8084/") as websocket:
            async def poll() -> None:
                while not stop_requested():
                    await websocket.send(json.dumps({"action": "start"}))
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
