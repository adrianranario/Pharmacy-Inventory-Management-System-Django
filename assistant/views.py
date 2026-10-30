from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from core.audit import log
from core.permissions import capability_required, has_capability
from .models import ChatHistory, ChatThread
from .facts import answer_inventory_question
from .llm import PharmacyAssistant
from .formatting import clean_assistant_answer
from .export import generate_pdf, generate_docx
from . import template_export


@capability_required('use_assistant')
def assistant_index(request):
    threads = ChatThread.objects.filter(user=request.user)
    selected = None
    thread_id = request.GET.get('thread')
    if thread_id:
        selected = get_object_or_404(ChatThread, pk=thread_id, user=request.user)
    elif threads.exists():
        selected = threads.first()

    messages_qs = selected.messages.order_by('created_at') if selected else ChatHistory.objects.none()
    chat_messages = list(messages_qs)
    for message in chat_messages:
        message.answer = clean_assistant_answer(message.answer)
    return render(request, 'assistant/index.html', {
        'threads': threads[:20],
        'selected_thread': selected,
        'chat_messages': chat_messages,
    })


@capability_required('use_assistant')
@require_POST
def new_thread(request):
    thread = ChatThread.objects.create(user=request.user, title='')
    return redirect(f"{reverse('assistant_index')}?thread={thread.pk}")


@capability_required('use_assistant')
@require_POST
def ask_assistant(request):
    question = request.POST.get('question', '').strip()[:1000]
    if not question:
        return JsonResponse({'answer': 'Please enter a question.'})

    thread = None
    thread_id = request.POST.get('thread_id')
    if thread_id:
        thread = ChatThread.objects.filter(pk=thread_id, user=request.user).first()
    if thread is None:
        thread = ChatThread.objects.create(user=request.user, title=question[:80])

    ql = question.lower()
    download_targets = [
        (('inventory' in ql), 'inventory', 'Inventory'),
        (('low stock' in ql or 'lowstock' in ql), 'low-stock', 'Low Stock'),
        (('near expiry' in ql or 'expir' in ql), 'near-expiry', 'Near Expiry'),
        (('sales' in ql), 'sales', 'Sales'),
    ]
    wants_export = any(keyword in ql for keyword in ['download', 'pdf', 'word', 'docx', 'export'])
    if not wants_export and 'report' in ql and any(keyword in ql for keyword in ['generate', 'create']):
        wants_export = True
    if wants_export:
        if not has_capability(request.user, 'export_reports'):
            answer = 'Report exports are available to pharmacists and administrators.'
            ChatHistory.objects.create(user=request.user, thread=thread, question=question, answer=answer)
            return JsonResponse({'answer': answer, 'thread_id': thread.pk})
        for matches, slug, label in download_targets:
            if matches:
                answer = f'Download the {label} report using the buttons below.'
                ChatHistory.objects.create(user=request.user, thread=thread, question=question, answer=answer)
                return JsonResponse({
                    'answer': answer,
                    'thread_id': thread.pk,
                    'download_pdf': f'/assistant/report/{slug}/pdf/',
                    'download_docx': f'/assistant/report/{slug}/docx/',
                })

    fact_answer = answer_inventory_question(question, request.user)
    if fact_answer is not None:
        answer = clean_assistant_answer(fact_answer)
    else:
        answer = clean_assistant_answer(PharmacyAssistant().ask(question, request.user))
    ChatHistory.objects.create(user=request.user, thread=thread, question=question, answer=answer)
    if not thread.title:
        thread.title = question[:80]
        thread.save(update_fields=['title'])
    thread.save(update_fields=['updated_at'])
    return JsonResponse({'answer': answer, 'thread_id': thread.pk})


@capability_required('use_assistant')
def download_pdf(request):
    if request.method == 'POST':
        content = request.POST.get('content', '')
        title = request.POST.get('title', 'Pharmacy_Report')
        log(request.user, 'export', description=f'Exported assistant PDF: {title}', request=request)
        return generate_pdf(title, content)
    return redirect('assistant_index')


@capability_required('use_assistant')
def download_docx(request):
    if request.method == 'POST':
        content = request.POST.get('content', '')
        title = request.POST.get('title', 'Pharmacy_Report')
        log(request.user, 'export', description=f'Exported assistant DOCX: {title}', request=request)
        return generate_docx(title, content)
    return redirect('assistant_index')


@capability_required('export_reports')
def report_inventory_pdf(request):
    return template_export.export_inventory_pdf()


@capability_required('export_reports')
def report_inventory_docx(request):
    return template_export.export_inventory_docx()


@capability_required('export_reports')
def report_low_stock_pdf(request):
    return template_export.export_low_stock_pdf()


@capability_required('export_reports')
def report_low_stock_docx(request):
    return template_export.export_low_stock_docx()


@capability_required('export_reports')
def report_near_expiry_pdf(request):
    return template_export.export_near_expiry_pdf()


@capability_required('export_reports')
def report_near_expiry_docx(request):
    return template_export.export_near_expiry_docx()


@capability_required('export_reports')
def report_sales_pdf(request):
    return template_export.export_sales_pdf()


@capability_required('export_reports')
def report_sales_docx(request):
    return template_export.export_sales_docx()
