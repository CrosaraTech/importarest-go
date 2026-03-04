from datetime import datetime
from core.validators import normalize_digits


def formatar_aliquota(val: str) -> str:
    """Formata alíquota para o TXT. Remove zeros à direita desnecessários."""
    try:
        num = float((val or "0").replace(",", "."))
        if num == 0:
            return "0"
        formatted = f"{num:.4f}".rstrip("0").rstrip(".")
        return formatted
    except (ValueError, AttributeError):
        return val.strip() if val else "0"



def sanitizar_campo(v) -> str:
    """Remove ';' de qualquer valor de campo para não corromper o TXT delimitado."""
    return str(v or "").replace(";", " ").strip()


def normalizar_uf(uf: str) -> str:
    """Garante que o UF seja uma sigla de exatamente 2 letras."""
    v = sanitizar_campo(uf).upper()
    letras = "".join(c for c in v if c.isalpha())
    if len(letras) == 2:
        return letras
    return ""


def normalizar_data_fmt(data: str) -> str:
    """Valida/converte data para o formato DDMMAAAA (8 dígitos)."""
    d = (data or "").strip()
    digits = normalize_digits(d)
    if len(digits) == 7:
        digits = digits.zfill(8)
    if len(digits) == 8:
        try:
            dd, mm, aaaa = int(digits[:2]), int(digits[2:4]), int(digits[4:])
            if 1 <= dd <= 31 and 1 <= mm <= 12 and 1900 <= aaaa <= 2100:
                return digits
        except (ValueError, TypeError):
            pass
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%Y/%m/%d"):
        try:
            dt = datetime.strptime(d, fmt)
            return dt.strftime("%d%m%Y")
        except (ValueError, TypeError):
            pass
    return ""
