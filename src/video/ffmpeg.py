import hashlib
import os
import shutil
import tempfile
import threading
import urllib.error
import urllib.request
import zipfile
from pathlib import Path


WINDOWS_FFMPEG_URL = (
    "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
)
WINDOWS_FFMPEG_SHA256_URL = f"{WINDOWS_FFMPEG_URL}.sha256"
DOWNLOAD_TIMEOUT_SECONDS = 120
_DOWNLOAD_LOCK = threading.Lock()


def resolve_ffmpeg_command() -> str:
    command = shutil.which("ffmpeg")
    if command is None and os.name == "nt":
        command = shutil.which("ffmpeg.exe")

    if command is not None:
        return command

    bundled_command = _bundled_ffmpeg_path()
    if bundled_command.exists():
        return str(bundled_command)

    if os.name == "nt":
        return str(_ensure_windows_ffmpeg())

    raise RuntimeError(
        "ffmpeg was not found. Install ffmpeg and add it to PATH."
    )


def _ensure_windows_ffmpeg() -> Path:
    target_path = _bundled_ffmpeg_path()
    if target_path.exists():
        return target_path

    with _DOWNLOAD_LOCK:
        if target_path.exists():
            return target_path

        target_path.parent.mkdir(parents=True, exist_ok=True)

        with tempfile.TemporaryDirectory(
            prefix="fuse-tools-ffmpeg-",
        ) as temp_dir:
            archive_path = Path(temp_dir) / "ffmpeg-release-essentials.zip"
            _download_file(WINDOWS_FFMPEG_URL, archive_path)
            _verify_archive_checksum(archive_path)
            _extract_ffmpeg_executable(archive_path, target_path)

        return target_path


def _bundled_ffmpeg_path() -> Path:
    return Path.home() / ".fuse-tools" / "ffmpeg" / "ffmpeg.exe"


def _download_file(url: str, destination: Path) -> None:
    try:
        with urllib.request.urlopen(
            url,
            timeout=DOWNLOAD_TIMEOUT_SECONDS,
        ) as response:
            destination.write_bytes(response.read())
    except urllib.error.URLError as exc:
        raise RuntimeError(
            f"Unable to download ffmpeg from {url}: {exc}"
        ) from exc


def _verify_archive_checksum(archive_path: Path) -> None:
    try:
        with urllib.request.urlopen(
            WINDOWS_FFMPEG_SHA256_URL,
            timeout=DOWNLOAD_TIMEOUT_SECONDS,
        ) as response:
            expected_checksum = response.read().decode(
                "utf-8",
                errors="ignore",
            ).strip().split()[0]
    except urllib.error.URLError:
        return

    actual_checksum = hashlib.sha256(archive_path.read_bytes()).hexdigest()
    if actual_checksum.lower() != expected_checksum.lower():
        raise RuntimeError("Downloaded ffmpeg archive failed checksum verification.")


def _extract_ffmpeg_executable(
    archive_path: Path,
    target_path: Path,
) -> None:
    try:
        with zipfile.ZipFile(archive_path) as archive:
            ffmpeg_member = next(
                (
                    name
                    for name in archive.namelist()
                    if name.lower().endswith("/bin/ffmpeg.exe")
                ),
                None,
            )

            if ffmpeg_member is None:
                raise RuntimeError(
                    "Downloaded ffmpeg archive did not contain bin/ffmpeg.exe."
                )

            with archive.open(ffmpeg_member) as source:
                temporary_target = target_path.with_suffix(".tmp")
                with temporary_target.open("wb") as destination:
                    shutil.copyfileobj(source, destination)
                temporary_target.replace(target_path)
    except zipfile.BadZipFile as exc:
        raise RuntimeError(
            "Downloaded ffmpeg archive was not a valid ZIP file."
        ) from exc
