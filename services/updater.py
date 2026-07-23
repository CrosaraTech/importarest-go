"""Auto-update: consulta GitHub Releases, baixa zip, dispara updater.bat."""
import json
import os
import ssl
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

from config import __version__, GITHUB_REPO, INSTALL_DIR

try:
    import certifi
    _SSL_CTX = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    _SSL_CTX = ssl.create_default_context()

GITHUB_API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
_UA = f"ImportaREST/{__version__}"

# Marker de update pendente — baixado numa sessao, aplicado na proxima.
_appdata = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~/.cache")
UPDATE_MARKER = Path(_appdata) / "ImportaREST" / "update_pending.json"


def _parse_version(v: str):
    v = (v or "").strip().lstrip("vV")
    out = []
    for p in v.split("."):
        try:
            out.append(int(p))
        except ValueError:
            break
    return tuple(out)


def _versao_atual():
    return __version__


def check_latest_release(timeout: int = 8):
    """Retorna (tag, download_url) do release mais recente. (None, None) em falha."""
    try:
        req = urllib.request.Request(
            GITHUB_API_URL,
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": _UA,
            },
        )
        with urllib.request.urlopen(req, timeout=timeout, context=_SSL_CTX) as r:
            data = json.loads(r.read().decode("utf-8"))
    except Exception:
        return None, None

    tag = data.get("tag_name", "") or ""
    url = ""
    for asset in data.get("assets", []) or []:
        name = (asset.get("name") or "").lower()
        if name.endswith(".zip") and "windows" in name:
            url = asset.get("browser_download_url", "") or ""
            break
    return (tag or None), (url or None)


def is_newer(latest_tag: str, current: str = None) -> bool:
    lat = _parse_version(latest_tag or "")
    cur = _parse_version(current or _versao_atual())
    return bool(lat) and bool(cur) and lat > cur


def download_zip(url: str, dest: Path, timeout: int = 120,
                 progress_cb=None) -> bool:
    """Baixa URL para dest. Retorna True em sucesso."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": _UA})
        with urllib.request.urlopen(req, timeout=timeout, context=_SSL_CTX) as r, open(dest, "wb") as f:
            total = int(r.headers.get("Content-Length", "0") or 0)
            baixado = 0
            while True:
                chunk = r.read(65536)
                if not chunk:
                    break
                f.write(chunk)
                baixado += len(chunk)
                if progress_cb and total:
                    try:
                        progress_cb(baixado, total)
                    except Exception:
                        pass
        return True
    except Exception:
        return False


def _bat_template(zip_path: Path, install_dir: str, pid: int) -> str:
    # Batch em cp850 (default Windows). Sem acentos.
    return f"""@echo off
setlocal
set INSTALL={install_dir}
set ZIP={zip_path}
set PIDMATA={pid}

REM Espera processo pai morrer (max 15s)
set /a WAIT=0
:wait_loop
tasklist /FI "PID eq %PIDMATA%" 2>NUL | find "%PIDMATA%" >NUL
if not errorlevel 1 (
    if %WAIT% lss 30 (
        timeout /t 1 /nobreak >nul
        set /a WAIT+=1
        goto wait_loop
    )
)

REM Backup pasta atual para rollback
if exist "%INSTALL%_bak" rmdir /s /q "%INSTALL%_bak"
if exist "%INSTALL%" (
    move "%INSTALL%" "%INSTALL%_bak" >nul 2>&1
)

REM Cria destino e extrai zip
mkdir "%INSTALL%" 2>nul
powershell -NoProfile -Command "try {{ Expand-Archive -Path '%ZIP%' -DestinationPath '%INSTALL%' -Force; exit 0 }} catch {{ exit 1 }}"

if errorlevel 1 (
    rmdir /s /q "%INSTALL%" 2>nul
    if exist "%INSTALL%_bak" move "%INSTALL%_bak" "%INSTALL%" >nul
    echo Falha ao aplicar atualizacao. Backup restaurado.
    pause
    exit /b 1
)

REM Zip pode extrair como C:\\ImportaREST\\ImportaREST\\ (subpasta). Achatar.
if exist "%INSTALL%\\ImportaREST\\ImportaREST.exe" (
    powershell -NoProfile -Command "Get-ChildItem -Path '%INSTALL%\\ImportaREST' -Force | Move-Item -Destination '%INSTALL%' -Force"
    rmdir /s /q "%INSTALL%\\ImportaREST" 2>nul
)

REM Preserva .env do backup (zip nao contem credenciais)
if exist "%INSTALL%_bak\\.env" (
    copy /Y "%INSTALL%_bak\\.env" "%INSTALL%\\.env" >nul
)

REM Cria atalho desktop se nao existir
set SHORTCUT=%USERPROFILE%\\Desktop\\ImportaREST.lnk
if not exist "%SHORTCUT%" (
    powershell -NoProfile -Command "$s=(New-Object -COM WScript.Shell).CreateShortcut('%SHORTCUT%'); $s.TargetPath='%INSTALL%\\ImportaREST.exe'; $s.IconLocation='%INSTALL%\\ImportaREST.exe'; $s.WorkingDirectory='%INSTALL%'; $s.Save()"
)

REM Limpa backup, remove zip
if exist "%INSTALL%_bak" rmdir /s /q "%INSTALL%_bak"
del "%ZIP%" 2>nul

REM Reinicia programa
start "" "%INSTALL%\\ImportaREST.exe"

REM Auto-delete .bat
(goto) 2>nul & del "%~f0"
"""


def apply_update(zip_path: Path, install_dir: str = None) -> None:
    """Escreve updater.bat, dispara em background e mata o processo atual."""
    install_dir = install_dir or INSTALL_DIR
    bat_path = Path(tempfile.gettempdir()) / "importarest_updater.bat"
    bat_path.write_text(
        _bat_template(zip_path, install_dir, os.getpid()),
        encoding="cp850",
        errors="replace",
    )
    # DETACHED_PROCESS = 0x00000008
    subprocess.Popen(
        ["cmd", "/c", str(bat_path)],
        creationflags=0x00000008,
        close_fds=True,
    )
    sys.exit(0)


def check_and_prepare():
    """Consulta release. Retorna (tag_nova, download_url) se ha update, senao (None, None)."""
    tag, url = check_latest_release()
    if not tag or not url or not is_newer(tag):
        return None, None
    return tag, url


def marcar_update_pendente(zip_path: Path, tag: str) -> None:
    """Escreve marker apontando pro zip baixado. Aplicado no proximo startup."""
    try:
        UPDATE_MARKER.parent.mkdir(parents=True, exist_ok=True)
        UPDATE_MARKER.write_text(
            json.dumps({"zip_path": str(zip_path), "tag": tag, "for_version": tag}),
            encoding="utf-8",
        )
    except OSError:
        pass


def check_pending_update() -> bool:
    """Se marker existe e zip valido, aplica update (mata processo).
    Chamar ANTES de abrir a UI no main.py.

    Retorna True se disparou update (nao volta), False se nada a fazer.
    """
    if not UPDATE_MARKER.exists():
        return False
    try:
        data = json.loads(UPDATE_MARKER.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        _limpar_marker()
        return False

    zip_path = Path(data.get("zip_path", ""))
    tag = data.get("tag", "")

    # Se a versao atual ja e igual ou maior, ignora (rollback ou instalacao manual)
    if tag and not is_newer(tag):
        _limpar_marker()
        try:
            if zip_path.exists():
                zip_path.unlink()
        except OSError:
            pass
        return False

    if not zip_path.exists():
        _limpar_marker()
        return False

    _limpar_marker()
    apply_update(zip_path)
    return True  # nao alcanca (apply_update chama sys.exit)


def _limpar_marker() -> None:
    try:
        UPDATE_MARKER.unlink()
    except OSError:
        pass
