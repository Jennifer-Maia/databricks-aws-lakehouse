# 04 · Arquitetura medalhão: Auto Loader, PySpark, Jobs serverless e Bundles

## Em uma frase

O dado passa por **camadas de qualidade crescente**: **Bronze** (cru), **Silver** (limpo) e **Gold** (pronto para o negócio). Um **job serverless** com 4 tarefas (Bronze → Silver → Gold → Qualidade) faz essa passagem, e um **bundle** leva **o mesmo código** para DEV e PROD.

> Primeiro tentamos um **pipeline declarativo** (Lakeflow Declarative Pipelines, o antigo DLT), mas ele não rodou nesta conta. O motivo e como isso foi investigado estão no [05 · Troubleshooting](05-troubleshooting.md). Saber explicar essa troca é um ótimo assunto de entrevista.

## As camadas deste projeto

```text
/Volumes/econ_<env>/landing/bcb/serie=*/...json        (arquivos da Lambda)
        │  01_bronze · Auto Loader (cloudFiles) + trigger(availableNow): só arquivos novos
        ▼
bronze.bcb_series_raw                  1 linha por arquivo · JSON intacto + _arquivo_origem, _carregado_em
        │  02_silver · explode · tipagem · regras de qualidade · dedup por (serie, data)
        ▼
silver.bcb_observacoes                 1 linha por (serie, data) · DATE e DECIMAL
silver.bcb_observacoes_rejeitadas      quarentena: linhas inválidas + _motivo_rejeicao
        │  03_gold · SELECTs em src/sql/gold/*.sql
        ▼
gold.cambio_diario                     dólar/euro por dia, variação %, média móvel 30d
gold.indicadores_mensais               câmbio + Selic + CDI acumulado + IPCA 12m + juro real
gold.ultimos_valores                   último valor de cada série (cartões do dashboard)
        │  04_qualidade · o job FALHA se uma regra quebrar
```

| Camada | Pergunta que responde | Regra de ouro |
|---|---|---|
| **Bronze** | "O que exatamente chegou, e quando?" | Nunca transformar. Só acrescentar metadados. Permite reprocessar tudo. |
| **Silver** | "Qual é o valor correto de cada série em cada dia?" | Tipos certos, sem duplicatas, inválidos em quarentena. |
| **Gold** | "Quanto o dólar subiu no mês? Qual o juro real?" | Modelada para o consumo, com nomes que o negócio entende. |

## Auto Loader + `availableNow`: streaming com custo de batch

```python
spark.readStream.format("cloudFiles")                       # Auto Loader
    .option("cloudFiles.format", "json")
    .option("cloudFiles.schemaLocation", ".../_schema")     # guarda o schema inferido
    .option("cloudFiles.schemaHints", BRONZE_SCHEMA_HINTS)  # força os tipos que importam
    .load("/Volumes/econ_dev/landing/bcb/")
    .writeStream.option("checkpointLocation", ".../_checkpoint")  # guarda QUAIS arquivos já leu
    .trigger(availableNow=True)                             # processa o que tem e PARA
    .toTable("econ_dev.bronze.bcb_series_raw")
```

- O **checkpoint** (num volume `bronze._checkpoints`) garante que cada arquivo é lido **exatamente uma vez**, mesmo que o job rode 10 vezes.
- **`availableNow`** transforma o streaming em batch incremental: liga, processa os arquivos novos e desliga. Não fica um cluster ligado esperando.

## Silver: lógica separada do I/O (e testada)

Os notebooks só leem e gravam. As regras ficam em [`platform/src/econ/transforms.py`](../../platform/src/econ/transforms.py) e são testadas com **PySpark local** em [`platform/tests/test_transforms.py`](../../platform/tests/test_transforms.py):

| Regra | Função | Teste |
|---|---|---|
| 1 arquivo → N observações; texto → DATE/DECIMAL | `explodir_e_tipar` | `test_silver_tipa_e_explode` |
| Data inválida, valor inválido, data futura → quarentena | `motivo_rejeicao` | `test_silver_manda_invalidos_para_quarentena` |
| Mesma (série, data) várias vezes → fica a coleta mais recente | `deduplicar` | `test_silver_deduplica_ficando_com_a_coleta_mais_recente` |

**Por que quarentena e não só apagar?** Porque um dado rejeitado é informação: se a API mudar de formato, a tabela `bcb_observacoes_rejeitadas` mostra o quê e de qual arquivo veio, com o motivo.

## Gold: SQL versionado e testável

Cada arquivo em [`platform/src/sql/gold/`](../../platform/src/sql/gold) é **um `SELECT`**. O nome do arquivo é o nome da tabela, e a 1ª linha (`-- comment:`) vira o comentário da tabela no Unity Catalog. O notebook `03_gold` faz `CREATE OR REPLACE TABLE gold.<arquivo> AS <SELECT>`. Nos testes, os mesmos SELECTs rodam numa Silver sintética de 13 meses.

### Truques de SQL usados (bons para entrevista)

| Problema | Solução |
|---|---|
| Série em linhas vira colunas | `max(CASE WHEN serie = 'dolar_venda' THEN valor END)` (pivot) |
| Variação diária | `valor / lag(valor) OVER (ORDER BY data) - 1` |
| Média móvel de 30 dias | `avg(...) OVER (ORDER BY data ROWS BETWEEN 29 PRECEDING AND CURRENT ROW)` |
| Valor de fechamento do mês | `max_by(valor, data)` = "o valor da maior data" |
| Agregar só uma série | `max_by(valor, data) FILTER (WHERE serie = 'selic_meta')` |
| Acumular taxas (juros compostos) | `exp(sum(ln(1 + taxa/100))) - 1`, porque somar logaritmos = multiplicar |
| IPCA de 12 meses só se houver 12 meses | `CASE WHEN count(ipca) OVER doze = 12 THEN ... END` |
| Juro real | `(1 + Selic) / (1 + IPCA 12m) - 1` (equação de Fisher) |

## Qualidade: o job falha se algo estiver errado

O notebook [`04_qualidade.py`](../../platform/src/notebooks/04_qualidade.py) verifica: Silver sem duplicatas, as 5 séries presentes, dólar atualizado há no máximo 5 dias, Gold não vazia e menos de 1% de rejeitados. Se uma regra quebrar, um `assert` faz o **job falhar**. A falha fica visível (e pode gerar alerta por e-mail) em vez de o dashboard mostrar dado errado em silêncio.

## Bundle (Declarative Automation Bundle, antigo DAB)

```text
platform/
├── databricks.yml                   # nome, variável catalog e targets dev/prod
├── resources/econ_daily.job.yml     # job: 4 tarefas serverless, agenda 21h (depois da Lambda das 20h)
├── src/
│   ├── econ/transforms.py           # regras (Python/PySpark)
│   ├── notebooks/01_bronze … 04_qualidade
│   └── sql/gold/*.sql               # 1 SELECT por tabela Gold
└── tests/test_transforms.py         # pytest + PySpark local
```

| | `-t dev` | `-t prod` |
|---|---|---|
| Workspace | `lakehouse-dev` | `lakehouse-prod` |
| Parâmetro `catalog` | `econ_dev` | `econ_prod` |
| `mode` | `development`: prefixo `[dev usuário]`, agenda **pausada** | `production`: pasta `/Workspace/Projects/...`, agenda **ativa**, só admins publicam |

```bash
uv run --no-project --with pytest --with "pyspark==4.0.*" pytest tests -q   # TEST
databricks bundle deploy -t dev  && databricks bundle run econ_daily -t dev  # DEV
databricks bundle deploy -t prod && databricks bundle run econ_daily -t prod # PROD (mesmo código)
```

## Resultado da primeira execução (26/11/2026, DEV)

| Tabela | Linhas |
|---|---|
| `bronze.bcb_series_raw` | 5 (1 arquivo por série) |
| `silver.bcb_observacoes` | 3.284 |
| `silver.bcb_observacoes_rejeitadas` | 0 |
| `gold.cambio_diario` | 730 dias |
| `gold.indicadores_mensais` | 35 meses (out/2026: IPCA 12m 4,63%, Selic 13,75%, juro real ≈ 8,72%) |

## Perguntas de entrevista (e como responder)

**"Explique a arquitetura medalhão do seu projeto."**
> Na Bronze guardo o JSON da API como chegou, com o arquivo de origem e o horário de carga, usando Auto Loader com checkpoint para ler cada arquivo uma vez. Na Silver explodo, tipo e deduplico por série e data, ficando com a coleta mais recente, e mando o que é inválido para uma quarentena. Na Gold tenho câmbio diário com variação e média móvel, e uma visão mensal com Selic, CDI acumulado, IPCA 12 meses e juro real.

**"Como você testa um pipeline de dados?"**
> Separo a lógica do I/O: as regras ficam num módulo Python e são testadas com PySpark local e dados sintéticos (dedup, quarentena, juros compostos). As consultas da Gold são arquivos SQL que rodam tanto no Databricks quanto no teste. Em produção, uma tarefa de qualidade faz o job falhar se houver duplicata, série faltando ou dado desatualizado.

**"Streaming ou batch?"**
> Os dois: uso Structured Streaming com Auto Loader, mas com `trigger(availableNow=True)`. Ganho a garantia de exactly-once do checkpoint e pago só o tempo de processamento, como um batch.

**"Por que reescrever a Silver inteira a cada execução, em vez de MERGE?"**
> O volume é pequeno (milhares de linhas), então recalcular é simples, barato e sempre consistente. Com milhões de linhas, eu usaria `MERGE INTO` com a chave (série, data) ou AUTO CDC num pipeline declarativo.

**"Como o mesmo código vai para produção?"**
> Com bundles: código e recursos versionados no Git, e cada target só muda a configuração (workspace, catálogo, modo). O catálogo chega aos notebooks como parâmetro do job.

## Para praticar sozinha depois

1. Abra o job no workspace DEV (**Jobs & Pipelines → [dev ...] econ-daily**) e veja o grafo das 4 tarefas e o output de cada uma.
2. Rode a Lambda (`make backfill ENV=dev START=2026-11-01`) e depois o job. Confirme que a Bronze ganhou 5 linhas, mas a Silver **não** duplicou.
3. Crie `platform/src/sql/gold/selic_vs_cdi.sql` (um SELECT novo), rode os testes e o job: a tabela aparece sozinha, sem mexer em notebook.
