from django.contrib import messages
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render

from core.permissions import capability_required
from inventory.models import Medicine
from .models import Forecast
from .services import calculate_forecast, generate_all_forecasts


@capability_required('view_reports')
def forecast_index(request):
    medicines = Medicine.objects.filter(status=True).select_related('category', 'supplier').prefetch_related('batches')
    forecasts = Forecast.objects.select_related('medicine').order_by('-created_at')[:20]
    return render(request, 'forecast/index.html', {'medicines': medicines, 'forecasts': forecasts})


@capability_required('view_reports')
def generate_forecast(request, pk):
    medicine = get_object_or_404(Medicine, pk=pk)
    try:
        forecast = calculate_forecast(medicine)
    except ValidationError as exc:
        messages.warning(request, exc.messages[0])
    else:
        mape = f'{forecast.mape}% MAPE' if forecast.mape is not None else 'no backtest'
        messages.success(
            request,
            f'Forecast for {medicine.generic_name}: {forecast.forecast_quantity} units over 28 days ({mape}).',
        )
    return redirect('forecast_index')


@capability_required('view_reports')
def generate_all(request):
    generated, skipped = generate_all_forecasts()
    messages.success(request, f'Generated {len(generated)} forecast(s).')
    if skipped:
        messages.info(request, f'{len(skipped)} medicine(s) skipped due to insufficient sales history.')
    return redirect('forecast_index')
