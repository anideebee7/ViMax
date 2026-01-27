# ViMax Frontend – API Explorer (Vue + Vite)
FROM node:22-alpine

WORKDIR /app

COPY package.json package-lock.json* /app/
RUN npm install

COPY . /app/

ENV VITE_PORT=5173
ENV VITE_API_URL=http://localhost:8000

EXPOSE 5173

CMD ["npm", "run", "dev"]
