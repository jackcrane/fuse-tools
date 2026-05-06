from PyQt5.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)


class RecordingStopDialog(QDialog):
    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setWindowTitle("Recording End Condition")
        self.setModal(True)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("When should this recording end?"))

        self.manual_option = QRadioButton("Manually")
        self.manual_option.setChecked(True)
        layout.addWidget(self.manual_option)

        self.idle_option = QRadioButton(
            "When the printer's status switches to idle"
        )
        layout.addWidget(self.idle_option)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def selected_mode(self) -> str:
        if self.idle_option.isChecked():
            return "until_idle"
        return "manual"
