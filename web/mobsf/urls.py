from django.urls import path
from mobsf import views

urlpatterns = [
    path("", views.index, name="mobsf"),
    path("runtime/health/", views.runtime_health, name="mobsf_runtime_health"),
    path("upload/", views.upload, name="mobsf_upload"),
    path("scan/<str:scan_type>/<str:file_hash>/", views.scan, name="mobsf_scan"),
    path("report/<str:scan_type>/<str:file_hash>/", views.report, name="mobsf_report"),
    path("recent/", views.recent_scans, name="mobsf_recent"),
    path("delete/<str:file_hash>/", views.delete_scan, name="mobsf_delete"),
    path("api/pdf/<str:file_hash>/", views.download_pdf, name="mobsf_pdf"),
    path("icon/<str:file_hash>/", views.icon_proxy, name="mobsf_icon"),
    path("dynamic/start/", views.dynamic_start, name="mobsf_dynamic_start"),
    path("anti-detect/status/", views.anti_detect_status, name="mobsf_anti_detect_status"),
]
