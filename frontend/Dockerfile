# Production Dockerfile for SourceLens UI
FROM node:22-alpine AS builder

# Set working directory
WORKDIR /app

# Build arguments for configuration
ARG VITE_API_BASE_URL
ARG VITE_TURNSTILE_SITE_KEY
ARG VITE_SENTRY_DSN
ARG VITE_SENTRY_ENVIRONMENT
ARG VITE_SENTRY_TRACES_SAMPLE_RATE
ARG VITE_SENTRY_SEND_DEFAULT_PII
ARG VITE_GA_ID

# Set as environment variables for build
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}
ENV VITE_TURNSTILE_SITE_KEY=${VITE_TURNSTILE_SITE_KEY}
ENV VITE_SENTRY_DSN=${VITE_SENTRY_DSN}
ENV VITE_SENTRY_ENVIRONMENT=${VITE_SENTRY_ENVIRONMENT}
ENV VITE_SENTRY_TRACES_SAMPLE_RATE=${VITE_SENTRY_TRACES_SAMPLE_RATE}
ENV VITE_SENTRY_SEND_DEFAULT_PII=${VITE_SENTRY_SEND_DEFAULT_PII}
ENV VITE_GA_ID=${VITE_GA_ID}

# Copy package files
COPY package*.json ./

# Install dependencies
RUN npm ci --only=production=false

# Copy source code
COPY . .

# Build the application
RUN npm run build

# Production stage
FROM nginx:alpine

# Stamp the release version onto the runtime image so scripts/install.sh can
# read it (docker inspect Config.Labels) for its version-skip check. Absent =>
# 0.0.0, which install.sh treats as "never skip".
ARG APP_VERSION=0.0.0
LABEL com.oneprocloud.sourcelens.version=$APP_VERSION

# Copy built files from builder
COPY --from=builder /app/dist /usr/share/nginx/html

# Copy custom nginx configuration for SPA routing
COPY docker/nginx.conf /etc/nginx/conf.d/default.conf

# Expose port
EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
