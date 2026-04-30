from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
import datetime

class PasswordResetOTP(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    otp_code = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)

    def is_valid(self):
        # OTP hanya berlaku 5 menit
        return self.created_at >= timezone.now() - datetime.timedelta(minutes=5)