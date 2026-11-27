"""Gera indicadores.lvdash.json (AI/BI Dashboard). Rode: python3 src/dashboards/build_dashboard.py

As consultas usam só o NOME da tabela; catálogo/schema vêm do bundle (dataset_catalog/dataset_schema),
então o mesmo arquivo serve para qualquer ambiente.
"""
import json
from pathlib import Path


def ql(sql: str) -> list[str]:
    return [line + "\n" for line in sql.strip().splitlines()]


def text(name, lines, x, y, w, h):
    return {"widget": {"name": name, "multilineTextboxSpec": {"lines": lines}}, "position": {"x": x, "y": y, "width": w, "height": h}}


def counter(name, title, field, fmt, template, x, y):
    return {
        "widget": {
            "name": name,
            "queries": [{"name": "main_query", "query": {"datasetName": "ds_kpis", "fields": [{"name": field, "expression": f"`{field}`"}], "disaggregated": True}}],
            "spec": {"version": 2, "widgetType": "counter",
                     "encodings": {"value": {"fieldName": field, "displayName": title, "format": fmt, "formatTemplate": template}},
                     "frame": {"showTitle": True, "title": title, "showDescription": True, "description": "Último valor publicado pelo BCB"}},
        },
        "position": {"x": x, "y": y, "width": 3, "height": 3},
    }


def line(name, title, ds, x_field, ys, x, y, w, h, kind="line", desc=""):
    fields = [{"name": x_field, "expression": f"`{x_field}`"}] + [{"name": f, "expression": f"`{f}`"} for f, _ in ys]
    y_enc = {"scale": {"type": "quantitative"}, "fields": [{"fieldName": f, "displayName": d} for f, d in ys]} if len(ys) > 1 \
        else {"fieldName": ys[0][0], "displayName": ys[0][1], "scale": {"type": "quantitative"}}
    return {
        "widget": {
            "name": name,
            "queries": [{"name": "main_query", "query": {"datasetName": ds, "fields": fields, "disaggregated": True}}],
            "spec": {"version": 3, "widgetType": kind,
                     "encodings": {"x": {"fieldName": x_field, "displayName": "Data", "scale": {"type": "temporal"}}, "y": y_enc},
                     "frame": {"showTitle": True, "title": title, "showDescription": bool(desc), "description": desc}},
        },
        "position": {"x": x, "y": y, "width": w, "height": h},
    }


PCT = {"type": "number-plain", "decimalPlaces": {"type": "max", "places": 2}}
BRL = {"type": "number-plain", "decimalPlaces": {"type": "max", "places": 4}}

datasets = [
    {"name": "ds_kpis", "displayName": "Últimos valores", "queryLines": ql("""
WITH u AS (SELECT * FROM ultimos_valores),
m AS (SELECT max_by(ipca_12m_pct, mes) AS ipca_12m, max_by(mes, mes) AS mes_ipca
      FROM indicadores_mensais WHERE ipca_12m_pct IS NOT NULL)
SELECT
  max(CASE WHEN serie = 'dolar_venda' THEN ultimo_valor END) AS dolar,
  max(CASE WHEN serie = 'euro_venda'  THEN ultimo_valor END) AS euro,
  max(CASE WHEN serie = 'selic_meta'  THEN ultimo_valor END) AS selic,
  max(m.ipca_12m)                                            AS ipca_12m,
  concat('Ref.: ', date_format(max(CASE WHEN serie = 'dolar_venda' THEN data_referencia END), 'dd/MM/yyyy')) AS ref
FROM u CROSS JOIN m""")},
    {"name": "ds_cambio", "displayName": "Câmbio diário", "queryLines": ql("""
SELECT data, dolar, euro, dolar_media_30d, euro_media_30d, dolar_variacao_pct
FROM cambio_diario
ORDER BY data""")},
    {"name": "ds_mensal", "displayName": "Indicadores mensais", "queryLines": ql("""
SELECT mes AS data, dolar_medio, dolar_fechamento, euro_medio, selic_meta_pct_aa, cdi_acumulado_mes_pct,
       ipca_mes_pct, ipca_12m_pct, juro_real_aprox_pct, dias_uteis
FROM indicadores_mensais
ORDER BY mes""")},
]

overview = [
    text("titulo", ["# 🏦 Indicadores Econômicos · Banco Central do Brasil\n", "\n",
                    "Câmbio, juros e inflação coletados diariamente da API SGS do BCB por uma **AWS Lambda**, "
                    "processados na arquitetura **medalhão** (Bronze → Silver → Gold) e governados pelo **Unity Catalog**. "
                    "Fonte: `econ_prod.gold` · atualização diária às 21h."], 0, 0, 12, 2),
    counter("kpi_dolar", "Dólar (venda)", "dolar", BRL, "R$ {{@formatted}}", 0, 2),
    counter("kpi_euro", "Euro (venda)", "euro", BRL, "R$ {{@formatted}}", 3, 2),
    counter("kpi_selic", "Selic meta", "selic", PCT, "{{@formatted}}% a.a.", 6, 2),
    counter("kpi_ipca", "IPCA 12 meses", "ipca_12m", PCT, "{{@formatted}}%", 9, 2),
    line("graf_dolar", "Dólar: cotação diária e média móvel de 30 dias úteis", "ds_cambio", "data",
         [("dolar", "Dólar (R$)"), ("dolar_media_30d", "Média 30d")], 0, 5, 12, 6),
    line("graf_juros", "Selic vs inflação: o juro real", "ds_mensal", "data",
         [("selic_meta_pct_aa", "Selic meta (% a.a.)"), ("ipca_12m_pct", "IPCA 12m (%)"), ("juro_real_aprox_pct", "Juro real (%)")],
         0, 11, 6, 6, desc="Juro real ≈ (1 + Selic) / (1 + IPCA 12m) − 1"),
    line("graf_ipca", "IPCA mensal (%)", "ds_mensal", "data", [("ipca_mes_pct", "IPCA no mês (%)")], 6, 11, 6, 6, kind="bar"),
    {
        "widget": {
            "name": "tabela_mensal",
            "queries": [{"name": "main_query", "query": {"datasetName": "ds_mensal", "fields": [
                {"name": c, "expression": f"`{c}`"} for c in
                ["data", "dolar_medio", "euro_medio", "selic_meta_pct_aa", "cdi_acumulado_mes_pct", "ipca_mes_pct", "ipca_12m_pct", "juro_real_aprox_pct"]
            ], "disaggregated": True, "orders": [{"direction": "DESC", "expression": "`data`"}]}}],
            "spec": {"version": 2, "widgetType": "table", "encodings": {"columns": [
                {"fieldName": "data", "displayName": "Mês", "dateTimeFormat": "MM/yyyy"},
                {"fieldName": "dolar_medio", "displayName": "Dólar médio"},
                {"fieldName": "euro_medio", "displayName": "Euro médio"},
                {"fieldName": "selic_meta_pct_aa", "displayName": "Selic (% a.a.)"},
                {"fieldName": "cdi_acumulado_mes_pct", "displayName": "CDI no mês (%)"},
                {"fieldName": "ipca_mes_pct", "displayName": "IPCA no mês (%)"},
                {"fieldName": "ipca_12m_pct", "displayName": "IPCA 12m (%)"},
                {"fieldName": "juro_real_aprox_pct", "displayName": "Juro real (%)"},
            ]}, "frame": {"showTitle": True, "title": "Tabela mensal"}},
        },
        "position": {"x": 0, "y": 17, "width": 12, "height": 7},
    },
]

filtro = {
    "widget": {
        "name": "filtro_periodo",
        "queries": [
            {"name": "q_cambio", "query": {"datasetName": "ds_cambio", "fields": [{"name": "data", "expression": "`data`"}], "disaggregated": False}},
            {"name": "q_mensal", "query": {"datasetName": "ds_mensal", "fields": [{"name": "data", "expression": "`data`"}], "disaggregated": False}},
        ],
        "spec": {"version": 2, "widgetType": "filter-date-range-picker",
                 "encodings": {"fields": [
                     {"fieldName": "data", "displayName": "Período", "queryName": "q_cambio"},
                     {"fieldName": "data", "displayName": "Período", "queryName": "q_mensal"},
                 ]},
                 "frame": {"showTitle": True, "title": "Período"}},
    },
    "position": {"x": 0, "y": 0, "width": 2, "height": 2},
}

dashboard = {
    "datasets": datasets,
    "pages": [
        {"name": "visao_geral", "displayName": "Visão geral", "pageType": "PAGE_TYPE_CANVAS", "layoutVersion": "GRID_V1", "layout": overview},
        {"name": "filtros", "displayName": "Filtros", "pageType": "PAGE_TYPE_GLOBAL_FILTERS", "layout": [filtro]},
    ],
    "uiSettings": {"theme": {
        "canvasBackgroundColor": {"light": "#FCFCFC", "dark": "#1F272D"},
        "widgetBackgroundColor": {"light": "#FFFFFF", "dark": "#11171C"},
        "widgetBorderColor": {"light": "#FFFFFF", "dark": "#11171C"},
        "fontColor": {"light": "#11171C", "dark": "#E8ECF0"},
        "selectionColor": {"light": "#2272B4", "dark": "#8ACAFF"},
        "visualizationColors": ["#0072B2", "#E69F00", "#009E73", "#CC79A7", "#D55E00", "#56B4E9"],
        "widgetHeaderAlignment": "LEFT",
        "widgetCornerRadius": 10,
    }},
}

out = Path(__file__).with_name("indicadores.lvdash.json")
out.write_text(json.dumps(dashboard, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"ok -> {out}")
