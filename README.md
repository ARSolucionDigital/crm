# CRM y documentación operativa

Este repositorio es un monorepo para el CRM de la empresa y su documentación
interna. La idea es que una persona nueva pueda entender el sistema, levantarlo
en local y empezar a contribuir sin conocer previamente Twenty, Docker o el
servidor de producción.

## Qué contiene el repositorio

| Proyecto | Para qué sirve | Dónde se ejecuta |
| --- | --- | --- |
| **CRM** | Twenty adaptado para gestionar compañías, personas, leads y procesos comerciales. | `https://crm.arsoluciondigital.com` o localmente en `http://localhost:3001` |
| **Documentación** | BookStack para guías internas, procedimientos y conocimiento operativo. | `https://doc.arsoluciondigital.com` o localmente en `http://localhost:8080` |

El código de ambos proyectos, sus Compose, scripts de backup/despliegue y
especificaciones viven aquí. Los datos persistentes y los secretos viven en el
servidor; nunca se suben al repositorio.

## Cómo funciona la arquitectura

```text
                        GitHub (main)
                              |
             +----------------+----------------+
             |                                 |
       Imagen CRM en GHCR              Compose de BookStack
             |                                 |
       servidor Hetzner                  servidor Hetzner
             |                                 |
   Twenty + PostgreSQL + Redis       BookStack + MariaDB
```

- **Twenty** tiene frontend y API en la misma imagen, un worker separado,
  PostgreSQL para los datos y Redis para las colas.
- **BookStack** tiene un contenedor web y MariaDB. Sus imágenes se fijan por
  digest para que una actualización sea reproducible.
- Cada despliegue crea un backup antes de cambiar contenedores y valida la
  salud del servicio antes de terminar.

## Empezar con el CRM en local

Requisitos: Node `24.x`, Yarn `4.x`, Docker y Docker Compose.

```bash
git clone git@github.com:ARSolucionDigital/crm.git
cd crm
yarn install
cp infra/production/twenty.env.example infra/production/.env.local
```

Edita `infra/production/.env.local` y cambia al menos `PG_DATABASE_PASSWORD`
y `APP_SECRET` por valores locales. Después inicia el entorno aislado:

```bash
docker compose \
  --env-file infra/production/.env.local \
  -f infra/production/twenty.compose.yml \
  -f infra/production/twenty.compose.local.yml \
  up -d --build
```

Abre `http://localhost:3001`. Los datos locales están en volúmenes Docker y
no interfieren con producción. Para detenerlo sin borrar datos:

```bash
docker compose \
  --env-file infra/production/.env.local \
  -f infra/production/twenty.compose.yml \
  -f infra/production/twenty.compose.local.yml \
  down
```

### Cómo interactuar con el CRM

- Usa la interfaz web para crear y consultar compañías, personas, leads y
  actividades.
- Las integraciones y herramientas internas hablan con la API GraphQL en
  `http://localhost:3001/graphql` (en producción, bajo el dominio del CRM).
- `/healthz` sirve para comprobar que el servidor está listo; no es un endpoint
  de negocio.
- El worker procesa tareas asíncronas a través de Redis. Si una funcionalidad
  depende de colas, comprueba también los logs del servicio `worker`.

### Dónde tocar el CRM

- `packages/twenty-front`: interfaz React.
- `packages/twenty-server`: API GraphQL, workers y lógica de negocio.
- `packages/twenty-shared`: tipos y utilidades compartidas.
- `packages/twenty-ui`: componentes de interfaz reutilizables.
- `docs/BBDD-Leads/`: ficheros de leads para importación local/manual; están
  ignorados por Git porque contienen datos de negocio.
- `scripts/`: importadores y automatizaciones auxiliares. Revísalos antes de
  ejecutarlos contra una base de datos real.

Comandos habituales:

```bash
npx nx lint:diff-with-main twenty-front
npx nx lint:diff-with-main twenty-server
npx nx typecheck twenty-front
npx nx typecheck twenty-server
npx nx test twenty-front
npx nx test twenty-server
```

## Empezar con la documentación en local

BookStack es una aplicación independiente, pero su infraestructura se
versiona en este mismo repositorio:

```bash
cp infra/bookstack/bookstack.env.example infra/bookstack/.env.local
```

Edita `.env.local`: usa `APP_URL=http://localhost:8080`, una `APP_KEY` propia
y contraseñas locales. No reutilices secretos de producción. Inicia BookStack:

```bash
docker compose \
  --env-file infra/bookstack/.env.local \
  -f infra/bookstack/bookstack.compose.yml \
  up -d
```

Abre `http://localhost:8080`. Para detenerlo sin borrar el contenido:

```bash
docker compose \
  --env-file infra/bookstack/.env.local \
  -f infra/bookstack/bookstack.compose.yml \
  down
```

La guía específica de este proyecto está en [`docs/README.md`](docs/README.md).

## Flujo de trabajo y despliegue

1. Parte de `main` y crea una rama pequeña, por ejemplo
   `codex/crm-campos` o `codex/documentacion-importacion`.
2. Trabaja y prueba en local.
3. Abre un Pull Request. El workflow de validación ejecuta seguridad,
   configuración Docker, lint, typecheck y tests.
4. Al integrar en `main`, GitHub construye una imagen inmutable del CRM,
   publica el SHA en GHCR y solicita aprobación del entorno `production`.
5. El despliegue hace backup, actualiza server/worker y comprueba `/healthz`.
6. BookStack se actualiza mediante el workflow manual `Deploy BookStack`,
   siempre con imágenes fijadas.

Las especificaciones completas están en [`docs/specs/README.md`](docs/specs/README.md)
y los runbooks reproducibles en [`infra/README.md`](infra/README.md).

## Ramas actuales

- `main`: baseline que se despliega en producción.
- `codex/email-campaigns`: automatizaciones de email aisladas.
- `codex/linkedin-campaigns`: automatizaciones de LinkedIn aisladas.
- `codex/bookstack`: trabajo específico de documentación/BookStack.

Las ramas de automatización no se despliegan automáticamente a producción.
Primero deben revisarse y fusionarse en `main`.

## Seguridad y datos

- No hagas `git add .` sin revisar antes `git status` y `git diff --cached`.
- No versionamos `.env`, tokens, claves SSH, sesiones de navegador, CSV de
  leads ni dumps SQL.
- Los secretos de producción están en el entorno protegido `production` de
  GitHub y en los ficheros locales del servidor.
- Para una emergencia, los scripts de rollback están en
  `infra/production/rollback-twenty.sh` y `infra/bookstack/rollback-bookstack.sh`.

## Ayuda rápida

| Necesito... | Empiezo por... |
| --- | --- |
| Entender el modelo de entrega | [`docs/specs/platform-delivery.md`](docs/specs/platform-delivery.md) |
| Cambiar o desplegar BookStack | [`docs/README.md`](docs/README.md) |
| Revisar backups y rollback | [`infra/README.md`](infra/README.md) |
| Trabajar en frontend/backend | `packages/twenty-front` / `packages/twenty-server` |
| Importar leads | `docs/BBDD-Leads/` y `scripts/` |

Para conocer el producto upstream de Twenty, consulta la
[documentación oficial](https://docs.twenty.com). Nuestro contrato operativo,
sin embargo, es el que está descrito en este README y en `docs/specs/`.
