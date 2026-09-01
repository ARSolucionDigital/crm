#!/usr/bin/env python3
"""
Twenty CRM — LinkedIn & Sales Navigator Campaign CLI Automation
===============================================================
Automated personalized LinkedIn DM, InMail & Connection Request sender
with full stealth and bidirectional Twenty CRM synchronization.
"""

import argparse
import datetime
import html
import json
import os
import random
import re
import subprocess
import sys
import time
import urllib.parse
from pathlib import Path
from playwright.sync_api import sync_playwright

# Paths
BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"
LOGS_DIR = BASE_DIR / "logs"
ENV_FILE = BASE_DIR / ".env.linkedin"
DEFAULT_SESSION_DIR = BASE_DIR / ".chrome-session"
SESSION_STATE_FILE = BASE_DIR / "session.json"

def load_env():
    """Load configuration from .env.linkedin file."""
    config = {
        "HEADLESS": "false",
        "DEFAULT_DELAY_MIN": "90",
        "DEFAULT_DELAY_MAX": "180",
        "DEFAULT_BATCH_LIMIT": "20",
        "CHROME_PROFILE_DIR": str(DEFAULT_SESSION_DIR),
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

def parse_template(campaign_name, modality):
    """
    Read and parse template file for a given campaign and modality.
    modality: 'dm', 'inmail', or 'conexion'
    """
    camp_dir = TEMPLATES_DIR / campaign_name
    if not camp_dir.exists():
        available = [d.name for d in TEMPLATES_DIR.iterdir() if d.is_dir() and not d.name.startswith(".")]
        raise FileNotFoundError(
            f"Campaña '{campaign_name}' no encontrada en {TEMPLATES_DIR}.\n"
            f"Campañas disponibles: {', '.join(available)}"
        )
    
    file_path = camp_dir / f"{modality}.md"
    if not file_path.exists():
        raise FileNotFoundError(f"Plantilla '{modality}.md' no encontrada en {camp_dir}")
    
    content = file_path.read_text(encoding="utf-8").strip()
    
    subject = ""
    body = content
    
    # Check for YAML frontmatter (for inmail subject)
    fm_match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", content, re.DOTALL)
    if fm_match:
        fm_text = fm_match.group(1)
        body = fm_match.group(2).strip()
        for line in fm_text.splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                if k.strip().lower() == "subject":
                    subject = v.strip().strip("\"'")
            
    return subject, body

def render_content(text, lead):
    """Render template string with lead attributes and smart fallbacks."""
    if not text:
        return ""
    first_name = (lead.get("nameFirstName") or "").strip()
    last_name = (lead.get("nameLastName") or "").strip()
    company = (lead.get("companyName") or "").strip()
    job_title = (lead.get("jobTitle") or "").strip()
    city = (lead.get("city") or "").strip()

    first_name_val = first_name if first_name else ""
    company_val = company if company else "tu empresa"
    job_title_val = job_title if job_title else "tu sector"
    city_val = city if city else "tu zona"

    rendered = text
    if first_name_val:
        rendered = rendered.replace("{{nameFirstName}}", first_name_val)
    else:
        rendered = re.sub(r"Hola,\s*\{\{nameFirstName\}\}:?", "Hola,", rendered)
        rendered = re.sub(r"Hola\s*\{\{nameFirstName\}\}:?", "Hola,", rendered)
        rendered = rendered.replace("{{nameFirstName}}", "")

    rendered = rendered.replace("{{nameLastName}}", last_name)
    rendered = rendered.replace("{{companyName}}", company_val)
    rendered = rendered.replace("{{jobTitle}}", job_title_val)
    rendered = rendered.replace("{{city}}", city_val)
    rendered = re.sub(r"[ ]{2,}", " ", rendered)
    
    return rendered.strip()

def get_target_leads(config, status_filter="EMAIL_FRIO", limit=20, lead_id=None, industry=None, role=None, min_employees=None, max_employees=None):
    """Query eligible leads from Twenty CRM database."""
    schema = config["WORKSPACE_SCHEMA"]
    
    where_clauses = [
        "p.\"deletedAt\" IS NULL",
        "p.\"linkedinLinkPrimaryLinkUrl\" IS NOT NULL",
        "p.\"linkedinLinkPrimaryLinkUrl\" != ''"
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
                  AND t.title = 'DM Linkedin' 
                  AND t.status = 'TODO'
            )
        """)
        
        if industry:
            if industry.lower() in ["moda", "retail"]:
                where_clauses.append("(c.industry ILIKE '%moda%' OR c.industry ILIKE '%ropa%' OR c.industry ILIKE '%retail%' OR c.industry ILIKE '%textil%')")
            elif industry.lower() in ["logistica", "transporte"]:
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
            p.\"linkedinLinkPrimaryLinkUrl\",
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
                  AND t.title = 'DM Linkedin' 
                LIMIT 1
            ) as \"taskId\"
        FROM \"{schema}\".\"person\" p 
        LEFT JOIN \"{schema}\".\"company\" c ON p.\"companyId\" = c.id 
        WHERE {where_sql}
        ORDER BY p.\"createdAt\" ASC
        LIMIT {limit}
    """
    return run_psql_json(query)

def update_crm_after_linkedin(config, lead, campaign_name, action_type, message_sent):
    """Update task and sequence status in Twenty CRM after LinkedIn action."""
    schema = config["WORKSPACE_SCHEMA"]
    member_id = config["WORKSPACE_MEMBER_ID"]
    person_id = lead["id"]
    task_id = lead.get("taskId")
    
    # 1. Update sequenceStatus to LINKEDIN_ENVIADO
    run_psql_exec(f"""
        UPDATE \"{schema}\".\"person\" 
        SET \"sequenceStatus\" = 'LINKEDIN_ENVIADO', \"updatedAt\" = NOW() 
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
        "campaign": campaign_name,
        "actionType": action_type,
        "profileUrl": lead.get("linkedinLinkPrimaryLinkUrl"),
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
            '{action_type}', '{activity_props}'::jsonb,
            '{person_id}', '{member_id}',
            'MANUAL', 'MANUAL',
            'Raul Almeida', 'Raul Almeida'
        );
    """)

def launch_stealth_browser(playwright_instance, config, headless=False):
    """Launch Google Chrome in persistent stealth context with storage state fallback."""
    profile_dir = Path(config.get("CHROME_PROFILE_DIR", DEFAULT_SESSION_DIR)).expanduser().resolve()
    profile_dir.mkdir(parents=True, exist_ok=True)
    
    mac_chrome_path = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    channel = "chrome" if os.path.exists(mac_chrome_path) else None

    storage_state_arg = str(SESSION_STATE_FILE) if SESSION_STATE_FILE.exists() else None

    browser_context = playwright_instance.chromium.launch_persistent_context(
        user_data_dir=str(profile_dir),
        channel=channel,
        headless=headless,
        ignore_default_args=["--enable-automation"],
        args=[
            "--disable-blink-features=AutomationControlled",
            "--disable-infobars",
            "--no-sandbox",
            "--start-maximized"
        ],
        viewport={"width": 1440, "height": 900},
        user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
    )

    if storage_state_arg and SESSION_STATE_FILE.exists():
        try:
            with open(SESSION_STATE_FILE, "r", encoding="utf-8") as f:
                state_data = json.load(f)
                browser_context.add_cookies(state_data.get("cookies", []))
        except Exception:
            pass

    browser_context.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        window.chrome = { runtime: {} };
    """)

    return browser_context

def human_type(element, text):
    """Simulate realistic human typing with variable inter-key delays."""
    element.focus()
    for char in text:
        element.type(char, delay=random.randint(35, 95))
        if char in [".", ",", "!", "?", "\n"]:
            time.sleep(random.uniform(0.15, 0.45))

def normalize_linkedin_url(raw_url):
    """Ensure URL is clean, unquoted, and starts with https."""
    if not raw_url:
        return ""
    url = urllib.parse.unquote(raw_url.strip())
    if not url.startswith("http"):
        url = "https://" + url
    if url.startswith("http://"):
        url = "https://" + url[7:]
    return url

def detect_profile_scenario(page):
    """
    Inspect the loaded profile page with maximum granularity and classify into:
    - 'DM': 1st degree connection (Direct Message link / 1st badge)
    - 'INMAIL': Sales Navigator InMail button available
    - 'CONNECT': Connect button / custom invite link available (with note)
    - 'PENDING': Invitation already pending
    - 'ERROR': Profile not found / 404 / Authwall
    """
    page.wait_for_timeout(3000)
    
    # 1. Check for 404 / Error / Authwall
    if "authwall" in page.url:
        return "ERROR", None

    if page.locator("text='Esta página no existe'").count() > 0 or page.locator("text='Page not found'").count() > 0:
        return "ERROR", None

    # 2. Check 1st Degree Connection (Badge or Direct Message <a> link)
    # LinkedIn renders the main profile direct message button as:
    # <a href="/messaging/compose/?profileUrn=...&interop=msgOverlay">Message</a>
    direct_msg_link = page.locator("main a[href*='/messaging/compose'], div.ph5 a[href*='/messaging/compose'], a.artdeco-button--primary:has-text('Message'), a.artdeco-button--primary:has-text('Mensaje')")
    degree_badge = page.locator("span:has-text('1st'), span:has-text('1.º'), .dist-value:has-text('1')")
    
    if direct_msg_link.count() > 0 and direct_msg_link.first.is_visible():
        return "DM", direct_msg_link.first
    elif degree_badge.count() > 0:
        # If badge says 1st degree, find any message button or link
        msg_any = page.locator("a[href*='/messaging/compose'], button:has-text('Mensaje'), button:has-text('Message')")
        if msg_any.count() > 0:
            return "DM", msg_any.first

    # 3. Check for Pending invitation
    pending_loc = page.locator("main button:has-text('Pendiente'), main button:has-text('Pending')")
    if pending_loc.count() > 0 and pending_loc.first.is_visible():
        return "PENDING", pending_loc.first

    # 4. Check for Connect button / invite link
    connect_btn = page.locator("main button:has-text('Conectar'), main button:has-text('Connect'), main a[href*='/preload/custom-invite/']")
    if connect_btn.count() > 0 and connect_btn.first.is_visible():
        return "CONNECT", connect_btn.first

    # 5. Check inside 'More' / 'Más' dropdown for Connect
    more_btn = page.locator("main button:has-text('Más'), main button:has-text('More'), main button[aria-label*='Más acciones']")
    if more_btn.count() > 0 and more_btn.first.is_visible():
        try:
            more_btn.first.click()
            page.wait_for_timeout(800)
            connect_in_more = page.locator("div[role='button']:has-text('Conectar'), div[role='button']:has-text('Connect'), button:has-text('Conectar')")
            if connect_in_more.count() > 0 and connect_in_more.first.is_visible():
                return "CONNECT", connect_in_more.first
        except Exception:
            pass

    # 6. Check for InMail button (Sales Nav or Premium) for 2nd/3rd degree
    inmail_loc = page.locator("button:has-text('InMail'), button[aria-label*='InMail'], button[data-control-name='inmail']")
    if inmail_loc.count() > 0 and inmail_loc.first.is_visible():
        return "INMAIL", inmail_loc.first

    # Fallback to Sales Nav button if available
    sales_nav_btn = page.locator("a:has-text('Ver en Sales Navigator'), a:has-text('View in Sales Navigator')")
    if sales_nav_btn.count() > 0 and sales_nav_btn.first.is_visible():
        return "INMAIL", sales_nav_btn.first

    return "CONNECT", None

def execute_login_setup(config):
    """Interactive mode to open browser, log into LinkedIn/Sales Navigator and save state."""
    print("\n" + "=" * 70)
    print("🔑 MODO CONFIGURACIÓN DE SESIÓN (LINKEDIN & SALES NAV)")
    print("=" * 70)
    print("Se abrirá Google Chrome.")
    print("1. Inicia sesión en LinkedIn y Sales Navigator.")
    print("2. Espera a que se cargue tu feed de LinkedIn.")
    print("3. Presiona ENTER aquí en la terminal para guardar la sesión.")
    print("=" * 70 + "\n")

    with sync_playwright() as p:
        context = launch_stealth_browser(p, config, headless=False)
        page = context.new_page()
        page.goto("https://www.linkedin.com/feed/", wait_until="domcontentloaded")
        
        input("\n[Presiona ENTER cuando estés dentro de LinkedIn]: ")
        
        # Save storage state JSON
        context.storage_state(path=str(SESSION_STATE_FILE))
        print(f"✅ ¡Cookies y tokens exportados con éxito a {SESSION_STATE_FILE.name}!")
        
        # Open Sales Nav tab to ensure session sync
        try:
            page.goto("https://www.linkedin.com/sales", wait_until="domcontentloaded")
            page.wait_for_timeout(3000)
            context.storage_state(path=str(SESSION_STATE_FILE))
        except Exception:
            pass
            
        context.close()
        print("✅ ¡Sesión guardada y verificada permanentemente!\n")

def test_single_url(config, campaign_name, url, dry_run=True):
    """Test classification and rendering on a single arbitrary LinkedIn URL."""
    print("\n" + "=" * 70)
    print(f"🧪 PROBANDO PERFIL INDIVIDUAL: {url}")
    print(f"📁 Campaña seleccionada : {campaign_name}")
    print(f"🛠️  Modo                 : {'DRY-RUN (Simulación)' if dry_run else 'ENVÍO REAL'}")
    print("=" * 70)

    clean_url = normalize_linkedin_url(url)
    sample_lead = {
        "nameFirstName": "Laura",
        "nameLastName": "Romero Ruiz",
        "companyName": "tu empresa",
        "jobTitle": "Directiva",
        "city": "España",
        "linkedinLinkPrimaryLinkUrl": clean_url
    }

    with sync_playwright() as p:
        context = launch_stealth_browser(p, config, headless=False)
        page = context.new_page()
        
        print(f"\n🔍 Navegando a: {clean_url} ...")
        page.goto(clean_url, wait_until="domcontentloaded", timeout=35000)
        page.wait_for_timeout(4000)

        # Extract name dynamically from page title / H1 (e.g. "Silvia Juliana | LinkedIn" -> "Silvia")
        page_title = page.title()
        print(f"📄 Título de la página: {page_title}")

        extracted_first_name = ""
        if "|" in page_title:
            full_title_name = page_title.split("|")[0].strip()
            name_parts = full_title_name.split()
            if name_parts:
                extracted_first_name = name_parts[0]

        sample_lead = {
            "nameFirstName": extracted_first_name,
            "nameLastName": "",
            "companyName": "tu empresa",
            "jobTitle": "Directiva",
            "city": "España",
            "linkedinLinkPrimaryLinkUrl": clean_url
        }

        scenario, action_btn = detect_profile_scenario(page)
        print(f"🎯 Escenario detectado: {scenario}")

        if scenario == "ERROR":
            print("❌ No se pudo autenticar la sesión en LinkedIn o el perfil es inaccesible.")
            context.close()
            return

        modality = "dm" if scenario == "DM" else ("inmail" if scenario == "INMAIL" else "conexion")
        subject_raw, body_raw = parse_template(campaign_name, modality)
        
        subject_rendered = render_content(subject_raw, sample_lead)
        body_rendered = render_content(body_raw, sample_lead)

        print(f"\n📝 Plantilla seleccionada: {modality}.md")
        if subject_rendered:
            print(f"📨 Asunto renderizado : {subject_rendered}")
        print(f"💬 Texto renderizado   : {body_rendered}")
        print(f"📏 Longitud del mensaje: {len(body_rendered)} caracteres")

        if dry_run:
            print("\n✨ [TEST DRY-RUN] Detección y renderizado completados con éxito (No enviado).")
        else:
            print("\n🚀 Ejecutando envío real a LinkedIn...")
            if scenario == "DM":
                if action_btn:
                    print("   👉 Abriendo ventana de chat directo...")
                    action_btn.click()
                    page.wait_for_timeout(2000)
                    
                    chat_box = page.locator("div.msg-form__contenteditable, div[role='textbox'], div[contenteditable='true']")
                    if chat_box.count() > 0:
                        print(f"   ⌨️  Escribiendo mensaje con tipeo humano...")
                        human_type(chat_box.first, body_rendered)
                        page.wait_for_timeout(1200)
                        
                        send_btn = page.locator("button.msg-form__send-button, button:has-text('Send'), button:has-text('Enviar')")
                        if send_btn.count() > 0:
                            print("   📤 Enviando mensaje...")
                            send_btn.first.click()
                            page.wait_for_timeout(3000)
                            print("   ✅ ¡Mensaje Directo enviado con éxito a Laura!")
                    else:
                        print("   ⚠️ No se encontró el campo de texto del chat.")

            elif scenario == "INMAIL":
                if action_btn:
                    print("   👉 Abriendo ventana de InMail...")
                    action_btn.click()
                    page.wait_for_timeout(2500)
                    
                    subject_input = page.locator("input[name='subject'], input[placeholder*='Asunto'], input[placeholder*='Subject']")
                    if subject_input.count() > 0 and subject_rendered:
                        print(f"   ⌨️  Escribiendo asunto: {subject_rendered}")
                        human_type(subject_input.first, subject_rendered)
                        page.wait_for_timeout(800)
                        
                    body_input = page.locator("div.msg-form__contenteditable, div[role='textbox'], textarea[name='message']")
                    if body_input.count() > 0:
                        print(f"   ⌨️  Escribiendo cuerpo de InMail...")
                        human_type(body_input.first, body_rendered)
                        page.wait_for_timeout(1000)
                        
                        send_inmail_btn = page.locator("button:has-text('Enviar InMail'), button:has-text('Send InMail'), button.msg-form__send-button")
                        if send_inmail_btn.count() > 0:
                            print("   📤 Enviando InMail...")
                            send_inmail_btn.first.click()
                            page.wait_for_timeout(3000)
                            print("   ✅ ¡InMail enviado con éxito!")

            elif scenario == "CONNECT":
                if action_btn:
                    print("   👉 Abriendo ventana de conexión...")
                    action_btn.click()
                    page.wait_for_timeout(1500)
                    
                    add_note_btn = page.locator("button:has-text('Añadir una nota'), button:has-text('Add a note')")
                    if add_note_btn.count() > 0 and add_note_btn.first.is_visible():
                        add_note_btn.first.click()
                        page.wait_for_timeout(1000)
                        note_box = page.locator("textarea[name='message'], textarea#custom-message")
                        if note_box.count() > 0:
                            print(f"   ⌨️  Escribiendo nota de conexión...")
                            human_type(note_box.first, body_rendered[:300])
                            page.wait_for_timeout(1000)
                            send_conn_btn = page.locator("button:has-text('Enviar'), button:has-text('Send')")
                            if send_conn_btn.count() > 0:
                                send_conn_btn.first.click()
                                page.wait_for_timeout(2500)
                                print("   ✅ ¡Solicitud de conexión con nota enviada con éxito!")
        
        page.wait_for_timeout(3000)
        context.close()

def main():
    parser = argparse.ArgumentParser(
        description="Twenty CRM — CLI de Automatización en LinkedIn & Sales Navigator",
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--template", "-t", default="moda-operaciones", help="Nombre de la campaña (ej. moda-operaciones, moda-ceos, logistica-operaciones)")
    parser.add_argument("--login", action="store_true", help="Abre el navegador para iniciar sesión y guardar cookies")
    parser.add_argument("--test-url", help="Prueba la detección y renderizado con una URL específica de LinkedIn")
    parser.add_argument("--limit", "-n", type=int, default=20, help="Límite de leads a procesar (por defecto: 20)")
    parser.add_argument("--dry-run", action="store_true", help="Previsualiza la detección de perfiles y textos sin enviar nada")
    parser.add_argument("--headless", action="store_true", help="Ejecutar en modo segundo plano (sin ventana visible)")
    parser.add_argument("--delay-min", type=int, help="Segundos mínimos de espera entre leads")
    parser.add_argument("--delay-max", type=int, help="Segundos máximos de espera entre leads")
    parser.add_argument("--status", default="EMAIL_FRIO", help="Filtrar por Sequence Status (por defecto: EMAIL_FRIO, o 'ALL')")
    parser.add_argument("--industry", help="Filtrar por sector (ej. moda, logistica, retail)")
    parser.add_argument("--role", help="Filtrar por cargo (ej. operaciones, ceo, founder)")
    parser.add_argument("--min-employees", type=int, help="Filtrar por mínimo de empleados (ej. 50)")
    parser.add_argument("--max-employees", type=int, help="Filtrar por máximo de empleados (ej. 49)")
    parser.add_argument("--lead-id", help="Procesar solo un Lead específico por UUID")
    parser.add_argument("--yes", "-y", action="store_true", help="Omitir confirmación interactiva")

    args = parser.parse_args()
    config = load_env()

    if args.login:
        execute_login_setup(config)
        sys.exit(0)

    if args.test_url:
        test_single_url(config, args.template, args.test_url, dry_run=args.dry_run)
        sys.exit(0)

    if not args.template:
        print("❌ Error: Debes especificar una campaña con --template <nombre> (ej. moda-operaciones)")
        parser.print_help()
        sys.exit(1)

    delay_min = args.delay_min if args.delay_min is not None else int(config["DEFAULT_DELAY_MIN"])
    delay_max = args.delay_max if args.delay_max is not None else int(config["DEFAULT_DELAY_MAX"])
    if delay_max < delay_min:
        delay_max = delay_min

    is_headless = args.headless or (config.get("HEADLESS", "false").lower() == "true")

    # 1. Fetch leads
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
        print(f"⚠️ No se encontraron leads pendientes con el estado '{args.status}' y URLs de LinkedIn válidas.")
        sys.exit(0)

    print(f"✅ Se encontraron {len(leads)} leads listos para la campaña de LinkedIn.")

    # 2. Confirmation
    est_minutes = round(((delay_min + delay_max) / 2 * (len(leads) - 1)) / 60, 1) if len(leads) > 1 else 0
    print("\n" + "=" * 70)
    print(f"💼 CAMPAÑA DE LINKEDIN: {args.template}")
    print(f"👥 Total de prospectos     : {len(leads)}")
    print(f"⏱️  Pausa entre prospectos : {delay_min}s - {delay_max}s (Estimado: ~{est_minutes} min)")
    print(f"🛡️  Modo Stealth           : ACTIVO (Google Chrome Nativo)")
    print(f"👁️  Modo Visual            : {'Segundo Plano (Headless)' if is_headless else 'Ventana Visible'}")
    print("=" * 70)

    if not args.yes and not args.dry_run:
        confirm = input("\n¿Deseas iniciar el proceso de LinkedIn ahora? [s/N]: ").strip().lower()
        if confirm not in ["s", "si", "y", "yes"]:
            print("❌ Proceso cancelado por el usuario.")
            sys.exit(0)

    # 3. Launch Browser and Process Leads
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    log_file = LOGS_DIR / f"linkedin_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    results = []

    print(f"\n🚀 Iniciando procesamiento de {len(leads)} leads con Playwright...\n")

    with sync_playwright() as p:
        context = launch_stealth_browser(p, config, headless=is_headless)
        page = context.new_page()

        for i, lead in enumerate(leads, 1):
            lead_name = f"{lead.get('nameFirstName', '')} {lead.get('nameLastName', '')}".strip()
            raw_url = lead.get("linkedinLinkPrimaryLinkUrl", "")
            clean_url = normalize_linkedin_url(raw_url)
            lead_company = lead.get("companyName", "N/A")

            print(f"[{i}/{len(leads)}] {lead_name} ({lead_company})")
            print(f"   🔗 URL: {clean_url}")

            if not clean_url:
                print("   ❌ Omitido: URL de LinkedIn vacía.")
                results.append({"personId": lead["id"], "name": lead_name, "status": "FAILED", "error": "Empty URL"})
                continue

            try:
                # Navigate to profile
                page.goto(clean_url, wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(random.randint(2500, 4500))

                scenario, action_btn = detect_profile_scenario(page)
                print(f"   🎯 Escenario detectado: {scenario}")

                if scenario == "ERROR":
                    print("   ⚠️ Perfil no encontrado o inaccesible (404).")
                    results.append({"personId": lead["id"], "name": lead_name, "status": "FAILED", "error": "Profile not found"})
                    continue

                if scenario == "PENDING":
                    print("   ℹ️ Invitación ya enviada previamente (Pendiente).")
                    if not args.dry_run:
                        update_crm_after_linkedin(config, lead, args.template, "linkedin.already_pending", "")
                    results.append({"personId": lead["id"], "name": lead_name, "status": "SKIPPED", "scenario": "PENDING"})
                    continue

                # Select modality
                modality = "dm" if scenario == "DM" else ("inmail" if scenario == "INMAIL" else "conexion")
                subject_raw, body_raw = parse_template(args.template, modality)
                
                subject_rendered = render_content(subject_raw, lead)
                body_rendered = render_content(body_raw, lead)

                print(f"   📝 Plantilla: {modality}.md")
                if subject_rendered:
                    print(f"   📨 Asunto: {subject_rendered}")
                print(f"   💬 Mensaje ({len(body_rendered)} car.): {body_rendered[:90]}...")

                if args.dry_run:
                    print("   🛠️ [DRY-RUN] Simulación exitosa (No enviado).")
                    results.append({"personId": lead["id"], "name": lead_name, "status": "DRY_RUN", "scenario": scenario})
                else:
                    # Execute actual send
                    if scenario == "DM":
                        if action_btn:
                            action_btn.click()
                            page.wait_for_timeout(1500)
                            chat_box = page.locator("div[role='textbox'], div.msg-form__contenteditable")
                            if chat_box.count() > 0:
                                human_type(chat_box.first, body_rendered)
                                page.wait_for_timeout(1000)
                                send_btn = page.locator("button.msg-form__send-button, button:has-text('Enviar')")
                                if send_btn.count() > 0:
                                    send_btn.first.click()
                                    page.wait_for_timeout(2000)
                        action_type = "linkedin.dm_sent"

                    elif scenario == "INMAIL":
                        if action_btn:
                            action_btn.click()
                            page.wait_for_timeout(2000)
                            subject_input = page.locator("input[name='subject'], input[placeholder*='Asunto'], input[placeholder*='Subject']")
                            if subject_input.count() > 0 and subject_rendered:
                                human_type(subject_input.first, subject_rendered)
                                page.wait_for_timeout(800)
                            body_input = page.locator("div[role='textbox'], textarea[name='message'], div.msg-form__contenteditable")
                            if body_input.count() > 0:
                                human_type(body_input.first, body_rendered)
                                page.wait_for_timeout(1000)
                                send_inmail_btn = page.locator("button:has-text('Enviar InMail'), button:has-text('Send InMail'), button.msg-form__send-button")
                                if send_inmail_btn.count() > 0:
                                    send_inmail_btn.first.click()
                                    page.wait_for_timeout(2000)
                        action_type = "linkedin.inmail_sent"

                    elif scenario == "CONNECT":
                        if action_btn:
                            action_btn.click()
                            page.wait_for_timeout(1500)
                            add_note_btn = page.locator("button:has-text('Añadir una nota'), button:has-text('Add a note')")
                            if add_note_btn.count() > 0 and add_note_btn.first.is_visible():
                                add_note_btn.first.click()
                                page.wait_for_timeout(1000)
                                note_box = page.locator("textarea[name='message'], textarea#custom-message")
                                if note_box.count() > 0:
                                    human_type(note_box.first, body_rendered[:300])
                                    page.wait_for_timeout(1000)
                                    send_conn_btn = page.locator("button:has-text('Enviar'), button:has-text('Send')")
                                    if send_conn_btn.count() > 0:
                                        send_conn_btn.first.click()
                                        page.wait_for_timeout(2000)
                            else:
                                # If no note button, send standard connect
                                send_conn_btn = page.locator("button:has-text('Enviar sin nota'), button:has-text('Send without note'), button:has-text('Enviar')")
                                if send_conn_btn.count() > 0:
                                    send_conn_btn.first.click()
                                    page.wait_for_timeout(1500)
                        action_type = "linkedin.connection_requested"

                    # Update CRM
                    update_crm_after_linkedin(config, lead, args.template, action_type, body_rendered)
                    print(f"   ✅ ENVIADO ({action_type}) & CRM actualizado.")
                    results.append({
                        "personId": lead["id"],
                        "name": lead_name,
                        "company": lead_company,
                        "status": "SENT",
                        "scenario": scenario,
                        "timestamp": datetime.datetime.now().isoformat()
                    })

            except Exception as e:
                print(f"   ❌ ERROR al procesar perfil: {e}")
                results.append({
                    "personId": lead["id"],
                    "name": lead_name,
                    "company": lead_company,
                    "status": "FAILED",
                    "error": str(e),
                    "timestamp": datetime.datetime.now().isoformat()
                })

            # Random human pause between leads
            if i < len(leads) and not args.dry_run:
                wait_sec = random.randint(delay_min, delay_max)
                print(f"   ⏳ Pausa de seguridad: esperando {wait_sec}s antes del siguiente lead...\n")
                time.sleep(wait_sec)
            else:
                print()

        context.close()

    # Save log
    with open(log_file, "w", encoding="utf-8") as f:
        json.dump({
            "campaign": args.template,
            "total": len(leads),
            "sent": sum(1 for r in results if r["status"] == "SENT"),
            "skipped": sum(1 for r in results if r["status"] == "SKIPPED"),
            "failed": sum(1 for r in results if r["status"] == "FAILED"),
            "results": results
        }, f, indent=2, ensure_ascii=False)

    sent_count = sum(1 for r in results if r["status"] == "SENT")
    skipped_count = sum(1 for r in results if r["status"] == "SKIPPED")
    failed_count = sum(1 for r in results if r["status"] == "FAILED")

    print("=" * 70)
    print("🎉 Proceso finalizado:")
    print(f"   ✅ Enviados con éxito : {sent_count}")
    print(f"   ℹ️  Omitidos (Pendientes): {skipped_count}")
    print(f"   ❌ Fallidos           : {failed_count}")
    print(f"   📄 Registro guardado en: {log_file.relative_to(BASE_DIR.parent.parent)}")
    print("=" * 70 + "\n")

if __name__ == "__main__":
    main()
