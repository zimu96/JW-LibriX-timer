"""
Meeting data models for the OnTime Meeting Timer application.
"""
from dataclasses import dataclass
from datetime import datetime, time
from typing import List, Optional
from enum import Enum

class MeetingType(Enum):
    """Types of meetings supported by the application"""
    MIDWEEK = "midweek"
    WEEKEND = "weekend"
    CUSTOM = "custom"

class MeetingSource(Enum):
    """How the meeting data was created"""
    SCRAPED = "scraped"    # Auto-fetched from web (EPUB scraper)
    MANUAL = "manual"      # User-created via the meeting editor

@dataclass
class MeetingPart:
    """Represents a single part in a meeting"""
    title: str
    duration_minutes: int
    presenter: str = ""
    notes: str = ""
    is_completed: bool = False
    original_duration_minutes: Optional[int] = None  # Pre-adjustment duration (None = not adjusted)
    
    @property
    def duration_seconds(self) -> int:
        """Convert minutes to seconds"""
        return self.duration_minutes * 60
    
    def to_dict(self) -> dict:
        """Convert to dictionary for storage"""
        d = {
            'title': self.title,
            'duration_minutes': self.duration_minutes,
            'presenter': self.presenter,
            'notes': self.notes,
            'is_completed': self.is_completed
        }
        if self.original_duration_minutes is not None:
            d['original_duration_minutes'] = self.original_duration_minutes
        return d
    
    @classmethod
    def from_dict(cls, data: dict) -> 'MeetingPart':
        """Create from dictionary"""
        return cls(
            title=data['title'],
            duration_minutes=data['duration_minutes'],
            presenter=data.get('presenter', ''),
            notes=data.get('notes', ''),
            is_completed=data.get('is_completed', False),
            original_duration_minutes=data.get('original_duration_minutes')
        )

@dataclass
class MeetingSection:
    """Represents a section of a meeting containing multiple parts"""
    title: str
    parts: List[MeetingPart]
    
    def to_dict(self) -> dict:
        """Convert to dictionary for storage"""
        return {
            'title': self.title,
            'parts': [part.to_dict() for part in self.parts]
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'MeetingSection':
        """Create from dictionary"""
        return cls(
            title=data['title'],
            parts=[MeetingPart.from_dict(part) for part in data['parts']]
        )
    
    @property
    def total_duration_minutes(self) -> int:
        """Calculate total duration of all parts in this section"""
        return sum(part.duration_minutes for part in self.parts)

@dataclass
class Meeting:
    """Represents a complete meeting with multiple sections"""
    meeting_type: MeetingType
    title: str
    date: datetime
    start_time: time
    sections: List[MeetingSection]
    language: str = "en"
    target_duration_minutes: Optional[int] = None  # Custom target for specific meeting (e.g., custom meetings)
    source: MeetingSource = MeetingSource.SCRAPED  # How the meeting was created

    def to_dict(self) -> dict:
        """Convert to dictionary for storage"""
        return {
            'meeting_type': self.meeting_type.value,
            'title': self.title,
            'date': self.date.isoformat(),
            'start_time': self.start_time.isoformat(),
            'sections': [section.to_dict() for section in self.sections],
            'language': self.language,
            'target_duration_minutes': self.target_duration_minutes,
            'source': self.source.value
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'Meeting':
        """Create from dictionary with backwards compatibility"""
        # Determine source - default to "scraped" for older files without the field
        source_str = data.get('source', MeetingSource.SCRAPED.value)
        try:
            source = MeetingSource(source_str)
        except ValueError:
            source = MeetingSource.SCRAPED

        return cls(
            meeting_type=MeetingType(data['meeting_type']),
            title=data['title'],
            date=datetime.fromisoformat(data['date']),
            start_time=time.fromisoformat(data['start_time']),
            sections=[MeetingSection.from_dict(section) for section in data['sections']],
            language=data.get('language', 'en'),
            target_duration_minutes=data.get('target_duration_minutes'),  # None if not specified
            source=source
        )
    
    @property
    def total_duration_minutes(self) -> int:
        """Calculate total duration of the entire meeting"""
        return sum(section.total_duration_minutes for section in self.sections)
    
    def get_all_parts(self) -> List[MeetingPart]:
        """Get a flattened list of all parts across all sections"""
        all_parts = []
        for section in self.sections:
            all_parts.extend(section.parts)
        return all_parts