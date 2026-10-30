from django.urls import path

from . import views

urlpatterns = [
    path('', views.pos_index, name='pos_index'),
    path('search/', views.search_medicine, name='pos_search'),
    path('checkout/', views.checkout, name='pos_checkout'),
    path('receipt/<int:pk>/', views.receipt, name='pos_receipt'),
]
