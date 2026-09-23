# panel_fetchers.py — OTP Panel v5 · ULTIMATE FIXED ENGINE v2
# ══════════════════════════════════════════════════════════════════
# ALL BUGS FIXED (original + newly found):
#  ✅ BUG-2  ims_login      — session cookie verification added
#  ✅ BUG-3  konekta_login  — dashboard URL check (not just "sign")
#  ✅ BUG-4  _captcha       — no hardcoded 4; BeautifulSoup fallback
#  ✅ BUG-5  CSRF           — logs warning, never silently fails
#  ✅ BUG-6  panel_login    — redirect-back-to-login detection added
#  ✅ BUG-8  session expiry — proactive detection via _is_session_expired()
#  ✅ BUG-9  error pages    — now correctly detected as session expiry
#  ✅ BUG-10 proofsms_fetch — properly exported (was dead code)
#  ✅ NEW    timesms_login/fetch — TimeSMS panel (sesskey from Reports)
#  ✅ NEW    _core_fetch    — also checks SMSCDRReports for sesskey
#  ✅ FIX-A  _parse()       — dict rows now handled (VoiceGate compat)
#  ✅ FIX-B  _roxysms_fetch — network error vs session expiry separated
#  ✅ FIX-C  timesms_fetch  — network error vs session expiry separated
#  ✅ FIX-D  panel_login    — laravel_session cookie now also checked
#  ✅ FIX-E  ProofSMS       — proofsms_fetch now dispatched for ProofSMS
#  ✅ FIX-XMS XMS incoming — supports the live HTML table/HTMX row formats
# ══════════════════════════════════════════════════════════════════

import os, re, json, csv, io, logging, html as _html, hashlib, threading, time
from urllib.parse import urljoin
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

NEXOR_SMS_HANDLER_VERSION = "2026-08-26-livewire-v5"

_COOKIE_BASE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cookies")
os.makedirs(_COOKIE_BASE, exist_ok=True)

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

_BASE_HEADERS = {
    "User-Agent":      _UA,
    "Accept":          "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate",
    "Connection":      "keep-alive",
}

_AJAX_HEADERS = {
    "User-Agent":       _UA,
    "Accept":           "application/json, text/javascript, */*; q=0.01",
    "Accept-Language":  "en-US,en;q=0.9",
    "Accept-Encoding":  "gzip, deflate",
    "X-Requested-With": "XMLHttpRequest",
    "Connection":       "keep-alive",
}

# Words that appear on login pages
_LOGIN_PAGE_SIGNALS = [
    "sign in", "signin", "please sign",
    "log in", "please login",
    "authentication required", "session expired",
    "unauthorized", "access denied",
    # NOTE: 'password' & 'username' removed — dashboard pages often have
    # 'Change Password' links which caused false session-expired detection.
]


def _dates():
    today     = datetime.now().strftime("%Y-%m-%d")
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    return f"{yesterday} 00:00:00", f"{today} 23:59:59"


def _session():
    import requests as rq
    s = rq.Session()
    s.headers.update(_BASE_HEADERS)
    return s


###############################################################################
#  API PANEL TYPES — ThirdWave, IPRN Elite, Elite SMS, Rez SMS, Axon,
#  SMSNode, Xisora
#
#  Panel accounts in the legacy engine use username/password columns. For
#  these API panels, username is the account label and password stores the API
#  key/token. This keeps all existing panel types and the SQLite schema intact.
###############################################################################
THIRDWAVE_DEFAULT_URL = "https://clients.thirdwave.im"
ELITE_DEFAULT_URL = "https://api.iprn-elite.com/v1.0"
ELITE_SMS_DEFAULT_URL = "https://elite-sms.com/api"
ELITE_SMS_V1_DEFAULT_URL = "https://elite-sms.com"
REZ_DEFAULT_URL = "https://rezsms.org/api/cdr.php"
AXON_DEFAULT_URL = "https://axonsms.xyz"
SMSNODE_DEFAULT_URL = "https://smsnode.app/api/v1"
XISORA_DEFAULT_URL = "http://51.38.148.122/crapi/reseller/mdr.php"
MJ_SMS_API_DEFAULT_URL = (
    "http://147.93.139.149/ints/login/api/agent_sms.php"
)
AUGESTEL_DEFAULT_URL = "https://augestel.com/api/v1/iprn"
KSI_DEFAULT_URL = "https://www.ksiiprn.com/api/v1/iprn"
IPRN_MIN_REQUEST_INTERVAL_SECONDS = 13

# Augestel documents a five-request-per-minute limit per API key. Accounts
# share the same key in some deployments, so an account-local sleep is not
# enough. Keep one limiter per key and serialize requests across all accounts.
_IPRN_RATE_LOCK = threading.Lock()
_IPRN_NEXT_REQUEST_AT = {}


def _api_window_params(records=100):
    now = datetime.utcnow().replace(microsecond=0)
    return {
        "dt1": (now - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S"),
        "dt2": now.strftime("%Y-%m-%d %H:%M:%S"),
        "records": records,
    }


def _api_base(url: str, default: str) -> str:
    return (url or default).strip().rstrip("/")


def _api_row_value(item: dict, *names: str) -> str:
    if not isinstance(item, dict):
        return ""
    for name in names:
        value = item.get(name)
        if isinstance(value, dict):
            for nested in ("full", "full_message", "message", "text", "content", "body", "value"):
                if nested in value and str(value[nested]).strip():
                    return str(value[nested]).strip()
        if value is not None and str(value).strip():
            return str(value).strip()
    normalized = {
        re.sub(r"[^a-z0-9]", "", str(key).lower()): value
        for key, value in item.items()
    }
    for name in names:
        value = normalized.get(re.sub(r"[^a-z0-9]", "", name.lower()))
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _api_row(stamp, row_id, number, sender, message):
    number = re.sub(r"\D", "", str(number or ""))
    message = str(message or "").strip()
    if not number or not message:
        return None
    row_id = str(row_id or "").strip() or "|".join(
        (str(stamp or ""), number, str(sender or ""), message)
    )
    return [str(stamp or ""), row_id, number, str(sender or ""), None, message]


def _check_json_response(response, label):
    if response.status_code in (401, 403):
        return None
    if response.status_code != 200:
        raise Exception(f"{label} API HTTP {response.status_code}")
    try:
        return response.json()
    except Exception as exc:
        raise Exception(f"{label} response bukan JSON yang valid") from exc


def _iprn_base(url, default):
    """Accept either the documented API base or the Augestel host itself."""
    base = _api_base(url, default)
    if base.lower() in {"https://augestel.com", "https://www.augestel.com"}:
        return f"{base}/api/v1/iprn"
    if base.lower() in {"https://www.ksiiprn.com", "https://ksiiprn.com"}:
        return f"{base}/api/v1/iprn"
    return base


def _iprn_wait_for_key(token):
    """Pace requests globally per API key before hitting the five/minute cap."""
    key = str(token or "").strip()
    if not key:
        return
    with _IPRN_RATE_LOCK:
        now = time.monotonic()
        wait_for = max(0.0, _IPRN_NEXT_REQUEST_AT.get(key, 0.0) - now)
        if wait_for:
            time.sleep(wait_for)
        _IPRN_NEXT_REQUEST_AT[key] = time.monotonic() + IPRN_MIN_REQUEST_INTERVAL_SECONDS


def _iprn_defer_key(token, seconds):
    key = str(token or "").strip()
    if not key:
        return
    try:
        seconds = max(0.0, float(seconds))
    except (TypeError, ValueError):
        return
    with _IPRN_RATE_LOCK:
        _IPRN_NEXT_REQUEST_AT[key] = max(
            _IPRN_NEXT_REQUEST_AT.get(key, 0.0),
            time.monotonic() + seconds,
        )


def _iprn_json(response):
    try:
        return response.json()
    except Exception:
        return None


def _iprn_error_text(payload, fallback):
    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict):
            code = str(error.get("code") or "").strip()
            message = str(error.get("message") or "").strip()
            if code and message:
                return f"{code}: {message}"
            if code:
                return code
            if message:
                return message
        if payload.get("success") is False:
            return str(payload.get("message") or fallback)
    return fallback


def _iprn_get(session, token, base, path, params, timeout, provider_label):
    _iprn_wait_for_key(token)
    try:
        response = session.get(
            f"{base}/{path.lstrip('/')}",
            params=params,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
            },
            timeout=timeout,
        )
    except Exception as exc:
        raise Exception(f"{provider_label} connection error: {exc}") from exc

    payload = _iprn_json(response)
    if response.status_code == 429:
        retry_after = response.headers.get("Retry-After")
        if not retry_after and isinstance(payload, dict):
            error = payload.get("error")
            if isinstance(error, dict):
                retry_after = error.get("retry_after")
        _iprn_defer_key(token, retry_after or IPRN_MIN_REQUEST_INTERVAL_SECONDS)
    return response, payload


def _iprn_login(bn, account_label, token, url, provider_label):
    """Login/health-check for the Augestel and KSI bearer-token APIs."""
    token = str(token or "").strip()
    if not token:
        raise Exception(f"{bn} · API key {provider_label} kosong")
    s = _session()
    default = AUGESTEL_DEFAULT_URL if provider_label == "Augestel" else KSI_DEFAULT_URL
    base = _iprn_base(url, default)
    response, payload = _iprn_get(
        s, token, base, "/numbers",
        {"page": 1, "per_page": 1}, 15, provider_label,
    )
    if response.status_code in (401, 403):
        raise Exception(f"{bn} · API key {provider_label} tidak valid/ditolak")
    if response.status_code != 200:
        detail = _iprn_error_text(payload, f"HTTP {response.status_code}")
        raise Exception(f"{bn} · {provider_label} {detail}")
    if not isinstance(payload, dict):
        raise Exception(f"{bn} · response {provider_label} bukan JSON")
    if payload.get("success") is False:
        raise Exception(f"{bn} · {provider_label}: {_iprn_error_text(payload, 'request gagal')}")
    logger.info(f"✅ {bn} {account_label} · {provider_label} API key valid")
    return s, token, base


def _iprn_fetch(session_info, provider_label):
    if not (isinstance(session_info, tuple) and len(session_info) == 3):
        return []
    s, token, base = session_info
    try:
        response, payload = _iprn_get(
            s, token, base, "/messages",
            {"page": 1, "per_page": 200, "type": "all"},
            20, provider_label,
        )
    except Exception as exc:
        logger.warning(f"{provider_label} fetch · network error: {str(exc)[:120]}")
        return []
    if response.status_code in (401, 403):
        return None
    if response.status_code == 429:
        logger.warning(
            f"{provider_label} fetch · rate limited: "
            f"{_iprn_error_text(payload, 'RATE_LIMIT_EXCEEDED')}"
        )
        return []
    if response.status_code != 200:
        logger.warning(
            f"{provider_label} fetch · "
            f"{_iprn_error_text(payload, f'HTTP {response.status_code}')}"
        )
        return []
    if not isinstance(payload, dict) or payload.get("success") is False:
        logger.warning(
            f"{provider_label} fetch · "
            f"{_iprn_error_text(payload, 'response tidak berhasil')}"
        )
        return []
    raw_rows = payload.get("data", []) if isinstance(payload, dict) else []
    if not isinstance(raw_rows, list):
        return []
    rows = []
    for item in raw_rows:
        if not isinstance(item, dict):
            continue
        row = _api_row(
            _api_row_value(item, "received_at", "receivedAt", "created_at", "createdAt", "timestamp", "date", "time"),
            _api_row_value(item, "id", "message_id", "event_id"),
            _api_row_value(item, "number", "phone_number", "phone", "recipient", "destination"),
            _api_row_value(item, "source", "sender", "sender_id", "origin"),
            _api_row_value(item, "message", "message_body", "message_text", "text", "content", "body", "sms"),
        )
        if row:
            rows.append(row)
    return rows


def augestel_login(bn, account_label, token, url=AUGESTEL_DEFAULT_URL):
    return _iprn_login(bn, account_label, token, url, "Augestel")


def augestel_fetch(session_info, url=AUGESTEL_DEFAULT_URL):
    return _iprn_fetch(session_info, "Augestel")


def ksi_login(bn, account_label, token, url=KSI_DEFAULT_URL):
    return _iprn_login(bn, account_label, token, url, "KSI")


def ksi_fetch(session_info, url=KSI_DEFAULT_URL):
    return _iprn_fetch(session_info, "KSI")


def thirdwave_login(bn, account_label, token, url=THIRDWAVE_DEFAULT_URL):
    token = str(token or "").strip()
    if not token:
        raise Exception(f"{bn} · API key ThirdWave kosong")
    s = _session()
    base = _api_base(url, THIRDWAVE_DEFAULT_URL)
    response = s.get(
        f"{base}/api/v1/traffic",
        params={"page": 1, "pageSize": 1},
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        timeout=15,
    )
    if response.status_code in (401, 403):
        raise Exception(f"{bn} · API key ThirdWave tidak valid/ditolak")
    if response.status_code != 200:
        raise Exception(f"{bn} · ThirdWave HTTP {response.status_code}")
    logger.info(f"✅ {bn} {account_label} · ThirdWave token valid")
    return s, token, base


def thirdwave_fetch(session_info, url=THIRDWAVE_DEFAULT_URL):
    if not (isinstance(session_info, tuple) and len(session_info) == 3):
        return []
    s, token, base = session_info
    try:
        response = s.get(
            f"{base}/api/v1/traffic",
            params={"page": 1, "pageSize": 100},
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            timeout=15,
        )
    except Exception as exc:
        logger.warning(f"ThirdWave fetch · network error: {str(exc)[:120]}")
        return []
    if response.status_code in (401, 403):
        return None
    if response.status_code != 200:
        logger.warning(f"ThirdWave fetch · HTTP {response.status_code}")
        return []
    try:
        payload = response.json()
    except Exception:
        return []
    raw_rows = payload.get("rows", []) if isinstance(payload, dict) else []
    rows = []
    for item in raw_rows:
        if not isinstance(item, dict):
            continue
        row = _api_row(
            item.get("receivedAt") or item.get("createdAt") or item.get("timestamp"),
            item.get("id"),
            item.get("destinationNumber") or item.get("number") or item.get("phone"),
            item.get("sourceAddress") or item.get("source") or item.get("sender"),
            item.get("messageBody") or item.get("message") or item.get("text"),
        )
        if row:
            rows.append(row)
    return rows


def _elite_rpc(s, base, token, method, params=None, endpoint=""):
    payload = {"jsonrpc": "2.0", "method": method, "params": params or {}, "id": None}
    target = f"{base}/{endpoint.lstrip('/')}" if endpoint else base
    response = s.post(
        target,
        json=payload,
        headers={
            "Api-Key": token,
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
        timeout=15,
    )
    if response.status_code in (401, 403):
        return None, response
    try:
        return response.json(), response
    except Exception:
        return {"_text": response.text}, response


def elite_login(bn, account_label, token, url=ELITE_DEFAULT_URL):
    token = str(token or "").strip()
    if not token:
        raise Exception(f"{bn} · API key IPRN Elite kosong")
    s = _session()
    base = _api_base(url, ELITE_DEFAULT_URL)
    payload, response = _elite_rpc(s, base, token, "account:get_join")
    if payload is None or response.status_code in (401, 403):
        raise Exception(f"{bn} · API key IPRN Elite tidak valid/ditolak")
    if isinstance(payload, dict) and isinstance(payload.get("result"), dict):
        if payload["result"].get("account_join"):
            logger.info(f"✅ {bn} {account_label} · IPRN Elite token valid")
            return s, token, base
    if isinstance(payload, dict) and not payload.get("error"):
        logger.info(f"✅ {bn} {account_label} · IPRN Elite session siap")
        return s, token, base
    raise Exception(f"{bn} · API key atau response IPRN Elite tidak valid")


def _elite_rows(payload):
    if not isinstance(payload, dict):
        return []
    result = payload.get("result", payload)
    if isinstance(result, dict):
        rows = result.get("mdr_full_list", result.get("rows", result.get("data", [])))
        return rows if isinstance(rows, list) else []
    if isinstance(result, str) and result.strip():
        try:
            delimiter = ";" if result[:4096].count(";") > result[:4096].count(",") else ","
            return list(csv.DictReader(io.StringIO(result), delimiter=delimiter))
        except (csv.Error, TypeError):
            return []
    return []


def elite_fetch(session_info, url=ELITE_DEFAULT_URL):
    if not (isinstance(session_info, tuple) and len(session_info) == 3):
        return []
    s, token, base = session_info
    params = {
        "filter": {
            "start_date": (datetime.utcnow() - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S"),
            "end_date": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S"),
        },
        "page": 1,
        "per_page": 1000,
    }
    try:
        payload, response = _elite_rpc(s, base, token, "sms.mdr_full:get_list", params)
        if payload is None:
            return None
        if response.status_code != 200:
            return []
        rows = []
        for item in _elite_rows(payload):
            if not isinstance(item, dict):
                continue
            stamp = _api_row_value(item, "datetime", "date", "time", "timestamp")
            number = _api_row_value(item, "phone", "b_number", "destinationnumber", "destination", "number")
            sender = _api_row_value(item, "senderid", "sender_id", "source", "sourceaddress", "origin")
            message = _api_row_value(
                item, "message", "message_text", "message_body", "text",
                "messagebody", "message_full", "full_message", "message_content",
                "sms", "content", "body",
            )
            row = _api_row(stamp, _api_row_value(item, "id", "message_id"), number, sender, message)
            if row:
                rows.append(row)
        return rows
    except Exception as exc:
        logger.warning(f"IPRN Elite fetch · network/API error: {str(exc)[:120]}")
        return []


def _elite_sms_headers(token):
    """Send Elite SMS's API key without placing it in query strings."""
    return {
        "Accept": "application/json",
        "X-API-Key": token,
    }


def _elite_sms_rows(payload):
    """Normalize Elite SMS REST /data records to the common panel row format."""
    if not isinstance(payload, dict):
        return []
    raw_rows = payload.get("data", payload.get("results", payload.get("items", [])))
    if not isinstance(raw_rows, list):
        return []

    rows = []
    for item in raw_rows:
        if not isinstance(item, dict):
            continue
        stamp = _api_row_value(
            item, "time", "timestamp", "received_at", "receivedAt",
            "created_at", "createdAt", "datetime", "date",
        )
        number = _api_row_value(
            item, "number", "phone", "phone_number", "msisdn",
            "destination", "recipient",
        )
        source = _api_row_value(
            item, "service", "sender", "source", "cli", "from", "panel",
        )
        message = _api_row_value(
            item, "message", "text", "body", "content", "sms", "otp",
        )
        row = _api_row(
            stamp,
            _api_row_value(item, "id", "message_id", "event_id") or
            hashlib.sha256(
                "|".join((stamp, number, source, message)).encode("utf-8")
            ).hexdigest(),
            number,
            source,
            message,
        )
        if row:
            rows.append(row)
    return rows


def elite_sms_api_login(bn, account_label, token, url=ELITE_SMS_DEFAULT_URL):
    """Validate an Elite SMS API key against the live JSON feed."""
    token = str(token or "").strip()
    if not token:
        raise Exception(f"{bn} · API key Elite SMS kosong")
    s = _session()
    base = _api_base(url, ELITE_SMS_DEFAULT_URL)
    try:
        response = s.get(
            f"{base}/data",
            params={"limit": 1},
            headers=_elite_sms_headers(token),
            timeout=15,
        )
    except Exception as exc:
        raise Exception(f"{bn} · Elite SMS server unreachable: {exc}") from exc
    if response.status_code in (401, 403):
        raise Exception(f"{bn} · API key Elite SMS tidak valid/ditolak")
    if response.status_code != 200:
        raise Exception(f"{bn} · Elite SMS API HTTP {response.status_code}")
    try:
        payload = response.json()
    except Exception as exc:
        raise Exception(f"{bn} · response Elite SMS bukan JSON") from exc
    if not isinstance(payload, dict):
        raise Exception(f"{bn} · response Elite SMS tidak valid")
    logger.info(f"✅ {bn} {account_label} · Elite SMS API siap")
    return s, token, base


def elite_sms_api_fetch(session_info, url=ELITE_SMS_DEFAULT_URL):
    """Fetch the newest Elite SMS records from the REST JSON feed."""
    if not (isinstance(session_info, tuple) and len(session_info) == 3):
        return []
    s, token, base = session_info
    try:
        response = s.get(
            f"{base or _api_base(url, ELITE_SMS_DEFAULT_URL)}/data",
            params={"limit": 200},
            headers=_elite_sms_headers(token),
            timeout=20,
        )
    except Exception as exc:
        logger.warning(f"Elite SMS fetch · network error: {str(exc)[:120]}")
        return []
    if response.status_code in (401, 403):
        return None
    if response.status_code == 429:
        logger.warning("Elite SMS fetch · rate limited")
        return []
    if response.status_code != 200:
        logger.warning(f"Elite SMS fetch · HTTP {response.status_code}")
        return []
    try:
        payload = response.json()
    except Exception:
        logger.warning("Elite SMS fetch · response bukan JSON")
        return []
    rows = _elite_sms_rows(payload)
    logger.info(f"✅ Elite SMS fetch · rows={len(rows)}")
    return rows


def _elite_sms_v1_rows(payload):
    """Normalize authenticated dashboard records from Elite SMS v1."""
    if not isinstance(payload, dict):
        return []
    raw_rows = payload.get("data", payload.get("messages", payload.get("items", [])))
    if not isinstance(raw_rows, list):
        return []
    rows = []
    for item in raw_rows:
        if not isinstance(item, dict):
            continue
        stamp = _api_row_value(
            item, "time", "timestamp", "received_at", "receivedAt",
            "created_at", "createdAt", "datetime", "date",
        )
        number = _api_row_value(
            item, "number", "phone", "phone_number", "msisdn",
            "destination", "recipient",
        )
        source = _api_row_value(
            item, "service", "sender", "source", "from", "cli", "panel",
        )
        message = _api_row_value(
            item, "message", "text", "body", "content", "sms",
        )
        row = _api_row(
            stamp,
            _api_row_value(item, "id", "message_id", "event_id") or "",
            number,
            source,
            message,
        )
        if row:
            rows.append(row)
    return rows


def _elite_sms_v1_base(url):
    base = _api_base(url, ELITE_SMS_V1_DEFAULT_URL)
    return re.sub(r"/(?:signin|dashboard)$", "", base, flags=re.IGNORECASE)


def elite_sms_v1_login(bn, username, password, url=ELITE_SMS_V1_DEFAULT_URL):
    """Sign in to the Elite SMS dashboard and retain its session cookie."""
    username = str(username or "").strip()
    password = str(password or "")
    if not username or not password:
        raise Exception(f"{bn} · username/email dan password Elite SMS wajib diisi")
    s = _session()
    base = _elite_sms_v1_base(url)
    try:
        response = s.post(
            f"{base}/app-api.php",
            data={
                "action": "signin",
                "email": username,
                "password": password,
            },
            headers={"Accept": "application/json"},
            allow_redirects=False,
            timeout=20,
        )
    except Exception as exc:
        raise Exception(f"{bn} · Elite SMS v1 server unreachable: {exc}") from exc
    try:
        payload = response.json()
    except Exception as exc:
        raise Exception(f"{bn} · response login Elite SMS v1 bukan JSON") from exc
    if response.status_code in (401, 403) or not isinstance(payload, dict) or payload.get("ok") is not True:
        raise Exception(f"{bn} · login Elite SMS v1 gagal")
    logger.info(f"✅ {bn} {username} · Elite SMS v1 session siap")
    return s, username, base


def elite_sms_v1_fetch(session_info, url=ELITE_SMS_V1_DEFAULT_URL):
    """Fetch authenticated account SMS from Elite SMS v1's dashboard API."""
    if not (isinstance(session_info, tuple) and len(session_info) == 3):
        return []
    s, _username, base = session_info
    try:
        response = s.get(
            f"{base or _elite_sms_v1_base(url)}/app-api.php",
            params={"action": "my_active", "limit": 200},
            headers={"Accept": "application/json"},
            timeout=20,
        )
    except Exception as exc:
        logger.warning(f"Elite SMS v1 fetch · network error: {str(exc)[:120]}")
        return []
    if response.status_code in (401, 403):
        return None
    if response.status_code != 200:
        logger.warning(f"Elite SMS v1 fetch · HTTP {response.status_code}")
        return []
    try:
        payload = response.json()
    except Exception:
        logger.warning("Elite SMS v1 fetch · response bukan JSON")
        return []
    if not isinstance(payload, dict) or payload.get("ok") is not True:
        return []
    rows = _elite_sms_v1_rows(payload)
    logger.info(f"✅ Elite SMS v1 fetch · rows={len(rows)}")
    return rows


def rez_sms_login(bn, account_label, token, url=REZ_DEFAULT_URL):
    token = str(token or "").strip()
    if not token:
        raise Exception(f"{bn} · API token Rez SMS kosong")
    s = _session()
    endpoint = _api_base(url, REZ_DEFAULT_URL)
    response = s.get(
        endpoint,
        params={**_api_window_params(1), "token": token},
        headers={"Accept": "application/json"},
        timeout=15,
    )
    if response.status_code != 200:
        raise Exception(f"{bn} · Rez SMS HTTP {response.status_code}")
    try:
        payload = response.json()
    except Exception as exc:
        raise Exception(f"{bn} · response Rez SMS bukan JSON") from exc
    if not isinstance(payload, dict) or payload.get("success") is not True:
        raise Exception(f"{bn} · API token Rez SMS tidak valid")
    logger.info(f"✅ {bn} {account_label} · Rez SMS token valid")
    return s, token, endpoint


def rez_sms_fetch(session_info, url=REZ_DEFAULT_URL):
    if not (isinstance(session_info, tuple) and len(session_info) == 3):
        return []
    s, token, endpoint = session_info
    try:
        response = s.get(
            endpoint,
            params={**_api_window_params(1000), "token": token},
            headers={"Accept": "application/json"},
            timeout=20,
        )
    except Exception as exc:
        logger.warning(f"Rez SMS fetch · network error: {str(exc)[:120]}")
        return []
    if response.status_code in (401, 403):
        return None
    if response.status_code != 200:
        return []
    try:
        payload = response.json()
    except Exception:
        return []
    if not isinstance(payload, dict) or payload.get("success") is not True:
        return None
    rows = []
    for item in payload.get("data", []):
        if not isinstance(item, dict):
            continue
        row = _api_row(
            _api_row_value(item, "dt", "date", "time", "timestamp"),
            _api_row_value(item, "id", "message_id", "record_id"),
            _api_row_value(item, "number", "phone", "msisdn"),
            _api_row_value(item, "cli", "sender", "service"),
            _api_row_value(item, "message", "msg", "text", "body", "sms", "content"),
        )
        if row:
            rows.append(row)
    return rows


def axon_login(bn, account_label, token, url=AXON_DEFAULT_URL):
    token = str(token or "").strip()
    if not token:
        raise Exception(f"{bn} · API token Axon kosong")
    s = _session()
    base = _api_base(url, AXON_DEFAULT_URL)
    response = s.get(
        f"{base}/api/sms",
        params={"page": 1, "limit": 1},
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        timeout=15,
    )
    if response.status_code in (401, 403):
        raise Exception(f"{bn} · API token Axon tidak valid/ditolak")
    if response.status_code != 200:
        raise Exception(f"{bn} · Axon HTTP {response.status_code}")
    logger.info(f"✅ {bn} {account_label} · Axon token valid")
    return s, token, base


def axon_fetch(session_info, url=AXON_DEFAULT_URL):
    if not (isinstance(session_info, tuple) and len(session_info) == 3):
        return []
    s, token, base = session_info
    try:
        response = s.get(
            f"{base}/api/sms",
            params={"page": 1, "limit": 100},
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            timeout=15,
        )
    except Exception as exc:
        logger.warning(f"Axon fetch · network error: {str(exc)[:120]}")
        return []
    if response.status_code in (401, 403):
        return None
    if response.status_code != 200:
        return []
    try:
        payload = response.json()
    except Exception:
        return []
    raw_rows = payload.get("data", []) if isinstance(payload, dict) else []
    rows = []
    for item in raw_rows:
        if not isinstance(item, dict):
            continue
        row = _api_row(
            item.get("received_at"),
            item.get("id"),
            item.get("number"),
            item.get("sender") or item.get("service"),
            item.get("message") or item.get("otp"),
        )
        if row:
            rows.append(row)
    return rows


def smsnode_login(bn, account_label, token, url=SMSNODE_DEFAULT_URL):
    token = str(token or "").strip()
    if not token:
        raise Exception(f"{bn} · API key SMSNode kosong")
    s = _session()
    base = _api_base(url, SMSNODE_DEFAULT_URL)
    response = s.get(
        f"{base}/sms/",
        params={"page": 1, "page_size": 1},
        headers={"X-API-Key": token, "Accept": "application/json"},
        timeout=15,
    )
    if response.status_code in (401, 403):
        raise Exception(f"{bn} · API key SMSNode tidak valid/ditolak")
    if response.status_code != 200:
        raise Exception(f"{bn} · SMSNode HTTP {response.status_code}")
    logger.info(f"✅ {bn} {account_label} · SMSNode key valid")
    return s, token, base


def smsnode_fetch(session_info, url=SMSNODE_DEFAULT_URL):
    if not (isinstance(session_info, tuple) and len(session_info) == 3):
        return []
    s, token, base = session_info
    try:
        response = s.get(
            f"{base}/sms/",
            params={"page": 1, "page_size": 200},
            headers={"X-API-Key": token, "Accept": "application/json"},
            timeout=15,
        )
    except Exception as exc:
        logger.warning(f"SMSNode fetch · network error: {str(exc)[:120]}")
        return []
    if response.status_code in (401, 403):
        return None
    if response.status_code != 200:
        return []
    try:
        payload = response.json()
    except Exception:
        return []
    raw_rows = payload.get("results", []) if isinstance(payload, dict) else []
    rows = []
    for item in raw_rows:
        if not isinstance(item, dict):
            continue
        row = _api_row(
            item.get("received_at"),
            item.get("id"),
            item.get("number"),
            item.get("sender_cli") or item.get("app_name"),
            item.get("body"),
        )
        if row:
            rows.append(row)
    return rows


def _xisora_params(token, records=200):
    now = datetime.now().replace(microsecond=0)
    return {
        "token": token,
        "fromdate": now.replace(hour=0, minute=0, second=0).strftime("%Y-%m-%d %H:%M:%S"),
        "todate": now.strftime("%Y-%m-%d %H:%M:%S"),
        "records": records,
        "searchnumber": "",
        "searchcli": "",
    }


def xisora_login(bn, account_label, token, url=XISORA_DEFAULT_URL):
    """Validate a Xisora MDR API key using its query-token endpoint."""
    token = str(token or "").strip()
    if not token:
        raise Exception(f"{bn} · API key Xisora kosong")
    s = _session()
    endpoint = _api_base(url, XISORA_DEFAULT_URL)
    try:
        response = s.get(
            endpoint,
            params=_xisora_params(token, records=1),
            headers={"Accept": "application/json"},
            timeout=15,
        )
    except Exception as exc:
        raise Exception(f"{bn} · Xisora server unreachable: {exc}") from exc
    if response.status_code in (401, 403):
        raise Exception(f"{bn} · API key Xisora tidak valid/ditolak")
    if response.status_code != 200:
        raise Exception(f"{bn} · Xisora HTTP {response.status_code}")
    try:
        payload = response.json()
    except Exception as exc:
        raise Exception(f"{bn} · response Xisora bukan JSON yang valid") from exc
    if not isinstance(payload, dict) or str(payload.get("status", "")).lower() != "success":
        reason = payload.get("description", payload.get("status", "Respons API tidak berhasil")) if isinstance(payload, dict) else "Respons API tidak valid"
        raise Exception(f"{bn} · Xisora: {reason}")
    logger.info(f"✅ {bn} {account_label} · Xisora API key valid")
    return s, token, endpoint


def xisora_fetch(session_info, url=XISORA_DEFAULT_URL):
    """Fetch and normalize Xisora MDR records to the common panel row format."""
    if not (isinstance(session_info, tuple) and len(session_info) == 3):
        return []
    s, token, endpoint = session_info
    try:
        response = s.get(
            endpoint or _api_base(url, XISORA_DEFAULT_URL),
            params=_xisora_params(token, records=200),
            headers={"Accept": "application/json"},
            timeout=20,
        )
    except Exception as exc:
        logger.warning(f"Xisora fetch · network error: {str(exc)[:120]}")
        return []
    if response.status_code in (401, 403):
        return None
    if response.status_code != 200:
        logger.warning(f"Xisora fetch · HTTP {response.status_code}")
        return []
    try:
        payload = response.json()
    except Exception:
        return []
    if not isinstance(payload, dict) or str(payload.get("status", "")).lower() != "success":
        return None
    rows = []
    for item in payload.get("data", []):
        if not isinstance(item, dict):
            continue
        timestamp = _api_row_value(item, "datetime", "date", "time", "timestamp")
        number = _api_row_value(item, "number", "phone", "phone_number", "msisdn")
        source = _api_row_value(item, "cli", "source", "sender", "sender_id")
        message = _api_row_value(item, "message", "message_body", "message_text", "text", "sms", "content")
        fingerprint = "|".join((timestamp, number, source, message))
        row = _api_row(
            timestamp,
            "xisora:" + hashlib.sha256(fingerprint.encode("utf-8")).hexdigest(),
            number,
            source,
            message,
        )
        if row:
            rows.append(row)
    return rows


def _mj_sms_api_rows(payload: object) -> list:
    """Normalize MJ SMS Agent API records to the bot's common row format."""
    if isinstance(payload, dict):
        error = str(payload.get("error") or "").strip()
        if error:
            raise Exception(f"MJ SMS API: {error}")
        raw_rows = payload.get("data", payload.get("results", []))
    else:
        raw_rows = payload

    if not isinstance(raw_rows, list):
        return []

    rows = []
    for index, item in enumerate(raw_rows):
        if not isinstance(item, dict):
            continue
        row = _api_row(
            _api_row_value(item, "received_at", "receivedAt", "date", "datetime"),
            _api_row_value(item, "id", "row_id", "rowid") or str(index),
            _api_row_value(item, "phone_number", "phone", "number", "msisdn"),
            _api_row_value(item, "sender", "cli", "from", "service"),
            _api_row_value(item, "message_body", "message", "body", "sms", "text"),
        )
        if row:
            rows.append(row)
    return rows


def mj_sms_api_login(bn, account_label, token, url=MJ_SMS_API_DEFAULT_URL):
    """Validate an MJ SMS Agent API token without putting it in the URL."""
    token = str(token or "").strip()
    if not token:
        raise Exception(f"{bn} · API token MJ SMS kosong")

    s = _session()
    endpoint = _api_base(url, MJ_SMS_API_DEFAULT_URL)
    try:
        response = s.get(
            endpoint,
            params={"limit": 1, "page": 1},
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
            },
            timeout=15,
        )
    except Exception as exc:
        raise Exception(f"{bn} · MJ SMS API server unreachable: {exc}")

    if response.status_code in (401, 403):
        raise Exception(f"{bn} · API token MJ SMS tidak valid/aktif")
    if response.status_code != 200:
        raise Exception(f"{bn} · MJ SMS API HTTP {response.status_code}")
    try:
        payload = response.json()
        _mj_sms_api_rows(payload)
    except ValueError as exc:
        raise Exception(f"{bn} · MJ SMS API response bukan JSON yang valid") from exc
    except Exception as exc:
        raise Exception(f"{bn} · {exc}")

    logger.info(f"✅ {bn} {account_label} · MJ SMS API token valid")
    return s, token, endpoint


def mj_sms_api_fetch(session_info, url=MJ_SMS_API_DEFAULT_URL):
    """Fetch the current MJ SMS Agent API page for the last two dates."""
    if not (isinstance(session_info, tuple) and len(session_info) == 3):
        return []

    s, token, endpoint = session_info
    d1, d2 = _dates()
    try:
        response = s.get(
            endpoint or _api_base(url, MJ_SMS_API_DEFAULT_URL),
            params={
                "from": d1[:10],
                "to": d2[:10],
                "limit": 500,
                "page": 1,
            },
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
            },
            timeout=15,
        )
    except Exception as exc:
        logger.warning(f"MJ SMS API fetch · network error: {str(exc)[:120]}")
        return []

    if response.status_code in (401, 403):
        return None
    if response.status_code != 200:
        raise Exception(f"MJ SMS API HTTP {response.status_code}")
    try:
        payload = response.json()
    except ValueError as exc:
        raise Exception("MJ SMS API response bukan JSON yang valid") from exc

    try:
        rows = _mj_sms_api_rows(payload)
    except Exception as exc:
        if "invalid or inactive" in str(exc).lower():
            return None
        raise
    logger.info(f"✅ MJ SMS API fetch · rows={len(rows)}")
    return rows


# ── ✅ BUG-4 FIX: Captcha solver — no hardcoded fallback ───────
def _solve_captcha(html_text: str) -> str:
    """
    Solve math captcha from HTML text.
    Supports addition, subtraction, multiplication and division.
    Tries regex first, then BeautifulSoup.
    Logs warning if captcha not found.
    """
    def solve_match(match):
        left, operator, right = int(match.group(1)), match.group(2), int(match.group(3))
        if operator == "+":
            return left + right
        if operator == "-":
            return max(0, left - right)
        if operator in {"*", "×", "x"}:
            return left * right
        if operator in {"/", "÷"}:
            return left // right if right and left % right == 0 else left / right
        return None

    operators = r"[+\-*/×÷x]"
    patterns = [
        rf"(?:what\s+is|captcha(?:\s+question)?)\s*:?\s*(\d{{1,6}})\s*({operators})\s*(\d{{1,6}})",
        rf"(?<![\w.])(\d{{1,6}})\s*({operators})\s*(\d{{1,6}})\s*=?\s*\?",
        rf"(?<![\w.])(\d{{1,6}})\s*({operators})\s*(\d{{1,6}})\s*=",
        rf"(?<![\w.])(\d{{1,6}})\s*({operators})\s*(\d{{1,6}})(?![\w.])",
    ]
    for candidate_text in (html_text,):
        for pat in patterns:
            match = re.search(pat, candidate_text, re.I)
            if match:
                result = solve_match(match)
                if result is not None:
                    return str(result)

    # BeautifulSoup fallback (useful when the question is split across tags).
    try:
        from bs4 import BeautifulSoup
        plain = BeautifulSoup(html_text, "html.parser").get_text()
        for pat in patterns:
            match = re.search(pat, plain, re.I)
            if match:
                result = solve_match(match)
                if result is not None:
                    return str(result)
    except ImportError:
        pass

    logger.warning("⚠️ Captcha not found — sending 0 (may cause login failure)")
    return "0"


# Backward compat alias
def _captcha(html: str) -> int:
    return int(_solve_captcha(html) or "0")


# ── ✅ BUG-9 FIX: Session expiry detector ─────────────────────
def _is_session_expired(resp) -> bool:
    """
    Returns True if response signals that session has expired.
    Checks: HTTP status, URL redirect history, response content.
    """
    # HTTP-level indicators
    if resp.status_code in (401, 403):
        return True

    # URL redirect to login page
    final_url = str(resp.url).lower()
    if any(x in final_url for x in ["/login", "/signin", "/sign-in", "/auth/login"]):
        return True

    # Redirect-history check — page content দিয়ে confirm করো
    if resp.history:
        last_url = str(resp.history[-1].url).lower()
        if (any(x in last_url for x in ["/login", "/signin", "/sign-in"])
                and "json" not in resp.headers.get("Content-Type", "").lower()):
            page = resp.text[:1500].lower()
            if "<html" in page and any(w in page for w in ["sign in", "please login", "signin"]):
                return True

    # Content-based check (only for non-JSON responses)
    ct = resp.headers.get("Content-Type", "").lower()
    if "json" not in ct:
        text_low = resp.text[:3000].lower()
        # Must look like an HTML page AND have login signals
        if ("<html" in text_low or "<form" in text_low):
            if any(w in text_low for w in _LOGIN_PAGE_SIGNALS):
                return True

    return False


# ══════════════════════════════════════════════════════════════
#  KEEPALIVE — session alive রাখার জন্য lightweight ping
#  ImsPanel আর RoxySMS এর server-side session টাইমআউট খুব কম।
#  fetch এর মাঝে idle থাকলে session মরে যায়।
#  এই function একটা dashboard GET করে — minimal traffic, session refresh।
# ══════════════════════════════════════════════════════════════
def _ims_keepalive(s, url: str, path: str) -> bool:
    """
    ImsPanel session alive রাখার জন্য dashboard ping।
    Returns True যদি session ঠিক থাকে, False যদি expired।
    """
    try:
        r = s.get(
            f"{url}/{path}/SMSDashboard",
            headers={**_BASE_HEADERS, "Referer": f"{url}/{path}/SMSCDRStats"},
            timeout=10, allow_redirects=True,
        )
        if _is_session_expired(r):
            logger.debug(f"ims_keepalive · session expired")
            return False
        logger.debug(f"ims_keepalive · OK (HTTP {r.status_code})")
        return True
    except Exception as e:
        logger.debug(f"ims_keepalive · network error: {str(e)[:60]}")
        return True   # network error → session এখনো হয়তো alive, False করবো না


def _roxy_keepalive(s, url: str, path: str) -> bool:
    """
    RoxySMS session alive রাখার জন্য SMSCDRReports ping।
    Returns True যদি session ঠিক থাকে, False যদি expired।
    """
    try:
        r = s.get(
            f"{url}/{path}/SMSCDRReports",
            headers={**_BASE_HEADERS, "Referer": f"{url}/{path}/SMSDashboard"},
            timeout=10, allow_redirects=True,
        )
        if _is_session_expired(r):
            logger.debug(f"roxy_keepalive · session expired")
            return False
        logger.debug(f"roxy_keepalive · OK (HTTP {r.status_code})")
        return True
    except Exception as e:
        logger.debug(f"roxy_keepalive · network error: {str(e)[:60]}")
        return True


def _classify(resp) -> str:
    """Returns: 'json' | 'login_page' | 'empty' | 'html_other'"""
    if _is_session_expired(resp):
        return "login_page"

    ct   = resp.headers.get("Content-Type", "").lower()
    text = resp.text.strip()

    if not text:
        return "empty"
    if "json" in ct or text.startswith("[") or text.startswith("{"):
        return "json"
    return "html_other"


# ── ✅ FIX-A: Row parser — handles both list AND dict rows ─────
def _parse(text: str, mask_only=False) -> list:
    """
    Parse panel JSON response into normalized rows.
    FIX-A: Now handles dict-type rows (e.g. VoiceGate) in addition to list rows.
    Returns list of [date, id, number, cli, None, sms] rows.
    """
    text = text.strip()
    if not text or text.startswith("<"):
        return []
    try:
        js = json.loads(text)
    except Exception:
        cut = text.rfind("]")
        if cut > 0:
            try:
                js = json.loads(text[:cut + 1])
            except Exception:
                return []
        else:
            return []

    if isinstance(js, dict):
        rows = js.get("aaData") or js.get("data") or js.get("results") or []
    elif isinstance(js, list):
        rows = js
    else:
        return []

    INVALID = {"None", "", "null", "—", "****", "***", "**", "*", "N/A", "$"}
    out = []

    for row in rows:
        # ── List row (standard panel format) ──────────────────
        if isinstance(row, list):
            if len(row) < 4:
                continue
            if str(row[0]).startswith("0,"):
                continue
            num = str(row[2]).strip().lstrip("+")
            if not num.isdigit() or num == "0":
                continue
            sms = ""
            # Zone SMS places the actual message in column 7:
            # [date, range, number, sender, currency, period, status, sms].
            # Keep the older columns first for all existing INTS panels.
            for col in [5, 4, 6, 7]:
                v = str(row[col]).strip() if len(row) > col else ""
                if v and v not in INVALID and not re.match(r'^\*+$', v):
                    sms = _html.unescape(v)
                    break
            if mask_only and not sms:
                continue
            out.append([str(row[0]), str(row[1]), num, str(row[3]), None, sms])

        # ── ✅ FIX-A: Dict row (VoiceGate and others) ─────────
        elif isinstance(row, dict):
            num = str(row.get("number", row.get("num", row.get("msisdn", "")))).strip().lstrip("+")
            if not num.isdigit() or num == "0":
                continue
            sms = str(row.get("sms", row.get("message", row.get("text", "")))).strip()
            if sms in INVALID or re.match(r'^\*+$', sms):
                sms = ""
            if mask_only and not sms:
                continue
            sms = _html.unescape(sms)
            cli = str(row.get("cli", row.get("service", row.get("sender", "")))).strip()
            dt  = str(row.get("date", row.get("dt", row.get("time", "")))).strip()
            rid = str(row.get("id", row.get("rowid", ""))).strip()
            out.append([dt, rid, num, cli, None, sms])

    return out


# ══════════════════════════════════════════════════════════════
#  XMS PANEL — Django session + HTML incoming messages
# ══════════════════════════════════════════════════════════════
_XMS_LOGIN_PATH = "/accounts/login/"
_XMS_INCOMING_PATH = "/messaging/incoming/"
_XMS_RECORDS_PATH = "/api/messaging/incoming-user/records/"

_XMS_PHONE_HEADERS = (
    "number", "phone", "msisdn", "mobile", "recipient",
    "destination", "receiver", "to", "line", "sim",
)
_XMS_MESSAGE_HEADERS = (
    "message", "sms", "content", "body", "text", "otp", "messagebody",
)
_XMS_SENDER_HEADERS = (
    "sender", "from", "cli", "service", "source",
)
_XMS_DATE_HEADERS = (
    "date", "time", "received", "created", "timestamp",
)
_XMS_ID_HEADERS = ("id", "messageid", "message_id", "rowid")


def _xms_cookie(session, name: str) -> str:
    """Read the latest non-empty cookie without failing on duplicate domains."""
    value = ""
    for cookie in session.cookies:
        if cookie.name == name and cookie.value:
            value = str(cookie.value)
    return value


def _xms_csrf_token(page_text: str, session) -> str:
    """Extract Django's CSRF token from HTML or the session cookie."""
    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(page_text or "", "html.parser")
        selectors = (
            'input[name="csrfmiddlewaretoken"]',
            'input[name="csrfmiddlewaretoken" i]',
            'meta[name="csrf-token"]',
            'meta[name="csrf_token"]',
            '[data-csrf-token]',
            '[data-csrf]',
        )
        for selector in selectors:
            node = soup.select_one(selector)
            if not node:
                continue
            value = node.get("value") or node.get("content")
            if value is None:
                value = node.get("data-csrf-token") or node.get("data-csrf")
            value = _html.unescape(str(value or "")).strip()
            if value:
                return value
    except Exception:
        pass

    patterns = (
        r'<input\b(?=[^>]*\bname\s*=\s*["\']csrfmiddlewaretoken["\'])'
        r'(?=[^>]*\bvalue\s*=\s*["\']([^"\']+)["\'])[^>]*>',
        r'<input\b(?=[^>]*\bvalue\s*=\s*["\']([^"\']+)["\'])'
        r'(?=[^>]*\bname\s*=\s*["\']csrfmiddlewaretoken["\'])[^>]*>',
        r'<meta\b(?=[^>]*\bname\s*=\s*["\']csrf[-_]token["\'])'
        r'(?=[^>]*\bcontent\s*=\s*["\']([^"\']+)["\'])[^>]*>',
        r'\bdata-csrf(?:-token)?\s*=\s*["\']([^"\']+)["\']',
    )
    for pattern in patterns:
        match = re.search(pattern, page_text or "", re.I | re.S)
        if match:
            value = _html.unescape(match.group(1)).strip()
            if value:
                return value

    return _xms_cookie(session, "csrftoken")


def _xms_form_action(page_text: str, login_url: str) -> str:
    """Use the Django login form action when present."""
    try:
        from bs4 import BeautifulSoup

        form = BeautifulSoup(page_text or "", "html.parser").select_one("form")
        action = str(form.get("action") or "").strip() if form else ""
        return urljoin(login_url, action) if action else login_url
    except Exception:
        match = re.search(
            r"<form\b[^>]*\baction\s*=\s*[\"']([^\"']+)[\"']",
            page_text or "",
            re.I | re.S,
        )
        return urljoin(login_url, match.group(1)) if match else login_url


def _xms_header_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def _xms_cell_text(cell) -> str:
    """Return the visible cell value, with common XMS data attributes as fallback.

    Some XMS themes render the value through an icon/link and keep the actual
    value in data-* or accessibility attributes.  The old parser treated those
    cells as empty, which made the whole row impossible to normalize.
    """
    visible = re.sub(r"\s+", " ", cell.get_text(" ", strip=True)).strip()
    if visible:
        return visible
    for attr in (
        "data-value", "data-number", "data-phone", "data-msisdn",
        "data-message", "data-text", "title", "aria-label",
    ):
        value = re.sub(r"\s+", " ", str(cell.get(attr, "") or "")).strip()
        if value:
            return value
    return ""


def _xms_find_value(values: dict, aliases: tuple[str, ...]) -> str:
    """Find a value by exact or contained normalized column name."""
    for key, value in values.items():
        if any(key == alias or (len(alias) >= 3 and alias in key) for alias in aliases):
            if value:
                return value
    return ""


def _xms_normalize_number(value: str) -> str:
    value = _html.unescape(value or "").strip()
    # Preserve the digits used by the bot's active-number matcher.
    digits = re.sub(r"[^\d]", "", value)
    return digits if 7 <= len(digits) <= 16 else ""


def _xms_is_date_like(value: str) -> bool:
    value = value.strip()
    return bool(re.search(r"\d{1,4}[-/]\d{1,2}[-/]\d{1,4}", value)
                or re.search(r"\d{1,2}:\d{2}", value))


def _xms_message_from_cells(cells: list[str], headers: list[str]) -> str:
    """Extract a message from a full row or a mobile detail/continuation row."""
    values = {}
    if headers and len(headers) == len(cells):
        values = {
            _xms_header_key(header): cell
            for header, cell in zip(headers, cells)
            if header
        }

    message = _xms_find_value(values, _XMS_MESSAGE_HEADERS)
    if message:
        return message

    number = _xms_normalize_number(_xms_find_value(values, _XMS_PHONE_HEADERS))
    candidates = [
        cell for cell in cells
        if cell and cell != number
        and not _xms_normalize_number(cell)
        and not _xms_is_date_like(cell)
    ]
    return max(candidates, key=len, default="")


def _xms_has_message_header(headers: list[str]) -> bool:
    normalized = {_xms_header_key(header) for header in headers if header}
    return any(
        key == alias or (len(alias) >= 3 and alias in key)
        for key in normalized
        for alias in _XMS_MESSAGE_HEADERS
    )


def _xms_looks_like_message(value: str) -> bool:
    value = value.strip()
    return bool(
        re.search(r"\b\d{4,8}\b", value)
        or re.search(r"\b(?:otp|code|pin|verification|password|passcode)\b", value, re.I)
    )


def _xms_row_to_normalized(cells: list[str], headers: list[str], row_index: int) -> list | None:
    """Convert one XMS table row to the common panel row shape."""
    if not cells:
        return None

    values = {}
    if headers and len(headers) == len(cells):
        values = {
            _xms_header_key(header): cell
            for header, cell in zip(headers, cells)
            if header
        }

    number = _xms_normalize_number(_xms_find_value(values, _XMS_PHONE_HEADERS))
    if not number:
        number = next((
            _xms_normalize_number(cell)
            for cell in cells
            if not _xms_is_date_like(cell)
        ), "")
    if not number:
        return None

    message = _xms_message_from_cells(cells, headers)
    sender = _xms_find_value(values, _XMS_SENDER_HEADERS)
    received = _xms_find_value(values, _XMS_DATE_HEADERS)
    row_id = _xms_find_value(values, _XMS_ID_HEADERS) or str(row_index)

    if not message:
        candidates = [
            cell for cell in cells
            if cell and not _xms_normalize_number(cell)
            and not _xms_is_date_like(cell)
            and cell != sender
        ]
        # XMS messages are normally the longest non-meta cell. This fallback
        # also supports table layouts that do not expose column headings.
        message = max(candidates, key=len, default="")
    if not sender:
        candidates = [
            cell for cell in cells
            if cell and cell != message and cell != received
            and not _xms_normalize_number(cell)
            and not _xms_is_date_like(cell)
        ]
        sender = candidates[0] if candidates else ""

    return [
        _html.unescape(received),
        _html.unescape(row_id),
        number,
        _html.unescape(sender),
        None,
        _html.unescape(message),
    ]


def _xms_parse_html(text: str) -> list:
    """Parse XMS's server-rendered incoming-message table.

    The page is HTML rather than the JSON shape used by the older panels.
    Column aliases and a no-header fallback keep this compatible with small
    presentation changes in the XMS dashboard.
    """
    try:
        from bs4 import BeautifulSoup
    except ImportError as exc:
        raise RuntimeError("XMS membutuhkan dependency beautifulsoup4") from exc

    soup = BeautifulSoup(text, "html.parser")
    out = []
    seen = set()

    tables = soup.find_all("table")

    for table in tables:
        headers = []
        # Prefer an explicit thead.  The previous implementation used the
        # first tr in the table, which is often the first data row when the
        # XMS template omits <thead>.
        header_candidates = []
        thead = table.find("thead")
        if thead:
            header_candidates.extend(thead.find_all("tr"))
        header_candidates.extend(table.find_all("tr"))

        for header_row in header_candidates:
            header_cells = header_row.find_all(["th", "td"], recursive=False)
            if not header_cells:
                continue
            candidate_headers = [_xms_cell_text(cell) for cell in header_cells]
            normalized_headers = {_xms_header_key(value) for value in candidate_headers if value}
            has_known_header = any(
                any(
                    key == alias or (len(alias) >= 3 and alias in key)
                    for alias_group in (
                        _XMS_PHONE_HEADERS,
                        _XMS_MESSAGE_HEADERS,
                        _XMS_SENDER_HEADERS,
                        _XMS_DATE_HEADERS,
                    )
                    for alias in alias_group
                )
                for key in normalized_headers
            )
            if any(cell.name == "th" for cell in header_cells) or has_known_header:
                headers = candidate_headers
                break

        rows = table.find_all("tr")
        for index, row in enumerate(rows, start=1):
            # A few XMS skins use <th> for the first cell in body rows.
            row_cells = row.find_all(["td", "th"], recursive=False)
            cells = [_xms_cell_text(cell) for cell in row_cells]
            if not cells:
                continue
            row_headers = headers
            if not row_headers:
                row_headers = [
                    cell.get("data-label") or cell.get("data-field")
                    or cell.get("data-column") or ""
                    for cell in row_cells
                ]
                if not any(row_headers):
                    row_headers = []
            normalized = _xms_row_to_normalized(cells, row_headers, index)
            if normalized:
                key = (normalized[1], normalized[2], normalized[5])
                if key not in seen:
                    seen.add(key)
                    out.append(normalized)
            elif out:
                # Mobile XMS layouts may render the SMS text in a detail row
                # below the row containing Date/Range/Number. Keep that text
                # attached to the previous normalized record instead of
                # dropping it because the detail row has no phone number.
                detail_message = _xms_message_from_cells(cells, row_headers)
                if detail_message and (
                    _xms_has_message_header(row_headers)
                    or _xms_looks_like_message(detail_message)
                ):
                    out[-1][5] = _html.unescape(detail_message)

    # HTMX can return a fragment without a <table> wrapper.  Support the
    # common row markup as a safe fallback, while leaving unrelated page text
    # alone when a table was already found.
    if not tables:
        fragment_rows = soup.select(
            '[role="row"], .message-row, .sms-row, .incoming-row, '
            '[data-message-row], [data-sms-row]'
        )
        for index, row in enumerate(fragment_rows, start=1):
            row_cells = row.find_all(
                ["td", "th", "span", "div"],
                recursive=False,
            )
            cells = [_xms_cell_text(cell) for cell in row_cells]
            normalized = _xms_row_to_normalized(cells, [], index)
            if normalized:
                key = (normalized[1], normalized[2], normalized[5])
                if key not in seen:
                    seen.add(key)
                    out.append(normalized)
            elif out:
                detail_message = _xms_message_from_cells(cells, [])
                if detail_message and _xms_looks_like_message(detail_message):
                    out[-1][5] = _html.unescape(detail_message)

    return out


def xms_login(bn, username, password, url=""):
    """Login to XMS's Django dashboard and retain its session cookies."""
    s = _session()
    url = url.rstrip("/")
    login_url = f"{url}{_XMS_LOGIN_PATH}"

    try:
        r = s.get(
            login_url,
            headers={
                **_BASE_HEADERS,
                "Cache-Control": "no-cache, no-store, max-age=0",
                "Pragma": "no-cache",
            },
            timeout=25,
            allow_redirects=True,
        )
    except Exception as exc:
        raise Exception(f"{bn} · XMS server unreachable: {exc}")

    if r.status_code == 429:
        retry_after = str(r.headers.get("Retry-After", "") or "").strip()
        retry_after_seconds = int(retry_after) if retry_after.isdigit() else 600
        raise Exception(
            f"{bn} · XMS rate limit (HTTP 429); "
            f"coba lagi setelah {retry_after_seconds} detik"
        )
    if r.status_code in (401, 403):
        raise Exception(f"{bn} · XMS login page blocked (HTTP {r.status_code})")
    if r.status_code >= 400:
        raise Exception(f"{bn} · XMS login page error (HTTP {r.status_code})")

    csrf = _xms_csrf_token(r.text, s)
    if not csrf:
        raise Exception(
            f"{bn} · XMS CSRF token tidak ditemukan "
            f"(HTTP {r.status_code}, URL {r.url})"
        )

    captcha = _solve_captcha(r.text)
    post_data = {
        "csrfmiddlewaretoken": csrf,
        "username": username,
        "password": password,
        "captcha_answer": captcha,
    }
    post_url = _xms_form_action(r.text, login_url)
    try:
        r2 = s.post(
            post_url,
            data=post_data,
            headers={
                **_BASE_HEADERS,
                "Referer": str(r.url or login_url),
                "Origin": url,
                "Content-Type": "application/x-www-form-urlencoded",
                "X-CSRFToken": csrf,
            },
            allow_redirects=True,
            timeout=25,
        )
    except Exception as exc:
        raise Exception(f"{bn} · XMS login request failed: {exc}")

    final_url = str(r2.url).lower()
    login_failed = (
        "/accounts/login" in final_url
        or "invalid username" in r2.text.lower()
        or "incorrect" in r2.text.lower()
    )
    if not _xms_cookie(s, "sessionid") or login_failed:
        raise Exception(f"{bn} · XMS login gagal — username/password atau captcha tidak valid")

    logger.info(f"✅ XMS login {bn} · session established")
    return s, url


def xms_fetch(bn, session_info, url=""):
    """Fetch and normalize messages from XMS's incoming-records API.

    The incoming page is only a JavaScript shell.  Its table is populated by
    ``/api/messaging/incoming-user/records/`` after the page loads, so scraping
    ``/messaging/incoming/`` directly returns empty table templates.
    """
    if not (isinstance(session_info, tuple) and len(session_info) == 2):
        return []
    s, session_url = session_info
    url = (session_url or url).rstrip("/")

    requests_to_try = [
        (
            f"{url}{_XMS_RECORDS_PATH}",
            {"page": 1, "page_size": 100},
            {
                **_BASE_HEADERS,
                "Referer": f"{url}{_XMS_INCOMING_PATH}",
                "Accept": "application/json",
                "X-Requested-With": "XMLHttpRequest",
                "Cache-Control": "no-cache, no-store, max-age=0",
                "Pragma": "no-cache",
            },
            "api",
        ),
        # Compatibility fallback for older XMS deployments that still render
        # incoming rows server-side rather than exposing the records API.
        (
            f"{url}{_XMS_INCOMING_PATH}",
            {"_": int(datetime.now().timestamp() * 1000)},
            {
                **_BASE_HEADERS,
                "Referer": f"{url}/",
                "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
                "X-Requested-With": "XMLHttpRequest",
                "HX-Request": "true",
                "Cache-Control": "no-cache, no-store, max-age=0",
                "Pragma": "no-cache",
            },
            "html",
        ),
    ]

    for endpoint, params, headers, source in requests_to_try:
        try:
            r = s.get(
                endpoint,
                params=params,
                headers=headers,
                timeout=25,
                allow_redirects=True,
            )
        except Exception as exc:
            err = str(exc)
            if any(word in err for word in ("NewConnection", "ConnectionError", "Max retries")):
                logger.warning(f"{bn} · XMS network error: {err[:120]}")
                return []
            if source == "api":
                logger.warning(f"{bn} · XMS records API error: {err[:120]}")
                continue
            raise

        if _is_session_expired(r):
            logger.warning(f"⚠️ {bn} · XMS refresh returned an expired session (HTTP {r.status_code})")
            return None

        content_type = r.headers.get("Content-Type", "").lower()
        is_json = "json" in content_type or r.text.lstrip().startswith(("[", "{"))
        if source == "api" and r.status_code >= 400:
            logger.warning(f"⚠️ {bn} · XMS records API HTTP {r.status_code}; trying fallback")
            continue

        if is_json:
            rows = _parse(r.text)
        else:
            rows = _xms_parse_html(r.text)

        logger.info(
            f"🔁 {bn} · XMS {source} refresh OK · HTTP {r.status_code} · "
            f"rows={len(rows)} · {r.url}"
        )
        # A successful API response is authoritative, including an empty
        # result set.  Do not replace it with the page shell.
        return rows

    return []


def gren_sms_login(bn, username, password, url=""):
    """Login to the Gren SMS Django panel using the existing XMS flow."""
    value = (url or "").rstrip("/")
    for suffix in ("/accounts/login", "/messaging/incoming"):
        if value.lower().endswith(suffix):
            value = value[:-len(suffix)].rstrip("/")
    return xms_login(bn, username, password, value)


def gren_sms_fetch(bn, session_info, url=""):
    """Fetch Gren SMS incoming messages through its records endpoint."""
    value = (url or "").rstrip("/")
    for suffix in ("/accounts/login", "/messaging/incoming"):
        if value.lower().endswith(suffix):
            value = value[:-len(suffix)].rstrip("/")
    return xms_fetch(bn, session_info, value)


# ══════════════════════════════════════════════════════════════
#  CORE FETCH — ULTIMATE FIXED ENGINE
# ══════════════════════════════════════════════════════════════
def _core_fetch(s, url: str, path: str) -> list | None:
    """
    Returns:
      list  → rows (may be empty [])
      None  → session expired (caller must re-login)
    """
    d1, d2 = _dates()
    paths_to_try = list(dict.fromkeys([path, "agent", "client", "reseller"]))

    for p in paths_to_try:
        base_params = {
            "fdate1": d1, "fdate2": d2,
            "frange": "", "fclient": "", "fnum": "", "fcli": "",
            "fgdate": "", "fgmonth": "", "fgrange": "",
            "fgclient": "", "fgnumber": "", "fgcli": "",
            "fg": "0",
        }

        # ── A. Direct hit (no sesskey) ──────────────────────
        for ep in [
            f"{url}/{p}/res/data_smscdr.php",
            f"{url}/{p}/res/data_smscdrreports.php",
        ]:
            try:
                r = s.get(ep, params=base_params,
                          headers={**_AJAX_HEADERS, "Referer": f"{url}/{p}/SMSCDRStats"},
                          timeout=20, allow_redirects=True)
                if _is_session_expired(r):
                    return None
                if _classify(r) == "json":
                    rows = _parse(r.text)
                    if rows:
                        return rows
            except Exception as e:
                err = str(e)
                if any(x in err for x in ["NewConnection", "ConnectionError",
                                           "Failed to establish", "Max retries"]):
                    break
                continue

        # ── B. Sesskey fallback ─────────────────────────────
        sesskey = ""
        for stats_ep in [
            f"{url}/{p}/SMSCDRStats",
            f"{url}/{p}/SMSCDRReports",  # TimeSMS uses this
        ]:
            if sesskey:
                break
            try:
                rs = s.get(stats_ep,
                           headers={**_BASE_HEADERS, "Referer": f"{url}/{p}/SMSDashboard"},
                           timeout=15, allow_redirects=True)
                if _is_session_expired(rs):
                    return None
                m = re.search(r'sesskey=([A-Za-z0-9+/=_-]+)', rs.text)
                if m:
                    sesskey = m.group(1)
            except Exception:
                continue

        if sesskey:
            for ep in [
                f"{url}/{p}/res/data_smscdr.php",
                f"{url}/{p}/res/data_smscdrreports.php",
            ]:
                try:
                    r = s.get(ep, params={**base_params, "sesskey": sesskey},
                              headers={**_AJAX_HEADERS, "Referer": f"{url}/{p}/SMSCDRStats"},
                              timeout=20, allow_redirects=True)
                    if _is_session_expired(r):
                        return None
                    if _classify(r) == "json":
                        rows = _parse(r.text)
                        if rows:
                            return rows
                except Exception:
                    pass

        # ── C. Test panel endpoint fallback ─────────────────
        try:
            r = s.get(f"{url}/{p}/res/data_testsmscdr.php",
                      params={"fdate1": d1, "fdate2": d2, "fg": "0"},
                      headers={**_AJAX_HEADERS, "Referer": f"{url}/{p}/SMSTestPanel"},
                      timeout=15, allow_redirects=True)
            if _is_session_expired(r):
                return None
            if _classify(r) == "json":
                rows = _parse(r.text)
                if rows:
                    return rows
        except Exception:
            pass

    return []  # authenticated but no data


# ══════════════════════════════════════════════════════════════
#  INTS LOGIN/FETCH  (HADI, Seven1Tel, Wolf, Gaza, Sniper, MAIT, etc.)
#  ✅ BUG-5 FIX: CSRF warning logged
#  ✅ BUG-6 FIX: URL redirect check after login
# ══════════════════════════════════════════════════════════════
def ints_login(bn, email, pw, url="", forced_path=None):
    s = _session()
    try:
        r = s.get(f"{url}/login", timeout=25, allow_redirects=True)
    except Exception as e:
        raise Exception(f"{bn} · server unreachable: {e}")

    low = r.text.lower()
    if r.status_code in (403, 401) or "not in allowlist" in low or "not allowed" in low:
        raise Exception(f"{bn} · IP blocked (HTTP {r.status_code})")

    capt = _solve_captcha(r.text)

    csrf = ""
    for pat in [
        r'name=["\']_token["\'][^>]+value=["\']([^"\']+)["\']',
        r'value=["\']([^"\']+)["\'][^>]+name=["\']_token["\']',
        r'meta[^>]+name=["\']csrf-token["\'][^>]+content=["\']([^"\']+)["\']',
    ]:
        m = re.search(pat, r.text)
        if m:
            csrf = m.group(1)
            break
    if not csrf:
        logger.debug(f"{bn} · no CSRF token on login page (may be OK for this panel)")

    post_data = {
        "username": email, "password": pw,
        "capt": capt, "g-recaptcha-response": "",
    }
    if csrf:
        post_data["_token"] = csrf

    try:
        r2 = s.post(
            f"{url}/signin",
            data=post_data,
            headers={**_BASE_HEADERS,
                     "Referer": f"{url}/login",
                     "Content-Type": "application/x-www-form-urlencoded",
                     "Origin": url},
            allow_redirects=True, timeout=20,
        )
    except Exception as e:
        raise Exception(f"{bn} · signin POST failed: {e}")

    # Check session cookie
    sid = (s.cookies.get("PHPSESSID") or s.cookies.get("session")
           or s.cookies.get("laravel_session"))
    if not sid:
        raise Exception(f"{bn} · no session cookie after login (HTTP {r2.status_code})"
                        " — wrong credentials or server issue")

    # ✅ BUG-6 FIX: Check URL — redirected back to login = failed
    final_url = str(r2.url).lower()
    if any(x in final_url for x in ["/login", "/signin", "/sign-in"]):
        raise Exception(f"{bn} · login failed — redirected back to login"
                        " (wrong credentials or rate limit)")

    # Detect path
    if forced_path in ("agent", "client", "reseller"):
        path = forced_path
    elif "client" in str(r2.url):
        path = "client"
    elif "reseller" in str(r2.url):
        path = "reseller"
    else:
        path = "agent"

    logger.info(f"✅ ints_login {bn} {email} · path:{path}")
    return s, path, url


def ints_fetch(bn, session_info, url=""):
    import requests as rq
    if (isinstance(session_info, tuple) and len(session_info) == 3
            and hasattr(session_info[0], "cookies")):
        s, path, _url = session_info
        url = _url or url
    else:
        # Legacy cookie-file fallback
        cookie_file = session_info[0] if isinstance(session_info, tuple) else session_info
        path = session_info[1] if isinstance(session_info, tuple) else "agent"
        s = _session()
        try:
            with open(cookie_file) as cf:
                for line in cf:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    parts = line.split("\t")
                    if len(parts) >= 7:
                        s.cookies.set(parts[5], parts[6], domain=parts[0])
        except Exception as e:
            logger.warning(f"ints_fetch cookie load fail {bn}: {e}")
            return None

    result = _core_fetch(s, url, path)
    if result is None:
        logger.warning(f"ints_fetch {bn} · session expired → will re-login")
    elif result:
        logger.info(f"✅ ints_fetch {bn} · {len(result)} rows")
    else:
        logger.debug(f"ints_fetch {bn} · 0 rows (authenticated, no data)")
    return result


# Backward compat
def hadi_login(email, pw, url=""): return ints_login("HADI_SMS", email, pw, url)
def hadi_fetch(cookie_file, url=""): return ints_fetch("HADI_SMS", cookie_file, url)


# ══════════════════════════════════════════════════════════════
#  MJ SMS — server-rendered /ints/sms-records
#
#  MJ SMS looks like an INTS panel, but its CDR is rendered as an
#  HTML table and the login form posts back to /login/.  Keep this
#  handler separate from the JSON-based INTS fetcher.
# ══════════════════════════════════════════════════════════════
def _mj_sms_base_url(url: str) -> str:
    """Normalize the MJ SMS base URL or one of its page URLs."""
    value = (url or "").strip().rstrip("/")
    return re.sub(r"/(?:login|dashboard|sms-records)/?$", "", value,
                  flags=re.I).rstrip("/")


def _mj_sms_parse_records_html(text: str) -> list:
    """Convert MJ SMS's Date/Range/Number/CLI/SMS table to panel rows."""
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        logger.error("MJ SMS parser requires beautifulsoup4")
        return []

    soup = BeautifulSoup(text or "", "html.parser")
    tables = soup.select("table.data-table") or soup.select("table")
    if not tables:
        return []

    def normalized(value):
        return re.sub(r"[^a-z0-9]+", "", value.lower())

    def find_index(headers, *names):
        for index, header in enumerate(headers):
            if any(
                header == name or (len(name) >= 4 and name in header)
                for name in names
            ):
                return index
        return None

    # MJ's page can contain dashboard tables before the CDR table.  Select the
    # table by its columns instead of assuming the first table is the report.
    for table in tables:
        header_cells = table.select("thead th")
        table_rows = table.select("tbody tr")
        if not header_cells:
            first_row = table.select_one("tr")
            header_cells = first_row.select("th") if first_row else []
            if not header_cells and first_row:
                header_cells = first_row.select("td")

        headers = [normalized(cell.get_text(" ", strip=True)) for cell in header_cells]
        number_index = find_index(headers, "number", "phone", "msisdn", "mobile")
        sms_index = find_index(headers, "sms", "message", "text", "body", "content")
        if number_index is None or sms_index is None:
            continue

        date_index = find_index(headers, "date", "datetime", "received", "timestamp")
        cli_index = find_index(headers, "cli", "sender", "from", "source")
        if not table_rows:
            table_rows = table.select("tr")[1:]

        rows = []
        for row_index, tr in enumerate(table_rows):
            cells = tr.select("td")
            if not cells or max(number_index, sms_index) >= len(cells):
                continue

            values = [cell.get_text(" ", strip=True) for cell in cells]
            number = re.sub(r"\D", "", values[number_index])
            if not number or number == "0":
                continue

            sms = _html.unescape(values[sms_index].strip())
            if not sms or sms in {"-", "—", "N/A", "None", "null"}:
                continue

            stamp = (
                values[date_index].strip()
                if date_index is not None and date_index < len(values)
                else ""
            )
            cli = (
                values[cli_index].strip()
                if cli_index is not None and cli_index < len(values)
                else ""
            )
            rid = tr.get("data-id") or tr.get("id") or str(row_index)
            rows.append([stamp, str(rid), number, cli, None, sms])
        return rows

    logger.warning("MJ SMS records page has no table with Number and SMS columns")
    return []


def mj_sms_login(bn, username, password, url=""):
    """Login to MJ SMS and retain its mj_sms_session cookie."""
    s = _session()
    base_url = _mj_sms_base_url(url)
    # The panel redirects /login to /login/.  Posting directly to the
    # canonical URL prevents a 301 from converting the POST into a GET.
    login_url = f"{base_url}/login/"

    try:
        response = s.get(
            login_url,
            headers=_BASE_HEADERS,
            timeout=25,
            allow_redirects=True,
        )
    except Exception as exc:
        raise Exception(f"{bn} · MJ SMS server unreachable: {exc}")

    if response.status_code >= 400:
        raise Exception(f"{bn} · MJ SMS login page HTTP {response.status_code}")

    post_data = {
        "username": username,
        "password": password,
        "captcha": _solve_captcha(response.text),
        "login": "Login",
    }
    try:
        result = s.post(
            login_url,
            data=post_data,
            headers={
                **_BASE_HEADERS,
                "Referer": login_url,
                "Content-Type": "application/x-www-form-urlencoded",
                "Origin": base_url,
            },
            allow_redirects=True,
            timeout=25,
        )
    except Exception as exc:
        raise Exception(f"{bn} · MJ SMS login POST failed: {exc}")

    sid = next(
        (cookie.value for cookie in s.cookies
         if cookie.name == "mj_sms_session" and cookie.value),
        "",
    )
    final_url = str(result.url).lower()
    if not sid:
        raise Exception(f"{bn} · MJ SMS session cookie tidak ditemukan")
    if "/login" in final_url or "account login" in result.text.lower():
        raise Exception(
            f"{bn} · MJ SMS login gagal — username/password atau captcha tidak valid"
        )

    logger.info(f"✅ mj_sms_login {bn} {username}")
    return s, "agent", base_url


def mj_sms_fetch(bn, session_info, url=""):
    """Fetch MJ SMS records using the authenticated HTML report page."""
    if not (isinstance(session_info, tuple) and len(session_info) == 3
            and hasattr(session_info[0], "cookies")):
        return []

    s, _role, session_url = session_info
    base_url = _mj_sms_base_url(session_url or url)
    d1, d2 = _dates()
    try:
        records_url = f"{base_url}/sms-records/"
        response = s.post(
            records_url,
            data={
                "filter_sms": "1",
                "search": "",
                "from": d1[:10],
                "to": d2[:10],
                "per_page": "all",
            },
            headers={
                **_BASE_HEADERS,
                "Referer": f"{base_url}/dashboard",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            timeout=25,
            allow_redirects=True,
        )
    except Exception as exc:
        logger.warning(f"{bn} · MJ SMS network error: {str(exc)[:120]}")
        return []

    if _is_session_expired(response):
        logger.warning(f"⚠️ {bn} · MJ SMS session expired")
        return None
    if response.status_code >= 400:
        raise Exception(f"{bn} · MJ SMS records HTTP {response.status_code}")

    rows = _mj_sms_parse_records_html(response.text)
    # Some MJ deployments render the report on GET and ignore POST filters.
    # A GET fallback also keeps the integration working when the account has
    # no filter form in its role-specific HTML.
    if not rows:
        try:
            fallback = s.get(
                records_url,
                headers={**_BASE_HEADERS, "Referer": f"{base_url}/dashboard"},
                timeout=25,
                allow_redirects=True,
            )
        except Exception as exc:
            logger.warning(f"{bn} · MJ SMS GET fallback failed: {str(exc)[:120]}")
        else:
            if _is_session_expired(fallback):
                logger.warning(f"⚠️ {bn} · MJ SMS GET fallback session expired")
                return None
            if fallback.status_code >= 400:
                raise Exception(f"{bn} · MJ SMS records GET HTTP {fallback.status_code}")
            rows = _mj_sms_parse_records_html(fallback.text)
    logger.info(f"✅ {bn} · MJ SMS records rows={len(rows)} · {response.url}")
    return rows


# ══════════════════════════════════════════════════════════════
#  NEXA SMS — server-rendered /ints/sms-cdr-reports
#
#  NEXA uses the same captcha/signin flow as the INTS family, but its
#  report page renders the SMS rows directly as HTML instead of exposing
#  the data_smscdr JSON endpoints used by _core_fetch().
# ══════════════════════════════════════════════════════════════
def _nexa_base_url(url: str) -> str:
    """Normalize either the panel base URL or one of NEXA's page URLs."""
    value = (url or "").strip().rstrip("/")
    return re.sub(r"/(?:login|sms-cdr-reports)/?$", "", value, flags=re.I).rstrip("/")


def _nexa_parse_cdr_html(text: str) -> list:
    """Convert NEXA's Detailed SMS Reports table to normalized panel rows."""
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        logger.error("NEXA parser requires beautifulsoup4")
        return []

    soup = BeautifulSoup(text or "", "html.parser")
    table = soup.select_one("table#dt") or soup.select_one("table")
    if table is None:
        return []

    header_cells = table.select("thead th")
    headers = [
        re.sub(r"[^a-z0-9]+", "", cell.get_text(" ", strip=True).lower())
        for cell in header_cells
    ]

    def find_index(*names):
        for name in names:
            if name in headers:
                return headers.index(name)
        return None

    date_index = find_index("date", "datetime", "received")
    number_index = find_index("number", "phone", "msisdn", "mobile")
    cli_index = find_index("cli", "sender", "service", "from")
    sms_index = find_index("sms", "message", "text", "body", "content")
    if number_index is None or sms_index is None:
        logger.warning("NEXA CDR table missing Number or SMS columns")
        return []

    rows = []
    for row_index, tr in enumerate(table.select("tbody tr")):
        cells = tr.select("td")
        if not cells:
            continue
        values = [cell.get_text("\n", strip=True) for cell in cells]
        if max(number_index, sms_index) >= len(values):
            continue

        number = re.sub(r"\D", "", values[number_index])
        if not number or number == "0":
            continue

        sms = values[sms_index].strip()
        if not sms or re.fullmatch(r"[*—]+", sms):
            continue

        stamp = values[date_index].strip() if date_index is not None and date_index < len(values) else ""
        cli = values[cli_index].strip() if cli_index is not None and cli_index < len(values) else ""
        rid = tr.get("data-id") or tr.get("id") or str(row_index)
        rows.append([stamp, str(rid), number, cli, None, sms])

    return rows


def nexa_login(bn, username, password, url=""):
    """NEXA login: reuse the compatible INTS captcha/signin flow."""
    return ints_login(bn, username, password, _nexa_base_url(url))


def nexa_fetch(bn, session_info, url=""):
    """Fetch NEXA SMS rows from the server-rendered CDR report page."""
    if not (isinstance(session_info, tuple) and len(session_info) == 3
            and hasattr(session_info[0], "cookies")):
        return []

    s, _role, session_url = session_info
    base_url = _nexa_base_url(session_url or url)
    d1, d2 = _dates()
    try:
        response = s.get(
            f"{base_url}/sms-cdr-reports",
            params={
                "fdate1": d1,
                "fdate2": d2,
                "frange": "",
                "fclient": "",
                "fnum": "",
                "fcli": "",
            },
            headers={
                **_BASE_HEADERS,
                "Referer": f"{base_url}/agent/SMSDashboard",
            },
            timeout=25,
            allow_redirects=True,
        )
    except Exception as exc:
        logger.warning(f"{bn} · NEXA network error: {str(exc)[:120]}")
        return []

    if _is_session_expired(response):
        logger.warning(f"{bn} · NEXA session expired")
        return None
    if response.status_code >= 400:
        raise Exception(f"{bn} · NEXA CDR HTTP {response.status_code}")

    rows = _nexa_parse_cdr_html(response.text)
    logger.info(f"✅ {bn} · NEXA CDR rows={len(rows)} · {response.url}")
    return rows


###############################################################################
#  MBCS — MBC SMS HTML login + server-rendered /agent/SMSCDRReports
#
#  MBCS uses the MBC SMS AJAX login form (username/password/capt) and a
#  server-rendered agent report. Keep it separate from the INTS JSON engine:
#  the login response can be JSON with a redirect rather than a normal 302,
#  and the report table has changed column names across deployments.
###############################################################################
MBCS_DEFAULT_URL = "https://mbcs-ms.com"
MBCS_API_DEFAULT_URL = "https://mbcs-ms.com/crapi/mbc/viewstats"


def _mbcs_base_url(url: str) -> str:
    value = (url or MBCS_DEFAULT_URL).strip().rstrip("/")
    return re.sub(
        r"/(?:login|agent/(?:SMSCDRReports|SMSDashboard))/?$",
        "",
        value,
        flags=re.I,
    ).rstrip("/")


def _mbcs_parse_cdr_html(text: str) -> list:
    """Parse MBCS report tables into the common panel row shape."""
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        logger.error("MBCS parser requires beautifulsoup4")
        return []

    soup = BeautifulSoup(text or "", "html.parser")
    output = []
    seen = set()

    for table in soup.find_all("table"):
        header_cells = table.select("thead th, thead td")
        if not header_cells:
            first_row = table.find("tr")
            header_cells = first_row.find_all(["th", "td"], recursive=False) if first_row else []
        headers = [
            re.sub(r"[^a-z0-9]+", "", cell.get_text(" ", strip=True).lower())
            for cell in header_cells
        ]

        def find_index(*aliases):
            for index, header in enumerate(headers):
                if any(alias == header or alias in header for alias in aliases):
                    return index
            return None

        date_index = find_index("date", "datetime", "received", "timestamp", "time")
        number_index = find_index("number", "phone", "msisdn", "mobile", "destination")
        sender_index = find_index("cli", "sender", "service", "from", "source")
        message_index = find_index("sms", "message", "text", "body", "content")

        table_rows = table.select("tbody tr")
        if not table_rows:
            all_rows = table.find_all("tr")
            table_rows = all_rows[1:] if headers and all_rows else all_rows

        for row_index, tr in enumerate(table_rows):
            cells = tr.find_all(["td", "th"], recursive=False)
            if not cells:
                continue
            values = [
                _html.unescape(
                    re.sub(r"\s+", " ", (
                        cell.get("data-message")
                        or cell.get("title")
                        or cell.get_text(" ", strip=True)
                    )).strip()
                )
                for cell in cells
            ]
            if not values:
                continue

            def value_at(index):
                return values[index].strip() if index is not None and index < len(values) else ""

            number = re.sub(r"\D", "", value_at(number_index))
            if len(number) < 6:
                number = next(
                    (
                        re.sub(r"\D", "", value)
                        for value in values
                        if len(re.sub(r"\D", "", value)) >= 6
                    ),
                    "",
                )
            if not number or number == "0":
                continue

            message = value_at(message_index)
            if not message:
                candidates = [
                    value for value in values
                    if value and re.sub(r"\D", "", value) != number
                    and not re.fullmatch(r"[-—N/A]+", value, re.I)
                ]
                message = max(candidates, key=len, default="")
            if not message or message in {"-", "—", "N/A", "None", "null"}:
                continue

            stamp = value_at(date_index)
            sender = value_at(sender_index)
            row_id = tr.get("data-id") or tr.get("id") or str(row_index)
            dedupe_key = (str(row_id), number, message)
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            output.append([stamp, str(row_id), number, sender, None, message])

    return output


def mbcs_login(bn, username, password, url=MBCS_DEFAULT_URL):
    """Authenticate to MBC SMS, whose AJAX login returns a redirect JSON."""
    s = _session()
    base_url = _mbcs_base_url(url)
    login_url = f"{base_url}/login"
    try:
        page = s.get(login_url, headers=_BASE_HEADERS, timeout=25, allow_redirects=True)
    except Exception as exc:
        raise Exception(f"{bn} · MBCS server unreachable: {exc}") from exc
    if page.status_code >= 400:
        raise Exception(f"{bn} · MBCS login page HTTP {page.status_code}")

    post_data = {
        "username": str(username or "").strip(),
        "password": str(password or ""),
        "capt": _solve_captcha(page.text),
    }
    try:
        response = s.post(
            login_url,
            data=post_data,
            headers={
                **_BASE_HEADERS,
                "Accept": "application/json, text/html;q=0.9",
                "X-Requested-With": "XMLHttpRequest",
                "Referer": str(page.url or login_url),
                "Origin": base_url,
                "Content-Type": "application/x-www-form-urlencoded",
            },
            timeout=25,
            allow_redirects=False,
        )
    except Exception as exc:
        raise Exception(f"{bn} · MBCS login request failed: {exc}") from exc

    if response.status_code == 429:
        retry_after = str(response.headers.get("Retry-After", "") or "").strip()
        suffix = f"; retry after {retry_after}s" if retry_after.isdigit() else ""
        raise Exception(f"{bn} · MBCS login rate limited{suffix}")
    if response.status_code in (401, 403):
        raise Exception(f"{bn} · MBCS login ditolak (HTTP {response.status_code})")

    redirect = response.headers.get("Location", "")
    payload = None
    if "json" in response.headers.get("Content-Type", "").lower():
        try:
            payload = response.json()
        except ValueError:
            payload = None
    if isinstance(payload, dict):
        if not payload.get("ok"):
            message = str(payload.get("message") or "username/password/captcha tidak valid")
            raise Exception(f"{bn} · MBCS login gagal: {message[:160]}")
        redirect = str(payload.get("redirect") or redirect or "/agent/SMSDashboard")
    elif response.status_code in (301, 302, 303, 307, 308):
        redirect = redirect or "/agent/SMSDashboard"
    elif response.status_code >= 400:
        raise Exception(f"{bn} · MBCS login HTTP {response.status_code}")

    landing = response
    if redirect:
        try:
            landing = s.get(
                urljoin(base_url + "/", redirect),
                headers={**_BASE_HEADERS, "Referer": login_url},
                timeout=25,
                allow_redirects=True,
            )
        except Exception as exc:
            raise Exception(f"{bn} · MBCS dashboard request failed: {exc}") from exc

    final_url = str(landing.url or "").lower()
    if not s.cookies or "/login" in final_url:
        raise Exception(f"{bn} · MBCS login gagal — username/password atau captcha tidak valid")

    logger.info(f"✅ MBCS login {bn} {str(username or '').strip()}")
    return s, "agent", base_url


def mbcs_fetch(bn, session_info, url=MBCS_DEFAULT_URL):
    """Fetch MBCS agent SMS history from SMSCDRReports."""
    if not (
        isinstance(session_info, tuple)
        and len(session_info) == 3
        and hasattr(session_info[0], "cookies")
    ):
        return []

    s, _role, session_url = session_info
    base_url = _mbcs_base_url(session_url or url)
    endpoint = f"{base_url}/agent/SMSCDRReports"
    d1, d2 = _dates()
    try:
        response = s.get(
            endpoint,
            params={
                "fdate1": d1,
                "fdate2": d2,
                "frange": "",
                "fclient": "",
                "fnum": "",
                "fcli": "",
            },
            headers={**_BASE_HEADERS, "Referer": f"{base_url}/agent/SMSDashboard"},
            timeout=25,
            allow_redirects=True,
        )
    except Exception as exc:
        logger.warning(f"{bn} · MBCS network error: {str(exc)[:120]}")
        return []

    if _is_session_expired(response):
        logger.warning(f"⚠️ {bn} · MBCS session expired")
        return None
    if response.status_code >= 400:
        raise Exception(f"{bn} · MBCS SMSCDRReports HTTP {response.status_code}")

    rows = _mbcs_parse_cdr_html(response.text)
    logger.info(f"✅ {bn} · MBCS SMSCDRReports rows={len(rows)}")
    return rows


###############################################################################
#  MBCS API — token query endpoint /crapi/mbc/viewstats
#
#  This is separate from the browser login above. MBC PANL exposes a client
#  token in the profile and expects it as ?token=... on every request.
###############################################################################
def _mbcs_api_endpoint(url: str) -> str:
    value = (url or MBCS_API_DEFAULT_URL).strip().rstrip("/")
    if value.lower().endswith("/crapi/mbc/viewstats"):
        return value
    return f"{value}/crapi/mbc/viewstats"


def _mbcs_api_payload(response, label):
    if response.status_code in (401, 403):
        return None
    try:
        payload = response.json()
    except Exception as exc:
        raise Exception(f"{label} response bukan JSON yang valid") from exc
    if response.status_code >= 400:
        message = payload.get("message") if isinstance(payload, dict) else ""
        raise Exception(f"{label} API HTTP {response.status_code}: {str(message or 'request gagal')[:160]}")
    return payload


def _mbcs_api_error(payload) -> str:
    if not isinstance(payload, dict):
        return ""
    status = str(payload.get("status") or "").strip().lower()
    if status in {"error", "failed", "fail"}:
        return str(payload.get("message") or payload.get("error") or "API request gagal")
    if payload.get("success") is False:
        return str(payload.get("message") or "API request gagal")
    return ""


def _mbcs_api_rows(payload) -> list:
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return []
    for key in ("data", "records", "results", "rows", "messages"):
        value = payload.get(key)
        if isinstance(value, list):
            return value
        if isinstance(value, dict):
            for nested_key in ("data", "records", "results", "rows", "messages"):
                nested = value.get(nested_key)
                if isinstance(nested, list):
                    return nested
    return []


def mbcs_api_login(bn, account_label, token, url=MBCS_API_DEFAULT_URL):
    """Validate an MBC PANL client token with one minimal records request."""
    token = str(token or "").strip()
    if not token:
        raise Exception(f"{bn} · API token MBCs kosong")
    endpoint = _mbcs_api_endpoint(url)
    s = _session()
    try:
        response = s.get(
            endpoint,
            params={"token": token, "records": 1},
            headers={"Accept": "application/json"},
            timeout=20,
        )
    except Exception as exc:
        raise Exception(f"{bn} · MBCs API connection error: {exc}") from exc
    payload = _mbcs_api_payload(response, "MBCs API")
    if payload is None:
        raise Exception(f"{bn} · API token MBCs tidak valid/ditolak")
    error = _mbcs_api_error(payload)
    if error:
        raise Exception(f"{bn} · MBCs API: {error[:160]}")
    logger.info(f"✅ {bn} {account_label} · MBCs API token valid")
    return s, token, endpoint


def mbcs_api_fetch(session_info, url=MBCS_API_DEFAULT_URL):
    """Fetch and normalize MBC PANL API records."""
    if not (isinstance(session_info, tuple) and len(session_info) == 3):
        return []
    s, token, endpoint = session_info
    endpoint = endpoint or _mbcs_api_endpoint(url)
    try:
        response = s.get(
            endpoint,
            params={"token": token, "records": 200},
            headers={"Accept": "application/json"},
            timeout=25,
        )
    except Exception as exc:
        logger.warning(f"MBCs API fetch · network error: {str(exc)[:120]}")
        return []
    if response.status_code in (401, 403):
        return None
    try:
        payload = response.json()
    except Exception:
        logger.warning("MBCs API fetch · response bukan JSON")
        return []
    error = _mbcs_api_error(payload)
    if error:
        if "token" in error.lower() or "auth" in error.lower():
            return None
        logger.warning(f"MBCs API fetch · {error[:160]}")
        return []

    rows = []
    for index, item in enumerate(_mbcs_api_rows(payload)):
        if not isinstance(item, dict):
            continue
        row = _api_row(
            _api_row_value(
                item, "received_at", "receivedAt", "created_at", "createdAt",
                "timestamp", "datetime", "date", "time", "dt",
            ),
            _api_row_value(item, "id", "record_id", "message_id", "sms_id", "event_id") or str(index),
            _api_row_value(item, "number", "num", "phone_number", "phone", "msisdn", "mobile", "destination"),
            _api_row_value(item, "cli", "source", "sender", "sender_id", "origin", "from"),
            _api_row_value(item, "message", "sms", "message_body", "message_text", "text", "content", "body"),
        )
        if row:
            rows.append(row)
    logger.info(f"✅ MBCs API fetch · rows={len(rows)}")
    return rows


# ══════════════════════════════════════════════════════════════
#  ALEIUS SMS — server-rendered /ints/{agent|client}/cdr
#
#  Aleius uses the same visual CDR table as the INTS family, but:
#    * login is POSTed to /ints/login (not /ints/signin)
#    * the CDR is rendered as HTML
#    * some rows intentionally hide the OTP or omit the CLI
#    * agent/cdr may be unavailable, so client/cdr is a fallback
# ══════════════════════════════════════════════════════════════
def _aleius_base_url(url: str) -> str:
    """Normalize an Aleius base URL or one of its page URLs."""
    value = (url or "").strip().rstrip("/")
    return re.sub(r"/(?:login|(?:agent|client|reseller)/cdr)/?$", "",
                  value, flags=re.I).rstrip("/")


def _aleius_parse_cdr_html(text: str) -> list:
    """
    Convert Aleius' HTML CDR table into the common panel row shape.

    A number is the minimum required field.  SMS/CLI are deliberately allowed
    to be empty so the caller can still forward the row to the OTP group with
    a hidden OTP placeholder.
    """
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        logger.error("Aleius parser requires beautifulsoup4")
        return []

    soup = BeautifulSoup(text or "", "html.parser")
    table = soup.select_one("table#dt") or soup.select_one("table")
    if table is None:
        return []

    headers = [
        re.sub(r"[^a-z0-9]+", "", cell.get_text(" ", strip=True).lower())
        for cell in table.select("thead th")
    ]

    def find_index(*names):
        for name in names:
            if name in headers:
                return headers.index(name)
        return None

    date_index = find_index("date", "datetime", "received", "timestamp")
    number_index = find_index("number", "phone", "msisdn", "mobile")
    cli_index = find_index("cli", "sender", "from", "source")
    sms_index = find_index("message", "sms", "text", "body", "content")
    if number_index is None:
        logger.warning("Aleius CDR table missing Number column")
        return []

    rows = []
    table_rows = table.select("tbody tr")
    if not table_rows:
        table_rows = table.select("tr")[1:]
    for row_index, tr in enumerate(table_rows):
        cells = tr.select("td")
        if not cells or number_index >= len(cells):
            continue

        values = [cell.get_text(" ", strip=True) for cell in cells]
        number = re.sub(r"\D", "", values[number_index])
        if not number or number == "0":
            continue

        sms = (
            values[sms_index].strip()
            if sms_index is not None and sms_index < len(values)
            else ""
        )
        if sms in {"-", "—", "N/A", "None", "null"}:
            sms = ""

        stamp = (
            values[date_index].strip()
            if date_index is not None and date_index < len(values)
            else ""
        )
        cli = (
            values[cli_index].strip()
            if cli_index is not None and cli_index < len(values)
            else ""
        )
        rid = tr.get("data-id") or tr.get("id") or str(row_index)
        rows.append([stamp, str(rid), number, cli, None, _html.unescape(sms)])

    return rows


def aleius_login(bn, username, password, url=""):
    """Login to Aleius' /ints/login form and preserve the resolved role path."""
    s = _session()
    base_url = _aleius_base_url(url)
    login_url = f"{base_url}/login"

    try:
        response = s.get(login_url, headers=_BASE_HEADERS,
                         timeout=25, allow_redirects=True)
    except Exception as exc:
        raise Exception(f"{bn} · server unreachable: {exc}")

    if response.status_code >= 400:
        raise Exception(f"{bn} · login page HTTP {response.status_code}")

    capt = _solve_captcha(response.text)
    post_data = {
        "username": username,
        "password": password,
        "capt": capt,
        "next": "",
    }
    try:
        result = s.post(
            login_url,
            data=post_data,
            headers={
                **_BASE_HEADERS,
                "Referer": login_url,
                "Content-Type": "application/x-www-form-urlencoded",
                "Origin": base_url,
            },
            allow_redirects=True,
            timeout=25,
        )
    except Exception as exc:
        raise Exception(f"{bn} · login POST failed: {exc}")

    if result.status_code in (401, 403):
        raise Exception(f"{bn} · login failed HTTP {result.status_code}")

    final_url = str(result.url).lower()
    if "/login" in final_url or "please sign in" in result.text.lower():
        raise Exception(f"{bn} · login failed — redirected back to login")

    if not s.cookies:
        raise Exception(f"{bn} · no session cookie after login")

    if "/client" in final_url:
        path = "client"
    elif "/reseller" in final_url:
        path = "reseller"
    else:
        path = "agent"

    logger.info(f"✅ aleius_login {bn} {username} · path:{path}")
    return s, path, base_url


def aleius_fetch(bn, session_info, url=""):
    """Fetch Aleius CDR rows, falling back from agent/cdr to client/cdr."""
    if not (isinstance(session_info, tuple) and len(session_info) == 3
            and hasattr(session_info[0], "cookies")):
        return []

    s, role, session_url = session_info
    base_url = _aleius_base_url(session_url or url)
    paths = list(dict.fromkeys([role, "agent", "client"]))
    last_status = None

    for path in paths:
        endpoint = f"{base_url}/{path}/cdr"
        try:
            response = s.get(
                endpoint,
                params={
                    "fdate1": _dates()[0],
                    "fdate2": _dates()[1],
                },
                headers={**_BASE_HEADERS, "Referer": endpoint},
                timeout=25,
                allow_redirects=True,
            )
        except Exception as exc:
            logger.warning(f"{bn} · Aleius {path}/cdr network error: {str(exc)[:120]}")
            continue

        last_status = response.status_code
        if _is_session_expired(response):
            # A forbidden path is a normal fallback signal here; an actual
            # redirect to login means the session itself has expired.
            if response.status_code == 403 and path != role:
                continue
            if "/login" in str(response.url).lower() or response.status_code == 401:
                return None
            continue

        if response.status_code >= 400:
            continue

        rows = _aleius_parse_cdr_html(response.text)
        logger.info(f"✅ {bn} · Aleius {path}/cdr rows={len(rows)}")
        if rows:
            return rows
        # A role page can return HTTP 200 with an empty shell or an access
        # notice. Try the alternate role before reporting no data.
        continue

    logger.warning(f"{bn} · Aleius CDR unavailable (last HTTP {last_status})")
    return []


# ══════════════════════════════════════════════════════════════
#  STANDARD PANEL  (PurplePanel, TrueSMS, etc.)
#  ✅ BUG-6 FIX: URL redirect check after login
#  ✅ FIX-D: laravel_session cookie now also checked
# ══════════════════════════════════════════════════════════════
def panel_login(bn, email, pw, url):
    s = _session()
    # Purple SMS uses a /sms application prefix and has a different
    # endpoint pair from the generic INTS panels.  Normalize the URL so
    # custom panel entries with a trailing slash work as well.
    url = (url or "").rstrip("/")
    if re.search(r"/sms(?:/|$)", url, re.I):
        lp, sp = "SignIn", "signmein"
    else:
        lp, sp = "login", "signin"

    try:
        r = s.get(f"{url}/{lp}", timeout=25, allow_redirects=True)
    except Exception as e:
        raise Exception(f"{bn} · server unreachable: {e}")

    low = r.text.lower()
    if r.status_code in (403, 401) or "not in allowlist" in low:
        raise Exception(f"{bn} · IP blocked (HTTP {r.status_code})")

    capt = _solve_captcha(r.text)
    csrf = ""
    m = re.search(r'name=["\']_token["\'][^>]+value=["\']([^"\']+)["\']', r.text)
    if m:
        csrf = m.group(1)

    post_data = {"username": email, "password": pw,
                 "capt": capt, "g-recaptcha-response": ""}
    if csrf:
        post_data["_token"] = csrf

    r2 = s.post(f"{url}/{sp}", data=post_data,
                headers={**_BASE_HEADERS,
                         "Referer": f"{url}/{lp}",
                         "Content-Type": "application/x-www-form-urlencoded",
                         "Origin": url},
                allow_redirects=True, timeout=20)

    # ✅ FIX-D: Also check laravel_session (some panels use it)
    sid = (s.cookies.get("PHPSESSID") or s.cookies.get("session")
           or s.cookies.get("laravel_session"))
    if not sid:
        raise Exception(f"{bn} · no session cookie after login (wrong credentials?)")

    # ✅ BUG-6 FIX: URL check
    final_url = str(r2.url).lower()
    if f"/{lp.lower()}" in final_url or f"/{sp.lower()}" in final_url:
        raise Exception(f"{bn} · login failed — redirected back to login page")

    rurl = str(r2.url)
    if "reseller" in rurl:
        path = "reseller"
    elif "client" in rurl:
        path = "client"
    else:
        path = "agent"

    logger.info(f"✅ panel_login {bn} {email} · path:{path}")
    return s, path, url


def purple_sms_login(bn, email, pw, url):
    """Purple SMS login: GET /sms/SignIn, then POST /sms/signmein."""
    return panel_login(bn, email, pw, (url or "").rstrip("/"))


def panel_fetch(session_info, url):
    if (isinstance(session_info, tuple) and len(session_info) == 3
            and hasattr(session_info[0], "cookies")):
        s, path, _url = session_info
        url = _url or url
    else:
        s = _session()
        path = "agent"
    return _core_fetch(s, url, path)


def sms_login(bn, email, pw, url):
    """Login to Nexor's Livewire portal without affecting other panel types."""
    import urllib.parse
    import time

    logger.info(f"🔧 [{bn}] SMS handler {NEXOR_SMS_HANDLER_VERSION}")
    s = _session()
    url = re.sub(
        r"/(?:portal/login|agent/stats|client/stats)/?$",
        "",
        (url or "").strip(),
        flags=re.I,
    ).rstrip("/")
    login_url = f"{url}/portal/login"
    try:
        page = s.get(login_url, timeout=25, allow_redirects=True)
    except Exception as exc:
        raise Exception(f"{bn} · Nexor server unreachable: {exc}")
    if page.status_code in (401, 403):
        raise Exception(f"{bn} · Nexor login page blocked (HTTP {page.status_code})")

    snapshot_match = re.search(r"""wire:snapshot=['"]([^'"]+)['"]""", page.text)
    if not snapshot_match:
        logger.error(
            f"❌ [{bn}] Nexor snapshot missing · HTTP {page.status_code} · "
            f"url={page.url} · bytes={len(page.text)} · "
            f"content_type={page.headers.get('Content-Type', '')}"
        )
        raise Exception(f"{bn} · Nexor Livewire snapshot tidak ditemukan")
    snapshot = _html.unescape(snapshot_match.group(1))
    try:
        snapshot_data = json.loads(snapshot)
    except Exception as exc:
        raise Exception(f"{bn} · Nexor snapshot tidak valid: {exc}")

    challenge = str(snapshot_data.get("data", {}).get("captchaChallenge", ""))
    zeros = int(snapshot_data.get("data", {}).get("captchaZeros", 0) or 0)
    nonce = ""
    if challenge and zeros:
        target = "0" * zeros
        for number in range(50_000_000):
            candidate = str(number)
            if hashlib.sha256(f"{challenge}:{candidate}".encode()).hexdigest().startswith(target):
                nonce = candidate
                break
        if not nonce:
            raise Exception(f"{bn} · Nexor captcha gagal diselesaikan")
    # Nexor rejects a Livewire login submitted immediately after page load.
    # Keep this deliberately longer for re-login after an expired session.
    time.sleep(8)

    update_uri_match = re.search(r"""data-update-uri=['"]([^'"]+)['"]""", page.text)
    update_url = _html.unescape(update_uri_match.group(1)) if update_uri_match else f"{url}/livewire/update"
    csrf_match = re.search(r"""data-csrf=['"]([^'"]+)['"]""", page.text)
    csrf = _html.unescape(csrf_match.group(1)) if csrf_match else ""
    component = {
        "snapshot": snapshot,
        "updates": {
            "username": email,
            "password": pw,
            "captchaNonce": nonce,
        },
        "calls": [{"path": "", "method": "login", "params": []}],
    }
    headers = {
        **_AJAX_HEADERS,
        "Accept": "application/json",
        "Content-Type": "application/json",
        "X-Livewire": "true",
        "Referer": login_url,
        "Origin": url,
    }
    if csrf:
        headers["X-CSRF-TOKEN"] = csrf
    try:
        response = s.post(update_url, json={"components": [component]},
                          headers=headers, timeout=35, allow_redirects=False)
    except Exception as exc:
        raise Exception(f"{bn} · Nexor login request failed: {exc}")
    if response.status_code not in (200, 204):
        raise Exception(f"{bn} · Nexor login gagal (HTTP {response.status_code})")

    location = response.headers.get("Location", "")
    if location:
        location = urllib.parse.urljoin(url + "/", location)
    else:
        try:
            payload = response.json()
            effects = payload.get("components", [{}])[0].get("effects", {})
            location = effects.get("redirect") or ""
        except Exception:
            location = ""
    if not location or "/portal/login" in location.lower():
        low = response.text.lower()
        if any(word in low for word in ("invalid", "incorrect", "captcha", "required")):
            raise Exception(f"{bn} · Nexor login gagal — username/password atau captcha tidak valid")
        raise Exception(f"{bn} · Nexor login gagal — redirect dashboard tidak ditemukan")

    role = "client" if "/client/" in location.lower() else "agent"
    logger.info(f"✅ Nexor login {bn} · path:{role}")
    return s, role, url


def _nexor_stats_rows(text: str) -> list:
    """Normalize Nexor stats HTML tables to the bot's common row format."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(text, "html.parser")
    output = []
    for table in soup.find_all("table"):
        headers = [
            re.sub(r"\s+", " ", cell.get_text(" ", strip=True)).lower()
            for cell in table.find_all("th")
        ]
        for index, tr in enumerate(table.find_all("tr"), start=1):
            cells = [
                _html.unescape(re.sub(r"\s+", " ", cell.get_text(" ", strip=True)))
                for cell in tr.find_all(["td", "th"])
            ]
            if len(cells) < 3:
                continue
            joined = " ".join(cells).lower()
            if any(label in joined for label in ("phone number", "message", "sms text")) and not any(
                char.isdigit() for char in joined
            ):
                continue
            number_index = next(
                (i for i, header in enumerate(headers)
                 if any(word in header for word in ("number", "phone", "msisdn", "mobile"))),
                None,
            )
            message_index = next(
                (i for i, header in enumerate(headers)
                 if any(word in header for word in ("message", "sms", "text", "body", "content"))),
                None,
            )
            date_index = next(
                (i for i, header in enumerate(headers)
                 if any(word in header for word in ("date", "time", "received", "created"))),
                0,
            )
            sender_index = next(
                (i for i, header in enumerate(headers)
                 if any(word in header for word in ("sender", "service", "from", "cli"))),
                None,
            )
            candidates = [number_index] if number_index is not None else range(len(cells))
            number = next(
                (re.sub(r"\D", "", cells[i]).lstrip("0")
                 for i in candidates if i < len(cells)
                 and len(re.sub(r"\D", "", cells[i])) >= 6),
                "",
            )
            if not number:
                continue
            message = cells[message_index] if message_index is not None and message_index < len(cells) else ""
            sender = cells[sender_index] if sender_index is not None and sender_index < len(cells) else ""
            stamp = cells[date_index] if date_index < len(cells) else ""
            output.append([stamp, str(index), number, sender, None, message])
    return output


def sms_fetch(session_info, url):
    """Read Nexor agent/client SMS history with a short polling path."""
    if not (isinstance(session_info, tuple) and len(session_info) == 3):
        return []
    s, role, session_url = session_info
    base_url = re.sub(
        r"/(?:portal/login|agent/stats|client/stats)/?$",
        "",
        (session_url or url or "").strip(),
        flags=re.I,
    ).rstrip("/")
    roles = [role] + [candidate for candidate in ("agent", "client") if candidate != role]
    for current_role in roles:
        try:
            response = s.get(f"{base_url}/{current_role}/stats",
                             headers={**_BASE_HEADERS, "Referer": f"{base_url}/{current_role}/stats"},
                             timeout=20, allow_redirects=True)
        except Exception as exc:
            logger.warning(f"sms_fetch · Nexor network error: {str(exc)[:100]}")
            return []
        if _is_session_expired(response):
            # Only the role selected during login determines whether the
            # session is really expired.  Nexor returns a login redirect for
            # the other role (for example /client/stats after an agent login)
            # even when the authenticated session is perfectly valid.
            if current_role == role:
                return None
            continue
        rows = _nexor_stats_rows(response.text)
        # An authenticated page with no SMS traffic is a valid empty result.
        # Do not probe the other role: its expected login redirect used to be
        # misclassified as an expired session and caused a login loop.
        logger.info(f"✅ Nexor fetch · {len(rows)} rows · {current_role}")
        return rows
    return []


###############################################################################
#  FALCON SMS — JSON API
#
#  Falcon's browser routes are /login and /sms-cdr, while the authenticated
#  data is exposed by /api/auth/login and /api/messages/cdr.  Keep this in its
#  own handler so the existing panel handlers remain untouched.
###############################################################################
_FALCON_LOGIN_PATH = "/login"
_FALCON_CDR_PATH = "/sms-cdr"
_FALCON_SESSION_COOKIE = "connect.sid"


def _falcon_base_url(url: str) -> str:
    """Normalize a Falcon panel URL to its origin/application base."""
    return re.sub(
        r"/(?:login|sms-cdr)/?$",
        "",
        (url or "").strip(),
        flags=re.I,
    ).rstrip("/")


def _falcon_has_session_cookie(session) -> bool:
    """Check Falcon's Express session cookie without assuming one domain."""
    try:
        return any(
            cookie.name == _FALCON_SESSION_COOKIE and bool(cookie.value)
            for cookie in session.cookies
        )
    except Exception:
        try:
            return bool(session.cookies.get(_FALCON_SESSION_COOKIE))
        except Exception:
            return False


def falcon_login(bn, email, pw, url="http://169.58.94.4/login"):
    """Authenticate to Falcon SMS and wait for its session to settle."""
    import time

    s = _session()
    base_url = _falcon_base_url(url)
    login_api = f"{base_url}/api/auth/login"
    try:
        response = s.post(
            login_api,
            json={"username": email, "password": pw},
            headers={
                **_AJAX_HEADERS,
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Referer": f"{base_url}{_FALCON_LOGIN_PATH}",
                "Origin": base_url,
            },
            timeout=25,
            allow_redirects=True,
        )
    except Exception as exc:
        raise Exception(f"{bn} · Falcon server unreachable: {exc}")

    try:
        payload = response.json()
    except Exception:
        payload = {}

    user = payload.get("user") if isinstance(payload, dict) else None
    if (
        response.status_code in (401, 403)
        or response.status_code >= 400
        or not isinstance(user, dict)
        or not _falcon_has_session_cookie(s)
    ):
        detail = ""
        if isinstance(payload, dict):
            detail = str(payload.get("message") or payload.get("error") or "").strip()
        if not _falcon_has_session_cookie(s):
            detail = detail or "cookie sesi connect.sid tidak diterima"
        suffix = f": {detail}" if detail else f" (HTTP {response.status_code})"
        raise Exception(f"{bn} · Falcon login gagal{suffix}")

    # Falcon needs a short delay after a successful login before CDR requests.
    time.sleep(8)
    logger.info(f"✅ Falcon login {bn} {email} · session ready")
    return s, "falcon", base_url


def falcon_fetch(session_info, url="http://169.58.94.4/login"):
    """Fetch Falcon SMS CDR rows and normalize them for the OTP engine."""
    if not (isinstance(session_info, tuple) and len(session_info) == 3
            and hasattr(session_info[0], "cookies")):
        return []

    s, _path, session_url = session_info
    base_url = _falcon_base_url(session_url or url)
    try:
        response = s.get(
            f"{base_url}/api/messages/cdr",
            headers={
                **_AJAX_HEADERS,
                "Accept": "application/json",
                "Referer": f"{base_url}{_FALCON_CDR_PATH}",
                "Origin": base_url,
            },
            timeout=20,
            allow_redirects=True,
        )
    except Exception as exc:
        logger.warning(f"falcon_fetch · network error: {str(exc)[:100]}")
        return []

    if response.status_code in (401, 403):
        logger.warning("falcon_fetch · session expired")
        return None
    if response.status_code >= 400:
        logger.warning(f"falcon_fetch · API HTTP {response.status_code}")
        return []

    try:
        payload = response.json()
    except Exception as exc:
        logger.warning(f"falcon_fetch · invalid JSON response: {exc}")
        return []

    if isinstance(payload, list):
        raw_rows = payload
    elif isinstance(payload, dict):
        if payload.get("authenticated") is False:
            return None
        raw_rows = payload.get("data") or payload.get("messages") or payload.get("results") or []
    else:
        raw_rows = []

    rows = []
    for item in raw_rows:
        if not isinstance(item, dict):
            continue

        number = re.sub(r"\D", "", str(
            item.get("number") or item.get("msisdn") or item.get("phone") or ""
        ))
        if not number or number == "0":
            continue

        message = str(
            item.get("content") or item.get("message") or item.get("sms")
            or item.get("text") or ""
        ).strip()
        if not message:
            continue

        stamp = str(
            item.get("time") or item.get("date") or item.get("createdAt")
            or item.get("created_at") or ""
        )
        row_id = str(item.get("id") or item.get("messageId") or "")
        sender = str(
            item.get("cllr") or item.get("cli") or item.get("sender")
            or item.get("range") or ""
        )
        rows.append([
            _html.unescape(stamp),
            _html.unescape(row_id),
            number,
            _html.unescape(sender),
            None,
            _html.unescape(message),
        ])

    logger.info(f"✅ Falcon fetch · {len(rows)} rows")
    return rows


###############################################################################
#  PORSHA SMS — Flask HTML inbox
#
#  Porsha uses a Flask session, a CSRF token on the login form, and renders
#  the message history server-side at /messages rather than exposing the
#  JSON/DataTables endpoints used by the older panels.
###############################################################################
_PORSHA_LOGIN_PATH = "/login"
_PORSHA_MESSAGES_PATH = "/messages"


def _porsha_base_url(url: str) -> str:
    """Accept either the panel origin or a supplied /login URL."""
    return re.sub(
        r"/(?:login|messages)/?$",
        "",
        (url or "").strip(),
        flags=re.I,
    ).rstrip("/")


def _porsha_csrf_token(text: str) -> str:
    """Extract Porsha's CSRF token from either the meta tag or form input."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(text or "", "html.parser")
    meta = soup.select_one('meta[name="csrf-token"]')
    if meta and meta.get("content"):
        return str(meta["content"]).strip()
    field = soup.select_one(
        'input[name="csrf_token"], input[name="_token"], '
        'input[name="csrf-token"]'
    )
    return str(field.get("value", "")).strip() if field else ""


def _porsha_login_page(response) -> bool:
    """Detect a redirect or HTML response that means the session is logged out."""
    final_url = str(getattr(response, "url", "")).lower()
    if re.search(r"/login(?:[/?#]|$)", final_url):
        return True
    text = getattr(response, "text", "") or ""
    low = text.lower()
    return (
        'name="username"' in low
        and 'name="password"' in low
        and ('porsha' in low or "secure access" in low)
    )


def porsha_login(bn, username, password, url=""):
    """Login to Porsha and return its live requests session."""
    s = _session()
    url = _porsha_base_url(url)
    login_url = f"{url}{_PORSHA_LOGIN_PATH}"

    try:
        page = s.get(login_url, timeout=25, allow_redirects=True)
    except Exception as exc:
        raise Exception(f"{bn} · Porsha server unreachable: {exc}")

    if page.status_code in (401, 403):
        raise Exception(f"{bn} · Porsha login page blocked (HTTP {page.status_code})")

    csrf = _porsha_csrf_token(page.text)
    post_data = {"username": username, "password": password}
    if csrf:
        post_data["csrf_token"] = csrf

    try:
        result = s.post(
            login_url,
            data=post_data,
            headers={
                **_BASE_HEADERS,
                "Referer": login_url,
                "Origin": url,
                "Content-Type": "application/x-www-form-urlencoded",
            },
            allow_redirects=True,
            timeout=25,
        )
    except Exception as exc:
        raise Exception(f"{bn} · Porsha login request failed: {exc}")

    low = (result.text or "").lower()
    final_url = str(result.url).lower()
    invalid = any(
        marker in low
        for marker in (
            "invalid credentials",
            "invalid username",
            "incorrect password",
            "login failed",
            "security check failed",
        )
    )
    if result.status_code >= 400 or invalid or _porsha_login_page(result):
        raise Exception(f"{bn} · Porsha login gagal — username/password atau token tidak valid")
    if not any(name in s.cookies for name in ("session", "sessionid", "connect.sid")):
        raise Exception(f"{bn} · Porsha tidak mengembalikan cookie sesi")
    if "/dashboard" not in final_url and "porsha sms - dashboard" not in low:
        raise Exception(f"{bn} · Porsha login gagal — dashboard tidak ditemukan")

    logger.info(f"✅ Porsha login {bn} {username} · session ready")
    return s, "user", url


def _porsha_clean_number(value: str) -> str:
    """Return a phone number from a cell without mistaking a date for one."""
    # A row's first cell can contain both the number and an adjacent
    # ``YYYY-MM-DD`` timestamp.  Split before the timestamp so the regex
    # cannot absorb the date into the phone number.
    fragments = re.split(
        r"\b20\d{2}[-/]\d{1,2}[-/]\d{1,2}"
        r"(?:\s+\d{1,2}:\d{2}(?::\d{2})?)?",
        value or "",
    )
    for fragment in fragments:
        for candidate in re.findall(r"\+?\d[\d\s().-]{5,}\d", fragment):
            digits = re.sub(r"\D", "", candidate)
            if len(digits) >= 7 and not (len(digits) == 8 and digits.startswith("20")):
                return digits
    return ""


def _porsha_parse_messages(text: str) -> list:
    """Normalize Porsha's message-table rows to the common panel row shape."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(text or "", "html.parser")
    nodes = soup.select(".message-table-row")
    if not nodes:
        nodes = soup.select("table tbody tr")
    if not nodes:
        nodes = soup.select("[data-message-id], article.message, .message-card")

    rows = []
    for index, node in enumerate(nodes):
        direct_cells = node.find_all(["td", "th"], recursive=False)
        if not direct_cells:
            direct_cells = node.find_all("div", recursive=False)
        if not direct_cells:
            direct_cells = [node]

        cells = [" ".join(cell.stripped_strings) for cell in direct_cells]
        number_el = node.select_one(
            '[data-number], .number, .phone, .message-number, [class*="number"]'
        )
        strong_el = direct_cells[0].find("strong") if direct_cells else None
        number = _porsha_clean_number(
            str(number_el.get_text(" ", strip=True)) if number_el else
            (strong_el.get_text(" ", strip=True) if strong_el else
             (cells[0] if cells else node.get_text(" ", strip=True)))
        )
        if not number:
            number = _porsha_clean_number(node.get_text(" ", strip=True))
        if not number:
            continue

        message_el = node.select_one(
            ".message-preview, .message-cell, .message, [data-message], "
            "[class*='message']"
        )
        message = (
            message_el.get_text(" ", strip=True)
            if message_el else
            (cells[2] if len(cells) > 2 else "")
        )
        message = _html.unescape(message).strip()
        if not message:
            continue

        first = node.select_one("time, [datetime]")
        if first:
            stamp = first.get("datetime") or first.get_text(" ", strip=True)
        else:
            stamp_el = direct_cells[0].select_one("small, time") if direct_cells else None
            stamp = stamp_el.get_text(" ", strip=True) if stamp_el else (
                cells[0] if cells else ""
            )

        source_el = node.select_one(".source-pill, .source, [data-source]")
        source = (
            source_el.get("data-source") or source_el.get_text(" ", strip=True)
            if source_el else (cells[1] if len(cells) > 1 else "")
        )
        row_id = (
            node.get("data-message-id")
            or node.get("data-id")
            or hashlib.sha1(
                f"{stamp}|{number}|{source}|{message}|{index}".encode()
            ).hexdigest()[:16]
        )
        rows.append([
            _html.unescape(str(stamp)),
            str(row_id),
            number,
            _html.unescape(str(source)),
            None,
            message,
        ])

    logger.info(f"✅ Porsha fetch parser · {len(rows)} rows")
    return rows


def porsha_fetch(bn, session_info, url=""):
    """Read Porsha's server-rendered SMS history from /messages."""
    if not (
        isinstance(session_info, tuple)
        and len(session_info) == 3
        and hasattr(session_info[0], "cookies")
    ):
        return []

    s, _role, session_url = session_info
    base_url = _porsha_base_url(session_url or url)
    try:
        response = s.get(
            f"{base_url}{_PORSHA_MESSAGES_PATH}",
            headers={
                **_BASE_HEADERS,
                "Accept": "text/html,application/xhtml+xml",
                "Referer": f"{base_url}/dashboard",
            },
            timeout=25,
            allow_redirects=True,
        )
    except Exception as exc:
        logger.warning(f"porsha_fetch · network error: {str(exc)[:100]}")
        return []

    if _porsha_login_page(response):
        logger.warning("porsha_fetch · session expired")
        return None
    if response.status_code >= 400:
        logger.warning(f"porsha_fetch · HTTP {response.status_code}")
        return []
    return _porsha_parse_messages(response.text)


def purple_sms_fetch(session_info, url):
    """Fetch Purple SMS reseller reports.

    Purple SMS does not expose its messages on SMSCDRStats.  The actual
    report is the reseller/SMSReports page, and its DataTables request still
    uses the common data_smscdr endpoint.
    """
    import requests as rq

    if not (isinstance(session_info, tuple) and len(session_info) == 3
            and hasattr(session_info[0], "cookies")):
        return []

    s, path, _url = session_info
    url = (_url or url or "").rstrip("/")
    # Login normally lands on reseller; keep the returned path but include
    # reseller as a safe fallback for older Purple SMS accounts.
    paths = list(dict.fromkeys([path, "reseller", "agent", "client"]))
    d1, d2 = _dates()

    def parse_purple_response(text):
        """Normalize Purple's report rows.

        Purple's reseller DataTables schema is:
        date, range, number, sender, currency, period, cost, ..., message.
        The message is column 10, unlike the older INTS schema.
        """
        try:
            payload = json.loads(text)
        except Exception:
            return []
        raw_rows = payload.get("aaData", []) if isinstance(payload, dict) else payload
        if not isinstance(raw_rows, list):
            return []
        normalized = []
        for row in raw_rows:
            if not isinstance(row, (list, tuple)) or len(row) < 3:
                continue
            number = str(row[2] or "").strip().lstrip("+")
            if not number.isdigit() or number == "0":
                continue
            message = ""
            for index in (10, 7, 6, 5):
                if len(row) > index and row[index] not in (None, "", "null"):
                    candidate = str(row[index]).strip()
                    if candidate and candidate not in ("0", "$", "Weekly", "Monthly30"):
                        message = _html.unescape(candidate)
                        break
            normalized.append([
                _html.unescape(str(row[0] or "")),
                _html.unescape(str(row[1] or "")),
                number,
                _html.unescape(str(row[3] or "")) if len(row) > 3 else "",
                _html.unescape(str(row[4] or "")) if len(row) > 4 else "",
                message,
            ])
        return normalized

    for p in paths:
        report_url = f"{url}/{p}/SMSReports"
        try:
            report = s.get(
                report_url,
                headers={**_BASE_HEADERS, "Referer": f"{url}/{p}/SMSDashboard"},
                timeout=20,
                allow_redirects=True,
            )
        except Exception as exc:
            logger.warning(f"Purple SMS · report page error: {str(exc)[:120]}")
            return []

        if _is_session_expired(report):
            return None

        # The report page may provide a session key used by its DataTables
        # request.  It is optional on some deployments.
        keys = re.findall(r"(?:sesskey|session_key|sessionKey)\s*[:=]\s*['\"]?"
                          r"([A-Za-z0-9+/=_-]+)", report.text, re.I)
        sesskeys = list(dict.fromkeys(keys + [""]))
        base_params = {
            "fdate1": d1, "fdate2": d2,
            "frange": "", "fclient": "", "fnum": "", "fcli": "",
            "fgdate": "", "fgmonth": "", "fgrange": "",
            "fgclient": "", "fgnumber": "", "fgcli": "", "fg": "0",
            # Purple SMS uses these names on its reseller report form.
            "ftermination": "", "fgtermination": "0",
            "iDisplayStart": "0", "iDisplayLength": "100", "sEcho": "1",
        }

        for endpoint in (
            f"{url}/{p}/ajax/dt_reports.php",
            f"{url}/{p}/res/data_smscdr.php",
            f"{url}/{p}/res/data_smscdrreports.php",
            f"{url}/{p}/res/data_smsreports.php",
        ):
            for sesskey in sesskeys:
                params = dict(base_params)
                if sesskey:
                    params["sesskey"] = sesskey
                try:
                    response = s.get(
                        endpoint,
                        params=params,
                        headers={**_AJAX_HEADERS, "Referer": report_url},
                        timeout=20,
                        allow_redirects=True,
                    )
                except Exception:
                    continue
                if _is_session_expired(response):
                    return None
                if _classify(response) == "json":
                    rows = (parse_purple_response(response.text)
                            if endpoint.endswith("/ajax/dt_reports.php")
                            else _parse(response.text))
                    if rows:
                        logger.info(f"✅ Purple SMS fetch · {len(rows)} rows")
                        return rows

        # A few old Purple SMS deployments render the table in the page.
        # Reuse the parser when the HTML contains a JSON-like table payload.
        rows = _parse(report.text)
        if rows:
            return rows

    return []


def reseller_fetch(sid, url):
    return panel_fetch(sid, url)


# ══════════════════════════════════════════════════════════════
#  IMS PANEL — NEW LOGIN SYSTEM
#  Human-like delays, multi-attempt login, etkk token refresh
# ══════════════════════════════════════════════════════════════
import time, random
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

def _ims_make_session():
    import requests as rq
    s = rq.Session()
    adapter = HTTPAdapter(max_retries=Retry(total=3, backoff_factor=2))
    s.mount("https://", adapter)
    s.mount("http://", adapter)
    s.headers.update({
        "User-Agent": _UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
    })
    return s

def _ims_human_delay(a=2, b=5):
    t = random.uniform(a, b)
    time.sleep(t)

def _ims_get_etkk(html):
    for pat in [
        r"name=['\"]etkk['\"][^>]+value=['\"]([^'\"]+)['\"]",
        r"value=['\"]([^'\"]+)['\"][^>]+name=['\"]etkk['\"]"
    ]:
        m = re.search(pat, html)
        if m:
            return m.group(1)
    return ""

def _ims_try_login(s, url, email, pw, etkk, capt):
    """Single login attempt with full browser-like headers."""
    import requests as rq
    try:
        r = s.post(
            f"{url}/signin",
            data={"username": email, "password": pw, "capt": capt, "etkk": etkk},
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Origin": url,
                "Referer": f"{url}/login",
                "Sec-Fetch-Site": "same-origin",
                "Sec-Fetch-Mode": "navigate",
                "Sec-Fetch-Dest": "document",
                "Sec-Fetch-User": "?1",
                "Cache-Control": "max-age=0",
                "Upgrade-Insecure-Requests": "1",
            },
            allow_redirects=True,
            timeout=30
        )
        return r
    except rq.exceptions.ConnectionError:
        logger.warning("ImsPanel · connection dropped, retrying in 8s...")
        time.sleep(8)
        return None

def ims_login(email, pw, url):
    s = _ims_make_session()

    # Homepage visit (human-like)
    try:
        s.get(url, timeout=20)
    except Exception:
        pass
    _ims_human_delay(2, 3)

    max_attempts = 5
    for attempt in range(1, max_attempts + 1):
        logger.info(f"ImsPanel · login attempt {attempt}/{max_attempts} — {email}")

        try:
            r = s.get(f"{url}/login", timeout=20, allow_redirects=True)
        except Exception as e:
            raise Exception(f"ImsPanel · server unreachable: {e}")

        etkk = _ims_get_etkk(r.text)
        capt = _solve_captcha(r.text)

        _ims_human_delay(3, 6)

        r2 = _ims_try_login(s, url, email, pw, etkk, capt)

        if r2 is None:
            _ims_human_delay(5, 8)
            continue

        final_url = str(r2.url).lower()

        # ── Success check ──────────────────────────────────
        if not any(x in final_url for x in ["/login", "/signin"]):
            for role in ["reseller", "agent", "admin", "client"]:
                if role in final_url:
                    logger.info(f"✅ ImsPanel · {email} · role: {role}")
                    return s, role, url
            logger.info(f"✅ ImsPanel · {email} · URL: {r2.url}")
            return s, "client", url

        # ── Failed — try with refreshed etkk immediately ──
        new_etkk = _ims_get_etkk(r2.text)
        new_capt = _solve_captcha(r2.text)

        if new_etkk and new_etkk != etkk:
            logger.info("ImsPanel · token changed, retrying immediately...")
            _ims_human_delay(2, 4)
            r3 = _ims_try_login(s, url, email, pw, new_etkk, new_capt)
            if r3 and not any(x in str(r3.url).lower() for x in ["/login", "/signin"]):
                for role in ["reseller", "agent", "admin", "client"]:
                    if role in str(r3.url).lower():
                        logger.info(f"✅ ImsPanel · {email} · role: {role}")
                        return s, role, url
                logger.info(f"✅ ImsPanel · {email} · URL: {r3.url}")
                return s, "client", url

        logger.warning(f"ImsPanel · attempt {attempt} failed. Retrying...")
        _ims_human_delay(5, 10)

    raise Exception(f"ImsPanel · all {max_attempts} login attempts failed for {email}")


def ims_fetch(session_info, url):
    if (isinstance(session_info, tuple) and len(session_info) == 3
            and hasattr(session_info[0], "cookies")):
        s, path, _url = session_info
        url = _url or url
    else:
        s = session_info
        path = "client"

    # Dashboard visit (human-like, keeps session alive)
    try:
        _ims_human_delay(2, 3)
        s.get(f"{url}/{path}/SMSDashboard", timeout=15)
        _ims_human_delay(1, 2)
    except Exception:
        pass

    # Get sesskey from CDR Stats
    sesskey = ""
    try:
        rs = s.get(f"{url}/{path}/SMSCDRStats", timeout=15, allow_redirects=True)
        if _is_session_expired(rs):
            logger.info("ims_fetch · session expired → re-login")
            return None
        m = re.search(r'sesskey=([A-Za-z0-9+/=_-]+)', rs.text)
        if m:
            sesskey = m.group(1)
    except Exception:
        pass

    _ims_human_delay(1, 2)

    from datetime import datetime as _dt2, timedelta as _td2
    today     = _dt2.now().strftime("%Y-%m-%d")
    yesterday = (_dt2.now() - _td2(days=1)).strftime("%Y-%m-%d")

    params = {
        "fdate1": f"{yesterday} 00:00:00",
        "fdate2": f"{today} 23:59:59",
        "frange": "", "fclient": "", "fnum": "", "fcli": "",
        "fgdate": "", "fgmonth": "", "fgrange": "",
        "fgclient": "", "fgnumber": "", "fgcli": "", "fg": "0"
    }
    if sesskey:
        params["sesskey"] = sesskey

    try:
        r = s.get(
            f"{url}/{path}/res/data_smscdr.php",
            params=params,
            headers={
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "X-Requested-With": "XMLHttpRequest",
                "Referer": f"{url}/{path}/SMSCDRStats",
            },
            timeout=20, allow_redirects=True
        )
        if _is_session_expired(r):
            logger.info("ims_fetch · session expired on CDR fetch → re-login")
            return None
        rows = _parse(r.text)
        if rows:
            logger.info(f"✅ ims_fetch · {len(rows)} rows")
        return rows
    except Exception as e:
        logger.warning(f"ims_fetch · fetch error: {e}")
        return []


# ══════════════════════════════════════════════════════════════
#  KONEKTA
#  ✅ BUG-3 FIX: Dashboard URL verification (not just "sign" check)
# ══════════════════════════════════════════════════════════════
def konekta_login(email, pw):
    s = _session()
    try:
        r = s.get("https://konektapremium.net/sign-in", timeout=15, allow_redirects=True)
    except Exception as e:
        raise Exception(f"Konekta · server unreachable: {e}")

    capt = _solve_captcha(r.text)
    r2 = s.post("https://konektapremium.net/signin",
                data={"username": email, "password": pw, "capt": capt},
                headers={**_BASE_HEADERS,
                         "Referer": "https://konektapremium.net/sign-in",
                         "Content-Type": "application/x-www-form-urlencoded"},
                allow_redirects=True, timeout=15)

    # ✅ BUG-3 FIX: Check for dashboard/agent in URL, not just absence of "sign"
    final = str(r2.url).lower()
    success_signals = ["dashboard", "agent", "client", "reseller", "smscdr", "sms"]
    if not any(x in final for x in success_signals):
        raise Exception(f"Konekta · login failed — unexpected URL: {r2.url}")

    # Also verify session cookie
    sid = s.cookies.get("PHPSESSID") or s.cookies.get("session")
    if not sid:
        raise Exception("Konekta · no session cookie after login")

    logger.info(f"✅ Konekta · {email}")
    return s, "agent", "https://konektapremium.net"


def konekta_fetch(session_info):
    if (isinstance(session_info, tuple) and len(session_info) >= 2
            and hasattr(session_info[0], "cookies")):
        s = session_info[0]
        url = "https://konektapremium.net"
        path = session_info[1] if len(session_info) > 1 else "agent"
    else:
        s = session_info
        path = "agent"
        url = "https://konektapremium.net"
    return _core_fetch(s, url, path)


# ══════════════════════════════════════════════════════════════
#  TIMESMS — NEW PANEL
#  Gets sesskey from SMSCDRReports (not SMSCDRStats)
#  ✅ FIX-C: Network errors separated from session expiry
# ══════════════════════════════════════════════════════════════
def timesms_login(bn, email, pw, url="https://www.timesms.org"):
    s = _session()
    try:
        r = s.get(f"{url}/login", timeout=25, allow_redirects=True)
    except Exception as e:
        raise Exception(f"{bn} · server unreachable: {e}")

    low = r.text.lower()
    if r.status_code in (403, 401) or "not in allowlist" in low:
        raise Exception(f"{bn} · IP blocked (HTTP {r.status_code})")

    capt = _solve_captcha(r.text)

    csrf = ""
    for pat in [
        r'name=["\']_token["\'][^>]+value=["\']([^"\']+)["\']',
        r'value=["\']([^"\']+)["\'][^>]+name=["\']_token["\']',
    ]:
        m = re.search(pat, r.text)
        if m:
            csrf = m.group(1)
            break

    post_data = {"username": email, "password": pw, "capt": capt}
    if csrf:
        post_data["_token"] = csrf

    try:
        r2 = s.post(f"{url}/signin", data=post_data,
                    headers={**_BASE_HEADERS,
                             "Referer": f"{url}/login",
                             "Content-Type": "application/x-www-form-urlencoded",
                             "Origin": url},
                    allow_redirects=True, timeout=20)
    except Exception as e:
        raise Exception(f"{bn} · signin POST failed: {e}")

    sid = (s.cookies.get("PHPSESSID") or s.cookies.get("session")
           or s.cookies.get("laravel_session"))
    if not sid:
        raise Exception(f"{bn} · no session cookie after login"
                        " (wrong credentials or rate limit)")

    final_url = str(r2.url).lower()
    if any(x in final_url for x in ["/login", "/signin", "/sign-in"]):
        raise Exception(f"{bn} · login failed — redirected back to login")

    if "client" in str(r2.url):
        path = "client"
    elif "reseller" in str(r2.url):
        path = "reseller"
    else:
        path = "agent"

    logger.info(f"✅ timesms_login {bn} {email} · path:{path}")
    return s, path, url


def timesms_fetch(bn, session_info, url="https://www.timesms.org"):
    """
    TimeSMS-specific fetch.
    ✅ FIX-C: Proper separation of network errors vs session expiry.
    """
    if not (isinstance(session_info, tuple) and len(session_info) == 3
            and hasattr(session_info[0], "cookies")):
        return []

    s, path, _url = session_info
    url = _url or url
    d1, d2 = _dates()

    # TimeSMS: sesskey preferably from SMSCDRReports
    sesskey = ""
    for ep in [
        f"{url}/{path}/SMSCDRReports",
        f"{url}/{path}/SMSCDRStats",
    ]:
        try:
            rs = s.get(ep, timeout=15, allow_redirects=True,
                       headers={**_BASE_HEADERS, "Referer": f"{url}/{path}/SMSDashboard"})
            if _is_session_expired(rs):
                return None  # ✅ FIX-C: session expiry → None
            m = re.search(r'sesskey=([A-Za-z0-9+/=_-]+)', rs.text)
            if m:
                sesskey = m.group(1)
                break
        except Exception as e:
            err = str(e)
            # Network-level failure — return [] not None
            if any(x in err for x in ["NewConnection", "ConnectionError", "Max retries"]):
                logger.warning(f"timesms_fetch {bn} · network error: {err[:80]}")
                return []
            continue

    params = {
        "fdate1": d1, "fdate2": d2,
        "frange": "", "fclient": "", "fnum": "", "fcli": "",
        "fgdate": "", "fgmonth": "", "fgrange": "",
        "fgclient": "", "fgnumber": "", "fgcli": "",
        "fg": "0",
    }
    if sesskey:
        params["sesskey"] = sesskey

    try:
        r = s.get(f"{url}/{path}/res/data_smscdr.php", params=params,
                  headers={**_AJAX_HEADERS,
                           "Referer": f"{url}/{path}/SMSCDRReports"},
                  timeout=20, allow_redirects=True)
        if _is_session_expired(r):
            return None  # ✅ FIX-C: session expiry → None
        if _classify(r) == "json":
            rows = _parse(r.text)
            if rows:
                logger.info(f"✅ timesms_fetch {bn} · {len(rows)} rows")
            else:
                logger.debug(f"timesms_fetch {bn} · 0 rows")
            return rows if rows is not None else []
    except Exception as e:
        err = str(e)
        if any(x in err for x in ["NewConnection", "ConnectionError", "Max retries"]):
            logger.warning(f"timesms_fetch {bn} · network error: {err[:80]}")
            return []
        logger.warning(f"timesms_fetch {bn} error: {err}")

    return []


# ══════════════════════════════════════════════════════════════
#  ROXYSMS
#  ✅ FIX-B: Network error vs session expiry separated
# ══════════════════════════════════════════════════════════════
def _roxysms_login(bn, email, pw, url=""):
    s = _session()
    try:
        r = s.get(f"{url}/Login", timeout=20, allow_redirects=True)
    except Exception as e:
        raise Exception(f"{bn} · server unreachable: {e}")

    if r.status_code in (403, 401):
        raise Exception(f"{bn} · IP blocked (HTTP {r.status_code})")

    capt = _solve_captcha(r.text)
    r2 = s.post(f"{url}/signin",
                data={"username": email, "password": pw,
                      "capt": capt, "g-recaptcha-response": ""},
                headers={**_BASE_HEADERS,
                         "Referer": f"{url}/Login",
                         "Content-Type": "application/x-www-form-urlencoded"},
                allow_redirects=True, timeout=20)
    if not (s.cookies.get("PHPSESSID") or s.cookies.get("session")
            or s.cookies.get("laravel_session")):
        raise Exception(f"{bn} · no session cookie after login"
                        " (wrong credentials or rate limit)")
    _roxy_final = str(r2.url).lower()
    if any(x in _roxy_final for x in ["/login", "/signin", "/sign-in"]):
        raise Exception(f"{bn} · login failed — redirected back to login"
                        " (wrong credentials or rate limit)")
    path = "agent" if "agent" in str(r2.url) else "client"
    logger.info(f"✅ {bn} {email} · path:{path}")
    return s, path, url


def _roxysms_fetch(bn, session_info, url=""):
    """
    ✅ FIX-B: Distinguishes network errors (return []) from session expiry (return None).
    Previously all exceptions returned [] which treated network failures as empty data.
    """
    if not isinstance(session_info, tuple):
        return []
    s, path, url = session_info
    d1, d2 = _dates()

    for p in [path, "agent", "client"]:
        sesskey = ""
        # ✅ KEEPALIVE: SMSCDRReports GET করি sesskey এর জন্য — এটাই keepalive হিসেবে কাজ করে।
        # আলাদা ping লাগবে না কারণ sesskey fetch টা নিজেই session refresh করে।
        try:
            rs = s.get(f"{url}/{p}/SMSCDRReports", timeout=15, allow_redirects=True)
            if _is_session_expired(rs):
                return None  # ✅ FIX-B: session expiry → None
            m = re.search(r'sesskey=([A-Za-z0-9+/=]+)', rs.text)
            if m:
                sesskey = m.group(1)
        except Exception as e:
            err = str(e)
            if any(x in err for x in ["NewConnection", "ConnectionError", "Max retries"]):
                logger.warning(f"_roxysms_fetch {bn} · network error: {err[:80]}")
                return []  # ✅ FIX-B: network error → [] (not session expiry)
            # Other exceptions: ignore and try next path

        params = {"fdate1": d1, "fdate2": d2, "frange": "", "fclient": "",
                  "fnum": "", "fcli": "", "fgdate": "", "fgmonth": "",
                  "fgrange": "", "fgclient": "", "fgnumber": "", "fgcli": "", "fg": "0"}
        if sesskey:
            params["sesskey"] = sesskey

        try:
            r = s.get(f"{url}/{p}/res/data_smscdr.php", params=params,
                      headers={**_AJAX_HEADERS, "Referer": f"{url}/{p}/SMSCDRReports"},
                      timeout=20)
            if _is_session_expired(r):
                return None  # ✅ FIX-B: session expiry → None
            rows = _parse(r.text, mask_only=True)
            if rows:
                return rows
        except Exception as e:
            err = str(e)
            if any(x in err for x in ["NewConnection", "ConnectionError", "Max retries"]):
                logger.warning(f"_roxysms_fetch {bn} · network error: {err[:80]}")
                return []

        try:
            r = s.get(f"{url}/{p}/res/data_testsmscdr.php",
                      params={"fdate1": d1, "fdate2": d2, "fg": "0"},
                      headers={**_AJAX_HEADERS, "Referer": f"{url}/{p}/SMSTestPanel"},
                      timeout=15)
            if _is_session_expired(r):
                return None  # ✅ FIX-B: session expiry → None
            rows = _parse(r.text, mask_only=True)
            if rows:
                return rows
        except Exception as e:
            err = str(e)
            if any(x in err for x in ["NewConnection", "ConnectionError", "Max retries"]):
                logger.warning(f"_roxysms_fetch {bn} · network error: {err[:80]}")
                return []

    return []


# ══════════════════════════════════════════════════════════════
#  VOICEGATE
# ══════════════════════════════════════════════════════════════
def _voicegate_login(bn, email, pw, url=""):
    s = _session()
    try:
        r = s.get(f"{url}/SignIn", timeout=20, allow_redirects=True)
    except Exception as e:
        raise Exception(f"{bn} · server unreachable: {e}")

    if r.status_code in (403, 401):
        raise Exception(f"{bn} · IP blocked (HTTP {r.status_code})")

    capt = _solve_captcha(r.text)
    _vg_data = {"username": email, "password": pw}
    if capt and capt != "0":          # skip if captcha not found
        _vg_data["capt"] = capt
    r2 = s.post(f"{url}/signmein",
                data=_vg_data,
                headers={**_BASE_HEADERS,
                         "Referer": f"{url}/SignIn",
                         "Content-Type": "application/x-www-form-urlencoded"},
                allow_redirects=True, timeout=20)
    if not (s.cookies.get("PHPSESSID") or s.cookies.get("session")
            or s.cookies.get("laravel_session")):
        raise Exception(f"{bn} · no session cookie after login"
                        " (wrong credentials or rate limit)")
    _vg_final = str(r2.url).lower()
    if any(x in _vg_final for x in ["/login", "/signin", "/sign-in"]):
        raise Exception(f"{bn} · login failed — redirected back to login"
                        " (wrong credentials or rate limit)")
    final = str(r2.url)
    path = "reseller" if "reseller" in final else ("agent" if "agent" in final else "client")
    logger.info(f"✅ {bn} {email} · path:{path}")
    return s, path, url


def _voicegate_fetch(bn, session_info, url=""):
    if not isinstance(session_info, tuple):
        return []
    s, path, url = session_info
    d1, d2 = _dates()
    params = {"fdate1": d1, "fdate2": d2, "ftermination": "", "fclient": "",
              "fnum": "", "fcli": "", "fgdate": "0", "fgtermination": "0",
              "fgclient": "0", "fgnumber": "0", "fgcli": "0", "fg": "0"}
    for p in [path, "reseller", "agent", "client"]:
        try:
            r = s.get(f"{url}/{p}/ajax/dt_reports.php", params=params,
                      headers={**_AJAX_HEADERS, "Referer": f"{url}/{p}/Reports"},
                      timeout=15)
            if _is_session_expired(r):
                return None
            rows = _parse(r.text)
            if rows:
                return rows
        except Exception:
            continue
    return []


# ══════════════════════════════════════════════════════════════
#  ZONESMS
#  Zone SMS uses the subclient account area and the Reports table.
#  Kept separate from the existing panel handlers so existing panel
#  behaviour remains unchanged.
# ══════════════════════════════════════════════════════════════
def zonesms_login(bn, email, pw, url="http://zonesms.net"):
    s = _session()
    url = (url or "http://zonesms.net").rstrip("/")
    login_path = "/SignIn"

    try:
        r = s.get(f"{url}{login_path}", timeout=20, allow_redirects=True)
    except Exception as e:
        raise Exception(f"{bn} · server unreachable: {e}")

    if r.status_code in (401, 403):
        raise Exception(f"{bn} · IP blocked (HTTP {r.status_code})")

    capt = _solve_captcha(r.text)
    post_data = {
        "username": email,
        "password": pw,
        "capt": capt,
        "g-recaptcha-response": "",
    }
    csrf = re.search(
        r'name=["\']_token["\'][^>]+value=["\']([^"\']+)["\']',
        r.text,
    )
    if csrf:
        post_data["_token"] = csrf.group(1)

    try:
        r2 = s.post(
            f"{url}/signmein",
            data=post_data,
            headers={
                **_BASE_HEADERS,
                "Referer": f"{url}{login_path}",
                "Content-Type": "application/x-www-form-urlencoded",
                "Origin": url,
            },
            allow_redirects=True,
            timeout=20,
        )
    except Exception as e:
        raise Exception(f"{bn} · signin failed: {e}")

    sid = (
        s.cookies.get("PHPSESSID")
        or s.cookies.get("session")
        or s.cookies.get("laravel_session")
    )
    if not sid:
        raise Exception(f"{bn} · no session cookie after login (wrong credentials?)")

    final_url = str(r2.url).lower()
    if any(x in final_url for x in ("/signin", "/sign-in", "/login")):
        raise Exception(f"{bn} · login failed — redirected back to login")

    logger.info(f"✅ zonesms_login {bn} {email} · path:subclient")
    return s, "subclient", url


def zonesms_fetch(bn, session_info, url="http://zonesms.net"):
    """Read Zone SMS history from /subclient/Reports."""
    if not (
        isinstance(session_info, tuple)
        and len(session_info) == 3
        and hasattr(session_info[0], "cookies")
    ):
        return []

    s, path, session_url = session_info
    url = (session_url or url).rstrip("/")
    d1, d2 = _dates()
    params = {
        "fdate1": d1,
        "fdate2": d2,
        "ftermination": "",
        "fclient": "",
        "fnum": "",
        "fcli": "",
        "fgdate": "0",
        "fgtermination": "0",
        "fgclient": "0",
        "fgnumber": "0",
        "fgcli": "0",
        "fg": "0",
    }

    try:
        # Visit the exact page supplied by the panel owner first. This also
        # keeps the authenticated session warm and exposes the table token.
        report_url = f"{url}/{path}/Reports"
        report = s.get(
            report_url,
            headers={**_BASE_HEADERS, "Referer": f"{url}/subclient/"},
            timeout=20,
            allow_redirects=True,
        )
        if _is_session_expired(report):
            return None

        r = s.get(
            f"{url}/{path}/ajax/dt_reports.php",
            params=params,
            headers={**_AJAX_HEADERS, "Referer": report_url},
            timeout=20,
            allow_redirects=True,
        )
        if _is_session_expired(r):
            return None
        if _classify(r) != "json":
            logger.warning(f"{bn} · Zone SMS Reports returned non-JSON response")
            return []
        rows = _parse(r.text)
        logger.info(f"✅ zonesms_fetch {bn} · {len(rows)} rows")
        return rows
    except Exception as e:
        err = str(e)
        if any(x in err for x in ("NewConnection", "ConnectionError", "Max retries")):
            logger.warning(f"{bn} · Zone SMS network error: {err[:100]}")
        else:
            logger.warning(f"{bn} · Zone SMS fetch error: {err}")
        return []


# ══════════════════════════════════════════════════════════════
#  ZED SMS — ZEDSMS web application API
# ══════════════════════════════════════════════════════════════
def _zedsms_api_url(url=""):
    """Turn the public ZEDSMS URL into its API base URL.

    ZEDSMS serves its UI from zedsms.com, while authentication and the
    inbox are served by control.zedsms.com/api.
    """
    value = (url or "").rstrip("/")
    if not value or "zedsms.com" in value.lower() and "control." not in value.lower():
        return "https://control.zedsms.com/api"
    return value


def _zedsms_rows(payload):
    """Normalize ZEDSMS /user/all-sms records to the bot row format."""
    if isinstance(payload, dict):
        data = payload.get("data", payload.get("results", []))
        if isinstance(data, dict):
            data = data.get("data", data.get("results", []))
    else:
        data = payload
    if not isinstance(data, list):
        return []

    rows = []
    for index, item in enumerate(data):
        if not isinstance(item, dict):
            continue
        number = ""
        for key in ("number", "phone_number", "phone", "msisdn", "mobile"):
            if item.get(key) not in (None, ""):
                number = str(item[key]).strip().lstrip("+")
                break
        number = re.sub(r"\D", "", number)
        if not number:
            continue

        message = ""
        for key in ("message", "sms", "text", "content", "body"):
            if item.get(key) not in (None, ""):
                message = str(item[key]).strip()
                break
        service = ""
        for key in ("service", "sender", "from", "cli", "app_name"):
            if item.get(key) not in (None, ""):
                service = str(item[key]).strip()
                break
        timestamp = ""
        for key in ("created_at", "received_at", "date", "time", "timestamp"):
            if item.get(key) not in (None, ""):
                timestamp = str(item[key]).strip()
                break
        row_id = str(item.get("id", item.get("message_id", index))).strip()
        rows.append([timestamp, row_id, number, service, None,
                     _html.unescape(message)])
    return rows


def zedsms_login(bn, email, pw, url="https://zedsms.com"):
    """Login to the ZED SMS Laravel panel, including its math captcha."""
    s = _session()
    url = (url or "http://194.233.79.217").rstrip("/")
    try:
        page = s.get(f"{url}/login", timeout=25, allow_redirects=True)
    except Exception as exc:
        raise Exception(f"{bn} · server unreachable: {exc}")
    if page.status_code in (401, 403):
        raise Exception(f"{bn} · IP blocked (HTTP {page.status_code})")

    csrf = re.search(
        r'name=["\']_token["\'][^>]+value=["\']([^"\']+)["\']',
        page.text, re.I,
    )
    captcha = _solve_captcha(page.text)
    if not captcha:
        raise Exception(f"{bn} · captcha ZED SMS tidak ditemukan")
    post_data = {
        "username": email,
        "password": pw,
        "captcha_answer": captcha,
    }
    if csrf:
        post_data["_token"] = csrf.group(1)
    try:
        response = s.post(
            f"{url}/login",
            data=post_data,
            headers={
                **_BASE_HEADERS,
                "Referer": f"{url}/login",
                "Content-Type": "application/x-www-form-urlencoded",
                "Origin": url,
            },
            timeout=25,
            allow_redirects=True,
        )
    except Exception as exc:
        raise Exception(f"{bn} · login request failed: {exc}")

    final_url = str(response.url).lower()
    if "/login" in final_url or "invalid" in response.text.lower():
        raise Exception(f"{bn} · login gagal — username/password atau captcha tidak valid")
    path = "client" if "/client/" in final_url else "agent"
    logger.info(f"✅ zedsms_login {bn} {email} · path:{path}")
    return s, path, url


def zedsms_fetch(bn, session_info, url="https://zedsms.com"):
    """Read ZED SMS CDR rows from the agent/client DataTables endpoint."""
    if not (isinstance(session_info, tuple) and len(session_info) == 3
            and hasattr(session_info[0], "cookies")):
        return []
    s, path, session_url = session_info
    panel_url = (session_url or url).rstrip("/")
    d1, d2 = _dates()
    params = {
        "draw": "1",
        "start": "0",
        "length": "100",
        "fdate1": d1,
        "fdate2": d2,
        "frange": "",
        "fclient": "",
        "fnum": "",
        "fcli": "",
    }
    try:
        response = s.get(
            f"{panel_url}/{path}/sms-cdr-reports",
            params=params,
            headers={
                **_AJAX_HEADERS,
                "Referer": f"{panel_url}/{path}/sms-cdr-reports",
            },
            timeout=25,
            allow_redirects=True,
        )
        if _is_session_expired(response):
            return None
        if _classify(response) != "json":
            logger.warning(f"{bn} · ZED SMS CDR returned non-JSON response")
            return []
        payload = response.json()
        records = payload.get("data", []) if isinstance(payload, dict) else []
        rows = []
        for index, item in enumerate(records):
            if not isinstance(item, dict):
                continue
            number = re.sub(r"\D", "", str(item.get("destination", "")))
            # Zed SMS may return an international dialling prefix (0077)
            # in front of an African destination. It is not part of the
            # destination shown by the panel; remove it before matching,
            # country detection, logging, and forwarding.
            if number.startswith("0077"):
                number = number[4:]
            if not number:
                continue
            rows.append([
                str(item.get("date", "")),
                str(item.get("id", index)),
                number,
                str(item.get("sender", "")),
                str(item.get("client", "")),
                re.sub(
                    r"<[^>]+>", "",
                    _html.unescape(str(item.get("message", ""))),
                ).strip(),
            ])
        logger.info(f"✅ zedsms_fetch {bn} · {len(rows)} rows")
        return rows
    except Exception as exc:
        logger.warning(f"{bn} · ZEDSMS fetch error: {exc}")
        return []


# ══════════════════════════════════════════════════════════════
#  NUMBERPANEL
# ══════════════════════════════════════════════════════════════
def _numberpanel_login(bn, email, pw, url=""):
    """Working login — exact logic from confirmed working standalone bot."""
    s = _session()
    try:
        r = s.get(f"{url}/login", timeout=15, allow_redirects=True)
    except Exception as e:
        raise Exception(f"{bn} · server unreachable: {e}")

    # Captcha: "What is X + Y"
    mc = re.search(r'What is (\d+)\s*\+\s*(\d+)', r.text, re.I)
    capt = int(mc.group(1)) + int(mc.group(2)) if mc else 0

    r2 = s.post(f"{url}/signin",
                data={"username": email, "password": pw, "capt": capt},
                headers={**_BASE_HEADERS,
                         "Referer": f"{url}/login",
                         "Content-Type": "application/x-www-form-urlencoded"},
                allow_redirects=True, timeout=15)

    if not s.cookies.get("PHPSESSID"):
        raise Exception(f"{bn} · login failed — no PHPSESSID (wrong credentials?)")

    path = "agent" if "agent" in str(r2.url) else "client"
    logger.info(f"✅ {bn} {email} · path:{path}")
    return s, path, url


def _numberpanel_fetch(bn, session_info, url=""):
    """Working fetch — exact logic from confirmed working standalone bot."""
    if not isinstance(session_info, tuple):
        return []
    s, path, url = session_info
    d1, d2 = _dates()

    # Get sesskey from SMSCDRStats
    sesskey = ""
    try:
        rs = s.get(f"{url}/{path}/SMSCDRStats",
                   headers={**_BASE_HEADERS, "Referer": f"{url}/{path}/SMSDashboard"},
                   timeout=15, allow_redirects=True)
        if _is_session_expired(rs):
            return None
        sk = re.search(r'sesskey=([A-Za-z0-9+/=]+)', rs.text)
        if sk:
            sesskey = sk.group(1)
    except Exception:
        pass

    params = {"fdate1": d1, "fdate2": d2, "fg": "0"}
    if sesskey:
        params["sesskey"] = sesskey

    try:
        r = s.get(f"{url}/{path}/res/data_smscdr.php",
                  params=params,
                  headers={**_AJAX_HEADERS,
                           "Referer": f"{url}/{path}/SMSCDRStats"},
                  timeout=15, allow_redirects=True)
        if _is_session_expired(r):
            return None
        t = r.text.strip()
        if not t or t.startswith("<"):
            return []
        rows = _parse(t)
        return rows
    except Exception as e:
        err = str(e)
        if any(x in err for x in ["NewConnection", "ConnectionError", "Max retries"]):
            return []
        return []


# ══════════════════════════════════════════════════════════════
#  PROOFSMS — ✅ BUG-10 FIX: Now properly exported (was dead code)
# ══════════════════════════════════════════════════════════════
def proofsms_fetch(session_info, url=""):
    """ProofSMS-specific fetch using sesskey from SMSCDRStats."""
    if not isinstance(session_info, tuple):
        return []
    s, path, _url = session_info
    url = _url or url
    d1, d2 = _dates()

    for p in ["agent", "client"]:
        sesskey = ""
        try:
            rs = s.get(f"{url}/{p}/SMSCDRStats", timeout=15, allow_redirects=True)
            if _is_session_expired(rs):
                return None
            m = re.search(r'sesskey=([A-Za-z0-9+/=_-]+)', rs.text)
            if m:
                sesskey = m.group(1)
        except Exception:
            pass

        if sesskey:
            try:
                params = {"fdate1": d1, "fdate2": d2, "fg": "0", "sesskey": sesskey}
                r = s.get(f"{url}/{p}/res/data_smscdr.php", params=params,
                          headers={**_AJAX_HEADERS,
                                   "Referer": f"{url}/{p}/SMSCDRStats"},
                          timeout=20, allow_redirects=True)
                if _is_session_expired(r):
                    return None
                rows = _parse(r.text)
                if rows:
                    return rows
            except Exception:
                pass

        # Fallback: test endpoint
        try:
            r = s.get(f"{url}/{p}/res/data_testsmscdr.php",
                      params={"fdate1": d1, "fdate2": d2, "fg": "0"},
                      headers={**_AJAX_HEADERS,
                               "Referer": f"{url}/{p}/SMSTestPanel"},
                      timeout=15, allow_redirects=True)
            if _is_session_expired(r):
                return None
            rows = _parse(r.text)
            if rows:
                return rows
        except Exception:
            pass

    return []


# Backward compat alias
_proofsms_fetch = proofsms_fetch



# ══════════════════════════════════════════════════════════════
#  SNIPER PANEL  (http://135.125.222.224/ints)
#  Fixed path=agent, SMSCDRReports Referer
# ══════════════════════════════════════════════════════════════
def _sniper_login(bn, email, pw, url=""):
    s = _session()
    try:
        r = s.get(f"{url}/login", timeout=15, allow_redirects=True)
    except Exception as e:
        raise Exception(f"{bn} · server unreachable: {e}")

    if r.status_code in (403, 401):
        raise Exception(f"{bn} · IP blocked (HTTP {r.status_code})")

    capt = _solve_captcha(r.text)

    csrf = ""
    for pat in [
        r'name=["\']_token["\'][^>]+value=["\']([^"\']+)["\']',
        r'value=["\']([^"\']+)["\'][^>]+name=["\']_token["\']',
    ]:
        m = re.search(pat, r.text)
        if m: csrf = m.group(1); break

    post_data = {"username": email, "password": pw, "capt": capt}
    if csrf: post_data["_token"] = csrf

    r2 = s.post(f"{url}/signin",
                data=post_data,
                headers={**_BASE_HEADERS,
                         "Referer": f"{url}/login",
                         "Content-Type": "application/x-www-form-urlencoded"},
                allow_redirects=True, timeout=15)

    if not s.cookies.get("PHPSESSID"):
        raise Exception(f"{bn} · no PHPSESSID cookie (wrong credentials?)")

    final_url = str(r2.url).lower()
    if any(x in final_url for x in ["/login", "/signin", "/sign-in"]):
        raise Exception(f"{bn} · login failed — redirected back to login")

    # Sniper always uses agent path
    path = "agent"
    logger.info(f"✅ {bn} {email} · path:{path}")
    return s, path, url


def _sniper_fetch(bn, session_info, url=""):
    if not isinstance(session_info, tuple):
        return []
    s, path, url = session_info
    d1, d2 = _dates()

    # Try main CDR endpoint with SMSCDRReports referer (sniper specific)
    for ep in [
        f"{url}/{path}/res/data_smscdr.php",
        f"{url}/{path}/res/data_smscdrreports.php",
    ]:
        sesskey = ""
        try:
            rs = s.get(f"{url}/{path}/SMSCDRReports",
                       headers={**_BASE_HEADERS, "Referer": f"{url}/{path}/SMSDashboard"},
                       timeout=15, allow_redirects=True)
            if _is_session_expired(rs):
                return None
            m = re.search(r'sesskey=([A-Za-z0-9+/=_-]+)', rs.text)
            if m: sesskey = m.group(1)
        except Exception:
            pass

        params = {
            "fdate1": d1, "fdate2": d2,
            "frange": "", "fclient": "", "fnum": "", "fcli": "",
            "fgdate": "", "fgmonth": "", "fgrange": "",
            "fgclient": "", "fgnumber": "", "fgcli": "",
            "fg": "0",
        }
        if sesskey:
            params["sesskey"] = sesskey

        try:
            r = s.get(ep, params=params,
                      headers={**_AJAX_HEADERS,
                               "Referer": f"{url}/{path}/SMSCDRReports"},
                      timeout=15, allow_redirects=True)
            if _is_session_expired(r):
                return None
            if _classify(r) == "json":
                rows = _parse(r.text)
                if rows:
                    return rows
        except Exception as e:
            err = str(e)
            if any(x in err for x in ["NewConnection", "ConnectionError", "Max retries"]):
                return []
            continue

    return []

# ══════════════════════════════════════════════════════════════
#  DISPATCH — new_panel_login / new_panel_fetch
#  ✅ FIX-E: ProofSMS now uses proofsms_fetch instead of ints_fetch
#  (handled in api_server_v2.py _get_fetch_fns, kept here for compat)
# ══════════════════════════════════════════════════════════════
def new_panel_login(bn, email, pw, url=""):
    if bn == "XMS":
        return xms_login(bn, email, pw, url)
    elif bn == "RoxySMS":
        return _roxysms_login(bn, email, pw, url)
    elif bn == "VoiceGate":
        return _voicegate_login(bn, email, pw, url)
    elif bn == "NumberPanel":
        return _numberpanel_login(bn, email, pw, url)
    elif bn == "SniperPanel":
        return _sniper_login(bn, email, pw, url)
    else:
        return ints_login(bn, email, pw, url)


def new_panel_fetch(bn, session_info, url=""):
    if bn == "XMS":
        return xms_fetch(bn, session_info, url)
    elif bn == "RoxySMS":
        return _roxysms_fetch(bn, session_info, url)
    elif bn == "VoiceGate":
        return _voicegate_fetch(bn, session_info, url)
    elif bn == "NumberPanel":
        return _numberpanel_fetch(bn, session_info, url)
    elif bn == "SniperPanel":
        return _sniper_fetch(bn, session_info, url)
    elif bn == "ProofSMS":
        return proofsms_fetch(session_info, url)
    else:
        return ints_fetch(bn, session_info, url)
