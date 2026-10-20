import httpx
import pytest

from app.clima import URL_GEOCODIFICACAO, ClienteOpenMeteo
from app.main import app

RESPOSTA_GEOCODIFICACAO = {
    "results": [
        {
            "name": "Recife",
            "latitude": -8.05389,
            "longitude": -34.88111,
            "admin1": "Pernambuco",
            "country": "Brasil",
        }
    ]
}

RESPOSTA_PREVISAO = {
    "timezone": "America/Recife",
    "current": {"temperature_2m": 28.0},
    "daily": {
        "time": ["2026-10-20"],
        "weather_code": [51],
        "temperature_2m_max": [29.5],
        "temperature_2m_min": [25.2],
        "precipitation_probability_max": [31],
        "precipitation_sum": [0.8],
        "wind_speed_10m_max": [16.1],
    },
}


def open_meteo_falso(geocodificacao=RESPOSTA_GEOCODIFICACAO, previsao_status=200):
    def responder(request: httpx.Request) -> httpx.Response:
        if str(request.url).startswith(URL_GEOCODIFICACAO):
            return httpx.Response(200, json=geocodificacao)
        return httpx.Response(previsao_status, json=RESPOSTA_PREVISAO)

    return httpx.MockTransport(responder)


@pytest.fixture
def cliente_api():
    def criar(transporte=None):
        app.state.open_meteo = ClienteOpenMeteo(
            httpx.AsyncClient(transport=transporte or open_meteo_falso())
        )
        # Sem lifespan: o cliente falso acima substitui o da Open-Meteo real
        return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://teste")

    return criar


async def test_previsao_por_cidade(cliente_api):
    async with cliente_api() as api:
        r = await api.get("/v1/clima/hoje", params={"cidade": "Recife"})
    assert r.status_code == 200
    corpo = r.json()
    assert corpo["local"]["nome"] == "Recife"
    assert corpo["local"]["estado"] == "Pernambuco"
    assert corpo["condicao"] == "Garoa leve"
    assert corpo["temperatura_c"] == {"atual": 28.0, "minima": 25.2, "maxima": 29.5}


async def test_previsao_por_coordenadas(cliente_api):
    async with cliente_api() as api:
        r = await api.get("/v1/clima/hoje", params={"lat": -8.05, "lon": -34.9})
    assert r.status_code == 200
    assert r.json()["local"]["nome"] is None
    assert r.json()["data"] == "2026-10-20"


@pytest.mark.parametrize(
    "params",
    [
        {},
        {"lat": -8.05},
        {"cidade": "Recife", "lat": -8.05, "lon": -34.9},
    ],
)
async def test_parametros_invalidos(cliente_api, params):
    async with cliente_api() as api:
        r = await api.get("/v1/clima/hoje", params=params)
    assert r.status_code == 400


async def test_coordenada_fora_do_intervalo(cliente_api):
    async with cliente_api() as api:
        r = await api.get("/v1/clima/hoje", params={"lat": 91, "lon": 0})
    assert r.status_code == 422


async def test_cidade_inexistente(cliente_api):
    async with cliente_api(open_meteo_falso(geocodificacao={})) as api:
        r = await api.get("/v1/clima/hoje", params={"cidade": "Cidadequenaoexiste"})
    assert r.status_code == 404


async def test_open_meteo_fora_do_ar(cliente_api):
    async with cliente_api(open_meteo_falso(previsao_status=503)) as api:
        r = await api.get("/v1/clima/hoje", params={"lat": -8.05, "lon": -34.9})
    assert r.status_code == 502
    async with cliente_api() as api:
        metricas = (await api.get("/metrics")).text
    assert 'clima_open_meteo_falhas_total{endpoint="previsao"}' in metricas
