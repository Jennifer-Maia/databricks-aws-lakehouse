"""Regras de transformação do lakehouse econ (Python puro + PySpark, testáveis localmente).

Os notebooks em src/notebooks só fazem I/O (ler/gravar tabelas); a lógica fica aqui,
coberta por testes em tests/test_transforms.py.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pyspark.sql import DataFrame, Window
from pyspark.sql import functions as F

def bronze_metadata() -> list:
    """Colunas de metadados que a Bronze acrescenta a cada arquivo lido (precisa de sessão Spark ativa)."""
    return [
        F.col("_metadata.file_path").alias("_arquivo_origem"),
        F.col("_metadata.file_modification_time").alias("_arquivo_modificado_em"),
        F.current_timestamp().alias("_carregado_em"),
    ]

# Schema do envelope gravado pela Lambda (ingestion/src/handler.py).
BRONZE_SCHEMA_HINTS = (
    "codigo_sgs INT, qtd_registros INT, coletado_em TIMESTAMP, janela_inicio DATE, janela_fim DATE, "
    "dados ARRAY<STRUCT<data: STRING, valor: STRING>>"
)


@dataclass
class SilverResult:
    validos: DataFrame
    rejeitados: DataFrame


def explodir_e_tipar(bronze: DataFrame) -> DataFrame:
    """1 arquivo -> N observações; 'dd/MM/yyyy' -> DATE; texto -> DECIMAL. Erros viram NULL (try_*)."""
    return (
        bronze.select(
            "serie", "codigo_sgs", "descricao", "coletado_em", "_arquivo_origem",
            F.explode("dados").alias("obs"),
        )
        .select(
            "serie",
            "codigo_sgs",
            "descricao",
            F.try_to_timestamp(F.col("obs.data"), F.lit("dd/MM/yyyy")).cast("date").alias("data"),
            F.expr("try_cast(obs.valor AS DECIMAL(18, 6))").alias("valor"),
            F.col("obs.data").alias("data_original"),
            F.col("obs.valor").alias("valor_original"),
            "coletado_em",
            "_arquivo_origem",
        )
    )


def motivo_rejeicao(df: DataFrame) -> DataFrame:
    """Regras de qualidade: cada linha ganha o motivo da rejeição (NULL = válida)."""
    return df.withColumn(
        "_motivo_rejeicao",
        F.when(F.col("serie").isNull(), F.lit("serie_nula"))
        .when(F.col("data").isNull(), F.lit("data_invalida"))
        .when(F.col("valor").isNull(), F.lit("valor_invalido"))
        .when(F.col("data") > F.current_date(), F.lit("data_futura")),
    )


def deduplicar(df: DataFrame) -> DataFrame:
    """1 linha por (serie, data): fica a coleta MAIS RECENTE (o BCB pode corrigir valores)."""
    janela = Window.partitionBy("serie", "data").orderBy(F.col("coletado_em").desc(), F.col("_arquivo_origem").desc())
    return df.withColumn("_ordem", F.row_number().over(janela)).filter("_ordem = 1").drop("_ordem")


def silver_observacoes(bronze: DataFrame) -> SilverResult:
    """Bronze -> Silver: tipa, valida (rejeitados vão para quarentena) e deduplica."""
    com_motivo = motivo_rejeicao(explodir_e_tipar(bronze))
    rejeitados = com_motivo.filter(F.col("_motivo_rejeicao").isNotNull())
    validos = deduplicar(
        com_motivo.filter(F.col("_motivo_rejeicao").isNull()).drop("_motivo_rejeicao", "data_original", "valor_original")
    )
    return SilverResult(validos=validos, rejeitados=rejeitados)


def carregar_sql_gold(pasta: Path) -> dict[str, tuple[str, str]]:
    """Lê src/sql/gold/*.sql -> {tabela: (comentário, SELECT)}. O nome do arquivo é o nome da tabela."""
    consultas = {}
    for arquivo in sorted(pasta.glob("*.sql")):
        texto = arquivo.read_text(encoding="utf-8")
        primeira = texto.splitlines()[0]
        comentario = primeira.removeprefix("-- comment:").strip() if primeira.startswith("-- comment:") else ""
        consultas[arquivo.stem] = (comentario, texto)
    return consultas
