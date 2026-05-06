import signal
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

from PyQt5.QtCore import QObject, Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QImage, QPixmap
from PyQt5.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QProgressBar,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from discover_printers import DEFAULT_SUBNETS, discover_printers
from printer_status import get_printer_status
from record import run_printer_video_stream


def format_status_details(printer: dict, status_response: dict) -> str:
    parameters = status_response["Parameters"]
    cylinder_last_print = parameters["cylinderLastPrint"]
    cylinder_tracking = parameters["cylinderTracking"]
    running_jobs = parameters["currentlyRunningJobHeights"]

    lines = [
        f'Serial: {printer["serial"]}',
        f'IP Address: {printer["ip"]}',
        f'Machine Type: {printer["machineTypeId"]}',
        f'Status: {"Printing" if parameters["isPrinting"] else "Idle"}',
        f'Accepting Jobs: {parameters["isAcceptingJobs"]}',
        f'Primed: {parameters["isPrimed"]}',
        f'Bed Temperature (C): {parameters["bedTemperature_C"]:.2f}',
        f'Powder Level: {parameters["powderLevel"]}',
        f'Material: {parameters["printerMaterial"]}',
        f'Material Credit (g): {parameters["materialCredit_g"]}',
        f'Printing Layer: {parameters["printingLayer"]}',
        (
            "Estimated Time Remaining (min): "
            f'{parameters["estimatedPrintTimeRemaining_ms"] / 60000:.1f}'
        ),
        f'Printing Job GUID: {parameters["printingJobGuid"]}',
        f'Job Revision: {parameters["printingJobRevision"]}',
        f'Cylinder Serial: {parameters["cylinderSerial"]}',
        f'Cylinder Material: {parameters["cylinderMaterialCode"]}',
        f'Cylinder Z Range (mm): {parameters["cylinderZAxisRange_mm"]}',
        (
            "Cylinder Last Print: "
            f'{cylinder_last_print["printGuid"]}'
        ),
        (
            "Last Print Progress: "
            f'{cylinder_last_print["layersPrinted"]}/'
            f'{cylinder_last_print["totalLayers"]} layers'
        ),
        f'Last Print Updated: {cylinder_last_print["metadataUpdateTimestamp"]}',
        (
            "Tracking Layers: "
            f'{cylinder_tracking["numberOfLayers"]}'
        ),
        (
            "Tracking Travel (mm): "
            f'{cylinder_tracking["totalTravel_mm"]:.2f}'
        ),
        f"Running Jobs: {len(running_jobs)}",
        f'Issues: {len(parameters["printerIssues"])}',
    ]

    if running_jobs:
        first_job = running_jobs[0]
        lines.extend(
            [
                f'Current Job GUID: {first_job["jobGuid"]}',
                (
                    "Core Print Height (mm): "
                    f'{first_job["heightCorePrint_mm"]}'
                ),
                (
                    "Hot Precoats Height (mm): "
                    f'{first_job["heightHotPrecoats_mm"]}'
                ),
            ]
        )

    return "\n".join(lines)


class AppSignals(QObject):
    discovery_complete = pyqtSignal(list)
    discovery_failed = pyqtSignal(str)


class DetailSignals(QObject):
    status_updated = pyqtSignal(str, str)
    status_failed = pyqtSignal(str)
    frame_updated = pyqtSignal(bytes)
    video_failed = pyqtSignal(str)


class PrinterDetailWindow(QWidget):
    def __init__(self, printer: dict) -> None:
        super().__init__()
        self.printer = dict(printer)
        self.stop_event = threading.Event()
        self.signals = DetailSignals()
        self.signals.status_updated.connect(self._update_status)
        self.signals.status_failed.connect(self._show_status_error)
        self.signals.frame_updated.connect(self._update_video_frame)
        self.signals.video_failed.connect(self._show_video_error)

        self.setWindowTitle(f'{self.printer["serial"]} Details')
        self.resize(1100, 720)
        self._build_ui()
        self._start_background_tasks()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        title = QLabel(
            f'{self.printer["serial"]} ({self.printer["ip"]})'
        )
        title.setStyleSheet("font-size: 20px; font-weight: 600;")
        layout.addWidget(title)

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
        threading.Thread(
            target=self._poll_status_loop,
            daemon=True,
        ).start()
        threading.Thread(
            target=self._run_video_stream,
            daemon=True,
        ).start()

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
            on_frame=lambda frame: self.signals.frame_updated.emit(frame),
            stop_requested=self.stop_event.is_set,
            on_error=lambda exc: self.signals.video_failed.emit(str(exc)),
        )

    def _update_status(self, summary: str, details: str) -> None:
        self.summary_label.setText(f"Status: {summary}")
        self.status_text.setPlainText(details)

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
        super().closeEvent(event)


class PrinterDiscoveryWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.signals = AppSignals()
        self.signals.discovery_complete.connect(self._show_printers)
        self.signals.discovery_failed.connect(self._show_error)
        self.detail_windows: list[PrinterDetailWindow] = []
        self.printers: list[dict] = []

        self.setWindowTitle("Printer Discovery")
        self.resize(860, 480)
        self._build_ui()
        self._start_discovery()

    def _build_ui(self) -> None:
        container = QWidget()
        layout = QVBoxLayout(container)

        self.status_label = QLabel("Discovering printers...")
        layout.addWidget(self.status_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        layout.addWidget(self.progress_bar)

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(
            ["Serial", "Machine Type", "IP Address", "Status"]
        )
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setAlternatingRowColors(True)
        self.table.doubleClicked.connect(self._open_selected_printer)
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table, 1)

        self.setCentralWidget(container)

    def _start_discovery(self) -> None:
        threading.Thread(
            target=self._discover_printers,
            daemon=True,
        ).start()

    def _discover_printers(self) -> None:
        try:
            printers = discover_printers(DEFAULT_SUBNETS)
            printers = self._attach_status_labels(printers)
            self.signals.discovery_complete.emit(printers)
        except Exception as exc:
            self.signals.discovery_failed.emit(str(exc))

    def _attach_status_labels(self, printers: list[dict]) -> list[dict]:
        if not printers:
            return []

        printers_with_status: list[dict] = []

        with ThreadPoolExecutor(max_workers=min(8, len(printers))) as executor:
            futures = {
                executor.submit(
                    self._get_status_label,
                    printer["ip"],
                ): printer
                for printer in printers
            }

            for future in as_completed(futures):
                printer = futures[future]
                printer_with_status = dict(printer)
                printer_with_status["status"] = future.result()
                printers_with_status.append(printer_with_status)

        return sorted(
            printers_with_status,
            key=lambda printer: printer["serial"],
        )

    def _get_status_label(self, printer_ip: str) -> str:
        try:
            response = get_printer_status(printer_ip)
            is_printing = response["Parameters"]["isPrinting"]
            return "Printing" if is_printing else "Idle"
        except Exception:
            return "Unknown"

    def _show_printers(self, printers: list[dict]) -> None:
        self.printers = printers
        self.progress_bar.hide()
        self.table.setRowCount(len(printers))

        for row, printer in enumerate(printers):
            for column, key in enumerate(
                ["serial", "machineTypeId", "ip", "status"]
            ):
                item = QTableWidgetItem(str(printer[key]))
                self.table.setItem(row, column, item)

        self.table.resizeColumnsToContents()

        if printers:
            self.status_label.setText(f"Found {len(printers)} printer(s).")
        else:
            self.status_label.setText("No printers found.")

    def _show_error(self, message: str) -> None:
        self.progress_bar.hide()
        self.status_label.setText(f"Printer discovery failed: {message}")

    def _open_selected_printer(self, *_args) -> None:
        row = self.table.currentRow()
        if row < 0 or row >= len(self.printers):
            return

        window = PrinterDetailWindow(self.printers[row])
        window.show()
        self.detail_windows.append(window)


def main() -> int:
    app = QApplication(sys.argv)
    window = PrinterDiscoveryWindow()
    window.show()

    signal.signal(signal.SIGINT, lambda *_args: app.quit())
    timer = QTimer()
    timer.timeout.connect(lambda: None)
    timer.start(100)

    return app.exec_()


if __name__ == "__main__":
    raise SystemExit(main())
