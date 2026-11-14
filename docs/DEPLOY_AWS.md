# Deploying Eco311 on AWS

One region is enough to start. The containers are the same ones `docker-compose.yml` builds.

| Piece | AWS service | Notes |
|---|---|---|
| Web app | S3 + CloudFront | `npm run build` → upload `frontend/dist`. CloudFront behaviour `/api/*` → ALB origin (no caching, forward `Authorization`, `X-User-Id` off in prod). |
| API | ECS Fargate behind an ALB | Image `backend/`. ≥2 tasks, target-tracking autoscaling on CPU. ALB idle timeout ≥ 300 s for SSE. Health check `/healthz`. |
| Agent checkpoints + data | RDS PostgreSQL 16 | `DATABASE_URL=postgresql+psycopg://…`. The LangGraph `PostgresSaver` tables are created on first start. Schema creation takes an advisory lock, so many tasks can start at the same time. |
| Photos | S3 bucket | `STORAGE_BACKEND=s3`, `S3_BUCKET=…`. Browsers upload with presigned PUT, so the bucket needs CORS allowing PUT from the site origin. |
| Background jobs | EventBridge Scheduler → ECS RunTask | Command `python -m app.workers followup`, hourly. Add SQS when ingestion volume grows. |
| Email | SES | `EMAIL_BACKEND=ses`, `EMAIL_FROM` must be a verified identity. SES event destination → SNS → small adapter that POSTs to `/api/webhooks/email`. |
| Auth | Cognito user pool | Set `JWT_SECRET` / `JWT_AUDIENCE`. For RS256 Cognito tokens, swap `auth.py` to JWKS verification. |
| Secrets | Secrets Manager | `OPENAI_API_KEY` / `ANTHROPIC_API_KEY`, `TAVILY_API_KEY`, `GOOGLE_MAPS_API_KEY`, DB password → ECS task `secrets`. |
| Logs / traces | CloudWatch Logs | Each agent step is also stored in `run_events`, so you can audit it later. |

Azure equivalents: Front Door + Storage static site, Container Apps, PostgreSQL Flexible
Server, Blob Storage, Service Bus + Container Apps jobs, Azure Communication Services Email, Entra ID.

## Minimal rollout

```bash
# 1. images
aws ecr create-repository --repository-name eco311-api
docker build -t <acct>.dkr.ecr.<region>.amazonaws.com/eco311-api:v1 backend
docker push <acct>.dkr.ecr.<region>.amazonaws.com/eco311-api:v1

# 2. web
cd frontend && npm ci && npm run build
aws s3 sync dist s3://<web-bucket> --delete
aws cloudfront create-invalidation --distribution-id <id> --paths "/*"
```

API task environment:

```
DATABASE_URL=postgresql+psycopg://eco:<from secret>@<rds-endpoint>:5432/eco311
PUBLIC_BASE_URL=https://<your-domain>
CORS_ORIGINS=["https://<your-domain>"]
STORAGE_BACKEND=s3
S3_BUCKET=<photo-bucket>
AWS_REGION=<region>
EMAIL_BACKEND=ses
EMAIL_FROM=reports@<your-domain>
LLM_MODEL=openai:gpt-4o-mini        # or anthropic:…
EMBEDDING_MODEL=openai:text-embedding-3-small
```

Task role permissions: `s3:PutObject`/`GetObject` on the photo bucket, `ses:SendEmail`.

## Before going public

- Turn off dev auth (set `JWT_SECRET`); restrict `POST /api/kb/contacts` to admins.
- Protect `/api/webhooks/email` (SNS signature check or a shared secret).
- Use a commercial tile provider (`VITE_MAP_STYLE_URL`). The OSM tile servers aren't meant
  for production traffic, and Nominatim allows at most 1 request/s (or use Google Geocoding
  via `GOOGLE_MAPS_API_KEY`).
- When the KB or pin count grows, move to PostGIS (`geography` + GiST) and pgvector. The
  schema already keeps a GeoJSON geometry, a centroid, and an embedding per row.
