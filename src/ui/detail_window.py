import threading
import time
from typing import Optional

from PyQt5.QtCore import QObject, Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QFontDatabase, QImage, QPixmap
from PyQt5.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from src.formatters import format_status_details
from src.printers.status import get_printer_status
from src.ui.dialogs import RecordingStopDialog
from src.video.recording import VideoRecorder, run_printer_video_stream


class DetailSignals(QObject):
    status_updated = pyqtSignal(str, str)
    status_failed = pyqtSignal(str)
    frame_updated = pyqtSignal(bytes)
    video_failed = pyqtSignal(str)
    recording_state_changed = pyqtSignal(bool, str)
    stop_recording_requested = pyqtSignal(str)


class PrinterDetailWindow(QWidget):
    def __init__(self, printer: dict) -> None:
        super().__init__()
        self.printer = dict(printer)
        self.stop_event = threading.Event()
        self.recorder: Optional[VideoRecorder] = None
        self.recording_started_at: Optional[float] = None
        self.recording_stop_mode = "manual"
        self.recording_idle_stop_armed = False
        self.last_status_summary: Optional[str] = None
        self.signals = DetailSignals()
        self.signals.status_updated.connect(self._update_status)
        self.signals.status_failed.connect(self._show_status_error)
        self.signals.frame_updated.connect(self._update_video_frame)
        self.signals.video_failed.connect(self._show_video_error)
        self.signals.recording_state_changed.connect(
            self._set_recording_state
        )
        self.signals.stop_recording_requested.connect(
            self._handle_stop_recording_requested
        )

        self.setWindowTitle(f'{self.printer["serial"]} Details')
        self.resize(1100, 720)
        self._build_ui()
        self.recording_timer = QTimer(self)
        self.recording_timer.timeout.connect(
            self._update_recording_duration
        )
        self._start_background_tasks()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        title_row = QHBoxLayout()
        title = QLabel(f'{self.printer["serial"]} ({self.printer["ip"]})')
        title.setStyleSheet("font-size: 20px; font-weight: 600;")
        title_row.addWidget(title)
        title_row.addStretch(1)

        self.recording_indicator = QLabel("\u25cf")
        self.recording_indicator.setStyleSheet(
            "color: #d7263d; font-size: 18px;"
        )
        self.recording_indicator.hide()
        title_row.addWidget(self.recording_indicator)

        self.recording_duration_label = QLabel("00:00:00")
        fixed_font = QFontDatabase.systemFont(QFontDatabase.FixedFont)
        fixed_font.setPointSize(14)
        self.recording_duration_label.setFont(fixed_font)
        self.recording_duration_label.hide()
        title_row.addWidget(self.recording_duration_label)

        self.record_button = QPushButton("Start recording")
        self.record_button.clicked.connect(self._toggle_recording)
        title_row.addWidget(self.record_button)
        layout.addLayout(title_row)

        self.summary_label = QLabel("Loading status...")
        layout.addWidget(self.summary_label)

        splitter = QSplitter(Qt.Horizontal)
        layout.addWidget(splitter, 1)

        self.status_text = QTextEdit()
        self.status_text.setReadOnly(True)
        self.status_text.setPlainText("Waiting for status...")
        splitter.addWidget(self.status_text)

        video_panel = QWidget()
        video_layout = QVBoxLayout(video_panel)
        video_layout.setContentsMargins(0, 0, 0, 0)

        self.video_status_label = QLabel("Connecting to live video...")
        video_layout.addWidget(self.video_status_label)

        self.video_label = QLabel()
        self.video_label.setAlignment(Qt.AlignCenter)
        self.video_label.setMinimumSize(480, 320)
        self.video_label.setStyleSheet(
            "background: #111; color: #ddd; border: 1px solid #555;"
        )
        self.video_label.setText("Waiting for video...")
        video_layout.addWidget(self.video_label, 1)

        splitter.addWidget(video_panel)
        splitter.setSizes([520, 520])

    def _start_background_tasks(self) -> None:
        threading.Thread(target=self._poll_status_loop, daemon=True).start()
        threading.Thread(target=self._run_video_stream, daemon=True).start()

    def _poll_status_loop(self) -> None:
        while not self.stop_event.is_set():
            try:
                status_response = get_printer_status(self.printer["ip"])
                summary = (
                    "Printing"
                    if status_response["Parameters"]["isPrinting"]
                    else "Idle"
                )
                details = format_status_details(
                    self.printer,
                    status_response,
                )
                self.signals.status_updated.emit(summary, details)
            except Exception as exc:
                self.signals.status_failed.emit(str(exc))

            if self.stop_event.wait(2.0):
                break

    def _run_video_stream(self) -> None:
        run_printer_video_stream(
            printer_ip=self.printer["ip"],
            on_frame=self._handle_video_frame,
            stop_requested=self.stop_event.is_set,
            on_error=lambda exc: self.signals.video_failed.emit(str(exc)),
        )

    def _handle_video_frame(self, frame: bytes) -> None:
        if self.recorder is not None:
            try:
                self.recorder.write_frame(frame)
            except Exception as exc:
                recorder = self.recorder
                self.recorder = None

                if recorder is not None:
                    try:
                        recorder.stop()
                    except Exception:
                        pass

                self.signals.recording_state_changed.emit(False, "")
                self.signals.video_failed.emit(f"Recording failed: {exc}")

        self.signals.frame_updated.emit(frame)

    def _update_status(self, summary: str, details: str) -> None:
        self.summary_label.setText(f"Status: {summary}")
        self.status_text.setPlainText(details)

        if (
            self.recorder is not None
            and self.recording_stop_mode == "until_idle"
        ):
            if summary != "Idle":
                self.recording_idle_stop_armed = True
            elif (
                self.recording_idle_stop_armed
                and self.last_status_summary is not None
                and self.last_status_summary != "Idle"
            ):
                self.signals.stop_recording_requested.emit(
                    "Recording stopped automatically when the printer became idle."
                )

        self.last_status_summary = summary

    def _show_status_error(self, message: str) -> None:
        self.summary_label.setText("Status: Unknown")
        self.status_text.setPlainText(f"Status fetch failed:\n{message}")

    def _update_video_frame(self, frame_bytes: bytes) -> None:
        image = QImage.fromData(frame_bytes)
        if image.isNull():
            return

        pixmap = QPixmap.fromImage(image)
        scaled = pixmap.scaled(
            self.video_label.size(),
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation,
        )
        self.video_label.setPixmap(scaled)
        self.video_status_label.setText("Live video")

    def _show_video_error(self, message: str) -> None:
        self.video_status_label.setText(f"Video unavailable: {message}")

    def _toggle_recording(self) -> None:
        if self.recorder is None:
            self._start_recording()
            return

        self._stop_recording()

    def _start_recording(self) -> None:
        default_filename = f'{self.printer["serial"]}.mp4'
        status_response = None

        try:
            status_response = get_printer_status(self.printer["ip"])
            job_guid = status_response["Parameters"]["printingJobGuid"]
            if job_guid:
                default_filename = (
                    f'{self.printer["serial"]}_{job_guid}.mp4'
                )
        except Exception:
            pass

        output_path, _selected_filter = QFileDialog.getSaveFileName(
            self,
            "Save Recording",
            default_filename,
            "MP4 Video (*.mp4)",
        )

        if not output_path:
            return

        stop_dialog = RecordingStopDialog(self)
        if stop_dialog.exec_() != RecordingStopDialog.Accepted:
            return

        try:
            recorder = VideoRecorder(output_path)
            recorder.start()
        except Exception as exc:
            self.video_status_label.setText(f"Recording unavailable: {exc}")
            return

        self.recorder = recorder
        self.recording_started_at = time.time()
        self.recording_stop_mode = stop_dialog.selected_mode()
        self.recording_idle_stop_armed = False

        if (
            self.recording_stop_mode == "until_idle"
            and status_response is not None
            and status_response["Parameters"]["isPrinting"]
        ):
            self.recording_idle_stop_armed = True

        self.signals.recording_state_changed.emit(
            True,
            f"Recording to {output_path}",
        )

    def _stop_recording(self, status_message: str = "Live video") -> None:
        recorder = self.recorder
        self.recorder = None
        self.recording_started_at = None
        self.recording_stop_mode = "manual"
        self.recording_idle_stop_armed = False

        if recorder is not None:
            try:
                recorder.stop()
            except Exception as exc:
                self.video_status_label.setText(
                    f"Recording stop failed: {exc}"
                )

        self.signals.recording_state_changed.emit(False, status_message)

    def _handle_stop_recording_requested(self, status_message: str) -> None:
        if self.recorder is None:
            return
        self._stop_recording(status_message)

    def _set_recording_state(
        self,
        is_recording: bool,
        status_text: str,
    ) -> None:
        self.recording_indicator.setVisible(is_recording)
        self.recording_duration_label.setVisible(is_recording)
        self.record_button.setText(
            "Stop recording" if is_recording else "Start recording"
        )

        if is_recording:
            self.recording_duration_label.setText("00:00:00")
            self.recording_timer.start(1000)
        else:
            self.recording_timer.stop()
            self.recording_duration_label.setText("00:00:00")

        if status_text:
            self.video_status_label.setText(status_text)

    def _update_recording_duration(self) -> None:
        if self.recording_started_at is None:
            self.recording_duration_label.setText("00:00:00")
            return

        elapsed_seconds = max(0, int(time.time() - self.recording_started_at))
        hours = elapsed_seconds // 3600
        minutes = (elapsed_seconds % 3600) // 60
        seconds = elapsed_seconds % 60
        self.recording_duration_label.setText(
            f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        )

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        pixmap = self.video_label.pixmap()
        if pixmap is None:
            return

        self.video_label.setPixmap(
            pixmap.scaled(
                self.video_label.size(),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )
        )

    def closeEvent(self, event) -> None:
        self.stop_event.set()
        self._stop_recording()
        super().closeEvent(event)
