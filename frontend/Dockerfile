### Build stage
### Build stage
FROM node:22-bullseye-slim AS build
WORKDIR /app

# Copy package files first for caching
COPY package.json package-lock.json* ./

# avoid interactive prompts during apt installs
ENV DEBIAN_FRONTEND=noninteractive

# Install system build deps (optional: python3 may not be needed for pure JS project)
RUN apt-get update \
	&& apt-get -o Acquire::Retries=3 install -y --no-install-recommends \
	   build-essential python3 git ca-certificates \
	|| (apt-get update && apt-get install -y --no-install-recommends --fix-missing \
	   build-essential python3 git ca-certificates) \
	&& rm -rf /var/lib/apt/lists/*

# Install JS dependencies
RUN npm install --silent

# Copy source and build
COPY . .
RUN npm run build

### Production stage (nginx)
FROM nginx:stable-alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
