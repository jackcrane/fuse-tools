import threading

from PyQt5.QtCore import QObject, pyqtSignal
from PyQt5.QtWidgets import (
    QLabel,
    QMainWindow,
    QProgressBar,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from src.printers.discovery import DEFAULT_SUBNETS, discover_printers
from src.printers.status import get_printer_status
from src.ui.detail_window import PrinterDetailWindow


class AppSignals(QObject):
    printer_found = pyqtSignal(dict)
    printer_status_updated = pyqtSignal(str, str)
    discovery_complete = pyqtSignal(list)
    discovery_failed = pyqtSignal(str)


class PrinterDiscoveryWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.signals = AppSignals()
        self.signals.printer_found.connect(self._add_printer)
        self.signals.printer_status_updated.connect(
            self._update_printer_status
        )
        self.signals.discovery_complete.connect(self._show_printers)
        self.signals.discovery_failed.connect(self._show_error)
        self.detail_windows: list[PrinterDetailWindow] = []
        self.printers: list[dict] = []
        self.printer_rows: dict[str, int] = {}

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
        threading.Thread(target=self._discover_printers, daemon=True).start()

    def _discover_printers(self) -> None:
        try:
            printers = discover_printers(
                DEFAULT_SUBNETS,
                on_found=self._handle_printer_found,
            )
            self.signals.discovery_complete.emit(printers)
        except Exception as exc:
            self.signals.discovery_failed.emit(str(exc))

    def _handle_printer_found(self, printer: dict) -> None:
        self.signals.printer_found.emit(dict(printer))
        threading.Thread(
            target=self._resolve_printer_status,
            args=(dict(printer),),
            daemon=True,
        ).start()

    def _resolve_printer_status(self, printer: dict) -> None:
        self.signals.printer_status_updated.emit(
            printer["printerId"],
            self._get_status_label(printer["ip"]),
        )

    def _get_status_label(self, printer_ip: str) -> str:
        try:
            response = get_printer_status(printer_ip)
            is_printing = response["Parameters"]["isPrinting"]
            return "Printing" if is_printing else "Idle"
        except Exception:
            return "Unknown"

    def _show_printers(self, printers: list[dict]) -> None:
        self.progress_bar.hide()

        if printers:
            self.status_label.setText(f"Found {len(printers)} printer(s).")
        else:
            self.status_label.setText("No printers found.")

    def _show_error(self, message: str) -> None:
        self.progress_bar.hide()
        self.status_label.setText(f"Printer discovery failed: {message}")

    def _add_printer(self, printer: dict) -> None:
        if printer["printerId"] in self.printer_rows:
            return

        row = self.table.rowCount()
        self.table.insertRow(row)

        printer_with_status = dict(printer)
        printer_with_status["status"] = "Checking..."
        self.printers.append(printer_with_status)
        self.printer_rows[printer["printerId"]] = row

        for column, key in enumerate(
            ["serial", "machineTypeId", "ip", "status"]
        ):
            item = QTableWidgetItem(str(printer_with_status[key]))
            self.table.setItem(row, column, item)

        self.table.resizeColumnsToContents()
        self.status_label.setText(f"Found {len(self.printers)} printer(s)...")

    def _update_printer_status(
        self,
        printer_id: str,
        status: str,
    ) -> None:
        row = self.printer_rows.get(printer_id)
        if row is None:
            return

        self.printers[row]["status"] = status
        status_item = self.table.item(row, 3)
        if status_item is None:
            self.table.setItem(row, 3, QTableWidgetItem(status))
        else:
            status_item.setText(status)

    def _open_selected_printer(self, *_args) -> None:
        row = self.table.currentRow()
        if row < 0 or row >= len(self.printers):
            return

        window = PrinterDetailWindow(self.printers[row])
        window.show()
        self.detail_windows.append(window)
