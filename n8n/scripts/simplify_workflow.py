"""Simplifica workflow n8n NFS-e: remove Supabase/HuggingFace/Drive,
embute lista LC 116 no system prompt do classificador."""
import json
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
WORKFLOW_IN = BASE / "backups" / "Tk9ekKdc6OsQsII4_pre_simplify.json"
WORKFLOW_OUT = BASE / "backups" / "Tk9ekKdc6OsQsII4_simplified.json"
LC116_MD = BASE / "lc116_prompt.md"

NEW_USER_PROMPT = """=Analise os seguintes dados extraidos do XML da NFS-e:

Item LC: {{ $json.item_lc }}
Descricao do servico (x_desc_serv): {{ $json.x_desc_serv }}
Discriminacao completa: {{ $json.discriminacao }}
Codigo tributario nacional (c_trib_nac): {{ $json.c_trib_nac }}
Descricao tributaria nacional (x_trib_nac): {{ $json.x_trib_nac }}
Descricao tributaria municipal (x_trib_mun): {{ $json.x_trib_mun }}
Descricao NBS (x_nbs): {{ $json.x_nbs }}

INSTRUCOES OBRIGATORIAS:
1. Consulte a REFERENCE TABLE - LC 116/2003 ITEMS do system prompt.
2. Escolha o item MAIS ESPECIFICO possivel da lista. Nao caia em codigos genericos (17.01, 14.02, 6.05, etc) quando existir um item que descreve exatamente o servico.
3. Regras rigidas (sempre aplicar quando descricao bater):
   - Contabilidade / servicos contabeis / escrituracao / apuracao de impostos -> 1719 (nunca 1701)
   - Auditoria -> 1716 (nunca 1701)
   - Advocacia / servicos juridicos / assessoria juridica -> 1714 (nunca 1701)
   - Pericia / laudo / exame tecnico -> 1709
   - Consultoria economica / financeira -> 1720
   - Estatistica -> 1721
   - Cobranca -> 1722
   - Fornecimento de mao-de-obra temporaria -> 1705
   - Assessoria ou consultoria geral (sem area especifica) -> 1701
4. Retorne apenas o JSON obrigatorio conforme schema definido no Parser Estruturado."""

NODES_TO_REMOVE = {
    "Supabase: Busca LC 116",
    "Embeddings HuggingFace (Busca)",
    "Download Base LC 116 (Drive)",
    "Extrair JSON LC 116",
    "Separar Itens LC",
    "Supabase: Inserir LC 116",
    "Embeddings HuggingFace (Inserção)",
    "Carregar Documento LC",
    "Dividir Texto em Chunks",
    "Sticky Note",  # Configuracao para consulta da IA na Base de dados
}

CLASSIFIER_NAME = "IA Classificar Item LC 116"


def build_new_system_prompt(lc116_md: str) -> str:
    return f"""=You are a Brazilian Tax Law Specialist with strict expertise in Complementary Law 116/2003.

INPUT DATA
Raw LC Item: {{{{ $json.item_lc }}}}
Service Description (x_desc_serv): {{{{ $json.x_desc_serv }}}}
Full Discrimination (discriminacao): {{{{ $json.discriminacao }}}}
National Tax Code (c_trib_nac): {{{{ $json.c_trib_nac }}}}
National Tax Description (x_trib_nac): {{{{ $json.x_trib_nac }}}}
Municipal Tax Description (x_trib_mun): {{{{ $json.x_trib_mun }}}}
NBS Description (x_nbs): {{{{ $json.x_nbs }}}}

PARSING RULE
The field 'Raw LC Item' arrives in the format "CODE - DESCRIPTION" (e.g., "1402 - Assistencia tecnica").
Split by " - ". LEFT = LC code. RIGHT = description.
If no " - " separator, treat entire field as description with no code.

6-DIGIT CODE RULE
If LC code has 6 digits (e.g., "170500"), use only the FIRST 4 digits ("1705" -> "17.05").

USING ALL AVAILABLE DESCRIPTIONS
Use ALL fields together to make the best classification:
- x_desc_serv: official service description tag from the XML
- discriminacao: full free-text discrimination
- c_trib_nac: national tax code (NBS-based)
- x_trib_nac: national tax description
- x_trib_mun: municipal tax description
- x_nbs: NBS description - use as a strong signal for classification

REFERENCE TABLE - LC 116/2003 ITEMS
The complete list of official items (codigo: descricao) is below. USE THIS LIST as the authoritative source when picking item_lc_final. Do not invent codes not present here.

{lc116_md}

SPECIFICITY RULE (READ THIS BEFORE ANY OTHER STEP)
Always pick the MOST SPECIFIC item from the REFERENCE TABLE. NEVER default to a generic parent item when a specific subitem exists.

Hard mappings (ALWAYS apply when the term appears in any description field):
- "contabilidade", "escrituracao", "apuracao de impostos", "servicos contabeis" -> item_lc_final "1719" (17.19), item_lc_formatted "17.19". NEVER 17.01.
- "auditoria" -> "1716" (17.16). NEVER 17.01.
- "advocacia", "servicos juridicos", "assessoria juridica" -> "1714" (17.14). NEVER 17.01.
- "pericia", "laudo tecnico", "exame tecnico" -> "1709" (17.09).
- "consultoria economica", "consultoria financeira" -> "1720" (17.20).
- "estatistica" -> "1721" (17.21).
- "cobranca" (servicos de cobranca em geral) -> "1722" (17.22).
- "fornecimento de mao-de-obra", "mao de obra temporaria" -> "1705" (17.05).
- "recrutamento", "selecao de mao-de-obra" -> "1704" (17.04).
- Only fall back to 1701 (assessoria/consultoria generica) when NONE of the above apply and no other more specific subitem matches.

Analogous specificity rules apply to all other groups: prefer subitems over parents (1.05 over 1, 15.14 over 15, etc.).

CLASSIFICATION LOGIC (STRICT PRIORITY ORDER)

STEP 0 - CHECK FOR SPECIFIC IDENTIFIABLE SERVICE FIRST

Before applying any override, check if x_desc_serv, discriminacao or x_nbs describes a SPECIFIC service that can be matched to an LC 116 item.

If YES (specific service identified):
- IGNORE x_trib_nac "sem incidencia" flags
- Classify based on the actual service description
- Match against the REFERENCE TABLE above by semantic proximity
- Known examples (apply directly):
  * x_nbs="Servicos de cartao de credito" OR x_desc_serv contains "gestao frota" OR "cartao frota" -> 15.14 (item_lc_final: "1514")
  * x_desc_serv="Software TEF" OR x_nbs contains "licenciamento de software" -> 1.05 (item_lc_final: "0105")
  * x_nbs="Agenciamento de seguros" -> 10.01 (item_lc_final: "1001")
- Set method: "INVOICE_CODE_VALIDATED"
- Set confidence_score: 0.95, confidence_level: "High"

If x_desc_serv, discriminacao and x_nbs are ALL empty or generic:
- Apply STEP 1 below

STEP 1 - VETADO / LOCACAO DE BENS MOVEIS

Apply ONLY when all descriptions are empty or generic AND any field contains:
- "Vetado", "(Vetado)", "Locacao de bens moveis", "Locacoes de bens moveis"

If YES:
- Return item_lc_final: "0304", item_lc_formatted: "03.04"
- Set method: "SPECIAL_OVERRIDE_VETADO"
- Set confidence_level: "High", confidence_score: 1.00
- Set justificativa: "Servico vetado ou locacao de bens moveis. Classificado como 0304 conforme regra interna Crosara Contabilidade."

STEP 2 - Validate the LC Code from the Invoice

If LC code present, check it exists in the REFERENCE TABLE.
If VALID: confirm item, confidence_score >= 0.95, method: "INVOICE_CODE_VALIDATED".

STEP 3 - Code Invalid or Absent, Match by Description

Discard code. Analyze ALL descriptions including x_nbs.
Pick the item from the REFERENCE TABLE whose descricao best matches the service.
Set method: "SEMANTIC_SEARCH".
Assign confidence_score based on match quality.

STEP 4 - Conflict Between Code and Description

If code valid but descriptions point to clearly different service:
- Use descriptions to pick item from REFERENCE TABLE
- Set method: "SEMANTIC_SEARCH_CONFLICT"

LC ITEM FORMAT RULE (MANDATORY)
1.05 -> "0105" | 7.09 -> "0709" | 8.02 -> "0802" | 17.12 -> "1712" | 15.14 -> "1514" | 16.02 -> "1602"
MAXIMUM: cannot exceed "4001".

OUTPUT RULES
Return ONLY a valid JSON object. No markdown, no code fences.
The output schema is defined in the connected Structured Output Parser and includes:
- item_lc_final (string, e.g. "0105", "1514")
- item_lc_formatted (string, e.g. "01.05", "15.14")
- method (string enum: INVOICE_CODE_VALIDATED | SEMANTIC_SEARCH | SEMANTIC_SEARCH_CONFLICT | SPECIAL_OVERRIDE_VETADO)
- justificativa (string - short technical justification in Portuguese)
- confidence_score (number 0-1)
- confidence_level (string enum: Low | Medium | High)"""


def main():
    wf = json.loads(WORKFLOW_IN.read_text(encoding="utf-8"))
    lc116_md = LC116_MD.read_text(encoding="utf-8")

    # Filtra nodes
    nodes_removed = []
    kept_nodes = []
    for node in wf["nodes"]:
        if node["name"] in NODES_TO_REMOVE:
            nodes_removed.append(node["name"])
            continue
        # Modifica classificador
        if node["name"] == CLASSIFIER_NAME:
            new_prompt = build_new_system_prompt(lc116_md)
            node["parameters"]["options"]["systemMessage"] = new_prompt
            node["parameters"]["text"] = NEW_USER_PROMPT
        kept_nodes.append(node)
    wf["nodes"] = kept_nodes

    # Limpa connections
    new_connections = {}
    remaining_names = {n["name"] for n in kept_nodes}
    for source_name, ports in wf["connections"].items():
        if source_name in NODES_TO_REMOVE:
            continue
        # Limpa cada porta / cada destino
        cleaned_ports = {}
        for port_key, arrays in ports.items():
            # Bug: chave "0" no classificador com destinos que nao existem
            if source_name == CLASSIFIER_NAME and port_key == "0":
                continue
            cleaned_arrays = []
            for arr in arrays:
                cleaned = [
                    conn for conn in arr
                    if conn.get("node") in remaining_names
                ]
                cleaned_arrays.append(cleaned)
            if any(cleaned_arrays):
                cleaned_ports[port_key] = cleaned_arrays
        if cleaned_ports:
            new_connections[source_name] = cleaned_ports
    wf["connections"] = new_connections

    WORKFLOW_OUT.write_text(json.dumps(wf, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"Nodes removidos: {len(nodes_removed)}")
    for n in nodes_removed:
        print(f"  - {n}")
    print(f"Nodes restantes: {len(kept_nodes)}")
    print(f"Novo prompt do classificador: {len(build_new_system_prompt(lc116_md))} chars")
    print(f"Output: {WORKFLOW_OUT}")


if __name__ == "__main__":
    main()
