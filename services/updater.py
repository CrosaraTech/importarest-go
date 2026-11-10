"""Auto-update: consulta GitHub Releases, baixa zip, dispara updater.bat."""
import json
import os
import shutil
import ssl
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

from config import __version__, GITHUB_REPO, INSTALL_DIR

try:
    import certifi
    _SSL_CTX = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    _SSL_CTX = ssl.create_default_context()

GITHUB_API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
_UA = f"ImportaREST/{__version__}"
EXE_NOME = "ImportaREST.exe"

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


def preparar_instalacao(zip_path: Path, install_dir: str = None) -> Path | None:
    """Extrai o update ao lado da instalacao, com o programa ainda aberto.

    Usa zipfile, nao PowerShell: o antivirus corporativo bloqueia o PowerShell
    de tocar o exe. Nada da instalacao atual e alterado aqui. Retorna a pasta
    pronta para a troca, ou None se o update nao serve.
    """
    install_dir = install_dir or INSTALL_DIR
    staging = Path(f"{install_dir}_novo")
    shutil.rmtree(staging, ignore_errors=True)
    try:
        with zipfile.ZipFile(zip_path) as z:
            z.extractall(staging)
        aninhada = staging / "ImportaREST"
        raiz = aninhada if (aninhada / EXE_NOME).exists() else staging
        if not (raiz / EXE_NOME).exists():
            raise FileNotFoundError(EXE_NOME)
        env = Path(install_dir) / ".env"
        if env.exists():
            shutil.copy2(env, raiz / ".env")
    except Exception:  # update ruim nunca pode impedir o programa de abrir
        shutil.rmtree(staging, ignore_errors=True)
        return None
    return raiz


def _bat_template(novo: Path, zip_path: Path, install_dir: str, pid: int) -> str:
    # Batch em cp850 (default Windows). Sem acentos.
    return f"""@echo off
setlocal
set INSTALL={install_dir}
set NOVO={novo}
set ZIP={zip_path}
set PIDMATA={pid}

REM Espera processo pai morrer (max 15s)
set /a WAIT=0
:wait_loop
tasklist /FI "PID eq %PIDMATA%" 2>NUL | find "%PIDMATA%" >NUL
if not errorlevel 1 (
    if %WAIT% lss 30 (
        ping -n 2 127.0.0.1 >nul
        set /a WAIT+=1
        goto wait_loop
    )
)

REM Pasta em uso: desiste sem tocar em nada e reabre a versao atual
if exist "%INSTALL%_bak" rmdir /s /q "%INSTALL%_bak"
move "%INSTALL%" "%INSTALL%_bak" >nul 2>&1
if errorlevel 1 goto reabrir

REM Antivirus prende arquivos recem-gravados por instantes: insiste por mais de 1 min.
REM ping e nao timeout: timeout falha em processo sem console.
set /a TENT=0
:mover_novo
move "%NOVO%" "%INSTALL%" >nul 2>&1
if exist "%INSTALL%\\{EXE_NOME}" goto concluir
if not exist "%NOVO%" goto restaurar
if %TENT% lss 12 (
    ping -n 3 127.0.0.1 >nul
    set /a TENT+=1
    goto mover_novo
)

:restaurar

REM xcopy e nao move: se a pasta nao sumir, move aninharia o backup dentro dela
rmdir /s /q "%INSTALL%" 2>nul
xcopy "%INSTALL%_bak" "%INSTALL%" /e /i /y /q /h >nul
goto reabrir

:concluir
rmdir /s /q "%INSTALL%_bak" 2>nul

:reabrir
rmdir /s /q "%INSTALL%_novo" 2>nul
del "%ZIP%" 2>nul

REM Cria atalho desktop se nao existir
set SHORTCUT=%USERPROFILE%\\Desktop\\ImportaREST.lnk
if not exist "%SHORTCUT%" powershell -NoProfile -Command "$s=(New-Object -COM WScript.Shell).CreateShortcut('%SHORTCUT%'); $s.TargetPath='%INSTALL%\\{EXE_NOME}'; $s.IconLocation='%INSTALL%\\{EXE_NOME}'; $s.WorkingDirectory='%INSTALL%'; $s.Save()"

REM Reinicia programa
start "" "%INSTALL%\\{EXE_NOME}"

REM Auto-delete .bat
(goto) 2>nul & del "%~f0"
"""


def apply_update(novo: Path, zip_path: Path, install_dir: str = None) -> None:
    """Escreve updater.bat, dispara em background e mata o processo atual."""
    install_dir = install_dir or INSTALL_DIR
    bat_path = Path(tempfile.gettempdir()) / "importarest_updater.bat"
    bat_path.write_text(
        _bat_template(novo, zip_path, install_dir, os.getpid()),
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
    novo = preparar_instalacao(zip_path)
    if novo is None:
        try:
            zip_path.unlink()
        except OSError:
            pass
        return False
    apply_update(novo, zip_path)
    return True  # nao alcanca (apply_update chama sys.exit)


def _limpar_marker() -> None:
    try:
        UPDATE_MARKER.unlink()
    except OSError:
        pass
