from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QObject, Qt, QThread, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from .indexer import save_index, scan_tools
from .models import APP_NAME, INDEX_FILE_NAME, AppConfig, ToolIndex, ToolInfo
from .services import ConfigStore, GitHubClient, StateStore, ToolLibrary, app_data_dir
from .styles import APP_QSS


class Worker(QObject):
    finished = Signal(object)
    failed = Signal(str)
    progress = Signal(str, int)

    def __init__(self, fn: Callable) -> None:
        super().__init__()
        self.fn = fn

    def run(self) -> None:
        try:
            self.finished.emit(self.fn(self.progress.emit))
        except Exception as exc:
            self.failed.emit(str(exc))


class ToolCard(QFrame):
    selected = Signal(object)
    action_requested = Signal(str, object)

    def __init__(self, tool: ToolInfo, status: str, local_version: str, is_selected: bool = False) -> None:
        super().__init__()
        self.tool = tool
        self.status = status
        self.setObjectName("ToolCard")
        self.setProperty("selected", "true" if is_selected else "false")
        self.setMinimumHeight(178)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 15, 16, 14)
        layout.setSpacing(11)

        header = QHBoxLayout()
        header.setSpacing(12)
        icon = QLabel(tool_initial(tool.name))
        icon.setObjectName("ToolIcon")
        icon.setFixedSize(50, 50)
        icon.setAlignment(Qt.AlignCenter)
        icon.setStyleSheet(f"background:{tool_color(tool.category)};")
        header.addWidget(icon)

        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        name = QLabel(tool.name)
        name.setObjectName("ToolName")
        category = QLabel(tool.category)
        category.setObjectName("Category")
        title_box.addWidget(name)
        title_box.addWidget(category)
        header.addLayout(title_box, 1)
        header.addWidget(status_label(status), 0, Qt.AlignTop)
        layout.addLayout(header)

        desc = QLabel(tool.description or "尚未填寫工具用途描述。")
        desc.setObjectName("CardDescription")
        desc.setWordWrap(True)
        desc.setMaximumHeight(42)
        layout.addWidget(desc)

        meta = QLabel(f"本機 {local_version or '-'}    雲端 {tool.version}    更新 {tool.updated_at or '-'}")
        meta.setObjectName("Meta")
        layout.addWidget(meta)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        primary_text = primary_action_text(status)
        primary = QPushButton(primary_text)
        primary.setObjectName("PrimaryButton")
        primary.clicked.connect(lambda: self.action_requested.emit(primary_text, self.tool))
        actions.addWidget(primary)

        folder = QPushButton("資料夾")
        folder.setObjectName("SecondaryButton")
        folder.clicked.connect(lambda: self.action_requested.emit("資料夾", self.tool))
        actions.addWidget(folder)

        more = QPushButton("...")
        more.setObjectName("GhostButton")
        more.setFixedWidth(42)
        more.clicked.connect(lambda: self.action_requested.emit("詳情", self.tool))
        actions.addWidget(more)
        layout.addLayout(actions)

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        self.selected.emit(self.tool)
        super().mousePressEvent(event)


class DetailsPanel(QFrame):
    action_requested = Signal(str, object)

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("DetailsPanel")
        self.setMinimumWidth(380)
        self.setMaximumWidth(460)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(24, 24, 24, 24)
        self.layout.setSpacing(12)
        self.render_empty()

    def clear(self) -> None:
        while self.layout.count():
            item = self.layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

    def render_empty(self) -> None:
        self.clear()
        empty_mark = QLabel("TM")
        empty_mark.setObjectName("BrandMark")
        empty_mark.setFixedSize(54, 54)
        empty_mark.setAlignment(Qt.AlignCenter)
        title = QLabel("選擇一個工具")
        title.setObjectName("Title")
        body = QLabel("點選左側工具卡片後，這裡會顯示版本、安裝位置、GitHub 來源與更新日誌。")
        body.setObjectName("Muted")
        body.setWordWrap(True)
        self.layout.addWidget(empty_mark)
        self.layout.addWidget(title)
        self.layout.addWidget(body)
        self.layout.addStretch(1)

    def render_tool(self, tool: ToolInfo, status: str, install_path: Path, local_version: str) -> None:
        self.clear()

        top = QHBoxLayout()
        top.setSpacing(14)
        icon = QLabel(tool_initial(tool.name))
        icon.setObjectName("ToolIcon")
        icon.setFixedSize(64, 64)
        icon.setAlignment(Qt.AlignCenter)
        icon.setStyleSheet(f"background:{tool_color(tool.category)};font-size:28px;")
        top.addWidget(icon)
        title_box = QVBoxLayout()
        title_box.setSpacing(3)
        title = QLabel(tool.name)
        title.setObjectName("Title")
        category = QLabel(tool.category)
        category.setObjectName("Category")
        title_box.addWidget(title)
        title_box.addWidget(category)
        top.addLayout(title_box, 1)
        top.addWidget(status_label(status), 0, Qt.AlignTop)
        self.layout.addLayout(top)

        desc = QLabel(tool.description or "尚未填寫工具用途描述。")
        desc.setObjectName("CardDescription")
        desc.setWordWrap(True)
        self.layout.addWidget(desc)

        primary_text = primary_action_text(status)
        primary = QPushButton(primary_text)
        primary.setObjectName("PrimaryButton")
        primary.clicked.connect(lambda: self.action_requested.emit(primary_text, tool))
        self.layout.addWidget(primary)

        folder = QPushButton("開啟資料夾")
        folder.setObjectName("SecondaryButton")
        folder.clicked.connect(lambda: self.action_requested.emit("資料夾", tool))
        self.layout.addWidget(folder)

        self.layout.addSpacing(12)
        self.layout.addWidget(section("工具資訊"))
        for key, value in [
            ("本機版本", local_version or "-"),
            ("雲端版本", tool.version),
            ("更新時間", tool.updated_at or "-"),
            ("安裝位置", str(install_path)),
            ("工具大小", tool.size or "-"),
            ("GitHub 路徑", tool.path or "-"),
            ("啟動檔", tool.entry or "-"),
            ("標籤", "、".join(tool.tags) if tool.tags else "-"),
        ]:
            self.layout.addWidget(meta_row(key, value))

        self.layout.addSpacing(12)
        self.layout.addWidget(section("更新日誌"))
        if tool.changelog:
            for item in tool.changelog:
                line = QLabel(f"- {item}")
                line.setWordWrap(True)
                self.layout.addWidget(line)
        else:
            empty = QLabel("尚未填寫更新日誌。")
            empty.setObjectName("Muted")
            self.layout.addWidget(empty)
        self.layout.addStretch(1)


class AdminDialog(QDialog):
    def __init__(self, parent: QWidget, config: AppConfig, config_store: ConfigStore) -> None:
        super().__init__(parent)
        self.config = config
        self.config_store = config_store
        self.setWindowTitle("管理者模式")
        self.resize(860, 680)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        title = QLabel("管理者模式")
        title.setObjectName("Title")
        layout.addWidget(title)

        path_row = QHBoxLayout()
        self.root_input = QLineEdit(str((manager_dir() / self.config.admin_tools_root).resolve()))
        browse = QPushButton("選擇資料夾")
        browse.clicked.connect(self.choose_folder)
        path_row.addWidget(QLabel("工具包根目錄"))
        path_row.addWidget(self.root_input, 1)
        path_row.addWidget(browse)
        layout.addLayout(path_row)

        actions = QHBoxLayout()
        scan = QPushButton("掃描工具")
        scan.setObjectName("PrimaryButton")
        scan.clicked.connect(self.scan)
        save = QPushButton("儲存 tools-index.json")
        save.clicked.connect(self.save)
        actions.addWidget(scan)
        actions.addWidget(save)
        actions.addStretch(1)
        layout.addLayout(actions)

        self.summary = QLabel("尚未掃描。")
        self.summary.setObjectName("Muted")
        layout.addWidget(self.summary)

        self.preview = QPlainTextEdit()
        self.preview.setReadOnly(True)
        layout.addWidget(self.preview, 1)

        close = QPushButton("關閉")
        close.clicked.connect(self.accept)
        layout.addWidget(close, 0, Qt.AlignRight)

    def choose_folder(self) -> None:
        selected = QFileDialog.getExistingDirectory(self, "選擇工具包根目錄", self.root_input.text())
        if selected:
            self.root_input.setText(selected)

    def scan(self) -> None:
        root = Path(self.root_input.text()).resolve()
        if not root.exists():
            QMessageBox.warning(self, APP_NAME, "工具包根目錄不存在。")
            return
        index = scan_tools(root)
        self.preview.setPlainText(json.dumps(index.to_dict(), ensure_ascii=False, indent=2))
        self.summary.setText(f"掃描完成：{len(index.tools)} 個工具。")

    def save(self) -> None:
        if not self.preview.toPlainText().strip():
            self.scan()
        root = Path(self.root_input.text()).resolve()
        data = json.loads(self.preview.toPlainText())
        save_index(ToolIndex.from_dict(data), root / INDEX_FILE_NAME)
        try:
            self.config.admin_tools_root = str(root.relative_to(manager_dir()))
        except ValueError:
            self.config.admin_tools_root = str(root)
        self.config_store.save(self.config)
        QMessageBox.information(self, APP_NAME, f"已儲存：{root / INDEX_FILE_NAME}")


class SettingsDialog(QDialog):
    def __init__(self, parent: QWidget, config: AppConfig, config_store: ConfigStore) -> None:
        super().__init__(parent)
        self.config = config
        self.config_store = config_store
        self.setWindowTitle("設定")
        self.resize(560, 340)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(10)

        self.owner = labeled_input(layout, "GitHub Owner", config.github_owner)
        self.repo = labeled_input(layout, "GitHub Repo", config.github_repo)
        self.branch = labeled_input(layout, "Branch", config.github_branch)
        self.install_root = labeled_input(layout, "工具安裝位置", config.install_root)

        buttons = QHBoxLayout()
        save = QPushButton("儲存")
        save.setObjectName("PrimaryButton")
        save.clicked.connect(self.save)
        cancel = QPushButton("取消")
        cancel.clicked.connect(self.reject)
        buttons.addStretch(1)
        buttons.addWidget(cancel)
        buttons.addWidget(save)
        layout.addLayout(buttons)

    def save(self) -> None:
        self.config.github_owner = self.owner.text().strip()
        self.config.github_repo = self.repo.text().strip()
        self.config.github_branch = self.branch.text().strip() or "main"
        self.config.install_root = self.install_root.text().strip()
        self.config_store.save(self.config)
        self.accept()


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(1440, 900)

        self.config_store = ConfigStore(manager_dir())
        self.config = self.config_store.load()
        self.state = StateStore(app_data_dir())
        self.library = ToolLibrary(self.config, self.state)
        self.github = GitHubClient(self.config)
        self.tools: list[ToolInfo] = []
        self.selected_tool: ToolInfo | None = None
        self.current_category = "全部工具"
        self.worker_thread: QThread | None = None
        self.worker: Worker | None = None
        self._last_card_columns = 0

        root = QWidget()
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)
        root_layout.addWidget(self.build_top_bar())
        root_layout.addWidget(self.build_body(), 1)
        self.setCentralWidget(root)

        self.load_local_index()
        if self.config.auto_check_on_start and self.github.is_configured:
            self.refresh_from_github()

    def build_top_bar(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("TopBar")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(18, 12, 18, 12)
        layout.setSpacing(14)

        brand = QLabel("TM")
        brand.setObjectName("BrandMark")
        brand.setFixedSize(42, 42)
        brand.setAlignment(Qt.AlignCenter)
        layout.addWidget(brand)

        title_box = QVBoxLayout()
        title_box.setSpacing(1)
        title = QLabel("工具包管理器")
        title.setObjectName("Title")
        subtitle = QLabel("GitHub 雲端工具同步中心")
        subtitle.setObjectName("AppSubtitle")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        layout.addLayout(title_box)

        self.sync_status = QLabel("GitHub 同步狀態：尚未同步")
        self.sync_status.setObjectName("Muted")
        layout.addWidget(self.sync_status)
        layout.addStretch(1)

        refresh = QPushButton("重新整理")
        refresh.clicked.connect(self.refresh_from_github)
        check = QPushButton("檢查更新")
        check.clicked.connect(self.refresh_from_github)
        admin = QPushButton("管理者模式")
        admin.clicked.connect(self.open_admin)
        settings = QPushButton("設定")
        settings.clicked.connect(self.open_settings)
        refresh.setObjectName("SecondaryButton")
        check.setObjectName("SecondaryButton")
        admin.setObjectName("SecondaryButton")
        settings.setObjectName("GhostButton")
        layout.addWidget(refresh)
        layout.addWidget(check)
        layout.addWidget(admin)
        layout.addWidget(settings)
        return bar

    def build_body(self) -> QWidget:
        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)

        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setMinimumWidth(250)
        sidebar.setMaximumWidth(290)
        side_layout = QVBoxLayout(sidebar)
        side_layout.setContentsMargins(0, 18, 0, 18)
        self.category_list = QListWidget()
        self.category_list.currentItemChanged.connect(self.category_changed)
        side_layout.addWidget(self.category_list, 1)
        splitter.addWidget(sidebar)

        main = QWidget()
        main_layout = QVBoxLayout(main)
        main_layout.setContentsMargins(24, 22, 24, 22)
        main_layout.setSpacing(14)

        controls = QHBoxLayout()
        controls.setSpacing(10)
        self.search = QLineEdit()
        self.search.setPlaceholderText("搜尋工具、用途或標籤...")
        self.search.textChanged.connect(self.render_tools)
        self.sort = QComboBox()
        self.sort.addItems(["名稱 (A-Z)", "分類", "更新日期"])
        self.sort.currentTextChanged.connect(self.render_tools)
        controls.addWidget(self.search, 1)
        controls.addWidget(QLabel("排序"))
        controls.addWidget(self.sort)
        main_layout.addLayout(controls)

        self.count_label = QLabel("共 0 個工具")
        self.count_label.setObjectName("Muted")
        main_layout.addWidget(self.count_label)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.cards_host = QWidget()
        self.cards_grid = QGridLayout(self.cards_host)
        self.cards_grid.setContentsMargins(0, 0, 0, 0)
        self.cards_grid.setSpacing(14)
        self.scroll.setWidget(self.cards_host)
        main_layout.addWidget(self.scroll, 1)
        splitter.addWidget(main)

        self.details = DetailsPanel()
        self.details.action_requested.connect(self.handle_action)
        splitter.addWidget(self.details)
        splitter.setSizes([270, 780, 390])
        return splitter

    def load_local_index(self) -> None:
        local_index = manager_dir().parent / INDEX_FILE_NAME
        if local_index.exists():
            data = json.loads(local_index.read_text(encoding="utf-8-sig"))
            self.tools = ToolIndex.from_dict(data).tools
            self.sync_status.setText("GitHub 同步狀態：已載入本機索引")
        else:
            self.tools = []
            self.sync_status.setText("GitHub 同步狀態：尚未設定，請先用管理者模式產生索引")
        self.render_categories()
        self.render_tools()

    def refresh_from_github(self) -> None:
        if not self.github.is_configured:
            QMessageBox.information(self, APP_NAME, "請先到設定填入 GitHub Owner 與 Repo。")
            return

        self.sync_status.setText("GitHub 同步狀態：正在讀取...")

        def job(_progress):
            return self.github.fetch_index()

        self.start_worker(job, self.apply_remote_index)

    def apply_remote_index(self, index: ToolIndex) -> None:
        self.tools = index.tools
        self.sync_status.setText(f"GitHub 同步狀態：已同步（{index.updated_at or '剛剛'}）")
        self.render_categories()
        self.render_tools()

    def render_categories(self) -> None:
        self.category_list.blockSignals(True)
        self.category_list.clear()
        categories = ["全部工具"]
        categories.extend(sorted({tool.category for tool in self.tools}))
        categories.extend(["已安裝", "可更新"])
        for category in categories:
            count = self.count_for_category(category)
            item = QListWidgetItem(f"{category}    {count}")
            item.setData(Qt.UserRole, category)
            self.category_list.addItem(item)
            if category == self.current_category:
                self.category_list.setCurrentItem(item)
        self.category_list.blockSignals(False)
        if not self.category_list.currentItem() and self.category_list.count():
            self.category_list.setCurrentRow(0)

    def count_for_category(self, category: str) -> int:
        if category == "全部工具":
            return len(self.tools)
        if category == "已安裝":
            return sum(1 for tool in self.tools if self.library.status_for(tool) != "未安裝")
        if category == "可更新":
            return sum(1 for tool in self.tools if self.library.status_for(tool) == "可更新")
        return sum(1 for tool in self.tools if tool.category == category)

    def category_changed(self, current: QListWidgetItem | None, _previous: QListWidgetItem | None) -> None:
        if current:
            self.current_category = current.data(Qt.UserRole)
            self.render_tools()

    def filtered_tools(self) -> list[ToolInfo]:
        query = self.search.text().strip().lower()
        result = []
        for tool in self.tools:
            status = self.library.status_for(tool)
            if self.current_category == "已安裝" and status == "未安裝":
                continue
            if self.current_category == "可更新" and status != "可更新":
                continue
            if self.current_category not in ("全部工具", "已安裝", "可更新") and tool.category != self.current_category:
                continue
            haystack = " ".join([tool.name, tool.category, tool.description, " ".join(tool.tags)]).lower()
            if query and query not in haystack:
                continue
            result.append(tool)

        sort_mode = self.sort.currentText()
        if sort_mode == "分類":
            result.sort(key=lambda item: (item.category, item.name))
        elif sort_mode == "更新日期":
            result.sort(key=lambda item: item.updated_at, reverse=True)
        else:
            result.sort(key=lambda item: item.name.lower())
        return result

    def render_tools(self) -> None:
        while self.cards_grid.count():
            item = self.cards_grid.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        tools = self.filtered_tools()
        self.count_label.setText(f"共 {len(tools)} 個工具")
        columns = self.card_column_count()
        self._last_card_columns = columns
        for index, tool in enumerate(tools):
            is_selected = bool(self.selected_tool and self.selected_tool.id == tool.id)
            card = ToolCard(tool, self.library.status_for(tool), self.local_version(tool), is_selected)
            card.selected.connect(self.select_tool)
            card.action_requested.connect(self.handle_action)
            row = index // columns
            col = index % columns
            self.cards_grid.addWidget(card, row, col)
        for col in range(columns):
            self.cards_grid.setColumnStretch(col, 1)
        self.cards_grid.setRowStretch((len(tools) + columns - 1) // columns, 1)

        if self.selected_tool:
            self.update_details()

    def card_column_count(self) -> int:
        width = self.scroll.viewport().width() if hasattr(self, "scroll") else self.width()
        return 2 if width >= 920 else 1

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        if hasattr(self, "scroll") and self.tools:
            columns = self.card_column_count()
            if columns != self._last_card_columns:
                self._last_card_columns = columns
                self.render_tools()

    def select_tool(self, tool: ToolInfo) -> None:
        self.selected_tool = tool
        self.render_tools()
        self.update_details()

    def update_details(self) -> None:
        if not self.selected_tool:
            self.details.render_empty()
            return
        self.details.render_tool(
            self.selected_tool,
            self.library.status_for(self.selected_tool),
            self.library.install_path_for(self.selected_tool),
            self.local_version(self.selected_tool),
        )

    def handle_action(self, action: str, tool: ToolInfo) -> None:
        self.selected_tool = tool
        self.update_details()
        if action in ("下載", "更新"):
            self.download_tool(tool)
        elif action == "開啟":
            self.try_action(lambda: self.library.launch(tool))
        elif action in ("資料夾", "開啟資料夾"):
            self.try_action(lambda: self.library.open_folder(tool))
        elif action == "詳情":
            self.update_details()

    def download_tool(self, tool: ToolInfo) -> None:
        if not self.github.is_configured:
            QMessageBox.information(self, APP_NAME, "請先到設定填入 GitHub Owner 與 Repo。")
            return
        destination = self.library.install_path_for(tool)
        self.sync_status.setText(f"正在下載：{tool.name}")

        def job(progress):
            self.github.download_tool(tool, destination, progress)
            return destination

        def done(path: Path):
            self.library.mark_installed(tool, path)
            self.sync_status.setText(f"已完成：{tool.name}")
            self.render_categories()
            self.render_tools()
            self.update_details()

        self.start_worker(job, done)

    def start_worker(self, fn: Callable, on_done: Callable) -> None:
        if self.worker_thread and self.worker_thread.isRunning():
            QMessageBox.information(self, APP_NAME, "目前已有操作正在執行，請稍候。")
            return
        thread = QThread(self)
        worker = Worker(fn)
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(on_done)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        worker.failed.connect(self.worker_failed)
        worker.failed.connect(thread.quit)
        worker.failed.connect(worker.deleteLater)
        worker.progress.connect(self.worker_progress)
        thread.finished.connect(self.clear_worker)
        thread.finished.connect(thread.deleteLater)
        self.worker_thread = thread
        self.worker = worker
        thread.start()

    def clear_worker(self) -> None:
        self.worker_thread = None
        self.worker = None

    def worker_progress(self, message: str, percent: int) -> None:
        self.sync_status.setText(f"{message} {percent}%")

    def worker_failed(self, message: str) -> None:
        self.sync_status.setText("操作失敗")
        QMessageBox.warning(self, APP_NAME, message)

    def open_admin(self) -> None:
        dialog = AdminDialog(self, self.config, self.config_store)
        if dialog.exec():
            self.load_local_index()

    def open_settings(self) -> None:
        dialog = SettingsDialog(self, self.config, self.config_store)
        if dialog.exec():
            self.config = self.config_store.load()
            self.github = GitHubClient(self.config)
            self.library = ToolLibrary(self.config, self.state)
            self.render_categories()
            self.render_tools()

    def try_action(self, fn: Callable[[], None]) -> None:
        try:
            fn()
        except Exception as exc:
            QMessageBox.warning(self, APP_NAME, str(exc))

    def local_version(self, tool: ToolInfo) -> str:
        installed = self.library.installed.get(tool.id)
        return installed.version if installed else ""


def tool_initial(name: str) -> str:
    cleaned = name.strip()
    if not cleaned:
        return "T"
    return cleaned[0].upper()


def tool_color(category: str) -> str:
    palette = {
        "Sharder": "#6f9f00",
        "SPINE相關工具": "#3a464d",
        "數字圖片工具": "#0f766e",
        "測試工具": "#8a6f13",
    }
    if category in palette:
        return palette[category]
    colors = ["#5f6b3a", "#364148", "#0f766e", "#7a6412", "#4f6f00"]
    return colors[sum(ord(char) for char in category) % len(colors)]


def status_label(status: str) -> QLabel:
    label = QLabel(status)
    if status == "已是最新版":
        label.setObjectName("StatusGreen")
    elif status == "可更新":
        label.setObjectName("StatusAmber")
    else:
        label.setObjectName("StatusGray")
    return label


def primary_action_text(status: str) -> str:
    if status == "未安裝":
        return "下載"
    if status == "可更新":
        return "更新"
    if status == "本機工具遺失":
        return "下載"
    return "開啟"


def section(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("SectionTitle")
    return label


def meta_row(key: str, value: str) -> QWidget:
    row = QWidget()
    layout = QHBoxLayout(row)
    layout.setContentsMargins(0, 0, 0, 0)
    key_label = QLabel(key)
    key_label.setObjectName("Muted")
    key_label.setFixedWidth(82)
    value_label = QLabel(value)
    value_label.setWordWrap(True)
    layout.addWidget(key_label)
    layout.addWidget(value_label, 1)
    return row


def labeled_input(layout: QVBoxLayout, label: str, value: str) -> QLineEdit:
    row = QHBoxLayout()
    row.addWidget(QLabel(label))
    field = QLineEdit(value)
    row.addWidget(field, 1)
    layout.addLayout(row)
    return field


def manager_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def main() -> None:
    app = QApplication(sys.argv)
    app.setStyleSheet(APP_QSS)
    app.setApplicationName(APP_NAME)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())
