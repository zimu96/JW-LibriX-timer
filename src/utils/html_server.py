"""
Simple HTTP server to serve the HTML client page for network display.
"""
import os
import threading
import socket
from http.server import HTTPServer, SimpleHTTPRequestHandler
from functools import partial
from typing import Dict, Optional
from PyQt6.QtCore import QObject, pyqtSignal
import traceback
import time

class RobustHTTPServer(HTTPServer):
    """HTTP Server that's more tolerant of dropped connections"""
    
    def handle_error(self, request, client_address):
        """Handle errors gracefully without stacktraces"""
        print(f"Error handling request from {client_address}")
    
    def server_bind(self):
        """Set socket options for address reuse"""
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        HTTPServer.server_bind(self)

class CustomHandler(SimpleHTTPRequestHandler):
    """Custom HTTP request handler that serves the HTML page and handles socket errors gracefully"""
    
    def __init__(self, *args, **kwargs):
        self.html_content = kwargs.pop('html_content', None)
        self.ws_port = kwargs.pop('ws_port', 8765)
        
        # Set timeout to avoid blocking indefinitely
        self.timeout = 5
        
        try:
            super().__init__(*args, **kwargs)
        except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError, socket.timeout, OSError) as e:
            print(f"Connection error in CustomHandler initialization: {e}")
            # Don't reraise, let the handler gracefully terminate
    
    def handle(self):
        """Override handle method to catch socket errors"""
        try:
            super().handle()
        except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError, socket.timeout, OSError) as e:
            print(f"Socket error during request handling: {e}")
            # Don't reraise, let the handler gracefully terminate
    
    def handle_one_request(self):
        """Override to catch socket errors at the request level"""
        try:
            return super().handle_one_request()
        except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError, socket.timeout, OSError) as e:
            print(f"Socket error during individual request: {e}")
            self.close_connection = True
            return
    
    def do_GET(self):
        """Handle GET requests"""
        try:
            print(f"GET request path: {self.path}")
            if self.path == '/' or self.path == '/index.html':
                self.send_response(200)
                self.send_header('Content-type', 'text/html')
                self.end_headers()
                
                # If we have custom HTML content, inject WebSocket port and serve it
                if self.html_content:
                    html = self.html_content.replace('{WS_PORT}', str(self.ws_port))
                    self.wfile.write(html.encode('utf-8'))
                else:
                    # Fallback to generic response
                    self.wfile.write(b'<html><body><h1>OnTime Meeting Timer</h1><p>Network display server is running.</p></body></html>')
            else:
                # For any other path, return 404
                self.send_response(404)
                self.end_headers()
                self.wfile.write(b'Not Found')
        except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError, socket.timeout, OSError) as e:
            print(f"Error serving GET request: {e}")
            self.close_connection = True
            # Don't reraise, just log the error
    
    def log_message(self, format, *args):
        """Suppress log messages"""
        pass


class NetworkHTTPServer(QObject):
    """HTTP server to serve the HTML client interface"""
    
    # Signals
    server_started = pyqtSignal(str, int)  # URL, port
    server_stopped = pyqtSignal()
    error_occurred = pyqtSignal(str)
    
    def __init__(self):
        super().__init__()
        
        # Server properties
        self.server = None
        self.thread = None
        self.host_ip = self._get_local_ip()
        self.port = 8080  # Default HTTP port
        self.html_content = None
        self.ws_port = 8765  # Default WebSocket port
        self.is_running = False
        
        # Default HTML if none is provided
        self._create_default_html()
    
    def _get_local_ip(self) -> str:
        """Get the local IP address of this machine"""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            # This doesn't actually establish a connection
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "127.0.0.1"
    
    def _create_default_html(self):
        """Create a default HTML template for network display"""
        self.default_html = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>OnTime Meeting Timer Display</title>
    <style>
        body {
            background-color: #000000;
            color: #ffffff;
            font-family: 'Tahoma', 'Arial', sans-serif;
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
        
        .running { color: #4caf50; }
        .warning { color: #ff9800; }
        .danger { color: #f44336; }
        .paused { color: #2196f3; }
        .transition { color: #bb86fc; }
        .stopped { color: #ffffff; }
        .countdown { color: #4a90e2; }
    </style>
</head>
<body>
    <div id="status">Connecting...</div>
    
    <h1 id="timer-display" class="stopped">00:00</h1>
    
    <div id="info-label"></div>
    
    <div id="end-time-label"></div>
    
    <script>
        // Timer display elements
        const timerDisplay = document.getElementById('timer-display');
        const infoLabel = document.getElementById('info-label');
        const endTimeLabel = document.getElementById('end-time-label');
        const status = document.getElementById('status');
        
        // Create WebSocket connection
        const socket = new WebSocket(`ws://${window.location.host}/ws`);
        
        // Connection opened
        socket.addEventListener('open', function(event) {
            status.textContent = 'Connected';
            status.style.color = '#4caf50';
        });
        
        // Connection closed
        socket.addEventListener('close', function(event) {
            status.textContent = 'Disconnected';
            status.style.color = '#f44336';
            
            // Try to reconnect after 5 seconds
            setTimeout(function() {
                window.location.reload();
            }, 5000);
        });
        
        // Listen for messages
        socket.addEventListener('message', function(event) {
            try {
                const data = JSON.parse(event.data);
                
                // Update timer display
                timerDisplay.textContent = data.time;
                
                // Set timer color based on state
                timerDisplay.className = data.state;
                
                // Handle meeting countdown display
                if (data.state === 'stopped' && data.countdownMessage) {
                    // We're in pre-meeting countdown mode
                    infoLabel.textContent = "MEETING STARTING SOON";
                    infoLabel.style.color = "#4a90e2";
                    
                    endTimeLabel.textContent = data.countdownMessage;
                    endTimeLabel.style.color = "#4a90e2";
                    endTimeLabel.style.display = "block";
                } 
                else if (data.state === 'transition') {
                    // Show chairman transition message
                    infoLabel.textContent = data.part;
                    infoLabel.style.color = "#bb86fc"; // Purple for transitions
                    
                    // Keep showing end time if available
                    if (data.endTime) {
                        endTimeLabel.style.display = "block";
                    } else {
                        endTimeLabel.style.display = "none";
                    }
                }
                else if (data.meetingEnded) {
                    // Meeting ended
                    infoLabel.textContent = "MEETING COMPLETED";
                    infoLabel.style.color = "#ffffff";
                    endTimeLabel.style.display = "none";
                }
                else {
                    // Regular meeting or part display
                    if (data.nextPart) {
                        infoLabel.textContent = `NEXT PART: ${data.nextPart}`;
                        infoLabel.style.color = "#ffffff";
                    } else {
                        infoLabel.textContent = "LAST PART";
                        infoLabel.style.color = "#ffffff";
                    }
                    
                    // Update end time if available
                    if (data.endTime) {
                        endTimeLabel.textContent = `PREDICTED END: ${data.endTime}`;
                        
                        // Add overtime information if available
                        if (data.overtime > 0) {
                            const minutes = Math.floor(data.overtime / 60);
                            endTimeLabel.textContent += ` (+${minutes} MIN)`;
                            endTimeLabel.style.color = '#f44336';
                        } else {
                            endTimeLabel.style.color = '#4caf50';
                        }
                        
                        endTimeLabel.style.display = "block";
                    } else {
                        endTimeLabel.style.display = "none";
                    }
                }
                
                // Update current time when in stopped state
                if (data.state === 'stopped' && !data.countdownMessage) {
                    // Use the browser's clock to update every second
                    function updateClock() {
                        const now = new Date();
                        timerDisplay.textContent = now.toTimeString().split(' ')[0];
                    }
                    updateClock();
                    clearInterval(window.clockInterval);
                    window.clockInterval = setInterval(updateClock, 1000);
                } else {
                    clearInterval(window.clockInterval);
                }
                
            } catch (error) {
                console.error('Error parsing message:', error);
            }
        });
    </script>
</body>
</html>
"""
    
    def load_html_content(self, html_path: str) -> bool:
        """Load HTML content from file"""
        try:
            with open(html_path, 'r', encoding='utf-8') as f:
                self.html_content = f.read()
                
            return True
        except Exception as e:
            self.error_occurred.emit(f"Failed to load HTML content: {str(e)}")
            # Use default HTML as fallback
            self.html_content = self.default_html
            print("Using default HTML template as fallback")
            return False
    
    def set_html_content(self, html_content: str):
        """Set HTML content directly"""
        self.html_content = html_content
        #print(f"HTML content set directly, size: {len(self.html_content)} bytes")
    
    def start_server(self, port: Optional[int] = None, ws_port: Optional[int] = None):
        """Start the HTTP server"""
        print(f"Attempting to start HTTP server on {self.host_ip}:{self.port}")
        server_address = ('0.0.0.0', self.port)
        if self.is_running:
            print("Server is already running, not starting again")
            return
        
        # Update ports if specified
        if port:
            self.port = port
            print(f"Using specified HTTP port: {port}")
        
        if ws_port:
            self.ws_port = ws_port
            print(f"Using specified WebSocket port: {ws_port}")
        
        # Use default HTML content if none was provided
        if not self.html_content:
            self.html_content = self.default_html
            print("Using default HTML template")
        
        # Define a handler factory that includes our custom parameters
        def handler_factory(*args, **kwargs):
            print("Creating handler for incoming connection")
            try:
                return CustomHandler(
                    *args, 
                    html_content=self.html_content,
                    ws_port=self.ws_port,
                    **kwargs
                )
            except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError, socket.timeout, OSError) as e:
                print(f"Socket error during handler creation: {e}")
                traceback.print_exc()
                # Return a dummy handler that does nothing
                class DummyHandler(SimpleHTTPRequestHandler):
                    def handle(self): pass
                    def handle_one_request(self): pass
                return DummyHandler(*args, **kwargs)
            
        handler_class = partial(CustomHandler, html_content=self.html_content, ws_port=self.ws_port)
        self.server = RobustHTTPServer(server_address, handler_class)
        
        def run_server():
            try:
                #print(f"Binding server to {self.host_ip}:{self.port}")
                server_address = ('0.0.0.0', self.port)
                
                self.server = RobustHTTPServer(server_address, handler_class)
                self.server.timeout = 10  # Set timeout to 10 seconds
                
                # Set an explicit timeout on the socket
                self.server.socket.settimeout(5)
                
                # Flag as running before emitting signal
                self.is_running = True
                print(f"HTTP server started successfully on {self.host_ip}:{self.port}")
                
                # Emit started signal
                self.server_started.emit(f"http://{self.host_ip}:{self.port}", self.port)
                
                # Serve forever with periodic checks
                while self.is_running:
                    try:
                        self.server.handle_request()
                        time.sleep(0.1)  # Small delay to reduce CPU usage
                    except (OSError, socket.error) as e:
                        print(f"Socket error in server loop: {e}")
                        if not self.is_running:  # Break if we're shutting down
                            break
                        # Otherwise, continue serving
                        continue
            except OSError as e:
                self.error_occurred.emit(f"Failed to start HTTP server: {str(e)}")
                self.is_running = False
            except Exception as e:
                self.error_occurred.emit(f"Error in HTTP server: {str(e)}")
                traceback.print_exc()
                self.is_running = False
            finally:
                # Ensure is_running is set to False when the server stops
                self.is_running = False
        
        # Start the server in a separate thread
        self.thread = threading.Thread(target=run_server, daemon=True)
        self.thread.start()
        print("Server thread started")
    
    def stop_server(self):
        """Stop the HTTP server"""
        if not self.is_running:
            return
        
        # Flag to stop the server loop
        self.is_running = False
        
        # Shutdown the server
        if self.server:
            try:
                # Create a final connection to trigger handle_request to return
                try:
                    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                        s.connect((self.host_ip, self.port))
                        s.close()
                except:
                    pass  # Ignore connection errors during shutdown
                
                # Close the server
                self.server.server_close()
                print("HTTP server closed")
            except Exception as e:
                print(f"Error closing HTTP server: {e}")
        
        # Wait for thread to terminate with timeout
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=2)
            print("HTTP server thread joined")
        
        # Emit signal
        self.server_stopped.emit()
        print("HTTP server stopped")
    
    def get_url(self) -> str:
        """Get the URL clients can use to connect"""
        return f"http://{self.host_ip}:{self.port}"