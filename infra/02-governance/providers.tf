# Autenticação: NENHUM segredo em arquivo, só NOMES de profiles.
#
# - aws:              profile do AWS CLI (~/.aws/config).
# - databricks.account: profile de CONTA (accounts.cloud.databricks.com).
#                     Cria grupos, usuários e atribui grupos aos workspaces.
# - databricks.dev/prod: um profile por WORKSPACE (databricks auth login
#                     --host <url do workspace> --profile lakehouse-dev ...).
#                     Criam os objetos do Unity Catalog.
#
# Por que um provider por workspace? Os catálogos são ISOLADOS (cada um só
# aparece no seu workspace). Um catálogo <project>_prod criado a partir do workspace DEV
# deixaria de ser visível para quem o criou; então cada catálogo é criado pelo
# provider do seu próprio workspace.

provider "aws" {
  profile = var.aws_profile
  region  = var.region

  default_tags {
    tags = var.tags
  }
}

provider "databricks" {
  alias      = "account"
  host       = "https://accounts.cloud.databricks.com"
  account_id = var.databricks_account_id
  profile    = var.databricks_account_profile
}

provider "databricks" {
  alias   = "dev"
  profile = var.workspace_profiles["dev"]
}

provider "databricks" {
  alias   = "prod"
  profile = var.workspace_profiles["prod"]
}
