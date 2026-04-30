import random
import textwrap
from django.shortcuts import render, redirect
from django.contrib.auth.models import User
from django.core.mail import send_mail
from django.conf import settings
from django.contrib import messages
from .models import PasswordResetOTP
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError


def request_password_reset(request):
    if request.method == 'POST':
        email = request.POST.get('email')

        try:
            user = User.objects.get(email = email)
            otp_code = str(random.randint(100000, 999999))
            PasswordResetOTP.objects.filter(user = user).delete()
            PasswordResetOTP.objects.create(user=user, otp_code=otp_code)
            subject = 'AMAL 4 - OTP for Password Reset'
            message = textwrap.dedent(f'''\
                Hi {user.username},
                We received a request to reset the password for your AMAL 4 account.
                Your verification code is: {otp_code}

                This code is valid for 5 minutes.
                If you did not request this, please ignore this email.''')
            send_mail(
                subject, message, settings.EMAIL_HOST_USER,
                [user.email],
                fail_silently=False,
            )

            request.session['reset_email'] = user.email
            messages.success(request, 'If the email exists in our system, an OTP code has been sent.')

            return redirect('verify_otp')

        except User.DoesNotExist:
            messages.success(request, 'If the email exists in our system, an OTP code has been sent.') # Pesan ambigu untuk keamanan
            request.session['reset_email'] = email # Tetap simpan untuk mengecoh attacker
            return redirect('verify_otp')

    return render(request, 'resetotp/request_otp.html')

def verify_otp_view(request):
    # Cek apakah user sudah melewati tahap request OTP (email tersimpan di session)
    email = request.session.get('reset_email')
    if not email:
        messages.error(request, 'Session has expired. Please request a new OTP code.')
        return redirect('password_reset')

    if request.method == 'POST':
        # Mengambil input OTP dari form HTML (nanti kita buat input hidden-nya bernama 'otp_code')
        otp_input = request.POST.get('otp_code')
        
        try:
            user = User.objects.get(email=email)
            # Ambil OTP terbaru milik user ini
            otp_record = PasswordResetOTP.objects.filter(user=user).latest('created_at')
            
            if otp_record.otp_code == otp_input:
                if otp_record.is_valid():
                    # OTP Benar dan Valid (Belum 5 menit)
                    request.session['otp_verified'] = True # Beri izin untuk ganti password
                    messages.success(request, 'OTP verified successfully. You can now set a new password.')
                    return redirect('set_new_password') # Nanti kita buat di Langkah 4
                else:
                    messages.error(request, 'OTP has expired. Please request a new one.')
            else:
                messages.error(request, 'Invalid OTP code.')
                
        except (User.DoesNotExist, PasswordResetOTP.DoesNotExist):
            messages.error(request, 'Something went wrong. Please try again.')

    return render(request, 'resetotp/verify_otp.html', {'email': email})

def set_new_password_view(request):
    # 1. CEK KEAMANAN: Pastikan user sudah melewati verifikasi OTP
    if not request.session.get('otp_verified'):
        messages.error(request, 'Access denied. Please verify OTP first.')
        return redirect('password_reset')

    # Ambil email dari session
    email = request.session.get('reset_email')
    if not email:
        return redirect('password_reset')

    if request.method == 'POST':
        new_password = request.POST.get('new_password')
        confirm_password = request.POST.get('confirm_password')

        # 2. Validasi Input
        if new_password and new_password == confirm_password:
            try:
                user = User.objects.get(email=email)

                try:
                    # Fungsi ini akan mengecek settings.AUTH_PASSWORD_VALIDATORS
                    validate_password(new_password, user=user)
                except ValidationError as e:
                    # Jika tidak valid, kirim semua pesan error ke template
                    for error in e.messages:
                        messages.error(request, error)
                    return render(request, 'resetotp/set_new_password.html')
                
                # 3. Simpan Password Baru (set_password akan meng-hash password otomatis)
                user.set_password(new_password)
                user.save()

                # 4. Bersihkan Jejak (Keamanan)
                del request.session['otp_verified']
                del request.session['reset_email']
                PasswordResetOTP.objects.filter(user=user).delete()

                messages.success(request, 'Password has been reset successfully. You can now log in with your new password.')
                return redirect('two_factor:login')
            except User.DoesNotExist:
                messages.error(request, 'User not found. Please try again.')
        else:
            messages.error(request, 'Passwords do not match or are empty. Please try again.')

    return render(request, 'resetotp/set_new_password.html')