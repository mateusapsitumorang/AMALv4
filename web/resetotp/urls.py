from django.urls import path
from . import views

urlpatterns = [
    # ... url lainnya ...
    path('password-reset-otp/', views.request_password_reset, name='password_reset'),
    path('verify-otp/', views.verify_otp_view, name='verify_otp'),
    path('set-new-password/', views.set_new_password_view, name='set_new_password'),
]