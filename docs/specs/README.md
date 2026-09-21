# Especificaciones de operación

Estas especificaciones definen cómo se gestiona el monorepo y cómo se entrega
software y configuración a producción. Son el contrato operativo antes de
implementar CI/CD o mover archivos de producción.

## Documentos

- [Plataforma y entrega del CRM](platform-delivery.md): fuente de verdad,
  ramas, imágenes, CI/CD, configuración y recuperación de Twenty.
- [Entrega de BookStack](bookstack-delivery.md): ciclo de actualización y
  recuperación de la documentación interna.
- [Plan de transición](rollout-plan.md): pasos con puntos de control para
  pasar del estado actual al modelo definido.

## Decisiones vigentes

1. Este repositorio sigue siendo el monorepo de Twenty y de la operación de
   producción; BookStack no se separará a otro repositorio por ahora.
2. Git es la fuente de verdad para código, Compose, scripts y documentación.
   El servidor es la fuente de verdad únicamente para datos persistentes y
   secretos de ejecución.
3. Los datos de clientes, exportaciones y credenciales no se versionan.
4. Producción solo ejecutará versiones inmutables identificables. El tag
   `latest` queda prohibido para nuevos despliegues.
