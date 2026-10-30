from django.conf import settings
from django.db import models

from inventory.models import Medicine


class Forecast(models.Model):
    METHOD_CHOICES = (
        ('ses', 'Exponential smoothing'),
        ('holt', 'Holt trend'),
        ('mean', 'Average'),
    )

    medicine = models.ForeignKey(Medicine, on_delete=models.CASCADE, related_name='forecasts')
    historical_data = models.JSONField(default=list)
    forecast_quantity = models.IntegerField(default=0)
    reorder_suggestion = models.IntegerField(default=0)
    safety_stock = models.IntegerField(default=0)
    lead_time_days = models.PositiveIntegerField(default=7)
    stock_cover_days = models.IntegerField(null=True, blank=True)
    method = models.CharField(max_length=20, choices=METHOD_CHOICES, default='ses')
    mape = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    forecast_period_start = models.DateField()
    forecast_period_end = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Forecast for {self.medicine.generic_name} - {self.created_at.date()}"
