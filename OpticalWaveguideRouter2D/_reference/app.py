# decompyle3 version 3.9.3
# Python bytecode version base 3.8.0 (3413)
# Decompiled from: Python 3.10.11 (tags/v3.10.11:7d4cc5a, Apr  5 2023, 00:38:17) [MSC v.1929 64 bit (AMD64)]
# Embedded file name: app.py
import sys
from PyQt5.QtWidgets import *
from PyQt5.QtGui import *
from PyQt5.QtCore import *
from main import Router
CN = True
MW_TITLE = "自动布线程序" if CN else "AutoRouter"
MW_WIDTH = 960
MW_HEIGHT = 720

class ButtonLineEdit(QLineEdit):
    buttonClicked = pyqtSignal(bool)

    def __init__(self, icon_file, parent=None):
        super(ButtonLineEdit, self).__init__(parent)
        self.button = QToolButton(self)
        self.button.setIcon(QIcon(icon_file))
        self.button.setStyleSheet("border: 0px; padding: 0px;")
        self.button.setCursor(Qt.ArrowCursor)
        self.button.clicked.connect(self.buttonClicked.emit)
        frameWidth = self.style().pixelMetric(QStyle.PM_DefaultFrameWidth)
        buttonSize = self.button.sizeHint()
        self.setStyleSheet("QLineEdit {padding-right: %dpx; }" % (buttonSize.width() + frameWidth + 1))
        self.setMinimumSize(max(self.minimumSizeHint().width(), buttonSize.width() + frameWidth * 2 + 2), max(self.minimumSizeHint().height(), buttonSize.height() + frameWidth * 2 + 2))

    def resizeEvent(self, event):
        buttonSize = self.button.sizeHint()
        frameWidth = self.style().pixelMetric(QStyle.PM_DefaultFrameWidth)
        self.button.move(self.rect().right() - frameWidth - buttonSize.width(), (self.rect().bottom() - buttonSize.height() + 1) / 2)
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
        panel.addRow("布线区域宽度(mm)" if CN else "x", self.area_x)
        self.area_y = QSpinBox()
        self.area_y.setMaximum(200)
        panel.addRow("布线区域高度(mm)" if CN else "y", self.area_y)
        self.wg_width = QSpinBox()
        panel.addRow("波导宽度(μm)" if CN else "Waveguide width", self.wg_width)
        self.wg_pitch = QSpinBox()
        self.wg_pitch.setMaximum(500)
        panel.addRow("波导间距(μm)" if CN else "Waveguide pitch", self.wg_pitch)
        self.r = QSpinBox()
        panel.addRow("波导半径(mm)" if CN else "Waveguide radius", self.r)
        self.N = QSpinBox()
        self.N.setMaximum(5120)
        panel.addRow("通道数量" if CN else "Channels", self.N)
        self.input = ButtonLineEdit("./resource/search.png")
        self.input.buttonClicked.connect(self.openFile)
        panel.addRow("输入文件" if CN else "Input file", self.input)
        self.output = ButtonLineEdit("./resource/search.png")
        self.output.buttonClicked.connect(self.openLocation)
        panel.addRow("输出文件夹" if CN else "Output location", self.output)
        w.setLayout(panel)
        parent.addWidget(w)

    def openLocation(self):
        options = QFileDialog.Options()
        options |= QFileDialog.DontUseNativeDialog
        fileDir = QFileDialog.getExistingDirectory(self, "Open Directory", "./", QFileDialog.ShowDirsOnly)
        BASE_PATH = fileDir
        self.output.setText(BASE_PATH)

    def openFile(self):
        self.input.setText(QFileDialog.getOpenFileName()[0])

    def start(self):
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

    def __init__(self, parent):
        super(Viewer, self).__init__(parent)
        self.initUI()

    def initUI(self):
        pass


class MainWindow(QMainWindow):

    def __init__(self, parent=None):
        super().__init__(parent)
        self.router = Router()
        self.router.logger.connect(self.onLog)
        self.router.finish.connect(self.showResult)
        self.initUI()
        self.initMenu()

    def initUI(self):
        self.setWindowTitle(MW_TITLE)
        self.resize(MW_WIDTH, MW_HEIGHT)
        self.move(0, 0)
        w = QWidget()
        styleFile = open("./style/app.qss").read()
        self.setStyleSheet(styleFile)
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
        mFile = menuBar.addMenu("文件" if CN else "File")
        mHelp = menuBar.addMenu("帮助" if CN else "Help")
        mAbout = menuBar.addMenu("关于" if CN else "About")

    def initAction(self):
        pass

    def onStart(self):
        self.router.start()

    def onLog(self, strCN, strEN):
        self.logger.appendPlainText(strCN if CN else strEN)

    def showResult(self, SaveFolder, N):
        SHOWED_IMGS = "fiberBoard" + str(N) + "bend.png"
        self.imageWindow = QDialog(self)
        self.imageWindow.setWindowTitle(str(N) + "通道波导排布结果" if CN else str(N) + "channels layout")
        self.imageWindow.setMinimumWidth(960)
        self.imageWindow.setMinimumHeight(720)
        self.imageLabel = QLabel("", self.imageWindow)
        image = QPixmap(SaveFolder + "/" + SHOWED_IMGS)
        self.imageLabel.setPixmap(image.scaled(960, 720))
        self.imageWindow.show()


def app():
    appFont = QFont()
    appFont.setFamily("Microsoft Yahei" if CN else "Arial")
    appFont.setPointSize(14)
    app = QApplication(sys.argv)
    app.setFont(appFont)
    mw = MainWindow()
    mw.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    app()
