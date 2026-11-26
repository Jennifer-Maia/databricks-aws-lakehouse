import json
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import handler  # noqa: E402

NOW = datetime(2026, 11, 26, 22, 0, 0, tzinfo=timezone.utc)


def test_janela_padrao_usa_lookback():
    assert handler.resolve_window({}, date(2026, 11, 26), 7) == (date(2026, 11, 19), date(2026, 11, 26))


def test_janela_backfill():
    assert handler.resolve_window({"start_date": "2024-01-01"}, date(2026, 11, 26), 7)[0] == date(2024, 1, 1)


def test_janela_invertida_falha():
    with pytest.raises(ValueError):
        handler.resolve_window({"start_date": "2026-12-01", "end_date": "2026-11-01"}, date(2026, 11, 26), 7)


def test_janela_maior_que_10_anos_falha():
    with pytest.raises(ValueError):
        handler.resolve_window({"start_date": "2000-01-01"}, date(2026, 11, 26), 7)


def test_serie_desconhecida_falha():
    with pytest.raises(ValueError):
        handler.resolve_series({"series": ["bitcoin"]})


def test_url_no_formato_do_sgs():
    url = handler.build_url(1, date(2026, 1, 5), date(2026, 2, 10))
    assert "bcdata.sgs.1/" in url and "dataInicial=05/01/2026" in url and "dataFinal=10/02/2026" in url


def test_s3_key_particionada_por_serie():
    assert handler.s3_key("dev", "dolar_venda", NOW) == "dev/bcb/serie=dolar_venda/2026-11-26T220000Z.json"


def test_run_grava_um_arquivo_por_serie_sem_alterar_os_dados():
    api = [{"data": "25/11/2026", "valor": "5.8825"}]
    gravados = {}

    resumo = handler.run(
        {"series": ["dolar_venda", "selic_meta"]},
        bucket="b", env="dev",
        fetch=lambda url: api,
        put=lambda bucket, key, body: gravados.__setitem__(key, json.loads(body)),
        now=NOW,
    )

    assert len(gravados) == 2 and len(resumo["arquivos"]) == 2
    payload = gravados["dev/bcb/serie=dolar_venda/2026-11-26T220000Z.json"]
    assert payload["dados"] == api            # raw: exatamente como veio
    assert payload["codigo_sgs"] == 1
    assert payload["qtd_registros"] == 1
    assert payload["coletado_em"] == NOW.isoformat()


def test_run_sem_dados_ainda_grava_envelope_vazio():
    gravados = {}
    handler.run({"series": ["ipca_mensal"]}, bucket="b", env="prod", fetch=lambda url: [],
                put=lambda b, k, body: gravados.__setitem__(k, json.loads(body)), now=NOW)
    assert list(gravados.values())[0]["qtd_registros"] == 0
