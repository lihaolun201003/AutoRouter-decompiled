"""预留 CSV、JSON 与 GDS 导出接口；不加载任何导出依赖。"""

from pathlib import Path

from .models import Route


def export_csv(routes: list[Route], path: str | Path) -> None:
    """CSV 导出占位接口；格式细节待定义。"""
    raise NotImplementedError


def export_json(routes: list[Route], path: str | Path) -> None:
    """JSON 导出占位接口；格式细节待定义。"""
    raise NotImplementedError


def export_gds(routes: list[Route], path: str | Path) -> None:
    """GDS 导出占位接口；格式细节待定义。"""
    raise NotImplementedError
