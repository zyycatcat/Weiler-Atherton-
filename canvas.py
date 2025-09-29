# canvas.py
"""
CanvasWidget: 负责绘制、鼠标交互
"""

from PyQt5.QtWidgets import QWidget
from PyQt5.QtCore import pyqtSignal, QPointF, Qt
from PyQt5.QtGui import QPainter, QPen, QBrush, QColor
from geometry import PolygonModel, is_ccw
from weiler_atherton import weiler_atherton_clip
from geometry import is_ccw, PolygonModel


class CanvasWidget(QWidget):
    polygon_added = pyqtSignal()
    polygons_changed = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.ClickFocus)
        self.polygons = []  # 已构建的多边形列表
        self.current_rings = []  # list[list[(x,y)]]
        self.current_ring_points = []  # 当前未闭合环的点数组

        # 裁剪结果存储为多边形列表
        self.clip_result_polygons = []

        self.info_text = "左键：添加点；右键/闭合按钮：闭合环；构建完成：结束一个多边形"

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            pt = (event.x(), event.y())
            self.current_ring_points.append(pt)
            self.update()
        elif event.button() == Qt.RightButton:
            self.close_current_ring()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QBrush(QColor(255, 255, 255)))

        # 绘制操作区多边形
        self._draw_operation_polygons(painter)

        # 绘制绘制区多边形
        self._draw_draft_polygons(painter)

        if self.clip_result_polygons:
            self._draw_clip_results(painter)

        # 始终显示当前正在绘制的环
        self._draw_current_rings(painter)
        
        # 绘制提示信息（放在左上角边框里）
        painter.setPen(QColor(0, 0, 0))
        margin = 10
        rect = self.rect().adjusted(margin, margin, -margin, -margin)
        painter.drawText(rect, Qt.AlignBottom | Qt.AlignLeft, self.info_text)

    def _draw_operation_polygons(self, painter):
        """绘制操作区多边形"""
        for poly in self.polygons:
            if not getattr(poly, "in_operation_area", False):
                continue

            if getattr(poly, "is_clipper", False):
                # 裁剪多边形：红色实线
                color = QColor(255, 0, 0)
                pen = QPen(color, 2)
            else:
                # 主多边形：黑色实线
                color = QColor(0, 0, 0)
                pen = QPen(color, 2)

            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)

            for ring in poly.rings:
                self._draw_ring(painter, ring)

    def _draw_draft_polygons(self, painter):
        """绘制绘制区多边形（灰色实线）"""
        for poly in self.polygons:
            if getattr(poly, "in_operation_area", False):
                continue

            color = QColor(128, 128, 128)  # 灰色
            pen = QPen(color, 2)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)

            for ring in poly.rings:
                self._draw_ring(painter, ring)

    def _draw_clip_results(self, painter):
        """绘制裁剪结果"""
        for poly in self.clip_result_polygons:
            # 高亮填充结果区域，但边框保持原色
            result_color = QColor(0, 255, 0, 100)  # 半透明绿色填充

            # 填充结果区域
            painter.setBrush(QBrush(result_color))
            painter.setPen(Qt.NoPen)  # 填充时不要边框

            for ring in poly.rings:
                if len(ring) >= 3:
                    polygon_points = [QPointF(x, y) for x, y in ring]
                    painter.drawPolygon(polygon_points)

    def _draw_current_rings(self, painter):
        """绘制当前正在绘制的环"""
        # 当前未闭合环（蓝色实线）
        pen_blue = QPen(QColor(50, 50, 150), 2)
        painter.setPen(pen_blue)
        r = self.current_ring_points
        if len(r) >= 2:
            for i in range(len(r)-1):
                painter.drawLine(r[i][0], r[i][1], r[i+1][0], r[i+1][1])

        # 当前已闭合环（蓝色虚线）
        pen_blue_dash = QPen(QColor(50, 50, 150), 1, Qt.DashLine)
        painter.setPen(pen_blue_dash)
        for r in self.current_rings:
            self._draw_ring(painter, r)

        # 绘制点
        painter.setBrush(QBrush(QColor(0, 0, 0)))
        for r in self.current_rings:
            for x, y in r:
                painter.drawEllipse(QPointF(x, y), 3, 3)
        for x, y in self.current_ring_points:
            painter.drawEllipse(QPointF(x, y), 3, 3)

    def _draw_ring(self, painter, ring):
        """绘制一个环"""
        n = len(ring)
        if n >= 2:
            for i in range(n-1):
                painter.drawLine(ring[i][0], ring[i][1],
                                 ring[i+1][0], ring[i+1][1])
            # 闭合最后一条边
            if ring[0] != ring[-1]:
                painter.drawLine(ring[-1][0], ring[-1][1],
                                 ring[0][0], ring[0][1])

    def close_current_ring(self):
        """闭合当前环"""
        if len(self.current_ring_points) < 3:
            return False

        ring = list(self.current_ring_points)
        if len(ring) > 1 and ring[0] == ring[-1]:
            ring = ring[:-1]
        self.current_rings.append(ring)
        self.current_ring_points = []
        self.update()
        return True

    def finish_building_polygon(self):
        """把 current_rings 组合为一个 PolygonModel 并加入 self.polygons"""
        if len(self.current_rings) == 0:
            return False

        norm_rings = []
        for i, r in enumerate(self.current_rings):
            rr = list(r)
            if len(rr) > 1 and rr[0] == rr[-1]:
                rr = rr[:-1]
            # 方向调整
            if i == 0:  # 外环（默认先画外环）
                if is_ccw(rr):
                    print("外环为顺时针绘制，需要翻转")
                    rr.reverse()
            else:  # 内环
                if not is_ccw(rr):
                    print("内环为逆时针绘制，需要翻转")
                    rr.reverse()
            norm_rings.append(rr)

        poly = PolygonModel(rings=norm_rings)

        # 新构建的多边形默认在绘制区（灰色实线显示）
        poly.in_operation_area = False
        poly.is_clipper = False
        poly.is_main = False

        self.polygons.append(poly)
        self.current_rings = []
        self.polygon_added.emit()
        self.update()
        return True

    def perform_clip_and_show(self):
        """执行裁剪并在画布上显示结果"""
        main_poly = None
        clip_poly = None

        # 只使用操作区中的多边形进行裁剪
        for p in self.polygons:
            if not getattr(p, "in_operation_area", False):
                continue
            if getattr(p, "is_clipper", False):
                clip_poly = p
            else:
                main_poly = p

        if main_poly is None or clip_poly is None:
            raise RuntimeError("请在操作区放置一个主多边形和一个裁剪多边形")

        # 调用 Weiler-Atherton
        result_rings = weiler_atherton_clip(main_poly, clip_poly)

        # 将结果环转换为 PolygonModel 列表
        self.clip_result_polygons = []
        if result_rings:
            # 创建一个结果多边形
            result_poly = PolygonModel(rings=result_rings)
            result_poly.is_result = True
            self.clip_result_polygons.append(result_poly)

        self.update()

    def clear_all(self):
        """清空所有内容"""
        self.polygons = []
        self.current_rings = []
        self.current_ring_points = []
        self.clip_result_polygons = []
        self.update()
