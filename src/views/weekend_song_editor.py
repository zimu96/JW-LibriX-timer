"""
Dialog for editing weekend meeting songs in the OnTime Meeting Timer application.
"""
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFormLayout, QSpinBox, QDialogButtonBox, QMessageBox
)
from PyQt6.QtCore import Qt

import re

# La parola «cantico» nelle lingue dell'app: l'editor cercava solo «song», e
# con i titoli in italiano («Cantico iniziale e preghiera») non trovava niente.
PAROLE_CANTICO = r"(?:song|cantico|canto|cantique|lied|canci[oó]n|c[aâ]ntico)"


def e_un_cantico(titolo: str) -> bool:
    return re.search(r"\b" + PAROLE_CANTICO + r"\b", titolo.lower()) is not None


def numero_nel_titolo(titolo: str):
    m = re.search(r"\b" + PAROLE_CANTICO + r"\s+(\d+)", titolo.lower())
    return int(m.group(1)) if m else None


def titolo_con_numero(titolo: str, numero: int) -> str:
    """Mette il numero del cantico nel titolo, nella stessa lingua del titolo."""
    if numero_nel_titolo(titolo) is not None:
        return re.sub(r"(\b" + PAROLE_CANTICO + r"\s+)\d+", lambda m: f"{m.group(1)}{numero}",
                      titolo, count=1, flags=re.IGNORECASE)
    qualifica = re.sub(r"(\b" + PAROLE_CANTICO + r")\s+(iniziale|finale|di apertura|di chiusura"
                       r"|opening|concluding)\b", lambda m: f"{m.group(1)} {numero}",
                       titolo, count=1, flags=re.IGNORECASE)
    if qualifica != titolo:
        return qualifica
    return re.sub(r"(\b" + PAROLE_CANTICO + r")\b", lambda m: f"{m.group(1)} {numero}",
                  titolo, count=1, flags=re.IGNORECASE)


class WeekendSongEditorDialog(QDialog):
    """Dialog for editing weekend meeting songs"""
    
    def __init__(self, meeting, parent=None):
        super().__init__(parent)
        self.setWindowTitle(self.tr("Edit Weekend Meeting Songs"))
        self.meeting = meeting
        self.song_fields = []

        # Ensure dialog appears on top of the main window (especially on Windows)
        self.setWindowFlags(
            self.windowFlags()
            & ~Qt.WindowType.WindowContextHelpButtonHint
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.raise_()
        self.activateWindow()

        # Setup UI
        self._setup_ui()
        
    def _setup_ui(self):
        """Setup the UI components"""
        layout = QVBoxLayout(self)
        
        # Add description
        description = QLabel(
            self.tr("Enter song numbers for the weekend meeting. Leave empty for songs "
            "that don't require a number (like theme songs or musical items).")
        )
        description.setWordWrap(True)
        layout.addWidget(description)
        
        # Create form for songs
        form_layout = QFormLayout()
        
        # Find all parts that contain "song" in their title
        song_parts = []
        for section in self.meeting.sections:
            for part in section.parts:
                if e_un_cantico(part.title):
                    song_parts.append((section.title, part))
        
        # Add fields for each song
        for section_title, part in song_parts:
            # Extract existing song number if present
            existing_number = None
            existing_number = numero_nel_titolo(part.title)
            
            # Create spin box for song number
            spin_box = QSpinBox()
            spin_box.setRange(0, 200)  # 0 = nessun numero (campo vuoto)
            spin_box.setSpecialValueText("")  # Empty for no number
            if existing_number:
                spin_box.setValue(existing_number)
            
            # Create label with context
            if re.search(r"prayer|preghiera", part.title.lower()):
                if re.search(r"opening|inizial", part.title.lower()) or "public" in section_title.lower():
                    label_text = f"{self.tr('Opening Song')} ({section_title}):"
                elif re.search(r"concluding|final", part.title.lower()) or "watchtower" in section_title.lower():
                    label_text = f"{self.tr('Concluding Song')} ({section_title}):"
                else:
                    label_text = f"{self.tr('Song and Prayer')} ({section_title}):"
            else:
                label_text = f"{self.tr('Song')} ({section_title}):"
            
            # Add to form
            form_layout.addRow(label_text, spin_box)
            
            # Store reference to the spin box along with the part
            self.song_fields.append((spin_box, part))
        
        layout.addLayout(form_layout)
        
        # Add dialog buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | 
            QDialogButtonBox.StandardButton.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
    
    def accept(self):
        """Handle dialog acceptance"""
        # Update song titles with numbers
        for spin_box, part in self.song_fields:
            song_number = spin_box.value()
            
            if song_number > 0:  # If a song number was provided
                part.title = titolo_con_numero(part.title, song_number)

        super().accept()