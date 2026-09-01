#!/usr/bin/env python3
"""
Twenty CRM — Cold Email Campaign CLI Sender
============================================
Automated personalized cold email campaign executor for Google Workspace & Twenty CRM.
"""

import argparse
import datetime
import html
import json
import os
import random
import re
import smtplib
import ssl
import subprocess
import sys
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

# Paths
BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"
LOGS_DIR = BASE_DIR / "logs"
ENV_FILE = BASE_DIR / ".env.campaign"
SIGNATURE_HTML_FILE = TEMPLATES_DIR / "_signature.html"
SIGNATURE_TXT_FILE = TEMPLATES_DIR / "_signature.txt"

def load_env():
    """Load configuration from .env.campaign file."""
    config = {
        "SMTP_HOST": "smtp.gmail.com",
        "SMTP_PORT": "465",
        "SMTP_SECURE": "true",
        "SMTP_USER": "",
        "SMTP_PASS": "",
        "FROM_NAME": "Raúl Almeida",
        "FROM_EMAIL": "raul.almeida@arsoluciondigital.com",
        "REPLY_TO": "raul.almeida@arsoluciondigital.com",
        "DEFAULT_DELAY_MIN": "45",
        "DEFAULT_DELAY_MAX": "90",
        "DEFAULT_BATCH_LIMIT": "30",
        "WORKSPACE_SCHEMA": "workspace_dy5bo7ispsr4124id7w3seocg",
        "WORKSPACE_MEMBER_ID": "2801663c-0ab4-4a61-8a2a-88dd2e709c07",
    }
    if ENV_FILE.exists():
        with open(ENV_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    config[k.strip()] = v.strip().strip("\"'")
    return config

def run_psql_json(query):
    """Execute query in twenty-db-1 container and return JSON parsed result."""
    wrapped_query = f"SELECT json_agg(t) FROM ({query}) t;"
    cmd = [
        "docker", "exec", "-i", "twenty-db-1",
        "psql", "-U", "postgres", "-d", "default", "-t", "-A", "-c", wrapped_query
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"Database error: {res.stderr.strip()}")
    out = res.stdout.strip()
    if not out or out == "null" or out == "":
        return []
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        return []

def run_psql_exec(sql):
    """Execute raw SQL statements in twenty-db-1."""
    cmd = [
        "docker", "exec", "-i", "twenty-db-1",
        "psql", "-U", "postgres", "-d", "default", "-c", sql
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"Database error: {res.stderr.strip()}")
    return res.stdout.strip()

def parse_template(template_name):
    """Read and parse template file with YAML frontmatter."""
    if not template_name.endswith(".md"):
        template_name += ".md"
    
    file_path = TEMPLATES_DIR / template_name
    if not file_path.exists():
        available = [f.stem for f in TEMPLATES_DIR.glob("*.md") if not f.name.startswith("_")]
        raise FileNotFoundError(
            f"Plantilla '{template_name}' no encontrada en {TEMPLATES_DIR}.\n"
            f"Plantillas disponibles: {', '.join(available)}"
        )
    
    content = file_path.read_text(encoding="utf-8")
    
    subject = "Mensaje de contacto"
    body = content
    
    # Check for frontmatter
    fm_match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", content, re.DOTALL)
    if fm_match:
        fm_text = fm_match.group(1)
        body = fm_match.group(2)
        for line in fm_text.splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                if k.strip().lower() == "subject":
                    subject = v.strip().strip("\"'")
            
    return subject, body.strip()

def render_content(text, lead):
    """Render template string with lead attributes and smart fallbacks."""
    first_name = (lead.get("nameFirstName") or "").strip()
    last_name = (lead.get("nameLastName") or "").strip()
    company = (lead.get("companyName") or "").strip()
    job_title = (lead.get("jobTitle") or "").strip()
    email_addr = (lead.get("emailsPrimaryEmail") or "").strip()
    city = (lead.get("city") or "").strip()

    first_name_val = first_name if first_name else ""
    company_val = company if company else "tu empresa"
    job_title_val = job_title if job_title else "tu sector"
    city_val = city if city else "tu zona"

    rendered = text
    if first_name_val:
        rendered = rendered.replace("{{nameFirstName}}", first_name_val)
    else:
        rendered = re.sub(r"Hola,\s*\{\{nameFirstName\}\}:?", "Hola:", rendered)
        rendered = re.sub(r"Hola\s*\{\{nameFirstName\}\}:?", "Hola:", rendered)
        rendered = rendered.replace("{{nameFirstName}}", "")

    rendered = rendered.replace("{{nameLastName}}", last_name)
    rendered = rendered.replace("{{companyName}}", company_val)
    rendered = rendered.replace("{{jobTitle}}", job_title_val)
    rendered = rendered.replace("{{emailsPrimaryEmail}}", email_addr)
    rendered = rendered.replace("{{city}}", city_val)
    rendered = re.sub(r"[ ]{2,}", " ", rendered)
    
    return rendered

def build_full_text(body_text):
    """Combine rendered body text with text signature."""
    sig_txt = ""
    if SIGNATURE_TXT_FILE.exists():
        sig_txt = SIGNATURE_TXT_FILE.read_text(encoding="utf-8").strip()
    elif (TEMPLATES_DIR / "_signature.md").exists():
        sig_txt = (TEMPLATES_DIR / "_signature.md").read_text(encoding="utf-8").strip()
    
    if sig_txt:
        return f"{body_text}\n\n{sig_txt}"
    return body_text

def build_full_html(body_text):
    """Convert body markdown to email HTML and append HTML table signature."""
    paragraphs = body_text.strip().split("\n\n")
    html_paragraphs = []
    
    for p in paragraphs:
        p = p.strip()
        if not p:
            continue
        p_html = html.escape(p)
        p_html = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", p_html)
        p_html = re.sub(r"\[(.+?)\]\((.+?)\)", r'<a href="\2" style="color: #2563eb; text-decoration: underline;">\1</a>', p_html)
        p_html = p_html.replace("\n", "<br>")
        html_paragraphs.append(f'<p style="margin: 0 0 16px 0; line-height: 1.6; color: #1e293b; font-size: 15px;">{p_html}</p>')

    body_html = "\n".join(html_paragraphs)
    
    sig_html = ""
    if SIGNATURE_HTML_FILE.exists():
        sig_html = SIGNATURE_HTML_FILE.read_text(encoding="utf-8").strip()
        
    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; font-size: 15px; color: #1e293b; background-color: #ffffff; padding: 12px 0; margin: 0;">
{body_html}
{sig_html}
</body>
</html>"""

def get_target_leads(config, status_filter="SIN_CONTACTAR", limit=30, lead_id=None, industry=None, role=None, min_employees=None, max_employees=None):
    """Query eligible leads from Twenty CRM database."""
    schema = config["WORKSPACE_SCHEMA"]
    
    where_clauses = [
        "p.\"deletedAt\" IS NULL",
        "p.\"emailsPrimaryEmail\" IS NOT NULL",
        "p.\"emailsPrimaryEmail\" != ''"
    ]
    
    if lead_id:
        where_clauses.append(f"p.id = '{lead_id}'")
    else:
        if status_filter and status_filter.upper() != "ALL":
            where_clauses.append(f"p.\"sequenceStatus\" = '{status_filter}'")
        
        where_clauses.append(f"""
            EXISTS (
                SELECT 1 FROM \"{schema}\".\"taskTarget\" tt 
                JOIN \"{schema}\".\"task\" t ON tt.\"taskId\" = t.id 
                WHERE tt.\"targetPersonId\" = p.id 
                  AND t.title = 'Enviar email en frio' 
                  AND t.status = 'TODO'
            )
        """)
        
        if industry:
            if industry.lower() == "moda" or industry.lower() == "retail":
                where_clauses.append("(c.industry ILIKE '%moda%' OR c.industry ILIKE '%ropa%' OR c.industry ILIKE '%retail%' OR c.industry ILIKE '%textil%')")
            elif industry.lower() == "logistica" or industry.lower() == "transporte":
                where_clauses.append("(c.industry ILIKE '%transporte%' OR c.industry ILIKE '%logistica%' OR c.industry ILIKE '%logística%' OR c.industry ILIKE '%camion%' OR c.industry ILIKE '%maritimo%')")
            else:
                where_clauses.append(f"c.industry ILIKE '%{industry}%'")
                
        if role:
            if role.lower() in ["operaciones", "coo", "ops"]:
                where_clauses.append("(p.\"jobTitle\" ILIKE '%operat%' OR p.\"jobTitle\" ILIKE '%coo%' OR p.\"jobTitle\" ILIKE '%logist%' OR p.\"jobTitle\" ILIKE '%trafic%')")
            elif role.lower() in ["ceo", "director", "founder", "fundador", "owner", "dueño"]:
                where_clauses.append("(p.\"jobTitle\" ILIKE '%ceo%' OR p.\"jobTitle\" ILIKE '%fundad%' OR p.\"jobTitle\" ILIKE '%founder%' OR p.\"jobTitle\" ILIKE '%owner%' OR p.\"jobTitle\" ILIKE '%general%')")
            else:
                where_clauses.append(f"p.\"jobTitle\" ILIKE '%{role}%'")
                
        if min_employees is not None:
            where_clauses.append(f"c.employees >= {min_employees}")
        if max_employees is not None:
            where_clauses.append(f"c.employees <= {max_employees}")
        
    where_sql = " AND ".join(where_clauses)
    
    query = f"""
        SELECT 
            p.id, 
            p.\"nameFirstName\", 
            p.\"nameLastName\", 
            p.\"emailsPrimaryEmail\", 
            p.\"jobTitle\", 
            p.\"city\",
            p.\"sequenceStatus\",
            c.name as \"companyName\",
            c.industry as \"companyIndustry\",
            c.employees as \"companyEmployees\",
            (
                SELECT t.id FROM \"{schema}\".\"taskTarget\" tt 
                JOIN \"{schema}\".\"task\" t ON tt.\"taskId\" = t.id 
                WHERE tt.\"targetPersonId\" = p.id 
                  AND t.title = 'Enviar email en frio' 
                LIMIT 1
            ) as \"taskId\"
        FROM \"{schema}\".\"person\" p 
        LEFT JOIN \"{schema}\".\"company\" c ON p.\"companyId\" = c.id 
        WHERE {where_sql}
        ORDER BY p.\"createdAt\" ASC
        LIMIT {limit}
    """
    return run_psql_json(query)

def send_email_smtp(config, to_email, subject, body_text, body_html):
    """Send pure text/HTML email via Google Workspace SMTP without attachments."""
    host = config["SMTP_HOST"]
    port = int(config["SMTP_PORT"])
    user = config["SMTP_USER"]
    password = config["SMTP_PASS"].replace(" ", "")
    from_name = config["FROM_NAME"]
    from_email = config["FROM_EMAIL"]
    reply_to = config.get("REPLY_TO", from_email)

    if not user or not password or password == "tu_app_password_de_16_caracteres":
        raise ValueError("Credenciales SMTP no configuradas. Añade tu App Password en scripts/email-campaigns/.env.campaign")

    # Clean multipart/alternative without MIME attachment parts
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"{from_name} <{from_email}>"
    msg["To"] = to_email
    msg["Reply-To"] = reply_to
    msg["Date"] = datetime.datetime.now(datetime.timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")

    part_text = MIMEText(body_text, "plain", "utf-8")
    part_html = MIMEText(body_html, "html", "utf-8")
    msg.attach(part_text)
    msg.attach(part_html)

    if port == 465:
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(host, port, context=context, timeout=20) as server:
            server.login(user, password)
            server.send_message(msg)
    else:
        with smtplib.SMTP(host, port, timeout=20) as server:
            server.starttls(context=ssl.create_default_context())
            server.login(user, password)
            server.send_message(msg)

def test_smtp_connection(config):
    """Test SMTP connection and credentials."""
    host = config["SMTP_HOST"]
    port = int(config["SMTP_PORT"])
    user = config["SMTP_USER"]
    password = config["SMTP_PASS"].replace(" ", "")
    
    print(f"\n🔌 Probando conexión SMTP a {host}:{port} con usuario {user}...")
    if not user or not password or password == "tu_app_password_de_16_caracteres":
        print("❌ Error: Debes colocar tu Contraseña de Aplicación de 16 caracteres en scripts/email-campaigns/.env.campaign")
        return False
        
    try:
        if port == 465:
            context = ssl.create_default_context()
            with smtplib.SMTP_SSL(host, port, context=context, timeout=15) as server:
                server.login(user, password)
        else:
            with smtplib.SMTP(host, port, timeout=15) as server:
                server.starttls(context=ssl.create_default_context())
                server.login(user, password)
        print("✅ ¡Autenticación SMTP de Google Workspace exitosa!\n")
        return True
    except Exception as e:
        print(f"❌ Fallo de autenticación SMTP: {e}\n")
        return False

def update_crm_after_send(config, lead, template_name, subject):
    """Update task and sequence status in Twenty CRM."""
    schema = config["WORKSPACE_SCHEMA"]
    member_id = config["WORKSPACE_MEMBER_ID"]
    person_id = lead["id"]
    task_id = lead.get("taskId")
    
    # 1. Update sequenceStatus to EMAIL_FRIO
    run_psql_exec(f"""
        UPDATE \"{schema}\".\"person\" 
        SET \"sequenceStatus\" = 'EMAIL_FRIO', \"updatedAt\" = NOW() 
        WHERE id = '{person_id}';
    """)
    
    # 2. Update task to DONE
    if task_id:
        run_psql_exec(f"""
            UPDATE \"{schema}\".\"task\" 
            SET status = 'DONE', \"updatedAt\" = NOW() 
            WHERE id = '{task_id}';
        """)
        
    # 3. Create timeline activity record
    activity_props = json.dumps({
        "template": template_name,
        "subject": subject,
        "sentTo": lead.get("emailsPrimaryEmail"),
        "date": datetime.datetime.now().isoformat()
    })
    
    run_psql_exec(f"""
        INSERT INTO \"{schema}\".\"timelineActivity\" (
            id, \"createdAt\", \"updatedAt\", \"happensAt\",
            name, properties,
            \"targetPersonId\", \"workspaceMemberId\",
            \"createdBySource\", \"updatedBySource\",
            \"createdByName\", \"updatedByName\"
        ) VALUES (
            gen_random_uuid(), NOW(), NOW(), NOW(),
            'email.sent', '{activity_props}'::jsonb,
            '{person_id}', '{member_id}',
            'MANUAL', 'MANUAL',
            'Raul Almeida', 'Raul Almeida'
        );
    """)

def main():
    parser = argparse.ArgumentParser(
        description="Twenty CRM — CLI de Campañas de Email en Frío Personalizadas",
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--template", "-t", help="Nombre de la plantilla en templates/ (ej. moda-operaciones, moda-ceos, logistica-operaciones)")
    parser.add_argument("--test-connection", action="store_true", help="Prueba solo la conexión y autenticación con Google SMTP")
    parser.add_argument("--test-email", help="Envía un email de prueba a tu dirección para verificar recepción y formato")
    parser.add_argument("--limit", "-n", type=int, default=30, help="Límite de leads a procesar (por defecto: 30)")
    parser.add_argument("--dry-run", action="store_true", help="Previsualiza el contenido y destinatarios sin enviar nada")
    parser.add_argument("--delay-min", type=int, help="Segundos mínimos de espera entre envíos")
    parser.add_argument("--delay-max", type=int, help="Segundos máximos de espera entre envíos")
    parser.add_argument("--status", default="SIN_CONTACTAR", help="Filtrar por Sequence Status (por defecto: SIN_CONTACTAR, o 'ALL')")
    parser.add_argument("--industry", help="Filtrar por sector (ej. moda, logistica, retail)")
    parser.add_argument("--role", help="Filtrar por cargo (ej. operaciones, ceo, founder)")
    parser.add_argument("--min-employees", type=int, help="Filtrar por mínimo de empleados (ej. 50)")
    parser.add_argument("--max-employees", type=int, help="Filtrar por máximo de empleados (ej. 49)")
    parser.add_argument("--lead-id", help="Enviar solo a un Lead específico por UUID")
    parser.add_argument("--yes", "-y", action="store_true", help="Omitir confirmación interactiva")

    args = parser.parse_args()
    config = load_env()

    # Test connection flag
    if args.test_connection:
        ok = test_smtp_connection(config)
        sys.exit(0 if ok else 1)

    # Test email flag
    if args.test_email:
        template_to_test = args.template if args.template else "moda-operaciones"
        subject_raw, body_raw = parse_template(template_to_test)
        sample_lead = {
            "nameFirstName": "Raúl",
            "nameLastName": "Almeida",
            "companyName": "AR Solución Digital",
            "jobTitle": "CTO",
            "emailsPrimaryEmail": args.test_email,
            "city": "Malta"
        }
        s = "[TEST SIN ADJUNTO] " + render_content(subject_raw, sample_lead)
        b_rendered = render_content(body_raw, sample_lead)
        b_text = build_full_text(b_rendered)
        b_html = build_full_html(b_rendered)
        print(f"\n📧 Enviando correo de prueba SIN adjuntos a {args.test_email}...")
        try:
            send_email_smtp(config, args.test_email, s, b_text, b_html)
            print(f"✅ ¡Correo de prueba enviado con éxito a {args.test_email}! Revisa tu bandeja de entrada.\n")
            sys.exit(0)
        except Exception as e:
            print(f"❌ Error al enviar correo de prueba: {e}\n")
            sys.exit(1)

    if not args.template:
        print("❌ Error: Debes especificar una plantilla con --template <nombre> (ej. moda-operaciones)")
        parser.print_help()
        sys.exit(1)

    delay_min = args.delay_min if args.delay_min is not None else int(config["DEFAULT_DELAY_MIN"])
    delay_max = args.delay_max if args.delay_max is not None else int(config["DEFAULT_DELAY_MAX"])
    if delay_max < delay_min:
        delay_max = delay_min

    # 1. Parse template
    try:
        subject_raw, body_raw = parse_template(args.template)
    except Exception as e:
        print(f"\n❌ Error al cargar plantilla: {e}\n")
        sys.exit(1)

    # 2. Fetch leads
    print(f"\n🔍 Consultando leads en Twenty CRM (Estado: {args.status}, Límite: {args.limit})...")
    leads = get_target_leads(
        config, 
        status_filter=args.status, 
        limit=args.limit, 
        lead_id=args.lead_id,
        industry=args.industry,
        role=args.role,
        min_employees=args.min_employees,
        max_employees=args.max_employees
    )

    if not leads:
        print(f"⚠️ No se encontraron leads pendientes con los filtros aplicados.")
        sys.exit(0)

    print(f"✅ Se encontraron {len(leads)} leads listos para la campaña.")

    # 3. Dry-run Mode
    if args.dry_run:
        print("\n" + "=" * 70)
        print(f"🛠️  MODO DRY-RUN (PREVISUALIZACIÓN) — Plantilla: {args.template}")
        print("=" * 70)
        
        for i, lead in enumerate(leads[:3], 1):
            s = render_content(subject_raw, lead)
            b = render_content(body_raw, lead)
            b_full = build_full_text(b)
            print(f"\n--- [Ejemplo {i}/{min(3, len(leads))}] ---")
            print(f"👤 Destinatario : {lead.get('nameFirstName', '')} {lead.get('nameLastName', '')} <{lead['emailsPrimaryEmail']}>")
            print(f"🏢 Empresa      : {lead.get('companyName', 'N/A')} ({lead.get('companyIndustry', 'N/A')}, {lead.get('companyEmployees', 'N/A')} emp.)")
            print(f"💼 Cargo        : {lead.get('jobTitle', 'N/A')}")
            print(f"📨 Asunto       : {s}")
            print("-" * 50)
            print(b_full)
            print("-" * 50)
            
        if len(leads) > 3:
            print(f"\n... y {len(leads) - 3} leads adicionales en cola.")
            
        print("\n✨ Previsualización completada con éxito. No se han enviado correos ni modificado datos.")
        sys.exit(0)

    # 4. Confirmation
    est_minutes = round(((delay_min + delay_max) / 2 * (len(leads) - 1)) / 60, 1) if len(leads) > 1 else 0
    print("\n" + "=" * 70)
    print(f"📧 CAMPAÑA DE EMAIL: {args.template}")
    print(f"👥 Total de destinatarios : {len(leads)}")
    print(f"⏱️  Pausa entre envíos     : {delay_min}s - {delay_max}s (Estimado: ~{est_minutes} min)")
    print(f"📤 Remitente               : {config['FROM_NAME']} <{config['FROM_EMAIL']}>")
    print("=" * 70)

    if not args.yes:
        confirm = input("\n¿Deseas iniciar el envío de esta campaña ahora? [s/N]: ").strip().lower()
        if confirm not in ["s", "si", "y", "yes"]:
            print("❌ Envío cancelado por el usuario.")
            sys.exit(0)

    # 5. Execution Loop
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    log_file = LOGS_DIR / f"campaign_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    results = []
    
    print(f"\n🚀 Iniciando envío a {len(leads)} leads...\n")

    for i, lead in enumerate(leads, 1):
        lead_name = f"{lead.get('nameFirstName', '')} {lead.get('nameLastName', '')}".strip()
        lead_email = lead["emailsPrimaryEmail"]
        lead_company = lead.get("companyName", "N/A")

        s = render_content(subject_raw, lead)
        b_rendered = render_content(body_raw, lead)
        b_text = build_full_text(b_rendered)
        b_html = build_full_html(b_rendered)

        print(f"[{i}/{len(leads)}] Enviando a: {lead_name} ({lead_company}) <{lead_email}> ...", end=" ", flush=True)

        try:
            send_email_smtp(config, lead_email, s, b_text, b_html)
            update_crm_after_send(config, lead, args.template, s)
            print("✅ ENVIADO")
            results.append({
                "personId": lead["id"],
                "name": lead_name,
                "email": lead_email,
                "company": lead_company,
                "status": "SENT",
                "subject": s,
                "timestamp": datetime.datetime.now().isoformat()
            })
        except Exception as e:
            print(f"❌ ERROR: {e}")
            results.append({
                "personId": lead["id"],
                "name": lead_name,
                "email": lead_email,
                "company": lead_company,
                "status": "FAILED",
                "error": str(e),
                "timestamp": datetime.datetime.now().isoformat()
            })

        # Sleep between emails except the last one
        if i < len(leads):
            wait_sec = random.randint(delay_min, delay_max)
            print(f"   ⏳ Esperando {wait_sec}s antes del siguiente correo...")
            time.sleep(wait_sec)

    # Save log
    with open(log_file, "w", encoding="utf-8") as f:
        json.dump({
            "template": args.template,
            "total": len(leads),
            "sent": sum(1 for r in results if r["status"] == "SENT"),
            "failed": sum(1 for r in results if r["status"] == "FAILED"),
            "results": results
        }, f, indent=2, ensure_ascii=False)

    sent_count = sum(1 for r in results if r["status"] == "SENT")
    failed_count = sum(1 for r in results if r["status"] == "FAILED")

    print("\n" + "=" * 70)
    print(f"🎉 Campaña finalizada:")
    print(f"   ✅ Enviados con éxito : {sent_count}")
    print(f"   ❌ Fallidos           : {failed_count}")
    print(f"   📄 Registro guardado en: {log_file.relative_to(BASE_DIR.parent.parent)}")
    print("=" * 70 + "\n")

if __name__ == "__main__":
    main()
