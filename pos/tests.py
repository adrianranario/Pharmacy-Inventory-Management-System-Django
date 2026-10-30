from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from core.testing import make_batch, make_medicine, make_user
from customers.models import Customer
from inventory.models import StockMovement
from pos.models import Sale, SaleReturn
from pos.services import checkout_cart, process_return, void_sale


class CheckoutTests(TestCase):
    def setUp(self):
        self.user = make_user(role='cashier')
        self.medicine = make_medicine(price='100.00')
        self.first = make_batch(self.medicine, quantity=2, days=10, batch_no='A')
        self.second = make_batch(self.medicine, quantity=5, days=90, batch_no='B')

    def test_checkout_uses_server_prices_and_fefo(self):
        sale = checkout_cart(
            cart=[{'id': self.medicine.pk, 'quantity': 3, 'price': '1.00'}],
            user=self.user,
            amount_paid='500',
        )

        self.assertEqual(sale.subtotal, Decimal('300.00'))
        self.assertEqual(sale.total_amount, Decimal('300.00'))
        self.assertEqual(sale.amount_paid, Decimal('500.00'))
        self.assertEqual(sale.change_amount, Decimal('200.00'))
        self.assertEqual(sale.items.count(), 2)
        self.assertEqual([item.quantity for item in sale.items.order_by('batch__expiry_date')], [2, 1])

        self.first.refresh_from_db()
        self.second.refresh_from_db()
        self.assertEqual(self.first.remaining_quantity, 0)
        self.assertEqual(self.second.remaining_quantity, 4)
        self.assertTrue(sale.invoice_no)
        self.assertTrue(sale.or_number)
        self.assertEqual(sale.status, 'completed')

    def test_search_reports_only_sellable_stock(self):
        make_batch(self.medicine, quantity=40, days=-1, batch_no='EXPIRED')
        self.client.force_login(self.user)

        response = self.client.get(reverse('pos_search'), {'q': self.medicine.medicine_code})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload), 1)
        self.assertEqual(payload[0]['stock'], 7)

    def test_senior_sale_requires_id_number(self):
        medicine = make_medicine(code='MED-NO-ID', name='Metformin', price='112.00')
        make_batch(medicine, quantity=10, days=90)

        with self.assertRaises(ValidationError):
            checkout_cart(
                cart=[{'id': medicine.pk, 'quantity': 1}],
                user=self.user,
                customer_type='senior_citizen',
                customer_name='No ID Customer',
                amount_paid='100',
            )

    def test_senior_discount_uses_vat_exempt_basis(self):
        medicine = make_medicine(code='MED-SENIOR', name='Amlodipine', price='112.00')
        make_batch(medicine, quantity=10, days=90)
        sale = checkout_cart(
            cart=[{'id': medicine.pk, 'quantity': 1}],
            user=self.user,
            customer_type='senior_citizen',
            customer_name='Lola Maria',
            id_no='SC-001',
            amount_paid='100',
        )
        self.assertEqual(sale.subtotal, Decimal('112.00'))
        self.assertEqual(sale.vat_exempt, Decimal('12.00'))
        self.assertEqual(sale.discount_amount, Decimal('20.00'))
        self.assertEqual(sale.total_amount, Decimal('80.00'))
        self.assertEqual(sale.change_amount, Decimal('20.00'))
        self.assertEqual(sale.customer.name, 'Lola Maria')
        self.assertEqual(sale.customer.loyalty_points, 0)

    def test_loyalty_points_are_awarded(self):
        medicine = make_medicine(code='MED-LOYAL', name='Losartan', price='125.00')
        make_batch(medicine, quantity=10, days=90)
        sale = checkout_cart(
            cart=[{'id': medicine.pk, 'quantity': 2}],
            user=self.user,
            customer_name='Maria Santos',
            amount_paid='250',
        )
        self.assertEqual(sale.total_amount, Decimal('250.00'))
        self.assertEqual(Customer.objects.get(name='Maria Santos').loyalty_points, 2)

    def test_underpayment_rolls_back(self):
        with self.assertRaises(ValidationError):
            checkout_cart(
                cart=[{'id': self.medicine.pk, 'quantity': 1}],
                user=self.user,
                amount_paid='99.99',
            )
        self.assertEqual(Sale.objects.count(), 0)
        self.first.refresh_from_db()
        self.assertEqual(self.first.remaining_quantity, 2)

    def test_insufficient_stock_rolls_back(self):
        with self.assertRaises(ValidationError):
            checkout_cart(
                cart=[{'id': self.medicine.pk, 'quantity': 99}],
                user=self.user,
                amount_paid='10000',
            )
        self.assertEqual(Sale.objects.count(), 0)
        self.assertEqual(self.first.remaining_quantity, 2)
        self.assertEqual(self.second.remaining_quantity, 5)

    def test_empty_cart_is_rejected(self):
        with self.assertRaises(ValidationError):
            checkout_cart(cart=[], user=self.user, amount_paid='100')


class VoidAndReturnTests(TestCase):
    def setUp(self):
        self.user = make_user(role='admin')
        self.medicine = make_medicine(price='100.00')
        self.batch = make_batch(self.medicine, quantity=5, days=90, batch_no='R1')
        self.sale = checkout_cart(
            cart=[{'id': self.medicine.pk, 'quantity': 2}],
            user=self.user,
            customer_name='Walk-in Customer',
            amount_paid='200',
        )

    def test_void_restores_stock_and_marks_sale_voided(self):
        void_sale(self.sale, self.user, 'Duplicate transaction')
        self.sale.refresh_from_db()
        self.batch.refresh_from_db()

        self.assertEqual(self.sale.status, 'voided')
        self.assertEqual(self.sale.void_reason, 'Duplicate transaction')
        self.assertEqual(self.batch.remaining_quantity, 5)
        self.assertTrue(StockMovement.objects.filter(movement_type='void', quantity=2).exists())

        with self.assertRaises(ValidationError):
            void_sale(self.sale, self.user, 'Again')

    def test_return_restores_stock_and_prorates_refund(self):
        item = self.sale.items.first()
        sale_return = process_return(
            self.sale,
            {item.pk: 1},
            'Customer changed their mind',
            self.user,
        )
        self.sale.refresh_from_db()
        self.batch.refresh_from_db()
        item.refresh_from_db()

        self.assertEqual(sale_return.total_amount, Decimal('100.00'))
        self.assertEqual(self.sale.refunded_amount, Decimal('100.00'))
        self.assertEqual(self.sale.status, 'partially_returned')
        self.assertEqual(item.returned_quantity, 1)
        self.assertEqual(self.batch.remaining_quantity, 4)
        self.assertTrue(StockMovement.objects.filter(movement_type='return', quantity=1).exists())

    def test_returning_everything_marks_sale_returned(self):
        item = self.sale.items.first()
        process_return(self.sale, {item.pk: 2}, 'Full refund', self.user)
        self.sale.refresh_from_db()
        self.batch.refresh_from_db()
        self.assertEqual(self.sale.status, 'returned')
        self.assertEqual(self.sale.refunded_amount, Decimal('200.00'))
        self.assertEqual(self.batch.remaining_quantity, 5)

    def test_cannot_return_more_than_sold(self):
        item = self.sale.items.first()
        with self.assertRaises(ValidationError):
            process_return(self.sale, {item.pk: 3}, 'Too many', self.user)
        self.assertFalse(SaleReturn.objects.exists())


class ReceiptViewTests(TestCase):
    def test_receipt_renders_with_vat_breakdown(self):
        user = make_user(role='cashier')
        medicine = make_medicine()
        make_batch(medicine, quantity=5, days=90)
        sale = checkout_cart(
            cart=[{'id': medicine.pk, 'quantity': 1}],
            user=user,
            amount_paid='500',
        )
        self.client.force_login(user)
        response = self.client.get(reverse('pos_receipt', args=[sale.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, sale.invoice_no)
        content = response.content.decode()
        self.assertIn('VAT', content)

    def test_receipt_zeroes_vat_for_exempt_senior_sale(self):
        user = make_user(username='senior-cashier', role='cashier')
        medicine = make_medicine(code='MED-RX-VAT', name='Amlodipine', price='112.00')
        make_batch(medicine, quantity=5, days=90)
        sale = checkout_cart(
            cart=[{'id': medicine.pk, 'quantity': 1}],
            user=user,
            customer_type='senior_citizen',
            customer_name='Lola Maria',
            id_no='SC-001',
            amount_paid='100',
        )
        self.client.force_login(user)
        response = self.client.get(reverse('pos_receipt', args=[sale.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['vat_amount'], Decimal('0.00'))
        self.assertEqual(response.context['vatable_sales'], Decimal('0.00'))
        self.assertEqual(response.context['exempt_sale'], Decimal('100.00'))
        self.assertContains(response, 'VAT-exempt sales')
