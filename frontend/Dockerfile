### Build stage
FROM node:18-bullseye-slim AS build
WORKDIR /app

# copy package files first for caching
COPY package.json package-lock.json* ./

# install system build deps required by some native modules and bundlers
RUN apt-get update \
	&& apt-get install -y --no-install-recommends build-essential python3 git ca-certificates \
	&& rm -rf /var/lib/apt/lists/*

# install JS dependencies (use npm install when package-lock.json may be absent)
RUN npm install --silent

# copy rest of source and build
COPY . .
RUN npm run build

### Production stage (nginx)
FROM nginx:stable-alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
