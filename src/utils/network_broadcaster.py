"""
This module provides functionality to broadcast timer data over the network.
"""
from datetime import datetime
import json
import functools
import asyncio
import threading
import websockets
from http import HTTPStatus
from websockets.asyncio.server import serve
import socket
import time
import traceback
from typing import Dict, Set, Optional, Any, List
from PyQt6.QtCore import QObject, pyqtSignal

class NetworkBroadcaster(QObject):
    """Broadcasts timer data over WebSocket to connected clients"""
    
    # Signals
    client_connected = pyqtSignal(str)
    client_disconnected = pyqtSignal(str)
    broadcast_started = pyqtSignal(str, int)  # URL, port
    broadcast_stopped = pyqtSignal()
    error_occurred = pyqtSignal(str)
    
    def __init__(self):
        super().__init__()
        
        # WebSocket server
        self.server = None
        self.server_task = None
        self.event_loop = None
        self.thread = None
        
        # Connection tracking
        self.connected_clients: Set[Any] = set()
        self.host_ip = self._get_local_ip()
        self.port = 8765  # Default WebSocket port
        self.is_broadcasting = False
        self.html = "<html><body>OnTime</body></html>"
        self._stop_event = threading.Event()
        
        # Current state
        current_time = datetime.now().strftime("%H:%M:%S")
        self.current_state = {
            "time": current_time,
            "state": "stopped",
            "part": "",
            "nextPart": "",
            "endTime": "",
            "overtime": 0,
            "countdownMessage": "",
            "meetingEnded": False
        }
    
    def _get_local_ip(self) -> str:
        """IP di questo computer nella rete locale (quello che il tablet raggiunge)."""
        candidati = []
        for destinazione in (("8.8.8.8", 80), ("10.255.255.255", 1), ("192.168.255.255", 1)):
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                    s.connect(destinazione)       # nessun pacchetto parte davvero
                    candidati.append(s.getsockname()[0])
            except OSError:
                pass
        try:
            candidati += socket.gethostbyname_ex(socket.gethostname())[2]
        except OSError:
            pass
        for ip in candidati:
            if ip and not ip.startswith("127."):
                return ip
        return "127.0.0.1"

    def set_html(self, html: str):
        """La pagina servita a chi apre http://ip:porta/"""
        self.html = html

    def _serve_page(self, connection, request):
        """Le richieste normali ricevono la pagina; solo /ws diventa WebSocket."""
        if request.path.split("?")[0] == "/ws":
            return None
        if request.path.split("?")[0] in ("/", "/index.html"):
            corpo = self.html.replace("{WS_PORT}", str(self.port)).encode("utf-8")
            from websockets.datastructures import Headers
            from websockets.http11 import Response
            return Response(200, "OK", Headers([
                ("Content-Type", "text/html; charset=utf-8"),
                ("Content-Length", str(len(corpo))),
                ("Cache-Control", "no-store"),
                ("Connection", "close"),
            ]), corpo)
        if request.path == "/manifest.json":
            from websockets.datastructures import Headers
            from websockets.http11 import Response
            corpo = json.dumps({"name": "Timer adunanza", "short_name": "Timer", "start_url": "/",
                                "display": "fullscreen", "orientation": "landscape",
                                "background_color": "#000000", "theme_color": "#000000"}).encode()
            return Response(200, "OK", Headers([("Content-Type", "application/manifest+json"),
                                                ("Content-Length", str(len(corpo)))]), corpo)
        return connection.respond(HTTPStatus.NOT_FOUND, "Not found\n")

    async def _handler(self, websocket):
        """Handle WebSocket connections with improved error handling"""
        # Register new client
        self.connected_clients.add(websocket)
        client_id = f"{websocket.remote_address[0]}:{websocket.remote_address[1]}" if websocket.remote_address else "?"
        #print(f"Client connected: {client_id}")
        self.client_connected.emit(client_id)
        
        # Send current state immediately upon connection
        try:
            serialized = json.dumps(self.current_state)
            #print(f"Sending to client {client_id}: {serialized}")
            await websocket.send(serialized)
        except (TypeError, ValueError) as e:
            traceback.print_exc()
        
        try:
            # Keep connection open and handle messages from clients
            async for message in websocket:
                try:
                    # Try to parse the message as JSON
                    data = json.loads(message)
                    
                    # Handle 'request_state' message type
                    if data.get('type') == 'request_state':
                        # Re-send the current state
                        await websocket.send(json.dumps(self.current_state))
                        #print(f"Re-sent state to client {client_id} after request")
                except Exception as e:
                    print(f"Error processing message from client {client_id}: {e}")
        except Exception as e:
            if isinstance(e, ConnectionResetError) or isinstance(e, websockets.exceptions.ConnectionClosed):
                print(f"Client connection closed: {client_id}")
            else:
                print(f"Error in WebSocket handler for {client_id}: {e}")
        finally:
            # Remove disconnected client
            self.connected_clients.discard(websocket)
            self.client_disconnected.emit(client_id)
            #print(f"Client disconnected: {client_id}")
    
    async def _server_main(self):
        """Main server coroutine with improved error handling"""
        try:
            # Start WebSocket server
            #print(f"Starting WebSocket server on {self.host_ip}:{self.port}")
            
            # Create server with ping/pong enabled for better connection management
            async with serve(
                self._handler,
                "0.0.0.0",
                self.port,
                process_request=self._serve_page,
                ping_interval=20,
                ping_timeout=20,
            ) as server:
                self.server = server
                self.is_broadcasting = True
                self.broadcast_started.emit(f"http://{self.host_ip}:{self.port}", self.port)
                self._stop_future = asyncio.get_running_loop().create_future()
                await self._stop_future

        except OSError as e:
            # Handle address already in use or other network errors
            error_msg = f"Failed to start WebSocket server: {str(e)}"
            print(error_msg)
            self.error_occurred.emit(error_msg)
            self.is_broadcasting = False
        except Exception as e:
            error_msg = f"Error in WebSocket server: {str(e)}"
            print(error_msg)
            traceback.print_exc()
            self.error_occurred.emit(error_msg)
            self.is_broadcasting = False

    def start_broadcasting(self, port: Optional[int] = None):
        """Start broadcasting timer data over WebSocket"""
        if self.is_broadcasting:
            print("WebSocket broadcaster already running")
            return
        
        # Update port if specified
        if port:
            self.port = port
            print(f"Using specified WebSocket port: {port}")
        
        # Reset stop event
        self._stop_event.clear()
        
        # Create a new event loop in a separate thread
        self.event_loop = asyncio.new_event_loop()
        
        def run_server():
            try:
                asyncio.set_event_loop(self.event_loop)
                self.server_task = self.event_loop.create_task(self._server_main())
                try:
                    self.event_loop.run_until_complete(self.server_task)
                except RuntimeError as e:
                    if "Event loop stopped before Future completed" in str(e):
                        print("[INFO] Event loop stopped cleanly before Future completed.")
                    else:
                        raise
            except Exception as e:
                print(f"Error in WebSocket server thread: {e}")
                traceback.print_exc()
            finally:
                print("WebSocket server thread finishing")
                if self.event_loop.is_running():
                    self.event_loop.stop()
                    self.event_loop.close()
        
        # Start the server in a separate thread
        self.thread = threading.Thread(target=run_server, daemon=True)
        self.thread.start()
        print("WebSocket broadcaster thread started")
        
        # Small delay to let the server start
        time.sleep(0.5)
    
    def stop_broadcasting(self):
        """Stop broadcasting timer data"""
        if not self.is_broadcasting:
            print("WebSocket broadcaster not running")
            return
        
        print("Stopping WebSocket broadcaster...")
        # Set stop event
        self._stop_event.set()
        
        # Complete the stop future to exit the server loop
        if hasattr(self, '_stop_future') and self._stop_future and not self._stop_future.done():
            if self.event_loop and self.event_loop.is_running():
                self.event_loop.call_soon_threadsafe(lambda: self._stop_future.set_result(None))
        
        # Wait for thread to terminate with timeout
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=3)
            print("WebSocket broadcaster thread joined")
            self.thread = None
            self.server = None
            self.server_task = None
            self.event_loop = None
        
        self.is_broadcasting = False
        self.broadcast_stopped.emit()
        print("WebSocket broadcaster stopped")
    
    async def _broadcast_to_clients(self, data: Dict[str, Any]):
        """Broadcast data to all connected clients with improved error handling"""
        if not self.connected_clients:
            return
        
        # Convert data to JSON
        json_data = json.dumps(data)
        
        # Send to all connected clients
        disconnected_clients = set()
        for client in self.connected_clients:
            try:
                await client.send(json_data)
            except websockets.exceptions.ConnectionClosed:
                # Mark for removal
                disconnected_clients.add(client)
            except Exception as e:
                print(f"Error sending to client {client.remote_address}: {e}")
                disconnected_clients.add(client)
        
        # Remove disconnected clients
        for client in disconnected_clients:
            if client in self.connected_clients:
                self.connected_clients.remove(client)
                try:
                    client_id = f"{client.remote_address[0]}:{client.remote_address[1]}"
                    self.client_disconnected.emit(client_id)
                    print(f"Client disconnected during broadcast: {client_id}")
                except:
                    pass  # Client might not have remote_address anymore
    
    def update_timer_data(self, time_str: str, state: str, part_title: str, 
                next_part: str = "", end_time: str = "", overtime_seconds: int = 0,
                countdown_message: str = "", meeting_ended: bool = False):
        """Update the current timer data and broadcast to clients"""
        # Update current state
        self.current_state = {
            "time": time_str,
            "state": state,
            "part": part_title,
            "nextPart": next_part,
            "endTime": end_time,
            "overtime": overtime_seconds,
            "countdownMessage": countdown_message,
            "meetingEnded": meeting_ended
        }
        
        # Broadcast to clients if server is running
        if self.is_broadcasting and self.event_loop:
            try:
                asyncio.run_coroutine_threadsafe(
                    self._broadcast_to_clients(self.current_state), 
                    self.event_loop
                )
            except Exception as e:
                print(f"Error broadcasting timer data: {e}")
    
    def get_connection_url(self) -> str:
        """Get the URL clients can use to connect"""
        return f"http://{self.host_ip}:{self.port}"

    def get_client_count(self) -> int:
        """Get the number of connected clients"""
        return len(self.connected_clients)
