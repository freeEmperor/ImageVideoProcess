"""界面配色与全局样式表。

只在这里定义颜色 / 圆角 / 间距，其它模块通过 ``objectName`` 引用样式，
避免颜色散落在各个面板里。

⚠️ **亮色主题必须在两处同时钉死**（只做一半就会出现"弹窗是暗的、字是黑的"）：

1. :data:`STYLESHEET` —— 管住了我们自己写了样式的控件；
2. :func:`light_palette` —— 管住**没有**写样式的控件（QMessageBox、下拉框弹出层、
   QToolTip、滚动区域……）。

Windows 开了"深色模式"时，Qt 6 会把系统暗色调色板交给 Fusion 样式；
只设样式表的话，那些没被样式表覆盖的控件会跟着系统变暗，
和我们亮色的界面撞在一起。**所以 ``app.setPalette(light_palette())`` 不能省。**
"""

from __future__ import annotations

from PySide6.QtGui import QColor, QPalette

#: 主色（按钮、选中项）
ACCENT = "#2f6fed"
ACCENT_HOVER = "#1f5fd8"
ACCENT_PRESSED = "#1848a8"

#: 页面背景与卡片
BACKGROUND = "#f3f5f9"
CARD_BACKGROUND = "#ffffff"
BORDER = "#dfe4ec"
SIDEBAR_BACKGROUND = "#ffffff"

#: 文字
TEXT_PRIMARY = "#1d2430"
TEXT_SECONDARY = "#6b7685"
TEXT_MUTED = "#98a1b0"

#: 语义色
SUCCESS = "#1a9e5c"
DANGER = "#d64545"
WARNING = "#c77700"


def light_palette() -> QPalette:
    """构造一套固定亮色的调色板（不跟随 Windows 深色模式）。"""
    palette = QPalette()
    role = QPalette.ColorRole
    group = QPalette.ColorGroup

    palette.setColor(role.Window, QColor(CARD_BACKGROUND))
    palette.setColor(role.WindowText, QColor(TEXT_PRIMARY))
    palette.setColor(role.Base, QColor(CARD_BACKGROUND))
    palette.setColor(role.AlternateBase, QColor("#f5f7fa"))
    palette.setColor(role.Text, QColor(TEXT_PRIMARY))
    palette.setColor(role.Button, QColor("#f7f9fc"))
    palette.setColor(role.ButtonText, QColor(TEXT_PRIMARY))
    palette.setColor(role.BrightText, QColor(DANGER))
    palette.setColor(role.Link, QColor(ACCENT))
    palette.setColor(role.Highlight, QColor(ACCENT))
    palette.setColor(role.HighlightedText, QColor("#ffffff"))
    palette.setColor(role.ToolTipBase, QColor(CARD_BACKGROUND))
    palette.setColor(role.ToolTipText, QColor(TEXT_PRIMARY))
    palette.setColor(role.PlaceholderText, QColor(TEXT_MUTED))

    # 禁用态：统一成浅灰，避免又变成系统暗色
    for disabled_role in (role.WindowText, role.Text, role.ButtonText):
        palette.setColor(group.Disabled, disabled_role, QColor(TEXT_MUTED))

    return palette


#: 全局样式表
STYLESHEET = f"""
QWidget {{
    font-family: "Microsoft YaHei UI", "Segoe UI", "Microsoft YaHei", sans-serif;
    font-size: 13px;
    color: {TEXT_PRIMARY};
}}

QMainWindow, QWidget#page {{
    background: {BACKGROUND};
}}

/* ---------------- 左侧功能列表 ---------------- */
QFrame#sidebarPanel {{
    background: {SIDEBAR_BACKGROUND};
    border-right: 1px solid {BORDER};
}}
QListWidget#sidebar {{
    background: {SIDEBAR_BACKGROUND};
    border: none;
    outline: none;
    padding: 8px 6px;
}}
QListWidget#sidebar::item {{
    border-radius: 8px;
    margin: 3px 2px;
    color: {TEXT_PRIMARY};
}}
QListWidget#sidebar::item:hover {{
    background: #eef2fb;
}}
QListWidget#sidebar::item:selected {{
    background: #e4edff;
}}
QListWidget#sidebar::item:disabled {{
    color: {TEXT_MUTED};
}}

QLabel#sidebarTitle {{
    font-size: 13px;
    font-weight: 600;
    color: {TEXT_PRIMARY};
    background: transparent;
}}
QLabel#sidebarSubtitle {{
    font-size: 11px;
    color: {TEXT_SECONDARY};
    background: transparent;
}}
QLabel#appTitle {{
    font-size: 15px;
    font-weight: 700;
    color: {TEXT_PRIMARY};
    padding: 12px 10px 6px 12px;
}}
QLabel#appSubtitle {{
    font-size: 11px;
    color: {TEXT_MUTED};
    padding: 0 10px 10px 12px;
}}

/* ---------------- 卡片 / 标题 ---------------- */
QFrame#card {{
    background: {CARD_BACKGROUND};
    border: 1px solid {BORDER};
    border-radius: 10px;
}}
QLabel#panelTitle {{
    font-size: 17px;
    font-weight: 700;
}}
QLabel#panelDescription {{
    font-size: 12px;
    color: {TEXT_SECONDARY};
}}
QLabel#hint {{
    font-size: 12px;
    color: {TEXT_SECONDARY};
}}
QLabel#hintWarn {{
    font-size: 12px;
    color: {WARNING};
}}
QLabel#fieldLabel {{
    font-size: 13px;
    color: {TEXT_PRIMARY};
}}
QLabel#ratio {{
    font-size: 13px;
    font-weight: 600;
    color: {ACCENT};
}}
QLabel#infoKey {{
    color: {TEXT_SECONDARY};
    font-size: 12px;
}}
QLabel#infoValue {{
    color: {TEXT_PRIMARY};
    font-size: 12px;
    font-weight: 600;
}}
QLabel#sectionTitle {{
    font-size: 13px;
    font-weight: 600;
    color: {TEXT_PRIMARY};
}}

/* ---------------- 拖拽区 ---------------- */
QFrame#dropZone {{
    background: #fbfcfe;
    border: 2px dashed #c3cede;
    border-radius: 10px;
}}
QFrame#dropZone[dragActive="true"] {{
    background: #eaf1ff;
    border: 2px dashed {ACCENT};
}}
QFrame#dropZone[loaded="true"] {{
    background: #f7fbf8;
    border: 1px solid #bfe3cd;
}}
QLabel#dropTitle {{
    font-size: 14px;
    font-weight: 600;
    color: {TEXT_PRIMARY};
    background: transparent;
}}
QLabel#dropHint {{
    font-size: 12px;
    color: {TEXT_SECONDARY};
    background: transparent;
}}

/* ---------------- 输入控件 ---------------- */
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
    background: {CARD_BACKGROUND};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 5px 8px;
    min-height: 20px;
    selection-background-color: {ACCENT};
    selection-color: #ffffff;
}}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{
    border: 1px solid {ACCENT};
}}
QSpinBox:disabled, QDoubleSpinBox:disabled, QComboBox:disabled {{
    background: #f1f3f7;
    color: {TEXT_MUTED};
}}
/* 需求：数值输入框不要增减按钮（控件里也用 setButtonSymbols(NoButtons) 关掉） */
QSpinBox::up-button, QSpinBox::down-button,
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{
    width: 0px;
    height: 0px;
    border: none;
    background: transparent;
}}
QSpinBox::up-arrow, QSpinBox::down-arrow,
QDoubleSpinBox::up-arrow, QDoubleSpinBox::down-arrow {{
    width: 0px;
    height: 0px;
    image: none;
}}
QComboBox::drop-down {{
    subcontrol-origin: padding;
    subcontrol-position: center right;
    width: 22px;
    border: none;
    background: transparent;
}}
/* 箭头由 gui/style.py 的 ChevronStyle 画（QSS 画不出折线箭头），
   所以这里不要写 QComboBox::down-arrow，否则会把绘制整个吃掉 */
/* 下拉弹出层：样式表管外观，调色板（light_palette）管边框，
   两者都要有，否则深色模式下会出现「亮底 + 暗边框」 */
QComboBox QAbstractItemView {{
    background: {CARD_BACKGROUND};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 4px;
    outline: none;
    selection-background-color: #e4edff;
    selection-color: {TEXT_PRIMARY};
}}
QComboBox QAbstractItemView::item {{
    min-height: 22px;
    padding: 2px 6px;
}}
QCheckBox {{
    font-size: 13px;
}}

/* ---------------- 对话框（QMessageBox 等：样式表 + light_palette 双保险）------- */
QMessageBox, QDialog {{
    background: {CARD_BACKGROUND};
}}
QMessageBox QLabel, QDialog QLabel {{
    color: {TEXT_PRIMARY};
    background: transparent;
}}
QMessageBox QPushButton, QDialog QPushButton {{
    min-width: 84px;
    padding: 6px 16px;
}}

/* ---------------- 按钮 ---------------- */
QPushButton {{
    background: {CARD_BACKGROUND};
    border: 1px solid {BORDER};
    border-radius: 7px;
    padding: 6px 14px;
    color: {TEXT_PRIMARY};
}}
QPushButton:hover {{
    background: #f2f5fb;
}}
QPushButton:pressed {{
    background: #e6ebf5;
}}
QPushButton:disabled {{
    background: #f1f3f7;
    color: {TEXT_MUTED};
    border-color: #e6e9ef;
}}
QPushButton#primary {{
    background: {ACCENT};
    border: 1px solid {ACCENT};
    color: #ffffff;
    font-weight: 600;
    padding: 8px 24px;
}}
QPushButton#primary:hover {{
    background: {ACCENT_HOVER};
    border-color: {ACCENT_HOVER};
}}
QPushButton#primary:pressed {{
    background: {ACCENT_PRESSED};
    border-color: {ACCENT_PRESSED};
}}
QPushButton#primary:disabled {{
    background: #c3cede;
    border-color: #c3cede;
    color: #f2f4f8;
}}
QPushButton#danger {{
    background: {DANGER};
    border: 1px solid {DANGER};
    color: #ffffff;
    font-weight: 600;
    padding: 8px 24px;
}}

/* ---------------- 进度条 ---------------- */
QProgressBar {{
    background: #eef1f6;
    border: none;
    border-radius: 6px;
    height: 12px;
    text-align: center;
    font-size: 11px;
    color: {TEXT_SECONDARY};
}}
QProgressBar::chunk {{
    background: {ACCENT};
    border-radius: 6px;
}}

/* ---------------- 提示条（自动消散） ---------------- */
QFrame#toast {{
    border-radius: 8px;
    border: 1px solid {BORDER};
    background: {CARD_BACKGROUND};
}}
QFrame#toast[level="success"] {{
    background: #eaf8f0;
    border: 1px solid #b7e3ca;
}}
QFrame#toast[level="error"] {{
    background: #fdeeee;
    border: 1px solid #f2c2c2;
}}
QFrame#toast[level="info"] {{
    background: #eef3ff;
    border: 1px solid #ccd9f7;
}}
QLabel#toastText {{
    font-size: 13px;
    font-weight: 600;
    background: transparent;
}}
QFrame#toast[level="success"] QLabel#toastText {{ color: #146c40; }}
QFrame#toast[level="error"] QLabel#toastText {{ color: #a52a2a; }}
QFrame#toast[level="info"] QLabel#toastText {{ color: #234b9c; }}

/* ---------------- 滚动条 ---------------- */
QScrollArea {{ border: none; background: transparent; }}
QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 2px;
}}
QScrollBar::handle:vertical {{
    background: #c9d1de;
    border-radius: 5px;
    min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{ background: #aeb9ca; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: none; }}

/* ---------------- 状态栏 ---------------- */
QStatusBar {{
    background: {SIDEBAR_BACKGROUND};
    border-top: 1px solid {BORDER};
    color: {TEXT_SECONDARY};
}}
QStatusBar::item {{ border: none; }}
"""
