from io import BytesIO
from django.http import HttpResponse
from django.utils import timezone
from datetime import timedelta

from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors

from docx import Document
from docx.shared import Pt
from docx.enum.table import WD_TABLE_ALIGNMENT

from inventory.models import Medicine, Batch
from pos.models import Sale


def export_inventory_pdf():
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()
    elements = []
    elements.append(Paragraph("PHARMACY INVENTORY REPORT", styles['Title']))
    elements.append(Paragraph(f"Generated: {timezone.now().strftime('%Y-%m-%d %H:%M:%S')}", styles['Normal']))
    elements.append(Spacer(1, 12))
    medicines = Medicine.objects.filter(status=True).select_related('category').prefetch_related('batches').order_by('medicine_code')
    data = [['Code', 'Generic Name', 'Brand', 'Category', 'Purchase Price', 'Selling Price', 'Stock', 'Reorder', 'Unit', 'Shelf']]
    for m in medicines:
        data.append([m.medicine_code, m.generic_name, m.brand_name or 'N/A', m.category.name, f'₱{m.purchase_price}', f'₱{m.selling_price}', str(m.sellable_stock()), str(m.reorder_level), m.unit, m.shelf_location or 'N/A'])
    table = Table(data, repeatRows=1)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#1f4e79')),
        ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,0), 7),
        ('FONTSIZE', (0,1), (-1,-1), 6),
        ('GRID', (0,0), (-1,-1), 0.5, colors.black),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor('#f2f2f2')]),
    ]))
    elements.append(table)
    doc.build(elements)
    pdf = buffer.getvalue()
    buffer.close()
    response = HttpResponse(pdf, content_type='application/pdf')
    response['Content-Disposition'] = 'attachment; filename="Inventory_Report.pdf"'
    return response


def export_inventory_docx():
    doc = Document()
    doc.add_heading('PHARMACY INVENTORY REPORT', 0)
    doc.add_paragraph(f'Generated: {timezone.now().strftime("%Y-%m-%d %H:%M:%S")}')
    medicines = Medicine.objects.filter(status=True).select_related('category').prefetch_related('batches').order_by('medicine_code')
    table = doc.add_table(rows=1, cols=10)
    table.style = 'Table Grid'
    hdr = table.rows[0].cells
    headers = ['Code', 'Generic Name', 'Brand', 'Category', 'Purchase Price', 'Selling Price', 'Stock', 'Reorder', 'Unit', 'Shelf']
    for i, h in enumerate(headers):
        hdr[i].text = h
    for m in medicines:
        row = table.add_row().cells
        row[0].text = m.medicine_code
        row[1].text = m.generic_name
        row[2].text = m.brand_name or 'N/A'
        row[3].text = m.category.name
        row[4].text = f'₱{m.purchase_price}'
        row[5].text = f'₱{m.selling_price}'
        row[6].text = str(m.sellable_stock())
        row[7].text = str(m.reorder_level)
        row[8].text = m.unit
        row[9].text = m.shelf_location or 'N/A'
    buffer = BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    response = HttpResponse(buffer.read(), content_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document')
    response['Content-Disposition'] = 'attachment; filename="Inventory_Report.docx"'
    return response


def export_low_stock_pdf():
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()
    elements = []
    elements.append(Paragraph("LOW STOCK REPORT", styles['Title']))
    elements.append(Paragraph(f"Generated: {timezone.now().strftime('%Y-%m-%d %H:%M:%S')}", styles['Normal']))
    elements.append(Spacer(1, 12))
    medicines = Medicine.objects.filter(status=True).prefetch_related('batches')
    low_stock = [m for m in medicines if m.is_low_stock()]
    data = [['Code', 'Generic Name', 'Brand', 'Current Stock', 'Reorder Level', 'Unit', 'Shelf Location']]
    for m in low_stock:
        data.append([m.medicine_code, m.generic_name, m.brand_name or 'N/A', str(m.sellable_stock()), str(m.reorder_level), m.unit, m.shelf_location or 'N/A'])
    table = Table(data, repeatRows=1)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.red),
        ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,0), 7),
        ('FONTSIZE', (0,1), (-1,-1), 6),
        ('GRID', (0,0), (-1,-1), 0.5, colors.black),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor('#ffe6e6')]),
    ]))
    elements.append(table)
    doc.build(elements)
    pdf = buffer.getvalue()
    buffer.close()
    response = HttpResponse(pdf, content_type='application/pdf')
    response['Content-Disposition'] = 'attachment; filename="Low_Stock_Report.pdf"'
    return response


def export_low_stock_docx():
    doc = Document()
    doc.add_heading('LOW STOCK REPORT', 0)
    doc.add_paragraph(f'Generated: {timezone.now().strftime("%Y-%m-%d %H:%M:%S")}')
    medicines = Medicine.objects.filter(status=True).prefetch_related('batches')
    low_stock = [m for m in medicines if m.is_low_stock()]
    table = doc.add_table(rows=1, cols=7)
    table.style = 'Table Grid'
    hdr = table.rows[0].cells
    for i, h in enumerate(['Code', 'Generic Name', 'Brand', 'Current Stock', 'Reorder Level', 'Unit', 'Shelf Location']):
        hdr[i].text = h
    for m in low_stock:
        row = table.add_row().cells
        row[0].text = m.medicine_code
        row[1].text = m.generic_name
        row[2].text = m.brand_name or 'N/A'
        row[3].text = str(m.sellable_stock())
        row[4].text = str(m.reorder_level)
        row[5].text = m.unit
        row[6].text = m.shelf_location or 'N/A'
    buffer = BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    response = HttpResponse(buffer.read(), content_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document')
    response['Content-Disposition'] = 'attachment; filename="Low_Stock_Report.docx"'
    return response


def export_near_expiry_pdf():
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()
    elements = []
    elements.append(Paragraph("NEAR EXPIRY REPORT (30 DAYS)", styles['Title']))
    elements.append(Paragraph(f"Generated: {timezone.now().strftime('%Y-%m-%d %H:%M:%S')}", styles['Normal']))
    elements.append(Spacer(1, 12))
    today = timezone.now().date()
    batches = Batch.objects.filter(remaining_quantity__gt=0, expiry_date__lte=today + timedelta(days=30)).select_related('medicine').order_by('expiry_date')
    data = [['Medicine Code', 'Medicine', 'Batch No.', 'Remaining Qty', 'Expiry Date', 'Days to Expire']]
    for b in batches:
        data.append([b.medicine.medicine_code, b.medicine.generic_name, b.batch_no, str(b.remaining_quantity), str(b.expiry_date), str(b.days_to_expire())])
    table = Table(data, repeatRows=1)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#ff8c00')),
        ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,0), 7),
        ('FONTSIZE', (0,1), (-1,-1), 6),
        ('GRID', (0,0), (-1,-1), 0.5, colors.black),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor('#fff4e6')]),
    ]))
    elements.append(table)
    doc.build(elements)
    pdf = buffer.getvalue()
    buffer.close()
    response = HttpResponse(pdf, content_type='application/pdf')
    response['Content-Disposition'] = 'attachment; filename="Near_Expiry_Report.pdf"'
    return response


def export_near_expiry_docx():
    doc = Document()
    doc.add_heading('NEAR EXPIRY REPORT (30 DAYS)', 0)
    doc.add_paragraph(f'Generated: {timezone.now().strftime("%Y-%m-%d %H:%M:%S")}')
    today = timezone.now().date()
    batches = Batch.objects.filter(remaining_quantity__gt=0, expiry_date__lte=today + timedelta(days=30)).select_related('medicine').order_by('expiry_date')
    table = doc.add_table(rows=1, cols=6)
    table.style = 'Table Grid'
    hdr = table.rows[0].cells
    for i, h in enumerate(['Medicine Code', 'Medicine', 'Batch No.', 'Remaining Qty', 'Expiry Date', 'Days to Expire']):
        hdr[i].text = h
    for b in batches:
        row = table.add_row().cells
        row[0].text = b.medicine.medicine_code
        row[1].text = b.medicine.generic_name
        row[2].text = b.batch_no
        row[3].text = str(b.remaining_quantity)
        row[4].text = str(b.expiry_date)
        row[5].text = str(b.days_to_expire())
    buffer = BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    response = HttpResponse(buffer.read(), content_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document')
    response['Content-Disposition'] = 'attachment; filename="Near_Expiry_Report.docx"'
    return response


def export_sales_pdf():
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter)
    styles = getSampleStyleSheet()
    elements = []
    elements.append(Paragraph("SALES REPORT", styles['Title']))
    elements.append(Paragraph(f"Generated: {timezone.now().strftime('%Y-%m-%d %H:%M:%S')}", styles['Normal']))
    elements.append(Spacer(1, 12))
    sales = Sale.objects.select_related('sold_by').order_by('-created_at')
    data = [['Invoice No.', 'Customer', 'Customer Type', 'Subtotal', 'Discount', 'Total Amount', 'Amount Paid', 'Change', 'Cashier', 'Date']]
    for s in sales:
        data.append([s.invoice_no, s.customer_name or 'Walk-in', s.get_customer_type_display(), f'₱{s.subtotal}', f'₱{s.discount_amount}', f'₱{s.total_amount}', f'₱{s.amount_paid}', f'₱{s.change_amount}', s.sold_by.username, s.created_at.strftime('%Y-%m-%d %H:%M')])
    table = Table(data, repeatRows=1)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#2e7d32')),
        ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,0), 6),
        ('FONTSIZE', (0,1), (-1,-1), 5),
        ('GRID', (0,0), (-1,-1), 0.5, colors.black),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor('#f1f8e9')]),
    ]))
    elements.append(table)
    doc.build(elements)
    pdf = buffer.getvalue()
    buffer.close()
    response = HttpResponse(pdf, content_type='application/pdf')
    response['Content-Disposition'] = 'attachment; filename="Sales_Report.pdf"'
    return response


def export_sales_docx():
    doc = Document()
    doc.add_heading('SALES REPORT', 0)
    doc.add_paragraph(f'Generated: {timezone.now().strftime("%Y-%m-%d %H:%M:%S")}')
    sales = Sale.objects.select_related('sold_by').order_by('-created_at')
    table = doc.add_table(rows=1, cols=10)
    table.style = 'Table Grid'
    hdr = table.rows[0].cells
    for i, h in enumerate(['Invoice No.', 'Customer', 'Customer Type', 'Subtotal', 'Discount', 'Total Amount', 'Amount Paid', 'Change', 'Cashier', 'Date']):
        hdr[i].text = h
    for s in sales:
        row = table.add_row().cells
        row[0].text = s.invoice_no
        row[1].text = s.customer_name or 'Walk-in'
        row[2].text = s.get_customer_type_display()
        row[3].text = f'₱{s.subtotal}'
        row[4].text = f'₱{s.discount_amount}'
        row[5].text = f'₱{s.total_amount}'
        row[6].text = f'₱{s.amount_paid}'
        row[7].text = f'₱{s.change_amount}'
        row[8].text = s.sold_by.username
        row[9].text = s.created_at.strftime('%Y-%m-%d %H:%M')
    buffer = BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    response = HttpResponse(buffer.read(), content_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document')
    response['Content-Disposition'] = 'attachment; filename="Sales_Report.docx"'
    return response
