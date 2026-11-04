""""Translator module for loading language translations in a PyQt application."""
# -*- coding: utf-8 -*-

import os
from pathlib import Path
from PyQt6.QtCore import QTranslator, QLocale, QCoreApplication

_current_translator = None

"""
Translation utility for the OnTime application.
"""
import os
from pathlib import Path
from PyQt6.QtCore import QTranslator, QLocale, QCoreApplication

_current_translator = None

def load_translation(app, language_code):
    """
    Load translation for the specified language.
    
    Args:
        app: QApplication instance
        language_code: Language code (e.g., 'en', 'it', 'fr', 'de')
    
    Returns:
        bool: True if translation was loaded successfully, False otherwise
    """
    global _current_translator
    
    print(f"[LANG] Attempting to load language: {language_code}")
    
    # Remove existing translator
    if _current_translator:
        print(f"[LANG] Removing existing translator")
        app.removeTranslator(_current_translator)
        _current_translator = None
    
    # For English, don't load any translator (use source strings)
    if language_code == 'en':
        print("[LANG] Using English (source language)")
        return True
    
    # Create new translator
    translator = QTranslator()
    
    # Find the application root directory more robustly
    current_file = Path(__file__).resolve()
    
    # Look for translations directory by going up the directory tree
    search_paths = [
        current_file.parent.parent.parent,  # From src/utils/ go to app root
        current_file.parent.parent,         # From utils/ go to src parent
        current_file.parent,                # Same directory as this file
        Path.cwd(),                         # Current working directory
    ]
    
    qm_file = None
    for search_path in search_paths:
        potential_qm = search_path / "translations" / "qm" / f"ontime_{language_code}.qm"
        print(f"[LANG] Checking: {potential_qm}")
        if potential_qm.exists() and potential_qm.stat().st_size > 50:
            qm_file = potential_qm
            break
    
    if not qm_file:
        print(f"[LANG] Translation file not found for: {language_code}")
        print(f"[LANG] Searched paths:")
        for path in search_paths:
            print(f"    {path / 'translations' / 'qm' / f'ontime_{language_code}.qm'}")
        return False
    
    print(f"[LANG] Found translation file: {qm_file}")
    print(f"[LANG] File size: {qm_file.stat().st_size} bytes")
    
    # Try multiple loading methods in order of preference
    loading_methods = [
        # Method 1: Load with full absolute path
        lambda: translator.load(str(qm_file.resolve())),
        
        # Method 2: Load with directory and filename (without extension)
        lambda: translator.load(qm_file.stem, str(qm_file.parent)),
        
        # Method 3: Load with the ontime_ prefix
        lambda: translator.load(f"ontime_{language_code}", str(qm_file.parent)),
        
        # Method 4: Load just the language code
        lambda: translator.load(language_code, str(qm_file.parent)),
    ]
    
    for i, method in enumerate(loading_methods, 1):
        try:
            print(f"[LANG] Trying loading method {i}...")
            if method():
                print(f"[LANG] Successfully loaded translation with method {i}")
                
                # Install the translator
                if app.installTranslator(translator):
                    _current_translator = translator
                    print(f"[LANG] Successfully installed translator for: {language_code}")
                    
                    # Verify the translation works by testing a known string
                    test_translation = QCoreApplication.translate("MainWindow", "OnTime Meeting Timer")
                    print(f"[LANG] Test translation: '{test_translation}'")
                    
                    return True
                else:
                    print(f"[LANG] Failed to install translator for: {language_code}")
                    return False
            else:
                print(f"[LANG] Method {i} failed to load translation")
                
        except Exception as e:
            print(f"[LANG] Method {i} raised exception: {e}")
    
    print(f"[LANG] All loading methods failed for: {language_code}")
    return False

def get_available_languages():
    """Get list of available language codes based on existing QM files."""
    languages = ['en']  # English is always available
    
    app_dir = Path(__file__).parent.parent.parent
    qm_dir = app_dir / "translations" / "qm"
    
    if qm_dir.exists():
        for qm_file in qm_dir.glob("ontime_*.qm"):
            lang_code = qm_file.stem.replace("ontime_", "")
            if lang_code not in languages:
                languages.append(lang_code)
    
    return languages

def get_current_language():
    """Get the current system language code."""
    locale = QLocale.system()
    return locale.name()[:2]  # Get just the language part (e.g., 'en' from 'en_US')