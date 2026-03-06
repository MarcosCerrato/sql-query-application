# db-service

Servicio de ejecución segura de SQL sobre PostgreSQL. Expone endpoints para ejecutar consultas y exportar el schema de la base de datos.

---

## Responsabilidad

- Ejecutar consultas SQL enviadas por el `model-service` y devolver los resultados como JSON.
- Exportar el schema de la tabla `sales` (columnas, tipos, valores de ejemplo) para que el `model-service` pueda construir prompts contextualizados.
- Garantizar que solo se ejecuten consultas de lectura (`SELECT`).

Este servicio **no genera SQL** ni interactúa con el LLM. Su única responsabilidad es ser una interfaz segura y predecible sobre la base de datos.

---

## Endpoints

### `POST /query`

Ejecuta una consulta SQL y devuelve los resultados.

**Request:**
```json
{ "sql": "SELECT product_name, SUM(quantity) FROM sales GROUP BY product_name LIMIT 5" }
```

**Response:**
```json
{
  "rows": [
    { "product_name": "Alfajor Super DDL x un", "sum": 342 }
  ],
  "count": 1
}
```

**Errores:**
- `400` si la query no es SELECT o falla en PostgreSQL (incluye el mensaje de error de pg en el detalle).

---

### `GET /schema`

Devuelve el schema de la tabla `sales` con valores de ejemplo para cada columna.

**Response:**
```json
{
  "table": "sales",
  "columns": [
    {
      "name": "product_name",
      "type": "VARCHAR",
      "sample_values": ["Alfajor Super DDL x un", "Medialunas x 6", "Café con leche"]
    }
  ]
}
```

Incluye sample values reales para que el LLM conozca los valores posibles y genere SQL más preciso (por ejemplo, saber el formato exacto de `week_day` o `hour`).

---

### `GET /health`

```json
{ "status": "ok" }
```

Verifica la conexión a PostgreSQL. Usado por Docker Compose para los healthchecks de dependencia.

---

## Schema de la tabla `sales`

| Columna | Tipo | Descripción |
|---------|------|-------------|
| `id` | INTEGER | PK auto-increment |
| `date` | DATE | Fecha de la venta |
| `week_day` | VARCHAR | Día de la semana (ej: Monday) |
| `hour` | VARCHAR | Hora en formato HH:MM |
| `ticket_number` | VARCHAR | ID del ticket de caja |
| `waiter` | INTEGER | ID numérico del mozo |
| `product_name` | VARCHAR | Nombre del producto |
| `quantity` | INTEGER | Unidades vendidas en la línea |
| `unitary_price` | NUMERIC(10,2) | Precio por unidad |
| `total` | NUMERIC(10,2) | Total de la línea (quantity × unitary_price) |

---

## Decisiones de implementación

### Solo SELECT (whitelist por regex)

Antes de ejecutar cualquier query, se valida que comience con `SELECT` (ignorando espacios y case). Cualquier otra instrucción (`DROP`, `INSERT`, `UPDATE`, `DELETE`, CTEs destructivas) devuelve `400` sin llegar a la base de datos.

Esta validación protege de modificaciones accidentales o inyecciones SQL maliciosas provenientes del LLM, que podría generar queries no deseadas.

```python
# db-service/main.py
if not sql.strip().upper().startswith("SELECT"):
    raise HTTPException(status_code=400, detail="Only SELECT queries are allowed")
```

### LIMIT automático

Si el SQL no contiene la palabra `LIMIT`, el servicio la inyecta automáticamente con el valor de `QUERY_LIMIT` (default: 1000). Esto protege contra queries que retornen toda la tabla y saturen la memoria del servicio o el ancho de banda entre servicios.

```python
if "LIMIT" not in sql.upper():
    sql = sql.rstrip(";") + f" LIMIT {settings.query_limit}"
```

### Alembic para migraciones

El schema se versiona con Alembic en lugar de crear la tabla directamente en `init_db.py`. Esto garantiza reproducibilidad y permite evolucionar el schema sin recrear la base de datos.

**Migración `0001_create_sales_table.py`**: crea la tabla `sales` con todas las columnas inicialmente como VARCHAR.

**Migración `0002_alter_date_column.py`**: convierte la columna `date` de VARCHAR a DATE usando `TO_DATE(date, 'YYYY-MM-DD')`. La conversión se hace en PostgreSQL directamente para preservar los datos existentes:

```sql
ALTER TABLE sales ALTER COLUMN date TYPE DATE
USING TO_DATE(date, 'YYYY-MM-DD');
```

Esta migración fue necesaria porque el CSV original almacena fechas como strings, pero para queries de rango de fechas y funciones de fecha (`EXTRACT`, `DATE_TRUNC`) PostgreSQL necesita el tipo nativo DATE.

### Carga inicial desde CSV (`init_db.py`)

Al arrancar el contenedor por primera vez, `init_db.py` detecta si la tabla `sales` está vacía y carga `data.csv` automáticamente usando `COPY` de PostgreSQL (vía `pandas + to_sql`). Es idempotente: no recarga si ya hay datos.

### SQLAlchemy ORM vs SQL raw

El modelo SQLAlchemy (`models.py`) define la estructura de la tabla y se usa por Alembic para las migraciones. Sin embargo, el endpoint `/query` ejecuta SQL raw recibido del model-service, ya que el objetivo es ejecutar queries arbitrarias generadas por el LLM, no hacer consultas predefinidas mediante el ORM.

---

## Configuración

Variables de entorno (con defaults):

| Variable | Default | Descripción |
|----------|---------|-------------|
| `DATABASE_URL` | `postgresql://app:app@postgres/sales` | URL de conexión a PostgreSQL |
| `QUERY_LIMIT` | `1000` | Límite máximo de filas por query |

---

## Tests

```bash
cd db-service
poetry install
poetry run pytest
```

### Cobertura

| Test | Descripción |
|------|-------------|
| `test_query_valid` | SELECT válido devuelve filas y count |
| `test_query_non_select` | DROP/INSERT devuelve 400 |
| `test_query_limit_injection` | Query sin LIMIT recibe LIMIT automático |
| `test_schema` | GET /schema devuelve columnas con sample values |
| `test_health` | GET /health devuelve ok |
| `test_db_failure` | Error de conexión devuelve 500 |

Los tests usan SQLite en memoria para aislar la base de datos real.

---

## Estructura de archivos

```
db-service/
├── main.py           # FastAPI app: endpoints /query, /schema, /health
├── models.py         # SQLAlchemy model de la tabla sales
├── config.py         # Settings con pydantic-settings (DATABASE_URL, QUERY_LIMIT)
├── init_db.py        # Carga data.csv en PostgreSQL al iniciar
├── Dockerfile        # Python 3.11 slim + Poetry
├── pyproject.toml    # Dependencias: FastAPI, SQLAlchemy, Alembic, psycopg2
├── alembic.ini       # Configuración de Alembic
├── alembic/
│   ├── env.py        # Alembic env: usa DATABASE_URL del entorno
│   └── versions/
│       ├── 0001_create_sales_table.py   # Crea tabla sales
│       └── 0002_alter_date_column.py    # VARCHAR → DATE
└── tests/
    ├── conftest.py           # Fixtures: app client, DB en memoria
    ├── test_endpoints.py     # Tests de integración de endpoints
    └── test_pure_logic.py    # Tests de lógica pura (validación SQL, LIMIT)
```
