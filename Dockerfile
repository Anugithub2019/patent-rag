FROM node:24-alpine

ENV NODE_ENV=production
WORKDIR /app

COPY package.json ./
COPY api ./api
COPY backend/hashtag_config.json ./backend/hashtag_config.json
COPY frontend ./frontend
COPY servers/node_server.mjs ./servers/node_server.mjs

USER node

EXPOSE 8080
CMD ["node", "servers/node_server.mjs"]
