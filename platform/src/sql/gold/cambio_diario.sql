-- comment: Cotação diária de venda do dólar e do euro (R$), variação diária e média móvel de 30 dias úteis
-- GOLD: câmbio diário (dólar e euro, venda) pronto para gráfico.
WITH pivot AS (
  SELECT
    data,
    max(CASE WHEN serie = 'dolar_venda' THEN valor END) AS dolar,
    max(CASE WHEN serie = 'euro_venda'  THEN valor END) AS euro
  FROM silver.bcb_observacoes
  WHERE serie IN ('dolar_venda', 'euro_venda')
  GROUP BY data
)
SELECT
  data,
  dolar,
  euro,
  round((dolar / lag(dolar) OVER w - 1) * 100, 4)                                    AS dolar_variacao_pct,
  round((euro  / lag(euro)  OVER w - 1) * 100, 4)                                    AS euro_variacao_pct,
  round(avg(dolar) OVER (ORDER BY data ROWS BETWEEN 29 PRECEDING AND CURRENT ROW), 4) AS dolar_media_30d,
  round(avg(euro)  OVER (ORDER BY data ROWS BETWEEN 29 PRECEDING AND CURRENT ROW), 4) AS euro_media_30d,
  round(euro / dolar, 4)                                                             AS euro_em_dolares
FROM pivot
WINDOW w AS (ORDER BY data)
