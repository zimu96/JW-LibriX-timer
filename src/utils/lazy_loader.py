"""
Lazy loading of components in the application to improve startup time and responsiveness.
This module provides a background thread to load components asynchronously, allowing the main UI to remain responsive.
It also includes a manager class to handle the loading process and caching of components.
The LazyComponentLoader class is responsible for loading components in a separate thread, emitting signals when components are loaded.

"""
from PyQt6.QtCore import QThread, pyqtSignal, QObject, QEventLoop, QTimer, QMetaObject, Qt, pyqtSlot
from PyQt6.QtWidgets import QApplication
import logging
import traceback


class ComponentLoadWorker(QThread):
    """Worker thread for loading components asynchronously"""
    
    # Signals
    component_loaded = pyqtSignal(str, object)  # component_name, component_object
    component_failed = pyqtSignal(str, str)     # component_name, error_message
    progress_updated = pyqtSignal(str, int)     # component_name, progress percentage
    finished = pyqtSignal()
    
    def __init__(self, main_window, components_to_load=None, priority_components=None):
        super().__init__()
        self.main_window = main_window
        self.components_to_load = components_to_load or [
            "meeting_view",
            "network_display_manager",
            "network_widget",
            # Remove "secondary_display_handler" and "secondary_display" from auto-load
            # These are now managed directly by MainWindow
        ]
        self.priority_components = set(priority_components or [])
        self.loaded_components = set()
        self.running = True
        
        # Updated component dependencies (simplified)
        self.dependencies = {
            "network_widget": ["network_display_manager"],
        }
        
        # Map of loader functions
        self.loader_functions = {
            "meeting_view": self._load_meeting_view,
            "network_display_manager": self._load_network_display_manager,
            "network_widget": self._load_network_widget,
        }
    
    def run(self):
        """Load components in priority order with proper dependency handling"""
        try:
            # Process high-priority components first
            priority_list = self._resolve_dependencies(list(self.priority_components))
            for component in priority_list:
                if not self.running:
                    break
                self._load_component(component)
            
            # Then process remaining components
            remaining = [c for c in self.components_to_load 
                        if c not in self.loaded_components]
            remaining_list = self._resolve_dependencies(remaining)
            
            for i, component in enumerate(remaining_list):
                if not self.running:
                    break
                self._load_component(component)
                
                # Update progress
                progress = int(((i + 1) / len(remaining_list)) * 100)
                self.progress_updated.emit(component, progress)
        
        except Exception as e:
            logging.error(f"Error in component loading thread: {str(e)}")
            logging.error(traceback.format_exc())
        finally:
            self.finished.emit()
    
    def _resolve_dependencies(self, component_list):
        """Resolve component dependencies to ensure proper load order"""
        result = []
        visited = set()
        
        def visit(component):
            if component in visited:
                return
            visited.add(component)
            
            # Process dependencies first
            deps = self.dependencies.get(component, [])
            for dep in deps:
                visit(dep)
                
            # Add component after its dependencies
            if component in component_list:
                result.append(component)
        
        # Visit all components to build ordered list
        for component in component_list:
            visit(component)
            
        return result
    
    def _load_component(self, component_name):
        """Load a specific component with error handling"""
        if component_name in self.loaded_components:
            return
            
        try:
            # Find the loader function
            loader_func = self.loader_functions.get(component_name)
            if not loader_func:
                raise ValueError(f"No loader function for component: {component_name}")

            # Build QObject-based components in the GUI thread
            if component_name in (
                "meeting_view",
                "network_display_manager",
                "network_widget",
            ):
                gui_thread = QApplication.instance().thread()
                current_thread = QThread.currentThread()

                # If we're already running on the GUI thread, build directly
                if current_thread == gui_thread:
                    component = loader_func()
                else:
                    # Otherwise build in the GUI thread and wait for completion
                    _holder = {}

                    class _Invoker(QObject):
                        @pyqtSlot()
                        def run(self):
                            _holder["instance"] = loader_func()

                    invoker = _Invoker()
                    invoker.moveToThread(gui_thread)

                    QMetaObject.invokeMethod(
                        invoker,
                        "run",
                        Qt.ConnectionType.BlockingQueuedConnection,
                    )
                    component = _holder["instance"]
            else:
                component = loader_func()

            # Emit the component loaded signal
            self.component_loaded.emit(component_name, component)

            # Add to loaded components
            self.loaded_components.add(component_name)

        except Exception as e:
            # Report loading failure
            error_msg = f"Failed to load component '{component_name}': {str(e)}"
            logging.error(error_msg)
            logging.error(traceback.format_exc())
            self.component_failed.emit(component_name, error_msg)
    
    def _load_meeting_view(self):
        """Load meeting view component"""
        from src.views.meeting_view import MeetingView
        
        return MeetingView(
            self.main_window.meeting_controller,
            self.main_window.timer_controller
        )
    
    def _load_network_display_manager(self):
        """Load network display manager component"""
        from src.utils.network_display_manager import NetworkDisplayManager
        
        return NetworkDisplayManager(
            self.main_window.timer_controller,
            self.main_window.settings_controller.settings_manager
        )
    
    def _load_network_widget(self):
        """Load network status widget component"""
        # Check if network display manager is already loaded
        network_display_manager = getattr(self.main_window, 'network_display_manager', None)
        
        # If not, we need to load it first
        if not network_display_manager:
            network_display_manager = self._load_network_display_manager()
            self.component_loaded.emit("network_display_manager", network_display_manager)
            self.loaded_components.add("network_display_manager")
        
        # Now load the widget
        from src.views.network_status_widget import NetworkStatusWidget
        return NetworkStatusWidget(network_display_manager)
    
    def stop(self):
        """Stop the loading process"""
        self.running = False
        
        # Wait for a short time to allow clean shutdown
        self.wait(1000)
        
        # Force terminate if still running
        if self.isRunning():
            self.terminate()


class ComponentLoadManager(QObject):
    """Manager for lazy loading components with improved error handling"""
    
    # Signals
    component_ready = pyqtSignal(str, object)  # component_name, component
    component_failed = pyqtSignal(str, str)    # component_name, error_message
    all_components_ready = pyqtSignal()
    loading_progress = pyqtSignal(str, int)    # component_name, progress
    
    def __init__(self, main_window):
        super().__init__(main_window)
        self.main_window = main_window
        self.worker = None
        self.component_cache = {}
        self.component_errors = {}
        self.loading_in_progress = False
    
    def start_loading(self, components_to_load=None, priority_components=None):
        """Start loading components in background"""
        if self.loading_in_progress:
            # If loading specific components with priority, update existing worker
            if priority_components and self.worker:
                self.worker.priority_components.update(priority_components)
            return
            
        # Create worker thread
        self.worker = ComponentLoadWorker(
            self.main_window, 
            components_to_load,
            priority_components
        )
        
        # Connect signals
        self.worker.component_loaded.connect(self._on_component_loaded)
        self.worker.component_failed.connect(self._on_component_failed)
        self.worker.progress_updated.connect(self.loading_progress)
        self.worker.finished.connect(self._on_loading_finished)
        
        # Start loading
        self.loading_in_progress = True
        self.worker.start()
    
    def get_component(self, name, blocking=False, timeout=5000):
        """
        Get a component by name, optionally blocking until it's loaded
        
        Args:
            name: Component name
            blocking: If True, block until component is loaded
            timeout: Maximum time to wait in milliseconds (only if blocking)
            
        Returns:
            The component or None if not loaded and non-blocking
        """
        # Check if component is already loaded
        if name in self.component_cache:
            return self.component_cache[name]
            
        # Check if component had a loading error
        if name in self.component_errors:
            logging.warning(f"Component '{name}' previously failed to load: {self.component_errors[name]}")
            if not blocking:  # For non-blocking, just return None on error
                return None
        
        # If not blocking, start loading and return None
        if not blocking:
            # Ensure the loader is running
            if not self.loading_in_progress:
                self.start_loading(priority_components=[name])
            return None
            
        # For blocking mode, wait for the component
        if not self.loading_in_progress:
            self.start_loading(priority_components=[name])
            
        # Create a local event loop to wait for the component
        loop = QEventLoop()
        timer = QTimer()
        timer.setSingleShot(True)
        timer.timeout.connect(loop.quit)
        
        # Set up handler for component loading
        def handle_component_loaded(loaded_name, component):
            if loaded_name == name:
                loop.quit()
                
        # Set up handler for component loading failure
        def handle_component_failed(failed_name, error):
            if failed_name == name:
                loop.quit()
        
        # Connect signals
        self.component_ready.connect(handle_component_loaded)
        self.component_failed.connect(handle_component_failed)
        
        # Start the timer
        timer.start(timeout)
        
        # Final check before waiting (in case it was loaded between checks)
        if name in self.component_cache:
            timer.stop()
            self.component_ready.disconnect(handle_component_loaded)
            self.component_failed.disconnect(handle_component_failed)
            return self.component_cache[name]
            
        # Wait for the component or timeout
        loop.exec()
        
        # Clean up
        timer.stop()
        self.component_ready.disconnect(handle_component_loaded)
        self.component_failed.disconnect(handle_component_failed)
        
        # Return the component if it was loaded
        return self.component_cache.get(name)
    
    def is_component_loaded(self, name):
        """Check if a component is loaded"""
        return name in self.component_cache
    
    def _on_component_loaded(self, name, component):
        """Handle a component being loaded"""
        # Cache the component
        self.component_cache[name] = component
        
        # Remove from errors if previously failed
        if name in self.component_errors:
            del self.component_errors[name]
        
        # Emit signal that component is ready
        self.component_ready.emit(name, component)
    
    def _on_component_failed(self, name, error_message):
        """Handle a component failing to load"""
        # Record the error
        self.component_errors[name] = error_message
        
        # Emit signal for component failure
        self.component_failed.emit(name, error_message)
        
        # Log the error
        logging.error(f"Failed to load component '{name}': {error_message}")
    
    def _on_loading_finished(self):
        """Handle all components being loaded"""
        self.loading_in_progress = False
        
        # Clean up the worker
        if self.worker:
            self.worker = None
        
        # Emit signal for all components loaded
        self.all_components_ready.emit()
    
    def cleanup(self):
        """Clean up resources"""
        if self.worker:
            self.worker.stop()
            self.worker = None
        
        # Clear caches
        self.component_cache.clear()
        self.component_errors.clear()
        self.loading_in_progress = False


# Legacy support classes (keep for compatibility)
class LazyComponentLoader(QThread):
    """Legacy loader - now delegates to ComponentLoadWorker"""
    component_loaded = pyqtSignal(str, object)
    all_components_loaded = pyqtSignal()
    progress_updated = pyqtSignal(str, int)

    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.components_to_load = [
            "meeting_view",
            "network_display_manager",
        ]
        self.loaded_components = set()
        self.running = True
        self.priority_components = set()

    def run(self):
        """Delegate to the new worker"""
        worker = ComponentLoadWorker(self.main_window, self.components_to_load, self.priority_components)
        worker.component_loaded.connect(self.component_loaded)
        worker.progress_updated.connect(self.progress_updated)
        worker.finished.connect(self.all_components_loaded)
        worker.run()

    def stop(self):
        self.running = False

    def set_priority_components(self, components):
        self.priority_components = set(components)
