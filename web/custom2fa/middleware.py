from django.shortcuts import redirect
from django.urls import reverse
from django_otp import user_has_device
from django.contrib.auth import get_user_model
from django.db.models import Q

class EnforceGoogleOTPMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path == reverse('two_factor:login') and request.method == 'POST':
            # library django-two-factor-auth secara default menggunakan awalan 'auth-' untuk nama inputnya
            username_input = request.POST.get('auth-username')
            password_input = request.POST.get('auth-password')
            
            if username_input and password_input:
                User = get_user_model()
                try:
                    # Cari user berdasarkan username ATAU email
                    user = User.objects.get(Q(username=username_input) | Q(email=username_input))
                    
                    # Jika akun belum aktif tapi password benar
                    if not user.is_active and user.check_password(password_input):
                        return redirect('account_inactive') # Langsung tembak ke halaman inactive
                        
                except (User.DoesNotExist, User.MultipleObjectsReturned):
                    # Kalau usernya nggak ada atau error, diamkan saja. 
                    # Biarkan sistem Django yang ngasih tau "Username/Password salah"
                    pass

        # Hanya cek jika user sudah login
        if request.user.is_authenticated:
            # Cek apakah user punya device 2FA TAPI belum melewati verifikasi OTP
            if user_has_device(request.user) and not request.user.is_verified():
                
                # Daftar halaman yang BOLEH diakses tanpa OTP agar tidak terjadi redirect berulang (loop)
                allowed_paths = [
                    reverse('custom_google_otp_verify'), 
                    reverse('two_factor:login'),
                    '/auth/',
                    '/accounts/',
                     # Biarkan mereka bisa logout jika mau
                    '/admin/logout/'
                ]
                # Check if current path is start with any of the allowed paths
                is_allowed_path = any(request.path.startswith(path) for path in allowed_paths)
                
                # If not on an allowed path, redirect to OTP verification page
                if not is_allowed_path and not request.path.startswith('/static/'):
                    return redirect('custom_google_otp_verify')

        return self.get_response(request)