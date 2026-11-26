# Atalhos do projeto. Uso: make <alvo>
# O /tmp desta máquina é pequeno (tmpfs): o Terraform baixa providers em TMPDIR.
export TMPDIR := $(HOME)/.cache/tmp
$(shell mkdir -p $(TMPDIR))

STACKS := infra/01-workspaces infra/02-governance

.PHONY: help fmt validate plan-workspaces apply-workspaces plan-governance apply-governance destroy-all

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

destroy-all:        ## Apaga TUDO, na ordem inversa (pede confirmação em cada stack)
	cd infra/02-governance && terraform destroy
	cd infra/01-workspaces && terraform destroy
