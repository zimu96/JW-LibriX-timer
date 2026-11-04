"""
Secondary display window for the OnTime - Speaker View.
A streamlined, distraction-free fullscreen view focusing on timer and next part.
"""
import traceback
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QLabel, 
    QSizePolicy, QFrame, QApplication
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QPalette, QColor, QFont

from src.controllers.timer_controller import TimerController
from src.models.timer import TimerState
from src.views.timer_view import TimerView


class SecondaryDisplay(QMainWindow):
    """Secondary display window for the timer - designed for speakers"""

    def __init__(self, timer_controller: TimerController, settings_controller, parent=None):
        
        super().__init__(parent, Qt.WindowType.Window)
        self.timer_controller = timer_controller
        self.settings_controller = settings_controller
        # Controls whether the live clock is allowed to update the label
        self.show_clock: bool = True
        self.next_part = None
        self._show_countdown = False
        self._positioning_in_progress = False

        # Set the window to delete on close
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        
        # Set window flags for presentation display - fullscreen with no chrome
        self.setWindowFlags(Qt.WindowType.Window)

        # Setup UI
        self._setup_ui()

        # Connect signals
        self._connect_signals()
        # Show the pre‑meeting countdown right from the start
        self.show_countdown = True

        # Connect settings changed signal
        self.settings_controller.settings_changed.connect(self._on_settings_updated)
    
    def _setup_ui(self):
        """Setup the UI components"""
        # Set application icon
        from src.utils.resources import get_icon
        self.setWindowIcon(get_icon("app_icon"))
        
        self.setWindowTitle("OnTime - Speaker View")
        
        # Set default background to black
        palette = self.palette()
        palette.setColor(QPalette.ColorRole.Window, QColor(0, 0, 0))
        palette.setColor(QPalette.ColorRole.WindowText, QColor(255, 255, 255))
        self.setPalette(palette)
        
        # Style the secondary display with high contrast regardless of theme
        self.setStyleSheet("""
            QMainWindow, QWidget {
                background-color: #000000;
                color: #ffffff;
            }
            
            QLabel {
                color: #ffffff;
                font-weight: bold;
            }
            
            QFrame {
                background-color: rgba(50, 50, 50, 150);
                border: 1px solid #ffffff;
                border-radius: 15px;
            }
        """)
        
        # Central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Main layout with ample margins for readability
        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(40, 20, 40, 20)
        layout.setSpacing(30)
        
        # Large digital timer display - very prominent
        self.timer_view = TimerView(self.timer_controller)
        #self.timer_view.setMinimumHeight(400)
        
        
        self.timer_frame = QFrame()
        self.timer_frame.setFrameShape(QFrame.Shape.StyledPanel)
        self.timer_frame.setStyleSheet("""
            background-color: #000000;
            border: 2px solid #333333;
            border-radius: 15px;
        """)
        
        timer_layout = QVBoxLayout(self.timer_frame)
        
        self.timer_label = QLabel("")
        self.timer_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.timer_label.setStyleSheet("""
            color: #ffffff;
            font-weight: bold;
            font-family: 'Tahoma', 'Arial Black', sans-serif;
            padding: 0px;
            margin: 0px;
        """)
        self.timer_label.setMinimumSize(0, 0)
        self.timer_label.setWordWrap(True)
        self.timer_label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        
        timer_layout.addWidget(self.timer_label)
        
        # Combined information panel for next part and predicted end time
        # Single info panel below the timer
        self.info_frame = QFrame()
        self.info_frame.setFrameShape(QFrame.Shape.StyledPanel)
        
        info_layout = QVBoxLayout(self.info_frame)
        info_layout.setSpacing(10)
        
        # Label for either countdown message or next part/predicted end
        self.info_label1 = QLabel()
        self.info_label1.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.info_label1.setStyleSheet("""
            color: #ffffff;
            font-weight: bold;
        """)
        self.info_label1.setMinimumSize(0, 0)
        self.info_label1.setWordWrap(True)
        self.info_label1.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self.info_label2 = QLabel()
        self.info_label2.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # Match info_label1 size
        self.info_label2.setStyleSheet("""
            color: #ff4d4d;
            font-weight: bold;
        """)
        self.info_label2.setMinimumSize(0, 0)
        self.info_label2.setWordWrap(True)
        self.info_label2.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        info_layout.addWidget(self.info_label1)
        info_layout.addWidget(self.info_label2)
        
        # Add the main components to the layout
        layout.addWidget(self.timer_frame, 10)  # Timer gets more vertical space
        layout.addWidget(self.info_frame, 1)   # Info panel gets less vertical space
        
    
    def _connect_signals(self):
        """Connect controller signals"""
        self.timer_controller.timer.time_updated.connect(self._update_time)
        self.timer_controller.timer.state_changed.connect(self._update_timer_state)
        self.timer_controller.part_changed.connect(self._part_changed)
        self.timer_controller.transition_started.connect(self._transition_started)
        self.timer_controller.predicted_end_time_updated.connect(self._update_predicted_end_time)
        self.timer_controller.meeting_started.connect(self._meeting_started)
        self.timer_controller.meeting_ended.connect(self._meeting_ended)
        self.timer_controller.meeting_countdown_updated.connect(self._update_countdown)
        self.timer_controller.timer.current_time_updated.connect(self._update_current_time)
    
    def show_on_configured_screen_safely(self):
        """Public method for main window to safely show secondary display"""
        if self._positioning_in_progress:
            return
        self._positioning_in_progress = True

        # Step 1: Show as normal window first
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, False)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, False)
        self.showNormal()
        
        # Step 2: Position on target screen
        QTimer.singleShot(200, self._apply_screen_positioning)
        
    def _apply_screen_positioning(self):
        """Apply screen positioning after initial show"""
        from src.utils.screen_handler import ScreenHandler
        
        settings = self.settings_controller.get_settings()
        target_screen = ScreenHandler.get_configured_screen(settings, is_primary=False)
        
        if target_screen:
            # Use the enhanced screen handler
            success = ScreenHandler.safe_bind_to_screen(self, target_screen)
            if success:
                print(f"[SecondaryDisplay] Successfully bound to {target_screen.name()}")
            else:
                print(f"[SecondaryDisplay] Failed to bind to {target_screen.name()}")
        
        # Step 3: Make frameless after positioning
        QTimer.singleShot(300, self._make_frameless)
    
    def _make_frameless(self):
        """Make window frameless after positioning"""
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
        self.show()  # Re-show to apply frameless
        
        # Step 4: Enable stay-on-top
        QTimer.singleShot(200, self._enable_stay_on_top)
    
    def _enable_stay_on_top(self):
        """Enable stay-on-top after frameless is applied"""
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self.show()  # Re-show to apply stay-on-top
        
        # Step 5: Go fullscreen as final step
        QTimer.singleShot(300, self._go_fullscreen_final)
    
    def _go_fullscreen_final(self):
        """Final step: go fullscreen with verification"""
        from src.utils.screen_handler import ScreenHandler
        
        settings = self.settings_controller.get_settings()
        target_screen = ScreenHandler.get_configured_screen(settings, is_primary=False)
        
        # Double-check we're on the right screen before fullscreen
        if target_screen and not ScreenHandler.verify_screen_binding(self, target_screen):
            ScreenHandler.safe_bind_to_screen(self, target_screen)
        
        # Go fullscreen
        self.showFullScreen()
        self._positioning_in_progress = False
        
        # Apply screen optimizations after fullscreen
        QTimer.singleShot(200, self._apply_screen_optimizations)
    
    
        
    def _update_current_time(self, time_str: str):
        """Update the current time display when in stopped state"""
        if (self.timer_controller.timer.state == TimerState.STOPPED or self.show_countdown) and self.show_clock:
            if self.timer_label.text() != time_str:
                self.timer_label.setText(time_str)
                self.timer_label.setStyleSheet("""
                    color: #ffffff;
                    font-weight: bold;
                """)
                self._adjust_font_sizes()
    
    def _update_countdown(self, seconds_remaining: int, message: str):
        """Update the countdown message"""

        # Guard clause: If meeting is not stopped or meeting has started, never show countdown
        if self.timer_controller.timer.state != TimerState.STOPPED or self.timer_controller.current_part_index >= 0:
            self.show_countdown = False
            self._show_countdown = False
            return

        # Block all updates unless explicitly in countdown mode (use internal flag strictly)
        if not getattr(self, "_show_countdown", False):
            return

        if seconds_remaining > 0:
            if self.info_label1.text() != message.upper():
                self.info_label1.setText(message.upper())
            self.info_label2.setText("")
        else:
            # Countdown ended
            self.show_countdown = False
            self._show_countdown = False
            if self.timer_controller.timer.state == TimerState.STOPPED and self.timer_controller.current_part_index == -1:
                self.info_label1.setText("")
                self.info_label2.setText("")
                
    
    def _update_time(self, seconds: int):
        """Update the timer display"""
        if seconds < 0:
            minutes = abs(seconds) // 60
            secs = abs(seconds) % 60
            time_str = f"-{minutes:02d}:{secs:02d}"
            color = "#ff4d4d"
        else:
            minutes = seconds // 60
            secs = seconds % 60
            time_str = f"{minutes:02d}:{secs:02d}"
            if seconds <= 60:
                color = "#ffaa00"
            else:
                color = "#00cc00"

        if self.timer_controller.timer.state != TimerState.STOPPED:
            if self.timer_label.text() != time_str:
                self.timer_label.setText(time_str)
                self.timer_label.setStyleSheet(f"""
                    color: {color};
                    font-weight: bold;
                """)
                self._adjust_font_sizes()
    
    def _update_timer_state(self, state: TimerState):
        """Update UI based on timer state"""
        if state == TimerState.PAUSED:
            # Blue color for paused state
            self.timer_label.setStyleSheet("""
                color: #3399ff;
                font-weight: bold;
            """)
        elif state == TimerState.TRANSITION:
            # Purple color for transition state
            self.timer_label.setStyleSheet("""
                color: #bb86fc;
                font-weight: bold;
            """)
    
    def _part_changed(self, current_part, index):
        """Update display when current part changes"""
        # We're in a meeting, show next part and predicted end
        self.show_countdown = False

        # Update next part information
        parts = self.timer_controller.parts_list

        # Check if there's a next part
        if index + 1 < len(parts):
            self.next_part = parts[index + 1]
            # Format text once and cache to prevent flickering
            next_part_text = f"{self.tr('NEXT PART')}: {self.next_part.title.upper()}"
            formatted_text = self._format_text_for_display_stable(next_part_text)
            
            # Only update if text actually changed
            if self.info_label1.text() != formatted_text:
                self.info_label1.setText(formatted_text)
                self.info_label1.setStyleSheet("""
                    color: #ffffff;
                    font-weight: bold;
                """)
        else:
            # No next part (this is the last part)
            self.next_part = None
            if self.info_label1.text() != "LAST PART":
                self.info_label1.setText(self.tr("LAST PART"))
                self.info_label1.setStyleSheet("""
                    color: #ffffff;
                    font-weight: bold;
                """)
    
    def _transition_started(self, transition_msg):
        """Handle chairman transition"""
        # In transition mode, show the upcoming part
        if self.next_part:
            # No need to change what's displayed, as we're already showing the next part
            pass
        else:
            # If this is the last transition
            formatted_text = self._format_text_for_display_stable(self.tr("MEETING CONCLUSION"))
            if self.info_label1.text() != formatted_text:
                self.info_label1.setText(formatted_text)

    def _update_predicted_end_time(self, original_end_time, predicted_end_time, target_end_time):
        """Display predicted end time compared to organizational target"""

        # Don't show predicted end during countdown
        if self.show_countdown:
            self.info_label2.setText("")
            return

        # Format predicted time in 12-hour format (e.g., 8:50 PM)
        predicted_time_str = predicted_end_time.strftime("%I:%M %p").lstrip('0')
        target_time_str = target_end_time.strftime("%I:%M %p").lstrip('0')

        # Calculate difference from TARGET (not template)
        time_diff = predicted_end_time - target_end_time
        diff_seconds = int(time_diff.total_seconds())
        diff_minutes = abs(diff_seconds) // 60

        # Color-coding based on target:
        # GREEN: Within 2 min of target (acceptable variance)
        # ORANGE: 3-5 min over target (caution)
        # RED: >5 min over target (concerning)

        if diff_seconds > 300:  # >5 min late
            status_text = f"{diff_minutes} min{'s' if diff_minutes != 1 else ''} over ⚠️"
            color = "#ff4d4d"  # Red
        elif diff_seconds > 120:  # 2-5 min late
            status_text = f"{diff_minutes} min{'s' if diff_minutes != 1 else ''} over"
            color = "#ffaa00"  # Orange
        elif diff_seconds > -120:  # Within ±2 min
            status_text = "On Time"
            color = "#4caf50"  # Green
        else:  # >2 min early
            status_text = f"{diff_minutes} min{'s' if diff_minutes != 1 else ''} early"
            color = "#4caf50"  # Green

        # Format: "Predicted End: 8:50 PM | 5 mins over"
        time_text = f"Predicted End: {predicted_time_str} | {status_text}"

        self.info_label2.setText(time_text.upper())
        self.info_label2.setStyleSheet(f"color: {color}; font-weight: bold;")

        # Tooltip shows target time for reference
        self.info_label2.setToolTip(f"Target finish: {target_time_str}")
        
    def _meeting_started(self):
        """Handle meeting start event"""
        # Suppress the real‑time clock while the meeting is running
        self.show_clock = False
        # Meeting started, switch from countdown to part info
        self.show_countdown = False
        # Make absolutely sure any countdown text disappears as soon as the
        # meeting begins.
        self.info_label1.clear()
        self.info_label2.clear()
        try:
            self.timer_controller.meeting_countdown_updated.disconnect(self._update_countdown)
        except TypeError:
            print("[DEBUG] Signal already disconnected or not connected")

        # Set initial next part info with stable formatting
        if len(self.timer_controller.parts_list) > 1:
            next_part = self.timer_controller.parts_list[1]
            next_part_text = f"{self.tr('NEXT PART')}: {next_part.title.upper()}"
            formatted_text = self._format_text_for_display_stable(next_part_text)
            self.info_label1.setText(formatted_text)
            self.info_label1.setStyleSheet("""
                color: #ffffff;
                font-weight: bold;
            """)
            # Show the info labels for meeting info
            self.info_label2.setVisible(True)
        else:
            # No next part (only one part in the meeting)
            self.info_label1.setText(self.tr("LAST PART"))
            self.info_label2.setVisible(True)

        # Force‑refresh the "next part" panel in case the part‑changed signal
        # was emitted before we connected to it.
        current_index = self.timer_controller.current_part_index
        if current_index < 0 and self.timer_controller.parts_list:
            # Meeting just started, so part 0 is active.
            current_index = 0
        if 0 <= current_index < len(self.timer_controller.parts_list):
            self._part_changed(self.timer_controller.parts_list[current_index],
                               current_index)
    
    def _meeting_ended(self):
        """Handle meeting end"""
        # Re‑enable the clock after the meeting ends
        self.show_clock = True
        self.show_countdown = False
        # Show meeting completed message
        self.info_label1.setText(self.tr("MEETING COMPLETED"))
        self.info_label2.setText("")
        # Re‑enable the countdown signal for the next meeting
        try:
            self.timer_controller.meeting_countdown_updated.connect(
                self._update_countdown,  # type: ignore[arg-type]
            )
        except TypeError:
            # Already connected
            pass
              
                
    def _apply_screen_optimizations(self):
        """Apply all screen-specific optimizations"""
        self._optimize_layout_for_screen()
        self._constrain_info_labels_width()
        self._adjust_font_sizes()
    
    def _optimize_layout_for_screen(self):
        """Optimize layout proportions based on screen aspect ratio"""
        if not self.screen():
            return
        
        geometry = self.screen().geometry()
        width = geometry.width()
        height = geometry.height()
        aspect_ratio = width / height if height > 0 else 1.78
        
        # Adjust layout proportions based on screen characteristics
        if aspect_ratio > 2.0:  # Ultra-wide screens
            timer_proportion = 80
            info_proportion = 20
        elif aspect_ratio < 1.3:  # Portrait or square screens
            timer_proportion = 70
            info_proportion = 30
        else:  # Standard widescreen
            timer_proportion = 75
            info_proportion = 25
        
        # Apply the proportions
        layout = self.centralWidget().layout()
        if layout and layout.count() >= 2:
            layout.setStretchFactor(self.timer_frame, timer_proportion)
            layout.setStretchFactor(self.info_frame, info_proportion)
    
    def _constrain_info_labels_width(self):
        """Ensure info labels don't exceed screen boundaries"""
        if not hasattr(self, 'info_label1') or not hasattr(self, 'info_label2'):
            return
        
        screen_width = self.width()
        max_label_width = int(screen_width * 0.95)
        
        for label in [self.info_label1, self.info_label2]:
            if label and label.isVisible():
                label.setMaximumWidth(max_label_width)
                label.setWordWrap(True)
    
    def _format_text_for_display(self, text, max_length=60):
        """Format text to prevent overflow, breaking long text intelligently"""
        if not text or len(text) <= max_length:
            return text
        
        # Try to break at natural points
        if ' - ' in text:
            parts = text.split(' - ')
            if len(parts) == 2:
                return f"{parts[0]}\n{parts[1]}"
        
        if ': ' in text and text.count(': ') == 1:
            parts = text.split(': ')
            if len(parts) == 2 and len(parts[0]) < 20:
                return f"{parts[0]}:\n{parts[1]}"
        
        # Break at roughly half-way point at a space
        words = text.split()
        if len(words) > 1:
            mid_point = len(words) // 2
            line1 = " ".join(words[:mid_point])
            line2 = " ".join(words[mid_point:])
            
            # If either line is still too long, truncate
            if len(line1) > max_length // 2:
                line1 = line1[:max_length // 2 - 3] + "..."
            if len(line2) > max_length // 2:
                line2 = line2[:max_length // 2 - 3] + "..."
                
            return f"{line1}\n{line2}"
        
        # Single word that's too long - truncate
        return text[:max_length - 3] + "..."
    
    def _format_text_for_screen_width(self, text, available_width, font_size):
        """Format text specifically for screen width constraints"""
        if not text:
            return text
        
        from PyQt6.QtGui import QFontMetrics, QFont
        
        # Create a test font to measure text
        test_font = QFont()
        test_font.setPointSize(font_size)
        metrics = QFontMetrics(test_font)
        
        # If text fits on one line, return as is
        if metrics.horizontalAdvance(text) <= available_width:
            return text
        
        # Try intelligent breaking points
        break_patterns = [
            (' - ', '\n'),
            (': ', ':\n'),
            (' | ', '\n'),
            (' / ', '\n'),
        ]
        
        for pattern, replacement in break_patterns:
            if pattern in text:
                parts = text.split(pattern)
                if len(parts) == 2:
                    test_text = parts[0] + replacement + parts[1]
                    lines = test_text.split('\n')
                    if all(metrics.horizontalAdvance(line) <= available_width for line in lines):
                        return test_text
        
        # Break at word boundaries
        words = text.split()
        if len(words) > 1:
            # Find the best break point
            for i in range(1, len(words)):
                line1 = ' '.join(words[:i])
                line2 = ' '.join(words[i:])
                
                if (metrics.horizontalAdvance(line1) <= available_width and 
                    metrics.horizontalAdvance(line2) <= available_width):
                    return f"{line1}\n{line2}"
        
        # If nothing works, truncate with ellipsis
        max_chars = len(text)
        for i in range(len(text), 0, -1):
            test_text = text[:i] + "..."
            if metrics.horizontalAdvance(test_text) <= available_width:
                return test_text
        
        return text[:10] + "..."  # Emergency fallback
    
    def _adjust_font_sizes(self):
        """Prioritize timer visibility and constrain info labels appropriately"""
        if not self.isVisible():
            return

        screen_width = self.width()
        screen_height = self.height()

        if not hasattr(self, 'max_timer_font'):
            self._set_font_size_ranges(screen_width, screen_height)

        # Calculate available space for timer
        timer_available_width = int(screen_width * 0.90)
        timer_available_height = int(self.timer_label.height() * 0.95)

        # PRIORITY 1: Timer label
        if hasattr(self, "timer_label") and self.timer_label.isVisible():
            from PyQt6.QtGui import QFontMetrics
            text = self.timer_label.text() or "00:00"

            font = self.timer_label.font()
            best_timer_size = getattr(self, 'min_timer_font', 100)
            max_timer_size = getattr(self, 'max_timer_font', 1400)

            for size in range(max_timer_size, best_timer_size, -10):
                font.setPointSize(size)
                metrics = QFontMetrics(font)
                text_width = metrics.horizontalAdvance(text)
                text_height = metrics.height()

                if text_width <= timer_available_width and text_height <= timer_available_height:
                    best_timer_size = size
                    break

            font.setPointSize(best_timer_size)
            self.timer_label.setFont(font)

        # PRIORITY 2: Info labels - with stability improvements
        max_info_font_size = getattr(self, 'max_info_font', 100)
        min_info_font_size = getattr(self, 'min_info_font', 80)

        for label_name in ["info_label1", "info_label2"]:
            if not hasattr(self, label_name):
                continue

            label = getattr(self, label_name)
            if not label.isVisible():
                continue

            text = label.text()
            if not text:
                continue

            # Check if we've already calculated font size for this exact text
            text_hash = hash(text)
            cache_key = f"{label_name}_font_cache"
            if not hasattr(self, cache_key):
                setattr(self, cache_key, {})
            
            font_cache = getattr(self, cache_key)
            
            # If we have a cached font size for this exact text, use it
            if text_hash in font_cache:
                cached_size = font_cache[text_hash]
                font = label.font()
                if font.pointSize() != cached_size:
                    font.setPointSize(cached_size)
                    label.setFont(font)
                continue

            available_width = int(screen_width * 0.95)
            available_height = int(screen_height * 0.20)

            # Pre-format text once to avoid repeated formatting
            formatted_text = self._format_text_for_screen_width(text, available_width, max_info_font_size)
            if formatted_text != text:
                label.setText(formatted_text)
                text = formatted_text

            from PyQt6.QtGui import QFontMetrics
            font = label.font()

            best_size = min_info_font_size
            for size in range(max_info_font_size, min_info_font_size, -2):
                font.setPointSize(size)
                metrics = QFontMetrics(font)

                lines = text.split('\n')
                fits = True
                total_height = 0

                for line in lines:
                    line_width = metrics.horizontalAdvance(line)
                    line_height = metrics.height()
                    total_height += line_height * 1.2

                    if line_width > available_width:
                        fits = False
                        break

                if fits and total_height <= available_height:
                    best_size = size
                    break

            # Cache the calculated font size for this text
            font_cache[text_hash] = best_size
            
            # Limit cache size to prevent memory bloat
            if len(font_cache) > 50:
                # Remove oldest entries
                oldest_keys = list(font_cache.keys())[:25]
                for key in oldest_keys:
                    del font_cache[key]

            font.setPointSize(best_size)
            label.setFont(font)
    
    def _set_font_size_ranges(self, screen_width, screen_height):
        """Set appropriate font size ranges based on screen resolution"""
        total_pixels = screen_width * screen_height
        scale_factor = max(1.0, screen_width / 1920.0)

        if total_pixels >= 3840 * 2160:  # 4K+
            self.max_timer_font = int(1600 * scale_factor)
            self.max_info_font = int(140 * scale_factor)
            self.min_timer_font = int(140 * scale_factor)
            self.min_info_font = int(32 * scale_factor)
        elif total_pixels >= 2560 * 1440:
            self.max_timer_font = int(1200 * scale_factor)
            self.max_info_font = int(120 * scale_factor)
            self.min_timer_font = int(100 * scale_factor)
            self.min_info_font = int(28 * scale_factor)
        elif total_pixels >= 1920 * 1080:
            self.max_timer_font = int(1000 * scale_factor)
            self.max_info_font = int(100 * scale_factor)
            self.min_timer_font = int(90 * scale_factor)
            self.min_info_font = int(24 * scale_factor)
        else:
            self.max_timer_font = int(800 * scale_factor)
            self.max_info_font = int(80 * scale_factor)
            self.min_timer_font = int(70 * scale_factor)
            self.min_info_font = int(20 * scale_factor)
            
    def _format_text_for_display_stable(self, text, max_length=60):
        """Format text for display with consistent results to prevent flickering"""
        if not text or len(text) <= max_length:
            return text
        
        # Create a stable cache key for this text
        cache_key = f"_format_cache_{hash(text)}"
        if hasattr(self, cache_key):
            return getattr(self, cache_key)
        
        # Format the text
        formatted = self._format_text_for_display(text, max_length)
        
        # Cache the result
        setattr(self, cache_key, formatted)
        
        # Limit cache size
        cache_attrs = [attr for attr in dir(self) if attr.startswith('_format_cache_')]
        if len(cache_attrs) > 20:
            # Remove oldest cache entries
            for attr in cache_attrs[:10]:
                delattr(self, attr)
        
        return formatted

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._adjust_font_sizes()

    def showEvent(self, event):
        super().showEvent(event)
        self._adjust_font_sizes()
        
    def closeEvent(self, event):
        """Handle close event"""
        # Force the window to close when the main window is closed
        #self.timer_controller.stop_timer()
        
        event.accept()
        
    def _on_settings_updated(self):
        """Handle settings updates"""
        settings = self.settings_controller.get_settings()
        use_secondary = settings.display.use_secondary_screen
        
        if use_secondary:
            self.show_on_configured_screen_safely()
        else:
            self.hide()

    def _move_to_configured_screen(self):
        """Move to configured screen using safe positioning"""
        if self._positioning_in_progress:
            return
            
        # Use the safe positioning method
        self.show_on_configured_screen_safely()
        
    @property
    def show_countdown(self):
        return self._show_countdown

    @show_countdown.setter
    def show_countdown(self, value):
        """
        Enable/disable the pre-meeting countdown.

        - Countdown is allowed only while the timer is STOPPED **and**
          no part has started (current_part_index == -1).
        - When the countdown is turned off we blank the info labels so the
          “next part / predicted end” text can appear immediately.
        """
        # Don’t allow countdown once the meeting is running
        if value and (
            self.timer_controller.timer.state != TimerState.STOPPED
            or self.timer_controller.current_part_index >= 0
        ):
            return

        # Nothing to do if the state isn’t changing
        if value == self._show_countdown:
            return

        self._show_countdown = value

        if not value:
            # Countdown just switched off – clear any left-over text
            self.info_label1.setText("")
            self.info_label2.setText("")
        else:
            # Countdown switched on – ensure second line is empty
            self.info_label2.setText("")