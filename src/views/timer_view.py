"""
Timer view component for displaying the timer in both digital and analog formats.
"""
from datetime import datetime
import math
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QFrame, QSizePolicy
)
from PyQt6.QtCore import Qt, QSize, QRectF, QPointF
from PyQt6.QtGui import QPainter, QBrush, QPen, QColor, QFont, QPainterPath

from src.controllers.timer_controller import TimerController
from src.models.timer import TimerState, TimerDisplayMode


class TimerView(QWidget):
    """Widget for displaying the timer"""
    
    def __init__(self, timer_controller: TimerController, parent=None):
        super().__init__(parent)
        self.timer_controller = timer_controller
        
        self.show_clock = True # Flag to show/hide clock
        
        # Current display properties
        self.display_mode = TimerDisplayMode.DIGITAL
        self.remaining_seconds = 0
        self.timer_state = TimerState.STOPPED
        self.part_title = ""
        self.current_time = datetime.now().strftime("%H:%M:%S")  # Initialize with current time
        self.countdown_message = ""
        
        # Setup UI
        self._setup_ui()
        
        # Connect signals
        self._connect_signals()
    
    def _setup_ui(self):
        """Setup the UI components"""
        layout = QVBoxLayout(self)
        
        # Timer panel
        self.timer_panel = QFrame()
        self.timer_panel.setFrameShape(QFrame.Shape.StyledPanel)
        self.timer_panel.setMinimumHeight(200)
        self.timer_panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        
        # Current part label
        self.part_label = QLabel()
        self.part_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.part_label.setStyleSheet("font-size: 18px; font-weight: bold;")
        self.part_label.setWordWrap(True)
        self.part_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        
        # Countdown message label
        self.countdown_label = QLabel()
        self.countdown_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.countdown_label.setStyleSheet("font-size: 16px; color: #4a90e2; font-weight: bold;")
        self.countdown_label.setVisible(False)
        self.countdown_label.setWordWrap(True)
        self.countdown_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        
        layout.addWidget(self.timer_panel)
        layout.addWidget(self.part_label)
        layout.addWidget(self.countdown_label)
        
        # Set the digital display as default
        self._create_digital_display()
    
    def _connect_signals(self):
        """Connect controller signals"""
        self.timer_controller.timer.time_updated.connect(self._update_time)
        self.timer_controller.timer.state_changed.connect(self._update_state)
        self.timer_controller.part_changed.connect(self._update_part)
        self.timer_controller.timer.current_time_updated.connect(self._update_current_time)
        self.timer_controller.meeting_countdown_updated.connect(self._update_countdown)
        
    def clear_countdown_message(self):
        """Clear the countdown message"""
        if hasattr(self, "countdown_label"):
            self.countdown_label.setText("")
    
    def set_display_mode(self, mode: TimerDisplayMode):
        """Set the timer display mode"""
        if self.display_mode == mode:
            return
        
        self.display_mode = mode
        
        # Update the display
        if mode == TimerDisplayMode.DIGITAL:
            self._create_digital_display()
        else:
            self._create_analog_display()
        
        # Update the timer display
        self._update_display()
    
    def _create_digital_display(self):
        """Create digital timer display"""
        # Clear existing layout
        if self.timer_panel.layout():
            QWidget().setLayout(self.timer_panel.layout())
        
        layout = QVBoxLayout(self.timer_panel)
        
        # Digital timer label
        self.timer_label = QLabel(self.current_time)
        self.timer_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.timer_label.setStyleSheet("""
            font-size: 120px;
            font-weight: bold;
            font-family: 'Courier New', monospace;
        """)
        self.timer_label.setMinimumSize(0, 0)
        self.timer_label.setWordWrap(True)
        self.timer_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        
        layout.addWidget(self.timer_label)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
    
    def _update_current_time(self, time_str: str):
        """Update the displayed current time when allowed"""
        self.current_time = time_str

        # Show the clock only if (a) we are in STOPPED state and (b) the view
        # isn't currently suppressed by a running meeting.
        if self.timer_state == TimerState.STOPPED and self.show_clock:
            try:
                # Check if timer_label still exists
                if hasattr(self, "timer_label") and self.timer_label is not None:
                    self.timer_label.setText(time_str)
            except RuntimeError:
                # The widget was deleted - just ignore the update
                pass
            except Exception as e:
                # Log any other errors but don't crash
                print(f"Error updating timer label: {e}")
    
    def _update_countdown(self, seconds_remaining: int, message: str):
        """Update the countdown message"""
        self.countdown_message = message
        
        # Update part label if we're in stopped state
        if self.timer_state == TimerState.STOPPED:
            if seconds_remaining > 0:
                # Show countdown in part label
                self.part_label.setText(self.tr("MEETING STARTING SOON"))

                # Show countdown message
                self.countdown_label.setText(message)
                self.countdown_label.setVisible(True)
            else:
                self.countdown_label.setVisible(False)
        else:
            # Hide countdown when timer is running
            self.countdown_label.setVisible(False)
    
    def deleteLater(self):
        """Override deleteLater to properly clean up signal connections"""
        # Disconnect from timer signals
        try:
            if hasattr(self, "timer_controller") and self.timer_controller:
                self.timer_controller.timer.time_updated.disconnect(self._update_time)
                self.timer_controller.timer.state_changed.disconnect(self._update_state)
                self.timer_controller.part_changed.disconnect(self._update_part)
                self.timer_controller.timer.current_time_updated.disconnect(self._update_current_time)
                self.timer_controller.meeting_countdown_updated.disconnect(self._update_countdown)
        except (TypeError, RuntimeError):
            # Signal was not connected
            pass
        
        # Call the parent implementation
        super().deleteLater()
        
    
    def _create_analog_display(self):
        """Create analog timer display"""
        # Clear existing layout
        if self.timer_panel.layout():
            QWidget().setLayout(self.timer_panel.layout())
        
        layout = QVBoxLayout(self.timer_panel)
        
        # Analog clock widget
        self.analog_clock = AnalogClockWidget()
        
        layout.addWidget(self.analog_clock)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
    
    def _update_time(self, seconds: int):
        """Update the displayed time (count‑down / timer).  
        This should *always* run, regardless of the show_clock flag, because
        show_clock only suppresses the live clock when the meeting is stopped.
        """
        self.remaining_seconds = seconds
        self._update_display()
    
    def _update_state(self, state: TimerState):
        """Update the timer state"""
        self.timer_state = state
        self._update_display()
    
    def _update_part(self, part, index):
        """Update the current part"""
        self.part_title = part.title
        self.part_label.setText(part.title)
    
    def _update_display(self):
        """Update the timer display based on current values"""
        if self.display_mode == TimerDisplayMode.DIGITAL:
            self._update_digital_display()
        else:
            self._update_analog_display()
    
    def _update_digital_display(self):
        """Update the digital timer display with enhanced visibility"""
        if self.timer_state == TimerState.OVERTIME:
            # For overtime, show negative time
            seconds = abs(self.remaining_seconds)
            sign = "-"
            color_class = "digitalTimerDanger"
        else:
            seconds = abs(self.remaining_seconds)
            sign = ""
            
            # Set color based on state
            if self.timer_state == TimerState.RUNNING:
                if self.remaining_seconds <= 60:  # Last minute
                    color_class = "digitalTimerWarning"
                else:
                    color_class = "digitalTimerRunning"
            elif self.timer_state == TimerState.PAUSED:
                color_class = "digitalTimerPaused"
            elif self.timer_state == TimerState.TRANSITION:
                color_class = "digitalTimerTransition"
            else:  # STOPPED or COUNTDOWN
                color_class = "digitalTimerStopped"
        
        # Format time as mm:ss
        minutes = seconds // 60
        seconds = seconds % 60
        time_str = f"{sign}{minutes:02d}:{seconds:02d}"
        
        # Update label
        self.timer_label.setText(time_str)
        
        # Set object name for QSS styling
        self.timer_label.setObjectName(color_class)
        
        # Force style update
        self.timer_label.style().unpolish(self.timer_label)
        self.timer_label.style().polish(self.timer_label)
        self.timer_label.update()
    
    def _update_analog_display(self):
        """Update the analog timer display"""
        if hasattr(self, 'analog_clock'):
            self.analog_clock.set_time(self.remaining_seconds, self.timer_state)

    def resizeEvent(self, event):
        try:
            super().resizeEvent(event)
            width = self.width()

            # Resize timer label font
            if hasattr(self, "timer_label") and self.timer_label is not None:
                try:
                    timer_font_size = max(24, min(160, width // 8))
                    timer_font = self.timer_label.font()
                    timer_font.setPointSize(timer_font_size)
                    self.timer_label.setFont(timer_font)
                except RuntimeError:
                    # Widget was deleted, ignore
                    pass

            # Resize part label font
            if hasattr(self, "part_label") and self.part_label is not None:
                try:
                    part_font_size = max(12, min(36, width // 30))
                    part_font = self.part_label.font()
                    part_font.setPointSize(part_font_size)
                    self.part_label.setFont(part_font)
                except RuntimeError:
                    # Widget was deleted, ignore
                    pass

            # Resize countdown label font
            if hasattr(self, "countdown_label") and self.countdown_label is not None:
                try:
                    countdown_font_size = max(12, min(32, width // 32))
                    countdown_font = self.countdown_label.font()
                    countdown_font.setPointSize(countdown_font_size)
                    self.countdown_label.setFont(countdown_font)
                except RuntimeError:
                    # Widget was deleted, ignore
                    pass
        except Exception as e:
        # Catch any other exceptions to prevent crashes
            print(f"Error in TimerView.resizeEvent: {e}")


class AnalogClockWidget(QWidget):
    """Widget for displaying an analog clock/timer"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        
        # Timer properties
        self.seconds = 0
        self.total_seconds = 0
        self.state = TimerState.STOPPED
        
        # Set minimum size
        self.setMinimumSize(200, 200)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
    
    def set_time(self, seconds: int, state: TimerState):
        """Set the time to display"""
        self.seconds = abs(seconds)
        self.state = state
        self.update()  # Trigger repaint
    
    def set_total_time(self, seconds: int):
        """Set the total time for the timer"""
        self.total_seconds = seconds
    
    def paintEvent(self, event):
        """Paint the analog clock"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Calculate clock dimensions
        width = self.width()
        height = self.height()
        size = min(width, height) - 10
        
        # Center the clock
        x_center = width / 2
        y_center = height / 2
        
        # Draw clock face
        self._draw_clock_face(painter, x_center, y_center, size / 2)
        
        # Draw minute and second hands
        minutes = self.seconds // 60
        seconds = self.seconds % 60
        
        self._draw_minute_hand(painter, x_center, y_center, size / 2, minutes)
        self._draw_second_hand(painter, x_center, y_center, size / 2, seconds)
        
        # Draw digital time in the middle
        self._draw_digital_time(painter, x_center, y_center, minutes, seconds)
        
        painter.end()
    
    def _draw_clock_face(self, painter, x_center, y_center, radius):
        """Draw the clock face"""
        # Choose color based on timer state
        if self.state == TimerState.OVERTIME:
            face_color = QColor(255, 200, 200)  # Light red
            border_color = QColor(255, 0, 0)    # Red
        elif self.state == TimerState.RUNNING:
            if self.seconds <= 60:  # Last minute
                face_color = QColor(255, 240, 200)  # Light orange
                border_color = QColor(255, 165, 0)  # Orange
            else:
                face_color = QColor(200, 255, 200)  # Light green
                border_color = QColor(0, 128, 0)    # Green
        elif self.state == TimerState.PAUSED:
            face_color = QColor(200, 200, 255)  # Light blue
            border_color = QColor(0, 0, 255)    # Blue
        else:  # STOPPED or COUNTDOWN
            face_color = QColor(240, 240, 240)  # Light gray
            border_color = QColor(100, 100, 100)  # Dark gray
        
        # Draw clock face
        painter.setPen(QPen(border_color, 2))
        painter.setBrush(QBrush(face_color))
        painter.drawEllipse(QPointF(x_center, y_center), radius, radius)
        
        # Draw minute markers
        painter.setPen(QPen(QColor(0, 0, 0), 1))
        for i in range(60):
            angle = math.radians(i * 6 - 90)  # 6 degrees per minute, -90 to start at top
            
            # Draw longer lines for every 5 minutes
            if i % 5 == 0:
                inner_radius = radius * 0.85
                # Draw minute numbers
                number_radius = radius * 0.7
                number_x = x_center + number_radius * math.cos(angle)
                number_y = y_center + number_radius * math.sin(angle)
                
                # Skip 0/60 position (put at top)
                minute_number = i // 5
                if minute_number == 0:
                    minute_number = 12
                
                # Draw number
                painter.save()
                painter.translate(number_x, number_y)
                painter.rotate(i * 6)  # Rotate text to be parallel with clock edge
                painter.drawText(QRectF(-20, -10, 40, 20), Qt.AlignmentFlag.AlignCenter, str(minute_number * 5))
                painter.restore()
            else:
                inner_radius = radius * 0.9
            
            # Calculate line positions
            x1 = x_center + inner_radius * math.cos(angle)
            y1 = y_center + inner_radius * math.sin(angle)
            x2 = x_center + radius * math.cos(angle)
            y2 = y_center + radius * math.sin(angle)
            
            # Draw line
            painter.drawLine(int(x1), int(y1), int(x2), int(y2))
    
    def _draw_minute_hand(self, painter, x_center, y_center, radius, minutes):
        """Draw the minute hand"""
        painter.setPen(QPen(QColor(0, 0, 0), 3))
        
        # Calculate angle (0 minutes is at the top, and moves clockwise)
        angle = math.radians(minutes * 6 - 90)  # 6 degrees per minute, -90 to start at top
        
        # Calculate hand position
        hand_length = radius * 0.7
        x = x_center + hand_length * math.cos(angle)
        y = y_center + hand_length * math.sin(angle)
        
        # Draw hand
        painter.drawLine(int(x_center), int(y_center), int(x), int(y))
    
    def _draw_second_hand(self, painter, x_center, y_center, radius, seconds):
        """Draw the second hand"""
        painter.setPen(QPen(QColor(255, 0, 0), 1))
        
        # Calculate angle (0 seconds is at the top, and moves clockwise)
        angle = math.radians(seconds * 6 - 90)  # 6 degrees per second, -90 to start at top
        
        # Calculate hand position
        hand_length = radius * 0.8
        x = x_center + hand_length * math.cos(angle)
        y = y_center + hand_length * math.sin(angle)
        
        # Draw hand
        painter.drawLine(int(x_center), int(y_center), int(x), int(y))
    
    def _draw_digital_time(self, painter, x_center, y_center, minutes, seconds):
        """Draw digital time in the center"""
        # Set up text properties
        painter.setPen(QColor(0, 0, 0))
        font = QFont("Arial", 12, QFont.Weight.Bold)
        painter.setFont(font)
        
        # Format time
        if self.state == TimerState.OVERTIME:
            time_text = f"-{minutes:02d}:{seconds:02d}"
        else:
            time_text = f"{minutes:02d}:{seconds:02d}"
        
        # Draw text
        painter.drawText(
            QRectF(x_center - 40, y_center + 20, 80, 30),
            Qt.AlignmentFlag.AlignCenter,
            time_text
        )
    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "timer_label"):
            width = self.timer_label.width()
            # Calculate font size dynamically (you can tweak the scaling factor)
            font_size = max(24, min(160, width // 8))
            font = self.timer_label.font()
            font.setPointSize(font_size)
            self.timer_label.setFont(font)