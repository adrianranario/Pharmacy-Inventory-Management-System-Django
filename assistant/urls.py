from django.urls import path

from . import views

urlpatterns = [
    path('', views.assistant_index, name='assistant_index'),
    path('ask/', views.ask_assistant, name='ask_assistant'),
    path('thread/new/', views.new_thread, name='assistant_new_thread'),
    path('download/pdf/', views.download_pdf, name='assistant_download_pdf'),
    path('download/docx/', views.download_docx, name='assistant_download_docx'),
    path('report/inventory/pdf/', views.report_inventory_pdf, name='report_inventory_pdf'),
    path('report/inventory/docx/', views.report_inventory_docx, name='report_inventory_docx'),
    path('report/low-stock/pdf/', views.report_low_stock_pdf, name='report_low_stock_pdf'),
    path('report/low-stock/docx/', views.report_low_stock_docx, name='report_low_stock_docx'),
    path('report/near-expiry/pdf/', views.report_near_expiry_pdf, name='report_near_expiry_pdf'),
    path('report/near-expiry/docx/', views.report_near_expiry_docx, name='report_near_expiry_docx'),
    path('report/sales/pdf/', views.report_sales_pdf, name='report_sales_pdf'),
    path('report/sales/docx/', views.report_sales_docx, name='report_sales_docx'),
]
