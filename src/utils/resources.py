"""
Resources utility for loading assets in the OnTime Meeting Timer application.
"""
import logging
import os
import sys
from pathlib import Path
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon, QPixmap
from PyQt6.QtWidgets import QApplication

logger = logging.getLogger("OnTime.Resources")


def get_resource_path(relative_path: str) -> Path:
    """
    Get absolute path to a resource, works for dev and for PyInstaller
    """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = Path(sys._MEIPASS)
    except AttributeError:
        # Running in normal Python environment
        if getattr(sys, 'frozen', False):
            # Running as bundled app
            base_path = Path(sys.executable).parent
        else:
            # Running in development environment
            base_path = Path(__file__).parent.parent.parent
    
    return base_path / relative_path


def get_icon(icon_name: str) -> QIcon:
    """
    Load an icon from the assets/icons directory
    
    Args:
        icon_name: Name of the icon file (with or without extension)
    
    Returns:
        QIcon object for the requested icon
    """
    # Add extension if not provided
    if not icon_name.endswith(('.png', '.ico', '.svg', '.jpg')):
        icon_name = f"{icon_name}.png"
    
    icon_path = get_resource_path(f"assets/icons/{icon_name}")
    
    if not icon_path.exists():
        print(f"Warning: Icon {icon_path} not found")
        return QIcon()
    
    return QIcon(str(icon_path))


def get_pixmap(icon_name: str) -> QPixmap:
    """
    Load a pixmap from the assets/icons directory
    
    Args:
        icon_name: Name of the icon file (with or without extension)
    
    Returns:
        QPixmap object for the requested icon
    """
    # Add extension if not provided
    if not icon_name.endswith(('.png', '.ico', '.svg', '.jpg')):
        icon_name = f"{icon_name}.svg"
    
    icon_path = get_resource_path(f"assets/icons/{icon_name}")
    
    if not icon_path.exists():
        print(f"Warning: Icon {icon_path} not found")
        return QPixmap()
    
    return QPixmap(str(icon_path))


def get_system_theme() -> str:
    """
    Detect the operating system's theme preference using Qt's QStyleHints.

    Returns:
        "dark" if the system is using dark mode, "light" otherwise
    """
    app = QApplication.instance()
    if app:
        hints = app.styleHints()
        if hints.colorScheme() == Qt.ColorScheme.Dark:
            return "dark"
    return "light"


def get_stylesheet(theme: str = "light") -> str:
    """
    Load a stylesheet from the assets/styles directory
    
    Args:
        theme: Name of the theme file (without extension)
    
    Returns:
        String containing the QSS stylesheet
    """
    # First load common styles
    common_style_path = get_resource_path("assets/styles/common.qss")
    theme_style_path = get_resource_path(f"assets/styles/{theme}.qss")
    
    style_content = ""
    
    # Load common styles if available
    if common_style_path.exists():
        with open(common_style_path, 'r') as f:
            style_content += f.read()
    
    # Load theme-specific styles if available
    if theme_style_path.exists():
        with open(theme_style_path, 'r') as f:
            style_content += f"\n" + f.read()
    else:
        logger.warning("Theme stylesheet not found: %s (theme=%r)", theme_style_path, theme)

    return style_content


def apply_stylesheet(app: QApplication, theme: str = "light"):
    """
    Apply a stylesheet to the QApplication
    
    Args:
        app: QApplication instance
        theme: Name of the theme file (without extension)
    """
    app.setStyleSheet(get_stylesheet(theme))