from typing import Optional, List
from pydantic import BaseModel, Field


class Settings(BaseModel):
    """Application settings model"""
    api_key: str = Field(..., description="Backboard.io API key")
    model: str = Field(default="gpt-4", description="LLM model to use")
    base_url: str = Field(default="https://app.backboard.io/api", description="Backboard.io API base URL")
    sync_enabled: bool = Field(default=True, description="Whether sync is enabled")
    assistant_id: Optional[str] = Field(default=None, description="Assistant ID for storing notes")
    app_assistant_ids: List[str] = Field(default_factory=list, description="List of assistant IDs created by this app")


class SettingsUpdate(BaseModel):
    """Model for updating settings"""
    api_key: Optional[str] = None
    model: Optional[str] = None
    base_url: Optional[str] = None
    sync_enabled: Optional[bool] = None
    assistant_id: Optional[str] = None
    app_assistant_ids: Optional[List[str]] = None