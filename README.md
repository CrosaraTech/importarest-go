<p align="center">
  <img src="assets/logo_importarest.png" alt="ImportaREST GO" width="360">
</p>

<h1 align="center">ImportaREST GO</h1>

<p align="center">
  <strong>Importação inteligente de NFS-e para o sistema REST</strong><br>
  Processamento automatizado de XMLs fiscais com classificação de serviços por IA.
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.10+-blue?logo=python&logoColor=white" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/plataforma-Windows-0078D6?logo=windows&logoColor=white" alt="Windows">
  <img src="https://img.shields.io/badge/IA-N8N%20%2B%20LLM-blueviolet?logo=n8n&logoColor=white" alt="N8N + LLM">
  <img src="https://img.shields.io/badge/status-produção-brightgreen" alt="Em produção">
</p>

---

## O Problema

Escritórios contábeis que utilizam o **sistema REST** precisam importar notas fiscais de serviço eletrônicas (NFS-e) manualmente — um processo repetitivo, demorado e propenso a erros. Cada município emite XMLs em formatos diferentes, os campos variam entre prefeituras, e a classificação do serviço (Item da Lista Complementar) exige conhecimento técnico-fiscal.

## A Solução

O **ImportaREST GO** automatiza todo o fluxo: lê os XMLs, extrai os dados fiscais, classifica o serviço usando inteligência artificial e gera o arquivo TXT pronto para importação no REST — em segundos.

---

## Funcionalidades

| Recurso | Descrição |
|---------|-----------|
| **Multi-padrão** | Compatível com XMLs nos padrões **ABRASF** e **Nacional** (NFS-e Nacional), cobrindo a grande maioria dos municípios brasileiros |
| **Classificação por IA** | Integração com pipeline N8N + LLM para identificar automaticamente o **Item LC** e **DDD** do serviço a partir da descrição |
| **Revisão manual assistida** | Quando a IA não atinge confiança suficiente, apresenta tela de revisão com os dados pré-preenchidos para validação humana |
| **Notas MEI** | Processamento específico para notas de Microempreendedor Individual (MEI) de Goiânia, com toggle na interface |
| **Separação por vigência** | Notas com data de emissão fora do mês selecionado são automaticamente separadas em arquivos TXT distintos |
| **Consulta IBGE** | Resolução automática do nome do município a partir do código IBGE via API oficial |
| **Detecção de cancelamentos** | Identifica e ignora automaticamente eventos de cancelamento presentes na pasta |
| **Relatório de processamento** | Gera relatório CSV detalhado com o status de cada nota (processada, erro, ignorada) e motivo |
| **Interface moderna** | GUI desktop com indicador de progresso circular, feedback em tempo real e fluxo intuitivo |

---

## Como Funciona

```
📂 Pasta de XMLs          ➜  📖 Leitura e parsing         ➜  🔍 Extração de dados
(ABRASF / Nacional)          (detecção automática)            (50+ campos fiscais)
                                                                      │
                                                                      ▼
📄 Arquivo TXT             ⬅  🧩 Montagem do TXT           ⬅  🤖 Classificação IA
(pronto para REST)             (cabeçalho + linhas)             (Item LC + DDD)
```

1. O usuário informa o **código da empresa** e a **vigência** (mês/ano)
2. O sistema localiza a pasta de XMLs correspondente no drive compartilhado
3. Cada XML é parseado, com detecção automática do padrão (ABRASF ou Nacional)
4. Os dados fiscais são extraídos: prestador, tomador, valores, impostos, descrição do serviço
5. A descrição é enviada ao pipeline de IA para classificação do serviço
6. O arquivo TXT é montado no formato exigido pelo sistema REST
7. O usuário salva o arquivo e importa diretamente no REST

---

## Stack Tecnológica

| Camada | Tecnologia |
|--------|-----------|
| **Linguagem** | Python 3.10+ |
| **Interface** | Tkinter + ttkbootstrap + Pillow |
| **Parsing XML** | xml.etree.ElementTree (stdlib) |
| **IA / Classificação** | N8N (workflow automation) + LLM |
| **API Externa** | IBGE Localidades (resolução de municípios) |
| **Relatórios** | CSV nativo |

---

## Arquitetura

```
importarest-go/
├── main.py                  # Entry point
├── config.py                # Configurações, paths e paleta de cores
├── core/                    # Lógica de negócio pura
│   ├── xml_parser.py        # Parsing XML e detecção de padrão
│   ├── extractor.py         # Extração de 50+ campos das NFS-e
│   ├── validators.py        # Validações e regras fiscais
│   ├── formatters.py        # Formatação de campos (data, UF, alíquota)
│   └── txt_builder.py       # Montagem das linhas do TXT de importação
├── services/                # Integrações externas
│   ├── ibge.py              # Consulta de municípios via API IBGE
│   ├── n8n_client.py        # Comunicação com webhook N8N (IA)
│   ├── processor.py         # Orquestrador do fluxo de processamento
│   └── report.py            # Geração de relatório CSV
└── ui/                      # Interface gráfica
    ├── components.py        # Widgets reutilizáveis (botões, entries, progresso)
    ├── dialogs.py           # Telas de preenchimento manual
    └── app.py               # Janela principal e fluxo de interação
```

---

## Requisitos

- **Python 3.10** ou superior
- **Windows 10/11**
- Acesso ao drive compartilhado com os XMLs
- Dependências Python:

```bash
pip install ttkbootstrap Pillow requests
```

---

## Uso

```bash
python main.py
```

1. Insira o **código da empresa** cadastrada no REST
2. Insira a **vigência** no formato `MMYYYY` (ex: `012026` para janeiro/2026)
3. Marque **"Gerar notas MEI"** se desejar incluir notas de MEI de Goiânia
4. Clique em **INICIAR IMPORTAÇÃO**
5. Acompanhe o progresso em tempo real
6. Ao finalizar, clique em **BAIXAR TXT** e salve o arquivo
7. Importe o TXT no sistema REST

---

## Padrões de NFS-e Suportados

| Padrão | Cobertura | Identificação |
|--------|-----------|---------------|
| **ABRASF** | Maioria dos municípios brasileiros (São Paulo, BH, Curitiba, Goiânia, etc.) | Tags `CompNfse`, `InfNfse`, `Rps` |
| **Nacional** | Municípios migrados para o padrão NFS-e Nacional (Receita Federal) | Tags `NFSe`, `infNFSe`, `emit`, `trib` |

---

<p align="center">
  <img src="assets/logo_crosara.png" alt="Crosara Tech" width="160">
  <br><br>
  <strong>Crosara Tech</strong><br>
  Tecnologia contábil que transforma rotina em resultado.
</p>
