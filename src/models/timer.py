"""
Timer model for the OnTime Meeting Timer application.
"""
import time
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional, Callable
from PyQt6.QtCore import QObject, QTimer, pyqtSignal


class TimerState(Enum):
    """Possible states for the timer"""
    STOPPED = 0
    RUNNING = 1
    PAUSED = 2
    OVERTIME = 3
    COUNTDOWN = 4  # Countdown to meeting start
    TRANSITION = 5  # Chairman transition between parts


class TimerDisplayMode(Enum):
    """Display modes for the timer"""
    DIGITAL = 0
    ANALOG = 1


class Timer(QObject):
    """Timer model for tracking time during meeting parts"""
    
    # Signals
    time_updated = pyqtSignal(int)  # Emits remaining seconds
    state_changed = pyqtSignal(TimerState)
    current_time_updated = pyqtSignal(str)  # signal for current time updates
    
    def __init__(self):
        super().__init__()
        
        # Timer properties
        self._total_seconds = 0
        self._remaining_seconds = 0
        self._start_time = None
        self._elapsed_time = 0
        self._state = TimerState.STOPPED
        
        # Current time and countdown properties
        self._target_meeting_time = None
        self._current_time_timer = QTimer(self)
        self._current_time_timer.setInterval(1000)  # Update every second
        self._current_time_timer.timeout.connect(self._update_current_time)
        self._current_time_timer.start()
        
        # Initial current time update
        self._update_current_time()
        
        # Qt timer for updates
        self._timer = QTimer(self)
        self._timer.setInterval(100)  # Update every 100ms for smooth display
        self._timer.timeout.connect(self._update_timer)
        
    @property
    def state(self) -> TimerState:
        """Get current timer state"""
        return self._state
    
    @property
    def remaining_seconds(self) -> int:
        """Get remaining seconds"""
        return self._remaining_seconds
    
    @property
    def total_seconds(self) -> int:
        """Get total seconds"""
        return self._total_seconds
    
    @property
    def elapsed_seconds(self) -> int:
        """Get elapsed seconds"""
        return self._total_seconds - self._remaining_seconds
    
    @property
    def progress_percentage(self) -> float:
        """Get progress as percentage (0-100)"""
        if self._total_seconds == 0:
            return 0
        return (self.elapsed_seconds / self._total_seconds) * 100
    
    def _update_current_time(self):
        """Update and emit the current time"""
        current_time = datetime.now().strftime("%H:%M:%S")
        self.current_time_updated.emit(current_time)
        
    def start_current_time_display(self):
        """Start displaying current time"""
        # Ensure the timer is in STOPPED state
        if self._state != TimerState.STOPPED:
            self._state = TimerState.STOPPED
            self.state_changed.emit(self._state)
        
        # Make sure the current time timer is running
        if not self._current_time_timer.isActive():
            self._current_time_timer.start()
        
        # Force an immediate update
        self._update_current_time()
                
    def set_meeting_target_time(self, target_datetime: datetime):
        """Set the target meeting time for countdown display"""
        self._target_meeting_time = target_datetime
        # Force an immediate update of the countdown
        self._update_current_time()
    
    def start(self, duration_seconds: int):
        """Start the timer with a given duration"""
        self._total_seconds = duration_seconds
        self._remaining_seconds = duration_seconds
        self._start_time = time.time()
        self._elapsed_time = 0
        self._state = TimerState.RUNNING
        self.state_changed.emit(self._state)
        self.time_updated.emit(self._remaining_seconds)
        self._timer.start()
    
    def pause(self):
        """Pause the timer"""
        if self._state == TimerState.RUNNING:
            self._timer.stop()
            self._elapsed_time += time.time() - self._start_time
            self._state = TimerState.PAUSED
            self.state_changed.emit(self._state)
    
    def resume(self):
        """Resume a paused timer"""
        if self._state == TimerState.PAUSED:
            self._start_time = time.time()
            self._state = TimerState.RUNNING
            self.state_changed.emit(self._state)
            self._timer.start()
    
    def stop(self):
        """Stop the timer"""
        self._timer.stop()
        self._state = TimerState.STOPPED
        self.state_changed.emit(self._state)
        self._remaining_seconds = 0
        self.time_updated.emit(self._remaining_seconds)
        # Update to show current time when stopped
        self._update_current_time()
    
    def reset(self):
        """Reset the timer without stopping it"""
        was_running = self._state == TimerState.RUNNING
        self._timer.stop()
        self._start_time = time.time() if was_running else None
        self._elapsed_time = 0
        self._remaining_seconds = self._total_seconds
        self.time_updated.emit(self._remaining_seconds)
        
        if was_running:
            self._timer.start()
    
    def adjust_time(self, seconds_delta: int):
        """Adjust the timer by adding/subtracting seconds"""
        new_total = max(0, self._total_seconds + seconds_delta)
        
        # Calculate new remaining time proportionally
        if self._state != TimerState.STOPPED:
            elapsed_percentage = self.elapsed_seconds / self._total_seconds if self._total_seconds > 0 else 0
            self._remaining_seconds = int(new_total * (1 - elapsed_percentage))
        else:
            self._remaining_seconds = new_total
            
        self._total_seconds = new_total
        self.time_updated.emit(self._remaining_seconds)
    
    def set_remaining_time(self, seconds: int):
        """Directly set the remaining time"""
        self._remaining_seconds = max(0, min(seconds, self._total_seconds))
        self.time_updated.emit(self._remaining_seconds)
        
        # Check if we need to change state to OVERTIME
        if self._remaining_seconds == 0 and self._state == TimerState.RUNNING:
            self._state = TimerState.OVERTIME
            self.state_changed.emit(self._state)
    
    def start_countdown(self, target_datetime: datetime):
        """Start a countdown to a specific date/time"""
        self._state = TimerState.COUNTDOWN
        self.state_changed.emit(self._state)
        
        # Set the target meeting time
        self._target_meeting_time = target_datetime
        
        # Calculate initial remaining time
        now = datetime.now()
        time_diff = target_datetime - now
        
        if time_diff.total_seconds() <= 0:
            self.stop()
            return
        
        self._total_seconds = int(time_diff.total_seconds())
        self._remaining_seconds = self._total_seconds
        self._start_time = time.time()
        self._elapsed_time = 0
        
        self.time_updated.emit(self._remaining_seconds)
        self._timer.start()
    
    def _update_timer(self):
        """Update timer calculations (called by QTimer)"""
        if self._state == TimerState.RUNNING:
            # Normal running timer (counting down)
            elapsed = self._elapsed_time + (time.time() - self._start_time)
            self._remaining_seconds = max(0, int(self._total_seconds - elapsed))
            
            # Check if timer has expired
            if self._remaining_seconds == 0:
                self._state = TimerState.OVERTIME
                self.state_changed.emit(self._state)
            
            self.time_updated.emit(self._remaining_seconds)
            
        elif self._state == TimerState.OVERTIME:
            # In overtime, we count up from zero
            elapsed = self._elapsed_time + (time.time() - self._start_time)
            overtime_seconds = int(elapsed - self._total_seconds)
            
            # For overtime, we emit negative values
            self._remaining_seconds = -overtime_seconds
            self.time_updated.emit(self._remaining_seconds)
            
        elif self._state == TimerState.COUNTDOWN:
            # Countdown to meeting start
            now = time.time()
            elapsed = now - self._start_time
            self._remaining_seconds = max(0, int(self._total_seconds - elapsed))
            if self._remaining_seconds == 0:
                self.stop()
                
            self.time_updated.emit(self._remaining_seconds)
    
    def set_duration(self, new_duration_minutes: int):
        """Adjust total duration of the running timer while preserving elapsed time"""
        if self.state in [TimerState.RUNNING, TimerState.PAUSED]:
            self._total_seconds = new_duration_minutes * 60
            self._update_timer()
    @property
    def target_meeting_time(self) -> Optional[datetime]:
        """Get or set the target meeting time for countdowns."""
        return self._target_meeting_time

    @target_meeting_time.setter
    def target_meeting_time(self, value: datetime):
        self._target_meeting_time = value