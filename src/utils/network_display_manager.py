"""
Network display manager for OnTime Meeting Timer.
This module integrates the WebSocket and HTTP servers to provide network display functionality.
"""
import os
from typing import Optional, Tuple
from datetime import datetime
from PyQt6.QtCore import QObject, pyqtSignal, QTimer

from src.utils.network_broadcaster import NetworkBroadcaster
from src.utils.html_server import NetworkHTTPServer
from src.controllers.timer_controller import TimerController
from src.models.settings import SettingsManager, NetworkDisplayMode
from src.models.timer import TimerState


class NetworkDisplayManager(QObject):
    """Manager for network display functionality"""
    
    # Signals
    display_started = pyqtSignal(str)  # Connection URL
    display_stopped = pyqtSignal()
    client_connected = pyqtSignal(str)
    client_disconnected = pyqtSignal(str)
    status_updated = pyqtSignal(str, int)  # Status message, client count
    network_ready = pyqtSignal()
    
    def __init__(self, timer_controller: TimerController, settings_manager: SettingsManager):
        super().__init__()
        
        self.timer_controller = timer_controller
        self.settings_manager = settings_manager
        
        # Create servers
        self.broadcaster = NetworkBroadcaster()
        self.http_server = NetworkHTTPServer()
        
        # Set up HTML content
        self._setup_html_content()
        
        # La pagina la serve lo stesso server dei dati (una sola porta)
        self.broadcaster.set_html(self.http_server.html_content or self.http_server.default_html)

        # Connect signals
        self._connect_signals()
        
        # Timer for periodic status updates
        self.status_timer = QTimer(self)
        self.status_timer.setInterval(5000)  # 5 seconds
        self.status_timer.timeout.connect(self._update_status)

        # Timer for periodic display refresh - DISABLE FOR NOW TO PREVENT RECURSION
        self.display_refresh_timer = QTimer(self)
        self.display_refresh_timer.setInterval(1000)  # every second
        # self.display_refresh_timer.timeout.connect(self._refresh_display_clock)  # COMMENTED OUT
        
        # Track if we're already updating to prevent recursion
        self._updating_display = False
    
    def _setup_html_content(self):
        """Set up the HTML content for the network display"""
        # Look for the HTML file in the top‑level resources folder
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        html_path = os.path.join(project_root, 'resources', 'network_display.html')

        # Try to load HTML content from file
        if os.path.exists(html_path):
            self.http_server.load_html_content(html_path)
        else:
            # File not found – fall back to an embedded template that matches the real HTML.
            warning = (
                f"[NetworkDisplayManager] WARNING: {html_path} not found. "
                "Using built‑in fallback template for network display."
            )
            print(warning)
            self.status_updated.emit("Using fallback network display template", 0)

            fallback_html = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>OnTime Meeting Timer Display</title>
    <style>
        body {
            background-color: #000000;
            color: #ffffff;
            font-family: 'Tahoma', 'Arial', 'sans-serif';
            margin: 0;
            padding: 0;
            display: flex;
            flex-direction: column;
            justify-content: center;
            align-items: center;
            height: 100vh;
            text-align: center;
            overflow: hidden;
        }

        #timer-display {
            font-family: 'Courier New', monospace;
            font-size: clamp(10vmin, 14vw, 20vmin);
            font-weight: bold;
            margin: 0;
            line-height: 1;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
            max-width: 90vw;
        }

        #info-label {
            font-size: 7vmin;
            font-weight: bold;
            margin: 2vh 5vw;
            max-width: 90vw;
        }

        #end-time-label {
            font-size: 5vmin;
            margin: 1vh 5vw;
            padding: 2vh;
            background-color: rgba(50, 50, 50, 0.8);
            border-radius: 15px;
            max-width: 90vw;
        }

        #status {
            position: absolute;
            top: 10px;
            right: 10px;
            padding: 5px 10px;
            background-color: rgba(0, 0, 0, 0.7);
            border-radius: 5px;
            font-size: 14px;
        }

        .running   { color: #4caf50; }
        .warning   { color: #ff9800; }
        .danger    { color: #f44336; }
        .paused    { color: #2196f3; }
        .transition{ color: #bb86fc; }
        .stopped   { color: #ffffff; }
    </style>
</head>
<body>
    <div id="status">Connecting...</div>

    <h1 id="timer-display" class="stopped">00:00</h1>

    <div id="info-label"></div>

    <div id="end-time-label"></div>

    <script>
        // Elements
        const timerDisplay  = document.getElementById('timer-display');
        const infoLabel     = document.getElementById('info-label');
        const endTimeLabel  = document.getElementById('end-time-label');
        const status        = document.getElementById('status');

        // WebSocket connection (port substituted by HTTP server)
        const socket = new WebSocket(`ws://${window.location.host}/ws`);

        socket.addEventListener('open', () => {
            status.textContent = 'Connected';
            status.style.color = '#4caf50';
        });

        socket.addEventListener('close', () => {
            status.textContent = 'Disconnected';
            status.style.color = '#f44336';
            setTimeout(() => window.location.reload(), 5000);
        });

        socket.addEventListener('message', (event) => {
            try {
                const data = JSON.parse(event.data);

                /* --- TIMER --- */
                timerDisplay.textContent = data.time;
                timerDisplay.className   = data.state;

                /* --- INFO & PREDICTED END --- */
                if (data.state === 'stopped' && data.countdownMessage) {
                    // Pre‑meeting countdown
                    infoLabel.textContent      = 'MEETING STARTING SOON';
                    infoLabel.style.color      = '#4a90e2';

                    endTimeLabel.textContent   = data.countdownMessage;
                    endTimeLabel.style.color   = '#4a90e2';
                    endTimeLabel.style.display = 'block';

                } else if (data.meetingEnded) {
                    // Meeting finished
                    infoLabel.textContent      = 'MEETING COMPLETED';
                    infoLabel.style.color      = '#ffffff';
                    endTimeLabel.style.display = 'none';

                } else if (data.state === 'transition') {
                    // Chairman transition
                    infoLabel.textContent = data.part;
                    infoLabel.style.color = '#bb86fc';
                    endTimeLabel.style.display = data.endTime ? 'block' : 'none';

                } else {
                    // Regular meeting
                    if (data.nextPart) {
                        infoLabel.textContent = `NEXT PART: ${data.nextPart}`;
                    } else if (data.part) {
                        infoLabel.textContent = data.part;
                    } else {
                        infoLabel.textContent = '—';
                    }
                    infoLabel.style.color = '#ffffff';

                    if (data.endTime) {
                        endTimeLabel.textContent = `PREDICTED END: ${data.endTime}`;

                        if (data.overtime && data.overtime > 0) {
                            const mins = Math.floor(data.overtime / 60);
                            endTimeLabel.textContent += ` (+${mins} MIN)`;
                            endTimeLabel.style.color = '#f44336';
                        } else {
                            endTimeLabel.style.color = '#4caf50';
                        }
                        endTimeLabel.style.display = 'block';
                    } else {
                        endTimeLabel.style.display = 'none';
                    }
                }

                /* --- LIVE CLOCK WHEN STOPPED --- */
                if (data.state === 'stopped' && !data.countdownMessage) {
                    const updateClock = () => {
                        const now = new Date();
                        timerDisplay.textContent = now.toTimeString().split(' ')[0];
                    };
                    updateClock();
                    clearInterval(window._clockInterval);
                    window._clockInterval = setInterval(updateClock, 1000);
                } else {
                    clearInterval(window._clockInterval);
                }

            } catch (err) {
                console.error('WS message error:', err);
            }
        });
    </script>
</body>
</html>
"""
            self.http_server.set_html_content(fallback_html)
    
    def _connect_signals(self):
        """Connect signals between components"""
        # Connect broadcaster signals
        self.broadcaster.client_connected.connect(self.client_connected)
        self.broadcaster.client_disconnected.connect(self.client_disconnected)
        self.broadcaster.broadcast_started.connect(self._on_broadcast_started)
        self.broadcaster.broadcast_stopped.connect(self.display_stopped)
        self.broadcaster.error_occurred.connect(self._handle_error)
        
        # Connect HTTP server signals
        self.http_server.server_started.connect(self._on_server_started)
        self.http_server.server_stopped.connect(self._on_server_stopped)
        self.http_server.error_occurred.connect(self._handle_error)
        
        # Connect timer controller signals
        self.timer_controller.timer.time_updated.connect(self._on_time_updated)
        self.timer_controller.timer.state_changed.connect(self._on_state_changed)
        self.timer_controller.part_changed.connect(self._on_part_changed)
        self.timer_controller.predicted_end_time_updated.connect(self._on_predicted_end_time_updated)
        self.timer_controller.meeting_overtime.connect(self._on_meeting_overtime)
        # Connect meeting_countdown_updated without debug print
        # (debug print removed for production)
    
    def start_network_display(self, mode: NetworkDisplayMode, 
                             http_port: Optional[int] = None, 
                             ws_port: Optional[int] = None) -> bool:
        """Start the network display"""
        try:
            # Use default ports if not specified
            if http_port is None:
                http_port = self.settings_manager.settings.network_display.http_port

            if ws_port is None:
                ws_port = self.settings_manager.settings.network_display.ws_port

            # Prevent double start
            if self.broadcaster.is_broadcasting:
                
                return True

            # Una sola porta: la pagina e i dati dello stesso server, in tutte e
            # due le modalita' (prima, "solo WebSocket" non serviva nessuna pagina).
            if mode == NetworkDisplayMode.DISABLED:
                return False
            self.broadcaster.start_broadcasting(ws_port)
            if not self.broadcaster.is_broadcasting:
                return False
            self.status_timer.start()
            self.network_ready.emit()
            return True

                
        except Exception as e:
            self._handle_error(f"Failed to start network display: {str(e)}")
            return False
    
    def stop_network_display(self):
        """Stop the network display"""
        # Stop the HTTP server
        self.http_server.stop_server()
        
        # Stop the WebSocket broadcaster
        self.broadcaster.stop_broadcasting()
        
        # Stop the status timer
        self.status_timer.stop()

        # Stop the periodic display refresh timer
        self.display_refresh_timer.stop()
        
        # Emit signal
        self.display_stopped.emit()
    
    def _on_broadcast_started(self, url: str, port: int):
        """Handle WebSocket broadcast started"""
        # Update status to show WebSocket is running
        self.display_started.emit(url)
        self.status_updated.emit(url, self.broadcaster.get_client_count())
    
    def _on_server_started(self, url: str, port: int):
        """Handle HTTP server started"""
        # Emit signal with connection URL
        self.display_started.emit(url)
    
    def _on_server_stopped(self):
        """Handle HTTP server stopped"""
        # Check if WebSocket is still running
        if not self.broadcaster.is_broadcasting:
            self.display_stopped.emit()
    
    def _update_status(self):
        """Update network display status"""
        # Get client count
        client_count = self.broadcaster.get_client_count()
        
        # Emit status update
        if self.broadcaster.is_broadcasting:
            url = self.broadcaster.get_connection_url()
            self.status_updated.emit(f"Network display active: {url}", client_count)
        else:
            self.status_updated.emit("Network display inactive", 0)
    
    def _handle_error(self, error_message: str):
        """Handle errors from components"""
        #print(f"Network display error: {error_message}")
        self.status_updated.emit(f"Error: {error_message}", 0)
    
    def _refresh_display_clock(self):
        """Refresh the display clock periodically (separate from main timer updates)"""
        # Only update if we're in STOPPED state to show current time
        if (self.timer_controller.timer.state == TimerState.STOPPED and
            self.timer_controller.current_part_index < 0 and
            not self._updating_display):
            
            # Send current time update without recursion
            current_time = datetime.now()
            time_str = current_time.strftime("%H:%M:%S")
            
            # Update broadcaster directly without triggering _on_time_updated
            self.broadcaster.update_timer_data(
                time_str=time_str,
                state="stopped",
                part_title="",
                next_part="",
                end_time="",
                overtime_seconds=0,
                countdown_message="",
                meeting_ended=False
            )
    
    def _on_current_time_updated(self, time_str: str):
        """Handle current time updates (string format) from the timer"""
        # This handles the current_time_updated signal which sends a formatted time string
        if (self.timer_controller.timer.state == TimerState.STOPPED and
            self.timer_controller.current_part_index < 0 and
            not self._updating_display):
            
            # Build countdown message if we have a target meeting time
            current_dt = datetime.now()
            countdown_message = ""
            if hasattr(self.timer_controller.timer, '_target_meeting_time'):
                target = self.timer_controller.timer._target_meeting_time
                if target and target > current_dt:
                    delta = target - current_dt
                    total_seconds = int(delta.total_seconds())
                    if total_seconds > 0:
                        hours, remainder = divmod(total_seconds, 3600)
                        minutes, seconds = divmod(remainder, 60)
                        if hours > 0:
                            countdown_message = f"L'adunanza inizia tra {hours}h {minutes}m {seconds}s"
                        else:
                            countdown_message = f"L'adunanza inizia tra {minutes}m {seconds}s"

            # Broadcast update (ensure part/nextPart are blank so client doesn’t show “LAST PART”)
            self.broadcaster.update_timer_data(
                time_str=time_str,
                state="stopped",
                part_title="",
                next_part="",
                end_time="",
                overtime_seconds=0,
                countdown_message=countdown_message,
                meeting_ended=False
            )
    
    def _on_time_updated(self, seconds: int):
        """Handle timer time updates with proper current time and countdown display"""
        # Prevent recursion
        if self._updating_display:
            print("[NetworkDisplayManager] Recursion detected - skipping update")
            return
            
        # Type check to prevent string/int errors
        if not isinstance(seconds, int):
            print(f"[NetworkDisplayManager] Warning: Expected int, got {type(seconds)}: {seconds}")
            return
            
        # Add stack trace debugging to find the source
        import traceback
        stack = traceback.extract_stack()
        if len(stack) > 50:  # Detect deep recursion
            print("[NetworkDisplayManager] Deep stack detected, aborting update")
            print("Stack depth:", len(stack))
            for frame in stack[-10:]:  # Show last 10 frames
                print(f"  {frame.filename}:{frame.lineno} in {frame.name}")
            return
            
        self._updating_display = True
        
        try:
            # Initialize variables
            current_time = datetime.now()
            time_str = "00:00"
            state_str = "stopped"
            part_title = ""
            next_part_title = ""
            end_time_str = ""
            overtime_seconds = 0
            countdown_message = ""
            meeting_ended = False

            # Check if we're in STOPPED state with no active part (pre-meeting, or pre-meeting countdown)
            if (self.timer_controller.timer.state == TimerState.STOPPED and
                (self.timer_controller.current_part_index < 0 or
                 (hasattr(self.timer_controller.timer, '_target_meeting_time') and
                  getattr(self.timer_controller.timer, '_target_meeting_time') and
                  getattr(self.timer_controller.timer, '_target_meeting_time') > current_time))):

                # Use current time for display in stopped state
                time_str = current_time.strftime("%H:%M:%S")

                # Check if we have a countdown message
                if hasattr(self.timer_controller.timer, '_target_meeting_time'):
                    target = self.timer_controller.timer._target_meeting_time
                    if target and target > current_time:
                        time_diff = target - current_time
                        seconds_remaining = int(time_diff.total_seconds())

                        if seconds_remaining > 0:
                            hours, remainder = divmod(seconds_remaining, 3600)
                            minutes, seconds = divmod(remainder, 60)

                            if hours > 0:
                                countdown_message = f"L'adunanza inizia tra {hours}h {minutes}m {seconds}s"
                            else:
                                countdown_message = f"L'adunanza inizia tra {minutes}m {seconds}s"

                # Clear titles so we don’t show an old part name
                part_title = ""
                next_part_title = ""

            # Check if meeting has ended (after last part completed)
            elif (self.timer_controller.timer.state == TimerState.STOPPED and
                  self.timer_controller.current_part_index >= 0 and
                  len(self.timer_controller.parts_list) > 0 and
                  self.timer_controller.current_part_index >= len(self.timer_controller.parts_list) - 1):

                meeting_ended = True
                time_str = current_time.strftime("%H:%M:%S")

            else:
                # Normal timer operation (during meeting)
                if seconds < 0:  # Overtime
                    minutes = abs(seconds) // 60
                    secs = abs(seconds) % 60
                    time_str = f"-{minutes:02d}:{secs:02d}"
                else:
                    minutes = seconds // 60
                    secs = seconds % 60
                    time_str = f"{minutes:02d}:{secs:02d}"

                # Map timer state to string representation
                state_map = {
                    TimerState.RUNNING: "running",
                    TimerState.PAUSED: "paused",
                    TimerState.OVERTIME: "danger",
                    TimerState.TRANSITION: "transition",
                    TimerState.STOPPED: "stopped",
                    TimerState.COUNTDOWN: "running"
                }

                state_str = state_map.get(self.timer_controller.timer.state, "stopped")

                # If timer is running and less than 60 seconds, use warning color
                if (self.timer_controller.timer.state == TimerState.RUNNING and
                    0 < self.timer_controller.timer.remaining_seconds <= 60):
                    state_str = "warning"

                # If in transition state, get the transition message
                if self.timer_controller.timer.state == TimerState.TRANSITION:
                    # Try to get the current transition message from the timer controller
                    if hasattr(self.timer_controller, '_transition_message'):
                        part_title = self.timer_controller._transition_message
                    else:
                        # Fallback to generic message if not stored
                        part_title = "Chairman transition"

                # Get current part title - only used in transition state
                elif self.timer_controller.current_part_index >= 0 and self.timer_controller.parts_list:
                    current_part = self.timer_controller.parts_list[self.timer_controller.current_part_index]
                    part_title = current_part.title

                # Get next part title (for "Next Part:" display)
                next_part_index = self.timer_controller.current_part_index + 1
                if (self.timer_controller.parts_list and
                    next_part_index < len(self.timer_controller.parts_list)):
                    next_part = self.timer_controller.parts_list[next_part_index]
                    next_part_title = next_part.title

                # Get predicted end time
                if hasattr(self.timer_controller, '_predicted_end_time') and self.timer_controller._predicted_end_time:
                    end_time_str = self.timer_controller._predicted_end_time.strftime("%H:%M")

                # Get overtime seconds
                overtime_seconds = getattr(self.timer_controller, '_total_overtime_seconds', 0)

            # Clear stale part titles when timer is stopped *before* the meeting
            if state_str == "stopped" and not countdown_message and not meeting_ended:
                part_title = ""
                next_part_title = ""
            # Update broadcaster with current state
            self.broadcaster.update_timer_data(
                time_str=time_str,
                state=state_str,
                part_title=part_title,
                next_part=next_part_title,
                end_time=end_time_str,
                overtime_seconds=overtime_seconds,
                countdown_message=countdown_message,
                meeting_ended=meeting_ended
            )
            
        finally:
            self._updating_display = False
    
    def _on_state_changed(self, state: TimerState):
        """Handle timer state changes"""
        # Force an immediate update of the display
        self._on_time_updated(self.timer_controller.timer.remaining_seconds)
    
    def _on_part_changed(self, part, index):
        """Handle part changes"""
        # Force an update to reflect the new part
        self._on_time_updated(self.timer_controller.timer.remaining_seconds)
    
    def _on_predicted_end_time_updated(self, original_end_time, predicted_end_time, target_end_time):
        """Handle predicted end time updates"""
        # Store target end time for display formatting
        self._target_end_time = target_end_time
        # Force an update to reflect the new predicted end time
        self._on_time_updated(self.timer_controller.timer.remaining_seconds)
    
    def _on_meeting_overtime(self, total_overtime_seconds):
        """Handle meeting overtime updates"""
        # Force an update to reflect the overtime
        self._on_time_updated(self.timer_controller.timer.remaining_seconds)
    
    def get_connection_info(self) -> Tuple[str, int, int]:
        """Get connection information for network display"""
        http_url = self.broadcaster.get_connection_url() if self.broadcaster.is_broadcasting else ""
        client_count = self.broadcaster.get_client_count()
        active_services = 1 if self.broadcaster.is_broadcasting else 0
        
        return (http_url, client_count, active_services)
    
    def cleanup(self):
        """Ensure everything is stopped cleanly"""
        self.stop_network_display()