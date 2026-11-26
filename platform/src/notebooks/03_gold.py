# Databricks notebook source
# MAGIC %md
# MAGIC # 03 · Gold: `silver.bcb_observacoes` → tabelas de negócio
# MAGIC
# MAGIC Cada arquivo em `src/sql/gold/*.sql` é um `SELECT`; o nome do arquivo é o nome da tabela.
# MAGIC Os mesmos SELECTs rodam nos testes locais (tests/test_transforms.py).

# COMMAND ----------

import os
import sys
from pathlib import Path

sys.path.append(os.path.abspath(".."))
from econ.transforms import carregar_sql_gold

catalog = dbutils.widgets.get("catalog")
spark.sql(f"USE CATALOG {catalog}")  # os SELECTs usam silver.<tabela> sem catálogo

for tabela, (comentario, consulta) in carregar_sql_gold(Path("../sql/gold")).items():
    alvo = f"{catalog}.gold.{tabela}"
    spark.sql(f"CREATE OR REPLACE TABLE {alvo} COMMENT '{comentario}' AS {consulta}")
    print(f"{alvo}: {spark.table(alvo).count()} linhas")
