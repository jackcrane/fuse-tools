import asyncio
import websockets
import subprocess
import json

FPS = 15
POLL_INTERVAL_MS = 1000 / FPS

FFMPEG_CMD = [
    "ffmpeg",
    "-y",
    "-loglevel", "info",
    "-f", "image2pipe",
    "-vcodec", "mjpeg",
    "-r", str(FPS),
    "-i", "-",
    "-c:v", "libx264",
    "-pix_fmt", "yuv420p",
    "output.mp4"
]

async def main():
    print("Starting FFmpeg...")
    ffmpeg = subprocess.Popen(
        FFMPEG_CMD,
        stdin=subprocess.PIPE
    )

    print("Connecting to WebSocket...")
    async with websockets.connect("ws://10.120.8.38:8084/") as ws:
        print("Connected!")

        async def poll():
            while True:
                await ws.send(json.dumps({"action": "start"}))
                await asyncio.sleep(POLL_INTERVAL_MS / 1000)

        async def receive():
            frame = 0
            while True:
                data = await ws.recv()

                if isinstance(data, str):
                    continue

                frame += 1

                ffmpeg.stdin.write(data)
                ffmpeg.stdin.flush()

        await asyncio.gather(poll(), receive())

asyncio.run(main())