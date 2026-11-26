# Ingestão: EventBridge Scheduler -> Lambda (Python) -> S3 raw.
#
#   ⏰ schedule econ-ingest-<env>  --invoke-->  λ econ-ingest-<env>  --PutObject-->  s3://econ-raw-<conta>/<env>/bcb/
#                                                   └── logs --> CloudWatch /aws/lambda/econ-ingest-<env>
#
# Uma Lambda por ambiente: cada uma só consegue gravar no prefixo do SEU ambiente.

data "aws_caller_identity" "current" {}

# O bucket raw foi criado pelo stack ../02-governance: aqui só lemos.
data "aws_s3_bucket" "raw" {
  bucket = "${var.project}-raw-${data.aws_caller_identity.current.account_id}"
}

locals {
  name = { for env in var.environments : env => "${var.project}-ingest-${env}" }
}

# Empacota ingestion/src/ (só handler.py: sem dependências externas).
data "archive_file" "lambda" {
  type        = "zip"
  source_dir  = "${path.module}/../../ingestion/src"
  output_path = "${path.module}/.build/ingest.zip"
  excludes    = ["__pycache__"]
}

# ---------------------------------------------------------------------------
# Logs: criamos o log group para controlar a retenção (sem isso, é "para sempre").
# ---------------------------------------------------------------------------
resource "aws_cloudwatch_log_group" "lambda" {
  for_each = local.name

  name              = "/aws/lambda/${each.value}"
  retention_in_days = var.log_retention_days
}

# ---------------------------------------------------------------------------
# IAM da Lambda: menor privilégio.
# ---------------------------------------------------------------------------
resource "aws_iam_role" "lambda" {
  for_each = local.name

  name        = each.value
  description = "Lambda de ingestão BCB (${each.key}): grava só em ${each.key}/bcb/ do bucket raw"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "lambda" {
  for_each = local.name

  name = "ingest-s3-and-logs"
  role = aws_iam_role.lambda[each.key].id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "GravarSoNoPrefixoDoAmbiente"
        Effect   = "Allow"
        Action   = ["s3:PutObject"]
        Resource = "${data.aws_s3_bucket.raw.arn}/${each.key}/bcb/*"
      },
      {
        Sid      = "EscreverLogs"
        Effect   = "Allow"
        Action   = ["logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = "${aws_cloudwatch_log_group.lambda[each.key].arn}:*"
      },
    ]
  })
}

# ---------------------------------------------------------------------------
# A função
# ---------------------------------------------------------------------------
resource "aws_lambda_function" "ingest" {
  for_each = local.name

  function_name    = each.value
  description      = "Busca séries do Banco Central (SGS) e grava o JSON bruto no S3 (${each.key})"
  role             = aws_iam_role.lambda[each.key].arn
  runtime          = "python3.12"
  handler          = "handler.lambda_handler"
  filename         = data.archive_file.lambda.output_path
  source_code_hash = data.archive_file.lambda.output_base64sha256
  timeout          = 120
  memory_size      = 256
  architectures    = ["arm64"] # Graviton: ~20% mais barato

  environment {
    variables = {
      RAW_BUCKET    = data.aws_s3_bucket.raw.bucket
      ENV           = each.key
      LOOKBACK_DAYS = tostring(var.lookback_days)
    }
  }

  depends_on = [aws_cloudwatch_log_group.lambda, aws_iam_role_policy.lambda]
}

# ---------------------------------------------------------------------------
# Agendamento: EventBridge Scheduler (serviço sucessor das "rules" com cron).
# ---------------------------------------------------------------------------
resource "aws_iam_role" "scheduler" {
  name        = "${var.project}-ingest-scheduler"
  description = "EventBridge Scheduler: só pode invocar as Lambdas de ingestão"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "scheduler.amazonaws.com" }
      Action    = "sts:AssumeRole"
      # Só agendamentos da MINHA conta podem usar esta role.
      Condition = { StringEquals = { "aws:SourceAccount" = data.aws_caller_identity.current.account_id } }
    }]
  })
}

resource "aws_iam_role_policy" "scheduler" {
  name = "invoke-ingest-lambdas"
  role = aws_iam_role.scheduler.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = "lambda:InvokeFunction"
      Resource = [for f in aws_lambda_function.ingest : f.arn]
    }]
  })
}

resource "aws_scheduler_schedule" "daily" {
  for_each = local.name

  name                         = each.value
  description                  = "Ingestão diária do BCB (${each.key})"
  schedule_expression          = var.schedule_expression
  schedule_expression_timezone = "America/Sao_Paulo"

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = aws_lambda_function.ingest[each.key].arn
    role_arn = aws_iam_role.scheduler.arn
    input    = jsonencode({}) # evento vazio = janela padrão (últimos lookback_days)

    retry_policy {
      maximum_retry_attempts = 2
    }
  }
}
