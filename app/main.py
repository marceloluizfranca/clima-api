"""API de clima: previsão do tempo do dia por cidade ou coordenadas."""

import os
from contextlib import asynccontextmanager
from typing import Annotated

import httpx
from fastapi import FastAPI, HTTPException, Query, Request, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from app.clima import CONDICOES_WMO, CidadeNaoEncontrada, ClienteOpenMeteo, ErroOpenMeteo, Local
from app import metricas
from app.metricas import CONDICOES, CONSULTAS, CONSULTAS_POR_CIDADE, MiddlewareMetricas

VERSAO = os.getenv("APP_VERSION", "dev")


@asynccontextmanager
async def ciclo_de_vida(app: FastAPI):
    async with httpx.AsyncClient(timeout=5.0) as http:
        app.state.open_meteo = ClienteOpenMeteo(http)
        yield


app = FastAPI(
    title="Clima API",
    description="Previsão do tempo para hoje, por nome da cidade ou coordenadas.",
    version=VERSAO,
    lifespan=ciclo_de_vida,
)
app.add_middleware(MiddlewareMetricas)
metricas.inicializar([*CONDICOES_WMO.values(), "Desconhecida"])


@app.get("/metrics", include_in_schema=False)
async def expor_metricas():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/healthz", include_in_schema=False)
async def healthz():
    return {"status": "ok"}


@app.get("/readyz", include_in_schema=False)
async def readyz():
    # A Open-Meteo não entra no readiness: se ela cair, os pods continuam
    # recebendo tráfego e respondem 502 em vez de saírem todos do Service.
    return {"status": "ok", "versao": VERSAO}


@app.get("/v1/clima/hoje", summary="Previsão do tempo para hoje")
async def clima_hoje(
    request: Request,
    cidade: Annotated[str | None, Query(min_length=2, description="Nome da cidade, ex.: Recife")] = None,
    lat: Annotated[float | None, Query(ge=-90, le=90, description="Latitude")] = None,
    lon: Annotated[float | None, Query(ge=-180, le=180, description="Longitude")] = None,
):
    tem_coordenadas = lat is not None and lon is not None
    if (lat is None) != (lon is None):
        raise HTTPException(400, "Informe lat e lon juntos.")
    if bool(cidade) == tem_coordenadas:
        raise HTTPException(400, "Informe 'cidade' ou o par 'lat'/'lon' (apenas um dos dois).")

    cliente: ClienteOpenMeteo = request.app.state.open_meteo
    try:
        local = await cliente.geocodificar(cidade) if cidade else Local(latitude=lat, longitude=lon)
        previsao = await cliente.previsao_hoje(local)
    except CidadeNaoEncontrada:
        raise HTTPException(404, f"Cidade '{cidade}' não encontrada.")
    except ErroOpenMeteo:
        raise HTTPException(502, "Serviço de previsão indisponível no momento.")

    CONSULTAS.labels("cidade" if cidade else "coordenadas").inc()
    if cidade:
        CONSULTAS_POR_CIDADE.labels(local.nome or "", local.pais or "").inc()
    CONDICOES.labels(previsao["condicao"]).inc()
    return previsao
