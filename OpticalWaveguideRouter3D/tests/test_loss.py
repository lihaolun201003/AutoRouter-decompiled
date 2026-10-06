"""基础损耗测试；不依赖几何、路由或第三方库。"""

from math import isclose
from unittest import TestCase

from src.loss import (
    propagation_loss, bend_loss_90, bend_loss, total_bend_loss, crossing_loss,
)

raises = TestCase().assertRaises


def test_propagation_zero():
    assert isclose(propagation_loss(0), 0, rel_tol=1e-12, abs_tol=1e-12)


def test_propagation_one():
    assert isclose(propagation_loss(1), 0.05, rel_tol=1e-12, abs_tol=1e-12)


def test_propagation_ten():
    assert isclose(propagation_loss(10), 0.5, rel_tol=1e-12, abs_tol=1e-12)


def test_propagation_custom():
    assert isclose(propagation_loss(3, 0.2), 0.6, rel_tol=1e-12, abs_tol=1e-12)


def test_bend_90_radius_2():
    assert isclose(bend_loss_90(2), 7.94, rel_tol=1e-12, abs_tol=1e-12)


def test_bend_90_radius_3():
    assert isclose(bend_loss_90(3), 6.81, rel_tol=1e-12, abs_tol=1e-12)


def test_bend_90_radius_4():
    assert isclose(bend_loss_90(4), 4.59, rel_tol=1e-12, abs_tol=1e-12)


def test_bend_90_radius_5():
    assert isclose(bend_loss_90(5), 2.39, rel_tol=1e-12, abs_tol=1e-12)


def test_bend_90_radius_6():
    assert isclose(bend_loss_90(6), 1.9, rel_tol=1e-12, abs_tol=1e-12)


def test_bend_right_angle():
    assert isclose(bend_loss(5, 90), 2.39, rel_tol=1e-12, abs_tol=1e-12)


def test_bend_half_angle():
    assert isclose(bend_loss(5, 45), 1.195, rel_tol=1e-12, abs_tol=1e-12)


def test_bend_zero_angle():
    assert isclose(bend_loss(5, 0), 0, rel_tol=1e-12, abs_tol=1e-12)


def test_bend_other_radius():
    assert isclose(bend_loss(2, 45), 3.97, rel_tol=1e-12, abs_tol=1e-12)


def test_bend_above_90():
    assert isclose(bend_loss(6, 180), 3.8, rel_tol=1e-12, abs_tol=1e-12)


def test_total_bends():
    assert isclose(total_bend_loss([(5, 45), (6, 180)]), 4.995, rel_tol=1e-12, abs_tol=1e-12)


def test_total_empty():
    assert isclose(total_bend_loss([]), 0, rel_tol=1e-12, abs_tol=1e-12)


def test_negative_length():
    with raises(ValueError):
        propagation_loss(-1)


def test_negative_coefficient():
    with raises(ValueError):
        propagation_loss(1, -0.05)


def test_unknown_radius():
    with raises(ValueError):
        bend_loss_90(2.5)


def test_negative_angle():
    with raises(ValueError):
        bend_loss(5, -1)


def test_angle_unknown_radius():
    with raises(ValueError):
        bend_loss(2.5, 45)


def test_zero_angle_unknown_radius():
    with raises(ValueError):
        bend_loss(2.5, 0)


def test_total_invalid_bend():
    with raises(ValueError):
        total_bend_loss([(5, 45), (2.5, 90)])


def test_unsupported_radius_values():
    for radius in (-1, 0, 1, 7, 5.000000001, float("nan"), float("inf")):
        with raises(ValueError):
            bend_loss_90(radius)


def test_nonfinite_inputs():
    for value in (float("nan"), float("inf"), -float("inf")):
        with raises(ValueError):
            propagation_loss(value)
        with raises(ValueError):
            propagation_loss(1, value)
        with raises(ValueError):
            bend_loss(5, value)


def test_crossing_not_implemented():
    with raises(NotImplementedError):
        crossing_loss(90)
