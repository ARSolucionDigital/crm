# 📧 Script de Campañas de Email en Frío — Twenty CRM

Motor de envío automatizado de emails en frío personalizados, integrado directamente con la base de datos de Twenty CRM. Convierte una lista de prospectos en una campaña de email orquestada, con personalización por lead, firma HTML profesional y trazabilidad completa de cada acción en el CRM.

---

## 📋 Índice

1. [¿Qué hace este script?](#1-qué-hace-este-script)
2. [Requisitos previos](#2-requisitos-previos)
3. [Instalación y configuración](#3-instalación-y-configuración)
4. [Estructura de archivos](#4-estructura-de-archivos)
5. [Cómo funcionan las plantillas](#5-cómo-funcionan-las-plantillas)
6. [Flujo de ejecución paso a paso](#6-flujo-de-ejecución-paso-a-paso)
7. [Comandos de uso](#7-comandos-de-uso)
8. [¿Qué ocurre en el CRM después de cada envío?](#8-qué-ocurre-en-el-crm-después-de-cada-envío)
9. [Sistema de logs y auditoría](#9-sistema-de-logs-y-auditoría)
10. [Referencia de filtros y parámetros](#10-referencia-de-filtros-y-parámetros)
11. [Resolución de problemas comunes](#11-resolución-de-problemas-comunes)

---

## 1. ¿Qué hace este script?

Este script realiza **de forma completamente automática** el proceso que haría un humano manualmente:

1. **Consulta la base de datos de Twenty CRM** para obtener la lista de prospectos que están listos para recibir el email en frío (estado `SIN_CONTACTAR` con tarea `Enviar email en frio` en estado `TODO`).
2. **Selecciona la plantilla** de la campaña indicada (ej. `moda-operaciones`, `logistica-ceos`).
3. **Personaliza cada email** reemplazando las variables con los datos reales del lead (nombre, empresa, cargo, ciudad).
4. **Construye el email completo** en formato texto plano + HTML con firma profesional visual.
5. **Envía cada email** a través de Google Workspace SMTP (Gmail) con autenticación segura.
6. **Espera un tiempo aleatorio** entre cada envío (45–90 segundos por defecto) para simular comportamiento humano y evitar filtros anti-spam.
7. **Actualiza el CRM automáticamente**: cambia el estado del lead a `EMAIL_FRIO`, marca la tarea como `DONE` y crea un registro de actividad en la línea de tiempo del lead.
8. **Guarda un registro JSON** completo de todos los envíos con su estado (éxito / error).

**Resultado final:** El prospecto recibe un email personalizado en su bandeja de entrada, y en el CRM queda registrado quién recibió qué, cuándo y con qué asunto.

---

## 2. Requisitos previos

### Software necesario

| Requisito | Versión mínima | Cómo verificar |
|---|---|---|
| Python | 3.9+ | `python3 --version` |
| Docker Desktop | Corriendo | `docker ps` (debe aparecer `twenty-db-1`) |
| Twenty CRM | Levantado localmente | `http://localhost:3000` accesible |

### Credenciales necesarias

- **Google App Password** (Contraseña de Aplicación de 16 caracteres) para la cuenta `raul.almeida@arsoluciondigital.com`.
  - Cómo obtenerla: [https://myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)
  - **Requisito:** La cuenta Google debe tener **2FA (verificación en dos pasos) activada**.

### Estado del CRM esperado

Los leads en Twenty CRM deben tener:
- `sequenceStatus = SIN_CONTACTAR`
- Una tarea asociada con título exacto `Enviar email en frio` en estado `TODO`
- Un email válido en el campo `emailsPrimaryEmail`

---

## 3. Instalación y configuración

### Paso 1: Crear el archivo de credenciales

```bash
cp scripts/email-campaigns/.env.campaign.example scripts/email-campaigns/.env.campaign
```

Abre `.env.campaign` y rellena tu App Password:

```env
SMTP_PASS=abcd efgh ijkl mnop   # Los 16 caracteres de tu App Password de Google
```

> ⚠️ **Nunca subas `.env.campaign` a git.** Está en `.gitignore` por seguridad.
> Solo el archivo `.env.campaign.example` (sin contraseñas reales) se versiona.

### Paso 2: Verificar Python (no se requieren paquetes externos)

```bash
python3 --version
# Python 3.11.x o superior
```

El script usa únicamente la **librería estándar de Python** (`smtplib`, `ssl`, `json`, `subprocess`, `pathlib`, etc.). No hay que instalar nada adicional con `pip`.

### Paso 3: Verificar la conexión SMTP

```bash
python3 scripts/email-campaigns/send-campaign.py --test-connection
```

Resultado esperado:
```
🔌 Probando conexión SMTP a smtp.gmail.com:465...
✅ ¡Autenticación SMTP de Google Workspace exitosa!
```

### Paso 4: Enviar un email de prueba a ti mismo

```bash
python3 scripts/email-campaigns/send-campaign.py \
  --template moda-operaciones \
  --test-email raul.almeida@arsoluciondigital.com
```

Revisa tu bandeja de entrada para confirmar que el email llega con el formato correcto, la firma visual y sin adjuntos extraños.

---

## 4. Estructura de archivos

```
scripts/email-campaigns/
│
├── send-campaign.py              # 🧠 Script principal de envío
├── run-all.py                    # 🚀 Runner para ejecutar todas las campañas en secuencia
│
├── .env.campaign                 # 🔐 Credenciales SMTP reales — NO está en git
├── .env.campaign.example         # 📄 Plantilla de credenciales — SÍ está en git (sin datos reales)
│
├── README.md                     # 📖 Esta documentación
│
├── templates/
│   ├── _signature.html           # Firma visual HTML (tabla con logo, nombre, cargo, redes sociales)
│   ├── _signature.txt            # Firma en texto plano (para clientes de email sin HTML)
│   ├── _signature.md             # Firma en Markdown (fuente base de la firma)
│   │
│   ├── moda-operaciones.md       # Campaña: Directores de operaciones de marcas de moda
│   ├── moda-ceos.md              # Campaña: CEOs y dueños de marcas de moda y retail
│   ├── logistica-operaciones.md  # Campaña: Directores de operaciones logísticas y COOs
│   ├── logistica-ceos.md         # Campaña: CEOs de empresas de logística y transporte
│   ├── medianas-integracion.md   # Campaña: Directivos de empresas medianas (integración de sistemas)
│   ├── general-intro.md          # Plantilla de contacto general (comodín)
│   └── operaciones-intro.md      # Plantilla de introducción a operaciones
│
└── logs/                         # 📊 Registros JSON de cada ejecución — NO está en git
    └── campaign_20260901_143022.json
```

---

## 5. Cómo funcionan las plantillas

Cada plantilla es un archivo **Markdown** con una cabecera **YAML frontmatter** que define el asunto del email, seguida del cuerpo del mensaje personalizable.

### Formato de una plantilla

```markdown
---
subject: "{{companyName}} — gestión de inventario en tiempo real"
---

Hola {{nameFirstName}},

He visto que en {{companyName}} gestionáis el stock de varias temporadas al mismo tiempo.
El mayor coste oculto en moda operativa es el cruce manual de inventarios entre ERP y web.

¿Tienes 10 minutos esta semana para ver cómo lo resolvemos sin cambiar de sistema?
```

### Variables disponibles en las plantillas

| Variable | Campo en el CRM | Fallback si está vacío |
|---|---|---|
| `{{nameFirstName}}` | `nameFirstName` del lead | (elimina el "Hola,") |
| `{{nameLastName}}` | `nameLastName` del lead | *(vacío)* |
| `{{companyName}}` | `name` de la empresa vinculada | `tu empresa` |
| `{{jobTitle}}` | `jobTitle` del lead | `tu sector` |
| `{{city}}` | `city` del lead | `tu zona` |
| `{{emailsPrimaryEmail}}` | Email principal del lead | *(vacío)* |

> El sistema aplica **fallbacks inteligentes**: si `companyName` está vacío, en lugar de mostrar `{{companyName}}` deja `tu empresa`. Nunca queda un placeholder sin reemplazar en el email final.

### Cómo añadir una nueva plantilla

1. Crea un archivo `.md` nuevo en `templates/`, por ejemplo `retail-directores.md`.
2. Añade el frontmatter YAML con `subject:`.
3. Escribe el cuerpo usando las variables `{{...}}`.
4. Úsala directamente con `--template retail-directores`.

---

## 6. Flujo de ejecución paso a paso

Lo que ocurre internamente cuando ejecutas `python3 send-campaign.py --template moda-operaciones`:

```
INICIO
  │
  ├── [1] Carga .env.campaign
  │         Lee: SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, FROM_NAME, FROM_EMAIL
  │         Lee: DEFAULT_DELAY_MIN, DEFAULT_DELAY_MAX, WORKSPACE_SCHEMA
  │
  ├── [2] Parsea la plantilla seleccionada (templates/moda-operaciones.md)
  │         Extrae el asunto del bloque ---YAML---
  │         Extrae el cuerpo Markdown después del bloque YAML
  │
  ├── [3] Consulta la base de datos de Twenty CRM vía Docker
  │         Comando: docker exec -i twenty-db-1 psql -U postgres -d default -c "<SQL>"
  │         Filtra por: sequenceStatus = 'SIN_CONTACTAR'
  │         Filtra por: tarea 'Enviar email en frio' con status = 'TODO'
  │         Devuelve: id, nombre, apellido, email, empresa, cargo, ciudad, taskId
  │         Respeta: --limit (por defecto 30), --industry, --role, --min-employees
  │
  ├── [4] Muestra resumen y pide confirmación (omitir con --yes)
  │         Número de leads, tiempo estimado, remitente
  │
  └── [5] BUCLE por cada lead:
        │
        ├── [5.1] Renderiza el asunto con datos reales del lead
        │          "{{companyName}} — inventario" → "CARGO CLUB — inventario"
        │
        ├── [5.2] Renderiza el cuerpo con datos reales del lead
        │          "Hola {{nameFirstName}}" → "Hola Judith"
        │
        ├── [5.3] Construye versión texto plano: body + firma _signature.txt
        │
        ├── [5.4] Construye versión HTML: body HTML + firma _signature.html
        │          Convierte párrafos a <p>, negrita **texto** a <strong>,
        │          enlaces [texto](url) a <a href>, y añade la tabla de firma
        │
        ├── [5.5] Envía el email por SMTP SSL (puerto 465)
        │          Protocolo: multipart/alternative (text/plain + text/html)
        │          Sin adjuntos. Sin imágenes embebidas. El logo está en HTTPS externo.
        │          Esto maximiza la tasa de entrega y evita filtros de spam.
        │
        ├── [5.6] Si el envío fue exitoso → Actualiza el CRM:
        │          UPDATE person SET sequenceStatus = 'EMAIL_FRIO'
        │          UPDATE task SET status = 'DONE'
        │          INSERT INTO timelineActivity (registro con asunto, plantilla, fecha)
        │
        ├── [5.7] Espera N segundos aleatorios (entre delay_min y delay_max)
        │          Simula comportamiento humano, evita patrones lineales detectables
        │
        └── [5.8] Repite con el siguiente lead

  ├── [6] Guarda logs/campaign_YYYYMMDD_HHMMSS.json con el resultado completo
  │
  └── [7] Muestra resumen final: enviados / fallidos / ruta del log

FIN
```

---

## 7. Comandos de uso

### Pre-vuelo: previsualizar sin enviar nada

```bash
python3 scripts/email-campaigns/send-campaign.py \
  --template moda-operaciones \
  --dry-run
```

Muestra los **primeros 3 leads** con el email completo renderizado (asunto + cuerpo + firma). **No envía nada, no modifica el CRM.**

---

### Envío de campaña con confirmación interactiva

```bash
python3 scripts/email-campaigns/send-campaign.py \
  --template moda-operaciones
```

Pide confirmación `¿Deseas iniciar el envío? [s/N]` antes de comenzar.

---

### Envío con confirmación automática (sin pausa de confirmación)

```bash
python3 scripts/email-campaigns/send-campaign.py \
  --template logistica-operaciones \
  --yes
```

---

### Envío con límite personalizado

```bash
python3 scripts/email-campaigns/send-campaign.py \
  --template moda-ceos \
  --limit 10
```

---

### Envío filtrado por industria y cargo

```bash
# Solo leads del sector moda con rol de operaciones
python3 scripts/email-campaigns/send-campaign.py \
  --template moda-operaciones \
  --industry moda \
  --role operaciones \
  --limit 30

# Solo leads de logística con empresa de +50 empleados
python3 scripts/email-campaigns/send-campaign.py \
  --template logistica-ceos \
  --industry logistica \
  --min-employees 50
```

---

### Envío a un lead específico por UUID

```bash
python3 scripts/email-campaigns/send-campaign.py \
  --template moda-operaciones \
  --lead-id b37b89dc-c823-4529-99bf-866dddd95f62 \
  --yes
```

---

### Prueba de conexión SMTP

```bash
python3 scripts/email-campaigns/send-campaign.py --test-connection
```

---

### Email de prueba a tu propia dirección

```bash
python3 scripts/email-campaigns/send-campaign.py \
  --template moda-operaciones \
  --test-email raul.almeida@arsoluciondigital.com
```

---

### Ejecutar todas las campañas en secuencia (run-all.py)

```bash
python3 scripts/email-campaigns/run-all.py
```

**¿Qué hace `run-all.py`?** Ejecuta las 5 campañas de email en frío configuradas, una tras otra, con 30 segundos de pausa entre cada una. Procesa un total de **150 leads** (30 por campaña).

#### Campañas que ejecuta (en orden)

| # | Campaña | Plantilla | Filtros | Leads |
|---|---|---|---|---|
| 1 | Moda & Retail — Operaciones | `moda-operaciones` | `--industry moda --role operaciones` | 30 |
| 2 | Moda & Retail — CEOs / Dueños | `moda-ceos` | `--industry moda --role ceo` | 30 |
| 3 | Logística & Transporte — Operaciones | `logistica-operaciones` | `--industry logistica --role operaciones` | 30 |
| 4 | Logística & Transporte — CEOs / Dirección | `logistica-ceos` | `--industry logistica` | 30 |
| 5 | Medianas Empresas (+50 empleados) | `medianas-integracion` | `--min-employees 50` | 30 |

#### Flujo de ejecución paso a paso

```
INICIO
  │
  ├── [1] Muestra encabezado
  │         "INICIANDO EJECUCIÓN MASIVA: 5 CAMPAÑAS (150 LEADS)"
  │         Remitente, pausas configuradas
  │
  ├── [2] Campaña 1/5: Moda Operaciones
  │         Ejecuta: python3 send-campaign.py --template moda-operaciones --industry moda --role operaciones --limit 30 -y
  │         Espera 30 segundos
  │
  ├── [3] Campaña 2/5: Moda CEOs
  │         Ejecuta: python3 send-campaign.py --template moda-ceos --industry moda --role ceo --limit 30 -y
  │         Espera 30 segundos
  │
  ├── [4] Campaña 3/5: Logística Operaciones
  │         Ejecuta: python3 send-campaign.py --template logistica-operaciones --industry logistica --role operaciones --limit 30 -y
  │         Espera 30 segundos
  │
  ├── [5] Campaña 4/5: Logística CEOs
  │         Ejecuta: python3 send-campaign.py --template logistica-ceos --industry logistica --limit 30 -y
  │         Espera 30 segundos
  │
  ├── [6] Campaña 5/5: Medianas Integración
  │         Ejecuta: python3 send-campaign.py --template medianas-integracion --min-employees 50 --limit 30 -y
  │
  └── [7] Muestra resumen final
            "TODAS LAS 5 CAMPAÑAS HAN SIDO COMPLETADAS CON ÉXITO"

FIN
```

#### Tiempo estimado total

- Cada campaña: ~30 leads × promedio 67.5s (45-90s) = ~34 minutos
- Pausa entre campañas: 30 segundos
- **Total estimado: ~2.5 - 3 horas** (dependiendo de los delays configurados)

#### Configuración de pausas

Las pausas entre correos dentro de cada campaña son las configuradas en `.env.campaign`:
- `DEFAULT_DELAY_MIN=45` (mínimo 45 segundos)
- `DEFAULT_DELAY_MAX=90` (máximo 90 segundos)

La pausa fija entre campañas es de **30 segundos** (hardcoded en el script).

---

### Atajos con Makefile (desde la raíz del proyecto)

```bash
make campaign-preview TEMPLATE=moda-operaciones       # Dry-run
make campaign-send TEMPLATE=moda-operaciones LIMIT=30  # Envío real
```

---

## 8. ¿Qué ocurre en el CRM después de cada envío?

Cuando un email se envía con éxito, el script realiza **3 actualizaciones automáticas** en la base de datos de Twenty CRM:

### Actualización 1: Estado del lead

```sql
UPDATE person
SET "sequenceStatus" = 'EMAIL_FRIO', "updatedAt" = NOW()
WHERE id = '<uuid_del_lead>';
```

El lead pasa de `SIN_CONTACTAR` → `EMAIL_FRIO`. Esto lo excluye de futuros envíos del email frío y lo marca como listo para el siguiente paso del funnel: el seguimiento por LinkedIn.

### Actualización 2: Cierre de la tarea

```sql
UPDATE task
SET status = 'DONE', "updatedAt" = NOW()
WHERE id = '<uuid_de_la_tarea>';
```

La tarea `Enviar email en frio` asociada al lead pasa de `TODO` a `DONE`.

### Actualización 3: Actividad en la línea de tiempo

```sql
INSERT INTO "timelineActivity" (
  id, "createdAt", "updatedAt", "happensAt",
  name, properties,
  "targetPersonId", "workspaceMemberId"
) VALUES (
  gen_random_uuid(), NOW(), NOW(), NOW(),
  'email.sent',
  '{
    "template": "moda-operaciones",
    "subject": "CARGO CLUB — inventario en tiempo real",
    "sentTo": "judith@cargoclub.com",
    "date": "2026-09-01T14:30:22"
  }'::jsonb,
  '<uuid_del_lead>',
  '<uuid_del_workspace_member>'
);
```

Aparece en la pestaña **Actividad** del lead en Twenty CRM con todos los detalles del envío.

---

## 9. Sistema de logs y auditoría

Cada ejecución genera un archivo JSON en `scripts/email-campaigns/logs/`. El nombre incluye la fecha y hora exactas.

### Estructura del archivo de log

```json
{
  "template": "moda-operaciones",
  "total": 30,
  "sent": 30,
  "failed": 0,
  "results": [
    {
      "personId": "b37b89dc-c823-4529-99bf-866dddd95f62",
      "name": "Judith Aliaga Gutierrez",
      "email": "judith@cargoclub.com",
      "company": "CARGO CLUB",
      "status": "SENT",
      "subject": "CARGO CLUB — gestión de inventario en tiempo real",
      "timestamp": "2026-09-01T14:30:22.123456"
    }
  ]
}
```

> Los logs **no se suben a git** (están en `.gitignore`) ya que contienen emails reales de prospectos.

---

## 10. Referencia de filtros y parámetros

| Parámetro | Tipo | Por defecto | Descripción |
|---|---|---|---|
| `--template`, `-t` | `string` | *(requerido)* | Nombre de la plantilla sin extensión. Ej: `moda-operaciones` |
| `--limit`, `-n` | `int` | `30` | Número máximo de leads a procesar en esta ejecución |
| `--dry-run` | `flag` | `false` | Previsualiza sin enviar ni modificar el CRM |
| `--yes`, `-y` | `flag` | `false` | Omite la confirmación interactiva |
| `--status` | `string` | `SIN_CONTACTAR` | Filtra por `sequenceStatus`. Usar `ALL` para no filtrar |
| `--industry` | `string` | *(ninguno)* | Filtra por sector: `moda`, `logistica`, `retail` |
| `--role` | `string` | *(ninguno)* | Filtra por cargo: `operaciones`, `ceo`, `director`, `founder` |
| `--min-employees` | `int` | *(ninguno)* | Empleados mínimos de la empresa del lead |
| `--max-employees` | `int` | *(ninguno)* | Empleados máximos de la empresa del lead |
| `--lead-id` | `string` | *(ninguno)* | UUID de un lead específico (ignora el resto de filtros) |
| `--delay-min` | `int` | `45` | Segundos mínimos de pausa entre emails |
| `--delay-max` | `int` | `90` | Segundos máximos de pausa entre emails |
| `--test-connection` | `flag` | — | Solo prueba la conexión SMTP y sale |
| `--test-email` | `string` | — | Envía un email de prueba a la dirección indicada y sale |

---

## 11. Resolución de problemas comunes

### ❌ "Credenciales SMTP no configuradas"

**Causa:** El archivo `.env.campaign` no existe o `SMTP_PASS` tiene el valor de ejemplo.
**Solución:**
```bash
cp scripts/email-campaigns/.env.campaign.example scripts/email-campaigns/.env.campaign
# Edita el archivo y añade tu App Password de Google (16 caracteres)
```

---

### ❌ "Username and Password not accepted" / "Authentication failed"

**Causa:** La App Password es incorrecta o el usuario no tiene 2FA activado en su cuenta Google.
**Solución:** Ve a [https://myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords), activa 2FA si no lo tienes, y genera una nueva App Password etiquetada como "Twenty CRM".

---

### ❌ "No se encontraron leads pendientes con los filtros aplicados"

**Causa:** No hay leads con `sequenceStatus = SIN_CONTACTAR` que tengan la tarea correcta en estado `TODO`.
**Solución:**
- Verifica en Twenty CRM que los leads tienen el estado correcto.
- Usa `--status ALL` para buscar leads independientemente del estado.
- Verifica que la tarea se llame exactamente `Enviar email en frio`.

---

### ❌ "Database error: connection refused" o "no container with name twenty-db-1"

**Causa:** El contenedor de Postgres de Docker no está corriendo.
**Solución:**
```bash
docker ps | grep twenty-db
# Si no aparece, levanta Twenty CRM:
yarn start
# O solo la base de datos:
cd packages/twenty-docker && docker-compose up -d
```

---

### ❌ El email llega con `{{companyName}}` sin reemplazar

**Causa:** Bug en la plantilla (variable con typo) o campo vacío sin fallback en el script.
**Solución:** Verifica que la variable está escrita exactamente como `{{companyName}}` (con doble llave, sin espacios, case-sensitive). Si el campo del CRM está vacío, el fallback automático es `tu empresa`.
