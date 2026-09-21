# Infraestructura operativa

Esta carpeta contiene las definiciones reproducibles para los dos proyectos del
monorepo. El [README principal](../README.md) explica el producto y el flujo
de contribución; este documento es el runbook técnico de Docker, backups y
despliegues. Los archivos `.env` reales permanecen en el host de ejecución.

## Twenty local

Usa esta opción cuando quieras trabajar en el CRM sin tocar la instancia de
producción. El Compose crea un proyecto Docker separado (`twenty-local`) y usa
los puertos 3001, 55432 y 56379 por defecto.

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
`/healthz`. El flujo está protegido por aprobación del entorno `production`.
Para volver atrás:

```bash
/opt/twenty-crm/managed/production/rollback-twenty.sh
```

## BookStack

BookStack tiene un Compose y un workflow manual independientes. Su `.env` debe
contener una imagen BookStack fijada a versión o digest, la clave de aplicación
y las credenciales de MariaDB. El workflow hace backup antes de recrear los dos
servicios. Para el flujo explicado para colaboradores, consulta
[`docs/README.md`](../docs/README.md).

## Secretos del entorno de GitHub

El entorno `production` debe definir `PRODUCTION_SSH_KEY`,
`PRODUCTION_KNOWN_HOSTS`, `PRODUCTION_HOST`, `PRODUCTION_USER`,
`PRODUCTION_REGISTRY_USERNAME` y `PRODUCTION_REGISTRY_TOKEN`. El token del
registro necesita permiso de lectura sobre el paquete publicado; el servidor
nunca recibe el token general del repositorio.

## Secretos y datos

No ejecutar `git add .` desde un script de despliegue. Revisar siempre `git
status` y `git diff --cached`. Los CSV/SQL de leads, sesiones de navegador y
archivos `.env` se mantienen fuera del índice de Git.
