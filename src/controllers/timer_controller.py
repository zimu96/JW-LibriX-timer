"""
Controller for managing timer functionality in the OnTime Meeting Timer application.
"""
import logging
from datetime import datetime, timedelta
from typing import List, Optional
from enum import Enum
from PyQt6.QtCore import QTimer
from PyQt6.QtCore import QObject, pyqtSignal

from src.controllers.settings_controller import SettingsController
from src.models.meeting import Meeting, MeetingPart, MeetingType
from src.models.timer import Timer, TimerState
from src.models.session import SessionManager, SessionState
from src.config import USER_DATA_DIR

logger = logging.getLogger("OnTime.TimerController")

class TransitionType(Enum):
    """Types of chairman transitions"""
    MIDWEEK = "Chairman Counsel and Transition"
    WEEKEND = "Chairman Introduction"
    GENERIC = "Chairman Transition"


class TimerController(QObject):
    """Controller for managing timer functionality"""
    
    # Signals
    part_changed = pyqtSignal(MeetingPart, int)  # part, index
    part_completed = pyqtSignal(int)  # part index
    meeting_started = pyqtSignal()
    meeting_ended = pyqtSignal()
    countdown_started = pyqtSignal(datetime)  # target datetime
    transition_started = pyqtSignal(str)  # transition description
    meeting_overtime = pyqtSignal(int)  # total overtime in seconds
    predicted_end_time_updated = pyqtSignal(datetime, datetime, datetime)  # original, predicted, and target end times
    meeting_countdown_updated = pyqtSignal(int, str)  # seconds remaining, formatted message
    durations_redistributed = pyqtSignal(list)  # [(global_idx, old_min, new_min), ...]
    durations_reset = pyqtSignal()
    late_start_absorbed = pyqtSignal(int, int)  # secondi di ritardo, secondi tolti alle parti
    
    def __init__(self, settings_controller: SettingsController):
        """Initialize the TimerController with a settings controller"""
        super().__init__()
        
        # Initialize settings controller
        self.settings_controller = settings_controller
        self.settings_controller.settings_changed.connect(self._on_settings_updated)
        
        # Timer model
        self.timer = Timer()
        
        # Current meeting state
        self.current_meeting: Optional[Meeting] = None
        self.current_part_index: int = -1
        self.parts_list: List[MeetingPart] = []
        
        # Initialize timer to show current time
        self.timer.start_current_time_display()
        
        # Transition state
        self._in_transition = False
        self._next_part_after_transition = -1

        # Re-entrancy guard for part navigation (prevents crashes from rapid button clicks)
        self._navigating_part = False
        
        # Meeting progress tracking
        self._total_overtime_seconds = 0
        self._meeting_start_time = None
        self._original_end_time = None
        self._predicted_end_time = None
        self._target_end_time = None  # Based on organizational standard or custom meeting target
        self._remaining_parts_duration = 0
        self._inizio_programmato = None  # ora dell'adunanza di oggi, se si e' partiti in ritardo
        
        # Meeting countdown tracking
        self._countdown_timer = QTimer(self)
        self._countdown_timer.setInterval(1000)  # Update every second
        self._countdown_timer.timeout.connect(self._update_meeting_countdown)
        self._meeting_target_datetime = None
        
        # Connect timer signals
        self.timer.state_changed.connect(self._handle_timer_state_change)
        self.timer.time_updated.connect(self._handle_time_update)

        # Session manager for crash recovery
        self.session_manager = SessionManager(USER_DATA_DIR, parent=self)
        self.session_manager.set_timer_controller(self)
        
    def _initialize_current_time_display(self):
        """Initialize the timer to display current time"""
        # Update the display to show current time
        self.timer._update_current_time()
    
    def set_meeting(self, meeting: Meeting):
        """Set the current meeting and initialize countdown"""
        self.current_meeting = meeting
        self.current_part_index = -1
        self.parts_list = meeting.get_all_parts()
        
        # Stop any previous timer and show current time
        self.timer.stop()
        self.timer.start_current_time_display()
        
        # Initialize countdown to meeting start time
        self._initialize_meeting_countdown()
        
    def _initialize_meeting_countdown(self):
        """Initialize countdown to meeting start time"""
        # Prevent countdown reinitialization if meeting is already in progress
        if self.current_part_index >= 0:
            return
        if not self.current_meeting:
            return

        now = datetime.now()
        today = now.date()
        now_time = now.time()

        settings = self.settings_controller.get_settings()
        if self.current_meeting.meeting_type == MeetingType.MIDWEEK:
            # Con la visita del sorvegliante l'adunanza e' il martedi'
            meeting_day = (1 if self.settings_controller.is_co_visit_active()
                           else settings.midweek_meeting.day.value)
            meeting_time = settings.midweek_meeting.time
        else:
            meeting_day = settings.weekend_meeting.day.value
            meeting_time = settings.weekend_meeting.time

        days_ahead = (meeting_day - today.weekday() + 7) % 7
        candidate_date = today + timedelta(days=days_ahead)

        # Use today if it's the meeting day and meeting time is still in the future
        if days_ahead == 0 and meeting_time > now_time:
            target_date = today
        else:
            target_date = candidate_date

        target_datetime = datetime.combine(target_date, meeting_time)

        # Step 1: Store the target meeting time in the Timer model for internal tracking
        self.timer.target_meeting_time = target_datetime

        # Only set countdown if meeting is in the future
        if target_datetime > now:
            # Set countdown target - this will trigger countdown updates
            self.timer.set_meeting_target_time(target_datetime)

            self._meeting_target_datetime = target_datetime

            # Make sure we're in stopped state to show current time
            if self.timer.state != TimerState.STOPPED:
                self.timer.stop()
                self.timer.start_current_time_display()

            # Start the countdown timer if not already running
            if not self._countdown_timer.isActive():
                self._countdown_timer.start()

            # Emit the countdown signal with target time
            self.countdown_started.emit(target_datetime)
        else:
            # Meeting time has passed, clear any countdown
            self.timer.target_meeting_time = None

            # Stop the countdown timer if it's running
            if self._countdown_timer.isActive():
                self._countdown_timer.stop()
                
    def _update_meeting_countdown(self):
        """Update the meeting countdown display"""
        if not self.current_meeting:
            return

        meeting_datetime = self._meeting_target_datetime
        if not meeting_datetime:
            return

        now = datetime.now()
        time_diff = meeting_datetime - now
        seconds_remaining = int(time_diff.total_seconds())

        if seconds_remaining > 0:
            hours = seconds_remaining // 3600
            minutes = (seconds_remaining % 3600) // 60
            seconds = seconds_remaining % 60
            if hours > 0:
                countdown_msg = f"{self.tr('Meeting starts in')} {hours}h {minutes}m"
            else:
                countdown_msg = f"{self.tr('Meeting starts in')} {minutes}m"
            self.meeting_countdown_updated.emit(seconds_remaining, countdown_msg)
        else:
            countdown_msg = self.tr("Meeting starts now!")
            self.meeting_countdown_updated.emit(0, countdown_msg)
            self._countdown_timer.stop()
    
    def start_meeting(self):
        """Start the current meeting"""
        if not self.current_meeting or not self.parts_list:
            return
        
        # Reset all parts completion status
        for part in self.parts_list:
            part.is_completed = False
            part.riduzione_secondi = 0
        
        # Move to first part
        self.current_part_index = 0
        
        # Reset overtime tracking
        self._total_overtime_seconds = 0
        
        # Record meeting start time and calculate original and target end times
        self._meeting_start_time = datetime.now()

        # Se si parte dopo l'ora dell'adunanza, il ritardo si toglie dalle parti
        # (non da cantici e preghiere) a pochi secondi per volta.
        self._inizio_programmato = self._scheduled_start_today()
        ritardo = 0
        if self._inizio_programmato is not None:
            ritardo = int((self._meeting_start_time - self._inizio_programmato).total_seconds())
            if not 1 <= ritardo <= 3 * 3600:
                ritardo = 0
                self._inizio_programmato = None
        tolti = self._spalma_ritardo(ritardo) if ritardo else 0

        current_part = self.parts_list[self.current_part_index]
        self._calculate_original_end_time()  # Template-based
        self._calculate_target_end_time()    # Standard-based or custom
        self._predicted_end_time = self._original_end_time
        
        # Start timer for first part
        self.timer.start(current_part.duration_seconds)
        
        # Stop the countdown timer if running
        if self._countdown_timer.isActive():
            self._countdown_timer.stop()
        
        # Emit signals
        self.part_changed.emit(current_part, self.current_part_index)
        self.meeting_started.emit()
        self.predicted_end_time_updated.emit(self._original_end_time, self._predicted_end_time, self._target_end_time)
        if ritardo:
            self.late_start_absorbed.emit(ritardo, tolti)

        # Start session tracking for crash recovery
        meeting_file = f"{self.current_meeting.meeting_type.value}_{self.current_meeting.date.strftime('%Y-%m-%d')}_{self.current_meeting.language}.json"
        self.session_manager.start_session(self.current_meeting, meeting_file)
    
    def _scheduled_start_today(self) -> Optional[datetime]:
        """L'ora in cui l'adunanza doveva iniziare OGGI, o None se oggi non e' il suo giorno."""
        if not self.current_meeting:
            return None
        settings = self.settings_controller.get_settings()
        if self.current_meeting.meeting_type == MeetingType.MIDWEEK:
            giorno = (1 if self.settings_controller.is_co_visit_active()
                      else settings.midweek_meeting.day.value)
            ora = settings.midweek_meeting.time
        elif self.current_meeting.meeting_type == MeetingType.WEEKEND:
            giorno = settings.weekend_meeting.day.value
            ora = settings.weekend_meeting.time
        else:
            return None
        adesso = datetime.now()
        if adesso.weekday() != giorno:
            return None
        return datetime.combine(adesso.date(), ora)

    @staticmethod
    def _e_cantico_o_preghiera(titolo: str) -> bool:
        """Cantici e preghiere non si accorciano mai."""
        import re
        return re.search(r"\b(cantic[oi]|canti?|song|cantique|lied|canci[oó]n|cantiga|"
                         r"preghier[ae]|prayer|pri[eè]re|gebet|oraci[oó]n|ora[cç][aã]o)\b",
                         titolo or "", re.IGNORECASE) is not None

    def _spalma_ritardo(self, ritardo: int) -> int:
        """Toglie `ritardo` secondi alle parti che si possono accorciare, a parti uguali.

        Ogni parte resta di almeno un minuto.  Ritorna i secondi davvero tolti
        (meno del ritardo se le parti non ne hanno abbastanza).
        """
        parti = [p for p in self.parts_list if not self._e_cantico_o_preghiera(p.title)]
        capacita = [max(0, p.duration_minutes * 60 - 60) for p in parti]
        tolti = [0] * len(parti)
        resto = ritardo
        while resto > 0:
            attive = [i for i in range(len(parti)) if tolti[i] < capacita[i]]
            if not attive:
                break
            base, extra = divmod(resto, len(attive))
            dati = 0
            for k, i in enumerate(attive):
                q = min(base + (1 if k < extra else 0), capacita[i] - tolti[i])
                tolti[i] += q
                dati += q
            if dati == 0:
                break
            resto -= dati
        for p, t in zip(parti, tolti):
            p.riduzione_secondi = t
        return ritardo - resto

    def _calculate_original_end_time(self):
        """Calculate the original end time based on scheduled parts"""
        if not self.current_meeting:
            return
        
        # Calculate total meeting duration in seconds
        total_seconds = 0
        for part in self.parts_list:
            total_seconds += part.duration_seconds
        
        # Add transition times between sections (1 minute per transition)
        section_transitions = len(self.current_meeting.sections) - 1
        total_seconds += section_transitions * 60
        
        # Set the original end time
        self._original_end_time = self._meeting_start_time + timedelta(seconds=total_seconds)

    def _calculate_target_end_time(self):
        """Calculate the target end time based on organizational standards or meeting-specific target"""
        if not self.current_meeting:
            return

        # Check if meeting has a custom target duration (for custom meetings)
        if self.current_meeting.target_duration_minutes is not None:
            target_minutes = self.current_meeting.target_duration_minutes
        else:
            # Use global settings for regular meetings
            settings = self.settings_controller.get_settings()
            if self.current_meeting.meeting_type == MeetingType.WEEKEND:
                target_minutes = settings.weekend_meeting.target_duration_minutes
            else:  # MIDWEEK or any other type defaults to midweek
                target_minutes = settings.midweek_meeting.target_duration_minutes

        # Calculate target end time (dall'ora dell'adunanza se si e' partiti in ritardo)
        inizio = getattr(self, '_inizio_programmato', None) or self._meeting_start_time
        self._target_end_time = inizio + timedelta(minutes=target_minutes)

    def _update_predicted_end_time(self):
        """Update the predicted end time based on current progress and real-time data"""
        if not self._meeting_start_time or self.current_part_index < 0:
            return
        
        now = datetime.now()
        
        # CRITICAL FIX: Predicted end time must NEVER be earlier than current time
        # Calculate remaining time from current position forward
        
        remaining_time = 0.0
        
        # 1. Add remaining time from current part
        if (self.current_part_index < len(self.parts_list) and 
            self.timer.state in [TimerState.RUNNING, TimerState.PAUSED]):
            # Only count remaining time if not in overtime
            remaining_time += max(0, self.timer.remaining_seconds)
        elif (self.current_part_index < len(self.parts_list) and 
            self.timer.state == TimerState.OVERTIME):
            # If in overtime, no remaining time for current part
            remaining_time += 0
        
        # 2. Add duration of all future parts
        for i in range(self.current_part_index + 1, len(self.parts_list)):
            remaining_time += self.parts_list[i].duration_seconds
        
        # 3. Add remaining transitions
        remaining_transitions = self._calculate_remaining_transitions()
        remaining_time += remaining_transitions * 60
        
        # 4. GUARANTEE: Predicted end = current time + remaining time
        # This ensures predicted end is ALWAYS >= current time
        self._predicted_end_time = now + timedelta(seconds=remaining_time)
        
        # 5. Calculate overtime relative to original schedule
        if self._original_end_time and self._predicted_end_time > self._original_end_time:
            overtime_seconds = (self._predicted_end_time - self._original_end_time).total_seconds()
        else:
            overtime_seconds = 0
        
        # Emit signal with updated prediction
        self.predicted_end_time_updated.emit(self._original_end_time, self._predicted_end_time, self._target_end_time)
        
        # Debug logging
        logger.debug(
            "Predicted end time: now=%s, part=%d/%d, state=%s, "
            "part_remaining=%.0fs, future=%.0fs, transitions=%d, "
            "total_remaining=%.0fs (%.1fm), predicted=%s, original=%s",
            now.strftime('%H:%M:%S'),
            self.current_part_index + 1, len(self.parts_list),
            self.timer.state,
            max(0, self.timer.remaining_seconds) if self.timer.state != TimerState.OVERTIME else 0,
            sum(self.parts_list[i].duration_seconds for i in range(self.current_part_index + 1, len(self.parts_list))),
            remaining_transitions,
            remaining_time, remaining_time / 60,
            self._predicted_end_time.strftime('%H:%M:%S'),
            self._original_end_time.strftime('%H:%M:%S') if self._original_end_time else 'N/A'
        )

        if self._predicted_end_time < now:
            logger.error(
                "Predicted end time is in the past: predicted=%s, current=%s",
                self._predicted_end_time, now
            )
    
    def _calculate_planned_elapsed_time(self) -> float:
        """Calculate how much time should have elapsed based on current part position"""
        if self.current_part_index < 0:
            return 0.0
        
        planned_elapsed = 0.0
        
        # Add duration of all completed parts
        for i in range(self.current_part_index):
            if i < len(self.parts_list):
                planned_elapsed += self.parts_list[i].duration_seconds
        
        # Add transitions that should have occurred
        completed_transitions = self._get_completed_transitions_count()
        planned_elapsed += completed_transitions * 60
        
        # Add elapsed time of current part
        if self.current_part_index < len(self.parts_list):
            current_part = self.parts_list[self.current_part_index]
            
            if self.timer.state == TimerState.OVERTIME:
                # If in overtime, we've used the full planned duration plus overtime
                planned_elapsed += current_part.duration_seconds
                # Note: overtime is handled by the drift calculation
            elif self.timer.state in [TimerState.RUNNING, TimerState.PAUSED]:
                # Add the elapsed portion of current part
                current_part_elapsed = current_part.duration_seconds - self.timer.remaining_seconds
                planned_elapsed += max(0, current_part_elapsed)
        
        return planned_elapsed
    
    def _calculate_remaining_planned_time(self) -> float:
        """Calculate remaining planned time from current position"""
        if self.current_part_index < 0:
            return sum(part.duration_seconds for part in self.parts_list)
        
        remaining_time = 0.0
        
        # Add remaining time from current part
        if (self.current_part_index < len(self.parts_list) and 
            self.timer.state in [TimerState.RUNNING, TimerState.PAUSED]):
            remaining_time += max(0, self.timer.remaining_seconds)
        
        # Add duration of future parts
        for i in range(self.current_part_index + 1, len(self.parts_list)):
            remaining_time += self.parts_list[i].duration_seconds
        
        # Add remaining transitions
        remaining_transitions = self._calculate_remaining_transitions()
        remaining_time += remaining_transitions * 60
        
        return remaining_time
    
    def _get_total_transitions_count(self) -> int:
        """Get total number of transitions in the meeting"""
        if not self.current_meeting:
            return 0

        if self.current_meeting.meeting_type == MeetingType.WEEKEND:
            return min(1, len(self.current_meeting.sections) - 1)  # Max 1 for weekend

        # For midweek, count all parts except those that don't get transitions
        count = 0
        all_parts = [part for section in self.current_meeting.sections for part in section.parts]
        total_parts = len(all_parts)

        for i, part in enumerate(all_parts):
            # Skip last part (no transition after it)
            if i >= total_parts - 1:
                continue

            # Skip Opening Song/Prayer (first part)
            if i == 0:
                continue

            # Skip CBS (3rd-to-last, typically 30 min)
            if i == total_parts - 3 and part.duration_minutes >= 25:
                continue

            # Skip Concluding Comments / Review and Preview (2nd-to-last)
            if i == total_parts - 2:
                continue

            count += 1

        return count
    
    def _calculate_remaining_transitions(self) -> int:
        """Calculate how many chairman transitions are left"""
        if not self.current_meeting or self.current_part_index < 0:
            return 0

        if self.current_meeting.meeting_type == MeetingType.WEEKEND:
            # Weekend meetings: find current section and count remaining section transitions
            current_section_index = -1
            part_count = 0
            for section_index, section in enumerate(self.current_meeting.sections):
                for part in section.parts:
                    if part_count == self.current_part_index:
                        current_section_index = section_index
                        break
                    part_count += 1
                if current_section_index != -1:
                    break

            if current_section_index != -1:
                remaining_sections = len(self.current_meeting.sections) - current_section_index - 1
                return min(remaining_sections, 1)  # Max 1 transition for weekend
            return 0

        # For midweek, count remaining parts that get transitions
        count = 0
        all_parts = [part for section in self.current_meeting.sections for part in section.parts]
        total_parts = len(all_parts)

        for i in range(self.current_part_index, total_parts):
            # Skip last part (no transition after it)
            if i >= total_parts - 1:
                continue

            part = all_parts[i]

            # Skip Opening Song/Prayer (first part)
            if i == 0:
                continue

            # Skip CBS (3rd-to-last, typically 30 min)
            if i == total_parts - 3 and part.duration_minutes >= 25:
                continue

            # Skip Concluding Comments / Review and Preview (2nd-to-last)
            if i == total_parts - 2:
                continue

            count += 1

        return count

    def _should_add_chairman_transition(self):
        """Check if we should add a chairman transition between parts"""
        if not self.current_meeting or not self.parts_list:
            return False

        # Don't add transition if we're at the last part
        if self.current_part_index < 0 or self.current_part_index >= len(self.parts_list) - 1:
            return False

        if self.current_meeting.meeting_type == MeetingType.WEEKEND:
            # Add transition only before part at index 1 or 2
            next_index = self.current_part_index + 1
            if next_index in [1, 2]:
                return True
            return False

        # Midweek meeting logic
        if self.current_meeting.meeting_type == MeetingType.MIDWEEK:
            current_part = self.parts_list[self.current_part_index]
            total_parts = len(self.parts_list)

            # NO transition after Opening Song/Prayer (first part)
            if self.current_part_index == 0:
                return False

            # NO transition after Congregation Bible Study (3rd-to-last, typically 30 min)
            if self.current_part_index == total_parts - 3 and current_part.duration_minutes >= 25:
                return False

            # NO transition after Concluding Comments / Review and Preview (2nd-to-last)
            if self.current_part_index == total_parts - 2:
                return False

            # All other parts get transitions
            return True

        # Default: allow transition
        return True
    
    def _start_chairman_transition(self):
        """Start a 1-minute chairman transition period with meeting-specific text"""
        # Create a transition for 1 minute (60 seconds)
        transition_seconds = 60
        
        # Set timer state to transition
        self.timer._state = TimerState.TRANSITION
        self.timer.state_changed.emit(TimerState.TRANSITION)
        
        # Start the timer
        self.timer.start(transition_seconds)
        
        # Determine transition text based on meeting type
        transition_type = TransitionType.GENERIC
        if self.current_meeting:
            if self.current_meeting.meeting_type == MeetingType.MIDWEEK:
                transition_type = TransitionType.MIDWEEK
            elif self.current_meeting.meeting_type == MeetingType.WEEKEND:
                transition_type = TransitionType.WEEKEND
        
        # Emit a signal with the appropriate transition message
        self.transition_started.emit(transition_type.value)
        
        # Store that we're in transition mode and which part is next
        self._in_transition = True
        self._next_part_after_transition = self.current_part_index + 1
        
    def _complete_transition(self):
        """Let transition enter overtime instead of moving to next part"""
        if self._in_transition:
            self._in_transition = False
            # Do not auto-advance. Allow the timer to go into overtime.

    def next_part(self):
        """Move to the next part, allowing transitions to be skipped"""
        if not self.current_meeting or not self.parts_list:
            return

        # Re-entrancy guard to prevent crashes from rapid button clicks
        if self._navigating_part:
            return
        self._navigating_part = True
        try:
            self._next_part_impl()
        finally:
            self._navigating_part = False

    def _next_part_impl(self):
        """Internal implementation of next_part (called with re-entrancy guard)"""
        # If we're in a transition, cancel it and move immediately to the next part
        if self._in_transition:
            if hasattr(self, '_transition_timer') and self._transition_timer.isActive():
                self._transition_timer.stop()
            self._in_transition = False
            self.current_part_index = self._next_part_after_transition
            if self.current_part_index >= len(self.parts_list):
                self.stop_meeting()
                return
            current_part = self.parts_list[self.current_part_index]
            self.timer.start(current_part.duration_seconds)
            self.part_changed.emit(current_part, self.current_part_index)
            self._update_predicted_end_time()
            return
        
        # Mark current part as completed
        if 0 <= self.current_part_index < len(self.parts_list):
            self.parts_list[self.current_part_index].is_completed = True
            self.part_completed.emit(self.current_part_index)
        
        # Add a chairman transition after every part
        if self._should_add_chairman_transition():
            self._start_chairman_transition()
            
            # Update predicted end time
            self._update_predicted_end_time()
            return
        
        # If no transition needed, move to next part directly
        self.current_part_index += 1
        
        # Check if we're at the end
        if self.current_part_index >= len(self.parts_list):
            self.stop_meeting()
            return
        
        # Get next part
        current_part = self.parts_list[self.current_part_index]
        
        # Start timer for next part
        self.timer.start(current_part.duration_seconds)
        
        # Emit signal
        self.part_changed.emit(current_part, self.current_part_index)
        
        # Update predicted end time
        self._update_predicted_end_time()
    
    def previous_part(self):
        """Move to the previous part"""
        if not self.current_meeting or not self.parts_list:
            return

        # Re-entrancy guard to prevent crashes from rapid button clicks
        if self._navigating_part:
            return
        self._navigating_part = True
        try:
            if self._in_transition:
                # Nel minuto del presidente «Precedente» riporta alla parte appena
                # finita (non due indietro) e annulla il passaggio: prima restava
                # un passaggio fantasma e «Successivo» saltava una parte.
                self._in_transition = False
                self._next_part_after_transition = -1
            else:
                # Move to previous part
                self.current_part_index -= 1

            # Check if we're at the beginning
            if self.current_part_index < 0:
                self.current_part_index = 0

            # Get current part
            current_part = self.parts_list[self.current_part_index]

            # Start timer for this part
            self.timer.start(current_part.duration_seconds)

            # Emit signal
            self.part_changed.emit(current_part, self.current_part_index)

            # Update predicted end time
            self._update_predicted_end_time()
        finally:
            self._navigating_part = False
    
    def stop_meeting(self):
        """Stop the current meeting"""
        # Cancel any active transition timer
        if hasattr(self, '_transition_timer') and self._transition_timer.isActive():
            self._transition_timer.stop()

        self._in_transition = False
        self.timer.stop()
        self.current_part_index = -1
        self._inizio_programmato = None
        for part in self.parts_list:
            part.riduzione_secondi = 0
        self.meeting_ended.emit()

        # End session tracking (clean exit)
        self.session_manager.end_session(clean=True)
    
    def pause_timer(self):
        """Pause the current timer"""
        self.timer.pause()
    
    def resume_timer(self):
        """Resume the current timer"""
        self.timer.resume()
    
    def reset_timer(self):
        """Reset the current timer"""
        if 0 <= self.current_part_index < len(self.parts_list):
            current_part = self.parts_list[self.current_part_index]
            self.timer.start(current_part.duration_seconds)
    
    def adjust_time(self, minutes_delta: int):
        """Adjust the current timer by adding/removing minutes"""
        self.timer.adjust_time(minutes_delta * 60)

        # Update predicted end time since we've changed the duration
        self._update_predicted_end_time()

    def redistribute_durations_for_end_time(self, target_end_time: datetime, from_part_index: int) -> dict:
        """Redistribute part durations from from_part_index onward to end meeting at target_end_time.

        Returns dict with 'success', 'error' (if failed), 'adjusted_parts' list of
        (global_index, old_minutes, new_minutes) tuples.
        """
        now = datetime.now()

        # Validate preconditions
        if self.current_part_index < 0 or not self.current_meeting:
            return {'success': False, 'error': 'Meeting is not running'}
        if target_end_time <= now:
            return {'success': False, 'error': 'Target end time must be in the future'}
        if from_part_index < self.current_part_index or from_part_index >= len(self.parts_list):
            return {'success': False, 'error': 'Invalid part index'}

        # Build section map: global_part_index -> section_index
        section_map = []
        for sec_idx, section in enumerate(self.current_meeting.sections):
            for _ in section.parts:
                section_map.append(sec_idx)

        # Calculate available time from now to target
        total_available = (target_end_time - now).total_seconds()

        # Subtract locked time (parts before from_part_index that we're NOT adjusting)
        locked_time = 0.0
        if from_part_index > self.current_part_index:
            # Current part's remaining time is locked
            locked_time += max(0, self.timer.remaining_seconds)
            # Parts between current+1 and from-1 are locked
            for i in range(self.current_part_index + 1, from_part_index):
                locked_time += self.parts_list[i].duration_seconds
            # Transitions in locked range
            for i in range(self.current_part_index, from_part_index - 1):
                if i + 1 < len(section_map) and section_map[i] != section_map[i + 1]:
                    locked_time += 60
        elif from_part_index == self.current_part_index:
            # Nothing locked — we're adjusting from the current part
            pass

        available_for_adjusted = total_available - locked_time

        # Subtract transitions within the adjusted range
        for i in range(from_part_index, len(self.parts_list) - 1):
            if section_map[i] != section_map[i + 1]:
                available_for_adjusted -= 60

        # Parts to adjust
        parts_to_adjust = self.parts_list[from_part_index:]
        if not parts_to_adjust:
            return {'success': False, 'error': 'No parts to adjust'}

        # For the current part, only its remaining time is adjustable
        is_current_included = (from_part_index == self.current_part_index)
        current_elapsed = 0
        if is_current_included:
            current_elapsed = self.timer.elapsed_seconds

        # Calculate original durations (use original_duration_minutes if previously adjusted)
        originals_seconds = []
        for i, part in enumerate(parts_to_adjust):
            orig = (part.original_duration_minutes or part.duration_minutes) * 60
            if i == 0 and is_current_included:
                # For current part, only the remaining portion participates
                orig = max(0, orig - current_elapsed)
            originals_seconds.append(orig)

        sum_originals = sum(originals_seconds)
        if sum_originals <= 0:
            return {'success': False, 'error': 'No adjustable time in selected parts'}

        # Validate minimum time
        min_time_needed = len(parts_to_adjust) * 60  # 1 min per part minimum
        if is_current_included:
            # Current part needs at least enough for its elapsed + 1 min
            min_time_needed = (len(parts_to_adjust) - 1) * 60 + max(60, current_elapsed + 60)

        if available_for_adjusted < min_time_needed:
            mins_needed = int(min_time_needed / 60)
            mins_available = int(available_for_adjusted / 60)
            return {
                'success': False,
                'error': f'Not enough time: need at least {mins_needed} min, '
                         f'but only {mins_available} min available'
            }

        # Distribute proportionally
        ratio = available_for_adjusted / sum_originals
        adjusted_parts = []
        allocated_seconds = 0

        for i, part in enumerate(parts_to_adjust):
            global_idx = from_part_index + i

            # Save original if first time adjusting
            if part.original_duration_minutes is None:
                part.original_duration_minutes = part.duration_minutes

            old_minutes = part.duration_minutes

            if i == len(parts_to_adjust) - 1:
                # Last part gets remainder
                remaining_available = available_for_adjusted - allocated_seconds
                if i == 0 and is_current_included:
                    new_minutes = max(1, round((remaining_available + current_elapsed) / 60))
                else:
                    new_minutes = max(1, round(remaining_available / 60))
            else:
                new_seconds = originals_seconds[i] * ratio
                if i == 0 and is_current_included:
                    # Add back elapsed time to get full duration
                    new_minutes = max(1, round((new_seconds + current_elapsed) / 60))
                    allocated_seconds += (new_minutes * 60) - current_elapsed
                else:
                    new_minutes = max(1, round(new_seconds / 60))
                    allocated_seconds += new_minutes * 60

            part.duration_minutes = new_minutes
            adjusted_parts.append((global_idx, old_minutes, new_minutes))

        # Update current part's timer if it was adjusted
        if is_current_included:
            new_total = parts_to_adjust[0].duration_seconds
            new_remaining = max(0, new_total - current_elapsed)
            self.timer._total_seconds = new_total
            self.timer._remaining_seconds = new_remaining
            self.timer.time_updated.emit(new_remaining)

        self._update_predicted_end_time()
        self.durations_redistributed.emit(adjusted_parts)

        return {'success': True, 'adjusted_parts': adjusted_parts}

    def reset_adjusted_durations(self) -> int:
        """Reset all adjusted parts back to their original durations. Returns count of parts reset."""
        count = 0
        for i, part in enumerate(self.parts_list):
            if part.original_duration_minutes is not None:
                part.duration_minutes = part.original_duration_minutes
                part.original_duration_minutes = None
                count += 1
                # Update running timer if this is the current part
                if i == self.current_part_index:
                    self.timer._total_seconds = part.duration_seconds
                    new_remaining = max(0, part.duration_seconds - self.timer.elapsed_seconds)
                    self.timer._remaining_seconds = new_remaining
                    self.timer.time_updated.emit(new_remaining)

        if count > 0:
            self._update_predicted_end_time()
            self.durations_reset.emit()

        return count

    def jump_to_part(self, part_index: int):
        """Jump to a specific part"""
        if not self.current_meeting or not self.parts_list:
            return
        
        if 0 <= part_index < len(self.parts_list):
            self._in_transition = False
            self._next_part_after_transition = -1
            # Mark parts before this as completed
            for i in range(part_index):
                self.parts_list[i].is_completed = True
                self.part_completed.emit(i)
            
            # Set current part
            self.current_part_index = part_index
            current_part = self.parts_list[self.current_part_index]
            
            # Start timer for this part
            self.timer.start(current_part.duration_seconds)
            
            # Emit signal
            self.part_changed.emit(current_part, self.current_part_index)
            
            # Update predicted end time
            self._update_predicted_end_time()
    
    def start_countdown_to_meeting(self, meeting: Meeting):
        """Start countdown to the meeting time"""
        # Create target datetime from meeting date and time
        meeting_datetime = datetime.combine(meeting.date, meeting.start_time)
        
        # Start countdown
        self.timer.start_countdown(meeting_datetime)
        
        # Emit signal
        self.countdown_started.emit(meeting_datetime)
    
    def _handle_timer_state_change(self, state: TimerState):
        """Handle timer state changes"""
        if state == TimerState.OVERTIME:
            # Timer has reached zero, but we'll let it continue counting
            # until the user manually advances
            pass
        
        elif state == TimerState.STOPPED:
            # Timer was stopped, check if we need to advance
            pass
    
    def _handle_time_update(self, seconds: int):
        """Handle timer time updates to track meeting progress"""
        # Update predicted end time on every timer update for real-time accuracy
        self._update_predicted_end_time()
        
        # Check if we're in overtime
        if self.timer.state == TimerState.OVERTIME:
            # Use the exact value from the timer instead of incrementing
            current_overtime = abs(seconds)  # Get absolute value of the negative seconds
            self._total_overtime_seconds = current_overtime
            
            # Emit signal about total meeting overtime
            self.meeting_overtime.emit(self._total_overtime_seconds)
            
    def apply_current_part_update(self):
        """Apply updated duration to the currently running part without restarting timer"""
        if 0 <= self.current_part_index < len(self.parts_list):
            current_part = self.parts_list[self.current_part_index]
            self.timer.set_duration(current_part.duration_minutes)
    def _on_settings_updated(self):
        """Handle updates to settings such as meeting time and target duration"""
        if self.current_meeting:
            # Update the meeting time in the timer
            self._initialize_meeting_countdown()

            # If a meeting is running, recalculate target end time
            if self._meeting_start_time is not None:
                self._calculate_target_end_time()
                self._update_predicted_end_time()

    def restore_session(self, session: SessionState, adjusted_state: dict):
        """Restore timer state from a saved session after crash recovery"""
        if not self.current_meeting or not self.parts_list:
            return

        # Restore part index
        self.current_part_index = session.current_part_index

        # Validate part index (allow -1 for "not started" state)
        if self.current_part_index >= len(self.parts_list):
            logger.warning("Invalid part index %d, resetting to 0", self.current_part_index)
            self.current_part_index = 0

        # Only proceed with session restoration if meeting was actually in progress
        if self.current_part_index < 0:
            # Meeting was never started, just restore the state without starting
            logger.info("Session shows meeting was not started, preserving pre-start state")
            return

        # Mark previous parts as completed
        for i in range(self.current_part_index):
            self.parts_list[i].is_completed = True

        # Get current part
        current_part = self.parts_list[self.current_part_index]

        # Restore meeting start time
        if session.meeting_start_time:
            try:
                self._meeting_start_time = datetime.fromisoformat(session.meeting_start_time)
            except ValueError:
                self._meeting_start_time = datetime.now()
        else:
            self._meeting_start_time = datetime.now()

        # Calculate original and target end times
        self._calculate_original_end_time()
        self._calculate_target_end_time()

        # Restore transition state
        self._in_transition = session.in_transition
        self._next_part_after_transition = session.next_part_after_transition
        self._total_overtime_seconds = session.total_overtime_seconds

        # Stop the countdown timer if running
        if self._countdown_timer.isActive():
            self._countdown_timer.stop()

        # Restore timer state based on adjusted values
        if adjusted_state.get('was_paused', False):
            # Resume in paused state
            self.timer.start(session.total_seconds)
            # Calculate elapsed time from remaining
            elapsed = session.total_seconds - session.remaining_seconds
            self.timer._elapsed_time = elapsed
            self.timer._remaining_seconds = session.remaining_seconds
            self.timer.pause()
        elif adjusted_state.get('overtime_seconds', 0) > 0:
            # Part should be in overtime
            self.timer.start(session.total_seconds)
            # Force into overtime state
            self.timer._elapsed_time = session.total_seconds + adjusted_state['overtime_seconds']
            self.timer._remaining_seconds = -adjusted_state['overtime_seconds']
            self.timer._state = TimerState.OVERTIME
            self.timer.state_changed.emit(TimerState.OVERTIME)
        else:
            # Normal running state with adjusted remaining time
            remaining = adjusted_state.get('remaining_seconds', session.remaining_seconds)
            self.timer.start(session.total_seconds)
            # Adjust to correct remaining time
            elapsed = session.total_seconds - remaining
            self.timer._elapsed_time = elapsed
            self.timer._remaining_seconds = remaining

        # Emit signals to update UI
        self.part_changed.emit(current_part, self.current_part_index)
        self.timer.state_changed.emit(self.timer.state)
        self.timer.time_updated.emit(self.timer.remaining_seconds)
        self.meeting_started.emit()

        # Update predicted end time (this method emits predicted_end_time_updated internally)
        self._update_predicted_end_time()

        # Restart session tracking
        meeting_file = f"{self.current_meeting.meeting_type.value}_{self.current_meeting.date.strftime('%Y-%m-%d')}_{self.current_meeting.language}.json"
        self.session_manager.start_session(self.current_meeting, meeting_file)