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

CONSULTAS = Counter(
    "clima_consultas_total",
    "Consultas de previsão respondidas com sucesso",
    ["tipo"],
)

# A cidade vem do resultado da geocodificação (nome oficial), e não do texto
# digitado, para "recife", "Recife " e "RECIFE" contarem como a mesma cidade
# e a cardinalidade ficar limitada às cidades que existem.
CONSULTAS_POR_CIDADE = Counter(
    "clima_consultas_por_cidade_total",
    "Consultas de previsão por cidade",
    ["cidade", "pais"],
)

CONDICOES = Counter(
    "clima_condicoes_total",
    "Condição do tempo retornada nas consultas",
    ["condicao"],
)

FALHAS_OPEN_METEO = Counter(
    "clima_open_meteo_falhas_total",
    "Falhas ao consultar a Open-Meteo",
    ["endpoint"],
)

# Rotas de infraestrutura ficam fora para não poluir os gráficos
ROTAS_IGNORADAS = {"/metrics", "/healthz", "/readyz"}

ROTA_CLIMA = "/v1/clima/hoje"


def inicializar(condicoes: list[str]) -> None:
    """Cria as séries conhecidas com valor zero.

    O Prometheus não conta a primeira ocorrência de uma série em rate() e
    increase(), porque ela já nasce com valor 1. Começando em zero, a
    primeira consulta já aparece nos gráficos.
    """
    for tipo in ("cidade", "coordenadas"):
        CONSULTAS.labels(tipo)
    for condicao in condicoes:
        CONDICOES.labels(condicao)
    for status in ("200", "400", "404", "422", "502"):
        REQUISICOES.labels("GET", ROTA_CLIMA, status)
    DURACAO.labels("GET", ROTA_CLIMA)
    for endpoint in ("geocodificacao", "previsao"):
        FALHAS_OPEN_METEO.labels(endpoint)


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
