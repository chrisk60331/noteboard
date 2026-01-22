import subprocess
import platform
from datetime import datetime
from typing import List, Optional
from app.models.note import Note
from app.services.cache import NotesCache

class AppleNotesReader:
    """Service to read Apple Notes from macOS using AppleScript"""
    
    def __init__(self, use_cache: bool = True):
        if platform.system() != "Darwin":
            raise RuntimeError("Apple Notes reader only works on macOS")
        self.use_cache = use_cache
        self.cache = NotesCache() if use_cache else None
    
    def _run_applescript(self, script: str) -> str:
        """Execute AppleScript and return output"""
        try:
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                text=True,
                check=True
            )
            return result.stdout.strip()
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"AppleScript execution failed: {e.stderr}")
    
    def get_all_notes(self) -> List[Note]:
        """Retrieve all notes from Apple Notes"""
        
        
        try:
            # Use a record separator to handle multi-line content
            script_lines = """
            tell application "Notes"
                set output to ""
                set recordSep to "___NOTE_RECORD_SEP___"
                repeat with aNote in notes
                    try
                        set noteId to id of aNote as string
                        set noteTitle to name of aNote
                        set noteContent to body of aNote
                        set noteDate to creation date of aNote
                        set noteModDate to modification date of aNote
                        
                        set output to output & noteId & "|||" & noteTitle & "|||" & noteContent & "|||" & (noteDate as string) & "|||" & (noteModDate as string) & recordSep
                    end try
                end repeat
                return output
            end tell
            """
            
            result = self._run_applescript(script_lines)
            
            
            if not result:
                
                return []
            
            notes = []
            # Split by record separator instead of newline
            record_sep = "___NOTE_RECORD_SEP___"
            note_records = result.split(record_sep)
            
            
            for record in note_records:
                if not record.strip():
                    continue
                
                # Split by field separator - format: noteId|||title|||content|||date1|||date2
                # Content may contain |||, so we need to handle that
                parts = record.split("|||")
                
                if len(parts) >= 5:
                    note_id = parts[0].strip()
                    title = parts[1].strip() or "Untitled"
                    # Content is everything between title and date1 (may contain |||)
                    content = "|||".join(parts[2:-2]).strip()
                    date1 = parts[-2].strip()
                    date2 = parts[-1].strip()
                    
                    # Parse dates (AppleScript date format)
                    try:
                        created_at = self._parse_applescript_date(date1)
                        updated_at = self._parse_applescript_date(date2)
                    except:
                        # Fallback to current time if parsing fails
                        created_at = datetime.now()
                        updated_at = datetime.now()
                    
                    notes.append(Note(
                        id=note_id,
                        title=title,
                        content=content,
                        created_at=created_at,
                        updated_at=updated_at
                    ))
                # Skip records with invalid format
            
            return notes
            
        except Exception as e:
            raise RuntimeError(f"Failed to read Apple Notes: {str(e)}")
    
    def _parse_applescript_date(self, date_str: str) -> datetime:
        """Parse AppleScript date string to Python datetime"""
        # AppleScript dates are in format like "Monday, January 1, 2024 at 12:00:00 PM"
        # Try to parse common formats
        try:
            # Try ISO format first
            return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        except:
            pass
        
        # Try common date formats
        formats = [
            "%A, %B %d, %Y at %I:%M:%S %p",
            "%B %d, %Y at %I:%M:%S %p",
            "%Y-%m-%d %H:%M:%S",
        ]
        
        for fmt in formats:
            try:
                return datetime.strptime(date_str, fmt)
            except:
                continue
        
        # Fallback to current time
        return datetime.now()
    
    def get_note_count(self) -> int:
        """Get the total number of notes"""
        try:
            script = """
            tell application "Notes"
                return count of notes
            end tell
            """
            result = self._run_applescript(script)
            return int(result) if result.isdigit() else 0
        except:
            return 0
    
    def get_last_modification_time(self) -> Optional[datetime]:
        """Get the last modification time of any note (for cache invalidation)"""
        try:
            script = """
            tell application "Notes"
                set maxDate to date "January 1, 1900"
                repeat with aNote in notes
                    try
                        set modDate to modification date of aNote
                        if modDate > maxDate then
                            set maxDate to modDate
                        end if
                    end try
                end repeat
                return maxDate as string
            end tell
            """
            result = self._run_applescript(script)
            if result:
                return self._parse_applescript_date(result)
            return None
        except:
            return None
    
    def get_all_notes_cached(self, force_refresh: bool = False) -> List[Note]:
        """Retrieve all notes from Apple Notes with caching support"""
        
        
        # Check cache first if enabled and not forcing refresh
        if self.use_cache and self.cache and not force_refresh:
            # Use fast cache validation that doesn't require AppleScript calls
            cached_notes = self.cache.get_cached_notes_fast()
            if cached_notes is not None:
                
                return cached_notes
            
            # Fast cache validation failed, check if cache is still valid by comparing with current state
            # This requires AppleScript calls, but only happens if fast validation fails
            note_count = self.get_note_count()
            last_modification = self.get_last_modification_time()
            
            
            cached_notes = self.cache.get_cached_notes(note_count, last_modification)
            if cached_notes is not None:
                
                return cached_notes
        
        
        
        # If cache miss or cache disabled, fetch from Apple Notes
        notes = self.get_all_notes()
        
        # Cache the results if caching is enabled
        if self.use_cache and self.cache:
            note_count = len(notes)
            last_modification = self.get_last_modification_time()
            
            self.cache.cache_notes(notes, note_count, last_modification)
        
        return notes