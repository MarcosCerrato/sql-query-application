# frontend-react

Interfaz de chat para consultar la base de datos en lenguaje natural. El usuario escribe una pregunta en español y recibe una respuesta conversacional, el SQL generado y los resultados en tabla.

---

## Arquitectura del componente

```
App.jsx
├── Sidebar
│   ├── Título de la app
│   └── Botones de ejemplos (prefill del input)
└── Chat area
    ├── ChatWindow.jsx     — Lista de mensajes (scroll automático)
    │   └── MessageBubble.jsx  — Renderiza un mensaje (user/assistant/loading/error)
    │       ├── SQLBlock.jsx       — Muestra el SQL generado con formato
    │       └── ResultsTable.jsx   — Tabla dinámica de resultados
    └── ChatInput.jsx      — Textarea auto-expandible + botón enviar
```

---

## Componentes

### `App.jsx`
Layout principal. Mantiene el estado de la conversación (`messages`), maneja el submit del input y llama a `POST /ask` del model-service. Inyecta los ejemplos predefinidos para onboarding.

### `ChatWindow.jsx`
Lista scrollable de mensajes. Hace scroll automático al último mensaje cuando se agrega uno nuevo. Itera sobre `messages` y renderiza un `MessageBubble` por cada uno.

### `ChatInput.jsx`
Textarea que se auto-expande verticalmente al tipear (hasta un máximo). Soporta envío con `Enter` (sin Shift). Se deshabilita mientras hay una respuesta en proceso.

### `MessageBubble.jsx`
Renderiza un mensaje según su tipo:

| Tipo | Contenido |
|------|-----------|
| `user` | Burbuja alineada a la derecha con la pregunta |
| `assistant` | Respuesta conversacional + `SQLBlock` + `ResultsTable` |
| `loading` | Spinner animado ("Consultando...") |
| `error` | Mensaje de error con estilo diferenciado |

### `SQLBlock.jsx`
Muestra el SQL generado en un bloque de código con fuente monoespaciada. Permite al usuario revisar qué consulta se ejecutó.

### `ResultsTable.jsx`
Tabla dinámica que extrae los headers de las keys del primer objeto en `rows`. Muestra las filas con scroll horizontal si hay muchas columnas.

---

## Decisiones de implementación

### React 19 + Vite 7
Vite ofrece HMR instantáneo y builds optimizados. React 19 incluye mejoras de performance y es el estándar actual. Esta combinación es la más rápida para desarrollo frontend en 2025.

### Tailwind CSS 4
Estilos puramente utilitarios sin archivos CSS custom. Tailwind 4 se integra como plugin de Vite, eliminando el paso de build separado. El resultado es un bundle CSS mínimo (solo las clases usadas).

### Una sola llamada al backend (`POST /ask`)
El frontend no orquesta nada: hace una sola llamada y recibe `{answer, sql, rows}` ya procesado. Esto simplifica el manejo de estado y los posibles estados de error. Toda la lógica vive en el model-service.

### Estado de mensajes como array tipado
Los mensajes se almacenan como objetos con `type`, `content`, y campos opcionales (`sql`, `rows`). Esto permite a `MessageBubble` decidir cómo renderizar sin lógica condicional dispersa.

```js
{
  type: "assistant",       // "user" | "assistant" | "loading" | "error"
  content: "El producto más vendido...",
  sql: "SELECT ...",
  rows: [{ product_name: "...", total: 342 }]
}
```

### Botones de ejemplo (onboarding)
La sidebar incluye preguntas de ejemplo que pre-rellenan el input con un click. Reduce la fricción inicial para usuarios que no saben qué preguntar.

### Dockerfile 2-stage
```dockerfile
# Stage 1: Build con Node + Vite
FROM node:20-alpine AS builder
RUN npm ci && npm run build

# Stage 2: Servir con nginx
FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
```

El artefacto final es solo nginx con los archivos estáticos compilados. Sin Node.js en producción, imagen resultante más liviana y segura.

---

## Desarrollo local

```bash
cd frontend-react

# Instalar dependencias
npm install

# Levantar en modo dev (HMR)
npm run dev
# → http://localhost:5173

# Build de producción
npm run build

# Tests
npm test
```

El dev server está configurado en `vite.config.js` para hacer proxy de `/ask`, `/schema` y `/health` al model-service en `localhost:8001` (útil cuando se corre el backend con Docker y el frontend localmente).

---

## Tests

```bash
npm test
```

Usa Vitest + React Testing Library. Los tests usan `jsdom` como entorno DOM.

| Test | Descripción |
|------|-------------|
| `ChatInput.test.jsx` | Auto-expand, submit con Enter, deshabilitar durante loading |
| `MessageBubble.test.jsx` | Renderiza tipo user, assistant, loading y error correctamente |
| `SQLBlock.test.jsx` | Muestra el SQL en bloque de código |

---

## Estructura de archivos

```
frontend-react/
├── src/
│   ├── App.jsx                   # Layout + estado de conversación + fetch a /ask
│   ├── main.jsx                  # Entry point de React
│   ├── index.css                 # Estilos globales (mínimos, Tailwind)
│   └── components/
│       ├── ChatWindow.jsx        # Lista de mensajes con scroll automático
│       ├── ChatInput.jsx         # Textarea auto-expandible
│       ├── MessageBubble.jsx     # Renderiza un mensaje según su tipo
│       ├── ResultsTable.jsx      # Tabla dinámica de resultados
│       └── SQLBlock.jsx          # Display del SQL generado
├── tests/
│   ├── setup.js                  # Configuración de vitest + testing-library
│   ├── ChatInput.test.jsx
│   ├── MessageBubble.test.jsx
│   └── SQLBlock.test.jsx
├── vite.config.js                # Vite + Tailwind CSS plugin + proxy config
├── package.json                  # React 19, Vite 7, Tailwind 4, Vitest
└── Dockerfile                    # 2-stage: build Vite → nginx
```
