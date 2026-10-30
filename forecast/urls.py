from django.urls import path

from . import views

urlpatterns = [
    path('', views.forecast_index, name='forecast_index'),
    path('generate/<int:pk>/', views.generate_forecast, name='generate_forecast'),
    path('generate-all/', views.generate_all, name='generate_all_forecasts'),
]
