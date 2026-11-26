data "aws_caller_identity" "current" {}

locals {
  aws_account_id = data.aws_caller_identity.current.account_id

  # Dois buckets de DADOS, cada um com as pastas dev/ e prod/:
  # - raw:       JSON como chegou da API do Banco Central (escrito pela Lambda).
  # - lakehouse: tabelas Delta (bronze, silver, gold) dos catálogos <project>_<env>.
  buckets = {
    raw       = "${var.project}-raw-${local.aws_account_id}"
    lakehouse = "${var.project}-lakehouse-${local.aws_account_id}"
  }

  # IAM role que o Unity Catalog assume para ler/gravar nos dois buckets.
  uc_role_name = "${var.project}-uc-role"
  uc_role_arn  = "arn:aws:iam::${local.aws_account_id}:role/${local.uc_role_name}"

  # Grupos (pessoas entram em grupos; permissões são dadas a grupos, nunca a pessoas).
  groups = ["platform-admins", "data-engineering", "analysts"]

  # Quem entra em qual workspace. Analistas só existem em PROD.
  workspace_access = {
    dev  = { "platform-admins" = "ADMIN", "data-engineering" = "USER" }
    prod = { "platform-admins" = "ADMIN", "data-engineering" = "USER", "analysts" = "USER" }
  }

  workspace_assignments = merge([
    for env, groups in local.workspace_access : {
      for group, role in groups : "${env}/${group}" => { env = env, group = group, role = role }
    }
  ]...)
}
