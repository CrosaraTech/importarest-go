"""Instalador ImportaREST — primeira instalacao em C:\\ImportaREST\\.

Fluxo:
 1. Pede UAC (admin) se nao tiver.
 2. Baixa ultimo release do GitHub.
 3. Extrai em C:\\ImportaREST\\.
 4. Ajusta permissoes da pasta para o usuario padrao (updates futuros sem UAC).
 5. Cria atalho na Area de Trabalho.
 6. Abre ImportaREST.exe.
"""
import ctypes
import json
import os
import shutil
import subprocess
import sys
import tempfile
import tkinter as tk
import urllib.request
import zipfile
from pathlib import Path
from tkinter import messagebox, ttk

GITHUB_REPO = "CrosaraTech/importarest-go"
GITHUB_API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
INSTALL_DIR = Path(r"C:\ImportaREST")
_UA = "ImportaREST-Installer/1.0"


def _is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def _elevate() -> None:
    """Reexecuta o instalador com UAC."""
    params = " ".join(f'"{a}"' for a in sys.argv[1:])
    ctypes.windll.shell32.ShellExecuteW(
        None, "runas", sys.executable, params, None, 1
    )
    sys.exit(0)


def _fetch_release():
    req = urllib.request.Request(
        GITHUB_API_URL,
        headers={"Accept": "application/vnd.github+json", "User-Agent": _UA},
    )
    with urllib.request.urlopen(req, timeout=15) as r:
        data = json.loads(r.read().decode("utf-8"))
    tag = data.get("tag_name", "") or ""
    url = ""
    for asset in data.get("assets", []) or []:
        name = (asset.get("name") or "").lower()
        if name.endswith(".zip") and "windows" in name:
            url = asset.get("browser_download_url", "") or ""
            break
    if not url:
        raise RuntimeError(
            "Nenhum asset .zip 'windows' encontrado no release mais recente."
        )
    return tag, url


def _download(url: str, dest: Path, progress_cb=None) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=120) as r, open(dest, "wb") as f:
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


def _flatten_if_nested(install_dir: Path) -> None:
    """Se zip extraiu como install_dir/ImportaREST/..., achata."""
    inner = install_dir / "ImportaREST"
    exe = inner / "ImportaREST.exe"
    if not exe.exists():
        return
    for item in inner.iterdir():
        alvo = install_dir / item.name
        if alvo.exists():
            if alvo.is_dir():
                shutil.rmtree(alvo, ignore_errors=True)
            else:
                alvo.unlink()
        shutil.move(str(item), str(alvo))
    try:
        inner.rmdir()
    except OSError:
        pass


def _grant_user_full_control(install_dir: Path) -> None:
    """icacls: da controle total pra grupo Users no dir. Updates futuros sem UAC."""
    subprocess.run(
        [
            "icacls", str(install_dir),
            "/grant", "*S-1-5-32-545:(OI)(CI)F",  # Users SID (independente de idioma)
            "/T", "/C", "/Q",
        ],
        check=False,
        creationflags=0x08000000,  # CREATE_NO_WINDOW
    )


def _create_desktop_shortcut(install_dir: Path) -> None:
    desktop = Path(os.environ.get("USERPROFILE", "")) / "Desktop"
    if not desktop.exists():
        return
    shortcut = desktop / "ImportaREST.lnk"
    exe = install_dir / "ImportaREST.exe"
    ps_cmd = (
        f'$s=(New-Object -COM WScript.Shell).CreateShortcut("{shortcut}"); '
        f'$s.TargetPath="{exe}"; '
        f'$s.IconLocation="{exe}"; '
        f'$s.WorkingDirectory="{install_dir}"; '
        f'$s.Save()'
    )
    subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_cmd],
        check=False,
        creationflags=0x08000000,
    )


def _bundled_env_path() -> Path:
    """.env embutido no installer (via PyInstaller --add-data ou spec datas)."""
    if getattr(sys, "frozen", False):
        base = Path(sys._MEIPASS)
    else:
        base = Path(__file__).parent
    return base / ".env"


def _install_all(status_cb):
    status_cb("Consultando ultima versao no GitHub...")
    tag, url = _fetch_release()

    status_cb(f"Baixando {tag}...")
    zip_path = Path(tempfile.gettempdir()) / f"ImportaREST-installer-{tag}.zip"

    def _pcb(baixado, total):
        pct = int(100 * baixado / total)
        status_cb(f"Baixando {tag}... {pct}%")

    _download(url, zip_path, _pcb)

    status_cb("Preparando pasta de instalacao...")
    # Se ja tem instalacao, backup antes de sobrescrever
    if INSTALL_DIR.exists():
        bak = INSTALL_DIR.parent / (INSTALL_DIR.name + "_bak")
        if bak.exists():
            shutil.rmtree(bak, ignore_errors=True)
        try:
            INSTALL_DIR.rename(bak)
        except OSError:
            shutil.rmtree(INSTALL_DIR, ignore_errors=True)
    INSTALL_DIR.mkdir(parents=True, exist_ok=True)

    status_cb("Extraindo arquivos...")
    with zipfile.ZipFile(zip_path) as z:
        z.extractall(INSTALL_DIR)
    _flatten_if_nested(INSTALL_DIR)

    # Copia .env embutido pra pasta de instalacao
    env_src = _bundled_env_path()
    if env_src.exists():
        try:
            shutil.copy2(str(env_src), str(INSTALL_DIR / ".env"))
        except OSError:
            pass

    status_cb("Ajustando permissoes...")
    _grant_user_full_control(INSTALL_DIR)

    status_cb("Criando atalho na Area de Trabalho...")
    _create_desktop_shortcut(INSTALL_DIR)

    # Limpa backup e zip
    bak = INSTALL_DIR.parent / (INSTALL_DIR.name + "_bak")
    if bak.exists():
        shutil.rmtree(bak, ignore_errors=True)
    try:
        zip_path.unlink()
    except OSError:
        pass

    status_cb(f"Instalacao concluida ({tag}).")


def _gui_main():
    root = tk.Tk()
    root.title("Instalador ImportaREST")
    root.geometry("480x220")
    root.resizable(False, False)
    root.configure(bg="#14110F")

    frm = tk.Frame(root, bg="#14110F", padx=24, pady=20)
    frm.pack(fill="both", expand=True)

    tk.Label(
        frm, text="Instalador ImportaREST",
        font=("Segoe UI", 14, "bold"),
        fg="#F4EFE7", bg="#14110F",
    ).pack(anchor="w")

    tk.Label(
        frm,
        text=f"Destino: {INSTALL_DIR}",
        font=("Segoe UI", 9),
        fg="#9D9286", bg="#14110F",
    ).pack(anchor="w", pady=(4, 12))

    status_var = tk.StringVar(value="Pronto para instalar.")
    tk.Label(
        frm, textvariable=status_var,
        font=("Segoe UI", 9),
        fg="#CBA75A", bg="#14110F",
        wraplength=430, justify="left",
    ).pack(anchor="w")

    btn_frame = tk.Frame(frm, bg="#14110F")
    btn_frame.pack(side="bottom", fill="x", pady=(20, 0))

    concluido = {"ok": False}

    def _run():
        btn_install.config(state="disabled")
        btn_close.config(state="disabled")
        try:
            _install_all(lambda m: (status_var.set(m), root.update_idletasks()))
            concluido["ok"] = True
            btn_close.config(state="normal", text="Abrir programa")
        except Exception as e:
            status_var.set(f"Erro: {e}")
            btn_close.config(state="normal")

    def _close():
        if concluido["ok"]:
            try:
                os.startfile(str(INSTALL_DIR / "ImportaREST.exe"))
            except OSError:
                pass
        root.destroy()

    btn_install = tk.Button(
        btn_frame, text="Instalar",
        bg="#E58A4E", fg="white",
        activebackground="#FFA866", activeforeground="white",
        relief="flat", padx=20, pady=6,
        command=lambda: root.after(50, _run),
    )
    btn_install.pack(side="right", padx=(8, 0))

    btn_close = tk.Button(
        btn_frame, text="Fechar",
        bg="#2A231F", fg="#F4EFE7",
        activebackground="#3A312C", activeforeground="#F4EFE7",
        relief="flat", padx=20, pady=6,
        command=_close,
    )
    btn_close.pack(side="right")

    root.mainloop()


def main():
    if not _is_admin():
        _elevate()
        return
    _gui_main()


if __name__ == "__main__":
    main()
