"""核心数据模型的基础保存行为测试。"""

from src.models import Board, Layer, PMT, Point2D, Point3D, Port, Route, Waveguide


def test_point2d_creation():
    point = Point2D(1.0, 2.0)
    assert point.x == 1.0
    assert point.y == 2.0


def test_point3d_creation():
    point = Point3D(1.0, 2.0, 0.0)
    assert point.x == 1.0
    assert point.y == 2.0
    assert point.z == 0.0


def test_port_stores_point3d():
    position = Point3D(1.0, 2.0, 0.0)
    port = Port(id=1, pmt_id=10, local_id=0, position=position)
    assert port.id == 1
    assert port.pmt_id == 10
    assert port.local_id == 0
    assert port.position is position


def test_waveguide_stores_ports():
    start = Port(id=1, pmt_id=10, local_id=0, position=Point3D(1.0, 2.0, 0.0))
    end = Port(id=2, pmt_id=20, local_id=0, position=Point3D(3.0, 4.0, 1.0))
    waveguide = Waveguide(id=10, start_port=start, end_port=end)
    assert waveguide.id == 10
    assert waveguide.start_port is start
    assert waveguide.end_port is end


def test_route_stores_multiple_points():
    first = Point3D(1.0, 2.0, 0.0)
    second = Point3D(3.0, 4.0, 1.0)
    route = Route(waveguide_id=10, points=[first, second])
    assert route.waveguide_id == 10
    assert len(route.points) == 2
    assert route.points[0] is first
    assert route.points[1] is second


def test_layer_creation():
    layer = Layer(id=1, z=2.0)
    assert layer.id == 1
    assert layer.z == 2.0


def test_board_stores_multiple_layers():
    first = Layer(id=0, z=0.0)
    second = Layer(id=1, z=1.0)
    board = Board(width=150.0, height=120.0, layers=[first, second])
    assert board.width == 150.0
    assert board.height == 120.0
    assert len(board.layers) == 2
    assert board.layers[0] is first
    assert board.layers[1] is second


def test_pmt_stores_ports():
    first = Port(id=1, pmt_id=10, local_id=0, position=Point3D(0.0, 0.0, 0.0))
    second = Port(id=2, pmt_id=10, local_id=1, position=Point3D(1.0, 0.0, 0.0))
    pmt = PMT(id=10, ports=[first, second])
    assert pmt.id == 10
    assert len(pmt.ports) == 2
    assert pmt.ports[0] is first
    assert pmt.ports[1] is second


def test_waveguides_between_same_pmts_keep_independent_ids():
    start_a = Port(id=1, pmt_id=10, local_id=0, position=Point3D(0.0, 0.0, 0.0))
    end_a = Port(id=2, pmt_id=20, local_id=0, position=Point3D(2.0, 0.0, 0.0))
    start_b = Port(id=3, pmt_id=10, local_id=1, position=Point3D(0.0, 1.0, 0.0))
    end_b = Port(id=4, pmt_id=20, local_id=1, position=Point3D(2.0, 1.0, 0.0))
    first = Waveguide(id=100, start_port=start_a, end_port=end_a)
    second = Waveguide(id=101, start_port=start_b, end_port=end_b)
    assert first.id == 100
    assert second.id == 101
    assert first.start_port.pmt_id == second.start_port.pmt_id == 10
    assert first.end_port.pmt_id == second.end_port.pmt_id == 20
    assert first.start_port is start_a
    assert first.end_port is end_a
    assert second.start_port is start_b
    assert second.end_port is end_b


def test_port_stores_point2d():
    position = Point2D(1.0, 2.0)
    port = Port(id=1, pmt_id=10, local_id=0, position=position)
    assert port.id == 1
    assert port.pmt_id == 10
    assert port.local_id == 0
    assert port.position is position


def test_route_stores_point2d_list():
    first = Point2D(1.0, 2.0)
    second = Point2D(3.0, 4.0)
    route = Route(waveguide_id=10, points=[first, second])
    assert route.waveguide_id == 10
    assert len(route.points) == 2
    assert route.points[0] is first
    assert route.points[1] is second


def test_port_unassigned_local_id():
    position = Point2D(1.0, 2.0)
    port = Port(id=1, pmt_id=10, local_id=None, position=position)
    assert port.local_id is None
    assert port.position is position


def test_port_undetermined_position():
    port = Port(id=1, pmt_id=10, local_id=3, position=None)
    assert port.local_id == 3
    assert port.position is None


def test_port_fully_unassigned():
    port = Port(id=1, pmt_id=10, local_id=None, position=None)
    assert port.id == 1
    assert port.pmt_id == 10
    assert port.local_id is None
    assert port.position is None


def test_waveguide_stores_unassigned_ports():
    start = Port(id=1, pmt_id=10, local_id=None, position=None)
    end = Port(id=2, pmt_id=20, local_id=None, position=None)
    waveguide = Waveguide(id=10, start_port=start, end_port=end)
    assert waveguide.id == 10
    assert waveguide.start_port is start
    assert waveguide.end_port is end
    assert start.local_id is None and start.position is None
    assert end.local_id is None and end.position is None


from src.models import LineSegment2D, ArcSegment2D, SmoothedRoute2D


def test_line_model():
    a,b=Point2D(0,0),Point2D(1,0)
    line=LineSegment2D(a,b)
    assert line.start is a and line.end is b


def test_arc_model():
    a,b,c=Point2D(1,0),Point2D(0,1),Point2D(0,0)
    arc=ArcSegment2D(a,b,c,1.0)
    assert arc.start is a and arc.end is b and arc.center is c and arc.sweep_rad==1.0


def test_smoothed_model():
    segments=[LineSegment2D(Point2D(0,0),Point2D(1,0))]
    result=SmoothedRoute2D(7,segments)
    assert result.waveguide_id==7 and result.segments is segments
