"""预留 Matplotlib 二维、三维布线图及调试可视化接口。"""

from .models import Route


def plot_routes_2d(routes: list[Route]) -> None:
    """二维布线图占位接口。"""
    raise NotImplementedError


def plot_routes_3d(routes: list[Route]) -> None:
    """三维布线图占位接口。"""
    raise NotImplementedError
