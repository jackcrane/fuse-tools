import signal
import sys

from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import QApplication

from src.ui.discovery_window import PrinterDiscoveryWindow


def main() -> int:
    app = QApplication(sys.argv)
    window = PrinterDiscoveryWindow()
    window.show()

    signal.signal(signal.SIGINT, lambda *_args: app.quit())
    timer = QTimer()
    timer.timeout.connect(lambda: None)
    timer.start(100)

    return app.exec_()
