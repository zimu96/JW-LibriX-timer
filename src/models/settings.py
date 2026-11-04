"""
Settings model for the OnTime Meeting Timer application.
"""
import json
import os
from dataclasses import dataclass, asdict, field
from datetime import time
from enum import Enum
from typing import Dict, Optional, List
from .timer import TimerDisplayMode


class DayOfWeek(Enum):
    """Days of the week"""
    MONDAY = 0
    TUESDAY = 1
    WEDNESDAY = 2
    THURSDAY = 3
    FRIDAY = 4
    SATURDAY = 5
    SUNDAY = 6


class MeetingSourceMode(Enum):
    """Meeting source modes"""
    WEB_SCRAPING = 0  # Automatically scrape from web
    MANUAL_ENTRY = 1  # Manually enter meeting parts
    TEMPLATE_BASED = 2  # Use templates with manual adjustments
    
class NetworkDisplayMode(Enum):
    """Modes for network display"""
    DISABLED = 0
    WEB_SOCKET_ONLY = 1
    HTTP_AND_WS = 2

@dataclass
class NetworkDisplaySettings:
    """Network display settings"""
    mode: NetworkDisplayMode = NetworkDisplayMode.DISABLED
    http_port: int = 8080
    ws_port: int = 8765
    auto_start: bool = False
    qr_code_enabled: bool = True  # Enable QR code for easy mobile connection


    def to_dict(self) -> dict:
        """Convert to dictionary for storage"""
        return {
            'mode': self.mode.value,
            'http_port': self.http_port,
            'ws_port': self.ws_port,
            'auto_start': self.auto_start,
            'qr_code_enabled': self.qr_code_enabled
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'NetworkDisplaySettings':
        """Create from dictionary"""
        return cls(
            mode=NetworkDisplayMode(data.get('mode', NetworkDisplayMode.DISABLED.value)),
            http_port=data.get('http_port', 8080),
            ws_port=data.get('ws_port', 8765),
            auto_start=data.get('auto_start', False),
            qr_code_enabled=data.get('qr_code_enabled', True)
        )


@dataclass
class COVisitSettings:
    """Settings for Circuit Overseer visit mode"""
    enabled: bool = False
    week_start_date: Optional[str] = None  # ISO format (Monday of week)

    def to_dict(self) -> dict:
        """Convert to dictionary for storage"""
        return {
            'enabled': self.enabled,
            'week_start_date': self.week_start_date
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'COVisitSettings':
        """Create from dictionary"""
        return cls(
            enabled=data.get('enabled', False),
            week_start_date=data.get('week_start_date')
        )

    def is_valid_for_current_week(self) -> bool:
        """Check if CO visit is still valid for current week"""
        if not self.enabled or not self.week_start_date:
            return False
        from datetime import datetime, timedelta
        try:
            stored_week_start = datetime.fromisoformat(self.week_start_date).date()
            today = datetime.now().date()
            current_week_start = today - timedelta(days=today.weekday())
            return stored_week_start == current_week_start
        except (ValueError, TypeError):
            return False


@dataclass
class DataCleanupSettings:
    """Settings for automatic data cleanup / garbage collection"""
    enabled: bool = True
    retention_days: int = 90  # Default 90 days

    def to_dict(self) -> dict:
        return {
            'enabled': self.enabled,
            'retention_days': self.retention_days
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'DataCleanupSettings':
        return cls(
            enabled=data.get('enabled', True),
            retention_days=data.get('retention_days', 90)
        )


@dataclass
class MeetingSettings:
    """Settings for a specific meeting type"""
    day: DayOfWeek = DayOfWeek.WEDNESDAY  # Default midweek meeting day
    time: time = field(default_factory=lambda: time(19, 0))  # Default 7:00 PM
    target_duration_minutes: int = 105  # Expected total meeting duration in minutes

    def to_dict(self) -> dict:
        """Convert to dictionary for storage"""
        return {
            'day': self.day.value,
            'time': self.time.isoformat(),
            'target_duration_minutes': self.target_duration_minutes
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'MeetingSettings':
        """Create from dictionary with backwards compatibility"""
        return cls(
            day=DayOfWeek(data['day']),
            time=time.fromisoformat(data['time']),
            target_duration_minutes=data.get('target_duration_minutes', 105)  # Default if missing
        )


@dataclass
class DisplaySettings:
    """Settings for timer display"""
    display_mode: TimerDisplayMode = TimerDisplayMode.DIGITAL
    primary_screen_index: int = 0
    primary_screen_name: str = ""
    secondary_screen_index: Optional[int] = None
    secondary_screen_name: str = ""
    use_secondary_screen: bool = False
    show_predicted_end_time: bool = True
    theme: str = "system"  # 'light', 'dark', or 'system' (follows OS theme)
    show_tools_dock: bool = False
    remember_tools_dock_state: bool = False  # Remember the state of the tools dock
    force_secondary_cleanup: bool = False  # Force cleanup of secondary screen on exit
    
    def to_dict(self) -> dict:
        """Convert to dictionary for storage"""
        return {
            'display_mode': self.display_mode.value,
            'primary_screen_index': self.primary_screen_index,
            'primary_screen_name': self.primary_screen_name,
            'secondary_screen_index': self.secondary_screen_index,
            'secondary_screen_name': self.secondary_screen_name,
            'use_secondary_screen': self.use_secondary_screen,
            'show_predicted_end_time': self.show_predicted_end_time,
            'theme': self.theme,
            'show_tools_dock': self.show_tools_dock,
            'remember_tools_dock_state': self.remember_tools_dock_state
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'DisplaySettings':
        """Create from dictionary"""
        use_secondary_screen = data.get('use_secondary_screen', False)
        return cls(
            display_mode=TimerDisplayMode(data.get('display_mode', TimerDisplayMode.DIGITAL.value)),
            primary_screen_index=data.get('primary_screen_index', 0),
            primary_screen_name=data.get('primary_screen_name', ""),
            secondary_screen_index=data.get('secondary_screen_index'),
            secondary_screen_name=data.get('secondary_screen_name', ""),
            use_secondary_screen=use_secondary_screen,
            show_predicted_end_time=data.get('show_predicted_end_time', True),
            theme=data.get('theme', 'system') if data.get('theme') in ('light', 'dark', 'system') else 'system',
            show_tools_dock=data.get('show_tools_dock', False),
            remember_tools_dock_state=data.get('remember_tools_dock_state', False)
        )


@dataclass
class MeetingSourceSettings:
    """Settings for meeting data sources"""
    mode: MeetingSourceMode = MeetingSourceMode.WEB_SCRAPING
    auto_update_meetings: bool = True
    save_scraped_as_template: bool = False  # Option to save scraped meetings as templates
    weekend_songs_manual: bool = True  # Always manually enter weekend songs
    
    def to_dict(self) -> dict:
        """Convert to dictionary for storage"""
        return {
            'mode': self.mode.value,
            'auto_update_meetings': self.auto_update_meetings,
            'save_scraped_as_template': self.save_scraped_as_template,
            'weekend_songs_manual': self.weekend_songs_manual
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'MeetingSourceSettings':
        """Create from dictionary"""
        return cls(
            mode=MeetingSourceMode(data.get('mode', MeetingSourceMode.WEB_SCRAPING.value)),
            auto_update_meetings=data.get('auto_update_meetings', True),
            save_scraped_as_template=data.get('save_scraped_as_template', False),
            weekend_songs_manual=data.get('weekend_songs_manual', True)
        )


@dataclass
class AppSettings:
    """Global application settings"""
    language: str = "en"
    midweek_meeting: MeetingSettings = field(default_factory=MeetingSettings)
    weekend_meeting: MeetingSettings = field(default_factory=lambda: MeetingSettings(
        day=DayOfWeek.SATURDAY,
        time=time(10, 0)  # Default 10:00 AM
    ))
    display: DisplaySettings = field(default_factory=DisplaySettings)
    meeting_source: MeetingSourceSettings = field(default_factory=MeetingSourceSettings)
    recent_meetings: List[str] = field(default_factory=list)  # List of meeting file paths
    network_display: NetworkDisplaySettings = field(default_factory=NetworkDisplaySettings)
    co_visit: COVisitSettings = field(default_factory=COVisitSettings)
    data_cleanup: DataCleanupSettings = field(default_factory=DataCleanupSettings)
    # Global notification reminder settings
    start_reminder_enabled: bool = True
    start_reminder_delay:   int  = 2  # seconds
    overrun_enabled:        bool = True
    overrun_delay:          int  = 20  # seconds

    # Bump this when settings structure changes so old files get migrated.
    SETTINGS_VERSION = 2

    def to_dict(self) -> dict:
        """Convert to dictionary for storage"""
        return {
            '_settings_version': self.SETTINGS_VERSION,
            'language': self.language,
            'midweek_meeting': self.midweek_meeting.to_dict(),
            'weekend_meeting': self.weekend_meeting.to_dict(),
            'display': self.display.to_dict(),
            'meeting_source': self.meeting_source.to_dict(),
            'recent_meetings': self.recent_meetings,
            'network_display': self.network_display.to_dict(),
            'co_visit': self.co_visit.to_dict(),
            'data_cleanup': self.data_cleanup.to_dict(),
            'start_reminder_enabled': self.start_reminder_enabled,
            'start_reminder_delay':   self.start_reminder_delay,
            'overrun_enabled':        self.overrun_enabled,
            'overrun_delay':          self.overrun_delay,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'AppSettings':
        """Create from dictionary"""
        return cls(
            language=data.get('language', 'en'),
            midweek_meeting=MeetingSettings.from_dict(data.get('midweek_meeting', {})),
            weekend_meeting=MeetingSettings.from_dict(data.get('weekend_meeting', {})),
            display=DisplaySettings.from_dict(data.get('display', {})),
            meeting_source=MeetingSourceSettings.from_dict(data.get('meeting_source', {})),
            recent_meetings=data.get('recent_meetings', []),
            network_display=NetworkDisplaySettings.from_dict(data.get('network_display', {})),
            co_visit=COVisitSettings.from_dict(data.get('co_visit', {})),
            data_cleanup=DataCleanupSettings.from_dict(data.get('data_cleanup', {})),
            start_reminder_enabled=data.get('start_reminder_enabled', True),
            start_reminder_delay=data.get('start_reminder_delay', 2),
            overrun_enabled=data.get('overrun_enabled', True),
            overrun_delay=data.get('overrun_delay', 20),
        )

class SettingsManager:
    """Manages loading and saving application settings"""

    def __init__(self, settings_file: str = "settings.json"):
        self.settings_file = settings_file
        self.settings = self._load_settings()

    def _load_settings(self) -> AppSettings:
        """Load settings from file or create default settings"""
        if os.path.exists(self.settings_file):
            try:
                with open(self.settings_file, 'r', encoding='utf-8') as f:
                    settings_dict = json.load(f)

                migrated = self._migrate(settings_dict)
                settings = AppSettings.from_dict(migrated)
                # Auto-save if migration changed the version (upgrades old files in place)
                if migrated.get('_settings_version') != settings_dict.get('_settings_version'):
                    with open(self.settings_file, 'w', encoding='utf-8') as fw:
                        json.dump(settings.to_dict(), fw, indent=2)
                return settings
            except (json.JSONDecodeError, KeyError, ValueError) as e:
                print(f"Error loading settings: {e}")
                return AppSettings()
        return AppSettings()

    @staticmethod
    def _migrate(data: dict) -> dict:
        """Apply sequential migrations to bring old settings up to date.

        Each migration handles one version bump.  When adding a new
        migration, bump ``AppSettings.SETTINGS_VERSION`` and add a new
        ``if version < N`` block at the end.
        """
        version = data.get('_settings_version', 1)

        if version < 2:
            # v1 → v2: validate theme value, add data_cleanup defaults
            display = data.get('display', {})
            if display.get('theme') not in ('light', 'dark', 'system'):
                display['theme'] = 'system'
            data['display'] = display
            data.setdefault('data_cleanup', {})
            version = 2

        # Future: if version < 3: ...

        data['_settings_version'] = version
        return data

    def save_settings(self):
        """Save current settings to file"""
        with open(self.settings_file, 'w', encoding='utf-8') as f:
            json.dump(self.settings.to_dict(), f, indent=2)

    def reset_settings(self):
        """Reset settings to defaults"""
        self.settings = AppSettings()
        self.save_settings()