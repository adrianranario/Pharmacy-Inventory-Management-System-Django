from django.urls import path

from . import views

urlpatterns = [
    path('', views.sales_list, name='sales_list'),
    path('view/<int:pk>/', views.sale_view, name='sale_view'),
    path('view/<int:pk>/return/', views.return_sale, name='sale_return'),
    path('view/<int:pk>/void/', views.void_sale_view, name='sale_void'),
]
