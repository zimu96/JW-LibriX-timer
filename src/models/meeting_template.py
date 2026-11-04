"""
Meeting template models for the OnTime Meeting Timer application.

This module provides classes for managing meeting templates,
which can be used to quickly create meetings with standard structures.
"""
import os
import json
from enum import Enum
from typing import List, Dict, Optional
from pathlib import Path
from datetime import datetime, time

from src.models.meeting import Meeting, MeetingSection, MeetingPart, MeetingType
from src.config import APP_DIR, USER_DATA_DIR


class TemplateType(Enum):
    """Types of meeting templates"""
    MIDWEEK = "midweek"
    WEEKEND = "weekend"
    CUSTOM = "custom"


class MeetingTemplate:
    """Class for managing meeting templates"""
    
    # Directory for storing templates
    TEMPLATES_DIR = USER_DATA_DIR / "templates"
    
    # Default templates included with the application
    DEFAULT_TEMPLATES_DIR = APP_DIR / "resources" / "templates"
    
    def __init__(self):
        """Initialize the meeting template manager"""
        # Ensure templates directory exists
        self.TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
        
        # List of template types and their file names
        self.template_files = {
            TemplateType.MIDWEEK: "midweek_template.json",
            TemplateType.WEEKEND: "weekend_template.json",
            TemplateType.CUSTOM: "custom_template.json"
        }
    
    def get_template(self, template_type: TemplateType) -> Dict:
        """
        Get a meeting template by type
        
        Args:
            template_type: Type of template to get
            
        Returns:
            Dictionary containing the template structure
        """
        # Try to load user-customized template first
        file_path = self.TEMPLATES_DIR / self.template_files[template_type]
        
        if file_path.exists():
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                print(f"Error loading user template: {e}")
        
        # Fall back to default template
        default_path = self.DEFAULT_TEMPLATES_DIR / self.template_files[template_type]
        
        if default_path.exists():
            try:
                with open(default_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError) as e:
                print(f"Error loading default template: {e}")
        
        # If no template found, return a minimal structure
        return self._create_minimal_template(template_type)
    
    def save_template(self, template_type: TemplateType, template_data: Dict) -> bool:
        """
        Save a meeting template
        
        Args:
            template_type: Type of template to save
            template_data: Template data dictionary
            
        Returns:
            True if successful, False otherwise
        """
        file_path = self.TEMPLATES_DIR / self.template_files[template_type]
        
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(template_data, f, indent=2)
            return True
        except IOError as e:
            print(f"Error saving template: {e}")
            return False
    
    def create_meeting_from_template(self, 
                                    template_type: TemplateType, 
                                    meeting_date: datetime,
                                    meeting_time: time) -> Meeting:
        """
        Create a new meeting from a template
        
        Args:
            template_type: Type of template to use
            meeting_date: Date for the meeting
            meeting_time: Time for the meeting
            
        Returns:
            A new Meeting object
        """
        template = self.get_template(template_type)
        
        # Convert template type to meeting type
        if template_type == TemplateType.MIDWEEK:
            meeting_type = MeetingType.MIDWEEK
        elif template_type == TemplateType.WEEKEND:
            meeting_type = MeetingType.WEEKEND
        else:
            meeting_type = MeetingType.CUSTOM
        
        # Create sections with parts
        sections = []
        for section_template in template.get('sections', []):
            parts = []
            
            for part_template in section_template.get('parts', []):
                part = MeetingPart(
                    title=part_template.get('title', ''),
                    duration_minutes=part_template.get('duration_minutes', 0),
                    presenter=part_template.get('presenter', ''),
                    notes=part_template.get('notes', '')
                )
                parts.append(part)
            
            section = MeetingSection(
                title=section_template.get('title', ''),
                parts=parts
            )
            sections.append(section)
        
        # Create meeting with the template
        meeting = Meeting(
            meeting_type=meeting_type,
            title=template.get('title', f"{meeting_type.value.capitalize()} Meeting"),
            date=meeting_date,
            start_time=meeting_time,
            sections=sections,
            language=template.get('language', 'en')
        )
        
        return meeting
    
    def _create_minimal_template(self, template_type: TemplateType) -> Dict:
        """
        Create a minimal template if none exists
        
        Args:
            template_type: Type of template to create
            
        Returns:
            Dictionary with a minimal template structure
        """
        if template_type == TemplateType.MIDWEEK:
            return {
                "title": "Midweek Meeting",
                "language": "en",
                "sections": [
                    {
                        "title": "TREASURES FROM GOD'S WORD",
                        "parts": [
                            {"title": "Opening Song and Prayer", "duration_minutes": 5},
                            {"title": "Bible Reading", "duration_minutes": 4}
                        ]
                    },
                    {
                        "title": "APPLY YOURSELF TO THE FIELD MINISTRY",
                        "parts": [
                            {"title": "Initial Call Video", "duration_minutes": 5}
                        ]
                    },
                    {
                        "title": "LIVING AS CHRISTIANS",
                        "parts": [
                            {"title": "Congregation Bible Study", "duration_minutes": 30},
                            {"title": "Concluding Comments and Prayer", "duration_minutes": 5}
                        ]
                    }
                ]
            }
        elif template_type == TemplateType.WEEKEND:
            return {
                "title": "Weekend Meeting",
                "language": "en",
                "sections": [
                    {
                        "title": "Public Talk",
                        "parts": [
                            {"title": "Opening Song and Prayer", "duration_minutes": 5},
                            {"title": "Public Talk", "duration_minutes": 30}
                        ]
                    },
                    {
                        "title": "Watchtower Study",
                        "parts": [
                            {"title": "Song", "duration_minutes": 5},
                            {"title": "Watchtower Study", "duration_minutes": 60},
                            {"title": "Concluding Song and Prayer", "duration_minutes": 5}
                        ]
                    }
                ]
            }
        else:  # CUSTOM
            return {
                "title": "Custom Meeting",
                "language": "en",
                "sections": [
                    {
                        "title": "Section 1",
                        "parts": [
                            {"title": "Part 1", "duration_minutes": 15}
                        ]
                    }
                ]
            }


def create_default_templates():
    """Create default templates in the resources directory if they don't exist"""
    # Create the directory if it doesn't exist
    template_dir = Path(APP_DIR) / "resources" / "templates"
    template_dir.mkdir(parents=True, exist_ok=True)
    
    # Define the default templates
    midweek_template = {
        "title": "Midweek Meeting",
        "language": "en",
        "sections": [
            {
                "title": "TREASURES FROM GOD'S WORD",
                "parts": [
                    {"title": "Opening Song and Prayer", "duration_minutes": 4, "presenter": ""},
                    {"title": "Treasures from God's Word", "duration_minutes": 10, "presenter": ""},
                    {"title": "Digging for Spiritual Gems", "duration_minutes": 10, "presenter": ""},
                    {"title": "Bible Reading", "duration_minutes": 4, "presenter": ""}
                ]
            },
            {
                "title": "APPLY YOURSELF TO THE FIELD MINISTRY",
                "parts": [
                    {"title": "First Return Visit", "duration_minutes": 5, "presenter": ""},
                    {"title": "Second Return Visit", "duration_minutes": 5, "presenter": ""},
                    {"title": "Bible Study", "duration_minutes": 5, "presenter": ""}
                ]
            },
            {
                "title": "LIVING AS CHRISTIANS",
                "parts": [
                    {"title": "Song", "duration_minutes": 2, "presenter": ""},
                    {"title": "Local Needs", "duration_minutes": 15, "presenter": ""},
                    {"title": "Congregation Bible Study", "duration_minutes": 30, "presenter": ""},
                    {"title": "Review and Preview", "duration_minutes": 3, "presenter": ""},
                    {"title": "Concluding Song and Prayer", "duration_minutes": 4, "presenter": ""}
                ]
            }
        ]
    }
    
    weekend_template = {
        "title": "Weekend Meeting",
        "language": "en",
        "sections": [
            {
                "title": "Public Talk",
                "parts": [
                    {"title": "Opening Song and Prayer", "duration_minutes": 5, "presenter": ""},
                    {"title": "Public Talk", "duration_minutes": 30, "presenter": ""}
                ]
            },
            {
                "title": "Watchtower Study",
                "parts": [
                    {"title": "Song", "duration_minutes": 5, "presenter": ""},
                    {"title": "Watchtower Study", "duration_minutes": 60, "presenter": ""},
                    {"title": "Concluding Song and Prayer", "duration_minutes": 5, "presenter": ""}
                ]
            }
        ]
    }
    
    custom_template = {
        "title": "Custom Meeting",
        "language": "en",
        "sections": [
            {
                "title": "Main Section",
                "parts": [
                    {"title": "Opening", "duration_minutes": 5, "presenter": ""},
                    {"title": "Main Part", "duration_minutes": 30, "presenter": ""},
                    {"title": "Closing", "duration_minutes": 5, "presenter": ""}
                ]
            }
        ]
    }
    
    # Save the templates
    templates = {
        "midweek_template.json": midweek_template,
        "weekend_template.json": weekend_template,
        "custom_template.json": custom_template
    }
    
    for filename, template in templates.items():
        file_path = template_dir / filename
        if not file_path.exists():
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(template, f, indent=2)
                print(f"Created default template: {filename}")
            except IOError as e:
                print(f"Error creating default template {filename}: {e}")