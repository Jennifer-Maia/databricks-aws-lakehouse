# Databricks notebook source
# MAGIC %md
# MAGIC # 01 · Bronze: landing (JSON) → `bronze.bcb_series_raw`
# MAGIC
# MAGIC **Auto Loader** (`cloudFiles`) lê **só os arquivos novos** do volume `landing.bcb`
# MAGIC (o checkpoint guarda o que já foi processado). `trigger(availableNow=True)` processa
# MAGIC tudo o que chegou e **para**: streaming com custo de batch.
# MAGIC
# MAGIC Nada é transformado: o JSON fica intacto + metadados de carga.

# COMMAND ----------

import os
import sys

sys.path.append(os.path.abspath(".."))  # src/ -> import econ
from econ.transforms import BRONZE_SCHEMA_HINTS, bronze_metadata

catalog = dbutils.widgets.get("catalog")
origem = f"/Volumes/{catalog}/landing/bcb/"
checkpoints = f"/Volumes/{catalog}/bronze/_checkpoints/bcb_series_raw"
tabela = f"{catalog}.bronze.bcb_series_raw"

spark.sql(f"CREATE VOLUME IF NOT EXISTS {catalog}.bronze._checkpoints COMMENT 'Checkpoints e schemas do Auto Loader'")
print(f"{origem} -> {tabela}")

# COMMAND ----------

stream = (
    spark.readStream.format("cloudFiles")
    .option("cloudFiles.format", "json")
    .option("cloudFiles.schemaLocation", f"{checkpoints}/_schema")
    .option("cloudFiles.schemaHints", BRONZE_SCHEMA_HINTS)
    .option("cloudFiles.inferColumnTypes", "true")
    .load(origem)
    .select("*", *bronze_metadata())
)

query = (
    stream.writeStream.option("checkpointLocation", f"{checkpoints}/_checkpoint")
    .option("mergeSchema", "true")
    .trigger(availableNow=True)
    .toTable(tabela)
)
query.awaitTermination()

# COMMAND ----------

novos = sum((p.get("numInputRows") or 0) for p in query.recentProgress)
total = spark.table(tabela).count()
spark.sql(f"COMMENT ON TABLE {tabela} IS 'Arquivos JSON da API SGS do Banco Central (1 linha por arquivo coletado pela Lambda)'")
print(f"Arquivos novos nesta execução: {novos} · total na bronze: {total}")
