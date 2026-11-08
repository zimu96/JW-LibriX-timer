"""
Main application window for the OnTime meeting timer app.
"""

# -*- coding: utf-8 -*-

import os
import logging
from datetime import datetime, timedelta
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QComboBox, QTabWidget, QMessageBox, QDockWidget,
    QSplitter, QFrame, QToolBar, QStatusBar, QMenuBar,
    QApplication, QSizePolicy, QSystemTrayIcon, QGraphicsOpacityEffect
)
from PyQt6.QtGui import QIcon, QAction, QFont
from PyQt6.QtCore import Qt, QSize, pyqtSlot, QTimer, QEvent, QThread, pyqtSignal, QObject, QPropertyAnimation, QEasingCurve
from PyQt6.QtWidgets import QDialog

from src.utils.screen_handler import ScreenHandler
from src.controllers.meeting_controller import MeetingController
from src.controllers.timer_controller import TimerController
from src.controllers.settings_controller import SettingsController
from src.models.settings import SettingsManager, TimerDisplayMode, MeetingSourceMode
from src.models.meeting import Meeting, MeetingType
from src.models.timer import TimerState
from src.models.session import SessionState
from src.views.timer_view import TimerView
from src.views.meeting_view import MeetingView
from src.views.settings_view import SettingsDialog
from src.views.secondary_display import SecondaryDisplay
from src.views.weekend_song_editor import WeekendSongEditorDialog
from src.utils.network_display_manager import NetworkDisplayManager
from src.utils.network_broadcaster import NetworkBroadcaster
from src.views.network_status_widget import NetworkStatusWidget, NetworkInfoDialog
from src.views.toast_notification import ToastManager
from src.models.settings import NetworkDisplayMode
from src.utils.update_checker import check_for_updates

logger = logging.getLogger("OnTime.MainWindow")


class UpdateCheckWorker(QObject):
    """Worker class for running update checks in a separate thread"""
    finished = pyqtSignal()
    
    def __init__(self, silent=False):
        super().__init__()
        self.silent = silent
        self._last_network_url = None
    
    def run(self):
        """Run the update check"""
        try:
            # Get the main window reference
            from PyQt6.QtWidgets import QApplication
            main_window = QApplication.activeWindow()
            
            # Import the update checker
            from src.utils.update_checker import check_for_updates
            
            # Run check on this thread
            check_for_updates(main_window, self.silent)
        except Exception as e:
            logger.error("Error checking for updates: %s", e)
        finally:
            self.finished.emit()

class MainWindow(QMainWindow):
    """Main application window"""

    def __init__(self, meeting_controller: MeetingController, timer_controller: TimerController, settings_controller: SettingsController):
        super().__init__()
        
        # Cache the last network URL so late‑loaded widgets can sync
        self._last_network_url = None
        
        # Initialize controllers
        self.meeting_controller = meeting_controller
        self.settings_controller = settings_controller
        self.timer_controller = TimerController(settings_controller)
        
        # Create the component load manager
        from src.utils.lazy_loader import ComponentLoadManager
        self.component_loader = ComponentLoadManager(self)
        
        # Connect component loader signals
        self.component_loader.component_ready.connect(self._on_component_ready)
        self.component_loader.all_components_ready.connect(self._on_all_components_ready)
        
        # Create placeholders for lazy-loaded components
        self.meeting_view = None
        self.network_display_manager = None
        self.network_status_widget = None
        # Secondary display window placeholder
        self.secondary_display = None

        # Button debouncing to prevent rapid click crashes on Windows
        self._button_cooldown = False
        self._cooldown_timer = QTimer()
        self._cooldown_timer.setSingleShot(True)
        self._cooldown_timer.timeout.connect(self._reset_button_cooldown)

        # Setup UI
        self.setWindowTitle("OnTime Meeting Timer")
        self.setMinimumSize(400, 300)
        
        # Apply minimal styling immediately
        self._apply_minimal_styling()
        
        # Create tools dock first (before menu bar)
        self._create_empty_dock()
        
        # Show/hide the tools dock based on settings
        settings = self.settings_controller.get_settings()
        if settings.display.remember_tools_dock_state and settings.display.show_tools_dock:
            self.tools_dock.show()
        else:
            self.tools_dock.hide()
        
        # Now create other UI components
        self._create_menu_bar()
        self._create_tool_bar()
        # L'icona nell'area di notifica non sta piu' qui: la mostra la finestra
        # principale di JW LibriX, e solo quando la X la manda in secondo piano.
        # L'oggetto resta (show_attention_indicator lo usa) ma resta nascosto.
        from src.utils.resources import get_icon
        self.tray_icon = QSystemTrayIcon(self.windowIcon(), self)
        self.tray_icon.setToolTip("OnTime Meeting Timer")
        if self.tray_icon.icon().isNull():
            self.tray_icon.setIcon(get_icon("clock"))
        self.tray_icon.setVisible(False)
        self._create_central_widget()
        self._create_status_bar()

        # Initialize toast notification manager for in-app notifications
        self.toast_manager = ToastManager(self)
        
        # Connect signals
        self._connect_signals()

        # Check if CO visit has expired (new week started)
        self.settings_controller.check_and_reset_co_visit()

        # Initialize timer to show current time
        self._initialize_timer_display()
        
        # Start loading components in background
        QTimer.singleShot(100, self._start_component_loading)
        
        # Reminders to start/advance the meeting
        from src.controllers.reminder_controller import ReminderController
        self.reminder_controller = ReminderController(
            self.timer_controller, 
            self.settings_controller,
            self.meeting_controller,
            parent=self)
        
        # Connect reminder signals
        self.reminder_controller.remind_to_start.connect(self._nudge_start)
        self.reminder_controller.remind_to_advance.connect(self._nudge_advance)

    def _restore_window_size(self):
        self.setMinimumSize(400, 300)
        self.resize(600, 400)
        
    def _apply_minimal_styling(self):
        """Apply minimal styling for fast initial display"""
        theme = self.settings_controller.get_settings().display.theme
        if theme == "dark":
            self.setStyleSheet("""
                QMainWindow, QWidget {
                    background-color: #2d2d2d;
                    color: #f0f0f0;
                }
                QLabel {
                    color: #f0f0f0;
                }
                QPushButton {
                    background-color: #3d7ebd;
                    color: white;
                    border: 1px solid #2d6ebd;
                    padding: 5px;
                }
                QMessageBox QPushButton {
                    background-color: #3d7ebd;
                    color: white;
                    border: 1px solid #2d6ebd;
                    padding: 5px;
                    min-width: 80px;
                }
            """)
    
    def _create_empty_dock(self):
        """Create empty dock widgets for later population"""
        # Create tab widget for docked tools
        self.dock_tabs = QTabWidget()
        self.dock_tabs.setTabPosition(QTabWidget.TabPosition.North)
        
        # Create a placeholder widget
        placeholder = QWidget()
        placeholder_layout = QVBoxLayout(placeholder)
        loading_label = QLabel(self.tr("Loading components..."))
        placeholder_layout.addWidget(loading_label)
        
        # Add to dock tabs
        self.dock_tabs.addTab(placeholder, self.tr("Network"))

        # Wrap in tools dock
        self.tools_dock = QDockWidget(self.tr("Tools"), self)
        self.tools_dock.setWidget(self.dock_tabs)
        self.tools_dock.setMinimumSize(200, 200)
        self.tools_dock.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.tools_dock.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetClosable)
        self.tools_dock.setAllowedAreas(Qt.DockWidgetArea.RightDockWidgetArea | Qt.DockWidgetArea.LeftDockWidgetArea)
        
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.tools_dock)
        
        # Restore dock visibility state
        if self.settings_controller.get_settings().display.show_tools_dock:
            self.tools_dock.show()
        else:
            self.tools_dock.hide()
    
    def _start_component_loading(self):
        """Start loading components in background"""
        # Start with meeting_view as high priority
        self.component_loader.start_loading(priority_components=["meeting_view"])
        
        # Update status bar
        self.statusBar().showMessage(self.tr("Loading components..."), 5000)

    def _is_component_ready(self, component_name):
        """Check if a component is ready for use"""
        return hasattr(self, component_name) and getattr(self, component_name) is not None

    def _store_pending_action(self, component_name, method_name, *args, **kwargs):
        """Store a pending action to be executed when the component is ready"""
        if not hasattr(self, '_pending_actions'):
            self._pending_actions = {}
        
        if component_name not in self._pending_actions:
            self._pending_actions[component_name] = []
        
        self._pending_actions[component_name].append((method_name, args, kwargs))
        
        # If the component loader exists, try to prioritize loading this component
        if hasattr(self, 'component_loader') and self.component_loader:
            self.component_loader.start_loading(priority_components=[component_name])

    def _process_pending_actions(self, component_name, component):
        """Process any pending actions for a component that has just become available"""
        if not hasattr(self, '_pending_actions') or component_name not in self._pending_actions:
            return
        
        pending = self._pending_actions[component_name]
        for method_name, args, kwargs in pending:
            if hasattr(component, method_name):
                method = getattr(component, method_name)
                if callable(method):
                    method(*args, **kwargs)
        
        # Clear processed actions
        self._pending_actions[component_name] = []
        
    def _on_component_ready(self, name, component):
        """Handle a component being ready and process any pending actions"""
        # Store the component
        setattr(self, name, component)
        
        # Component-specific handling
        if name == "meeting_view":
            # Get the splitter from the central widget
            splitter = self.centralWidget().layout().itemAt(0).widget()

            # Get the second widget in the splitter (current placeholder)
            old_widget = splitter.widget(1)

            # Replace with the new meeting view
            splitter.replaceWidget(1, component)

            # Clean up the old widget
            if old_widget:
                old_widget.deleteLater()

            # Process any pending actions for this component
            self._process_pending_actions(name, component)

            # If we have a current meeting, update the view
            if self.meeting_controller.current_meeting:
                meeting = self.meeting_controller.current_meeting
                if meeting.meeting_type == MeetingType.WEEKEND:
                    meeting.title = self.tr("Public Talk and Watchtower Study")
                component.set_meeting(meeting)
                
        elif name == "network_display_manager":
            self.network_display_manager = component
            # Connect the network manager's signals
            self._connect_network_display_signals()

            # connect the network signals to the network status widget
            self._connect_network_signals()

            # If the dock panel already exists, give it the manager reference
            if self.network_status_widget:
                self.network_status_widget.set_network_manager(self.network_display_manager)
                # Force sync with current state
                self._sync_network_widget_state()

            # Process any pending actions for this component
            self._process_pending_actions(name, component)
            
        elif name == "network_widget":
            # Replace the placeholder in the dock tabs
            old_widget = self.dock_tabs.widget(0)
            self.dock_tabs.removeTab(0)
            self.dock_tabs.insertTab(0, component, "Network")
            self.network_status_widget = component  # keep a reference

            # Hand over the manager reference (if it's already loaded)
            if self.network_display_manager:
                self.network_status_widget.set_network_manager(self.network_display_manager)
                # Force sync with current state
                self._sync_network_widget_state()
            else:
                self.network_status_widget._display_stopped()

            # Sync widget with current broadcast state
            if self._last_network_url:
                self.network_status_widget._display_started(self._last_network_url)
            else:
                self.network_status_widget._display_stopped()

            # Clean up the old widget
            if old_widget:
                old_widget.deleteLater()

            # Process any pending actions for this component
            self._process_pending_actions(name, component)
            # Sync widget with current broadcast state
            if self.network_display_manager and self.network_display_manager.broadcaster:
                if self.network_display_manager.broadcaster.is_broadcasting:
                    url, _, _ = self.network_display_manager.get_connection_info()
                    if url:
                        self.network_status_widget._display_started(url)
                else:
                    self.network_status_widget._display_stopped()
            
    
    def _sync_network_widget_state(self):
        """Explicitly synchronize the network widget with the actual network display state"""
        if not self.network_status_widget or not self.network_display_manager:
            return
            
        # Check if the network display is actually running
        if (self.network_display_manager.broadcaster and 
            self.network_display_manager.broadcaster.is_broadcasting):
            # Get the current connection URL
            url, client_count, _ = self.network_display_manager.get_connection_info()
            if url:
                # Force update the widget to active state
                self.network_status_widget._display_started(url)
                # Update status with client count
                self.network_status_widget._status_updated(
                    f"Network display running at: {url}",
                    client_count
                )
            else:
                # Fallback to inactive if no URL
                self.network_status_widget._display_stopped()
        else:
            # Ensure widget shows inactive state
            self.network_status_widget._display_stopped()
            
        # Update the toggle button text
        if hasattr(self.network_status_widget, "toggle_button"):
            if (self.network_display_manager.broadcaster and 
                self.network_display_manager.broadcaster.is_broadcasting):
                self.network_status_widget.toggle_button.setText("Stop")
            else:
                self.network_status_widget.toggle_button.setText("Start")

    
    def _on_all_components_ready(self):
        """Handle all components being loaded"""
        # Update status bar
        self.statusBar().showMessage(self.tr("All components loaded"), 3000)

        # Auto-start network display if enabled
        if self.settings_controller.get_settings().network_display.auto_start:
            mode = self.settings_controller.get_settings().network_display.mode
            if mode != NetworkDisplayMode.DISABLED and self.network_display_manager:
                QTimer.singleShot(500, self._auto_start_network_display)

        # Check for session recovery (crash recovery)
        self.esegui_quando_visibile(self._check_session_recovery, 1000)

        # silently check for updates after a short delay
        QTimer.singleShot(3000, lambda: self._check_for_updates(silent=True))
    
    def _connect_network_display_signals(self):
        """Connect timer controller signals to network display manager after it's loaded"""
        if self.network_display_manager:
            
            
            # Make sure the timer_controller is directly accessible
            self.network_display_manager.timer_controller = self.timer_controller
            
            # Connect timer signals to network display manager
            self.timer_controller.timer.time_updated.connect(self.network_display_manager._on_time_updated)
            self.timer_controller.timer.state_changed.connect(self.network_display_manager._on_state_changed)
            self.timer_controller.part_changed.connect(self.network_display_manager._on_part_changed)
            self.timer_controller.predicted_end_time_updated.connect(self.network_display_manager._on_predicted_end_time_updated)
            self.timer_controller.meeting_overtime.connect(self.network_display_manager._on_meeting_overtime)
            
            # Connect current time updates - use specific format for current time
            # This connects directly to the broadcaster
            self.timer_controller.timer.current_time_updated.connect(
                self.network_display_manager._on_current_time_updated
            )
            
            
        else:
            logger.warning("Cannot connect network display manager signals - component not loaded yet")
    
    def _ensure_single_secondary_display(self):
        """Ensure only one secondary display exists with safe positioning"""
        settings = self.settings_controller.get_settings()
        
        # If secondary display should be disabled, clean up
        if not settings.display.use_secondary_screen:
            self._cleanup_secondary_display()
            return None
        
        # Create if it doesn't exist
        if not hasattr(self, 'secondary_display') or self.secondary_display is None:
            self.secondary_display = SecondaryDisplay(
                self.timer_controller, 
                self.settings_controller, 
                parent=self
            )
            
            # Connect countdown signal
            self.timer_controller.meeting_countdown_updated.connect(
                self.secondary_display._update_countdown
            )
            
            # Apply styling
            self._apply_secondary_display_theme()
            
            # Use the safe positioning method
            self.secondary_display.show_on_configured_screen_safely()
            
            # Start monitoring
            QTimer.singleShot(2000, self._start_screen_monitoring)
        else:
            # If it exists, just reposition safely
            self.secondary_display.show_on_configured_screen_safely()
        
        return self.secondary_display
    
    def _start_screen_monitoring(self):
        """Start monitoring secondary display placement"""
        if not hasattr(self, '_screen_monitor_timer'):
            
            self._screen_monitor_timer = QTimer()
            self._screen_monitor_timer.timeout.connect(self._verify_secondary_screen_placement)
            self._screen_monitor_timer.setSingleShot(False)
        
        # Monitor for 30 seconds
        self._screen_monitor_timer.start(2000)
        QTimer.singleShot(30000, self._stop_screen_monitoring)
        
    def _stop_screen_monitoring(self):
        """Stop screen monitoring"""
        if hasattr(self, '_screen_monitor_timer') and self._screen_monitor_timer:
            self._screen_monitor_timer.stop()
    
    def _verify_secondary_screen_placement(self):
        """Verify secondary display is on correct screen"""
        if not hasattr(self, 'secondary_display') or not self.secondary_display:
            self._stop_screen_monitoring()
            return
        
        from src.utils.screen_handler import ScreenHandler
        
        settings = self.settings_controller.get_settings()
        target_screen = ScreenHandler.get_configured_screen(settings, is_primary=False)
        
        if target_screen and not ScreenHandler.verify_screen_binding(self.secondary_display, target_screen):
            self._fix_secondary_screen_placement(target_screen)
    
    def _fix_secondary_screen_placement(self, target_screen):
        """Fix secondary display placement"""
        if not self.secondary_display or not target_screen:
            return

        # Use the safe positioning method
        self.secondary_display.show_on_configured_screen_safely()
    
    
    def _check_for_updates(self, silent=False):
        """Check for application updates"""     
        try:
            from src.utils.update_checker import check_for_updates
            
            # Store the thread reference so it doesn't get garbage collected
            self.update_thread = check_for_updates(self, silent)
            return self.update_thread
            
        except Exception as e:
            logger.error("Error in _check_for_updates: %s", e)
            import traceback
            traceback.print_exc()
            return None
        
    
    def _show_update_dialog(self, version_info):
        """Show the update dialog (called from the main thread)"""
        from src.utils.update_checker import UpdateDialog
        dialog = UpdateDialog(version_info, self)
        dialog.exec()

    def _show_no_update_message(self):
        """Show no update available message (thread-safe)"""
        QTimer.singleShot(0, lambda: QMessageBox.information(
            self,
            "No Updates Available",
            "You are using the latest version of OnTime Meeting Timer."
        ))

    def _show_update_error(self, error_message):
        """Show update error message (thread-safe)"""
        QTimer.singleShot(0, lambda: QMessageBox.warning(
            self,
            "Update Check Failed",
            f"Failed to check for updates:\n{error_message}"
        ))
    
    def _initialize_timer_display(self):
        """Initialize timer to show current time and meeting countdown"""
        # Update the meeting selector with available meetings
        self._update_meeting_selector()
        
        # Auto-select the appropriate meeting based on current day
        self._auto_select_current_meeting()
        
        # If we have a current meeting, initialize the countdown
        if self.meeting_controller.current_meeting:
            meeting = self.meeting_controller.current_meeting
            
            # Force refresh of the meeting view
            if self._is_component_ready('meeting_view'):
                self.meeting_view.set_meeting(meeting)
            else:
                self._store_pending_action('meeting_view', 'set_meeting', meeting)
            
            # Ensure the status bar shows the correct meeting
            if meeting.meeting_type == MeetingType.WEEKEND:
                self.current_meeting_label.setText(self.tr(f"Current Meeting: Public Talk and Watchtower Study ({meeting.date.strftime('%Y-%m-%d')})"))
            else:
                self.current_meeting_label.setText(self.tr(f"Current Meeting: {meeting.title}"))

            # Debug output
            #print(f"Selected meeting in _initialize_timer_display: {meeting.title}, Type: {meeting.meeting_type.value}")
            #print(f"Sections: {[s.title for s in meeting.sections]}")
    
    def _auto_select_current_meeting(self):
        """Automatically select the appropriate meeting based on the current day"""
        if not self.meeting_controller.current_meetings:
            return
        
        # Get current date and settings
        now = datetime.now()
        current_day = now.weekday()  # 0 = Monday, 6 = Sunday
        settings = self.settings_controller.get_settings()
        
        # Get configured days from settings
        midweek_day = (1 if self.settings_controller.is_co_visit_active()
                       else settings.midweek_meeting.day.value)  # martedi' con la visita
        weekend_day = settings.weekend_meeting.day.value  # Day of week (0-6)
        
        meeting_to_select = None
        selection_reason = ""
        
        # First check if today is either meeting day
        if current_day == midweek_day and MeetingType.MIDWEEK in self.meeting_controller.current_meetings:
            meeting_to_select = self.meeting_controller.current_meetings[MeetingType.MIDWEEK]
            selection_reason = f"Today is the midweek meeting day (day {current_day})"
        elif current_day == weekend_day and MeetingType.WEEKEND in self.meeting_controller.current_meetings:
            meeting_to_select = self.meeting_controller.current_meetings[MeetingType.WEEKEND]
            selection_reason = f"Today is the weekend meeting day (day {current_day})"
        else:
            # If today isn't a meeting day, find the next meeting day
            days_to_midweek = (midweek_day - current_day) % 7
            days_to_weekend = (weekend_day - current_day) % 7
            
            # Choose the closest upcoming meeting
            if days_to_midweek < days_to_weekend:
                if MeetingType.MIDWEEK in self.meeting_controller.current_meetings:
                    meeting_to_select = self.meeting_controller.current_meetings[MeetingType.MIDWEEK]
                    selection_reason = f"Midweek meeting is next (in {days_to_midweek} days)"
            else:
                if MeetingType.WEEKEND in self.meeting_controller.current_meetings:
                    meeting_to_select = self.meeting_controller.current_meetings[MeetingType.WEEKEND]
                    selection_reason = f"Weekend meeting is next (in {days_to_weekend} days)"
        
        # If we found a meeting to select, update the selector and set current meeting
        if meeting_to_select:
            
            
            # Find the meeting in the selector
            found_index = -1
            for i in range(self.meeting_selector.count()):
                meeting = self.meeting_selector.itemData(i)
                if meeting and meeting.meeting_type == meeting_to_select.meeting_type:
                    found_index = i
                    break
            
            if found_index >= 0:
                # Temporarily block signals to avoid recursive updates
                self.meeting_selector.blockSignals(True)
                self.meeting_selector.setCurrentIndex(found_index)
                self.meeting_selector.blockSignals(False)
                
                # Apply CO visit modifications if active
                if self.settings_controller.is_co_visit_active():
                    meeting_to_select = self.meeting_controller.apply_co_visit_modifications(meeting_to_select)

                # Update controllers and views
                self._set_current_meeting(meeting_to_select)
            else:
                print("Warning: Selected meeting not found in selector")
        else:
            print("No appropriate meeting found to auto-select")
            
    def _set_current_meeting(self, meeting):
        """Set the current meeting in all components safely"""
        if not meeting:
            return
        
        # Update the meeting controller
        self.meeting_controller.set_current_meeting(meeting)
        
        # Update the timer controller with the selected meeting
        
        # Update the meeting view
        if self._is_component_ready('meeting_view'):
            self.meeting_view.set_meeting(meeting)
        else:
            self._store_pending_action('meeting_view', 'set_meeting', meeting)
        
        # Update status bar
        if meeting.meeting_type == MeetingType.WEEKEND:
            self.current_meeting_label.setText(f"{self.tr('Current Meeting: Public Talk and Watchtower Study')} ({self.tr(meeting.date.strftime('%Y-%m-%d'))})")
        else:
            self.current_meeting_label.setText(f"{self.tr('Current Meeting:')} {self.tr(meeting.title)}")

        # Re‑enable countdown on the secondary display for the newly selected meeting
        if self.secondary_display:
            self.secondary_display.show_countdown = True
        # Initialize meeting countdown
        self.timer_controller._initialize_meeting_countdown()
        
        # Check for missing songs if this is a weekend meeting
        if meeting.meeting_type == MeetingType.WEEKEND:
            self._process_weekend_meeting_songs(meeting)
        #print(f"Current meeting set to: {meeting.title}, Type: {meeting.meeting_type.value}")
            
    def _update_countdown(self, seconds_remaining: int, message: str):
        """Update the countdown message with lazy-loaded components"""
        import traceback
        # Debug print to show the message received by MainWindow
        # Update status bar with countdown message
        if seconds_remaining > 0:
            # Show countdown in status bar
            if self.current_part_label.text() != message:
                self.current_part_label.setText(self.tr(message))

            # If the secondary display exists and is allowed to show the countdown, update it as well.
            secondary_display = self.secondary_display
            if secondary_display is not None:
                # Il monitor puo' essere gia' stato chiuso/distruttto (chiusura
                # dell'app, monitor spento): allora non c'e' piu' niente da
                # aggiornare, e non e' un errore da scrivere nel log.
                try:
                    from PyQt6 import sip
                    if sip.isdeleted(secondary_display) or sip.isdeleted(
                            getattr(secondary_display, "info_label1", None) or secondary_display):
                        self.secondary_display = None
                        secondary_display = None
                except Exception:
                    pass
            if secondary_display and getattr(secondary_display, "show_countdown", True):
                try:
                    if hasattr(secondary_display, "info_label1") and secondary_display.info_label1 is not None:
                        if secondary_display.info_label1.text() != message:
                            secondary_display.info_label1.setText(self.tr(message))
                        # Use only color/font-weight, let SecondaryDisplay handle font-size/layout
                        secondary_display.info_label1.setStyleSheet("color: #4a90e2; font-weight: bold;")
                        # Clear the second label during countdown
                        if hasattr(secondary_display, "info_label2"):
                            secondary_display.info_label2.setText("")
                        # Set flag to track that we're currently showing the countdown
                        secondary_display.show_countdown = True
                except RuntimeError as e:
                    if "has been deleted" in str(e):
                        self.secondary_display = None
                    else:
                        logger.error("Error updating secondary display: %s", e)
                except Exception as e:
                    logger.error("Unexpected error updating secondary display: %s", e)

            # Disable countdown updates on secondary display (old logic, not needed with centralized management)
            # if self._is_component_ready('secondary_display_handler'):
            #     sd = self.secondary_display_handler.get_display()
            #     if sd:
            #         sd.show_countdown = False

            # Update the status bar to show next part only
            if (
                hasattr(self, "timer_controller")
                and hasattr(self.timer_controller, "parts_list")
                and hasattr(self.timer_controller, "current_part_index")
            ):
                next_index = self.timer_controller.current_part_index + 1
                if next_index < len(self.timer_controller.parts_list):
                    next_part = self.timer_controller.parts_list[next_index]
                    label_text = self.tr("Next Part: %s") % next_part.title
                    self.current_part_label.setText(self.tr(label_text))
                elif self.timer_controller.current_part_index >= 0:
                    current_part = self.timer_controller.parts_list[self.timer_controller.current_part_index]
                    label_text = f"Current Part: {current_part.title}"  # tradotto da tr()
                    self.current_part_label.setText(self.tr(label_text))
                else:
                    label_text = "Meeting in progress"
                    self.current_part_label.setText(self.tr(label_text))

    def _update_meeting_selector(self):
        """Update the meeting selector dropdown with available meetings"""
        self.meeting_selector.clear()
        
        meetings = self.meeting_controller.current_meetings
        if not meetings:
            self.meeting_selector.addItem(self.tr("No meetings available"))
            return
        
        # Avoid duplicate entries for the same meeting type
        seen_meeting_types = set()
        for meeting_type, meeting in meetings.items():
            if meeting_type in seen_meeting_types:
                continue
            seen_meeting_types.add(meeting_type)
            date_str = meeting.date.strftime("%Y-%m-%d")
            if meeting_type == MeetingType.WEEKEND:
                display_title = f"{self.tr('Public Talk and Watchtower Study')} ({self.tr(date_str)})"
            else:
                display_title = f"{self.tr(meeting.title)} ({self.tr(date_str)})"
            self.meeting_selector.addItem(display_title, meeting)
        
        # Select the first item
        if self.meeting_selector.count() > 0:
            self.meeting_selector.setCurrentIndex(0)
        
    def _show_secondary_display(self):
        """Show secondary display safely"""
        secondary_display = self._ensure_single_secondary_display()
        if secondary_display:
            self.secondary_display_label.setText(self.tr("Secondary Display: Active"))
            self.toggle_secondary_action.setChecked(True)
        
    def _aggiorna_contenuti(self, meeting):
        """Dopo un cambio dei cantici il pannello Contenuti si rifa' da solo."""
        pannello = getattr(self, "contenuti", None)
        if pannello is not None:
            pannello.imposta_adunanza(meeting, mantieni=True)

    def esegui_quando_visibile(self, funzione, ritardo_ms: int = 0):
        """Esegue `funzione` solo quando il timer e' davvero davanti all'utente.

        Il timer si costruisce all'avvio dell'app (per il monitor), ma l'utente
        puo' essere in un'altra sezione: avvisi e domande non devono saltare
        fuori li'.  Se non e' visibile, si aspetta la prima volta che lo e'.
        """
        if self.isVisible():
            QTimer.singleShot(ritardo_ms, funzione)
        else:
            if not hasattr(self, "_in_attesa_di_vista"):
                self._in_attesa_di_vista = []
            self._in_attesa_di_vista.append((funzione, ritardo_ms))

    def showEvent(self, event):
        """Override show event to initialize screens when window is shown"""
        super().showEvent(event)
        in_attesa = getattr(self, "_in_attesa_di_vista", [])
        self._in_attesa_di_vista = []
        for funzione, ritardo in in_attesa:
            QTimer.singleShot(ritardo, funzione)
        
        # This is the right time to initialize screens, after the window is fully created
        # and about to become visible
        self._initialize_screens()
        
        # Auto-start network display if enabled in settings
        if self.settings_controller.get_settings().network_display.auto_start:
            mode = self.settings_controller.get_settings().network_display.mode
            if mode != NetworkDisplayMode.DISABLED:
                QTimer.singleShot(1000, self._auto_start_network_display)
        
        # check for updates after a short delay
        #QTimer.singleShot(3000, lambda: self._check_for_updates(False))
    
    def _create_menu_bar(self):
        """Create the application menu bar"""
        from src.utils.resources import get_icon
        
        menu_bar = self.menuBar()
        
        # File menu
        file_menu = menu_bar.addMenu(self.tr("&File"))

        # Create new meeting
        new_meeting_action = QAction(get_icon("clock"), self.tr("&New Meeting"), self)
        new_meeting_action.setShortcut("Ctrl+N")
        new_meeting_action.triggered.connect(self._create_new_meeting)
        file_menu.addAction(new_meeting_action)
        
        # Open meeting
        open_meeting_action = QAction(get_icon("clock"), self.tr("&Open Meeting"), self)
        open_meeting_action.setShortcut("Ctrl+O")
        open_meeting_action.triggered.connect(self._open_meeting)
        file_menu.addAction(open_meeting_action)
        
        # Edit current meeting
        edit_meeting_action = QAction(get_icon("edit"), self.tr("&Edit Current Meeting"), self)
        edit_meeting_action.setShortcut("Ctrl+E")
        edit_meeting_action.triggered.connect(self._edit_current_meeting)
        file_menu.addAction(edit_meeting_action)
        edit_songs_action = QAction(get_icon("music"), self.tr("Edit Weekend &Songs"), self)
        edit_songs_action.setShortcut("Ctrl+Shift+S")
        edit_songs_action.triggered.connect(self._edit_weekend_meeting_songs)
        file_menu.addAction(edit_songs_action)
        
        file_menu.addSeparator()
        
        # Update meetings from web
        update_meetings_action = QAction(get_icon("increase"), self.tr("&Update Meetings from Web"), self)
        update_meetings_action.setShortcut("F5")
        update_meetings_action.triggered.connect(self._update_meetings)
        file_menu.addAction(update_meetings_action)
        
        file_menu.addSeparator()
        
        # View menu
        view_menu = menu_bar.addMenu(self.tr("&View"))

        # Network display actions
        self.network_menu = view_menu.addMenu(self.tr("&Network Display"))

        # Toggle network dock widget
        toggle_network_dock_action = QAction(self.tr("Show Network Panel"), self)
        toggle_network_dock_action.setCheckable(True)
        toggle_network_dock_action.setChecked(self.tools_dock.isVisible())
        toggle_network_dock_action.triggered.connect(lambda checked: self.tools_dock.setVisible(checked))
        self.network_menu.addAction(toggle_network_dock_action)

        # Start/stop network display
        self.toggle_network_action = QAction(self.tr("Start Network Display"), self)
        self.toggle_network_action.triggered.connect(self._toggle_network_display)
        self.network_menu.addAction(self.toggle_network_action)

        # Show network info
        network_info_action = QAction(self.tr("Network Display Info..."), self)
        network_info_action.triggered.connect(self._show_network_info)
        self.network_menu.addAction(network_info_action)
        
        # Settings
        settings_action = QAction(get_icon("settings"), self.tr("&Settings"), self)
        settings_action.setShortcut("Ctrl+,")
        settings_action.triggered.connect(self._open_settings)
        file_menu.addAction(settings_action)
        
        file_menu.addSeparator()
        
        # Exit
        exit_action = QAction(self.tr("E&xit"), self)
        exit_action.setShortcut("Alt+F4")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        
        # Toggle secondary display
        self.toggle_secondary_action = QAction(self.tr("Toggle &Secondary Display"), self)
        self.toggle_secondary_action.setShortcut("F10")
        self.toggle_secondary_action.triggered.connect(self._toggle_secondary_display)
        self.toggle_secondary_action.setCheckable(True)
        self.toggle_secondary_action.setChecked(
            self.settings_controller.get_settings().display.use_secondary_screen
        )
        view_menu.addAction(self.toggle_secondary_action)
        
        # Switch display mode
        """ 
        switch_display_mode_action = QAction("Switch Display &Mode", self)
        switch_display_mode_action.setShortcut("F9")
        switch_display_mode_action.triggered.connect(self._toggle_display_mode)
        view_menu.addAction(switch_display_mode_action) 
        """
        
        # Switch theme
        self.theme_menu = view_menu.addMenu(self.tr("&Theme"))

        # System theme action (follow OS)
        self.system_theme_action = QAction(self.tr("&System (follow OS)"), self)
        self.system_theme_action.setCheckable(True)
        self.system_theme_action.triggered.connect(lambda: self._set_theme("system"))
        self.theme_menu.addAction(self.system_theme_action)

        # Light theme action
        self.light_theme_action = QAction(self.tr("&Light Theme"), self)
        self.light_theme_action.setCheckable(True)
        self.light_theme_action.triggered.connect(lambda: self._set_theme("light"))
        self.theme_menu.addAction(self.light_theme_action)

        # Dark theme action
        self.dark_theme_action = QAction(self.tr("&Dark Theme"), self)
        self.dark_theme_action.setCheckable(True)
        self.dark_theme_action.triggered.connect(lambda: self._set_theme("dark"))
        self.theme_menu.addAction(self.dark_theme_action)

        # Set initial theme selection
        current_theme = self.settings_controller.get_settings().display.theme
        self.system_theme_action.setChecked(current_theme == "system")
        self.light_theme_action.setChecked(current_theme == "light")
        self.dark_theme_action.setChecked(current_theme == "dark")

        # CO Visit toggle
        view_menu.addSeparator()
        self.co_visit_action = QAction(self.tr("CO Visit Mode"), self)
        self.co_visit_action.setCheckable(True)
        self.co_visit_action.setChecked(self.settings_controller.is_co_visit_active())
        self.co_visit_action.triggered.connect(self._toggle_co_visit)
        view_menu.addAction(self.co_visit_action)

        # Help menu
        help_menu = menu_bar.addMenu(self.tr("&Help"))

        # About
        about_action = QAction(self.tr("&About"), self)
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)
        
        help_menu.addSeparator()
        
        # Check for updates
        check_updates_action = QAction(self.tr("&Check for Updates"), self)
        check_updates_action.triggered.connect(lambda: self._check_for_updates(False))
        help_menu.addAction(check_updates_action)
    
    def _create_tool_bar(self):
        """Create the main toolbar"""
        from src.utils.resources import get_icon
        
        tool_bar = QToolBar("Main Toolbar")
        tool_bar.setIconSize(QSize(32, 32))
        tool_bar.setMovable(False)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, tool_bar)
        # Timer controls
        self.start_button = QPushButton(self.tr("Start Meeting"))
        self.start_button.setIcon(get_icon("play"))
        self.start_button.setIconSize(QSize(24, 24))
        self.start_button.setObjectName("startButton")
        self.start_button.clicked.connect(self._start_meeting)
        tool_bar.addWidget(self.start_button)

        self.pause_resume_button = QPushButton(self.tr("Pause"))
        self.pause_resume_button.setIcon(get_icon("pause"))
        self.pause_resume_button.setIconSize(QSize(24, 24))
        self.pause_resume_button.setObjectName("pauseButton")
        self.pause_resume_button.clicked.connect(self._toggle_pause_resume)
        self.pause_resume_button.setEnabled(False)
        tool_bar.addWidget(self.pause_resume_button)
        
        tool_bar.addSeparator()
        
        # Part navigation
        self.prev_button = QPushButton(self.tr("Previous"))
        self.prev_button.setIcon(get_icon("previous"))
        self.prev_button.setIconSize(QSize(24, 24))
        self.prev_button.clicked.connect(self._previous_part)
        self.prev_button.setEnabled(False)
        tool_bar.addWidget(self.prev_button)

        self.next_button = QPushButton(self.tr("Next"))
        self.next_button.setIcon(get_icon("next"))
        self.next_button.setIconSize(QSize(24, 24))
        self.next_button.clicked.connect(self._next_part)
        self.next_button.setEnabled(False)
        tool_bar.addWidget(self.next_button)
        
        tool_bar.addSeparator()
        
        # Time adjustment
        self.decrease_button = QPushButton(self.tr("-1 Minute"))
        self.decrease_button.setIcon(get_icon("decrease"))
        self.decrease_button.setIconSize(QSize(24, 24))
        self.decrease_button.clicked.connect(lambda: self._adjust_time(-1))
        self.decrease_button.setEnabled(False)
        tool_bar.addWidget(self.decrease_button)

        self.increase_button = QPushButton(self.tr("+1 Minute"))
        self.increase_button.setIcon(get_icon("increase"))
        self.increase_button.setIconSize(QSize(24, 24))
        self.increase_button.clicked.connect(lambda: self._adjust_time(1))
        self.increase_button.setEnabled(False)
        tool_bar.addWidget(self.increase_button)
        
        tool_bar.addSeparator()
        
        # Meeting selector
        self.meeting_selector = QComboBox()
        self.meeting_selector.currentIndexChanged.connect(self._meeting_selected)
        self.current_meeting_label = QLabel("No meeting selected")
        #tool_bar.addWidget("Current Meeting:")
        tool_bar.addWidget(self.meeting_selector)
        
        # Settings button
        settings_button = QPushButton(self.tr("Settings"))
        settings_button.setIcon(get_icon("settings"))
        settings_button.clicked.connect(self._open_settings)
        tool_bar.addWidget(settings_button)
        
    def _toggle_network_display(self):
        """Toggle network display on/off with lazy-loaded components"""
        if not self._is_component_ready('network_display_manager'):
            # Try to load the network manager component
            if hasattr(self, 'component_loader') and self.component_loader:
                # Load with blocking to ensure it's available
                self.component_loader.get_component('network_display_manager', blocking=True, timeout=5000)
            
            # Check again if it's available
            if not self._is_component_ready('network_display_manager'):
                self.statusBar().showMessage("Network display component not available", 3000)
                return
        
        # Now use the component
        if self.network_display_manager.broadcaster and self.network_display_manager.broadcaster.is_broadcasting:
            # Stop network display
            self.network_display_manager.stop_network_display()
            self.toggle_network_action.setText(self.tr("Start Network Display"))
        else:
            # Start network display with current settings
            mode = self.settings_controller.get_settings().network_display.mode
            http_port = self.settings_controller.get_settings().network_display.http_port
            ws_port = self.settings_controller.get_settings().network_display.ws_port

            # Show the tools dock if it's not visible
            if not self.tools_dock.isVisible():
                self.tools_dock.show()

            # Start network display
            if mode != NetworkDisplayMode.DISABLED:
                QTimer.singleShot(0, lambda: self.network_display_manager.start_network_display(mode, http_port, ws_port))
                self.toggle_network_action.setText(self.tr("Stop Network Display"))
            else:
                # Show message if network display is disabled in settings
                QTimer.singleShot(0, lambda: QMessageBox.information(
                    self,
                    self.tr("Network Display Disabled"),
                    self.tr("Network display is disabled in settings. Please enable it in Settings > Network Display.")
                ))
    
    def _show_network_info(self):
        """Show network display information dialog with lazy-loaded components"""
        if not self._is_component_ready('network_display_manager'):
            # Try to load the network manager
            if hasattr(self, 'component_loader') and self.component_loader:
                # Load with blocking to ensure it's available
                self.component_loader.get_component('network_display_manager', blocking=True, timeout=5000)
            
            # Check again if it's available
            if not self._is_component_ready('network_display_manager'):
                self.statusBar().showMessage(self.tr("Network display component not available"), 3000)
                return
        
        # Now use the component
        from src.views.network_status_widget import NetworkInfoDialog
        dialog = NetworkInfoDialog(self.network_display_manager, self)
        dialog.exec()
        
    def _auto_start_network_display(self):
        """Auto-start network display with lazy-loaded components"""
        if not self._is_component_ready('network_display_manager'):
            # Try to load the network manager
            if hasattr(self, 'component_loader') and self.component_loader:
                # Store this as a pending action rather than blocking
                self._store_pending_action('network_display_manager', '_auto_start_network_display_impl')
                return
        
        # If we have the component, call the implementation
        self._auto_start_network_display_impl()
        
    def _auto_start_network_display_impl(self):
        """Implementation of auto-start network display once component is available"""
        if not self._is_component_ready('network_display_manager'):
            return
            
        mode = self.settings_controller.get_settings().network_display.mode
        http_port = self.settings_controller.get_settings().network_display.http_port
        ws_port = self.settings_controller.get_settings().network_display.ws_port
        
        # Start network display if enabled
        if mode != NetworkDisplayMode.DISABLED:
            self.network_display_manager.start_network_display(mode, http_port, ws_port)
            self.toggle_network_action.setText(self.tr("Stop Network Display"))

            # Also sync the network widget if it exists
            if self._is_component_ready('network_status_widget'):
                QTimer.singleShot(500, self._sync_network_widget_state)
    
    def _create_central_widget(self):
        """Create the central widget with timer and a placeholder for meeting view"""
        from PyQt6.QtWidgets import QProgressBar
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Main layout
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(4)
        
        # Splitter for timer and parts
        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.setChildrenCollapsible(False)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        
        # Timer view - this is needed right away so create it directly
        self.timer_view = TimerView(self.timer_controller)
        self.timer_view.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        splitter.addWidget(self.timer_view)
        
        # Meeting view placeholder until the real one is loaded
        meeting_view_placeholder = QWidget()
        meeting_view_layout = QVBoxLayout(meeting_view_placeholder)
        
        # Create a placeholder message
        placeholder_label = QLabel(self.tr("Loading meeting information..."))
        placeholder_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        meeting_view_layout.addWidget(placeholder_label)
        
        # Add progress indicator
        progress = QProgressBar()
        progress.setRange(0, 0)  # Indeterminate progress
        meeting_view_layout.addWidget(progress)
        
        meeting_view_placeholder.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        splitter.addWidget(meeting_view_placeholder)
        
        # Set initial sizes
        splitter.setSizes([300, 400])
        
        main_layout.addWidget(splitter)
        
        # Store splitter reference to allow replacing widgets later
        self.main_splitter = splitter
    
    def _create_status_bar(self):
        """Create the status bar"""
        status_bar = QStatusBar()
        self.setStatusBar(status_bar)
        # Current part label
        self.current_part_label = QLabel(self.tr("No meeting selected"))
        self.current_part_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        status_bar.addWidget(self.current_part_label)
        
        # Spacer
        spacer = QWidget()
        spacer.setSizePolicy(
            QSizePolicy.Policy.Expanding, 
            QSizePolicy.Policy.Preferred
        )
        status_bar.addWidget(spacer)
        
        # Predicted end time label
        self.predicted_end_time_label = QLabel()
        self.predicted_end_time_label.setVisible(False)
        status_bar.addPermanentWidget(self.predicted_end_time_label)
        
        # Meeting overtime indicator
        self.meeting_overtime_label = QLabel()
        self.meeting_overtime_label.setVisible(False)
        status_bar.addPermanentWidget(self.meeting_overtime_label)
        
        # Display mode indicator
        """
        self.display_mode_label = QLabel()
        self._update_display_mode_label()
        status_bar.addPermanentWidget(self.display_mode_label)
        """
        
        # Secondary display indicator
        self.secondary_display_label = QLabel()
        self._update_secondary_display_label()
        status_bar.addPermanentWidget(self.secondary_display_label)
    
    def _connect_signals(self):
        """Connect controller signals to UI handlers"""
        # Meeting controller signals
        self.meeting_controller.meetings_loaded.connect(self._meetings_loaded)
        self.meeting_controller.meeting_updated.connect(self._meeting_updated)
        self.meeting_controller.error_occurred.connect(self._show_error)
        self.meeting_controller.part_updated.connect(self._part_updated)
        
        # Timer controller signals
        self.timer_controller.part_changed.connect(self._part_changed)
        self.timer_controller.meeting_started.connect(self._meeting_started)
        self.timer_controller.meeting_ended.connect(self._meeting_ended)
        self.timer_controller.transition_started.connect(self._transition_started)
        self.timer_controller.meeting_overtime.connect(self._meeting_overtime)
        self.timer_controller.predicted_end_time_updated.connect(self._update_predicted_end_time)
        self.timer_controller.meeting_countdown_updated.connect(self._update_countdown)
        self.timer_controller.durations_redistributed.connect(self._on_durations_redistributed)
        self.timer_controller.durations_reset.connect(self._on_durations_reset)

        # Settings controller signals

        self.settings_controller.language_changed.connect(self._on_language_changed) # Language change signal
        self.settings_controller.secondary_screen_changed.connect(self._on_secondary_screen_changed)
        self.settings_controller.tools_dock_state_changed.connect(self._on_tools_dock_state_changed)
        self.settings_controller.theme_changed.connect(self._theme_changed)
        self.settings_controller.meeting_settings_changed.connect(self._on_meeting_settings_changed)
        self.settings_controller.reminder_settings_changed.connect(self._on_reminder_settings_changed)
        self.settings_controller.co_visit_changed.connect(self._on_co_visit_changed)
        # General settings changed signal for all other settings
        self.settings_controller.settings_changed.connect(self._settings_changed)
        
    def _connect_network_signals(self):
        """Connect network display manager signals when component is available"""
        if not hasattr(self, 'network_display_manager') or not self.network_display_manager:
            return
            
        # Connect network display manager signals
        self.network_display_manager.display_started.connect(self._network_display_started)
        self.network_display_manager.display_stopped.connect(self._network_display_stopped)

    
    def _network_display_started(self, url):
        """Handle network display started"""
        self._last_network_url = url # Store the URL for later use
        # Update menu action text
        self.toggle_network_action.setText(self.tr("Stop Network Display"))

        # Update session state for crash recovery
        logger.info("Network display started with url: %s", url)
        has_timer = hasattr(self, 'timer_controller')
        has_session = has_timer and self.timer_controller.session_manager.has_active_session()
        logger.debug("has_timer_controller: %s, has_active_session: %s", has_timer, has_session)
        if has_timer and has_session:
            self.timer_controller.session_manager.set_network_broadcast_state(True)
            logger.debug("Set network_broadcast_active to True")

        # Update status bar
        self.statusBar().showMessage(self.tr(f"Network display started at {url}"), 5000)
        if hasattr(self, "network_status_widget") and self.network_status_widget:
            self.network_status_widget._display_started(url)
        
        # network_status_widget is not None
        if self.network_status_widget:
            self.network_status_widget._display_started(url)
            
        # Update the network widget if it exists
        if hasattr(self, "network_status_widget") and self.network_status_widget:
            self.network_status_widget._display_started(url)
            # Make sure the toggle button text is updated too
            if hasattr(self.network_status_widget, "toggle_button"):
                self.network_status_widget.toggle_button.setText("Stop")

    def _network_display_stopped(self):
        """Handle network display stopped"""
        self._last_network_url = None # Clear the URL
        # Update menu action text
        self.toggle_network_action.setText(self.tr("Start Network Display"))

        # Update session state for crash recovery
        if hasattr(self, 'timer_controller') and self.timer_controller.session_manager.has_active_session():
            self.timer_controller.session_manager.set_network_broadcast_state(False)

        # Update status bar
        self.statusBar().showMessage(self.tr("Network display stopped"), 5000)
        if hasattr(self, "network_status_widget") and self.network_status_widget:
            self.network_status_widget._display_stopped()
            # Make sure the toggle button text is updated too
            if hasattr(self.network_status_widget, "toggle_button"):
                self.network_status_widget.toggle_button.setText(self.tr("Start"))

    def _meetings_loaded(self, meetings):
        """Handle loaded meetings"""
        # Check for missing songs in weekend meeting
        if MeetingType.WEEKEND in meetings:
            
            weekend_meeting = meetings[MeetingType.WEEKEND]
            self._process_weekend_meeting_songs(weekend_meeting)

        # Update meeting selector
        self.meeting_selector.clear()
        
        if not meetings:
            self.meeting_selector.addItem(self.tr("No meetings available"))
            return
        
        for meeting_type, meeting in meetings.items():
            date_str = meeting.date.strftime("%Y-%m-%d")
            if meeting_type == MeetingType.WEEKEND:
                display_title = f"{self.tr('Public Talk and Watchtower Study')} ({date_str})"
            else:
                display_title = f"{meeting.title} ({date_str})"
            self.meeting_selector.addItem(display_title, meeting)
    
    def _meeting_selected(self, index):
        """Handle meeting selection from the dropdown"""
        if index < 0 or self.meeting_selector.count() == 0:
            return

        meeting = self.meeting_selector.itemData(index)
        if meeting:
            # Apply CO visit modifications if active
            if self.settings_controller.is_co_visit_active():
                meeting = self.meeting_controller.apply_co_visit_modifications(meeting)
            self._set_current_meeting(meeting)

    
    def _meeting_updated(self, meeting):
        """Handle meeting update with lazy-loaded components"""
        if self._is_component_ready('meeting_view'):
            self.meeting_view.set_meeting(meeting)
        else:
            self._store_pending_action('meeting_view', 'set_meeting', meeting)

    
    def _part_changed(self, part, index):
        """Handle part change with lazy-loaded components"""
        # Guard: Only update display if meeting is actually running
        if self.timer_controller.current_part_index < 0:
            # Meeting hasn't started yet, don't update the display
            return

        # Update status bar to show the next part instead of the current part
        parts = self.timer_controller.parts_list
        if index + 1 < len(parts):
            next_part = parts[index + 1]
            self.current_part_label.setText(self.tr(f"Next Part: {next_part.title}"))
        else:
            self.current_part_label.setText(self.tr("Last Part"))

        # Highlight the current part in the meeting view
        if self._is_component_ready('meeting_view'):
            self.meeting_view.highlight_part(index)
        else:
            self._store_pending_action('meeting_view', 'highlight_part', index)

        # Display part information in the central widget
        self.timer_view.part_label.setText(self.tr(f"Current Part: {part.title}"))
        
        # Show next part in bottom label (formerly countdown)
        if index + 1 < len(self.timer_controller.parts_list):
            next_part = self.timer_controller.parts_list[index + 1]
            self.timer_view.countdown_label.setText(self.tr("Next Part: %s") % next_part.title)
        else:
            self.timer_view.countdown_label.setText(self.tr("Meeting End"))
            self.timer_view.countdown_label.setVisible(True)

        # Update secondary display if available
        if self.secondary_display:
            if index + 1 < len(parts):
                next_part = parts[index + 1]
                self.secondary_display.info_label1.setText(self.tr(f"Next Part: {next_part.title}"))
                # Use only color/font-weight, let SecondaryDisplay handle font-size/layout
                self.secondary_display.info_label1.setStyleSheet("color: #ffffff; font-weight: bold;")
            else:
                self.secondary_display.info_label1.setText(self.tr("Last Part"))
                self.secondary_display.info_label1.setStyleSheet("color: #ffffff; font-weight: bold;")

    def _part_updated(self, part, section_index, part_index):
        """Handle a part being updated"""
        global_index = self._get_global_part_index(section_index, part_index)

        # Replace the part in the timer's active list
        if 0 <= global_index < len(self.timer_controller.parts_list):
            self.timer_controller.parts_list[global_index] = part

            # If this is the current part and the timer is running, update its duration
            if global_index == self.timer_controller.current_part_index:
                self.timer_controller.apply_current_part_update()

        # Emit part_changed to refresh display
        self.timer_controller.part_changed.emit(part, global_index)
    
    def _meeting_started(self):
        """Handle meeting start event in the main window"""
        from src.utils.resources import get_icon

        self.start_button.setText(self.tr("Stop Meeting"))
        self.start_button.setIcon(get_icon("stop"))
        self.start_button.setObjectName("stopButton")  # Change style
        self.start_button.setStyleSheet("")  # Force style refresh
        self.start_button.clicked.disconnect()
        self.start_button.clicked.connect(self._stop_meeting)

        # Enable controls
        self.pause_resume_button.setEnabled(True)
        self.prev_button.setEnabled(True)
        self.next_button.setEnabled(True)
        self.decrease_button.setEnabled(True)
        self.increase_button.setEnabled(True)

        # Disable meeting selector and apply blur
        # Resta visibile ma non cliccabile (senza sfocatura: con il tema scuro
        # l'effetto lo faceva sparire e lasciava un buco nella barra)
        self.meeting_selector.setEnabled(False)

        # Clear any leftover countdown or status text in the status bar
        self.current_part_label.setText("")

        # stop start reminder animation
        if hasattr(self, 'start_button') and hasattr(self.start_button, '_pulse_animations'):
            for anim in list(self.start_button._pulse_animations):  # Copy list to avoid modification during iteration
                if anim is not None:
                    anim.stop()
            self.start_button._pulse_animations.clear()
            effect = self.start_button.graphicsEffect()
            if effect is not None:
                effect.setOpacity(1.0)

        # If secondary display exists, update it to show meeting info
        self.timer_view.show_clock = False
        self.timer_view.clear_countdown_message()
        # Insert: Display current and next part in timer view
        parts = self.timer_controller.parts_list
        if parts:
            self.timer_view.part_label.setText(self.tr(f"Current Part: {parts[0].title}"))
            if len(parts) > 1:
                self.timer_view.countdown_label.setText(self.tr(f"Next Part: {parts[1].title}"))
                self.timer_view.countdown_label.setVisible(True)
            else:
                self.timer_view.countdown_label.setText(self.tr("Last Part"))
                self.timer_view.countdown_label.setVisible(True)
        if self.secondary_display:
            self.secondary_display.show_clock = False
            # Hide countdown, show part info
            self.secondary_display.show_countdown = False

            # Set part information
            parts = self.timer_controller.parts_list
            if len(parts) > 1:
                # Show current and next part info
                self.secondary_display.info_label1.setText(self.tr(f"Next Part: {parts[1].title}"))
                self.secondary_display.info_label1.setStyleSheet("""
                    color: #ffffff; 
                    font-size: 60px;
                    font-weight: bold;
                """)
            else:
                # Only one part in the meeting
                self.secondary_display.info_label1.setText(self.tr("Last Part"))

            # Ensure both labels are visible
            self.secondary_display.info_label2.setVisible(True)

        # Disconnect countdown update signal so countdown label updates stop after meeting starts
        try:
            self.timer_controller.meeting_countdown_updated.disconnect(self._update_countdown)
        except TypeError:
            print("Countdown update already disconnected or never connected")
    
    def _meeting_ended(self):
        """Handle meeting end"""
        from src.utils.resources import get_icon

        self.start_button.setText(self.tr("Start Meeting"))
        self.start_button.setIcon(get_icon("play"))
        self.start_button.setObjectName("startButton")  # Change style
        self.start_button.setStyleSheet("")  # Force style refresh
        self.start_button.clicked.disconnect()
        self.start_button.clicked.connect(self._start_meeting)

        # Enable meeting selector and remove blur
        self.meeting_selector.setEnabled(True)
        if isinstance(self.meeting_selector.graphicsEffect(), QGraphicsOpacityEffect):
            self.meeting_selector.setGraphicsEffect(None)

        # Disable controls
        self.pause_resume_button.setEnabled(False)
        self.prev_button.setEnabled(False)
        self.next_button.setEnabled(False)
        self.decrease_button.setEnabled(False)
        self.increase_button.setEnabled(False)

        # Reset pause/resume button
        self.pause_resume_button.setText(self.tr("Pause"))
        self.pause_resume_button.setIcon(get_icon("pause"))
        self.pause_resume_button.setObjectName("pauseButton")  # Change style
        self.pause_resume_button.setStyleSheet("")  # Force style refresh

        # Reset overtime indicator
        self.meeting_overtime_label.setVisible(False)

        # Reset predicted end time
        self.predicted_end_time_label.setVisible(False)

        # Clean up center display after meeting ends
        self.timer_view.part_label.setText(self.tr("Meeting Ended"))
        self.timer_view.countdown_label.setText("")
        self.timer_view.countdown_label.setVisible(False)
        # show the clock in the timer view
        self.timer_view.show_clock = True

        # Update secondary display
        if self.secondary_display:
            self.secondary_display.show_clock = True
            # Show meeting completed message
            self.secondary_display.info_label1.setText(self.tr("Meeting Ended"))
            self.secondary_display.info_label1.setStyleSheet("""
                color: #ffffff; 
                font-size: 60px;
                font-weight: bold;
            """)
            # Clear predicted end time
            self.secondary_display.info_label2.setText("")
            # Reset countdown flag
            self.secondary_display.show_countdown = False
        # force an immediate refresh so the time appears right away
        if self.timer_controller.timer.state == TimerState.STOPPED:
            self.timer_controller.timer._update_current_time()
    
    def _translate_transition_message(self, transition_msg):
        """Translate chairman transition messages.

        Uses literal strings so pylupdate6 can extract them for translation.
        """
        # Map enum values to translated strings using literal tr() calls
        translations = {
            "Chairman Counsel and Transition": self.tr("Chairman Counsel and Transition"),
            "Chairman Introduction": self.tr("Chairman Introduction"),
            "Chairman Transition": self.tr("Chairman Transition"),
        }
        return translations.get(transition_msg, transition_msg)

    def _transition_started(self, transition_msg):
        """Handle chairman transition period"""
        # Translate the transition message
        translated_msg = self._translate_transition_message(transition_msg)

        # Update the current part label
        self.current_part_label.setText(f"⏳ {translated_msg} (1:00)")

        # Also update the part_label in the timer view
        self.timer_view.part_label.setText(translated_msg)

        # Update secondary display if available
        if self.secondary_display:
            # Use info_label1 instead of next_part_label in the new design
            self.secondary_display.info_label1.setText(translated_msg)
            self.secondary_display.info_label1.setStyleSheet("""
                color: #bb86fc; /* Purple for transitions */
                font-size: 60px;
                font-weight: bold;
            """)
    
    def _get_global_part_index(self, section_index, part_index):
        """Helper method to get global part index from section and part indices"""
        if not self.meeting_controller.current_meeting:
            return -1
        
        meeting = self.meeting_controller.current_meeting
        global_index = 0
        
        for i in range(section_index):
            global_index += len(meeting.sections[i].parts)
        
        global_index += part_index
        return global_index
    
    
    def _on_language_changed(self, lang_code: str):
        """Handle runtime language change"""
        from src.utils.translator import load_translation
        import sys
        from PyQt6.QtCore import QProcess
        load_translation(QApplication.instance(), lang_code)

        QMessageBox.information(self, self.tr("Language Changed"), self.tr("App will now restart to apply changes."))
        QApplication.quit()
        QProcess.startDetached(sys.executable, sys.argv)

    def _settings_changed(self):
        """Handle general settings changes (fallback for uncategorized settings)"""
        # This should now rarely be called since most settings have specific signals
        pass
    
    def _on_tools_dock_state_changed(self, visible: bool):
        """Handle tools dock state changes"""
        # Update tools dock state without affecting secondary screen
        self.settings_controller.update_tools_dock_state(self.tools_dock.isVisible())
    
    def _on_meeting_settings_changed(self):
        """Handle meeting time/source settings changes"""
        # Update meeting-related UI if needed
        pass
    
    def _on_reminder_settings_changed(self):
        """Handle reminder settings changes"""
        # Update reminder-related functionality if needed
        pass
    
    def _update_secondary_display_label(self):
        """Update the secondary display indicator in the status bar"""
        settings = self.settings_controller.get_settings()
        if settings.display.use_secondary_screen and settings.display.secondary_screen_index is not None:
            self.secondary_display_label.setText(self.tr("Secondary Display: Active"))
        else:
            self.secondary_display_label.setText(self.tr("Secondary Display: Inactive"))

    
    def _apply_current_theme(self):
        """Apply the current theme from settings"""
        from src.utils.resources import apply_stylesheet, get_system_theme

        theme = self.settings_controller.get_settings().display.theme
        # Resolve "system" to actual theme
        if theme == "system":
            theme = get_system_theme()
        # Guard against invalid values reaching the stylesheet loader
        if theme not in ("light", "dark"):
            theme = "light"

        app = QApplication.instance()
        apply_stylesheet(app, theme)
        # Force full widget repaint — needed on Windows where
        # setStyleSheet alone may not propagate to all children
        app.style().unpolish(app)
        app.style().polish(app)
        app.processEvents()

    def _set_theme(self, theme: str):
        """Set the application theme"""
        # Update theme in settings
        self.settings_controller.set_theme(theme)

        # Update menu checkboxes
        self.system_theme_action.setChecked(theme == "system")
        self.light_theme_action.setChecked(theme == "light")
        self.dark_theme_action.setChecked(theme == "dark")

        # Apply the theme
        self._apply_current_theme()

    def _theme_changed(self, theme: str):
        """Handle theme change from settings"""
        # Update menu checkboxes
        self.system_theme_action.setChecked(theme == "system")
        self.light_theme_action.setChecked(theme == "light")
        self.dark_theme_action.setChecked(theme == "dark")

        # Apply the theme
        self._apply_current_theme()
        
        # Update secondary display if open
        if self.secondary_display:
            self._apply_secondary_display_theme()
    
    def _apply_secondary_display_theme(self):
        """Apply high-contrast styling to the secondary display regardless of theme"""
        if not self.secondary_display:
            return
        
        try:
            # Always apply a black background with white text for maximum visibility
            self.secondary_display.setStyleSheet("""
                QMainWindow, QWidget {
                    background-color: #000000;
                    color: #ffffff;
                }
                
                QLabel {
                    color: #ffffff;
                    font-weight: bold;
                }
                
                QFrame {
                    background-color: rgba(50, 50, 50, 180);
                    border: 2px solid #ffffff;
                    border-radius: 15px;
                }
                
                TimerView {
                    background-color: #000000;
                    border: 2px solid #333333;
                }
                
                TimerView QLabel {
                    color: #ffffff;
                    font-weight: bold;
                }
            """)
            
            # Check if the attribute exists before trying to access it
            if hasattr(self.secondary_display, 'timer_view'):
                try:
                    if hasattr(self.secondary_display.timer_view, 'timer_label'):
                        self.secondary_display.timer_view.timer_label.setStyleSheet("color: #ffffff; font-weight: bold;")
                except (RuntimeError, AttributeError):
                    # Ignore errors if the component has been deleted
                    pass
            
            # Check for direct timer_label attribute in newer implementation
            if hasattr(self.secondary_display, 'timer_label'):
                try:
                    self.secondary_display.timer_label.setStyleSheet("""
                        color: #ffffff;
                        font-size: 380px;
                        font-weight: bold;
                        font-family: 'Courier New', monospace;
                    """)
                except (RuntimeError, AttributeError):
                    pass
        except Exception as e:
            logger.error("Error applying secondary display theme: %s", e)
    
    def _start_meeting(self):
        """Start the current meeting"""
        if not self.meeting_controller.current_meeting:
            QTimer.singleShot(0, lambda: QMessageBox.warning(self, self.tr("No Meeting Selected"),
                                                            self.tr("Please select a meeting to start.")))
            return
        
        # Stop countdown updates immediately
        try:
            self.timer_controller.meeting_countdown_updated.disconnect(self._update_countdown)
        except TypeError:
            pass  # Already disconnected
        
        # Clear countdown from main window immediately
        self.current_part_label.setText("")
        
         # Clear countdown from secondary display immediately
        if self.secondary_display:
            self.secondary_display.show_countdown = False
            self.secondary_display._show_countdown = False
            # Clear any countdown text immediately
            self.secondary_display.info_label1.setText("")
            self.secondary_display.info_label2.setText("")
        
        self.timer_controller.start_meeting()
    
    def _stop_meeting(self):
        """Stop the current meeting after confirmation"""
        confirm = QMessageBox.question(
            self,
            self.tr("End Meeting?"),
            self.tr("😅 Hold up! Are you sure you want to stop the meeting?\nThis will end the timer and reset the session."),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel
        )
        if confirm == QMessageBox.StandardButton.Yes:
            # Stop visual animations (e.g., start/next button pulse)
            for btn in [self.start_button, self.next_button]:
                if hasattr(btn, '_pulse_animations'):
                    for anim in list(btn._pulse_animations):  # Copy list to avoid modification during iteration
                        if anim is not None:
                            anim.stop()
                    btn._pulse_animations.clear()
                    effect = btn.graphicsEffect()
                    if effect is not None:
                        effect.setOpacity(1.0)
                        btn.setGraphicsEffect(None)

            self.timer_controller.stop_meeting()
    
    def _toggle_pause_resume(self):
        """Toggle between pause and resume"""
        # Debounce rapid clicks to prevent crashes on Windows
        if self._is_button_debounced():
            return
        from src.utils.resources import get_icon

        if self.timer_controller.timer.state == TimerState.RUNNING:
            self.timer_controller.pause_timer()
            # Disable all other controls during pause
            self.prev_button.setEnabled(False)
            self.next_button.setEnabled(False)
            self.decrease_button.setEnabled(False)
            self.increase_button.setEnabled(False)
            #self.start_button.setEnabled(False)
            self.pause_resume_button.setText(self.tr("Resume"))
            self.pause_resume_button.setIcon(get_icon("play"))
            self.pause_resume_button.setObjectName("startButton")  # Change style
            self.pause_resume_button.setStyleSheet("")  # Force style refresh
            
            # Blur/opacity effect on controls
            for widget in [self.prev_button, self.next_button, self.decrease_button, self.increase_button]:
                if widget:
                    blur_effect = QGraphicsOpacityEffect(widget)
                    blur_effect.setOpacity(0.4)
                    widget.setGraphicsEffect(blur_effect)
            
        else:
            self.timer_controller.resume_timer()
            # Re-enable controls after resuming
            self.prev_button.setEnabled(True)
            self.next_button.setEnabled(True)
            self.decrease_button.setEnabled(True)
            self.increase_button.setEnabled(True)
            self.meeting_selector.setEnabled(True)
            self.pause_resume_button.setText(self.tr("Pause"))
            self.pause_resume_button.setIcon(get_icon("pause"))
            self.pause_resume_button.setObjectName("pauseButton")  # Change style
            self.pause_resume_button.setStyleSheet("")  # Force style refresh
            
            # Remove blur/opacity effect on controls
            for widget in [self.prev_button, self.next_button, self.decrease_button, self.increase_button, self.start_button, self.meeting_selector]:
                if widget and isinstance(widget.graphicsEffect(), QGraphicsOpacityEffect):
                    widget.graphicsEffect().setOpacity(1.0)
                    widget.setGraphicsEffect(None)
    
    def _reset_button_cooldown(self):
        """Reset the button cooldown flag"""
        self._button_cooldown = False

    def _is_button_debounced(self) -> bool:
        """Check if button action should be debounced (ignored due to rapid clicking)"""
        if self._button_cooldown:
            return True
        self._button_cooldown = True
        self._cooldown_timer.start(150)  # 150ms cooldown between button actions
        return False

    def _next_part(self):
        """Move to the next part"""
        # Debounce rapid clicks to prevent crashes on Windows
        if self._is_button_debounced():
            return
        # Stop next button pulse if active
        if hasattr(self, 'next_button') and hasattr(self.next_button, '_pulse_animations'):
            for anim in list(self.next_button._pulse_animations):  # Copy list to avoid modification during iteration
                if anim is not None:
                    anim.stop()
            self.next_button._pulse_animations.clear()
            effect = self.next_button.graphicsEffect()
            if effect is not None:
                effect.setOpacity(1.0)
        # Move to the next part
        self.timer_controller.next_part()

    def _previous_part(self):
        """Move to the previous part"""
        # Debounce rapid clicks to prevent crashes on Windows
        if self._is_button_debounced():
            return
        self.timer_controller.previous_part()

    def _adjust_time(self, minutes_delta):
        """Adjust timer by adding/removing minutes"""
        # Debounce rapid clicks to prevent crashes on Windows
        if self._is_button_debounced():
            return
        self.timer_controller.adjust_time(minutes_delta)
    
    # Notification for meeting start and advance    
    def _pulse_widget(self, widget):
        """Animate a widget like a heartbeat until manually stopped."""

        if not widget or not widget.isVisible():
        
            return

        # Ensure the widget has an opacity effect
        effect = widget.graphicsEffect()
        if not isinstance(effect, QGraphicsOpacityEffect):
            effect = QGraphicsOpacityEffect(widget)
            widget.setGraphicsEffect(effect)
            effect.setOpacity(1.0)

        # Create heartbeat-like pulse animation
        anim = QPropertyAnimation(effect, b"opacity")
        anim.setDuration(1200)
        anim.setKeyValues([
            (0.0, 1.0),
            (0.1, 0.3),
            (0.2, 1.0),
            (0.3, 0.4),
            (0.4, 1.0),
            (1.0, 1.0),
        ])
        anim.setLoopCount(-1)
        anim.setEasingCurve(QEasingCurve.Type.InOutQuad)
        anim.start()

        effect.setEnabled(True)

        if not hasattr(widget, '_pulse_animations'):
            widget._pulse_animations = []
        widget._pulse_animations = [a for a in widget._pulse_animations if a.state() == QPropertyAnimation.State.Running]
        widget._pulse_animations.append(anim)
        
    def _on_durations_redistributed(self, adjusted_parts: list):
        """Handle duration redistribution — show toast notification"""
        count = len(adjusted_parts)
        target = getattr(self.timer_controller, '_predicted_end_time', None)
        time_str = target.strftime("%H:%M") if target else "?"
        self._show_toast_notification(
            self.tr("Schedule Updated"),
            self.tr("%n part(s) redistributed — meeting now ends at", "", count)
            + f" {time_str}",
            icon="toast-adjust"
        )

    def _on_durations_reset(self):
        """Handle duration reset — show toast notification"""
        self._show_toast_notification(
            self.tr("Durations Reset"),
            self.tr("All part durations restored to their original values."),
            icon="toast-reset"
        )

    def _show_toast_notification(self, title, message, icon=""):
        """Show an in-app toast notification with the given title and message.

        Args:
            title: The notification title (should be pre-translated via tr())
            message: The notification message (should be pre-translated via tr())
            icon: Optional emoji icon to display
        """
        if hasattr(self, 'toast_manager') and self.toast_manager:
            self.toast_manager.show_toast(title, message, icon, duration=5000)
        else:
            print("No toast_manager found")
        
    def _nudge_start(self):
        """Visual + toast nudge to remind the user to start the meeting."""
        if not getattr(self, 'start_button', None):
            return

        # Pulse the button
        self._pulse_widget(self.start_button)

        # Show in-app toast message
        self._show_toast_notification(
            self.tr("Ready to Begin?"),
            self.tr("Press Start Meeting to begin the timer and stay on schedule."),
            icon="toast-reminder"
        )


            
    def _nudge_advance(self):
        """Visual + toast nudge to remind the user to advance to the next part."""
        print("_nudge_advance called")
        if not getattr(self, 'next_button', None):
            print("No next_button found")
            return

        # Pulse the button
        self._pulse_widget(self.next_button)

        # Get current part title
        part_title = self.tr("current part")
        if (hasattr(self.timer_controller, 'current_part_index') and
            hasattr(self.timer_controller, 'parts_list') and
            0 <= self.timer_controller.current_part_index < len(self.timer_controller.parts_list)):

            part = self.timer_controller.parts_list[self.timer_controller.current_part_index]
            if hasattr(part, 'title'):
                part_title = part.title

        # Show in-app toast message
        self._show_toast_notification(
            self.tr("Over Time"),
            self.tr("'{part_title}' has exceeded its allotted time.").replace("{part_title}", part_title),
            icon="toast-overtime"
        )

    
    def _create_new_meeting(self):
        """Create a new custom meeting"""
        # Show the meeting editor dialog
        self.meeting_controller.show_meeting_editor(self)
    
    def _open_meeting(self):
        """Open an existing meeting file"""
        from PyQt6.QtWidgets import QFileDialog

        # Show file dialog
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Open Meeting",
            str(self.meeting_controller.meetings_dir),
            "Meeting Files (*.json)"
        )

        if file_path:
            try:
                # Load meeting
                meeting = self.meeting_controller._load_meeting_file(file_path)
                if meeting:
                    # Set as current meeting
                    self.meeting_controller.set_current_meeting(meeting)

                    # Update meeting view
                    if self._is_component_ready('meeting_view'):
                        self.meeting_view.set_meeting(meeting)
                    else:
                        self._store_pending_action('meeting_view', 'set_meeting', meeting)

                    # Add to recent meetings
                    if file_path not in self.meeting_controller.settings_manager.settings.recent_meetings:
                        self.meeting_controller.settings_manager.settings.recent_meetings.append(file_path)
                        self.meeting_controller.settings_manager.save_settings()
            except Exception as e:
                QTimer.singleShot(0, lambda: QMessageBox.critical(self, self.tr("Error"), self.tr(f"Failed to load meeting: {str(e)}")))

    def _update_meetings(self):
        """Update meetings from web with enhanced weekend meeting handling"""
        # Check meeting source mode
        mode = self.settings_controller.get_settings().meeting_source.mode
        if mode == MeetingSourceMode.WEB_SCRAPING:
            # Show a progress dialog
            from PyQt6.QtWidgets import QProgressDialog
            progress = QProgressDialog(self.tr("Updating meetings from wol.jw.org..."), self.tr("Cancel"), 0, 0, self)
            progress.setWindowTitle(self.tr("Updating Meetings"))
            progress.setWindowModality(Qt.WindowModality.WindowModal)
            progress.show()

            try:
                # Use web scraping
                meetings = self.meeting_controller.update_meetings_from_web()
                # Insert check for no meetings returned
                if not meetings:
                    raise ValueError("No meetings were returned from the update process.")

                # Process weekend meeting to ensure songs are properly displayed
                if MeetingType.WEEKEND in meetings:
                    weekend_meeting = meetings[MeetingType.WEEKEND]
                    self._process_weekend_meeting_songs(weekend_meeting)

                progress.close()

                # Show a success message
                QTimer.singleShot(0, lambda: QMessageBox.information(self, self.tr("Update Complete"),
                                               self.tr("Meetings have been successfully updated.")))
            except Exception as e:
                progress.close()
                QTimer.singleShot(0, lambda e=e: QMessageBox.warning(self, self.tr("Update Failed"),
                                              self.tr(f"Failed to update meetings: {str(e)}")))
        else:
            # Show options dialog as before
            from PyQt6.QtWidgets import QMenu

            menu = QMenu(self)
            web_action = menu.addAction(self.tr("Update from Web"))
            web_action.triggered.connect(self.meeting_controller.update_meetings_from_web)

            edit_action = menu.addAction(self.tr("Edit Current Meeting"))
            edit_action.triggered.connect(lambda: self._edit_current_meeting())

            menu.addSeparator()

            create_action = menu.addAction(self.tr("Create New Meeting"))
            create_action.triggered.connect(self._create_new_meeting)

            # Position menu at cursor – sender() is a QAction (no geometry)
            from PyQt6.QtGui import QCursor
            menu.exec(QCursor.pos())
            
    def _process_weekend_meeting_songs(self, meeting: Meeting):
        """Process weekend meeting to ensure songs are properly displayed"""
      
        if meeting.meeting_type != MeetingType.WEEKEND:
            
            return
        # Only trigger dialog if manual weekend songs setting is enabled
        if not self.settings_controller.get_settings().meeting_source.weekend_songs_manual:
            
            return
        # Check for missing songs in the meeting
        import re
        missing_songs = False

        for section in meeting.sections:
            for part in section.parts:
                
                title = part.title.lower().strip()
                from src.views.weekend_song_editor import e_un_cantico, numero_nel_titolo
                if e_un_cantico(title) and numero_nel_titolo(title) is None:
                    missing_songs = True

        if missing_songs:
            # Una domanda sola, anche se la funzione arriva da piu' strade
            # (caricamento delle adunanze e scelta dell'adunanza).
            if getattr(self, "_cantici_in_attesa", False):
                return
            self._cantici_in_attesa = True

            def ask_and_edit():
                nonlocal meeting
                self._cantici_in_attesa = False
                # Si chiede solo se l'adunanza aperta ORA e' la domenica e il
                # numero del cantico manca ancora.  Con l'infrasettimanale
                # aperta, o con il numero gia' messo, non si chiede niente.
                corrente = self.meeting_controller.current_meeting
                if corrente is None or corrente.meeting_type != MeetingType.WEEKEND:
                    return
                from src.views.weekend_song_editor import e_un_cantico, numero_nel_titolo
                if not any(e_un_cantico(p.title) and numero_nel_titolo(p.title) is None
                           for sez in corrente.sections for p in sez.parts):
                    return
                meeting = corrente
                from PyQt6.QtWidgets import QDialog, QVBoxLayout, QLabel, QHBoxLayout, QPushButton
                from PyQt6.QtCore import Qt, QTimer
                
                dialog = QDialog(self)
                dialog.setWindowTitle(self.tr("Song Entry Required"))
                dialog.setMinimumWidth(450)
                dialog.setModal(True)
                # Ensure dialog appears on top of the main window (especially on Windows)
                dialog.setWindowFlags(
                    dialog.windowFlags()
                    & ~Qt.WindowType.WindowContextHelpButtonHint
                    | Qt.WindowType.WindowStaysOnTopHint
                )
                dialog.raise_()
                dialog.activateWindow()

                layout = QVBoxLayout(dialog)

                info_label = QLabel(
                                self.tr("Some songs of the weekend meeting have no number yet.") + "\n\n" +
                                self.tr("Enter them now?")
                            )
                info_label.setWordWrap(True)
                layout.addWidget(info_label)

                buttons_layout = QHBoxLayout()
                edit_now_button = QPushButton(self.tr("Edit Now"))
                edit_now_button.clicked.connect(lambda: dialog.accept())
                buttons_layout.addWidget(edit_now_button)

                skip_button = QPushButton(self.tr("Skip"))
                def handle_skip():
                    dialog.reject()
                    QTimer.singleShot(200, self._force_normal_window_state)
                skip_button.clicked.connect(handle_skip)
                buttons_layout.addWidget(skip_button)

                layout.addLayout(buttons_layout)

                if dialog.exec() == QDialog.DialogCode.Accepted:
                    from src.views.weekend_song_editor import WeekendSongEditorDialog
                    # Save window state before opening the editor dialog
                    was_maximized = self.isMaximized()
                    was_fullscreen = self.isFullScreen()

                    editor_dialog = WeekendSongEditorDialog(meeting, self)
                    if editor_dialog.exec() == QDialog.DialogCode.Accepted:
                        self.meeting_controller.save_meeting(meeting)
                        if self._is_component_ready('meeting_view'):
                            self.meeting_view.set_meeting(meeting)
                        else:
                            self._store_pending_action('meeting_view', 'set_meeting', meeting)
                        self._aggiorna_contenuti(meeting)

                    # Restore the window state after the dialog closes
                    if was_maximized:
                        self.showMaximized()
                    elif was_fullscreen:
                        self.showFullScreen()
                    else:
                        QTimer.singleShot(200, self._force_normal_window_state)
            # Delay slightly to ensure main window is fully shown (helps on Windows)
            self.esegui_quando_visibile(ask_and_edit, 300)

    def _force_normal_window_state(self):
        self.showNormal()

        # Only resize if the window is unusually large
        if self.width() > 1000 or self.height() > 800:
            self.resize(800, 600)

        # Center the window on the primary screen
        screen = QApplication.primaryScreen()
        if screen:
            screen_geometry = screen.availableGeometry()
            window_geometry = self.frameGeometry()
            window_geometry.moveCenter(screen_geometry.center())
            self.move(window_geometry.topLeft())
    
    def _edit_current_meeting(self):
        """Edit the currently selected meeting"""
        if not self.meeting_controller.current_meeting:
            QTimer.singleShot(0, lambda: QMessageBox.warning(self, self.tr("No Meeting Selected"),
                                                            self.tr("Please select a meeting to edit.")))
            return

        from src.views.meeting_editor_dialog import MeetingEditorDialog

        dialog = MeetingEditorDialog(self, self.meeting_controller.current_meeting)
        dialog.meeting_updated.connect(self._on_meeting_updated)
        dialog.exec()

        # Pass the _on_meeting_updated method so changes reflect live
        self.meeting_controller.show_meeting_editor(
        self,
        self.meeting_controller.current_meeting,
        self._on_meeting_updated
        )


    def _on_meeting_updated(self, updated_meeting: Meeting):
        """Apply updated meeting edits immediately"""
        self.meeting_controller.set_current_meeting(updated_meeting)
        self.timer_controller.set_meeting(updated_meeting)
        self._initialize_timer_display()
    
    def _edit_weekend_meeting_songs(self):
        """Edit weekend meeting songs"""
        current_meeting = self.meeting_controller.current_meeting

        # Check if we have a weekend meeting selected
        if not current_meeting or current_meeting.meeting_type != MeetingType.WEEKEND:
            QTimer.singleShot(0, lambda: QMessageBox.warning(self, self.tr("Not a Weekend Meeting"),
                                                            self.tr("Please select a weekend meeting first.")))
            return

        # Show the weekend song editor dialog
        from src.views.weekend_song_editor import WeekendSongEditorDialog
        dialog = WeekendSongEditorDialog(current_meeting, self)

        if dialog.exec() == QDialog.DialogCode.Accepted:
            # Save the updated meeting
            self.meeting_controller.save_meeting(current_meeting)

            # Update the meeting display
            if self._is_component_ready('meeting_view'):
                self.meeting_view.set_meeting(current_meeting)
            else:
                self._store_pending_action('meeting_view', 'set_meeting', current_meeting)
            self._aggiorna_contenuti(current_meeting)

            # Show confirmation message
            QTimer.singleShot(0, lambda: QMessageBox.information(self, self.tr("Songs Updated"),
                                                                self.tr("Weekend meeting songs have been updated.")))

    def _open_settings(self):
        """Open settings dialog"""
        dialog = SettingsDialog(self.settings_controller, self)
        dialog.exec()
    
    def _initialize_screens(self):
        """Initialize screens with focus management"""
        settings = self.settings_controller.settings_manager._load_settings()
        
        # Position main window first
        self._position_main_window()
        
        # Ensure main window has focus
        self.activateWindow()
        self.raise_()
        
        # Show secondary display if enabled
        if settings.display.use_secondary_screen:
            # Longer delay for safe positioning
            QTimer.singleShot(1500, self._ensure_single_secondary_display)
            
            # Handle focus after creation
            QTimer.singleShot(2500, self._handle_secondary_focus_issues)
    
    def _handle_secondary_focus_issues(self):
        """Handle focus-related issues"""
        # Keep main window focused
        self.activateWindow()
        self.raise_()
        
        # Ensure secondary stays on top without stealing focus
        if hasattr(self, 'secondary_display') and self.secondary_display and self.secondary_display.isVisible():
            # Return focus to main window after brief delay
            QTimer.singleShot(100, lambda: self.activateWindow())
    
    def _position_main_window(self):
        """Position the main window on the primary screen from settings"""
        settings = self.settings_controller.get_settings()
        #primary_index = settings.display.primary_screen_index
        
        # Get the screen by index
        screen = ScreenHandler.get_configured_screen(settings, is_primary=True)
        if screen:
            # Center the window on the selected primary screen
            geometry = screen.availableGeometry()
            self.setGeometry(
                geometry.x() + (geometry.width() - self.width()) // 2,
                geometry.y() + (geometry.height() - self.height()) // 2,
                self.width(),
                self.height()
            )
    
    def _toggle_secondary_display(self):
        """Toggle the secondary display on or off"""
        settings = self.settings_controller.get_settings()
        settings.display.use_secondary_screen = not settings.display.use_secondary_screen
        self.settings_controller.save_settings()

        if not settings.display.use_secondary_screen:
            try:
                if self.secondary_display:
                    self.secondary_display.close()
            except RuntimeError:
                print("[MainWindow] Secondary display already deleted.")
            self.secondary_display = None

        self._update_secondary_display()

    def _toggle_co_visit(self, checked: bool):
        """Toggle CO visit mode"""
        if checked:
            self._show_toast_notification(
                self.tr("CO Visit Mode Enabled"),
                self.tr("CO visit schedule will be applied to meetings this week."),
                icon="toast-info"
            )
        else:
            self._show_toast_notification(
                self.tr("CO Visit Mode Disabled"),
                self.tr("Normal meeting schedule restored."),
                icon="toast-info"
            )

        self.settings_controller.set_co_visit_enabled(checked)
        self._reload_current_meeting_with_co_visit()

    def _reload_current_meeting_with_co_visit(self):
        """Reload the current meeting with or without CO visit modifications"""
        current_meeting = self.meeting_controller.current_meeting
        if not current_meeting:
            return

        # Get the original meeting from the controller
        meeting_type = current_meeting.meeting_type
        original_meeting = self.meeting_controller.current_meetings.get(meeting_type)

        if original_meeting:
            if self.settings_controller.is_co_visit_active():
                modified = self.meeting_controller.apply_co_visit_modifications(original_meeting)
                self._set_current_meeting(modified)
            else:
                self._set_current_meeting(original_meeting)

    def _on_co_visit_changed(self, enabled: bool):
        """Handle CO visit mode changes from settings"""
        if hasattr(self, 'co_visit_action'):
            self.co_visit_action.setChecked(enabled)
        self._reload_current_meeting_with_co_visit()
    
    def _update_secondary_display(self):
        """Update secondary display based on settings"""
        try:
            settings = self.settings_controller.get_settings()

            if settings.display.use_secondary_screen and settings.display.secondary_screen_index is not None:
                if not self.secondary_display or not self.secondary_display.isVisible():
                    self._show_secondary_display()
                if self.secondary_display and self.secondary_display.isVisible():
                    self._apply_secondary_display_theme()
            else:
                if self.secondary_display:
                    try:
                        self.secondary_display.hide()
                        self.toggle_secondary_action.setChecked(False)
                        self._cleanup_secondary_display()
                    except Exception as e:
                        logger.error("Error hiding secondary display: %s", e)

            # Update toggle action (ensure it's in sync)
            if hasattr(self, 'toggle_secondary_action'):
                self.toggle_secondary_action.setChecked(settings.display.use_secondary_screen)

        except Exception as e:
            logger.error("Error updating secondary display: %s", e)

    def _cleanup_secondary_display(self):
        """Clean up secondary display with monitoring stop"""
        try:
            if hasattr(self, 'secondary_display') and self.secondary_display:
                logger.debug("Cleaning up secondary display")
                
                # Stop monitoring
                self._stop_screen_monitoring()
                
                # Disconnect signals
                try:
                    self.timer_controller.meeting_countdown_updated.disconnect(
                        self.secondary_display._update_countdown
                    )
                except (TypeError, RuntimeError):
                    pass
                
                # Hide and delete
                self.secondary_display.hide()
                self.secondary_display.deleteLater()
                self.secondary_display = None
                
        except Exception as e:
            logger.error("Error cleaning up secondary display: %s", e)
            self.secondary_display = None
    
    """  
    def _toggle_display_mode(self):
        settings = self.settings_controller.get_settings()
        current_mode = settings.display.display_mode
        
        if current_mode == TimerDisplayMode.DIGITAL:
            self.settings_controller.set_display_mode(TimerDisplayMode.ANALOG)
        else:
            self.settings_controller.set_display_mode(TimerDisplayMode.DIGITAL)
    """ 
    
    def _meeting_overtime(self, total_overtime_seconds):
        """Handle meeting overtime notification"""
        if total_overtime_seconds > 0:
            minutes = total_overtime_seconds // 60
            seconds = total_overtime_seconds % 60

            # Set color based on severity
            if total_overtime_seconds < 60:
                color = "orange"
            else:
                color = "red"

            self.meeting_overtime_label.setText(self.tr(f"Meeting Overtime: {minutes:02d}:{seconds:02d}"))
            self.meeting_overtime_label.setStyleSheet(f"color: {color}; font-weight: bold;")
            self.meeting_overtime_label.setVisible(True)
    
    def _update_predicted_end_time(self, original_end_time, predicted_end_time, target_end_time):
        """Update the predicted end time display"""
        # Only show if the setting is enabled
        settings = self.settings_controller.get_settings()
        if not settings.display.show_predicted_end_time:
            self.predicted_end_time_label.setVisible(False)
            return

        # Ora in formato 24 ore, testi in italiano
        predicted_time_str = predicted_end_time.strftime("%H:%M")
        target_time_str = target_end_time.strftime("%H:%M")

        # Differenza rispetto all'ora di fine prevista dall'adunanza
        time_diff = predicted_end_time - target_end_time
        diff_seconds = int(time_diff.total_seconds())
        diff_minutes = abs(diff_seconds) // 60

        if diff_seconds > 300:  # oltre 5 minuti di ritardo
            status_text = f"{diff_minutes} min di ritardo ⚠️"
            color = "#f87171"
        elif diff_seconds > 120:  # 2-5 minuti di ritardo
            status_text = f"{diff_minutes} min di ritardo"
            color = "#fbbf24"
        elif diff_seconds > -120:  # entro 2 minuti
            status_text = "In orario"
            color = "#4ade80"
        else:  # oltre 2 minuti in anticipo
            status_text = f"{diff_minutes} min in anticipo"
            color = "#4ade80"

        self.predicted_end_time_label.setText(f"Fine: {predicted_time_str} | {status_text}")
        self.predicted_end_time_label.setStyleSheet(f"color: {color};")
        self.predicted_end_time_label.setToolTip(f"Fine prevista: {target_time_str}")

        # Make the label visible
        self.predicted_end_time_label.setVisible(True)
    
    def _show_about(self):
        """Show the about dialog"""
        QMessageBox.about(
            self,
            self.tr("About OnTime Meeting Timer"),
            self.tr("OnTime Meeting Timer\n\n"
            "A cross-platform timer application for managing JW meeting schedules.\n\n"
            "© 2025 Open Source")
        )
    
    def _show_error(self, message):
        """Show error message (thread-safe)"""
        QTimer.singleShot(0, lambda: QMessageBox.critical(self, self.tr("Error"), message))


    # ------------------------------------------------------------------
    # Session Recovery (Crash Recovery)
    # ------------------------------------------------------------------
    def _check_session_recovery(self):
        """Check if there's a session to recover from a crash"""
        session = self.timer_controller.session_manager.check_for_recovery()

        if not session:
            return

        # Check if session is stale (older than 24 hours)
        is_stale = self.timer_controller.session_manager.is_session_stale(session)

        if is_stale:
            self._show_stale_session_dialog(session)
        else:
            self._show_recovery_dialog(session)

    def _show_recovery_dialog(self, session: SessionState):
        """Show dialog offering to recover the session"""
        from src.config import MEETINGS_DIR

        # Try to load the meeting to check for changes
        meeting_path = MEETINGS_DIR / session.meeting_file
        meeting = None
        if meeting_path.exists():
            meeting = self.meeting_controller._load_meeting_file(str(meeting_path))

        # Check if meeting has changed
        meeting_changed = False
        if meeting:
            meeting_changed = self.timer_controller.session_manager.is_meeting_changed(session, meeting)

        if meeting_changed:
            msg = QMessageBox(self)
            msg.setWindowTitle(self.tr("Session Recovery"))
            msg.setText(self.tr("A previous session was interrupted, but the meeting schedule has changed."))
            msg.setInformativeText(self.tr("Would you like to attempt recovery anyway, start fresh, or discard?"))
            msg.setStandardButtons(
                QMessageBox.StandardButton.Yes |
                QMessageBox.StandardButton.No |
                QMessageBox.StandardButton.Discard
            )
            msg.button(QMessageBox.StandardButton.Yes).setText(self.tr("Recover Anyway"))
            msg.button(QMessageBox.StandardButton.No).setText(self.tr("Start Fresh"))
            msg.button(QMessageBox.StandardButton.Discard).setText(self.tr("Discard"))

            result = msg.exec()

            if result == QMessageBox.StandardButton.Discard:
                self.timer_controller.session_manager.clear_session()
                return
            elif result == QMessageBox.StandardButton.No:
                self.timer_controller.session_manager.clear_session()
                return
            # Yes = continue to restore
        else:
            # Calculate adjusted state to show in dialog
            adjusted = self.timer_controller.session_manager.calculate_adjusted_state(session)

            msg = QMessageBox(self)
            msg.setWindowTitle(self.tr("Session Recovery"))
            msg.setText(self.tr("A previous meeting session was interrupted."))

            # Build informative text
            part_num = session.current_part_index + 1
            if adjusted.get('was_paused', False):
                mins = session.remaining_seconds // 60
                secs = session.remaining_seconds % 60
                info = self.tr(f"Resume at part {part_num} with {mins}:{secs:02d} remaining? (paused)")
            elif adjusted.get('overtime_seconds', 0) > 0:
                overtime_mins = adjusted['overtime_seconds'] // 60
                overtime_secs = adjusted['overtime_seconds'] % 60
                info = self.tr(f"Part {part_num} is now {overtime_mins}:{overtime_secs:02d} into overtime.")
            else:
                mins = adjusted['remaining_seconds'] // 60
                secs = adjusted['remaining_seconds'] % 60
                info = self.tr(f"Resume at part {part_num} with {mins}:{secs:02d} remaining?")

            msg.setInformativeText(info)
            msg.setStandardButtons(
                QMessageBox.StandardButton.Yes |
                QMessageBox.StandardButton.No
            )
            msg.button(QMessageBox.StandardButton.Yes).setText(self.tr("Resume"))
            msg.button(QMessageBox.StandardButton.No).setText(self.tr("Start Fresh"))

            result = msg.exec()

            if result != QMessageBox.StandardButton.Yes:
                self.timer_controller.session_manager.clear_session()
                return

        # Restore the session
        self._restore_session(session)

    def _show_stale_session_dialog(self, session: SessionState):
        """Show dialog for stale session (crashed long ago)"""
        try:
            last_save = datetime.fromisoformat(session.last_save_time)
            date_str = last_save.strftime("%Y-%m-%d %H:%M")
        except (ValueError, TypeError):
            date_str = "unknown time"

        msg = QMessageBox(self)
        msg.setWindowTitle(self.tr("Old Session Found"))
        msg.setText(self.tr(f"A session from {date_str} was found."))
        msg.setInformativeText(self.tr("This session is quite old. Would you like to discard it or attempt recovery?"))
        msg.setStandardButtons(
            QMessageBox.StandardButton.Yes |
            QMessageBox.StandardButton.No
        )
        msg.button(QMessageBox.StandardButton.Yes).setText(self.tr("Discard"))
        msg.button(QMessageBox.StandardButton.No).setText(self.tr("Attempt Recovery"))

        if msg.exec() == QMessageBox.StandardButton.Yes:
            self.timer_controller.session_manager.clear_session()
        else:
            self._show_recovery_dialog(session)

    def _restore_session(self, session: SessionState):
        """Restore a meeting session from crash recovery"""
        from src.config import MEETINGS_DIR

        # Load the meeting
        meeting_path = MEETINGS_DIR / session.meeting_file
        if not meeting_path.exists():
            QMessageBox.warning(
                self,
                self.tr("Recovery Failed"),
                self.tr("Could not find the meeting file. Starting fresh.")
            )
            self.timer_controller.session_manager.clear_session()
            return

        meeting = self.meeting_controller._load_meeting_file(str(meeting_path))
        if not meeting:
            QMessageBox.warning(
                self,
                self.tr("Recovery Failed"),
                self.tr("Could not load the meeting file. Starting fresh.")
            )
            self.timer_controller.session_manager.clear_session()
            return

        # Set up the meeting in the controller

        # Update the meeting view if available
        if self.meeting_view:
            self.meeting_view.set_meeting(meeting)

        # Calculate adjusted state
        adjusted = self.timer_controller.session_manager.calculate_adjusted_state(session)

        # Restore the session state
        self.timer_controller.restore_session(session, adjusted)

        # Update UI
        self._update_ui_for_running_meeting()

        # Restore network broadcast if it was active
        logger.info("Session network_broadcast_active: %s", session.network_broadcast_active)
        if session.network_broadcast_active:
            QTimer.singleShot(500, self._restore_network_broadcast)

        # Show confirmation
        self.statusBar().showMessage(self.tr("Session restored successfully"), 5000)

    def _restore_network_broadcast(self):
        """Restore network broadcast after session recovery"""
        logger.info("Attempting to restore network broadcast...")

        if not self._is_component_ready('network_display_manager'):
            logger.info("Network display manager not ready, loading...")
            if hasattr(self, 'component_loader') and self.component_loader:
                self.component_loader.get_component('network_display_manager', blocking=True, timeout=5000)

            if not self._is_component_ready('network_display_manager'):
                logger.warning("Could not restore network broadcast - component not available")
                return

        # Check if already broadcasting
        if self.network_display_manager.broadcaster and self.network_display_manager.broadcaster.is_broadcasting:
            logger.info("Network broadcast already active, skipping restore")
            return

        # Start network display with settings
        from src.models.settings import NetworkDisplayMode
        mode = self.settings_controller.get_settings().network_display.mode
        http_port = self.settings_controller.get_settings().network_display.http_port
        ws_port = self.settings_controller.get_settings().network_display.ws_port

        logger.info("Network display mode from settings: %s", mode)

        # If mode is disabled but we know broadcast was active, use HTTP_ONLY as fallback
        if mode == NetworkDisplayMode.DISABLED:
            logger.info("Mode is DISABLED but broadcast was active, using HTTP_ONLY as fallback")
            mode = NetworkDisplayMode.HTTP_ONLY

        self.network_display_manager.start_network_display(mode, http_port, ws_port)
        self.toggle_network_action.setText(self.tr("Stop Network Display"))
        logger.info("Network broadcast restore initiated")

    def _update_ui_for_running_meeting(self):
        """Update UI elements to reflect a running meeting state"""
        # The meeting_started signal should have already triggered _meeting_started()
        # but call it explicitly to ensure UI is properly updated
        self._meeting_started()

    # ------------------------------------------------------------------
    # Ensure all child windows shut down cleanly when the main window
    # is closed (especially the secondary display, which otherwise keeps
    # running and may spawn duplicates next time).
    # ------------------------------------------------------------------
    def closeEvent(self, event):
        """Qt close handler – make sure secondary display and background
        tasks are cleaned up before the application quits."""
        # End session tracking cleanly (this deletes the session file on clean exit)
        try:
            if hasattr(self, 'timer_controller') and self.timer_controller.session_manager.has_active_session():
                self.timer_controller.session_manager.end_session(clean=True)
        except Exception as e:
            logger.error("Error ending session: %s", e)

        try:
            # Shut down the secondary display if it exists
            if hasattr(self, "secondary_display") and self.secondary_display:
                # Disconnect signals to avoid callbacks during teardown
                try:
                    self.timer_controller.meeting_countdown_updated.disconnect(
                        self.secondary_display._update_countdown
                    )
                except (TypeError, RuntimeError):
                    pass
                self.secondary_display.close()
                self.secondary_display.deleteLater()
                self.secondary_display = None
        except Exception as e:
            logger.error("Error closing secondary display: %s", e)

        # Also make sure the network display stops broadcasting
        if getattr(self, "network_display_manager", None):
            try:
                self.network_display_manager.stop_network_display()
            except Exception as e:
                logger.error("Error stopping network display: %s", e)

        # Finally proceed with the default close behavior
        super().closeEvent(event)
        
    def _on_secondary_screen_changed(self, *_):
        """Handle live updates to the selected secondary screen"""
        settings = self.settings_controller.get_settings()

        if not settings.display.use_secondary_screen:
            self._cleanup_secondary_display()
            self._update_secondary_display_label()
            return

        # Only continue if secondary display is enabled
        if not self.secondary_display:
            self._ensure_single_secondary_display()

        screen = ScreenHandler.get_configured_screen(settings, is_primary=False)
        if screen:
            QTimer.singleShot(500, lambda: self._move_secondary_display(screen))
        else:
            logger.warning("Could not resolve a valid screen for secondary display")

        self._update_secondary_display_label()

    def _move_secondary_display(self, screen):
        """Safely move the secondary display to the selected screen after a delay"""
        if not self.secondary_display or not screen:
            return

        # Insert user alert and log if secondary screen is the same as primary
        primary_screen = QApplication.primaryScreen()
        if screen == primary_screen:
            QTimer.singleShot(0, lambda: QMessageBox.information(
                self,
                self.tr("Same Screen Selected"),
                self.tr("The primary and secondary screens are the same. This may cause overlapping windows.")
            ))

        geometry = screen.geometry()
        self.secondary_display.setGeometry(geometry)
        self.secondary_display.show()
        QTimer.singleShot(200, lambda: self.secondary_display.showFullScreen())
        #print(f"[FIXED] Moved secondary display to screen: {screen.name()}")
    # The following methods were used for lazy-loading and are now removed:
    def show_attention_indicator(self):
        """Change tray icon to show a red badge or indicator"""
        from PyQt6.QtGui import QPixmap, QPainter, QColor
        base_icon = self.windowIcon().pixmap(64, 64)
        icon_with_badge = QPixmap(base_icon)
        painter = QPainter(icon_with_badge)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        radius = 10
        badge_color = QColor(220, 0, 0)
        painter.setBrush(badge_color)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(icon_with_badge.width() - radius * 2, 0, radius * 2, radius * 2)
        painter.setPen(QColor("white"))
        font = painter.font()
        font.setPointSize(10)
        painter.setFont(font)
        painter.drawText(icon_with_badge.width() - radius * 2, 0, radius * 2, radius * 2, Qt.AlignmentFlag.AlignCenter, "1")
        painter.end()
        self.tray_icon.setIcon(QIcon(icon_with_badge))

    def clear_attention_indicator(self):
        """Restore original tray icon without badge"""
        self.tray_icon.setIcon(self.windowIcon())

    def start_pulse_button(self, button_name):
        """Start pulsing the specified button continuously until stopped"""
        button = getattr(self, button_name, None)
        if button:
            self._pulse_widget(button)  # Call the already defined method

    def stop_pulse_button(self, button_name):
        """Stop all animations for the given button"""
        button = getattr(self, button_name, None)
        if button and hasattr(button, '_pulse_animations'):
            for anim in button._pulse_animations:
                anim.stop()
            button._pulse_animations.clear()
            if button.graphicsEffect():
                button.graphicsEffect().setOpacity(1.0)