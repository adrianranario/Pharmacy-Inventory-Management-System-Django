from io import BytesIO

from django.http import HttpResponse
from django.utils import timezone
from xlsxwriter import Workbook


def _write_sheet(workbook, sheet_name, title, headers, rows, widths=None):
    sheet = workbook.add_worksheet(sheet_name[:31])
    heading = workbook.add_format({'bold': True, 'font_size': 14, 'font_color': '#111827'})
    sub = workbook.add_format({'font_color': '#6b7280', 'italic': True})
    header = workbook.add_format({'bold': True, 'bg_color': '#f4f4f5', 'border': 1, 'border_color': '#e4e4e7'})
    cell = workbook.add_format({'border': 1, 'border_color': '#e4e4e7'})
    money = workbook.add_format({'border': 1, 'border_color': '#e4e4e7', 'num_format': '#,##0.00'})

    sheet.write(0, 0, title, heading)
    sheet.write(1, 0, f'Generated {timezone.localtime():%Y-%m-%d %H:%M} by Pharmacy IMS', sub)
    for column, value in enumerate(headers):
        sheet.write(3, column, value, header)

    for row_index, row in enumerate(rows, start=4):
        for column, value in enumerate(row):
            if isinstance(value, (int, float)):
                sheet.write_number(row_index, column, value, money)
            else:
                sheet.write(row_index, column, '' if value is None else str(value), cell)

    for column, width in enumerate(widths or [24] * len(headers)):
        sheet.set_column(column, column, width)
    sheet.freeze_panes(4, 0)
    sheet.autofilter(3, 0, max(3, len(rows) + 3), max(0, len(headers) - 1))


def xlsx_response(filename, title, headers, rows, widths=None):
    buffer = BytesIO()
    workbook = Workbook(buffer, {'in_memory': True})
    _write_sheet(workbook, 'Report', title, headers, rows, widths)
    workbook.close()
    buffer.seek(0)
    response = HttpResponse(
        buffer.getvalue(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


def inventory_export(medicines):
    rows = [
        [
            m.medicine_code,
            m.generic_name,
            m.brand_name or '',
            m.category.name,
            m.stock_on_hand if hasattr(m, 'stock_on_hand') else m.sellable_stock(),
            m.unit,
            m.reorder_level,
            float(m.purchase_price),
            float(m.selling_price),
            m.shelf_location or '',
            'Active' if m.status else 'Inactive',
        ]
        for m in medicines
    ]
    return xlsx_response(
        f'inventory-{timezone.localdate():%Y%m%d}.xlsx',
        'Inventory valuation report',
        ['Code', 'Generic name', 'Brand', 'Category', 'Stock', 'Unit', 'Reorder level', 'Cost', 'Selling price', 'Shelf', 'Status'],
        rows,
        [14, 30, 20, 18, 10, 10, 12, 12, 12, 12, 10],
    )


def low_stock_export(medicines):
    rows = [
        [m.medicine_code, m.generic_name, m.brand_name or '', m.sellable_stock(), m.reorder_level, m.unit, m.supplier.name if m.supplier else '']
        for m in medicines
    ]
    return xlsx_response(
        f'low-stock-{timezone.localdate():%Y%m%d}.xlsx',
        'Low stock report',
        ['Code', 'Medicine', 'Brand', 'Stock', 'Reorder level', 'Unit', 'Supplier'],
        rows,
        [14, 30, 20, 10, 12, 10, 22],
    )


def near_expiry_export(batches):
    rows = [
        [b.medicine.medicine_code, b.medicine.generic_name, b.batch_no, b.remaining_quantity, b.expiry_date.isoformat(), b.days_to_expire()]
        for b in batches
    ]
    return xlsx_response(
        f'near-expiry-{timezone.localdate():%Y%m%d}.xlsx',
        'Near expiry report',
        ['Code', 'Medicine', 'Batch', 'Quantity', 'Expiry', 'Days left'],
        rows,
        [14, 30, 18, 10, 12, 10],
    )


def sales_export(sales):
    rows = [
        [
            s.invoice_no,
            s.or_number or '',
            s.created_at.strftime('%Y-%m-%d %H:%M'),
            s.customer_name or 'Walk-in',
            s.get_payment_method_display(),
            float(s.subtotal),
            float(s.discount_amount),
            float(s.total_amount),
            float(s.refunded_amount),
            float(s.net_total),
            s.get_status_display(),
            s.sold_by.username,
        ]
        for s in sales
    ]
    return xlsx_response(
        f'sales-{timezone.localdate():%Y%m%d}.xlsx',
        'Sales report',
        ['Invoice', 'OR No.', 'Date', 'Customer', 'Payment', 'Subtotal', 'Discount', 'Total', 'Refunded', 'Net', 'Status', 'Cashier'],
        rows,
        [18, 14, 18, 26, 12, 12, 12, 12, 12, 12, 14, 14],
    )


def purchases_export(purchases):
    rows = [
        [
            p.purchase_no,
            p.purchase_date.isoformat(),
            p.supplier.name,
            p.invoice_no,
            p.get_status_display(),
            float(p.total_amount),
            p.purchased_by.username,
            p.received_at.strftime('%Y-%m-%d %H:%M') if p.received_at else '',
        ]
        for p in purchases
    ]
    return xlsx_response(
        f'purchases-{timezone.localdate():%Y%m%d}.xlsx',
        'Purchases report',
        ['PO No.', 'Date', 'Supplier', 'Supplier invoice', 'Status', 'Total', 'Created by', 'Received at'],
        rows,
        [18, 12, 26, 18, 12, 12, 16, 18],
    )
