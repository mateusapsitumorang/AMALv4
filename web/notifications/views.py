from django.http import JsonResponse
from django.shortcuts import render
from django.utils import timezone
import pytz
from django.views.decorators.http import require_POST, require_http_methods
from django.views.decorators.csrf import csrf_exempt, ensure_csrf_cookie
from django.contrib.auth.decorators import login_required
from functools import wraps
from .models import Notification


# Custom decorator for API endpoints that need authentication
def api_login_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({'error': 'Not authenticated', 'notifications': [], 'unread_count': 0}, status=401)
        return view_func(request, *args, **kwargs)
    return wrapper

@csrf_exempt
@require_POST
def create_notification(request):
    from django.contrib.auth.models import User
    import json
    data = json.loads(request.body)
    user_id = data.get('user_id')
    type_ = data.get('type')
    title = data.get('title')
    message = data.get('message')
    link = data.get('link', '')
    
    user = User.objects.get(id=user_id) if user_id else None
    Notification.objects.create(
        user=user,
        type=type_,
        title=title,
        message=message,
        link=link
    )
    return JsonResponse({'status': 'created'})

@api_login_required
@require_http_methods(["GET"])
def get_notifications(request):
    notifs = Notification.objects.filter(user=request.user, is_read=False).order_by('-created_at')[:10]
    unread_count = Notification.objects.filter(user=request.user, is_read=False).count()
    wib_tz = pytz.timezone('Asia/Jakarta')
    data = {
        'unread_count': unread_count,
        'notifications': [
            {
                'id':         n.id,
                'type':       n.type,
                'title':      n.title,
                'message':    n.message,
                'link':       n.link or '#',
                'created_at': n.created_at.astimezone(wib_tz).strftime('%d %b %Y, %H:%M'),
            }
            for n in notifs
        ]
    }
    return JsonResponse(data)

@api_login_required
@require_http_methods(["GET"])
def list_notifications(request):
    from django.db.models import Q
    types = request.GET.getlist('type')
    limit = int(request.GET.get('limit', 10))
    
    query = Q(user=request.user)
    if types:
        query &= Q(type__in=types)
    
    notifs = Notification.objects.filter(query).order_by('-created_at')[:limit]
    wib_tz = pytz.timezone('Asia/Jakarta')
    data = [
        {
            'id':         n.id,
            'type':       n.type,
            'title':      n.title,
            'message':    n.message,
            'link':       n.link or '#',
            'created_at': n.created_at.astimezone(wib_tz).isoformat(),
        }
        for n in notifs
    ]
    return JsonResponse(data, safe=False)

@api_login_required
@require_POST
def mark_read(request, pk):
    # Only mark as read if it belongs to the current user
    Notification.objects.filter(pk=pk, user=request.user).update(is_read=True)
    return JsonResponse({'status': 'ok'})

@api_login_required
@require_POST
def mark_all_read(request):
    # Only mark as read if it belongs to the current user
    Notification.objects.filter(user=request.user, is_read=False).update(is_read=True)
    return JsonResponse({'status': 'ok'})

@login_required
def notifications_page(request):
    if not request.user.is_authenticated:
        return render(request, 'error.html', {'error': 'Not authenticated'})
    all_notifs = Notification.objects.filter(user=request.user).order_by('-created_at')
    return render(request, 'notifications.html', {'notifications': all_notifs})
