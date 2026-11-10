"""Uma atualizacao que falha nao pode deixar a analista sem o programa."""
import subprocess
import sys
import threading
import zipfile
from pathlib import Path
from unittest.mock import patch

import pytest

import services.updater as up

windows = pytest.mark.skipif(sys.platform != "win32", reason="updater.bat so roda no Windows")


def _instalacao(tmp_path) -> Path:
    inst = tmp_path / "ImportaREST"
    (inst / "_internal").mkdir(parents=True)
    (inst / "ImportaREST.exe").write_bytes(b"VELHO")
    (inst / "_internal" / "lib.dll").write_bytes(b"VELHO")
    (inst / ".env").write_text("X=1")
    return inst


def _zip(tmp_path, truncar=False, com_exe=True) -> Path:
    z_path = tmp_path / "update.zip"
    with zipfile.ZipFile(z_path, "w") as z:
        if com_exe:
            z.writestr("ImportaREST/ImportaREST.exe", b"NOVO" * 500)
        z.writestr("ImportaREST/_internal/lib.dll", b"NOVO" * 500)
    if truncar:
        z_path.write_bytes(z_path.read_bytes()[:120])
    return z_path


def _rodar_bat(novo: Path, zip_path: Path, inst: Path) -> None:
    """Executa o .bat real, sem reabrir o programa falso nem se apagar."""
    linhas = up._bat_template(novo, zip_path, str(inst), 999999).splitlines()
    bat = inst.parent / "teste.bat"
    bat.write_text(
        "\n".join(l for l in linhas
                  if not l.startswith('start ""') and "(goto)" not in l
                  and "SHORTCUT" not in l and "CreateShortcut" not in l),
        encoding="cp850",
    )
    subprocess.run(["cmd", "/c", str(bat)], stdin=subprocess.DEVNULL,
                   capture_output=True, timeout=60, check=False)


# --- Preparacao, com o programa ainda aberto ------------------------------

def test_preparar_extrai_ao_lado_sem_tocar_na_instalacao(tmp_path):
    inst = _instalacao(tmp_path)
    novo = up.preparar_instalacao(_zip(tmp_path), str(inst))

    assert (novo / "ImportaREST.exe").read_bytes().startswith(b"NOVO")
    assert (novo / ".env").read_text() == "X=1"
    assert (inst / "ImportaREST.exe").read_bytes() == b"VELHO"


@pytest.mark.parametrize("zip_kw", [{"truncar": True}, {"com_exe": False}])
def test_preparar_recusa_zip_ruim_sem_deixar_sobra(tmp_path, zip_kw):
    inst = _instalacao(tmp_path)
    assert up.preparar_instalacao(_zip(tmp_path, **zip_kw), str(inst)) is None
    assert (inst / "ImportaREST.exe").read_bytes() == b"VELHO"
    assert not Path(f"{inst}_novo").exists()


def test_update_ruim_nao_fecha_o_programa(tmp_path):
    inst = _instalacao(tmp_path)
    z = _zip(tmp_path, truncar=True)
    marker = tmp_path / "marker.json"
    marker.write_text('{"zip_path": "%s", "tag": "v9.9"}' % z.as_posix())

    with patch.object(up, "UPDATE_MARKER", marker), \
         patch.object(up, "INSTALL_DIR", str(inst)), \
         patch.object(up, "apply_update") as aplicar:
        assert up.check_pending_update() is False

    aplicar.assert_not_called()
    assert not z.exists()


# --- Troca de pastas, com o programa fechado ------------------------------

def test_bat_nao_depende_do_powershell_para_extrair():
    assert "Expand-Archive" not in up._bat_template(Path("n"), Path("z"), "i", 1)


@windows
def test_bat_troca_a_versao(tmp_path):
    inst = _instalacao(tmp_path)
    z = _zip(tmp_path)
    _rodar_bat(up.preparar_instalacao(z, str(inst)), z, inst)

    assert (inst / "ImportaREST.exe").read_bytes().startswith(b"NOVO")
    assert (inst / ".env").exists()
    assert not Path(f"{inst}_bak").exists()
    assert not Path(f"{inst}_novo").exists()


@windows
def test_bat_com_arquivo_em_uso_mantem_a_versao_atual(tmp_path):
    inst = _instalacao(tmp_path)
    z = _zip(tmp_path)
    novo = up.preparar_instalacao(z, str(inst))
    with open(inst / "_internal" / "lib.dll", "rb"):   # antivirus, outra janela
        _rodar_bat(novo, z, inst)

    assert (inst / "ImportaREST.exe").read_bytes() == b"VELHO"
    assert (inst / "_internal" / "lib.dll").exists()
    assert not Path(f"{inst}_novo").exists()


@windows
def test_bat_espera_o_antivirus_soltar_os_arquivos_novos(tmp_path):
    # O antivirus examina o que acabou de ser gravado e prende os arquivos por instantes.
    inst = _instalacao(tmp_path)
    z = _zip(tmp_path)
    novo = up.preparar_instalacao(z, str(inst))
    trava = open(novo / "ImportaREST.exe", "rb")
    threading.Timer(15, trava.close).start()

    _rodar_bat(novo, z, inst)

    assert (inst / "ImportaREST.exe").read_bytes().startswith(b"NOVO")


def test_bat_nao_usa_timeout_que_falha_sem_console():
    assert "timeout /t" not in up._bat_template(Path("n"), Path("z"), "i", 1)


@windows
def test_bat_restaura_na_raiz_se_o_exe_novo_nao_chegar(tmp_path):
    inst = _instalacao(tmp_path)
    novo = tmp_path / "ImportaREST_novo" / "ImportaREST"
    novo.mkdir(parents=True)
    (novo / "lib.dll").write_bytes(b"NOVO")   # antivirus levou o exe

    _rodar_bat(novo, _zip(tmp_path), inst)

    assert (inst / "ImportaREST.exe").read_bytes() == b"VELHO"
    assert (inst / ".env").exists()
    assert not list(inst.glob("*_bak"))


def test_codigo_declara_a_versao_mais_nova_que_a_ultima_publicada():
    from config import __version__
    assert up._parse_version(__version__) > up._parse_version("v1.18")
