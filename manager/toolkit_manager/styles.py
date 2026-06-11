APP_QSS = """
* {
    font-family: "Microsoft JhengHei UI", "Segoe UI", sans-serif;
    font-size: 13px;
}

QMainWindow, QWidget {
    background: #f7f8fa;
    color: #1f2937;
}

QFrame#TopBar {
    background: #ffffff;
    border-bottom: 1px solid #e5e7eb;
}

QFrame#Sidebar {
    background: #ffffff;
    border-right: 1px solid #e5e7eb;
}

QPushButton {
    background: #ffffff;
    border: 1px solid #d7dce3;
    border-radius: 7px;
    padding: 7px 12px;
}

QPushButton:hover {
    background: #f1f5f9;
}

QPushButton#PrimaryButton {
    background: #1769e0;
    color: #ffffff;
    border-color: #1769e0;
    font-weight: 600;
}

QPushButton#PrimaryButton:hover {
    background: #0f5bc4;
}

QLineEdit, QComboBox {
    background: #ffffff;
    border: 1px solid #d7dce3;
    border-radius: 7px;
    padding: 8px 10px;
}

QListWidget {
    background: #ffffff;
    border: none;
    outline: none;
}

QListWidget::item {
    padding: 11px 12px;
    border-radius: 8px;
    margin: 2px 8px;
}

QListWidget::item:selected {
    background: #e8f1ff;
    color: #1769e0;
}

QScrollArea {
    border: none;
    background: transparent;
}

QFrame#ToolCard {
    background: #ffffff;
    border: 1px solid #e1e5ea;
    border-radius: 8px;
}

QFrame#ToolCard[selected="true"] {
    border: 2px solid #2f7df4;
}

QFrame#DetailsPanel {
    background: #ffffff;
    border-left: 1px solid #e5e7eb;
}

QLabel#Title {
    font-size: 22px;
    font-weight: 700;
}

QLabel#SectionTitle {
    font-size: 16px;
    font-weight: 700;
}

QLabel#ToolName {
    font-size: 15px;
    font-weight: 700;
}

QLabel#Category {
    color: #1769e0;
    font-weight: 600;
}

QLabel#Muted {
    color: #667085;
}

QLabel#StatusGreen {
    background: #dcfce7;
    color: #15803d;
    border-radius: 10px;
    padding: 4px 8px;
    font-weight: 600;
}

QLabel#StatusAmber {
    background: #ffedd5;
    color: #c2410c;
    border-radius: 10px;
    padding: 4px 8px;
    font-weight: 600;
}

QLabel#StatusGray {
    background: #eef2f7;
    color: #475467;
    border-radius: 10px;
    padding: 4px 8px;
    font-weight: 600;
}

QPlainTextEdit {
    background: #ffffff;
    border: 1px solid #d7dce3;
    border-radius: 7px;
    padding: 8px;
}
"""
