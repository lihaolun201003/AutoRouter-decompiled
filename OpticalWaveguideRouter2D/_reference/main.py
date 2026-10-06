# decompyle3 version 3.9.3
# Python bytecode version base 3.8.0 (3413)
# Decompiled from: Python 3.10.11 (tags/v3.10.11:7d4cc5a, Apr  5 2023, 00:38:17) [MSC v.1929 64 bit (AMD64)]
# Embedded file name: main.py
import pandas as pd
from problem_graph import create_sim_space, read_sim_space
from wiring_rect_826 import plotter_rect, svg2dwgscr_rect
from wiring_bend_826 import plotter_bend, svg2gds_bend
from waveguide_calculator import calc_index, draw_chart
from PyQt5.QtCore import *
Delta_Arc = 0.001

class Router(QThread):
    logger = pyqtSignal(str, str)
    finish = pyqtSignal(str, int)

    def __init__(self, N=256, SaveFolder='./results', Src='./fiberBoard256.xlsx', Line_Width=0.05, Dist=0.25, Bend_Radius=5, height=150, width=150):
        super(Router, self).__init__()
        self.N = N
        self.SaveFolder = SaveFolder
        self.Src = Src
        self.Line_Width = Line_Width
        self.Dist = Dist
        self.Bend_Radius = Bend_Radius
        self.height = height
        self.width = width

    def run(self):
        self.router(self.N, self.SaveFolder, self.Src, self.Line_Width, self.Dist, self.Bend_Radius, self.height, self.width)

    def router(self, N, SaveFolder, Src, Line_Width, Dist, Bend_Radius, height, width) -> None:
        print("******* Start! ********")
        self.logger.emit("正在进行直波导布线......", "Routing the straight waveguides......")
        print("******* Routing the waveguides without bend... ********")
        df = create_sim_space(Src, SaveFolder, Line_Width, Dist, height=height, N=N)
        df_rect = plotter_rect(df, Line_Width, (Dist + Line_Width), SaveFolder, height=height, N=N, r=Bend_Radius)
        self.logger.emit("正在为波导添加弯曲......", "Adding the waveguide bends......")
        print("******* Adding bend to the routed plain... ********")
        df_bend = plotter_bend(df_rect, Line_Width, Dist + Line_Width, Bend_Radius, Delta_Arc, SaveFolder, "fiberBoard" + str(N) + "bend")
        svg2gds_bend(df_bend, Line_Width, Bend_Radius, "fiberBoard" + str(N) + "bend.gds", SaveFolder)
        self.logger.emit("波导布线完成", "Complete!")
        print("******* All done! ********")
        self.finish.emit(SaveFolder, N)


if __name__ == "__main__":
    N = 512
    SaveFolder = "./results"
    Src = "./fiberBoard" + str(N) + ".xlsx"
    SimSpace = SaveFolder + "fiberBoard" + str(N) + "rect.xlsx"
    Line_Width = 0.05
    Dist = 0.125
    Bend_Radius = 5
    height = 150
    width = 150
    router = Router(N, SaveFolder, Src, Line_Width, Dist, Bend_Radius, height, width)
    router.run()
