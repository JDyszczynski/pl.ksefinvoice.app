import sys
import os

def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except AttributeError:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)

def sanitize_text(text, multiline=False):
    """
    Sanityzuje tekst usuwając białe znaki z początku/końca,
    znaki sterujące (np. powrót karetki) oraz wielokrotne spacje.
    Używane przed zapisem do bazy/XML.
    """
    if not text:
        return ""
    
    # 1. Strip whitespace
    text = text.strip()
    
    # 2. Normalize newlines
    if multiline:
        # Normalize CR+LF -> LF
        text = text.replace('\r\n', '\n').replace('\r', '\n')
    else:
        # Remove newlines completely for single-line fields
        text = text.replace('\r\n', ' ').replace('\r', ' ').replace('\n', ' ')
        
    # 3. Remove other control chars (0x00-0x08, 0x0B-0x0C, 0x0E-0x1F)
    # Valid XML chars: #x9 | #xA | #xD | [#x20-#xD7FF] ...
    # Python str.isprintable() handles most logic but we want to allow standard polish chars.
    # Simple regex for control chars (excluding allowed whitespace)
    import re
    # Remove control characters except standard whitespace if multiline allow \n
    if multiline:
        text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', text)
    else:
        text = re.sub(r'[\x00-\x1f]', '', text) # Remove all lower ascii control including newlines/tabs if strictly single line
    
    # 4. Collapse multiple spaces (optional, improves display)
    if not multiline:
        text = re.sub(r'\s+', ' ', text)
    
    return text.strip()

from PySide6.QtCore import QSettings
from PySide6.QtGui import QGuiApplication

def safe_restore_geometry(widget, settings_key, default_percent_w=0.8, default_percent_h=0.8, min_w=800, min_h=600):
    """
    Restores geometry from QSettings using 'settings_key'.
    If not found, centers the widget on the primary screen with default size (percentage of screen).
    Ensures restored geometry is visible on screen.
    """
    settings = QSettings("JaroslawDyszczynski", "KSeFInvoice")
    geometry_bytes = settings.value(settings_key)
    
    restored = False
    if geometry_bytes:
        restored = widget.restoreGeometry(geometry_bytes)
    
    app = QGuiApplication.instance()
    if not app:
        return
        
    screen = app.primaryScreen()
    if not screen:
        return
        
    avail_geo = screen.availableGeometry()
    
    if not restored:
        # Initial sizing logic
        w = int(avail_geo.width() * default_percent_w)
        h = int(avail_geo.height() * default_percent_h)
        
        # Ensure minimums/maximums
        w = max(min_w, min(w, avail_geo.width()))
        h = max(min_h, min(h, avail_geo.height()))
        
        widget.resize(w, h)
        
        # Center
        x = avail_geo.left() + (avail_geo.width() - w) // 2
        y = avail_geo.top() + (avail_geo.height() - h) // 2
        widget.move(x, y)

    else:
        # Validation: If restored window is completely off-screen or invisible, bring it back.
        geo = widget.geometry()
        center = geo.center()
        
        is_visible = False
        for s in app.screens():
            if s.availableGeometry().contains(center):
                is_visible = True
                break
        
        if not is_visible:
            # Move to center of primary screen
            w = geo.width()
            h = geo.height()
            
            # Ensure it fits
            w = min(w, avail_geo.width())
            h = min(h, avail_geo.height())
            
            x = avail_geo.left() + (avail_geo.width() - w) // 2
            y = avail_geo.top() + (avail_geo.height() - h) // 2
            
            widget.setGeometry(x, y, w, h)

def save_geometry(widget, settings_key):
    """
    Saves widget geometry to QSettings.
    """
    settings = QSettings("JaroslawDyszczynski", "KSeFInvoice")
    settings.setValue(settings_key, widget.saveGeometry())
