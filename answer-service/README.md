# answer-service

Servicio de generación de respuestas en lenguaje natural. Recibe una pregunta, el SQL generado y los resultados de la base de datos, y produce una respuesta conversacional en español.

---

## Responsabilidad

- Convertir filas de resultados SQL a una respuesta comprensible para un usuario no técnico.

Este servicio no sabe de SQL ni de bases de datos. Su único input es la pregunta del usuario, el SQL (para dar contexto semántico) y las filas de resultados.

---

## Endpoints

### `POST /answer`

**Request:**
```json
{
  "question": "¿Cuál es el producto más vendido?",
  "sql": "SELECT product_name, SUM(quantity) AS total FROM sales GROUP BY product_name ORDER BY total DESC LIMIT 1",
  "rows": [{ "product_name": "Alfajor Super DDL x un", "total": 342 }]
}
```

**Response:**
```json
{
  "answer": "El producto más vendido es el Alfajor Super DDL con 342 unidades vendidas."
}
```

Si `rows` es una lista vacía, devuelve: *"The query returned no results."*

---

### `GET /health`

```json
{ "status": "ok" }
```

---

## Decisiones de implementación

### Prompt con hints de dominio

El prompt incluye notas sobre el dominio para reducir errores del LLM:
- `waiter` es un ID numérico, no un nombre de persona.
- `week_day` está en inglés (Monday, Tuesday...).
- Responder en el mismo idioma de la pregunta (español).
- No mencionar el SQL ni jerga técnica.
- Solo las primeras 20 filas se incluyen en el prompt para limitar tokens.

### NOT_APPLICABLE

Si la pregunta no es sobre datos de ventas (ej. "¿qué hora es?"), el LLM responde con `NOT_APPLICABLE` y el servicio devuelve un mensaje fijo en lugar de intentar parafrasear datos irrelevantes.

---

## Configuración

| Variable | Default | Descripción |
|----------|---------|-------------|
| `OLLAMA_ANSWER_MODEL` | `qwen2.5-coder:7b` | Modelo para generación de respuestas (override de OLLAMA_MODEL) |
| `OLLAMA_MODEL` | `qwen2.5-coder:7b` | Modelo base si OLLAMA_ANSWER_MODEL no está definido |
| `OLLAMA_BASE_URL` | `http://ollama:11434` | URL del servidor Ollama |

---

## Tests

```bash
cd answer-service
poetry install
poetry run pytest
```

### Cobertura

| Test | Descripción |
|------|-------------|
| `test_empty_rows` | Responde "sin resultados" para rows vacías |
| `test_answer_endpoint` | POST /answer retorna respuesta (mock Ollama) |
| `test_rows_truncated_to_20` | El prompt incluye máximo 20 filas |
| `test_sql_appears_in_prompt` | El SQL aparece en el prompt |
| `test_question_appears_in_prompt` | La pregunta aparece en el prompt |

---

## Estructura de archivos

```
answer-service/
├── main.py         # FastAPI app: endpoint /answer, config
├── service.py      # Lógica pura: build_prompt
├── config.py       # Settings con pydantic-settings
├── schemas.py      # Pydantic models
├── Dockerfile      # Python 3.11 slim + Poetry
└── pyproject.toml  # Dependencias: FastAPI, httpx, pydantic, pydantic-settings
```
