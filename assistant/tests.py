from decimal import Decimal
from unittest.mock import patch

from django.test import Client, TestCase, override_settings
from django.urls import reverse

from assistant.facts import answer_inventory_question
from assistant.formatting import clean_assistant_answer
from assistant.llm import PharmacyAssistant
from assistant.models import ChatHistory
from core.testing import make_batch, make_medicine, make_user
from pos.models import Sale


@override_settings(EXPIRY_WARNING_DAYS=90)
class AssistantContextTests(TestCase):
    def test_expiry_context_reports_30_and_90_day_windows_separately(self):
        loratadine = make_medicine(code='MED-010', name='Loratadine')
        metformin = make_medicine(code='MED-008', name='Metformin')
        make_batch(loratadine, quantity=69, days=81, batch_no='LATE-90-A')
        make_batch(metformin, quantity=66, days=86, batch_no='LATE-90-B')

        context = PharmacyAssistant().get_system_context()

        self.assertIn('Near Expiry (30 days): 0 batches (0 medicines)', context)
        self.assertIn('Near Expiry (90 days): 2 batches (2 medicines)', context)
        self.assertIn('NEAR EXPIRY WITHIN 90 DAYS:', context)
        self.assertIn('LATE-90-A', context)
        self.assertIn('LATE-90-B', context)

    def test_sales_context_uses_net_sales_for_cashier(self):
        user = make_user(username='cashier', role='cashier')
        Sale.objects.create(
            invoice_no='INV-CTX-1',
            sold_by=user,
            total_amount=Decimal('100.00'),
            refunded_amount=Decimal('10.00'),
        )

        context = PharmacyAssistant().get_system_context(user)

        self.assertIn("Today's Sales: 1 transaction, ₱90.00", context)

    def test_sales_context_is_hidden_without_view_sales_capability(self):
        user = make_user(username='clerk', role='inventory_clerk')

        context = PharmacyAssistant().get_system_context(user)

        self.assertIn("Today's Sales: Not available for this role", context)


class AssistantFormattingTests(TestCase):
    def test_markdown_asterisks_are_removed_and_bullets_are_clean(self):
        raw = (
            "### Near-expiry stock\n\n"
            "**2 medicines** expire within 90 days:\n\n"
            "* **Loratadine**: 69 units\n"
            "- **Metformin**: 66 units"
        )

        cleaned = clean_assistant_answer(raw)

        self.assertNotIn('*', cleaned)
        self.assertIn('Near-expiry stock', cleaned)
        self.assertIn('2 medicines expire within 90 days:', cleaned)
        self.assertIn('• Loratadine: 69 units', cleaned)
        self.assertIn('• Metformin: 66 units', cleaned)


@override_settings(EXPIRY_WARNING_DAYS=90)
class AssistantFactTests(TestCase):
    def test_expiry_answer_uses_exact_30_and_90_day_windows(self):
        loratadine = make_medicine(code='MED-010', name='Loratadine')
        metformin = make_medicine(code='MED-008', name='Metformin')
        make_batch(loratadine, quantity=69, days=81, batch_no='LATE-90-A')
        make_batch(metformin, quantity=66, days=86, batch_no='LATE-90-B')

        answer = answer_inventory_question('How many medicines expire within 90 days?')

        self.assertIn('2 medicines have 2 batches due to expire within 90 days.', answer)
        self.assertIn('Within 30 days: 0 batches.', answer)
        self.assertIn('LATE-90-A', answer)
        self.assertIn('LATE-90-B', answer)
        self.assertNotIn('*', answer)

    def test_expiry_answer_uses_singular_grammar_for_one_batch(self):
        medicine = make_medicine(code='MED-011', name='Paracetamol')
        make_batch(medicine, quantity=20, days=1, batch_no='SOON-1')

        answer = answer_inventory_question('What expires in the next 30 days?')

        self.assertIn('1 medicine has 1 batch due to expire within 30 days.', answer)
        self.assertIn('SOON-1', answer)

    def test_tomorrow_expiry_excludes_today_batches(self):
        medicine = make_medicine(code='MED-012', name='Paracetamol')
        make_batch(medicine, quantity=10, days=0, batch_no='TODAY-1')
        make_batch(medicine, quantity=10, days=1, batch_no='TOMORROW-1')

        answer = answer_inventory_question('What expires tomorrow?')

        self.assertNotIn('TODAY-1', answer)
        self.assertIn('TOMORROW-1', answer)
        self.assertIn('1 medicine has 1 batch due to expire tomorrow.', answer)

    def test_low_stock_answer_lists_exact_stock_and_reorder_level(self):
        medicine = make_medicine(code='LOW-001', name='Paracetamol', reorder_level=5)
        make_batch(medicine, quantity=2, days=30, batch_no='LOW-1')

        answer = answer_inventory_question('Which medicines are low on stock?')

        self.assertIn('1 medicine at or below the reorder level:', answer)
        self.assertIn('Paracetamol [LOW-001]', answer)
        self.assertIn('On hand: 2 tablet', answer)
        self.assertIn('Reorder level: 5 tablet', answer)
        self.assertIn('Suggested order: 8 tablet', answer)
        self.assertNotIn('*', answer)

    def test_expired_answer_reports_expired_batches(self):
        medicine = make_medicine(code='EXP-001', name='Paracetamol')
        make_batch(medicine, quantity=3, days=-1, batch_no='EXP-1')

        answer = answer_inventory_question('Which batches are expired?')

        self.assertIn('1 medicine has 1 expired batch with remaining stock:', answer)
        self.assertIn('EXP-1', answer)
        self.assertNotIn('*', answer)

    def test_expired_guidance_is_role_appropriate(self):
        user = make_user(username='cashier', role='cashier')
        medicine = make_medicine(code='EXP-002', name='Paracetamol')
        make_batch(medicine, quantity=3, days=-1, batch_no='EXP-2')

        answer = answer_inventory_question('Which batches are expired?', user)

        self.assertIn('Ask a pharmacist or inventory clerk', answer)
        self.assertNotIn('Use the Alerts page', answer)

    def test_medicine_expiry_question_is_scoped_to_that_medicine(self):
        paracetamol = make_medicine(code='MED-001', name='Paracetamol')
        loratadine = make_medicine(code='MED-010', name='Loratadine')
        make_batch(paracetamol, quantity=10, days=20, batch_no='PARA-1')
        make_batch(loratadine, quantity=10, days=20, batch_no='LORA-1')

        answer = answer_inventory_question('What is the expiry of Paracetamol?')

        self.assertIn('PARA-1', answer)
        self.assertNotIn('LORA-1', answer)

    def test_medicine_stock_answer_reads_live_batches(self):
        medicine = make_medicine(code='MED-001', name='Paracetamol', reorder_level=5)
        make_batch(medicine, quantity=7, days=30, batch_no='STK-1')

        answer = answer_inventory_question('What is the stock of Paracetamol?')

        self.assertIn('Stock details for Paracetamol:', answer)
        self.assertIn('Sellable stock: 7 tablet', answer)
        self.assertIn('Reorder level: 5 tablet', answer)
        self.assertIn('batch STK-1: 7 units', answer)
        self.assertNotIn('*', answer)

    def test_total_medicines_answer_counts_active_catalog(self):
        make_medicine(code='MED-001', name='Paracetamol')
        make_medicine(code='MED-002', name='Ibuprofen')

        answer = answer_inventory_question('How many medicines are in the catalog?')

        self.assertIn('There are 2 medicines in the active catalog.', answer)

    def test_sales_answer_uses_net_sales_and_respects_role_scope(self):
        user = make_user(username='cashier', role='cashier')
        Sale.objects.create(
            invoice_no='INV-001',
            sold_by=user,
            total_amount=Decimal('100.00'),
            refunded_amount=Decimal('10.00'),
        )

        answer = answer_inventory_question('How were sales today?', user)

        self.assertIn('Your sales: 1 transaction, ₱90.00.', answer)
        self.assertNotIn('*', answer)

    def test_sales_answer_respects_view_sales_capability(self):
        user = make_user(username='clerk', role='inventory_clerk')

        answer = answer_inventory_question('How were sales today?', user)

        self.assertIn(
            'Sales summaries are available to cashiers, pharmacists, and administrators.',
            answer,
        )


class AssistantViewTests(TestCase):
    def test_ask_assistant_returns_database_facts_without_calling_the_llm(self):
        user = make_user(username='admin', role='admin')
        medicine = make_medicine(code='LOW-001', name='Paracetamol', reorder_level=5)
        make_batch(medicine, quantity=2, days=30, batch_no='LOW-1')
        client = Client()
        client.force_login(user)

        with patch(
            'assistant.views.PharmacyAssistant.ask',
            side_effect=AssertionError('LLM should not be called'),
        ):
            response = client.post(
                '/assistant/ask/',
                {'question': 'Which medicines are low on stock?'},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn('Paracetamol [LOW-001]', payload['answer'])
        self.assertNotIn('*', payload['answer'])
        self.assertTrue(
            ChatHistory.objects.filter(
                user=user,
                question='Which medicines are low on stock?',
            ).exists()
        )

    def test_assistant_page_uses_accurate_live_data_note(self):
        user = make_user(username='viewer', role='admin')
        client = Client()
        client.force_login(user)

        response = client.get(reverse('assistant_index'))

        self.assertContains(
            response,
            'Inventory facts are read directly from the current database.',
        )
        self.assertNotContains(response, 'may be imperfect')

    def test_assistant_page_hides_unavailable_suggestions(self):
        user = make_user(username='clerk', role='inventory_clerk')
        client = Client()
        client.force_login(user)

        response = client.get(reverse('assistant_index'))

        self.assertContains(response, 'Which medicines are low on stock?')
        self.assertNotContains(response, 'How were sales this week?')
        self.assertNotContains(response, 'Generate an inventory report')
