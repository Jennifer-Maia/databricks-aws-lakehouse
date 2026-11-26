"""Testes locais (estágio TEST): regras da Silver e as consultas da Gold, com PySpark local."""

import sys
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from pyspark.sql import SparkSession
from pyspark.sql import types as T

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from econ.transforms import carregar_sql_gold, silver_observacoes  # noqa: E402

BRONZE_SCHEMA = T.StructType([
    T.StructField("serie", T.StringType()),
    T.StructField("codigo_sgs", T.IntegerType()),
    T.StructField("descricao", T.StringType()),
    T.StructField("coletado_em", T.TimestampType()),
    T.StructField("_arquivo_origem", T.StringType()),
    T.StructField("dados", T.ArrayType(T.StructType([
        T.StructField("data", T.StringType()),
        T.StructField("valor", T.StringType()),
    ]))),
])


@pytest.fixture(scope="session")
def spark(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("spark")
    s = (
        SparkSession.builder.master("local[1]")
        .appName("econ-tests")
        .config("spark.sql.shuffle.partitions", "1")
        .config("spark.ui.enabled", "false")
        .config("spark.sql.warehouse.dir", str(tmp / "warehouse"))
        .config("spark.local.dir", str(tmp / "local"))
        .config("spark.sql.session.timeZone", "UTC")
        .getOrCreate()
    )
    yield s
    s.stop()


def arquivo(serie, codigo, coletado, dados, origem="f.json"):
    return (serie, codigo, serie, coletado, origem, [{"data": d, "valor": v} for d, v in dados])


def test_silver_tipa_e_explode(spark):
    bronze = spark.createDataFrame([arquivo("dolar_venda", 1, datetime(2026, 11, 26), [("24/11/2026", "5.8573"), ("25/11/2026", "5.8825")])], BRONZE_SCHEMA)
    linhas = silver_observacoes(bronze).validos.orderBy("data").collect()
    assert [(r.data, r.valor) for r in linhas] == [(date(2026, 11, 24), Decimal("5.857300")), (date(2026, 11, 25), Decimal("5.882500"))]


def test_silver_deduplica_ficando_com_a_coleta_mais_recente(spark):
    bronze = spark.createDataFrame([
        arquivo("dolar_venda", 1, datetime(2026, 11, 25), [("24/11/2026", "5.80")], "antigo.json"),
        arquivo("dolar_venda", 1, datetime(2026, 11, 26), [("24/11/2026", "5.85")], "novo.json"),  # BCB corrigiu
    ], BRONZE_SCHEMA)
    linhas = silver_observacoes(bronze).validos.collect()
    assert len(linhas) == 1 and linhas[0].valor == Decimal("5.850000") and linhas[0]._arquivo_origem == "novo.json"


def test_silver_manda_invalidos_para_quarentena(spark):
    bronze = spark.createDataFrame([arquivo("dolar_venda", 1, datetime(2026, 11, 26), [
        ("24/11/2026", "5.85"), ("data-ruim", "5.86"), ("25/11/2026", "abc"), ("01/01/2999", "6.00"),
    ])], BRONZE_SCHEMA)
    r = silver_observacoes(bronze)
    assert r.validos.count() == 1
    motivos = sorted(x._motivo_rejeicao for x in r.rejeitados.collect())
    assert motivos == ["data_futura", "data_invalida", "valor_invalido"]


@pytest.fixture(scope="module")
def silver(spark):
    """Silver sintética: 13 meses de dólar/euro/selic/cdi/ipca para exercitar a Gold."""
    linhas = []
    for i in range(13):
        ano, mes = 2025 + (i // 12), (i % 12) + 1
        for dia in (5, 20):
            d = date(ano, mes, dia)
            linhas += [("dolar_venda", d, Decimal("5.00") + Decimal(i) / 10), ("euro_venda", d, Decimal("6.00")),
                       ("selic_meta", d, Decimal("15.00")), ("cdi_diario", d, Decimal("0.05"))]
        linhas.append(("ipca_mensal", date(ano, mes, 1), Decimal("0.50")))
    schema = "serie STRING, data DATE, valor DECIMAL(18,6)"
    df = spark.createDataFrame(linhas, schema).selectExpr("*", "0 AS codigo_sgs", "serie AS descricao", "current_timestamp() AS coletado_em")
    spark.sql("CREATE DATABASE IF NOT EXISTS silver")
    df.write.mode("overwrite").saveAsTable("silver.bcb_observacoes")
    return df


@pytest.fixture(scope="module")
def gold(spark, silver):
    return {nome: spark.sql(sql) for nome, (_, sql) in carregar_sql_gold(ROOT / "src" / "sql" / "gold").items()}


def test_gold_tem_as_tres_tabelas_com_comentario(gold):
    consultas = carregar_sql_gold(ROOT / "src" / "sql" / "gold")
    assert set(gold) == {"cambio_diario", "indicadores_mensais", "ultimos_valores"}
    assert all(comentario for comentario, _ in consultas.values())


def test_gold_cambio_variacao_e_razao(gold):
    linhas = gold["cambio_diario"].orderBy("data").collect()
    assert linhas[0].dolar_variacao_pct is None            # primeiro dia não tem anterior
    assert float(linhas[0].euro_em_dolares) == pytest.approx(1.2)


def test_gold_mensal_ipca_12m_so_com_12_meses(gold):
    meses = gold["indicadores_mensais"].orderBy("mes").collect()
    assert len(meses) == 13
    assert all(m.ipca_12m_pct is None for m in meses[:11])
    assert float(meses[11].ipca_12m_pct) == pytest.approx((1.005 ** 12 - 1) * 100, abs=0.01)  # 6,17%
    assert float(meses[11].cdi_acumulado_mes_pct) == pytest.approx((1.0005 ** 2 - 1) * 100, abs=1e-3)
    assert meses[11].juro_real_aprox_pct is not None


def test_gold_ultimos_valores_pega_a_data_mais_recente(gold):
    dolar = [r for r in gold["ultimos_valores"].collect() if r.serie == "dolar_venda"][0]
    assert dolar.data_referencia == date(2026, 1, 20) and float(dolar.ultimo_valor) == pytest.approx(6.2)
