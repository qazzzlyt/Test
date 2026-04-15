"""
myapp.py — Single file for PyInstaller

Build command:
    pyinstaller myapp.py --onefile --noupx --name myapp --clean

Release a new version:
    git tag v1.2.3 && git push origin v1.2.3
    (GitHub Actions will build and upload to Releases automatically)
"""

# Version number: replaced by CI at build time, keep as dev for local development
__version__ = "v0.0.3-dev"

# ════════════════════════════════════════════════════════════════════════════════
# Auto-updater (embedded, completely invisible to users)
# ════════════════════════════════════════════════════════════════════════════════
import hashlib, json, os, platform, shutil, subprocess, sys
import tempfile, threading, time
from pathlib import Path
from urllib.request import Request, urlopen

GITHUB_OWNER = "qazzzlyt"
GITHUB_REPO  = "Test"
_APP_NAME    = "myapp"


def _update_dir() -> Path:
    d = Path(tempfile.gettempdir()) / f"{_APP_NAME}-update"
    d.mkdir(parents=True, exist_ok=True)
    return d

def _pending_path() -> Path:
    return _update_dir() / "pending.json"

def _current_exe() -> Path:
    return Path(sys.executable).resolve()

def _asset_name() -> str:
    return "myapp.exe"

def _parse_ver(tag: str):
    try:
        return tuple(int(x) for x in tag.lstrip("v").split("."))
    except ValueError:
        return (0,)

def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()

def _apply_pending_update():
    """Called at startup. If a downloaded update exists, replace self and restart. Otherwise return immediately."""
    p = _pending_path()
    if not p.exists():
        return
    try:
        info    = json.loads(p.read_text(encoding="utf-8"))
        new_exe = Path(info["file_path"])
        cksum   = info["checksum"]
    except Exception:
        p.unlink(missing_ok=True)
        return

    if not new_exe.exists() or _sha256(new_exe) != cksum:
        p.unlink(missing_ok=True)
        new_exe.unlink(missing_ok=True)
        return

    cur    = _current_exe()
    backup = Path(str(cur) + ".old")
    backup.unlink(missing_ok=True)

    try:
        cur.rename(backup)          # Windows allows renaming a running EXE
    except OSError:
        return

    try:
        shutil.copy2(str(new_exe), str(cur))
        if platform.system() != "Windows":
            cur.chmod(0o755)
    except OSError:
        backup.rename(cur)          # rollback on failure
        return

    p.unlink(missing_ok=True)
    new_exe.unlink(missing_ok=True)

    args = [str(cur)] + sys.argv[1:]
    try:
        if platform.system() == "Windows":
            subprocess.Popen(args, creationflags=0x00000008 | 0x00000200, close_fds=True)
        else:
            subprocess.Popen(args, start_new_session=True, close_fds=True)
    except OSError:
        backup.rename(cur)          # rollback if launch fails
        return

    os._exit(0)                     # exit old process, new process takes over

def _cleanup_old_backup():
    """Remove the .old backup left by the previous update."""
    Path(str(_current_exe()) + ".old").unlink(missing_ok=True)

def _check_and_download():
    """Background thread: wait 5 seconds, check GitHub, silently download if newer version exists."""
    time.sleep(5)
    try:
        url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"
        req = Request(url, headers={"Accept": "application/vnd.github.v3+json",
                                    "User-Agent": f"{_APP_NAME}-updater"})
        with urlopen(req, timeout=30) as r:
            release = json.loads(r.read())
    except Exception:
        return

    if _parse_ver(release.get("tag_name","")) <= _parse_ver(__version__):
        return

    dl_url = next(
        (a["browser_download_url"] for a in release.get("assets", [])
         if a["name"] == _asset_name()),
        None,
    )
    if not dl_url:
        return

    dest = _update_dir() / _asset_name()
    h = hashlib.sha256()
    try:
        req2 = Request(dl_url, headers={"User-Agent": f"{_APP_NAME}-updater"})
        with urlopen(req2, timeout=900) as r, open(dest, "wb") as f:
            while chunk := r.read(65536):
                f.write(chunk)
                h.update(chunk)
    except Exception:
        dest.unlink(missing_ok=True)
        return

    _pending_path().write_text(
        json.dumps({"version": release["tag_name"],
                    "file_path": str(dest),
                    "checksum": h.hexdigest()}, indent=2),
        encoding="utf-8",
    )


# ════════════════════════════════════════════════════════════════════════════════
# Entry point
# ════════════════════════════════════════════════════════════════════════════════

def main():
    _apply_pending_update()   # apply pending update if available, restart silently
    _cleanup_old_backup()     # remove .old backup from previous update
    threading.Thread(target=_check_and_download, daemon=True).start()  # check for updates in background

    run_app()


def run_app():
    """Replace this with your actual application code."""
    print(f"MyApp {__version__} running...")
    for i in range(60):
        time.sleep(1)
        print(f"tick {i+1}")


if __name__ == "__main__":
    main()