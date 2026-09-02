# Script de Campañas de LinkedIn & Sales Navigator — Twenty CRM

Motor de automatización de LinkedIn y Sales Navigator con Playwright, integrado directamente con la base de datos de Twenty CRM. Envía DMs, InMails y solicitudes de conexión personalizadas con detección automática del escenario de perfil.

---

## Índice

1. [¿Qué hace este script?](#1-qué-hace-este-script)
2. [Requisitos previos](#2-requisitos-previos)
3. [Instalación y configuración](#3-instalación-y-configuración)
4. [Estructura de archivos](#4-estructura-de-archivos)
5. [Cómo funciona la detección de escenarios](#5-cómo-funciona-la-detección-de-escenarios)
6. [Cómo funcionan las plantillas](#6-cómo-funcionan-las-plantillas)
7. [Flujo de ejecución paso a paso](#7-flujo-de-ejecución-paso-a-paso)
8. [Comandos de uso](#8-comandos-de-uso)
9. [¿Qué ocurre en el CRM después de cada acción?](#9-qué-ocurre-en-el-crm-después-de-cada-acción)
10. [Sistema de stealth y anti-detección](#10-sistema-de-stealth-y-anti-detección)
11. [Sistema de logs y auditoría](#11-sistema-de-logs-y-auditoría)
12. [Referencia de filtros y parámetros](#12-referencia-de-filtros-y-parámetros)
13. [Resolución de problemas comunes](#13-resolución-de-problemas-comunes)

---

## 1. ¿Qué hace este script?

Este script realiza **de forma completamente automática** el proceso que haría un humano manualmente en LinkedIn:

1. **Consulta la base de datos de Twenty CRM** para obtener la lista de prospectos que tienen URL de LinkedIn y están listos para recibir un mensaje (estado `EMAIL_FRIO` con tarea `DM Linkedin` en estado `TODO`).
2. **Abre Google Chrome** en modo stealth (invisible para LinkedIn) con una sesión persistente.
3. **Navega al perfil de cada lead** en LinkedIn.
4. **Detecta automáticamente el escenario** del perfil:
   - ¿Es conexión de 1er grado? → Envía **DM** (mensaje directo)
   - ¿No es conexión? → Prioriza **InMail** (usa créditos de Sales Nav)
   - ¿No hay InMail disponible? → Envía **solicitud de conexión** con nota personalizada
5. **Personaliza el mensaje** reemplazando las variables con datos reales del lead.
6. **Escribe el mensaje** con tipeo humano simulado (velocidad variable, pausas en puntuación).
7. **Envía el mensaje** en LinkedIn sin ser detectado como bot.
8. **Actualiza el CRM automáticamente**: cambia el estado del lead a `LINKEDIN_ENVIADO`, marca la tarea como `DONE` y crea un registro de actividad en la línea de tiempo del lead.
9. **Guarda un registro JSON** completo de todas las acciones.

**Resultado final:** El prospecto recibe un mensaje personalizado en LinkedIn, y en el CRM queda registrado quién recibió qué acción, cuándo y con qué plantilla.

---

## 2. Requisitos previos

### Software necesario

| Requisito | Versión mínima | Cómo verificar |
|---|---|---|
| Python | 3.9+ | `python3 --version` |
| Docker Desktop | Corriendo | `docker ps` (debe aparecer `twenty-db-1`) |
| Twenty CRM | Levantado localmente | `http://localhost:3000` accesible |
| Playwright | Instalado | `pip3 list \| grep playwright` |
| Google Chrome | Instalado | `/Applications/Google Chrome.app` |

### Instalar Playwright

```bash
cd scripts/linkedin-campaigns
python3 -m venv .venv
source .venv/bin/activate
pip install playwright
playwright install chromium
```

### Sesión de LinkedIn

Necesitas haber iniciado sesión al menos una vez usando el modo `--login`. Esto guarda las cookies de LinkedIn en un archivo `session.json` para reutilizaciones posteriores.

---

## 3. Instalación y configuración

### Paso 1: Crear el archivo de configuración

```bash
cp scripts/linkedin-campaigns/.env.linkedin.example scripts/linkedin-campaigns/.env.linkedin
```

### Paso 2: Configurar las variables

Abre `.env.linkedin` y ajusta según necesites:

```env
# Modo visual (para debugging y login)
HEADLESS=false

# Delays entre leads (recomendado: 90-180 segundos)
DEFAULT_DELAY_MIN=90
DEFAULT_DELAY_MAX=180

# Límite de leads por ejecución
DEFAULT_BATCH_LIMIT=20

# Directorio del perfil de Chrome persistente
CHROME_PROFILE_DIR=./.chrome-session
```

### Paso 3: Configurar la sesión de LinkedIn (obligatorio la primera vez)

```bash
python3 scripts/linkedin-campaigns/send-linkedin.py --login
```

Esto:
1. Abre Google Chrome con la URL `https://www.linkedin.com/feed/`
2. **Tú inicias sesión manualmente** en LinkedIn (y Sales Navigator si lo usas)
3. Cuando estés dentro, presionas **ENTER** en la terminal
4. El script guarda las cookies y tokens en `session.json`
5. Las sesiones posteriores reutilizan estas cookies automáticamente

### Paso 4: Verificar con una URL de prueba

```bash
python3 scripts/linkedin-campaigns/send-linkedin.py \
  --test-url https://www.linkedin.com/in/perfil-ejemplo/ \
  --template moda-operaciones \
  --dry-run
```

Esto prueba la detección de escenario y el renderizado de la plantilla sin enviar nada.

---

## 4. Estructura de archivos

```
scripts/linkedin-campaigns/
│
├── send-linkedin.py              # 🧠 Script principal de automatización
│
├── .env.linkedin                 # 🔐 Configuración — NO está en git
├── .env.linkedin.example         # 📄 Plantilla de configuración — SÍ está en git
│
├── session.json                  # 🔑 Cookies de sesión de LinkedIn — NO está en git
├── .chrome-session/              # 📁 Perfil persistente de Chrome — NO está en git
│
├── README.md                     # 📖 Esta documentación
│
├── templates/
│   ├── moda-operaciones/
│   │   ├── dm.md                 # Plantilla para DM directo
│   │   ├── inmail.md             # Plantilla para InMail
│   │   └── conexion.md           # Plantilla para solicitud de conexión
│   │
│   ├── moda-ceos/
│   │   ├── dm.md
│   │   ├── inmail.md
│   │   └── conexion.md
│   │
│   ├── logistica-operaciones/
│   │   ├── dm.md
│   │   ├── inmail.md
│   │   └── conexion.md
│   │
│   ├── logistica-ceos/
│   │   ├── dm.md
│   │   ├── inmail.md
│   │   └── conexion.md
│   │
│   └── medianas-integracion/
│       ├── dm.md
│       ├── inmail.md
│       └── conexion.md
│
├── logs/                         # 📊 Registros JSON de cada ejecución — NO está en git
│   └── linkedin_20260901_143022.json
│
└── .venv/                        # 🐍 Entorno virtual de Python — NO está en git
```

---

## 5. Cómo funciona la detección de escenarios

Cuando el script llega al perfil de un lead en LinkedIn, analiza la página para determinar qué tipo de acción realizar. La lógica de detección sigue esta prioridad:

### Escenarios posibles

```
PERFIL DE LINKEDIN
        │
        ├── ¿URL da 404 o authwall?
        │     SÍ → ERROR (perfil inaccesible)
        │
        ├── ¿Es conexión de 1er grado? (badge "1st")
        │     SÍ → ¿Hay botón "Message"?
        │           SÍ → DM (Mensaje Directo)
        │           NO → CONNECT (fallback)
        │
        ├── ¿No es conexión (2do/3er grado)?
        │     ¿Hay botón InMail o Sales Navigator?
        │       SÍ → INMAIL (usa créditos de Sales Nav)
        │       NO → ¿Hay botón "Connect"?
        │             SÍ → CONNECT (solicitud con nota)
        │             NO → ¿Ya está pendiente?
        │                   SÍ → PENDING (omitido)
        │                   NO → CONNECT (sin botón visible)
        │
        └── RESULTADO: DM | INMAIL | CONNECT | PENDING | ERROR
```

### Tabla resumen

| Escenario | Significado | Acción | Plantilla usada |
|---|---|---|---|
| `DM` | Conexión de 1er grado | Mensaje directo en chat | `dm.md` |
| `INMAIL` | No es conexión, hay créditos InMail | InMail vía Sales Navigator | `inmail.md` |
| `CONNECT` | No hay InMail, hay botón Connect | Solicitud de conexión con nota | `conexion.md` |
| `PENDING` | Ya se envió solicitud previamente | Se omite (skip) | — |
| `ERROR` | Perfil no encontrado o authwall | Se omite (skip) | — |

### ¿Por qué priorizar InMail sobre conexión?

- El **InMail** tiene mayor tasa de apertura que una solicitud de conexión
- LinkedIn prioriza los InMails en la bandeja del destinatario
- Los créditos de InMail se renuevan mensualmente en Sales Navigator
- Si no hay créditos disponibles, el script cae automáticamente a CONNECT

---

## 6. Cómo funcionan las plantillas

Cada campaña tiene 3 plantillas (una por modalidad): `dm.md`, `inmail.md` y `conexion.md`.

### Formato de una plantilla DM

```markdown
Hola {{nameFirstName}},

He visto que en {{companyName}} trabajáis con procesos operativos que seguro
seBenefician de una buena integración de sistemas.

¿Tienes 10 minutos esta semana para que te cuente cómo ayudamos a empresas
como la suya a automatizar sus flujos de datos?
```

### Formato de una plantilla InMail (con subject)

```markdown
---
subject: "{{companyName}} — automatización de procesos"
---

Hola {{nameFirstName}},

¿Sabías que las empresas de {{jobTitle}} pierden un promedio de 15 horas
semanales en tareas manuales de integración?

En {{companyName}} hemos ayudado a empresas similares a reducir ese tiempo
a menos de 2 horas. ¿Te gustaría ver cómo?
```

### Variables disponibles

| Variable | Campo en el CRM | Fallback si está vacío |
|---|---|---|
| `{{nameFirstName}}` | `nameFirstName` del lead | (elimina el "Hola") |
| `{{nameLastName}}` | `nameLastName` del lead | *(vacío)* |
| `{{companyName}}` | `name` de la empresa vinculada | `tu empresa` |
| `{{jobTitle}}` | `jobTitle` del lead | `tu sector` |
| `{{city}}` | `city` del lead | `tu zona` |

### Cómo añadir una nueva campaña

1. Crea un directorio en `templates/`, por ejemplo `nueva-campana/`
2. Crea 3 archivos: `dm.md`, `inmail.md`, `conexion.md`
3. Usa las variables `{{...}}` para personalizar
4. Ejecuta: `python3 send-linkedin.py --template nueva-campana`

---

## 7. Flujo de ejecución paso a paso

Lo que ocurre internamente cuando ejecutas `python3 send-linkedin.py --template moda-operaciones`:

```
INICIO
  │
  ├── [1] Carga .env.linkedin
  │         Lee: HEADLESS, DEFAULT_DELAY_MIN, DEFAULT_DELAY_MAX
  │         Lee: CHROME_PROFILE_DIR, WORKSPACE_SCHEMA
  │
  ├── [2] Consulta la base de datos de Twenty CRM vía Docker
  │         Comando: docker exec -i twenty-db-1 psql -U postgres -d default -c "<SQL>"
  │         Filtra por: sequenceStatus = 'EMAIL_FRIO'
  │         Filtra por: tarea 'DM Linkedin' con status = 'TODO'
  │         Filtra por: linkedinLinkPrimaryLinkUrl IS NOT NULL
  │         Devuelve: id, nombre, email, URL LinkedIn, empresa, cargo, taskId
  │
  ├── [3] Muestra resumen y pide confirmación (omitir con --yes)
  │         Número de prospectos, tiempo estimado, modo visual
  │
  ├── [4] Lanza navegador Playwright en modo stealth
  │         Perfil persistente de Chrome
  │         User agent real de Chrome
  │         Inyecta scripts anti-detección (navigator.webdriver = undefined)
  │
  └── [5] BUCLE por cada lead:
        │
        ├── [5.1] Normaliza la URL de LinkedIn
        │          Quita caracteres encodeados, fuerza https://
        │
        ├── [5.2] Navega al perfil del lead
        │          page.goto(url, timeout=30s)
        │          Espera 2.5-4.5 segundos (tiempo humano)
        │
        ├── [5.3] Detecta el escenario del perfil
        │          Analiza badges de conexión (1st, 2nd, 3rd)
        │          Busca botones de Message, InMail, Connect
        │          Resultado: DM | INMAIL | CONNECT | PENDING | ERROR
        │
        ├── [5.4] Selecciona la plantilla según el escenario
        │          DM → templates/moda-operaciones/dm.md
        │          INMAIL → templates/moda-operaciones/inmail.md
        │          CONNECT → templates/moda-operaciones/conexion.md
        │
        ├── [5.5] Renderiza el mensaje con datos reales del lead
        │          "{{companyName}}" → "CARGO CLUB"
        │          "{{nameFirstName}}" → "Judith"
        │
        ├── [5.6] Ejecuta la acción en LinkedIn (si no es dry-run):
        │          │
        │          ├── DM:
        │          │     Cierra overlays de chat previos
        │          │     Click en botón "Message"
        │          │     Escribe mensaje con tipeo humano
        │          │     Click en "Send"
        │          │
        │          ├── INMAIL:
        │          │     Cierra overlays de chat previos
        │          │     Click en botón InMail/Sales Navigator
        │          │     Escribe asunto (si existe)
        │          │     Escribe cuerpo con tipeo humano
        │          │     Click en "Send InMail"
        │          │
        │          └── CONNECT:
        │                Click en botón "Connect"
        │                Click en "Add a note"
        │                Escribe nota (máx 300 caracteres)
        │                Click en "Send"
        │
        ├── [5.7] Actualiza el CRM:
        │          UPDATE person SET sequenceStatus = 'LINKEDIN_ENVIADO'
        │          UPDATE task SET status = 'DONE'
        │          INSERT INTO timelineActivity (registro con acción, plantilla, fecha)
        │
        ├── [5.8] Espera N segundos aleatorios (entre delay_min y delay_max)
        │          Simula comportamiento humano
        │          Evita patrones lineales detectables por LinkedIn
        │
        └── [5.9] Repite con el siguiente lead

  ├── [6] Guarda logs/linkedin_YYYYMMDD_HHMMSS.json con el resultado completo
  │
  └── [7] Muestra resumen final: enviados / omitidos / fallidos / ruta del log

FIN
```

---

## 8. Comandos de uso

### Configurar sesión de LinkedIn (obligatorio la primera vez)

```bash
python3 scripts/linkedin-campaigns/send-linkedin.py --login
```

Abre Chrome, te deja iniciar sesión, y guarda las cookies al presionar ENTER.

---

### Pre-vuelo: probar con una URL individual

```bash
python3 scripts/linkedin-campaigns/send-linkedin.py \
  --test-url https://www.linkedin.com/in/perfil-ejemplo/ \
  --template moda-operaciones \
  --dry-run
```

Muestra el escenario detectado, la plantilla seleccionada y el mensaje renderizado. **No envía nada.**

---

### Pre-vuelo: previsualizar sin enviar nada

```bash
python3 scripts/linkedin-campaigns/send-linkedin.py \
  --template moda-operaciones \
  --dry-run
```

Consulta los leads del CRM y muestra el escenario detectado y el mensaje renderizado para cada uno. **No envía nada, no modifica el CRM.**

---

### Envío de campaña con confirmación interactiva

```bash
python3 scripts/linkedin-campaigns/send-linkedin.py \
  --template moda-operaciones
```

Pide confirmación `¿Deseas iniciar el proceso de LinkedIn ahora? [s/N]` antes de comenzar.

---

### Envío con confirmación automática

```bash
python3 scripts/linkedin-campaigns/send-linkedin.py \
  --template logistica-operaciones \
  --yes
```

---

### Envío en modo headless (sin ventana visible)

```bash
python3 scripts/linkedin-campaigns/send-linkedin.py \
  --template moda-ceos \
  --headless \
  --yes
```

---

### Envío con límite personalizado

```bash
python3 scripts/linkedin-campaigns/send-linkedin.py \
  --template moda-operaciones \
  --limit 10
```

---

### Envío filtrado por industria y cargo

```bash
# Solo leads del sector moda con rol de operaciones
python3 scripts/linkedin-campaigns/send-linkedin.py \
  --template moda-operaciones \
  --industry moda \
  --role operaciones \
  --limit 20

# Solo leads de logística con empresa de +50 empleados
python3 scripts/linkedin-campaigns/send-linkedin.py \
  --template logistica-ceos \
  --industry logistica \
  --min-employees 50
```

---

### Envío a un lead específico por UUID

```bash
python3 scripts/linkedin-campaigns/send-linkedin.py \
  --template moda-operaciones \
  --lead-id b37b89dc-c823-4529-99bf-866dddd95f62 \
  --yes
```

---

### Atajos con Makefile (desde la raíz del proyecto)

```bash
make linkedin-login                                            # Configurar sesión
make linkedin-preview TEMPLATE=moda-operaciones                # Dry-run
make linkedin-send TEMPLATE=moda-operaciones LIMIT=20          # Envío real
```

---

## 9. ¿Qué ocurre en el CRM después de cada acción?

Cuando una acción de LinkedIn se ejecuta con éxito, el script realiza **3 actualizaciones automáticas** en la base de datos de Twenty CRM:

### Actualización 1: Estado del lead

```sql
UPDATE person
SET "sequenceStatus" = 'LINKEDIN_ENVIADO', "updatedAt" = NOW()
WHERE id = '<uuid_del_lead>';
```

El lead pasa de `EMAIL_FRIO` → `LINKEDIN_ENVIADO`. Esto lo excluye de futuros envíos de LinkedIn.

### Actualización 2: Cierre de la tarea

```sql
UPDATE task
SET status = 'DONE', "updatedAt" = NOW()
WHERE id = '<uuid_de_la_tarea>';
```

La tarea `DM Linkedin` asociada al lead pasa de `TODO` a `DONE`.

### Actualización 3: Actividad en la línea de tiempo

```sql
INSERT INTO "timelineActivity" (
  id, "createdAt", "updatedAt", "happensAt",
  name, properties,
  "targetPersonId", "workspaceMemberId"
) VALUES (
  gen_random_uuid(), NOW(), NOW(), NOW(),
  'linkedin.dm_sent',
  '{
    "campaign": "moda-operaciones",
    "actionType": "linkedin.dm_sent",
    "profileUrl": "https://www.linkedin.com/in/perfil/",
    "date": "2026-09-01T14:30:22"
  }'::jsonb,
  '<uuid_del_lead>',
  '<uuid_del_workspace_member>'
);
```

### Tipos de acción registrados

| Acción | Significado |
|---|---|
| `linkedin.dm_sent` | Se envió un mensaje directo |
| `linkedin.inmail_sent` | Se envió un InMail |
| `linkedin.connection_requested` | Se envió solicitud de conexión |
| `linkedin.already_pending` | Ya había solicitud pendiente (omitido) |

---

## 10. Sistema de stealth y anti-detección

LinkedIn detecta y bloquea bots. Este script usa múltiples técnicas para evitar la detección:

### Playwright con Chrome nativo

```python
playwright.chromium.launch_persistent_context(
    channel="chrome",  # Usa Chrome instalado, no Chromium de Playwright
    user_data_dir=profile_dir,  # Perfil persistente con cookies reales
    ignore_default_args=["--enable-automation"],
    args=[
        "--disable-blink-features=AutomationControlled",
        "--disable-infobars",
        "--no-sandbox",
        "--start-maximized"
    ],
    user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) ..."
)
```

### Inyección de scripts anti-detección

```javascript
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
window.chrome = { runtime: {} };
```

### Tipeo humano simulado

```python
def human_type(element, text):
    for char in text:
        element.type(char, delay=random.randint(35, 85))  # 35-85ms por tecla
        if char in [".", ",", "!", "?", "\n"]:
            time.sleep(random.uniform(0.12, 0.30))  # Pausa en puntuación
```

### Pausas aleatorias entre leads

- **DM/InMail:** 90-180 segundos por defecto (configurable)
- **Conexiones:** 90-180 segundos por defecto
- Los valores son aleatorios dentro del rango para evitar patrones lineales

### Cierre automático de overlays

Antes de cada acción, el script cierra automáticamente las ventanas de chat flotantes de leads anteriores para evitar interferencias.

---

## 11. Sistema de logs y auditoría

Cada ejecución genera un archivo JSON en `scripts/linkedin-campaigns/logs/`.

### Estructura del archivo de log

```json
{
  "campaign": "moda-operaciones",
  "total": 20,
  "sent": 18,
  "skipped": 1,
  "failed": 1,
  "results": [
    {
      "personId": "b37b89dc-c823-4529-99bf-866dddd95f62",
      "name": "Judith Aliaga Gutierrez",
      "company": "CARGO CLUB",
      "status": "SENT",
      "scenario": "DM",
      "timestamp": "2026-09-01T14:30:22.123456"
    },
    {
      "personId": "c48d90ed-d934-5630-aacc-977eeff06g73",
      "name": "Laura Romero",
      "company": "OTRA EMPRESA",
      "status": "SKIPPED",
      "scenario": "PENDING",
      "timestamp": "2026-09-01T14:35:45.789012"
    }
  ]
}
```

### Estados posibles

| Estado | Significado |
|---|---|
| `SENT` | Acción ejecutada con éxito |
| `SKIPPED` | Omitido (perfil pendiente o inaccesible) |
| `FAILED` | Error al procesar el perfil |
| `DRY_RUN` | Simulación exitosa (modo previsualización) |

---

## 12. Referencia de filtros y parámetros

| Parámetro | Tipo | Por defecto | Descripción |
|---|---|---|---|
| `--template`, `-t` | `string` | `moda-operaciones` | Nombre de la campaña |
| `--limit`, `-n` | `int` | `20` | Número máximo de leads a procesar |
| `--dry-run` | `flag` | `false` | Previsualiza sin enviar ni modificar el CRM |
| `--yes`, `-y` | `flag` | `false` | Omite la confirmación interactiva |
| `--headless` | `flag` | `false` | Ejecuta sin ventana visible |
| `--login` | `flag` | `false` | Abre Chrome para configurar sesión |
| `--test-url` | `string` | — | Prueba la detección con una URL específica |
| `--status` | `string` | `EMAIL_FRIO` | Filtra por `sequenceStatus`. Usar `ALL` para no filtrar |
| `--industry` | `string` | *(ninguno)* | Filtra por sector: `moda`, `logistica`, `retail` |
| `--role` | `string` | *(ninguno)* | Filtra por cargo: `operaciones`, `ceo`, `director` |
| `--min-employees` | `int` | *(ninguno)* | Empleados mínimos de la empresa del lead |
| `--max-employees` | `int` | *(ninguno)* | Empleados máximos de la empresa del lead |
| `--lead-id` | `string` | *(ninguno)* | UUID de un lead específico |
| `--delay-min` | `int` | `90` | Segundos mínimos de pausa entre leads |
| `--delay-max` | `int` | `180` | Segundos máximos de pausa entre leads |

---

## 13. Resolución de problemas comunes

### ❌ "No se encontraron leads pendientes con el estado 'EMAIL_FRIO'"

**Causa:** No hay leads con `sequenceStatus = EMAIL_FRIO` que tengan la tarea `DM Linkedin` en estado `TODO` y URL de LinkedIn válida.

**Solución:**
- Verifica en Twenty CRM que los leads tienen el estado correcto
- Verifica que la tarea se llame exactamente `DM Linkedin`
- Usa `--status ALL` para buscar leads independientemente del estado

---

### ❌ "Sesión no guardada" o LinkedIn muestra authwall

**Causa:** Las cookies de sesión expiraron o no se guardaron correctamente.

**Solución:**
```bash
# Volver a configurar la sesión
python3 scripts/linkedin-campaigns/send-linkedin.py --login
```

---

### ❌ "Playwright no encontrado" o "ModuleNotFoundError"

**Causa:** Playwright no está instalado en el entorno virtual.

**Solución:**
```bash
cd scripts/linkedin-campaigns
python3 -m venv .venv
source .venv/bin/activate
pip install playwright
playwright install chromium
```

---

### ❌ El navegador no abre en modo visual

**Causa:** `HEADLESS=true` en `.env.linkedin` o se pasó `--headless`.

**Solución:**
- Editar `.env.linkedin` y poner `HEADLESS=false`
- O ejecutar sin `--headless`

---

### ❌ LinkedIn bloquea la cuenta

**Causa:** Demasiados mensajes en poco tiempo o patrones detectados.

**Solución:**
- Aumentar los delays: `--delay-min 120 --delay-max 240`
- Reducir el límite por ejecución: `--limit 10`
- Ejecutar solo en horario laboral (9am-6pm)
- No usar headless (el modo visual genera menos sospecha)

---

### ❌ "Database error: connection refused"

**Causa:** El contenedor de Postgres de Docker no está corriendo.

**Solución:**
```bash
docker ps | grep twenty-db
# Si no aparece, levantar Twenty CRM:
make up
```

---

### ❌ El chat de LinkedIn no se encuentra

**Causa:** LinkedIn cambió la estructura del DOM (selectores CSS obsoletos).

**Solución:**
- Verificar que la sesión sigue activa con `--test-url`
- Actualizar los selectores CSS en la función `detect_profile_scenario()`
- Reportar el issue con captura de pantalla
