from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class CalendarFeedOut(BaseModel):
    active: bool
    url: Optional[str] = None          # https://…/api/calendar/feed/<token>.ics
    webcal_url: Optional[str] = None   # webcal://… — opens "Subscribe" on iPhone / macOS
    google_add_url: Optional[str] = None  # Google Calendar "add by URL" page
    qr_code_base64: Optional[str] = None  # PNG of webcal_url — scan with the iPhone camera
    lang: Optional[str] = None
    created_at: Optional[datetime] = None


class GoogleCalendarStatusOut(BaseModel):
    configured: bool                   # GOOGLE_CLIENT_ID / SECRET set on the server
    connected: bool
    calendar_id: Optional[str] = None
    calendar_url: Optional[str] = None
    last_synced_at: Optional[datetime] = None
    last_error: Optional[str] = None


class GoogleConnectOut(BaseModel):
    auth_url: str


class GoogleSyncOut(BaseModel):
    synced: int
    deleted: int
    last_synced_at: Optional[datetime] = None
