# clima-api

API que retorna a previsão do tempo **de hoje** para uma cidade (pelo nome) ou para um par de coordenadas. Os dados vêm da [Open-Meteo](https://open-meteo.com), que é gratuita e não exige chave.

## Endpoints

| Método | Rota | Descrição |
|---|---|---|
| GET | `/v1/clima/hoje?cidade=Recife` | Previsão de hoje pelo nome da cidade |
| GET | `/v1/clima/hoje?lat=-8.05&lon=-34.9` | Previsão de hoje por coordenadas |
| GET | `/docs` | Documentação interativa (Swagger) |
| GET | `/metrics` | Métricas no formato Prometheus |
| GET | `/healthz`, `/readyz` | Probes do Kubernetes |

Códigos de resposta: `400` se faltar parâmetro ou vierem os dois modos juntos, `404` se a cidade não for encontrada, `422` se a coordenada estiver fora do intervalo e `502` se a Open-Meteo estiver indisponível.

Exemplo:

```bash
curl "localhost:30080/v1/clima/hoje?cidade=Recife"
```

```json
{
  "local": {"nome": "Recife", "estado": "Pernambuco", "pais": "Brasil", "latitude": -8.05389, "longitude": -34.88111, "fuso_horario": "America/Recife"},
  "data": "2026-10-20",
  "condicao": "Garoa leve",
  "codigo_wmo": 51,
  "temperatura_c": {"atual": 28.0, "minima": 25.2, "maxima": 29.5},
  "precipitacao": {"probabilidade_max_pct": 31, "total_mm": 0.8},
  "vento_max_kmh": 16.1,
  "fonte": "Open-Meteo"
}
```

O "hoje" é calculado no fuso horário do local consultado, não no do servidor.

## Desenvolvimento local

```bash
uv sync
uv run pytest
uv run uvicorn app.main:app --reload
```

Com Docker:

```bash
docker build -t clima-api:local .
docker run --rm -p 8000:8000 clima-api:local
```

## Pipeline

O workflow `.github/workflows/ci-cd.yaml` tem três jobs:

1. **testes**: roda o pytest em todo push e pull request.
2. **imagem**: em push na `main` ou em tag `vX.Y.Z`, gera a imagem arm64 e publica em `ghcr.io/marceloluizfranca/clima-api` com as tags `sha-<commit>`, `latest` e a versão semver.
3. **deploy**: roda no runner self-hosted `arc-splic`, que fica **dentro** do cluster kind. Aplica `k8s/` com a imagem do commit e espera o rollout terminar.

O runner usa a ServiceAccount do próprio pod, com permissão apenas no namespace `clima`. Não há kubeconfig guardado em secret.

## Integração com a plataforma

O cluster, os runners e a stack de monitoramento são mantidos no repositório [devops](https://github.com/marceloluizfranca/devops). Esta aplicação foi integrada seguindo o guia [Adicionar um repositório](https://github.com/marceloluizfranca/devops/blob/main/github-runners/README.md#adicionar-um-repositório), com:

| Variável | Valor |
|---|---|
| `REPO` | `clima-api` |
| `DONO` | `marceloluizfranca` |
| `NAMESPACE` | `clima` |
| `SCALE_SET` | `arc-splic` |

## Observabilidade

O monitoramento é declarado junto com a aplicação e aplicado pelo mesmo deploy:

| Arquivo | O que faz |
|---|---|
| `k8s/servicemonitor.yaml` | Prometheus coleta `/metrics` a cada 15s |
| `k8s/observabilidade/alertas.yaml` | Regras de alerta (`PrometheusRule`) |
| `k8s/observabilidade/dashboard.json` | Dashboard "Clima API" no Grafana, pasta *Aplicações* |

Métricas expostas:

| Métrica | Tipo | Labels |
|---|---|---|
| `clima_http_requisicoes_total` | counter | `metodo`, `rota`, `status` |
| `clima_http_duracao_segundos` | histogram | `metodo`, `rota` |
| `clima_open_meteo_falhas_total` | counter | `endpoint` |

Alertas:

| Alerta | Condição |
|---|---|
| `ClimaApiTaxaDeErroAlta` | Mais de 5% de respostas 5xx por 5 min |
| `ClimaApiOpenMeteoFalhando` | Mais de 5 falhas na Open-Meteo em 5 min |
| `ClimaApiLatenciaAlta` | p95 acima de 2s por 10 min |
| `ClimaApiSemReplicas` | Nenhuma réplica disponível por 2 min |

## Versionamento

Commits seguem o [Conventional Commits](https://www.conventionalcommits.org/pt-br/) e as versões seguem o [SemVer](https://semver.org/lang/pt-BR/): `feat` sobe a versão menor, `fix` sobe a correção e mudanças incompatíveis sobem a maior.
