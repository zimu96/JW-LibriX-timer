"""
Application configuration constants and settings for OnTime Meeting Timer
"""
import os
import sys
from pathlib import Path
from src import __version__ as APP_VERSION

# Application information
APP_NAME = "OnTime"
APP_AUTHOR = "Open Source"

# Determine if we're running in a bundled app (e.g., PyInstaller)
if getattr(sys, 'frozen', False):
    # Running as compiled executable
    APP_DIR = Path(sys.executable).parent
else:
    # Running in development environment
    APP_DIR = Path(__file__).parent.parent

# User data directory
# Dentro JW LibriX la cartella la decide l'app (variabile ONTIME_DATA_DIR):
# cosi' impostazioni e adunanze del timer stanno con i dati dell'app.
if os.environ.get("ONTIME_DATA_DIR"):
    USER_DATA_DIR = Path(os.environ["ONTIME_DATA_DIR"])
elif sys.platform == 'win32':
    # Windows
    USER_DATA_DIR = Path(os.environ['APPDATA']) / APP_NAME
elif sys.platform == 'darwin':
    # macOS
    USER_DATA_DIR = Path.home() / "Library" / "Application Support" / APP_NAME
else:
    # Linux and other UNIX-like systems
    USER_DATA_DIR = Path.home() / f".{APP_NAME.lower().replace(' ', '_')}"

# Ensure user data directory exists
USER_DATA_DIR.mkdir(parents=True, exist_ok=True)

# Paths
SETTINGS_FILE = USER_DATA_DIR / "settings.json"
MEETINGS_DIR = USER_DATA_DIR / "meetings"
MEETINGS_DIR.mkdir(exist_ok=True)

# Web Scraping
WOL_BASE_URL = "https://wol.jw.org"
MEETINGS_PATH = "/en/wol/meetings/r1/lp-e"
USER_AGENT = f"OntimeMeetingTimer/{APP_VERSION} (Python)"

# Available UI languages
AVAILABLE_LANGUAGES = {
    "en": "English",
    "it": "Italiano",
    "fr": "Français",
    "de": "Deutsch"
}

# Default settings
DEFAULT_LANGUAGE = "en"
DEFAULT_MIDWEEK_DAY = 2  # Wednesday
DEFAULT_WEEKEND_DAY = 5  # Saturday
DEFAULT_MIDWEEK_TIME = "19:00"  # 7:00 PM
DEFAULT_WEEKEND_TIME = "10:00"  # 10:00 AM

# Display settings
TIMER_FONT_SIZE = 120
PART_FONT_SIZE = 18
SECONDS_PER_MINUTE = 60