# Atalhos do projeto. Uso: make <alvo>
# O /tmp desta máquina é pequeno (tmpfs): o Terraform baixa providers em TMPDIR.
export TMPDIR := $(HOME)/.cache/tmp
$(shell mkdir -p $(TMPDIR))

STACKS := infra/01-workspaces infra/02-governance infra/03-ingestion

ENV ?= dev
START ?= 2024-01-01

.PHONY: deploy-dev deploy-prod test plan-ingestion apply-ingestion backfill help fmt validate plan-workspaces apply-workspaces plan-governance apply-governance destroy-all

help:               ## Lista os alvos
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | sed 's/:.*##/ ·/'

fmt:                ## Formata o Terraform
	terraform fmt -recursive infra

validate:           ## fmt -check + validate em todos os stacks
	@for s in $(STACKS); do (cd $$s && terraform fmt -check -recursive && terraform init -backend=false -input=false >/dev/null && terraform validate) || exit 1; done

plan-workspaces:    ## Stack 1: plano dos workspaces
	cd infra/01-workspaces && terraform init -input=false && terraform plan
apply-workspaces:   ## Stack 1: cria os workspaces
	cd infra/01-workspaces && terraform apply

plan-governance:    ## Stack 2: plano da governança
	cd infra/02-governance && terraform init -input=false && terraform plan
apply-governance:   ## Stack 2: buckets, role, grupos, catálogos e grants
	cd infra/02-governance && terraform apply

test:               ## Testes da Lambda e do pipeline (PySpark local)
	cd ingestion && uv run --no-project --python 3.12 --with pytest pytest tests -q
	cd platform && uv run --no-project --python 3.12 --with pytest --with "pyspark==4.0.*" pytest tests -q

deploy-dev:         ## Publica e roda o job em DEV
	cd platform && databricks bundle deploy -t dev && databricks bundle run econ_daily -t dev

deploy-prod:        ## Publica e roda o job em PROD (mesmo código)
	cd platform && databricks bundle deploy -t prod && databricks bundle run econ_daily -t prod

plan-ingestion:     ## Stack 3: plano da ingestão
	cd infra/03-ingestion && terraform init -input=false && terraform plan
apply-ingestion:    ## Stack 3: Lambdas + agendamento
	cd infra/03-ingestion && terraform apply

backfill:           ## Carga histórica (ENV=dev|prod START=2024-01-01)
	aws lambda invoke --function-name econ-ingest-$(ENV) --cli-binary-format raw-in-base64-out --payload '{"start_date":"$(START)"}' /dev/stdout

destroy-all:        ## Apaga TUDO, na ordem inversa (pede confirmação em cada stack)
	cd infra/03-ingestion && terraform destroy
	cd infra/02-governance && terraform destroy
	cd infra/01-workspaces && terraform destroy
