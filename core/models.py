"""Data models for DispatchMind using Pydantic v2."""

import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field, field_validator, model_validator


class Order(BaseModel):
    """Delivery order model with Indian validation standards."""

    id: str = Field(..., description="Unique order identifier")
    customer_name: str = Field(..., description="Name of the customer or recipient")
    phone: str = Field(..., description="10-digit Indian mobile number")
    address: str = Field(..., description="Delivery street address")
    pincode: str = Field(..., description="6-digit Indian postal code")
    lat: Optional[float] = Field(None, description="Latitude coordinates")
    lng: Optional[float] = Field(None, description="Longitude coordinates")
    weight_kg: float = Field(..., gt=0, description="Package weight in kilograms")
    window_start: str = Field("09:00", description="Delivery window start time (HH:MM or ISO)")
    window_end: str = Field("18:00", description="Delivery window end time (HH:MM or ISO)")
    status: str = Field("pending", description="Status: pending, assigned, in_transit, delivered, failed")
    assigned_vehicle: Optional[str] = Field(None, description="Assigned vehicle identifier")
    eway_bill_no: Optional[str] = Field(None, description="12-digit Indian e-Way bill number")
    gstin: Optional[str] = Field(None, description="15-character GST identification number")
    confidence_score: Optional[float] = Field(1.0, description="Overall extraction confidence score (0.0 to 1.0)")
    field_confidences: Optional[Dict[str, float]] = Field(default_factory=dict, description="Confidence per field")
    created_at: Optional[str] = None
    delivered_at: Optional[str] = None
    pod_id: Optional[str] = None

    @field_validator("pincode")
    @classmethod
    def validate_pincode(cls, v: str) -> str:
        cleaned = re.sub(r"\s+", "", str(v).strip())
        if not re.match(r"^\d{6}$", cleaned):
            raise ValueError(f"Invalid Indian pincode: {v}. Must be exactly 6 digits.")
        return cleaned

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        cleaned = re.sub(r"[\s\-\+\(\)]", "", str(v).strip())
        if cleaned.startswith("91") and len(cleaned) == 12:
            cleaned = cleaned[2:]
        elif cleaned.startswith("0") and len(cleaned) == 11:
            cleaned = cleaned[1:]
        if not re.match(r"^[6-9]\d{9}$", cleaned):
            raise ValueError(f"Invalid Indian phone number: {v}. Must be 10 digits starting with 6-9.")
        return cleaned

    @field_validator("weight_kg")
    @classmethod
    def validate_weight(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("Weight must be greater than 0 kg.")
        return round(float(v), 2)


class MissingFields(BaseModel):
    """Report gaps in order intake with clarification questions."""

    order_id: Optional[str] = Field(None, description="Order ID if known or extracted")
    missing_fields: List[str] = Field(default_factory=list, description="Names of missing required fields")
    questions: List[str] = Field(default_factory=list, description="Exactly one precise question per gap")
    field_confidences: Optional[Dict[str, float]] = Field(default_factory=dict, description="Confidence scores")
    extracted_fields: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Partially extracted fields")
    raw_input: Optional[str] = None


class Vehicle(BaseModel):
    """Fleet vehicle model."""

    id: str = Field(..., description="Vehicle ID e.g. TN09AB1234")
    model: str = Field("Tata Ace", description="Vehicle model or make")
    driver_id: Optional[str] = Field(None, description="Assigned driver ID")
    capacity_kg: float = Field(..., gt=0, description="Maximum load capacity in kg")
    current_lat: float = Field(13.0067, description="Current latitude")
    current_lng: float = Field(80.2025, description="Current longitude")
    status: str = Field("idle", description="Status: available, busy, maintenance, idle, breakdown")
    speed_kmh: float = Field(30.0, description="Average transit speed in km/h for ETA calculations")


class Driver(BaseModel):
    """Fleet driver model."""

    id: str = Field(..., description="Driver ID")
    name: str = Field(..., description="Driver full name")
    phone: str = Field(..., description="Driver phone number")
    current_vehicle_id: Optional[str] = Field(None, description="Assigned vehicle ID")
    vehicle_id: Optional[str] = Field(None, description="Assigned vehicle ID alias")
    status: str = Field("available", description="Status: available, on_route, off_duty")
    preferred_language: str = Field("en", description="Preferred language code: en, ta, hi")

    @model_validator(mode="after")
    def sync_vehicle_ids(self) -> "Driver":
        if self.current_vehicle_id and not self.vehicle_id:
            self.vehicle_id = self.current_vehicle_id
        elif self.vehicle_id and not self.current_vehicle_id:
            self.current_vehicle_id = self.vehicle_id
        return self


class Stop(BaseModel):
    """Individual delivery stop in a planned route."""

    stop_number: int = Field(..., description="Stop sequence number")
    order_id: str = Field(..., description="Associated order ID")
    customer_name: Optional[str] = Field(None, description="Customer name")
    address: Optional[str] = Field(None, description="Delivery address")
    pincode: Optional[str] = Field(None, description="Pincode")
    lat: float = Field(..., description="Latitude")
    lng: float = Field(..., description="Longitude")
    weight_kg: float = Field(..., description="Weight to deliver")
    eta: str = Field(..., description="Estimated arrival time")
    planned_eta: Optional[str] = Field(None, description="Original planned arrival time")
    window_start: str = Field("09:00", description="Customer window start")
    window_end: str = Field("18:00", description="Customer window end")
    status: str = Field("pending", description="Stop status: pending, planned, in_transit, completed, delayed")


class VehicleRoute(BaseModel):
    """Ordered sequence of stops for a single vehicle."""

    vehicle_id: str = Field(..., description="Vehicle ID")
    driver_id: Optional[str] = Field(None, description="Driver ID")
    stops: List[Stop] = Field(default_factory=list, description="Ordered sequence of delivery stops")
    total_km: float = Field(0.0, description="Total planned route distance in kilometers")
    total_weight_kg: float = Field(0.0, description="Total load weight assigned to this vehicle")
    start_time: str = Field("09:00", description="Route start time")
    end_time: str = Field("18:00", description="Route end time")


class UnassignedOrder(BaseModel):
    """Order unassigned during route planning with justification."""

    order_id: str = Field(..., description="Unassigned order ID")
    reason: str = Field(..., description="Reason why order could not be assigned")

    def __getitem__(self, item: str):
        return getattr(self, item)


class RoutePlan(BaseModel):
    """Master route plan across the fleet."""

    plan_id: str = Field(..., description="Unique route plan identifier")
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    routes: List[VehicleRoute] = Field(default_factory=list, description="List of routes by vehicle")
    unassigned_orders: List[Union[UnassignedOrder, Dict[str, Any]]] = Field(
        default_factory=list,
        description="Orders that could not be assigned",
    )
    total_km: float = Field(0.0, description="Total kilometers across routes")
    total_distance_km: float = Field(0.0, description="Total distance in km alias")
    explanation: Optional[str] = Field(None, description="Explanatory text for the plan")

    @model_validator(mode="after")
    def sync_total_distance(self) -> "RoutePlan":
        if self.total_km and not self.total_distance_km:
            self.total_distance_km = self.total_km
        elif self.total_distance_km and not self.total_km:
            self.total_km = self.total_distance_km
        return self


class Alert(BaseModel):
    """Real-time monitoring alert."""

    alert_id: str = Field(..., description="Unique alert ID")
    vehicle_id: Optional[str] = Field(None, description="Vehicle ID involved")
    order_id: Optional[str] = Field(None, description="Order ID involved")
    alert_type: str = Field(..., description="Type: eta_drift, delay, idle, rain_risk, breakdown")
    message: str = Field(..., description="Alert description")
    severity: str = Field("medium", description="Severity: low, medium, high, critical")
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    drift_minutes: Optional[int] = None
    weather_condition: Optional[str] = None
    idle_minutes: Optional[int] = None
    resolved: bool = False


class RecoveryAction(BaseModel):
    """Recovery action proposal or execution record."""

    action_id: str = Field(..., description="Unique action ID")
    alert_id: str = Field(..., description="Associated alert ID")
    action_type: str = Field(..., description="Action type: resequence, reassign, reschedule")
    description: Optional[str] = Field(None, description="Description of recovery action")
    proposal: Optional[str] = Field(None, description="Proposal summary for dispatcher")
    affected_vehicle_id: Optional[str] = None
    target_vehicle_id: Optional[str] = None
    order_ids: List[str] = Field(default_factory=list)
    delay_impact_min: int = 0
    auto_applied: bool = Field(False, description="Whether action was automatically applied")
    status: str = Field("pending", description="Status: pending, proposed, approved, applied, rejected")
    result_status: Optional[str] = None
    timestamp: Optional[str] = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @model_validator(mode="after")
    def sync_proposals(self) -> "RecoveryAction":
        if self.description and not self.proposal:
            self.proposal = self.description
        elif self.proposal and not self.description:
            self.description = self.proposal
        if not self.result_status:
            self.result_status = self.status
        return self


class PODResult(BaseModel):
    """Proof of Delivery verification result."""

    pod_id: Optional[str] = None
    order_id: str = Field(..., description="Delivered order ID")
    photo_url: Optional[str] = None
    verified: bool = Field(False, description="Whether photo verification passed")
    is_verified: bool = Field(False, description="Verification status alias")
    recipient_name: Optional[str] = Field(None, description="Recipient name")
    confidence: float = Field(0.0, description="Verification confidence score")
    confidence_score: Optional[float] = None
    notes: Optional[str] = None
    needs_human: bool = False
    timestamp: Optional[str] = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    gps_lat: Optional[float] = None
    gps_lng: Optional[float] = None

    @model_validator(mode="after")
    def sync_pod_fields(self) -> "PODResult":
        if self.confidence and self.confidence_score is None:
            self.confidence_score = self.confidence
        elif self.confidence_score is not None and not self.confidence:
            self.confidence = self.confidence_score
        if self.verified and not self.is_verified:
            self.is_verified = self.verified
        elif self.is_verified and not self.verified:
            self.verified = self.is_verified
        return self


class TuningUpdate(BaseModel):
    """Feedback tuning parameters for ETA adjustments."""

    tuning_id: Optional[str] = None
    pincode: str = Field(..., description="6-digit Indian postal code")
    eta_buffer_min: int = Field(..., description="Buffer minutes to add to ETA")
    hour_band: Optional[str] = Field(None, description="Optional hour band e.g. 09-12")
    predicted_error_min: Optional[float] = None
    failure_reasons: List[str] = Field(default_factory=list)
    suggested_prompt_diff: Optional[str] = None
    reason: Optional[str] = None
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class Degraded(BaseModel):
    """Degraded response returned when resilience fallback is triggered."""

    is_degraded: bool = True
    reason: str
    error: Optional[str] = None
    fallback_result: Any = None
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class Event(BaseModel):
    """Event log record for audit, resilience, and feedback."""

    event_id: str = Field(..., description="Unique event identifier")
    event_type: str = Field(..., description="Event type identifier")
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    source: str = Field(..., description="Source component or function")
    details: Dict[str, Any] = Field(default_factory=dict)
