import json
import hashlib
from pathlib import Path
from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel
from app.models.note import Note
from app.config import BASE_DIR


class CacheMetadata(BaseModel):
    """Metadata for cached notes"""
    note_count: int
    cache_key: str
    cached_at: datetime
    notes_hash: str
    last_modification: Optional[datetime] = None
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class NotesCache:
    """Service to cache processed Apple Notes"""
    
    def __init__(self, cache_file: Optional[Path] = None):
        if cache_file is None:
            cache_file = BASE_DIR / ".cache" / "notes_cache.json"
        self.cache_file = cache_file
        self.cache_file.parent.mkdir(parents=True, exist_ok=True)
    
    def _generate_cache_key(self, note_count: int, last_modification: Optional[datetime] = None) -> str:
        """Generate a cache key based on note count and last modification time"""
        # Ensure consistent datetime serialization - use ISO format with microseconds stripped for consistency
        if last_modification:
            # Round to seconds to avoid microsecond precision issues
            mod_time_str = last_modification.replace(microsecond=0).isoformat()
        else:
            mod_time_str = 'none'
        key_data = f"{note_count}_{mod_time_str}"
        return hashlib.md5(key_data.encode()).hexdigest()
    
    def _hash_notes(self, notes: List[Note]) -> str:
        """Generate a hash of notes content for validation"""
        # Create a stable representation of notes
        notes_data = [
            {
                "id": note.id,
                "title": note.title,
                "updated_at": note.updated_at.isoformat()
            }
            for note in sorted(notes, key=lambda n: n.id)
        ]
        notes_json = json.dumps(notes_data, sort_keys=True)
        return hashlib.md5(notes_json.encode()).hexdigest()
    
    def get_cached_notes_fast(self) -> Optional[List[Note]]:
        """Get cached notes without requiring AppleScript calls - validates using cached metadata"""
        if not self.cache_file.exists():
            return None
        
        try:
            with open(self.cache_file, "r") as f:
                cache_data = json.load(f)
            
            metadata_dict = cache_data.get("metadata", {})
            # Parse datetime strings back to datetime objects
            if "cached_at" in metadata_dict and isinstance(metadata_dict["cached_at"], str):
                metadata_dict["cached_at"] = datetime.fromisoformat(metadata_dict["cached_at"])
            if "last_modification" in metadata_dict and isinstance(metadata_dict["last_modification"], str):
                metadata_dict["last_modification"] = datetime.fromisoformat(metadata_dict["last_modification"])
            
            metadata = CacheMetadata(**metadata_dict)
            cached_notes = cache_data.get("notes", [])
            
            # Validate notes hash (this validates the actual notes content)
            notes = []
            for note_data in cached_notes:
                # Parse datetime strings back to datetime objects
                if "created_at" in note_data and isinstance(note_data["created_at"], str):
                    note_data["created_at"] = datetime.fromisoformat(note_data["created_at"])
                if "updated_at" in note_data and isinstance(note_data["updated_at"], str):
                    note_data["updated_at"] = datetime.fromisoformat(note_data["updated_at"])
                notes.append(Note(**note_data))
            
            current_hash = self._hash_notes(notes)
            if metadata.notes_hash != current_hash:
                return None
            
            # Cache is valid - return notes
            return notes
        except Exception as e:
            # If cache is corrupted, return None
            return None
    
    def get_cached_notes(self, note_count: int, last_modification: Optional[datetime] = None) -> Optional[List[Note]]:
        """Get cached notes if cache is valid (validates against current note_count and last_modification)"""
        # First try fast validation
        cached_notes = self.get_cached_notes_fast()
        if cached_notes is None:
            return None
        
        # If fast validation passed, validate against current note_count and last_modification
        # Normalize last_modification datetime to seconds precision for consistent key generation
        normalized_mod = last_modification.replace(microsecond=0) if last_modification else None
        expected_key = self._generate_cache_key(note_count, normalized_mod)
        
        # Load metadata to check cache key (reuse from fast validation if possible, but reload for safety)
        try:
            with open(self.cache_file, "r") as f:
                cache_data = json.load(f)
            metadata_dict = cache_data.get("metadata", {})
            if "last_modification" in metadata_dict and isinstance(metadata_dict["last_modification"], str):
                metadata_dict["last_modification"] = datetime.fromisoformat(metadata_dict["last_modification"])
            metadata = CacheMetadata(**metadata_dict)
            
            if metadata.cache_key != expected_key:
                return None
            
            return cached_notes
        except Exception:
            return None
    
    def cache_notes(self, notes: List[Note], note_count: int, last_modification: Optional[datetime] = None) -> None:
        """Cache processed notes"""
        try:
            # Normalize last_modification datetime to seconds precision for consistent key generation
            normalized_mod = last_modification.replace(microsecond=0) if last_modification else None
            cache_key = self._generate_cache_key(note_count, normalized_mod)
            notes_hash = self._hash_notes(notes)
            
            metadata = CacheMetadata(
                note_count=note_count,
                cache_key=cache_key,
                cached_at=datetime.now().replace(microsecond=0),
                notes_hash=notes_hash,
                last_modification=normalized_mod
            )
            
            cache_data = {
                "metadata": metadata.model_dump(mode="json"),
                "notes": [note.model_dump(mode="json") for note in notes]
            }
            
            with open(self.cache_file, "w") as f:
                json.dump(cache_data, f, indent=2)
        except Exception:
            # Silently fail if caching fails
            pass
    
    def invalidate_cache(self) -> None:
        """Invalidate the cache by deleting the cache file"""
        if self.cache_file.exists():
            self.cache_file.unlink()
    
    def is_cache_valid(self, note_count: int, last_modification: Optional[datetime] = None) -> bool:
        """Check if cache exists and is valid"""
        return self.get_cached_notes(note_count, last_modification) is not None
