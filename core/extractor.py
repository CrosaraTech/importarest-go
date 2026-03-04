import xml.etree.ElementTree as ET
from datetime import datetime

from core.xml_parser import find_text, detectar_padrao_nfse
from core.validators import normalize_digits, has_value, item_lc_valido
from core.formatters import formatar_aliquota


def extrair_dados_python(xml_string):
    try:
        root = ET.fromstring(xml_string)
        padrao = detectar_padrao_nfse(root)

        codigo_municipio = find_text(root, [
            ".//{*}OrgaoGerador//{*}CodigoMunicipio",
            ".//{*}InfNfse//{*}OrgaoGerador//{*}CodigoMunicipio",
            ".//{*}PrestadorServico//{*}Endereco//{*}CodigoMunicipio",
            ".//{*}TomadorServico//{*}Endereco//{*}CodigoMunicipio",
            ".//{*}Servico//{*}MunicipioIncidencia",
            ".//{*}MunicipioIncidencia",
            ".//{*}cLocIncid",
            ".//{*}cLocEmi",
            ".//{*}cLocPrestacao",
            ".//{*}CodigoMunicipio",
            ".//{*}cMun",
        ], default="")

        _cep_raw = find_text(root, [
            ".//{*}PrestadorServico//{*}Endereco//{*}Cep",
            ".//{*}Prestador//{*}Endereco//{*}Cep",
            ".//{*}emit//{*}enderNac//{*}CEP",
        ], default="")
        cep = normalize_digits(_cep_raw).zfill(8) if _cep_raw else ""

        endereco = find_text(root, [
            ".//{*}PrestadorServico//{*}Endereco//{*}Endereco",
            ".//{*}Prestador//{*}Endereco//{*}Endereco",
            ".//{*}emit//{*}enderNac//{*}xLgr",
        ], default="")

        numero_end = find_text(root, [
            ".//{*}PrestadorServico//{*}Endereco//{*}Numero",
            ".//{*}Prestador//{*}Endereco//{*}Numero",
            ".//{*}emit//{*}enderNac//{*}nro",
        ], default="")

        bairro = find_text(root, [
            ".//{*}PrestadorServico//{*}Endereco//{*}Bairro",
            ".//{*}Prestador//{*}Endereco//{*}Bairro",
            ".//{*}emit//{*}enderNac//{*}xBairro",
        ], default="")

        numero = find_text(root, [
            ".//{*}CompNfse//{*}Nfse//{*}InfNfse//{*}Numero",
            ".//{*}Nfse//{*}InfNfse//{*}Numero",
            ".//{*}InfNfse//{*}Numero",
            ".//{*}infNFSe//{*}nNFSe",
            ".//{*}nNFSe",
            ".//{*}nDFSe",
            ".//{*}nDPS",
        ], default="")

        cnpj_p = find_text(root, [
            ".//{*}Prestador//{*}Cnpj",
            ".//{*}PrestadorServico//{*}IdentificacaoPrestador//{*}CpfCnpj//{*}Cnpj",
            ".//{*}IdentificacaoPrestador//{*}CpfCnpj//{*}Cnpj",
            ".//{*}emit//{*}CNPJ",
            ".//{*}prest//{*}CNPJ",
        ], default="")

        im_p = find_text(root, [
            ".//{*}Prestador//{*}InscricaoMunicipal",
            ".//{*}PrestadorServico//{*}IdentificacaoPrestador//{*}InscricaoMunicipal",
            ".//{*}IdentificacaoPrestador//{*}InscricaoMunicipal",
            ".//{*}emit//{*}IM",
            ".//{*}prest//{*}IM",
        ], default="")

        razao_p = find_text(root, [
            ".//{*}PrestadorServico//{*}RazaoSocial",
            ".//{*}Prestador//{*}RazaoSocial",
            ".//{*}RazaoSocial",
            ".//{*}emit//{*}xNome",
        ], default="")

        vlr_doc = find_text(root, [
            ".//{*}Servico//{*}Valores//{*}ValorServicos",
            ".//{*}Servico//{*}ValoresServico//{*}ValorServicos",
            ".//{*}vServPrest//{*}vServ",
            ".//{*}ValoresNfse//{*}ValorServicos",
            ".//{*}ValorServicos",
            ".//{*}vServ",
            ".//{*}ValoresNfse//{*}ValorLiquidoNfse",
            ".//{*}ValorLiquidoNfse",
            ".//{*}valores//{*}vLiq",
            ".//{*}valores//{*}vBC",
        ], default="")

        vlr_trib = find_text(root, [
            ".//{*}ValoresNfse//{*}BaseCalculo",
            ".//{*}Servico//{*}Valores//{*}BaseCalculo",
            ".//{*}BaseCalculo",
            ".//{*}valores//{*}vBC",
        ], default="")

        aliq_val = find_text(root, [
            ".//{*}ValoresNfse//{*}Aliquota",
            ".//{*}Servico//{*}Valores//{*}Aliquota",
            ".//{*}Aliquota",
            ".//{*}pAliqAplic",
            ".//{*}tribMun//{*}pAliq",
        ], default="0")

        try:
            _aliq_num = float((aliq_val or "0").replace(",", "."))
        except ValueError:
            _aliq_num = 0.0

        if _aliq_num == 0:
            valor_iss = find_text(root, [
                ".//{*}Servico//{*}Valores//{*}ValorIss",
                ".//{*}ValoresNfse//{*}ValorIss",
                ".//{*}ValorIss",
                ".//{*}tribMun//{*}vTribMun",
                ".//{*}vRecTrib",
            ], default="")
            try:
                _iss = float((valor_iss or "0").replace(",", "."))
                _base = float((vlr_trib or vlr_doc or "0").replace(",", "."))
                if _iss > 0 and _base > 0:
                    aliq_val = str(round((_iss / _base) * 100, 2))
            except (ValueError, ZeroDivisionError):
                pass

        aliq_val = formatar_aliquota(aliq_val)

        iss_ret = find_text(root, [
            ".//{*}Servico//{*}IssRetido",
            ".//{*}IssRetido",
        ], default="")
        iss_ret_origem = "abrasf"

        if not iss_ret:
            iss_ret = find_text(root, [
                ".//{*}tribMun//{*}tpRetISSQN",
                ".//{*}tpRetISSQN",
            ], default="1")
            iss_ret_origem = "nacional"

        item_lista_servico = find_text(root, [
            ".//{*}Servico//{*}ItemListaServico",
            ".//{*}ItemListaServico",
        ], default="")

        ctribnac = find_text(root, [
            ".//{*}cServ//{*}cTribNac",
            ".//{*}cTribNac",
        ], default="")

        xtribnac = find_text(root, [
            ".//{*}cServ//{*}xTribNac",
            ".//{*}xTribNac",
        ], default="").strip()

        xtribmun = find_text(root, [
            ".//{*}cServ//{*}xTribMun",
            ".//{*}xTribMun",
        ], default="").strip()

        descricao_servico = find_text(root, [
            ".//{*}Servico//{*}Discriminacao",
            ".//{*}Discriminacao",
            ".//{*}xDescServ",
            ".//{*}cServ//{*}xDescServ",
        ], default="").strip()

        ctribnac = normalize_digits(ctribnac)
        item_lc_final = ""

        # Escolhe a melhor descrição tributária disponível:
        # xTribNac é descartado quando contém "(VETADO)" ou "sem a incidência"
        _xtribnac_lower = xtribnac.lower() if xtribnac else ""
        _xtribnac_vetado = (
            not xtribnac
            or "vetado" in _xtribnac_lower
            or "sem a incidência" in _xtribnac_lower
            or "sem a incidencia" in _xtribnac_lower
        )
        _desc_trib = xtribnac if not _xtribnac_vetado else (xtribmun or xtribnac)

        if item_lista_servico:
            item_lc_final = normalize_digits(item_lista_servico)[:4]
        elif ctribnac:
            if _desc_trib:
                item_lc_final = f"{ctribnac} - {_desc_trib}"
            else:
                item_lc_final = normalize_digits(ctribnac)

        if item_lc_final and not item_lc_valido(item_lc_final):
            item_lc_final = ""

        # Descrição do serviço: prefere xTribNac (se útil) > xTribMun > Discriminação
        _xtribnac_util = xtribnac if not _xtribnac_vetado else ""
        descricao_servico = _xtribnac_util or xtribmun or descricao_servico

        uf = find_text(root, [
            ".//{*}PrestadorServico//{*}Endereco//{*}Uf",
            ".//{*}Prestador//{*}Endereco//{*}Uf",
            ".//{*}Uf",
            ".//{*}emit//{*}enderNac//{*}UF",
            ".//{*}emit//{*}UF",
        ], default="")

        dt_emissao = find_text(root, [
            ".//{*}CompNfse//{*}Nfse//{*}InfNfse//{*}DataEmissao",
            ".//{*}Nfse//{*}InfNfse//{*}DataEmissao",
            ".//{*}InfNfse//{*}DataEmissao",
            ".//{*}infNFSe//{*}DPS//{*}infDPS//{*}dCompet",
            ".//{*}DPS//{*}infDPS//{*}dCompet",
            ".//{*}infDPS//{*}dCompet",
            ".//{*}infNFSe//{*}DPS//{*}infDPS//{*}dhEmi",
            ".//{*}DPS//{*}infDPS//{*}dhEmi",
            ".//{*}infDPS//{*}dhEmi",
        ], default="")

        dt_fmt = ""
        if dt_emissao:
            try:
                dt_raw = dt_emissao.split("T")[0]
                dt_fmt = datetime.strptime(dt_raw, "%Y-%m-%d").strftime("%d%m%Y")
            except (ValueError, IndexError):
                dt_fmt = ""

        chave_nfse = find_text(root, [
            ".//{*}CompNfse//{*}Nfse//{*}InfNfse//{*}CodigoVerificacao",
            ".//{*}Nfse//{*}InfNfse//{*}CodigoVerificacao",
            ".//{*}InfNfse//{*}CodigoVerificacao",
            ".//{*}infNFSe//{*}DPS//{*}infDPS//{*}id",
            ".//{*}DPS//{*}infDPS//{*}id",
            ".//{*}infDPS//{*}id",
        ], default="").replace("URN:prop:SefazNacional:nfse:id:", "").strip()

        reg_ap_trib_sn = find_text(root, [
            ".//{*}infDPS//{*}regApTribSN",
            ".//{*}DPS//{*}infDPS//{*}regApTribSN",
            ".//{*}regApTribSN",
        ], default="")
        regime_esp_trib = find_text(root, [
            ".//{*}InfNfse//{*}RegimeEspecialTributacao",
            ".//{*}RegimeEspecialTributacao",
            ".//{*}Nfse//{*}InfNfse//{*}RegimeEspecialTributacao",
        ], default="")
        eh_mei = (reg_ap_trib_sn.strip() == "3") or (regime_esp_trib.strip() == "5")

        dados = {
            "padrao": padrao,
            "numero": numero,
            "vlr_trib": vlr_trib,
            "vlr_doc": vlr_doc,
            "cnpj_p": cnpj_p,
            "razao_p": razao_p,
            "im_p": im_p,
            "iss_ret": iss_ret,
            "iss_ret_origem": iss_ret_origem,
            "uf": uf,
            "codigo_municipio": codigo_municipio,
            "aliq_val": aliq_val,
            "dt_fmt": dt_fmt,
            "item_lc_final": item_lc_final,
            "descricao_servico": descricao_servico,
            "cep": cep,
            "endereco": endereco,
            "numero_end": numero_end,
            "bairro": bairro,
            "chave_nfse": chave_nfse,
            "eh_mei": eh_mei,
        }

        if padrao == "desconhecido":
            return "desconhecido", dados

        obrigatorios = ["numero", "vlr_doc", "cnpj_p", "dt_fmt", "codigo_municipio"]
        faltando = [c for c in obrigatorios if not has_value(dados.get(c))]
        if faltando:
            dados["_faltando"] = faltando
            return "incompleto", dados

        return "completo", dados

    except Exception as e:
        return "erro", {"_erro": str(e)}


def extrair_cabecalho_info(root):
    im_tomador = find_text(root, [
        ".//{*}TomadorServico//{*}IdentificacaoTomador//{*}InscricaoMunicipal",
        ".//{*}toma//{*}IM",
        ".//{*}toma//{*}InscricaoMunicipal",
        ".//{*}CNPJ/../IM",
    ], default="")

    razao_tomador = find_text(root, [
        ".//{*}TomadorServico//{*}RazaoSocial",
        ".//{*}toma//{*}xNome",
    ], default="")

    mun_tomador = find_text(root, [
        ".//{*}DeclaracaoPrestacaoServico//{*}InfDeclaracaoPrestacaoServico//{*}TomadorServico//{*}Endereco//{*}CodigoMunicipio",
        ".//{*}TomadorServico//{*}Endereco//{*}CodigoMunicipio",
        ".//{*}infDPS//{*}toma//{*}end//{*}endNac//{*}cMun",
        ".//{*}DPS//{*}infDPS//{*}toma//{*}end//{*}endNac//{*}cMun",
        ".//{*}toma//{*}end//{*}endNac//{*}cMun",
    ], default="")

    data_emissao = find_text(root, [
        ".//{*}InfNfse//{*}DataEmissao",
        ".//{*}DataEmissao",
        ".//{*}dhProc",
        ".//{*}dhEmi",
    ], default="")

    return im_tomador, razao_tomador, data_emissao, mun_tomador
