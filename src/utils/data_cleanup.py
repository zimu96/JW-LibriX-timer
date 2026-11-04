"""
Data cleanup utility for removing stale meeting files and cache data.
Runs on startup to prevent indefinite file accumulation.
"""
import logging
import time as time_module
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Set

from PyQt6.QtCore import QThread, pyqtSignal

logger = logging.getLogger("OnTime.DataCleanup")


@dataclass
class CleanupResult:
    """Result of a cleanup operation"""
    meetings_removed: int = 0
    epub_files_removed: int = 0
    cache_files_removed: int = 0
    total_bytes_freed: int = 0
    errors: List[str] = field(default_factory=list)

    @property
    def total_removed(self) -> int:
        return self.meetings_removed + self.epub_files_removed + self.cache_files_removed

    @property
    def has_removals(self) -> bool:
        return self.total_removed > 0

    def summary(self) -> str:
        """Human-readable summary for toast notification"""
        parts = []
        if self.meetings_removed:
            parts.append(f"{self.meetings_removed} meeting file(s)")
        if self.epub_files_removed:
            parts.append(f"{self.epub_files_removed} EPUB cache file(s)")
        if self.cache_files_removed:
            parts.append(f"{self.cache_files_removed} scraper cache file(s)")

        size_str = _format_bytes(self.total_bytes_freed)
        return f"Removed {', '.join(parts)} ({size_str} freed)"


class CleanupWorker(QThread):
    """Worker thread that performs file cleanup off the main thread."""

    finished = pyqtSignal(object)  # emits CleanupResult

    def __init__(
        self,
        meetings_dir: Path,
        cache_dir: Path,
        retention_days: int,
        active_meeting_files: Set[str],
        parent=None
    ):
        super().__init__(parent)
        self.meetings_dir = meetings_dir
        self.cache_dir = cache_dir
        self.retention_days = retention_days
        self.active_meeting_files = active_meeting_files

    def run(self):
        result = CleanupResult()
        cutoff = time_module.time() - (self.retention_days * 86400)

        # 1. Clean meeting JSON files
        self._clean_meetings(cutoff, result)

        # 2. Clean EPUB cache files
        self._clean_epub_cache(cutoff, result)

        # 3. Clean web scraper cache files (HTML + JSON)
        self._clean_scraper_cache(cutoff, result)

        if result.has_removals:
            logger.info("Cleanup complete: %s", result.summary())
        else:
            logger.debug("Cleanup: no stale files found (retention=%d days)", self.retention_days)

        self.finished.emit(result)

    def _clean_meetings(self, cutoff: float, result: CleanupResult):
        """Remove meeting JSON files older than cutoff, excluding active meetings."""
        if not self.meetings_dir.exists():
            return

        for f in self.meetings_dir.iterdir():
            if not f.is_file() or f.suffix != '.json':
                continue
            # Never delete settings.json
            if f.name == 'settings.json':
                continue
            # Skip currently loaded meeting files
            if f.name in self.active_meeting_files:
                continue
            try:
                if f.stat().st_mtime < cutoff:
                    size = f.stat().st_size
                    f.unlink()
                    result.meetings_removed += 1
                    result.total_bytes_freed += size
                    logger.debug("Removed stale meeting: %s", f.name)
            except OSError as e:
                result.errors.append(f"Meeting {f.name}: {e}")
                logger.warning("Failed to remove %s: %s", f, e)

    def _clean_epub_cache(self, cutoff: float, result: CleanupResult):
        """Remove EPUB files older than cutoff."""
        if not self.cache_dir.exists():
            return

        for f in self.cache_dir.iterdir():
            if not f.is_file() or f.suffix != '.epub':
                continue
            try:
                if f.stat().st_mtime < cutoff:
                    size = f.stat().st_size
                    f.unlink()
                    result.epub_files_removed += 1
                    result.total_bytes_freed += size
                    logger.debug("Removed stale EPUB: %s", f.name)
            except OSError as e:
                result.errors.append(f"EPUB {f.name}: {e}")
                logger.warning("Failed to remove %s: %s", f, e)

    def _clean_scraper_cache(self, cutoff: float, result: CleanupResult):
        """Remove web scraper cache files (HTML, JSON) older than cutoff."""
        if not self.cache_dir.exists():
            return

        scraper_extensions = {'.html', '.json'}

        for f in self.cache_dir.iterdir():
            if not f.is_file() or f.suffix not in scraper_extensions:
                continue
            try:
                if f.stat().st_mtime < cutoff:
                    size = f.stat().st_size
                    f.unlink()
                    result.cache_files_removed += 1
                    result.total_bytes_freed += size
                    logger.debug("Removed stale cache: %s", f.name)
            except OSError as e:
                result.errors.append(f"Cache {f.name}: {e}")
                logger.warning("Failed to remove %s: %s", f, e)


def _format_bytes(num_bytes: int) -> str:
    """Format byte count as human-readable string."""
    if num_bytes < 1024:
        return f"{num_bytes} B"
    elif num_bytes < 1024 * 1024:
        return f"{num_bytes / 1024:.1f} KB"
    else:
        return f"{num_bytes / (1024 * 1024):.1f} MB"
