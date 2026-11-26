output "buckets" {
  description = "Buckets do projeto: raw (arquivos) e lakehouse (tabelas)."
  value       = { for k, b in aws_s3_bucket.this : k => b.bucket }
}

output "catalogs" {
  description = "Catálogos por ambiente."
  value       = { dev = module.dev.catalog, prod = module.prod.catalog }
}

output "landing_volume_paths" {
  description = "Onde a bronze lê os arquivos (volume do Unity Catalog)."
  value       = { dev = module.dev.landing_volume_path, prod = module.prod.landing_volume_path }
}

output "raw_s3_paths" {
  description = "Para onde a Lambda de ingestão grava o JSON."
  value       = { dev = module.dev.raw_s3_path, prod = module.prod.raw_s3_path }
}
