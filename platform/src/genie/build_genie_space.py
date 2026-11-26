"""Gera a definição do Genie "Analista Econômico" (perguntas em português sobre a camada Gold).

Uso:  python3 src/genie/build_genie_space.py   ->  src/genie/analista_economico.<catalog>.geniespace.json

O Genie exige o nome COMPLETO das tabelas, então há um arquivo por catálogo.
IDs são derivados do texto (md5): o arquivo só muda quando o conteúdo muda.
"""

import hashlib
import json
from pathlib import Path

CATALOGS = ["econ_prod"]

SAMPLE_QUESTIONS = [
    "Qual é a cotação mais recente do dólar e do euro?",
    "Como o dólar variou nos últimos 12 meses?",
    "Em qual mês a Selic esteve mais alta?",
    "Qual foi o juro real no último mês disponível?",
    "Qual foi o IPCA acumulado em 12 meses em cada mês de 2026?",
    "Quais foram os 5 dias de maior alta do dólar?",
    "Quanto rendeu o CDI acumulado em 2025?",
]

INSTRUCTIONS = [
    "Você responde perguntas sobre indicadores econômicos do Brasil, com dados oficiais do Banco Central (API SGS).\n",
    "Tabelas: cambio_diario (1 linha por dia útil: dólar e euro de venda em R$), indicadores_mensais (1 linha por mês: "
    "câmbio médio, Selic meta, CDI acumulado no mês, IPCA do mês, IPCA 12 meses e juro real) e ultimos_valores "
    "(último valor de cada série).\n",
    "Para 'cotação atual' ou 'mais recente', use ultimos_valores ou a maior data de cambio_diario e informe a data de referência.\n",
    "Taxas em % já estão em pontos percentuais (13.75 = 13,75%). Nunca some taxas de meses diferentes: "
    "para acumular use (EXP(SUM(LN(1 + taxa/100))) - 1) * 100.\n",
    "Juro real = juro_real_aprox_pct (Selic meta descontada do IPCA 12 meses). Só existe quando há 12 meses de IPCA.\n",
    "O IPCA é mensal e sai com cerca de 10 dias de atraso: o mês atual pode não ter IPCA ainda; diga isso ao usuário.\n",
    "Sem período informado, use todo o histórico e diga o intervalo de datas. Responda em português do Brasil; "
    "valores em R$ com 4 casas e taxas com 2 casas e o símbolo %.",
]

TABLES = {
    "cambio_diario": {
        "data": (["Dia útil da cotação."], ["dia", "data da cotação"]),
        "dolar": (["Dólar americano, venda, em R$ (PTAX/SGS 1)."], ["dólar", "USD", "cotação do dólar"]),
        "euro": (["Euro, venda, em R$ (SGS 21619)."], ["euro", "EUR"]),
        "dolar_variacao_pct": (["Variação % do dólar em relação ao dia útil anterior."], ["alta do dólar", "variação diária"]),
        "euro_variacao_pct": (["Variação % do euro em relação ao dia útil anterior."], ["variação do euro"]),
        "dolar_media_30d": (["Média móvel de 30 dias úteis do dólar."], ["média móvel"]),
        "euro_media_30d": (["Média móvel de 30 dias úteis do euro."], []),
        "euro_em_dolares": (["Quantos dólares vale 1 euro (euro/dólar)."], ["EUR/USD", "paridade"]),
    },
    "indicadores_mensais": {
        "mes": (["Primeiro dia do mês de referência."], ["mês", "competência"]),
        "dolar_medio": (["Média do dólar no mês."], ["dólar médio"]),
        "dolar_fechamento": (["Dólar no último dia útil do mês."], ["fechamento"]),
        "euro_medio": (["Média do euro no mês."], []),
        "selic_meta_pct_aa": (["Meta da Selic no fim do mês, % ao ano."], ["Selic", "taxa básica de juros"]),
        "cdi_acumulado_mes_pct": (["CDI acumulado no mês, %."], ["CDI", "rendimento do CDI"]),
        "ipca_mes_pct": (["IPCA do mês, %."], ["inflação do mês", "IPCA mensal"]),
        "ipca_12m_pct": (["IPCA acumulado em 12 meses, %."], ["inflação anual", "inflação em 12 meses"]),
        "juro_real_aprox_pct": (["Juro real aproximado: (1+Selic)/(1+IPCA 12m)-1, %."], ["juro real"]),
        "dias_uteis": (["Dias úteis com cotação no mês."], []),
    },
    "ultimos_valores": {
        "serie": (["Nome da série: dolar_venda, euro_venda, selic_meta, cdi_diario, ipca_mensal."], ["indicador"]),
        "codigo_sgs": (["Código da série no SGS do Banco Central."], []),
        "descricao": (["Descrição oficial da série."], []),
        "ultimo_valor": (["Valor mais recente publicado."], ["valor atual"]),
        "data_referencia": (["Data a que o último valor se refere."], ["data de referência"]),
        "coletado_em": (["Quando a Lambda coletou o dado."], []),
    },
}
CATEGORICAL = {"serie"}


def hid(*parts: str) -> str:
    return hashlib.md5("|".join(parts).encode("utf-8")).hexdigest()


def example_sqls(c: str) -> list[tuple[str, str]]:
    return [
        ("Quais foram os 5 dias de maior alta do dólar?",
         f"SELECT data, dolar, dolar_variacao_pct FROM {c}.gold.cambio_diario "
         "WHERE dolar_variacao_pct IS NOT NULL ORDER BY dolar_variacao_pct DESC LIMIT 5"),
        ("Quanto rendeu o CDI acumulado em 2025?",
         f"SELECT ROUND((EXP(SUM(LN(1 + cdi_acumulado_mes_pct / 100))) - 1) * 100, 2) AS cdi_acumulado_2025_pct "
         f"FROM {c}.gold.indicadores_mensais WHERE YEAR(mes) = 2025"),
        ("Qual foi o juro real no último mês disponível?",
         f"SELECT mes, selic_meta_pct_aa, ipca_12m_pct, juro_real_aprox_pct FROM {c}.gold.indicadores_mensais "
         "WHERE juro_real_aprox_pct IS NOT NULL ORDER BY mes DESC LIMIT 1"),
    ]


def build(catalog: str) -> dict:
    tables = []
    for table, cols in sorted(TABLES.items()):
        configs = []
        for name, (desc, syn) in sorted(cols.items()):
            cfg = {"column_name": name, "description": desc, "synonyms": syn}
            if name in CATEGORICAL:
                cfg["enable_format_assistance"] = True
                cfg["enable_entity_matching"] = True
            configs.append(cfg)
        tables.append({"identifier": f"{catalog}.gold.{table}", "column_configs": configs})
    return {
        "version": 2,
        "config": {"sample_questions": sorted([{"id": hid("q", q), "question": [q]} for q in SAMPLE_QUESTIONS], key=lambda x: x["id"])},
        "data_sources": {"tables": tables},
        "instructions": {
            "text_instructions": [{"id": hid("instr"), "content": INSTRUCTIONS}],
            "example_question_sqls": sorted(
                [{"id": hid("sql", q), "question": [q], "sql": [s]} for q, s in example_sqls(catalog)], key=lambda x: x["id"]),
        },
    }


if __name__ == "__main__":
    here = Path(__file__).parent
    for catalog in CATALOGS:
        out = here / f"analista_economico.{catalog}.geniespace.json"
        out.write_text(json.dumps(build(catalog), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"Gerado: {out}")
