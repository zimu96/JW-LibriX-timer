"""
Settings dialog for the OnTime Meeting Timer application.
"""
import os
from datetime import time
import qrcode
from io import BytesIO
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTabWidget, QWidget,
    QLabel, QComboBox, QCheckBox, QTimeEdit, QPushButton,
    QGroupBox, QFormLayout, QSpinBox, QDialogButtonBox,
    QRadioButton, QButtonGroup, QLineEdit, QGridLayout
)
from PyQt6.QtCore import Qt, QTime
from PyQt6.QtGui import QPixmap, QImage

from src.config import AVAILABLE_LANGUAGES

from src.models.settings import NetworkDisplayMode
from src.utils.qr_code_utility import generate_qr_code

from src.utils.screen_handler import ScreenHandler
from src.controllers.settings_controller import SettingsController
from src.models.settings import DayOfWeek, TimerDisplayMode, MeetingSourceMode


class SettingsDialog(QDialog):
    """Settings dialog for the application"""
    
    def __init__(self, settings_controller: SettingsController, parent=None):
        super().__init__(parent)
        self.settings_controller = settings_controller
        
        # Available languages
        self.available_languages = AVAILABLE_LANGUAGES
        
        # Setup UI
        self._setup_ui()
        
        # Load current settings
        self._load_settings()
    
    def _nome_giorno(self, giorno) -> str:
        """Il giorno nella lingua del timer (che segue quella dell'app)."""
        from PyQt6.QtCore import QLocale
        lingua = self.settings_controller.get_settings().language or "it"
        return QLocale(lingua).dayName(giorno.value + 1).capitalize()

    def _setup_ui(self):
        """Setup the UI components"""
        self.setWindowTitle(self.tr("Settings"))
        self.setMinimumWidth(540)
        self.setMinimumHeight(600)
        
        layout = QVBoxLayout(self)
        
        # Create tab widget
        self.tab_widget = QTabWidget()
        
        # Create tabs
        self.general_tab = QWidget()
        self.meetings_tab = QWidget()
        self.display_tab = QWidget()
        self.meeting_source_tab = QWidget()  # New tab for meeting source options
        self.network_display_tab = QWidget()  # Setup network display tab
        self.data_management_tab = QWidget()  # Data cleanup settings tab

        self._setup_general_tab()
        self._setup_meetings_tab()
        self._setup_display_tab()
        self._setup_meeting_source_tab()  # Setup new tab
        self._setup_network_display_tab()  # Setup network display tab
        self._setup_data_management_tab()  # Setup data management tab

        # Add tabs to tab widget
        self.tab_widget.addTab(self.general_tab, self.tr("General"))
        self.tab_widget.addTab(self.meetings_tab, self.tr("Meetings"))
        self.tab_widget.addTab(self.display_tab, self.tr("Display"))
        self.tab_widget.addTab(self.meeting_source_tab, self.tr("Meeting Source"))
        self.tab_widget.addTab(self.network_display_tab, self.tr("Network Display"))
        self.tab_widget.addTab(self.data_management_tab, self.tr("Data Management"))

        # Make tab bar responsive: truncate labels before hiding tabs
        self.tab_widget.setElideMode(Qt.TextElideMode.ElideRight)
        self.tab_widget.tabBar().setExpanding(True)
        self.tab_widget.setUsesScrollButtons(True)

        # Add tab widget to layout
        layout.addWidget(self.tab_widget)
        
        # Add button box
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | 
            QDialogButtonBox.StandardButton.Cancel | 
            QDialogButtonBox.StandardButton.Apply |
            QDialogButtonBox.StandardButton.Reset
        )
        
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        button_box.button(QDialogButtonBox.StandardButton.Apply).clicked.connect(self._apply_settings)
        button_box.button(QDialogButtonBox.StandardButton.Reset).clicked.connect(self._reset_settings)
        
        layout.addWidget(button_box)
        
        # Enforce reasonable size
        self.resize(720, 720)
        self.setSizeGripEnabled(True)
    
    def _setup_general_tab(self):
        """Setup general settings tab"""
        layout = QVBoxLayout(self.general_tab)
        
        # Language selection
        language_group = QGroupBox(self.tr("Language"))
        language_layout = QFormLayout(language_group)
        
        self.language_combo = QComboBox()
        for lang_code, lang_name in self.available_languages.items():
            self.language_combo.addItem(lang_name, lang_code)

        language_layout.addRow(self.tr("Interface Language:"), self.language_combo)

        # Add groups to layout
        layout.addWidget(language_group)
        layout.addStretch()
    
    def _setup_meetings_tab(self):
        """Setup meetings settings tab"""
        layout = QVBoxLayout(self.meetings_tab)
        
        # Midweek meeting settings
        midweek_group = QGroupBox(self.tr("Midweek Meeting"))
        midweek_layout = QFormLayout(midweek_group)
        
        self.midweek_day_combo = QComboBox()
        for day in DayOfWeek:
            self.midweek_day_combo.addItem(self._nome_giorno(day), day.value)
        
        self.midweek_time_edit = QTimeEdit()
        self.midweek_time_edit.setDisplayFormat("HH:mm")

        # Target duration setting for midweek
        self.midweek_duration_spin = QSpinBox()
        self.midweek_duration_spin.setRange(60, 180)  # 1-3 hours
        self.midweek_duration_spin.setValue(105)  # Default
        self.midweek_duration_spin.setSuffix(" min")
        self.midweek_duration_spin.setToolTip(
            self.tr("Organizational standard for total meeting duration (e.g., 105 minutes)")
        )

        # Preview label showing calculated end time
        self.midweek_end_time_preview = QLabel()
        self.midweek_end_time_preview.setStyleSheet("color: gray; font-size: 10pt;")

        midweek_layout.addRow(self.tr("Day:"), self.midweek_day_combo)
        midweek_layout.addRow(self.tr("Time:"), self.midweek_time_edit)
        midweek_layout.addRow(self.tr("Target Duration:"), self.midweek_duration_spin)
        midweek_layout.addRow("", self.midweek_end_time_preview)

        # Connect signals to update preview when start time or duration changes
        self.midweek_time_edit.timeChanged.connect(self._update_midweek_end_time_preview)
        self.midweek_duration_spin.valueChanged.connect(self._update_midweek_end_time_preview)

        # Weekend meeting settings
        weekend_group = QGroupBox(self.tr("Weekend Meeting"))
        weekend_layout = QFormLayout(weekend_group)
        
        self.weekend_day_combo = QComboBox()
        for day in DayOfWeek:
            self.weekend_day_combo.addItem(self._nome_giorno(day), day.value)
        
        self.weekend_time_edit = QTimeEdit()
        self.weekend_time_edit.setDisplayFormat("HH:mm")

        # Target duration setting for weekend
        self.weekend_duration_spin = QSpinBox()
        self.weekend_duration_spin.setRange(60, 180)  # 1-3 hours
        self.weekend_duration_spin.setValue(105)  # Default
        self.weekend_duration_spin.setSuffix(" min")
        self.weekend_duration_spin.setToolTip(
            self.tr("Organizational standard for total meeting duration (e.g., 105 minutes)")
        )

        # Preview label showing calculated end time
        self.weekend_end_time_preview = QLabel()
        self.weekend_end_time_preview.setStyleSheet("color: gray; font-size: 10pt;")

        weekend_layout.addRow(self.tr("Day:"), self.weekend_day_combo)
        weekend_layout.addRow(self.tr("Time:"), self.weekend_time_edit)
        weekend_layout.addRow(self.tr("Target Duration:"), self.weekend_duration_spin)
        weekend_layout.addRow("", self.weekend_end_time_preview)

        # Connect signals to update preview when start time or duration changes
        self.weekend_time_edit.timeChanged.connect(self._update_weekend_end_time_preview)
        self.weekend_duration_spin.valueChanged.connect(self._update_weekend_end_time_preview)

        # Initialize notification reminder controls
        self.start_reminder_check = QCheckBox(self.tr("Remind to start timer after delay"))
        self.start_delay_spin = QSpinBox()
        self.start_delay_spin.setRange(1, 300)
        self.start_delay_spin.setSuffix(" s")
        self.start_delay_spin.setMaximumWidth(60)
        self.start_reminder_check.setToolTip(
            self.tr("When enabled, shows a reminder if you haven't started the timer after the specified delay.")
        )
        self.start_delay_spin.setToolTip(
            self.tr("Delay in seconds before reminding to start the timer.")
        )

        self.overrun_reminder_check = QCheckBox(self.tr("Remind on part overrun after delay"))
        self.overrun_delay_spin = QSpinBox()
        self.overrun_delay_spin.setRange(1, 300)
        self.overrun_delay_spin.setSuffix(" s")
        self.overrun_delay_spin.setMaximumWidth(60)
        self.overrun_reminder_check.setToolTip(
            self.tr("When enabled, shows a reminder if a meeting part exceeds its allocated time.")
        )
        self.overrun_delay_spin.setToolTip(
            self.tr("Delay in seconds before reminding to move to the next part.")
        )
        
        # Notification reminders settings
        notif_group = QGroupBox(self.tr("Notification Reminders"))
        notif_layout = QFormLayout(notif_group)
        #notif_group.setLayout(notif_layout)
        #notif_layout.setContentsMargins(10, 5, 10, 10)
        #notif_layout.setSpacing(8)
        notif_layout.addRow(self.start_reminder_check, self.start_delay_spin)
        notif_layout.addRow(self.overrun_reminder_check, self.overrun_delay_spin)
       
        
        
        # Add groups to layout
        layout.addWidget(midweek_group)
        layout.addWidget(weekend_group)
        layout.addWidget(notif_group)
        layout.addStretch()
        
       
    def _setup_display_tab(self):
        """Setup display settings tab"""
        layout = QVBoxLayout(self.display_tab)

        # Timer display mode
        display_mode_group = QGroupBox(self.tr("Timer Display"))
        display_mode_layout = QVBoxLayout(display_mode_group)
        # Digital is the only supported mode, so no need for a checkbox.

        # Theme selection
        theme_layout = QHBoxLayout()
        theme_layout.addWidget(QLabel(self.tr("Theme:")))

        self.theme_combo = QComboBox()
        self.theme_combo.addItem(self.tr("System (follow OS)"), "system")
        self.theme_combo.addItem(self.tr("Light Theme"), "light")
        self.theme_combo.addItem(self.tr("Dark Theme"), "dark")

        theme_layout.addWidget(self.theme_combo)
        display_mode_layout.addLayout(theme_layout)

        # Tools dock options
        tools_dock_group = QGroupBox(self.tr("Tools Dock"))
        tools_dock_layout = QVBoxLayout(tools_dock_group)

        self.remember_tools_dock_check = QCheckBox(self.tr("Remember tools dock state between sessions"))
        self.remember_tools_dock_check.setToolTip(self.tr("When enabled, the dock will be shown or hidden based on its state when you last closed the application"))
        tools_dock_layout.addWidget(self.remember_tools_dock_check)

        # Meeting timing options
        timing_group = QGroupBox(self.tr("Meeting Timing"))
        timing_layout = QVBoxLayout(timing_group)

        self.show_end_time_check = QCheckBox(self.tr("Show predicted meeting end time"))
        self.show_end_time_check.setToolTip(self.tr("Display the predicted meeting end time based on current progress"))
        timing_layout.addWidget(self.show_end_time_check)

        # Screen selection
        screen_group = QGroupBox(self.tr("Screen Selection"))
        screen_layout = QFormLayout(screen_group)

        # Get available screens
        self.available_screens = ScreenHandler.get_all_screens()

        # Primary screen selection
        self.primary_screen_combo = QComboBox()
        for screen in self.available_screens:
            primary_text = " (Primary)" if screen['primary'] else ""
            self.primary_screen_combo.addItem(
                f"{screen['name']} ({screen['width']}x{screen['height']}){primary_text}",
                screen['index']
            )

        # Secondary screen selection
        self.secondary_screen_combo = QComboBox()
        self.secondary_screen_combo.addItem("None", None)
        for screen in self.available_screens:
            self.secondary_screen_combo.addItem(
                f"{screen['name']} ({screen['width']}x{screen['height']})",
                screen['index']
            )

        # Connect signal to handle selection changes
        self.secondary_screen_combo.currentIndexChanged.connect(self._secondary_screen_selection_changed)

        self.use_secondary_check = QCheckBox(self.tr("Use Secondary Display"))
        self.use_secondary_check.toggled.connect(self._toggle_secondary_screen)

        screen_layout.addRow(self.tr("Primary Screen:"), self.primary_screen_combo)
        screen_layout.addRow(self.tr("Secondary Screen:"), self.secondary_screen_combo)
        screen_layout.addRow("", self.use_secondary_check)

        # Add groups to layout
        layout.addWidget(display_mode_group)
        layout.addWidget(tools_dock_group)
        layout.addWidget(timing_group)
        layout.addWidget(screen_group)
        layout.addStretch()
    
    def _populate_secondary_screen_combo(self):
        """Populate secondary screen combo box, excluding the primary screen"""
        self.secondary_screen_combo.clear()
        
        primary_index = self.primary_screen_combo.currentData()
        screens = ScreenHandler.get_all_screens()
        
        for screen in screens:
            if screen['index'] != primary_index:
                self.secondary_screen_combo.addItem(
                    f"{screen['name']} ({screen['width']}x{screen['height']})", 
                    screen['index']
                )
        
        # If no other screens available, add the primary as the only option
        if self.secondary_screen_combo.count() == 0:
            for screen in screens:
                if screen['index'] == primary_index:
                    self.secondary_screen_combo.addItem(
                        f"{screen['name']} ({screen['width']}x{screen['height']}) (Same as Primary)", 
                        screen['index']
                    )
    
    def _setup_meeting_source_tab(self):
        """Setup meeting source settings tab"""
        layout = QVBoxLayout(self.meeting_source_tab)
        
        # Meeting source mode
        source_mode_group = QGroupBox(self.tr("Meeting Data Source"))
        source_mode_layout = QVBoxLayout(source_mode_group)
        
        # Create radio buttons for each mode
        self.source_mode_radios = {}
        self.source_mode_group = QButtonGroup(self)
        
        for mode in MeetingSourceMode:
            radio = QRadioButton(self._get_source_mode_display_name(mode))
            self.source_mode_radios[mode] = radio
            self.source_mode_group.addButton(radio)
            source_mode_layout.addWidget(radio)
        
        # Web scraping options
        self.web_options_group = QGroupBox(self.tr("Web Scraping Options"))
        web_options_layout = QVBoxLayout(self.web_options_group)

        self.auto_update_check = QCheckBox(self.tr("Automatically update meetings from the web"))
        self.auto_update_check.setToolTip(self.tr("Update meetings from jw.org when the application starts"))

        self.save_scraped_check = QCheckBox(self.tr("Save scraped meetings as templates"))
        self.save_scraped_check.setToolTip(self.tr("Save scraped meeting data as templates for future use"))

        web_options_layout.addWidget(self.auto_update_check)
        web_options_layout.addWidget(self.save_scraped_check)
        
        # Song options
        self.song_options_group = QGroupBox(self.tr("Song Entry Options"))
        song_options_layout = QVBoxLayout(self.song_options_group)

        self.weekend_songs_manual_check = QCheckBox(self.tr("Always manually enter weekend songs"))
        self.weekend_songs_manual_check.setToolTip(self.tr("Weekend songs must be entered manually for each meeting"))

        song_options_layout.addWidget(self.weekend_songs_manual_check)
        
        # Connect source mode changes to toggle option groups
        for mode, radio in self.source_mode_radios.items():
            radio.toggled.connect(self._update_source_options_visibility)
        
        # Add groups to layout
        layout.addWidget(source_mode_group)
        layout.addWidget(self.web_options_group)
        layout.addWidget(self.song_options_group)
        layout.addStretch()
    
    def _get_source_mode_display_name(self, mode: MeetingSourceMode) -> str:
        """Get a user-friendly display name for source modes"""
        if mode == MeetingSourceMode.WEB_SCRAPING:
            return self.tr("Web Scraping (Automatically download from jw.org)")
        elif mode == MeetingSourceMode.MANUAL_ENTRY:
            return self.tr("Manual Entry (Enter meeting parts manually)")
        elif mode == MeetingSourceMode.TEMPLATE_BASED:
            return self.tr("Template-Based (Use templates with modifications)")
        return str(mode)
    
    def _update_source_options_visibility(self):
        """Update visibility of option groups based on selected source mode"""
        # Determine which mode is selected
        selected_mode = None
        for mode, radio in self.source_mode_radios.items():
            if radio.isChecked():
                selected_mode = mode
                break
        
        # Update visibility based on selected mode
        if selected_mode == MeetingSourceMode.WEB_SCRAPING:
            self.web_options_group.setVisible(True)
            self.auto_update_check.setEnabled(True)
            self.save_scraped_check.setEnabled(True)
        else:
            self.web_options_group.setVisible(False)
        
        # Song options are always visible, but context changes
        if selected_mode == MeetingSourceMode.WEB_SCRAPING:
            self.weekend_songs_manual_check.setText(self.tr("Always manually enter weekend songs"))
        else:
            self.weekend_songs_manual_check.setText(self.tr("Include song placeholders in templates"))

    def _secondary_screen_selection_changed(self, index):
        """Handle changes to the secondary screen selection"""
        if index < 0:  # Invalid index
            return
            
        selected_value = self.secondary_screen_combo.currentData()
        if selected_value is None or selected_value == "None":  # Check both None and "None"
            # If "None" is selected, automatically uncheck the use_secondary_check
            self.use_secondary_check.setChecked(False)
            # Also disable the checkbox to make it clear that it can't be enabled without a screen
            self.use_secondary_check.setEnabled(False)
        else:
            # Re-enable the checkbox if a valid screen is selected
            self.use_secondary_check.setEnabled(True)
    
    def _load_settings(self):
        """Load current settings into UI"""
        settings = self.settings_controller.get_settings()
        
        # General settings
        language_index = self.language_combo.findData(settings.language)
        if language_index >= 0:
            self.language_combo.setCurrentIndex(language_index)
        
        # Meeting settings
        self.midweek_day_combo.setCurrentIndex(settings.midweek_meeting.day.value)
        self.midweek_time_edit.setTime(QTime(
            settings.midweek_meeting.time.hour,
            settings.midweek_meeting.time.minute
        ))
        self.midweek_duration_spin.setValue(settings.midweek_meeting.target_duration_minutes)
        self._update_midweek_end_time_preview()  # Calculate initial preview

        self.weekend_day_combo.setCurrentIndex(settings.weekend_meeting.day.value)
        self.weekend_time_edit.setTime(QTime(
            settings.weekend_meeting.time.hour,
            settings.weekend_meeting.time.minute
        ))
        self.weekend_duration_spin.setValue(settings.weekend_meeting.target_duration_minutes)
        self._update_weekend_end_time_preview()  # Calculate initial preview

        # Notification reminder settings
        self.start_reminder_check.setChecked(settings.start_reminder_enabled)
        self.start_delay_spin.setValue(settings.start_reminder_delay)
        self.overrun_reminder_check.setChecked(settings.overrun_enabled)
        self.overrun_delay_spin.setValue(settings.overrun_delay)
        
        # Display settings
        # Digital is the only supported mode; nothing to update here.
        
        if hasattr(self, 'remember_tools_dock_check'):
            self.remember_tools_dock_check.setChecked(settings.display.remember_tools_dock_state)
        
        # Theme setting
        theme_index = self.theme_combo.findData(settings.display.theme)
        if theme_index >= 0:
            self.theme_combo.setCurrentIndex(theme_index)
        
        # Predicted end time
        self.show_end_time_check.setChecked(settings.display.show_predicted_end_time)
        
        # Screen settings
        primary_index = self.primary_screen_combo.findData(settings.display.primary_screen_index)
        if primary_index >= 0:
            self.primary_screen_combo.setCurrentIndex(primary_index)
        
        secondary_index = self.secondary_screen_combo.findData(settings.display.secondary_screen_index)
        if secondary_index >= 0:
            self.secondary_screen_combo.setCurrentIndex(secondary_index)
        else:
            # If secondary screen is not found (e.g., None), select "None"
            none_index = self.secondary_screen_combo.findData(None)
            if none_index >= 0:
                self.secondary_screen_combo.setCurrentIndex(none_index)
        
        # Ensure use_secondary_check is consistent with settings
        use_secondary = settings.display.use_secondary_screen
        secondary_screen = settings.display.secondary_screen_index
        
        # If secondary_screen is None, use_secondary should be False
        if secondary_screen is None:
            use_secondary = False
        
        self.use_secondary_check.setChecked(use_secondary)
        # Also set the enabled state based on whether a valid screen is selected
        self.use_secondary_check.setEnabled(secondary_screen is not None)        
        self._toggle_secondary_screen(settings.display.use_secondary_screen)
        # Do NOT call toggle_secondary_screen on the controller here; only update UI.
        
        # Meeting source settings
        source_mode = settings.meeting_source.mode
        if source_mode in self.source_mode_radios:
            self.source_mode_radios[source_mode].setChecked(True)
        
        self.auto_update_check.setChecked(settings.meeting_source.auto_update_meetings)
        self.save_scraped_check.setChecked(settings.meeting_source.save_scraped_as_template)
        self.weekend_songs_manual_check.setChecked(settings.meeting_source.weekend_songs_manual)
        
        # Update visibility based on current settings
        self._update_source_options_visibility()
        
        # Network display settings
        if hasattr(self, 'network_mode_radios'):
            network_mode = settings.network_display.mode
            if network_mode in self.network_mode_radios:
                self.network_mode_radios[network_mode].setChecked(True)
            
            self.http_port_spin.setValue(settings.network_display.http_port)
            self.ws_port_spin.setValue(settings.network_display.ws_port)
            self.auto_start_check.setChecked(settings.network_display.auto_start)
            self.qr_code_check.setChecked(settings.network_display.qr_code_enabled)

        # Update UI state based on current settings
        self._update_network_display_ui_state()
        self._update_qr_code_preview()

        # Data cleanup settings
        self.cleanup_enabled_check.setChecked(settings.data_cleanup.enabled)
        self.retention_days_spin.setValue(settings.data_cleanup.retention_days)
        self.retention_days_spin.setEnabled(settings.data_cleanup.enabled)
    
    def _apply_settings(self):
        """Apply settings changes"""
        # General settings
        language = self.language_combo.currentData()
        self.settings_controller.set_language(language)
        
        # Meeting settings
        midweek_day = DayOfWeek(self.midweek_day_combo.currentData())
        midweek_time_qtime = self.midweek_time_edit.time()
        midweek_time = time(midweek_time_qtime.hour(), midweek_time_qtime.minute())
        midweek_duration = self.midweek_duration_spin.value()

        self.settings_controller.set_midweek_meeting(midweek_day, midweek_time, midweek_duration)

        weekend_day = DayOfWeek(self.weekend_day_combo.currentData())
        weekend_time_qtime = self.weekend_time_edit.time()
        weekend_time = time(weekend_time_qtime.hour(), weekend_time_qtime.minute())
        weekend_duration = self.weekend_duration_spin.value()

        self.settings_controller.set_weekend_meeting(weekend_day, weekend_time, weekend_duration)
        
        # Notification reminder settings
        self.settings_controller.set_start_reminder_enabled(self.start_reminder_check.isChecked())
        self.settings_controller.set_start_reminder_delay(self.start_delay_spin.value())
        self.settings_controller.set_overrun_enabled(self.overrun_reminder_check.isChecked())
        self.settings_controller.set_overrun_delay(self.overrun_delay_spin.value())
        
        # Display settings
        if hasattr(self, 'remember_tools_dock_check'):
            self.settings_controller.update_tools_dock_state(self.remember_tools_dock_check.isChecked())
        
        # Theme setting
        theme = self.theme_combo.currentData()
        self.settings_controller.set_theme(theme)
        
        # Predicted end time
        self.settings_controller.set_show_predicted_end_time(self.show_end_time_check.isChecked())
        
        # Screen settings
        primary_screen = self.primary_screen_combo.currentData()
        self.settings_controller.set_primary_screen(primary_screen)

        secondary_screen = self.secondary_screen_combo.currentData()
        use_secondary = self.use_secondary_check.isChecked()

        # Make sure use_secondary is False if secondary_screen is None
        if secondary_screen is None:
            use_secondary = False
            self.settings_controller.set_force_secondary_cleanup(True)
        else:
            self.settings_controller.set_force_secondary_cleanup(False)

        # Set secondary screen first
        if secondary_screen is not None:
            self.settings_controller.set_secondary_screen(secondary_screen)

        # Then update use_secondary_screen
        self.settings_controller.toggle_secondary_screen(use_secondary)
        
        # Meeting source settings
        for mode, radio in self.source_mode_radios.items():
            if radio.isChecked():
                self.settings_controller.set_meeting_source_mode(mode)
                break
        
        self.settings_controller.set_auto_update_meetings(self.auto_update_check.isChecked())
        self.settings_controller.set_save_scraped_as_template(self.save_scraped_check.isChecked())
        self.settings_controller.set_weekend_songs_manual(self.weekend_songs_manual_check.isChecked())
        
        # Network display settings
        for mode, radio in self.network_mode_radios.items():
            if radio.isChecked():
                self.settings_controller.set_network_display_mode(mode)
                break

        self.settings_controller.set_network_display_ports(
            self.http_port_spin.value(),
            self.ws_port_spin.value()
        )

        self.settings_controller.set_network_display_options(
            self.auto_start_check.isChecked(),
            self.qr_code_check.isChecked()
        )

        # Data cleanup settings
        self.settings_controller.set_data_cleanup_enabled(self.cleanup_enabled_check.isChecked())
        self.settings_controller.set_data_cleanup_retention_days(self.retention_days_spin.value())

        # Save the updated settings so get_settings() returns latest values
        self.settings_controller.save_settings()
        # Emit the signal to notify changes have occurred
        self.settings_controller.settings_changed.emit()
        
        
    def _setup_data_management_tab(self):
        """Setup data management settings tab for automatic cleanup"""
        layout = QVBoxLayout(self.data_management_tab)

        # Auto-cleanup group
        cleanup_group = QGroupBox(self.tr("Automatic Data Cleanup"))
        cleanup_layout = QFormLayout(cleanup_group)

        self.cleanup_enabled_check = QCheckBox(self.tr("Enable automatic cleanup on startup"))
        self.cleanup_enabled_check.setToolTip(
            self.tr("Automatically remove old meeting files and cache data when the application starts")
        )
        cleanup_layout.addRow(self.cleanup_enabled_check)

        self.retention_days_spin = QSpinBox()
        self.retention_days_spin.setRange(7, 365)
        self.retention_days_spin.setSuffix(self.tr(" days"))
        self.retention_days_spin.setToolTip(
            self.tr("Files older than this many days will be removed")
        )
        cleanup_layout.addRow(self.tr("Retention period:"), self.retention_days_spin)

        # Toggle spin box enabled state based on checkbox
        self.cleanup_enabled_check.toggled.connect(self.retention_days_spin.setEnabled)

        # Informational label
        info_label = QLabel(self.tr(
            "Cleanup removes old meeting JSON files, EPUB downloads, "
            "and web scraper cache files. Currently loaded meetings "
            "are never removed."
        ))
        info_label.setWordWrap(True)
        info_label.setStyleSheet("color: gray; font-size: 9pt;")
        cleanup_layout.addRow(info_label)

        layout.addWidget(cleanup_group)
        layout.addStretch()

    def _setup_network_display_tab(self):
        """Setup network display tab in the settings dialog"""
        layout = QVBoxLayout(self.network_display_tab)

        # Network Display Mode group
        mode_group = QGroupBox(self.tr("Network Display Mode"))
        mode_layout = QVBoxLayout(mode_group)
        mode_layout.setSpacing(8)
        mode_layout.setContentsMargins(10, 10, 10, 10)

        # Create radio buttons for each mode
        self.network_mode_radios = {}
        self.network_mode_group = QButtonGroup(self)

        # Disabled mode
        self.disabled_radio = QRadioButton(self.tr("Disabled (No network display)"))
        self.network_mode_radios[NetworkDisplayMode.DISABLED] = self.disabled_radio
        self.network_mode_group.addButton(self.disabled_radio)
        mode_layout.addWidget(self.disabled_radio)
        self.disabled_radio.setToolTip(self.tr("No network display is provided."))

        # WebSocket only mode
        self.ws_only_radio = QRadioButton(self.tr("WebSocket Only (Use your own web page)"))
        self.network_mode_radios[NetworkDisplayMode.WEB_SOCKET_ONLY] = self.ws_only_radio
        self.network_mode_group.addButton(self.ws_only_radio)
        mode_layout.addWidget(self.ws_only_radio)
        self.ws_only_radio.setToolTip(self.tr("Broadcasts timer data over WebSocket only. Use this if you have your own HTML/JS client."))

        # HTTP and WebSocket mode
        self.http_ws_radio = QRadioButton(self.tr("HTTP and WebSocket (Complete solution)"))
        self.network_mode_radios[NetworkDisplayMode.HTTP_AND_WS] = self.http_ws_radio
        self.network_mode_group.addButton(self.http_ws_radio)
        mode_layout.addWidget(self.http_ws_radio)
        self.http_ws_radio.setToolTip(self.tr("Provides both a WebSocket server and an HTTP server to serve a built-in display page."))

        # Ports group
        ports_group = QGroupBox(self.tr("Network Ports"))
        ports_layout = QFormLayout(ports_group)
        ports_layout.setSpacing(8)
        ports_layout.setContentsMargins(10, 10, 10, 10)

        # HTTP port
        self.http_port_spin = QSpinBox()
        self.http_port_spin.setRange(1024, 65535)  # Common non-privileged port range
        self.http_port_spin.setValue(8080)
        self.http_port_spin.setToolTip(self.tr("Port for the HTTP server (client web page)"))
        ports_layout.addRow(self.tr("HTTP Port:"), self.http_port_spin)

        # WebSocket port
        self.ws_port_spin = QSpinBox()
        self.ws_port_spin.setRange(1024, 65535)
        self.ws_port_spin.setValue(8765)
        self.ws_port_spin.setToolTip(self.tr("Port for the WebSocket server (timer data)"))
        ports_layout.addRow(self.tr("WebSocket Port:"), self.ws_port_spin)

        # Options group
        options_group = QGroupBox(self.tr("Network Options"))
        options_layout = QVBoxLayout(options_group)
        options_layout.setSpacing(8)
        options_layout.setContentsMargins(10, 10, 10, 10)

        # Auto-start option
        self.auto_start_check = QCheckBox(self.tr("Auto-start network display when application launches"))
        self.auto_start_check.setToolTip(self.tr("Automatically start the network display when the application starts"))
        options_layout.addWidget(self.auto_start_check)

        # QR code option
        self.qr_code_check = QCheckBox(self.tr("Show QR code for easy connection"))
        self.qr_code_check.setToolTip(self.tr("Display a QR code in the main window for easy connection from mobile devices"))
        options_layout.addWidget(self.qr_code_check)

        # Help button for connection help
        help_button = QPushButton(self.tr("Connection Help"))
        help_button.setToolTip(self.tr("Click to view connection instructions for the network display"))
        help_button.clicked.connect(self._show_network_help_dialog)
        layout.addWidget(help_button, alignment=Qt.AlignmentFlag.AlignLeft)

        # QR code preview (will be populated when network display is active)
        self.qr_placeholder = QLabel(self.tr("QR Code will be shown here when network display is active"))
        self.qr_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.qr_placeholder.setMinimumHeight(150)

        # Add groups to layout
        layout.addWidget(mode_group)
        layout.addWidget(ports_group)
        layout.addWidget(options_group)
        layout.addWidget(self.qr_placeholder)
        layout.addStretch()

        # Connect signals to update UI state
        for mode, radio in self.network_mode_radios.items():
            radio.toggled.connect(self._update_network_display_ui_state)

    def _show_network_help_dialog(self):
        from PyQt6.QtWidgets import QMessageBox
        QMessageBox.information(
            self,
            self.tr("Network Display Help"),
            self.tr("To connect to the network display:\n\n"
                    "1. Make sure all devices are on the same network (LAN/WiFi)\n"
                    "2. Start the network display from the main window\n"
                    "3. On client devices, open a web browser and enter the URL shown\n"
                    "4. For easy connection from mobile devices, scan the QR code")
        )
    
    def _update_network_display_ui_state(self):
        """Update enabled state of network display UI elements based on selected mode"""
        # Determine which mode is selected
        selected_mode = None
        for mode, radio in self.network_mode_radios.items():
            if radio.isChecked():
                selected_mode = mode
                break
        
        # Enable/disable port settings based on mode
        enabled = (selected_mode != NetworkDisplayMode.DISABLED)
        self.ws_port_spin.setEnabled(enabled)
        
        # HTTP port only needed for HTTP_AND_WS mode
        self.http_port_spin.setEnabled(selected_mode == NetworkDisplayMode.HTTP_AND_WS)
        
        # Options are only relevant if network display is enabled
        self.auto_start_check.setEnabled(enabled)
        self.qr_code_check.setEnabled(enabled)
    
    def _reset_settings(self):
        """Reset settings to defaults"""
        self.settings_controller.reset_settings()
        self._load_settings()
    
    def _toggle_secondary_screen(self, enabled):
        """Toggle secondary screen combo box"""
        self.secondary_screen_combo.setEnabled(enabled)
    
    def _update_midweek_end_time_preview(self):
        """Update the preview label showing when midweek meeting will end"""
        from datetime import datetime, timedelta

        start_time = self.midweek_time_edit.time().toPyTime()
        duration_minutes = self.midweek_duration_spin.value()

        # Calculate end time
        start_datetime = datetime.combine(datetime.today(), start_time)
        end_datetime = start_datetime + timedelta(minutes=duration_minutes)
        end_time_str = end_datetime.strftime("%H:%M")

        self.midweek_end_time_preview.setText(f"→ {self.tr('Meeting will end at:')} {end_time_str}")

    def _update_weekend_end_time_preview(self):
        """Update the preview label showing when weekend meeting will end"""
        from datetime import datetime, timedelta

        start_time = self.weekend_time_edit.time().toPyTime()
        duration_minutes = self.weekend_duration_spin.value()

        # Calculate end time
        start_datetime = datetime.combine(datetime.today(), start_time)
        end_datetime = start_datetime + timedelta(minutes=duration_minutes)
        end_time_str = end_datetime.strftime("%H:%M")

        self.weekend_end_time_preview.setText(f"→ {self.tr('Meeting will end at:')} {end_time_str}")

    def accept(self):
        """Handle dialog acceptance"""
        self._apply_settings()
        super().accept()
    def _update_qr_code_preview(self):
        """Update QR code display in the settings dialog"""
        from src.utils.qr_code_utility import generate_qr_code
        from PyQt6.QtGui import QPixmap, QImage

        settings = self.settings_controller.get_settings()

        if (settings.network_display.qr_code_enabled and 
            settings.network_display.mode != NetworkDisplayMode.DISABLED):
            host = getattr(settings.network_display, "host", "localhost")
            url = f"http://{host}:{settings.network_display.http_port}"
            qr_image = generate_qr_code(url)
            pixmap = QPixmap.fromImage(QImage(qr_image))
            self.qr_placeholder.setPixmap(pixmap.scaled(150, 150, Qt.AspectRatioMode.KeepAspectRatio))
        else:
            self.qr_placeholder.setText(self.tr("QR Code will be shown here when network display is active"))