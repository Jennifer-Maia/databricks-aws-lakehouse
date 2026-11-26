-- comment: Último valor publicado de cada série do BCB e a data de referência
-- GOLD: o valor mais recente de cada série (para os "cartões" do dashboard).
SELECT
  serie,
  codigo_sgs,
  descricao,
  max_by(valor, data) AS ultimo_valor,
  max(data)           AS data_referencia,
  max(coletado_em)    AS coletado_em
FROM silver.bcb_observacoes
GROUP BY serie, codigo_sgs, descricao
