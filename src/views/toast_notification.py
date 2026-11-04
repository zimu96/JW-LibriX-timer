"""
In-app toast notification widget for displaying messages.
Supports localization via Qt's tr() system - pass translated strings when calling show_toast().
"""

import sys
from PyQt6.QtWidgets import (
    QWidget, QLabel, QHBoxLayout, QVBoxLayout,
    QGraphicsOpacityEffect, QPushButton
)
from PyQt6.QtCore import (
    Qt, QTimer, QPropertyAnimation, QEasingCurve,
    pyqtSignal, QPoint
)
from PyQt6.QtGui import QFont, QPainter, QColor, QPainterPath, QPixmap
from PyQt6.QtSvg import QSvgRenderer

from src.utils.resources import get_resource_path

# Margin from the edges of the parent window
_MARGIN = 16


class ToastNotification(QWidget):
    """A toast notification widget that appears at the bottom-right of the parent window."""

    closed = pyqtSignal()

    def __init__(self, parent=None, duration=5000):
        super().__init__(parent)
        self.duration = duration
        self._setup_ui()
        self._setup_animations()

        # Auto-hide timer
        self.hide_timer = QTimer(self)
        self.hide_timer.setSingleShot(True)
        self.hide_timer.timeout.connect(self.fade_out)

        # Start hidden
        self.hide()

    def _setup_ui(self):
        """Setup the toast UI."""
        flags = (Qt.WindowType.FramelessWindowHint
                 | Qt.WindowType.Tool
                 | Qt.WindowType.WindowStaysOnTopHint)
        # On Windows, bypass the window manager to avoid taskbar flicker
        if sys.platform == "win32":
            flags |= Qt.WindowType.WindowDoesNotAcceptFocus
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)

        # Main layout
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(12)

        # Icon label (renders SVG/PNG via QPixmap)
        self.icon_label = QLabel()
        self.icon_label.setFixedSize(28, 28)
        self.icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.icon_label)

        # Text container
        text_container = QVBoxLayout()
        text_container.setSpacing(2)

        # Title label
        self.title_label = QLabel()
        title_font = QFont()
        title_font.setBold(True)
        title_font.setPointSize(12)
        self.title_label.setFont(title_font)
        self.title_label.setWordWrap(True)
        text_container.addWidget(self.title_label)

        # Message label
        self.message_label = QLabel()
        message_font = QFont()
        message_font.setPointSize(11)
        self.message_label.setFont(message_font)
        self.message_label.setWordWrap(True)
        text_container.addWidget(self.message_label)

        layout.addLayout(text_container, 1)

        # Close button
        self.close_button = QPushButton("\u00d7")
        self.close_button.setFixedSize(24, 24)
        self.close_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.close_button.clicked.connect(self.fade_out)
        layout.addWidget(self.close_button, 0, Qt.AlignmentFlag.AlignTop)

        # Set minimum size
        self.setMinimumWidth(300)
        self.setMaximumWidth(450)

        # Apply default styling
        self._apply_styling()

    def _apply_styling(self):
        """Apply styling to the toast."""
        self.setStyleSheet("""
            ToastNotification {
                background-color: rgba(50, 50, 50, 240);
                border-radius: 8px;
                border: 1px solid rgba(255, 255, 255, 0.1);
            }
            QLabel {
                color: #ffffff;
                background: transparent;
            }
            QPushButton {
                background-color: transparent;
                color: rgba(255, 255, 255, 0.6);
                border: none;
                font-size: 18px;
                font-weight: bold;
            }
            QPushButton:hover {
                color: #ffffff;
            }
        """)

    def _setup_animations(self):
        """Setup fade animations."""
        self.opacity_effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.opacity_effect)
        self.opacity_effect.setOpacity(0)

        # Fade in animation
        self.fade_in_anim = QPropertyAnimation(self.opacity_effect, b"opacity")
        self.fade_in_anim.setDuration(200)
        self.fade_in_anim.setStartValue(0)
        self.fade_in_anim.setEndValue(1)
        self.fade_in_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        # Fade out animation
        self.fade_out_anim = QPropertyAnimation(self.opacity_effect, b"opacity")
        self.fade_out_anim.setDuration(300)
        self.fade_out_anim.setStartValue(1)
        self.fade_out_anim.setEndValue(0)
        self.fade_out_anim.setEasingCurve(QEasingCurve.Type.InCubic)
        self.fade_out_anim.finished.connect(self._on_fade_out_finished)

    def show_toast(self, title: str, message: str, icon: str = ""):
        """Show the toast with given title and message.

        Args:
            title: The toast title (should be pre-translated via tr())
            message: The toast message (should be pre-translated via tr())
            icon: Icon name (without extension) from assets/icons/,
                  e.g. "toast-adjust". Falls back to hiding the icon.
        """
        # Stop any existing animations/timers
        self.hide_timer.stop()
        self.fade_in_anim.stop()
        self.fade_out_anim.stop()

        # Set content
        self.title_label.setText(title)
        self.message_label.setText(message)
        self._set_icon(icon)

        # Adjust size
        self.adjustSize()

        # Position at bottom-right of parent
        self._position_toast()

        # Show and animate
        self.show()
        self.raise_()
        self.fade_in_anim.start()

        # Start auto-hide timer
        self.hide_timer.start(self.duration)

    def _set_icon(self, icon_name: str):
        """Load an SVG/PNG icon into the icon label."""
        if not icon_name:
            self.icon_label.setVisible(False)
            return

        pixmap = None
        icon_size = 28

        # Try SVG first (resolution-independent)
        svg_path = get_resource_path(f"assets/icons/{icon_name}.svg")
        if svg_path.exists():
            renderer = QSvgRenderer(str(svg_path))
            if renderer.isValid():
                pixmap = QPixmap(icon_size, icon_size)
                pixmap.fill(Qt.GlobalColor.transparent)
                painter = QPainter(pixmap)
                renderer.render(painter)
                painter.end()

        # Fallback to PNG
        if pixmap is None:
            png_path = get_resource_path(f"assets/icons/{icon_name}.png")
            if png_path.exists():
                pixmap = QPixmap(str(png_path)).scaled(
                    icon_size, icon_size,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation
                )

        if pixmap and not pixmap.isNull():
            self.icon_label.setPixmap(pixmap)
            self.icon_label.setVisible(True)
        else:
            self.icon_label.setVisible(False)

    def _position_toast(self):
        """Position the toast at the bottom-right of the parent window."""
        if not self.parent():
            return

        parent = self.parent()
        # Map the parent's bottom-right corner to global screen coordinates.
        # This is required because Tool windows use screen-level positioning.
        parent_bottom_right = parent.mapToGlobal(
            QPoint(parent.rect().width(), parent.rect().height())
        )

        x = parent_bottom_right.x() - self.width() - _MARGIN
        y = parent_bottom_right.y() - self.height() - _MARGIN

        self.move(x, y)

    def fade_out(self):
        """Start the fade out animation."""
        self.hide_timer.stop()
        self.fade_out_anim.start()

    def _on_fade_out_finished(self):
        """Handle fade out completion."""
        self.hide()
        self.closed.emit()

    def paintEvent(self, event):
        """Custom paint for rounded background."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Draw rounded rectangle background
        path = QPainterPath()
        path.addRoundedRect(0, 0, self.width(), self.height(), 8, 8)

        painter.fillPath(path, QColor(50, 50, 50, 240))
        painter.setPen(QColor(255, 255, 255, 25))
        painter.drawPath(path)


class ToastManager(QWidget):
    """Manages toast notifications for a parent window."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.toast = None
        self.setVisible(False)  # Manager widget is invisible

    def show_toast(self, title: str, message: str, icon: str = "", duration: int = 5000):
        """Show a toast notification.

        Args:
            title: The toast title (should be pre-translated via tr())
            message: The toast message (should be pre-translated via tr())
            icon: Icon name from assets/icons/ (e.g. "toast-adjust")
            duration: How long to show the toast (ms)
        """
        # Create toast if needed, or reuse existing
        if not self.toast:
            self.toast = ToastNotification(self.parent(), duration=duration)
        else:
            self.toast.duration = duration

        self.toast.show_toast(title, message, icon)

    def hide_toast(self):
        """Hide the current toast."""
        if self.toast:
            self.toast.fade_out()
