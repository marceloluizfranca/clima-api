"""Métricas Prometheus expostas em /metrics."""

import time

from prometheus_client import Counter, Histogram
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

REQUISICOES = Counter(
    "clima_http_requisicoes_total",
    "Total de requisições HTTP recebidas",
    ["metodo", "rota", "status"],
)

DURACAO = Histogram(
    "clima_http_duracao_segundos",
    "Duração das requisições HTTP",
    ["metodo", "rota"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10),
)

FALHAS_OPEN_METEO = Counter(
    "clima_open_meteo_falhas_total",
    "Falhas ao consultar a Open-Meteo",
    ["endpoint"],
)

# Rotas de infraestrutura ficam fora para não poluir os gráficos
ROTAS_IGNORADAS = {"/metrics", "/healthz", "/readyz"}


class MiddlewareMetricas(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        inicio = time.perf_counter()
        status = 500
        try:
            resposta = await call_next(request)
            status = resposta.status_code
            return resposta
        finally:
            # Usa o template da rota (ex.: /v1/clima/hoje) para não explodir a cardinalidade
            rota = getattr(request.scope.get("route"), "path", "desconhecida")
            if rota not in ROTAS_IGNORADAS:
                REQUISICOES.labels(request.method, rota, str(status)).inc()
                DURACAO.labels(request.method, rota).observe(time.perf_counter() - inicio)
