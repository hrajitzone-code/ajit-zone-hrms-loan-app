import os
import time
import json
import urllib.request
import urllib.error

LOCAL_TMP_DB = "/tmp/loan_system.db"
BLOB_PUT_URL = "https://blob.vercel-storage.com/database/loan_system.db"
BLOB_LIST_URL = "https://blob.vercel-storage.com?prefix=database/loan_system.db"

_cached_download_url = None
_cached_uploaded_at = None
_last_check_time = 0.0

def is_vercel():
    return os.environ.get('VERCEL') == '1' or os.environ.get('VERCEL_ENV') is not None

def get_token():
    return os.environ.get('BLOB_READ_WRITE_TOKEN')

def sync_from_blob(force=False):
    """
    Ensures /tmp/loan_system.db is up to date with the latest Vercel Blob database.
    Checks blob metadata and downloads if a newer database exists in the cloud.
    """
    global _cached_download_url, _cached_uploaded_at, _last_check_time

    if not is_vercel():
        return False

    token = get_token()
    if not token:
        return False

    now = time.time()
    # Check at most once every 1.5 seconds per container unless forced
    if not force and os.path.exists(LOCAL_TMP_DB) and (now - _last_check_time < 1.5):
        return True

    _last_check_time = now

    try:
        # 1. Fetch current blob info with cache-busting
        list_url = f"{BLOB_LIST_URL}&_cb={int(now * 1000)}"
        req = urllib.request.Request(list_url, headers={
            'Authorization': f'Bearer {token}',
            'Cache-Control': 'no-cache, no-store, must-revalidate',
            'Pragma': 'no-cache'
        })
        with urllib.request.urlopen(req, timeout=4.0) as resp:
            data = json.loads(resp.read().decode('utf-8'))

        blobs = data.get('blobs', [])
        if not blobs:
            # No remote DB yet; if local bundled DB exists, upload it as initial seed
            bundled_db = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'instance', 'loan_system.db')
            if os.path.exists(bundled_db):
                print("[BLOB SYNC] Initializing remote blob database from local seed...", flush=True)
                sync_to_blob(source_path=bundled_db)
            return True

        blob_info = blobs[0]
        remote_url = blob_info.get('url')
        remote_uploaded_at = blob_info.get('uploadedAt')
        remote_size = blob_info.get('size', 0)
        _cached_download_url = remote_url

        # Check if local DB is missing, remote has a newer version, or remote size differs
        needs_download = False
        if not os.path.exists(LOCAL_TMP_DB) or os.path.getsize(LOCAL_TMP_DB) == 0:
            needs_download = True
        elif _cached_uploaded_at != remote_uploaded_at or (remote_size > 0 and os.path.getsize(LOCAL_TMP_DB) != remote_size):
            needs_download = True

        if needs_download and remote_url:
            print(f"[BLOB SYNC] Downloading updated database from {remote_url} (Version: {remote_uploaded_at}, Size: {remote_size})...", flush=True)
            cache_bust_url = f"{remote_url}{'&' if '?' in remote_url else '?'}t={int(now * 1000)}"
            down_req = urllib.request.Request(cache_bust_url, headers={
                'Authorization': f'Bearer {token}',
                'Cache-Control': 'no-cache, no-store, must-revalidate',
                'Pragma': 'no-cache'
            })
            with urllib.request.urlopen(down_req, timeout=8.0) as down_resp:
                content = down_resp.read()

            # Close and dispose active SQLAlchemy connections before replacing database file
            try:
                from models import db
                db.session.remove()
                db.engine.dispose()
            except Exception:
                pass

            os.makedirs(os.path.dirname(LOCAL_TMP_DB), exist_ok=True)
            # Write atomically using a temporary file
            tmp_write_file = LOCAL_TMP_DB + ".download"
            with open(tmp_write_file, 'wb') as f:
                f.write(content)
            try:
                os.chmod(tmp_write_file, 0o666)
            except Exception:
                pass
            os.replace(tmp_write_file, LOCAL_TMP_DB)
            try:
                os.chmod(LOCAL_TMP_DB, 0o666)
            except Exception:
                pass

            # Dispose engine after file replacement so new queries open clean handles
            try:
                from models import db
                db.engine.dispose()
            except Exception:
                pass

            _cached_uploaded_at = remote_uploaded_at
            print(f"[BLOB SYNC] Successfully synced database ({len(content)} bytes) to {LOCAL_TMP_DB}", flush=True)

        return True

    except Exception as e:
        print(f"[BLOB SYNC ERROR] Failed to sync from blob: {e}", flush=True)
        return False

def sync_to_blob(source_path=None):
    """
    Uploads the local database to Vercel Blob storage so all containers and sessions share the state.
    """
    global _cached_download_url, _cached_uploaded_at

    token = get_token()
    if not token:
        return False

    db_file = source_path or LOCAL_TMP_DB
    if not os.path.exists(db_file) or os.path.getsize(db_file) == 0:
        return False

    try:
        with open(db_file, 'rb') as f:
            data = f.read()

        req = urllib.request.Request(BLOB_PUT_URL, data=data, headers={
            'Authorization': f'Bearer {token}',
            'x-add-random-suffix': 'false',
            'x-vercel-blob-access': 'private',
            'Content-Type': 'application/x-sqlite3'
        }, method='PUT')

        with urllib.request.urlopen(req, timeout=8.0) as resp:
            result = json.loads(resp.read().decode('utf-8'))
            _cached_download_url = result.get('url')
            _cached_uploaded_at = result.get('uploadedAt')
            _last_check_time = time.time()
            print(f"[BLOB SYNC] Successfully uploaded database to blob storage ({len(data)} bytes, version {_cached_uploaded_at})", flush=True)
            return True

    except Exception as e:
        print(f"[BLOB SYNC ERROR] Failed to upload database to blob: {e}", flush=True)
        return False
