# Documentación interna (BookStack)

Este proyecto mantiene la documentación operativa de la empresa en BookStack:
procedimientos, guías de uso del CRM, decisiones técnicas y pasos de respuesta
ante incidencias.

## Dónde está y cómo se usa

- Producción: [`https://doc.arsoluciondigital.com`](https://doc.arsoluciondigital.com)
- Local: `http://localhost:8080`
- Infraestructura versionada: [`../infra/bookstack`](../infra/bookstack)
- Especificación de entrega: [`specs/bookstack-delivery.md`](specs/bookstack-delivery.md)

El contenido de las páginas vive en MariaDB y en el volumen persistente de
BookStack. Por eso Git versiona la infraestructura y los runbooks, pero no
intenta convertir cada página de BookStack en un fichero Markdown.

## Levantar BookStack en local

Desde la raíz del repositorio:

```bash
cp infra/bookstack/bookstack.env.example infra/bookstack/.env.local
```

Edita `infra/bookstack/.env.local`:

- `APP_URL=http://localhost:8080`;
- una `APP_KEY` generada solo para local;
- contraseñas locales para MariaDB;
- imágenes fijadas por versión o digest.

Después inicia los servicios:

```bash
docker compose \
  --env-file infra/bookstack/.env.local \
  -f infra/bookstack/bookstack.compose.yml \
  up -d
```

Comprueba el estado y abre `http://localhost:8080`:

```bash
docker compose \
  --env-file infra/bookstack/.env.local \
  -f infra/bookstack/bookstack.compose.yml \
  ps
```

Para detenerlo sin borrar los volúmenes:

```bash
docker compose \
  --env-file infra/bookstack/.env.local \
  -f infra/bookstack/bookstack.compose.yml \
  down
```

No uses `down -v` salvo que quieras eliminar el contenido local.

## Cómo se actualiza producción

BookStack no se actualiza con cada push. El flujo es deliberadamente manual:

1. Cambia de forma deliberada `BOOKSTACK_IMAGE` y `MARIADB_IMAGE` en la entrada
   del workflow, preferiblemente a digests.
2. Ejecuta **Actions → Deploy BookStack → Run workflow** sobre `main`.
3. Aprueba el entorno protegido `production`.
4. El workflow copia los scripts gestionados al servidor, crea backup de
   MariaDB y del volumen de configuración, actualiza ambos contenedores y
   comprueba `APP_URL`.
5. Verifica la página y deja constancia del cambio en el Pull Request o en
   BookStack.

Los secretos nunca se ponen en este directorio. GitHub usa estos secretos del
entorno `production`:

- `PRODUCTION_SSH_KEY`
- `PRODUCTION_KNOWN_HOSTS`
- `PRODUCTION_HOST`
- `PRODUCTION_USER`

Las credenciales de BookStack/MariaDB permanecen en el `.env.bookstack` del
servidor y no se copian al repositorio.

## Backup y rollback

El despliegue crea archivos en `/opt/twenty-crm/backups/bookstack/`:

- `mariadb_<timestamp>.sql.gz`: exportación de la base de datos;
- `config_<timestamp>.tar.gz`: volumen persistente de configuración.

En una incidencia, conecta al servidor y ejecuta:

```bash
DEPLOY_DIR=/opt/twenty-crm \
ENV_FILE=/opt/twenty-crm/.env.bookstack \
/opt/twenty-crm/managed/bookstack/rollback-bookstack.sh
```

El rollback usa las imágenes anteriores registradas en
`/opt/twenty-crm/.bookstack-deploy-state` y valida de nuevo `APP_URL`.

## Cómo contribuir contenido

1. Comprueba si la información ya existe antes de crear otra página.
2. Usa títulos orientados a una tarea: “Importar leads”, “Restaurar un backup”,
   “Publicar una campaña”, etc.
3. Empieza cada página con el objetivo, los requisitos y el resultado esperado.
4. Separa pasos para usuario, pasos para operador y comandos de emergencia.
5. Incluye fecha de revisión y propietario cuando el procedimiento dependa de
   un servicio externo.
6. Nunca pegues tokens, contraseñas, datos personales ni dumps en BookStack.

Los cambios de infraestructura se revisan como código en GitHub. Los cambios
de contenido se revisan en BookStack y deben enlazar a este repositorio cuando
dependan de un script o configuración versionada.
