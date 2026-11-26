# 01 · Terraform: infraestrutura como código

## Em uma frase

Terraform é uma ferramenta em que você **descreve** a infraestrutura que quer (buckets, roles, workspaces) em arquivos de texto, e ela **cria, altera ou apaga** essa infraestrutura para ficar igual ao que está escrito.

Em vez de clicar 40 vezes no console da AWS, você escreve o que quer, revisa e aplica. Esse jeito de trabalhar se chama **IaC (Infrastructure as Code)**, infraestrutura como código.

## Por que as empresas usam

| Clicando no console | Com Terraform |
|---|---|
| Ninguém sabe exatamente o que foi feito | O código *é* a documentação |
| Recriar o ambiente PROD igual ao DEV é sujeito a erro | O mesmo código cria DEV e PROD idênticos |
| Mudanças não passam por revisão | Mudanças passam por Pull Request, como código |
| Apagar tudo exige lembrar de cada peça | `terraform destroy` apaga tudo o que ele criou |

## Os 5 conceitos que você precisa saber

1. **Provider:** o "plugin" que sabe falar com um serviço. Neste projeto usamos `aws` (cria S3 e IAM), `databricks` (cria credential e workspaces no Account Console) e `time` (cria pausas). Veja [`infra/01-workspaces/versions.tf`](../../infra/01-workspaces/versions.tf).
2. **Resource:** uma peça de infraestrutura. Exemplo: `resource "aws_s3_bucket" "root"` é o bucket raiz ([`aws_storage.tf`](../../infra/01-workspaces/aws_storage.tf)).
3. **Variable:** um valor que muda por pessoa ou ambiente (Account ID, prefixo, região). Os valores reais ficam no `terraform.tfvars`, que **não vai para o Git**.
4. **State (`terraform.tfstate`):** o arquivo em que o Terraform anota o que já criou e os IDs reais. É assim que ele sabe o que precisa criar, alterar ou apagar. Contém dados sensíveis, então também fica fora do Git. Em empresa, ele fica num bucket S3 compartilhado (o *remote backend*).
5. **Data source:** algo que o Terraform **lê** sem criar. Exemplo: `data "databricks_aws_unity_catalog_assume_role_policy"` gera o JSON da trust policy para nós.

## O ciclo de trabalho

```bash
terraform init      # baixa os providers (uma vez por pasta)
terraform plan      # mostra O QUE vai mudar, sem mudar nada (+ criar, ~ alterar, - apagar)
terraform apply     # executa o plano (pede "yes")
terraform destroy   # apaga tudo o que este código criou
```

Regra de ouro: **leia o `plan` antes de todo `apply`**. Foi o que fizemos: o plano dizia `15 to add, 0 to change, 0 to destroy`, ou seja, nada do que já existia seria tocado.

## Como o Terraform sabe a ordem?

Ele monta um **grafo de dependências** a partir das referências entre recursos. Se o workspace usa `databricks_mws_credentials.this.credentials_id`, o Terraform sabe que precisa criar a credential primeiro. Recursos independentes são criados em paralelo.

Às vezes a dependência é "invisível". O IAM da AWS leva alguns segundos para propagar uma role nova, e a Databricks falha se validar cedo demais. Por isso o projeto usa `time_sleep` (uma pausa de 20 s) entre criar a role e registrá-la na Databricks ([`databricks.tf`](../../infra/01-workspaces/databricks.tf)).

## O que este projeto cria (stack `infra/01-workspaces`)

```text
AWS (sua conta)                                Databricks (Account Console)
├── S3: bucket raiz  ───────────────────────►  storage configuration ─┐
├── IAM: storage role (Unity Catalog) ──────►        (usa a role)      ├─► workspace lakehouse-dev
└── IAM: cross-account role (EC2) ──────────►  credential ─────────────┘   workspace lakehouse-prod
```

Ao subir cada workspace, a Databricks usa a cross-account role para criar **na sua conta** a VPC, as subnets e o NAT Gateway.

## Perguntas de entrevista (e como responder)

**"O que é Terraform e por que usar?"**
> É uma ferramenta de infraestrutura como código. Eu descrevo os recursos de forma declarativa, reviso o `plan` e aplico. Isso dá reprodutibilidade (DEV e PROD idênticos), revisão por PR e facilidade para destruir ambientes. No meu projeto criei com ele as IAM roles, o bucket S3 e dois workspaces Databricks numa conta AWS.

**"Declarativo vs imperativo?"**
> Declarativo: digo o *estado final* ("quero 2 workspaces") e a ferramenta descobre os passos. Imperativo: escrevo os *passos* (um script com `aws s3 mb ...`). Terraform é declarativo.

**"Onde fica o state e por que importa?"**
> É o mapa entre o código e os recursos reais. Localmente fica no `terraform.tfstate`. Em time, vai para um backend remoto (S3 com lock), para duas pessoas não aplicarem ao mesmo tempo. Nunca vai para o Git, porque pode ter dados sensíveis.

**"Como você evita colocar segredos no código?"**
> Os providers usam **profiles** do AWS CLI e do Databricks CLI (login por navegador/OAuth). No código só existe o *nome* do profile. Os valores reais ficam no `terraform.tfvars`, que está no `.gitignore`.

**"Terraform vs CloudFormation?"**
> CloudFormation é da AWS e só cria recursos da AWS. Terraform é multi-cloud e tem provider da Databricks, então consigo criar as peças da AWS e da Databricks no mesmo código, com dependências entre elas.

## Para praticar sozinha depois

1. Abra [`infra/01-workspaces/variables.tf`](../../infra/01-workspaces/variables.tf) e descubra o que muda se você criar só o DEV (`environments = { dev = "lakehouse-dev" }`).
2. Rode `terraform plan` e leia o resultado sem aplicar.
3. Rode `terraform state list` para ver tudo o que o Terraform está gerenciando.
4. Curso gratuito oficial: *HashiCorp Developer → Terraform → Get Started (AWS)*.
