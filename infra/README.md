# Infraestructura operativa

Esta carpeta contiene únicamente definiciones reproducibles y plantillas
sanitizadas. Los archivos `.env` reales permanecen en el host de ejecución.

## Twenty local

```bash
cp infra/production/twenty.env.example infra/production/.env.local
# Editar valores locales, nunca usar secretos de producción.
docker compose \
  --env-file infra/production/.env.local \
  -f infra/production/twenty.compose.yml \
  -f infra/production/twenty.compose.local.yml \
  up -d --build
```

El Compose local usa el proyecto `twenty-local` y los puertos 3001, 55432 y
56379 por defecto para no interferir con una instancia Twenty ya existente.

Para parar el entorno sin borrar datos locales:

```bash
docker compose \
  --env-file infra/production/.env.local \
  -f infra/production/twenty.compose.yml \
  -f infra/production/twenty.compose.local.yml \
  down
```

## Producción

El workflow publica una imagen `ghcr.io/arsoluciondigital/crm:<git-sha>` y
ejecuta `infra/production/deploy-twenty.sh` en el servidor. El script exige un
SHA de 40 caracteres, crea backup, actualiza solo server/worker y valida
`/healthz`. Para volver atrás:

```bash
/opt/twenty-crm/managed/production/rollback-twenty.sh
```

## BookStack

BookStack tiene un Compose y un workflow manual independientes. Su `.env` debe
contener una imagen BookStack fijada a versión o digest, la clave de aplicación
y las credenciales de MariaDB. El workflow hace backup antes de recrear los dos
servicios.

## Required GitHub environment secrets

The `production` environment must define `PRODUCTION_SSH_KEY`,
`PRODUCTION_KNOWN_HOSTS`, `PRODUCTION_HOST`, `PRODUCTION_USER`,
`PRODUCTION_REGISTRY_USERNAME`, and `PRODUCTION_REGISTRY_TOKEN`. The registry
token needs read access on the published package; the server never receives the
GitHub repository token.

## Secretos y datos

No ejecutar `git add .` desde un script de despliegue. Revisar siempre `git
status` y `git diff --cached`. Los CSV/SQL de leads, sesiones de navegador y
archivos `.env` se mantienen fuera del índice de Git.
