from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from core.testing import make_medicine, make_user
from inventory.models import Batch
from purchases.models import Purchase


class PurchasePermissionTests(TestCase):
    def setUp(self):
        self.cashier = make_user(username='cashier', role='cashier')
        self.pharmacist = make_user(username='pharmacist', role='pharmacist')
        self.medicine = make_medicine()
        self.supplier = self.medicine.supplier

    def purchase_payload(self):
        return {
            'supplier': self.supplier.pk,
            'purchase_date': timezone.localdate().isoformat(),
            'invoice_no': 'SI-100',
            'notes': '',
            'medicine_id[]': [self.medicine.pk],
            'batch_no[]': ['PO-B1'],
            'quantity[]': ['4'],
            'unit_price[]': ['50.00'],
            'expiry_date[]': [(timezone.localdate() + timedelta(days=365)).isoformat()],
            'action': 'draft',
        }

    def test_cashier_cannot_create_purchase(self):
        self.client.force_login(self.cashier)
        response = self.client.post(reverse('purchase_add'), self.purchase_payload())
        self.assertRedirects(response, reverse('dashboard'))
        self.assertFalse(Purchase.objects.exists())

    def test_pharmacist_can_create_draft_and_receive_once(self):
        self.client.force_login(self.pharmacist)
        response = self.client.post(reverse('purchase_add'), self.purchase_payload())
        purchase = Purchase.objects.get()
        self.assertRedirects(response, reverse('purchase_view', args=[purchase.pk]))
        self.assertEqual(purchase.status, 'draft')
        self.assertFalse(Batch.objects.filter(medicine=self.medicine).exists())

        response = self.client.post(reverse('purchase_mark_ordered', args=[purchase.pk]))
        self.assertRedirects(response, reverse('purchase_view', args=[purchase.pk]))
        purchase.refresh_from_db()
        self.assertEqual(purchase.status, 'ordered')

        response = self.client.post(reverse('purchase_receive', args=[purchase.pk]))
        self.assertRedirects(response, reverse('purchase_view', args=[purchase.pk]))
        purchase.refresh_from_db()
        self.assertEqual(purchase.status, 'received')
        self.assertEqual(Batch.objects.filter(medicine=self.medicine).count(), 1)
        self.assertEqual(Batch.objects.get(medicine=self.medicine).remaining_quantity, 4)

        self.client.post(reverse('purchase_receive', args=[purchase.pk]))
        self.assertEqual(Batch.objects.filter(medicine=self.medicine).count(), 1)

    def test_past_expiry_is_rejected(self):
        self.client.force_login(self.pharmacist)
        payload = self.purchase_payload()
        payload['expiry_date[]'] = [(timezone.localdate() - timedelta(days=1)).isoformat()]
        response = self.client.post(reverse('purchase_add'), payload)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Purchase.objects.exists())
