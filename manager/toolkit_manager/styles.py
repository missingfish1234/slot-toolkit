APP_QSS = """
* {
    font-family: "Microsoft JhengHei UI", "Segoe UI", sans-serif;
    font-size: 13px;
    letter-spacing: 0px;
}

QMainWindow {
    background: #0b0d0f;
    color: #eef5ee;
}

QWidget {
    background: #0b0d0f;
    color: #eef5ee;
}

QLabel {
    background: transparent;
}

QFrame#TopBar {
    background: #111417;
    border-bottom: 1px solid #2a3035;
}

QFrame#Sidebar {
    background: #101316;
    border-right: 1px solid #2a3035;
}

QFrame#DetailsPanel {
    background: #111417;
    border-left: 1px solid #2a3035;
}

QSplitter::handle {
    background: #20262b;
}

QPushButton {
    background: #171b1f;
    border: 1px solid #3a444a;
    border-radius: 7px;
    color: #e8f1e8;
    padding: 8px 13px;
    font-weight: 700;
}

QPushButton:hover {
    background: #20272b;
    border-color: #8ee600;
    color: #f5ffe8;
}

QPushButton:pressed {
    background: #11180f;
    border-color: #c6ff00;
}

QPushButton#PrimaryButton {
    background: #91e600;
    color: #11170d;
    border-color: #c8ff2a;
    font-weight: 900;
}

QPushButton#PrimaryButton:hover {
    background: #b8ff19;
    border-color: #e1ff75;
}

QPushButton#SecondaryButton {
    background: #161b1e;
    color: #dce8dc;
    border-color: #445057;
}

QPushButton#GhostButton {
    background: transparent;
    border-color: transparent;
    color: #aeb8ae;
}

QPushButton#GhostButton:hover {
    background: #182017;
    border-color: #52613d;
    color: #dfffad;
}

QLineEdit, QComboBox {
    background: #12171a;
    border: 1px solid #384249;
    border-radius: 8px;
    color: #eff7ef;
    padding: 9px 11px;
    selection-background-color: #77bb00;
    selection-color: #10140c;
}

QLineEdit:focus, QComboBox:focus {
    border: 1px solid #a8ff16;
}

QLineEdit::placeholder {
    color: #78837c;
}

QComboBox QAbstractItemView {
    background: #151a1d;
    color: #eef5ee;
    border: 1px solid #3a444a;
    selection-background-color: #26331c;
}

QComboBox::drop-down {
    width: 28px;
    border-left: 1px solid #2d353a;
}

QListWidget {
    background: transparent;
    border: none;
    outline: none;
}

QListWidget::item {
    padding: 12px 14px;
    border-radius: 7px;
    margin: 3px 10px;
    color: #c5d0c7;
    border: 1px solid transparent;
}

QListWidget::item:hover {
    background: #171d20;
    border-color: #39442e;
    color: #efffe0;
}

QListWidget::item:selected {
    background: #223315;
    border-color: #95e600;
    color: #dfff85;
    font-weight: 900;
}

QScrollArea {
    border: none;
    background: transparent;
}

QScrollBar:vertical {
    background: #101316;
    width: 12px;
    margin: 0px;
}

QScrollBar::handle:vertical {
    background: #3a454b;
    border-radius: 5px;
    min-height: 40px;
}

QScrollBar::handle:vertical:hover {
    background: #7fbf00;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}

QFrame#ToolCard {
    background: #14191c;
    border: 1px solid #303a40;
    border-radius: 9px;
}

QFrame#ToolCard:hover {
    background: #171e20;
    border-color: #7fbf00;
}

QFrame#ToolCard[selected="true"] {
    background: #182018;
    border: 2px solid #a8ff16;
}

QLabel#BrandMark {
    background: #91e600;
    color: #10140c;
    border-radius: 9px;
    font-size: 18px;
    font-weight: 900;
}

QLabel#Title {
    font-size: 22px;
    font-weight: 900;
    color: #f4fff0;
}

QLabel#AppSubtitle {
    color: #95a096;
    font-size: 12px;
}

QLabel#SectionTitle {
    font-size: 15px;
    font-weight: 900;
    color: #dfff85;
}

QLabel#ToolName {
    font-size: 15px;
    font-weight: 900;
    color: #f4fff0;
}

QLabel#Category {
    color: #a8ff16;
    font-weight: 800;
}

QLabel#Muted, QLabel#Meta {
    color: #9aa69d;
}

QLabel#CardDescription {
    color: #c7d3ca;
    line-height: 150%;
}

QLabel#ToolIcon {
    color: #f8fff3;
    border-radius: 9px;
    font-size: 21px;
    font-weight: 900;
    border: 1px solid #6a7a5a;
}

QLabel#StatusGreen {
    background: #203817;
    color: #b8ff19;
    border: 1px solid #7fbf00;
    border-radius: 11px;
    padding: 4px 9px;
    font-size: 12px;
    font-weight: 900;
}

QLabel#StatusAmber {
    background: #3a2d13;
    color: #ffd166;
    border: 1px solid #b88416;
    border-radius: 11px;
    padding: 4px 9px;
    font-size: 12px;
    font-weight: 900;
}

QLabel#StatusGray {
    background: #20262b;
    color: #c0c8c2;
    border: 1px solid #3e4a51;
    border-radius: 11px;
    padding: 4px 9px;
    font-size: 12px;
    font-weight: 900;
}

QPlainTextEdit {
    background: #12171a;
    color: #eef5ee;
    border: 1px solid #384249;
    border-radius: 8px;
    padding: 10px;
}
"""
