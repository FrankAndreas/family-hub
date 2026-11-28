# Built from the repository root (docker build -f frontend/Dockerfile .): the page uses the theme package in theme/
# Stage 1: build the app
FROM node:26-slim AS build

WORKDIR /app/frontend

COPY theme/ /app/theme/
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./

# Call the API on the same origin; nginx forwards /api to the backend
ENV VITE_API_URL=/
RUN npm run build

# Stage 2: serve it with nginx as a non-root user, on port 8080
FROM nginxinc/nginx-unprivileged:1.31.7-alpine

COPY --from=build --chown=nginx:nginx /app/frontend/dist /usr/share/nginx/html
COPY --chown=nginx:nginx frontend/nginx.conf /etc/nginx/conf.d/default.conf
COPY --chown=nginx:nginx frontend/security-headers.conf /etc/nginx/security-headers.conf

EXPOSE 8080

CMD ["nginx", "-g", "daemon off;"]
