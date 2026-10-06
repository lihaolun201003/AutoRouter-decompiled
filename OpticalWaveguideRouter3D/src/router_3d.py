"""多层分配、三维搜索、层间切换与 1024 通道布线的路由骨架。"""

from .models import Board, Route, Waveguide


class Router3D:
    """3D optical waveguide router skeleton."""

    def __init__(self, board: Board) -> None:
        self.board = board

    def route(self, waveguides: list[Waveguide]) -> list[Route]:
        """预留路由接口；当前不执行路径搜索。"""
        raise NotImplementedError
