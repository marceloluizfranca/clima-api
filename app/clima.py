"""Cliente da Open-Meteo: geocodificação de cidades e previsão do dia."""

from dataclasses import dataclass

import httpx

from app.metricas import FALHAS_OPEN_METEO

URL_GEOCODIFICACAO = "https://geocoding-api.open-meteo.com/v1/search"
URL_PREVISAO = "https://api.open-meteo.com/v1/forecast"

VARIAVEIS_DIARIAS = [
    "weather_code",
    "temperature_2m_max",
    "temperature_2m_min",
    "precipitation_probability_max",
    "precipitation_sum",
    "wind_speed_10m_max",
]

# Códigos WMO usados pela Open-Meteo: https://open-meteo.com/en/docs#weathervariables
CONDICOES_WMO = {
    0: "Céu limpo",
    1: "Predominantemente limpo",
    2: "Parcialmente nublado",
    3: "Nublado",
    45: "Neblina",
    48: "Neblina com geada",
    51: "Garoa leve",
    53: "Garoa moderada",
    55: "Garoa intensa",
    56: "Garoa congelante leve",
    57: "Garoa congelante intensa",
    61: "Chuva leve",
    63: "Chuva moderada",
    65: "Chuva forte",
    66: "Chuva congelante leve",
    67: "Chuva congelante forte",
    71: "Neve leve",
    73: "Neve moderada",
    75: "Neve forte",
    77: "Grãos de neve",
    80: "Pancadas de chuva leves",
    81: "Pancadas de chuva moderadas",
    82: "Pancadas de chuva violentas",
    85: "Pancadas de neve leves",
    86: "Pancadas de neve fortes",
    95: "Trovoada",
    96: "Trovoada com granizo leve",
    99: "Trovoada com granizo forte",
}


class CidadeNaoEncontrada(Exception):
    pass


class ErroOpenMeteo(Exception):
    pass


@dataclass
class Local:
    latitude: float
    longitude: float
    nome: str | None = None
    estado: str | None = None
    pais: str | None = None


class ClienteOpenMeteo:
    def __init__(self, http: httpx.AsyncClient):
        self.http = http

    async def _get(self, operacao: str, url: str, params: dict) -> dict:
        try:
            resposta = await self.http.get(url, params=params)
            resposta.raise_for_status()
            return resposta.json()
        except (httpx.HTTPError, ValueError) as erro:
            FALHAS_OPEN_METEO.labels(operacao=operacao).inc()
            raise ErroOpenMeteo(f"falha ao consultar {operacao}: {erro}") from erro

    async def geocodificar(self, cidade: str) -> Local:
        dados = await self._get(
            "geocodificacao",
            URL_GEOCODIFICACAO,
            {"name": cidade, "count": 1, "language": "pt", "format": "json"},
        )
        resultados = dados.get("results") or []
        if not resultados:
            raise CidadeNaoEncontrada(cidade)
        r = resultados[0]
        return Local(
            latitude=r["latitude"],
            longitude=r["longitude"],
            nome=r.get("name"),
            estado=r.get("admin1"),
            pais=r.get("country"),
        )

    async def previsao_hoje(self, local: Local) -> dict:
        dados = await self._get(
            "previsao",
            URL_PREVISAO,
            {
                "latitude": local.latitude,
                "longitude": local.longitude,
                "daily": ",".join(VARIAVEIS_DIARIAS),
                "current": "temperature_2m",
                # timezone=auto faz o "hoje" ser o dia no fuso do local consultado
                "timezone": "auto",
                "forecast_days": 1,
            },
        )
        diario = {chave: valores[0] for chave, valores in dados["daily"].items()}
        codigo = diario["weather_code"]
        return {
            "local": {
                "nome": local.nome,
                "estado": local.estado,
                "pais": local.pais,
                "latitude": local.latitude,
                "longitude": local.longitude,
                "fuso_horario": dados.get("timezone"),
            },
            "data": diario["time"],
            "condicao": CONDICOES_WMO.get(codigo, "Desconhecida"),
            "codigo_wmo": codigo,
            "temperatura_c": {
                "atual": dados.get("current", {}).get("temperature_2m"),
                "minima": diario["temperature_2m_min"],
                "maxima": diario["temperature_2m_max"],
            },
            "precipitacao": {
                "probabilidade_max_pct": diario["precipitation_probability_max"],
                "total_mm": diario["precipitation_sum"],
            },
            "vento_max_kmh": diario["wind_speed_10m_max"],
            "fonte": "Open-Meteo",
        }
