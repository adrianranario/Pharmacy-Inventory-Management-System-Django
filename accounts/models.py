from django.contrib.auth.models import AbstractUser
from django.db import models


class CustomUser(AbstractUser):
    ROLE_CHOICES = (
        ('admin', 'Administrator'),
        ('pharmacist', 'Pharmacist'),
        ('cashier', 'Cashier'),
        ('inventory_clerk', 'Inventory Clerk'),
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='cashier')
    phone = models.CharField(max_length=15, blank=True, null=True)
    license_no = models.CharField(max_length=50, blank=True, null=True, help_text='For Pharmacist')
    status = models.BooleanField(default=True)
    otp_secret = models.CharField(max_length=64, blank=True)
    otp_enabled = models.BooleanField(default=False)

    def is_admin(self):
        return self.role == 'admin'

    def is_pharmacist(self):
        return self.role == 'pharmacist'

    def is_cashier(self):
        return self.role == 'cashier'

    def is_inventory_clerk(self):
        return self.role == 'inventory_clerk'

    def __str__(self):
        return f"{self.username} - {self.get_role_display()}"
