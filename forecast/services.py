"""Demand forecasting with backtested error estimates and demand classification.

Builds a weekly series, classifies demand (smooth/intermittent/lumpy/erratic),
evaluates multiple methods (SES, Holt's linear trend, Croston's for intermittent),
and derives reorder points from lead time plus safety stock.
"""
import math
import statistics
from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db.models import F, Sum
from django.db.models.functions import TruncWeek
from django.utils import timezone

from inventory.models import Medicine
from pos.models import SaleItem
from .models import Forecast

HISTORY_WEEKS = 26
HOLDOUT_WEEKS = 4


def _weekly_series(medicine, today):
    start = today - timedelta(weeks=HISTORY_WEEKS)
    rows = (
        SaleItem.objects.filter(
            medicine=medicine,
            sale__created_at__date__gte=start,
            sale__status__in=['completed', 'partially_returned', 'returned'],
        )
        .annotate(week=TruncWeek('sale__created_at'))
        .values('week')
        .annotate(qty=Sum(F('quantity') - F('returned_quantity')))
        .order_by('week')
    )
    by_week = {row['week'].date(): max(0, int(row['qty'] or 0)) for row in rows}

    series = []
    cursor = start - timedelta(days=start.weekday())
    end = today - timedelta(days=today.weekday())
    while cursor <= end:
        series.append({'week': cursor.isoformat(), 'qty': by_week.get(cursor, 0)})
        cursor += timedelta(days=7)
    return series


def _ses_forecast_level(values, alpha):
    level = values[0]
    for value in values[1:]:
        level = alpha * value + (1 - alpha) * level
    return level


def _ses_forecast(values, alpha):
    return _ses_forecast_level(values, alpha)


def _holt_forecast(values, alpha, beta):
    if len(values) == 0:
        return 0.0
    level = values[0]
    trend = values[1] - values[0] if len(values) > 1 else 0.0
    for value in values[1:]:
        prev_level = level
        level = alpha * value + (1 - alpha) * (level + trend)
        trend = beta * (level - prev_level) + (1 - beta) * trend
    return level + trend


def _holt_forecast_level_trend(values, alpha, beta):
    if len(values) == 0:
        return 0.0, 0.0
    level = values[0]
    trend = values[1] - values[0] if len(values) > 1 else 0.0
    for value in values[1:]:
        prev_level = level
        level = alpha * value + (1 - alpha) * (level + trend)
        trend = beta * (level - prev_level) + (1 - beta) * trend
    return level, trend


def _croston_forecast(values, alpha=0.1):
    """Croston's method for intermittent demand."""
    if not values:
        return 0.0
    # Separate demand sizes and intervals
    demand_sizes = []
    intervals = []
    last_demand_idx = None
    for i, v in enumerate(values):
        if v > 0:
            demand_sizes.append(v)
            if last_demand_idx is not None:
                intervals.append(i - last_demand_idx)
            last_demand_idx = i
    if not demand_sizes:
        return 0.0
    if not intervals:
        # All non-zero from start or only one demand
        avg_size = statistics.fmean(demand_sizes)
        return avg_size / len(values) if len(values) > 0 else avg_size
    # Initialize
    z = demand_sizes[0]  # demand size estimate
    p = intervals[0]  # interval estimate
    for q in demand_sizes[1:]:
        z = alpha * q + (1 - alpha) * z
    for iv in intervals[1:]:
        p = alpha * iv + (1 - alpha) * p
    if p <= 0:
        p = 1
    return z / p


def _mape(actual, predicted):
    errors = []
    for real, forecast in zip(actual, predicted):
        if real > 0:
            errors.append(abs(real - forecast) / real)
    return (sum(errors) / len(errors) * 100) if errors else None


def _classify_demand(values):
    """Classify demand pattern using ADI (Average Demand Interval) and CV^2."""
    if not values or sum(values) == 0:
        return 'none'
    non_zero_periods = sum(1 for v in values if v > 0)
    if non_zero_periods == 0:
        return 'none'
    # Calculate intervals between demands
    intervals = []
    last_idx = None
    for i, v in enumerate(values):
        if v > 0:
            if last_idx is not None:
                intervals.append(i - last_idx)
            last_idx = i
    if not intervals:
        adi = 1.0
    else:
        adi = statistics.fmean(intervals)
    # CV^2 of demand sizes when demand occurs
    demand_sizes = [v for v in values if v > 0]
    if len(demand_sizes) == 0:
        cv2 = 0
    elif len(demand_sizes) == 1:
        cv2 = 0
    else:
        mean_d = statistics.fmean(demand_sizes)
        if mean_d == 0:
            cv2 = float('inf')
        else:
            std_d = statistics.pstdev(demand_sizes)
            cv2 = (std_d / mean_d) ** 2
    # Classification (Syntetos-Boylan)
    if adi < 1.32:
        if cv2 < 0.49:
            return 'smooth'
        else:
            return 'erratic'
    else:
        if cv2 < 0.49:
            return 'intermittent'
        else:
            return 'lumpy'


def _evaluate(values):
    """Pick the best method and parameters with holdout MAPE."""
    if len(values) < HOLDOUT_WEEKS + 4:
        return None, None, 'mean'

    train, actual = values[:-HOLDOUT_WEEKS], values[-HOLDOUT_WEEKS:]
    best_score = None
    best_result = (0.4, None, 'ses')  # (alpha_or_param, mape, method)

    # Try SES
    for alpha in [round(0.1 * step, 1) for step in range(1, 10)]:
        predictions = []
        level = train[0]
        for value in train[1:]:
            level = alpha * value + (1 - alpha) * level
        for value in actual:
            predictions.append(max(0, level))
            level = alpha * value + (1 - alpha) * level
        error = _mape(actual, predictions)
        if error is not None and (best_score is None or error < best_score):
            best_score = error
            best_result = (alpha, error, 'ses')

    # Try Holt's linear trend
    for alpha in [round(0.1 * step, 1) for step in range(1, 10)]:
        for beta in [round(0.1 * step, 1) for step in range(1, 6)]:
            if len(train) < 2:
                continue
            predictions = []
            level = train[0]
            trend = train[1] - train[0]
            for value in train[1:]:
                prev_level = level
                level = alpha * value + (1 - alpha) * (level + trend)
                trend = beta * (level - prev_level) + (1 - beta) * trend
            for value in actual:
                predictions.append(max(0, level + trend))
                prev_level = level
                level = alpha * value + (1 - alpha) * (level + trend)
                trend = beta * (level - prev_level) + (1 - beta) * trend
            error = _mape(actual, predictions)
            if error is not None and (best_score is None or error < best_score):
                best_score = error
                best_result = ((alpha, beta), error, 'holt')

    # Try Croston's for intermittent patterns
    demand_class = _classify_demand(values)
    if demand_class in ['intermittent', 'lumpy']:
        for alpha in [0.1, 0.2, 0.3, 0.4, 0.5]:
            predictions = []
            # Build up to train end
            full_series = train + list(actual)
            # Simpler holdout: forecast based on train
            demand_sizes = []
            intervals = []
            last_demand_idx = None
            for i, v in enumerate(train):
                if v > 0:
                    demand_sizes.append(v)
                    if last_demand_idx is not None:
                        intervals.append(i - last_demand_idx)
                    last_demand_idx = i
            if demand_sizes and intervals:
                z = demand_sizes[0]
                p = intervals[0]
                for q in demand_sizes[1:]:
                    z = alpha * q + (1 - alpha) * z
                for iv in intervals[1:]:
                    p = alpha * iv + (1 - alpha) * p
                if p <= 0:
                    p = 1
                pred = max(0, z / p)
                for value in actual:
                    predictions.append(pred)
                error = _mape(actual, predictions)
                if error is not None and (best_score is None or error < best_score):
                    best_score = error
                    best_result = (alpha, error, 'croston')

    if best_result[2] == 'mean':
        return None, None, 'mean'
    return best_result[0], best_result[1], best_result[2]


def _lead_time_days(medicine):
    if medicine.supplier_id:
        try:
            return max(1, medicine.supplier.lead_time_days or 7)
        except Exception:
            pass
    try:
        last = (
            medicine.purchaseitem_set.select_related('purchase__supplier')
            .order_by('-purchase__created_at')
            .first()
        )
        if last and last.purchase.supplier_id:
            return max(1, last.purchase.supplier.lead_time_days or 7)
    except Exception:
        pass
    return 7


def calculate_forecast(medicine):
    today = timezone.localdate()
    series = _weekly_series(medicine, today)
    values = [row['qty'] for row in series]

    if not values or sum(values) == 0:
        raise ValidationError('Not enough sales history to forecast this medicine.')

    params, mape, method = _evaluate(values)
    if method == 'ses' and params is not None:
        weekly_demand = _ses_forecast(values, params)
    elif method == 'holt' and params is not None and isinstance(params, tuple):
        alpha, beta = params
        weekly_demand = _holt_forecast(values, alpha, beta)
    elif method == 'croston' and params is not None:
        weekly_demand = _croston_forecast(values, params)
    else:
        weekly_demand = statistics.fmean(values)
        method = 'mean'

    weekly_demand = max(0.0, weekly_demand)
    lead_time_days = _lead_time_days(medicine)
    lead_weeks = lead_time_days / 7
    sigma = statistics.pstdev(values) if len(values) > 1 else 0
    safety_stock = math.ceil(1.65 * sigma * math.sqrt(max(lead_weeks, 1)))

    reorder_point = math.ceil(weekly_demand * lead_weeks + safety_stock)
    forecast_quantity = math.ceil(weekly_demand * 4)  # next 28 days
    current_stock = medicine.sellable_stock()
    reorder_suggestion = max(0, reorder_point + forecast_quantity - current_stock)
    stock_cover_days = math.floor(current_stock / (weekly_demand / 7)) if weekly_demand > 0 else None

    return Forecast.objects.create(
        medicine=medicine,
        historical_data=series,
        forecast_quantity=forecast_quantity,
        reorder_suggestion=reorder_suggestion,
        safety_stock=safety_stock,
        lead_time_days=lead_time_days,
        stock_cover_days=stock_cover_days,
        method=method,
        mape=round(mape, 2) if mape is not None else None,
        forecast_period_start=today + timedelta(days=1),
        forecast_period_end=today + timedelta(days=28),
    )


def generate_all_forecasts():
    generated, skipped = [], []
    for medicine in Medicine.objects.filter(status=True):
        try:
            generated.append(calculate_forecast(medicine))
        except ValidationError:
            skipped.append(medicine)
    return generated, skipped
