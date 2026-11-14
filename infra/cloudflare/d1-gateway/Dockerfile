FROM node:22-slim

RUN apt-get update \
    && apt-get install --no-install-recommends -y ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /worker

COPY package.json package-lock.json ./
RUN npm ci

COPY migrations ./migrations
COPY src ./src
COPY wrangler.jsonc ./wrangler.jsonc
COPY entrypoint.sh ./entrypoint.sh

ENV WRANGLER_SEND_METRICS=false

ENTRYPOINT ["sh", "/worker/entrypoint.sh"]
