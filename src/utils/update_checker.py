"""
Update checker for OnTime Meeting Timer application.
Thread-safe implementation that checks for updates against a GitHub repository.
"""
import os
import sys
import json
import time
import platform
import tempfile
import subprocess
from pathlib import Path
import urllib.request
import urllib.error
import ssl

from src import __version__ as CURRENT_VERSION


 # Use certifi bundle to ensure up-to-date CAs on macOS and packaged Python
try:
    import certifi
    SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    SSL_CONTEXT = ssl.create_default_context()
from typing import Dict, Optional, Tuple, Any
from datetime import datetime
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QProgressBar, QMessageBox
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QObject, QTimer


# URL to check for updates
# temporal for testing purposes remember to change it back to the original URL
#UPDATE_CHECK_URL = "file:///Users/griffithsobli-laryea/Documents/meeting_timer/test_version.json"
UPDATE_CHECK_URL = "https://raw.githubusercontent.com/berba-q/meeting_timer/main/version.json"

class UpdateChecker(QObject):
    """Thread-safe update checker"""
    
    # Signals for update status
    update_available = pyqtSignal(dict)
    no_update_available = pyqtSignal()
    error_occurred = pyqtSignal(str)
    
    def __init__(self, parent=None, silent=False):
        super().__init__(parent)
        self.silent = silent
        
    def check_for_updates(self):
        """Check for updates - called from a worker thread"""
        # Add a random query parameter to avoid caching
        
        cache_buster = f"?t={int(time.time())}"
        url = UPDATE_CHECK_URL + cache_buster
        
        for attempt in range(3):
            try:
                with urllib.request.urlopen(url, timeout=15, context=SSL_CONTEXT) as response:
                    content = response.read().decode('utf-8')
                    version_info = json.loads(content)

                    if self._is_newer_version(version_info.get('version', '0.0.0')):
                        self.update_available.emit(version_info)
                    else:
                        self.no_update_available.emit()
                    return
            except urllib.error.URLError as e:
                if attempt == 2:
                    if isinstance(e.reason, ssl.SSLError):
                        self.error_occurred.emit("SSL handshake failed. Check your network or certificate settings.")
                    else:
                        self.error_occurred.emit(str(e))
                else:
                    time.sleep(2 ** attempt)
            except Exception as e:
                if attempt == 2:
                    self.error_occurred.emit(str(e))
                else:
                    time.sleep(2 ** attempt)
    
    def _is_newer_version(self, remote_version: str) -> bool:
        """Compare version strings to determine if remote is newer"""
        remote_version = remote_version.lstrip('v')
        # Parse versions into tuples of integers
        current = [int(x) for x in CURRENT_VERSION.split('.')]
        remote = [int(x) for x in remote_version.split('.')]
        
        # Pad with zeros to make equal length
        max_length = max(len(current), len(remote))
        current.extend([0] * (max_length - len(current)))
        remote.extend([0] * (max_length - len(remote)))
        
        # Compare component by component
        return remote > current


class UpdateDialog(QDialog):
    """Dialog for handling application updates"""
    
    def __init__(self, version_info: Dict[str, Any], parent=None):
        super().__init__(parent)
        self.version_info = version_info
        self.downloaded_file = None
        self.download_thread = None
        
        # Setup UI
        self._setup_ui()
    
    def _setup_ui(self):
        """Setup the dialog UI"""
        self.setWindowTitle("Update Available")
        self.setMinimumWidth(450)
        
        layout = QVBoxLayout(self)
        
        # Update information
        info_label = QLabel(
            f"<b>A new version of OnTime Meeting Timer is available!</b><br><br>"
            f"Current version: {CURRENT_VERSION}<br>"
            f"New version: {self.version_info.get('version', 'Unknown')}<br>"
            f"Released: {self.version_info.get('releaseDate', 'Unknown')}<br><br>"
            f"<b>Release Notes:</b><br>{self.version_info.get('releaseNotes', 'No release notes available.')}"
        )
        info_label.setWordWrap(True)
        layout.addWidget(info_label)
        
        # Links section
        links_layout = QHBoxLayout()

        # Release Notes button
        release_notes_url = self.version_info.get('releaseNotesUrl')
        if release_notes_url:
            release_notes_btn = QPushButton("📋 View Release Notes")
            release_notes_btn.clicked.connect(lambda: self._open_url(release_notes_url))
            links_layout.addWidget(release_notes_btn)

        # Changelog button
        repo_url = release_notes_url.split('/releases/')[0] if release_notes_url else None
        if repo_url:
            changelog_url = f"{repo_url}/blob/main/CHANGELOG.md"
            changelog_btn = QPushButton("📝 View Changelog")
            changelog_btn.clicked.connect(lambda: self._open_url(changelog_url))
            links_layout.addWidget(changelog_btn)

        layout.addLayout(links_layout)
        
        # Progress bar (hidden initially)
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)
        
        # Buttons
        buttons_layout = QHBoxLayout()
        
        self.download_button = QPushButton("Download Update")
        self.download_button.clicked.connect(self._download_update)
        buttons_layout.addWidget(self.download_button)
        
        self.remind_button = QPushButton("Remind Me Later")
        self.remind_button.clicked.connect(self.reject)
        buttons_layout.addWidget(self.remind_button)
        
        self.skip_button = QPushButton("Skip This Version")
        self.skip_button.clicked.connect(self._skip_version)
        buttons_layout.addWidget(self.skip_button)
        
        layout.addLayout(buttons_layout)
    
    def _open_url(self, url):
        """Open URL in the system's default browser"""
        import webbrowser
        try:
            webbrowser.open(url)
        except Exception as e:
            QMessageBox.information(self, "URL", f"Could not open browser. Please visit:\n{url}")
    
    def _download_update(self):
        """Download the update file"""
        # Determine the correct download URL based on platform
        system = platform.system().lower()

        if system == 'windows':
            url_key = 'windows'
        elif system == 'darwin':
            url_key = 'macos'
        elif system == 'linux':
            url_key = 'linux'
        else:
            QMessageBox.warning(self, "Download Failed", "Unsupported platform.")
            return

        # Get the download URL
        download_urls = self.version_info.get('downloadUrl', {})
        download_url = download_urls.get(url_key)

        if not download_url:
            QMessageBox.warning(self, "Download Failed", "No download URL available for your platform.")
            return

        # Get expected SHA256 value if present
        sha_expected = self.version_info.get("sha256", {}).get(url_key)

        # Show progress bar
        self.progress_bar.setVisible(True)
        self.download_button.setEnabled(False)
        self.remind_button.setEnabled(False)
        self.skip_button.setEnabled(False)

        # Create a temporary file to download to
        with tempfile.NamedTemporaryFile(delete=False, suffix=self._get_file_extension()) as temp_file:
            self.downloaded_file = temp_file.name

        # Create a thread for downloading
        self.download_thread = QThread()
        self.download_worker = DownloadWorker(download_url, self.downloaded_file, sha256_expected=sha_expected)
        self.download_worker.moveToThread(self.download_thread)

        # Connect signals
        self.download_thread.started.connect(self.download_worker.start_download)
        self.download_worker.progress_updated.connect(self.progress_bar.setValue)
        self.download_worker.download_finished.connect(self._download_completed)
        self.download_worker.error_occurred.connect(self._download_error)

        # Start download
        self.download_thread.start()
    
    def _download_completed(self):
        """Handle download completion"""
        # Clean up thread
        self.download_thread.quit()
        self.download_thread.wait()
        
        # Ask user if they want to install now
        reply = QMessageBox.question(
            self,
            "Download Complete",
            "The update has been downloaded. Do you want to install it now?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        
        if reply == QMessageBox.StandardButton.Yes:
            # Install the update
            self._install_update()
        else:
            # Clean up downloaded file
            self._cleanup_download()
            self.accept()
    
    def _download_error(self, error_message):
        """Handle download error"""
        # Clean up thread
        self.download_thread.quit()
        self.download_thread.wait()
        
        # Reset UI
        self.progress_bar.setVisible(False)
        self.download_button.setEnabled(True)
        self.remind_button.setEnabled(True)
        self.skip_button.setEnabled(True)
        
        # Show error message
        QMessageBox.warning(self, "Download Failed", error_message)
        
        # Clean up downloaded file if it exists
        self._cleanup_download()
    
    def _cleanup_download(self):
        """Clean up downloaded file"""
        if self.downloaded_file and os.path.exists(self.downloaded_file):
            try:
                os.unlink(self.downloaded_file)
            except Exception as e:
                print(f"Failed to delete temporary file: {e}")
    
    def _install_update(self):
        """Install the downloaded update"""
        if not self.downloaded_file or not os.path.exists(self.downloaded_file):
            QMessageBox.warning(self, "Install Failed", "Update file not found.")
            return
        
        try:
            # Platform-specific installation
            system = platform.system().lower()
            
            if system == 'windows':
                # On Windows, launch the installer
                subprocess.Popen([self.downloaded_file], shell=True)
                
            elif system == 'darwin':
                # On macOS, open the DMG
                subprocess.Popen(['open', self.downloaded_file])
                
            elif system == 'linux':
                # On Linux, make the AppImage executable and run it
                os.chmod(self.downloaded_file, 0o755)
                subprocess.Popen([self.downloaded_file])
                
            # Application will exit to complete installation
            if self.parent():
                self.parent().close()
            
        except Exception as e:
            QMessageBox.warning(self, "Install Failed", f"Failed to install update: {str(e)}")
    
    def _skip_version(self):
        """Skip this version for future update checks"""
        # Save the skipped version to settings
        from src.models.settings import SettingsManager
        try:
            # Get the settings manager
            settings_file = os.path.join(os.path.expanduser("~"), ".ontime", "settings.json")
            settings_manager = SettingsManager(settings_file)
            settings = settings_manager.settings
            # Set skipped version safely
            settings.skipped_version = self.version_info.get('version', '')
            settings_manager.save_settings()
            self.accept()
        except Exception as e:
            print(f"Failed to save skipped version: {e}")
            self.reject()
    
    def _get_file_extension(self) -> str:
        """Get the correct file extension based on platform"""
        system = platform.system().lower()
        
        if system == 'windows':
            return '.exe'
        elif system == 'darwin':
            return '.dmg'
        elif system == 'linux':
            return '.AppImage'
        else:
            return '.bin'


class DownloadWorker(QObject):
    """Worker for downloading the update file"""

    # Signals
    progress_updated = pyqtSignal(int)
    download_finished = pyqtSignal()
    error_occurred = pyqtSignal(str)

    def __init__(self, url, destination, sha256_expected=None):
        super().__init__()
        self.url = url
        self.destination = destination
        self.sha256_expected = sha256_expected

    def _compute_sha256(self, filepath):
        import hashlib
        sha256 = hashlib.sha256()
        with open(filepath, "rb") as f:
            for block in iter(lambda: f.read(4096), b""):
                sha256.update(block)
        return sha256.hexdigest()

    def start_download(self):
        """Start downloading the file"""
        try:
            # Create a request with timeout and user-agent header
            request = urllib.request.Request(self.url, headers={'User-Agent': 'Mozilla/5.0'})

            # Open the URL
            with urllib.request.urlopen(request, timeout=30, context=SSL_CONTEXT) as response:
                # Get file size
                file_size = int(response.info().get('Content-Length', 0))

                # Download the file in chunks
                downloaded_size = 0
                chunk_size = 8192

                with open(self.destination, 'wb') as f:
                    while True:
                        chunk = response.read(chunk_size)
                        if not chunk:
                            break

                        f.write(chunk)
                        downloaded_size += len(chunk)

                        # Update progress
                        if file_size > 0:
                            progress = int((downloaded_size / file_size) * 100)
                            self.progress_updated.emit(progress)

            # After download, verify SHA256 if expected
            if self.sha256_expected:
                actual_sha = self._compute_sha256(self.destination)
                if actual_sha.lower() != self.sha256_expected.lower():
                    self.error_occurred.emit("Downloaded file hash mismatch. Update aborted.")
                    return

            # Download complete
            self.download_finished.emit()

        except Exception as e:
            self.error_occurred.emit(f"Download failed: {str(e)}")


def check_for_updates(parent=None, silent=False):
    """
    Thread-safe check for updates
    
    Args:
        parent: Parent widget for dialogs
        silent: If True, don't show dialogs for errors or "no updates"
        
    Returns:
        Thread object (you don't need to wait for it)
    """
    # Create a checking dialog if not silent
    checking_dialog = None
    if not silent and parent:
        checking_dialog = QMessageBox(parent)
        checking_dialog.setWindowTitle("Checking for Updates")
        checking_dialog.setText("Checking for updates...")
        checking_dialog.setStandardButtons(QMessageBox.StandardButton.NoButton)
        checking_dialog.show()
    
    # Create worker and thread
    thread = QThread(parent)
    checker = UpdateChecker(None, silent)  # No parent for the checker
    checker.moveToThread(thread)
    
    # Handle update available
    def on_update_available(version_info):
        # Close checking dialog if it exists
        if checking_dialog:
            checking_dialog.accept()
        
        # Check if we should skip this version
        try:
            # Get the settings manager
            settings_file = os.path.join(os.path.expanduser("~"), ".ontime", "settings.json")
            if os.path.exists(settings_file):
                from src.models.settings import SettingsManager
                settings_manager = SettingsManager(settings_file)
                
                # Check for skipped version
                if hasattr(settings_manager.settings, 'skipped_version'):
                    skipped_version = settings_manager.settings.skipped_version
                    if skipped_version == version_info.get('version', ''):
                        # Skip this version
                        cleanup()
                        return
        except Exception as e:
            print(f"Failed to check skipped version: {e}")
        
        # Show update dialog if not silent
        if parent:
            update_dialog = UpdateDialog(version_info, parent)
            update_dialog.exec()
        
        # Clean up thread
        cleanup()
    
    # Handle no update available
    def on_no_update():
        # Close checking dialog
        if checking_dialog:
            checking_dialog.accept()
            
        # Show message if not silent
        if not silent and parent:
            QMessageBox.information(
                parent,
                "No Updates Available",
                f"You are using the latest version ({CURRENT_VERSION})."
            )
        
        # Clean up thread
        cleanup()
    
    # Handle error
    def on_error(error_message):
        # Close checking dialog
        if checking_dialog:
            checking_dialog.accept()
            
        # Show error message if not silent
        if not silent and parent:
            QMessageBox.warning(
                parent,
                "Update Check Failed",
                f"Failed to check for updates:\n{error_message}"
            )
        
        # Clean up thread
        cleanup()
    
    # Clean up thread and worker
    def cleanup():
        checker.deleteLater()
        thread.quit()
        thread.wait()
    
    # Connect signals (using QueuedConnection to ensure they run on main thread)
    thread.started.connect(checker.check_for_updates)
    checker.update_available.connect(on_update_available, type=Qt.ConnectionType.QueuedConnection)
    checker.no_update_available.connect(on_no_update, type=Qt.ConnectionType.QueuedConnection)
    checker.error_occurred.connect(on_error, type=Qt.ConnectionType.QueuedConnection)
    
    # Make sure thread is cleaned up when it finishes
    thread.finished.connect(thread.deleteLater)
    
    # Start thread
    thread.start()
    
    # Return thread so it doesn't get garbage collected
    return thread

