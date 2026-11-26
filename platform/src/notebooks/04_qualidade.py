# Databricks notebook source
# MAGIC %md
# MAGIC # 04 · Qualidade: o job FALHA se alguma regra for quebrada
# MAGIC
# MAGIC | Regra | Por quê |
# MAGIC |---|---|
# MAGIC | Silver sem duplicatas por (serie, data) | garante a deduplicação |
# MAGIC | Todas as 5 séries presentes | uma série sumida = ingestão quebrada |
# MAGIC | Dólar atualizado há no máximo 5 dias | detecta ingestão parada (feriados longos cabem) |
# MAGIC | Gold não vazia | consumo depende dela |
# MAGIC | Rejeitados < 1% | muita rejeição = mudança no formato da API |

# COMMAND ----------

catalog = dbutils.widgets.get("catalog")
q = lambda sql: spark.sql(sql.format(c=catalog)).collect()[0][0]

checks = {
    "silver_sem_duplicatas": q("SELECT count(*) FROM (SELECT serie, data FROM {c}.silver.bcb_observacoes GROUP BY ALL HAVING count(*) > 1)") == 0,
    "cinco_series_presentes": q("SELECT count(DISTINCT serie) FROM {c}.silver.bcb_observacoes") == 5,
    "dolar_atualizado": q("SELECT datediff(current_date(), max(data)) FROM {c}.gold.cambio_diario") <= 5,
    "gold_cambio_nao_vazia": q("SELECT count(*) FROM {c}.gold.cambio_diario") > 0,
    "gold_mensal_nao_vazia": q("SELECT count(*) FROM {c}.gold.indicadores_mensais") > 0,
    "rejeitados_abaixo_1pct": q(
        "SELECT coalesce((SELECT count(*) FROM {c}.silver.bcb_observacoes_rejeitadas) / nullif((SELECT count(*) FROM {c}.silver.bcb_observacoes), 0), 0)"
    ) < 0.01,
}

for nome, ok in checks.items():
    print(f"{'OK   ' if ok else 'FALHA'} {nome}")

falhas = [n for n, ok in checks.items() if not ok]
assert not falhas, f"Regras de qualidade quebradas: {falhas}"
