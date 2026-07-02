# Copyright: Ankitects Pty Ltd and contributors
# License: GNU AGPL, version 3 or later; http://www.gnu.org/licenses/agpl.html

"""SOA Exam P "Speedrun" desktop UI: the readiness dashboard window.

Hosts the SvelteKit ``readiness-dashboard`` page, which calls the Rust
``compute_readiness`` RPC and renders the honesty bundle / give-up state.
"""

from __future__ import annotations

import aqt
import aqt.main
from aqt.qt import QDialog, Qt, QVBoxLayout
from aqt.utils import disable_help_button, restoreGeom, saveGeom
from aqt.webview import AnkiWebView, AnkiWebViewKind


class ReadinessDialog(QDialog):
    def __init__(self, mw: aqt.main.AnkiQt) -> None:
        QDialog.__init__(self, mw, Qt.WindowType.Window)
        mw.garbage_collect_on_dialog_finish(self)
        self.mw = mw
        self.name = "speedrunReadiness"
        self.setWindowTitle("Exam readiness (Speedrun)")
        disable_help_button(self)

        self.web = AnkiWebView(kind=AnkiWebViewKind.DEFAULT)
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.web)
        self.setLayout(layout)

        restoreGeom(self, self.name, default_size=(720, 820))
        self.web.load_sveltekit_page("readiness-dashboard")
        self.show()
        self.activateWindow()

    def reject(self) -> None:
        if self.web:
            self.web.cleanup()
            self.web = None  # type: ignore[assignment]
        saveGeom(self, self.name)
        QDialog.reject(self)


def show_readiness_dashboard(mw: aqt.main.AnkiQt) -> None:
    ReadinessDialog(mw)
