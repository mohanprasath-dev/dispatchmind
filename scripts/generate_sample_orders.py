import os
import sys
from pathlib import Path
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from PIL import Image, ImageDraw, ImageFont

DATA_DIR = Path("data/sample_orders")
DATA_DIR.mkdir(parents=True, exist_ok=True)

SAMPLES = [
    {
        "id": "INV-2026-001",
        "doc_type": "TAX INVOICE",
        "order_id": "ORD-2026-101",
        "seller_name": "Southern Industrial Fasteners Pvt Ltd",
        "seller_addr": "Plot 14, SIDCO Industrial Estate, Guindy, Chennai 600032",
        "seller_gstin": "33AAAAA1234A1Z5",
        "buyer_name": "Apex Auto Spares",
        "buyer_addr": "45 Usman Road, T. Nagar, Chennai 600017",
        "pincode": "600017",
        "phone": "+91 98401 23456",
        "eway_bill": "2410 9811 2045",
        "weight_kg": "85.50 kg",
        "window": "10:00 - 13:00",
        "items": [
            ("High-Tensile Flange Bolts M12", "73181500", "20.00 kg", "INR 12,400"),
            ("Self-Locking Nylon Nuts M10", "73181600", "15.50 kg", "INR 8,680"),
            ("Hardened Zinc Flat Washers", "73182100", "50.00 kg", "INR 21,400")
        ],
        "total_amount": "INR 42,480.00",
        "has_gap": False,
        "gap_note": None
    },
    {
        "id": "EWAY-2026-002",
        "doc_type": "CONSOLIDATED E-WAY BILL",
        "order_id": "ORD-2026-102",
        "seller_name": "Coromandel Cargo Hub Terminal",
        "seller_addr": "Berth 4, Royapuram Terminal, Chennai 600013",
        "seller_gstin": "33BBBBB5678B1Z2",
        "buyer_name": "Precision Heavy Engineering Works",
        "buyer_addr": "Shed C-12, Ambattur Industrial Estate, Chennai 600058",
        "pincode": "600058",
        "phone": "+91 94440 98765",
        "eway_bill": "2410 9876 5432",
        "weight_kg": "320.00 kg",
        "window": "09:00 - 12:00",
        "items": [
            ("Industrial High-Pressure Cast Valves", "84818090", "280.00 kg", "INR 1,45,000"),
            ("Hydraulic Actuator Flanges", "84819090", "40.00 kg", "INR 38,500")
        ],
        "total_amount": "INR 1,83,500.00",
        "has_gap": False,
        "gap_note": None
    },
    {
        "id": "CHALLAN-2026-003",
        "doc_type": "DELIVERY CHALLAN & CONSIGNMENT NOTE",
        "order_id": "ORD-2026-103",
        "seller_name": "Sriperumbudur Electronics Hub",
        "seller_addr": "Phase II, SIPCOT Hi-Tech SEZ, Kanchipuram 602105",
        "seller_gstin": "33CCCCC9012C1Z8",
        "buyer_name": "SmartTech Distribution Center",
        "buyer_addr": "12 Sardar Patel Road, Adyar, Chennai 600020",
        "pincode": "600020",
        "phone": "+91 97910 11223",
        "eway_bill": "2410 8823 4410",
        "weight_kg": "140.00 kg",
        "window": "14:00 - 17:00",
        "items": [
            ("Network Server Racks 42U", "85177090", "110.00 kg", "INR 84,000"),
            ("Fiber Distribution Enclosures", "85369090", "30.00 kg", "INR 26,000")
        ],
        "total_amount": "INR 1,10,000.00",
        "has_gap": False,
        "gap_note": None
    },
    {
        "id": "INV-2026-004",
        "doc_type": "TAX INVOICE & PACKING LIST",
        "order_id": "ORD-2026-104",
        "seller_name": "Kovai Fresh Foods Logistics Hub",
        "seller_addr": "Wholesale Market Road, Koyambedu, Chennai 600107",
        "seller_gstin": "33DDDDD3456D1Z1",
        "buyer_name": "Nilgiri Retail Depot",
        "buyer_addr": "82 100 Feet Bypass Road, Velachery, Chennai 600042",
        "pincode": "600042",
        "phone": "+91 98840 55678",
        "eway_bill": "2410 7734 5519",
        "weight_kg": "45.00 kg",
        "window": "11:00 - 14:00",
        "items": [
            ("Cold Chain Ambient Dairy Provisions", "04012000", "25.00 kg", "INR 14,500"),
            ("Sealed Food Grade Storage Tubs", "39231090", "20.00 kg", "INR 6,200")
        ],
        "total_amount": "INR 20,700.00",
        "has_gap": False,
        "gap_note": None
    },
    {
        "id": "INV-2026-005-GAP",
        "doc_type": "COMMERCIAL INVOICE",
        "order_id": "ORD-2026-105",
        "seller_name": "Madras Hardware Consortium",
        "seller_addr": "108 Broadway, George Town, Chennai 600001",
        "seller_gstin": "33EEEEE7890E1Z4",
        "buyer_name": "Krishna Construction Supplies",
        "buyer_addr": "Door No 42, 2nd Avenue, Anna Nagar West, Chennai, Tamil Nadu",
        "pincode": "",  # INTENTIONAL GAP FOR INTAKE CLARIFICATION
        "phone": "+91 98412 34999",
        "eway_bill": "2410 6655 4321",
        "weight_kg": "65.00 kg",
        "window": "13:00 - 16:00",
        "items": [
            ("Heavy-Duty PVC Conduit Pipes 25mm", "39172300", "45.00 kg", "INR 18,200"),
            ("Industrial Armoured Cable Bundles", "85444990", "20.00 kg", "INR 15,300")
        ],
        "total_amount": "INR 33,500.00",
        "has_gap": True,
        "gap_note": "INTENTIONAL GAP: Missing 6-digit Pincode in delivery address"
    }
]

def generate_pdf(sample: dict, output_path: Path):
    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=letter,
        rightMargin=36,
        leftMargin=36,
        topMargin=36,
        bottomMargin=36
    )
    styles = getSampleStyleSheet()
    
    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Heading1'],
        fontName='Helvetica-Bold',
        fontSize=18,
        leading=22,
        textColor=colors.HexColor('#0f172a'),
        alignment=1
    )
    
    sub_title_style = ParagraphStyle(
        'DocSub',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=10,
        leading=14,
        textColor=colors.HexColor('#64748b'),
        alignment=1
    )

    h2_style = ParagraphStyle(
        'SecHead',
        parent=styles['Heading2'],
        fontName='Helvetica-Bold',
        fontSize=11,
        leading=14,
        textColor=colors.HexColor('#1e293b')
    )

    text_style = ParagraphStyle(
        'BodyTxt',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=9,
        leading=13,
        textColor=colors.HexColor('#334155')
    )
    
    bold_style = ParagraphStyle(
        'BoldTxt',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=9,
        leading=13,
        textColor=colors.HexColor('#0f172a')
    )

    alert_style = ParagraphStyle(
        'AlertTxt',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=9,
        leading=13,
        textColor=colors.HexColor('#dc2626')
    )

    story = []
    
    # Header
    story.append(Paragraph(f"<b>{sample['doc_type']}</b>", title_style))
    story.append(Paragraph("DISPATCHMIND VERIFIED LOGISTICS DOCUMENT - TAMIL NADU REGION", sub_title_style))
    story.append(Spacer(1, 10))
    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor('#2563eb'), spaceAfter=12))

    # Meta Table (Doc ID, Order ID, e-Way bill, Date)
    meta_data = [
        [
            Paragraph(f"<b>Doc ID:</b> {sample['id']}", bold_style),
            Paragraph(f"<b>Order ID:</b> {sample['order_id']}", bold_style),
            Paragraph(f"<b>e-Way Bill No:</b> {sample['eway_bill']}", bold_style),
            Paragraph("<b>Date:</b> 17-Oct-2026", text_style)
        ]
    ]
    meta_table = Table(meta_data, colWidths=[130, 130, 150, 130])
    meta_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f1f5f9')),
        ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
    ]))
    story.append(meta_table)
    story.append(Spacer(1, 14))

    # Consignor & Consignee boxes
    pincode_display = sample['pincode'] if sample['pincode'] else "[MISSING PINCODE - REQUIRES DISPATCHER CLARIFICATION]"
    pincode_para = Paragraph(f"<b>Delivery Pincode:</b> {pincode_display}", alert_style if sample['has_gap'] else bold_style)

    parties_data = [
        [
            Paragraph("<b>CONSIGNOR (Shipper)</b>", h2_style),
            Paragraph("<b>CONSIGNEE (Ship To Delivery)</b>", h2_style)
        ],
        [
            Paragraph(f"<b>{sample['seller_name']}</b><br/>{sample['seller_addr']}<br/><b>GSTIN:</b> {sample['seller_gstin']}", text_style),
            Paragraph(f"<b>{sample['buyer_name']}</b><br/>{sample['buyer_addr']}<br/><b>Phone:</b> {sample['phone']}<br/>", text_style)
        ],
        [
            Paragraph("<b>Origin:</b> Chennai Logistics Zone", text_style),
            pincode_para
        ]
    ]
    parties_table = Table(parties_data, colWidths=[270, 270])
    parties_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e2e8f0')),
        ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
    ]))
    story.append(parties_table)
    story.append(Spacer(1, 14))

    # Shipment Specs Table
    specs_data = [
        [
            Paragraph("<b>Consignment Weight</b>", bold_style),
            Paragraph("<b>Delivery Window</b>", bold_style),
            Paragraph("<b>Vehicle Type</b>", bold_style),
            Paragraph("<b>Transit Status</b>", bold_style)
        ],
        [
            Paragraph(sample['weight_kg'], text_style),
            Paragraph(sample['window'], text_style),
            Paragraph("Tata Ace / Eicher Pro (3.5T)", text_style),
            Paragraph("READY FOR INTAKE", bold_style)
        ]
    ]
    specs_table = Table(specs_data, colWidths=[135, 135, 135, 135])
    specs_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f8fafc')),
        ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
    ]))
    story.append(specs_table)
    story.append(Spacer(1, 14))

    # Items Table
    items_header = [
        Paragraph("<b>Item Description</b>", bold_style),
        Paragraph("<b>HSN Code</b>", bold_style),
        Paragraph("<b>Weight / Qty</b>", bold_style),
        Paragraph("<b>Taxable Value</b>", bold_style)
    ]
    items_rows = [items_header]
    for desc, hsn, wt, val in sample['items']:
        items_rows.append([
            Paragraph(desc, text_style),
            Paragraph(hsn, text_style),
            Paragraph(wt, text_style),
            Paragraph(val, text_style)
        ])
    items_rows.append([
        Paragraph("<b>Total Taxable Amount</b>", bold_style),
        Paragraph("", text_style),
        Paragraph(f"<b>{sample['weight_kg']}</b>", bold_style),
        Paragraph(f"<b>{sample['total_amount']}</b>", bold_style)
    ])
    
    items_table = Table(items_rows, colWidths=[240, 100, 100, 100])
    items_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#2563eb')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#cbd5e1')),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#f1f5f9')),
    ]))
    story.append(items_table)
    story.append(Spacer(1, 16))

    if sample['has_gap']:
        gap_box_data = [[
            Paragraph("<b>ATTENTION INTAKE AGENT:</b> Intentional Gap Active - Missing Delivery Pincode in consignee address. Model must extract all valid fields and generate a precise clarification question to the dispatcher without hallucinating postal code.", alert_style)
        ]]
        gap_table = Table(gap_box_data, colWidths=[540])
        gap_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#fee2e2')),
            ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#ef4444')),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('LEFTPADDING', (0, 0), (-1, -1), 10),
            ('RIGHTPADDING', (0, 0), (-1, -1), 10),
        ]))
        story.append(gap_table)
        story.append(Spacer(1, 10))

    # Footer declaration
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor('#cbd5e1'), spaceAfter=8))
    story.append(Paragraph("This is a computer generated document. Valid for transport operations under GST Rule 138 of Tamil Nadu State Goods and Services Tax Rules.", sub_title_style))

    doc.build(story)
    print(f"Generated PDF: {output_path}")

def generate_image(sample: dict, output_path: Path):
    # Create high-res document image
    w, h = 1000, 1300
    img = Image.new("RGB", (w, h), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)

    # Fonts
    font_path = "C:/Windows/Fonts/arial.ttf"
    font_bold_path = "C:/Windows/Fonts/arialbd.ttf"
    
    font_h1 = ImageFont.truetype(font_bold_path, 28)
    font_h2 = ImageFont.truetype(font_bold_path, 18)
    font_h3 = ImageFont.truetype(font_bold_path, 15)
    font_body = ImageFont.truetype(font_path, 14)
    font_small = ImageFont.truetype(font_path, 12)
    font_bold = ImageFont.truetype(font_bold_path, 14)

    # Top border bar
    draw.rectangle([(0, 0), (w, 12)], fill=(37, 99, 235))

    # Header
    draw.text((w // 2, 45), sample['doc_type'], fill=(15, 23, 42), font=font_h1, anchor="mm")
    draw.text((w // 2, 75), "DISPATCHMIND VERIFIED LOGISTICS DOCUMENT - TAMIL NADU REGION", fill=(100, 116, 139), font=font_small, anchor="mm")
    draw.line([(40, 95), (w - 40, 95)], fill=(203, 213, 225), width=2)

    # Meta bar
    draw.rounded_rectangle([(40, 115), (w - 40, 165)], radius=6, fill=(241, 245, 249), outline=(203, 213, 225))
    draw.text((60, 130), f"Doc ID: {sample['id']}", fill=(15, 23, 42), font=font_bold)
    draw.text((280, 130), f"Order: {sample['order_id']}", fill=(15, 23, 42), font=font_bold)
    draw.text((500, 130), f"e-Way Bill: {sample['eway_bill']}", fill=(15, 23, 42), font=font_bold)
    draw.text((790, 130), "Date: 17-Oct-2026", fill=(71, 85, 105), font=font_body)

    # Consignor & Consignee panels
    # Consignor Left
    draw.rounded_rectangle([(40, 185), (480, 360)], radius=6, fill=(255, 255, 255), outline=(203, 213, 225))
    draw.rectangle([(40, 185), (480, 220)], fill=(226, 232, 240))
    draw.text((55, 195), "CONSIGNOR (Shipper)", fill=(30, 41, 59), font=font_h3)
    draw.text((55, 235), sample['seller_name'], fill=(15, 23, 42), font=font_bold)
    draw.text((55, 260), sample['seller_addr'][:42], fill=(51, 65, 85), font=font_body)
    draw.text((55, 280), sample['seller_addr'][42:], fill=(51, 65, 85), font=font_body)
    draw.text((55, 310), f"GSTIN: {sample['seller_gstin']}", fill=(15, 23, 42), font=font_bold)
    draw.text((55, 335), "Dispatch Hub: Chennai Logistics Zone", fill=(71, 85, 105), font=font_small)

    # Consignee Right
    draw.rounded_rectangle([(520, 185), (w - 40, 360)], radius=6, fill=(255, 255, 255), outline=(203, 213, 225))
    draw.rectangle([(520, 185), (w - 40, 220)], fill=(226, 232, 240))
    draw.text((535, 195), "CONSIGNEE (Delivery Destination)", fill=(30, 41, 59), font=font_h3)
    draw.text((535, 235), sample['buyer_name'], fill=(15, 23, 42), font=font_bold)
    draw.text((535, 260), sample['buyer_addr'][:45], fill=(51, 65, 85), font=font_body)
    draw.text((535, 280), sample['buyer_addr'][45:], fill=(51, 65, 85), font=font_body)
    draw.text((535, 308), f"Contact Phone: {sample['phone']}", fill=(15, 23, 42), font=font_bold)
    
    if sample['pincode']:
        draw.text((535, 335), f"Pincode: {sample['pincode']}", fill=(37, 99, 235), font=font_bold)
    else:
        draw.rectangle([(530, 330), (940, 355)], fill=(254, 226, 226))
        draw.text((535, 335), "[GAP: PINCODE MISSING FROM INVOICE]", fill=(220, 38, 38), font=font_bold)

    # Shipment Specs Bar
    draw.rounded_rectangle([(40, 380), (w - 40, 440)], radius=6, fill=(248, 250, 252), outline=(203, 213, 225))
    draw.text((60, 392), "Consignment Weight", fill=(100, 116, 139), font=font_small)
    draw.text((60, 412), sample['weight_kg'], fill=(15, 23, 42), font=font_bold)

    draw.text((300, 392), "Delivery Window", fill=(100, 116, 139), font=font_small)
    draw.text((300, 412), sample['window'], fill=(15, 23, 42), font=font_bold)

    draw.text((540, 392), "Vehicle Assignment", fill=(100, 116, 139), font=font_small)
    draw.text((540, 412), "Tata Ace / Eicher 3.5T", fill=(15, 23, 42), font=font_bold)

    draw.text((760, 392), "Status", fill=(100, 116, 139), font=font_small)
    draw.text((760, 412), "READY FOR INTAKE", fill=(22, 101, 52), font=font_bold)

    # Items Table
    y_tbl = 460
    draw.rectangle([(40, y_tbl), (w - 40, y_tbl + 35)], fill=(37, 99, 235))
    draw.text((60, y_tbl + 10), "Item Description", fill=(255, 255, 255), font=font_bold)
    draw.text((500, y_tbl + 10), "HSN Code", fill=(255, 255, 255), font=font_bold)
    draw.text((680, y_tbl + 10), "Weight / Qty", fill=(255, 255, 255), font=font_bold)
    draw.text((830, y_tbl + 10), "Value", fill=(255, 255, 255), font=font_bold)

    curr_y = y_tbl + 35
    for idx, (desc, hsn, wt, val) in enumerate(sample['items']):
        bg_col = (255, 255, 255) if idx % 2 == 0 else (248, 250, 252)
        draw.rectangle([(40, curr_y), (w - 40, curr_y + 35)], fill=bg_col, outline=(226, 232, 240))
        draw.text((60, curr_y + 9), desc, fill=(30, 41, 59), font=font_body)
        draw.text((500, curr_y + 9), hsn, fill=(51, 65, 85), font=font_body)
        draw.text((680, curr_y + 9), wt, fill=(51, 65, 85), font=font_body)
        draw.text((830, curr_y + 9), val, fill=(15, 23, 42), font=font_bold)
        curr_y += 35

    # Total row
    draw.rectangle([(40, curr_y), (w - 40, curr_y + 40)], fill=(241, 245, 249), outline=(203, 213, 225))
    draw.text((60, curr_y + 12), "Total Consignment", fill=(15, 23, 42), font=font_h3)
    draw.text((680, curr_y + 12), sample['weight_kg'], fill=(15, 23, 42), font=font_h3)
    draw.text((830, curr_y + 12), sample['total_amount'], fill=(37, 99, 235), font=font_h3)
    curr_y += 55

    # Barcode representation
    bar_x = 60
    bar_y = curr_y + 20
    draw.text((bar_x, bar_y - 20), f"CONSIGNMENT BARCODE: {sample['eway_bill']}", fill=(100, 116, 139), font=font_small)
    # Draw simulated barcode bars
    import random
    rng = random.Random(sum(ord(c) for c in sample['eway_bill']))
    for i in range(120):
        bar_width = rng.choice([2, 3, 5])
        gap = rng.choice([2, 3, 4])
        draw.rectangle([(bar_x, bar_y), (bar_x + bar_width, bar_y + 45)], fill=(15, 23, 42))
        bar_x += bar_width + gap
        if bar_x > w - 100:
            break

    curr_y = bar_y + 70

    if sample['has_gap']:
        draw.rounded_rectangle([(40, curr_y), (w - 40, curr_y + 70)], radius=6, fill=(254, 226, 226), outline=(239, 68, 68))
        draw.text((60, curr_y + 14), "INTENTIONAL TEST GAP: DELIVERY PINCODE MISSING", fill=(185, 28, 28), font=font_bold)
        draw.text((60, curr_y + 38), "Intake agent must catch this gap and prompt: 'What is the delivery pincode for Anna Nagar West?'", fill=(153, 27, 27), font=font_body)
        curr_y += 85

    # Official Seal / Stamp representation
    stamp_x, stamp_y = w - 240, h - 220
    draw.ellipse([(stamp_x, stamp_y), (stamp_x + 160, stamp_y + 160)], outline=(37, 99, 235), width=3)
    draw.text((stamp_x + 80, stamp_y + 50), "DISPATCHMIND", fill=(37, 99, 235), font=font_bold, anchor="mm")
    draw.text((stamp_x + 80, stamp_y + 75), "VERIFIED SHIPMENT", fill=(37, 99, 235), font=font_small, anchor="mm")
    draw.text((stamp_x + 80, stamp_y + 100), "CHENNAI HUB", fill=(37, 99, 235), font=font_bold, anchor="mm")

    # Bottom legal
    draw.line([(40, h - 50), (w - 40, h - 50)], fill=(226, 232, 240), width=1)
    draw.text((w // 2, h - 30), "Computer generated document valid under GST Rule 138 of Tamil Nadu Goods and Services Tax Rules.", fill=(148, 163, 184), font=font_small, anchor="mm")

    img.save(output_path, "PNG")
    print(f"Generated Image: {output_path}")

def main():
    print(f"Generating 5 sample documents in {DATA_DIR}...")
    for sample in SAMPLES:
        pdf_path = DATA_DIR / f"{sample['id']}.pdf"
        png_path = DATA_DIR / f"{sample['id']}.png"
        generate_pdf(sample, pdf_path)
        generate_image(sample, png_path)
    print("All sample documents successfully generated!")

if __name__ == "__main__":
    main()
