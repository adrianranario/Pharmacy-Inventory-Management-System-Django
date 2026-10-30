from django.urls import path

from . import views

urlpatterns = [
    path('', views.reports_index, name='reports_index'),
    path('inventory/', views.report_inventory, name='report_inventory'),
    path('low-stock/', views.report_low_stock, name='report_low_stock'),
    path('near-expiry/', views.report_near_expiry, name='report_near_expiry'),
    path('sales/', views.report_sales, name='report_sales'),
    path('purchases/', views.report_purchases, name='report_purchases'),
    path('export/inventory/', views.export_inventory, name='export_inventory'),
    path('export/low-stock/', views.export_low_stock, name='export_low_stock'),
    path('export/near-expiry/', views.export_near_expiry, name='export_near_expiry'),
    path('export/sales/', views.export_sales, name='export_sales'),
    path('export/purchases/', views.export_purchases, name='export_purchases'),
]
