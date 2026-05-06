from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

import objc
from AppKit import (
    NSApp,
    NSApplication,
    NSApplicationActivationPolicyRegular,
    NSBackingStoreBuffered,
    NSBezelBorder,
    NSMakeRect,
    NSProgressIndicator,
    NSScrollView,
    NSTableColumn,
    NSTableView,
    NSTextField,
    NSWindow,
    NSWindowStyleMaskClosable,
    NSWindowStyleMaskMiniaturizable,
    NSWindowStyleMaskResizable,
    NSWindowStyleMaskTitled,
)
from Foundation import NSObject
from PyObjCTools import AppHelper

from discover_printers import DEFAULT_SUBNETS, discover_printers
from printer_status import get_printer_status


class PrinterTableDataSource(NSObject):
    def init(self):
        self = objc.super(PrinterTableDataSource, self).init()
        if self is None:
            return None

        self.printers = []
        return self

    def setPrinters_(self, printers):
        self.printers = list(printers)

    def numberOfRowsInTableView_(self, _table_view):
        return len(self.printers)

    def tableView_objectValueForTableColumn_row_(
        self,
        _table_view,
        table_column,
        row,
    ):
        printer = self.printers[row]
        identifier = str(table_column.identifier())

        if identifier == "serial":
            return printer["serial"]
        if identifier == "machineTypeId":
            return printer["machineTypeId"]
        if identifier == "ip":
            return printer["ip"]
        if identifier == "status":
            return printer["status"]

        return ""


class AppDelegate(NSObject):
    def applicationDidFinishLaunching_(self, _notification):
        self.data_source = PrinterTableDataSource.alloc().init()
        self._build_window()
        self._start_discovery()

    def applicationShouldTerminateAfterLastWindowClosed_(self, _app):
        return True

    def _build_window(self):
        frame = NSMakeRect(240.0, 240.0, 760.0, 420.0)
        style = (
            NSWindowStyleMaskTitled
            | NSWindowStyleMaskClosable
            | NSWindowStyleMaskResizable
            | NSWindowStyleMaskMiniaturizable
        )

        self.window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            frame,
            style,
            NSBackingStoreBuffered,
            False,
        )
        self.window.setTitle_("Printer Discovery")
        self.window.makeKeyAndOrderFront_(None)

        content_view = self.window.contentView()

        self.status_label = NSTextField.alloc().initWithFrame_(
            NSMakeRect(20.0, 375.0, 720.0, 24.0)
        )
        self.status_label.setEditable_(False)
        self.status_label.setBordered_(False)
        self.status_label.setDrawsBackground_(False)
        self.status_label.setStringValue_("Discovering printers...")
        content_view.addSubview_(self.status_label)

        self.spinner = NSProgressIndicator.alloc().initWithFrame_(
            NSMakeRect(20.0, 345.0, 160.0, 20.0)
        )
        self.spinner.setIndeterminate_(True)
        self.spinner.startAnimation_(None)
        content_view.addSubview_(self.spinner)

        scroll_view = NSScrollView.alloc().initWithFrame_(
            NSMakeRect(20.0, 20.0, 720.0, 310.0)
        )
        scroll_view.setHasVerticalScroller_(True)
        scroll_view.setBorderType_(NSBezelBorder)

        self.table_view = NSTableView.alloc().initWithFrame_(
            NSMakeRect(0.0, 0.0, 720.0, 310.0)
        )
        self.table_view.setDataSource_(self.data_source)

        for identifier, title, width in [
            ("serial", "Serial", 220.0),
            ("machineTypeId", "Machine Type", 200.0),
            ("ip", "IP Address", 180.0),
            ("status", "Status", 120.0),
        ]:
            column = NSTableColumn.alloc().initWithIdentifier_(identifier)
            column.setWidth_(width)
            column.headerCell().setStringValue_(title)
            self.table_view.addTableColumn_(column)

        scroll_view.setDocumentView_(self.table_view)
        content_view.addSubview_(scroll_view)

    def _start_discovery(self):
        threading.Thread(
            target=self._discover_printers,
            daemon=True,
        ).start()

    def _discover_printers(self):
        try:
            printers = self._discover_printers_with_status()
            self.performSelectorOnMainThread_withObject_waitUntilDone_(
                "showPrinters:",
                printers,
                False,
            )
        except Exception as exc:
            self.performSelectorOnMainThread_withObject_waitUntilDone_(
                "showError:",
                str(exc),
                False,
            )

    def _discover_printers_with_status(self):
        printers = discover_printers(DEFAULT_SUBNETS)

        if not printers:
            return []

        printers_with_status = []

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

    def _get_status_label(self, printer_ip):
        try:
            response = get_printer_status(printer_ip)
            is_printing = response["Parameters"]["isPrinting"]
            return "Printing" if is_printing else "Idle"
        except Exception:
            return "Unknown"

    def showPrinters_(self, printers):
        self.spinner.stopAnimation_(None)
        self.spinner.setHidden_(True)
        self.data_source.setPrinters_(printers)
        self.table_view.reloadData()

        if printers:
            self.status_label.setStringValue_(
                f"Found {len(printers)} printer(s)."
            )
        else:
            self.status_label.setStringValue_("No printers found.")

    def showError_(self, message):
        self.spinner.stopAnimation_(None)
        self.spinner.setHidden_(True)
        self.status_label.setStringValue_(f"Printer discovery failed: {message}")


def main():
    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(NSApplicationActivationPolicyRegular)

    delegate = AppDelegate.alloc().init()
    app.setDelegate_(delegate)
    AppHelper.runEventLoop()


if __name__ == "__main__":
    main()
