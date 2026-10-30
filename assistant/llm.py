import requests

from django.conf import settings
from django.utils import timezone

from core.permissions import has_capability
from inventory.models import Medicine, Batch
from pos.models import Sale


def _count_label(count, singular, plural=None):
    return f"{count} {singular if count == 1 else (plural or singular + 's')}"


class PharmacyAssistant:
    def __init__(self):
        self.api_key = getattr(settings, 'GROQ_API_KEY', '')
        self.model = getattr(settings, 'LLM_MODEL', 'qwen/qwen3.8-27b')
        self.base_url = getattr(settings, 'LLM_BASE_URL', 'https://api.groq.com/openai/v1/chat/completions')
    
    def get_system_context(self, user=None):
        today = timezone.localdate()
        warning_days = getattr(settings, 'EXPIRY_WARNING_DAYS', 90)
        medicines = Medicine.objects.filter(status=True).select_related('category').prefetch_related('batches')
        low_stock = [m for m in medicines if m.is_low_stock()]
        batches = list(
            Batch.objects.filter(remaining_quantity__gt=0)
            .select_related('medicine')
            .order_by('expiry_date')
        )
        near_expiry_30 = [b for b in batches if b.is_near_expiry(30)]
        near_expiry_warning = [b for b in batches if b.is_near_expiry(warning_days)]
        expired = [b for b in batches if b.is_expired()]
        near_expiry_30_medicines = {b.medicine_id for b in near_expiry_30}
        near_expiry_warning_medicines = {b.medicine_id for b in near_expiry_warning}
        near_expiry_30_batches_label = _count_label(len(near_expiry_30), 'batch', 'batches')
        near_expiry_30_medicines_label = _count_label(len(near_expiry_30_medicines), 'medicine')
        near_expiry_warning_batches_label = _count_label(len(near_expiry_warning), 'batch', 'batches')
        near_expiry_warning_medicines_label = _count_label(len(near_expiry_warning_medicines), 'medicine')
        sales_today = Sale.objects.filter(created_at__date=today).exclude(status='voided')
        if user is not None:
            if not has_capability(user, 'view_sales'):
                sales_today = sales_today.none()
            elif (
                not getattr(user, 'is_superuser', False)
                and getattr(user, 'role', None) not in {'admin', 'pharmacist'}
            ):
                sales_today = sales_today.filter(sold_by=user)
        total_today = sum(s.net_total for s in sales_today)
        sales_label = f"{_count_label(sales_today.count(), 'transaction')}, ₱{total_today:,.2f}"
        if user is not None and not has_capability(user, 'view_sales'):
            sales_label = 'Not available for this role'
        
        context = f"""You are a STRICTLY DOMAIN-LIMITED Pharmacy Inventory Management System AI Assistant.

RULES (MUST FOLLOW):
- ONLY answer about pharmacy inventory, stock levels, medicines, batches, expiry dates, purchases, sales, and reports
- ABSOLUTELY NO medical diagnosis, treatment advice, prescriptions, drug interactions, dosages for conditions, or medical recommendations
- If asked for medical advice, politely refuse and redirect to inventory queries
- Base ALL answers ONLY on the provided system data
- Be concise, accurate, and helpful
- The 30-day and {warning_days}-day expiry windows are separate. A batch outside the 30-day window can still be inside the {warning_days}-day window. Never infer one count from the other.

RESPONSE STYLE:
- Write in warm, clear, professional English for pharmacy staff.
- Use plain text only. Do not use Markdown, asterisks, hash signs, underscores for emphasis, or backticks.
- Start with a short summary, then use short section labels.
- Use numbered lists for multiple items and put each detail on its own line.
- Do not use tables or code blocks.
- Keep the answer concise and easy to scan.

CURRENT SYSTEM DATA:
- Total Medicines: {medicines.count()}
- Low Stock Items: {len(low_stock)}
- Near Expiry (30 days): {near_expiry_30_batches_label} ({near_expiry_30_medicines_label})
- Near Expiry ({warning_days} days): {near_expiry_warning_batches_label} ({near_expiry_warning_medicines_label})
- Expired Batches: {len(expired)}
- Today's Sales: {sales_label}

LOW STOCK DETAILS:
{chr(10).join([f'- {m.generic_name} ({m.brand_name or "N/A"}): {m.sellable_stock()}/{m.reorder_level} {m.unit}' for m in low_stock[:10]]) or '- None'}

NEAR EXPIRY WITHIN 30 DAYS:
{chr(10).join([f'- {b.medicine.generic_name} ({b.medicine.brand_name or "N/A"}) / batch {b.batch_no}: {b.remaining_quantity} units, expires {b.expiry_date} ({b.days_to_expire()} days)' for b in near_expiry_30[:10]]) or '- None'}

NEAR EXPIRY WITHIN {warning_days} DAYS:
{chr(10).join([f'- {b.medicine.generic_name} ({b.medicine.brand_name or "N/A"}) / batch {b.batch_no}: {b.remaining_quantity} units, expires {b.expiry_date} ({b.days_to_expire()} days)' for b in near_expiry_warning[:20]]) or '- None'}

EXPIRED BATCHES:
{chr(10).join([f'- {b.medicine.generic_name} ({b.medicine.brand_name or "N/A"}) / batch {b.batch_no}: {b.remaining_quantity} units, expired {b.expiry_date}' for b in expired[:10]]) or '- None'}

MEDICINES CATALOG (Sample):
{chr(10).join([f'- {m.medicine_code}: {m.generic_name} ({m.brand_name or "N/A"}) - Stock:{m.sellable_stock()} {m.unit} - ₱{m.selling_price} - Shelf:{m.shelf_location or "N/A"}' for m in medicines[:15]])}
"""
        return context
    
    def ask(self, question, user):
        if not self.api_key:
            return "API key not configured. Please set GROQ_API_KEY in your environment or .env file. Get a free key at https://console.groq.com/keys"
        
        blocked = ['diagnose', 'diagnosis', 'prescribe', 'prescription', 'treatment', 'cure', 'dosage for', 'how much to take for', 'drug interaction']
        q_lower = question.lower()
        if any(b in q_lower for b in blocked):
            return "I'm sorry, but I can only assist with inventory-related queries. I cannot provide medical diagnosis, treatment advice, prescriptions, or dosage recommendations. Please ask about stock levels, medicines, expiry dates, or sales instead."
        
        system_context = self.get_system_context(user)
        warning_days = getattr(settings, 'EXPIRY_WARNING_DAYS', 90)
        system_prompt = system_context + f"\n\nYou must only answer using this data. If information isn't available, say so clearly. For expiry questions, use the exact 30-day and {warning_days}-day counts above; do not assume the {warning_days}-day count is zero just because the 30-day count is zero. Use a friendly, professional tone and plain text only. Never use asterisks or Markdown; use short section labels and numbered lists instead.\n\nNEVER say you cannot generate files. You are integrated with a file export system - if asked to download/export as PDF or Word/DOCX, provide a complete formatted report with title, details, and data ready to export. The system will handle the download."
        
        try:
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": question}
                ],
                "temperature": 0.1,
                "max_tokens": 600,
                "top_p": 0.9
            }
            response = requests.post(self.base_url, headers=headers, json=payload, timeout=90)
            if response.status_code != 200:
                try:
                    err = response.json()
                    return f"Groq Error ({response.status_code}): {err.get('error', {}).get('message', response.text)}"
                except:
                    return f"Groq Error ({response.status_code}): {response.text}"
            data = response.json()
            answer = data['choices'][0]['message']['content']
            # Force override if model refuses
            ql = question.lower()
            if any(x in answer.lower() for x in ['cannot generate', 'cannot export', 'text-based ai', 'cannot provide a downloadable']) and any(x in ql for x in ['download', 'pdf', 'word', 'docx', 'export']):
                return "PHARMACY INVENTORY REPORT\n\n" + self.get_system_context(user).split('CURRENT SYSTEM DATA:')[1] if 'CURRENT SYSTEM DATA:' in self.get_system_context(user) else answer
            return answer
        except requests.exceptions.Timeout:
            return "Request timed out. The model is taking too long to respond. Please try again with a shorter question."
        except requests.exceptions.RequestException as e:
            return f"Error connecting to LLM: {str(e)}. Please check your API key and internet connection."
        except Exception as e:
            return f"Error: {str(e)}"
