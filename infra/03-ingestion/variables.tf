variable "aws_profile" {
  description = "Profile do AWS CLI (a mesma conta dos outros stacks)."
  type        = string
}

variable "region" {
  description = "Região AWS (a mesma dos buckets)."
  type        = string
  default     = "us-east-2"
}

variable "project" {
  description = "Mesmo valor do stack ../02-governance (define o nome do bucket raw)."
  type        = string
  default     = "econ"
}

variable "environments" {
  description = "Ambientes com uma Lambda própria (cada uma grava em <env>/bcb/ no bucket raw)."
  type        = set(string)
  default     = ["dev", "prod"]
}

variable "schedule_expression" {
  description = "Quando rodar (EventBridge Scheduler). Default: todo dia às 20h de Brasília, depois da PTAX."
  type        = string
  default     = "cron(0 20 * * ? *)"
}

variable "lookback_days" {
  description = "Quantos dias para trás a execução diária relê (o BCB publica com atraso e corrige valores)."
  type        = number
  default     = 7
}

variable "log_retention_days" {
  description = "Por quantos dias o CloudWatch guarda os logs da Lambda."
  type        = number
  default     = 7
}

variable "tags" {
  description = "Tags aplicadas a todos os recursos."
  type        = map(string)
  default = {
    Projeto       = "lakehouse-aws-portfolio"
    Camada        = "ingestao"
    GerenciadoPor = "terraform"
  }
}
