from config import GOIANIA_IBGE_7, GOIANIA_IBGE_6


def normalize_digits(s: str) -> str:
    return "".join(ch for ch in (s or "") if ch.isdigit())


def has_value(v) -> bool:
    if v is None:
        return False
    if isinstance(v, str):
        return v.strip() != ""
    return True


def eh_goiania(dados) -> bool:
    cod = normalize_digits(dados.get("codigo_municipio") or "")
    return cod in (GOIANIA_IBGE_7, GOIANIA_IBGE_6)


def item_lc_valido(codigo: str) -> bool:
    """Verifica se o item LC está na faixa válida da LC 116 (01.01 a 40.99)."""
    d = normalize_digits(codigo or "")
    d = d.zfill(4)
    if len(d) < 4:
        return False
    try:
        grupo = int(d[:2])
        return 1 <= grupo <= 40
    except ValueError:
        return False


def imposto_retido_norm(iss_ret: str, origem: str = "abrasf") -> str:
    v = (iss_ret or "").strip()
    if origem == "nacional":
        # tpRetISSQN: 1=não retido→0, 2=retido tomador→1, 3=retido intermediário→1
        if v == "1":
            return "0"
        if v in ("2", "3"):
            return "1"
        return "0"
    # IssRetido (ABRASF): 1=retido→1, 2=não retido→0
    if v == "2":
        return "0"
    if v in ("0", "1"):
        return v
    return "0"

