# 02 · IAM e Unity Catalog: como a Databricks acessa a AWS com segurança

## Em uma frase

A Databricks **não recebe senha nem chave** da sua AWS. Ela **assume uma role IAM** (pede um "crachá temporário"), e a AWS só entrega esse crachá se o pedido vier de quem você autorizou **e** com o código combinado (o **External ID**).

## Os personagens

| Peça | Analogia | Neste projeto |
|---|---|---|
| **Usuário IAM** | Funcionário com crachá permanente | `jenmaia-admin` (você, com MFA) |
| **Role IAM** | Crachá de visitante, emprestado por tempo limitado | `econ-uc-role`, `databricks-lakehouse-cross-account-role` |
| **Trust policy** | A lista de quem pode pegar o crachá emprestado | "a conta AWS da Databricks, se trouxer o External ID" |
| **Permissions policy** | O que o crachá abre | "só os buckets `econ-raw` e `econ-lakehouse`" |
| **STS** | A portaria que entrega os crachás | `sts:AssumeRole` devolve credenciais que **expiram** |
| **External ID** | Senha combinada entre você e a Databricks | o seu Databricks Account ID |

## Por que o External ID existe (o "confused deputy")

A Databricks atende milhares de clientes com a mesma conta AWS. Sem o External ID, um cliente mal-intencionado poderia cadastrar na Databricks o ARN da **sua** role e fazer a Databricks acessar os seus dados em nome dele. A Databricks seria o "deputado confuso".

Com o External ID na trust policy, a role só é assumida quando o pedido traz o ID da **sua** conta Databricks. O outro cliente não tem esse ID.

## As 3 roles que criamos

| Role | Quem assume | O que pode | Stack |
|---|---|---|---|
| `databricks-lakehouse-cross-account-role` | Control plane da Databricks | Criar EC2, subnets e NAT para os clusters | `infra/01-workspaces` |
| `databricks-lakehouse-storage-role` | Unity Catalog | Prefixo `unity-catalog/` do bucket raiz | `infra/01-workspaces` |
| `econ-uc-role` | Unity Catalog (storage credential `econ-s3`) | Ler e gravar nos buckets do projeto | `infra/02-governance` |

### O detalhe da "self-assuming role"

A trust policy da `econ-uc-role` permite que **ela mesma** se assuma. A Databricks exige isso nas roles do Unity Catalog. Só que, no console, a AWS não deixa citar uma role que ainda não existe. O Terraform resolve montando o ARN pelo nome (`arn:aws:iam::<conta>:role/econ-uc-role`) antes de a role existir. Veja [`infra/02-governance/aws.tf`](../../infra/02-governance/aws.tf).

## Unity Catalog: do S3 até a tabela

```text
IAM role (AWS)
   └── storage credential  "econ-s3"        → o UC guarda QUAL role assumir
         ├── external location "econ-raw-dev"       → s3://econ-raw-<conta>/dev/
         │     └── volume econ_dev.landing.bcb        (arquivos JSON)
         └── external location "econ-lakehouse-dev" → s3://econ-lakehouse-<conta>/dev/
               └── catálogo econ_dev                  (tabelas Delta)
                     ├── landing · bronze · silver · gold   (schemas)
```

A hierarquia do Unity Catalog tem **3 níveis**: `catálogo.schema.tabela`, por exemplo `econ_prod.gold.cambio_diario`. Acima dos catálogos fica o **metastore**, um por região (`us-east-2`), compartilhado pelos dois workspaces.

### Por que catálogos `ISOLATED`?

Por padrão, todo catálogo aparece em todos os workspaces do metastore. Com `isolation_mode = "ISOLATED"` e um *workspace binding*, o `econ_prod` **só existe** dentro do `lakehouse-prod`. Testamos: no DEV, `databricks catalogs list` mostra `econ_dev`, mas não `econ_prod`.

## Grants: o modelo de permissões

```sql
-- O que o Terraform aplicou em PROD, traduzido para SQL:
GRANT USE CATALOG ON CATALOG econ_prod TO `analysts`;
GRANT USE SCHEMA, SELECT ON SCHEMA econ_prod.gold TO `analysts`;
GRANT USE CATALOG, USE SCHEMA, SELECT, READ VOLUME ON CATALOG econ_prod TO `data-engineering`;
```

Para ler uma tabela, a pessoa precisa de **três** permissões encadeadas: `USE CATALOG` no catálogo, `USE SCHEMA` no schema e `SELECT` na tabela (ou no schema inteiro). Por isso o analista consegue ler `gold`, mas não `bronze`: ele não tem `USE SCHEMA` lá.

## Perguntas de entrevista (e como responder)

**"Como você conectou a Databricks ao S3 sem expor credenciais?"**
> Com IAM roles. A Databricks assume a role via STS e recebe credenciais temporárias. A trust policy exige o External ID da minha conta Databricks, o que protege contra o *confused deputy*. No Unity Catalog, essa role vira uma *storage credential*, e cada caminho do S3 vira uma *external location*.

**"Qual a diferença entre a cross-account role e a role de storage?"**
> A cross-account é para *compute*: a Databricks cria EC2 e a rede na minha VPC. A de storage é para *dados*: o Unity Catalog lê e grava no S3. São permissões separadas, cada uma com o mínimo necessário.

**"Como você garantiria que analistas não vejam dados brutos?"**
> Separei as camadas em schemas (`bronze`, `silver`, `gold`) e dei aos analistas `USE SCHEMA` e `SELECT` só no `gold`, e só no catálogo de PROD. O catálogo de PROD é isolado no workspace de PROD, e os analistas nem têm acesso ao workspace de DEV.

**"Por que dar permissões a grupos e não a pessoas?"**
> Porque escala e é auditável: quando alguém entra ou sai, só muda de grupo. Os grants ficam estáveis e versionados no Terraform.

**"O que é uma external location e por que não ler o S3 direto com a chave?"**
> É o registro, no Unity Catalog, de um caminho do S3 associado a uma credential. Com ela, todo acesso passa pelo Unity Catalog, que aplica permissões e registra auditoria e lineage. Ler direto com chave contornaria a governança.

## Para praticar sozinha depois

1. No console AWS: **IAM → Roles → econ-uc-role → Trust relationships**. Ache o `sts:ExternalId`.
2. No Databricks (PROD): **Catalog → econ_prod → Permissions**. Compare com a tabela de grants acima.
3. No DEV, rode `SHOW CATALOGS` e confirme que `econ_prod` não aparece.
