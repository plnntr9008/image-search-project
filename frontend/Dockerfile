### Build stage
FROM node:18-alpine AS build
WORKDIR /app

# copy package files first for caching
COPY package.json package-lock.json* ./
COPY public ./public
COPY src ./src
COPY vite.config.js ./

RUN npm ci --silent
RUN npm run build

### Production stage (nginx)
FROM nginx:stable-alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
