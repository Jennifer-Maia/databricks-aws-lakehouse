# Databricks notebook source
# MAGIC %md
# MAGIC # 02 · Silver: `bronze.bcb_series_raw` → `silver.bcb_observacoes`
# MAGIC
# MAGIC Explode o array `dados`, tipa (DATE, DECIMAL), aplica as regras de qualidade e
# MAGIC deduplica por (série, data) ficando com a coleta mais recente.
# MAGIC Linhas inválidas vão para a **quarentena** `silver.bcb_observacoes_rejeitadas`.
# MAGIC A lógica está em `src/econ/transforms.py` (testada com pytest).

# COMMAND ----------

import os
import sys

sys.path.append(os.path.abspath(".."))
from econ.transforms import silver_observacoes

catalog = dbutils.widgets.get("catalog")
bronze = spark.table(f"{catalog}.bronze.bcb_series_raw")
resultado = silver_observacoes(bronze)

# COMMAND ----------

def gravar(df, tabela, comentario):
    (df.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(tabela))
    spark.sql(f"COMMENT ON TABLE {tabela} IS '{comentario}'")
    return spark.table(tabela).count()

n_validos = gravar(
    resultado.validos, f"{catalog}.silver.bcb_observacoes",
    "Observações das séries do BCB: tipadas, validadas e deduplicadas por (serie, data)",
)
n_rejeitados = gravar(
    resultado.rejeitados, f"{catalog}.silver.bcb_observacoes_rejeitadas",
    "Quarentena: observações que falharam nas regras de qualidade (coluna _motivo_rejeicao)",
)
print(f"Silver: {n_validos} válidos · {n_rejeitados} rejeitados")
