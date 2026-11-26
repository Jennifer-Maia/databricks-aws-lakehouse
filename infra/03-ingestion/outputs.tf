output "lambda_functions" {
  description = "Nome da Lambda de cada ambiente."
  value       = { for env, f in aws_lambda_function.ingest : env => f.function_name }
}

output "raw_bucket" {
  description = "Bucket onde as Lambdas gravam."
  value       = data.aws_s3_bucket.raw.bucket
}

output "backfill_command" {
  description = "Exemplo de carga histórica (rode uma vez por ambiente)."
  value       = "aws lambda invoke --function-name ${local.name["dev"]} --cli-binary-format raw-in-base64-out --payload '{\"start_date\": \"2024-01-01\"}' /dev/stdout"
}
