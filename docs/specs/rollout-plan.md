# Plan de transición al monorepo operable

## Estado de ejecución — 21 Sep 2026

- **Fase 0:** ejecutada en lo operativo. Se capturaron los digests actuales,
  se migró la configuración de BookStack a un `.env` con permisos 600, se
  fijaron los Compose legados y se verificaron backups SQL y de volúmenes.
- **Fase 1:** implementada en el checkout. `infra/` y los workflows están
  creados; los CSV de leads y `.env.bak` se conservan localmente pero ya no
  están en el índice de Git.
- **Fase 2:** workflows y scripts instalados en
  `/opt/twenty-crm/managed/`; falta configurar los secretos del entorno
  `production` en GitHub y ejecutar el primer build/push de imagen propia.
- **Fase 3:** Compose y workflow de BookStack están implementados; falta el
  primer lanzamiento aprobado del workflow para validar la ruta de actualización
  end-to-end. Los servicios actuales no se reiniciaron durante esta transición.
- **Pendiente de coordinación:** purgar los CSV y secretos del historial Git
  remoto mediante una reescritura acordada; retirarlos del índice evita nuevas
  exposiciones, pero no modifica el historial existente.

## Principio de seguridad

No se reemplaza la instancia funcional ni se migran datos durante la primera
fase. Cada hito tiene una comprobación y un rollback antes de continuar.

## Fase 0 — Inventario y congelación

1. Registrar en un archivo operativo privado el digest de Twenty y BookStack,
   estado de volúmenes, dominios, puertos y fecha del último backup.
2. Descargar y verificar una copia de backup de cada servicio.
3. Rotar credenciales que hayan aparecido en archivos compartidos o historial
   de terminal y trasladarlas a `.env` solo de servidor o a un gestor de
   secretos.
4. Añadir reglas para impedir que CSV, SQL de datos, sesiones o `.env` entren
   al índice de Git.

Salida: una línea base recuperable, sin cambios de aplicación.

## Fase 1 — Saneamiento de Git

1. Crear `ops/production-baseline` desde la referencia estable elegida.
2. Mover la definición no secreta de Compose y scripts a `infra/`.
3. Reemplazar el script local que hace staging automático por comandos seguros
   que solo consulten o desplieguen un SHA explícito.
4. Extraer email, LinkedIn e importación de leads a sus ramas de función.
5. Establecer protección de `main`: pull request, CI verde y revisión.

Salida: `main` es una base limpia y desplegable; los experimentos permanecen
aislados.

## Fase 2 — Artefactos y CI

1. Crear la imagen de Twenty desde el monorepo y publicarla con SHA inmutable.
2. Añadir `validate.yml` y validar su ejecución en una PR de prueba.
3. Configurar secretos de CI: clave SSH de despliegue, registro de imágenes y
   host; no usar secretos del runtime de la aplicación.
4. Ejecutar el primer deploy en modo aprobación manual y conservar el tag
   anterior.

Salida: el SHA publicado llega a producción y aparece en el registro de deploy.

## Fase 3 — BookStack

1. Versionar sus plantillas Compose y scripts sanitizados en `infra/bookstack`.
2. Fijar la imagen actual a una versión/digest conocido.
3. Probar el workflow manual de backup, actualización y rollback.
4. Separar formalmente sus alertas y calendario de actualizaciones de Twenty.

Salida: BookStack se mantiene en el monorepo sin acoplar su entrega a la del CRM.

## Fase 4 — Operación continua

1. Ensayar restores trimestrales de Twenty y mensuales de BookStack.
2. Revisar actualizaciones de imágenes y dependencias mensualmente.
3. Evaluar separar repositorios solo cuando los equipos, permisos, ciclos de
   release o costes operativos justifiquen esa complejidad.
