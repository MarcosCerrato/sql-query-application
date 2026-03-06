# answer-service

Servicio de generación de respuestas en lenguaje natural. Recibe una pregunta, el SQL generado y los resultados de la base de datos, y produce una respuesta conversacional en español.

---

## Responsabilidad

- Convertir filas de resultados SQL a una respuesta comprensible para un usuario no técnico.
- Validar que la respuesta del LLM no contenga alucinaciones ni output incoherente.
- Proveer un fallback determinístico cuando el LLM falla o genera respuestas inválidas.

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

Si `rows` es una lista vacía, devuelve: *"No se encontraron resultados para tu consulta."*

---

### `GET /health`

```json
{ "status": "ok" }
```

---

## Decisiones de implementación

### Modelo más liviano (llama3.2:1b)

La tarea de generar una respuesta conversacional es más simple que generar SQL correcto. No requiere razonamiento sobre schemas ni sintaxis. Por eso se usa `llama3.2:1b` (≈1.3 GB) en lugar del `qwen2.5-coder:7b` (≈4.7 GB) usado para SQL.

Ventajas:
- Latencia menor (~1–2s vs ~5–8s)
- Menor consumo de memoria
- Suficiente calidad para parafrasear datos estructurados

### Detección de alucinaciones numéricas

El LLM puede inventar números que no están en los datos. Por ejemplo, si el total real es 342, el modelo podría responder "se vendieron 1,342 unidades". Para detectarlo:

1. Se extraen todos los números de 4+ dígitos de la respuesta generada.
2. Se verifica que cada número extraído esté presente en los datos reales (serialización JSON de `rows`).
3. Si algún número no está en los datos → la respuesta se descarta.

```python
numbers = re.findall(r"\b\d{4,}\b", cleaned_text)
for n in numbers:
    if n not in data_str:
        return True  # Alucinación detectada
```

Se usan números de 4+ dígitos para evitar falsos positivos con números pequeños (años, horas, cantidades chicas que pueden coincidir por azar).

### Detección de output garbled

Para resultados con múltiples filas, el modelo puede omitir entradas o mezclar valores. Se verifica que al menos el 50% de los valores de la primera columna de cada fila aparezca en la respuesta:

```python
key_values = [str(row[first_col]) for row in rows]
covered = sum(1 for v in key_values if v in answer)
if covered / len(key_values) < 0.5:
    return True  # Output garbled
```

### Fallback determinístico

Si el LLM falla (timeout, error de conexión, alucinación, garbled), en lugar de devolver error al usuario, el servicio genera una respuesta automática:

- **1 fila**: lista los pares `columna: valor` de la fila.
- **N filas**: enumera los valores de la primera columna con sus totales si hay columna numérica.

```
• Alfajor Super DDL x un: 342
• Medialunas x 6: 289
• Café con leche: 201
```

Esto garantiza que el usuario siempre recibe información útil aunque el LLM falle.

### Prompt con hints de dominio

El prompt incluye notas sobre el dominio para reducir errores del LLM:
- `waiter` es un ID numérico, no un nombre de persona.
- `week_day` está en inglés (Monday, Tuesday...).
- Responder en el mismo idioma de la pregunta (español).
- No mencionar el SQL ni jerga técnica.
- Solo las primeras 20 filas se incluyen en el prompt para limitar tokens.

---

## Configuración

| Variable | Default | Descripción |
|----------|---------|-------------|
| `OLLAMA_ANSWER_MODEL` | `llama3.2:1b` | Modelo para generación de respuestas |
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
| `test_hallucination_detected` | Descarta respuesta con número inventado |
| `test_hallucination_not_detected` | Acepta respuesta con números correctos |
| `test_garbled_detected` | Descarta respuesta que omite valores clave |
| `test_fallback_single_row` | Fallback correcto para 1 fila |
| `test_fallback_multi_row` | Fallback correcto para N filas |
| `test_answer_endpoint` | POST /answer retorna respuesta (mock Ollama) |

---

## Estructura de archivos

```
answer-service/
├── main.py         # FastAPI app completa (143 líneas): endpoint /answer, validaciones, fallback
├── Dockerfile      # Python 3.11 slim + Poetry
└── pyproject.toml  # Dependencias: FastAPI, httpx, pydantic, pydantic-settings
```

El servicio es intencionalmente compacto. Toda la lógica vive en `main.py` para facilitar lectura y modificación.
