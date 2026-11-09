"""GUI 层测试：功能注册表、面板校验联动、侧栏切换确认。

Qt 用 offscreen 平台跑，不需要真实显示器。
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication  # noqa: E402

from imagevideoprocess.core.paths import PROCESSED_DIRNAME  # noqa: E402
from imagevideoprocess.gui import features as feature_registry  # noqa: E402
from imagevideoprocess.gui.main_window import MainWindow  # noqa: E402
from imagevideoprocess.gui.panels.compress import (
    _DEFAULT_VALUE as DEFAULT_COMPRESS_VALUE,  # noqa: E402
)
from media_factory import make_image, make_video  # noqa: E402


@pytest.fixture(scope="session")
def qapp():
    """整个测试会话共用一个 QApplication。"""
    app = QApplication.instance() or QApplication([])
    yield app


# ------------------------------------------------------------------ 注册表
def test_registry_has_all_features() -> None:
    """需求里的功能必须都在注册表里（以后加功能只需在此追加）。"""
    keys = [feature.key for feature in feature_registry.all_features()]
    assert {"compress", "resize", "frames", "convert", "audio", "superres"} <= set(keys)
    assert len(keys) == len(set(keys)), "功能 key 不能重复"
    # 顺序按 order 升序排列，侧栏显示顺序即此顺序
    orders = [feature.order for feature in feature_registry.all_features()]
    assert orders == sorted(orders)


def test_registry_metadata() -> None:
    """每个功能都要有标题、说明、图标和可构造的面板类。"""
    for feature in feature_registry.all_features():
        assert feature.title
        assert feature.subtitle
        assert feature.description
        assert feature.icon
        assert callable(feature.panel_factory)
        assert feature.file_filter


@pytest.mark.parametrize("key", ["frames", "audio"])
def test_video_only_features(key: str) -> None:
    """抽帧与音频提取都只接受视频。"""
    feature = feature_registry.find_feature(key)
    assert feature is not None
    assert feature.accepts_video
    assert not feature.accepts_image


def test_superres_accepts_image_only() -> None:
    """超分只接受图片。"""
    feature = feature_registry.find_feature("superres")
    assert feature is not None
    assert feature.accepts_image
    assert not feature.accepts_video


def test_duplicate_key_rejected() -> None:
    """同一个 key 不能注册两次（防止将来加功能时冲突）。"""
    with pytest.raises(ValueError):

        @feature_registry.register_feature(key="compress", title="重复", subtitle="重复")
        class _Duplicate:
            pass


# -------------------------------------------------------------------- 面板
def test_panels_build_without_error(qapp) -> None:
    """注册表里的每个面板都能构造出来，且刚建好时不算「已修改」。"""
    for feature in feature_registry.all_features():
        panel = feature.panel_factory(feature)
        assert panel is not None
        # 没有文件时按钮必须是灰的
        assert not panel.action_button.isEnabled()
        # 初始化控件触发的信号不能被当成「用户修改」，否则一切换功能就弹框
        assert not panel.is_dirty(), f"{feature.key} 刚打开就被标成了已修改"


def test_compress_panel_validation(qapp, tmp_dir) -> None:
    """压缩面板：比例提示与按钮可用性。"""
    feature = feature_registry.find_feature("compress")
    assert feature is not None
    panel = feature.panel_factory(feature)

    image = make_image(tmp_dir / "photo.jpg", size=(800, 600))
    size = image.stat().st_size
    panel.set_source(image)

    # 载入后自动给一个合理默认值（原体积的一半左右）
    assert 0 < panel.value_input.value() <= 1024
    assert panel.validation_error() is None
    assert panel.action_button.isEnabled()
    assert panel.ratio_label.text().startswith("（压缩至 ")
    assert panel.ratio_label.text().endswith("%）")

    # 目标大于原文件 → 不可点，并给出原因
    panel.unit_input.setCurrentIndex(0)  # KB
    panel.value_input.setValue(min(1024.0, size / 1024 * 2))
    error = panel.validation_error()
    assert error is not None and "小于原文件" in error
    assert not panel.action_button.isEnabled()

    # 数值为 0 → 不可点
    panel.value_input.setValue(0.0)
    assert panel.validation_error() is not None


def test_compress_panel_rejects_wrong_kind(qapp, tmp_dir) -> None:
    """压缩面板两种文件都收，抽帧面板拒收图片。"""
    video = make_video(tmp_dir / "clip.mp4", seconds=0.5, fps=10, size=(160, 90))
    frames_feature = feature_registry.find_feature("frames")
    assert frames_feature is not None
    panel = frames_feature.panel_factory(frames_feature)
    image = make_image(tmp_dir / "photo.jpg", size=(64, 64))

    panel.set_source(image)
    assert panel.source is None, "图片不应被抽帧面板接受"

    panel.set_source(video)
    assert panel.source == video
    assert panel.action_button.isEnabled()


def test_resize_panel_validation(qapp, tmp_dir) -> None:
    """缩放面板：宽高必须都小于原分辨率。"""
    feature = feature_registry.find_feature("resize")
    assert feature is not None
    panel = feature.panel_factory(feature)
    image = make_image(tmp_dir / "photo.jpg", size=(800, 600))
    panel.set_source(image)

    # 默认填了原尺寸的一半
    assert panel.target_size == (400, 300)
    assert panel.validation_error() is None

    panel.width_input.setValue(900)
    assert panel.validation_error() is not None
    panel.width_input.setValue(400)
    panel.height_input.setValue(600)
    assert panel.validation_error() is not None


def test_frames_panel_validation(qapp, tmp_dir) -> None:
    """抽帧面板：区间必须在视频范围内。"""
    feature = feature_registry.find_feature("frames")
    assert feature is not None
    panel = feature.panel_factory(feature)
    video = make_video(tmp_dir / "clip.mp4", seconds=1.0, fps=30, size=(160, 90))
    panel.set_source(video)

    # 默认 0 帧起取 1 帧
    assert panel.start_input.value() == 0.0
    assert panel.span_input.value() == 1.0
    assert panel.validation_error() is None
    assert panel.action_button.isEnabled()

    # 把跨度固定成 10 帧，专门测越界判断
    panel.span_input.setValue(10.0)
    panel.start_input.setValue(21.0)  # 21 ~ 30 帧，超出 30 帧
    assert panel.validation_error() is not None
    panel.start_input.setValue(20.0)  # 20 ~ 29 帧，正好到末尾
    assert panel.validation_error() is None


# -------------------------------------------------------- 格式转换 / 音频提取
def test_convert_panel_excludes_source_format(qapp, tmp_dir) -> None:
    """格式转换面板：载入文件后，目标格式列表不含原格式，且按钮可点。"""
    feature = feature_registry.find_feature("convert")
    assert feature is not None
    panel = feature.panel_factory(feature)

    image = make_image(tmp_dir / "photo.jpg", size=(120, 90))
    panel.set_source(image)
    keys = [panel.format_input.itemData(i) for i in range(panel.format_input.count())]
    assert keys, "应当有可选格式"
    assert "jpg" not in keys, "不能把原格式列出来"
    assert panel.validation_error() is None
    assert panel.action_button.isEnabled()
    assert panel.hint_label.text(), "应当给出转换方式说明"

    # 换成 PNG 文件，列表里就应该没有 png 而有 jpg
    png = make_image(tmp_dir / "logo.png", size=(120, 90))
    panel.set_source(png)
    keys = [panel.format_input.itemData(i) for i in range(panel.format_input.count())]
    assert "png" not in keys
    assert "jpg" in keys


def test_convert_panel_accepts_video(qapp, tmp_dir) -> None:
    """格式转换也吃视频，并且视频的目标列表是正确的容器。"""
    feature = feature_registry.find_feature("convert")
    assert feature is not None
    panel = feature.panel_factory(feature)
    video = make_video(tmp_dir / "clip.mp4", seconds=0.5, fps=10, size=(160, 90))
    panel.set_source(video)

    keys = [panel.format_input.itemData(i) for i in range(panel.format_input.count())]
    assert "mkv" in keys and "webm" in keys
    assert "mp4" not in keys
    assert panel.action_button.isEnabled()


def test_audio_panel_validation(qapp, tmp_dir) -> None:
    """音频提取面板：只收视频，且视频必须真有音轨。"""
    feature = feature_registry.find_feature("audio")
    assert feature is not None
    panel = feature.panel_factory(feature)

    keys = [panel.format_input.itemData(i) for i in range(panel.format_input.count())]
    assert "mp3" in keys
    assert "图片" not in panel.drop_zone.title_text

    # 有音轨的视频 → 可点
    video = make_video(tmp_dir / "clip.mp4", seconds=0.5, fps=10, size=(160, 90))
    panel.set_source(video)
    assert panel.validation_error() is None
    assert panel.action_button.isEnabled()
    assert "源音轨" in panel.source_label.text()

    # 没音轨的视频 → 不可点
    silent = make_video(
        tmp_dir / "silent.mp4", seconds=0.5, fps=10, size=(160, 90), with_audio=False
    )
    panel.set_source(silent)
    assert panel.validation_error() is not None
    assert not panel.action_button.isEnabled()

    # 图片 → 直接拒收（面板保持原来的文件不变）
    image = make_image(tmp_dir / "photo.jpg", size=(64, 64))
    panel.set_source(image)
    assert panel.source == silent, "图片不该被音频提取面板接受"


def test_superres_panel_defaults_and_validation(qapp, tmp_dir) -> None:
    """超分面板：默认方法 / 倍率、下拉框带方法特点、载入图片后按钮可点。"""
    from imagevideoprocess.core import superres

    feature = feature_registry.find_feature("superres")
    assert feature is not None
    panel = feature.panel_factory(feature)

    # 只接受图片
    assert "图片" in panel.drop_zone.title_text
    assert "视频" not in panel.drop_zone.title_text

    # 方法下拉框里每一项都要带上特点说明（需求要求）
    labels = [panel.method_input.itemText(i) for i in range(panel.method_input.count())]
    assert labels, "应当有可选方法"
    assert all("—" in text and len(text) > 8 for text in labels), labels
    assert panel.method_key == superres.DEFAULT_METHOD
    assert panel.scale == superres.DEFAULT_SCALE

    # 没文件时按钮不可点
    assert panel.validation_error() is not None

    image = make_image(tmp_dir / "photo.jpg", size=(200, 150))
    panel.set_source(image)
    assert panel.validation_error() is None
    assert panel.action_button.isEnabled()

    # 提示里要写明目标分辨率与输出文件名
    assert "400×300" in panel.hint_label.text()
    assert "photo_lanczos_2x.jpg" in panel.hint_label.text()

    # 换倍率 → 说明跟着变
    panel.scale_input.setCurrentIndex(panel.scale_input.findData(4))
    assert panel.scale == 4
    assert "800×600" in panel.hint_label.text()
    assert "photo_lanczos_4x.jpg" in panel.hint_label.text()

    # 换方法 → 说明跟着变
    panel.method_input.setCurrentIndex(panel.method_input.findData("nearest"))
    assert "photo_nearest_4x.jpg" in panel.hint_label.text()

    # 重置回默认
    panel.reset_parameters()
    assert panel.method_key == superres.DEFAULT_METHOD
    assert panel.scale == superres.DEFAULT_SCALE


def test_file_card_path_spans_full_row(qapp, tmp_dir) -> None:
    """信息卡片：路径排第一，且横跨整排。"""
    from imagevideoprocess.core import media_info
    from imagevideoprocess.gui.widgets.filecard import FileInfoCard

    video = make_video(tmp_dir / "clip.mp4", seconds=0.5, fps=10, size=(160, 90))
    info = media_info.probe(video)
    card = FileInfoCard()
    card.set_info(info)
    assert card.isVisible() or card.isVisibleTo(card.parentWidget() or card)

    grid = card._grid
    positions: list[tuple[str, int, int, int, int]] = []
    for index in range(grid.count()):
        item = grid.itemAt(index)
        widget = item.widget() if item is not None else None
        if widget is None:
            continue
        row, column, row_span, column_span = grid.getItemPosition(index)
        positions.append((widget.toolTip() or widget.text(), row, column, row_span, column_span))

    path_entries = [entry for entry in positions if entry[0] == str(video)]
    assert path_entries, "信息卡片里应当有完整路径"
    _text, row, _column, _row_span, column_span = path_entries[0]
    assert row == 0, "路径必须在第一排"
    assert column_span > 1, "路径必须横跨整排"

    # 属性名在路径行的最左边
    key_entries = [entry for entry in positions if entry[0] == "路径"]
    assert key_entries and key_entries[0][1] == 0 and key_entries[0][2] == 0


# ------------------------------------------------------------------ 主窗口
def test_main_window_sidebar(qapp) -> None:
    """左侧列表条数与功能数一致，启动时不显示任何工作台。"""
    window = MainWindow()
    assert window._sidebar.count() == len(feature_registry.all_features())
    assert window._current_key is None, "启动时不该已经进入某个工作台"
    window.close()


def test_switch_without_changes_needs_no_confirmation(qapp) -> None:
    """没动过的工作台（没拖文件、没改参数）切换时不弹确认框。

    三个功能都要覆盖：抽帧面板在 build_parameters 里会初始化单位下拉框，
    很容易被误标成「已修改」。
    """
    window = MainWindow()
    for feature in window._features:
        window._activate(feature)
        assert window._current_key == feature.key
        assert not window._panels[feature.key].is_dirty(), f"{feature.key} 未做修改却要求确认"
        assert not window._current_panel_dirty()

    window._activate(window._features[0])
    window._confirm_switch = lambda current, target: pytest.fail("未修改时不该弹确认框")
    window._on_row_activated(1)
    assert window._current_key == "resize"
    assert window._sidebar.currentRow() == 1

    # 切回来也不该弹框（切走时已把上一个工作台清空）
    window._on_row_activated(0)
    assert window._current_key == "compress"
    window.close()


def test_switch_after_loading_file_requires_confirmation(qapp, tmp_dir) -> None:
    """拖入过文件 → 属于「已修改」，切换要弹确认框：取消保持不变，确定才切换。"""
    window = MainWindow()
    window._activate(window._features[0])
    panel = window._panels["compress"]
    image = make_image(tmp_dir / "photo.jpg", size=(400, 300))
    panel.set_source(image)
    assert window._panels["compress"].is_dirty(), "拖入文件后应视为已修改"

    window._confirm_switch = lambda current, target: False  # 模拟点「取消」
    window._on_row_activated(1)
    assert window._current_key == "compress", "取消后不该切换功能"
    assert window._sidebar.currentRow() == 0, "取消后左侧选中项应退回"

    window._confirm_switch = lambda current, target: True  # 模拟点「确定」
    window._on_row_activated(1)
    assert window._current_key == "resize"
    assert window._sidebar.currentRow() == 1
    # 切走后，上一个工作台被清空
    assert not window._panels["compress"].is_dirty()
    assert window._panels["compress"].source is None

    # 点击当前功能不弹框、不报错
    window._confirm_switch = lambda current, target: pytest.fail("不该弹确认框")
    window._on_row_activated(1)
    window.close()


def test_switch_after_editing_parameter_requires_confirmation(qapp) -> None:
    """只改参数（没拖文件）也算「已修改」。"""
    window = MainWindow()
    window._activate(window._features[0])
    panel = window._panels["compress"]
    assert not panel.is_dirty()

    panel.value_input.setValue(panel.value_input.value() + 10)  # 用户改了输入
    assert panel.is_dirty(), "改过参数后应视为已修改"

    calls: list[tuple[str, str]] = []
    window._confirm_switch = lambda current, target: (
        calls.append((current.key, target.key)),
        True,
    )[1]
    window._on_row_activated(1)
    assert calls == [("compress", "resize")]
    assert window._current_key == "resize"
    window.close()


def test_reset_clears_panel_state(qapp, tmp_dir) -> None:
    """重置：文件、参数、脏标记都要回到初始状态。"""
    window = MainWindow()
    window._activate(window._features[0])
    panel = window._panels["compress"]
    panel.set_source(make_image(tmp_dir / "photo.jpg", size=(320, 240)))
    panel.value_input.setValue(123.0)

    panel.reset()
    assert panel.source is None
    assert panel.info is None
    assert not panel.is_dirty()
    assert panel.value_input.value() == DEFAULT_COMPRESS_VALUE
    assert panel.ratio_label.text() == "（压缩至 --%）"


def test_drop_zone_text_matches_accepted_kinds(qapp) -> None:
    """拖拽区文案随功能接受的类型变化：抽帧只写「视频」。"""
    frames_feature = feature_registry.find_feature("frames")
    compress_feature = feature_registry.find_feature("compress")
    assert frames_feature is not None and compress_feature is not None

    frames_panel = frames_feature.panel_factory(frames_feature)
    compress_panel = compress_feature.panel_factory(compress_feature)

    assert frames_panel.drop_zone.title_text == "把视频拖拽到这里"
    assert "图片" not in frames_panel.drop_zone.title_text
    assert compress_panel.drop_zone.title_text == "把图片 / 视频拖拽到这里"


def test_spin_boxes_have_no_buttons(qapp) -> None:
    """需求：数值输入框里不要增减按钮。"""
    from PySide6.QtWidgets import QAbstractSpinBox

    for key in ("compress", "resize", "frames"):
        feature = feature_registry.find_feature(key)
        assert feature is not None
        panel = feature.panel_factory(feature)
        for box in panel.findChildren(QAbstractSpinBox):
            assert box.buttonSymbols() == QAbstractSpinBox.ButtonSymbols.NoButtons, key


def test_light_palette_is_light() -> None:
    """必须钉死亮色调色板，否则 Windows 深色模式下弹窗会变暗、字看不清。"""
    from PySide6.QtGui import QPalette

    from imagevideoprocess.gui.theme import light_palette

    palette = light_palette()
    window_color = palette.color(QPalette.ColorRole.Window)
    text_color = palette.color(QPalette.ColorRole.WindowText)
    # 背景亮、文字暗，且对比度足够
    assert window_color.lightness() > 200, "对话框底色应为亮色"
    assert text_color.lightness() < 100, "对话框文字应为深色"
    assert light_palette().color(QPalette.ColorRole.Highlight).name() == "#2f6fed"


def test_processed_dir_is_next_to_app() -> None:
    """输出目录固定为「应用目录/processed」。"""
    from imagevideoprocess.core.paths import app_dir, processed_dir

    assert processed_dir(create=False).name == PROCESSED_DIRNAME
    assert processed_dir(create=False).parent == app_dir()
