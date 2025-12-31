import os
import sys
import json
import socket
import webbrowser
from pathlib import Path

from PyQt5 import QtCore, QtGui, QtWidgets


def tor_port_open(host: str, port: int, timeout=1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def pick_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class LocalServer(QtCore.QObject):
    started = QtCore.pyqtSignal(int)
    stopped = QtCore.pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.proc = QtCore.QProcess(self)
        self.proc.finished.connect(lambda *_: self.stopped.emit())

    def start(self, directory: str, port: int = 0):
        if port == 0:
            port = pick_free_port()

        self.proc.setWorkingDirectory(directory)
        self.proc.start(sys.executable, ["-m", "http.server", str(port)])
        if self.proc.waitForStarted(1500):
            self.started.emit(port)
        else:
            raise RuntimeError("HTTP server başlatılamadı")

    def stop(self):
        if self.proc.state() != QtCore.QProcess.NotRunning:
            self.proc.kill()


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Tor Scraper GUI (UI’siz)")
        self.resize(1200, 720)

        self.scraper = QtCore.QProcess(self)
        self.scraper.readyReadStandardOutput.connect(self.on_proc_stdout)
        self.scraper.readyReadStandardError.connect(self.on_proc_stderr)
        self.scraper.finished.connect(self.on_proc_finished)

        self.server = LocalServer(self)
        self.server.started.connect(self.on_server_started)
        self._open_after_server = None  # html filename

        self.build_ui()
        self.apply_theme()
        self.wire_events()

        self.btnStop.setEnabled(False)
        self.refresh_outputs()

        # Tor status timer
        self.torTimer = QtCore.QTimer(self)
        self.torTimer.timeout.connect(self.update_tor_status)
        self.torTimer.start(1500)
        self.update_tor_status()

    # ---------------- UI ----------------

    def build_ui(self):
        central = QtWidgets.QWidget()
        self.setCentralWidget(central)

        root = QtWidgets.QHBoxLayout(central)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(10)

        # LEFT PANEL
        left = QtWidgets.QFrame()
        left.setFrameShape(QtWidgets.QFrame.StyledPanel)
        left.setMinimumWidth(330)
        left_layout = QtWidgets.QVBoxLayout(left)
        left_layout.setSpacing(10)

        # Add URL group
        grpAdd = QtWidgets.QGroupBox("Hedef URL Ekle")
        gadd = QtWidgets.QVBoxLayout(grpAdd)
        gadd.setContentsMargins(12, 12, 12, 12)
        gadd.setSpacing(10)

        self.txtUrl = QtWidgets.QLineEdit()
        self.txtUrl.setPlaceholderText("http://... / https://... / onion...")
        gadd.addWidget(self.txtUrl)

        rowAdd = QtWidgets.QHBoxLayout()
        self.btnAddUrl = QtWidgets.QPushButton("Ekle")
        self.btnRemoveSelected = QtWidgets.QPushButton("Seçileni Sil")
        rowAdd.addWidget(self.btnAddUrl)
        rowAdd.addWidget(self.btnRemoveSelected)
        gadd.addLayout(rowAdd)

        self.btnClearTargets = QtWidgets.QPushButton("Listeyi Temizle")
        gadd.addWidget(self.btnClearTargets)

        left_layout.addWidget(grpAdd)

        # Targets group
        grpTargets = QtWidgets.QGroupBox("Hedef Listesi")
        gt = QtWidgets.QVBoxLayout(grpTargets)
        gt.setContentsMargins(12, 12, 12, 12)
        gt.setSpacing(8)
        self.listTargets = QtWidgets.QListWidget()
        gt.addWidget(self.listTargets)
        left_layout.addWidget(grpTargets)

        # Run group
        grpRun = QtWidgets.QGroupBox("Çalıştırma")
        gr = QtWidgets.QGridLayout(grpRun)
        gr.setContentsMargins(12, 12, 12, 12)
        gr.setHorizontalSpacing(10)
        gr.setVerticalSpacing(12)
        gr.setColumnStretch(1, 1)
        gr.setColumnStretch(2, 1)

        self.txtExePath = QtWidgets.QLineEdit(str(Path.cwd() / "tor-scraper.exe"))
        self.btnBrowseExe = QtWidgets.QPushButton("Seç...")
        self.txtOutDir = QtWidgets.QLineEdit(str(Path.cwd() / "output"))
        self.btnBrowseOut = QtWidgets.QPushButton("Klasör...")
        self.txtProxy = QtWidgets.QLineEdit("127.0.0.1:9150")

        self.spWorkers = QtWidgets.QSpinBox()
        self.spWorkers.setRange(1, 50)
        self.spWorkers.setValue(1)

        self.spTimeout = QtWidgets.QSpinBox()
        self.spTimeout.setRange(1, 300)
        self.spTimeout.setValue(20)

        self.chkScreenshot = QtWidgets.QCheckBox("Screenshot al")
        self.chkScreenshot.setChecked(True)

        self.chkTorCheck = QtWidgets.QCheckBox("Tor Check (check.torproject.org)")
        self.chkTorCheck.setChecked(False)

        self.btnStart = QtWidgets.QPushButton("Başlat")
        self.btnStop = QtWidgets.QPushButton("Durdur")

        self.lblTorStatus = QtWidgets.QLabel("Tor: bilinmiyor")
        self.lblTorStatus.setStyleSheet("font-weight: 600;")

        r = 0
        gr.addWidget(QtWidgets.QLabel("EXE:"), r, 0, alignment=QtCore.Qt.AlignVCenter)
        gr.addWidget(self.txtExePath, r, 1)
        gr.addWidget(self.btnBrowseExe, r, 2)
        r += 1
        gr.addWidget(QtWidgets.QLabel("Output:"), r, 0, alignment=QtCore.Qt.AlignVCenter)
        gr.addWidget(self.txtOutDir, r, 1)
        gr.addWidget(self.btnBrowseOut, r, 2)
        r += 1
        gr.addWidget(QtWidgets.QLabel("Proxy:"), r, 0, alignment=QtCore.Qt.AlignVCenter)
        gr.addWidget(self.txtProxy, r, 1, 1, 2)
        r += 1
        gr.addWidget(QtWidgets.QLabel("Workers:"), r, 0, alignment=QtCore.Qt.AlignVCenter)
        gr.addWidget(self.spWorkers, r, 1, alignment=QtCore.Qt.AlignVCenter)
        gr.addWidget(QtWidgets.QLabel("Timeout(s):"), r, 2, alignment=QtCore.Qt.AlignVCenter)
        r += 1
        gr.addWidget(self.spTimeout, r, 2, alignment=QtCore.Qt.AlignVCenter)
        gr.addWidget(self.chkScreenshot, r, 0, 1, 2, alignment=QtCore.Qt.AlignVCenter)
        r += 1
        gr.addWidget(self.chkTorCheck, r, 0, 1, 3, alignment=QtCore.Qt.AlignVCenter)
        r += 1
        rowBtns = QtWidgets.QHBoxLayout()
        rowBtns.addWidget(self.btnStart)
        rowBtns.addWidget(self.btnStop)
        gr.addLayout(rowBtns, r, 0, 1, 3)
        r += 1
        gr.addWidget(self.lblTorStatus, r, 0, 1, 3)

        left_layout.addWidget(grpRun)
        left_layout.addStretch(1)

        # RIGHT PANEL (Tabs)
        self.tabs = QtWidgets.QTabWidget()
        self.tabs.setDocumentMode(True)

        # HTML tab
        self.tabHtml = QtWidgets.QWidget()
        vhtml = QtWidgets.QVBoxLayout(self.tabHtml)

        self.tblHtml = QtWidgets.QTableWidget()
        self.tblHtml.setColumnCount(3)
        self.tblHtml.setHorizontalHeaderLabels(["Dosya", "URL", "Aç"])
        self.tblHtml.horizontalHeader().setSectionResizeMode(0, QtWidgets.QHeaderView.ResizeToContents)
        self.tblHtml.horizontalHeader().setSectionResizeMode(1, QtWidgets.QHeaderView.Stretch)
        self.tblHtml.horizontalHeader().setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeToContents)
        self.tblHtml.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.tblHtml.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.tblHtml.setAlternatingRowColors(True)
        self.tblHtml.verticalHeader().setVisible(False)
        vhtml.addWidget(self.tblHtml)

        self.tabs.addTab(self.tabHtml, "HTML")

        # Screenshots tab
        self.tabShots = QtWidgets.QWidget()
        vshot = QtWidgets.QVBoxLayout(self.tabShots)
        self.listShots = QtWidgets.QListWidget()
        self.btnOpenShot = QtWidgets.QPushButton("Seçileni Aç")
        vshot.addWidget(self.listShots)
        vshot.addWidget(self.btnOpenShot)
        self.tabs.addTab(self.tabShots, "Screenshots")

        # Logs tab
        self.tabLogs = QtWidgets.QWidget()
        vlog = QtWidgets.QVBoxLayout(self.tabLogs)
        self.txtLog = QtWidgets.QTextEdit()
        self.txtLog.setReadOnly(True)
        self.txtLog.setFont(QtGui.QFont("Consolas", 10))
        vlog.addWidget(self.txtLog)

        rowLogBtns = QtWidgets.QHBoxLayout()
        self.btnOpenReport = QtWidgets.QPushButton("scan_report.log Aç")
        self.btnOpenSummary = QtWidgets.QPushButton("scan_summary.log Aç")
        self.btnOpenJson = QtWidgets.QPushButton("scan_results.json Aç")
        self.btnClearLogView = QtWidgets.QPushButton("Ekranı Temizle")
        rowLogBtns.addWidget(self.btnOpenReport)
        rowLogBtns.addWidget(self.btnOpenSummary)
        rowLogBtns.addWidget(self.btnOpenJson)
        rowLogBtns.addStretch(1)
        rowLogBtns.addWidget(self.btnClearLogView)
        vlog.addLayout(rowLogBtns)

        self.tabs.addTab(self.tabLogs, "Logs")

        # Compose layout
        root.addWidget(left)
        root.addWidget(self.tabs, 1)

    def apply_theme(self):
        base_font = QtGui.QFont("Segoe UI", 10)
        self.setFont(base_font)

        palette = QtGui.QPalette()
        palette.setColor(QtGui.QPalette.Window, QtGui.QColor("#0e1626"))
        palette.setColor(QtGui.QPalette.Base, QtGui.QColor("#111a2c"))
        palette.setColor(QtGui.QPalette.AlternateBase, QtGui.QColor("#132036"))
        palette.setColor(QtGui.QPalette.Text, QtGui.QColor("#e9f0ff"))
        palette.setColor(QtGui.QPalette.WindowText, QtGui.QColor("#e9f0ff"))
        palette.setColor(QtGui.QPalette.Button, QtGui.QColor("#182338"))
        palette.setColor(QtGui.QPalette.ButtonText, QtGui.QColor("#e9f0ff"))
        palette.setColor(QtGui.QPalette.Highlight, QtGui.QColor("#1ea7ff"))
        palette.setColor(QtGui.QPalette.HighlightedText, QtGui.QColor("#0c1220"))
        self.setPalette(palette)

        for btn in self.findChildren(QtWidgets.QPushButton):
            btn.setMinimumHeight(34)
            btn.setCursor(QtGui.QCursor(QtCore.Qt.PointingHandCursor))
        for edit in self.findChildren((QtWidgets.QLineEdit, QtWidgets.QSpinBox)):
            edit.setMinimumHeight(32)
        for group in self.findChildren(QtWidgets.QGroupBox):
            group.setContentsMargins(10, 16, 10, 10)

        style = """
        QWidget {
            background-color: #0e1626;
            color: #e9f0ff;
        }
        QFrame, QGroupBox {
            background-color: #111a2c;
            border: 1px solid #2b3c55;
            border-radius: 10px;
            margin-top: 6px;
            padding-top: 12px;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            left: 12px;
            padding: 0 6px;
            color: #8dd7ff;
            font-weight: 700;
            background-color: transparent;
        }
        QLineEdit, QSpinBox {
            background-color: #0f1829;
            color: #e9f0ff;
            border: 1px solid #2b3c55;
            border-radius: 8px;
            padding: 6px 10px;
            selection-background-color: #38bdf8;
        }
        QLineEdit::placeholder {
            color: #9fb4d7;
        }
        QSpinBox::up-button, QSpinBox::down-button {
            width: 16px;
            background-color: #1c2a42;
            border: none;
        }
        QSpinBox::up-button:hover, QSpinBox::down-button:hover {
            background-color: #1ea7ff;
        }
        QPushButton {
            background-color: #1c2a42;
            color: #e9f0ff;
            border: 1px solid #365072;
            border-radius: 10px;
            padding: 8px 12px;
            font-weight: 600;
        }
        QPushButton:hover {
            background-color: #1ea7ff;
            border-color: #48bffc;
            color: #0c1220;
        }
        QPushButton:pressed {
            background-color: #0f8dd9;
        }
        QPushButton:disabled {
            background-color: #1a2334;
            color: #6f7c94;
            border-color: #2a3549;
        }
        QListWidget, QTextEdit, QTableWidget {
            background-color: #101a2b;
            border: 1px solid #2b3c55;
            border-radius: 10px;
            color: #e9f0ff;
        }
        QTableWidget {
            alternate-background-color: #0f1829;
        }
        QTableWidget::item {
            padding: 6px 8px;
        }
        QTableWidget::item:selected, QListWidget::item:selected {
            background-color: #1ea7ff;
            color: #0c1220;
        }
        QHeaderView::section {
            background-color: #131f33;
            color: #cbd6ea;
            padding: 6px;
            border: 0px;
            border-right: 1px solid #2b3c55;
        }
        QTabWidget::pane {
            border: 1px solid #2b3c55;
            border-radius: 12px;
            background: #111a2c;
        }
        QTabBar::tab {
            background: #131f33;
            padding: 8px 14px;
            border: 1px solid #2b3c55;
            border-bottom: none;
            border-top-left-radius: 10px;
            border-top-right-radius: 10px;
            color: #cbd6ea;
            min-width: 110px;
        }
        QTabBar::tab:selected {
            background: #1ea7ff;
            color: #0c1220;
            border-color: #48bffc;
        }
        QLabel {
            color: #cbd6ea;
        }
        QCheckBox, QRadioButton {
            color: #cbd6ea;
        }
        QCheckBox::indicator {
            width: 16px;
            height: 16px;
            border-radius: 4px;
            border: 1px solid #365072;
            background: #101a2b;
        }
        QCheckBox::indicator:checked {
            background: #1ea7ff;
            border-color: #48bffc;
        }
        """
        self.setStyleSheet(style)

    def wire_events(self):
        self.btnAddUrl.clicked.connect(self.add_url)
        self.btnRemoveSelected.clicked.connect(self.remove_selected)
        self.btnClearTargets.clicked.connect(self.listTargets.clear)

        self.btnBrowseExe.clicked.connect(self.browse_exe)
        self.btnBrowseOut.clicked.connect(self.browse_out)

        self.btnStart.clicked.connect(self.start_scan)
        self.btnStop.clicked.connect(self.stop_scan)

        self.btnOpenShot.clicked.connect(self.open_selected_shot)

        self.btnOpenReport.clicked.connect(lambda: self.open_out_file("scan_report.log"))
        self.btnOpenSummary.clicked.connect(lambda: self.open_out_file("scan_summary.log"))
        self.btnOpenJson.clicked.connect(lambda: self.open_out_file("scan_results.json"))
        self.btnClearLogView.clicked.connect(self.txtLog.clear)

    # ---------------- Helpers ----------------

    def log(self, s: str):
        self.txtLog.append(s.rstrip())

    def update_tor_status(self):
        proxy = self.txtProxy.text().strip()
        host, port = "127.0.0.1", 9150
        if ":" in proxy:
            host, p = proxy.split(":", 1)
            try:
                port = int(p)
            except ValueError:
                port = 9150
        ok = tor_port_open(host, port)
        self.lblTorStatus.setText(f"Tor: {'AÇIK ✅' if ok else 'KAPALI ❌'} ({host}:{port})")

    def add_url(self):
        url = self.txtUrl.text().strip()
        if not url:
            return
        self.listTargets.addItem(url)
        self.txtUrl.clear()

    def remove_selected(self):
        for item in self.listTargets.selectedItems():
            self.listTargets.takeItem(self.listTargets.row(item))

    def browse_exe(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "tor-scraper.exe seç", str(Path.cwd()), "EXE (*.exe)"
        )
        if path:
            self.txtExePath.setText(path)

    def browse_out(self):
        path = QtWidgets.QFileDialog.getExistingDirectory(self, "Output klasörü seç", str(Path.cwd()))
        if path:
            self.txtOutDir.setText(path)

    def normalize_targets_yaml(self, targets, out_path: Path):
        out_path.write_text("".join([f"- {t}\n" for t in targets]), encoding="utf-8")

    # ---------------- Run ----------------

    def start_scan(self):
        exe = self.txtExePath.text().strip()
        out_dir = Path(self.txtOutDir.text().strip())
        proxy = self.txtProxy.text().strip()
        workers = self.spWorkers.value()
        timeout_s = self.spTimeout.value()
        take_shot = self.chkScreenshot.isChecked()
        tor_check = self.chkTorCheck.isChecked()

        targets = [self.listTargets.item(i).text().strip() for i in range(self.listTargets.count())]
        if not targets:
            QtWidgets.QMessageBox.warning(self, "Uyarı", "Hedef listesi boş. Önce URL ekle.")
            return

        if not os.path.exists(exe):
            QtWidgets.QMessageBox.critical(self, "Hata", f"EXE bulunamadı:\n{exe}")
            return

        # Ensure output structure
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "html").mkdir(parents=True, exist_ok=True)
        if take_shot:
            (out_dir / "screenshots").mkdir(parents=True, exist_ok=True)

        targets_yaml = Path.cwd() / "targets.yaml"
        self.normalize_targets_yaml(targets, targets_yaml)

        args = [
            "-targets", str(targets_yaml),
            "-out", str(out_dir),
            "-proxy", proxy,
            "-workers", str(workers),
            "-timeout", f"{timeout_s}s",
            "-check-tor=" + ("true" if tor_check else "false"),
            "-screenshot=" + ("true" if take_shot else "false"),
        ]

        self.log(f"[GUI] Çalıştırılıyor: {exe} {' '.join(args)}")
        self.btnStart.setEnabled(False)
        self.btnStop.setEnabled(True)

        self.scraper.setProgram(exe)
        self.scraper.setArguments(args)
        self.scraper.setWorkingDirectory(str(Path.cwd()))
        self.scraper.start()

        if not self.scraper.waitForStarted(1500):
            self.log("[GUI][ERR] Process başlatılamadı.")
            self.btnStart.setEnabled(True)
            self.btnStop.setEnabled(False)

    def stop_scan(self):
        if self.scraper.state() != QtCore.QProcess.NotRunning:
            self.scraper.kill()
            self.log("[GUI] Durduruldu (kill).")

    def on_proc_stdout(self):
        data = bytes(self.scraper.readAllStandardOutput()).decode(errors="ignore")
        if data.strip():
            self.log(data)

    def on_proc_stderr(self):
        data = bytes(self.scraper.readAllStandardError()).decode(errors="ignore")
        if data.strip():
            self.log("[STDERR] " + data)

    def on_proc_finished(self):
        self.log("[GUI] Tarama bitti. Dosyalar yenileniyor...")
        self.btnStart.setEnabled(True)
        self.btnStop.setEnabled(False)
        self.refresh_outputs()

    # ---------------- Outputs ----------------

    def refresh_outputs(self):
        out_dir = Path(self.txtOutDir.text().strip())
        html_dir = out_dir / "html"
        shot_dir = out_dir / "screenshots"
        json_path = out_dir / "scan_results.json"

        results = []
        if json_path.exists():
            try:
                results = json.loads(json_path.read_text(encoding="utf-8"))
            except Exception as e:
                self.log(f"[GUI][WARN] JSON okunamadı: {e}")

        url_by_html = {}
        for r in results:
            saved = r.get("saved_html")
            if saved:
                url_by_html[Path(saved).name] = r.get("normalized_url", r.get("url", ""))

        # Fill HTML table
        self.tblHtml.setRowCount(0)
        if html_dir.exists():
            files = sorted(html_dir.glob("*.html"), key=lambda p: p.stat().st_mtime, reverse=True)
            for f in files:
                self.add_html_row(f, url_by_html.get(f.name, ""))

        # Screenshots list
        self.listShots.clear()
        if shot_dir.exists():
            shots = sorted(shot_dir.glob("*.png"), key=lambda p: p.stat().st_mtime, reverse=True)
            for p in shots:
                self.listShots.addItem(str(p))

    def add_html_row(self, html_path: Path, url: str):
        row = self.tblHtml.rowCount()
        self.tblHtml.insertRow(row)
        self.tblHtml.setItem(row, 0, QtWidgets.QTableWidgetItem(html_path.name))
        self.tblHtml.setItem(row, 1, QtWidgets.QTableWidgetItem(url))

        btn_serve = QtWidgets.QPushButton("Aç")
        btn_serve.clicked.connect(lambda _, p=str(html_path): self.serve_and_open(p))
        self.tblHtml.setCellWidget(row, 2, btn_serve)

    def open_selected_shot(self):
        item = self.listShots.currentItem()
        if item:
            self.open_file(item.text())

    def open_out_file(self, name: str):
        out_dir = Path(self.txtOutDir.text().strip())
        path = out_dir / name
        if path.exists():
            self.open_file(str(path))
        else:
            QtWidgets.QMessageBox.information(self, "Bilgi", f"Dosya yok: {path}")

    def open_file(self, path: str):
        try:
            os.startfile(path)  # Windows
        except Exception:
            webbrowser.open("file:///" + str(Path(path).resolve()).replace("\\", "/"))

    # ------------- Live server equivalent -------------

    def serve_and_open(self, html_path: str):
        out_dir = Path(self.txtOutDir.text().strip())
        html_dir = out_dir / "html"
        if not html_dir.exists():
            QtWidgets.QMessageBox.warning(self, "Uyarı", "HTML klasörü bulunamadı.")
            return

        self._open_after_server = Path(html_path).name

        try:
            self.server.stop()
            self.server.start(str(html_dir), port=0)
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Hata", f"Server başlatılamadı:\n{e}")

    def on_server_started(self, port: int):
        if not self._open_after_server:
            return
        url = f"http://127.0.0.1:{port}/{self._open_after_server}"
        self.log(f"[GUI] Local server: {url}")
        webbrowser.open(url)


def main():
    app = QtWidgets.QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
