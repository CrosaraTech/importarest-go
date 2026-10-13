"""
Script único para preencher campos faltantes da planilha RELACAO_EMPRESAS_atualizada.xlsx
a partir de TODOS os XMLs fiscais (NFS-e, NF-e, CT-e, NFC-e) nas pastas Entradas e Saidas.

Campos preenchidos (somente se vazios):
  - INSC. MUNICIPAL  (col H)
  - MUNICIPIO         (col F)
  - ESTADO            (col E)

Fontes (ordem de prioridade):
  1. Saidas/NF-e   → <emit>  (dados mais completos da empresa: IM, xMun, UF)
  2. Saidas/NFS-e  → <emit> ou <PrestadorServico>
  3. Saidas/NFC-e  → <emit>
  4. Entradas/NF-e → <dest>  (xMun, UF, às vezes IM)
  5. Entradas/CT-e → <dest>  (xMun, UF)
  6. Entradas/NFS-e→ <toma>  (IM, cMun)
"""

import os
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

import openpyxl
import requests

# ── Caminhos ────────────────────────────────────────────────────────────────
PLANILHA = Path(r"C:\Users\Havai\Desktop\Rest iss.net\RELACAO_EMPRESAS_atualizada.xlsx")
XML_ROOT = Path(r"G:\Drives compartilhados\FISCAL\autmais\xml")
IBGE_MUN_URL = "https://servicodados.ibge.gov.br/api/v1/localidades/municipios/{}"

# Diretórios a varrer, na ordem de prioridade (melhores fontes primeiro)
FONTES = [
    ("Saidas/NF-e",    "emit"),
    ("Saidas/NFS-e",   "emit_nfse"),
    ("Saidas/NFC-e",   "emit"),
    ("Entradas/NF-e",  "dest"),
    ("Entradas/CT-e",  "dest"),
    ("Entradas/NFS-e", "toma_nfse"),
]

# ── Colunas (1-based para openpyxl) ────────────────────────────────────────
COL_COD   = 1   # A
COL_NOME  = 2   # B
COL_CNPJ  = 3   # C
COL_ESTADO = 5  # E
COL_MUNICIPIO = 6  # F
COL_IM    = 8   # H

# ── Helpers ─────────────────────────────────────────────────────────────────

def normalize_digits(s):
    return "".join(ch for ch in (s or "") if ch.isdigit())


def _text(node):
    return node.text.strip() if node is not None and node.text else ""


def find_text(root, paths):
    for p in paths:
        node = root.find(p)
        v = _text(node)
        if v:
            return v
    return ""


# ── Cache IBGE ──────────────────────────────────────────────────────────────
_ibge_cache = {}

_UF_IBGE = {
    "11": "RO", "12": "AC", "13": "AM", "14": "RR", "15": "PA",
    "16": "AP", "17": "TO", "21": "MA", "22": "PI", "23": "CE",
    "24": "RN", "25": "PB", "26": "PE", "27": "AL", "28": "SE",
    "29": "BA", "31": "MG", "32": "ES", "33": "RJ", "35": "SP",
    "41": "PR", "42": "SC", "43": "RS", "50": "MS", "51": "MT",
    "52": "GO", "53": "DF",
}


def consulta_ibge(codigo_municipio):
    """Retorna (nome_municipio, uf) a partir do código IBGE."""
    cod = normalize_digits(codigo_municipio)
    if not cod:
        return "", ""
    uf = _UF_IBGE.get(cod[:2], "")
    if cod in _ibge_cache:
        return _ibge_cache[cod], uf
    try:
        r = requests.get(IBGE_MUN_URL.format(cod), timeout=20)
        if r.status_code == 200:
            js = r.json()
            nome = (js.get("nome") or "").strip().upper()
            _ibge_cache[cod] = nome
            return nome, uf
    except Exception:
        pass
    _ibge_cache[cod] = ""
    return "", uf


# ── Extratores por tipo de XML ─────────────────────────────────────────────

def _extrair_emit(xml_bytes):
    """Extrai dados de <emit> em NF-e / NFC-e (Saidas → empresa é emitente)."""
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return None
    cnpj = find_text(root, [".//{*}emit//{*}CNPJ"])
    if not cnpj:
        return None
    return {
        "cnpj": normalize_digits(cnpj),
        "im": find_text(root, [".//{*}emit//{*}IM"]),
        "cod_municipio": find_text(root, [".//{*}emit//{*}enderEmit//{*}cMun", ".//{*}emit//{*}cMun"]),
        "nome_municipio": find_text(root, [".//{*}emit//{*}enderEmit//{*}xMun", ".//{*}emit//{*}xMun"]),
        "uf": find_text(root, [".//{*}emit//{*}enderEmit//{*}UF", ".//{*}emit//{*}UF"]),
    }


def _extrair_emit_nfse(xml_bytes):
    """Extrai dados de <emit> ou <PrestadorServico> em NFS-e (Saidas)."""
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return None
    # Nacional
    cnpj = find_text(root, [
        ".//{*}emit//{*}CNPJ",
        ".//{*}PrestadorServico//{*}IdentificacaoPrestador//{*}CpfCnpj//{*}Cnpj",
        ".//{*}Prestador//{*}Cnpj",
    ])
    if not cnpj:
        return None
    return {
        "cnpj": normalize_digits(cnpj),
        "im": find_text(root, [
            ".//{*}emit//{*}IM",
            ".//{*}prest//{*}IM",
            ".//{*}PrestadorServico//{*}IdentificacaoPrestador//{*}InscricaoMunicipal",
            ".//{*}Prestador//{*}InscricaoMunicipal",
        ]),
        "cod_municipio": find_text(root, [
            ".//{*}emit//{*}enderNac//{*}cMun",
            ".//{*}PrestadorServico//{*}Endereco//{*}CodigoMunicipio",
        ]),
        "nome_municipio": "",
        "uf": find_text(root, [
            ".//{*}emit//{*}enderNac//{*}UF",
            ".//{*}PrestadorServico//{*}Endereco//{*}Uf",
        ]),
    }


def _extrair_dest(xml_bytes):
    """Extrai dados de <dest> em NF-e / CT-e (Entradas → empresa é destinatário)."""
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return None
    cnpj = find_text(root, [".//{*}dest//{*}CNPJ"])
    if not cnpj:
        return None
    return {
        "cnpj": normalize_digits(cnpj),
        "im": find_text(root, [".//{*}dest//{*}IM"]),
        "cod_municipio": find_text(root, [
            ".//{*}dest//{*}enderDest//{*}cMun",
            ".//{*}dest//{*}cMun",
        ]),
        "nome_municipio": find_text(root, [
            ".//{*}dest//{*}enderDest//{*}xMun",
            ".//{*}dest//{*}xMun",
        ]),
        "uf": find_text(root, [
            ".//{*}dest//{*}enderDest//{*}UF",
            ".//{*}dest//{*}UF",
        ]),
    }


def _extrair_toma_nfse(xml_bytes):
    """Extrai dados do tomador de NFS-e (Entradas → empresa é tomador)."""
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return None
    cnpj = find_text(root, [
        ".//{*}toma//{*}CNPJ",
        ".//{*}TomadorServico//{*}IdentificacaoTomador//{*}CpfCnpj//{*}Cnpj",
        ".//{*}TomadorServico//{*}Cnpj",
    ])
    if not cnpj:
        return None
    return {
        "cnpj": normalize_digits(cnpj),
        "im": find_text(root, [
            ".//{*}toma//{*}IM",
            ".//{*}toma//{*}InscricaoMunicipal",
            ".//{*}TomadorServico//{*}IdentificacaoTomador//{*}InscricaoMunicipal",
        ]),
        "cod_municipio": find_text(root, [
            ".//{*}toma//{*}end//{*}endNac//{*}cMun",
            ".//{*}TomadorServico//{*}Endereco//{*}CodigoMunicipio",
        ]),
        "nome_municipio": "",
        "uf": find_text(root, [
            ".//{*}toma//{*}end//{*}endNac//{*}UF",
            ".//{*}TomadorServico//{*}Endereco//{*}Uf",
        ]),
    }


EXTRATORES = {
    "emit":      _extrair_emit,
    "emit_nfse": _extrair_emit_nfse,
    "dest":      _extrair_dest,
    "toma_nfse": _extrair_toma_nfse,
}


# ── Mapear TODAS as pastas por código ──────────────────────────────────────

def mapear_pastas():
    """Retorna {cod: [(dir_path, tipo_extrator), ...]} com todas as pastas de empresa."""
    resultado = {}  # cod → list of (path, extrator_key)
    for subdir, extrator in FONTES:
        full_dir = XML_ROOT / subdir
        if not full_dir.exists():
            continue
        try:
            nomes = os.listdir(full_dir)
        except OSError:
            continue
        for nome in nomes:
            pasta = full_dir / nome
            if pasta.is_dir() and nome.endswith("-"):
                cod_str = nome.rstrip("-")
                try:
                    cod = int(cod_str)
                except ValueError:
                    continue
                resultado.setdefault(cod, []).append((pasta, extrator))
    return resultado


# ── Busca genérica em uma pasta de empresa ─────────────────────────────────

MAX_XMLS_PER_ZIP = 5  # Ler no máximo N XMLs por ZIP para evitar lentidão no Drive


def buscar_dados(empresa_dir, cnpj_empresa, extrator_fn):
    """Percorre subpastas de meses, lê XMLs (soltos ou .zip),
    retorna dados encontrados que batem com o CNPJ."""
    cnpj_norm = normalize_digits(cnpj_empresa)
    melhor = {"im": "", "cod_municipio": "", "nome_municipio": "", "uf": ""}

    try:
        meses = sorted(os.listdir(empresa_dir), reverse=True)
    except OSError:
        return melhor

    # Limitar a 2 meses mais recentes para velocidade
    for mes in meses[:2]:
        mes_path = empresa_dir / mes
        if not mes_path.is_dir():
            continue
        try:
            arquivos = os.listdir(mes_path)
        except OSError:
            continue

        for arq in arquivos:
            arq_path = mes_path / arq

            xmls_to_parse = []

            if arq.lower().endswith(".xml"):
                try:
                    xmls_to_parse.append(arq_path.read_bytes())
                except Exception:
                    continue
            elif arq.lower().endswith(".zip"):
                try:
                    with zipfile.ZipFile(arq_path, "r") as zf:
                        count = 0
                        for name in zf.namelist():
                            if name.lower().endswith(".xml"):
                                try:
                                    xmls_to_parse.append(zf.read(name))
                                    count += 1
                                    if count >= MAX_XMLS_PER_ZIP:
                                        break
                                except Exception:
                                    continue
                except (zipfile.BadZipFile, OSError):
                    continue

            for xml_bytes in xmls_to_parse:
                dados = extrator_fn(xml_bytes)
                if not dados or dados["cnpj"] != cnpj_norm:
                    continue
                if dados["im"] and not melhor["im"]:
                    melhor["im"] = dados["im"]
                if dados["cod_municipio"] and not melhor["cod_municipio"]:
                    melhor["cod_municipio"] = dados["cod_municipio"]
                if dados.get("nome_municipio") and not melhor["nome_municipio"]:
                    melhor["nome_municipio"] = dados["nome_municipio"]
                if dados["uf"] and not melhor["uf"]:
                    melhor["uf"] = dados["uf"]

                if melhor["im"] and melhor["cod_municipio"] and melhor["uf"]:
                    return melhor

            if melhor["im"] and melhor["cod_municipio"] and melhor["uf"]:
                return melhor

        if melhor["im"] and melhor["cod_municipio"] and melhor["uf"]:
            return melhor

    return melhor


# ── Merge de resultados ────────────────────────────────────────────────────

def merge(acumulado, novo):
    """Mescla novo resultado no acumulado, preenchendo apenas campos vazios."""
    for k in ("im", "cod_municipio", "nome_municipio", "uf"):
        if novo.get(k) and not acumulado.get(k):
            acumulado[k] = novo[k]


# ── Main ────────────────────────────────────────────────────────────────────

def main():
    print("Carregando planilha...")
    wb = openpyxl.load_workbook(str(PLANILHA))
    ws = wb.active

    print("Mapeando pastas de empresas em todos os diretórios...")
    todas_pastas = mapear_pastas()
    codigos_unicos = set(todas_pastas.keys())
    print(f"Códigos de empresas encontrados: {len(codigos_unicos)}")

    atualizados = 0
    sem_pasta = 0
    sem_dados = 0
    total_processados = 0

    for row in range(2, ws.max_row + 1):
        cod_val = ws.cell(row, COL_COD).value
        if cod_val is None:
            continue
        try:
            cod = int(cod_val)
        except (ValueError, TypeError):
            continue

        cnpj_raw = str(ws.cell(row, COL_CNPJ).value or "")
        cnpj_norm = normalize_digits(cnpj_raw)
        nome = ws.cell(row, COL_NOME).value or ""

        val_estado = ws.cell(row, COL_ESTADO).value
        val_mun = ws.cell(row, COL_MUNICIPIO).value
        val_im = ws.cell(row, COL_IM).value

        falta_estado = not val_estado or str(val_estado).strip() == ""
        falta_mun = not val_mun or str(val_mun).strip() == ""
        falta_im = not val_im or str(val_im).strip() == ""

        if not (falta_estado or falta_mun or falta_im):
            continue

        if not cnpj_norm:
            continue

        total_processados += 1

        if cod not in todas_pastas:
            sem_pasta += 1
            continue

        print(f"  Processando COD {cod:>5} | {nome[:30]:<30} ...", end="", flush=True)

        # Buscar em todas as fontes (já ordenadas por prioridade)
        acumulado = {"im": "", "cod_municipio": "", "nome_municipio": "", "uf": ""}

        for pasta, extrator_key in todas_pastas[cod]:
            extrator_fn = EXTRATORES[extrator_key]
            resultado = buscar_dados(pasta, cnpj_norm, extrator_fn)
            merge(acumulado, resultado)

            # Parar se já tem tudo que falta
            tudo_ok = True
            if falta_im and not acumulado["im"]:
                tudo_ok = False
            if falta_mun and not acumulado["cod_municipio"] and not acumulado["nome_municipio"]:
                tudo_ok = False
            if falta_estado and not acumulado["uf"]:
                tudo_ok = False
            if tudo_ok:
                break

        if not any([acumulado["im"], acumulado["cod_municipio"], acumulado["nome_municipio"], acumulado["uf"]]):
            sem_dados += 1
            print(" sem dados", flush=True)
            continue

        alterou = False

        # Preencher IM
        if falta_im and acumulado["im"]:
            ws.cell(row, COL_IM).value = acumulado["im"]
            alterou = True

        # Preencher Município
        if falta_mun:
            if acumulado["nome_municipio"]:
                ws.cell(row, COL_MUNICIPIO).value = acumulado["nome_municipio"].upper()
                alterou = True
            elif acumulado["cod_municipio"]:
                nome_mun, uf_ibge = consulta_ibge(acumulado["cod_municipio"])
                if nome_mun:
                    ws.cell(row, COL_MUNICIPIO).value = nome_mun
                    alterou = True
                if falta_estado and not acumulado["uf"] and uf_ibge:
                    acumulado["uf"] = uf_ibge

        # Preencher Estado
        if falta_estado and acumulado["uf"]:
            ws.cell(row, COL_ESTADO).value = acumulado["uf"]
            alterou = True
        elif falta_estado and acumulado["cod_municipio"]:
            uf_ibge = _UF_IBGE.get(normalize_digits(acumulado["cod_municipio"])[:2], "")
            if uf_ibge:
                ws.cell(row, COL_ESTADO).value = uf_ibge
                alterou = True

        if alterou:
            atualizados += 1
            mun_display = acumulado["nome_municipio"] or acumulado["cod_municipio"] or "-"
            print(f" OK | IM={acumulado['im'] or '-':<15} MUN={mun_display:<20} UF={acumulado['uf'] or '-'}", flush=True)
        else:
            print(" já preenchido", flush=True)

    # Salvar
    print(f"\n{'='*60}")
    print(f"Empresas com campos faltantes: {total_processados}")
    print(f"Sem pasta em nenhum diretório: {sem_pasta}")
    print(f"Sem dados úteis nos XMLs:      {sem_dados}")
    print(f"Atualizadas:                   {atualizados}")

    if atualizados > 0:
        wb.save(str(PLANILHA))
        print(f"\nPlanilha salva em: {PLANILHA}")
    else:
        print("\nNenhuma alteração feita.")

    wb.close()


if __name__ == "__main__":
    main()
