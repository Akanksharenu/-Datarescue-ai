# DataRescue AI dashboard: build the static bundle with Node, serve it with nginx.
FROM node:24-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . .
# Baked in at build time; override with: docker compose build --build-arg VITE_API_URL=...
ARG VITE_API_URL=http://localhost:8000
ENV VITE_API_URL=$VITE_API_URL
RUN npm run build

FROM nginx:1.27-alpine
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
