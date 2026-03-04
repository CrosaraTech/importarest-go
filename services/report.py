import csv
import os
from config import RELATORIO_CSV

_CABECALHO = [
    "Arquivo", "CNPJ Prestador", "Numero Nota", "Valor Documento",
    "Status", "Modo", "Detalhe", "Chave NFS-e", "Data/Hora Execucao", "Linha TXT"
]


def gravar_relatorio(relatorio: list, path: str = RELATORIO_CSV) -> None:
    """Grava o relatório CSV com o resultado de cada nota processada."""
    if not relatorio:
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow(_CABECALHO)
        writer.writerows(relatorio)
