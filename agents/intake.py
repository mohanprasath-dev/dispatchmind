import json
import logging
import re
from pathlib import Path
from typing import Optional, Dict, Any, Union, List

from core.config import GOOGLE_API_KEY, DEMO_MODE
from core.models import Order, MissingFields
from core.resilience import resilient
from core.store import store

logger = logging.getLogger(__name__)

# Chennai known pincode coordinates for geocoding fallback
CHENNAI_PINCODE_COORDS: Dict[str, tuple[float, float]] = {
    "600001": (13.0901, 80.2925),  # George Town
    "600002": (13.0645, 80.2707),  # Anna Salai / Mount Road
    "600004": (13.0336, 80.2678),  # Mylapore
    "600013": (13.1118, 80.2974),  # Royapuram
    "600017": (13.0418, 80.2341),  # T. Nagar
    "600020": (13.0012, 80.2565),  # Adyar
    "600028": (13.0238, 80.2537),  # R.A. Puram
    "600032": (13.0116, 80.2038),  # Guindy
    "600034": (13.0610, 80.2415),  # Nungambakkam
    "600040": (13.0850, 80.2101),  # Anna Nagar
    "600042": (12.9750, 80.2210),  # Velachery
    "600045": (12.9249, 80.1000),  # Tambaram
    "600047": (12.9320, 80.1250),  # Tambaram Sanatorium
    "600058": (13.1143, 80.1548),  # Ambattur
    "600085": (13.0125, 80.2340),  # Kotturpuram
    "600091": (12.9620, 80.1980),  # Madipakkam
    "600096": (12.9675, 80.2410),  # Perungudi
    "600097": (12.9416, 80.2362),  # Thoraipakkam
    "600100": (12.9228, 80.1872),  # Medavakkam
    "600101": (13.0880, 80.1950),  # Anna Nagar West Ext
    "600107": (13.0694, 80.1948),  # Koyambedu
    "600113": (12.9863, 80.2432),  # Taramani
    "600116": (13.0359, 80.1584),  # Porur
    "600119": (12.8988, 80.2281),  # Sholinganallur
}


def clean_phone(raw_phone: Optional[str]) -> Optional[str]:
    """Clean and validate Indian 10-digit mobile number."""
    if not raw_phone:
        return None
    cleaned = re.sub(r"[\s\-\+\(\)]", "", str(raw_phone).strip())
    if cleaned.startswith("91") and len(cleaned) == 12:
        cleaned = cleaned[2:]
    elif cleaned.startswith("0") and len(cleaned) == 11:
        cleaned = cleaned[1:]
    if re.match(r"^[6-9]\d{9}$", cleaned):
        return cleaned
    return None


def clean_pincode(raw_pincode: Optional[str]) -> Optional[str]:
    """Clean and validate Indian 6-digit postal pincode."""
    if not raw_pincode:
        return None
    cleaned = re.sub(r"\s+", "", str(raw_pincode).strip())
    if re.match(r"^\d{6}$", cleaned):
        return cleaned
    return None


def extract_text_from_pdf(pdf_bytes: bytes) -> str:
    """Extract plain text from PDF bytes using pypdf."""
    try:
        import io
        import pypdf
        reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
        pages_text = [page.extract_text() or "" for page in reader.pages]
        return "\n".join(pages_text)
    except Exception as exc:
        logger.warning(f"Failed to extract text from PDF: {exc}")
        return ""


def deterministic_text_extractor(text: str) -> Dict[str, Any]:
    """
    Deterministic rule-based extractor for logistics text, invoices, and challans.
    Extracts structured fields accurately without hallucinating values.
    """
    data: Dict[str, Any] = {
        "order_id": None,
        "customer": None,
        "phone": None,
        "address": None,
        "pincode": None,
        "weight_kg": None,
        "time_window": None,
        "gstin": None,
        "eway_bill_no": None,
    }
    confidences: Dict[str, float] = {k: 0.0 for k in data.keys()}

    lines = [line.strip() for line in text.split("\n") if line.strip()]

    for i, line in enumerate(lines):
        # Order ID
        if "Order ID:" in line:
            data["order_id"] = line.split("Order ID:")[1].strip()
            confidences["order_id"] = 0.98
        elif "Doc ID:" in line and not data["order_id"]:
            data["order_id"] = line.split("Doc ID:")[1].strip()
            confidences["order_id"] = 0.85

        # e-Way Bill No
        if "e-Way Bill No:" in line:
            val = line.split("e-Way Bill No:")[1].strip().replace(" ", "")
            if len(val) >= 12:
                data["eway_bill_no"] = val
                confidences["eway_bill_no"] = 0.98

        # GSTIN and Consignee Address Block
        if "GSTIN:" in line:
            gstin_val = line.split("GSTIN:")[1].strip()
            if re.match(r"^\d{2}[A-Z]{5}\d{4}[A-Z]{1}[A-Z\d]{1}[Z]{1}[A-Z\d]{1}$", gstin_val):
                data["gstin"] = gstin_val
                confidences["gstin"] = 0.98
            # In standard logistics templates, consignee name is immediately after consignor GSTIN
            if i + 1 < len(lines):
                cust_candidate = lines[i + 1]
                if not cust_candidate.startswith("Phone:") and not cust_candidate.startswith("Origin:"):
                    data["customer"] = cust_candidate
                    confidences["customer"] = 0.95

            # Lines between customer and Phone/Origin represent consignee address
            addr_parts = []
            j = i + 2
            while j < len(lines) and not lines[j].startswith("Phone:") and not lines[j].startswith("Origin:"):
                addr_parts.append(lines[j])
                j += 1
            if addr_parts:
                data["address"] = ", ".join(addr_parts)
                confidences["address"] = 0.92

        # Phone
        if line.startswith("Phone:"):
            phone_val = line.split("Phone:")[1].strip()
            data["phone"] = phone_val
            confidences["phone"] = 0.95

        # Delivery Pincode
        if "Delivery Pincode:" in line:
            pin_str = line.split("Delivery Pincode:")[1].strip()
            if "MISSING" in pin_str.upper() or "[MISSING" in pin_str.upper():
                data["pincode"] = None
                confidences["pincode"] = 0.0
            else:
                pin_match = re.search(r"\b\d{6}\b", pin_str)
                if pin_match:
                    data["pincode"] = pin_match.group(0)
                    confidences["pincode"] = 0.98

        # Weight
        weight_match = re.match(r"^([\d\.]+)\s*(?:kg|kgs)$", line, re.IGNORECASE)
        if weight_match and data["weight_kg"] is None:
            try:
                data["weight_kg"] = float(weight_match.group(1))
                confidences["weight_kg"] = 0.95
            except ValueError:
                pass

        # Time Window
        window_match = re.match(r"^\d{1,2}:\d{2}\s*[\-\u2013\u2014]\s*\d{1,2}:\d{2}$", line)
        if window_match and data["time_window"] is None:
            data["time_window"] = re.sub(r"[\u2013\u2014]", "-", line).strip()
            confidences["time_window"] = 0.92

    # Fallback search if fields still missing
    if not data["order_id"]:
        m = re.search(r"\b(ORD\-[A-Za-z0-9\-]+|INV\-[A-Za-z0-9\-]+)\b", text)
        if m:
            data["order_id"] = m.group(0)
            confidences["order_id"] = 0.85

    if not data["customer"]:
        m_cust = re.search(r"Customer\s*:\s*([^\n\,]+)", text, re.IGNORECASE)
        if m_cust:
            data["customer"] = m_cust.group(1).strip()
            confidences["customer"] = 0.88
        else:
            m_nl = re.search(
                r"(?:deliver\s+(?:[\d\.]+\s*kg\s+package\s+)?to|ship\s+to|send\s+to)\s+([A-Za-z0-9\s\.\&]+?)\s+(?:at|address:?)\s+([0-9A-Za-z\s\,\.\-]+?)(?:,|\s+contact|\s+phone|\s+order|\s+pincode|\s+between|$)",
                text,
                re.IGNORECASE,
            )
            if m_nl:
                data["customer"] = m_nl.group(1).strip()
                confidences["customer"] = 0.88
                if not data["address"]:
                    data["address"] = m_nl.group(2).strip()
                    confidences["address"] = 0.85

    if not data["address"]:
        m_addr = re.search(r"Address\s*:\s*([^\n]+)", text, re.IGNORECASE)
        if m_addr:
            data["address"] = m_addr.group(1).strip()
            confidences["address"] = 0.88

    if not data["phone"]:
        m_ph = re.search(r"\b(?:\+91[\-\s]?)?[6-9]\d{9}\b", text)
        if m_ph:
            data["phone"] = m_ph.group(0).strip()
            confidences["phone"] = 0.85

    if not data["pincode"] and "MISSING PINCODE" not in text.upper():
        pins = re.findall(r"\b600\d{3}\b", text)
        if pins:
            data["pincode"] = pins[-1]
            confidences["pincode"] = 0.80

    if not data["weight_kg"]:
        m_w = re.search(r"([\d\.]+)\s*(?:kg|kgs|kilograms)", text, re.IGNORECASE)
        if m_w:
            try:
                data["weight_kg"] = float(m_w.group(1))
                confidences["weight_kg"] = 0.85
            except ValueError:
                pass

    if not data["time_window"]:
        m_win = re.search(r"(\d{1,2}:\d{2}\s*[\-\u2013\u2014]\s*\d{1,2}:\d{2})", text)
        if m_win:
            data["time_window"] = re.sub(r"[\u2013\u2014]", "-", m_win.group(1)).strip()
            confidences["time_window"] = 0.85
        else:
            data["time_window"] = "09:00 - 18:00"
            confidences["time_window"] = 0.60

    return {"fields": data, "confidences": confidences}


def call_gemini_vision_or_doc(
    content_bytes: bytes,
    mime_type: str,
    prompt: str,
) -> Optional[Dict[str, Any]]:
    """Call Gemini 2.5 Flash via google-genai SDK for multimodal extraction."""
    if not GOOGLE_API_KEY:
        return None

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=GOOGLE_API_KEY)
        part = types.Part.from_bytes(data=content_bytes, mime_type=mime_type)

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[part, prompt],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.0,
            ),
        )
        if response and response.text:
            return json.loads(response.text)
    except Exception as exc:
        logger.warning(f"Gemini API call failed: {exc}")
    return None


EXTRACTION_PROMPT = """
You are an expert logistics document extraction agent for Indian fleet operations.
Analyze the provided document (invoice, e-way bill, label photo, or shipping note).

Extract the following target fields into a structured JSON object:
- order_id: string identifier of the order or invoice (e.g. ORD-2026-101, INV-2026-001)
- customer: consignee or recipient customer business/personal name
- phone: 10-digit Indian contact phone number (digits only or with standard spacing)
- address: full delivery street address of the consignee
- pincode: 6-digit Indian postal pincode for delivery destination
- weight_kg: total consignment weight as a positive float in kilograms
- time_window: delivery time window (e.g. 10:00 - 13:00)
- gstin: 15-character GSTIN number if present
- eway_bill_no: 12-digit Indian e-way bill number if present

CRITICAL EXTRACTION RULES:
1. Never invent or hallucinate missing data. If a field is missing, illegible, or explicitly marked missing, set value to null and confidence to 0.0.
2. For each field, provide a confidence score between 0.0 and 1.0 reflecting clarity and certainty.
3. If confidence is below 0.6 for any field, set confidence accurately below 0.6 so dispatcher clarification is requested.

Return strictly JSON matching this structure:
{
  "fields": {
    "order_id": str or null,
    "customer": str or null,
    "phone": str or null,
    "address": str or null,
    "pincode": str or null,
    "weight_kg": float or null,
    "time_window": str or null,
    "gstin": str or null,
    "eway_bill_no": str or null
  },
  "confidences": {
    "order_id": float,
    "customer": float,
    "phone": float,
    "address": float,
    "pincode": float,
    "weight_kg": float,
    "time_window": float,
    "gstin": float,
    "eway_bill_no": float
  }
}
"""


def parse_raw_input(
    content: Union[str, bytes, Path],
    filename: Optional[str] = None,
) -> Dict[str, Any]:
    """Parse raw content (file, text, or bytes) using Gemini with deterministic fallback."""
    raw_text = ""
    content_bytes = b""
    mime_type = "text/plain"

    if isinstance(content, Path) or (isinstance(content, str) and Path(content).exists()):
        file_path = Path(content)
        filename = filename or file_path.name
        content_bytes = file_path.read_bytes()
        if file_path.suffix.lower() == ".pdf":
            mime_type = "application/pdf"
            raw_text = extract_text_from_pdf(content_bytes)
        elif file_path.suffix.lower() in [".png", ".jpg", ".jpeg", ".webp"]:
            mime_type = f"image/{file_path.suffix.lower().replace('.', '')}"
        else:
            raw_text = content_bytes.decode("utf-8", errors="ignore")
    elif isinstance(content, bytes):
        content_bytes = content
        if content_bytes.startswith(b"%PDF"):
            mime_type = "application/pdf"
            raw_text = extract_text_from_pdf(content_bytes)
        elif content_bytes.startswith(b"\x89PNG") or content_bytes.startswith(b"\xff\xd8"):
            mime_type = "image/png" if content_bytes.startswith(b"\x89PNG") else "image/jpeg"
        else:
            raw_text = content_bytes.decode("utf-8", errors="ignore")
    else:
        raw_text = str(content)
        content_bytes = raw_text.encode("utf-8")
        mime_type = "text/plain"

    # Try Gemini multimodal call if API key available and image or non-empty bytes
    gemini_result = None
    if GOOGLE_API_KEY and (mime_type.startswith("image/") or not raw_text):
        gemini_result = call_gemini_vision_or_doc(content_bytes, mime_type, EXTRACTION_PROMPT)

    if gemini_result and "fields" in gemini_result and "confidences" in gemini_result:
        return gemini_result

    # Fallback to deterministic text extractor
    if not raw_text and content_bytes:
        raw_text = content_bytes.decode("utf-8", errors="ignore")
    return deterministic_text_extractor(raw_text)


def validate_and_build_result(
    extracted_data: Dict[str, Any],
    save_to_store: bool = True,
) -> Union[Order, MissingFields]:
    """
    Validate extracted fields against Indian logistics requirements:
    - 6-digit Indian pincode
    - 10-digit Indian phone (starting with 6-9)
    - Positive weight (> 0 kg)
    - Non-empty customer and address
    - Confidence >= 0.6 per required field

    Never invent missing data.
    Return MissingFields with exactly one precise question per gap if any check fails.
    Otherwise return validated Order.
    """
    fields = extracted_data.get("fields", {})
    confidences = extracted_data.get("confidences", {})

    gaps: List[str] = []
    questions: List[str] = []

    # 1. Order ID
    raw_order_id = fields.get("order_id")
    order_id_conf = confidences.get("order_id", 0.0)
    order_id = str(raw_order_id).strip() if raw_order_id else None
    if not order_id or order_id_conf < 0.6:
        gaps.append("order_id")
        questions.append("What is the order ID or reference number for this consignment?")
    order_id_display = order_id or "this shipment"

    # 2. Customer
    raw_customer = fields.get("customer")
    customer_conf = confidences.get("customer", 0.0)
    customer = str(raw_customer).strip() if raw_customer else None
    if not customer or customer_conf < 0.6 or len(customer) < 2:
        gaps.append("customer")
        questions.append(f"What is the customer or recipient business name for order {order_id_display}?")
    cust_display = customer or "the consignee"

    # 3. Address
    raw_address = fields.get("address")
    address_conf = confidences.get("address", 0.0)
    address = str(raw_address).strip() if raw_address else None
    if not address or address_conf < 0.6 or len(address) < 4:
        gaps.append("address")
        questions.append(f"What is the complete street delivery address for order {order_id_display}?")
    addr_display = address or "the delivery location"

    # 4. Phone
    raw_phone = fields.get("phone")
    phone_conf = confidences.get("phone", 0.0)
    cleaned_phone = clean_phone(raw_phone)
    if not cleaned_phone or phone_conf < 0.6:
        gaps.append("phone")
        questions.append(f"What is the 10-digit Indian contact phone number for customer {cust_display}?")

    # 5. Pincode
    raw_pincode = fields.get("pincode")
    pincode_conf = confidences.get("pincode", 0.0)
    cleaned_pincode = clean_pincode(raw_pincode)
    if not cleaned_pincode or pincode_conf < 0.6:
        gaps.append("pincode")
        questions.append(f"What is the 6-digit delivery pincode for customer {cust_display} at {addr_display}?")

    # 6. Weight
    raw_weight = fields.get("weight_kg")
    weight_conf = confidences.get("weight_kg", 0.0)
    valid_weight = None
    try:
        if raw_weight is not None and float(raw_weight) > 0:
            valid_weight = round(float(raw_weight), 2)
    except (ValueError, TypeError):
        valid_weight = None

    if valid_weight is None or weight_conf < 0.6:
        gaps.append("weight_kg")
        questions.append(f"What is the consignment package weight in kilograms for order {order_id_display}?")

    # If any gap detected, return MissingFields with exactly one precise question per gap
    if gaps:
        return MissingFields(
            order_id=order_id,
            missing_fields=gaps,
            questions=questions,
            field_confidences=confidences,
            extracted_fields=fields,
        )

    # All required fields are valid and >= 0.6 confidence
    time_window_raw = fields.get("time_window", "09:00 - 18:00")
    window_start = "09:00"
    window_end = "18:00"
    if time_window_raw:
        times = re.findall(r"\d{1,2}:\d{2}", str(time_window_raw))
        if len(times) >= 2:
            window_start = times[0]
            window_end = times[1]

    # Geocode coordinates lookup
    lat, lng = None, None
    if cleaned_pincode in CHENNAI_PINCODE_COORDS:
        lat, lng = CHENNAI_PINCODE_COORDS[cleaned_pincode]

    # Calculate overall confidence score
    confidence_values = [v for v in confidences.values() if isinstance(v, (int, float))]
    avg_confidence = round(sum(confidence_values) / len(confidence_values), 2) if confidence_values else 0.95

    order = Order(
        id=order_id,
        customer_name=customer,
        phone=cleaned_phone,
        address=address,
        pincode=cleaned_pincode,
        lat=lat,
        lng=lng,
        weight_kg=valid_weight,
        window_start=window_start,
        window_end=window_end,
        status="pending",
        assigned_vehicle=None,
        eway_bill_no=fields.get("eway_bill_no"),
        gstin=fields.get("gstin"),
        confidence_score=avg_confidence,
        field_confidences=confidences,
    )

    if save_to_store:
        store.set("orders", order.id, order)

    return order


@resilient(retries=2, base_delay=0.01)
def process_intake(
    content: Union[str, bytes, Path],
    filename: Optional[str] = None,
    save_to_store: bool = True,
) -> Union[Order, MissingFields]:
    """
    Main intake entrypoint:
    Extracts, validates, and returns Order or MissingFields.
    """
    extracted = parse_raw_input(content, filename=filename)
    return validate_and_build_result(extracted, save_to_store=save_to_store)


def build_agent():
    """Build and export Google ADK Intake Agent."""
    from google.adk.agents import Agent

    def intake_tool(document_text: str) -> str:
        """Parse raw text or invoice data and validate Indian dispatch order fields."""
        res = process_intake(document_text)
        return json.dumps(res.model_dump())

    agent = Agent(
        name="intake",
        model="gemini-2.5-flash",
        description="Multi-modal intake agent for parsing Indian logistics invoices, e-way bills, and challans.",
        instruction=(
            "You are the Intake Agent for DispatchMind. "
            "Your job is to parse invoices, e-way bills, delivery challans, and customer messages. "
            "Extract: order_id, customer, phone, address, pincode, weight_kg, time_window, GSTIN, eway_bill_no. "
            "Validate: 6-digit Indian pincode, 10-digit Indian phone (starting 6-9), positive weight > 0 kg. "
            "Confidence must be at least 0.6 for all required fields. "
            "Never invent or hallucinate missing data. "
            "Return MissingFields with exactly one precise question per gap if any information is missing."
        ),
        tools=[intake_tool],
    )
    return agent
