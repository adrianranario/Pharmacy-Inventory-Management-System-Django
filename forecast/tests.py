from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from core.testing import make_batch, make_medicine, make_user
from inventory.models import Batch
from pos.models import Sale, SaleItem
from forecast.models import Forecast
from forecast.services import calculate_forecast, generate_all_forecasts


class ForecastTests(TestCase):
    def setUp(self):
        self.user = make_user(role='pharmacist')
        self.medicine = make_medicine()
        today = timezone.localdate()

        # Ten weeks of steady sales (5 units per week).
        for week in range(10):
            sale = Sale.objects.create(
                invoice_no=f'F-{week:03d}',
                sold_by=self.user,
                subtotal=Decimal('50.00'),
                total_amount=Decimal('50.00'),
                amount_paid=Decimal('50.00'),
                status='completed',
            )
            SaleItem.objects.create(
                sale=sale,
                medicine=self.medicine,
                batch=make_batch(self.medicine, quantity=5, days=365, batch_no=f'FB-{week}'),
                quantity=5,
                price=Decimal('10.00'),
            )
            Sale.objects.filter(pk=sale.pk).update(
                created_at=timezone.now() - timedelta(weeks=week, days=1)
            )

        # Historical sales should not leave stock on hand for the reorder math.
        Batch.objects.filter(medicine=self.medicine).update(remaining_quantity=0)

    def test_forecast_uses_sales_history(self):
        forecast = calculate_forecast(self.medicine)
        self.assertGreater(forecast.forecast_quantity, 0)
        self.assertEqual(forecast.method, 'ses')
        self.assertEqual(forecast.lead_time_days, 7)
        self.assertGreaterEqual(forecast.safety_stock, 0)
        self.assertGreaterEqual(forecast.reorder_suggestion, forecast.forecast_quantity)
        self.assertIsNotNone(forecast.mape)
        self.assertEqual(len(forecast.historical_data), 27)

    def test_forecast_requires_sales_history(self):
        empty = make_medicine(code='EMPTY-1', name='Unused medicine')
        with self.assertRaises(ValidationError):
            calculate_forecast(empty)

    def test_generate_all_skips_medicines_without_history(self):
        make_medicine(code='EMPTY-2', name='Also unused')
        generated, skipped = generate_all_forecasts()
        self.assertTrue(any(forecast.medicine_id == self.medicine.pk for forecast in generated))
        self.assertTrue(any(medicine.code if hasattr(medicine, 'code') else medicine.medicine_code == 'EMPTY-2' for medicine in skipped))
        self.assertTrue(Forecast.objects.filter(medicine=self.medicine).exists())
