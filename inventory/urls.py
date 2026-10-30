from django.urls import path

from . import views

urlpatterns = [
    path('', views.medicine_list, name='medicine_list'),
    path('add/', views.medicine_add, name='medicine_add'),
    path('edit/<int:pk>/', views.medicine_edit, name='medicine_edit'),
    path('categories/', views.category_list, name='category_list'),
    path('categories/add/', views.category_add, name='category_add'),
    path('categories/edit/<int:pk>/', views.category_edit, name='category_edit'),
    path('suppliers/', views.supplier_list, name='supplier_list'),
    path('suppliers/add/', views.supplier_add, name='supplier_add'),
    path('suppliers/edit/<int:pk>/', views.supplier_edit, name='supplier_edit'),
    path('stock/', views.inventory_list, name='inventory_list'),
    path('stock/<int:pk>/adjust/', views.adjust_stock, name='adjust_stock'),
    path('stock/<int:pk>/write-off/', views.write_off_batch_view, name='write_off_batch'),
    path('movements/', views.stock_movements, name='stock_movements'),
    path('alerts/', views.alerts, name='alerts'),
    path('alerts/write-off-expired/', views.write_off_expired, name='write_off_expired'),
]
