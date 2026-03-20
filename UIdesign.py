import sys
import os
import numpy as np
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QHBoxLayout, QPushButton, QLabel, QStackedWidget,
                             QListWidget, QFrame, QSplitter, QTabWidget,
                             QTextEdit, QTableWidget, QTableWidgetItem,
                             QProgressBar, QFileDialog, QMessageBox,
                             QGroupBox, QFormLayout, QLineEdit, QComboBox,
                             QCheckBox, QSpinBox, QDoubleSpinBox, QSlider)
from PyQt5.QtCore import Qt, QSize
from PyQt5.QtGui import QFont, QPalette, QColor, QIcon


class GeneticAnalyzer:
    """遗传分析计算核心类"""

    def __init__(self):
        self.traits = ['树高', '冠幅', '树冠面积', '体积', '通直度']
        self.heritabilities = {}  # 各性状遗传力
        self.breeding_values = {}  # 各性状育种值
        self.genetic_gains = {}  # 各性状遗传增益

    def calculate_heritability(self, trait_data):
        """计算遗传力"""
        # 模拟计算，实际中应该使用混合线性模型
        genetic_variance = np.var(trait_data) * 0.6  # 假设遗传方差占总方差的60%
        phenotypic_variance = np.var(trait_data)
        heritability = genetic_variance / phenotypic_variance if phenotypic_variance > 0 else 0
        return min(heritability, 0.95)  # 限制最大遗传力

    def calculate_genetic_gain(self, heritability, selection_intensity=0.1):
        """计算遗传增益"""
        # 遗传增益 = 选择强度 × 遗传力 × 表型标准差
        return selection_intensity * heritability * 100  # 以百分比表示

    def calculate_breeding_values(self, trait_data, individual_ids):
        """计算个体育种值"""
        # 模拟育种值计算，基于BLUP方法
        mean_value = np.mean(trait_data)
        std_value = np.std(trait_data) if np.std(trait_data) > 0 else 1

        breeding_values = {}
        for i, ind_id in enumerate(individual_ids):
            # 育种值 = 个体值偏离均值的标准化值 × 遗传力
            deviation = (trait_data[i] - mean_value) / std_value
            breeding_values[ind_id] = deviation * 0.8  # 简化计算

        return breeding_values

    def select_optimal_trait(self, heritabilities, genetic_gains):
        """选择最优性状：综合考虑遗传力和遗传增益"""
        if not heritabilities:
            return None

        # 计算综合得分：遗传力权重0.6，遗传增益权重0.4
        scores = {}
        for trait in heritabilities.keys():
            h2 = heritabilities.get(trait, 0)
            gain = genetic_gains.get(trait, 0)
            score = 0.6 * h2 + 0.4 * (gain / 100)  # 归一化处理
            scores[trait] = score

        # 返回得分最高的性状
        optimal_trait = max(scores.items(), key=lambda x: x[1])[0]
        return optimal_trait

    def select_top_individuals(self, breeding_values, top_n=10):
        """基于育种值选择Top N个体"""
        if not breeding_values:
            return []

        # 按育种值降序排序
        sorted_individuals = sorted(breeding_values.items(), key=lambda x: x[1], reverse=True)
        return sorted_individuals[:top_n]


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("DeepForest Breeder - 林木遗传分析平台")
        self.setGeometry(100, 100, 1400, 900)

        # 初始化遗传分析器
        self.genetic_analyzer = GeneticAnalyzer()

        # 模拟数据
        self.setup_mock_data()

        self.set_dark_theme()
        self.setup_ui()

    def setup_mock_data(self):
        """设置模拟数据"""
        np.random.seed(42)  # 确保结果可重现

        self.individual_ids = [f"IND_{1000 + i}" for i in range(100)]
        self.family_ids = [f"FAM_{(i % 10) + 1}" for i in range(100)]

        # 模拟各性状数据 - 更新为新的表型参数
        self.trait_data = {
            '树高': np.random.normal(15, 3, 100),  # 均值15m，标准差3m
            '冠幅': np.random.normal(8, 1.5, 100),  # 均值8m，标准差1.5m
            '树冠面积': np.random.normal(50, 12, 100),  # 均值50m²，标准差12m²
            '体积': np.random.normal(120, 30, 100),  # 均值120m³，标准差30m³
            '通直度': np.random.normal(0.85, 0.1, 100)  # 均值0.85，标准差0.1 (0-1之间)
        }

    def set_dark_theme(self):
        """设置深色主题"""
        self.setStyleSheet("""
            QMainWindow {
                background-color: #2b2b2b;
                color: #ffffff;
            }
            QListWidget {
                background-color: #3c3f41;
                color: #ffffff;
                border: 1px solid #555555;
                border-radius: 5px;
            }
            QListWidget::item {
                padding: 10px;
                border-bottom: 1px solid #555555;
            }
            QListWidget::item:selected {
                background-color: #4a5b7c;
                color: #ffffff;
            }
            QPushButton {
                background-color: #4a5b7c;
                color: #ffffff;
                border: none;
                padding: 8px 15px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #5a6b8c;
            }
            QPushButton:pressed {
                background-color: #3a4b6c;
            }
            QLabel {
                color: #ffffff;
            }
            QGroupBox {
                color: #ffffff;
                border: 2px solid #555555;
                border-radius: 8px;
                margin-top: 10px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px 0 5px;
            }
            QTableWidget {
                background-color: #3c3f41;
                color: #ffffff;
                gridline-color: #555555;
                border: 1px solid #555555;
            }
            QHeaderView::section {
                background-color: #4a5b7c;
                color: #ffffff;
                padding: 5px;
                border: 1px solid #555555;
            }
            QTabWidget::pane {
                border: 1px solid #555555;
                background-color: #3c3f41;
            }
            QTabBar::tab {
                background-color: #4a5b7c;
                color: #ffffff;
                padding: 8px 15px;
                margin-right: 2px;
            }
            QTabBar::tab:selected {
                background-color: #5a6b8c;
            }
        """)

    def setup_ui(self):
        """设置主界面"""
        # 创建中央部件
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # 主布局
        main_layout = QHBoxLayout(central_widget)

        # 创建分割器
        splitter = QSplitter(Qt.Horizontal)

        # 左侧导航栏
        left_widget = self.create_left_sidebar()
        splitter.addWidget(left_widget)

        # 右侧主区域
        right_widget = self.create_main_content()
        splitter.addWidget(right_widget)

        # 设置分割器比例
        splitter.setSizes([200, 1200])

        main_layout.addWidget(splitter)

    def create_left_sidebar(self):
        """创建左侧导航栏"""
        sidebar = QWidget()
        sidebar.setMaximumWidth(250)
        layout = QVBoxLayout(sidebar)

        # 标题
        title_label = QLabel("TreeGenetic AI ")
        title_label.setFont(QFont("Arial", 10, QFont.Bold))
        title_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(title_label)

        # 导航列表
        self.nav_list = QListWidget()
        self.nav_list.addItems([
            "🏠 项目总览",
            "📁 数据管理",
            "🌳 单木分割",
            "📊 表型提取",
            "🧬 遗传分析",
            "📈 选择预测",
            "📋 可视化报告"
        ])
        self.nav_list.currentRowChanged.connect(self.change_page)
        layout.addWidget(self.nav_list)

        # 底部状态信息
        status_group = QGroupBox("系统状态")
        status_layout = QVBoxLayout()

        status_layout.addWidget(QLabel("当前项目: 模拟数据"))
        status_layout.addWidget(QLabel("数据状态: 已加载"))
        status_layout.addWidget(QLabel("分析状态: 就绪"))

        status_group.setLayout(status_layout)
        layout.addWidget(status_group)

        return sidebar

    def create_main_content(self):
        """创建右侧主内容区域"""
        main_content = QWidget()
        layout = QVBoxLayout(main_content)

        # 创建堆叠窗口
        self.stacked_widget = QStackedWidget()

        # 添加各个页面
        self.stacked_widget.addWidget(self.create_dashboard_page())  # 0: 项目总览
        self.stacked_widget.addWidget(self.create_data_management_page())  # 1: 数据管理
        self.stacked_widget.addWidget(self.create_tree_segmentation_page())  # 2: 单木分割
        self.stacked_widget.addWidget(self.create_phenotype_page())  # 3: 表型提取
        self.stacked_widget.addWidget(self.create_genetic_analysis_page())  # 4: 遗传分析
        self.stacked_widget.addWidget(self.create_selection_page())  # 5: 选择预测
        self.stacked_widget.addWidget(self.create_visualization_page())  # 6: 可视化报告

        layout.addWidget(self.stacked_widget)

        return main_content

    def create_dashboard_page(self):
        """创建项目总览页面"""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        # 标题
        title = QLabel("项目总览")
        title.setFont(QFont("Arial", 16, QFont.Bold))
        layout.addWidget(title)

        # 统计卡片
        stats_layout = QHBoxLayout()

        # # 项目统计卡片 - 更新统计信息
        # stats_cards = [
        #     ("Number", "3", "#4a5b7c"),
        #     ("分析个体", "100", "#2e7d32"),
        #     ("遗传力", "0.65", "#c62828"),
        #     ("完成度", "92%", "#ed6c02")
        # ]

        # for stat_name, stat_value, color in stats_cards:
        #     card = self.create_stat_card(stat_name, stat_value, color)
        #     stats_layout.addWidget(card)

        layout.addLayout(stats_layout)

        # 图表区域
        charts_tabs = QTabWidget()

        # 育种值分布
        heritability_tab = QWidget()
        heritability_layout = QVBoxLayout(heritability_tab)
        heritability_layout.addWidget(QLabel("📊 表型性状育种值分布 (模拟)"))
        heritability_layout.addWidget(QLabel("树高: 15.72 | 冠幅: 8.58 | 树冠面积: 40.65 | 体积: 80.68 | 通直度: 0.81"))
        charts_tabs.addTab(heritability_tab, "育种值分布")

        # 育种值排名
        breeding_tab = QWidget()
        breeding_layout = QVBoxLayout(breeding_tab)
        breeding_layout.addWidget(QLabel("🏆 综合育种值排名TOP 10 (模拟)"))

        # 创建模拟排名表格
        table = QTableWidget(10, 3)
        table.setHorizontalHeaderLabels(["排名", "个体ID", "综合育种值"])
        for i in range(10):
            table.setItem(i, 0, QTableWidgetItem(str(i + 1)))
            table.setItem(i, 1, QTableWidgetItem(f"IND_{1000 + i}"))
            table.setItem(i, 2, QTableWidgetItem(f"{0.85 - i * 0.05:.2f}"))
        breeding_layout.addWidget(table)
        charts_tabs.addTab(breeding_tab, "育种值排名")

        layout.addWidget(charts_tabs)

        return widget

    def create_stat_card(self, title, value, color):
        """创建统计卡片"""
        card = QFrame()
        card.setStyleSheet(f"""
            QFrame {{
                background-color: {color};
                border-radius: 8px;
                padding: 15px;
            }}
        """)
        card.setFixedSize(150, 80)

        layout = QVBoxLayout(card)
        layout.addWidget(QLabel(title))

        value_label = QLabel(value)
        value_label.setFont(QFont("Arial", 20, QFont.Bold))
        layout.addWidget(value_label)

        return card

    def create_data_management_page(self):
        """创建数据管理页面"""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        title = QLabel("📁 数据管理")
        title.setFont(QFont("Arial", 16, QFont.Bold))
        layout.addWidget(title)

        # 数据导入区域
        import_group = QGroupBox("数据导入")
        import_layout = QVBoxLayout()

        # 遥感数据导入
        remote_sensing_layout = QHBoxLayout()
        remote_sensing_layout.addWidget(QLabel("图像数据:"))
        self.remote_data_path = QLineEdit()
        # self.remote_data_path.setPlaceholderText("选择遥感影像或点云数据...")
        remote_sensing_layout.addWidget(self.remote_data_path)
        browse_remote_btn = QPushButton("浏览")
        browse_remote_btn.clicked.connect(self.browse_remote_data)
        remote_sensing_layout.addWidget(browse_remote_btn)
        import_layout.addLayout(remote_sensing_layout)

        # 田间设计数据
        # field_layout = QHBoxLayout()
        # # field_layout.addWidget(QLabel("田间设计:"))
        # self.field_data_path = QLineEdit()
        # self.field_data_path.setPlaceholderText("选择田间设计表格...")
        # field_layout.addWidget(self.field_data_path)
        # browse_field_btn = QPushButton("浏览")
        # browse_field_btn.clicked.connect(self.browse_field_data)
        # field_layout.addWidget(browse_field_btn)
        # import_layout.addLayout(field_layout)

        import_group.setLayout(import_layout)
        layout.addWidget(import_group)

        # 数据预览
        preview_group = QGroupBox("数据预览")
        preview_layout = QVBoxLayout()

        preview_tabs = QTabWidget()

        # 遥感数据预览
        remote_preview = QWidget()
        remote_preview_layout = QVBoxLayout(remote_preview)
        remote_preview_layout.addWidget(QLabel("图像数据预览区域"))
        remote_preview_layout.addWidget(QLabel("(此处将显示图像数据)"))
        # preview_tabs.addTab(remote_preview, "遥感数据")

        # 田间设计预览
        # field_preview = QWidget()
        # field_preview_layout = QVBoxLayout(field_preview)
        # field_preview_layout.addWidget(QLabel("田间设计数据预览"))
        # preview_tabs.addTab(field_preview, "田间设计")

        preview_layout.addWidget(preview_tabs)
        preview_group.setLayout(preview_layout)
        layout.addWidget(preview_group)

        return widget

    def create_tree_segmentation_page(self):
        """创建单木分割页面"""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        title = QLabel("🌳 单木分割")
        title.setFont(QFont("Arial", 16, QFont.Bold))
        layout.addWidget(title)

        # 分割控制区域
        control_group = QGroupBox("分割参数设置")
        control_layout = QFormLayout()

        self.model_combo = QComboBox()
        self.model_combo.addItems(["PointNet++", "Mask R-CNN", "U-Net", "自定义模型"])
        control_layout.addRow("选择模型:", self.model_combo)

        self.confidence_slider = QSlider(Qt.Horizontal)
        self.confidence_slider.setRange(50, 95)
        self.confidence_slider.setValue(80)
        control_layout.addRow("置信度阈值:", self.confidence_slider)

        self.min_area_spin = QSpinBox()
        self.min_area_spin.setRange(1, 100)
        self.min_area_spin.setValue(10)
        control_layout.addRow("最小树冠面积:", self.min_area_spin)

        control_group.setLayout(control_layout)
        layout.addWidget(control_group)

        # 可视化区域
        viz_layout = QHBoxLayout()

        # 原图
        original_group = QGroupBox("原始数据")
        original_layout = QVBoxLayout()
        original_layout.addWidget(QLabel("原始影像/点云显示区域"))
        original_group.setLayout(original_layout)
        viz_layout.addWidget(original_group)

        # 分割结果
        result_group = QGroupBox("分割结果")
        result_layout = QVBoxLayout()
        result_layout.addWidget(QLabel("单木分割结果可视化"))
        result_group.setLayout(result_layout)
        viz_layout.addWidget(result_group)

        layout.addLayout(viz_layout)

        # 控制按钮
        button_layout = QHBoxLayout()
        start_btn = QPushButton("开始分割")
        start_btn.clicked.connect(self.start_segmentation)
        button_layout.addWidget(start_btn)

        self.segmentation_progress = QProgressBar()
        button_layout.addWidget(self.segmentation_progress)

        layout.addLayout(button_layout)

        return widget

    def create_phenotype_page(self):
        """创建表型提取页面 - 已更新表型参数"""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        title = QLabel("📊 表型提取与整理")
        title.setFont(QFont("Arial", 16, QFont.Bold))
        layout.addWidget(title)

        # 性状选择
        traits_group = QGroupBox("选择表型性状")
        traits_layout = QVBoxLayout()

        self.trait_height = QCheckBox("树高 (m)")
        self.trait_height.setChecked(True)
        traits_layout.addWidget(self.trait_height)

        self.trait_crown = QCheckBox("冠幅 (m)")
        self.trait_crown.setChecked(True)
        traits_layout.addWidget(self.trait_crown)

        self.trait_crown_area = QCheckBox("树冠面积 (m²)")
        self.trait_crown_area.setChecked(True)
        traits_layout.addWidget(self.trait_crown_area)

        self.trait_volume = QCheckBox("体积 (m³)")
        traits_layout.addWidget(self.trait_volume)

        self.trait_straightness = QCheckBox("通直度 (0-1)")
        traits_layout.addWidget(self.trait_straightness)

        traits_group.setLayout(traits_layout)
        layout.addWidget(traits_group)

        # 数据表格
        table_group = QGroupBox("表型数据表格")
        table_layout = QVBoxLayout()

        self.phenotype_table = QTableWidget(0, 7)
        self.phenotype_table.setHorizontalHeaderLabels([
            "树木ID", "树高(m)", "冠幅(m)", "树冠面积(m²)", "体积(m³)", "通直度", "家系匹配"
        ])
        table_layout.addWidget(self.phenotype_table)

        table_group.setLayout(table_layout)
        layout.addWidget(table_group)

        # 操作按钮
        button_layout = QHBoxLayout()
        extract_btn = QPushButton("提取表型")
        extract_btn.clicked.connect(self.extract_phenotypes)
        button_layout.addWidget(extract_btn)

        match_btn = QPushButton("自动匹配家系")
        match_btn.clicked.connect(self.auto_match_families)
        button_layout.addWidget(match_btn)

        export_btn = QPushButton("导出数据")
        export_btn.clicked.connect(self.export_phenotype_data)
        button_layout.addWidget(export_btn)

        layout.addLayout(button_layout)

        return widget


    def create_genetic_analysis_page(self):
        """创建遗传分析页面 - 已更新性状选项"""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        title = QLabel("🧬 遗传分析")
        title.setFont(QFont("Arial", 16, QFont.Bold))
        layout.addWidget(title)

        # 分析向导标签页
        analysis_tabs = QTabWidget()

        # 步骤1: 模型选择
        step1_tab = QWidget()
        step1_layout = QFormLayout(step1_tab)

        self.trait_combo = QComboBox()
        self.trait_combo.addItems(["树高", "冠幅", "树冠面积", "体积", "通直度"])
        step1_layout.addRow("选择性状:", self.trait_combo)

        self.model_type_combo = QComboBox()
        self.model_type_combo.addItems(["线性混合模型", "动物模型", "多性状模型"])
        step1_layout.addRow("遗传模型:", self.model_type_combo)

        self.fixed_effect_combo = QComboBox()
        self.fixed_effect_combo.addItems(["区块", "年份", "区块+年份"])
        step1_layout.addRow("固定效应:", self.fixed_effect_combo)

        # 选择强度设置
        self.selection_intensity_step1 = QSlider(Qt.Horizontal)
        self.selection_intensity_step1.setRange(1, 30)
        self.selection_intensity_step1.setValue(10)
        step1_layout.addRow("选择强度(%):", self.selection_intensity_step1)

        analysis_tabs.addTab(step1_tab, "步骤1: 模型设置")

        # 步骤2: 运行分析
        step2_tab = QWidget()
        step2_layout = QVBoxLayout(step2_tab)

        step2_layout.addWidget(QLabel("点击开始按钮运行遗传分析:"))

        run_btn = QPushButton("开始分析")
        run_btn.clicked.connect(self.run_genetic_analysis)
        step2_layout.addWidget(run_btn)

        self.analysis_progress = QProgressBar()
        step2_layout.addWidget(self.analysis_progress)

        # 日志输出
        self.analysis_log = QTextEdit()
        self.analysis_log.setPlaceholderText("分析日志将显示在这里...")
        step2_layout.addWidget(self.analysis_log)

        analysis_tabs.addTab(step2_tab, "步骤2: 运行分析")

        # 步骤3: 结果查看 - 已添加遗传增益显示
        step3_tab = QWidget()
        step3_layout = QVBoxLayout(step3_tab)

        # 关键遗传参数卡片
        params_layout = QHBoxLayout()

        # 遗传力卡片
        heritability_card = QGroupBox("遗传力估计")
        heritability_card_layout = QVBoxLayout()
        self.heritability_value = QLabel("h² = 0.000 ± 0.000")
        self.heritability_value.setFont(QFont("Arial", 16, QFont.Bold))
        self.heritability_value.setStyleSheet("color: #4CAF50; padding: 10px;")
        heritability_card_layout.addWidget(self.heritability_value)

        self.heritability_interpretation = QLabel("遗传控制程度: 未分析")
        self.heritability_interpretation.setStyleSheet("color: #BDBDBD;")
        heritability_card_layout.addWidget(self.heritability_interpretation)
        heritability_card.setLayout(heritability_card_layout)
        params_layout.addWidget(heritability_card)

        # 遗传增益卡片
        genetic_gain_card = QGroupBox("遗传增益预测")
        genetic_gain_card_layout = QVBoxLayout()
        self.genetic_gain_value = QLabel("ΔG = 0.00%")
        self.genetic_gain_value.setFont(QFont("Arial", 16, QFont.Bold))
        self.genetic_gain_value.setStyleSheet("color: #FF9800; padding: 10px;")
        genetic_gain_card_layout.addWidget(self.genetic_gain_value)

        self.genetic_gain_interpretation = QLabel("选择效果: 未分析")
        self.genetic_gain_interpretation.setStyleSheet("color: #BDBDBD;")
        genetic_gain_card_layout.addWidget(self.genetic_gain_interpretation)
        genetic_gain_card.setLayout(genetic_gain_card_layout)
        params_layout.addWidget(genetic_gain_card)

        # 选择响应卡片
        response_card = QGroupBox("选择响应")
        response_card_layout = QVBoxLayout()
        self.response_value = QLabel("R = 0.000")
        self.response_value.setFont(QFont("Arial", 16, QFont.Bold))
        self.response_value.setStyleSheet("color: #2196F3; padding: 10px;")
        response_card_layout.addWidget(self.response_value)

        self.response_interpretation = QLabel("育种进展: 未分析")
        self.response_interpretation.setStyleSheet("color: #BDBDBD;")
        response_card_layout.addWidget(self.response_interpretation)
        response_card.setLayout(response_card_layout)
        params_layout.addWidget(response_card)

        step3_layout.addLayout(params_layout)

        # 方差组分分析
        variance_group = QGroupBox("方差组分分析")
        variance_layout = QHBoxLayout()

        # 方差组分饼图说明
        variance_info = QVBoxLayout()
        variance_info.addWidget(QLabel("方差组分比例:"))

        self.genetic_variance_label = QLabel("遗传方差: 0.0%")
        self.genetic_variance_label.setStyleSheet("color: #4CAF50;")
        variance_info.addWidget(self.genetic_variance_label)

        self.environment_variance_label = QLabel("环境方差: 0.0%")
        self.environment_variance_label.setStyleSheet("color: #FF9800;")
        variance_info.addWidget(self.environment_variance_label)

        self.residual_variance_label = QLabel("残差方差: 0.0%")
        self.residual_variance_label.setStyleSheet("color: #2196F3;")
        variance_info.addWidget(self.residual_variance_label)

        variance_info.addStretch()
        variance_layout.addLayout(variance_info)

        # 添加一个模拟的方差组分显示区域
        variance_display = QLabel("(方差组分饼图将显示在这里)")
        variance_display.setAlignment(Qt.AlignCenter)
        variance_display.setStyleSheet("""
            QLabel {
                background-color: #3c3f41;
                border: 2px dashed #555555;
                border-radius: 10px;
                padding: 40px;
                color: #888888;
            }
        """)
        variance_display.setMinimumHeight(150)
        variance_layout.addWidget(variance_display)

        variance_group.setLayout(variance_layout)
        step3_layout.addWidget(variance_group)

        # 育种值分布
        breeding_layout = QHBoxLayout()

        # 育种值统计
        breeding_stats_group = QGroupBox("育种值统计")
        breeding_stats_layout = QFormLayout()

        self.mean_breeding_value = QLabel("0.000")
        breeding_stats_layout.addRow("平均育种值:", self.mean_breeding_value)

        self.std_breeding_value = QLabel("0.000")
        breeding_stats_layout.addRow("育种值标准差:", self.std_breeding_value)

        self.max_breeding_value = QLabel("0.000")
        breeding_stats_layout.addRow("最大育种值:", self.max_breeding_value)

        self.min_breeding_value = QLabel("0.000")
        breeding_stats_layout.addRow("最小育种值:", self.min_breeding_value)

        breeding_stats_group.setLayout(breeding_stats_layout)
        breeding_layout.addWidget(breeding_stats_group)

        # 育种值分布图
        breeding_dist_group = QGroupBox("育种值分布")
        breeding_dist_layout = QVBoxLayout()
        breeding_dist_display = QLabel("(育种值分布直方图将显示在这里)")
        breeding_dist_display.setAlignment(Qt.AlignCenter)
        breeding_dist_display.setStyleSheet("""
            QLabel {
                background-color: #3c3f41;
                border: 2px dashed #555555;
                border-radius: 10px;
                padding: 40px;
                color: #888888;
            }
        """)
        breeding_dist_display.setMinimumHeight(150)
        breeding_dist_layout.addWidget(breeding_dist_display)
        breeding_dist_group.setLayout(breeding_dist_layout)
        breeding_layout.addWidget(breeding_dist_group)

        step3_layout.addLayout(breeding_layout)

        # 育种值表格
        breeding_table_group = QGroupBox("个体育种值排名")
        breeding_table_layout = QVBoxLayout()

        # 表格控制
        table_control_layout = QHBoxLayout()
        table_control_layout.addWidget(QLabel("显示前"))
        self.top_n_breeding = QSpinBox()
        self.top_n_breeding.setRange(10, 100)
        self.top_n_breeding.setValue(20)
        self.top_n_breeding.valueChanged.connect(self.update_breeding_table)
        table_control_layout.addWidget(self.top_n_breeding)
        table_control_layout.addWidget(QLabel("个个体"))
        table_control_layout.addStretch()

        export_breeding_btn = QPushButton("导出育种值")
        export_breeding_btn.clicked.connect(self.export_breeding_values)
        table_control_layout.addWidget(export_breeding_btn)

        breeding_table_layout.addLayout(table_control_layout)

        self.breeding_value_table = QTableWidget(0, 4)
        self.breeding_value_table.setHorizontalHeaderLabels([
            "排名", "个体ID", "家系", "育种值"
        ])
        breeding_table_layout.addWidget(self.breeding_value_table)

        breeding_table_group.setLayout(breeding_table_layout)
        step3_layout.addWidget(breeding_table_group)

        analysis_tabs.addTab(step3_tab, "步骤3: 查看结果")

        layout.addWidget(analysis_tabs)

        return widget

    def update_genetic_gain_display(self, trait):
        """更新遗传增益显示"""
        if trait in self.genetic_analyzer.heritabilities:
            h2 = self.genetic_analyzer.heritabilities[trait]
            selection_intensity = self.selection_intensity_step1.value() / 100.0

            # 计算遗传增益
            genetic_gain = self.genetic_analyzer.calculate_genetic_gain(h2, selection_intensity)

            # 计算选择响应 (R = i * h * σp)
            phenotypic_std = np.std(self.trait_data[trait])
            selection_response = selection_intensity * np.sqrt(h2) * phenotypic_std

            # 更新遗传增益显示
            self.genetic_gain_value.setText(f"ΔG = {genetic_gain:.2f}%")

            # 更新选择响应显示
            if trait == '树高':
                unit = "m"
            elif trait == '冠幅':
                unit = "m"
            elif trait == '树冠面积':
                unit = "m²"
            elif trait == '体积':
                unit = "m³"
            else:  # 通直度
                unit = ""

            self.response_value.setText(f"R = {selection_response:.3f} {unit}")

            # 更新解释文本
            if genetic_gain > 15:
                gain_interpretation = "极高遗传增益"
            elif genetic_gain > 10:
                gain_interpretation = "高遗传增益"
            elif genetic_gain > 5:
                gain_interpretation = "中等遗传增益"
            else:
                gain_interpretation = "低遗传增益"

            self.genetic_gain_interpretation.setText(f"选择效果: {gain_interpretation}")
            self.response_interpretation.setText(f"育种进展: 每代提升 {selection_response:.3f}{unit}")

            # 更新方差组分
            genetic_variance_percent = h2 * 100
            environmental_variance_percent = (1 - h2) * 60  # 假设环境方差占剩余方差的60%
            residual_variance_percent = 100 - genetic_variance_percent - environmental_variance_percent

            self.genetic_variance_label.setText(f"遗传方差: {genetic_variance_percent:.1f}%")
            self.environment_variance_label.setText(f"环境方差: {environmental_variance_percent:.1f}%")
            self.residual_variance_label.setText(f"残差方差: {residual_variance_percent:.1f}%")

            # 更新育种值统计
            if trait in self.genetic_analyzer.breeding_values:
                breeding_values = list(self.genetic_analyzer.breeding_values[trait].values())
                if breeding_values:
                    self.mean_breeding_value.setText(f"{np.mean(breeding_values):.3f}")
                    self.std_breeding_value.setText(f"{np.std(breeding_values):.3f}")
                    self.max_breeding_value.setText(f"{np.max(breeding_values):.3f}")
                    self.min_breeding_value.setText(f"{np.min(breeding_values):.3f}")

    def update_breeding_table(self):
        """更新育种值表格"""
        # 这个函数会在步骤3的spinbox值改变时调用
        current_trait = self.trait_combo.currentText()
        if current_trait in self.genetic_analyzer.breeding_values:
            breeding_values = self.genetic_analyzer.breeding_values[current_trait]
            top_n = self.top_n_breeding.value()

            # 按育种值排序
            sorted_individuals = sorted(breeding_values.items(), key=lambda x: x[1], reverse=True)[:top_n]

            self.breeding_value_table.setRowCount(len(sorted_individuals))

            for i, (ind_id, breeding_value) in enumerate(sorted_individuals):
                # 查找个体对应的家系
                family_index = self.individual_ids.index(ind_id)
                family_id = self.family_ids[family_index]

                self.breeding_value_table.setItem(i, 0, QTableWidgetItem(str(i + 1)))
                self.breeding_value_table.setItem(i, 1, QTableWidgetItem(ind_id))
                self.breeding_value_table.setItem(i, 2, QTableWidgetItem(family_id))
                self.breeding_value_table.setItem(i, 3, QTableWidgetItem(f"{breeding_value:.3f}"))

    def export_breeding_values(self):
        """导出育种值数据"""
        if self.breeding_value_table.rowCount() == 0:
            QMessageBox.warning(self, "警告", "没有可导出的育种值数据！")
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self, "导出育种值数据", "", "CSV文件 (*.csv)"
        )
        if file_path:
            QMessageBox.information(self, "成功", f"育种值数据已导出到: {file_path}")

    def create_selection_page(self):
        """创建选择预测页面 - 已更新为新的表型参数"""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        title = QLabel("📈 遗传选择与优良个体筛选")
        title.setFont(QFont("Arial", 16, QFont.Bold))
        layout.addWidget(title)

        # 性状比较区域
        comparison_group = QGroupBox("性状遗传参数比较")
        comparison_layout = QVBoxLayout()

        # 创建性状比较表格
        self.trait_comparison_table = QTableWidget(0, 4)
        self.trait_comparison_table.setHorizontalHeaderLabels([
            "性状", "遗传力(h²)", "遗传增益(%)", "综合得分"
        ])
        comparison_layout.addWidget(self.trait_comparison_table)

        # 最优性状显示
        self.optimal_trait_label = QLabel("最优性状: 未计算")
        self.optimal_trait_label.setFont(QFont("Arial", 14, QFont.Bold))
        self.optimal_trait_label.setStyleSheet("color: #FF9800; padding: 10px;")
        comparison_layout.addWidget(self.optimal_trait_label)

        comparison_group.setLayout(comparison_layout)
        layout.addWidget(comparison_group)

        # 选择设置
        strategy_group = QGroupBox("选择参数设置")
        strategy_layout = QFormLayout()

        self.selection_intensity_slider = QSlider(Qt.Horizontal)
        self.selection_intensity_slider.setRange(1, 30)
        self.selection_intensity_slider.setValue(10)
        self.selection_intensity_slider.valueChanged.connect(self.update_selection_display)
        strategy_layout.addRow("选择强度(%):", self.selection_intensity_slider)

        self.top_n_spin = QSpinBox()
        self.top_n_spin.setRange(1, 50)
        self.top_n_spin.setValue(10)
        self.top_n_spin.valueChanged.connect(self.update_selection_display)
        strategy_layout.addRow("选择个体数:", self.top_n_spin)

        strategy_group.setLayout(strategy_layout)
        layout.addWidget(strategy_group)

        # 优良个体列表
        selection_group = QGroupBox("优良个体选择结果")
        selection_layout = QVBoxLayout()

        self.selected_individuals_table = QTableWidget(0, 4)
        self.selected_individuals_table.setHorizontalHeaderLabels([
            "排名", "个体ID", "家系", "育种值"
        ])
        selection_layout.addWidget(self.selected_individuals_table)

        selection_group.setLayout(selection_layout)
        layout.addWidget(selection_group)

        # 操作按钮
        button_layout = QHBoxLayout()

        calculate_btn = QPushButton("计算遗传参数")
        calculate_btn.clicked.connect(self.calculate_genetic_parameters)
        button_layout.addWidget(calculate_btn)

        select_btn = QPushButton("筛选优良个体")
        select_btn.clicked.connect(self.select_elite_individuals)
        button_layout.addWidget(select_btn)

        export_btn = QPushButton("导出选择结果")
        export_btn.clicked.connect(self.export_selection_results)
        button_layout.addWidget(export_btn)

        layout.addLayout(button_layout)

        return widget

    def create_visualization_page(self):
        """创建可视化报告页面"""
        widget = QWidget()
        layout = QVBoxLayout(widget)

        title = QLabel("📋 可视化与报告")
        title.setFont(QFont("Arial", 16, QFont.Bold))
        layout.addWidget(title)

        # 可视化标签页
        viz_tabs = QTabWidget()

        # 地图视图
        map_tab = QWidget()
        map_layout = QVBoxLayout(map_tab)
        map_layout.addWidget(QLabel("🌍 优良个体空间位置可视化"))
        # map_layout.addWidget(QLabel("(此处将显示育种值空间分布图)"))
        viz_tabs.addTab(map_tab, "DEM展示")

        # 图表仪表板
        dashboard_tab = QWidget()
        dashboard_layout = QVBoxLayout(dashboard_tab)
        dashboard_layout.addWidget(QLabel("📊 优良个体育种值结果展示"))
        # dashboard_layout.addWidget(QLabel("(此处将集成所有分析图表)"))
        viz_tabs.addTab(dashboard_tab, "优良个体")

        layout.addWidget(viz_tabs)

        # 报告生成
        report_group = QGroupBox("报告生成")
        report_layout = QVBoxLayout()

        report_options_layout = QHBoxLayout()
        report_options_layout.addWidget(QLabel("报告格式:"))

        self.pdf_radio = QCheckBox("PDF")
        self.pdf_radio.setChecked(True)
        report_options_layout.addWidget(self.pdf_radio)

        self.html_radio = QCheckBox("HTML")
        report_options_layout.addWidget(self.html_radio)

        report_options_layout.addStretch()

        report_layout.addLayout(report_options_layout)

        generate_btn = QPushButton("生成分析报告")
        generate_btn.clicked.connect(self.generate_report)
        report_layout.addWidget(generate_btn)

        report_group.setLayout(report_layout)
        layout.addWidget(report_group)

        return widget

    # 以下是信号槽函数
    def change_page(self, index):
        """切换页面"""
        self.stacked_widget.setCurrentIndex(index)

    def browse_remote_data(self):
        """浏览遥感数据"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择图像数据", "",
            "图像文件 (*.tif *.tiff *.jpg *.png);;点云文件 (*.las *.laz *.ply)"
        )
        if file_path:
            self.remote_data_path.setText(file_path)

    def browse_field_data(self):
        """浏览田间设计数据"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择田间设计数据", "",
            "表格文件 (*.csv *.xlsx *.xls)"
        )
        if file_path:
            self.field_data_path.setText(file_path)

    def start_segmentation(self):
        """开始单木分割"""
        self.segmentation_progress.setValue(0)
        # 模拟进度更新
        for i in range(101):
            self.segmentation_progress.setValue(i)
            QApplication.processEvents()

    def extract_phenotypes(self):
        """提取表型 - 已更新为新的表型参数"""
        # 模拟表型数据
        self.phenotype_table.setRowCount(10)
        for i in range(10):
            self.phenotype_table.setItem(i, 0, QTableWidgetItem(f"TREE_{i + 1}"))
            self.phenotype_table.setItem(i, 1, QTableWidgetItem(f"{15 + i * 0.5:.1f}"))  # 树高
            self.phenotype_table.setItem(i, 2, QTableWidgetItem(f"{8 + i * 0.3:.1f}"))  # 冠幅
            self.phenotype_table.setItem(i, 3, QTableWidgetItem(f"{50 + i * 5:.1f}"))  # 树冠面积
            self.phenotype_table.setItem(i, 4, QTableWidgetItem(f"{120 + i * 10:.1f}"))  # 体积
            self.phenotype_table.setItem(i, 5, QTableWidgetItem(f"{0.85 + i * 0.01:.2f}"))  # 通直度
            self.phenotype_table.setItem(i, 6, QTableWidgetItem(f"FAM_{i // 2 + 1}"))  # 家系匹配

    def auto_match_families(self):
        """自动匹配家系"""
        QMessageBox.information(self, "信息", "家系自动匹配完成！")

    def export_phenotype_data(self):
        """导出表型数据"""
        file_path, _ = QFileDialog.getSaveFileName(
            self, "导出表型数据", "", "CSV文件 (*.csv)"
        )
        if file_path:
            QMessageBox.information(self, "成功", f"数据已导出到: {file_path}")

    def run_genetic_analysis(self):
        """运行遗传分析"""
        self.analysis_progress.setValue(0)
        self.analysis_log.clear()

        # 模拟分析过程
        steps = [
            "正在加载表型数据...",
            "正在构建混合线性模型...",
            "正在估计方差组分...",
            "正在计算遗传力...",
            "正在估计个体育种值...",
            "分析完成！"
        ]

        for i, step in enumerate(steps):
            self.analysis_log.append(step)
            self.analysis_progress.setValue(int((i + 1) * 100 / len(steps)))
            QApplication.processEvents()

        # 更新结果表格
        self.breeding_value_table.setRowCount(15)
        for i in range(15):
            self.breeding_value_table.setItem(i, 0, QTableWidgetItem(f"IND_{1000 + i}"))
            self.breeding_value_table.setItem(i, 1, QTableWidgetItem(f"FAM_{(i % 5) + 1}"))
            self.breeding_value_table.setItem(i, 2, QTableWidgetItem(f"{0.5 + i * 0.03:.3f}"))

        # 更新遗传力显示
        selected_trait = self.trait_combo.currentText()
        if selected_trait in self.genetic_analyzer.heritabilities:
            h2 = self.genetic_analyzer.heritabilities[selected_trait]
            self.heritability_value.setText(f"h² = {h2:.3f} ± 0.015")

            if h2 > 0.5:
                interpretation = "该性状受高强度遗传控制"
            elif h2 > 0.3:
                interpretation = "该性状受中等强度遗传控制"
            else:
                interpretation = "该性状受低强度遗传控制"
            self.heritability_interpretation.setText(interpretation)

    def calculate_genetic_parameters(self):
        """计算各性状的遗传参数"""
        try:
            # 计算各性状的遗传力
            self.genetic_analyzer.heritabilities = {}
            for trait in self.genetic_analyzer.traits:
                data = self.trait_data[trait]
                h2 = self.genetic_analyzer.calculate_heritability(data)
                self.genetic_analyzer.heritabilities[trait] = h2

            # 计算各性状的遗传增益（基于当前选择强度）
            selection_intensity = self.selection_intensity_slider.value() / 100.0
            self.genetic_analyzer.genetic_gains = {}
            for trait in self.genetic_analyzer.traits:
                h2 = self.genetic_analyzer.heritabilities[trait]
                gain = self.genetic_analyzer.calculate_genetic_gain(h2, selection_intensity)
                self.genetic_analyzer.genetic_gains[trait] = gain

            # 计算各性状的育种值
            self.genetic_analyzer.breeding_values = {}
            for trait in self.genetic_analyzer.traits:
                data = self.trait_data[trait]
                bvs = self.genetic_analyzer.calculate_breeding_values(data, self.individual_ids)
                self.genetic_analyzer.breeding_values[trait] = bvs

            # 更新性状比较表格
            self.update_trait_comparison_table()

            QMessageBox.information(self, "成功", "遗传参数计算完成！")

        except Exception as e:
            QMessageBox.critical(self, "错误", f"计算遗传参数时出错: {str(e)}")

    def update_trait_comparison_table(self):
        """更新性状比较表格"""
        self.trait_comparison_table.setRowCount(len(self.genetic_analyzer.traits))

        for i, trait in enumerate(self.genetic_analyzer.traits):
            h2 = self.genetic_analyzer.heritabilities.get(trait, 0)
            gain = self.genetic_analyzer.genetic_gains.get(trait, 0)
            score = 0.6 * h2 + 0.4 * (gain / 100)  # 综合得分

            self.trait_comparison_table.setItem(i, 0, QTableWidgetItem(trait))
            self.trait_comparison_table.setItem(i, 1, QTableWidgetItem(f"{h2:.3f}"))
            self.trait_comparison_table.setItem(i, 2, QTableWidgetItem(f"{gain:.2f}%"))
            self.trait_comparison_table.setItem(i, 3, QTableWidgetItem(f"{score:.3f}"))

    def select_elite_individuals(self):
        """筛选优良个体"""
        if not self.genetic_analyzer.heritabilities:
            QMessageBox.warning(self, "警告", "请先计算遗传参数！")
            return

        try:
            # 选择最优性状
            optimal_trait = self.genetic_analyzer.select_optimal_trait(
                self.genetic_analyzer.heritabilities,
                self.genetic_analyzer.genetic_gains
            )

            # 更新最优性状显示
            h2 = self.genetic_analyzer.heritabilities[optimal_trait]
            gain = self.genetic_analyzer.genetic_gains[optimal_trait]
            self.optimal_trait_label.setText(
                f"最优选择性状: {optimal_trait} (遗传力: {h2:.3f}, 遗传增益: {gain:.2f}%)"
            )

            # 基于最优性状的育种值选择Top N个体
            top_n = self.top_n_spin.value()
            breeding_values = self.genetic_analyzer.breeding_values[optimal_trait]
            top_individuals = self.genetic_analyzer.select_top_individuals(breeding_values, top_n)

            # 更新优良个体表格
            self.update_selected_individuals_table(top_individuals, optimal_trait)

            QMessageBox.information(self, "成功",
                                    f"基于性状'{optimal_trait}'筛选出{top_n}个优良个体！")

        except Exception as e:
            QMessageBox.critical(self, "错误", f"筛选优良个体时出错: {str(e)}")

    def update_selected_individuals_table(self, top_individuals, trait):
        """更新选中个体表格"""
        self.selected_individuals_table.setRowCount(len(top_individuals))

        for i, (ind_id, breeding_value) in enumerate(top_individuals):
            # 查找个体对应的家系
            family_index = self.individual_ids.index(ind_id)
            family_id = self.family_ids[family_index]

            self.selected_individuals_table.setItem(i, 0, QTableWidgetItem(str(i + 1)))
            self.selected_individuals_table.setItem(i, 1, QTableWidgetItem(ind_id))
            self.selected_individuals_table.setItem(i, 2, QTableWidgetItem(family_id))
            self.selected_individuals_table.setItem(i, 3, QTableWidgetItem(f"{breeding_value:.3f}"))

    def update_selection_display(self):
        """更新选择强度显示"""
        intensity = self.selection_intensity_slider.value()
        # 如果已经计算过遗传参数，重新计算遗传增益
        if hasattr(self.genetic_analyzer, 'heritabilities') and self.genetic_analyzer.heritabilities:
            selection_intensity = intensity / 100.0
            for trait in self.genetic_analyzer.traits:
                h2 = self.genetic_analyzer.heritabilities[trait]
                gain = self.genetic_analyzer.calculate_genetic_gain(h2, selection_intensity)
                self.genetic_analyzer.genetic_gains[trait] = gain

            self.update_trait_comparison_table()

    def export_selection_results(self):
        """导出选择结果"""
        if self.selected_individuals_table.rowCount() == 0:
            QMessageBox.warning(self, "警告", "没有可导出的选择结果！")
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self, "导出选择结果", "", "CSV文件 (*.csv)"
        )
        if file_path:
            QMessageBox.information(self, "成功", f"选择结果已导出到: {file_path}")

    def generate_report(self):
        """生成报告"""
        format_type = "PDF" if self.pdf_radio.isChecked() else "HTML"
        QMessageBox.information(self, "成功", f"{format_type}报告生成完成！")


def main():
    app = QApplication(sys.argv)

    # 设置应用程序图标和属性
    app.setApplicationName("DeepForest Breeder")
    app.setApplicationVersion("1.0.0")

    window = MainWindow()
    window.show()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()