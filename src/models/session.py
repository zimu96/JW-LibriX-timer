"""
Session persistence model for crash recovery in OnTime Meeting Timer.
"""
import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional, TYPE_CHECKING

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

logger = logging.getLogger("OnTime.SessionManager")

if TYPE_CHECKING:
    from src.models.meeting import Meeting


@dataclass
class SessionState:
    """Represents a recoverable meeting session state"""
    version: str = "1.0"
    clean_exit: bool = False
    meeting_file: str = ""
    meeting_hash: str = ""
    current_part_index: int = -1
    timer_state: str = "STOPPED"
    total_seconds: int = 0
    elapsed_seconds: int = 0
    remaining_seconds: int = 0
    in_transition: bool = False
    next_part_after_transition: int = -1
    meeting_start_time: Optional[str] = None
    total_overtime_seconds: int = 0
    last_save_time: Optional[str] = None
    network_broadcast_active: bool = False

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON storage"""
        return {
            'version': self.version,
            'clean_exit': self.clean_exit,
            'meeting_file': self.meeting_file,
            'meeting_hash': self.meeting_hash,
            'current_part_index': self.current_part_index,
            'timer_state': self.timer_state,
            'total_seconds': self.total_seconds,
            'elapsed_seconds': self.elapsed_seconds,
            'remaining_seconds': self.remaining_seconds,
            'in_transition': self.in_transition,
            'next_part_after_transition': self.next_part_after_transition,
            'meeting_start_time': self.meeting_start_time,
            'total_overtime_seconds': self.total_overtime_seconds,
            'last_save_time': self.last_save_time,
            'network_broadcast_active': self.network_broadcast_active
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'SessionState':
        """Create from dictionary"""
        return cls(
            version=data.get('version', '1.0'),
            clean_exit=data.get('clean_exit', False),
            meeting_file=data.get('meeting_file', ''),
            meeting_hash=data.get('meeting_hash', ''),
            current_part_index=data.get('current_part_index', -1),
            timer_state=data.get('timer_state', 'STOPPED'),
            total_seconds=data.get('total_seconds', 0),
            elapsed_seconds=data.get('elapsed_seconds', 0),
            remaining_seconds=data.get('remaining_seconds', 0),
            in_transition=data.get('in_transition', False),
            next_part_after_transition=data.get('next_part_after_transition', -1),
            meeting_start_time=data.get('meeting_start_time'),
            total_overtime_seconds=data.get('total_overtime_seconds', 0),
            last_save_time=data.get('last_save_time'),
            network_broadcast_active=data.get('network_broadcast_active', False)
        )


class SessionManager(QObject):
    """Manages session persistence for crash recovery"""

    SESSION_FILE = "session.json"
    AUTOSAVE_INTERVAL_MS = 5000  # 5 seconds
    STALE_SESSION_HOURS = 24

    # Signals
    session_saved = pyqtSignal()

    def __init__(self, data_dir: Path, parent=None):
        super().__init__(parent)
        self.data_dir = Path(data_dir)
        self.session_file = self.data_dir / self.SESSION_FILE

        self._autosave_timer = QTimer(self)
        self._autosave_timer.timeout.connect(self._autosave)

        self._current_session: Optional[SessionState] = None
        self._timer_controller = None
        self._meeting_file: str = ""

    def set_timer_controller(self, timer_controller):
        """Set reference to timer controller for state updates"""
        self._timer_controller = timer_controller

    def start_session(self, meeting: 'Meeting', meeting_file: str):
        """Start tracking a new meeting session"""
        self._meeting_file = meeting_file
        self._current_session = SessionState(
            clean_exit=False,
            meeting_file=meeting_file,
            meeting_hash=self._compute_meeting_hash(meeting),
            meeting_start_time=datetime.now().isoformat()
        )

        # Save the meeting file to ensure it exists for recovery
        self._save_meeting_for_recovery(meeting, meeting_file)

        self._save_session()
        self._autosave_timer.start(self.AUTOSAVE_INTERVAL_MS)

    def _save_meeting_for_recovery(self, meeting: 'Meeting', meeting_file: str):
        """Save the meeting to MEETINGS_DIR for crash recovery"""
        from src.config import MEETINGS_DIR

        meeting_path = MEETINGS_DIR / meeting_file
        try:
            MEETINGS_DIR.mkdir(parents=True, exist_ok=True)
            with open(meeting_path, 'w', encoding='utf-8') as f:
                json.dump(meeting.to_dict(), f, indent=2)
        except IOError as e:
            logger.error("Error saving meeting for recovery: %s", e)

    def update_session_from_controller(self):
        """Update session state from timer controller"""
        if not self._current_session or not self._timer_controller:
            return

        tc = self._timer_controller
        timer = tc.timer

        self._current_session.current_part_index = tc.current_part_index
        self._current_session.timer_state = timer.state.name
        self._current_session.total_seconds = timer.total_seconds
        self._current_session.elapsed_seconds = timer.elapsed_seconds
        self._current_session.remaining_seconds = timer.remaining_seconds
        self._current_session.in_transition = tc._in_transition
        self._current_session.next_part_after_transition = tc._next_part_after_transition
        self._current_session.total_overtime_seconds = tc._total_overtime_seconds
        self._current_session.last_save_time = datetime.now().isoformat()

    def set_network_broadcast_state(self, is_active: bool):
        """Update the network broadcast state in the session"""
        logger.debug("set_network_broadcast_state called with: %s", is_active)
        if self._current_session:
            self._current_session.network_broadcast_active = is_active
            logger.debug("Session network_broadcast_active now: %s", self._current_session.network_broadcast_active)
        else:
            logger.debug("No current session to update network broadcast state")

    def end_session(self, clean: bool = True):
        """End the current session"""
        self._autosave_timer.stop()

        if clean:
            # Clean exit - delete the session file
            self._delete_session_file()

        self._current_session = None

    def check_for_recovery(self) -> Optional[SessionState]:
        """Check if there's a recoverable session from a crash"""
        if not self.session_file.exists():
            return None

        try:
            with open(self.session_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            session = SessionState.from_dict(data)

            # If clean_exit is True, previous session ended normally
            if session.clean_exit:
                self._delete_session_file()
                return None

            return session

        except (json.JSONDecodeError, KeyError, IOError) as e:
            logger.error("Error reading session file: %s", e)
            return None

    def is_session_stale(self, session: SessionState) -> bool:
        """Check if a session is older than STALE_SESSION_HOURS"""
        if not session.last_save_time:
            return True

        try:
            last_save = datetime.fromisoformat(session.last_save_time)
            hours_passed = (datetime.now() - last_save).total_seconds() / 3600
            return hours_passed > self.STALE_SESSION_HOURS
        except ValueError:
            return True

    def is_meeting_changed(self, session: SessionState, meeting: 'Meeting') -> bool:
        """Check if the meeting has changed since the session was saved"""
        current_hash = self._compute_meeting_hash(meeting)
        return session.meeting_hash != current_hash

    def calculate_adjusted_state(self, session: SessionState) -> dict:
        """Calculate adjusted timer state accounting for time passed while app was closed"""
        if not session.last_save_time:
            return {
                'remaining_seconds': session.remaining_seconds,
                'overtime_seconds': 0,
                'was_paused': False
            }

        try:
            last_save = datetime.fromisoformat(session.last_save_time)
            time_passed = (datetime.now() - last_save).total_seconds()
        except ValueError:
            return {
                'remaining_seconds': session.remaining_seconds,
                'overtime_seconds': 0,
                'was_paused': False
            }

        # If timer was paused, no time adjustment needed
        if session.timer_state == "PAUSED":
            return {
                'remaining_seconds': session.remaining_seconds,
                'overtime_seconds': 0,
                'was_paused': True
            }

        # If timer was in overtime, add more overtime
        if session.timer_state == "OVERTIME":
            additional_overtime = int(time_passed)
            return {
                'remaining_seconds': 0,
                'overtime_seconds': abs(session.remaining_seconds) + additional_overtime,
                'was_paused': False
            }

        # Timer was running - subtract time passed from remaining
        adjusted_remaining = session.remaining_seconds - int(time_passed)

        if adjusted_remaining < 0:
            # Part would have gone into overtime
            return {
                'remaining_seconds': 0,
                'overtime_seconds': abs(adjusted_remaining),
                'was_paused': False
            }

        return {
            'remaining_seconds': adjusted_remaining,
            'overtime_seconds': 0,
            'was_paused': False
        }

    def clear_session(self):
        """Clear the session file without marking clean exit"""
        self._autosave_timer.stop()
        self._delete_session_file()
        self._current_session = None

    def has_active_session(self) -> bool:
        """Check if there's an active session being tracked"""
        return self._current_session is not None

    def _autosave(self):
        """Periodic autosave callback"""
        if self._current_session:
            self.update_session_from_controller()
            self._save_session()

    def _save_session(self):
        """Save current session to file"""
        if not self._current_session:
            return

        try:
            self.data_dir.mkdir(parents=True, exist_ok=True)
            with open(self.session_file, 'w', encoding='utf-8') as f:
                json.dump(self._current_session.to_dict(), f, indent=2)
            self.session_saved.emit()
        except IOError as e:
            logger.error("Error saving session: %s", e)

    def _delete_session_file(self):
        """Delete the session file"""
        try:
            if self.session_file.exists():
                self.session_file.unlink()
        except IOError as e:
            logger.error("Error deleting session file: %s", e)

    def _compute_meeting_hash(self, meeting: 'Meeting') -> str:
        """Compute a hash of meeting parts for change detection"""
        parts_data = []
        for part in meeting.get_all_parts():
            parts_data.append(f"{part.title}:{part.duration_minutes}")

        content = "|".join(parts_data)
        return hashlib.md5(content.encode()).hexdigest()[:8]
