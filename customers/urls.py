from django.urls import path

from . import views

urlpatterns = [
    path('', views.customer_list, name='customer_list'),
    path('add/', views.customer_add, name='customer_add'),
    path('search/', views.customer_search, name='customer_search'),
    path('<int:pk>/', views.customer_detail, name='customer_detail'),
    path('<int:pk>/edit/', views.customer_edit, name='customer_edit'),
    path('prescriptions/', views.prescription_list, name='prescription_list'),
    path('prescriptions/add/', views.prescription_add, name='prescription_add'),
    path('prescriptions/<int:pk>/edit/', views.prescription_edit, name='prescription_edit'),
]
