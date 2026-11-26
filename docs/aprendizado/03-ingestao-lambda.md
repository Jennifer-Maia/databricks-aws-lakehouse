# 03 · Ingestão serverless na AWS: Lambda + EventBridge + S3

## Em uma frase

Uma **função Lambda** (código Python que roda sem servidor) é disparada **uma vez por dia** pelo **EventBridge Scheduler**, busca as séries na API do Banco Central e grava o JSON **sem alterar nada** no **S3**. Esse bucket é a "landing zone" que o Databricks lê.

```text
⏰ EventBridge Scheduler ──invoke──► λ econ-ingest-<env> ──HTTPS──► api.bcb.gov.br
   (20h, America/Sao_Paulo)            │
                                       ├──PutObject──► s3://econ-raw-<conta>/<env>/bcb/serie=<nome>/<timestamp>.json
                                       └──logs───────► CloudWatch /aws/lambda/econ-ingest-<env> (7 dias)
```

## Conceitos

| Conceito | O que é | Neste projeto |
|---|---|---|
| **Lambda** | Código que roda sob demanda; você paga por milissegundo de execução | `econ-ingest-dev` e `econ-ingest-prod`, Python 3.12, ARM (Graviton) |
| **Handler** | A função que a AWS chama, `arquivo.funcao` | `handler.lambda_handler` |
| **Evento** | O JSON de entrada da execução | `{}` (diário) ou `{"start_date": "2024-01-01"}` (backfill) |
| **Execution role** | Role IAM que a Lambda assume para acessar outros serviços | Só pode `s3:PutObject` em `<env>/bcb/*` e escrever os próprios logs |
| **EventBridge Scheduler** | Agendador da AWS (cron/rate, com fuso horário) | `cron(0 20 * * ? *)` no fuso de São Paulo |
| **CloudWatch Logs** | Onde ficam os `print`/`logging` da Lambda | Retenção de 7 dias (o padrão é guardar para sempre e cobrar por isso) |
| **Landing / raw** | Primeira parada do dado, exatamente como veio da fonte | JSON com um envelope de metadados |

## Decisões de design (e o porquê)

| Decisão | Por quê |
|---|---|
| **Uma Lambda por ambiente** | A Lambda de DEV *não consegue* gravar em `prod/` (a IAM bloqueia). Isola falhas e testes. |
| **Gravar o dado cru + envelope** | Raw deve ser fiel à fonte para permitir reprocessar. O envelope (`serie`, `codigo_sgs`, `coletado_em`, `fonte_url`) dá rastreabilidade sem mexer em `dados`. |
| **Reler os últimos 7 dias todo dia** | O BCB publica com atraso e às vezes corrige valores. A Silver deduplica por (série, data), então a carga é **idempotente**: rodar 2x não duplica nada. |
| **Backfill pelo mesmo código** | `{"start_date": ...}` faz a carga histórica. Não existe um "script especial" de carga inicial. |
| **Partição `serie=<nome>/` no S3** | Organiza os arquivos e facilita ler uma série só. É o formato Hive, que o Spark entende. |
| **Só biblioteca padrão + boto3** | O `boto3` já vem no runtime da Lambda, então o .zip tem 1 arquivo e não precisa de *layer*. |
| **Retentativa com backoff** | Erros 5xx e timeouts são tentados de novo (2 s, 4 s); 404 do SGS significa "sem dados na janela" (comum no IPCA). |
| **Núcleo testável (`run`)** | Rede e S3 são *injetados* (`fetch`, `put`). Os testes rodam sem internet e sem AWS. |
| **ARM64 (Graviton)** | Cerca de 20% mais barato que x86 para o mesmo código Python. |

## O código

- Lambda: [`ingestion/src/handler.py`](../../ingestion/src/handler.py)
- Testes (pytest, 9 casos): [`ingestion/tests/test_handler.py`](../../ingestion/tests/test_handler.py)
- Infra: [`infra/03-ingestion/main.tf`](../../infra/03-ingestion/main.tf). O provider `archive` empacota o `.zip`, e o `source_code_hash` faz o Terraform republicar a Lambda quando o código muda.

### Comandos úteis

```bash
# Rodar uma vez (execução normal: últimos 7 dias)
aws lambda invoke --function-name econ-ingest-dev --payload '{}' --cli-binary-format raw-in-base64-out /dev/stdout

# Backfill (carga histórica)
aws lambda invoke --function-name econ-ingest-dev --payload '{"start_date":"2024-01-01"}' --cli-binary-format raw-in-base64-out /dev/stdout

# Ver os logs em tempo real
aws logs tail /aws/lambda/econ-ingest-dev --follow

# Ver o que chegou no S3
aws s3 ls s3://econ-raw-<conta>/dev/bcb/ --recursive

# Ver os mesmos arquivos pelo Unity Catalog (é o mesmo lugar!)
databricks fs ls dbfs:/Volumes/econ_dev/landing/bcb -p lakehouse-dev
```

## Resultado da primeira execução (26/11/2026)

| Série | Código SGS | Registros (jan/2024 → nov/2026) |
|---|---|---|
| `dolar_venda` | 1 | 730 |
| `euro_venda` | 21619 | 730 |
| `selic_meta` | 432 | 1.061 |
| `cdi_diario` | 12 | 729 |
| `ipca_mensal` | 433 | 34 |

## Perguntas de entrevista (e como responder)

**"Por que Lambda e não um job no Databricks para buscar a API?"**
> Separação de responsabilidades e custo. A coleta é leve (uns segundos por dia), e a Lambda custa praticamente zero. Um cluster Databricks levaria minutos para subir e cobraria DBU. Além disso, o dado chega à landing zone independente da plataforma de processamento: se amanhã trocarmos o Databricks, a ingestão continua.

**"Como você garante que reprocessar não duplica dados?"**
> A ingestão é *append-only* no raw (cada execução é um arquivo novo, com timestamp). A deduplicação acontece na Silver, por chave (série, data), ficando com a coleta mais recente. Rodar duas vezes gera dois arquivos no raw, mas a Silver continua com uma linha por série e data.

**"Como funciona a segurança da Lambda?"**
> Ela tem uma execution role com o mínimo: `s3:PutObject` só no prefixo do seu ambiente e escrita só no próprio log group. O Scheduler tem outra role, que só pode invocar essas Lambdas, com a condição `aws:SourceAccount` para impedir uso por outra conta.

**"E se a API cair?"**
> O código tenta de novo com backoff exponencial, e o Scheduler tem mais 2 retentativas. Como a janela é de 7 dias, se um dia falhar, o dia seguinte recupera os dados que faltaram. Os erros ficam no CloudWatch Logs.

**"EventBridge Rules vs EventBridge Scheduler?"**
> O Scheduler é o serviço mais novo para agendamentos: aceita fuso horário (`America/Sao_Paulo`), janelas flexíveis e política de retentativa por alvo. As *rules* com `cron` só trabalham em UTC.

## Para praticar sozinha depois

1. Mude `lookback_days` para 3 no `terraform.tfvars` de `infra/03-ingestion`, rode `terraform plan` e veja que só a variável de ambiente da Lambda muda (`~ update in-place`).
2. Adicione uma série nova ao dicionário `SERIES` (por exemplo, `"igpm_mensal": (189, "IGP-M")`), rode os testes e depois `terraform apply`.
3. No console AWS: **Lambda → econ-ingest-dev → Monitor**, e veja duração, erros e invocações.
