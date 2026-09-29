"""PyQt5 front end for the legacy AutoRouter 2D routing workflow.

Python 3.10 port of the legacy ``app.py``.  The window,
its labels and the interaction are the legacy ones (routing area, waveguide
width/pitch/radius, channel count, input workbook, output folder, log pane and
a result image dialog).

Repairs compared with the decompiled listing:

* ``ButtonLineEdit.resizeEvent`` passed a float to ``QToolButton.move``; PyQt5
  on Python 3.10 rejects that with ``TypeError``.
* ``./resource/search.png`` and ``./style/app.qss`` were opened relative to the
  current directory and crashed the window when missing; both are now resolved
  from the project directory and have fallbacks.
* the result dialog built its path by string concatenation.
* routing exceptions used to kill the worker thread silently; ``Router.error``
  is now logged into the GUI log pane.
* the spin boxes had no initial values (all zero, which is not a usable routing
  area); they now start at the documented 512-channel parameters and are
  validated before routing starts.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QFont, QIcon, QPixmap
from PyQt5.QtWidgets import (
    QApplication,
    QDialog,
    QFileDialog,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QStyle,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from main import Router

BASE_DIR = Path(__file__).resolve().parent

CN = True
MW_TITLE = "自动布线程序" if CN else "AutoRouter"
MW_WIDTH = 960
MW_HEIGHT = 720

SEARCH_ICON = BASE_DIR / "resource" / "search.png"
STYLE_SHEET = BASE_DIR / "style" / "app.qss"

FALLBACK_QSS = """
QLabel { font-size: 20px; }
QPlainTextEdit { border: 1px solid #6a63a9; border-radius: 4px; font-size: 20px; }
QPushButton { border: 2px outset #6a63a9; border-radius: 6px; font: bold 28px; min-width: 150px; min-height: 50px; }
"""


def load_style_sheet() -> str:
    """Read ``style/app.qss``, falling back to a built-in sheet."""
    try:
        return STYLE_SHEET.read_text(encoding="utf-8")
    except OSError:
        return FALLBACK_QSS


class ButtonLineEdit(QLineEdit):
    buttonClicked = pyqtSignal(bool)

    def __init__(self, icon_file, parent=None):
        super(ButtonLineEdit, self).__init__(parent)
        self.button = QToolButton(self)
        icon_path = Path(icon_file)
        if icon_path.is_file():
            self.button.setIcon(QIcon(str(icon_path)))
        else:
            # The legacy bundle shipped resource/search.png; without it a text
            # button keeps the browse action reachable.
            self.button.setText("...")
        self.button.setStyleSheet("border: 0px; padding: 0px;")
        self.button.setCursor(Qt.ArrowCursor)
        self.button.clicked.connect(self.buttonClicked.emit)
        frameWidth = self.style().pixelMetric(QStyle.PM_DefaultFrameWidth)
        buttonSize = self.button.sizeHint()
        self.setStyleSheet(
            "QLineEdit {padding-right: %dpx; }" % (buttonSize.width() + frameWidth + 1)
        )
        self.setMinimumSize(
            max(self.minimumSizeHint().width(), buttonSize.width() + frameWidth * 2 + 2),
            max(self.minimumSizeHint().height(), buttonSize.height() + frameWidth * 2 + 2),
        )

    def resizeEvent(self, event):
        buttonSize = self.button.sizeHint()
        frameWidth = self.style().pixelMetric(QStyle.PM_DefaultFrameWidth)
        # PyQt5 requires int coordinates here; the legacy float arithmetic
        # raised TypeError under Python 3.10.
        self.button.move(
            int(self.rect().right() - frameWidth - buttonSize.width()),
            int((self.rect().bottom() - buttonSize.height() + 1) / 2),
        )
        super(ButtonLineEdit, self).resizeEvent(event)


class InputPanel(QWidget):
    startTrigger = pyqtSignal()
    startLogger = pyqtSignal(str)

    def __init__(self, parent, router):
        super(InputPanel, self).__init__(parent)
        self.router = router
        self.initUI()

    def initUI(self):
        layout = QVBoxLayout()
        layout.setAlignment(Qt.AlignVCenter)
        self.setPanel(layout)
        self.setLayout(layout)

    def setPanel(self, parent):
        w = QWidget()
        panel = QFormLayout()
        panel.setHorizontalSpacing(50)
        panel.setVerticalSpacing(20)
        self.area_x = QSpinBox()
        self.area_x.setMaximum(200)
        self.area_x.setValue(150)
        panel.addRow("布线区域宽度(mm)" if CN else "x", self.area_x)
        self.area_y = QSpinBox()
        self.area_y.setMaximum(200)
        self.area_y.setValue(150)
        panel.addRow("布线区域高度(mm)" if CN else "y", self.area_y)
        self.wg_width = QSpinBox()
        self.wg_width.setMaximum(1000)
        self.wg_width.setValue(50)
        panel.addRow("波导宽度(μm)" if CN else "Waveguide width", self.wg_width)
        self.wg_pitch = QSpinBox()
        self.wg_pitch.setMaximum(500)
        self.wg_pitch.setValue(125)
        panel.addRow("波导间距(μm)" if CN else "Waveguide pitch", self.wg_pitch)
        self.r = QSpinBox()
        self.r.setMaximum(100)
        self.r.setValue(5)
        panel.addRow("波导半径(mm)" if CN else "Waveguide radius", self.r)
        self.N = QSpinBox()
        self.N.setMaximum(5120)
        self.N.setValue(512)
        panel.addRow("通道数量" if CN else "Channels", self.N)
        self.input = ButtonLineEdit(SEARCH_ICON)
        self.input.buttonClicked.connect(self.openFile)
        panel.addRow("输入文件" if CN else "Input file", self.input)
        self.output = ButtonLineEdit(SEARCH_ICON)
        self.output.buttonClicked.connect(self.openLocation)
        panel.addRow("输出文件夹" if CN else "Output location", self.output)
        w.setLayout(panel)
        parent.addWidget(w)

    def openLocation(self):
        options = QFileDialog.Options()
        options |= QFileDialog.DontUseNativeDialog
        fileDir = QFileDialog.getExistingDirectory(
            self, "Open Directory", str(BASE_DIR), QFileDialog.ShowDirsOnly
        )
        BASE_PATH = fileDir
        self.output.setText(BASE_PATH)

    def openFile(self):
        self.input.setText(
            QFileDialog.getOpenFileName(
                self, "Open Workbook", str(BASE_DIR / "data"), "Workbooks (*.xlsx *.xls)"
            )[0]
        )

    def validate(self):
        """Return an error message for the current settings, or ``None``."""
        N = self.N.value()
        if N not in (256, 512):
            return (
                "通道数量必须是 256 或 512。"
                if CN
                else "Channels must be 256 or 512."
            )
        Src = self.input.text().strip()
        if not Src:
            return "请选择输入文件。" if CN else "Choose an input workbook."
        if not Path(Src).is_file():
            return (
                f"输入文件不存在：{Src}" if CN else f"Input workbook does not exist: {Src}"
            )
        SaveFolder = self.output.text().strip()
        if not SaveFolder:
            return "请选择输出文件夹。" if CN else "Choose an output folder."
        try:
            Path(SaveFolder).mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            return (
                f"无法创建输出文件夹：{exc}" if CN else f"Cannot create output folder: {exc}"
            )
        if self.area_x.value() <= 0 or self.area_y.value() <= 0:
            return "布线区域宽度和高度必须大于 0。" if CN else "Routing area must be positive."
        if self.wg_width.value() <= 0:
            return "波导宽度必须大于 0。" if CN else "Waveguide width must be positive."
        if self.wg_pitch.value() <= 0:
            return "波导间距必须大于 0。" if CN else "Waveguide pitch must be positive."
        if self.r.value() <= 0:
            return "波导半径必须大于 0。" if CN else "Waveguide radius must be positive."
        return None

    def start(self):
        error = self.validate()
        if error is not None:
            QMessageBox.critical(self, MW_TITLE, error)
            self.startLogger.emit(error)
            return
        N = self.N.value()
        SaveFolder = self.output.text()
        Src = self.input.text()
        self.startLogger.emit("开始布线......" if CN else "Router Started......")
        self.router.N = N
        self.router.SaveFolder = SaveFolder
        self.router.Src = Src
        self.router.Line_Width = self.wg_width.value() / 1000
        self.router.Dist = self.wg_pitch.value() / 1000
        self.router.Bend_Radius = self.r.value()
        self.router.height = self.area_y.value()
        self.router.width = self.area_x.value()
        self.startTrigger.emit()


def Viewer():
    """Unused viewer helper carried over from the legacy source.

    The decompiled module defines this name as a function holding nested
    ``__init__``/``initUI`` definitions and never calls it, so it is kept as an
    inert placeholder instead of inventing behaviour for it.
    """
    return None


class MainWindow(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.router = Router()
        self.router.logger.connect(self.onLog)
        self.router.finish.connect(self.showResult)
        self.router.error.connect(self.onError)
        self.imageWindow = None
        self.initUI()
        self.initMenu()

    def initUI(self):
        self.setWindowTitle(MW_TITLE)
        self.resize(MW_WIDTH, MW_HEIGHT)
        self.move(0, 0)
        w = QWidget()
        self.setStyleSheet(load_style_sheet())
        self.inputPanel = InputPanel(w, self.router)
        self.b = QPushButton("开始布线" if CN else "Start Routing")
        self.b.clicked.connect(self.inputPanel.start)
        self.logger = QPlainTextEdit(w)
        self.logger.setReadOnly(True)
        self.logger.setMaximumHeight(180)
        self.inputPanel.startLogger.connect(self.logger.appendPlainText)
        self.inputPanel.startTrigger.connect(self.onStart)
        self.principalLayout = QVBoxLayout()
        self.principalLayout.addWidget(self.inputPanel)
        self.principalLayout.addWidget(self.b)
        self.principalLayout.addWidget(self.logger)
        self.principalLayout.setAlignment(self.b, Qt.AlignHCenter)
        w.setLayout(self.principalLayout)
        self.setCentralWidget(w)

    def initMenu(self):
        menuBar = self.menuBar()
        self.initAction()
        menuBar.addMenu("文件" if CN else "File")
        menuBar.addMenu("帮助" if CN else "Help")
        menuBar.addMenu("关于" if CN else "About")

    def initAction(self):
        pass

    def onStart(self):
        if self.router.isRunning():
            self.logger.appendPlainText(
                "布线正在进行中。" if CN else "Routing is already running."
            )
            return
        self.router.start()

    def onLog(self, strCN, strEN):
        self.logger.appendPlainText(strCN if CN else strEN)

    def onError(self, traceback_text):
        self.logger.appendPlainText(("布线失败：\n" if CN else "Routing failed:\n") + traceback_text)
        QMessageBox.critical(self, MW_TITLE, traceback_text.splitlines()[-1])

    def showResult(self, SaveFolder, N):
        SHOWED_IMGS = "fiberBoard" + str(N) + "bend.png"
        image_path = Path(SaveFolder) / SHOWED_IMGS
        self.imageWindow = QDialog(self)
        self.imageWindow.setWindowTitle(
            str(N) + "通道波导排布结果" if CN else str(N) + "channels layout"
        )
        self.imageWindow.setMinimumWidth(960)
        self.imageWindow.setMinimumHeight(720)
        self.imageLabel = QLabel("", self.imageWindow)
        image = QPixmap(str(image_path))
        if image.isNull():
            self.imageLabel.setText(
                f"找不到结果图：{image_path}" if CN else f"Result image not found: {image_path}"
            )
        else:
            self.imageLabel.setPixmap(image.scaled(960, 720))
        self.imageWindow.show()


def app():
    appFont = QFont()
    appFont.setFamily("Microsoft Yahei" if CN else "Arial")
    appFont.setPointSize(14)
    application = QApplication(sys.argv)
    application.setFont(appFont)
    mw = MainWindow()
    mw.show()
    sys.exit(application.exec_())


if __name__ == "__main__":
    app()
