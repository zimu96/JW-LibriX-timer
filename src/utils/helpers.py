"""
Helper utilities for the OnTime Meeting Timer application.
"""
import os
import sys
import json
import logging
import platform
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Union
from pathlib import Path

# Set up logging
logger = logging.getLogger("OnTime")


def setup_logging(log_dir: Optional[Union[str, Path]] = None, level: int = logging.INFO) -> logging.Logger:
    """Set up application logging with file rotation and console output.

    Args:
        log_dir: Directory for log files. If None, file logging is skipped.
        level: Logging level (default: INFO).

    Returns:
        The configured 'OnTime' logger.
    """
    from logging.handlers import RotatingFileHandler

    # Avoid adding duplicate handlers on repeated calls
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_formatter = logging.Formatter(
        '%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        datefmt='%H:%M:%S'
    )
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    # File handler with rotation
    if log_dir:
        log_path = Path(log_dir)
        log_path.mkdir(parents=True, exist_ok=True)
        log_file = log_path / "ontime.log"

        file_handler = RotatingFileHandler(
            log_file,
            maxBytes=2 * 1024 * 1024,  # 2 MB per file
            backupCount=3,
            encoding='utf-8'
        )
        file_handler.setLevel(logging.DEBUG)
        file_formatter = logging.Formatter(
            '%(asctime)s [%(levelname)s] %(name)s (%(filename)s:%(lineno)d): %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)

    return logger


def setup_crash_handlers(log_dir: Optional[Union[str, Path]] = None):
    """Set up global crash handlers for uncaught exceptions and native crashes.

    Args:
        log_dir: Directory for crash dump files. If None, uses stderr only.
    """
    import faulthandler

    # Enable faulthandler for native crashes (segfaults, SIGABRT, etc.)
    if log_dir:
        crash_path = Path(log_dir)
        crash_path.mkdir(parents=True, exist_ok=True)
        crash_file = crash_path / "crash_dump.txt"
        # Kept open for process lifetime — faulthandler needs a live fd
        _crash_fd = open(crash_file, 'a')
        faulthandler.enable(file=_crash_fd)
    else:
        faulthandler.enable()

    # Route uncaught Python exceptions through the logger
    def _uncaught_exception_handler(exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return
        logger.critical(
            "Uncaught exception",
            exc_info=(exc_type, exc_value, exc_traceback)
        )

    sys.excepthook = _uncaught_exception_handler


def format_time(seconds: int) -> str:
    """Format seconds as mm:ss"""
    minutes = abs(seconds) // 60
    seconds = abs(seconds) % 60
    
    if seconds < 0:
        return f"-{minutes:02d}:{seconds:02d}"
    return f"{minutes:02d}:{seconds:02d}"


def format_time_with_hours(seconds: int) -> str:
    """Format seconds as hh:mm:ss"""
    hours = abs(seconds) // 3600
    minutes = (abs(seconds) % 3600) // 60
    seconds = abs(seconds) % 60
    
    if seconds < 0:
        return f"-{hours:02d}:{minutes:02d}:{seconds:02d}"
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def get_app_data_dir() -> Path:
    """Get application data directory based on platform"""
    from src.config import APP_NAME
    
    if sys.platform == 'win32':
        # Windows
        return Path(os.environ['APPDATA']) / APP_NAME
    elif sys.platform == 'darwin':
        # macOS
        return Path.home() / "Library" / "Application Support" / APP_NAME
    else:
        # Linux and other UNIX-like systems
        return Path.home() / f".{APP_NAME.lower().replace(' ', '_')}"


def safe_json_load(file_path: Union[str, Path], default=None) -> Dict:
    """Safely load JSON data from a file with error handling"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, IOError) as e:
        logger.error(f"Error loading JSON from {file_path}: {e}")
        return default or {}


def safe_json_save(data: Dict, file_path: Union[str, Path]) -> bool:
    """Safely save JSON data to a file with error handling"""
    try:
        # Create directory if it doesn't exist
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
        return True
    except (IOError, TypeError) as e:
        logger.error(f"Error saving JSON to {file_path}: {e}")
        return False


def get_system_info() -> Dict[str, str]:
    """Get system information for debugging purposes"""
    return {
        "platform": platform.platform(),
        "python_version": platform.python_version(),
        "system": platform.system(),
        "release": platform.release(),
        "architecture": " ".join(platform.architecture()),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "screens": _get_screens_info()
    }


def _get_screens_info() -> List[Dict]:
    """Get information about available screens"""
    try:
        from PyQt6.QtWidgets import QApplication
        
        # Create QApplication if it doesn't exist
        app = QApplication.instance()
        if not app:
            app = QApplication([])
        
        screens = []
        primary_screen = app.primaryScreen()
        for i, screen in enumerate(app.screens()):
            geometry = screen.geometry()
            screens.append({
                'index': i,
                'name': screen.name(),
                'width': geometry.width(),
                'height': geometry.height(),
                'primary': (screen == primary_screen)
            })
        
        return screens
    except Exception as e:
        logger.error(f"Error getting screen info: {e}")
        return []


def next_meeting_datetime(day_of_week: int, time_str: str) -> datetime:
    """Calculate next meeting datetime based on day of week and time"""
    today = datetime.now().date()
    today_weekday = today.weekday()
    
    # Calculate days until next meeting
    days_until = (day_of_week - today_weekday) % 7
    
    # If today is the meeting day and meeting time hasn't passed yet, days_until should be 0
    if days_until == 0:
        hour, minute = map(int, time_str.split(':'))
        meeting_time = datetime.now().replace(hour=hour, minute=minute, second=0, microsecond=0)
        
        if datetime.now() > meeting_time:
            # Meeting time has passed, go to next week
            days_until = 7
    
    # Calculate next meeting date
    next_date = today + timedelta(days=days_until)
    
    # Parse time
    hour, minute = map(int, time_str.split(':'))
    
    # Create datetime object
    return datetime.combine(next_date, datetime.min.time().replace(hour=hour, minute=minute))