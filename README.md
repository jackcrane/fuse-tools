# fuse-tools

Simple desktop tools for discovering compatible printers on your network recording video feeds.

> [!IMPORTANT]
> Start this application from a standalone terminal window, not from VSCode's embedded terminal.
> On macOS, use the Terminal app.
> On Windows, use Command Prompt.

## Requirements

- Python 3.10 or newer
- `pip`
- Network access to the printers you want to discover
- `ffmpeg` for video recording or streaming features

Notes on ffmpeg:

- On Windows, the app can automatically download `ffmpeg` if it is missing.
- On Intel macOS, the app can also download `ffmpeg` automatically if it is missing.
- On Apple Silicon macOS, install `ffmpeg` manually and make sure it is available on your `PATH`.

## Install

1. Clone this repository.
2. Open a standalone terminal window in the project folder.
3. Install the Python dependencies:

```bash
python -m pip install -r requirements.txt
```

If `python` does not point to Python 3 on your machine, use `python3` instead.

## Start

### macOS / Linux

```bash
python main.py
```

If needed:

```bash
python3 main.py
```

### Windows

```bat
start.bat
```