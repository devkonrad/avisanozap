from datetime import datetime, time
from ninja import Schema
from uuid import UUID
from decimal import Decimal

class ProfessionalProfileSchema(Schema):
    id: UUID
    slug: str
    whatsapp_number: str
    whatsapp_session_status: str

class ServiceSchema(Schema):
    id: UUID
    name: str
    duration_minutes: int
    price: Decimal
    is_active: bool

class ServiceCreateSchema(Schema):
    name: str
    duration_minutes: int = 30
    price: Decimal = 0.00

class AppointmentCreateSchema(Schema):
    professional_id: UUID
    service_id: UUID
    client_name: str
    client_whatsapp: str
    start_datetime: datetime

class AppointmentSchema(Schema):
    id: UUID
    client_name: str
    client_whatsapp: str
    start_datetime: datetime
    end_datetime: datetime
    status: str
    created_at: datetime
