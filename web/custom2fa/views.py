from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django import forms
from django_otp import match_token
from django_otp import login as otp_login
from django.contrib import messages

# Simple form for OTP input.
class SimpleOTPForm(forms.Form):
    otp_token = forms.CharField(max_length=8, required=True)

@login_required
def custom_google_otp_verify(request):
    # Jika sudah terverifikasi, langsung usir ke dashboard
    if request.user.is_verified():
        return redirect('dashboard')

    if request.method == 'POST':
        form = SimpleOTPForm(request.POST)
        
        if form.is_valid():
            token = form.cleaned_data.get('otp_token')
            
            # Check token for all devices linked to the user
            device = match_token(request.user, token)
            
            if device:
                # Add verified device to session and log the user in
                otp_login(request, device)
                return redirect('dashboard')
            else:
                # Error handling
                messages.error(request, 'The OTP/token you entered is incorrect or has expired.')
    else:
        form = SimpleOTPForm()

    return render(request, 'two_factor/custom_google_verify.html', {'form': form})