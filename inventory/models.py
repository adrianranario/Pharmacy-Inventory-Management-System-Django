from django.db import models
from django.utils import timezone


class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = 'Categories'

    def __str__(self):
        return self.name


class Supplier(models.Model):
    name = models.CharField(max_length=200)
    contact_person = models.CharField(max_length=100, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    phone = models.CharField(max_length=15, blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    lead_time_days = models.PositiveIntegerField(default=7, help_text='Typical delivery lead time in days')
    notes = models.TextField(blank=True, null=True)
    status = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class Medicine(models.Model):
    medicine_code = models.CharField(max_length=50, unique=True)
    generic_name = models.CharField(max_length=200)
    brand_name = models.CharField(max_length=200, blank=True, null=True)
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name='medicines')
    supplier = models.ForeignKey(
        Supplier,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name='medicines',
        help_text='Preferred supplier, used for reorder lead time',
    )
    dosage_form = models.CharField(max_length=50, blank=True, null=True)
    strength = models.CharField(max_length=50, blank=True, null=True)
    unit = models.CharField(max_length=20, default='pcs')
    purchase_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    selling_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    reorder_level = models.IntegerField(default=10)
    shelf_location = models.CharField(max_length=50, blank=True, null=True)
    barcode = models.CharField(max_length=100, blank=True, null=True, unique=True)
    description = models.TextField(blank=True, null=True)
    status = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def total_stock(self):
        cache = getattr(self, '_prefetched_objects_cache', {})
        if 'batches' in cache:
            return sum(batch.remaining_quantity for batch in self.batches.all() if batch.remaining_quantity > 0)
        return sum(batch.remaining_quantity for batch in self.batches.filter(remaining_quantity__gt=0))

    def sellable_stock(self):
        """Units that can still be sold, excluding expired batches."""
        today = timezone.localdate()
        cache = getattr(self, '_prefetched_objects_cache', {})
        if 'batches' in cache:
            batches = self.batches.all()
        else:
            batches = self.batches.filter(remaining_quantity__gt=0)
        return sum(
            batch.remaining_quantity
            for batch in batches
            if batch.remaining_quantity > 0 and batch.expiry_date >= today
        )

    def is_low_stock(self):
        return self.sellable_stock() <= self.reorder_level

    def suggested_order_quantity(self):
        """Bring sellable stock back to twice the reorder level."""
        return max(self.reorder_level * 2 - self.sellable_stock(), 0)

    def __str__(self):
        return f"{self.generic_name} ({self.brand_name or 'N/A'})"


class Batch(models.Model):
    medicine = models.ForeignKey(Medicine, on_delete=models.CASCADE, related_name='batches')
    batch_no = models.CharField(max_length=50)
    quantity = models.IntegerField()
    remaining_quantity = models.IntegerField()
    purchase_price = models.DecimalField(max_digits=10, decimal_places=2)
    expiry_date = models.DateField()
    received_date = models.DateField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['expiry_date']
        indexes = [models.Index(fields=['expiry_date']), models.Index(fields=['remaining_quantity'])]

    def is_expired(self):
        return self.expiry_date < timezone.localdate()

    def days_to_expire(self):
        delta = self.expiry_date - timezone.localdate()
        return delta.days

    def is_near_expiry(self, days=None):
        if days is None:
            from django.conf import settings

            days = getattr(settings, 'EXPIRY_WARNING_DAYS', 90)
        return 0 <= self.days_to_expire() <= days

    def __str__(self):
        return f"{self.medicine.generic_name} - {self.batch_no}"

    @property
    def stock_value(self):
        return self.remaining_quantity * self.purchase_price


class StockMovement(models.Model):
    """Append-only ledger of every stock change."""

    TYPE_CHOICES = (
        ('purchase', 'Purchase received'),
        ('sale', 'Sale'),
        ('return', 'Customer return'),
        ('adjustment', 'Adjustment'),
        ('writeoff', 'Write-off'),
        ('expiry', 'Expired'),
        ('void', 'Sale voided'),
    )

    medicine = models.ForeignKey(Medicine, on_delete=models.CASCADE, related_name='stock_movements')
    batch = models.ForeignKey(Batch, on_delete=models.SET_NULL, null=True, blank=True, related_name='movements')
    movement_type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    quantity = models.IntegerField(help_text='Signed change: positive adds stock, negative removes it')
    balance_after = models.IntegerField(null=True, blank=True, help_text='Batch balance after this movement')
    reference = models.CharField(max_length=80, blank=True)
    notes = models.TextField(blank=True)
    user = models.ForeignKey(
        'accounts.CustomUser',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='stock_movements',
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['movement_type']), models.Index(fields=['reference'])]

    def __str__(self):
        return f'{self.get_movement_type_display()} {self.quantity:+d} {self.medicine.generic_name}'
