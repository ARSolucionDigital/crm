# Especificación: entrega de Twenty CRM

## Objetivo

Permitir desarrollar localmente, revisar en GitHub y desplegar Twenty CRM de
forma reproducible al servidor, sin perder los leads existentes ni depender de
una imagen mutable de terceros.

## Estado de partida

Producción ejecuta Twenty, PostgreSQL y Redis mediante Docker Compose. Los
datos viven en volúmenes persistentes y se respaldan diariamente. La aplicación
actual funciona y debe considerarse el baseline operativo; no existe un SHA de
Git que permita reconstruir exactamente la imagen que está ejecutándose.

Por tanto, el baseline se registra por su digest de imagen, fecha de despliegue,
configuración no secreta y procedimiento de restauración. No se debe afirmar
que corresponde a una rama local concreta.

## Fuente de verdad y límites

| Elemento | Fuente de verdad | Regla |
| --- | --- | --- |
| Código Twenty, scripts y documentación | Git / `main` | Todo cambio revisable se versiona. |
| Definiciones Docker y plantillas de entorno | Git | Sin secretos ni datos personales. |
| Secretos y `.env` de producción | Servidor / gestor de secretos | Nunca se añaden a Git ni a logs de CI. |
| PostgreSQL, Redis y ficheros de Twenty | Volúmenes de producción + backups | No se reemplazan durante un despliegue. |
| Leads y exportaciones | Almacenamiento privado controlado | Git contiene solo muestras anonimizadas. |

## Estructura objetivo del monorepo

```text
docs/specs/                         # Contrato operativo
infra/
  production/
    twenty.compose.yml              # Compose sin secretos
    twenty.env.example
    scripts/
      deploy-twenty.sh
      backup-twenty.sh
      rollback-twenty.sh
  bookstack/                        # Definición de BookStack, independiente
scripts/
  email-campaigns/                  # Automatización opcional; no se despliega
  linkedin-campaigns/               # Automatización opcional; no se despliega
  leads-import/                     # Código de importación sin datos reales
.github/workflows/
  validate.yml
  deploy-twenty.yml
  deploy-bookstack.yml
```

La ruta final puede ajustarse durante la implementación, pero las definiciones
de infraestructura deben estar aisladas del código de producto y tener una
plantilla de variables asociada.

## Modelo de ramas

`main` es la rama estable y desplegable del CRM. Todo merge a `main` debe poder
generar una imagen y pasar validaciones. No contiene campañas ejecutándose,
sesiones de navegador, credenciales ni CSV de clientes.

Las ramas de trabajo se crean desde `main` y se integran mediante pull request:

```text
feat/email-campaigns
feat/linkedin-campaigns
feat/leads-import
ops/production-baseline
ops/bookstack
```

Las campañas de email y LinkedIn se mantienen separadas porque tienen riesgos,
secretos, límites de proveedores y ritmos de entrega distintos. El código de
importación se revisa aparte; los archivos reales de `docs/BBDD-Leads/` se
mueven a almacenamiento privado antes de que su rama sea integrada.

## Artefacto desplegable

Cada commit aprobado de `main` produce una imagen de la organización:

```text
ghcr.io/arsoluciondigital/crm:<git-sha>
```

Opcionalmente se publica un tag de versión semántica, pero el servidor siempre
recibe el SHA completo. El manifiesto Compose de producción usa la referencia
completa `IMAGE_REFERENCE` y
nunca usa `latest`.

El registro de despliegue debe guardar: SHA Git, digest Docker, autor, fecha,
estado del health check y el SHA previamente activo. Esto permite rollback sin
recompilar ni descargar una etiqueta distinta inesperadamente.

## Flujo de cambios

```text
Rama de trabajo -> Pull request -> Validación CI -> merge a main
-> crear/push imagen SHA -> backup -> despliegue SSH -> health checks
-> registrar versión activa
```

### Validación de pull request

La primera versión de CI ejecuta, como mínimo:

1. comprobación de formato y lint de los archivos modificados;
2. typecheck de `twenty-front` y `twenty-server` cuando cambien;
3. tests unitarios relevantes cuando cambien;
4. detección de secretos y rechazo de archivos de leads/exportaciones.

Las validaciones costosas pueden convertirse en requeridas gradualmente, pero
una PR no puede mergearse con errores de tipo, lint o secretos.

### Despliegue de `main`

El workflow de despliegue se activa solo tras un merge a `main` y requiere una
aprobación de entorno `production` mientras el proceso sea nuevo. Debe:

1. construir y publicar la imagen inmutable;
2. conectar por SSH con una clave de despliegue limitada;
3. ejecutar un backup comprobable de PostgreSQL y los volúmenes de Twenty;
4. actualizar exclusivamente `IMAGE_REFERENCE=<registry>/<image>:<SHA>`;
5. hacer `docker compose pull` y `up -d` para Twenty y worker;
6. verificar `/healthz`, HTTPS y el estado de los contenedores;
7. guardar el resultado y la versión previa.

Un fallo antes de sustituir contenedores deja producción intacta. Un fallo tras
sustituirlos ejecuta rollback a la referencia anterior y conserva la evidencia para
diagnóstico. Las migraciones de base de datos requieren una comprobación
adicional y un backup confirmado antes de aplicar la imagen.

## Desarrollo local

Local reproduce la topología de Twenty con Compose y variables no productivas.
El desarrollador carga datos ficticios o anonimizados. Una importación real se
ejecuta como operación controlada, nunca como efecto secundario de `yarn start`
ni de un deploy.

El comando de despliegue no puede ejecutar `git add .`, crear commits ni hacer
push. Recibe un SHA ya publicado por CI y solo opera sobre ese artefacto.

## Backups y restauración

Antes de cada despliegue se toma un backup y diariamente se mantienen copias
con retención definida. Deben existir y probarse trimestralmente:

- restauración de PostgreSQL en un entorno aislado;
- restauración de `server-local-data`;
- arranque de Twenty restaurado sin apuntar a producción;
- verificación de un conjunto mínimo de leads y metadatos.

## Criterios de aceptación

- Un SHA de Git identifica de forma inequívoca el código e imagen de producción.
- No hay `latest` en los manifiestos de producción de Twenty.
- Un despliegue no puede incluir archivos no revisados ni datos de leads.
- Se puede volver a la versión anterior con un comando documentado.
- Un restore ensayado recupera la instancia y sus leads sin modificar producción.
