from PyQt5.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QSizePolicy,
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


class StreamConfigurationDialog(QDialog):
    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setWindowTitle("Livestream Settings")
        self.setModal(True)
        self.resize(560, 180)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Enter the RTMP destination details."))

        form_layout = QFormLayout()
        form_layout.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)
        self.rtmp_url_input = QLineEdit()
        self.rtmp_url_input.setPlaceholderText("rtmp://server/app")
        self.rtmp_url_input.setMinimumWidth(360)
        self.rtmp_url_input.setSizePolicy(
            QSizePolicy.Expanding,
            QSizePolicy.Fixed,
        )
        self.rtmp_url_input.setStyleSheet("border: 1px solid black;")
        form_layout.addRow("RTMP URL", self.rtmp_url_input)

        self.stream_key_input = QLineEdit()
        self.stream_key_input.setPlaceholderText("Stream key")
        self.stream_key_input.setEchoMode(QLineEdit.Password)
        self.stream_key_input.setMinimumWidth(360)
        self.stream_key_input.setSizePolicy(
            QSizePolicy.Expanding,
            QSizePolicy.Fixed,
        )
        self.stream_key_input.setStyleSheet("border: 1px solid black;")
        form_layout.addRow("Stream key", self.stream_key_input)
        layout.addLayout(form_layout)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Save | QDialogButtonBox.Cancel
        )
        next_button = buttons.button(QDialogButtonBox.Save)
        if next_button is not None:
            next_button.setText("Next")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def rtmp_url(self) -> str:
        return self.rtmp_url_input.text().strip()

    def stream_key(self) -> str:
        return self.stream_key_input.text().strip()
