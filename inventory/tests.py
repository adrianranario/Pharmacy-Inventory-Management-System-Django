from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from core.testing import make_batch, make_medicine, make_user
from purchases.models import Purchase, PurchaseItem
from inventory.models import Batch, StockMovement
from inventory.services import (
    adjust_batch,
    deduct_fefo,
    expire_batches,
    receive_purchase,
    write_off_batch,
)


class FEFOTests(TestCase):
    def setUp(self):
        self.user = make_user()
        self.medicine = make_medicine()

    def test_earliest_expiry_is_consumed_first(self):
        first = make_batch(self.medicine, quantity=3, days=10, batch_no='EARLY')
        second = make_batch(self.medicine, quantity=10, days=100, batch_no='LATE')

        consumed = deduct_fefo(self.medicine, 5, user=self.user, reference='INV-1')

        first.refresh_from_db()
        second.refresh_from_db()
        self.assertEqual(first.remaining_quantity, 0)
        self.assertEqual(second.remaining_quantity, 8)
        self.assertEqual([(batch.batch_no, taken) for batch, taken in consumed], [('EARLY', 3), ('LATE', 2)])

        movements = list(
            StockMovement.objects.filter(medicine=self.medicine, movement_type='sale').order_by('pk')
        )
        self.assertEqual([movement.quantity for movement in movements], [-3, -2])
        self.assertEqual(movements[0].balance_after, 0)
        self.assertEqual(movements[1].balance_after, 8)

    def test_expired_batches_are_not_sellable(self):
        expired = make_batch(self.medicine, quantity=50, days=-1, batch_no='EXPIRED')
        sellable = make_batch(self.medicine, quantity=2, days=30, batch_no='GOOD')

        with self.assertRaises(ValidationError):
            deduct_fefo(self.medicine, 3, user=self.user)

        expired.refresh_from_db()
        sellable.refresh_from_db()
        self.assertEqual(expired.remaining_quantity, 50)
        self.assertEqual(sellable.remaining_quantity, 2)
        self.assertFalse(StockMovement.objects.filter(movement_type='sale').exists())

    def test_sellable_stock_excludes_expired_batches(self):
        make_batch(self.medicine, quantity=50, days=-1, batch_no='EXPIRED')
        make_batch(self.medicine, quantity=2, days=30, batch_no='GOOD')

        self.assertEqual(self.medicine.total_stock(), 52)
        self.assertEqual(self.medicine.sellable_stock(), 2)

        self.medicine.reorder_level = 5
        self.medicine.save(update_fields=['reorder_level'])
        self.assertTrue(self.medicine.is_low_stock())
        self.assertEqual(self.medicine.suggested_order_quantity(), 8)

    def test_missing_stock_raises(self):
        make_batch(self.medicine, quantity=1, days=30)
        with self.assertRaises(ValidationError):
            deduct_fefo(self.medicine, 2, user=self.user)


class AdjustmentTests(TestCase):
    def setUp(self):
        self.user = make_user()
        self.medicine = make_medicine()
        self.batch = make_batch(self.medicine, quantity=5)

    def test_adjustment_records_the_delta(self):
        movement = adjust_batch(self.batch, 8, 'Cycle count', self.user)
        self.batch.refresh_from_db()
        self.assertEqual(self.batch.remaining_quantity, 8)
        self.assertEqual(movement.quantity, 3)
        self.assertEqual(movement.movement_type, 'adjustment')
        self.assertEqual(movement.balance_after, 8)
        self.assertIsNone(adjust_batch(self.batch, 8, 'No change', self.user))

    def test_adjustment_cannot_go_negative(self):
        with self.assertRaises(ValidationError):
            adjust_batch(self.batch, -1, 'Invalid', self.user)

    def test_write_off_records_loss(self):
        movement = write_off_batch(self.batch, 2, 'Damaged', self.user)
        self.batch.refresh_from_db()
        self.assertEqual(self.batch.remaining_quantity, 3)
        self.assertEqual(movement.quantity, -2)
        self.assertEqual(movement.movement_type, 'writeoff')


class PurchaseReceivingTests(TestCase):
    def setUp(self):
        self.user = make_user()
        self.medicine = make_medicine()
        self.purchase = Purchase.objects.create(
            purchase_no='PO-0001',
            supplier=self.medicine.supplier,
            purchased_by=self.user,
            purchase_date=timezone.localdate(),
            status='draft',
        )
        PurchaseItem.objects.create(
            purchase=self.purchase,
            medicine=self.medicine,
            batch_no='PO-BATCH',
            quantity=4,
            unit_price=Decimal('50.00'),
            expiry_date=timezone.localdate() + timedelta(days=200),
        )

    def test_receiving_creates_batches_and_movements_once(self):
        receive_purchase(self.purchase, self.user)
        self.purchase.refresh_from_db()

        self.assertEqual(self.purchase.status, 'received')
        self.assertEqual(self.purchase.received_by, self.user)
        batches = Batch.objects.filter(medicine=self.medicine)
        self.assertEqual(batches.count(), 1)
        self.assertEqual(batches.first().remaining_quantity, 4)
        movement = StockMovement.objects.get(movement_type='purchase')
        self.assertEqual(movement.quantity, 4)
        self.assertEqual(movement.reference, 'PO-0001')

        with self.assertRaises(ValidationError):
            receive_purchase(self.purchase, self.user)
        self.assertEqual(Batch.objects.filter(medicine=self.medicine).count(), 1)

    def test_cancelled_purchase_cannot_be_received(self):
        self.purchase.status = 'cancelled'
        self.purchase.save(update_fields=['status'])
        with self.assertRaises(ValidationError):
            receive_purchase(self.purchase, self.user)


class ExpiryTests(TestCase):
    def test_expire_batches_zeros_stock_and_records_loss(self):
        medicine = make_medicine()
        batch = make_batch(medicine, quantity=6, days=-3, batch_no='OLD')
        self.user = make_user()

        affected = expire_batches(user=self.user)

        batch.refresh_from_db()
        self.assertEqual(len(affected), 1)
        self.assertEqual(batch.remaining_quantity, 0)
        movement = StockMovement.objects.get(movement_type='expiry')
        self.assertEqual(movement.quantity, -6)
        self.assertEqual(movement.balance_after, 0)
