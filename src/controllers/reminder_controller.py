"""
Reminder controller for handling meeting start and part overrun notifications.
"""
from PyQt6.QtCore import QObject, pyqtSignal, QTimer
from src.models.timer import TimerState

class ReminderController(QObject):
    """Controller for managing meeting reminders and notifications"""
    
    # Signals
    remind_to_start = pyqtSignal()  # Signal to remind user to start meeting
    remind_to_advance = pyqtSignal()  # Signal to remind user to advance to next part
    
    def __init__(self, timer_controller, settings_controller, meeting_controller, parent=None):
        super().__init__(parent)
        self.timer_controller = timer_controller
        self.settings_controller = settings_controller
        self.meeting_controller = meeting_controller
        
        # Reminder state
        self.waiting_for_start = False  # Whether we're waiting for meeting to start
        self.start_reminder_triggered = False  # Whether we've already shown the start reminder
        self.overrun_reminder_triggered = False  # Whether we've already shown the overrun reminder
        
        # Timers for delayed notifications
        self.start_reminder_timer = QTimer(self)
        self.start_reminder_timer.setSingleShot(True)
        self.start_reminder_timer.timeout.connect(self._trigger_start_reminder)
        
        self.overrun_reminder_timer = QTimer(self)
        self.overrun_reminder_timer.setSingleShot(True)
        self.overrun_reminder_timer.timeout.connect(self._trigger_overrun_reminder)
        
        # Connect to timer controller signals
        self._connect_signals()
    
    def _connect_signals(self):
        """Connect to timer controller signals"""
        # Connect to countdown start to know when a meeting is ready to start
        self.timer_controller.countdown_started.connect(self._on_countdown_started)
        
        # Connect to meeting start to know when the meeting has started
        self.timer_controller.meeting_started.connect(self._on_meeting_started)
        
        # Connect to timer state changes to track overtime
        self.timer_controller.timer.state_changed.connect(self._on_timer_state_changed)
        
        # Connect to settings changes to update reminder settings
        self.settings_controller.settings_changed.connect(self._on_settings_changed)
        
        # Also connect to part changed to clear overrun reminder when advancing parts
        self.timer_controller.part_changed.connect(self._on_part_changed)
    
    def _on_countdown_started(self, target_datetime):
        """Handle start of countdown to meeting"""
        self.waiting_for_start = True
        self.start_reminder_triggered = False

        import datetime
        now = datetime.datetime.now()

        # Always schedule the reminder based on settings delay
        self._start_reminder_timer(meeting_start_time=target_datetime)
    
    def _on_meeting_started(self):
        """Handle meeting start"""
        # Meeting has started, we're no longer waiting
        self.waiting_for_start = False
        self.start_reminder_triggered = False
        
        # Stop the start reminder timer if it's running
        if self.start_reminder_timer.isActive():
            self.start_reminder_timer.stop()
    
    def _on_timer_state_changed(self, state):
        """Handle timer state changes"""
        if state == TimerState.OVERTIME:
            self.overrun_reminder_triggered = False
            self._start_overrun_timer()
        elif state == TimerState.STOPPED:
            self.waiting_for_start = False
            self.start_reminder_triggered = False
            self.overrun_reminder_triggered = False
            if self.start_reminder_timer.isActive():
                self.start_reminder_timer.stop()
            if self.overrun_reminder_timer.isActive():
                self.overrun_reminder_timer.stop()
        elif state != TimerState.OVERTIME:
            self.overrun_reminder_triggered = False
            if self.overrun_reminder_timer.isActive():
                self.overrun_reminder_timer.stop()
    
    def _on_part_changed(self, part, index):
        """Handle part changes - reset overrun reminder"""
        self.overrun_reminder_triggered = False
        if self.overrun_reminder_timer.isActive():
            self.overrun_reminder_timer.stop()
    
    def _on_settings_changed(self):
        """Handle settings changes"""
        # We could restart timers with new durations, but for simplicity
        # we'll just let the next trigger update the timers with new settings
        settings = self.settings_controller.get_settings()
    
    def _start_reminder_timer(self, meeting_start_time=None):
        settings = self.settings_controller.get_settings()

        if not settings.start_reminder_enabled:
            pass
        if self.start_reminder_triggered:
            pass

        if settings.start_reminder_enabled and not self.start_reminder_triggered:
            delay_seconds = settings.start_reminder_delay

            # If we have a meeting start time, calculate delay from now to meeting start + delay
            if meeting_start_time:
                import datetime
                now = datetime.datetime.now()
                intended_time = meeting_start_time + datetime.timedelta(seconds=delay_seconds)
                delay = max(0, (intended_time - now).total_seconds()) * 1000  # milliseconds
            else:
                delay = delay_seconds * 1000

            if self.start_reminder_timer.isActive():
                self.start_reminder_timer.stop()

            self.start_reminder_timer.start(int(delay))
    
    def _start_overrun_timer(self):
        """Start the timer for part overrun reminder"""
        settings = self.settings_controller.get_settings()
        
        # Only start if enabled and not already triggered
        if settings.overrun_enabled and not self.overrun_reminder_triggered:
            # Get delay from settings (in seconds)
            delay = settings.overrun_delay * 1000  # Convert to milliseconds
            
            # Stop any existing timer
            if self.overrun_reminder_timer.isActive():
                self.overrun_reminder_timer.stop()
            
            # Start the timer
            self.overrun_reminder_timer.start(delay)
    
    def _trigger_start_reminder(self):
        """Trigger the reminder to start meeting"""
        if self.waiting_for_start and not self.start_reminder_triggered:
            self.start_reminder_triggered = True
            self.remind_to_start.emit()
    
    def _trigger_overrun_reminder(self):
        """Trigger the reminder to advance to next part"""
        if not self.overrun_reminder_triggered and self.timer_controller.timer.state == TimerState.OVERTIME:
            self.overrun_reminder_triggered = True
            self.remind_to_advance.emit()