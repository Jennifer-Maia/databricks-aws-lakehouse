# Unity Catalog: a ponte entre o S3 (dado físico) e as tabelas (metadado).
#
#   IAM role ──> storage credential ──┬─> external location <project>-raw-<env>
#                                     │      └── volume <project>_<env>.landing.bcb  (JSON como chegou)
#                                     └─> external location <project>-lakehouse-<env>
#                                            └── catálogo <project>_<env>
#                                                 ├── landing  (volume com os arquivos brutos)
#                                                 ├── bronze   (dado bruto em Delta, com metadados de carga)
#                                                 ├── silver   (tipado, limpo, sem duplicatas)
#                                                 └── gold     (pronto para o negócio)

# Storage credential: o Unity Catalog guarda QUAL role assumir.
# Criada antes da role existir (o ARN é montado pelo nome); a role usa o
# External ID gerado aqui na trust policy (aws.tf).
resource "databricks_storage_credential" "this" {
  provider = databricks.dev

  name    = "${var.project}-s3"
  comment = "Acesso aos buckets raw e lakehouse do projeto ${var.project} (Terraform)"
  owner   = databricks_group.this["platform-admins"].display_name

  aws_iam_role {
    role_arn = local.uc_role_arn
  }

  # A role ainda não existe neste momento; a validação acontece nas external locations.
  skip_validation = true
  force_destroy   = true # didático: permite o destroy mesmo com external locations
}

# Um bloco por ambiente. Cada um usa o provider do SEU workspace.
module "dev" {
  source    = "./modules/environment"
  providers = { databricks = databricks.dev }

  project            = var.project
  env                = "dev"
  workspace_id       = var.workspace_ids.dev
  raw_bucket         = aws_s3_bucket.this["raw"].bucket
  lakehouse_bucket   = aws_s3_bucket.this["lakehouse"].bucket
  storage_credential = databricks_storage_credential.this.name
  owner_group        = databricks_group.this["platform-admins"].display_name
  role_ready         = time_sleep.uc_role.id

  # DEV: engenharia desenvolve (lê e escreve em tudo).
  catalog_grants = {
    "data-engineering" = ["USE_CATALOG", "USE_SCHEMA", "CREATE_SCHEMA", "CREATE_TABLE", "CREATE_VOLUME", "SELECT", "MODIFY", "READ_VOLUME", "WRITE_VOLUME"]
  }
  gold_grants = {}

  depends_on = [databricks_mws_permission_assignment.this]
}

module "prod" {
  source    = "./modules/environment"
  providers = { databricks = databricks.prod }

  project            = var.project
  env                = "prod"
  workspace_id       = var.workspace_ids.prod
  raw_bucket         = aws_s3_bucket.this["raw"].bucket
  lakehouse_bucket   = aws_s3_bucket.this["lakehouse"].bucket
  storage_credential = databricks_storage_credential.this.name
  owner_group        = databricks_group.this["platform-admins"].display_name
  role_ready         = time_sleep.uc_role.id

  # PROD: engenharia só lê (quem escreve é o job publicado pelo bundle).
  # Analistas: entram no catálogo e só enxergam o schema gold.
  catalog_grants = {
    "data-engineering" = ["USE_CATALOG", "USE_SCHEMA", "SELECT", "READ_VOLUME"]
    "analysts"         = ["USE_CATALOG"]
  }
  gold_grants = {
    "analysts" = ["USE_SCHEMA", "SELECT"]
  }

  depends_on = [databricks_mws_permission_assignment.this]
}
