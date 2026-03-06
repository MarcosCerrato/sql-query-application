# Stage 1: build
FROM node:20-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
# VITE_API_URL must point to where the browser can reach model-service
# (host port 8001, exposed by docker-compose)
ARG VITE_API_URL=http://localhost:8001
ARG VITE_DB_SERVICE_URL=http://localhost:8000
ARG VITE_ANSWER_SERVICE_URL=http://localhost:8002
ENV VITE_API_URL=$VITE_API_URL
ENV VITE_DB_SERVICE_URL=$VITE_DB_SERVICE_URL
ENV VITE_ANSWER_SERVICE_URL=$VITE_ANSWER_SERVICE_URL
RUN npm run build

# Stage 2: serve with nginx
FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
# SPA fallback: all routes → index.html
RUN printf 'server {\n  listen 5173;\n  root /usr/share/nginx/html;\n  index index.html;\n  location / {\n    try_files $uri $uri/ /index.html;\n  }\n}\n' \
    > /etc/nginx/conf.d/default.conf
EXPOSE 5173
