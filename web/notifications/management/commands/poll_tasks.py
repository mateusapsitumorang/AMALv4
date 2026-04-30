from django.core.management.base import BaseCommand
from notifications.models import Notification
import psycopg2
import time
import logging

logger = logging.getLogger(__name__)

# CAPEv2 PostgreSQL Configuration
CAPE_DB = {
    'host':     'localhost',
    'port':     5432,
    'dbname':   'cape',
    'user':     'cape',
    'password': 'SuperPuperSecret',
}

class Command(BaseCommand):
    help = 'Polls CAPEv2 PostgreSQL and generates automatic notifications'

    def handle(self, *args, **kwargs):
        self.stdout.write(self.style.SUCCESS("[*] CAPEv2 task polling started..."))
        
        # Keep track of notified tasks to avoid duplicates
        seen_links = set(Notification.objects.values_list('link', flat=True))
        last_processed_id = 0

        while True:
            try:
                conn = psycopg2.connect(**CAPE_DB)
                cur  = conn.cursor()
                
                # Fetch tasks that have finished or failed
                cur.execute("""
                    SELECT id, target, status::text
                    FROM tasks
                    WHERE id > %s
                      AND status::text IN ('reported', 'failed_reporting', 'failed_analysis')
                    ORDER BY id ASC
                """, (last_processed_id,))
                
                tasks = cur.fetchall()
                cur.close()
                conn.close()

                for task_id, target, status in tasks:
                    link = f'/analysis/{task_id}/'
                    
                    # Update the high-water mark for IDs
                    if task_id > last_processed_id:
                        last_processed_id = task_id
                    
                    # Skip if we have already notified for this specific task link
                    if link in seen_links:
                        continue
                    
                    seen_links.add(link)

                    if status == 'reported':
                        Notification.objects.create(
                            type='success',
                            title=f'Analysis Completed #{task_id}',
                            message=f'Task #{task_id} - {target} has finished analyzing.',
                            link=link
                        )
                        self.stdout.write(self.style.SUCCESS(f"[+] SUCCESS: Task #{task_id} notified."))

                    elif status == 'failed_reporting':
                        Notification.objects.create(
                            type='error',
                            title=f'Reporting Failed #{task_id}',
                            message=f'Task #{task_id} - {target} failed during the reporting stage.',
                            link=link
                        )
                        self.stdout.write(self.style.WARNING(f"[!] FAILED_REPORTING: Task #{task_id} notified."))

                    elif status == 'failed_analysis':
                        Notification.objects.create(
                            type='error',
                            title=f'Analysis Failed #{task_id}',
                            message=f'Task #{task_id} - {target} failed during analysis.',
                            link=link
                        )
                        self.stdout.write(self.style.NOTICE(f"[!] FAILED_ANALYSIS: Task #{task_id} notified."))

            except Exception as e:
                error_msg = f"Polling Error: {e}"
                self.stdout.write(self.style.ERROR(f"[ERROR] {error_msg}"))
                logger.error(error_msg)

            # Wait for 10 seconds before the next poll
            time.sleep(10)