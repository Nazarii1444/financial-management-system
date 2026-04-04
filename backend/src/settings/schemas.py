from typing import Optional, List
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from src.models import SubscriptionPlan


class ProfileUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: Optional[str] = Field(default=None, min_length=3, max_length=64)
    avatar_url: Optional[str] = Field(default=None, max_length=512)
    timezone: Optional[str] = Field(default=None, max_length=64)


class ProfileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id_: int
    username: str
    email: EmailStr
    avatar_url: Optional[str] = None
    timezone: Optional[str] = None
    default_currency: str
    twofa_enabled: bool
    subscription_plan: SubscriptionPlan


class CurrencySettingUpdate(BaseModel):
    default_currency: str = Field(min_length=3, max_length=3)


class CurrencySettingOut(BaseModel):
    default_currency: str


class EmailChangeRequest(BaseModel):
    new_email: EmailStr


class NotificationPreferencesUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email_enabled: Optional[bool] = None
    push_enabled: Optional[bool] = None
    budget_limit_alerts: Optional[bool] = None
    recurring_reminders: Optional[bool] = None
    goal_milestone_alerts: Optional[bool] = None
    monthly_summary: Optional[bool] = None


class NotificationPreferencesOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    email_enabled: bool
    push_enabled: bool
    budget_limit_alerts: bool
    recurring_reminders: bool
    goal_milestone_alerts: bool
    monthly_summary: bool


class SubscriptionFeature(BaseModel):
    label: str
    available: bool


class SubscriptionOut(BaseModel):
    plan: SubscriptionPlan
    features: List[SubscriptionFeature]


class SubscriptionUpgradeOut(BaseModel):
    plan: SubscriptionPlan
    message: str
