# Build context: should be apps/web/ (not monorepo root)
# Build with: docker build -t wingman-web apps/web/

FROM node:24-alpine AS base
ENV NEXT_TELEMETRY_DISABLED=1

# ── Dependency install stage ───────────────────────────────────────────────────
FROM base AS deps
WORKDIR /app
COPY package.json ./
RUN npm install

# ── Build stage ────────────────────────────────────────────────────────────────
FROM base AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules

# Copy only the web app files (not the monorepo root)
COPY app ./app
COPY components ./components
COPY hooks ./hooks
COPY lib ./lib
COPY public ./public
COPY stores ./stores
COPY types ./types
COPY package.json next.config.ts postcss.config.mjs tsconfig.json components.json ./

# Env vars needed at build time (API URLs baked in as public runtime config)
ARG NEXT_PUBLIC_DAY1_API_URL=/api/day1
ARG NEXT_PUBLIC_DAY2_API_URL=/api/day2
ARG NEXT_PUBLIC_AUTH_API_URL=/api/auth

# Build using next directly (not turbo)
RUN npx next build

# ── Runtime stage ──────────────────────────────────────────────────────────────
FROM base AS runner
WORKDIR /app
ENV NODE_ENV=production

RUN addgroup --system --gid 1001 nodejs && \
    adduser --system --uid 1001 nextjs

# Standalone output from next build (includes only what's needed to run)
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static
COPY --from=builder --chown=nextjs:nodejs /app/public ./public

USER nextjs
EXPOSE 3000
ENV PORT=3000 HOSTNAME=0.0.0.0

CMD ["node", "server.js"]
