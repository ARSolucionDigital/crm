# Scripts de Infraestructura — Twenty CRM

Scripts de nivel raíz para gestionar la infraestructura de Twenty CRM: túneles ngrok para exposición pública y configuración inicial del CRM con campos personalizados.

---

## Índice

1. [Resumen rápido](#1-resumen-rápido)
2. [tunnel-start.sh — Iniciar túnel ngrok](#2-tunnel-startsh--iniciar-túnel-ngrok)
3. [tunnel-stop.sh — Detener túnel ngrok](#3-tunnel-stopsh--detener-túnel-ngrok)
4. [crm-configure.sh — Configurar CRM para Ar Solución Digital](#4-crm-configuresh--configurar-crm-para-ar-solución-digital)
5. [Estructura de archivos](#5-estructura-de-archivos)
6. [Flujo visual del sistema de túneles](#6-flujo-visual-del-sistema-de-túneles)
7. [Resolución de problemas](#7-resolución-de-problemas)

---

## 1. Resumen rápido

| Script | Propósito | Comando rápido |
|---|---|---|
| `tunnel-start.sh` | Exponer localhost:3000 vía ngrok | `bash scripts/tunnel-start.sh` |
| `tunnel-stop.sh` | Cerrar túnel y restaurar localhost | `bash scripts/tunnel-stop.sh` |
| `crm-configure.sh` | Crear campos personalizados en el CRM | `bash scripts/crm-configure.sh` |

---

## 2. tunnel-start.sh — Iniciar túnel ngrok

**Archivo:** `scripts/tunnel-start.sh`

### ¿Qué hace este script?

Lanza un servidor ngrok que expone la instancia de Twenty CRM (que corre en `localhost:3000`) a una URL pública de internet. Esto permite acceder al CRM desde cualquier dispositivo (móvil, tableta, otra red) sin configurar firewalls ni port forwarding.

### Requisitos previos

| Requisito | Cómo verificar |
|---|---|
| ngrok instalado | `ngrok version` |
| jq instalado | `jq --version` |
| Docker corriendo con Twenty | `docker ps \| grep server.*Up` |
| Archivo `.env` existe | `ls packages/twenty-docker/.env` |

### Flujo de ejecución paso a paso

```
INICIO
  │
  ├── [1] Verifica prerequisitos
  │         ¿ngrok instalado? → Si no: FAIL con link de descarga
  │         ¿jq instalado? → Si no: FAIL con instrucción brew install jq
  │         ¿Existe .env? → Si no: FAIL indicando ejecutar make up primero
  │
  ├── [2] Verifica que Twenty está corriendo
  │         docker compose ps → busca "server.*Up"
  │         Si no está: FAIL indicando ejecutar make up primero
  │
  ├── [3] Detiene ngroks anteriores
  │         Lee .ngrok.pid y mata el proceso si sigue vivo
  │         También busca procesos ngrok en puerto 4040 y los mata
  │
  ├── [4] Lanza ngrok en background
  │         nohup ngrok http 3000 --log=stdout &
  │         Guarda el PID en .ngrok.pid
  │
  ├── [5] Espera la URL del túnel (máx 30 segundos)
  │         Consulta http://localhost:4040/api/tunnels cada segundo
  │         Extrae la URL pública con jq
  │         Si no resuelve en 30s: FAIL
  │
  ├── [6] Actualiza SERVER_URL en .env
  │         Crea backup: .env.bak
  │         Reemplaza SERVER_URL=https://xxxx.ngrok-free.app
  │
  ├── [7] Recrea contenedores server y worker
  │         docker compose up -d --force-recreate server worker
  │         Esto aplica el nuevo SERVER_URL al contenedor
  │
  ├── [8] Espera a que el servidor esté sano (máx 60 segundos)
  │         Verifica "server.*healthy" en docker compose ps
  │
  └── [9] Muestra resultado
            URL pública del túnel
            Instrucciones para detener: make tunnel-stop

FIN
```

### Resultado esperado

Al finalizar verás:
```
============================================
  Tunnel ready!
  URL: https://xxxx.ngrok-free.app
============================================

  Access from any device: https://xxxx.ngrok-free.app
  Stop tunnel: make tunnel-stop
```

### Comandos de uso

```bash
# Iniciar túnel (desde la raíz del proyecto)
make tunnel

# O directamente:
bash scripts/tunnel-start.sh
```

---

## 3. tunnel-stop.sh — Detener túnel ngrok

**Archivo:** `scripts/tunnel-stop.sh`

### ¿Qué hace este script?

Cierra el túnel ngrok, restaura la configuración del servidor a `localhost:3000` y recrea los contenedores para que Twenty CRM vuelva a funcionar solo en local.

### Flujo de ejecución paso a paso

```
INICIO
  │
  ├── [1] Detiene ngrok
  │         Si existe .ngrok.pid → mata el proceso por PID
  │         Si no existe PID file → busca procesos ngrok en puerto 4040
  │         Si no encuentra nada → OK (ya estaba detenido)
  │
  ├── [2] Restaura SERVER_URL en .env
  │         Reemplaza la URL de ngrok por http://localhost:3000
  │         Si SERVER_URL no existía → la añade
  │
  ├── [3] Recrea contenedores server y worker
  │         docker compose up -d --force-recreate server worker
  │         Los contenedores ahora usan localhost:3000
  │
  └── [4] Muestra confirmación
            "Tunnel closed. Twenty is back on localhost:3000"

FIN
```

### Resultado esperado

```
=> Stopping ngrok (PID 12345)...
   done: ngrok stopped
=> Restoring SERVER_URL to localhost...
   done: SERVER_URL restored to http://localhost:3000
=> Recreating server and worker containers with localhost URL...
   done: Tunnel closed. Twenty is back on localhost:3000
```

### Comandos de uso

```bash
# Detener túnel
make tunnel-stop

# O directamente:
bash scripts/tunnel-stop.sh
```

---

## 4. crm-configure.sh — Configurar CRM para Ar Solución Digital

**Archivo:** `scripts/crm-configure.sh`

### ¿Qué hace este script?

Configura Twenty CRM con los campos personalizados necesarios para el proceso de ventas de **Ar Solución Digital** (empresa B2B de desarrollo de software). Crea 9 campos personalizados en 3 objetos del CRM.

### Requisitos previos

| Requisito | Cómo verificar |
|---|---|
| Twenty CRM corriendo | `http://localhost:3000` accesible |
| jq instalado | `jq --version` |
| curl instalado | `curl --version` |

### Flujo de ejecución paso a paso

```
INICIO
  │
  ├── [1] Autenticación
  │         Mutation GraphQL: signIn(email, password)
  │         Email: admin@arsoluciondigital.com
  │         Password: Admin1234!
  │         Resultado: access_token + workspace_id
  │
  ├── [2] Obtener IDs de metadatos de objetos
  │         Query: minimalMetadata { objectMetadataItems }
  │         Extrae IDs de: company, person, opportunity
  │
  ├── [3] Crear campos personalizados en COMPANY
  │         Campo "Sector" (SELECT):
  │           Opciones: Tecnología, Retail, Salud, Finanzas,
  │                    Manufactura, Educación, Otro
  │
  │         Campo "Company Size" (SELECT):
  │           Opciones: 1-10, 11-50, 50-200, 200+
  │
  │         Campo "Lead Source" (SELECT):
  │           Opciones: LinkedIn, Web, Referido, Evento, Prospección fría
  │
  ├── [4] Crear campos personalizados en PERSON
  │         Campo "LinkedIn" (LINKS): URL del perfil de LinkedIn
  │         Campo "Last Contact" (DATE): Fecha del último contacto
  │         Campo "Sequence Status" (SELECT):
  │           Opciones: Sin contactar, Email enviado, LinkedIn enviado,
  │                    Llamada hecha, Respondió, No interesa
  │
  ├── [5] Crear campos personalizados en OPPORTUNITY
  │         Campo "Service Type" (SELECT):
  │           Opciones: Desarrollo a medida, Consultoría, Mantenimiento,
  │                    Migración, Auditoría técnica
  │
  │         Campo "Estimated Budget" (CURRENCY): Presupuesto estimado
  │         Campo "Estimated Start Date" (DATE): Fecha estimada de inicio
  │
  └── [6] Muestra resumen
            Lista de campos creados por objeto
            Siguientes pasos: verificar en UI, configurar pipeline

FIN
```

### Campos creados — Resumen visual

```
COMPANY (Empresa)
├── Sector          → SELECT (7 opciones)
├── Company Size    → SELECT (4 opciones)
└── Lead Source     → SELECT (5 opciones)

PERSON (Contacto)
├── LinkedIn        → LINKS (URL)
├── Last Contact    → DATE
└── Sequence Status → SELECT (6 opciones)

OPPORTUNITY (Oportunidad)
├── Service Type           → SELECT (5 opciones)
├── Estimated Budget       → CURRENCY
└── Estimated Start Date   → DATE
```

### Resultado esperado

```
=> Step 1: Authenticating...
   ✓ Access token obtained
   ✓ Workspace ID: dy5bo7ispsr4124id7w3seocg
=> Step 2: Fetching object metadata...
   ✓ Company object ID: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
   ✓ Person object ID: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
   ✓ Opportunity object ID: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
=> Step 3: Creating custom fields for Companies...
   ✓ Sector field created: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
   ✓ Company Size field created: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
   ✓ Lead Source field created: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
=> Step 4: Creating custom fields for People...
   ✓ LinkedIn field created: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
   ✓ Last Contact field created: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
   ✓ Sequence Status field created: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
=> Step 5: Creating custom fields for Opportunities...
   ✓ Service Type field created: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
   ✓ Estimated Budget field created: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
   ✓ Estimated Start Date field created: xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx

============================================
  CRM Configuration Complete!
============================================

  Next steps:
  1. Open http://localhost:3000
  2. Go to Settings > Data Model to verify fields
  3. Configure Opportunity pipeline stages in the UI
  4. Start adding your real leads
```

### Comandos de uso

```bash
bash scripts/crm-configure.sh
```

### ¿Qué pasa si los campos ya existen?

El script no falla si un campo ya existe. Muestra un warning y continúa:
```
   Warning: Sector field may already exist or failed: ...
```

Esto permite ejecutar el script múltiples veces sin riesgo de duplicados.

---

## 5. Estructura de archivos

```
scripts/
├── README.md                   # 📖 Esta documentación
│
├── tunnel-start.sh             # 🌐 Iniciar túnel ngrok
├── tunnel-stop.sh              # 🌐 Detener túnel ngrok
├── crm-configure.sh            # ⚙️ Configurar campos personalizados del CRM
│
├── email-campaigns/            # 📧 Campañas de email (ver su propio README)
│   ├── send-campaign.py
│   ├── run-all.py
│   ├── templates/
│   ├── logs/
│   └── README.md
│
└── linkedin-campaigns/         # 💼 Campañas de LinkedIn (ver su propio README)
    ├── send-linkedin.py
    ├── templates/
    ├── logs/
    └── README.md
```

---

## 6. Flujo visual del sistema de túneles

```
                    ANTES de tunnel-start.sh
                    ┌─────────────────────┐
                    │   localhost:3000     │
                    │   (Twenty CRM)      │
                    │   Solo accesible    │
                    │   desde tu máquina   │
                    └─────────────────────┘

                              │
                              ▼  tunnel-start.sh

                    DESPUÉS de tunnel-start.sh
                    ┌─────────────────────┐
                    │   localhost:3000     │
                    │   (Twenty CRM)      │◄──── ngrok tunnel
                    └─────────────────────┘      │
                                                 │
                              ┌──────────────────┘
                              ▼
                    ┌─────────────────────┐
                    │  https://xxx.ngrok  │
                    │  -free.app          │
                    │  Accesible desde    │
                    │  CUALQUIER device   │
                    └─────────────────────┘

                              │
                              ▼  tunnel-stop.sh

                    DESPUÉS de tunnel-stop.sh
                    ┌─────────────────────┐
                    │   localhost:3000     │
                    │   (Twenty CRM)      │
                    │   Solo accesible    │
                    │   desde tu máquina   │
                    └─────────────────────┘
```

---

## 7. Resolución de problemas

### ❌ "ngrok not installed"

```bash
# macOS
brew install ngrok

# O descargar desde https://ngrok.com/download
```

### ❌ "jq not installed"

```bash
brew install jq
```

### ❌ "Twenty server is not running"

```bash
# Levantar todo (Docker)
make up

# O solo verificar
docker ps | grep twenty
```

### ❌ "ngrok did not register a tunnel within 30 seconds"

- Verifica que ngrok está autenticado: `ngrok config check`
- Si es primera vez, ejecuta: `ngrok config add-authtoken <tu_token>`
- Verifica que el puerto 3000 no está ocupado por otro proceso: `lsof -ti:3000`

### ❌ crm-configure.sh falla al autenticar

- Verifica que Twenty CRM está corriendo en `localhost:3000`
- Las credenciales por defecto son: `admin@arsoluciondigital.com` / `Admin1234!`
- Si cambiaste la contraseña, edita las variables `EMAIL` y `PASSWORD` al inicio del script

### ❌ "Warning: Sector field may already exist"

No es un error. Significa que el campo ya fue creado en una ejecución anterior. El script continúa con los demás campos.
