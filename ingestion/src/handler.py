"""Lambda de ingestão: API SGS do Banco Central -> S3 (camada raw/landing).

Para cada série configurada, busca os valores de uma janela de datas e grava UM arquivo
JSON no S3, sem transformar nada:

    s3://<BUCKET>/<ENV>/bcb/serie=<nome>/<AAAA-MM-DD>T<HHMMSS>Z.json

Evento (todos os campos são opcionais):
    {}                                          -> últimos LOOKBACK_DAYS dias (execução diária)
    {"start_date": "2024-01-01"}                -> carga histórica (backfill) até hoje
    {"start_date": "...", "end_date": "...", "series": ["dolar_venda"]}

Por que reler os últimos dias todo dia? Porque o BCB publica com atraso e às vezes corrige
valores. A Silver deduplica por (série, data), então reler é seguro (idempotente).

Só usa a biblioteca padrão + boto3 (que já vem no runtime Python da Lambda).
"""

from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone
from typing import Callable

logger = logging.getLogger()
logger.setLevel(logging.INFO)

API_URL = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{codigo}/dados?formato=json&dataInicial={ini}&dataFinal={fim}"

# nome -> (código SGS, descrição). O nome vira a partição no S3 e a coluna `serie` na Silver.
SERIES: dict[str, tuple[int, str]] = {
    "dolar_venda": (1, "Taxa de câmbio livre - Dólar americano (venda) - diário"),
    "euro_venda": (21619, "Taxa de câmbio - Euro (venda) - diário"),
    "selic_meta": (432, "Meta da taxa Selic definida pelo Copom (% a.a.)"),
    "cdi_diario": (12, "Taxa de juros CDI (% a.d.)"),
    "ipca_mensal": (433, "IPCA - variação mensal (%)"),
}

# A API do SGS aceita no máximo 10 anos por consulta em séries diárias.
MAX_WINDOW_DAYS = 3650


def parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def resolve_window(event: dict, today: date, lookback_days: int) -> tuple[date, date]:
    """Define a janela [início, fim] a partir do evento."""
    end = parse_date(event["end_date"]) if event.get("end_date") else today
    start = parse_date(event["start_date"]) if event.get("start_date") else end - timedelta(days=lookback_days)
    if start > end:
        raise ValueError(f"start_date ({start}) depois de end_date ({end})")
    if (end - start).days > MAX_WINDOW_DAYS:
        raise ValueError(f"janela de {(end - start).days} dias: o SGS aceita no máximo {MAX_WINDOW_DAYS}")
    return start, end


def resolve_series(event: dict) -> list[str]:
    wanted = event.get("series") or list(SERIES)
    unknown = sorted(set(wanted) - set(SERIES))
    if unknown:
        raise ValueError(f"séries desconhecidas: {unknown}. Válidas: {sorted(SERIES)}")
    return wanted


def build_url(codigo: int, start: date, end: date) -> str:
    return API_URL.format(codigo=codigo, ini=start.strftime("%d/%m/%Y"), fim=end.strftime("%d/%m/%Y"))


def http_get_json(url: str, retries: int = 3, timeout: int = 20) -> list[dict]:
    """GET com retentativa (backoff exponencial). 404 do SGS = sem dados na janela."""
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "econ-ingest/1.0"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return []
            if exc.code < 500 or attempt == retries:
                raise
        except (urllib.error.URLError, TimeoutError):
            if attempt == retries:
                raise
        time.sleep(2 ** attempt)
    return []


def build_payload(nome: str, codigo: int, descricao: str, url: str, dados: list[dict], start: date, end: date, now: datetime) -> dict:
    """Envelope com metadados + os dados EXATAMENTE como vieram da API."""
    return {
        "serie": nome,
        "codigo_sgs": codigo,
        "descricao": descricao,
        "fonte_url": url,
        "janela_inicio": start.isoformat(),
        "janela_fim": end.isoformat(),
        "coletado_em": now.isoformat(),
        "qtd_registros": len(dados),
        "dados": dados,
    }


def s3_key(env: str, nome: str, now: datetime) -> str:
    return f"{env}/bcb/serie={nome}/{now.strftime('%Y-%m-%dT%H%M%SZ')}.json"


def run(event: dict, *, bucket: str, env: str, fetch: Callable[[str], list[dict]], put: Callable[[str, str, bytes], None],
        now: datetime, lookback_days: int = 7) -> dict:
    """Núcleo testável: sem boto3 nem rede (fetch e put são injetados)."""
    start, end = resolve_window(event, now.date(), lookback_days)
    resumo = []
    for nome in resolve_series(event):
        codigo, descricao = SERIES[nome]
        url = build_url(codigo, start, end)
        dados = fetch(url)
        payload = build_payload(nome, codigo, descricao, url, dados, start, end, now)
        key = s3_key(env, nome, now)
        put(bucket, key, json.dumps(payload, ensure_ascii=False).encode("utf-8"))
        logger.info(json.dumps({"serie": nome, "registros": len(dados), "s3_key": key}))
        resumo.append({"serie": nome, "registros": len(dados), "s3_key": key})
    return {"bucket": bucket, "env": env, "janela": [start.isoformat(), end.isoformat()], "arquivos": resumo}


def lambda_handler(event, context):  # pragma: no cover - integração (testada na AWS)
    import boto3

    s3 = boto3.client("s3")

    def put(bucket: str, key: str, body: bytes) -> None:
        s3.put_object(Bucket=bucket, Key=key, Body=body, ContentType="application/json")

    return run(
        event or {},
        bucket=os.environ["RAW_BUCKET"],
        env=os.environ["ENV"],
        fetch=http_get_json,
        put=put,
        now=datetime.now(timezone.utc),
        lookback_days=int(os.environ.get("LOOKBACK_DAYS", "7")),
    )
