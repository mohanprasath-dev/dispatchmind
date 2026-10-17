"""Feedback and continuous learning module for ETA variance and postal buffer tuning."""

import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Union
from core.models import Event


def parse_time_to_minutes(time_val: Any) -> Optional[int]:
    """Convert time representations (HH:MM, ISO datetime string, or number) to minutes from midnight."""
    if time_val is None:
        return None
    if isinstance(time_val, (int, float)):
        return int(time_val)

    s = str(time_val).strip()
    if not s:
        return None

    # Check for HH:MM format
    m = re.search(r"(\d{1,2}):(\d{2})", s)
    if m:
        h, mins = int(m.group(1)), int(m.group(2))
        return h * 60 + mins

    # Check for ISO format
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return dt.hour * 60 + dt.minute
    except Exception:
        pass

    return None


def get_hour_band(time_val: Any) -> str:
    """Return hour band string e.g. '09-12', '12-15', '15-18' based on time."""
    minutes = parse_time_to_minutes(time_val)
    if minutes is None:
        return "09-12"

    hour = (minutes // 60) % 24
    if hour < 9:
        return "06-09"
    elif hour < 12:
        return "09-12"
    elif hour < 15:
        return "12-15"
    elif hour < 18:
        return "15-18"
    else:
        return "18-21"


def get_default_historical_events() -> List[Dict[str, Any]]:
    """
    Generate realistic historical delivery completion events across Chennai.
    Pincodes include 600017 (T. Nagar), 600058 (Ambattur), and 600042 (Velachery).
    Baseline error averages ~24.8m; applying tuned buffers reduces residual error to ~6.2m (~75% reduction).
    """
    events: List[Dict[str, Any]] = []

    # 1. T. Nagar (600017): commercial hub, heavy traffic congestion, narrow roads
    t_nagar_diffs = [19, 29, 33, 22, 37, 31, 30, 22, 35, 20, 37, 37, 38, 34, 27, 19]
    t_nagar_records = []
    for i, diff in enumerate(t_nagar_diffs):
        oid = f"ORD-H1{i+1:02d}"
        planned_h = 9 + (i // 4)
        planned_m = (i % 4) * 15
        planned = f"{planned_h:02d}:{planned_m:02d}"
        act_total = planned_h * 60 + planned_m + diff
        act_h = (act_total // 60) % 24
        act_m = act_total % 60
        actual = f"{act_h:02d}:{act_m:02d}"
        band = "09-12" if planned_h < 12 else ("12-15" if planned_h < 15 else "15-18")
        reasons = ["traffic congestion", "narrow roads"] if i % 2 == 0 else ["commercial market gridlock"]
        t_nagar_records.append((oid, planned, actual, diff, band, reasons))

    for oid, planned, actual, diff, band, reasons in t_nagar_records:
        events.append({
            "event_id": f"evt_{oid.lower()}",
            "event_type": "delivery_completed",
            "source": "pod",
            "timestamp": f"2026-10-15T{actual}:00Z",
            "details": {
                "order_id": oid,
                "pincode": "600017",
                "planned_eta": planned,
                "actual_arrival": actual,
                "variance_min": diff,
                "hour_band": band,
                "failure_reasons": reasons,
            },
        })

    # 2. Ambattur (600058): industrial freight corridor, railway crossing, container delays
    ambattur_diffs = [15, 24, 22, 29, 18, 30, 16, 19, 16, 34, 18, 31, 30, 17, 15, 32]
    ambattur_records = []
    for i, diff in enumerate(ambattur_diffs):
        oid = f"ORD-H2{i+1:02d}"
        planned_h = 10 + (i // 4)
        planned_m = (i % 4) * 15
        planned = f"{planned_h:02d}:{planned_m:02d}"
        act_total = planned_h * 60 + planned_m + diff
        act_h = (act_total // 60) % 24
        act_m = act_total % 60
        actual = f"{act_h:02d}:{act_m:02d}"
        band = "09-12" if planned_h < 12 else ("12-15" if planned_h < 15 else "15-18")
        reasons = ["freight vehicle congestion"] if i % 2 == 0 else ["railway crossing delay", "narrow roads"]
        ambattur_records.append((oid, planned, actual, diff, band, reasons))

    for oid, planned, actual, diff, band, reasons in ambattur_records:
        events.append({
            "event_id": f"evt_{oid.lower()}",
            "event_type": "delivery_completed",
            "source": "pod",
            "timestamp": f"2026-10-15T{actual}:00Z",
            "details": {
                "order_id": oid,
                "pincode": "600058",
                "planned_eta": planned,
                "actual_arrival": actual,
                "variance_min": diff,
                "hour_band": band,
                "failure_reasons": reasons,
            },
        })

    # 3. Velachery (600042): waterlogging and metro construction bottlenecks
    velachery_diffs = [30, 19, 30, 28, 26, 32, 17, 15, 27, 12, 32, 20, 15, 16, 24, 13]
    velachery_records = []
    for i, diff in enumerate(velachery_diffs):
        oid = f"ORD-H3{i+1:02d}"
        planned_h = 10 + (i // 4)
        planned_m = (i % 4) * 15
        planned = f"{planned_h:02d}:{planned_m:02d}"
        act_total = planned_h * 60 + planned_m + diff
        act_h = (act_total // 60) % 24
        act_m = act_total % 60
        actual = f"{act_h:02d}:{act_m:02d}"
        band = "09-12" if planned_h < 12 else ("12-15" if planned_h < 15 else "15-18")
        reasons = ["waterlogging"] if i % 2 == 0 else ["metro construction bottleneck"]
        velachery_records.append((oid, planned, actual, diff, band, reasons))

    for oid, planned, actual, diff, band, reasons in velachery_records:
        events.append({
            "event_id": f"evt_{oid.lower()}",
            "event_type": "delivery_completed",
            "source": "pod",
            "timestamp": f"2026-10-15T{actual}:00Z",
            "details": {
                "order_id": oid,
                "pincode": "600042",
                "planned_eta": planned,
                "actual_arrival": actual,
                "variance_min": diff,
                "hour_band": band,
                "failure_reasons": reasons,
            },
        })

    return events


def _extract_event_info(event: Union[Dict[str, Any], Event]) -> Optional[Dict[str, Any]]:
    """Extract standard fields (pincode, error_min, hour_band, failure_reasons) from an event."""
    if isinstance(event, Event):
        details = event.details or {}
        event_type = event.event_type
        timestamp = event.timestamp
    elif isinstance(event, dict):
        details = event.get("details", {})
        event_type = event.get("event_type", "")
        timestamp = event.get("timestamp", "")
    else:
        return None

    # Filter for delivery or variance-relevant events
    pincode = details.get("pincode") or details.get("postal_code")
    if not pincode and isinstance(event, dict):
        pincode = event.get("pincode")
    if not pincode:
        return None
    pincode = str(pincode).strip()

    # Calculate error in minutes
    error_min: Optional[float] = None
    if "variance_min" in details:
        try:
            error_min = float(details["variance_min"])
        except (ValueError, TypeError):
            pass
    elif "delay_minutes" in details:
        try:
            error_min = float(details["delay_minutes"])
        except (ValueError, TypeError):
            pass
    elif "error_min" in details:
        try:
            error_min = float(details["error_min"])
        except (ValueError, TypeError):
            pass

    planned_eta = details.get("planned_eta") or details.get("predicted_eta") or details.get("eta")
    actual_arrival = details.get("actual_arrival") or details.get("actual_time") or details.get("delivered_at")

    if error_min is None and planned_eta and actual_arrival:
        plan_m = parse_time_to_minutes(planned_eta)
        act_m = parse_time_to_minutes(actual_arrival)
        if plan_m is not None and act_m is not None:
            error_min = float(act_m - plan_m)

    if error_min is None:
        return None

    # Hour band
    band = details.get("hour_band")
    if not band:
        time_ref = planned_eta or actual_arrival or timestamp
        band = get_hour_band(time_ref)

    # Failure reasons
    reasons = details.get("failure_reasons", [])
    if isinstance(reasons, str):
        reasons = [reasons]
    elif not isinstance(reasons, list):
        reasons = []

    single_reason = details.get("failure_reason") or details.get("reason")
    if single_reason and single_reason not in reasons:
        reasons.append(single_reason)

    return {
        "pincode": pincode,
        "error_min": error_min,
        "hour_band": band,
        "failure_reasons": reasons,
        "planned_eta": planned_eta,
        "actual_arrival": actual_arrival,
    }


def compute_eta_variance(historical_events: List[Any]) -> Dict[str, Any]:
    """
    Compares predicted ETA vs actual arrival times from completed delivery events.
    Aggregates mean error in minutes grouped by pincode and hour band (e.g. 09-12, 12-15, 15-18).
    Calculates recommended buffer adjustments: eta_buffer_min per pincode.
    """
    if not historical_events:
        return {
            "pincode_buffers": {},
            "by_pincode": {},
            "by_hour_band": {},
            "overall_mean_error_min": 0.0,
            "total_events": 0,
        }

    pincode_data: Dict[str, Dict[str, Any]] = {}
    hour_band_data: Dict[str, List[float]] = {}
    all_errors: List[float] = []

    for evt in historical_events:
        extracted = _extract_event_info(evt)
        if not extracted:
            continue

        pincode = extracted["pincode"]
        err = extracted["error_min"]
        band = extracted["hour_band"]
        reasons = extracted["failure_reasons"]

        all_errors.append(err)

        if pincode not in pincode_data:
            pincode_data[pincode] = {
                "errors": [],
                "hour_bands": {},
                "failure_reasons": {},
            }

        pincode_data[pincode]["errors"].append(err)

        # Hour bands per pincode
        if band not in pincode_data[pincode]["hour_bands"]:
            pincode_data[pincode]["hour_bands"][band] = []
        pincode_data[pincode]["hour_bands"][band].append(err)

        # Global hour bands
        if band not in hour_band_data:
            hour_band_data[band] = []
        hour_band_data[band].append(err)

        # Failure reasons count
        for r in reasons:
            r_str = str(r).strip().lower()
            if r_str:
                pincode_data[pincode]["failure_reasons"][r_str] = (
                    pincode_data[pincode]["failure_reasons"].get(r_str, 0) + 1
                )

    # Process by pincode summary
    by_pincode: Dict[str, Dict[str, Any]] = {}
    pincode_buffers: Dict[str, int] = {}

    for pin, data in pincode_data.items():
        errs = data["errors"]
        mean_err = sum(errs) / len(errs) if errs else 0.0
        # Buffer recommendation: round positive mean error to integer minutes
        recommended_buffer = max(0, int(round(mean_err)))

        # Sort failure reasons by frequency
        sorted_reasons = sorted(
            data["failure_reasons"].keys(),
            key=lambda k: data["failure_reasons"][k],
            reverse=True,
        )

        # Hour band breakdown
        hb_summary: Dict[str, Dict[str, Any]] = {}
        for b, b_errs in data["hour_bands"].items():
            hb_summary[b] = {
                "mean_error_min": round(sum(b_errs) / len(b_errs), 2) if b_errs else 0.0,
                "sample_count": len(b_errs),
            }

        pin_summary = {
            "pincode": pin,
            "mean_error_min": round(mean_err, 2),
            "eta_buffer_min": recommended_buffer,
            "recommended_buffer_min": recommended_buffer,
            "sample_count": len(errs),
            "failure_reasons": sorted_reasons,
            "hour_bands": hb_summary,
        }
        by_pincode[pin] = pin_summary
        pincode_buffers[pin] = recommended_buffer

    # Process global hour band summary
    by_hour_band: Dict[str, Dict[str, Any]] = {}
    for b, b_errs in hour_band_data.items():
        by_hour_band[b] = {
            "mean_error_min": round(sum(b_errs) / len(b_errs), 2) if b_errs else 0.0,
            "sample_count": len(b_errs),
        }

    overall_mean = (
        round(sum(all_errors) / len(all_errors), 2) if all_errors else 0.0
    )

    result = {
        "pincode_buffers": pincode_buffers,
        "by_pincode": by_pincode,
        "by_hour_band": by_hour_band,
        "overall_mean_error_min": overall_mean,
        "total_events": len(all_errors),
    }

    # Also add direct pincode access for flexibility
    for pin, buf in pincode_buffers.items():
        result[pin] = buf

    return result


def compute_metrics_summary(
    historical_events: List[Any],
    tuning_data: Union[Dict[str, Any], Any],
) -> Dict[str, Any]:
    """
    Returns before_mean_error_min, after_mean_error_min, error_reduction_pct, sample_count.
    Evaluates baseline ETA error vs residual error after applying tuned pincode buffers.
    """
    # Extract buffers mapping from tuning_data
    buffers: Dict[str, int] = {}
    if isinstance(tuning_data, dict):
        if "pincode_buffers" in tuning_data and isinstance(tuning_data["pincode_buffers"], dict):
            buffers = {str(k): int(v) for k, v in tuning_data["pincode_buffers"].items()}
        elif "by_pincode" in tuning_data and isinstance(tuning_data["by_pincode"], dict):
            for k, v in tuning_data["by_pincode"].items():
                if isinstance(v, dict) and "eta_buffer_min" in v:
                    buffers[str(k)] = int(v["eta_buffer_min"])
        elif "eta_buffer_min" in tuning_data and "pincode" in tuning_data:
            buffers[str(tuning_data["pincode"])] = int(tuning_data["eta_buffer_min"])
        else:
            for k, v in tuning_data.items():
                if str(k).isdigit() and len(str(k)) == 6 and isinstance(v, (int, float)):
                    buffers[str(k)] = int(v)
    elif hasattr(tuning_data, "pincode") and hasattr(tuning_data, "eta_buffer_min"):
        buffers[str(tuning_data.pincode)] = int(tuning_data.eta_buffer_min)

    if not historical_events:
        return {
            "before_mean_error_min": 0.0,
            "after_mean_error_min": 0.0,
            "error_reduction_pct": 0.0,
            "sample_count": 0,
        }

    before_errors: List[float] = []
    after_errors: List[float] = []

    for evt in historical_events:
        extracted = _extract_event_info(evt)
        if not extracted:
            continue

        pincode = extracted["pincode"]
        error_val = extracted["error_min"]

        # Original absolute error before buffer
        abs_before = abs(error_val)
        before_errors.append(abs_before)

        # Buffer learned for this pincode
        buf = buffers.get(pincode, 0)
        # Residual error after buffer adjustment
        abs_after = abs(error_val - buf)
        after_errors.append(abs_after)

    if not before_errors:
        return {
            "before_mean_error_min": 0.0,
            "after_mean_error_min": 0.0,
            "error_reduction_pct": 0.0,
            "sample_count": 0,
        }

    before_mean = round(sum(before_errors) / len(before_errors), 2)
    after_mean = round(sum(after_errors) / len(after_errors), 2)

    if before_mean > 0:
        reduction_pct = round(((before_mean - after_mean) / before_mean) * 100, 2)
    else:
        reduction_pct = 0.0

    return {
        "before_mean_error_min": before_mean,
        "after_mean_error_min": after_mean,
        "error_reduction_pct": reduction_pct,
        "sample_count": len(before_errors),
    }
