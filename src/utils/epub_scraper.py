"""
Complete EPUB-based Meeting Scraper using JW API endpoint
Language-agnostic implementation using HTML structure and date arithmetic
"""
import calendar
import locale
import logging
import dateparser
import json
import re
import requests
import zipfile
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from xml.etree import ElementTree as ET
from dateutil.parser import parse as parse_date

logger = logging.getLogger("OnTime.EPUBScraper")

# Platformdirs support for cache directory
try:
    from platformdirs import user_cache_dir
except ImportError:
    def user_cache_dir(appname, appauthor=None):
        return str(Path.home() / ".meeting_timer_cache")

from src.models.meeting import Meeting, MeetingSection, MeetingPart, MeetingType

class EPUBMeetingScraper:
    """Language-agnostic EPUB-based scraper using JW API endpoint"""
    
    # Language code mappings for API
    LANG_CODES = {
        "en": "E",   # English
        "it": "I",   # Italian
        "fr": "F",   # French
        "es": "S",   # Spanish
        "de": "X",   # German
        "pt": "T",   # Portuguese
        "ja": "J",   # Japanese
        "ko": "K",   # Korean
        "zh": "CHS", # Chinese Simplified
    }
    
    # ISO codes for txtCMSLang parameter
    ISO_CODES = {
        "en": "en", "it": "it", "fr": "fr", "es": "es", "de": "de",
        "pt": "pt", "ja": "ja", "ko": "ko", "zh": "zh"
    }
    
    API_BASE_URL = "https://b.jw-cdn.org/apis/pub-media/GETPUBMEDIALINKS"
    CACHE_DIR = Path(user_cache_dir("MeetingTimer"))
    
    # Cache TTL settings
    EPUB_TTL = 60 * 60 * 24 * 30  # 30 days for EPUB files
    JSON_TTL = 60 * 60 * 24 * 7   # 7 days for parsed JSON
    
    def __init__(self, language: str = "en"):
        if language not in self.LANG_CODES:
            logger.warning(f"Language '{language}' not supported, defaulting to English.")
            language = "en"
        
        self.language = language
        self.lang_code = self.LANG_CODES[language]
        self.iso_code = self.ISO_CODES[language]
        
        self.CACHE_DIR.mkdir(parents=True, exist_ok=True)
        self.session = requests.Session()
        
        self.cache_path = self.CACHE_DIR / f"{self.language}_meetings_cache.json"
        
        # Setup translations for display only
        self._setup_translations()
    
    def _setup_translations(self):
        """Setup translations for meeting parts - only for display"""
        self.translations = {
            "en": {
                "song": "Song {}",
                "opening_comments": "Opening Comments",
                "concluding_comments": "Concluding Comments", 
                "opening_song_prayer": "Opening Song and Prayer",
                "closing_song_prayer": "Closing Song and Prayer",
                "public_talk": "Public Talk",
                "watchtower_study": "Watchtower Study",
                "treasures": "TREASURES FROM GOD'S WORD",
                "ministry": "APPLY YOURSELF TO THE FIELD MINISTRY", 
                "christian_living": "LIVING AS CHRISTIANS"
            },
            "it": {
                "song": "Cantico {}",
                "opening_comments": "Commenti introduttivi",
                "concluding_comments": "Commenti conclusivi",
                "opening_song_prayer": "Cantico iniziale e preghiera",
                "closing_song_prayer": "Cantico finale e preghiera", 
                "public_talk": "Discorso pubblico",
                "watchtower_study": "Torre di Guardia",
                "treasures": "TESORI DELLA PAROLA DI DIO",
                "ministry": "EFFICACI NEL MINISTERO",
                "christian_living": "VITA CRISTIANA"
            },
            "fr": {
                "song": "Cantique {}",
                "opening_comments": "Paroles d'introduction", 
                "concluding_comments": "Commentaires de conclusion",
                "opening_song_prayer": "Cantique d'ouverture et prière",
                "closing_song_prayer": "Cantique de clôture et prière",
                "public_talk": "Discours public",
                "watchtower_study": "La Tour de Garde",
                "treasures": "JOYAUX DE LA PAROLE DE DIEU",
                "ministry": "APPLIQUE-TOI AU MINISTÈRE", 
                "christian_living": "VIE CHRÉTIENNE"
            },
            "es": {
                "song": "Canción {}",
                "opening_comments": "Palabras de introducción",
                "concluding_comments": "Comentarios finales",
                "opening_song_prayer": "Canción inicial y oración", 
                "closing_song_prayer": "Canción final y oración",
                "public_talk": "Discurso público",
                "watchtower_study": "La Atalaya",
                "treasures": "TESOROS DE LA BIBLIA",
                "ministry": "SEAMOS MEJORES MAESTROS",
                "christian_living": "NUESTRA VIDA CRISTIANA"
            },
            "de": {
                "song": "Lied {}",
                "opening_comments": "Einleitende Worte",
                "concluding_comments": "Schlussworte",
                "opening_song_prayer": "Eingangslied und Gebet",
                "closing_song_prayer": "Schlusslied und Gebet",
                "public_talk": "Öffentlicher Vortrag", 
                "watchtower_study": "Wachtturm",
                "treasures": "SCHÄTZE AUS GOTTES WORT",
                "ministry": "UNS IM DIENST VERBESSERN",
                "christian_living": "UNSER LEBEN ALS CHRIST"
            }
        }
        self.trans = self.translations.get(self.language, self.translations["en"])
    
    def _get_current_issue_dates(self) -> Tuple[str, str]:
        """Get correct MWB and WT issues based on this week's meetings (using Monday of current week)"""
        today = datetime.now()
        # 1. Find this week's Monday
        monday = today - timedelta(days=today.weekday())

        # 2. Determine MWB issue start month based on the Monday
        month = monday.month
        year = monday.year

        if month in [1, 2]:
            mwb_month = 1
        elif month in [3, 4]:
            mwb_month = 3
        elif month in [5, 6]:
            mwb_month = 5
        elif month in [7, 8]:
            mwb_month = 7
        elif month in [9, 10]:
            mwb_month = 9
        else:
            mwb_month = 11

        mwb_issue = f"{year}{mwb_month:02d}"
        w_issue = f"{monday.year}{monday.month:02d}"

        return mwb_issue, w_issue

    def _get_relevant_watchtower_issues(self) -> List[str]:
        """Get Watchtower issue based on 5-week study periods, 2-month lead time"""
        today = datetime.now()
        
        # Each WT covers ~5 weeks, published exactly 2 months before study period
        # So we need to go back 2 months from current date
        
        target_month = today.month - 2
        target_year = today.year
        
        # Handle year rollover
        if target_month <= 0:
            target_month += 12
            target_year -= 1
        
        # The main candidate
        primary_issue = f"{target_year}{target_month:02d}"
        
        # Add adjacent months as backup (for week boundaries)
        candidates = []
        for offset in [-1, 0, 1]:
            candidate_month = target_month + offset
            candidate_year = target_year
            
            if candidate_month <= 0:
                candidate_month += 12
                candidate_year -= 1
            elif candidate_month > 12:
                candidate_month -= 12
                candidate_year += 1
                
            issue_code = f"{candidate_year}{candidate_month:02d}"
            candidates.append(issue_code)
        
        # Remove duplicates and sort, with primary issue first
        candidates = sorted(list(set(candidates)))
        if primary_issue in candidates:
            candidates.remove(primary_issue)
            candidates.insert(0, primary_issue)
        
        logger.debug(f"For {today.strftime('%B %d')}, trying Watchtower issues: {candidates}")
        return candidates
    
    def _download_epub(self, publication: str, issue: str) -> Optional[Path]:
        """Download EPUB file from JW API"""
        cache_file = self.CACHE_DIR / f"{publication}_{issue}_{self.language}.epub"

        # Check cache first
        if cache_file.exists() and (time.time() - cache_file.stat().st_mtime) < self.EPUB_TTL:
            return cache_file

        # Build API URL
        params = {
            'pub': publication,
            'issue': issue,
            'fileformat': 'EPUB',
            'output': 'json',
            'langwritten': self.lang_code,
            'txtCMSLang': self.iso_code,
            'alllangs': '0',
            'includefiles': '1'
        }

        try:
            logger.info(f"Downloading {publication} {issue}...")
            # Print the final constructed API URL for debugging
            full_url = self.session.prepare_request(requests.Request('GET', self.API_BASE_URL, params=params)).url
            logger.debug(f"API request URL: {full_url}")
            response = self.session.get(self.API_BASE_URL, params=params, timeout=30)

            if response.status_code != 200:
                logger.error(f"API request failed: {response.status_code}")
                return None

            # Parse API response to get download URL
            api_data = response.json()
            # extracting EPUB URL from API JSON response
            files = api_data.get("files", {}).get(self.lang_code, {}).get("EPUB", [])
            epub_url = None
            if files and isinstance(files[0], dict):
                epub_url = files[0].get("file", {}).get("url")

            if not epub_url:
                logger.error(f"No EPUB URL found in API response")
                return None
            # Print the EPUB download URL for debugging
            logger.debug(f"EPUB download URL: {epub_url}")

            # Download the EPUB file
            epub_response = self.session.get(epub_url, timeout=60)
            if epub_response.status_code == 200:
                cache_file.write_bytes(epub_response.content)
                logger.info(f"Downloaded {cache_file.name}")
                return cache_file
            else:
                logger.error(f"EPUB download failed: {epub_response.status_code}")
                return None

        except Exception as e:
            logger.error(f"Error downloading {publication} {issue}: {e}")
            return None
    
    def _parse_epub_content(self, epub_path: Path) -> Dict:
        """Parse EPUB file and extract HTML content"""
        try:
            with zipfile.ZipFile(epub_path, 'r') as epub_zip:
                # Find all HTML/XHTML files
                html_files = [f for f in epub_zip.namelist() if f.endswith(('.html', '.xhtml'))]
                logger.debug(f"EPUB contains {len(html_files)} HTML files: {html_files[:5]}")
                content = {}
                for html_file in html_files:
                    try:
                        html_content = epub_zip.read(html_file).decode('utf-8')
                        content[html_file] = html_content
                    except Exception as e:
                        logger.error(f"Error reading {html_file}: {e}")
                        continue
                
                return content
                
        except Exception as e:
            logger.error(f"Error parsing EPUB {epub_path}: {e}")
            return {}
    
    def _data_europea(self, testo: str) -> Optional[str]:
        """Lunedi' della settimana per le intestazioni «7-13 settembre» e
        «28 settembre – 4 ottobre» (giorno prima del mese), come in italiano,
        francese, spagnolo, tedesco...  Se il formato non e' questo, None e
        resta valido il lettore originale (formato inglese «September 7-13»).
        """
        import dateparser
        from datetime import date as _data

        t = re.sub(r"[\u00a0\u00ba\u00b0]", " ", testo or "").strip()
        m = re.search(r"(\d{1,2})\s+([^\W\d_]+)(?:\s+\d{4})?\s*[-\u2013\u2014]+\s*(\d{1,2})\s+([^\W\d_]+)", t)
        if m:
            giorno, mese = int(m.group(1)), m.group(2)
        else:
            m = re.search(r"(\d{1,2})\s*[-\u2013\u2014]+\s*(\d{1,2})\s+([^\W\d_]+)", t)
            if not m:
                return None
            giorno, mese = int(m.group(1)), m.group(3)
        prova = dateparser.parse(f"1 {mese} 2000", languages=[self.language, "en"])
        if not prova:
            return None
        anno_esplicito = re.search(r"\b(20\d{2})\b", t)
        oggi = datetime.now().date()
        candidati = [int(anno_esplicito.group(1))] if anno_esplicito else [
            oggi.year - 1, oggi.year, oggi.year + 1]
        scelta = None
        for anno in candidati:
            try:
                d = _data(anno, prova.month, giorno)
            except ValueError:
                continue
            if scelta is None or abs((d - oggi).days) < abs((scelta - oggi).days):
                scelta = d
        if scelta is None:
            return None
        return (scelta - timedelta(days=scelta.weekday())).strftime("%Y-%m-%d")

    def _parse_meeting_date_from_workbook(self, date_text: str) -> Optional[str]:
        """Language-agnostic date parsing using locale and dateparser"""
        try:
            date_text = date_text.strip()
            logger.debug(f"Parsing date text: '{date_text}'")
            europea = self._data_europea(date_text)
            if europea:
                return europea
            
            # Method 1: Try with dateparser library (handles most languages automatically)
            try:
                import dateparser
                
                # Extract date range patterns
                # Pattern 1: Same month range (e.g., "MAY 5-11", "MAGGIO 5-11", "MAI 5-11")
                same_month_match = re.search(r'([A-ZÀ-ÿ]+)\s+(\d{1,2})\s*[-–]\s*(\d{1,2})', date_text, re.IGNORECASE)
                
                if same_month_match:
                    month_name, start_day, end_day = same_month_match.groups()
                    start_day = int(start_day)
                    
                    # Create a test date string with the month name and start day
                    # Use current year as baseline
                    current_year = datetime.now().year
                    test_date_str = f"{start_day} {month_name} {current_year}"
                    
                    # Parse using dateparser with the document's language
                    parsed_date = dateparser.parse(
                        test_date_str, 
                        languages=[self.language, 'en'],  # Try document language first, then English
                        settings={'PREFER_DAY_OF_MONTH': 'first'}
                    )
                    
                    if parsed_date:
                        # Adjust year if needed (if the date is in the past, try next year)
                        if parsed_date < datetime.now() - timedelta(days=30):
                            parsed_date = parsed_date.replace(year=current_year + 1)
                        
                        # Ensure we get the Monday of that week
                        monday_date = self._get_monday_of_week(parsed_date)
                        result = monday_date.strftime('%Y-%m-%d')
                        logger.debug(f"Dateparser same-month: {date_text} -> {result}")
                        return result
                
                # Pattern 2: Cross-month range (e.g., "JUNE 30--JULY 6", "GIUGNO 30--LUGLIO 6")
                cross_month_match = re.search(
                    r'([A-ZÀ-ÿ]+)\s+(\d{1,2})\s*[-–]+\s*([A-ZÀ-ÿ]+)\s+(\d{1,2})', 
                    date_text, re.IGNORECASE
                )
                
                if cross_month_match:
                    start_month_name, start_day, end_month_name, end_day = cross_month_match.groups()
                    start_day = int(start_day)
                    
                    # Parse the start date
                    current_year = datetime.now().year
                    test_date_str = f"{start_day} {start_month_name} {current_year}"
                    
                    parsed_date = dateparser.parse(
                        test_date_str,
                        languages=[self.language, 'en'],
                        settings={'PREFER_DAY_OF_MONTH': 'first'}
                    )
                    
                    if parsed_date:
                        # Adjust year if needed
                        if parsed_date < datetime.now() - timedelta(days=30):
                            parsed_date = parsed_date.replace(year=current_year + 1)
                        
                        # Ensure we get the Monday of that week
                        monday_date = self._get_monday_of_week(parsed_date)
                        result = monday_date.strftime('%Y-%m-%d')
                        logger.debug(f"Dateparser cross-month: {date_text} -> {result}")
                        return result
                        
            except ImportError:
                logger.warning(f"dateparser not available, falling back to locale method")
            
            # Method 2: Use locale-based parsing (fallback)
            return self._parse_with_locale(date_text)
            
        except Exception as e:
            logger.error(f"Error parsing date '{date_text}': {e}")
            return None
    
    def _parse_with_locale(self, date_text: str) -> Optional[str]:
        """Fallback method using locale settings"""
        try:
            # Map language codes to locale codes
            locale_map = {
                'en': ['en_US.UTF-8', 'en_GB.UTF-8', 'C'],
                'it': ['it_IT.UTF-8', 'it_CH.UTF-8'],
                'fr': ['fr_FR.UTF-8', 'fr_CA.UTF-8'],
                'es': ['es_ES.UTF-8', 'es_MX.UTF-8'],
                'de': ['de_DE.UTF-8', 'de_CH.UTF-8'],
                'pt': ['pt_PT.UTF-8', 'pt_BR.UTF-8'],
                'ja': ['ja_JP.UTF-8'],
                'ko': ['ko_KR.UTF-8'],
                'zh': ['zh_CN.UTF-8', 'zh_TW.UTF-8']
            }
            
            locales_to_try = locale_map.get(self.language, ['C'])
            
            # Save current locale
            original_locale = locale.getlocale()
            
            for loc in locales_to_try:
                try:
                    locale.setlocale(locale.LC_TIME, loc)
                    
                    # Get month names in the current locale
                    month_names = {}
                    for i in range(1, 13):
                        full_name = calendar.month_name[i].upper()
                        abbr_name = calendar.month_abbr[i].upper()
                        month_names[full_name] = i
                        month_names[abbr_name] = i
                    
                    # Try to parse with this locale
                    result = self._parse_with_month_names(date_text, month_names)
                    if result:
                        return result
                        
                except locale.Error:
                    continue
                finally:
                    # Restore original locale
                    try:
                        locale.setlocale(locale.LC_TIME, original_locale)
                    except:
                        pass
            
            # Final fallback: use position-based parsing
            return self._parse_by_position(date_text)
            
        except Exception as e:
            logger.error(f"Locale parsing failed: {e}")
            return self._parse_by_position(date_text)
        
    def _parse_with_month_names(self, date_text: str, month_names: dict) -> Optional[str]:
        """Parse using provided month name mappings"""
        # Same month pattern
        same_month_match = re.search(r'([A-ZÀ-ÿ]+)\s+(\d{1,2})\s*[-–]\s*(\d{1,2})', date_text, re.IGNORECASE)
        
        if same_month_match:
            month_name, start_day, end_day = same_month_match.groups()
            month_name_upper = month_name.upper()
            
            month_num = month_names.get(month_name_upper)
            if month_num:
                start_day = int(start_day)
                current_year = datetime.now().year
                
                # Create date and find Monday
                try:
                    parsed_date = datetime(current_year, month_num, start_day)
                    
                    # Adjust year if needed
                    if parsed_date < datetime.now() - timedelta(days=30):
                        parsed_date = parsed_date.replace(year=current_year + 1)
                    
                    monday_date = self._get_monday_of_week(parsed_date)
                    result = monday_date.strftime('%Y-%m-%d')
                    logger.debug(f"Locale parsing: {date_text} -> {result}")
                    return result
                    
                except ValueError:
                    pass
        
        return None

    def _parse_by_position(self, date_text: str) -> Optional[str]:
        """Final fallback: parse by position and context"""
        try:
            # Extract the first number as start day
            day_match = re.search(r'(\d{1,2})', date_text)
            if not day_match:
                return None
                
            start_day = int(day_match.group(1))
            
            # Use current date context to guess month
            now = datetime.now()
            current_month = now.month
            current_year = now.year
            
            # Try current month, then next few months
            for month_offset in range(4):  # Try current and next 3 months
                try:
                    test_month = current_month + month_offset
                    test_year = current_year
                    
                    if test_month > 12:
                        test_month = test_month - 12
                        test_year += 1
                    
                    # Try to create a valid date
                    test_date = datetime(test_year, test_month, start_day)
                    
                    # Find Monday of that week
                    monday_date = self._get_monday_of_week(test_date)
                    
                    # Check if this seems reasonable (not too far in past/future)
                    days_diff = abs((monday_date - now).days)
                    if days_diff <= 120:  # Within 4 months
                        result = monday_date.strftime('%Y-%m-%d')
                        logger.debug(f"Position fallback: {date_text} -> {result}")
                        return result
                        
                except ValueError:
                    continue
            
            return None
            
        except Exception as e:
            logger.error(f"Position parsing failed: {e}")
            return None
        
    def _get_monday_of_week(self, date_obj: datetime) -> datetime:
        """Get the Monday of the week containing the given date"""
        # Calculate days since Monday (0 = Monday, 6 = Sunday)
        days_since_monday = date_obj.weekday()
        
        # Subtract days to get to Monday
        monday_date = date_obj - timedelta(days=days_since_monday)
        
        return monday_date
    
    def _determine_section_by_structure(self, header, container) -> str:
        """Determine section based on HTML structure rather than text"""
        # Look for the parent section with class indicators
        section_parent = header
        for _ in range(5):  # Look up to 5 levels up
            section_parent = section_parent.find_parent()
            if not section_parent:
                break
            
            classes = ' '.join(section_parent.get('class', []))
            if 'dc-icon--gem' in classes:
                return 'treasures'
            elif 'dc-icon--wheat' in classes:
                return 'ministry'
            elif 'dc-icon--sheep' in classes:
                return 'christian_living'
        
        # Fallback: look for section headers in the container
        treasures_header = container.find(string=re.compile(r'TREASURES|TESORI|JOYAUX|TESOROS|SCHÄTZE'))
        ministry_header = container.find(string=re.compile(r'APPLY|EFFICACI|APPLIQUE|SEAMOS|VERBESSERN'))
        christian_header = container.find(string=re.compile(r'LIVING|VITA|VIE|NUESTRA|UNSER'))
        
        # Determine position relative to section headers
        if treasures_header and ministry_header:
            if header.sourceline < ministry_header.parent.sourceline:
                return 'treasures'
            elif christian_header and header.sourceline < christian_header.parent.sourceline:
                return 'ministry'
            else:
                return 'christian_living'
        
        return 'treasures'  # default
    
    def _get_default_duration_by_position(self, position: int) -> int:
        """Get default duration based on position in meeting"""
        defaults = [4, 1, 10, 10, 4, 2, 3, 3, 3, 4, 15, 30, 3]  # typical meeting durations
        return defaults[position] if position < len(defaults) else 5
    
    def _determine_part_type(self, text: str, position: int) -> str:
        """Enhanced part type determination"""
        text_lower = text.lower()
        
        # Songs and prayers
        if re.search(r'song.*prayer|prayer.*song', text_lower):
            return 'song_prayer'
        elif re.search(r'song|cantico|cantique|canción|lied', text_lower):
            return 'song'
        elif 'prayer' in text_lower or 'preghiera' in text_lower or 'prière' in text_lower:
            return 'prayer'
        
        # Comments
        elif any(word in text_lower for word in ['opening comment', 'concluding comment', 'commenti']):
            return 'comments'
        
        # Bible reading
        elif 'bible reading' in text_lower:
            return 'bible_reading'
        
        # Spiritual gems
        elif 'spiritual gems' in text_lower:
            return 'spiritual_gems'
        
        # Ministry parts
        elif any(word in text_lower for word in ['conversation', 'following up', 'making disciples', 'explaining']):
            return 'ministry'
        
        # Talks
        elif 'talk' in text_lower or 'discorso' in text_lower:
            return 'talk'
        
        # Studies
        elif any(word in text_lower for word in ['bible study', 'studio', 'étude']):
            return 'study'
        
        # Discussion
        elif 'discussion' in text_lower:
            return 'discussion'
        
        # Local needs
        elif 'local needs' in text_lower:
            return 'local_needs'
        
        # Numbered parts (generic parts)
        elif re.search(r'^\d+\.', text.strip()):
            return 'part'
        
        return 'part'  # Default fallback
    
    def _extract_songs(self, container) -> List[int]:
        """Extract song numbers universally using regex"""
        songs = []
        
        # Look for song patterns in any language
        song_patterns = [
            r'(?:Song|Cantico|Cantique|Canción|Lied)\s+(\d{1,3})',
            r'(\d{1,3})\s*(?:Song|Cantico|Cantique|Canción|Lied)',
            r'<.*?>(\d{1,3})<.*?>'  # Numbers in HTML tags
        ]
        
        text_content = container.get_text() if hasattr(container, 'get_text') else str(container)
        
        for pattern in song_patterns:
            matches = re.findall(pattern, text_content, re.IGNORECASE)
            for match in matches:
                try:
                    song_num = int(match)
                    if 1 <= song_num <= 200:  # Valid song range
                        songs.append(song_num)
                except ValueError:
                    continue
        
        return list(dict.fromkeys(songs))  # Remove duplicates while preserving order
    
    def _extract_midweek_meetings(self, epub_content: Dict) -> Dict[str, List[Dict]]:
        """
        Extract midweek meeting parts using structure-based approach, scanning only TOC files for date links.
        Improved: Accepts date ranges in headings, does not require ISO date in heading, uses fallback if needed.
        Prevents cross-month fallback conflicts and ensures each XHTML file is uniquely assigned.
        """
        meetings = {}
        import re
        from bs4 import BeautifulSoup
        # Only scan TOC files for date links
        toc_links = []
        toc_date_fallback = {}  # file_path -> parsed_date from TOC
        for file_name, html in epub_content.items():
            if 'toc' not in file_name.lower():
                continue
            logger.debug(f"Scanning TOC file: {file_name}")
            soup = BeautifulSoup(html, 'html.parser')
            links = soup.find_all('a')
            for link in links:
                date_text = link.get_text(strip=True)
                href = link.get('href')
                if not date_text or not href:
                    continue
                match = re.search(r'(\d{1,2})\s*(?:[.–\-–]|bis)?\s*(\d{1,2})[.,]?\s*(\w+)?', date_text, re.IGNORECASE)
                if match:
                    logger.debug(f"TOC entry: '{date_text}'  {href}")
                    toc_links.append((date_text, href))
                    parsed_date = self._parse_meeting_date_from_workbook(date_text)
                    if parsed_date:
                        target_file = href.split('#')[0]
                        content_file = None
                        if target_file in epub_content:
                            content_file = target_file
                        else:
                            for f in epub_content:
                                if f.endswith(target_file):
                                    content_file = f
                                    break
                        if content_file:
                            toc_date_fallback[content_file] = parsed_date

        # --- Begin: Populate meetings dict with parsed meeting parts
        registered_meeting_dates = set()
        for date_text, href in toc_links:
            file_path = None
            target_file = href.split('#')[0]
            if target_file in epub_content:
                file_path = target_file
            else:
                for f in epub_content:
                    if f.endswith(target_file):
                        file_path = f
                        break
            if not file_path:
                continue
            try:
                body_html = epub_content[file_path]
                soup_part = BeautifulSoup(body_html, 'html.parser')

                # Extract all <h1> and <h2> headings
                headings = []
                for h in soup_part.find_all(['h1', 'h2']):
                    headings.append(h.get_text().strip())

                # Try to parse a date range from each heading. Use the same normalization logic.
                date_found = None
                for h_text in headings:
                    parsed_date = self._parse_meeting_date_from_workbook(h_text)
                    if parsed_date:
                        date_found = parsed_date
                        break

                # Date fallback logic
                parsed_date = date_found
                if not parsed_date:
                    # Try fallback using TOC date if available
                    parsed_date = toc_date_fallback.get(file_path)
                    if parsed_date:
                        if parsed_date in registered_meeting_dates:
                            logger.warning(f"Skipping duplicate meeting date: {parsed_date} from {file_path}")
                            continue  # Skip registering this meeting
                        logger.debug(f"No heading date match, using TOC date {parsed_date} for {file_path}")
                    else:
                        logger.warning(f"Could not determine date for {file_path}, skipping")
                        continue

                # Instead of registering and checking for duplicates immediately, check for parts first
                parts = self._extract_parts_by_structure(soup_part)
                # Check if there are actual parts
                if not parts or len(parts) == 0:
                    logger.warning(f"Skipping empty or invalid meeting for {parsed_date} from {file_path}")
                    continue

                # Now check for duplicates
                if parsed_date in registered_meeting_dates:
                    logger.warning(f"Duplicate meeting for {parsed_date} detected from {file_path}, skipping")
                    continue
                registered_meeting_dates.add(parsed_date)

                meetings[parsed_date] = parts
                logger.info(f"Registered MIDWEEK meeting for {parsed_date} with {len(parts)} parts")
            except Exception as e:
                logger.error(f"Error extracting midweek from {file_path}: {e}")
        # --- End: Populate meetings dict
        return meetings
    
    def _extract_parts_by_structure(self, container) -> List[Dict]:
        """Extract meeting parts using HTML structure with improved duration parsing"""
        parts = []
        
        # Find all h3 elements (meeting parts)
        part_headers = container.find_all('h3')
        
        for i, header in enumerate(part_headers):
            text = header.get_text().strip()
            
            # Skip empty headers
            if not text:
                continue
            
            # Extract duration with improved logic
            duration = self._extract_duration_from_header_context(header, i)
            
            # Determine section by HTML structure
            section = self._determine_section_by_structure(header, container)
            
            # Determine part type
            part_type = self._determine_part_type(text, i)
            
            parts.append({
                'title': text,
                'duration_minutes': duration,
                'type': part_type,
                'section': section
            })
        
        return parts
    
    def _extract_duration_from_header_context(self, header, position: int) -> int:
        """Extract duration from header and its surrounding context"""
        
        # Method 1: Check if duration is directly in the header text
        header_text = header.get_text()
        duration_match = re.search(r'\((\d+)\s*min', header_text, re.IGNORECASE)
        if duration_match:
            duration = int(duration_match.group(1))
            logger.debug(f"Found duration in header: {duration} min for '{header_text[:50]}...'")
            return duration
        
        # Method 2: Look in the next few siblings for duration info
        # This handles cases where duration is in a separate div after the header
        for sibling in header.find_next_siblings():
            if sibling.name in ['div', 'p', 'span']:
                sibling_text = sibling.get_text()
                duration_match = re.search(r'\((\d+)\s*min', sibling_text, re.IGNORECASE)
                if duration_match:
                    duration = int(duration_match.group(1))
                    logger.debug(f"Found duration in sibling: {duration} min for '{header_text[:50]}...'")
                    return duration
            
            # Stop looking if we hit another header or major section
            if sibling.name in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
                break
            
            # Also check nested elements within siblings
            duration_elements = sibling.find_all(string=re.compile(r'\(\d+\s*min', re.IGNORECASE))
            if duration_elements:
                for elem_text in duration_elements:
                    duration_match = re.search(r'\((\d+)\s*min', elem_text, re.IGNORECASE)
                    if duration_match:
                        duration = int(duration_match.group(1))
                        logger.debug(f"Found duration in nested element: {duration} min for '{header_text[:50]}...'")
                        return duration
        
        # Method 3: Look in the parent container for duration info
        parent = header.parent
        if parent:
            parent_text = parent.get_text()
            duration_match = re.search(r'\((\d+)\s*min', parent_text, re.IGNORECASE)
            if duration_match:
                duration = int(duration_match.group(1))
                logger.debug(f"Found duration in parent: {duration} min for '{header_text[:50]}...'")
                return duration
        
        # Method 4: Use improved default durations based on content analysis
        default_duration = self._get_intelligent_default_duration(header_text, position)
        logger.debug(f"Using intelligent default duration: {default_duration} min for '{header_text[:50]}...'")
        return default_duration
    
    def _get_intelligent_default_duration(self, text: str, position: int) -> int:
        """Get more intelligent default duration based on part content and position"""
        text_lower = text.lower()
        
        # Songs and prayers
        if re.search(r'song.*prayer|prayer.*song', text_lower):
            return 3
        elif 'song' in text_lower:
            return 3
        elif 'prayer' in text_lower:
            return 2
        
        # Opening/closing comments
        elif 'opening comment' in text_lower or 'concluding comment' in text_lower:
            return 1
        
        # Bible reading
        elif 'bible reading' in text_lower:
            return 4
        
        # Spiritual gems
        elif 'spiritual gems' in text_lower:
            return 10
        
        # Treasures section parts (usually longer)
        elif any(keyword in text_lower for keyword in ['treasures', 'tesori', 'joyaux', 'tesoros', 'schätze']):
            return 10
        
        # Ministry parts (field service)
        elif any(keyword in text_lower for keyword in ['conversation', 'following up', 'making disciples', 'explaining']):
            if 'conversation' in text_lower:
                return 3
            elif 'following up' in text_lower:
                return 4
            elif 'making disciples' in text_lower:
                return 5
            elif 'explaining' in text_lower:
                return 4
            else:
                return 3
        
        # Talk
        elif 'talk' in text_lower:
            return 5
        
        # Living as Christians section
        elif any(keyword in text_lower for keyword in ['local needs', 'congregation bible study']):
            if 'local needs' in text_lower:
                return 15
            elif 'congregation bible study' in text_lower:
                return 30
            else:
                return 10
        
        # Discussion parts (usually longer)
        elif 'discussion' in text_lower:
            return 15
        
        # Video parts
        elif 'video' in text_lower:
            return 10
        
        # Position-based fallback (old logic as final resort)
        defaults = [3, 1, 10, 4, 3, 4, 5, 3, 15, 30, 3]  # Updated defaults
        if position < len(defaults):
            return defaults[position]
        
        return 5  # Final fallback
    
    def _extract_weekend_meetings(self, epub_content: Dict) -> Dict[str, List[Dict]]:
        """
        Extract weekend meeting parts from Watchtower EPUB using the detailed group TOC page.
        """
        meetings = {}
        from bs4 import BeautifulSoup
        
        # Step 1: Find the TOC XHTML file and parse it.
        toc_file = None
        for file_name in epub_content:
            if 'toc' in file_name.lower() and file_name.endswith(('.xhtml', '.html')):
                toc_file = file_name
                break
        if not toc_file:
            logger.warning(f"No TOC file found in Watchtower EPUB.")
            return meetings
        
        toc_html = epub_content[toc_file]
        soup = BeautifulSoup(toc_html, 'html.parser')
        logger.debug(f"Scanning TOC file: {toc_file}")
        
        # --- Begin: Find the 'chapter2' li to locate the detailed groupTOC
        chapter2 = soup.find('li', id='chapter2')
        if chapter2:
            a = chapter2.find('a')
            if a and a.get('href'):
                group_toc_href = a['href'].split('#')[0]
                # Find full path
                group_toc_file = None
                for f in epub_content:
                    if f.endswith(group_toc_href):
                        group_toc_file = f
                        break
                if group_toc_file:
                    logger.debug(f"Found group TOC file: {group_toc_file}")
                    toc_html = epub_content[group_toc_file]
                    soup = BeautifulSoup(toc_html, 'html.parser')
        # --- End: groupTOC logic
        
        date_to_file = {}
        
        # Scan for <h3> elements containing date range and article titles, then extract article file from sibling <a>
        for h3 in soup.find_all('h3'):
            h3_text = h3.get_text(" ", strip=True)
            logger.debug(f"Found heading with potential date: '{h3_text}'")
            logger.debug(f"Inspecting heading: '{h3_text}'")

            # --- New: try to extract the heading date using fallback logic for date ranges
            meeting_date = self._extract_heading_date(h3_text)
            if not meeting_date:
                logger.debug(f"Skipping due to no date-like pattern in heading.")
                continue
            else:
                logger.debug(f"Passed date pattern check for heading.")
            
            # Find the first <a> sibling after this <h3> (article link)
            a_tag = None
            for sib in h3.find_all_next():
                if sib.name == 'a':
                    a_tag = sib
                    break
                # stop if we hit another h3
                if sib.name == 'h3':
                    break

            if a_tag and a_tag.get('href'):
                href = a_tag['href'].split('#')[0]
                content_file = None
                if href in epub_content:
                    content_file = href
                else:
                    for f in epub_content:
                        if f.endswith(href):
                            content_file = f
                            break
                if content_file:
                    date_to_file[meeting_date] = (content_file, h3_text)
                    logger.debug(f"Matched TOC entry '{h3_text}' to file '{content_file}'")

        # Step 3: Parse the corresponding file and extract <h1> article title and songs.
        # Sort the meeting dates before processing, in chronological order
        for meeting_date in sorted(date_to_file):
            content_file, link_text = date_to_file[meeting_date]
            logger.debug(f"Processing Watchtower content from: {content_file} for date: {meeting_date}")
            html_content = epub_content[content_file]
            try:
                article_soup = BeautifulSoup(html_content, 'html.parser')
                # Find article title
                title_elem = article_soup.find("h1")
                if not title_elem:
                    logger.warning(f"No <h1> found in {content_file}")
                    continue
                title_text = title_elem.get_text().strip()
                if len(title_text) < 10:
                    continue
                
                # Extract songs
                songs = self._extract_songs(article_soup)
                logger.debug(f"Normalized meeting date: {meeting_date}")
                meeting_parts = self._build_weekend_meeting(title_text, songs)
                meetings[meeting_date] = meeting_parts
                logger.info(f"Registered WEEKEND meeting for {meeting_date}: {title_text} with {len(songs)} songs")
            except Exception as e:
                logger.error(f"Error extracting weekend from {content_file}: {e}")
                continue
        
        return meetings
    
    def _build_weekend_meeting(self, watchtower_title: str, songs: List[int]) -> List[Dict]:
        """Build weekend meeting structure with correct song placement"""
        meeting_parts = []
        
        # Limit to only 2 songs maximum for weekend meetings
        if len(songs) > 2:
            songs = songs[:2]  # Take only first 2 songs found
            logger.debug(f"Limited weekend songs to 2: {songs}")
        
        # 1. Opening Song and Prayer (GENERIC - no specific number)
        meeting_parts.append({
            'title': "OPENING_SONG_PRAYER",
            'duration_minutes': 3,
            'type': 'song_prayer',
            'section': 'public_talk'
        })
        
        # 2. Public Talk
        meeting_parts.append({
            'title': self.trans['public_talk'],
            'duration_minutes': 30,
            'type': 'talk',
            'section': 'public_talk'
        })
        
        # 3. Watchtower Opening Song (FIRST song from EPUB - e.g., Song 87)
        watchtower_song = songs[0] if songs else None
        if watchtower_song:
            meeting_parts.append({
                'title': f"MIDDLE_SONG {watchtower_song}",
                'duration_minutes': 3,
                'type': 'song',
                'section': 'watchtower'
            })
        else:
            meeting_parts.append({
                'title': "MIDDLE_SONG",
                'duration_minutes': 3,
                'type': 'song',
                'section': 'watchtower'
            })
        
        # 4. Watchtower Study
        meeting_parts.append({
            'title': watchtower_title,
            'duration_minutes': 60,
            'type': 'study',
            'section': 'watchtower'
        })
        
        # 5. Closing Song and Prayer (SECOND song from EPUB - e.g., Song 90)
        closing_song = songs[1] if len(songs) > 1 else watchtower_song
        if closing_song:
            meeting_parts.append({
                'title': f"CLOSING_SONG_PRAYER |{closing_song}",
                'duration_minutes': 3,
                'type': 'song_prayer',
                'section': 'watchtower'
            })
        else:
            meeting_parts.append({
                'title': "CLOSING_SONG_PRAYER",
                'duration_minutes': 3,
                'type': 'song_prayer',
                'section': 'watchtower'
            })
        
        return meeting_parts
    
    def _estimate_weekend_date(self) -> str:
        """Estimate weekend date for Watchtower study"""
        today = datetime.now()
        days_until_weekend = (5 - today.weekday()) % 7  # Saturday
        if days_until_weekend == 0 and today.weekday() == 5:  # If today is Saturday
            weekend = today
        else:
            weekend = today + timedelta(days=days_until_weekend)
        
        return weekend.strftime('%Y-%m-%d')
    
    def _load_cached_meetings(self) -> Dict:
        """Load cached meeting data from JSON"""
        cache_file = self.CACHE_DIR / f"{self.language}_meetings_cache.json"
        
        if cache_file.exists() and (time.time() - cache_file.stat().st_mtime) < self.JSON_TTL:
            try:
                with open(cache_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error loading cache: {e}")
        
        return {}
    
    def _post_process_midweek_meetings(self, meetings_data: Dict):
        """Post-process midweek meetings using position-based logic (no language dependencies)"""
        
        if 'midweek' not in meetings_data:
            return
        
        for issue, issue_meetings in meetings_data['midweek'].items():
            for meeting_date, parts_list in issue_meetings.items():
                if not parts_list or len(parts_list) < 3:
                    continue
                    
                logger.debug(f"Post-processing midweek meeting {meeting_date}")
                
                # Extract all song numbers using universal pattern
                song_numbers = []
                for part in parts_list:
                    song_num = self._extract_song_number(part['title'])
                    if song_num:
                        song_numbers.append(song_num)
                
                logger.debug(f"Found songs: {song_numbers}")
                
                if len(song_numbers) < 2:
                    logger.debug(f"Not enough songs found, skipping post-processing")
                    continue
                
                # Process based on POSITION and DURATION patterns
                new_parts = []
                
                for i, part in enumerate(parts_list):
                    title = part['title']
                    duration = part.get('duration_minutes', 0)
                    
                    # RULE 1: First part with song number 
                    if (i == 0 and 
                        self._extract_song_number(title) and 
                        duration <= 3):  # Combined opening is usually 1 minutes
                        
                        opening_song = song_numbers[0]
                        logger.debug(f"Splitting opening part by position/duration")
                        
                        new_parts.extend([
                            {
                                'title': f"OPENING_SONG_PRAYER|{opening_song}",
                                'duration_minutes': 4,
                                'type': 'song_prayer',
                                'section': part.get('section', 'treasures')
                            },
                            {
                                'title': "OPENING_COMMENTS",
                                'duration_minutes': 1,
                                'type': 'comments',
                                'section': part.get('section', 'treasures')
                            }
                        ])
                        
                    # RULE 2: Last part with song number + long duration (likely combined closing)
                    elif (i >= len(parts_list) - 2 and 
                        self._extract_song_number(title) and 
                        duration <= 4):  # Combined closing is usually 4+ minutes
                        
                        closing_song = song_numbers[-1]
                        logger.debug(f"Splitting closing part by position/duration")
                        
                        new_parts.extend([
                            {
                                'title': "CONCLUDING_COMMENTS",
                                'duration_minutes': 3,
                                'type': 'comments',
                                'section': part.get('section', 'christian_living')
                            },
                            {
                                'title': f"CLOSING_SONG_PRAYER|{closing_song}",
                                'duration_minutes': 4,
                                'type': 'song_prayer',
                                'section': part.get('section', 'christian_living')
                            }
                        ])
                        
                    # RULE 3: Middle part with song number + short duration (standalone song)
                    elif (self._extract_song_number(title) and 
                        duration <= 3 and  # Short duration = standalone song
                        i > 0 and i < len(parts_list) - 2):  # Not first or last
                        
                        song_num = self._extract_song_number(title)
                        logger.debug(f"Processing middle song by position/duration")
                        
                        new_parts.append({
                            'title': f"MIDDLE_SONG|{song_num}",
                            'duration_minutes': 2,
                            'type': 'song',
                            'section': part.get('section', 'christian_living')
                        })
                        
                    else:
                        # Regular part - keep as is
                        new_parts.append(part)
                
                # Replace the original parts list
                meetings_data['midweek'][issue][meeting_date] = new_parts
                logger.debug(f"Post-processed {meeting_date}: {len(parts_list)} -> {len(new_parts)} parts")
    
    def _extract_song_number(self, text: str) -> Optional[int]:
        """Extract song number from text with improved precision"""
        # Multi-language song word patterns
        song_patterns = [
            r'(?:Song|SONG|Cantico|CANTICO|Cantique|CANTIQUE|Canción|CANCIÓN|Lied|LIED)\s+(\d{1,3})',
            r'(\d{1,3})\s*(?:Song|SONG|Cantico|CANTICO|Cantique|CANTIQUE|Canción|CANCIÓN|Lied|LIED)',
        ]
        
        for pattern in song_patterns:
            song_match = re.search(pattern, text, re.IGNORECASE)
            if song_match:
                try:
                    song_num = int(song_match.group(1))
                    if 1 <= song_num <= 200:  # Valid song range
                        return song_num
                except ValueError:
                    continue
        
        return None
    
    def _save_cached_meetings(self, meetings_data: Dict):
        """Save meeting data with two-stage process: raw → processed"""
        
        cache_file = self.CACHE_DIR / f"{self.language}_meetings_cache.json"
        
        try:
            # STAGE 1: Save original raw data first
            logger.debug(f"Saving raw cache data...")
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(meetings_data, f, ensure_ascii=False, indent=2)
            logger.debug(f"Raw cache saved: {cache_file}")
            
            # STAGE 2: Read back, post-process, and save updated version
            logger.debug(f"Reading back for post-processing...")
            with open(cache_file, 'r', encoding='utf-8') as f:
                loaded_data = json.load(f)
            
            # Post-process the loaded data
            self._post_process_midweek_meetings(loaded_data)
            
            # Save the processed version
            logger.debug(f"Saving processed cache data...")
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(loaded_data, f, ensure_ascii=False, indent=2)
            logger.debug(f"Processed cache saved: {cache_file}")

        except Exception as e:
            logger.error(f"Error in two-stage save process: {e}")

    
    def update_meetings_cache(self) -> bool:
        """Update the meetings cache with latest EPUB content"""
        logger.info(f"Updating meetings cache...")
        today = datetime.now()
        
        # Get current issue dates
        mwb_issue, _ = self._get_current_issue_dates()

        # Download EPUBs, print the constructed download URL for debugging
        logger.debug(f"Attempting to download MWB EPUB for issue {mwb_issue}...")
        mwb_epub = self._download_epub('mwb', mwb_issue)

        meetings_data = self._load_cached_meetings()

        # Parse midweek meetings
        if 'midweek' not in meetings_data:
            meetings_data['midweek'] = {}
        if mwb_epub:
            logger.info(f"Parsing midweek meetings from {mwb_epub.name}...")
            mwb_content = self._parse_epub_content(mwb_epub)
            midweek_meetings = self._extract_midweek_meetings(mwb_content)
            meetings_data['midweek'][mwb_issue] = midweek_meetings or {}
        else:
            meetings_data['midweek'][mwb_issue] = {}

        # We'll try multiple Watchtower issues and keep the first one that yields meetings
        w_issues = self._get_relevant_watchtower_issues()
        w_epub = None
        w_issue_selected = None
        for w_candidate in w_issues:
            logger.debug(f"Attempting to download Watchtower EPUB for issue {w_candidate}...")
            temp_epub = self._download_epub('w', w_candidate)
            if temp_epub:
                # Parse the content to check if it has studies for our target date
                w_content = self._parse_epub_content(temp_epub)
                weekend_meetings = self._extract_weekend_meetings(w_content)
                
                # Check if this Watchtower contains studies for our target date
                # _extract_heading_date returns the START of the study week
                # (e.g., "2026-02-23" for heading "February 23 - March 1, 2026")
                contains_current_studies = False
                for meeting_date_str in weekend_meetings.keys():
                    week_start = datetime.strptime(meeting_date_str, '%Y-%m-%d')
                    week_end = week_start + timedelta(days=6)
                    if week_start <= today <= week_end:
                        contains_current_studies = True
                        break
                
                if contains_current_studies:
                    logger.info(f"Found relevant studies in {w_candidate}")
                    w_epub = temp_epub
                    w_issue_selected = w_candidate
                    break
                else:
                    logger.debug(f"No relevant studies in {w_candidate}, trying next...")

        if 'weekend' not in meetings_data:
            meetings_data['weekend'] = {}
        if w_epub:
            logger.info(f"Parsing weekend meetings from {w_epub.name}...")
            w_content = self._parse_epub_content(w_epub)
            weekend_meetings = self._extract_weekend_meetings(w_content)
            meetings_data['weekend'][w_issue_selected] = weekend_meetings or {}
        elif w_issue_selected:
            meetings_data['weekend'][w_issue_selected] = {}

        # Save updated cache
        self._save_cached_meetings(meetings_data)
        logger.info(f"Cache file written: {self.CACHE_DIR / f'{self.language}_meetings_cache.json'}")

        return bool(mwb_epub or w_epub)
    
    def get_meeting_by_date_range(self, date_str: str, meeting_type: MeetingType) -> Optional[Meeting]:
        """Get meeting by checking if a date falls within any meeting week range"""
        meetings_data = self._load_cached_meetings()
        
        meeting_type_key = 'midweek' if meeting_type == MeetingType.MIDWEEK else 'weekend'
        type_data = meetings_data.get(meeting_type_key, {})
        
        # Print number of issues loaded for this meeting type
        logger.debug(f"Loaded {len(type_data)} issues for {meeting_type.name}")
        
        try:
            target_date = datetime.strptime(date_str, '%Y-%m-%d')
        except ValueError:
            return None
        
        # Find the meeting week that contains the target date
        for issue, issue_meetings in type_data.items():
            for meeting_date_str, meeting_parts_data in issue_meetings.items():
                meeting_date = datetime.strptime(meeting_date_str, '%Y-%m-%d')
                
                if meeting_type == MeetingType.MIDWEEK:
                    # For midweek meetings: cached date is Monday, week runs Monday to Sunday
                    week_start = meeting_date  # Monday
                    week_end = meeting_date + timedelta(days=6)  # Sunday
                else:
                    # For weekend meetings: cached date is the START of the week (same as midweek)
                    # _extract_heading_date() returns the start date of the range
                    # For example: heading "June 23-29" returns "2025-06-23" (the start)
                    week_start = meeting_date  # Start of week
                    week_end = meeting_date + timedelta(days=6)  # End of week (Sunday)
                
                logger.debug(f"Checking week from {week_start.date()} to {week_end.date()} against {target_date.date()}")
                
                if week_start <= target_date <= week_end:
                    logger.debug(f"Match found in issue {issue} for meeting on {meeting_date_str}")
                    return self._convert_to_meeting_object(meeting_parts_data, meeting_type, meeting_date_str)
        
        return None
    
    def _convert_to_meeting_object(self, parts_data: List[Dict], meeting_type: MeetingType, date_str: str) -> Meeting:
        """Convert cached meeting data to Meeting object with proper section grouping"""
        sections = []
        
        if meeting_type == MeetingType.MIDWEEK:
            # Group parts by section
            treasures_parts = []
            ministry_parts = []
            christian_parts = []
            
            for part_data in parts_data:
                part = MeetingPart(
                    title=part_data['title'],
                    duration_minutes=part_data['duration_minutes']
                )
                
                section = part_data.get('section', '')
                if section == 'treasures':
                    treasures_parts.append(part)
                elif section == 'ministry':
                    ministry_parts.append(part)
                elif section == 'christian_living':
                    christian_parts.append(part)
                else:
                    # Default placement based on content
                    if 'song' in part_data.get('type', '').lower():
                        treasures_parts.append(part)
                    else:
                        christian_parts.append(part)
            
            sections = [
                MeetingSection(title=self.trans['treasures'], parts=treasures_parts),
                MeetingSection(title=self.trans['ministry'], parts=ministry_parts),
                MeetingSection(title=self.trans['christian_living'], parts=christian_parts)
            ]
        
        else:  # Weekend meeting
            public_parts = []
            watchtower_parts = []
            
            for part_data in parts_data:
                part = MeetingPart(
                    title=part_data['title'],
                    duration_minutes=part_data['duration_minutes']
                )
                
                section = part_data.get('section', '')
                if section == 'public_talk':
                    public_parts.append(part)
                else:
                    watchtower_parts.append(part)
            
            sections = [
                MeetingSection(title=self.trans['public_talk'], parts=public_parts),
                MeetingSection(title=self.trans['watchtower_study'], parts=watchtower_parts)
            ]
        
        # Create meeting object
        meeting_date = datetime.strptime(date_str, '%Y-%m-%d')
        if self.language == "it":
            from PyQt6.QtCore import QLocale
            data = QLocale("it").toString(meeting_date.date(), "d MMMM yyyy")
            nome = ("Adunanza infrasettimanale" if meeting_type == MeetingType.MIDWEEK
                    else "Adunanza del fine settimana")
            title = f"{nome}: {data}"
        elif meeting_type == MeetingType.MIDWEEK:
            title = f"Midweek Meeting: {meeting_date.strftime('%B %d, %Y')}"
        else:
            title = f"Weekend Meeting: {meeting_date.strftime('%B %d, %Y')}"
        
        return Meeting(
            meeting_type=meeting_type,
            title=title,
            date=meeting_date,
            start_time=datetime.now().time(),
            sections=sections,
            language=self.language
        )
    
    def get_meeting_for_current_week(self, meeting_type: MeetingType) -> Optional[Meeting]:
        """Get meeting for current week using intelligent date matching"""
        today = datetime.now()
        logger.debug(f"Today's date: {today}")
        # Always use today's date for both meeting types
        target_date = today
        current_date_str = target_date.strftime('%Y-%m-%d')
        logger.debug(f"Attempting to find meeting for type: {meeting_type.name}")
        logger.debug(f"Looking for {meeting_type.name} meeting for date: {current_date_str}")
        meeting = self.get_meeting_by_date_range(current_date_str, meeting_type)
        if meeting:
            logger.info(f"Found {meeting_type.name} meeting: {meeting.title}")
        else:
            logger.warning(f"No {meeting_type.name} meeting found for current week.")
        return meeting
    
    def update_meetings(self) -> Dict[MeetingType, Meeting]:
        """Main method to get current week's meetings"""
        # Update cache if needed
        self.update_meetings_cache()
        
        meetings = {}
        
        # Get current week's meetings
        midweek_meeting = self.get_meeting_for_current_week(MeetingType.MIDWEEK)
        if midweek_meeting:
            meetings[MeetingType.MIDWEEK] = midweek_meeting
        
        # Get weekend meeting for current week  
        weekend_meeting = self.get_meeting_for_current_week(MeetingType.WEEKEND)
        if weekend_meeting:
            meetings[MeetingType.WEEKEND] = weekend_meeting
        
        return meetings
    
    def get_meeting_for_specific_date(self, date_str: str, meeting_type: MeetingType) -> Optional[Meeting]:
        """Get meeting for a specific date (e.g., '2025-06-24' should return '23-29 GIUGNO' meeting)"""
        return self.get_meeting_by_date_range(date_str, meeting_type)

    def _extract_heading_date(self, heading_text: str) -> Optional[str]:
        """
        Extract the date from a heading string. Handles full dates and date ranges.
        Returns the normalized date string (YYYY-MM-DD) for the *start* of the range.
        """
        europea = self._data_europea(heading_text)
        if europea:
            return europea
        import dateparser
        from datetime import datetime
        # Try to match a full date first, e.g. "September 15, 2025"
        full_date_match = re.search(r"(?P<month>\w+)\s+(?P<day>\d{1,2}),?\s+(?P<year>\d{4})", heading_text)
        if full_date_match:
            try:
                month = full_date_match.group("month")
                day = full_date_match.group("day")
                year = full_date_match.group("year")
                dt = dateparser.parse(f"{month} {day} {year}", languages=[self.language, 'en'])
                if dt:
                    return dt.strftime("%Y-%m-%d")
            except Exception:
                pass
        # Fallback: match date range, e.g. "September 15–21, 2025" or "September 15-21, 2025"
        range_match = re.search(
            r"(?P<start_month>\w+)\s(?P<start_day>\d{1,2})[\-–](?P<end_day>\d{1,2}),?\s(?P<year>\d{4})",
            heading_text
        )
        if range_match:
            try:
                start_month = range_match.group("start_month")
                start_day = range_match.group("start_day")
                year = range_match.group("year")
                dt = dateparser.parse(f"{start_month} {start_day} {year}", languages=[self.language, 'en'])
                if dt:
                    return dt.strftime("%Y-%m-%d")
            except Exception:
                pass
        # No match
        return None