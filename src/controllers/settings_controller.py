"""
Controller for managing application settings in the OnTime Meeting Timer application.
"""
from datetime import time
from typing import List, Dict
from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtGui import QScreen

from src.utils.screen_handler import ScreenHandler
from src.models.settings import (
    SettingsManager, AppSettings, MeetingSettings, 
    DisplaySettings, DayOfWeek, TimerDisplayMode, 
    MeetingSourceMode, MeetingSourceSettings
)
from src.models.settings import NetworkDisplayMode, NetworkDisplaySettings


class SettingsController(QObject):
    """Controller for managing application settings"""
    
    # Signals
    settings_changed = pyqtSignal()
    language_changed = pyqtSignal(str)
    display_mode_changed = pyqtSignal(TimerDisplayMode)
    theme_changed = pyqtSignal(str)
    meeting_source_mode_changed = pyqtSignal(MeetingSourceMode)
    primary_screen_changed = pyqtSignal(int)  # Emits the new primary screen index
    secondary_screen_changed = pyqtSignal(int, bool)  # Emits (screen_index, enabled)
    network_display_mode_changed = pyqtSignal(NetworkDisplayMode)
    network_display_ports_changed = pyqtSignal(int, int)  # HTTP port, WS port
    network_display_options_changed = pyqtSignal(bool, bool)  # Auto-start, QR code
    tools_dock_state_changed = pyqtSignal(bool)  # Tools dock visibility changed
    meeting_settings_changed = pyqtSignal()  # Midweek/weekend meeting times
    reminder_settings_changed = pyqtSignal()  # Notification reminder settings
    timing_settings_changed = pyqtSignal()  # Predicted end time, etc.
    general_settings_changed = pyqtSignal()  # Language, etc.
    co_visit_changed = pyqtSignal(bool)  # CO visit mode changed
    
    def __init__(self, settings_manager: SettingsManager):
        super().__init__()
        self.settings_manager = settings_manager
        
        self._updating_settings = False
        
        # Initialize correct screen indices if not already set
        self._initialize_screen_settings()
    
    def get_settings(self) -> AppSettings:
        """Get current settings"""
        return self.settings_manager.settings
    
    def save_settings(self):
        """Save current settings"""
        self.settings_manager.save_settings()
        if not self._updating_settings:
            self.settings_changed.emit()
    
    def reset_settings(self):
        """Reset settings to defaults"""
        self.settings_manager.reset_settings()
        self.settings_changed.emit()
    
    def set_language(self, language: str):
        """Set application language"""
        if language != self.settings_manager.settings.language:
            self.settings_manager.settings.language = language
            self.settings_manager.save_settings()
            self.language_changed.emit(language)
            self.general_settings_changed.emit()
    
    def set_midweek_meeting(self, day: DayOfWeek, meeting_time: time, target_duration_minutes: int = 105):
        """Set midweek meeting day, time, and target duration"""
        self.settings_manager.settings.midweek_meeting = MeetingSettings(
            day=day,
            time=meeting_time,
            target_duration_minutes=target_duration_minutes
        )
        self.settings_manager.save_settings()
        self.settings_changed.emit()  # Notify timer controller of changes
        self.meeting_settings_changed.emit()

    def set_weekend_meeting(self, day: DayOfWeek, meeting_time: time, target_duration_minutes: int = 105):
        """Set weekend meeting day, time, and target duration"""
        self.settings_manager.settings.weekend_meeting = MeetingSettings(
            day=day,
            time=meeting_time,
            target_duration_minutes=target_duration_minutes
        )
        self.settings_manager.save_settings()
        self.settings_changed.emit()  # Notify timer controller of changes
        self.meeting_settings_changed.emit()
    
    def set_display_mode(self, display_mode: TimerDisplayMode):
        """Set timer display mode"""
        self.settings_manager.settings.display.display_mode = display_mode
        self.settings_manager.save_settings()
        self.display_mode_changed.emit(display_mode)
        #self.settings_changed.emit()
    
    def set_theme(self, theme: str):
        """Set application theme (light, dark, or system)"""
        if theme not in ['light', 'dark', 'system']:
            theme = 'system'  # Default to system theme if invalid
            
        self.settings_manager.settings.display.theme = theme
        self.settings_manager.save_settings()
        self.theme_changed.emit(theme)
        self.settings_changed.emit()
    
    def set_show_predicted_end_time(self, enabled: bool):
        """Enable/disable predicted meeting end time"""
        self.settings_manager.settings.display.show_predicted_end_time = enabled
        self.settings_manager.save_settings()
        self.timing_settings_changed.emit()
    
    def set_primary_screen(self, screen_index: int):
        """Set primary screen index"""
        if screen_index != self.settings_manager.settings.display.primary_screen_index:
            # Check if this was previously the secondary screen
            if screen_index == self.settings_manager.settings.display.secondary_screen_index:
                # Swap screens
                old_primary = self.settings_manager.settings.display.primary_screen_index
                self.settings_manager.settings.display.secondary_screen_index = old_primary
            
            # Set new primary
            self.settings_manager.settings.display.primary_screen_index = screen_index
            self.settings_manager.save_settings()
            self.primary_screen_changed.emit(screen_index)
            #self.settings_changed.emit()
    
    def set_secondary_screen(self, screen_index: int):
        """Set secondary screen index"""
        if screen_index != self.settings_manager.settings.display.secondary_screen_index:
            # Check if this was previously the primary screen
            if screen_index == self.settings_manager.settings.display.primary_screen_index:
                # Swap screens
                old_secondary = self.settings_manager.settings.display.secondary_screen_index
                self.settings_manager.settings.display.primary_screen_index = old_secondary
            
            # Set new secondary
            self.settings_manager.settings.display.secondary_screen_index = screen_index
            
            # If enabling or changing secondary screen, make sure it's enabled
            self.settings_manager.settings.display.use_secondary_screen = True
            
            self.settings_manager.save_settings()
            self.secondary_screen_changed.emit(screen_index, True)
            #self.settings_changed.emit()
    
    def toggle_secondary_screen(self, enabled: bool):
        """Enable/disable secondary screen"""
        self.settings_manager.settings.display.use_secondary_screen = enabled
        self.settings_manager.save_settings()
        self.secondary_screen_changed.emit(
            self.settings_manager.settings.display.secondary_screen_index or 0, 
            enabled
        )
        #self.settings_changed.emit()

    # New methods for meeting source settings
    def set_meeting_source_mode(self, mode: MeetingSourceMode):
        """Set meeting source mode (web scraping, manual entry, template-based)"""
        if mode != self.settings_manager.settings.meeting_source.mode:
            self.settings_manager.settings.meeting_source.mode = mode
            self.settings_manager.save_settings()
            self.meeting_source_mode_changed.emit(mode)
            #self.settings_changed.emit()
    
    def set_auto_update_meetings(self, enabled: bool):
        """Enable/disable auto-update of meetings from web"""
        self.settings_manager.settings.meeting_source.auto_update_meetings = enabled
        self.settings_manager.save_settings()
        self.meeting_settings_changed.emit()
    
    def set_save_scraped_as_template(self, enabled: bool):
        """Enable/disable saving scraped meetings as templates"""
        self.settings_manager.settings.meeting_source.save_scraped_as_template = enabled
        self.settings_manager.save_settings()
        self.meeting_settings_changed.emit()

    def set_weekend_songs_manual(self, enabled: bool):
        """Enable/disable manual weekend song entry"""
        self.settings_manager.settings.meeting_source.weekend_songs_manual = enabled
        self.settings_manager.save_settings()
        self.meeting_settings_changed.emit()

    def set_start_reminder_enabled(self, enabled: bool):
        """Enable/disable start timer reminder"""
        self.settings_manager.settings.start_reminder_enabled = enabled
        self.settings_manager.save_settings()
        self.reminder_settings_changed.emit()

    def set_start_reminder_delay(self, delay: int):
        """Set delay (seconds) before start timer reminder"""
        self.settings_manager.settings.start_reminder_delay = delay
        self.settings_manager.save_settings()
        self.reminder_settings_changed.emit()

    def set_overrun_enabled(self, enabled: bool):
        """Enable/disable part overrun reminder"""
        self.settings_manager.settings.overrun_enabled = enabled
        self.settings_manager.save_settings()
        self.reminder_settings_changed.emit()

    def set_overrun_delay(self, delay: int):
        """Set delay (seconds) before part overrun reminder"""
        self.settings_manager.settings.overrun_delay = delay
        self.settings_manager.save_settings()
        self.reminder_settings_changed.emit()

    def get_all_screens(self):
        """Get information about all available screens"""
        return ScreenHandler.get_all_screens()
    
    def _initialize_screen_settings(self):
        """Initialize screen settings with correct values if not already set"""
        settings = self.settings_manager.settings
        screens = ScreenHandler.get_all_screens()
        
        # Set primary screen to system primary if not set
        if settings.display.primary_screen_index is None:
            settings.display.primary_screen_index = ScreenHandler.get_primary_screen_index()
        
        # Set secondary screen to first non-primary screen if not set
        if settings.display.secondary_screen_index is None:
            primary_index = settings.display.primary_screen_index
            # Look for a screen that's not the primary
            for screen in screens:
                if screen['index'] != primary_index:
                    settings.display.secondary_screen_index = screen['index']
                    break
            
            # If no secondary screen found, use same as primary (will be disabled)
            if settings.display.secondary_screen_index is None and screens:
                settings.display.secondary_screen_index = primary_index
                settings.display.use_secondary_screen = False
                
    def set_network_display_mode(self, mode: NetworkDisplayMode):
        """Set network display mode"""
        if mode != self.settings_manager.settings.network_display.mode:
            self.settings_manager.settings.network_display.mode = mode
            self.settings_manager.save_settings()
            self.network_display_mode_changed.emit(mode)
            #self.settings_changed.emit()

    def set_network_display_ports(self, http_port: int, ws_port: int):
        """Set network display ports"""
        settings = self.settings_manager.settings.network_display
        if http_port != settings.http_port or ws_port != settings.ws_port:
            settings.http_port = http_port
            settings.ws_port = ws_port
            self.settings_manager.save_settings()
            self.network_display_ports_changed.emit(http_port, ws_port)
            #self.settings_changed.emit()

    def set_network_display_options(self, auto_start: bool, qr_code_enabled: bool):
        """Set network display options"""
        settings = self.settings_manager.settings.network_display
        if auto_start != settings.auto_start or qr_code_enabled != settings.qr_code_enabled:
            settings.auto_start = auto_start
            settings.qr_code_enabled = qr_code_enabled
            self.settings_manager.save_settings()
            self.network_display_options_changed.emit(auto_start, qr_code_enabled)
            #self.settings_changed.emit()
        
        # Save updated settings
        self.settings_manager.save_settings()

    def update_secondary_screen_config(self, use_secondary: bool, screen_index: int = None):
        """Update and persist secondary screen configuration"""
        # Prevent recursion
        if self._updating_settings:
            return
            
        self._updating_settings = True
        try:
            settings = self.get_settings()
            changed = False

            if settings.display.use_secondary_screen != use_secondary:
                settings.display.use_secondary_screen = use_secondary
                changed = True

            if screen_index is not None and screen_index != settings.display.secondary_screen_index:
                settings.display.secondary_screen_index = screen_index
                changed = True

            if changed:
                self.settings_manager.save_settings() 
                self.secondary_screen_changed.emit(settings.display.secondary_screen_index, use_secondary)
        finally:
            self._updating_settings = False
            
    def update_tools_dock_state(self, visible: bool):
        """Update and persist the tools dock visibility if settings allow"""
        # Prevent recursion - this is the source of the infinite loop
        if self._updating_settings:
            return
            
        self._updating_settings = True
        try:
            settings = self.get_settings()
            if settings.display.remember_tools_dock_state:
                if settings.display.show_tools_dock != visible:
                    settings.display.show_tools_dock = visible
                    self.settings_manager.save_settings()  
                    self.tools_dock_state_changed.emit(visible)
        finally:
            self._updating_settings = False
    

    def set_force_secondary_cleanup(self, enabled: bool):
        """Enable/disable forced cleanup of secondary display on close"""
        self.settings_manager.settings.display.force_secondary_cleanup = enabled
        self.settings_manager.save_settings()
        #self.settings_changed.emit()

    def set_co_visit_enabled(self, enabled: bool):
        """Enable/disable CO visit mode for current week"""
        from datetime import datetime, timedelta
        settings = self.settings_manager.settings

        if enabled:
            today = datetime.now().date()
            week_start = today - timedelta(days=today.weekday())
            settings.co_visit.enabled = True
            settings.co_visit.week_start_date = week_start.isoformat()
        else:
            settings.co_visit.enabled = False
            settings.co_visit.week_start_date = None

        self.settings_manager.save_settings()
        self.co_visit_changed.emit(enabled)

    def is_co_visit_active(self) -> bool:
        """Check if CO visit mode is currently active"""
        return self.settings_manager.settings.co_visit.is_valid_for_current_week()

    def check_and_reset_co_visit(self):
        """Reset CO visit if week has expired"""
        settings = self.settings_manager.settings
        if settings.co_visit.enabled and not settings.co_visit.is_valid_for_current_week():
            settings.co_visit.enabled = False
            settings.co_visit.week_start_date = None
            self.settings_manager.save_settings()
            self.co_visit_changed.emit(False)

    # --- Data Cleanup Settings ---

    def set_data_cleanup_enabled(self, enabled: bool):
        """Enable/disable automatic data cleanup"""
        self.settings_manager.settings.data_cleanup.enabled = enabled
        self.settings_manager.save_settings()

    def set_data_cleanup_retention_days(self, days: int):
        """Set data retention period in days"""
        self.settings_manager.settings.data_cleanup.retention_days = max(7, min(365, days))
        self.settings_manager.save_settings()