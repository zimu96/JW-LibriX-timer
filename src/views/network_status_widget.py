"""
Network status widget for the main window.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QDialog, QFormLayout
)
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap, QFont

from src.utils.network_display_manager import NetworkDisplayManager
from src.models.settings import NetworkDisplayMode
from src.utils.qr_code_utility import generate_qr_code


class NetworkStatusWidget(QWidget):
    """Widget showing network display status and controls"""
    
    def __init__(self, network_manager: NetworkDisplayManager, parent=None):
        super().__init__(parent)
        self.network_manager = network_manager
        self.is_active = False
        
        # Setup UI
        self._setup_ui()
        
        # Connect signals
        self._connect_signals()

        # Sync UI with the current manager state (in case the display was started before the widget was created)
        url, client_count, _ = self.network_manager.get_connection_info()
        if url:
            self._display_started(url)
        else:
            self._display_stopped()
    
    def _setup_ui(self):
        """Setup the UI components"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        
        # Status card
        status_frame = QFrame()
        status_frame.setFrameShape(QFrame.Shape.StyledPanel)
        status_frame.setStyleSheet(
            "QFrame { background-color: rgba(50, 50, 50, 0.1); border-radius: 8px; }"
        )
        status_layout = QVBoxLayout(status_frame)
        
        # Status heading
        heading_layout = QHBoxLayout()
        status_heading = QLabel(self.tr("Network Display"))
        status_heading.setStyleSheet("font-weight: bold; font-size: 14px;")
        heading_layout.addWidget(status_heading)
        
        # Status indicator
        self.status_indicator = QLabel(self.tr("Inactive"))
        self.status_indicator.setStyleSheet("color: #999999;")
        heading_layout.addWidget(self.status_indicator)
        heading_layout.addStretch()
        
        # Toggle button
        self.toggle_button = QPushButton(self.tr("Start"))
        self.toggle_button.setMinimumWidth(100)
        heading_layout.addWidget(self.toggle_button)
        
        status_layout.addLayout(heading_layout)
        
        # Horizontal separator
        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setFrameShadow(QFrame.Shadow.Sunken)
        status_layout.addWidget(separator)
        
        # Status details
        details_layout = QHBoxLayout()
        
        # Connection info
        self.info_label = QLabel(self.tr("Network display is not active"))
        self.info_label.setWordWrap(True)
        details_layout.addWidget(self.info_label, 1)
        
        # QR code (hidden initially)
        self.qr_label = QLabel()
        self.qr_label.setFixedSize(100, 100)
        self.qr_label.setScaledContents(True)
        self.qr_label.setVisible(False)
        details_layout.addWidget(self.qr_label, 0)
        
        status_layout.addLayout(details_layout)
        
        # Add help text
        help_text = QLabel(self.tr(
            "Enable this to display the timer on other devices on the same network. "
            "Configure in Settings > Network Display."
        ))
        help_text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        help_text.setWordWrap(True)
        help_text.setStyleSheet("color: #666666; font-size: 11px;")
        status_layout.addWidget(help_text)
        
        layout.addWidget(status_frame)
    
    def _connect_signals(self):
        """Connect signals"""
        # Connect toggle button
        self.toggle_button.clicked.connect(self._toggle_network_display)
        
        # Connect network manager signals
        self.network_manager.display_started.connect(self._display_started)
        self.network_manager.display_stopped.connect(self._display_stopped)
        self.network_manager.status_updated.connect(self._status_updated)
        self.network_manager.client_connected.connect(self._client_connected)
        self.network_manager.client_disconnected.connect(self._client_disconnected)
        
    
    def set_network_manager(self, manager):
        """
        Attach a NetworkDisplayManager instance so the dock can reflect its
        state even if the network display was started before this widget
        existed.
        """
        if manager is None:
            return

        self.network_manager = manager

        # (Re-)connect manager signals to our own slots
        try:
            manager.display_started.disconnect(self._display_started)
        except (TypeError, RuntimeError):
            pass
        manager.display_started.connect(self._display_started)

        try:
            manager.display_stopped.disconnect(self._display_stopped)
        except (TypeError, RuntimeError):
            pass
        manager.display_stopped.connect(self._display_stopped)

        # Immediate sync
        if manager.broadcaster and manager.broadcaster.is_broadcasting:
            url, _, _ = manager.get_connection_info()
            if url:
                self._display_started(url)
                # Also update the client count
                _, client_count, _ = manager.get_connection_info()
                client_text = f"{client_count} client{'s' if client_count != 1 else ''} connected"
                self.info_label.setText(self.tr(f"Network display running at:\n{url}\n{client_text}"))
        else:
            self._display_stopped()
    
    def _toggle_network_display(self):
        """Toggle network display on/off"""
        if self.is_active:
            self.network_manager.stop_network_display()
            self.toggle_button.setText(self.tr("Start"))
        else:
            # Start network display with current settings
            from src.models.settings import NetworkDisplayMode
            mode = self.network_manager.settings_manager.settings.network_display.mode
            http_port = self.network_manager.settings_manager.settings.network_display.http_port
            ws_port = self.network_manager.settings_manager.settings.network_display.ws_port
            
            self.network_manager.start_network_display(mode, http_port, ws_port)
            self.toggle_button.setText(self.tr("Stop"))

    def _display_started(self, url: str):
        """Handle network display started"""
        self.is_active = True
        self.toggle_button.setText(self.tr("Stop"))
        self.status_indicator.setText(self.tr("Active"))
        self.status_indicator.setStyleSheet("color: #4caf50; font-weight: bold;")
        
        # Update info label
        self.info_label.setText(self.tr(f"Network display running at:\n{url}"))

        # Show QR code if enabled
        if self.network_manager.settings_manager.settings.network_display.qr_code_enabled:
            qr_pixmap = generate_qr_code(url, 100)
            self.qr_label.setPixmap(qr_pixmap)
            self.qr_label.setVisible(True)
    
    def _display_stopped(self):
        """Handle network display stopped"""
        self.is_active = False
        self.toggle_button.setText(self.tr("Start"))
        self.status_indicator.setText(self.tr("Inactive"))
        self.status_indicator.setStyleSheet("color: #999999;")
        
        # Update info label
        self.info_label.setText(self.tr("Network display is not active"))

        # Hide QR code
        self.qr_label.setVisible(False)
    
    def _status_updated(self, message: str, client_count: int):
        """Handle status updates"""
        if self.is_active:
            client_text = f"{client_count} client{'s' if client_count != 1 else ''} connected"
            self.info_label.setText(self.tr(f"{message}\n{client_text}"))

    def _client_connected(self, client_id: str):
        """Handle client connection"""
        # Update client count in status
        url, client_count, active_services = self.network_manager.get_connection_info()
        client_text = f"{client_count} client{'s' if client_count != 1 else ''} connected"
        self.info_label.setText(self.tr(f"Network display running at:\n{url}\n{client_text}"))

    def _client_disconnected(self, client_id: str):
        """Handle client disconnection"""
        # Update client count in status
        url, client_count, active_services = self.network_manager.get_connection_info()
        client_text = f"{client_count} client{'s' if client_count != 1 else ''} connected"
        self.info_label.setText(self.tr(f"Network display running at:\n{url}\n{client_text}"))


class NetworkInfoDialog(QDialog):
    """Dialog showing detailed network display information"""
    
    def __init__(self, network_manager: NetworkDisplayManager, parent=None):
        super().__init__(parent)
        self.network_manager = network_manager
        
        # Setup UI
        self._setup_ui()
    
    def _setup_ui(self):
        """Setup the UI components"""
        self.setWindowTitle(self.tr("Network Display Information"))
        self.setMinimumWidth(400)
        
        layout = QVBoxLayout(self)
        
        # Connection info
        info_frame = QFrame()
        info_frame.setFrameShape(QFrame.Shape.StyledPanel)
        info_layout = QFormLayout(info_frame)
        
        # URL
        url, client_count, active_services = self.network_manager.get_connection_info()
        self.url_label = QLabel(url if url else "Not active")
        self.url_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        info_layout.addRow("Connection URL:", self.url_label)
        
        # WebSocket port
        self.ws_port_label = QLabel(str(self.network_manager.settings_manager.settings.network_display.ws_port))
        self.ws_port_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        info_layout.addRow("WebSocket Port:", self.ws_port_label)
        
        # HTTP port (if active)
        if self.network_manager.settings_manager.settings.network_display.mode == NetworkDisplayMode.HTTP_AND_WS:
            self.http_port_label = QLabel(str(self.network_manager.settings_manager.settings.network_display.http_port))
            self.http_port_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            info_layout.addRow("HTTP Port:", self.http_port_label)
        
        # Client count
        self.client_count_label = QLabel(str(client_count))
        info_layout.addRow("Connected Clients:", self.client_count_label)
        
        # Active services
        services_text = f"{active_services} service{'s' if active_services != 1 else ''} running"
        self.services_label = QLabel(services_text)
        info_layout.addRow("Active Services:", self.services_label)
        
        layout.addWidget(info_frame)
        
        # QR code (if enabled)
        if self.network_manager.settings_manager.settings.network_display.qr_code_enabled and url:
            # QR code group
            qr_frame = QFrame()
            qr_frame.setFrameShape(QFrame.Shape.StyledPanel)
            qr_layout = QVBoxLayout(qr_frame)
            
            # QR code heading
            qr_heading = QLabel(self.tr("QR Code for Easy Connection"))
            qr_heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
            qr_heading.setStyleSheet("font-weight: bold;")
            qr_layout.addWidget(qr_heading)
            
            # QR code
            qr_label = QLabel()
            qr_pixmap = generate_qr_code(url, 200)
            qr_label.setPixmap(qr_pixmap)
            qr_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            qr_layout.addWidget(qr_label)
            
            # QR code instructions
            qr_instructions = QLabel(self.tr("Scan this code with your mobile device to connect"))
            qr_instructions.setAlignment(Qt.AlignmentFlag.AlignCenter)
            qr_layout.addWidget(qr_instructions)
            
            layout.addWidget(qr_frame)
        
        # Connection instructions
        instructions_label = QLabel(self.tr(
            "To connect from other devices:\n\n"
            "1. Make sure all devices are on the same network (LAN/WiFi)\n"
            "2. Open a web browser on the client device\n"
            "3. Enter the URL shown above in the browser\n"
            "4. The timer display should appear automatically\n\n"
            "If you have trouble connecting, check your network settings and firewall configuration."
        ))
        instructions_label.setWordWrap(True)
        layout.addWidget(instructions_label)
        
        # Close button
        close_button = QPushButton(self.tr("Close"))
        close_button.clicked.connect(self.accept)
        layout.addWidget(close_button)