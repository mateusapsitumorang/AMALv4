import json
import logging
import mimetypes
import os
import shutil
import socket
import subprocess
import threading
import time
import base64
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.csrf import csrf_exempt

logger = logging.getLogger(__name__)

# In-memory cache for security scores: {md5: score}
_score_cache = {}
_score_cache_lock = threading.Lock()
MOBSF_API_URL = "http://127.0.0.1:8002"
# Public URL for browser-facing links (HTTPS via nginx)
MOBSF_PUBLIC_URL = "https://192.168.88.244:8001"
MOBSF_API_KEY = "eeea2e461a233af51e247b700076656fe90d657ae9ca167a6eb335a9bf593d84"
MOBSF_TIMEOUT = 300
MOBSF_CONTAINER = "mobsf"
MOBSF_DOWNLOADS_PATH = "/home/mobsf/.MobSF/downloads"
MOBSF_HOST_ADB = getattr(settings, "MOBSF_HOST_ADB", "/opt/android-sdk/platform-tools/adb")
MOBSF_RUNTIME_DEFAULT_IDENTIFIER = getattr(settings, "MOBSF_RUNTIME_DEFAULT_IDENTIFIER", "172.17.0.1:5555")
MOBSF_RUNTIME_FIX_RETRIES = int(getattr(settings, "MOBSF_RUNTIME_FIX_RETRIES", 3))


EMULATOR_SPOOF_PROPS = {
    "ro.product.model": "Pixel 6",
    "ro.product.manufacturer": "Google",
    "ro.product.brand": "google",
    "ro.kernel.qemu": "0",           
    "ro.hardware": "oriole",
    "ro.build.tags": "release-keys",
    "ro.build.type": "user",
    "ro.debuggable": "0",
}

FRIDA_SCRIPT_PATH = os.path.join(os.path.dirname(__file__), "frida_anti_detect.js")


def _mobsf_headers():
    return {"Authorization": MOBSF_API_KEY}


def _resolve_adb_binary():
    """Resolve an ADB binary that can be used on the host."""
    candidates = [MOBSF_HOST_ADB, "adb"]
    for candidate in candidates:
        if os.path.isabs(candidate):
            if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
                return candidate
        else:
            resolved = shutil.which(candidate)
            if resolved:
                return resolved
    return None


def _ensure_host_adb_server():
    """Start host ADB server in externally reachable mode for MobSF container."""
    adb_bin = _resolve_adb_binary()
    if not adb_bin:
        return False, "ADB binary not found on host"

    try:
        run = subprocess.run(
            [adb_bin, "-a", "start-server"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        if run.returncode == 0:
            return True, (run.stdout or run.stderr or "ADB server started").strip()
        return False, (run.stderr or run.stdout or "Failed to start ADB server").strip()
    except Exception as e:
        return False, str(e)


def _fetch_dynamic_runtime_info():
    """Fetch MobSF dynamic runtime metadata (identifier, android version)."""
    try:
        resp = requests.get(
            f"{MOBSF_API_URL}/api/v1/dynamic/get_apps",
            headers=_mobsf_headers(),
            timeout=20,
        )
        if resp.status_code == 200:
            payload = resp.json()
            if isinstance(payload, dict):
                return payload
    except Exception as e:
        logger.warning("Failed to fetch MobSF dynamic runtime info: %s", e)
    return {}


def _build_identifier_candidates(primary_identifier):
    """Build candidate runtime identifiers ordered by likely success."""
    raw = [
        primary_identifier,
        MOBSF_RUNTIME_DEFAULT_IDENTIFIER,
        "172.17.0.1:5555",
        "host.docker.internal:5555",
        "emulator-5554",
    ]
    seen = set()
    candidates = []
    for item in raw:
        ident = (item or "").strip()
        if ident and ident not in seen:
            seen.add(ident)
            candidates.append(ident)
    return candidates


def _call_mobsfy(identifier):
    """Call MobSF Android mobsfy endpoint for a given identifier."""
    try:
        resp = requests.post(
            f"{MOBSF_API_URL}/api/v1/android/mobsfy",
            headers=_mobsf_headers(),
            data={"identifier": identifier},
            timeout=MOBSF_TIMEOUT,
        )
        payload = {}
        try:
            payload = resp.json()
        except Exception:
            payload = {}

        if resp.status_code == 200 and payload.get("status") == "ok":
            return True, payload

        message = payload.get("message") if isinstance(payload, dict) else None
        if not message:
            message = f"HTTP {resp.status_code}: {resp.text[:200]}"
        return False, {"status": "failed", "message": message}
    except Exception as e:
        return False, {"status": "failed", "message": str(e)}


def _prime_mobsf_adb_connection(identifier):
    """Prime adb_mobsf connection in container before running full MobSFy flow."""
    try:
        run = subprocess.run(
            ["docker", "exec", MOBSF_CONTAINER, "/home/mobsf/adb_mobsf", "connect", identifier],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        output = (run.stdout or run.stderr or "").strip()
        return run.returncode == 0, output
    except Exception as e:
        return False, str(e)


def _is_tcp_open(host, port, timeout=2):
    """Check if a TCP endpoint is reachable."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False

def _spoof_emulator_properties():
    """Set ADB properties untuk menyamarkan emulator."""
    adb_bin = _resolve_adb_binary()
    if not adb_bin:
        return False, "ADB not found"

    results = []
    for prop, value in EMULATOR_SPOOF_PROPS.items():
        try:
            run = subprocess.run(
                [adb_bin, "-s", MOBSF_RUNTIME_DEFAULT_IDENTIFIER,
                 "shell", "setprop", prop, value],
                capture_output=True, text=True, timeout=10,
            )
            results.append(f"{prop}={'ok' if run.returncode == 0 else 'fail'}")
        except Exception as e:
            results.append(f"{prop}=error:{e}")

    return True, "; ".join(results)

def _load_frida_script():
    """Load anti-detection Frida script content."""
    try:
        with open(FRIDA_SCRIPT_PATH, "r") as f:
            return f.read()
    except FileNotFoundError:
        logger.warning("Frida anti-detect script not found at %s", FRIDA_SCRIPT_PATH)
        return None


def _inject_frida_script(package_name: str) -> dict:
    """
    Inject the Frida anti-emulator script into a running app via the MobSF API.
    Called after the app is run in dynamic analysis.
    """
    script_content = _load_frida_script()
    if not script_content:
        return {"success": False, "error": "Script not found"}

    try:
        resp = requests.post(
            f"{MOBSF_API_URL}/api/v1/frida/instrument",
            headers=_mobsf_headers(),
            data={
                "default_hooks": "api_monitor,ssl_pinning_bypass,root_bypass",
                "auxiliary_hooks": "",
                "frida_code": script_content,
                "package": package_name,
            },
            timeout=30,
        )
        if resp.status_code == 200:
            return {"success": True, "data": resp.json()}
        return {"success": False, "error": f"HTTP {resp.status_code}: {resp.text[:200]}"}
    except Exception as e:
        logger.exception("Frida injection error")
        return {"success": False, "error": str(e)}

def _get_scan_score(file_hash):
    """Fetch security score for a single scan hash, with in-memory cache."""
    with _score_cache_lock:
        if file_hash in _score_cache:
            return _score_cache[file_hash]
    try:
        resp = requests.post(
            f"{MOBSF_API_URL}/api/v1/report_json",
            headers=_mobsf_headers(),
            data={"hash": file_hash},
            timeout=60,
        )
        if resp.status_code == 200:
            data = resp.json()
            appsec = data.get("appsec", {})
            if isinstance(appsec, dict):
                score = appsec.get("security_score", None)
                with _score_cache_lock:
                    _score_cache[file_hash] = score
                return score
    except Exception:
        pass
    return None


@login_required
def index(request):
    """MobSF main page — upload form + recent scans."""
    recent = []
    try:
        resp = requests.get(
            f"{MOBSF_API_URL}/api/v1/scans",
            headers=_mobsf_headers(),
            timeout=10,
        )
        if resp.status_code == 200:
            data = resp.json()
            recent = data.get("content", data) if isinstance(data, dict) else data
            if isinstance(recent, list):
                recent = recent[:20]
            else:
                recent = []

            # Enrich each scan with its security score (parallel)
            hashes = [s.get("MD5", "") for s in recent if s.get("MD5")]
            scores = {}
            if hashes:
                with ThreadPoolExecutor(max_workers=8) as pool:
                    future_map = {pool.submit(_get_scan_score, h): h for h in hashes}
                    for f in as_completed(future_map):
                        scores[future_map[f]] = f.result()
            for scan in recent:
                scan["SECURITY_SCORE"] = scores.get(scan.get("MD5", ""))
    except Exception as e:
        logger.warning("MobSF recent scans fetch failed: %s", e)

    return render(request, "mobsf/index.html", {"recent_scans": recent})


def _trigger_scan_async(file_hash, scan_type, file_name):
    """Fire MobSF scan in a background thread so the request doesn't block."""
    def _run():
        try:
            requests.post(
                f"{MOBSF_API_URL}/api/v1/scan",
                headers=_mobsf_headers(),
                data={"hash": file_hash, "scan_type": scan_type, "file_name": file_name},
                timeout=MOBSF_TIMEOUT,
            )
        except Exception as e:
            logger.warning("MobSF background scan error for %s: %s", file_hash, e)

    t = threading.Thread(target=_run, daemon=True)
    t.start()


@login_required
def upload(request):
    """Upload APK/IPA/ZIP to MobSF and trigger static scan."""
    if request.method != "POST":
        return redirect("mobsf")

    uploaded_file = request.FILES.get("sample")
    if not uploaded_file:
        return render(request, "mobsf/index.html", {
            "error": "No file selected. Please choose an APK, IPA, or ZIP file.",
            "recent_scans": [],
        })

    # Validate file extension
    allowed_ext = (".apk", ".ipa", ".zip", ".appx", ".xapk", ".apks")
    if not uploaded_file.name.lower().endswith(allowed_ext):
        return render(request, "mobsf/index.html", {
            "error": f"Invalid file type. Allowed: {', '.join(allowed_ext)}",
            "recent_scans": [],
        })

    try:
        # 1) Upload to MobSF (usually fast)
        upload_resp = requests.post(
            f"{MOBSF_API_URL}/api/v1/upload",
            headers=_mobsf_headers(),
            files={"file": (uploaded_file.name, uploaded_file.read(), uploaded_file.content_type)},
            timeout=120,
        )

        if upload_resp.status_code != 200:
            return render(request, "mobsf/index.html", {
                "error": f"MobSF upload failed (HTTP {upload_resp.status_code}): {upload_resp.text[:200]}",
                "recent_scans": [],
            })

        upload_data = upload_resp.json()
        file_hash = upload_data.get("hash", "")
        scan_type = upload_data.get("scan_type", "")
        file_name = upload_data.get("file_name", uploaded_file.name)

        if not file_hash:
            return render(request, "mobsf/index.html", {
                "error": "MobSF did not return a file hash.",
                "recent_scans": [],
            })

        # 2) Fire scan in background thread — don't block the HTTP response
        _trigger_scan_async(file_hash, scan_type, file_name)

        # 3) Redirect immediately to report page (will show "scanning" state)
        return redirect("mobsf_report", scan_type=scan_type, file_hash=file_hash)

    except requests.exceptions.ConnectionError:
        return render(request, "mobsf/index.html", {
            "error": "Cannot connect to MobSF. Is the MobSF Docker container running?",
            "recent_scans": [],
        })
    except Exception as e:
        logger.exception("MobSF upload error")
        return render(request, "mobsf/index.html", {
            "error": f"Unexpected error: {str(e)}",
            "recent_scans": [],
        })


@login_required
def scan(request, scan_type, file_hash):
    """Trigger a scan (static or rescan)."""
    try:
        resp = requests.post(
            f"{MOBSF_API_URL}/api/v1/scan",
            headers=_mobsf_headers(),
            data={"hash": file_hash, "scan_type": scan_type},
            timeout=MOBSF_TIMEOUT,
        )
        if resp.status_code == 200:
            return redirect("mobsf_report", scan_type=scan_type, file_hash=file_hash)
    except Exception as e:
        logger.exception("MobSF scan error")

    return redirect("mobsf")


@login_required
def report(request, scan_type, file_hash):
    """Fetch and display MobSF scan report."""
    report_data = {}
    error = None
    scanning = False

    try:
        resp = requests.post(
            f"{MOBSF_API_URL}/api/v1/report_json",
            headers=_mobsf_headers(),
            data={"hash": file_hash},
            timeout=30,
        )

        if resp.status_code == 200:
            report_data = resp.json()
        elif resp.status_code in (404, 500):
            # Scan likely still in progress
            scanning = True
        else:
            error = f"Report not available (HTTP {resp.status_code})."
    except requests.exceptions.ConnectionError:
        error = "Cannot connect to MobSF service."
    except Exception as e:
        logger.exception("MobSF report error")
        error = f"Error fetching report: {str(e)}"

    # Extract security_score and appsec summary from nested dict
    security_score = 0
    high_count = 0
    warning_count = 0
    info_count = 0
    secure_count = 0
    trackers_detected = 0
    total_trackers = 0
    appsec = report_data.get("appsec", {})
    if isinstance(appsec, dict):
        security_score = appsec.get("security_score", 0) or 0
        high_count = len(appsec.get("high", []))
        warning_count = len(appsec.get("warning", []))
        info_count = len(appsec.get("info", []))
        secure_count = len(appsec.get("secure", []))
        trackers_detected = appsec.get("trackers", 0)
        total_trackers = appsec.get("total_trackers", 0)

    # Build network graph data from URLs, domains, emails
    network_domains = []
    network_urls = []
    network_emails = []

    raw_domains = report_data.get("domains", [])
    if isinstance(raw_domains, list):
        for d in raw_domains:
            if isinstance(d, dict):
                domain = d.get("domain", "")
                geolocation = d.get("geolocation", "")
                ip = d.get("ip", "")
                if domain:
                    network_domains.append({"domain": domain, "geolocation": geolocation, "ip": ip})
            elif isinstance(d, str) and d:
                network_domains.append({"domain": d, "geolocation": "", "ip": ""})

    raw_urls = report_data.get("urls", [])
    if isinstance(raw_urls, list):
        for u in raw_urls:
            url_str = u.get("urls", u) if isinstance(u, dict) else u
            if url_str:
                network_urls.append(str(url_str))

    raw_emails = report_data.get("emails", [])
    if isinstance(raw_emails, list):
        network_emails = [str(e) for e in raw_emails if e]

    return render(request, "mobsf/report.html", {
        "report": report_data,
        "file_hash": file_hash,
        "scan_type": scan_type,
        "error": error,
        "scanning": scanning,
        "mobsf_url": MOBSF_PUBLIC_URL,
        "security_score": security_score,
        "high_count": high_count,
        "warning_count": warning_count,
        "info_count": info_count,
        "secure_count": secure_count,
        "trackers_detected": trackers_detected,
        "total_trackers": total_trackers,
        "network_domains_json": json.dumps(network_domains),
        "network_urls_json": json.dumps(network_urls),
        "network_emails_json": json.dumps(network_emails),
        "app_name": report_data.get("app_name", "App"),
    })


@login_required
def recent_scans(request):
    """API: return recent scans as JSON."""
    try:
        resp = requests.get(
            f"{MOBSF_API_URL}/api/v1/scans",
            headers=_mobsf_headers(),
            timeout=10,
        )
        if resp.status_code == 200:
            return JsonResponse(resp.json(), safe=False)
    except Exception:
        pass
    return JsonResponse({"content": []})


@login_required
def runtime_health(request):
    """Runtime status/fix endpoint for MobSF Android dynamic analysis."""
    runtime_info = _fetch_dynamic_runtime_info()
    identifier = runtime_info.get("identifier") or MOBSF_RUNTIME_DEFAULT_IDENTIFIER
    android_version = runtime_info.get("android_version")

    if request.method != "POST":
        reachable = _is_tcp_open("127.0.0.1", 8002)
        adb_ok = _is_tcp_open("127.0.0.1", 5037)
        return JsonResponse(
            {
                "error": False,
                "data": {
                    "identifier": identifier,
                    "android_version": android_version,
                    "mobsf_api": "online" if reachable else "offline",
                    "adb_server": "online" if adb_ok else "offline",
                    "runtime_ready": bool(identifier),
                },
            }
        )

    traces = []
    ok, adb_message = _ensure_host_adb_server()
    traces.append(f"Host ADB: {adb_message}")
    if not ok:
        return JsonResponse(
            {
                "error": True,
                "error_value": "Cannot start host ADB server",
                "data": {"identifier": identifier, "trace": traces},
            },
            status=500,
        )

    last_error = "Unknown error"
    candidates = _build_identifier_candidates(identifier)
    for attempt in range(1, max(1, MOBSF_RUNTIME_FIX_RETRIES) + 1):
        for candidate in candidates:
            primed, prime_message = _prime_mobsf_adb_connection(candidate)
            if prime_message:
                traces.append(f"Prime {candidate}: {prime_message[:180]}")
            if not primed and (
                "failed to connect to '172.17.0.1:5037'" in prime_message
                or "cannot connect to daemon" in prime_message
            ):
                _ensure_host_adb_server()
                time.sleep(1)

            success, payload = _call_mobsfy(candidate)
            if success:
                version = payload.get("android_version", android_version)
                notification = "MobSF agents and Frida server installed."
                if isinstance(version, (int, float)) and version < 5:
                    notification = (
                        "Successfully created MobSF Dynamic Analysis environment. "
                        "Install Xposed framework, then restart and enable modules."
                    )
                return JsonResponse(
                    {
                        "error": False,
                        "data": {
                            "identifier": candidate,
                            "android_version": version,
                            "status": "ok",
                            "notification": notification,
                            "trace": traces,
                        },
                    }
                )

            message = payload.get("message", "Connection failed")
            last_error = message
            traces.append(f"Attempt {attempt} ({candidate}): {message}")

            if "failed to connect to '172.17.0.1:5037'" in message or "cannot connect to daemon" in message:
                _ensure_host_adb_server()
                time.sleep(1)
    spoof_ok, spoof_msg = _spoof_emulator_properties()
    traces.append(f"Emulator spoof: {spoof_msg}")

    return JsonResponse(
        {
            "error": True,
            "error_value": "MobSF runtime setup failed",
            "data": {
                "identifier": identifier,
                "status": "failed",
                "message": last_error,
                "trace": traces,
            },
        },
        status=500,
    )


@login_required
def delete_scan(request, file_hash):
    """Delete a scan from MobSF."""
    if request.method == "POST":
        try:
            requests.post(
                f"{MOBSF_API_URL}/api/v1/delete_scan",
                headers=_mobsf_headers(),
                data={"hash": file_hash},
                timeout=30,
            )
        except Exception as e:
            logger.warning("MobSF delete error: %s", e)
    return redirect("mobsf")


@login_required
def download_pdf(request, file_hash):
    """Download PDF report from MobSF."""
    try:
        resp = requests.post(
            f"{MOBSF_API_URL}/api/v1/download_pdf",
            headers=_mobsf_headers(),
            data={"hash": file_hash},
            timeout=MOBSF_TIMEOUT,
            stream=True,
        )
        if resp.status_code == 200:
            response = HttpResponse(resp.content, content_type="application/pdf")
            response["Content-Disposition"] = f'attachment; filename="mobsf_report_{file_hash[:8]}.pdf"'
            return response
    except Exception as e:
        logger.warning("MobSF PDF download error: %s", e)

    return redirect("mobsf_report", scan_type="apk", file_hash=file_hash)


@login_required
def icon_proxy(request, file_hash):
    """Serve app icon from MobSF container via docker exec."""
    # Determine icon filename — try common extensions
    for ext in ("png", "webp", "svg", "jpg", "jpeg"):
        icon_filename = f"{file_hash}-icon.{ext}"
        icon_path = f"{MOBSF_DOWNLOADS_PATH}/{icon_filename}"
        try:
            result = subprocess.run(
                ["docker", "exec", MOBSF_CONTAINER, "cat", icon_path],
                capture_output=True,
                timeout=5,
            )
            if result.returncode == 0 and result.stdout:
                content_type, _ = mimetypes.guess_type(icon_filename)
                if not content_type:
                    content_type = "image/png"
                resp = HttpResponse(result.stdout, content_type=content_type)
                resp["Cache-Control"] = "public, max-age=86400"
                return resp
        except Exception:
            continue

    # Fallback: return a 1x1 transparent PNG
    transparent_png = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
        b"\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
        b"\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01"
        b"\r\n\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    return HttpResponse(transparent_png, content_type="image/png")

@login_required
def dynamic_start(request):
    """
    Start dynamic analysis with automatic anti-emulator evasion.
    POST: { hash, package }
    """
    if request.method != "POST":
        return JsonResponse({"error": "Method not allowed"}, status=405)

    file_hash = request.POST.get("hash", "")
    package_name = request.POST.get("package", "")

    if not file_hash or not package_name:
        return JsonResponse({"error": "hash and package are required"}, status=400)

    results = {"hash": file_hash, "package": package_name, "steps": []}

    try:
        resp = requests.get(
            f"{MOBSF_API_URL}/api/v1/dynamic/start_analysis",
            headers=_mobsf_headers(),
            params={"hash": file_hash, "re_install": 1, "install": 1},
            timeout=60,
        )
        results["steps"].append({
            "step": "start_analysis",
            "status": "ok" if resp.status_code == 200 else "failed",
            "code": resp.status_code,
        })
    except Exception as e:
        return JsonResponse({"error": f"Cannot start dynamic analysis: {e}"}, status=500)

    import time
    time.sleep(5)  

    inject_result = _inject_frida_script(package_name)
    results["steps"].append({
        "step": "frida_inject",
        "status": "ok" if inject_result["success"] else "failed",
        "detail": inject_result,
    })

    return JsonResponse(results)


@login_required 
def anti_detect_status(request):
    """
    Check the status and capabilities of the anti-detection environment.
    GET: Returns information about the active setup.
    """
    checks = {}

    try:
        result = subprocess.run(
            ["docker", "exec", MOBSF_CONTAINER, "pgrep", "-f", "frida-server"],
            capture_output=True, text=True, timeout=10,
        )
        checks["frida_server"] = "running" if result.returncode == 0 else "not_running"
    except Exception:
        checks["frida_server"] = "unknown"

    checks["anti_detect_script"] = "available" if os.path.exists(FRIDA_SCRIPT_PATH) else "missing"

    checks["adb_connected"] = _is_tcp_open("127.0.0.1", 5037)

    return JsonResponse({
        "error": False,
        "data": checks,
    })
