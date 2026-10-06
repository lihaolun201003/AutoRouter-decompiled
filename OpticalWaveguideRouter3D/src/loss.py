"""使用前代论文中采用/报告的数据计算基础损耗，长度单位由调用者明确提供。"""

from math import fsum, isfinite

# 前代论文中采用/报告的数据，并非普适物理常数。
PROPAGATION_LOSS_DB_PER_CM: float = 0.05
_BEND_LOSS_90_DB: dict[float, float] = {
    2.0: 7.94,
    3.0: 6.81,
    4.0: 4.59,
    5.0: 2.39,
    6.0: 1.90,
}


def propagation_loss(
    length_cm: float, loss_db_per_cm: float = PROPAGATION_LOSS_DB_PER_CM
) -> float:
    """返回传播损耗 dB；长度为 cm，系数为 dB/cm，均须有限且非负。"""
    if not isfinite(length_cm) or length_cm < 0:
        raise ValueError("length_cm must be finite and nonnegative.")
    if not isfinite(loss_db_per_cm) or loss_db_per_cm < 0:
        raise ValueError("loss_db_per_cm must be finite and nonnegative.")
    return length_cm * loss_db_per_cm


def bend_loss_90(radius_mm: float) -> float:
    """返回给定 mm 半径下的 90 度弯曲损耗 dB；仅接受已报告数据点。"""
    if radius_mm not in _BEND_LOSS_90_DB:
        raise ValueError("radius_mm must be a reported value: 2, 3, 4, 5 or 6.")
    return _BEND_LOSS_90_DB[radius_mm]


def bend_loss(radius_mm: float, angle_deg: float) -> float:
    """按前代候选线性规则 L90(r) * angle_deg / 90 返回 dB，不限制角度上限。"""
    if not isfinite(angle_deg) or angle_deg < 0:
        raise ValueError("angle_deg must be finite and nonnegative.")
    return bend_loss_90(radius_mm) * (angle_deg / 90.0)


def total_bend_loss(bends: list[tuple[float, float]]) -> float:
    """求和各项 (radius_mm, angle_deg) 的弯曲损耗 dB；空列表返回零。"""
    return fsum(bend_loss(radius_mm, angle_deg) for radius_mm, angle_deg in bends)


def crossing_loss(angle_deg: float) -> float:
    """完整 crossing-angle loss 数据尚未确认，获得可靠前代或实验数据前不实现数值模型。"""
    raise NotImplementedError("Reliable crossing-angle loss data has not been confirmed.")
