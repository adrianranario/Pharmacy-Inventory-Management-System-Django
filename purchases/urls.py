from django.urls import path

from . import views

urlpatterns = [
    path('', views.purchase_list, name='purchase_list'),
    path('add/', views.purchase_add, name='purchase_add'),
    path('view/<int:pk>/', views.purchase_view, name='purchase_view'),
    path('view/<int:pk>/ordered/', views.purchase_mark_ordered, name='purchase_mark_ordered'),
    path('view/<int:pk>/receive/', views.purchase_receive, name='purchase_receive'),
    path('view/<int:pk>/cancel/', views.purchase_cancel, name='purchase_cancel'),
]
