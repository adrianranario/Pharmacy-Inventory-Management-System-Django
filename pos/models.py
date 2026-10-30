from django.conf import settings
from django.db import models
from django.utils import timezone

from customers.models import Customer
from inventory.models import Batch, Medicine


class Sale(models.Model):
    CUSTOMER_CHOICES = (
        ('regular', 'Regular'),
        ('senior_citizen', 'Senior Citizen'),
        ('pwd', 'PWD'),
    )
    PAYMENT_CHOICES = (
        ('cash', 'Cash'),
        ('gcash', 'GCash'),
        ('card', 'Card'),
    )
    STATUS_CHOICES = (
        ('completed', 'Completed'),
        ('partially_returned', 'Partially returned'),
        ('returned', 'Returned'),
        ('voided', 'Voided'),
    )

    invoice_no = models.CharField(max_length=50, unique=True)
    or_number = models.CharField(max_length=30, unique=True, null=True, blank=True)
    sold_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='sales')
    customer = models.ForeignKey(Customer, on_delete=models.SET_NULL, null=True, blank=True, related_name='sales')
    customer_name = models.CharField(max_length=200, blank=True, null=True)
    customer_type = models.CharField(max_length=20, choices=CUSTOMER_CHOICES, default='regular')
    id_no = models.CharField(max_length=50, blank=True, null=True)
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    discount_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    discount_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    vat_exempt = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    refunded_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    amount_paid = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    change_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    payment_method = models.CharField(max_length=20, choices=PAYMENT_CHOICES, default='cash')
    payment_reference = models.CharField(max_length=80, blank=True, help_text='GCash / card reference number')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='completed')
    voided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='voided_sales',
    )
    voided_at = models.DateTimeField(null=True, blank=True)
    void_reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['status']), models.Index(fields=['created_at'])]

    def __str__(self):
        return self.invoice_no

    @property
    def net_total(self):
        return (self.total_amount or 0) - (self.refunded_amount or 0)

    @property
    def is_refundable(self):
        return self.status in {'completed', 'partially_returned'}


class SaleItem(models.Model):
    sale = models.ForeignKey(Sale, on_delete=models.CASCADE, related_name='items')
    medicine = models.ForeignKey(Medicine, on_delete=models.PROTECT)
    batch = models.ForeignKey(Batch, on_delete=models.PROTECT)
    quantity = models.IntegerField()
    returned_quantity = models.IntegerField(default=0)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    subtotal = models.DecimalField(max_digits=10, decimal_places=2)

    @property
    def refundable_quantity(self):
        return max(0, self.quantity - self.returned_quantity)

    def save(self, *args, **kwargs):
        self.subtotal = self.quantity * self.price
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.sale.invoice_no} - {self.medicine.generic_name}"


class SaleReturn(models.Model):
    return_no = models.CharField(max_length=50, unique=True)
    sale = models.ForeignKey(Sale, on_delete=models.PROTECT, related_name='returns')
    processed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='returns_processed')
    reason = models.CharField(max_length=200)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.return_no


class SaleReturnItem(models.Model):
    sale_return = models.ForeignKey(SaleReturn, on_delete=models.CASCADE, related_name='items')
    sale_item = models.ForeignKey(SaleItem, on_delete=models.PROTECT, related_name='return_items')
    quantity = models.IntegerField()
    amount = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return f'{self.sale_return.return_no} - {self.sale_item.medicine.generic_name}'
