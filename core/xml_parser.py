import re
import xml.etree.ElementTree as ET


def _text(node, default=""):
    return node.text.strip() if node is not None and node.text else default


def find_text(root, paths, default=""):
    for p in paths:
        v = _text(root.find(p), "")
        if v.strip() != "":
            return v.strip()
    return default


def eh_evento_cancelamento(xml_string: str) -> bool:
    """Verifica se o XML de evento contém tag <e10xxxx> dentro de <infPedReg> (cancelamento)."""
    try:
        root = ET.fromstring(xml_string)
        for inf in root.iter():
            tag_local = inf.tag.split("}")[-1] if "}" in inf.tag else inf.tag
            if tag_local == "infPedReg":
                for child in inf:
                    child_tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
                    if re.match(r"^e10\d+$", child_tag):
                        return True
    except ET.ParseError:
        pass
    return False


def detectar_padrao_nfse(root: ET.Element) -> str:
    tag = (root.tag or "").lower()

    # 1) Detecção por namespace do root tag
    if "abrasf.org.br/nfse.xsd" in tag or tag.endswith("consultarnfseservicoprestadoresposta"):
        return "abrasf"
    if "sped.fazenda.gov.br/nfse" in tag or tag.endswith("nfse"):
        return "nacional"

    # 2) Fallback: fingerprint pelos elementos internos
    _ABRASF_TAGS = {"InfNfse", "CompNfse", "ListaNfse", "Nfse",
                    "PrestadorServico", "TomadorServico", "Servico",
                    "ItemListaServico", "IssRetido", "ValoresNfse"}
    _NACIONAL_TAGS = {"infNFSe", "NFSe", "DPS", "infDPS", "cServ",
                      "cTribNac", "tpRetISSQN", "vServPrest"}

    abrasf_hits = 0
    for elem in root.iter():
        local = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
        if local in _ABRASF_TAGS:
            abrasf_hits += 1
            if abrasf_hits >= 2:
                return "abrasf"
        if local in _NACIONAL_TAGS:
            return "nacional"

    if abrasf_hits >= 1:
        return "abrasf"

    return "desconhecido"
