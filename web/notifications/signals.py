import logging
logger = logging.getLogger(__name__)

def create_task_notification(task_id, status, owner_username=None, owner_user_id=None):
    try:
        from django.contrib.auth.models import User
        from .models import Notification

        owner_user = None
        if owner_user_id:
            owner_user = User.objects.filter(id=int(owner_user_id)).first()
        if not owner_user and owner_username:
            if str(owner_username).isdigit():
                owner_user = User.objects.filter(id=int(owner_username)).first()
            else:
                owner_user = User.objects.filter(
                    username__iexact=str(owner_username)
                ).first()

        if not owner_user:
            logger.debug(f"[NOTIF] User not found for task {task_id}")
            return False

        notif_pref = True
        try:
            if hasattr(owner_user, 'userprofile'):
                profile = owner_user.userprofile
                if status == 'reported':
                    notif_pref = getattr(profile, 'notif_analysis', True)
                else:
                    notif_pref = getattr(profile, 'notif_report', True)
        except Exception:
            pass

        if not notif_pref:
            return False

        already = Notification.objects.filter(
            user=owner_user,
            link=f"/analysis/{task_id}/",
            type__in=("success", "error"),
        ).exists()
        if already:
            return False

        if status == "reported":
            Notification.objects.create(
                user=owner_user,
                type="success",
                title="Analysis Complete",
                message=f"Analysis #{task_id} has been successfully reported.",
                link=f"/analysis/{task_id}/",
            )
        elif status in ("failed_analysis", "failed_processing", "failed_reporting"):
            label = {
                "failed_analysis":   "analysis",
                "failed_processing": "processing",
                "failed_reporting":  "reporting",
            }.get(status, "unknown stage")
            Notification.objects.create(
                user=owner_user,
                type="error",
                title="Analysis Failed",
                message=f"Analysis #{task_id} failed during {label}.",
                link=f"/analysis/{task_id}/",
            )
        else:
            return False

        logger.info(f"[NOTIF] Notification created for task {task_id} "
                    f"({status}) → user: {owner_user.username}")
        return True

    except Exception as e:
        logger.error(f"[NOTIF] create_task_notification error task {task_id}: {e}")
        return False