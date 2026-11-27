# Um ambiente (dev ou prod) no Unity Catalog:
#   external location raw       s3://<project>-raw-<conta>/<env>/        -> volume <project>_<env>.landing.bcb
#   external location lakehouse s3://<project>-lakehouse-<conta>/<env>/  -> catálogo <project>_<env> (tabelas)
# + schemas landing/bronze/silver/gold + grants. O catálogo é isolado no workspace do ambiente.

terraform {
  required_providers {
    databricks = {
      source = "databricks/databricks"
    }
  }
}

variable "project" { type = string }
variable "env" { type = string }
variable "workspace_id" { type = number }
variable "raw_bucket" { type = string }
variable "lakehouse_bucket" { type = string }
variable "storage_credential" { type = string }
variable "owner_group" { type = string }
variable "role_ready" {
  description = "Só para ordenar: a external location espera a role IAM propagar."
  type        = string
}
variable "catalog_grants" { type = map(list(string)) }
variable "gold_grants" {
  description = "Grants no schema gold (consumo pelo negócio)."
  type        = map(list(string))
}

locals {
  raw_prefix       = "s3://${var.raw_bucket}/${var.env}"
  lakehouse_prefix = "s3://${var.lakehouse_bucket}/${var.env}"
  schemas = {
    landing = "Arquivos brutos da API do Banco Central (volume)"
    bronze  = "Dado bruto em Delta, com metadados de carga"
    silver  = "Séries tipadas, limpas e sem duplicatas"
    gold    = "Indicadores prontos para o negócio"
  }
}

# A Databricks testa leitura/escrita nas duas URLs ao criar.
resource "databricks_external_location" "raw" {
  force_destroy   = true
  name            = "${var.project}-raw-${var.env}"
  url             = "${local.raw_prefix}/"
  credential_name = var.storage_credential
  owner           = var.owner_group
  comment         = "Arquivos brutos de ${upper(var.env)} (role pronta: ${var.role_ready})"
}

resource "databricks_external_location" "lakehouse" {
  force_destroy   = true
  name            = "${var.project}-lakehouse-${var.env}"
  url             = "${local.lakehouse_prefix}/"
  credential_name = var.storage_credential
  owner           = var.owner_group
  comment         = "Tabelas Delta de ${upper(var.env)} (role pronta: ${var.role_ready})"
}

# Catálogo <project>_<env>. As tabelas gerenciadas ficam no bucket lakehouse.
# ISOLATED: o catálogo só aparece no workspace vinculado (binding abaixo).
resource "databricks_catalog" "this" {
  name           = "${var.project}_${var.env}"
  comment        = "Indicadores econômicos do Banco Central · ${upper(var.env)}"
  storage_root   = "${local.lakehouse_prefix}/"
  isolation_mode = "ISOLATED"
  owner          = var.owner_group
  # Didático: deixa o destroy apagar o catálogo com tabelas dentro. Em produção, false.
  force_destroy = true

  depends_on = [databricks_external_location.lakehouse]
}

resource "databricks_workspace_binding" "this" {
  securable_name = databricks_catalog.this.name
  securable_type = "catalog"
  workspace_id   = var.workspace_id
  binding_type   = "BINDING_TYPE_READ_WRITE"
}

# Um schema por camada da arquitetura medalhão.
resource "databricks_schema" "this" {
  for_each = local.schemas

  catalog_name = databricks_catalog.this.name
  name         = each.key
  comment      = each.value
  owner        = var.owner_group
}

# Volume externo apontando para o bucket RAW:
# /Volumes/<project>_<env>/landing/bcb  ==  s3://<project>-raw-<conta>/<env>/bcb/
resource "databricks_volume" "bcb" {
  catalog_name     = databricks_catalog.this.name
  schema_name      = databricks_schema.this["landing"].name
  name             = "bcb"
  volume_type      = "EXTERNAL"
  storage_location = "${local.raw_prefix}/bcb"
  owner            = var.owner_group
  comment          = "JSON da API SGS do Banco Central, gravado pela Lambda: fonte da bronze"

  depends_on = [databricks_external_location.raw]
}

# databricks_grant (singular) não é autoritativo: não apaga grants feitos por outros.
resource "databricks_grant" "catalog" {
  for_each = var.catalog_grants

  catalog    = databricks_catalog.this.name
  principal  = each.key
  privileges = each.value
}

resource "databricks_grant" "gold" {
  for_each = var.gold_grants

  schema     = "${databricks_catalog.this.name}.${databricks_schema.this["gold"].name}"
  principal  = each.key
  privileges = each.value
}

output "catalog" { value = databricks_catalog.this.name }
output "landing_volume_path" { value = "/Volumes/${databricks_catalog.this.name}/landing/${databricks_volume.bcb.name}" }
output "raw_s3_path" { value = "${local.raw_prefix}/bcb/" }
