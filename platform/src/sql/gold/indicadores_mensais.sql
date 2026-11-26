-- comment: Indicadores econômicos por mês: dólar, euro, Selic, CDI acumulado, IPCA (mês e 12 meses) e juro real aproximado
-- GOLD: visão mensal que junta câmbio, juros e inflação.
-- Juros compostos: acumular taxas = multiplicar (1 + taxa). Em SQL: exp(sum(ln(1 + taxa))).
WITH mensal AS (
  SELECT
    CAST(date_trunc('MONTH', data) AS DATE)                                       AS mes,
    avg(CASE WHEN serie = 'dolar_venda' THEN valor END)                           AS dolar_medio,
    max_by(valor, data) FILTER (WHERE serie = 'dolar_venda')                      AS dolar_fechamento,
    avg(CASE WHEN serie = 'euro_venda' THEN valor END)                            AS euro_medio,
    max_by(valor, data) FILTER (WHERE serie = 'selic_meta')                       AS selic_meta_pct_aa,
    (exp(sum(ln(1 + valor / 100)) FILTER (WHERE serie = 'cdi_diario')) - 1) * 100 AS cdi_acumulado_mes_pct,
    max(CASE WHEN serie = 'ipca_mensal' THEN valor END)                           AS ipca_mes_pct,
    count(CASE WHEN serie = 'dolar_venda' THEN 1 END)                             AS dias_uteis
  FROM silver.bcb_observacoes
  GROUP BY CAST(date_trunc('MONTH', data) AS DATE)
),
com_12m AS (
  SELECT
    *,
    (exp(sum(ln(1 + ipca_mes_pct / 100)) OVER doze) - 1) * 100 AS ipca_12m_bruto,
    count(ipca_mes_pct) OVER doze                              AS meses_com_ipca
  FROM mensal
  WINDOW doze AS (ORDER BY mes ROWS BETWEEN 11 PRECEDING AND CURRENT ROW)
)
SELECT
  mes,
  round(dolar_medio, 4)                                           AS dolar_medio,
  round(dolar_fechamento, 4)                                      AS dolar_fechamento,
  round(euro_medio, 4)                                            AS euro_medio,
  round(selic_meta_pct_aa, 2)                                     AS selic_meta_pct_aa,
  round(cdi_acumulado_mes_pct, 4)                                 AS cdi_acumulado_mes_pct,
  round(ipca_mes_pct, 2)                                          AS ipca_mes_pct,
  CASE WHEN meses_com_ipca = 12 THEN round(ipca_12m_bruto, 2) END AS ipca_12m_pct,
  CASE WHEN meses_com_ipca = 12
       THEN round(((1 + selic_meta_pct_aa / 100) / (1 + ipca_12m_bruto / 100) - 1) * 100, 2)
  END                                                             AS juro_real_aprox_pct,
  dias_uteis
FROM com_12m
