"""
Web scraper for fetching meeting data from wol.jw.org
"""
import re
import requests
from bs4 import BeautifulSoup, Tag
from datetime import datetime, timedelta
from typing import List, Dict, Tuple, Optional, Set
from dateutil.parser import parse as parse_date


import json
import hashlib
import time
from pathlib import Path

# Platformdirs support for cache directory
try:
    from platformdirs import user_cache_dir
except ImportError:
    def user_cache_dir(appname, appauthor=None):
        return str(Path.home() / ".meeting_timer_cache")

from src.models.meeting import Meeting, MeetingSection, MeetingPart, MeetingType

class MeetingScraper:
    """Scraper for fetching meeting data from wol.jw.org"""
    
    BASE_URL = "https://wol.jw.org"

    # ---------- simple on‑disk cache ----------
    CACHE_DIR = Path(user_cache_dir("MeetingTimer"))
    LINKS_TTL = 60 * 60 * 24 * 7  # 7 days
    PAGE_TTL  = 60 * 60 * 24 * 7  # 7 days
    
    def __init__(self, language: str = "en"):
        self.language = language
        self.session = requests.Session()
        self.CACHE_DIR.mkdir(parents=True, exist_ok=True)
        
        # Set language in URL
        lang_code = "r1/lp-e" if language == "en" else language
        self.meetings_url = f"{self.BASE_URL}/{language}/wol/meetings/{lang_code}"
    
    def get_current_meeting_urls(self) -> Dict[MeetingType, str]:
        """Get URLs for the current week's meetings"""
        from datetime import date
        week_id = f"{date.today().isocalendar().year}_W{date.today().isocalendar().week}"
        cache_file = self.CACHE_DIR / f"{self.language}_{week_id}_meeting_links.json"
        cached = self._cache_load(cache_file, self.LINKS_TTL)
        if cached:
            raw_links = json.loads(cached)
            # convert string keys back to MeetingType
            return {MeetingType(k): v for k, v in raw_links.items()}

        response = self.session.get(self.meetings_url)
        if response.status_code != 200:
            raise Exception(f"Failed to fetch meetings page: {response.status_code}")
        
        soup = BeautifulSoup(response.text, "html.parser")
        meeting_links = {}
        
        # Find all links on the page
        all_links = soup.find_all('a', href=True)
        
        for link in all_links:
            href = link.get('href')
            link_text = link.get_text().strip().lower()
            
            # Skip links without href or text
            if not href or not link_text:
                continue
            
            # Make the URL absolute if it's not already
            if not href.startswith('http'):
                href = f"{self.BASE_URL}{href}"
            
            # Look for specific indicators in the text or href
            is_midweek = any(term in link_text for term in ['life', 'ministry', 'treasures', 'apply yourself'])
            is_weekend = any(term in link_text for term in ['watchtower', 'study article', 'public talk'])
            
            # Additional check for href patterns
            if '/lf/' in href or '/mwb/' in href:
                is_midweek = True
                
            # If this link matches a meeting type and we haven't found one yet
            if is_midweek and MeetingType.MIDWEEK not in meeting_links:
                meeting_links[MeetingType.MIDWEEK] = href
                
            #========   WEEKEND MEETING   ========
            
        weekend_found = False
        
        # Method 1: Look in groupTOC class elements (based on the screenshot)
        toc_elements = soup.find_all(class_='groupTOC')
        for toc in toc_elements:
            links = toc.find_all('a', href=True)
            for link in links:
                href = link.get('href')
                strong_tags = link.find_all('strong')
                
                # Check if this link has a strong tag with substantial text
                if strong_tags and len(strong_tags[0].get_text().strip()) > 10:
                    if not href.startswith('http'):
                        href = f"{self.BASE_URL}{href}"
                    
                    meeting_links[MeetingType.WEEKEND] = href
                    weekend_found = True
                    break
            if weekend_found:
                break
        
        # Method 2: Look for strong tags containing Watchtower titles anywhere
        if not weekend_found:
            for strong in soup.find_all('strong'):
                text = strong.get_text().strip()
                if len(text) > 15 and any(x in text.lower() for x in ["jehovah", "forgiveness", "—", "means"]):
                    # Found a likely Watchtower title, check if it's in a link
                    parent_link = strong.find_parent('a')
                    if parent_link and parent_link.has_attr('href'):
                        href = parent_link.get('href')
                        if not href.startswith('http'):
                            href = f"{self.BASE_URL}{href}"
                        
                        meeting_links[MeetingType.WEEKEND] = href
                        weekend_found = True
                        break
            
        # Method 3: Fall back to original method for weekend if still not found
        if not weekend_found:
            for link in all_links:
                href = link.get('href')
                link_text = link.get_text().strip().lower()
                
                if not href or not link_text:
                    continue
                    
                if not href.startswith('http'):
                    href = f"{self.BASE_URL}{href}"
                
                is_weekend = any(term in link_text for term in ['watchtower', 'study article', 'public talk'])
                if '/w/' in href or '/wp/' in href or '/d/' in href:
                    is_weekend = True
                    
                if is_weekend and MeetingType.WEEKEND not in meeting_links:
                    meeting_links[MeetingType.WEEKEND] = href
        # save to cache
        try:
            json_links = {k.value: v for k, v in meeting_links.items()}
            self._cache_save(cache_file, json.dumps(json_links))
        except Exception:
            pass
        return meeting_links
    
    def scrape_meeting(self, url: str, meeting_type: MeetingType) -> Meeting:
        """Scrape meeting data from a specific URL"""
        # page‑cache key: md5(url)
        key = hashlib.md5(url.encode()).hexdigest() + ".html"
        page_path = self.CACHE_DIR / key
        html = self._cache_load(page_path, self.PAGE_TTL)
        if html is None:
            response = self.session.get(url)
            if response.status_code != 200:
                raise Exception(f"Failed to fetch meeting page: {response.status_code}")
            html = response.text
            self._cache_save(page_path, html)
        soup = BeautifulSoup(html, "html.parser")
        
        # Extract date information
        date_text = self._extract_date(soup)
        
        # Create title based on meeting type and date
        if meeting_type == MeetingType.MIDWEEK:
            title = f"Midweek Meeting: {date_text}"
        else:
            title = f"Weekend Meeting: {date_text}"
        
        # Parse date
        meeting_date = datetime.now()
        try:
            # Try to extract a date from the date text
            date_match = re.search(r'(\w+)\s+(\d+)(?:\s*-\s*\d+)?(?:,\s*(\d{4}))?', date_text)
            if date_match:
                month, day, year = date_match.groups()
                year = year or str(datetime.now().year)
                date_str = f"{month} {day}, {year}"
                meeting_date = parse_date(date_str)
        except (ValueError, TypeError):
            # If date parsing fails, use current date
            pass
        
        # Extract meeting sections and parts based on meeting type
        if meeting_type == MeetingType.MIDWEEK:
            sections = self._parse_midweek_meeting(soup)
        else:
            sections = self._parse_weekend_meeting(soup)
        
        # Use current time as default start time
        start_time = datetime.now().time()
        
        # Create and return Meeting object
        meeting = Meeting(
            meeting_type=meeting_type,
            title=title,
            date=meeting_date,
            start_time=start_time,
            sections=sections,
            language=self.language
        )
        
        return meeting

    # ---------- cache helpers ----------
    def _cache_load(self, path: Path, ttl: int) -> Optional[str]:
        if path.exists() and (time.time() - path.stat().st_mtime) < ttl:
            try:
                return path.read_text(encoding="utf‑8")
            except Exception:
                pass
        return None

    def _cache_save(self, path: Path, data: str) -> None:
        try:
            path.write_text(data, encoding="utf‑8")
        except Exception:
            pass
    
    def _extract_date(self, soup: BeautifulSoup) -> str:
        """Extract date information from the page"""
        # Try various selectors that might contain date information
        date_elements = [
            soup.select_one('.pageNumber'),  # Page number span
            soup.select_one('[id*="pageNum"]'),  # Element with pageNum in ID
            soup.select_one('h1'),  # Main heading
            soup.select_one('header h1'),  # Header heading
            soup.find(string=re.compile(r'\w+\s+\d+\s*-\s*\d+'))  # Text with date pattern
        ]
        
        for element in date_elements:
            if element and element.get_text().strip():
                text = element.get_text().strip()
                # Look for date patterns like "April 21-27"
                date_match = re.search(r'\w+\s+\d+\s*-\s*\d+', text)
                if date_match:
                    return date_match.group(0)
        
        # If no date found, return current month and week
        now = datetime.now()
        month = now.strftime("%B")
        day = now.day
        # Calculate the end of the week (day + 6, or end of month)
        end_day = min(day + 6, (now.replace(month=now.month+1, day=1) - timedelta(days=1)).day)
        return f"{month} {day}-{end_day}"
        
    def _find_duration_for_part(self, part_num: int, soup: BeautifulSoup) -> Optional[int]:
        """Find the duration for a part by searching for it based on HTML structure rather than content patterns"""
        # Look specifically for the part with this number
        for h3 in soup.find_all(['h3']):
            h3_text = h3.get_text().strip()
            part_match = re.match(r'(\d+)\.\s+(.*)', h3_text)
            
            if part_match and int(part_match.group(1)) == part_num:
                # Found the heading for this part, now look for duration in the next paragraph
                next_p = h3.find_next('p')
                if next_p:
                    p_text = next_p.get_text().strip()
                    duration = self._extract_duration(p_text)
                    if duration:
                        return duration
                
                # Also look for duration in the h3 itself
                duration = self._extract_duration(h3_text)
                if duration:
                    return duration
        
        # If we couldn't find the part in h3 elements, try looking for it in strong elements
        for strong in soup.find_all('strong'):
            strong_text = strong.get_text().strip()
            part_match = re.match(r'(\d+)\.\s+(.*)', strong_text)
            
            if part_match and int(part_match.group(1)) == part_num:
                # Found the part in a strong tag, check parent and surrounding elements
                parent = strong.parent
                
                # Check parent element for duration
                if parent:
                    parent_text = parent.get_text().strip()
                    duration = self._extract_duration(parent_text)
                    if duration:
                        return duration
                    
                    # Check next sibling of parent
                    next_elem = parent.find_next_sibling()
                    if next_elem:
                        next_text = next_elem.get_text().strip()
                        duration = self._extract_duration(next_text)
                        if duration:
                            return duration
        
        # If still not found, look for any element containing part number string (e.g., "1.")
        part_pattern = re.compile(rf'^{part_num}\.\s')
        
        for elem in soup.find_all(['p', 'span', 'strong', 'h3']):
            elem_text = elem.get_text().strip()
            
            if part_pattern.match(elem_text):
                # Found the part, check this element and the next for duration
                duration = self._extract_duration(elem_text)
                if duration:
                    return duration
                
                # Check next element
                next_elem = elem.find_next()
                if next_elem:
                    next_text = next_elem.get_text().strip()
                    duration = self._extract_duration(next_text)
                    if duration:
                        return duration
        
        # If part number is mentioned anywhere in any element
        for elem in soup.find_all():
            text = elem.get_text().strip()
            if f"{part_num}." in text:
                # Found a mention, check surrounding elements
                duration = self._extract_duration(text)
                if duration:
                    return duration
                
                # Check next element
                next_elem = elem.find_next()
                if next_elem:
                    next_text = next_elem.get_text().strip()
                    duration = self._extract_duration(next_text)
                    if duration:
                        return duration
        
        # Return None if we couldn't find a duration
        return None
    
    def _extract_duration(self, text: str) -> Optional[int]:
        """Extract duration in minutes from text"""
        # Enhanced pattern to catch more duration formats
        patterns = [
            r'\((\d+)\s*min\.?\)',                # (10 min) or (10 min.)
            r'(?<!\()(\d+)\s*min\.?(?!\))',       # 10 min or 10 min. not in parentheses
            r'(\d+)(?:\s*|-)\s*minute',           # 10 minute or 10-minute
            r'(\d+)\s*(?:min|m)(?:\.|,|\s|$)',    # 10 min. or 10m or 10 min
            r'\((\d+)\)'                          # (10) - as a last resort, if clearly in context
        ]
        
        for pattern in patterns:
            duration_match = re.search(pattern, text, re.IGNORECASE)
            if duration_match:
                return int(duration_match.group(1))
        
        return None
    
    def _extract_song_number(self, text: str) -> Optional[int]:
        """Extract song number from text"""
        # Match patterns like "Song 76" or "SONG 76"
        song_match = re.search(r'[Ss][Oo][Nn][Gg]\s+(\d+)', text)
        if song_match:
            return int(song_match.group(1))
        return None
    
    def _remove_duplicate_duration(self, title: str) -> str:
        """Remove duplicate duration formats from part titles"""
        # Match (X min) (X min) pattern
        duplicate_match = re.search(r'(\(\d+\s*min\.?\))\s+\(\d+\s*min\.?\)', title)
        if duplicate_match:
            # Keep only the first duration
            return title.replace(duplicate_match.group(0), duplicate_match.group(1))
        return title
    
    def _format_part_title(self, base_title: str, duration: Optional[int] = None) -> str:
        """Format part title with proper duration and without duplicates"""
        # Check if the duration is already in the title
        if "min" in base_title:
            # Ensure consistent format
            return self._remove_duplicate_duration(base_title)
        
        # Add duration to title only if provided
        if duration is not None:
            return f"{base_title} ({duration} min)"
        
        # Return original title if no duration provided
        return base_title
    
    def _parse_midweek_meeting(self, soup: BeautifulSoup) -> List[MeetingSection]:
        """Parse midweek meeting structure to match the desired output format"""
        # Create default sections 
        treasures_section = MeetingSection(title="TREASURES FROM GOD'S WORD", parts=[])
        ministry_section = MeetingSection(title="APPLY YOURSELF TO THE FIELD MINISTRY", parts=[])
        christians_section = MeetingSection(title="LIVING AS CHRISTIANS", parts=[])
        
        # Find all songs in the document
        songs = []
        for el in soup.find_all(['h3', 'p', 'strong', 'a', 'span']):
            el_text = el.get_text().strip()
            if ("Song" in el_text or "SONG" in el_text) and "Song and Prayer" not in el_text:
                song_num = self._extract_song_number(el_text)
                if song_num:
                    songs.append((song_num, el_text))
        
        # Use a set to track part numbers we've already processed to avoid duplicates
        processed_part_numbers = set()
        
        # First, look for section headers to confirm the structure
        section_headers = {
            "treasures": False,
            "ministry": False,
            "christians": False
        }
        
        for h3 in soup.find_all(['h3']):
            h3_text = h3.get_text().strip().upper()
            if "TREASURES FROM GOD'S WORD" in h3_text:
                section_headers["treasures"] = True
            elif "APPLY YOURSELF TO THE FIELD MINISTRY" in h3_text:
                section_headers["ministry"] = True
            elif "LIVING AS CHRISTIANS" in h3_text:
                section_headers["christians"] = True
        
        # Find all numbered parts (1. Title) in any tag
        numbered_parts = []
        
        # Look for parts in an ordered way - first in h3 tags with strong elements
        for h3 in soup.find_all('h3'):
            strong_tags = h3.find_all('strong')
            for strong in strong_tags:
                strong_text = strong.get_text().strip()
                part_match = re.match(r'(\d+)\.\s+(.*)', strong_text)
                if part_match:
                    part_num = int(part_match.group(1))
                    if part_num not in processed_part_numbers:
                        processed_part_numbers.add(part_num)
                        part_title = strong_text
                        duration = self._find_duration_for_part(part_num, soup)
                        numbered_parts.append((part_num, part_title, duration))
        
        # Then look in h3 tags directly
        for h3 in soup.find_all('h3'):
            h3_text = h3.get_text().strip()
            part_match = re.match(r'(\d+)\.\s+(.*)', h3_text)
            if part_match:
                part_num = int(part_match.group(1))
                if part_num not in processed_part_numbers:
                    processed_part_numbers.add(part_num)
                    part_title = h3_text
                    duration = self._find_duration_for_part(part_num, soup)
                    numbered_parts.append((part_num, part_title, duration))
        
        # Finally look in any element that might contain a part number
        for el in soup.find_all(['p', 'span', 'div']):
            el_text = el.get_text().strip()
            part_match = re.match(r'(\d+)\.\s+(.*)', el_text)
            if part_match:
                part_num = int(part_match.group(1))
                if part_num not in processed_part_numbers:
                    processed_part_numbers.add(part_num)
                    part_title = el_text
                    duration = self._find_duration_for_part(part_num, soup)
                    numbered_parts.append((part_num, part_title, duration))
        
        # Add opening song to Treasures section
        if songs:
            opening_song_num = songs[0][0]
            treasures_section.parts.append(
                MeetingPart(title=f"SONG {opening_song_num} AND PRAYER | OPENING COMMENTS (1 MIN.)", duration_minutes=1)
            )
        
        # Distribute numbered parts to the appropriate sections
        for part_num, part_title, duration in numbered_parts:
            # Format title with duration if available
            if duration is not None:
                formatted_title = self._format_part_title(part_title, duration)
                duration_minutes = duration
            else:
                formatted_title = part_title  # Keep original title if no duration found
                duration_minutes = 0  # Use 0 to indicate missing duration
            
            if 1 <= part_num <= 3:
                treasures_section.parts.append(
                    MeetingPart(title=formatted_title, duration_minutes=duration_minutes)
                )
            elif 4 <= part_num <= 6:
                ministry_section.parts.append(
                    MeetingPart(title=formatted_title, duration_minutes=duration_minutes)
                )
            elif 7 <= part_num <= 9:
                christians_section.parts.append(
                    MeetingPart(title=formatted_title, duration_minutes=duration_minutes)
                )
        
        # Add middle song to Christians section if there are at least 2 songs
        if len(songs) >= 2:
            middle_song_num = songs[1][0]
            # Insert at the beginning of the Christians section
            christians_section.parts.insert(0, 
                MeetingPart(title=f"Song {middle_song_num}", duration_minutes=3)
            )
        elif len(christians_section.parts) > 0:
            # If we didn't find a specific middle song but we know there should be one,
            # use the first song as a fallback
            if songs:
                fallback_song = songs[0][0]
                christians_section.parts.insert(0,
                    MeetingPart(title=f"Song {fallback_song}", duration_minutes=3)
                )
        
        # Add concluding comments and song
        closing_song_num = ""
        if len(songs) >= 3:
            closing_song_num = songs[2][0]
        elif len(songs) >= 1:
            # Fallback to the opening song if we don't have a specific closing song
            closing_song_num = songs[0][0]
        
        # Look for concluding comments
        concluding_found = False
        concluding_duration = 3  # Default
        for el in soup.find_all(['p', 'h3', 'strong', 'span']):
            el_text = el.get_text().strip()
            if "Concluding Comments" in el_text:
                concluding_found = True
                # Extract duration if present
                duration = self._extract_duration(el_text)
                if duration:
                    concluding_duration = duration
                
                # Extract song number if present
                song_match = re.search(r'Song\s+(\d+)', el_text, re.IGNORECASE)
                if song_match:
                    closing_song_num = song_match.group(1)
                
                christians_section.parts.append(
                    MeetingPart(title=f"Concluding Comments (3 min.) | Song {closing_song_num} and Prayer", 
                            duration_minutes=concluding_duration + 5)  # Add 5 for song and prayer
                )
                break
        
        # If concluding comments not found, add a default entry
        if not concluding_found:
            christians_section.parts.append(
                MeetingPart(title=f"Concluding Comments (3 min.) | Song {closing_song_num} and Prayer", 
                        duration_minutes=8)
            )
        
        # Return only non-empty sections
        sections = []
        if treasures_section.parts:
            sections.append(treasures_section)
        if ministry_section.parts:
            sections.append(ministry_section)
        if christians_section.parts:
            sections.append(christians_section)
    
        return sections
    
    def _parse_weekend_meeting(self, soup: BeautifulSoup) -> List[MeetingSection]:
        """Parse weekend meeting structure with precise song extraction"""
        # Create the two main sections
        public_talk_section = MeetingSection(title="Public Talk", parts=[])
        watchtower_section = MeetingSection(title="Watchtower Study", parts=[])
        
        #========= Extract Watchtower title ============
        # Extract Watchtower title from the first h1/strong combination
        watchtower_title = None
        
        # Method 1: Find the first h1 element with a strong tag
        h1_elements = soup.find_all('h1')
        for h1 in h1_elements:
            strong_tag = h1.find('strong')
            if strong_tag:
                title_text = strong_tag.get_text().strip()
                if title_text and len(title_text) > 10:  # Reasonable title length
                    watchtower_title = title_text
                    #print(f"Found title in first h1/strong: {watchtower_title}")
                    break
        
        # Method 2: Look for a heading with proper structure if above fails
        if not watchtower_title:
            # Try looking for a strong tag inside any heading element
            for tag in ['h2', 'h3', 'h4']:
                if watchtower_title:
                    break
                    
                elements = soup.find_all(tag)
                for el in elements:
                    strong_tag = el.find('strong')
                    if strong_tag:
                        title_text = strong_tag.get_text().strip()
                        if title_text and len(title_text) > 10:
                            watchtower_title = title_text
                            #print(f"Found title in {tag}/strong: {watchtower_title}")
                            break
        
        # Method 3: As a fallback, look for article title class
        if not watchtower_title:
            article_title_elements = soup.find_all(class_=re.compile(r'article.*title|title.*article', re.IGNORECASE))
            for element in article_title_elements:
                text = element.get_text().strip()
                if text and len(text) > 10:
                    watchtower_title = text
                    #print(f"Found title in article title class: {watchtower_title}")
                    break
        
        # Extract songs directly from the Watchtower article page
        watchtower_opening_song = None
        watchtower_closing_song = None
        
        # Find all song references in the page
        song_elements = []
        for element in soup.find_all(string=re.compile(r'SONG \d+|Song \d+', re.IGNORECASE)):
            parent = element.parent
            if parent:
                song_elements.append((element, parent))
        
        
        
        # Process song elements to find opening and closing songs
        for i, (element, parent) in enumerate(song_elements):
            text = element.strip()
            #print(f"Song element {i}: {text}")
            
            song_match = re.search(r'SONG\s+(\d+)|Song\s+(\d+)', text, re.IGNORECASE)
            if song_match:
                song_num = int(song_match.group(1) or song_match.group(2))
                
                # Determine if this is the opening or closing song for the Watchtower
                # First song is typically the opening song
                if i == 0 and watchtower_opening_song is None:
                    watchtower_opening_song = song_num
                    #print(f"Identified opening Watchtower song: {song_num}")
                
                # Last song is typically the closing song
                if i == len(song_elements) - 1 and watchtower_closing_song is None:
                    watchtower_closing_song = song_num
                    #print(f"Identified closing Watchtower song: {song_num}")
        
        # 1. Add Opening Song and Prayer for Public Talk
        # Note: We don't try to determine this - let the user enter it
        public_talk_section.parts.append(
            MeetingPart(title="Opening Song and Prayer", duration_minutes=3)
        )
        
        # 2. Add Public Talk
        public_talk_section.parts.append(
            MeetingPart(title="Public Talk", duration_minutes=30)
        )
        
        # 3. Add Opening Song for Watchtower
        if watchtower_opening_song:
            watchtower_section.parts.append(
                MeetingPart(title=f"Song {watchtower_opening_song}", duration_minutes=3)
            )
        else:
            # Generic fallback
            watchtower_section.parts.append(
                MeetingPart(title="Song", duration_minutes=3)
            )
        
        # 4. Add Watchtower Study with the extracted title
        if watchtower_title:
            watchtower_section.parts.append(
                MeetingPart(title=watchtower_title, duration_minutes=60)
            )
        else:
            watchtower_section.parts.append(
                MeetingPart(title="Watchtower Study", duration_minutes=60)
            )
        
        # 5. Add Closing Song and Prayer
        if watchtower_closing_song:
            watchtower_section.parts.append(
                MeetingPart(title=f"Song {watchtower_closing_song} and Prayer", duration_minutes=3)
            )
        else:
            # Generic fallback
            watchtower_section.parts.append(
                MeetingPart(title="Concluding Song and Prayer", duration_minutes=3)
            )
        
        return [public_talk_section, watchtower_section]
    
    def update_meetings(self) -> Dict[MeetingType, Meeting]:
        """Fetch and update all current meetings"""
        try:
            meeting_links = self.get_current_meeting_urls()
            meetings = {}
            
            for meeting_type, url in meeting_links.items():
                try:
                    meeting = self.scrape_meeting(url, meeting_type)
                    meetings[meeting_type] = meeting
                except Exception as e:
                    print(f"Error fetching {meeting_type.value} meeting: {e}")
            
            return meetings
            
        except Exception as e:
            print(f"Error updating meetings: {e}")
            return {}