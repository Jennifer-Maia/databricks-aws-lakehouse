variable "databricks_account_id" {
  description = "Databricks Account ID (Account Console > menu do usuário)."
  type        = string

  validation {
    condition     = can(regex("^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", var.databricks_account_id))
    error_message = "O Databricks Account ID é um UUID, no formato xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx."
  }
}

variable "project" {
  description = "Nome curto do projeto. Entra no nome dos buckets, da role, dos catálogos (<project>_dev) etc."
  type        = string
  default     = "econ"

  validation {
    condition     = can(regex("^[a-z][a-z0-9]{2,15}$", var.project))
    error_message = "Use de 3 a 16 caracteres: letras minúsculas e números, começando por letra."
  }
}

variable "aws_profile" {
  description = "Profile do AWS CLI (a mesma conta AWS dos workspaces)."
  type        = string
}

variable "databricks_account_profile" {
  description = "Profile de CONTA do ~/.databrickscfg."
  type        = string
  default     = "workshop-account"
}

variable "workspace_profiles" {
  description = "Profile do ~/.databrickscfg de cada workspace (databricks auth login --host <url> --profile <nome>)."
  type        = map(string)
  default = {
    dev  = "lakehouse-dev"
    prod = "lakehouse-prod"
  }
}

variable "workspace_ids" {
  description = "ID numérico de cada workspace: output workspace_ids do stack ../01-workspaces."
  type        = object({ dev = number, prod = number })
}

variable "region" {
  description = "Região AWS (a mesma dos workspaces e do metastore)."
  type        = string
  default     = "us-east-2"
}

variable "platform_admins" {
  description = "E-mails (já existentes na conta Databricks) que entram no grupo platform-admins."
  type        = list(string)
}

variable "demo_users" {
  description = "Usuários de teste: e-mail => grupo. Precisam ser e-mails diferentes de verdade: a Databricks trata voce+alias@gmail.com como o mesmo usuário."
  type        = map(string)
  default     = {}

  validation {
    condition     = alltrue([for g in values(var.demo_users) : contains(["platform-admins", "data-engineering", "analysts"], g)])
    error_message = "Grupo inválido. Use: platform-admins, data-engineering ou analysts."
  }
}

variable "tags" {
  description = "Tags aplicadas a todos os recursos da AWS."
  type        = map(string)
  default = {
    Projeto       = "lakehouse-aws-portfolio"
    GerenciadoPor = "terraform"
  }
}
