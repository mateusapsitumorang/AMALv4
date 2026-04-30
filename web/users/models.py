from django.db import models
from django.contrib.auth import get_user_model

User = get_user_model()

class UserProfile(models.Model):
    user         = models.OneToOneField(User, on_delete=models.CASCADE, related_name="userprofile")
    organization = models.CharField(max_length=200, blank=True, default="")
    unit         = models.CharField(max_length=200, blank=True, default="")
    avatar       = models.ImageField(upload_to="profile/avatars/", blank=True, null=True)
    header       = models.ImageField(upload_to="profile/headers/", blank=True, null=True)

    notif_analysis   = models.BooleanField(default=True)
    notif_report     = models.BooleanField(default=True)
    notif_system     = models.BooleanField(default=False)
    display_compact  = models.BooleanField(default=False)
    display_timestamps = models.BooleanField(default=True)

    def __str__(self):
        return f"Profile — {self.user.username}"

    def get_avatar_url(self):
        if self.avatar:
            return self.avatar.url
        return None

    def get_header_url(self):
        if self.header:
            return self.header.url
        return None