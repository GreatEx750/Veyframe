FROM node:22-alpine AS dependencies

WORKDIR /app

COPY package.json package-lock.json ./
COPY apps/web/package.json apps/web/package.json
COPY packages/contracts/package.json packages/contracts/package.json
RUN npm ci

FROM dependencies AS builder

COPY apps/web apps/web
COPY packages/contracts packages/contracts
COPY artifacts/verification/golden-export-20s.mp4 apps/web/public/judge-demo.mp4
RUN npm run build --workspace @demodirector/web

FROM node:22-alpine AS runner

ENV NODE_ENV=production
ENV PORT=8080

WORKDIR /app

COPY package.json package-lock.json ./
COPY apps/web/package.json apps/web/package.json
COPY packages/contracts/package.json packages/contracts/package.json
RUN npm ci --omit=dev

COPY apps/web apps/web
COPY packages/contracts packages/contracts
COPY artifacts/verification/golden-export-20s.mp4 apps/web/public/judge-demo.mp4
COPY --from=builder /app/apps/web/.next apps/web/.next

EXPOSE 8080

CMD ["npm", "run", "start", "--workspace", "@demodirector/web", "--", "--hostname", "0.0.0.0", "--port", "8080"]
