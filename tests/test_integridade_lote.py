"""Uma declaracao nao pode sair com nota a mais (cancelada) nem a menos (perdida)
sem que o resultado da empresa acuse isso."""
import queue
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import services.autmais_api as api
from services.autmais_api import AutmaisAPIError, baixar_xmls_da_empresa
from services.batch_orchestrator import BatchOrchestrator
from services.dmste_processor import processar_empresa_dmste
from services.issnet_lote import ERRO, REVISAO, executar_lote
from services.processor import ProcessorResult, WorkflowProcessor


class FakeCliente:
    def __init__(self, notas, cnpj="00000000000191"):
        self.notas, self.cnpj = notas, cnpj

    def buscar_cnpj_por_cod(self, cod):
        return self.cnpj

    def listar_notas(self, cnpj, ano_mes):
        return iter(self.notas)

    def baixar_xml(self, url):
        if "quebrada" in url:
            raise AutmaisAPIError("Download XML falhou (500)")
        return "<xml/>"


def _baixar(notas, **kw):
    with patch.object(api, "get_cliente", return_value=FakeCliente(notas)):
        return baixar_xmls_da_empresa("1", "2026-09", **kw)


def _processor():
    return WorkflowProcessor(lambda m: None, lambda t: None, lambda a, t: None, None)


# --- Download -------------------------------------------------------------

def test_nota_cancelada_nao_entra_mesmo_com_url_xml():
    # Formato real da API: `nota_cancelada` = 1 ou campo ausente, sempre com url_xml.
    canceladas = []
    xmls = _baixar(
        [{"_id": "viva", "url_xml": "http://ok"},
         {"_id": "morta", "url_xml": "http://ok", "nota_cancelada": 1,
          "url_xml_cancel": "http://cancel"}],
        canceladas_out=canceladas,
    )
    assert list(xmls) == ["viva.xml"]
    assert canceladas == ["morta.xml"]


def test_url_xml_cancel_sozinha_tambem_indica_cancelamento():
    assert _baixar([{"_id": "a", "url_xml": "http://ok", "url_xml_cancel": "http://c"}]) == {}


def test_nota_cancelada_zero_nao_e_cancelada():
    assert list(_baixar([{"_id": "a", "url_xml": "http://ok", "nota_cancelada": 0,
                          "url_xml_cancel": ""}])) == ["a.xml"]


def test_download_falho_e_nota_sem_url_sao_registrados():
    falhas = []
    xmls = _baixar(
        [{"_id": "boa", "url_xml": "http://ok"},
         {"_id": "ruim", "url_xml": "http://quebrada"},
         {"_id": "semurl", "url_xml": ""}],
        falhas_out=falhas,
    )
    assert list(xmls) == ["boa.xml"]
    assert {nome for nome, _ in falhas} == {"ruim.xml", "semurl.xml"}


def test_nenhum_xml_baixado_e_erro_e_nao_empresa_vazia():
    with pytest.raises(AutmaisAPIError):
        _baixar([{"_id": "ruim", "url_xml": "http://quebrada"}])


def test_empresa_fora_do_cadastro_e_erro_e_nao_empresa_vazia():
    with patch.object(api, "get_cliente", return_value=FakeCliente([], cnpj=None)):
        with pytest.raises(AutmaisAPIError):
            baixar_xmls_da_empresa("999", "2026-09")


# --- Processor ------------------------------------------------------------

def test_falha_da_api_nao_vira_none():
    with patch("services.processor.baixar_xmls_da_empresa",
               side_effect=AutmaisAPIError("503")):
        with pytest.raises(AutmaisAPIError):
            _processor().processar("1", "092026")


def test_relatorio_mostra_cancelada_e_falha_e_so_a_falha_e_pendencia():
    def baixar(cod, vig, log_fn=None, chaves_out=None, falhas_out=None, canceladas_out=None):
        falhas_out.append(("ruim.xml", "Download XML falhou (500)"))
        canceladas_out.append("morta.xml")
        return {"boa.xml": "<xml/>"}

    p = _processor()
    with patch("services.processor.baixar_xmls_da_empresa", baixar), \
         patch.object(p, "_processar_notas", return_value=({}, [], {}, {})), \
         patch.object(p, "_gerar_cabecalho", return_value=("", "", "", "")):
        r = p.processar("1", "092026")

    status = {row[0]: (row[4], row[6]) for row in r.relatorio}
    assert status["morta.xml"] == ("Ignorada", "Nota cancelada")
    assert status["ruim.xml"][0] == "Erro"
    assert [row[0] for row in r.pendencias] == ["ruim.xml"]


# --- Orquestrador e lote --------------------------------------------------

def _resultado(*status_notas):
    relatorio = [[f"{i}.xml", "", "", "", s, "extract", "motivo"]
                 for i, s in enumerate(status_notas)]
    return ProcessorResult({"k": "2;1"}, relatorio, {}, "1", "E", "cab\n2;1")


def _processor_fake(resultado):
    fake = MagicMock()
    fake.return_value.processar.return_value = resultado
    return fake


@pytest.mark.parametrize("status", ["Erro", "Manual Review", "Cancelado"])
def test_nota_perdida_reprova_empresa_e_nao_marca_baixadas(tmp_path, status):
    q = queue.Queue()
    fake = _processor_fake(_resultado("OK", status))
    with patch("services.batch_orchestrator.WorkflowProcessor", fake):
        BatchOrchestrator(q).run([{"cod": "1", "razao": "E"}], "092026", tmp_path,
                                 marcar_baixadas=True)
    msgs = [q.get_nowait() for _ in range(q.qsize())]
    done = next(m for m in msgs if m[0] == "company_done")
    assert done[2] == "error"
    assert "1 nota" in done[5]
    fake.return_value.marcar_baixadas_na_autmais.assert_not_called()


def test_notas_ignoradas_de_proposito_nao_reprovam(tmp_path):
    q = queue.Queue()
    with patch("services.batch_orchestrator.WorkflowProcessor",
               _processor_fake(_resultado("OK", "Ignorada"))):
        BatchOrchestrator(q).run([{"cod": "1", "razao": "E"}], "092026", tmp_path)
    msgs = [q.get_nowait() for _ in range(q.qsize())]
    assert next(m for m in msgs if m[0] == "company_done")[2] == "ok"


def _lote(tmp_path, processar):
    empresa = SimpleNamespace(cod="1", nome="E", municipio="")
    with patch("services.batch_orchestrator.WorkflowProcessor") as fake:
        fake.return_value.processar.side_effect = processar
        return executar_lote([empresa], "092026", tmp_path, {"1": "b"}).empresas[0]


def test_lote_nao_deposita_empresa_com_nota_perdida(tmp_path):
    r = _lote(tmp_path, lambda *a, **k: _resultado("OK", "Erro"))
    assert r.status == ERRO and not r.apta_para_deposito


def test_lote_mantem_revisao_quando_gate_foi_acionado(tmp_path):
    def processar(*a, **k):
        from services import batch_orchestrator as bo
        callback = bo.WorkflowProcessor.call_args.kwargs["abrir_tela_manual_fn"]
        assert callback({}, "chave") is None
        return _resultado("OK", "Cancelado")

    r = _lote(tmp_path, processar)
    assert r.status == REVISAO and r.revisoes == ["chave"]


# --- DMS-e ----------------------------------------------------------------

def _dmste(tmp_path, xmls, falhas=(), canceladas=(), marcar=False):
    def baixar(cod, vig, chaves_out=None, falhas_out=None, canceladas_out=None):
        falhas_out.extend(falhas)
        canceladas_out.extend(canceladas)
        if chaves_out is not None:
            chaves_out.append("id")
        return xmls

    cli = MagicMock()
    with patch("services.dmste_processor.baixar_xmls_da_empresa", baixar), \
         patch("services.dmste_processor.get_cliente_autmais", return_value=cli), \
         patch("services.dmste_processor.extrair_dados_python",
               return_value=("completo", {"dt_fmt": "01092026"})), \
         patch("services.dmste_processor.build_dmste_row", return_value={"ALIQUOTA": "3,00"}), \
         patch("services.dmste_processor.escrever_csv_dmste"):
        return processar_empresa_dmste("1", "E", "CRIXAS", "092026", tmp_path, marcar), cli


def test_dmste_conta_falha_e_cancelada_e_nao_marca_baixadas(tmp_path):
    r, cli = _dmste(tmp_path, {"a.xml": "<x/>"}, falhas=[("b.xml", "500")],
                    canceladas=["c.xml"], marcar=True)
    assert (r.status, r.notas_erro, r.notas_canceladas) == ("ok", 1, 1)
    cli.marcar_baixadas.assert_not_called()


def test_dmste_sem_linhas_por_falha_e_erro_e_nao_vazio(tmp_path):
    def baixar(cod, vig, chaves_out=None, falhas_out=None, canceladas_out=None):
        return {"a.xml": "<x/>"}

    with patch("services.dmste_processor.baixar_xmls_da_empresa", baixar), \
         patch("services.dmste_processor.extrair_dados_python", return_value=("erro", {})):
        r = processar_empresa_dmste("1", "E", "CRIXAS", "092026", tmp_path)
    assert r.status == "erro"
