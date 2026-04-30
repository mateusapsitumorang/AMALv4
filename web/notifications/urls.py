from django.urls import path
from . import views

urlpatterns = [
    path('api/notifications/',            views.get_notifications, name='get_notifications'),
    path('api/notifications/list/',       views.list_notifications, name='list_notifications'),
    path('api/notifications/create/',     views.create_notification, name='create_notification'),
    path('api/notifications/read-all/',   views.mark_all_read,     name='mark_all_read'),
    path('api/notifications/<int:pk>/read/', views.mark_read,      name='mark_read'),
    path('notifications/',                views.notifications_page, name='notifications_page'),
]