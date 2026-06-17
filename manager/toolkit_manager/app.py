from __future__ import annotations

import json
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QObject, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from .indexer import save_all_tool_metadata, save_index, save_tool_metadata, scan_tools
from .models import APP_NAME, APP_VERSION, INDEX_FILE_NAME, AppConfig, ManagerRelease, ToolIndex, ToolInfo
from .services import ConfigStore, GitHubClient, StateStore, ToolLibrary, app_data_dir, compare_versions, ensure_safe_child
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
        self.setFixedHeight(178)
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
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.content = QWidget()
        self.content.setObjectName("DetailsContent")
        self.layout = QVBoxLayout(self.content)
        self.layout.setContentsMargins(24, 24, 24, 24)
        self.layout.setSpacing(12)
        self.scroll.setWidget(self.content)
        outer.addWidget(self.scroll, 1)
        self.render_empty()

    def clear(self) -> None:
        while self.layout.count():
            item = self.layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.setParent(None)
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
        title.setWordWrap(True)
        category = QLabel(tool.category)
        category.setObjectName("Category")
        category.setWordWrap(True)
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
    index_updated = Signal()

    def __init__(self, parent: QWidget, config: AppConfig, config_store: ConfigStore) -> None:
        super().__init__(parent)
        self.config = config
        self.config_store = config_store
        self.index: ToolIndex | None = None
        self.current_tool: ToolInfo | None = None
        self.setWindowTitle("管理者模式")
        self.resize(1040, 720)

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
        scan = QPushButton("掃描並更新文件")
        scan.setObjectName("PrimaryButton")
        scan.clicked.connect(self.scan)
        save_current = QPushButton("儲存目前工具")
        save_current.clicked.connect(self.save_current)
        save_all = QPushButton("儲存全部並更新總索引")
        save_all.clicked.connect(self.save_all)
        push_git = QPushButton("推送工具更新到 Git")
        push_git.setObjectName("SecondaryButton")
        push_git.clicked.connect(self.push_tool_updates_to_git)
        actions.addWidget(scan)
        actions.addWidget(save_current)
        actions.addWidget(save_all)
        actions.addWidget(push_git)
        actions.addStretch(1)
        layout.addLayout(actions)

        self.summary = QLabel("尚未掃描。掃描後會自動建立每個工具資料夾的 tool.json，並更新根目錄 tools-index.json。")
        self.summary.setObjectName("Muted")
        layout.addWidget(self.summary)

        body = QSplitter(Qt.Horizontal)
        body.setChildrenCollapsible(False)
        self.tool_list = QListWidget()
        self.tool_list.setMinimumWidth(280)
        self.tool_list.currentItemChanged.connect(self.tool_changed)
        body.addWidget(self.tool_list)

        editor = QWidget()
        editor_layout = QVBoxLayout(editor)
        editor_layout.setContentsMargins(14, 0, 0, 0)
        editor_layout.setSpacing(10)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight)
        form.setFormAlignment(Qt.AlignTop)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(10)

        self.path_value = QLabel("-")
        self.path_value.setWordWrap(True)
        self.id_input = QLineEdit()
        self.name_input = QLineEdit()
        self.category_input = QLineEdit()
        self.version_input = QLineEdit()
        self.entry_input = QLineEdit()
        self.updated_input = QLineEdit()
        self.tags_input = QLineEdit()
        self.description_input = QPlainTextEdit()
        self.description_input.setFixedHeight(92)
        self.changelog_input = QPlainTextEdit()
        self.changelog_input.setFixedHeight(118)

        form.addRow("資料夾路徑", self.path_value)
        form.addRow("工具 ID", self.id_input)
        form.addRow("工具名稱", self.name_input)
        form.addRow("分類", self.category_input)
        form.addRow("版本", self.version_input)
        form.addRow("啟動檔", self.entry_input)
        form.addRow("更新日期", self.updated_input)
        form.addRow("標籤", self.tags_input)
        form.addRow("用途描述", self.description_input)
        form.addRow("更新日誌", self.changelog_input)
        editor_layout.addLayout(form)

        hint = QLabel("標籤可用逗號分隔；更新日誌一行一筆。用途描述會顯示在工具卡片與右側資訊欄。")
        hint.setObjectName("Muted")
        hint.setWordWrap(True)
        editor_layout.addWidget(hint)
        editor_layout.addStretch(1)
        body.addWidget(editor)
        body.setSizes([320, 700])
        layout.addWidget(body, 1)

        close = QPushButton("關閉")
        close.clicked.connect(self.accept)
        layout.addWidget(close, 0, Qt.AlignRight)

    def choose_folder(self) -> None:
        selected = QFileDialog.getExistingDirectory(self, "選擇工具包根目錄", self.root_input.text())
        if selected:
            self.root_input.setText(selected)

    def root_path(self) -> Path:
        return Path(self.root_input.text()).resolve()

    def scan(self) -> None:
        root = self.root_path()
        if not root.exists():
            QMessageBox.warning(self, APP_NAME, "工具包根目錄不存在。")
            return
        index = scan_tools(root)
        save_all_tool_metadata(root, index)
        save_index(index, root / INDEX_FILE_NAME)
        self.index = index
        self.populate_tool_list()
        self.persist_admin_root(root)
        self.summary.setText(f"已掃描 {len(index.tools)} 個工具，並更新 tool.json / {INDEX_FILE_NAME}。")
        self.index_updated.emit()

    def populate_tool_list(self) -> None:
        self.tool_list.blockSignals(True)
        self.tool_list.clear()
        self.current_tool = None
        if not self.index:
            self.tool_list.blockSignals(False)
            return
        for tool in self.index.tools:
            item = QListWidgetItem(f"{tool.name}    {tool.category}")
            item.setData(Qt.UserRole, tool)
            self.tool_list.addItem(item)
        self.tool_list.blockSignals(False)
        if self.tool_list.count():
            self.tool_list.setCurrentRow(0)
            self.load_tool(self.tool_list.currentItem().data(Qt.UserRole))

    def tool_changed(self, current: QListWidgetItem | None, _previous: QListWidgetItem | None) -> None:
        if self.current_tool:
            self.apply_fields_to_tool(self.current_tool)
        if current:
            self.load_tool(current.data(Qt.UserRole))

    def load_tool(self, tool: ToolInfo) -> None:
        self.current_tool = tool
        self.path_value.setText(tool.path or "-")
        self.id_input.setText(tool.id)
        self.name_input.setText(tool.name)
        self.category_input.setText(tool.category)
        self.version_input.setText(tool.version)
        self.entry_input.setText(tool.entry)
        self.updated_input.setText(tool.updated_at)
        self.tags_input.setText(", ".join(tool.tags))
        self.description_input.setPlainText(tool.description)
        self.changelog_input.setPlainText("\n".join(tool.changelog))

    def apply_fields_to_tool(self, tool: ToolInfo) -> None:
        tool.id = self.id_input.text().strip() or tool.id
        tool.name = self.name_input.text().strip() or tool.name
        tool.category = self.category_input.text().strip() or tool.category
        tool.version = self.version_input.text().strip() or "1.0.0"
        tool.entry = self.entry_input.text().strip().replace("\\", "/").strip("/")
        tool.updated_at = self.updated_input.text().strip()
        tool.description = self.description_input.toPlainText().strip()
        tool.tags = self.parse_tags(self.tags_input.text())
        tool.changelog = [
            line.lstrip("-").strip()
            for line in self.changelog_input.toPlainText().splitlines()
            if line.lstrip("-").strip()
        ]

    def parse_tags(self, value: str) -> list[str]:
        normalized = value
        for separator in ["，", "、", ";", "；", "\n"]:
            normalized = normalized.replace(separator, ",")
        return [item.strip() for item in normalized.split(",") if item.strip()]

    def save_current(self) -> None:
        if not self.index or not self.current_tool:
            QMessageBox.information(self, APP_NAME, "請先掃描工具。")
            return
        root = self.root_path()
        self.apply_fields_to_tool(self.current_tool)
        save_tool_metadata(root, self.current_tool)
        save_index(self.index, root / INDEX_FILE_NAME)
        self.update_current_item_text()
        self.persist_admin_root(root)
        self.summary.setText(f"已儲存：{self.current_tool.name}")
        self.index_updated.emit()

    def save_all(self) -> None:
        if not self.index:
            self.scan()
            return
        root = self.root_path()
        if self.current_tool:
            self.apply_fields_to_tool(self.current_tool)
        save_all_tool_metadata(root, self.index)
        save_index(self.index, root / INDEX_FILE_NAME)
        self.update_current_item_text()
        self.persist_admin_root(root)
        self.summary.setText(f"已儲存全部工具，並更新 {INDEX_FILE_NAME}。")
        self.index_updated.emit()
        QMessageBox.information(self, APP_NAME, "工具文件已更新完成。")

    def push_tool_updates_to_git(self) -> None:
        root = self.root_path()
        if not root.exists():
            QMessageBox.warning(self, APP_NAME, "工具包根目錄不存在。")
            return
        if not (root / ".git").exists():
            QMessageBox.warning(self, APP_NAME, "工具包根目錄不是 Git repository。")
            return
        try:
            if self.index:
                if self.current_tool:
                    self.apply_fields_to_tool(self.current_tool)
                save_all_tool_metadata(root, self.index)
                save_index(self.index, root / INDEX_FILE_NAME)
                self.index_updated.emit()

            status = git_output(root, ["status", "--short"])
            if not status.strip():
                QMessageBox.information(self, APP_NAME, "目前沒有需要推送的工具更新。")
                return
            paths = git_tool_update_paths(root, status)
            if not paths:
                QMessageBox.information(self, APP_NAME, "目前沒有工具更新需要推送；管理器或設計檔變更請用命令列提交。")
                return

            preview = "\n".join(git_status_lines_for_paths(status, paths))
            if len(preview) > 2400:
                preview = preview[:2400] + "\n..."
            choice = QMessageBox.question(
                self,
                APP_NAME,
                f"即將提交並推送以下工具更新：\n\n{preview}\n\n是否繼續？",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes,
            )
            if choice != QMessageBox.Yes:
                return

            message, ok = QInputDialog.getText(
                self,
                "Git Commit",
                "請輸入提交訊息",
                QLineEdit.Normal,
                "更新工具包版本",
            )
            if not ok:
                return
            message = message.strip()
            if not message:
                QMessageBox.warning(self, APP_NAME, "提交訊息不可空白。")
                return

            git_run(root, ["add", "-A", "--", *paths])
            staged = git_output(root, ["diff", "--cached", "--name-only"])
            if not staged.strip():
                QMessageBox.information(self, APP_NAME, "沒有可提交的工具更新。")
                return
            git_run(root, ["commit", "-m", message])
            branch = git_output(root, ["branch", "--show-current"]).strip() or "main"
            git_run(root, ["push", "origin", branch])
            self.summary.setText(f"已提交並推送到 origin/{branch}：{message}")
            QMessageBox.information(self, APP_NAME, f"工具更新已推送到 Git：origin/{branch}")
        except Exception as exc:
            QMessageBox.warning(self, APP_NAME, f"Git 推送失敗：\n{exc}")

    def update_current_item_text(self) -> None:
        item = self.tool_list.currentItem()
        if item and self.current_tool:
            item.setText(f"{self.current_tool.name}    {self.current_tool.category}")

    def persist_admin_root(self, root: Path) -> None:
        try:
            self.config.admin_tools_root = str(root.relative_to(manager_dir()))
        except ValueError:
            self.config.admin_tools_root = str(root)
        self.config_store.save(self.config)


class SettingsDialog(QDialog):
    def __init__(self, parent: QWidget, config: AppConfig, config_store: ConfigStore) -> None:
        super().__init__(parent)
        self.config = config
        self.config_store = config_store
        self.original_admin_password = config.admin_password
        self.admin_password_unlocked = False
        self.setWindowTitle("設定")
        self.resize(560, 390)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(10)

        self.owner = labeled_input(layout, "GitHub Owner", config.github_owner)
        self.repo = labeled_input(layout, "GitHub Repo", config.github_repo)
        self.branch = labeled_input(layout, "Branch", config.github_branch)
        self.install_root = labeled_input(layout, "工具安裝位置", config.install_root)

        password_row = QHBoxLayout()
        password_row.addWidget(QLabel("管理者密碼"))
        self.admin_password = QLineEdit("********")
        self.admin_password.setEchoMode(QLineEdit.Password)
        self.admin_password.setReadOnly(True)
        self.admin_password.setPlaceholderText("需驗證後才能修改")
        password_row.addWidget(self.admin_password, 1)
        self.unlock_admin_password_button = QPushButton("修改")
        self.unlock_admin_password_button.setObjectName("SecondaryButton")
        self.unlock_admin_password_button.clicked.connect(self.unlock_admin_password)
        password_row.addWidget(self.unlock_admin_password_button)
        layout.addLayout(password_row)

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

    def unlock_admin_password(self) -> None:
        password, ok = QInputDialog.getText(
            self,
            "管理者驗證",
            "請先輸入目前管理者密碼",
            QLineEdit.Password,
        )
        if not ok:
            return
        if password != self.original_admin_password:
            QMessageBox.warning(self, APP_NAME, "管理者密碼錯誤。")
            return
        self.admin_password_unlocked = True
        self.admin_password.clear()
        self.admin_password.setReadOnly(False)
        self.admin_password.setPlaceholderText("輸入新的管理者密碼")
        self.admin_password.setFocus()
        self.unlock_admin_password_button.setText("已解鎖")
        self.unlock_admin_password_button.setEnabled(False)

    def save(self) -> None:
        self.config.github_owner = self.owner.text().strip()
        self.config.github_repo = self.repo.text().strip()
        self.config.github_branch = self.branch.text().strip() or "main"
        self.config.install_root = self.install_root.text().strip()
        if self.admin_password_unlocked:
            new_password = self.admin_password.text().strip()
            if not new_password:
                QMessageBox.warning(self, APP_NAME, "請輸入新的管理者密碼，或按取消放棄修改。")
                return
            self.config.admin_password = new_password
        else:
            self.config.admin_password = self.original_admin_password
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
        self.worker_done_callback: Callable[[object], None] | None = None
        self.worker_failed_callback: Callable[[str], None] | None = None
        self._last_card_columns = 0
        self.progress_bar: QProgressBar | None = None
        self.manager_update_checked = False

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
        title = QLabel(APP_NAME)
        title.setObjectName("Title")
        subtitle = QLabel(f"GitHub 雲端工具同步中心  v{APP_VERSION}")
        subtitle.setObjectName("AppSubtitle")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)
        layout.addLayout(title_box)

        self.sync_status = QLabel("GitHub 同步狀態：尚未同步")
        self.sync_status.setObjectName("Muted")
        layout.addWidget(self.sync_status)
        self.progress_bar = QProgressBar()
        self.progress_bar.setObjectName("DownloadProgress")
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedWidth(220)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.hide()
        layout.addWidget(self.progress_bar)
        layout.addStretch(1)

        refresh = QPushButton("重新整理")
        refresh.clicked.connect(self.refresh_from_github)
        check = QPushButton("檢查更新")
        check.clicked.connect(self.refresh_from_github)
        manager_update = QPushButton("管理器更新")
        manager_update.clicked.connect(self.check_manager_update)
        admin = QPushButton("管理者模式")
        admin.clicked.connect(self.open_admin)
        settings = QPushButton("設定")
        settings.clicked.connect(self.open_settings)
        refresh.setObjectName("SecondaryButton")
        check.setObjectName("SecondaryButton")
        manager_update.setObjectName("SecondaryButton")
        admin.setObjectName("SecondaryButton")
        settings.setObjectName("GhostButton")
        layout.addWidget(refresh)
        layout.addWidget(check)
        layout.addWidget(manager_update)
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
        self.reconcile_selected_tool()
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
        self.reconcile_selected_tool()
        self.render_categories()
        self.render_tools()
        if not self.manager_update_checked:
            QTimer.singleShot(300, self.check_manager_update_silent)

    def reconcile_selected_tool(self) -> None:
        if not self.selected_tool:
            return
        selected_id = self.selected_tool.id
        self.selected_tool = next((tool for tool in self.tools if tool.id == selected_id), None)
        if not self.selected_tool:
            self.details.render_empty()

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
                widget.setParent(None)
                widget.deleteLater()

        tools = self.filtered_tools()
        self.count_label.setText(f"共 {len(tools)} 個工具")
        columns = self.card_column_count()
        self._last_card_columns = columns
        row_count = (len(tools) + columns - 1) // columns
        for index, tool in enumerate(tools):
            is_selected = bool(self.selected_tool and self.selected_tool.id == tool.id)
            card = ToolCard(tool, self.library.status_for(tool), self.local_version(tool), is_selected)
            card.selected.connect(self.select_tool)
            card.action_requested.connect(self.handle_action)
            row = index // columns
            col = index % columns
            self.cards_grid.addWidget(card, row, col)
        for row in range(row_count):
            self.cards_grid.setRowMinimumHeight(row, 178)
        for col in range(columns):
            self.cards_grid.setColumnStretch(col, 1)
        self.cards_grid.setRowStretch(row_count, 1)
        self.cards_host.setMinimumHeight(max(0, row_count * 192))

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
        self.show_progress(0)

        def job(progress):
            self.github.download_tool(tool, destination, progress)
            return destination

        def done(path: Path):
            self.library.mark_installed(tool, path)
            self.sync_status.setText(f"已完成：{tool.name}")
            self.show_progress(100)
            QTimer.singleShot(1200, self.hide_progress)
            self.render_categories()
            self.render_tools()
            self.update_details()

        self.start_worker(job, done)

    def check_manager_update_silent(self) -> None:
        self.check_manager_update_impl(silent=True)

    def check_manager_update(self) -> None:
        self.check_manager_update_impl(silent=False)

    def check_manager_update_impl(self, silent: bool) -> None:
        if not self.github.is_configured:
            if not silent:
                QMessageBox.information(self, APP_NAME, "請先到設定填入 GitHub Owner 與 Repo。")
            return
        self.manager_update_checked = True
        if not silent:
            self.sync_status.setText("正在檢查管理器本體更新...")

        def job(_progress):
            return self.github.fetch_latest_manager_release()

        def done(release: ManagerRelease | None):
            self.handle_manager_release(release, silent)

        self.start_worker(
            job,
            done,
            on_failed=lambda message: self.manager_update_failed(message, silent),
        )

    def manager_update_failed(self, message: str, silent: bool) -> None:
        if silent:
            return
        self.sync_status.setText("管理器更新檢查失敗")
        QMessageBox.warning(self, APP_NAME, message)

    def handle_manager_release(self, release: ManagerRelease | None, silent: bool) -> None:
        if not release:
            if not silent:
                QMessageBox.information(self, APP_NAME, "GitHub Release 找不到 ToolkitManager.zip 更新包。")
            return
        if compare_versions(APP_VERSION, release.version) >= 0:
            if not silent:
                QMessageBox.information(self, APP_NAME, f"目前已是最新版：v{APP_VERSION}")
            return

        body = release.body.strip()
        detail = f"目前版本：v{APP_VERSION}\n雲端版本：{release.tag_name}\n更新包：{release.asset_name}"
        if body:
            detail += f"\n\n更新說明：\n{body[:800]}"
        choice = QMessageBox.question(
            self,
            APP_NAME,
            f"發現新版{APP_NAME}。\n\n{detail}\n\n是否立即下載並更新？",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )
        if choice == QMessageBox.Yes:
            self.download_manager_update(release)

    def download_manager_update(self, release: ManagerRelease) -> None:
        if not getattr(sys, "frozen", False):
            QMessageBox.information(
                self,
                APP_NAME,
                "目前是開發模式，管理器本體更新只會在打包後的 ToolkitManager.exe 中執行。",
            )
            return
        updates_dir = app_data_dir() / "updates"
        self.sync_status.setText(f"正在下載管理器更新：{release.tag_name}")
        self.show_progress(0)

        def job(progress):
            return self.github.download_manager_release(release, updates_dir, progress)

        def done(zip_path: Path):
            self.show_progress(100)
            self.install_manager_update(zip_path)

        self.start_worker(job, done)

    def install_manager_update(self, zip_path: Path) -> None:
        updates_dir = app_data_dir() / "updates"
        extract_dir = updates_dir / "extracted"
        if extract_dir.exists():
            shutil.rmtree(extract_dir)
        extract_dir.mkdir(parents=True, exist_ok=True)
        extract_update_zip(zip_path, extract_dir)
        source_dir = find_update_source_dir(extract_dir)
        target_dir = manager_dir()
        script_path = write_update_script(source_dir, target_dir)
        QMessageBox.information(self, APP_NAME, "更新包已下載完成。按下確定後，管理器會關閉、套用更新並重新啟動。")
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        subprocess.Popen(["cmd", "/c", str(script_path)], cwd=str(target_dir), creationflags=flags)
        app = QApplication.instance()
        if app:
            app.quit()

    def start_worker(self, fn: Callable, on_done: Callable, on_failed: Callable[[str], None] | None = None) -> None:
        if self.worker_thread and self.worker_thread.isRunning():
            QMessageBox.information(self, APP_NAME, "目前已有操作正在執行，請稍候。")
            return
        thread = QThread(self)
        worker = Worker(fn)
        worker.moveToThread(thread)
        self.worker_done_callback = on_done
        self.worker_failed_callback = on_failed
        thread.started.connect(worker.run)
        worker.finished.connect(self.worker_finished)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        worker.failed.connect(self.worker_failed_dispatch)
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
        self.worker_done_callback = None
        self.worker_failed_callback = None

    def worker_finished(self, result: object) -> None:
        callback = self.worker_done_callback
        if not callback:
            return
        try:
            callback(result)
        except Exception as exc:
            self.worker_failed(str(exc))

    def worker_failed_dispatch(self, message: str) -> None:
        callback = self.worker_failed_callback or self.worker_failed
        try:
            callback(message)
        except Exception as exc:
            self.worker_failed(str(exc))

    def worker_progress(self, message: str, percent: int) -> None:
        self.sync_status.setText(f"{message} {percent}%")
        self.show_progress(percent)

    def worker_failed(self, message: str) -> None:
        self.sync_status.setText("操作失敗")
        self.hide_progress()
        QMessageBox.warning(self, APP_NAME, message)

    def open_admin(self) -> None:
        password, ok = QInputDialog.getText(
            self,
            "管理者驗證",
            "請輸入管理者密碼",
            QLineEdit.Password,
        )
        if not ok:
            return
        if password != self.config.admin_password:
            QMessageBox.warning(self, APP_NAME, "管理者密碼錯誤。")
            return
        dialog = AdminDialog(self, self.config, self.config_store)
        dialog.index_updated.connect(self.load_local_index)
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

    def show_progress(self, percent: int) -> None:
        if not self.progress_bar:
            return
        self.progress_bar.setValue(max(0, min(100, percent)))
        self.progress_bar.show()

    def hide_progress(self) -> None:
        if not self.progress_bar:
            return
        self.progress_bar.hide()


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
    row = QFrame()
    row.setObjectName("MetaRow")
    layout = QHBoxLayout(row)
    layout.setContentsMargins(10, 7, 10, 7)
    layout.setSpacing(10)
    key_label = QLabel(key)
    key_label.setObjectName("MetaKey")
    key_label.setFixedWidth(76)
    key_label.setAlignment(Qt.AlignTop | Qt.AlignLeft)
    value_label = QLabel(soft_wrap_text(value))
    value_label.setObjectName("MetaValue")
    value_label.setWordWrap(True)
    value_label.setMinimumWidth(0)
    value_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
    value_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
    layout.addWidget(key_label)
    layout.addWidget(value_label, 1)
    return row


def soft_wrap_text(value: str) -> str:
    return value.replace("\\", "\\\u200b").replace("/", "/\u200b").replace("_", "_\u200b")


def labeled_input(layout: QVBoxLayout, label: str, value: str) -> QLineEdit:
    row = QHBoxLayout()
    row.addWidget(QLabel(label))
    field = QLineEdit(value)
    row.addWidget(field, 1)
    layout.addLayout(row)
    return field


def git_run(root: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    command = ["git", "-c", "core.quotepath=false", *args]
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    result = subprocess.run(
        command,
        cwd=str(root),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=300,
        creationflags=flags,
    )
    if result.returncode != 0:
        output = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(output or f"git {' '.join(args)} 執行失敗。")
    return result


def git_output(root: Path, args: list[str]) -> str:
    return git_run(root, args).stdout


def git_tool_update_paths(root: Path, status: str) -> list[str]:
    ignored_roots = {".git", ".github", "manager", "design", "dist", "build"}
    root_entries = {
        path.name
        for path in root.iterdir()
        if path.is_dir() and path.name not in ignored_roots
    }
    allowed_paths = {INDEX_FILE_NAME, *root_entries}
    result: list[str] = []
    for line in status.splitlines():
        path = git_status_path(line)
        if not path:
            continue
        top = path.split("/", 1)[0]
        if top in allowed_paths:
            result.append(path)
    return result


def git_status_path(line: str) -> str:
    path = line[3:].strip()
    if " -> " in path:
        path = path.rsplit(" -> ", 1)[1].strip()
    return path


def git_status_lines_for_paths(status: str, paths: list[str]) -> list[str]:
    allowed = set(paths)
    return [
        line
        for line in status.splitlines()
        if git_status_path(line) in allowed
    ]


def extract_update_zip(zip_path: Path, destination: Path) -> None:
    with zipfile.ZipFile(zip_path) as archive:
        for info in archive.infolist():
            target = destination / info.filename
            ensure_safe_child(destination, target)
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info) as source, target.open("wb") as output:
                shutil.copyfileobj(source, output)


def find_update_source_dir(extract_dir: Path) -> Path:
    matches = sorted(extract_dir.rglob("ToolkitManager.exe"), key=lambda path: len(path.parts))
    if not matches:
        raise RuntimeError("更新包內找不到 ToolkitManager.exe。")
    return matches[0].parent


def write_update_script(source_dir: Path, target_dir: Path) -> Path:
    updates_dir = app_data_dir() / "updates"
    updates_dir.mkdir(parents=True, exist_ok=True)
    script_path = updates_dir / "apply_toolkit_manager_update.bat"
    script = f"""@echo off
setlocal
chcp 65001 >nul
set "SOURCE={source_dir}"
set "TARGET={target_dir}"
set "CONFIG_BACKUP=%TEMP%\\ToolkitManager.config.backup.json"
timeout /t 2 /nobreak >nul
if exist "%TARGET%\\config.json" copy /Y "%TARGET%\\config.json" "%CONFIG_BACKUP%" >nul
xcopy "%SOURCE%\\*" "%TARGET%\\" /E /I /Y /Q >nul
if exist "%CONFIG_BACKUP%" copy /Y "%CONFIG_BACKUP%" "%TARGET%\\config.json" >nul
start "" "%TARGET%\\ToolkitManager.exe"
endlocal
"""
    script_path.write_text(script, encoding="utf-8")
    return script_path


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
