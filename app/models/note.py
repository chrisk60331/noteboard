from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class Note(BaseModel):
    """Note model representing a note in Backboard.io"""
    id: str
    title: str
    content: str
    created_at: datetime
    updated_at: datetime

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class NoteCreate(BaseModel):
    """Model for creating a new note"""
    title: str = Field(..., min_length=1)
    content: str = ""


class NoteUpdate(BaseModel):
    """Model for updating an existing note"""
    title: Optional[str] = Field(None, min_length=1)
    content: Optional[str] = None
