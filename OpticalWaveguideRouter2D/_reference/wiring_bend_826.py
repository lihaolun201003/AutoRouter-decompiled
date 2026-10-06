# decompyle3 version 3.9.3
# Python bytecode version base 3.8.0 (3413)
# Decompiled from: Python 3.10.11 (tags/v3.10.11:7d4cc5a, Apr  5 2023, 00:38:17) [MSC v.1929 64 bit (AMD64)]
# Embedded file name: wiring_bend_826.py
import pandas as pd, numpy as np, gdspy, matplotlib
import matplotlib.pyplot as plt
matplotlib.rcParams["xtick.direction"] = "in"
matplotlib.rcParams["ytick.direction"] = "in"
matplotlib.rcParams["mathtext.rm"] = "Arial"

class data_linewidth_plot:

    def __init__(self, x, y, **kwargs):
        self.ax = kwargs.pop("ax", plt.gca())
        self.fig = self.ax.get_figure()
        self.lw_data = kwargs.pop("linewidth", 1)
        self.lw = 1
        self.fig.canvas.draw()
        self.ppd = 72.0 / self.fig.dpi
        self.trans = self.ax.transData.transform
        self.linehandle, = (self.ax.plot)([], [], **kwargs)
        if "label" in kwargs:
            kwargs.pop("label")
        self.line, = (self.ax.plot)(x, y, **kwargs)
        self.line.set_color(self.linehandle.get_color())
        self._resize()
        self.cid = self.fig.canvas.mpl_connect("draw_event", self._resize)

    def _resize(self, event=None):
        lw = ((self.trans((1, self.lw_data)) - self.trans((0, 0))) * self.ppd)[1]
        if lw != self.lw:
            self.line.set_linewidth(lw)
            self.lw = lw
            self._redraw_later()

    def _redraw_later(self):
        self.timer = self.fig.canvas.new_timer(interval=10)
        self.timer.single_shot = True
        self.timer.add_callback(lambda: self.fig.canvas.draw_idle())
        self.timer.start()


def plotter_bend(df_rect: pd.DataFrame, line_width: float, dist: float, bend_radius: float=5.0, delta_arc: float=0.001, save_folder: str='./results/', file_name: str='fiberBoard256bend') -> pd.DataFrame:

    def dir_norm(a: list) -> list:
        for i in range(len(a)):
            if a[i] > 0:
                a[i] = 1
            if a[i] < 0:
                a[i] = -1
            return a

    def dir_list(x):
        dir_list = []
        for i in range(len(x.inflection_x) - 2):
            dir_in = dir_norm([x.inflection_x[i] - x.inflection_x[i + 1], x.inflection_y[i] - x.inflection_y[i + 1]])
            dir_out = dir_norm([
             x.inflection_x[i + 2] - x.inflection_x[i + 1], x.inflection_y[i + 2] - x.inflection_y[i + 1]])
            dir_list.append(tuple(np.array(dir_in) + np.array(dir_out)))

        return dir_list

    def elements_round_list(a: list) -> list:
        for i in range(len(a)):
            a[i] = round(a[i], 4)

        return a

    def bend_x_list(x):
        bend_x_list = []
        for i in range(len(x.inflection_x) - 2):
            dir_in = dir_norm([x.inflection_x[i] - x.inflection_x[i + 1], x.inflection_y[i] - x.inflection_y[i + 1]])
            dir_out = dir_norm([
             x.inflection_x[i + 2] - x.inflection_x[i + 1], x.inflection_y[i + 2] - x.inflection_y[i + 1]])
            if x.dx >= bend_radius * 2:
                bend_x_list = bend_x_list + [x.inflection_x[i + 1] + bend_radius * dir_in[0],
                 x.inflection_x[i + 1] + bend_radius * dir_out[0]]
            else:
                bend_x_list = bend_x_list + [x.inflection_x[i + 1] + x.dx * 0.5 * dir_in[0],
                 x.inflection_x[i + 1] + x.dx * 0.5 * dir_out[0]]

        return elements_round_list(bend_x_list)

    def bend_y_list(x):
        bend_y_list = []
        for i in range(len(x.inflection_x) - 2):
            dir_in = dir_norm([x.inflection_x[i] - x.inflection_x[i + 1], x.inflection_y[i] - x.inflection_y[i + 1]])
            dir_out = dir_norm([
             x.inflection_x[i + 2] - x.inflection_x[i + 1], x.inflection_y[i + 2] - x.inflection_y[i + 1]])
            if x.dx >= bend_radius * 2:
                bend_y_list = bend_y_list + [x.inflection_y[i + 1] + bend_radius * dir_in[1],
                 x.inflection_y[i + 1] + bend_radius * dir_out[1]]
            else:
                bend_y_list = bend_y_list + [x.inflection_y[i + 1] + bend_radius * np.sin(np.arccos((bend_radius - x.dx * 0.5) / bend_radius)) * dir_in[1],
                 x.inflection_y[i + 1] + bend_radius * np.sin(np.arccos((bend_radius - x.dx * 0.5) / bend_radius)) * dir_out[1]]

        return elements_round_list(bend_y_list)

    def center_list(x):
        center_list = []
        for i in range(len(x.dir)):
            if x.dx >= bend_radius * 2:
                center_list.append(tuple(np.array([x.inflection_x[i + 1], x.inflection_y[i + 1]]) + bend_radius * np.array(x.dir[i])))
            else:
                center_list.append(tuple(np.array([x.bend_x[i * (len(x.bend_x) - 1)] + bend_radius * x.dir[i][0], x.bend_y[i * (len(x.bend_y) - 1)]])))

        return center_list

    def calc_theta(dx, d):
        theta = np.arccos((bend_radius - dx * 0.5) / bend_radius)
        theta_map_s = [(0, theta), (np.pi - theta, np.pi), (np.pi, np.pi + theta), (2 * np.pi - theta, 2 * np.pi)]
        return theta_map_s[dir_map.index(d)]

    dir_map = [
     (-1.0, -1.0), (1.0, -1.0), (1.0, 1.0), (-1.0, 1.0)]
    theta_map = [(0, np.pi / 2), (np.pi / 2, np.pi), (np.pi, np.pi / 2 * 3), (np.pi / 2 * 3, 2 * np.pi)]
    df = df_rect.copy()
    df["dir"] = df.apply(dir_list, axis=1)
    df["bend_x"] = df.apply(bend_x_list, axis=1)
    df["bend_y"] = df.apply(bend_y_list, axis=1)
    df["center"] = df.apply(center_list, axis=1)
    fig = plt.figure()
    ax = plt.gca()
    ax.set_xlabel("$\\mathrm{x(mm)}$", fontsize=18)
    ax.set_ylabel("$\\mathrm{y(mm)}$", fontsize=18)
    color = [
     "r", "b", "m", "c"]
    for layer in range(4):
        for i in range(df[df["dz"] == layer].shape[0]):
            tempx = df[df["dz"] == layer]["inflection_x"].tolist()[i]
            tempy = df[df["dz"] == layer]["inflection_y"].tolist()[i]
            bendx = df[df["dz"] == layer]["bend_x"].tolist()[i]
            bendy = df[df["dz"] == layer]["bend_y"].tolist()[i]
            dir_list = df[df["dz"] == layer]["dir"].tolist()[i]
            center_list = df[df["dz"] == layer]["center"].tolist()[i]
            dx = df[df["dz"] == layer]["dx"].tolist()[i]
            x_list = [
             tempx[0]] + bendx + [tempx[-1]]
            y_list = [tempy[0]] + bendy + [tempy[-1]]
            theta_list = [calc_theta(dx, d) if dx != 0 else theta_map[dir_map.index(d)] for d in dir_list if dx < bend_radius * 2]
            j = 0
            for k in range(int(len(x_list) / 2)):
                ax.plot((x_list[j:j + 2]), (y_list[j:j + 2]), color=(color[layer]), linewidth=0.2, alpha=1.0)
                j = j + 2

            for k in range(int(len(center_list))):
                arc_x_list = list(center_list[k][0] + bend_radius * np.cos(np.arange(theta_list[k][0], theta_list[k][1], delta_arc)))
                arc_y_list = list(center_list[k][1] + bend_radius * np.sin(np.arange(theta_list[k][0], theta_list[k][1], delta_arc)))
                ax.plot(arc_x_list, arc_y_list, color=(color[layer]), linewidth=0.2, alpha=1.0)

    plt.axis("scaled")
    df["theta"] = df.apply((lambda x: [calc_theta(x.dx, d) if x.dx != 0 else theta_map[dir_map.index(d)] for d in x.dir if x.dx < bend_radius * 2]), axis=1)
    print("******** Output Routed waveguides to svg file and pdf file ********")
    fig.savefig((save_folder + "/" + file_name + ".png"), dpi=150, format="png")
    fig.savefig((save_folder + "/" + file_name + ".pdf"), dpi=3000, format="pdf")
    df.to_excel(save_folder + file_name + ".xlsx")
    return df


def svg2gds_bend(df: pd.DataFrame, line_width: float=0.125, bend_radius: float=5, gds_filename: str='fiberBoard896bend.gds', save_folder: str='./results/') -> None:
    gdspy.current_library = gdspy.GdsLibrary()
    cell = gdspy.Cell("wiring896")
    for i in range(df.shape[0]):
        points = []
        for j in range(len(df["inflection_x"][i])):
            points = points + [tuple([df["inflection_x"][i][j], df["inflection_y"][i][j]])]

        sp = gdspy.FlexPath(points, line_width, corners="circular bend", bend_radius=bend_radius, gdsii_path=True)
        cell.add(sp)

    gdspy.write_gds(save_folder + gds_filename)
