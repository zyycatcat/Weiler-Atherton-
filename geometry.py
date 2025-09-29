# geometry.py
from dataclasses import dataclass
from typing import List, Tuple, Optional
import math

Point = Tuple[float, float]
Ring = List[Point]


@dataclass
class PolygonModel:
    rings: List[Ring]
    is_main: bool = False
    is_clipper: bool = False


# 公共常量
EPS = 1e-8

def signed_area(pts: Ring) -> float:
    """多边形带符号面积（正为逆时针）"""
    a = 0.0
    n = len(pts)
    for i in range(n):
        x1, y1 = pts[i]
        x2, y2 = pts[(i+1) % n]
        a += x1 * y2 - x2 * y1
    return a / 2.0

def is_ccw(pts: Ring) -> bool:
    return signed_area(pts) > 0

# 数值相等
def almost_equal(a: float, b: float, eps: float = EPS) -> bool:
    return abs(a - b) <= eps

# 点重合
def point_eq(a: Point, b: Point, eps: float = EPS) -> bool:
    return math.hypot(a[0] - b[0], a[1] - b[1]) <= eps

# 叉积
def orient(a: Point, b: Point, c: Point) -> float:
    """叉积 (b-a) x (c-a)"""
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def on_segment(a: Point, b: Point, p: Point) -> bool:
    """判断点 p 是否在线段 ab 上（包含端点）"""
    if abs(orient(a, b, p)) > EPS:
        return False
    if min(a[0], b[0]) - EPS <= p[0] <= max(a[0], b[0]) + EPS and \
       min(a[1], b[1]) - EPS <= p[1] <= max(a[1], b[1]) + EPS:
        return True
    return False


def seg_intersection(a: Point, b: Point, c: Point, d: Point) -> Optional[Point]:
    """
    计算线段 AB 与 CD 的交点（如果存在单一交点），返回点坐标。
    若平行或完全重合返回 None（重合端点通过 on_segment 方式会被捕捉）。
    """
    x1, y1 = a
    x2, y2 = b
    x3, y3 = c
    x4, y4 = d
    denom = (x1-x2)*(y3-y4) - (y1-y2)*(x3-x4)
    if abs(denom) < EPS:
        # 平行或共线：只处理端点落在线段上的情况
        for p in (a, b):
            if on_segment(c, d, p):
                return p
        for p in (c, d):
            if on_segment(a, b, p):
                return p
        return None
    px = ((x1*y2 - y1*x2)*(x3-x4) - (x1-x2)*(x3*y4 - y3*x4)) / denom
    py = ((x1*y2 - y1*x2)*(y3-y4) - (y1-y2)*(x3*y4 - y3*x4)) / denom
    # 检查落在两段范围内
    if (min(x1, x2)-EPS <= px <= max(x1, x2)+EPS and min(y1, y2)-EPS <= py <= max(y1, y2)+EPS and
            min(x3, x4)-EPS <= px <= max(x3, x4)+EPS and min(y3, y4)-EPS <= py <= max(y3, y4)+EPS):
        return (px, py)
    return None


def point_in_ring(pt: Point, ring: Ring) -> bool:
    """射线法判断点是否在单个环（简单多边形）内部（含边界视为内部）"""
    x, y = pt
    inside = False
    n = len(ring)
    for i in range(n):
        x1, y1 = ring[i]
        x2, y2 = ring[(i+1) % n]
        # 在边上视为内部
        if on_segment((x1, y1), (x2, y2), (x, y)):
            return True
        # 射线交点统计
        if ((y1 > y) != (y2 > y)):
            xinters = (x2 - x1) * (y - y1) / (y2 - y1) + x1
            if xinters > x:
                inside = not inside
    return inside


def point_in_polygon_with_holes(pt: Point, poly: PolygonModel) -> bool:
    """
    判断点是否在 poly 内（考虑洞）。
    poly.rings[0] 是外环，其余是内环（洞）。
    点在外环内部且不在任何内环内部 -> True
    """
    if not poly.rings:
        return False
    if not point_in_ring(pt, poly.rings[0]):
        return False
    for inner in poly.rings[1:]:
        if point_in_ring(pt, inner):
            return False
    return True
