from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QPushButton, QListWidget, QListWidgetItem,
    QHBoxLayout, QVBoxLayout, QLabel, QMessageBox, QFrame
)
from PyQt5.QtCore import Qt, pyqtSignal
from canvas import CanvasWidget
from geometry import PolygonModel


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Weiler-Atherton 多边形裁剪演示")
        self.resize(1200, 800)

        # 主 widget
        main_widget = QWidget()
        self.setCentralWidget(main_widget)

        # 顶部按钮
        self.btn_close_ring = QPushButton("闭合轮廓")
        self.btn_build_done = QPushButton("构建完成")
        self.btn_start_clip = QPushButton("开始裁剪")
        self.btn_clear = QPushButton("清空")

        top_layout = QHBoxLayout()
        top_layout.addWidget(self.btn_close_ring)
        top_layout.addWidget(self.btn_build_done)
        top_layout.addWidget(self.btn_start_clip)
        top_layout.addWidget(self.btn_clear)
        top_layout.addStretch()

        # 创建主水平布局：左侧画布，右侧列表区域
        main_h_layout = QHBoxLayout()

        # 左侧画布
        self.canvas = CanvasWidget()

        # 右侧列表区域
        right_widget = QWidget()
        right_layout = QVBoxLayout()

        # 操作区
        operation_frame = QFrame()
        operation_frame.setFrameStyle(QFrame.Box)
        operation_layout = QVBoxLayout()
        operation_layout.addWidget(QLabel("操作区（放置主多边形和裁剪多边形）"))
        self.operation_list = QListWidget()
        operation_layout.addWidget(self.operation_list)
        operation_frame.setLayout(operation_layout)

        # 绘制区
        drawing_frame = QFrame()
        drawing_frame.setFrameStyle(QFrame.Box)
        drawing_layout = QVBoxLayout()
        drawing_layout.addWidget(QLabel("绘制区（双击可移动至操作区）"))
        self.drawing_list = QListWidget()
        drawing_layout.addWidget(self.drawing_list)
        drawing_frame.setLayout(drawing_layout)

        # 添加到右侧布局
        right_layout.addWidget(operation_frame)
        right_layout.addWidget(drawing_frame)

        # 设置右侧区域宽度
        right_widget.setLayout(right_layout)
        right_widget.setMaximumWidth(300)

        # 添加到主水平布局
        main_h_layout.addWidget(self.canvas, 3)  # 画布占3份
        main_h_layout.addWidget(right_widget, 1)  # 右侧区域占1份

        # 主垂直布局
        main_layout = QVBoxLayout()
        main_layout.addLayout(top_layout)
        main_layout.addLayout(main_h_layout, 1)

        main_widget.setLayout(main_layout)

        # 信号连接
        self.btn_close_ring.clicked.connect(self.on_close_ring)
        self.btn_build_done.clicked.connect(self.on_build_done)
        self.btn_start_clip.clicked.connect(self.on_start_clip)
        self.btn_clear.clicked.connect(self.on_clear)

        # 列表交互信号
        self.operation_list.itemDoubleClicked.connect(
            self.on_operation_item_double_clicked)
        self.drawing_list.itemDoubleClicked.connect(
            self.on_drawing_item_double_clicked)

        # 在 canvas 有新的 polygon 时更新列表
        self.canvas.polygon_added.connect(self.refresh_poly_lists)
        self.canvas.polygons_changed.connect(self.refresh_poly_lists)

        # 初始化列表
        self.refresh_poly_lists()

    def on_close_ring(self):
        """闭合当前正在绘制的环（外环或内环）"""
        ok = self.canvas.close_current_ring()
        if not ok:
            QMessageBox.information(self, "提示", "当前没有有效的环可以闭合。")

    def on_build_done(self):
        """结束当前多边形的构建（将正在绘制的多环组合成一个多边形）"""
        ok = self.canvas.finish_building_polygon()
        if not ok:
            QMessageBox.information(self, "提示", "请先绘制至少一个环并闭合后再构建完成。")
        else:
            self.refresh_poly_lists()

    def on_start_clip(self):
        """开始裁剪，触发 canvas 执行裁剪并显示结果"""
        try:
            self.canvas.perform_clip_and_show()
        except Exception as e:
            QMessageBox.critical(self, "裁剪错误", str(e))

    def on_clear(self):
        """清空所有绘制"""
        self.canvas.clear_all()
        self.refresh_poly_lists()

    def refresh_poly_lists(self):
        """根据 canvas 当前模型刷新两个列表"""
        self.operation_list.clear()
        self.drawing_list.clear()

        for idx, poly in enumerate(self.canvas.polygons):
            name = f"多边形 {idx+1}"
            item = QListWidgetItem(name)
            item.setData(Qt.UserRole, idx)

            if getattr(poly, "in_operation_area", False):
                if getattr(poly, "is_clipper", False):
                    name += "（裁剪多边形）"
                    item = QListWidgetItem(name)
                    item.setData(Qt.UserRole, idx)
                else:
                    name += "（主多边形）"
                    item = QListWidgetItem(name)
                    item.setData(Qt.UserRole, idx)
                self.operation_list.addItem(item)
            else:
                self.drawing_list.addItem(item)

    def on_operation_item_double_clicked(self, item):
        """双击操作区项：移动到绘制区"""
        idx = item.data(Qt.UserRole)
        self.move_to_drawing_area(idx)

    def on_drawing_item_double_clicked(self, item):
        """双击绘制区项：移动到操作区"""
        idx = item.data(Qt.UserRole)
        self.move_to_operation_area(idx)

    def move_to_operation_area(self, idx):
        """将指定多边形移动到操作区"""
        poly = self.canvas.polygons[idx]

        # 检查操作区是否已满
        operation_count = sum(1 for p in self.canvas.polygons if getattr(
            p, "in_operation_area", False))
        if operation_count >= 2:
            QMessageBox.information(self, "提示", "操作区最多只能放入两个多边形")
            return

        # 移动到操作区
        poly.in_operation_area = True

        # 设置角色：第一个放入的是主多边形，第二个是裁剪多边形
        if operation_count == 0:
            poly.is_clipper = False
        else:
            poly.is_clipper = True
            # 确保另一个是主多边形
            for other_idx, other_poly in enumerate(self.canvas.polygons):
                if other_idx != idx and getattr(other_poly, "in_operation_area", False):
                    other_poly.is_clipper = False
                    break

        self.canvas.update()
        self.refresh_poly_lists()

    def move_to_drawing_area(self, idx):
        """将指定多边形移动到绘制区"""
        poly = self.canvas.polygons[idx]

        # 移动到绘制区
        poly.in_operation_area = False
        poly.is_clipper = False

        self.canvas.update()
        self.refresh_poly_lists()
