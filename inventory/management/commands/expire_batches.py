from django.core.management.base import BaseCommand
from django.utils import timezone

from inventory.services import expire_batches


class Command(BaseCommand):
    help = 'Write off every expired batch and record the loss in the stock ledger.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be written off without changing any stock.',
        )

    def handle(self, *args, **options):
        today = timezone.localdate()
        from inventory.models import Batch

        batches = list(
            Batch.objects.filter(remaining_quantity__gt=0, expiry_date__lt=today)
            .select_related('medicine')
            .order_by('expiry_date')
        )
        self.stdout.write(f'Expired batches on {today}: {len(batches)}')
        lost = 0
        for batch in batches:
            lost += batch.remaining_quantity
            self.stdout.write(
                f'  - {batch.medicine.generic_name} / {batch.batch_no} '
                f'({batch.remaining_quantity} units, expired {batch.expiry_date})'
            )

        if options['dry_run']:
            self.stdout.write(self.style.WARNING('Dry run: no stock was changed.'))
            return

        affected = expire_batches(today=today)
        self.stdout.write(
            self.style.SUCCESS(f'Wrote off {len(affected)} batch(es), {lost} units total.')
        )
