"""轻量核心数据模型；3D坐标提供基础度量/校验，不包含布线算法。"""

from dataclasses import dataclass
from math import hypot, isfinite


@dataclass
class Point2D:
    """二维坐标点。"""

    x: float
    y: float


@dataclass
class Point3D:
    """3D coordinates in mm; exact equality remains dataclass equality."""

    x: float
    y: float
    z: float

    def __post_init__(self) -> None:
        self.validate()

    def validate(self) -> None:
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not isfinite(v)
               for v in (self.x, self.y, self.z)):
            raise ValueError("Point3D requires finite numeric coordinates in mm.")

    def distance_to(self, other: "Point3D") -> float:
        self.validate()
        if not isinstance(other, Point3D):
            raise TypeError("Expected Point3D.")
        other.validate()
        value = hypot(other.x-self.x, other.y-self.y, other.z-self.z)
        if not isfinite(value):
            raise ValueError("3D distance is not representable.")
        return value

    def is_close(self, other: "Point3D", tol: float = 1e-9) -> bool:
        """Euclidean absolute tolerance in mm, independent of exact equality."""
        if isinstance(tol, bool) or not isinstance(tol, (int, float)) or not isfinite(tol) or tol < 0:
            raise ValueError("Tolerance must be finite and nonnegative.")
        return self.distance_to(other) <= tol


@dataclass
class PMT:
    """保存 PMT 标识符及其端口集合。"""

    id: int
    ports: list["Port"]


@dataclass
class Port:
    """保存端口身份及分配信息。

    local_id=None 表示局部槽位尚未分配，position=None 表示物理位置尚未确定；
    两者都是连接关系已知、布线准备尚未完成时的合法状态。
    """

    id: int
    pmt_id: int
    local_id: int | None
    position: Point2D | Point3D | None


@dataclass
class Waveguide:
    """具有独立 ID 的波导需求，允许同一对 PMT 之间存在多根波导。"""

    id: int
    start_port: Port
    end_port: Port


@dataclass
class Layer:
    """Explicit physical z in mm; no default layer spacing or assignment policy."""

    id: int
    z: float

    def __post_init__(self) -> None:
        self.validate()

    def validate(self) -> None:
        if type(self.id) is not int:
            raise ValueError("Layer id must be an integer.")
        if isinstance(self.z, bool) or not isinstance(self.z, (int, float)) or not isfinite(self.z):
            raise ValueError("Layer z must be explicitly finite, in mm.")

    @property
    def layer_id(self) -> int:
        return self.id

    @property
    def z_mm(self) -> float:
        return self.z


@dataclass
class Route:
    """波导对应的统一维度路径点序列，可为二维或三维。"""

    waveguide_id: int
    points: list[Point2D] | list[Point3D]


@dataclass
class Board:
    """板尺寸与布线层集合。"""

    width: float
    height: float
    layers: list[Layer]


@dataclass
class LineSegment2D:
    """Directed analytic line, with no bound physical unit."""

    start: Point2D
    end: Point2D


@dataclass
class ArcSegment2D:
    """Circular arc: positive sweep is counterclockwise in x-right/y-up coordinates."""

    start: Point2D
    end: Point2D
    center: Point2D
    sweep_rad: float


@dataclass
class SmoothedRoute2D:
    """Independent analytic geometry associated with a skeleton by waveguide_id."""

    waveguide_id: int
    segments: list[LineSegment2D | ArcSegment2D]
