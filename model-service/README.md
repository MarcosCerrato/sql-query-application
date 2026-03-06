# model-service

Orquestador central del sistema. Recibe preguntas en lenguaje natural y coordina el pipeline completo: generación de SQL con LLM → ejecución → respuesta conversacional. Es el único servicio con el que habla el frontend.

---

## Responsabilidad

- Convertir preguntas en español a SQL usando Ollama (text-to-SQL).
- Orquestar el pipeline completo: SQL → db-service → answer-service.
- Manejar reintentos automáticos cuando el SQL generado falla en la base de datos.
- Cachear SQL generado para preguntas repetidas.

---

## Endpoints

### `POST /ask`

Pipeline completo. El frontend llama solo este endpoint.

**Request:**
```json
{ "question": "¿Cuál es el producto más vendido?" }
```

**Response:**
```json
{
  "answer": "El producto más vendido es el Alfajor Super DDL con 342 unidades.",
  "sql": "SELECT product_name, SUM(quantity) AS total FROM sales GROUP BY product_name ORDER BY total DESC LIMIT 1",
  "rows": [{ "product_name": "Alfajor Super DDL x un", "total": 342 }]
}
```

---

### `POST /text-to-sql`

Solo generación de SQL, sin ejecutar.

**Request:**
```json
{ "question": "¿Cuánto se vendió el lunes?" }
```

**Response:**
```json
{
  "sql": "SELECT SUM(total) FROM sales WHERE week_day = 'Monday'",
  "cached": false
}
```

---

### `POST /text-to-sql-with-feedback`

Regenera SQL incorporando el error de PostgreSQL como contexto.

**Request:**
```json
{
  "question": "¿Cuánto se vendió el lunes?",
  "pg_error": "column \"weekday\" does not exist"
}
```

**Response:**
```json
{ "sql": "SELECT SUM(total) FROM sales WHERE week_day = 'Monday'", "cached": false }
```

---

### `POST /refresh-schema`

Invalida el cache de schema y SQL. Útil si el schema de la base de datos cambió.

```json
{ "status": "ok" }
```

### `GET /health`

```json
{ "status": "ok" }
```

---

## Flujo interno de `/ask`

```
POST /ask {question}
     │
     ▼
¿Está en cache?  ──YES──▶  usa SQL cacheado
     │ NO
     ▼
Obtiene schema de db-service (columnas + sample values)
     │
     ▼
Selecciona 4 few-shots relevantes de los 16 en few_shots.yaml
     │
     ▼
Construye prompt (system + schema + few-shots + pregunta)
     │
     ▼
Llama a Ollama (qwen2.5-coder:7b) → SQL
     │
     ▼
Guarda SQL en cache (TTL 5 min)
     │
     ▼
POST /query {sql} → db-service
     │
     ├── ERROR 400 (SQL inválido)
     │         │
     │         ▼ (hasta 2 reintentos)
     │   POST /text-to-sql-with-feedback {question, pg_error}
     │         │
     │         └──▶ vuelve a POST /query con nuevo SQL
     │
     ▼ OK
POST /answer {question, sql, rows} → answer-service
     │
     ▼
{answer, sql, rows} → Frontend
```

---

## Decisiones de implementación

### Few-shots en YAML (`few_shots.yaml`)

16 pares pregunta→SQL almacenados en un archivo YAML externo. El servicio carga el archivo al iniciar y selecciona dinámicamente los 4 más relevantes para cada pregunta usando coincidencia de keywords.

**Por qué YAML y no hardcoded:** permite agregar o modificar ejemplos sin tocar código Python. Un analista de datos puede agregar ejemplos sin conocimiento del backend.

**Selección por keywords:** cada pregunta se tokeniza y se busca superposición con las palabras del few-shot. Se toman los 4 con mayor coincidencia. Esto mantiene el prompt corto y relevante.

```yaml
# few_shots.yaml
- question: "¿Cuánto se vendió el lunes?"
  sql: "SELECT SUM(total) FROM sales WHERE week_day = 'Monday'"
```

### Cache SHA256 + TTL 5 min

La clave de cache es `SHA256(pregunta + nombres_de_columnas)`. Incluir las columnas del schema en la clave garantiza que si el schema cambia (via `/refresh-schema`), el cache se invalida automáticamente.

```python
key = hashlib.sha256(f"{question}|{schema_sig}".encode()).hexdigest()
```

El TTL de 5 minutos balancea performance con frescura de datos. El cache vive en memoria del proceso (dict Python), suficiente para el caso de uso de un solo nodo. Para producción multi-nodo, se reemplazaría con Redis.

### Retry con error context

Cuando db-service devuelve `400` con el error de PostgreSQL, el model-service no falla inmediatamente. Reenvía la pregunta original más el mensaje de error al LLM pidiendo que corrija el SQL:

```
El SQL anterior falló con: column "weekday" does not exist
Genera un SQL corregido usando los nombres exactos del schema.
```

Esto permite autocorrección de errores comunes como nombres de columna incorrectos o funciones no soportadas. Máximo 2 reintentos para evitar loops.

### Schema con sample values

Al construir el prompt, se incluyen 3 valores de ejemplo por columna. Esto permite al LLM:
- Conocer el formato exacto de `week_day` → `'Monday'` no `'lunes'`
- Conocer el formato de `hour` → `'11:31'`
- No inventar valores de producto que no existen

### Separación router / service

El código está separado en `router.py` (endpoints FastAPI) y `service.py` (lógica de negocio). Esto facilita los tests: `service.py` se puede testear mockeando Ollama y db-service sin levantar un servidor HTTP.

### Carga de schema al iniciar

Al arrancar, el servicio hace una llamada a `GET /schema` de db-service y la almacena en memoria. Esto evita una llamada a la base de datos en cada request. Se puede refrescar con `POST /refresh-schema`.

---

## Configuración

| Variable | Default | Descripción |
|----------|---------|-------------|
| `OLLAMA_MODEL` | `qwen2.5-coder:7b` | Modelo para generación de SQL |
| `OLLAMA_BASE_URL` | `http://ollama:11434` | URL del servidor Ollama |
| `DB_SERVICE_URL` | `http://db-service:8000` | URL del db-service |
| `ANSWER_SERVICE_URL` | `http://answer-service:8002` | URL del answer-service |
| `CACHE_TTL_SECONDS` | `300` | TTL del cache en segundos |

---

## Tests

```bash
cd model-service
poetry install
poetry run pytest
```

### Cobertura

| Test | Descripción |
|------|-------------|
| `test_text_to_sql` | Genera SQL a partir de una pregunta (mock Ollama) |
| `test_cache_hit` | Segunda llamada con misma pregunta usa cache |
| `test_cache_invalidation` | /refresh-schema invalida el cache |
| `test_retry_on_sql_error` | Si db-service devuelve 400, reintenta con feedback |
| `test_few_shot_selection` | Selecciona los 4 few-shots más relevantes |
| `test_sql_extraction` | Extrae SQL de respuesta con code fences (\`\`\`sql) |
| `test_ask_full_pipeline` | Pipeline completo con mocks de todos los servicios |

---

## Estructura de archivos

```
model-service/
├── main.py           # FastAPI app factory (crea app, registra router)
├── router.py         # Endpoints: /ask, /text-to-sql, /text-to-sql-with-feedback, /refresh-schema
├── service.py        # Lógica core: prompt building, Ollama calls, cache, retry
├── config.py         # Settings con pydantic-settings
├── few_shots.yaml    # 16 ejemplos pregunta→SQL para few-shot prompting
├── Dockerfile        # Python 3.11 slim + Poetry
├── pyproject.toml    # Dependencias: FastAPI, httpx, pyyaml, pydantic-settings
└── tests/
    ├── conftest.py              # Fixtures: app client, mocks de servicios externos
    ├── test_endpoints.py        # Tests de integración de endpoints
    └── test_pure_functions.py   # Tests de lógica pura: cache, few-shots, SQL extraction
```
