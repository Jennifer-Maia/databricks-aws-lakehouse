output "workspace_urls" {
  description = "URL de cada workspace, por ambiente."
  value       = { for env, ws in databricks_mws_workspaces.this : env => ws.workspace_url }
}

output "workspace_ids" {
  description = "ID numérico de cada workspace (entrada do stack ../02-governance)."
  value       = { for env, ws in databricks_mws_workspaces.this : env => ws.workspace_id }
}

output "root_bucket_name" {
  description = "Bucket raiz dos workspaces."
  value       = aws_s3_bucket.root.bucket
}

output "storage_role_arn" {
  description = "ARN da storage role do Unity Catalog."
  value       = aws_iam_role.storage.arn
}

output "cross_account_role_arn" {
  description = "ARN da cross-account role (EC2)."
  value       = aws_iam_role.cross_account.arn
}
