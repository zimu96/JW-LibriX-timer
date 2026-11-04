"""
Controller for managing meetings in the OnTime Meeting Timer application.
"""
import os
import json
import re
from datetime import datetime, time
from typing import Dict, List, Optional, Tuple
from PyQt6.QtCore import QObject, pyqtSignal
from PyQt6.QtWidgets import QApplication
from PyQt6.QtWidgets import QMessageBox
from PyQt6.QtWidgets import QDialog

from src.models.meeting import Meeting, MeetingType, MeetingSection, MeetingPart, MeetingSource
from src.models.settings import SettingsManager, MeetingSourceMode
from src.models.meeting_template import MeetingTemplate, TemplateType
from src.utils.epub_scraper import EPUBMeetingScraper
from src.utils.helpers import safe_json_load, safe_json_save
from src.views.weekend_song_editor import WeekendSongEditorDialog


class MeetingController(QObject):
    """Controller for managing meeting data"""
    
    # Signals
    meeting_updated = pyqtSignal(Meeting)
    meetings_loaded = pyqtSignal(dict)  # Dict[MeetingType, Meeting]
    error_occurred = pyqtSignal(str)
    part_updated = pyqtSignal(MeetingPart, int, int)  # part, section_index, part_index
    
    def __init__(self):
        super().__init__()
        
        # Setup data directories
        from src.config import USER_DATA_DIR
        self.data_dir = str(USER_DATA_DIR)
        self.meetings_dir = os.path.join(self.data_dir, "meetings")
        
        # Create directories if they don't exist
        os.makedirs(self.data_dir, exist_ok=True)
        os.makedirs(self.meetings_dir, exist_ok=True)
        
        # Load settings
        self.settings_manager = SettingsManager(
            os.path.join(self.data_dir, "settings.json")
        )
        
        # Current meetings
        self.current_meetings: Dict[MeetingType, Meeting] = {}
        self.current_meeting: Optional[Meeting] = None
        
        # Initialize scraper
        self.scraper = EPUBMeetingScraper(self.settings_manager.settings.language)
        
        # Initialize template manager
        self.template_manager = MeetingTemplate()
    
    def _localize_meeting_parts(self, meeting: Meeting) -> Meeting:
        """Replace pattern-based titles with localized text"""
        
        translations = self._get_translations(meeting.language)
        
        for section in meeting.sections:
            for part in section.parts:
                title = part.title
                
                # Handle opening song and prayer
                if title.startswith("OPENING_SONG_PRAYER"):
                    if "|" in title:
                        # Format: "OPENING_SONG_PRAYER|99"
                        song_num = title.split("|")[1]
                        part.title = f"{translations['song']} {song_num} {translations['and_prayer']}"
                    else:
                        # Format: "OPENING_SONG_PRAYER" (no song number)
                        part.title = f"{translations['opening_song_prayer']}"
                
                # Handle middle song
                elif title.startswith("MIDDLE_SONG"):
                    if "|" in title:
                        # Format: "MIDDLE_SONG|99"
                        song_num = title.split("|")[1]
                        part.title = f"{translations['song']} {song_num}"
                    else:
                        # Format: "MIDDLE_SONG 99" or "MIDDLE_SONG"
                        song_match = re.search(r'MIDDLE_SONG\s+(\d+)', title)
                        if song_match:
                            song_num = song_match.group(1)
                            part.title = f"{translations['song']} {song_num}"
                        else:
                            part.title = translations['song']
                
                # Handle closing song and prayer
                elif title.startswith("CLOSING_SONG_PRAYER"):
                    if "|" in title:
                        # Format: "CLOSING_SONG_PRAYER|100"
                        song_num = title.split("|")[1]
                        part.title = f"{translations['song']} {song_num} {translations['and_prayer']}"
                    else:
                        # Format: "CLOSING_SONG_PRAYER [100" or just "CLOSING_SONG_PRAYER"
                        song_match = re.search(r'CLOSING_SONG_PRAYER\s*\[?(\d+)', title)
                        if song_match:
                            song_num = song_match.group(1)
                            part.title = f"{translations['song']} {song_num} {translations['and_prayer']}"
                        else:
                            part.title = f"{translations['closing_song_prayer']}"
                
                # Handle comments
                elif title == "OPENING_COMMENTS":
                    part.title = translations['opening_comments']
                elif title == "CONCLUDING_COMMENTS":
                    part.title = translations['concluding_comments']
        
        return meeting

    def _get_translations(self, language: str) -> dict:
        """Get translations for ANY language (scalable to 20+)"""
        translations = {
            "en": {
                "song": "Song",
                "and_prayer": "and Prayer",
                "opening_comments": "Opening Comments",
                "concluding_comments": "Concluding Comments",
                "opening_song_prayer": "Opening Song and Prayer",
                "closing_song_prayer": "Closing Song and Prayer",
                "service_talk": "Service Talk",
                "co_talk": "Circuit Overseer Talk"
            },
            "it": {
                "song": "Cantico",
                "and_prayer": "e preghiera",
                "opening_comments": "Commenti introduttivi",
                "concluding_comments": "Commenti conclusivi",
                "opening_song_prayer": "Cantico iniziale e preghiera",
                "closing_song_prayer": "Cantico finale e preghiera",
                "service_talk": "Discorso di servizio",
                "co_talk": "Discorso del sorvegliante di circoscrizione"
            },
            "fr": {
                "song": "Cantique",
                "and_prayer": "et prière",
                "opening_comments": "Paroles d'introduction",
                "concluding_comments": "Commentaires de conclusion",
                "opening_song_prayer": "Cantique d'ouverture et prière",
                "closing_song_prayer": "Cantique de clôture et prière",
                "service_talk": "Discours de service",
                "co_talk": "Discours du surveillant de circonscription"
            },
            "es": {
                "song": "Canción",
                "and_prayer": "y oración",
                "opening_comments": "Palabras de introducción",
                "concluding_comments": "Comentarios finales",
                "opening_song_prayer": "Canción inicial y oración",
                "closing_song_prayer": "Canción final y oración",
                "service_talk": "Discurso de servicio",
                "co_talk": "Discurso del superintendente de circuito"
            },
            "de": {
                "song": "Lied",
                "and_prayer": "und Gebet",
                "opening_comments": "Einleitende Worte",
                "concluding_comments": "Schlussworte",
                "opening_song_prayer": "Eingangslied und Gebet",
                "closing_song_prayer": "Schlusslied und Gebet",
                "service_talk": "Dienstgespräch",
                "co_talk": "Ansprache des Kreisaufsehers"
            },
            "pt": {
                "song": "Cântico",
                "and_prayer": "e oração",
                "opening_comments": "Comentários introdutórios",
                "concluding_comments": "Comentários finais",
                "opening_song_prayer": "Cântico inicial e oração",
                "closing_song_prayer": "Cântico final e oração",
                "service_talk": "Discurso de serviço",
                "co_talk": "Discurso do superintendente de circuito"
            },
            "ja": {
                "song": "歌",
                "and_prayer": "と祈り",
                "opening_comments": "開会の言葉",
                "concluding_comments": "結びの言葉",
                "opening_song_prayer": "開会の歌と祈り",
                "closing_song_prayer": "閉会の歌と祈り",
                "service_talk": "奉仕の話",
                "co_talk": "巡回監督の話"
            },
            "ko": {
                "song": "노래",
                "and_prayer": "및 기도",
                "opening_comments": "개회사",
                "concluding_comments": "폐회사",
                "opening_song_prayer": "개회 노래 및 기도",
                "closing_song_prayer": "폐회 노래 및 기도",
                "service_talk": "봉사 연설",
                "co_talk": "순회 감독자 연설"
            },
            "zh": {
                "song": "歌曲",
                "and_prayer": "和祈祷",
                "opening_comments": "开场白",
                "concluding_comments": "结束语",
                "opening_song_prayer": "开场歌曲和祈祷",
                "closing_song_prayer": "结束歌曲和祈祷",
                "service_talk": "服务讲话",
                "co_talk": "巡回监督讲话"
            }
            # Add more languages as needed
        }
        return translations.get(language, translations["en"])  # Fallback to English
    
    def load_meetings(self):
        """Load the most recent meetings"""
        meeting_source_mode = self.settings_manager.settings.meeting_source.mode
        
        # Check if we need to update meetings from web
        if (meeting_source_mode == MeetingSourceMode.WEB_SCRAPING and 
            self.settings_manager.settings.meeting_source.auto_update_meetings):
            self.update_meetings_from_web()
        else:
            # Load from local files or templates based on mode
            self._load_local_meetings()
        
        # Process weekend meeting songs if present
        if MeetingType.WEEKEND in self.current_meetings:
            weekend_meeting = self.current_meetings[MeetingType.WEEKEND]
            self.process_weekend_meeting_songs(weekend_meeting)
            
            # Save processed meeting
            self.save_meeting(weekend_meeting)
    
    def update_meetings_from_web(self):
        """Update meetings from the web"""
        try:
            # Update scraper language
            self.scraper.language = self.settings_manager.settings.language

            # Fetch meetings
            meetings = self.scraper.update_meetings()
            
            # Localize meeting parts
            for meeting_type, meeting in meetings.items():
                meetings[meeting_type] = self._localize_meeting_parts(meeting)

            # Handle weekend songs manual entry if enabled
            if self.settings_manager.settings.meeting_source.weekend_songs_manual:
                if MeetingType.WEEKEND in meetings:
                    weekend_meeting = meetings[MeetingType.WEEKEND]
                    self.process_weekend_meeting_songs(weekend_meeting)

            # Save scraped meetings as templates if option enabled
            if self.settings_manager.settings.meeting_source.save_scraped_as_template:
                self._save_meetings_as_templates(meetings)

            # Update current meetings
            self.current_meetings = meetings

            # Save fetched meetings
            for meeting_type, meeting in meetings.items():
                self.save_meeting(meeting)

            # Emit signal
            self.meetings_loaded.emit(self.current_meetings)

        except Exception as e:
            error_message = f"Failed to update meetings: {str(e)}"
            print(error_message)
            self.error_occurred.emit(error_message)

            # If update fails, try loading from local files
            self._load_local_meetings()
        return self.current_meetings
    
    def process_weekend_meeting_songs(self, meeting: Meeting):
        """
        Process weekend meeting songs using data already extracted by scraper
        - Simply checks if song numbers are present in the scraped data
        - Returns True if songs need manual entry (no numbers detected)
        """
        if meeting.meeting_type != MeetingType.WEEKEND:
            return False
        
        needs_manual_update = False
        
        # Check if any song parts are missing numbers
        # The scraper already positioned and localized everything correctly
        for section in meeting.sections:
            for part in section.parts:
                if self._is_song_part(part.title):
                    if not self._has_song_number_simple(part.title):
                        needs_manual_update = True
                        break
            if needs_manual_update:
                break
        
        return needs_manual_update
    
    def _is_song_part(self, title: str) -> bool:
        """Check if a part is a song part (language-agnostic)"""
        # The scraper already uses localized terms, so we check for them
        song_indicators = [
            "song", "cantico", "cantique", "canción", "lied",
            "prayer", "preghiera", "prière", "oración", "gebet"
        ]
        
        title_lower = title.lower()
        return any(indicator in title_lower for indicator in song_indicators)
    
    def _has_song_number_simple(self, title: str) -> bool:
        """Simple check for song numbers in title"""
        # Look for any number in the title - much simpler than before
        return bool(re.search(r'\b\d{1,3}\b', title))
    
    def _show_weekend_song_editor(self, meeting: Meeting):
        """Show the weekend song editor dialog"""
        
        # Get parent window if any
        parent = QApplication.activeWindow()
        
        dialog = WeekendSongEditorDialog(meeting, parent)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            # Save the updated meeting
            self.save_meeting(meeting)
            
            # If this is the current meeting, emit update signal
            if meeting is self.current_meeting:
                self.meeting_updated.emit(meeting)
    
    def _clear_weekend_songs(self, meeting: Meeting):
        """
        Clear song numbers from weekend meeting for manual entry
        Uses the localized titles already provided by scraper
        """
        if meeting.meeting_type != MeetingType.WEEKEND:
            return
        
        # Check if all songs already have numbers
        all_songs_have_numbers = True
        
        for section in meeting.sections:
            for part in section.parts:
                if self._is_song_part(part.title):
                    if not self._has_song_number_simple(part.title):
                        all_songs_have_numbers = False
                        break
            if not all_songs_have_numbers:
                break
        
        # If all songs already have numbers, keep them
        if all_songs_have_numbers:
            return
        
        # Clear song numbers while preserving the localized structure
        for section in meeting.sections:
            for part in section.parts:
                if self._is_song_part(part.title):
                    # Remove any numbers from the title, keep the localized text
                    part.title = re.sub(r'\b\d{1,3}\b', '', part.title).strip()
                    # Clean up any extra spaces
                    part.title = re.sub(r'\s+', ' ', part.title)
                    # Fix any formatting issues (like "Song  and Prayer" -> "Song and Prayer")
                    part.title = part.title.replace('  ', ' ')
    
    def _save_meetings_as_templates(self, meetings: Dict[MeetingType, Meeting]):
        """Save fetched meetings as templates for future use"""
        for meeting_type, meeting in meetings.items():
            # Convert to template format
            template_data = {
                'title': meeting.title,
                'language': meeting.language,
                'sections': []
            }
            
            for section in meeting.sections:
                section_data = {
                    'title': section.title,
                    'parts': []
                }
                
                for part in section.parts:
                    part_data = {
                        'title': part.title,
                        'duration_minutes': part.duration_minutes,
                        'presenter': part.presenter,
                        'notes': part.notes
                    }
                    section_data['parts'].append(part_data)
                
                template_data['sections'].append(section_data)
            
            # Save as template
            if meeting_type == MeetingType.MIDWEEK:
                self.template_manager.save_template(TemplateType.MIDWEEK, template_data)
            elif meeting_type == MeetingType.WEEKEND:
                self.template_manager.save_template(TemplateType.WEEKEND, template_data)
    
    def _load_local_meetings(self):
        """Load the most recent meetings from local files"""
        meetings = {}
        
        # Check if we should use templates instead of saved meetings
        meeting_source_mode = self.settings_manager.settings.meeting_source.mode
        
        if meeting_source_mode == MeetingSourceMode.TEMPLATE_BASED:
            # Create meetings from templates
            meetings = self._create_meetings_from_templates()
        else:
            try:
                # Get all meeting files
                meeting_files = [f for f in os.listdir(self.meetings_dir)
                               if f.endswith('.json')]

                # Group by meeting type
                midweek_files = [f for f in meeting_files if 'midweek' in f.lower()]
                weekend_files = [f for f in meeting_files if 'weekend' in f.lower()]

                # Sort by date (assuming filename contains date)
                midweek_files.sort(reverse=True)
                weekend_files.sort(reverse=True)

                # Load most recent of each type, preferring scraped over manual
                meetings[MeetingType.MIDWEEK] = self._load_best_meeting(midweek_files)
                meetings[MeetingType.WEEKEND] = self._load_best_meeting(weekend_files)

                # Remove None entries
                meetings = {k: v for k, v in meetings.items() if v is not None}
            
            except Exception as e:
                error_message = f"Failed to load meetings: {str(e)}"
                print(error_message)
                self.error_occurred.emit(error_message)
                
                # Fall back to templates if local loading fails
                if not meetings:
                    meetings = self._create_meetings_from_templates()
        
        # Localize meeting parts
        for meeting_type, meeting in meetings.items():
            meetings[meeting_type] = self._localize_meeting_parts(meeting)
        
        self.current_meetings = meetings
        self.meetings_loaded.emit(meetings)
    
    def _create_meetings_from_templates(self) -> Dict[MeetingType, Meeting]:
        """Create meetings from templates for the current week"""
        meetings = {}
        
        # Get current date/time
        now = datetime.now()
        
        # Create midweek meeting
        midweek_day = self.settings_manager.settings.midweek_meeting.day.value
        midweek_time = self.settings_manager.settings.midweek_meeting.time
        
        # Calculate the date for the next midweek meeting
        days_until_midweek = (midweek_day - now.weekday()) % 7
        if days_until_midweek == 0 and now.time() > midweek_time:
            days_until_midweek = 7  # Move to next week if today's meeting passed
        
        midweek_date = now.replace(
            hour=0, minute=0, second=0, microsecond=0
        ) + datetime.timedelta(days=days_until_midweek)
        
        # Create midweek meeting from template
        midweek_meeting = self.template_manager.create_meeting_from_template(
            TemplateType.MIDWEEK,
            midweek_date,
            midweek_time
        )
        
        # Localize midweek meeting parts
        midweek_meeting = self._localize_meeting_parts(midweek_meeting)
        
        meetings[MeetingType.MIDWEEK] = midweek_meeting
        
        # Create weekend meeting
        weekend_day = self.settings_manager.settings.weekend_meeting.day.value
        weekend_time = self.settings_manager.settings.weekend_meeting.time
        
        # Calculate the date for the next weekend meeting
        days_until_weekend = (weekend_day - now.weekday()) % 7
        if days_until_weekend == 0 and now.time() > weekend_time:
            days_until_weekend = 7  # Move to next week if today's meeting passed
        
        weekend_date = now.replace(
            hour=0, minute=0, second=0, microsecond=0
        ) + datetime.timedelta(days=days_until_weekend)
        
        # Create weekend meeting from template
        weekend_meeting = self.template_manager.create_meeting_from_template(
            TemplateType.WEEKEND,
            weekend_date,
            weekend_time
        )
        
        weekend_meeting = self._localize_meeting_parts(weekend_meeting)
        meetings[MeetingType.WEEKEND] = weekend_meeting
        
        return meetings
    
    def _load_meeting_file(self, file_path: str) -> Optional[Meeting]:
        """Load a meeting from a file"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                meeting_data = json.load(f)
                
                meeting = Meeting.from_dict(meeting_data)
                
                # Localize meeting parts
                meeting = self._localize_meeting_parts(meeting)

            return meeting
        except Exception as e:
            print(f"Error loading meeting file {file_path}: {e}")
            return None
    
    def _load_best_meeting(self, files: List[str]) -> Optional[Meeting]:
        """Load the best meeting from a list of files, preferring scraped over manual.

        Files should already be sorted by date (most recent first).
        Scraped meetings are preferred because manual (user-created) meetings
        may have test/placeholder data that shouldn't override real meeting content.
        """
        if not files:
            return None

        # Try to find the most recent scraped meeting first
        best_scraped = None
        best_manual = None

        for filename in files:
            meeting = self._load_meeting_file(
                os.path.join(self.meetings_dir, filename)
            )
            if not meeting:
                continue

            if meeting.source == MeetingSource.SCRAPED and best_scraped is None:
                best_scraped = meeting
                break  # Most recent scraped meeting found, no need to continue
            elif meeting.source == MeetingSource.MANUAL and best_manual is None:
                best_manual = meeting
                # Don't break — keep looking for a scraped one

        return best_scraped or best_manual

    def save_meeting(self, meeting: Meeting):
        """Save a meeting to a file"""
        # Create filename with date, meeting type, and language
        date_str = meeting.date.strftime("%Y-%m-%d")
        filename = f"{meeting.meeting_type.value}_{date_str}_{meeting.language}.json"
        file_path = os.path.join(self.meetings_dir, filename)
        
        # Save meeting data
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(meeting.to_dict(), f, indent=2)
        
        # Add to recent meetings list if not already there
        if file_path not in self.settings_manager.settings.recent_meetings:
            self.settings_manager.settings.recent_meetings.append(file_path)
            
            # Limit to last 10 meetings
            if len(self.settings_manager.settings.recent_meetings) > 10:
                self.settings_manager.settings.recent_meetings.pop(0)
            
            self.settings_manager.save_settings()
    
    def set_current_meeting(self, meeting: Meeting):
        """Set the currently active meeting"""
        
        meeting = self._localize_meeting_parts(meeting)
        self.current_meeting = meeting
        self.meeting_updated.emit(meeting)
        
    def get_meeting(self, meeting_type: MeetingType) -> Optional[Meeting]:
        """Get a meeting by type"""
        return self.current_meetings.get(meeting_type)
    
    def create_custom_meeting(self, title: str, date: datetime) -> Meeting:
        """Create a new custom meeting"""
        # Create blank meeting
        meeting = Meeting(
            meeting_type=MeetingType.CUSTOM,
            title=title,
            date=date,
            start_time=datetime.now().time(),
            sections=[]
        )
        
        return meeting
    
    def add_section_to_meeting(self, meeting: Meeting, section_title: str) -> Meeting:
        """Add a new section to a meeting"""
        # Create new section
        section = MeetingSection(
            title=section_title,
            parts=[]
        )
        
        # Add to meeting
        meeting.sections.append(section)
        
        # If this is the current meeting, emit update
        if meeting is self.current_meeting:
            self.meeting_updated.emit(meeting)
        
        return meeting
    
    def add_part_to_section(self, meeting: Meeting, section_index: int, 
                           part_title: str, duration_minutes: int, 
                           presenter: str = "") -> Meeting:
        """Add a new part to a section in a meeting"""
        # Create new part
        part = MeetingPart(
            title=part_title,
            duration_minutes=duration_minutes,
            presenter=presenter
        )
        
        # Add to section
        if 0 <= section_index < len(meeting.sections):
            meeting.sections[section_index].parts.append(part)
            
            # Emit part updated signal
            part_index = len(meeting.sections[section_index].parts) - 1
            self.part_updated.emit(part, section_index, part_index)
        
        # If this is the current meeting, emit update
        if meeting is self.current_meeting:
            self.meeting_updated.emit(meeting)
        
        return meeting
    
    def update_part(self, meeting: Meeting, section_index: int, part_index: int, 
                   updated_part: MeetingPart) -> Meeting:
        """Update a part in a meeting section"""
        # Check bounds
        if (0 <= section_index < len(meeting.sections) and 
            0 <= part_index < len(meeting.sections[section_index].parts)):
            
            # Update the part
            meeting.sections[section_index].parts[part_index] = updated_part
            
            # Emit part updated signal
            self.part_updated.emit(updated_part, section_index, part_index)
            
            # If this is the current meeting, save and emit update
            if meeting is self.current_meeting:
                self.save_meeting(meeting)
                self.meeting_updated.emit(meeting)
        
        return meeting
    
    def remove_part(self, meeting: Meeting, section_index: int, part_index: int) -> Meeting:
        """Remove a part from a meeting section"""
        # Check bounds
        if (0 <= section_index < len(meeting.sections) and 
            0 <= part_index < len(meeting.sections[section_index].parts)):
            
            # Remove the part
            removed_part = meeting.sections[section_index].parts.pop(part_index)
            
            # If this is the current meeting, save and emit update
            if meeting is self.current_meeting:
                self.save_meeting(meeting)
                self.meeting_updated.emit(meeting)
        
        return meeting
    
    def get_part_indices(self, meeting: Meeting, global_part_index: int) -> Tuple[int, int]:
        """Convert global part index to section and part indices"""
        current_index = 0
        
        for section_index, section in enumerate(meeting.sections):
            for part_index, part in enumerate(section.parts):
                if current_index == global_part_index:
                    return section_index, part_index
                current_index += 1
        
        # If not found, return invalid indices
        return -1, -1
    
    def edit_part_at_global_index(self, meeting: Meeting, global_part_index: int, 
                                 updated_part: MeetingPart) -> bool:
        """Edit a part identified by its global index across all sections"""
        section_index, part_index = self.get_part_indices(meeting, global_part_index)
        
        if section_index >= 0 and part_index >= 0:
            meeting.sections[section_index].parts[part_index] = updated_part
            
            # Emit part updated signal
            self.part_updated.emit(updated_part, section_index, part_index)
            
            # If this is the current meeting, save and emit update
            if meeting is self.current_meeting:
                self.save_meeting(meeting)
                self.meeting_updated.emit(meeting)
                
            return True
            
        return False
    
    def show_meeting_editor(self, parent=None, meeting: Optional[Meeting] = None, on_meeting_updated=None):
        """Show the meeting editor dialog
        :param parent: Parent widget
        :param meeting: Meeting instance to edit
        :param on_meeting_updated: Optional callback to connect to meeting_updated signal
        """
        from src.views.meeting_editor_dialog import MeetingEditorDialog

        dialog = MeetingEditorDialog(parent, meeting, self.settings_manager)

        # Connect the signal from the dialog
        if on_meeting_updated:
            dialog.meeting_updated.connect(on_meeting_updated)
        else:
            dialog.meeting_updated.connect(self._handle_meeting_updated)

        # Show the dialog
        dialog.exec()
    
    def _handle_meeting_updated(self, meeting: Meeting):
        """Handle a meeting being updated from the editor"""
        # Save the meeting
        self.save_meeting(meeting)

        # Update current meetings dictionary
        self.current_meetings[meeting.meeting_type] = meeting

        # Set as current meeting
        self.set_current_meeting(meeting)

        # Emit signal to notify all components
        self.meetings_loaded.emit(self.current_meetings)

    def apply_co_visit_modifications(self, meeting: Meeting) -> Meeting:
        """Apply CO visit schedule modifications to a meeting"""
        import copy
        modified = copy.deepcopy(meeting)

        if meeting.meeting_type == MeetingType.MIDWEEK:
            return self._apply_midweek_co_visit(modified)
        elif meeting.meeting_type == MeetingType.WEEKEND:
            return self._apply_weekend_co_visit(modified)
        return modified

    def _apply_midweek_co_visit(self, meeting: Meeting) -> Meeting:
        """
        Apply midweek CO visit modifications using indices relative to END:
        - Section 2 (Living as Christians): [..., CBS(-3), Review(-2), Closing(-1)]
        - Replace CBS with Service Talk (30 min); Review stays before the closing song
        """
        translations = self._get_translations(meeting.language)

        # Living as Christians is section index 2
        if len(meeting.sections) > 2:
            section = meeting.sections[2]
            parts = section.parts

            # Use indices from the end (works regardless of how many parts there are)
            # Structure ends with: [..., CBS, Review/Concluding Comments, Closing Song]
            if len(parts) >= 3:
                # CBS e' la terza dalla fine.  I commenti conclusivi restano dopo
                # il discorso, subito prima del cantico finale (l'originale li
                # spostava prima del discorso).
                cbs_idx = len(parts) - 3
                parts[cbs_idx].title = translations.get('service_talk', 'Service Talk')
                parts[cbs_idx].duration_minutes = 30

        return meeting

    def _apply_weekend_co_visit(self, meeting: Meeting) -> Meeting:
        """
        Apply weekend CO visit modifications using section/part indices:
        - Section 1 (Watchtower Study): [Song(0), WT Study(1), Closing(2)]
        - Reduce WT Study (index 1) to 30 mins
        - Insert CO Talk (30 min) at index 2 (before closing song)
        """
        translations = self._get_translations(meeting.language)

        # Watchtower Study is section index 1
        if len(meeting.sections) > 1:
            section = meeting.sections[1]
            parts = section.parts

            # Expected structure: [Song(0), WT Study(1), Closing(2)]
            # We need at least 3 parts
            if len(parts) >= 3:
                # Reduce Watchtower Study (index 1) to 30 minutes
                parts[1].duration_minutes = 30

                # Insert CO Talk at index 2 (before closing song)
                co_talk = MeetingPart(
                    title=translations.get('co_talk', 'Circuit Overseer Talk'),
                    duration_minutes=30,
                    presenter=""
                )
                parts.insert(2, co_talk)
                # Now structure is: [Song(0), WT Study(1), CO Talk(2), Closing(3)]

        return meeting