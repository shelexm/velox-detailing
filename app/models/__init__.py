"""Import every model so Base.metadata is complete for Alembic and tests."""

from app.models.booking import Booking, BookingEvent, Client, NotificationOutbox, Vehicle
from app.models.catalog import Resource, Service, ServiceCategory, ServiceGroup, ServiceStaff, Staff
from app.models.schedule import SpecialDay, StaffAbsence, StaffHours, StudioBreak, StudioHours, TimeBlock
from app.models.studio import Studio

__all__ = [
    "Booking",
    "BookingEvent",
    "Client",
    "NotificationOutbox",
    "Resource",
    "Service",
    "ServiceCategory",
    "ServiceGroup",
    "ServiceStaff",
    "SpecialDay",
    "Staff",
    "StaffAbsence",
    "StaffHours",
    "Studio",
    "StudioBreak",
    "StudioHours",
    "TimeBlock",
    "Vehicle",
]
