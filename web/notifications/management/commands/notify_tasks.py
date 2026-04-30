import time
import logging
from django.core.management.base import BaseCommand

logger = logging.getLogger(__name__)

TRIGGER_STATUSES = (
    "reported",
    "failed_analysis",
    "failed_processing",
    "failed_reporting",
)


class Command(BaseCommand):
    help = "Poll CAPE task status dan kirim notifikasi ke user"

    def add_arguments(self, parser):
        parser.add_argument("--interval", type=int, default=20)
        parser.add_argument("--once", action="store_true")

    def handle(self, *args, **options):
        interval = options["interval"]
        run_once = options["once"]
        self.stdout.write(self.style.SUCCESS(
            f"[notify_tasks] Polling setiap {interval} detik..."
        ))
        while True:
            try:
                count = self._process()
                if count:
                    self.stdout.write(self.style.SUCCESS(
                        f"  -> {count} notifikasi dibuat"
                    ))
                else:
                    self.stdout.write(f"  -> 0 notifikasi baru")
            except Exception as e:
                logger.error(f"[notify_tasks] Error: {e}", exc_info=True)
                self.stderr.write(f"[notify_tasks] Error: {e}")
            if run_once:
                break
            time.sleep(interval)

    def _get_db_with_retry(self, max_attempts=5, wait=3):
        from lib.cuckoo.core.database import Database
        last_err = None
        for attempt in range(max_attempts):
            try:
                db = Database()
                return db
            except Exception as e:
                last_err = e
                time.sleep(wait)
        raise Exception(f"Gagal connect DB setelah {max_attempts} percobaan: {last_err}")

    def _list_tasks_with_retry(self, db, status, limit=100, max_attempts=5, wait=3):
        last_err = None
        for attempt in range(max_attempts):
            try:
                return db.list_tasks(status=status, limit=limit)
            except Exception as e:
                last_err = e
                if "locked" in str(e).lower():
                    self.stdout.write(f"  [retry {attempt+1}] database locked, tunggu {wait}s...")
                    time.sleep(wait)
                else:
                    raise
        raise Exception(f"list_tasks gagal setelah {max_attempts} percobaan: {last_err}")

    def _process(self):
        from notifications.signals import create_task_notification
        from notifications.models import Notification

        db = self._get_db_with_retry()
        created = 0

        for status in TRIGGER_STATUSES:
            try:
                tasks = self._list_tasks_with_retry(db, status=status, limit=100)
            except Exception as e:
                logger.error(f"[notify_tasks] list_tasks error status={status}: {e}")
                self.stderr.write(f"  list_tasks error ({status}): {e}")
                continue

            for task in tasks:
                try:
                    d = task.to_dict()
                    task_id = d.get("id")
                    if not task_id:
                        continue

                    user_id = d.get("user_id")
                    if not user_id:
                        logger.debug(f"[notify_tasks] task #{task_id} tidak punya user_id, skip")
                        continue

                    already = Notification.objects.filter(
                        link=f"/analysis/{task_id}/",
                        type__in=("success", "error"),
                    ).exists()
                    if already:
                        continue

                    result = create_task_notification(
                        task_id=task_id,
                        status=status,
                        owner_user_id=user_id,
                    )
                    if result:
                        created += 1
                        self.stdout.write(self.style.SUCCESS(
                            f"  OK task #{task_id} ({status}) -> user_id={user_id}"
                        ))
                    else:
                        self.stdout.write(
                            f"  SKIP task #{task_id} user_id={user_id} (user tidak ditemukan atau pref off)"
                        )
                except Exception as e:
                    logger.error(f"[notify_tasks] task error: {e}")
                    self.stderr.write(f"  task error: {e}")
        return created
