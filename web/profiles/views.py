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
        db = Database()
        with db.session() as session:
            from sqlalchemy import select, func as sa_func
            # Use user_id, not owner
            uid = request.user.id
            total_analyses   = session.scalar(select(sa_func.count(Task.id)).where(Task.user_id == uid)) or 0
            pending_count    = session.scalar(select(sa_func.count(Task.id)).where(Task.user_id == uid, Task.status == TASK_PENDING)) or 0
            submission_count = session.scalar(select(sa_func.count(Task.id)).where(Task.user_id == uid, Task.status == TASK_REPORTED)) or 0
    except Exception as e:
        total_analyses = pending_count = submission_count = 0

    return render(request, "profiles/index.html", {
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

    user = request.user
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

    # Avatar
    if request.POST.get("delete_avatar") == "1":
        if profile_obj.avatar:
            profile_obj.avatar.delete(save=False)
        profile_obj.avatar = None
    elif "avatar" in request.FILES:
        if profile_obj.avatar:
            profile_obj.avatar.delete(save=False)
        profile_obj.avatar = request.FILES["avatar"]

    #  Header
    if request.POST.get("delete_header") == "1":
        if profile_obj.header:
            profile_obj.header.delete(save=False)
        profile_obj.header = None
    elif "header" in request.FILES:
        if profile_obj.header:
            profile_obj.header.delete(save=False)
        profile_obj.header = request.FILES["header"]

    # Settings toggles 
    if request.POST.get('form_type') == 'settings':
        profile_obj.notif_analysis     = "notif_analysis"     in request.POST
        profile_obj.notif_report       = "notif_report"       in request.POST
        profile_obj.notif_system       = "notif_system"       in request.POST
        profile_obj.display_compact    = "display_compact"    in request.POST
        profile_obj.display_timestamps = "display_timestamps" in request.POST

    profile_obj.save()
    messages.success(request, "Profile updated successfully.")
    return redirect("profile")