from django.conf import settings
from django.db import models


class AuditLog(models.Model):
    ACTION_CHOICES = (
        ('login', 'Signed in'),
        ('login_failed', 'Failed sign-in'),
        ('logout', 'Signed out'),
        ('create', 'Created'),
        ('update', 'Updated'),
        ('delete', 'Deleted'),
        ('sale', 'Sale completed'),
        ('void', 'Sale voided'),
        ('return', 'Sale returned'),
        ('stock', 'Stock movement'),
        ('export', 'Report exported'),
        ('security', 'Security change'),
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='audit_logs',
    )
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    model_name = models.CharField(max_length=80, blank=True)
    object_id = models.CharField(max_length=40, blank=True)
    description = models.TextField(blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.get_action_display()} {self.model_name} {self.object_id}'.strip()
