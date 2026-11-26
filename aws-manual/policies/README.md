# Policies IAM e S3

Modelos das policies usadas no setup manual (`<...>` marca o que muda por conta). Para gerar as policies **já preenchidas** com os seus IDs:

```bash
python3 aws-manual/policies/gerar_policies.py --aws <AWS_ACCOUNT_ID> --databricks <DATABRICKS_ACCOUNT_ID> --prefix workshop
```

A saída vai para `aws-manual/policies/prontas/<AWS_ACCOUNT_ID>/COLAR.md` — pasta ignorada pelo git, porque contém os IDs reais da sua conta.
