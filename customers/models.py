from django.conf import settings
from django.db import models
from django.utils import timezone


class Customer(models.Model):
    CUSTOMER_CHOICES = (
        ('regular', 'Regular'),
        ('senior_citizen', 'Senior Citizen'),
        ('pwd', 'PWD'),
    )

    name = models.CharField(max_length=200)
    phone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    address = models.TextField(blank=True)
    customer_type = models.CharField(max_length=20, choices=CUSTOMER_CHOICES, default='regular')
    id_no = models.CharField(max_length=50, blank=True, help_text='Senior citizen / PWD ID number')
    loyalty_points = models.IntegerField(default=0)
    notes = models.TextField(blank=True)
    status = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        indexes = [models.Index(fields=['name']), models.Index(fields=['phone'])]

    def __str__(self):
        return self.name

    @property
    def active_prescriptions(self):
        return self.prescriptions.filter(status='active').count()


class Prescription(models.Model):
    STATUS_CHOICES = (
        ('active', 'Active'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    )

    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='prescriptions')
    medicine = models.ForeignKey('inventory.Medicine', on_delete=models.PROTECT, related_name='prescriptions')
    rx_no = models.CharField(max_length=50, unique=True)
    prescriber = models.CharField(max_length=200)
    issued_date = models.DateField(default=timezone.localdate)
    expiry_date = models.DateField(null=True, blank=True)
    refills_remaining = models.PositiveIntegerField(default=0)
    directions = models.CharField(max_length=300, blank=True)
    notes = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='prescriptions_created',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.rx_no} - {self.customer.name}'

    @property
    def is_expired(self):
        return bool(self.expiry_date and self.expiry_date < timezone.localdate())
