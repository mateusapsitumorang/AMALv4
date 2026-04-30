# Copyright (C) 2010-2015 Cuckoo Foundation.
# This file is part of Cuckoo Sandbox - http://www.cuckoosandbox.org
# See the file 'docs/LICENSE' for copying permission.

import logging
import os
import sys
import socket
from datetime import datetime
from collections import OrderedDict
from datetime import datetime, timedelta
from pathlib import Path

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.views.decorators.http import require_safe


sys.path.append(settings.CUCKOO_PATH)

from lib.cuckoo.common.web_utils import top_detections, statistics as get_full_statistics
from lib.cuckoo.core.data.task import (
    TASK_COMPLETED,
    TASK_DISTRIBUTED,
    TASK_FAILED_ANALYSIS,
    TASK_FAILED_PROCESSING,
    TASK_FAILED_REPORTING,
    TASK_PENDING,
    TASK_RECOVERED,
    TASK_REPORTED,
    TASK_RUNNING,
    Task,
)
from lib.cuckoo.core.database import Database
from django_otp.decorators import otp_required

log = logging.getLogger(__name__)

HAVE_MONGO = False
mongo_aggregate = None
mongo_find_one = None
try:
    from dev_utils.mongodb import mongo_aggregate, mongo_find_one
    HAVE_MONGO = True
except ImportError:
    pass


class conditional_login_required:
    def __init__(self, dec, condition):
        self.decorator = dec
        self.condition = condition

    def __call__(self, func):
        if settings.ANON_VIEW:
            return func
        if not self.condition:
            return func
        return self.decorator(func)


def format_number_with_space(number):
    return f"{number:,}".replace(",", " ")


def _build_task_statistics(db, days=7):
    """Query task stats directly from SQL — always works without MongoDB."""
    stats = {"total": 0, "average": "0", "tasks": OrderedDict()}
    now = datetime.now()

    try:
        from sqlalchemy import func as sa_func, select

        with db.session() as session:
            start_date = now - timedelta(days=days)

            # Total completed/reported tasks in the timeframe
            total = session.scalar(
                select(sa_func.count(Task.id)).where(
                    Task.completed_on >= start_date
                )
            ) or 0
            stats["total"] = total
            stats["average"] = f"{round(total / max(days, 1), 2):.2f}"

            # Per-day breakdown
            for i in range(days):
                day_dt = now - timedelta(days=i)
                day_str = day_dt.strftime("%Y-%m-%d")
                day_start = day_dt.replace(hour=0, minute=0, second=0, microsecond=0)
                day_end   = day_dt.replace(hour=23, minute=59, second=59, microsecond=999999)

                added = session.scalar(
                    select(sa_func.count(Task.id)).where(
                        Task.added_on >= day_start, Task.added_on <= day_end
                    )
                ) or 0

                reported = session.scalar(
                    select(sa_func.count(Task.id)).where(
                        Task.added_on >= day_start,
                        Task.added_on <= day_end,
                        Task.status == TASK_REPORTED,
                    )
                ) or 0

                failed = session.scalar(
                    select(sa_func.count(Task.id)).where(
                        Task.added_on >= day_start,
                        Task.added_on <= day_end,
                        Task.status.in_([
                            TASK_FAILED_ANALYSIS,
                            TASK_FAILED_PROCESSING,
                            TASK_FAILED_REPORTING,
                        ]),
                    )
                ) or 0

                stats["tasks"][day_str] = {
                    "added": added,
                    "reported": reported,
                    "failed": failed,
                }
    except Exception as e:
        log.error("Task statistics DB error: %s", e, exc_info=True)

    return stats


def _get_mongo_stats(days=7):
    """Fetch detections, ASNs and module-perf from MongoDB (optional)."""
    if not HAVE_MONGO or mongo_aggregate is None:
        return {}

    stats = {}
    date_str = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")

    def agg(pipeline):
        try:
            return list(mongo_aggregate("analysis", pipeline))
        except Exception as e:
            log.debug("mongo_aggregate error: %s", e)
            return []

    # Top detections
    rows = agg([
        {"$match": {"info.started": {"$gte": date_str}, "detections.family": {"$exists": True, "$ne": []}}},
        {"$unwind": "$detections.family"},
        {"$group": {"_id": "$detections.family", "total": {"$sum": 1}}},
        {"$sort": {"total": -1}},
        {"$limit": 20},
    ])
    if rows:
        stats["detections"] = {"items": [{"family": r["_id"], "total": r["total"]} for r in rows]}

    # Top ASNs
    rows = agg([
        {"$match": {"info.started": {"$gte": date_str}, "network.hosts.asn": {"$exists": True, "$ne": ""}}},
        {"$unwind": "$network.hosts"},
        {"$match": {"network.hosts.asn": {"$exists": True, "$ne": ""}}},
        {"$group": {"_id": "$network.hosts.asn", "total": {"$sum": 1}}},
        {"$sort": {"total": -1}},
        {"$limit": 20},
    ])
    if rows:
        stats["asns"] = [{"asn": r["_id"], "total": r["total"]} for r in rows]

    # Module performance
    for module in ("processing", "signatures", "reporting"):
        rows = agg([
            {"$match": {"info.started": {"$gte": date_str}}},
            {"$project": {f"statistics.{module}": 1}},
            {"$unwind": f"$statistics.{module}"},
            {"$group": {"_id": f"$statistics.{module}.name",
                        "total": {"$sum": f"$statistics.{module}.time"},
                        "runs": {"$sum": 1}}},
            {"$sort": {"total": -1}},
        ])
        if rows:
            stats[module] = OrderedDict(
                (r["_id"], {
                    "total":   round(r["total"], 2),
                    "runs":    r["runs"],
                    "average": round(r["total"] / max(r["runs"], 1), 2),
                })
                for r in rows
            )
    return stats

def _get_recent_analyses(limit=5):
    """Fetch the N most recent completed/reported analyses for the dashboard."""
    recent = []
    try:
        db = Database()
        tasks = db.list_tasks(
            limit=limit,
            not_status=TASK_PENDING,
            order_by=Task.id.desc(),
        )
        for task in tasks:
            info = task.to_dict()
            if info.get("category") in ("file", "pcap", "static") and info.get("sample_id"):
                sample = db.view_sample(info["sample_id"])
                if sample:
                    info["sample"] = sample.to_dict()
                info["filename"] = os.path.basename(info.get("target", ""))
            elif info.get("category") == "url":
                info["filename"] = info.get("target", "")
            else:
                info["filename"] = os.path.basename(info.get("target", ""))

            # Try to get detections from MongoDB
            if HAVE_MONGO and mongo_find_one is not None:
                try:
                    rtmp = mongo_find_one(
                        "analysis",
                        {"info.id": int(info["id"])},
                        {"detections": 1, "malscore": 1, "_id": 0},
                        sort=[("_id", -1)],
                    )
                    if rtmp:
                        info["detections"] = rtmp.get("detections", "")
                        info["malscore"] = rtmp.get("malscore", 0)
                except Exception:
                    pass

            if info.get("machine"):
                info["machine"] = os.path.basename(info["machine"].strip(".vmx"))
            
            # Check if PDF report exists
            pdf_path = Path(settings.CUCKOO_PATH) / "storage" / "analyses" / str(info["id"]) / "reports" / "report.pdf"
            info["has_pdf"] = pdf_path.exists()
            
            recent.append(info)
    except Exception as e:
        log.warning("Recent analyses fetch error: %s", e)
    return recent

def _get_machines_list():
    try:
        from lib.cuckoo.core.database import Database as MachineDB
        from lib.cuckoo.common.config import Config
        machine_db = MachineDB()
        web_conf = Config("web")
        
        machines = []
        for machine in machine_db.list_machines():
            tags = [tag.name for tag in machine.tags]
            label = f"{machine.label}:{machine.arch}"
            if tags:
                label = f"{label}:{','.join(tags)}"
            if web_conf.linux.enabled:
                label = machine.platform + ":" + label
            machines.append((machine.label, label))
        
        if web_conf.all_vms.enabled:
            machines.insert(1, ("all", "All"))
        
        return machines
    except Exception as e:
        log.warning("Failed to load machines list: %s", e)
        return []

# @otp_required
@require_safe
@conditional_login_required(login_required, settings.WEB_AUTHENTICATION)
def index(request):

    machines = _get_machines_list()


    db = Database()
    days = 7

    report = dict(
        total_samples=format_number_with_space(db.count_samples()),
        total_tasks=format_number_with_space(db.count_tasks()),
        states_count={},
        estimate_hour=None,
        estimate_day=None,
    )

    states = (
        TASK_PENDING,
        TASK_RUNNING,
        TASK_DISTRIBUTED,
        TASK_COMPLETED,
        TASK_RECOVERED,
        TASK_REPORTED,
        TASK_FAILED_ANALYSIS,
        TASK_FAILED_PROCESSING,
        TASK_FAILED_REPORTING,
    )
    for state in states:
        report["states_count"][state] = db.count_tasks(status=state)

    # Throughput estimate
    tasks_done = db.count_tasks(status=TASK_COMPLETED) + db.count_tasks(status=TASK_REPORTED)
    if tasks_done:
        started, completed = db.minmax_tasks()
        if started and completed and int(completed - started):
            hourly = 60 * 60 * tasks_done / (completed - started)
        else:
            hourly = 0
        report["estimate_hour"] = format_number_with_space(int(hourly))
        report["estimate_day"]  = format_number_with_space(int(24 * hourly))
        report["top_detections"] = top_detections()

    # Recent analyses (must run BEFORE _build_task_statistics which closes the session)
    recent_analyses = _get_recent_analyses(limit=5)

    # Build statistics
    statistics_data = {}

    try:
        statistics_data = get_full_statistics(days)
    except Exception as e:
        log.error("Failed to load full statistics for dashboard: %s", e)
        statistics_data = {}

    statistics_data.update(_build_task_statistics(db, days=days))

    mongo_dashboard_stats = _get_mongo_stats(days=days)
    
    if "asns" in mongo_dashboard_stats:
        statistics_data["asns"] = mongo_dashboard_stats["asns"]
        
    if "detections" in mongo_dashboard_stats:
        statistics_data["detections"] = mongo_dashboard_stats["detections"].get("items", [])

    if "signatures" in mongo_dashboard_stats:
        top_5_signatures = list(mongo_dashboard_stats["signatures"].items())[:5]
        statistics_data["custom_statistics"] = dict(top_5_signatures)

    if not statistics_data.get("distributed_tasks"):
        
        try:
            server_name = f"{socket.gethostname()} (Jakarta, ID)"
        except Exception:
            server_name = "AMAL-Main-Node (Jakarta, ID)"

        local_cluster = {}
        today_str = datetime.now().strftime("%Y-%m-%d")
        
        if "tasks" in statistics_data:
            for day, info in statistics_data["tasks"].items():
                tasks_total = info.get("added", 0) + info.get("reported", 0) + info.get("failed", 0)
                if tasks_total > 0 or day == today_str:
                    local_cluster[day] = {server_name: tasks_total}

        if not local_cluster:
            local_cluster = {today_str: {server_name: 0}}

        statistics_data["distributed_tasks"] = local_cluster

    return render(request, "dashboard/index.html", {
        "report":           report,
        "statistics":       statistics_data,
        "days":             days,
        "recent_analyses":  recent_analyses,
        "machines":         machines,
    })

    
