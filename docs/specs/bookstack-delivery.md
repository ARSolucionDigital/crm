# Especificación: entrega de BookStack

## Objetivo

Gestionar BookStack dentro del mismo monorepo, con configuración, actualizaciones
y recuperación independientes de Twenty. BookStack es un producto de terceros:
el repositorio gestiona su infraestructura y contenido operativo, no su código
fuente.

## Separación respecto a Twenty

BookStack comparte host, proxy, backups y disciplina de entrega con Twenty,
pero tiene Compose, imagen, volumen y base MariaDB propios. Ningún despliegue de
Twenty puede reiniciar, migrar o sustituir BookStack; ningún despliegue de
BookStack puede tocar PostgreSQL, Redis o los volúmenes de Twenty.

## Configuración versionada

`infra/bookstack/` contendrá:

```text
bookstack.compose.yml
bookstack.env.example
scripts/deploy-bookstack.sh
scripts/backup-bookstack.sh
scripts/rollback-bookstack.sh
README.md
```

El fichero real `.env` sigue solo en producción. Incluye claves de aplicación,
contraseñas de MariaDB, dominio, correo y cualquier integración. Los ejemplos
usan valores vacíos o marcadores y documentan el significado de cada variable.

## Versionado y actualización

La imagen se fija a una versión concreta de BookStack, no a `latest`.
Ejemplo: `lscr.io/linuxserver/bookstack:<version>`. Cada actualización se hace
en una PR `ops/bookstack-upgrade-<version>` que declara versión anterior,
versión objetivo, cambios relevantes y plan de rollback.

El deploy se lanza mediante workflow manual con aprobación `production`. El
workflow exige como inputs las referencias fijadas de BookStack y MariaDB; así
se puede actualizar una imagen sin copiar el `.env` con secretos al repositorio.

1. validar el Compose y las variables requeridas sin revelar valores;
2. verificar un backup reciente de MariaDB y del volumen de configuración;
3. crear un backup previo a la actualización;
4. descargar la imagen fijada y recrear solo los servicios BookStack;
5. comprobar el endpoint HTTPS y los logs de arranque;
6. registrar imagen/digest, hora y resultado.

La versión anterior permanece disponible hasta que la verificación termine. El
rollback restaura el tag anterior; si hay migración de datos incompatible,
restaura además la base y configuración desde el backup previo.

## Contenido de la documentación

El contenido editable de BookStack vive en MariaDB y en su volumen, no se
sincroniza bidireccionalmente desde Markdown en la primera fase. Los runbooks,
especificaciones y documentación técnica del CRM sí se mantienen en Git bajo
`docs/`.

Una futura fase puede exportar periódicamente BookStack a un archivo privado
para auditoría, pero no debe sobrescribir contenido desde Git sin una decisión
explícita de gobernanza.

## Validación y recuperación

El workflow de BookStack comprueba que el Compose sea válido y que no contenga
secretos. Tras el deploy valida HTTPS, el estado del contenedor y la salud de
MariaDB. Mensualmente se ensaya una restauración aislada de MariaDB y
`bookstack-data`.

## Criterios de aceptación

- Twenty y BookStack se despliegan por workflows distintos.
- La versión y digest de BookStack están registrados y son reproducibles.
- Las credenciales no están en Git, logs ni plantillas con valores reales.
- Existe un backup previo y un rollback documentado por cada actualización.
