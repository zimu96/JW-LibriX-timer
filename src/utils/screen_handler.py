"""
Screen handling utilities for the OnTime Meeting Timer application.
"""
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QGuiApplication, QScreen


class ScreenHandler:
    """Helper class to manage screen selection and positioning"""
    
    @staticmethod
    def get_all_screens():
        """Get information about all available screens"""
        screens = []
        primary_screen = QApplication.primaryScreen()
        for i, screen in enumerate(QApplication.screens()):
            geometry = screen.geometry()
            screens.append({
                'index': i,
                'name': screen.name(),
                'width': geometry.width(),
                'height': geometry.height(),
                'primary': (screen == primary_screen),
            })
        return screens
    
    @staticmethod
    def get_screen_by_name(name):
        """Get a screen by its name (more reliable than index in some cases)"""
        for screen in QApplication.screens():
            if screen.name() == name:
                return screen
        return None
    
    @staticmethod
    def get_screen_by_index(index):
        """Get a screen by its index"""
        screens = QApplication.screens()
        if 0 <= index < len(screens):
            return screens[index]
        return None
    
    @staticmethod
    def get_primary_screen_index():
        """Get the index of the system's primary screen"""
        primary_screen = QApplication.primaryScreen()
        screens = QApplication.screens()
        for i, screen in enumerate(screens):
            if screen == primary_screen:
                return i
        # If not found, try to match by object identity
        screens = QApplication.screens()
        if primary_screen in screens:
            return screens.index(primary_screen)
        # If no match, prefer non-primary if available
        for i, screen in enumerate(screens):
            if screen != QApplication.primaryScreen():
                return i
        return 0  # fallback to first screen if only one available
    
    @staticmethod
    def save_screen_selection(settings, primary_screen, secondary_screen):
        """Save screen selection with both index and name for robustness"""
        # Save primary screen
        settings.display.primary_screen_index = primary_screen['index']
        settings.display.primary_screen_name = primary_screen['name']
        
        # Save secondary screen
        settings.display.secondary_screen_index = secondary_screen['index']
        settings.display.secondary_screen_name = secondary_screen['name']
        
    @staticmethod
    def get_configured_screen(settings, is_primary=True):
        """Get the configured screen (tries by index first, then by name)"""
        screens = QApplication.screens()

        if is_primary:
            index = settings.display.primary_screen_index
            name = getattr(settings.display, 'primary_screen_name', '')
        else:
            index = settings.display.secondary_screen_index
            name = getattr(settings.display, 'secondary_screen_name', '')

        # Try by index first
        if index is not None and 0 <= index < len(screens):
            screen = screens[index]
            if is_primary or screen != QApplication.primaryScreen():
                return screen

        # If index fails or resolves to primary when it shouldn't, try by name
        if name:
            for screen in screens:
                if screen.name() == name:
                    if is_primary or screen != QApplication.primaryScreen():
                        return screen

        # If all else fails, return primary screen for primary, non-primary for secondary
        if is_primary:
            return QApplication.primaryScreen()
        else:
            primary_screen = QApplication.primaryScreen()
            secondary_candidates = [s for s in screens if s != primary_screen]
            for screen in secondary_candidates:
                if screen.name() != getattr(settings.display, 'primary_screen_name', ''):
                    return screen
            if secondary_candidates:
                return secondary_candidates[0]
            return screens[-1] if screens else None
    
    @staticmethod
    def verify_screen_binding(window, target_screen):
        """Verify if a window is properly bound to the target screen"""
        if not window or not window.windowHandle() or not target_screen:
            return False
        
        current_screen = window.windowHandle().screen()
        return current_screen == target_screen
    
    @staticmethod
    def safe_bind_to_screen(window, target_screen, max_attempts=3):
        """Safely bind a window to a specific screen with retries"""
        if not window or not target_screen:
            return False
        
        for attempt in range(max_attempts):
            try:
                # Set geometry first
                window.setGeometry(target_screen.geometry())
                
                # Then bind to screen
                if window.windowHandle():
                    window.windowHandle().setScreen(target_screen)
                
                # Verify binding
                if ScreenHandler.verify_screen_binding(window, target_screen):
                    return True
                    
            except Exception as e:
                print(f"[ScreenHandler] Binding attempt {attempt + 1} failed: {e}")
        
        return False