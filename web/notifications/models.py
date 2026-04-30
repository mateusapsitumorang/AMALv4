from django.db import models
from django.contrib.auth.models import User

class Notification(models.Model):
    TYPE_CHOICES = [
        ('success', 'Analysis Completed'),
        ('error',   'Analysis Failed'),
        ('info',    'Sample Submitted'),
        ('warning', 'System Alert'),
        ('comment', 'New Comment'),
        ('reply',   'New Reply'),
    ]

    user       = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    type       = models.CharField(max_length=20, choices=TYPE_CHOICES)
    title      = models.CharField(max_length=255)
    message    = models.TextField()
    link       = models.CharField(max_length=500, blank=True, null=True)
    is_read    = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"[{self.type}] {self.title}"
