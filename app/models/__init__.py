"""Import every model so Base.metadata is complete for Alembic and tests."""

from app.models.auth import StudioMembership, User, UserSession
from app.models.booking import Booking, BookingEvent, Client, NotificationOutbox, Vehicle
from app.models.catalog import Resource, Service, ServiceCategory, ServiceGroup, ServiceStaff, Staff
from app.models.content import GiftOption, MediaAsset, PortfolioCase, Review, SiteSection
from app.models.schedule import SpecialDay, StaffAbsence, StaffHours, StudioBreak, StudioHours, TimeBlock
from app.models.studio import Studio

__all__ = [
    "Booking",
    "BookingEvent",
    "Client",
    "GiftOption",
    "MediaAsset",
    "NotificationOutbox",
    "PortfolioCase",
    "Resource",
    "Review",
    "Service",
    "ServiceCategory",
    "ServiceGroup",
    "ServiceStaff",
    "SiteSection",
    "SpecialDay",
    "Staff",
    "StaffAbsence",
    "StaffHours",
    "Studio",
    "StudioBreak",
    "StudioHours",
    "StudioMembership",
    "TimeBlock",
    "User",
    "UserSession",
    "Vehicle",
]
