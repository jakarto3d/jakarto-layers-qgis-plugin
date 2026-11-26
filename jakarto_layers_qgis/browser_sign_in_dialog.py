"""The window shown while the person approves the sign-in in their browser."""

from __future__ import annotations

import time

import requests
from qgis.PyQt.QtCore import Qt, QTimer, QUrl
from qgis.PyQt.QtGui import QDesktopServices, QFont
from qgis.PyQt.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from . import browser_sign_in
from .browser_sign_in import BrowserSignInError, DeviceCode


class BrowserSignInDialog(QDialog):
    """Asks for a code, opens the browser, waits for the approval.

    Accepted once `session` holds the Jakarto session cookie; rejected when
    cancelled. `error` says why it stopped otherwise.
    """

    def __init__(self, session: requests.Session, parent=None):
        super().__init__(parent)
        self.session = session
        self.error: str | None = None
        self._device_code: DeviceCode | None = None
        self._interval = 5
        self._deadline = 0.0

        self.setWindowTitle("Sign in to Jakarto")
        self.setMinimumWidth(420)

        layout = QVBoxLayout(self)
        intro = QLabel(
            "Your browser opens the Jakarto sign-in page. Sign in, then check that "
            "the page shows this code and approve:"
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        self._code_label = QLabel("…")
        font = QFont()
        font.setPointSize(22)
        font.setBold(True)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self._code_label.setFont(font)
        self._code_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._code_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        layout.addWidget(self._code_label)

        self._status = QLabel("Waiting for the approval in the browser…")
        self._status.setWordWrap(True)
        layout.addWidget(self._status)

        self._open_button = QPushButton("Open the page again")
        self._open_button.clicked.connect(self._open_browser)
        self._open_button.setEnabled(False)
        layout.addWidget(self._open_button)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._poll)

        # once the window is shown, so a slow network does not delay it appearing
        QTimer.singleShot(0, self._start)

    def _start(self) -> None:
        try:
            self._device_code = browser_sign_in.request_device_code(self.session)
        except (BrowserSignInError, requests.RequestException) as e:
            self._fail(f"Could not start the sign-in: {e}")
            return
        self._code_label.setText(self._device_code.display_code)
        self._interval = self._device_code.interval
        self._deadline = time.monotonic() + self._device_code.expires_in
        self._open_button.setEnabled(True)
        self._open_browser()
        self._timer.start(self._interval * 1000)

    def _open_browser(self) -> None:
        if self._device_code is not None:
            QDesktopServices.openUrl(QUrl(self._device_code.verification_uri_complete))

    def _poll(self) -> None:
        if time.monotonic() > self._deadline:
            self._fail("The code expired. Close this window and sign in again.")
            return
        try:
            result = browser_sign_in.poll(self.session, self._device_code)
        except BrowserSignInError as e:
            self._fail(str(e))
            return
        except requests.RequestException:
            # a network hiccup: keep waiting, the code is still valid
            result = browser_sign_in.PENDING

        if result == browser_sign_in.APPROVED:
            self.accept()
            return
        if result == browser_sign_in.SLOW_DOWN:
            self._interval += 5
        self._timer.start(self._interval * 1000)

    def _fail(self, message: str) -> None:
        self.error = message
        self._timer.stop()
        self._status.setText(message)
        self._open_button.setEnabled(False)

    def reject(self) -> None:
        self._timer.stop()
        super().reject()
