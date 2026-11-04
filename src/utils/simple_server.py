# Import necessary modules
import http.server
import socketserver
import threading
import socket
from PyQt6.QtCore import QObject, pyqtSignal

class SimpleNetworkServer(QObject):
    """A simpler network server implementation"""
    
    # Signals
    server_started = pyqtSignal(str, int)  # URL, port
    server_stopped = pyqtSignal()
    error_occurred = pyqtSignal(str)
    
    def __init__(self):
        super().__init__()
        self.is_running = False
        self.server = None
        self.thread = None
        self.port = 8080
        self.ws_port = 8765
        
        # Get the local IP
        self.host_ip = self._get_local_ip()
        
        # Create default HTML content
        self._create_default_html()
    
    def _get_local_ip(self):
        """Get the local IP address"""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except:
            return "127.0.0.1"
    
    def _create_default_html(self):
        """Create default HTML content"""
        self.html_content = f"""<!DOCTYPE html>
<html>
<head>
    <title>OnTime Meeting Timer</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body {{ background: black; color: white; font-family: Arial; text-align: center; margin: 0; padding: 20px; }}
        #timer {{ font-size: 120px; margin: 50px 0; font-family: monospace; font-weight: bold; }}
        #part {{ font-size: 24px; margin: 20px 0; }}
        #next {{ font-size: 18px; margin: 10px 0; color: #aaa; }}
        .green {{ color: #4caf50; }}
        .orange {{ color: #ff9800; }}
        .red {{ color: #f44336; }}
        .blue {{ color: #2196f3; }}
    </style>
</head>
<body>
    <h1>OnTime Meeting Timer</h1>
    <div id="timer" class="green">00:00</div>
    <div id="part">Waiting for connection...</div>
    <div id="next">Next: -</div>
    
    <script>
        // Connect to WebSocket server
        const socket = new WebSocket('ws://{self.host_ip}:{self.ws_port}');
        
        // Elements
        const timer = document.getElementById('timer');
        const part = document.getElementById('part');
        const next = document.getElementById('next');
        
        // Connection opened
        socket.addEventListener('open', (event) => {{
            part.textContent = 'Connected!';
        }});
        
        // Connection closed
        socket.addEventListener('close', (event) => {{
            part.textContent = 'Disconnected - Reconnecting...';
            setTimeout(() => window.location.reload(), 5000);
        }});
        
        // Listen for messages
        socket.addEventListener('message', (event) => {{
            try {{
                const data = JSON.parse(event.data);
                
                // Update timer
                timer.textContent = data.time;
                
                // Update classes based on state
                timer.className = data.state;
                
                // Update part
                if (data.part) {{
                    part.textContent = data.part;
                }}
                
                // Update next part
                if (data.nextPart) {{
                    next.textContent = 'Next: ' + data.nextPart;
                }} else {{
                    next.textContent = 'Next: -';
                }}
            }} catch (err) {{
                console.error('Error parsing message:', err);
            }}
        }});
    </script>
</body>
</html>
"""
    
    def start_server(self, port=None, ws_port=None):
        """Start the HTTP server"""
        if self.is_running:
            print("Server already running")
            return
            
        # Update ports if specified
        if port:
            self.port = port
        if ws_port:
            self.ws_port = ws_port
            
        # Update WebSocket URL in HTML content
        self.html_content = self.html_content.replace(f"{self.host_ip}:{self.ws_port}", f"{self.host_ip}:{self.ws_port}")
            
        def run_server():
            """Run the server in a separate thread"""
            try:
                # Define a simple request handler
                class SimpleHandler(http.server.BaseHTTPRequestHandler):
                    def do_GET(self):
                        try:
                            self.send_response(200)
                            self.send_header('Content-type', 'text/html')
                            self.end_headers()
                            self.wfile.write(self.server.html_content.encode())
                        except Exception as e:
                            print(f"Error handling request: {e}")
                    
                    def log_message(self, format, *args):
                        # Suppress logging
                        pass
                
                # Create a TCP server
                try:
                    print(f"Starting server on 0.0.0.0:{self.port}")
                    httpd = socketserver.TCPServer(("0.0.0.0", self.port), SimpleHandler)
                    httpd.html_content = self.html_content  # Pass content to handler
                    self.server = httpd
                    
                    # Server is running
                    self.is_running = True
                    print(f"Server started on port {self.port}")
                    self.server_started.emit(f"http://{self.host_ip}:{self.port}", self.port)
                    
                    # Serve until stopped
                    httpd.serve_forever()
                except Exception as e:
                    print(f"Error starting server: {e}")
                    self.error_occurred.emit(f"Failed to start server: {e}")
            finally:
                self.is_running = False
                print("Server stopped")
        
        # Start server in a thread
        self.thread = threading.Thread(target=run_server)
        self.thread.daemon = True
        self.thread.start()
    
    def set_html_content(self, html_content):
        """Set the HTML content directly"""
        self.html_content = html_content
        print(f"HTML content set directly, size: {len(self.html_content)} bytes")
    
    def load_html_content(self, file_path):
        """Load HTML content from a file"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                self.html_content = f.read()
                print(f"Loaded HTML content from {file_path}, size: {len(self.html_content)} bytes")
            return True
        except Exception as e:
            print(f"Failed to load HTML from {file_path}: {e}")
            # Keep using default HTML
            return False
    
    def get_url(self):
        """Get the URL for connecting to the server"""
        return f"http://{self.host_ip}:{self.port}"
    
    def stop_server(self):
        """Stop the server"""
        if not self.is_running:
            return
            
        if self.server:
            self.server.shutdown()
            self.server.server_close()
            self.is_running = False
            self.server_stopped.emit()