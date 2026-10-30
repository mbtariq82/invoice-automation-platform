FROM node:24.11.0-bookworm-slim@sha256:76d0ed0ed93bed4f4376211e9d8fddac4d8b3fbdb54cc45955696001a3c91152 AS build
WORKDIR /app
COPY package.json bun.lock ./
RUN bun install --frozen-lockfile
COPY index.html styles.css tsconfig*.json vite.config.ts ./
COPY public ./public
COPY src ./src
RUN bun run build

FROM node:24.11.0-bookworm-slim@sha256:76d0ed0ed93bed4f4376211e9d8fddac4d8b3fbdb54cc45955696001a3c91152
ENV NODE_ENV=production PORT=8080
WORKDIR /app
COPY package.json bun.lock server.mjs ./
RUN bun install --production --frozen-lockfile
COPY --from=build /app/dist ./dist
USER node
EXPOSE 8080
CMD ["node", "server.mjs"]
