# 05 · Troubleshooting: problemas reais deste projeto e como foram investigados

Problemas reais, na ordem em que aconteceram. Em entrevista, **"me conte um problema que você resolveu"** é pergunta certa. Para cada caso: sintoma → hipóteses → testes → causa → solução.

---

## 1. `/tmp` cheio ao instalar ferramentas

| | |
|---|---|
| **Sintoma** | `No space left on device` ao baixar o AWS CLI; depois, `terraform init` falhando ao baixar o provider da AWS. |
| **Causa** | O VS Code roda num Flatpak, onde o `/tmp` é um *tmpfs* (fica em memória) de apenas 764 MB. |
| **Solução** | Apontar a pasta temporária para o disco: `export TMPDIR=$HOME/.cache/tmp`. O `Makefile` do projeto já faz isso. |
| **Lição** | Erros de "disco cheio" nem sempre são o disco principal: confira com `df -h <pasta>`. |

## 2. `aws login` sem resposta e perfil "preso" no root

| | |
|---|---|
| **Sintoma** | O login expirou; depois, o CLI perguntou `(y/n)` para trocar o root pelo usuário IAM e falhou com `EOF when reading a line`. |
| **Causa** | O comando rodava num terminal que não aceita digitação interativa. |
| **Solução** | Remover a sessão antiga do `~/.aws/config` e logar de novo já com o usuário IAM no navegador. |
| **Lição** | Use **usuário IAM com MFA** no dia a dia, nunca o root. |

## 3. Usuários de teste com Gmail "+alias" recusados

| | |
|---|---|
| **Sintoma** | `A user with email voce+analista@gmail.com already exists with a different version: voce@gmail.com` |
| **Causa** | A Databricks trata `voce+qualquercoisa@gmail.com` como o mesmo usuário de `voce@gmail.com`. |
| **Solução** | Usar um e-mail realmente diferente para o usuário de teste (analista). |

## 4. `outputs.tf` vazio no material original

| | |
|---|---|
| **Sintoma** | `terraform output workspace_ids` → `Output "workspace_ids" not found`. |
| **Causa** | O arquivo `outputs.tf` do repositório de referência estava vazio. |
| **Solução** | Escrever os outputs e rodar `terraform apply -refresh-only` (atualiza o state sem mudar nenhum recurso). |

## 5. ⭐ Pipeline declarativo serverless: 403 Forbidden no S3

O mais interessante: vale contar em entrevista.

**Sintoma:**
```text
[UNITY_CATALOG_INITIALIZATION_FAILED] ... getFileStatus on s3://econ-lakehouse-.../__unitystorage/.../_delta_log:
AmazonS3Exception: Forbidden ... Request ID: null ... Proxy: 192.168.200.0 ... 403 Forbidden
```

**Investigação (eliminando hipóteses uma a uma):**

| # | Hipótese | Teste | Resultado |
|---|---|---|---|
| 1 | Permissão IAM da `econ-uc-role` errada | SQL serverless: `CREATE TABLE econ_dev.bronze._teste AS SELECT 1` | ✅ funcionou → IAM ok |
| 2 | Unity Catalog / external location errada | `LIST 's3://econ-lakehouse-.../dev/'` e `LIST` no raw | ✅ ambos listam |
| 3 | Política de rede do serverless bloqueando | `databricks account network-policies list-network-policies-rpc` | ✅ `FULL_ACCESS` |
| 4 | Erro passageiro da 1ª execução | Rodar de novo | ❌ mesmo erro → não é passageiro |
| 5 | Só o compute de **pipelines** serverless é afetado | Job serverless com notebook criando tabela | ✅ funcionou |

**Pista importante:** `Request ID: null`. Quando o S3 nega um acesso, ele sempre devolve um Request ID. Sem ele, quem negou foi alguma coisa **no caminho** (o proxy de saída do compute), não o S3. No ensaio do workshop original aconteceu o mesmo, só que no SQL warehouse serverless.

**Tentativa 2: pipeline em compute clássico (EC2 na nossa VPC)**

```text
InvalidParameterCombination: The specified instance type is not eligible for Free Tier.
```

O **Free plan** da AWS só permite instâncias do free tier (`t3.micro`, `m7i-flex.large`...), e **nenhuma** delas está na lista de tipos aceitos pela Databricks. Conferido cruzando as duas listas:

```bash
aws ec2 describe-instance-types --filters Name=free-tier-eligible,Values=true ...
databricks clusters list-node-types ...
comm -12 free_tier.txt databricks.txt      # vazio
```

Além disso, a conta tinha **cota de 5 vCPUs** para EC2 (`aws service-quotas get-service-quota --service-code ec2 --quota-code L-1216C47A`).

**Solução adotada:** trocar o pipeline declarativo por um **job serverless com notebooks PySpark** (Auto Loader + `availableNow`), que o teste 5 mostrou funcionar. As camadas, a governança e a promoção DEV → PROD ficaram iguais. O que perdemos (expectations nativas) foi substituído pela quarentena na Silver e pela tarefa `04_qualidade`.

**O que eu faria numa empresa:** abrir um chamado no suporte da Databricks com o ID do pipeline e o erro completo, e usar compute clássico (que numa conta paga funciona) até a correção.

**Como contar em entrevista (formato STAR):**
> **Situação:** o pipeline declarativo serverless falhava com 403 ao gravar no S3. **Tarefa:** descobrir se era permissão minha ou da plataforma, sem sair do orçamento zero. **Ação:** isolei as variáveis: testei a mesma credential pelo SQL serverless (funcionou), listei as external locations, conferi a política de rede, repeti a execução e testei um job serverless comum. O `Request ID: null` indicava bloqueio no proxy, não no S3. O plano B (compute clássico) esbarrou na restrição de instâncias do Free plan da AWS, que confirmei cruzando as listas de instâncias. **Resultado:** migrei para job serverless com Auto Loader, mantive testes, qualidade e promoção, e documentei tudo.

## 6. Bundle pedindo confirmação para apagar o pipeline antigo

| | |
|---|---|
| **Sintoma** | `the deployment requires destructive actions, but the current console does not support prompting.` |
| **Causa** | Remover o pipeline do YAML faz o `bundle deploy` querer **apagar** o pipeline publicado, e o bundle protege recursos de dados. |
| **Solução** | Confirmar que o pipeline não tinha tabelas (`databricks tables list econ_dev bronze`), pedir aprovação e usar `--auto-approve`. |
| **Lição** | Nunca usar `--auto-approve` às cegas: leia o plano de exclusão antes. |

## 7. ⭐ Analista não conseguia nem entrar no workspace

| | |
|---|---|
| **Sintoma** | Na guia anônima, com o usuário analista: *"Unable to view page. You do not have permission to access this page in workspace … ensure you are assigned to the workspace and have either the 'Workspace access', 'Databricks SQL access', or 'Consumer access' entitlement"*. |
| **Por que não apareceu antes** | Eu (admin) sempre conseguia entrar: **admin ignora entitlements**. Só um teste com um usuário comum revelou o problema. |
| **Diagnóstico** | `databricks groups get <id> -p lakehouse-prod` → `entitlements: None` em **todos** os grupos, inclusive `users`. |
| **Causa** | São duas camadas diferentes. **Atribuir o grupo ao workspace** (`databricks_mws_permission_assignment`, no nível da conta) diz *em qual workspace a pessoa pode entrar*. **Entitlements** (`databricks_entitlements`, no nível do workspace) dizem *o que ela pode usar lá dentro*. Neste workspace novo, nenhum grupo tinha entitlement. |
| **Solução** | Terraform em [`infra/02-governance/identity.tf`](../../infra/02-governance/identity.tf): `data-engineering` com `workspace_access` + `databricks_sql_access` (DEV e PROD) e `analysts` só com `databricks_sql_access` (PROD). |
| **Lição** | **Teste a governança com um usuário que não é admin.** Permissões no Unity Catalog (dados) e entitlements no workspace (interface) são camadas independentes, e as duas precisam estar certas. |

### As 4 camadas de acesso (resumo para entrevista)

| Camada | Pergunta | Onde configuramos |
|---|---|---|
| 1. Identidade (conta) | A pessoa existe e está em qual grupo? | `databricks_user`, `databricks_group_member` |
| 2. Atribuição ao workspace | Em qual workspace o grupo pode entrar? | `databricks_mws_permission_assignment` |
| 3. Entitlements | O que o grupo usa no workspace (notebooks? só SQL?) | `databricks_entitlements` |
| 4. Unity Catalog | Quais dados o grupo pode ler ou escrever? | `databricks_grant` (catálogo, schema `gold`) |

## 8. ⭐ Destruir também é engenharia: a limpeza deixou rede órfã

Ao final, apagamos tudo com `bundle destroy` e `terraform destroy` (ingestão → governança → workspaces). Três lições:

| # | O que aconteceu | Causa | Solução |
|---|---|---|---|
| a | `cannot delete schema: Catalog 'econ_dev' is not accessible in current workspace` | O destroy apagou primeiro o **workspace binding**. Sem ele, um catálogo `ISOLATED` fica invisível, até para quem vai apagá-lo. | Religar o catálogo (`databricks workspace-bindings update-bindings`), apagar com `databricks catalogs delete --force` e tirar do state (`terraform state rm`). |
| b | `Cannot delete external location ... 12 dependent managed tables` | Tabelas gerenciadas apagadas ficam **7 dias** recuperáveis (`UNDROP TABLE`) e continuam contando como dependentes. | `databricks external-locations delete --force`, já que o bucket seria apagado de qualquer jeito. |
| c | Depois de tudo "destruído", **sobraram 2 NAT Gateways, 2 IPs públicos e 2 VPCs**, cobrando ~US$ 2,40/dia | A Databricks apaga a rede do workspace **de forma assíncrona**, usando a cross-account role. O Terraform apagou a role logo depois do workspace, e a limpeza ficou sem permissão. | Remoção manual (NAT → IPs → endpoints → IGW → subnets → route tables → security groups → VPC), só nas VPCs com tag `databricks-WorkerEnvId(workerenv-<id do workspace>)`. Correção permanente: `destroy_duration = "15m"` no `time_sleep` da role ([`infra/01-workspaces/aws_iam.tf`](../../infra/01-workspaces/aws_iam.tf)). |

**Lição:** depois de um destroy, **confira na AWS** se não sobrou nada cobrando:

```bash
aws ec2 describe-nat-gateways --filter Name=state,Values=available   # NAT (o mais caro)
aws ec2 describe-addresses                                           # IPs públicos
aws ec2 describe-vpcs --filters Name=is-default,Values=false         # VPCs que sobraram
aws ec2 describe-instances --filters Name=instance-state-name,Values=running
```

## Comandos de diagnóstico que valem guardar

```bash
aws sts get-caller-identity --profile <p>                        # quem sou eu na AWS?
aws freetier get-account-plan-state --region us-east-1           # plano da conta e créditos
databricks auth profiles                                         # perfis e se o login é válido
databricks current-user me -p <perfil>                           # quem sou eu no workspace?
databricks groups get <group-id> -p <perfil>                     # entitlements de um grupo
databricks clusters events <cluster-id> -p <perfil>              # por que o cluster não subiu?
databricks experimental aitools tools query "<SQL>" -p <perfil>  # rodar SQL do terminal
terraform plan                                                   # o que vai mudar? (sempre antes do apply)
terraform state list                                             # o que o Terraform gerencia
```
