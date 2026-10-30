import pyotp
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from core.permissions import has_capability
from core.testing import make_batch, make_medicine, make_user
from customers.models import Customer, Prescription
from pos.services import checkout_cart


class PermissionTests(TestCase):
    def setUp(self):
        self.cashier = make_user(username='cashier', role='cashier')
        self.pharmacist = make_user(username='pharmacist', role='pharmacist')
        self.admin = make_user(username='admin', role='admin')
        self.superuser = make_user(username='root', role='cashier', is_superuser=True, is_staff=True)

    def test_capability_matrix(self):
        self.assertTrue(has_capability(self.admin, 'manage_users'))
        self.assertFalse(has_capability(self.pharmacist, 'manage_users'))
        self.assertTrue(has_capability(self.pharmacist, 'void_sale') is False)
        self.assertTrue(has_capability(self.cashier, 'sell'))
        self.assertFalse(has_capability(self.cashier, 'view_reports'))
        self.assertTrue(has_capability(self.superuser, 'manage_users'))

    def test_cashier_redirected_from_reports(self):
        self.client.force_login(self.cashier)
        response = self.client.get(reverse('reports_index'))
        self.assertRedirects(response, reverse('dashboard'))

    def test_logout_requires_post_and_redirects_to_login(self):
        self.client.force_login(self.cashier)

        self.assertEqual(self.client.get(reverse('logout')).status_code, 405)

        dashboard = self.client.get(reverse('dashboard'))
        self.assertContains(dashboard, f'action="{reverse("logout")}"', count=2)
        self.assertNotContains(dashboard, f'href="{reverse("logout")}"')

        response = self.client.post(reverse('logout'))
        self.assertRedirects(response, reverse('login'))
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_pharmacist_can_view_reports(self):
        self.client.force_login(self.pharmacist)
        response = self.client.get(reverse('reports_index'))
        self.assertEqual(response.status_code, 200)

    def test_cashier_redirected_from_user_admin(self):
        self.client.force_login(self.cashier)
        response = self.client.get(reverse('user_list'))
        self.assertRedirects(response, reverse('dashboard'))

    def test_cashier_redirected_from_inventory_pages(self):
        self.client.force_login(self.cashier)
        for name in ('medicine_list', 'inventory_list', 'stock_movements', 'alerts'):
            response = self.client.get(reverse(name))
            self.assertRedirects(response, reverse('dashboard'), msg_prefix=name)

    def test_cashier_redirected_from_prescription_register(self):
        self.client.force_login(self.cashier)
        response = self.client.get(reverse('prescription_list'))
        self.assertRedirects(response, reverse('dashboard'))

    def test_pharmacist_can_view_inventory(self):
        self.client.force_login(self.pharmacist)
        for name in ('medicine_list', 'inventory_list', 'stock_movements', 'alerts'):
            self.assertEqual(self.client.get(reverse(name)).status_code, 200, name)

    def test_customer_detail_hides_prescriptions_from_cashier(self):
        customer = Customer.objects.create(name='Prescription Privacy')
        medicine = make_medicine()
        Prescription.objects.create(
            customer=customer,
            medicine=medicine,
            rx_no='RX-PRIVATE-1',
            prescriber='Dr. Privacy',
            issued_date=timezone.localdate(),
            directions='Once daily',
            created_by=self.pharmacist,
        )

        self.client.force_login(self.cashier)
        response = self.client.get(reverse('customer_detail', args=[customer.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'RX-PRIVATE-1')

        self.client.force_login(self.pharmacist)
        response = self.client.get(reverse('customer_detail', args=[customer.pk]))
        self.assertContains(response, 'RX-PRIVATE-1')

    def test_cashier_cannot_export_reports_through_assistant(self):
        self.client.force_login(self.cashier)
        response = self.client.post(reverse('ask_assistant'), {'question': 'download sales pdf'})
        payload = response.json()
        self.assertNotIn('download_pdf', payload)
        self.assertIn('pharmacists and administrators', payload['answer'])

    def test_deactivated_user_session_is_ended(self):
        self.client.force_login(self.cashier)
        self.cashier.status = False
        self.cashier.save(update_fields=['status'])

        response = self.client.get(reverse('dashboard'))

        self.assertRedirects(response, reverse('login'))

    def test_user_with_sales_cannot_be_deleted(self):
        medicine = make_medicine()
        make_batch(medicine, quantity=2, days=90)
        checkout_cart(
            cart=[{'id': medicine.pk, 'quantity': 1}],
            user=self.cashier,
            amount_paid='200',
        )

        self.client.force_login(self.admin)
        response = self.client.post(reverse('user_delete', args=[self.cashier.pk]))

        self.assertRedirects(response, reverse('user_list'))
        self.assertTrue(type(self.cashier).objects.filter(pk=self.cashier.pk).exists())

    def test_admin_can_view_users(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse('user_list'))
        self.assertEqual(response.status_code, 200)

    def test_anonymous_is_sent_to_login(self):
        response = self.client.get(reverse('reports_index'))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('login'), response.url)


class TwoFactorTests(TestCase):
    def setUp(self):
        self.user = make_user(username='twofactor', role='cashier', email='twofactor@example.com')
        self.user.otp_secret = pyotp.random_base32()
        self.user.otp_enabled = True
        self.user.save(update_fields=['otp_secret', 'otp_enabled'])

    def test_login_asks_for_code_then_signs_in(self):
        response = self.client.post(reverse('login'), {'username': 'twofactor', 'password': 'Test-pass-123'})
        self.assertRedirects(response, reverse('otp_verify'))
        self.assertNotIn('_auth_user_id', self.client.session)

        code = pyotp.TOTP(self.user.otp_secret).now()
        response = self.client.post(reverse('otp_verify'), {'code': code})
        self.assertRedirects(response, reverse('dashboard'))
        self.assertEqual(int(self.client.session['_auth_user_id']), self.user.pk)

    def test_wrong_code_keeps_user_signed_out(self):
        self.client.post(reverse('login'), {'username': 'twofactor', 'password': 'Test-pass-123'})
        response = self.client.post(reverse('otp_verify'), {'code': '000000'})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_disabled_account_cannot_sign_in(self):
        self.user.otp_enabled = False
        self.user.status = False
        self.user.save(update_fields=['otp_enabled', 'status'])
        response = self.client.post(reverse('login'), {'username': 'twofactor', 'password': 'Test-pass-123'})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('_auth_user_id', self.client.session)


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class PasswordResetTests(TestCase):
    def test_reset_email_is_sent_for_known_address(self):
        user = make_user(username='resetme', role='cashier', email='reset@example.com')
        response = self.client.post(reverse('password_reset'), {'email': user.email})
        self.assertRedirects(response, reverse('password_reset_done'))
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('password', mail.outbox[0].subject.lower())
        self.assertIn('/accounts/password/reset/', mail.outbox[0].body)
