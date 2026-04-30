import sys
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect

sys.path.append(settings.CUCKOO_PATH)

from lib.cuckoo.core.database import Database
from lib.cuckoo.core.data.task import Task, TASK_PENDING, TASK_REPORTED
from userprofile.models import UserProfile

User = get_user_model()


@login_required
def profile_view(request):
    from rest_framework.authtoken.models import Token

    profile_obj, _ = UserProfile.objects.get_or_create(user=request.user)

    try:
        api_key_obj, _ = Token.objects.get_or_create(user=request.user)
        api_key = api_key_obj.key
    except Exception:
        api_key = None

    try:
        owner = request.user.username
        db = Database()
        with db.session() as session:
            from sqlalchemy import select, func as sa_func
            total_analyses   = session.scalar(select(sa_func.count(Task.id)).where(Task.owner == owner)) or 0
            pending_count    = session.scalar(select(sa_func.count(Task.id)).where(Task.owner == owner, Task.status == TASK_PENDING)) or 0
            submission_count = session.scalar(select(sa_func.count(Task.id)).where(Task.owner == owner, Task.status == TASK_REPORTED)) or 0
    except Exception:
        total_analyses = pending_count = submission_count = 0

    return render(request, "userprofile/index.html", {
        "total_analyses":   total_analyses,
        "pending_count":    pending_count,
        "submission_count": submission_count,
        "api_key":          api_key,
        "profile_obj":      profile_obj,
    })


@login_required
def profile_update(request):
    from allauth.socialaccount.models import SocialAccount

    if request.method != "POST":
        return redirect("profile")

    user        = request.user
    profile_obj, _ = UserProfile.objects.get_or_create(user=user)

    first_name   = request.POST.get("first_name",   "").strip()
    last_name    = request.POST.get("last_name",    "").strip()
    username     = request.POST.get("username",     "").strip()
    email        = request.POST.get("email",        "").strip()
    organization = request.POST.get("organization", "").strip()
    unit         = request.POST.get("unit",         "").strip()

    if not username:
        messages.error(request, "Username cannot be empty.")
        return redirect("profile")

    if User.objects.exclude(pk=user.pk).filter(username=username).exists():
        messages.error(request, f'Username "{username}" is already taken.')
        return redirect("profile")

    user.first_name = first_name
    user.last_name  = last_name
    user.username   = username

    has_google = SocialAccount.objects.filter(user=user, provider="google").exists()
    if not has_google and email:
        if User.objects.exclude(pk=user.pk).filter(email=email).exists():
            messages.error(request, f'Email "{email}" is already registered.')
            return redirect("profile")
        user.email = email

    user.save()

    profile_obj.organization = organization
    profile_obj.unit         = unit

    if "avatar" in request.FILES:
        profile_obj.avatar = request.FILES["avatar"]

    if "header" in request.FILES:
        profile_obj.header = request.FILES["header"]

    profile_obj.save()

    messages.success(request, "Profile updated successfully.")
    return redirect("profile")