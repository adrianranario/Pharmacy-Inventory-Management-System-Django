from datetime import timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand
from django.utils import timezone

from inventory.models import Batch, Medicine


class Command(BaseCommand):
    help = 'Email a digest of low-stock and near-expiry items to ALERT_EMAILS.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Print the digest instead of sending email.',
        )

    def handle(self, *args, **options):
        today = timezone.localdate()
        warning_days = getattr(settings, 'EXPIRY_WARNING_DAYS', 90)

        medicines = Medicine.objects.filter(status=True).prefetch_related('batches')
        low_stock = sorted(
            (medicine for medicine in medicines if medicine.is_low_stock()),
            key=lambda medicine: medicine.sellable_stock(),
        )
        near_expiry = (
            Batch.objects.filter(
                remaining_quantity__gt=0,
                expiry_date__gte=today,
                expiry_date__lte=today + timedelta(days=warning_days),
            )
            .select_related('medicine')
            .order_by('expiry_date')
        )
        expired = Batch.objects.filter(remaining_quantity__gt=0, expiry_date__lt=today).select_related('medicine')

        lines = [f'Pharmacy stock digest for {today:%B %d, %Y}', '']
        lines.append(f'LOW STOCK ({len(low_stock)})')
        if low_stock:
            for medicine in low_stock:
                lines.append(
                    f'  - {medicine.generic_name}: {medicine.sellable_stock()} on hand, '
                    f'reorder at {medicine.reorder_level} (suggest {medicine.suggested_order_quantity()})'
                )
        else:
            lines.append('  None')
        lines.append('')

        lines.append(f'EXPIRING WITHIN {warning_days} DAYS ({near_expiry.count()})')
        if near_expiry:
            for batch in near_expiry:
                days_left = batch.days_to_expire()
                lines.append(
                    f'  - {batch.medicine.generic_name} / {batch.batch_no}: '
                    f'{batch.remaining_quantity} units, expires {batch.expiry_date} '
                    f'({days_left} day{"s" if days_left != 1 else ""})'
                )
        else:
            lines.append('  None')
        lines.append('')

        lines.append(f'EXPIRED STOCK NOT YET WRITTEN OFF ({expired.count()})')
        if expired:
            for batch in expired:
                lines.append(
                    f'  - {batch.medicine.generic_name} / {batch.batch_no}: '
                    f'{batch.remaining_quantity} units, expired {batch.expiry_date}'
                )
            lines.append('')
            lines.append('Run `python manage.py expire_batches` to write these off.')
        else:
            lines.append('  None')

        body = '\n'.join(lines)
        recipients = getattr(settings, 'ALERT_EMAILS', [])

        if options['dry_run'] or not recipients:
            if not recipients:
                self.stdout.write(self.style.WARNING('ALERT_EMAILS is empty; printing the digest instead.'))
            self.stdout.write(body)
            return

        send_mail(
            subject=f'Pharmacy stock digest — {today:%b %d, %Y}',
            message=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=recipients,
            fail_silently=False,
        )
        self.stdout.write(self.style.SUCCESS(f'Digest sent to {", ".join(recipients)}.'))
