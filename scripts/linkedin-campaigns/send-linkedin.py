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
import unicodedata
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

def human_type(element, text, force_click=False):
    """Simulate realistic human typing with variable inter-key delays."""
    element.click(force=force_click)
    for char in text:
        element.type(char, delay=random.randint(35, 85))
        if char in [".", ",", "!", "?", "\n"]:
            time.sleep(random.uniform(0.12, 0.30))

def close_chat_overlays(page):
    """Close or minimize any open floating chat bubbles from previous leads."""
    try:
        close_btns = page.locator("aside.msg-overlay-container button[data-control-name='overlay.close_conversation_window'], aside.msg-overlay-container button[aria-label*='Close conversation'], aside.msg-overlay-container button[aria-label*='Cerrar'], button:has(svg[data-test-icon='close-small'])")
        for i in range(close_btns.count()):
            if close_btns.nth(i).is_visible():
                close_btns.nth(i).click()
                page.wait_for_timeout(250)
    except Exception:
        pass

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
    Inspect profile page with strategic InMail priority:
    1. 1st Degree Connection -> 'DM' (Free direct chat via dm.md)
    2. Non-Connection (2nd/3rd Degree) -> 'INMAIL' (Prioritized InMail via inmail.md using Sales Nav credits)
    3. Fallback (If InMail restricted) -> 'CONNECT' (Connection request with note via conexion.md)
    4. Pending without InMail -> 'PENDING'
    5. Error / Authwall -> 'ERROR'
    """
    page.wait_for_timeout(3000)
    
    # 1. Check for 404 / Error / Authwall
    if "authwall" in page.url:
        return "ERROR", None

    if page.locator("text='Esta página no existe'").count() > 0 or page.locator("text='Page not found'").count() > 0:
        return "ERROR", None

    # 2. Check 1st Degree Connection (Strictly in profile top card)
    top_card = page.locator("main section").first
    top_badges = top_card.locator("span.dist-value, span:has-text('1st'), span:has-text('1.º')").all_text_contents()
    is_1st_degree = any(('1st' in b or '1.º' in b) for b in top_badges if b.strip())
    
    if is_1st_degree:
        direct_msg_link = top_card.locator("a[href*='/messaging/compose'], a:has-text('Message'), a:has-text('Mensaje'), button:has-text('Message'), button:has-text('Mensaje')")
        if direct_msg_link.count() > 0:
            return "DM", direct_msg_link.first

    # 3. For 2nd/3rd Degree: Prioritize INMAIL (Using available InMail credits)
    # Check for direct InMail / Sales Nav buttons in top card
    inmail_direct = top_card.locator(
        "button:has-text('InMail'), button[data-control-name='inmail'], "
        "button[aria-label*='InMail'], button[title*='InMail'], "
        "a[aria-label*='InMail'], a[title*='InMail']"
    )
    if inmail_direct.count() > 0 and inmail_direct.first.is_visible():
        return "INMAIL", inmail_direct.first

    # LinkedIn's non-connection Message action opens the InMail composer.
    message_compose_link = top_card.locator("a[href*='/messaging/compose']")
    if message_compose_link.count() > 0 and message_compose_link.first.is_visible():
        return "INMAIL", message_compose_link.first

    # Check inside 'More' / 'Más' dropdown for InMail / Sales Navigator
    more_btn = page.locator("main button[aria-label*='More'], main button[aria-label*='Más'], main button:has-text('More'), main button:has-text('Más')")
    if more_btn.count() > 0 and more_btn.first.is_visible():
        try:
            more_btn.first.click()
            page.wait_for_timeout(800)
            
            inmail_in_more = page.locator("div[role='button']:has-text('InMail'), [role='menuitem']:has-text('InMail')")
            if inmail_in_more.count() > 0 and inmail_in_more.first.is_visible():
                return "INMAIL", inmail_in_more.first
        except Exception:
            pass

    # 4. Connection requests are intentionally disabled for this campaign.
    connect_btn = page.locator("main button:has-text('Conectar'), main button:has-text('Connect'), main a[href*='/preload/custom-invite/']")
    if connect_btn.count() > 0 and connect_btn.first.is_visible():
        return "INMAIL", None

    # Check inside 'More' dropdown for Connect
    if more_btn.count() > 0 and more_btn.first.is_visible():
        try:
            connect_in_more = page.locator("div[role='button']:has-text('Connect'), div[role='button']:has-text('Conectar'), [role='menuitem']:has-text('Connect'), [role='menuitem']:has-text('Conectar'), button:has-text('Conectar'), button:has-text('Connect')")
            if connect_in_more.count() > 0 and connect_in_more.first.is_visible():
                return "INMAIL", None
        except Exception:
            pass

    # 5. Check if already Pending
    pending_loc = page.locator("main button:has-text('Pendiente'), main button:has-text('Pending'), div[role='button']:has-text('Pending'), [role='menuitem']:has-text('Pending')")
    if pending_loc.count() > 0:
        return "PENDING", None

    # Never send a connection request when the profile is not a first-degree
    # contact unless LinkedIn explicitly exposed a usable InMail action.
    return "INMAIL", None

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

def confirm_inmail_sent(page, body_input):
    """Confirm that LinkedIn closed the compose form or displayed a send notice."""
    page.wait_for_timeout(3000)
    confirmation_text = " ".join(
        page.locator(
            "[role='alert'], .artdeco-toast-item, "
            ".msg-form__sent-message, .msg-s-message-list__event"
        ).all_text_contents()
    ).lower()
    page_text = page.locator("body").inner_text().lower()
    if any(
        token in confirmation_text
        for token in [
            "sent",
            "enviado",
            "enviada",
            "message sent",
            "message was sent",
            "your message",
            "mensaje enviado",
        ]
    ):
        return True
    if "awaiting reply from" in page_text and "new inmail" in page_text:
        return True
    if not body_input.is_visible():
        return True
    subject_inputs = page.locator(
        "input[aria-label='Subject (required)']:visible, "
        "input[aria-label='Asunto (obligatorio)']:visible"
    )
    return subject_inputs.count() == 0

def normalize_search_text(value):
    """Normalize names for matching CRM values against LinkedIn labels."""
    return "".join(
        character for character in unicodedata.normalize("NFKD", value.lower())
        if not unicodedata.combining(character)
    )

def open_sales_navigator_inmail(page, lead):
    """Open the real InMail composer from the matching Sales Navigator lead."""
    lead_name = " ".join(
        value for value in [
            (lead.get("nameFirstName") or "").strip(),
            (lead.get("nameLastName") or "").strip(),
        ] if value
    )
    if not lead_name:
        raise RuntimeError("El lead no tiene nombre para buscarlo en Sales Navigator.")

    normalized_lead_name = normalize_search_text(lead_name)
    matching_link = None
    search_queries = [lead_name]
    profile_slug = urllib.parse.urlparse(
        normalize_linkedin_url(lead.get("linkedinLinkPrimaryLinkUrl", ""))
    ).path.strip("/").split("/")[-1]
    if profile_slug:
        search_queries.append(profile_slug)

    for search_query in search_queries:
        search_url = (
            "https://www.linkedin.com/sales/search/people?keywords="
            + urllib.parse.quote(search_query)
        )
        page.goto(search_url, wait_until="domcontentloaded", timeout=35000)
        page.wait_for_timeout(5000)
        result_links = page.locator("a[data-lead-search-result^='profile-link-']")
        for index in range(result_links.count()):
            candidate = result_links.nth(index)
            candidate_name = normalize_search_text(candidate.inner_text().strip())
            candidate_href = normalize_search_text(candidate.get_attribute("href") or "")
            compact_candidate_name = candidate_name.replace(" ", "")
            if (
                candidate_name == normalized_lead_name
                or (profile_slug and profile_slug in candidate_href)
                or (profile_slug and compact_candidate_name in profile_slug)
            ):
                matching_link = candidate
                break
        if matching_link is not None:
            break

        # CRM names can be abbreviated or omit middle names; use the strongest
        # token match only after exact and profile-slug matches fail.
        lead_tokens = {
            token for token in normalized_lead_name.split() if len(token) > 1
        }
        best_match = None
        best_score = 1
        for index in range(result_links.count()):
            candidate = result_links.nth(index)
            candidate_tokens = set(normalize_search_text(candidate.inner_text()).split())
            score = len(lead_tokens & candidate_tokens)
            if score > best_score:
                best_score = score
                best_match = candidate
        if best_match is not None and best_score >= 2:
            matching_link = best_match
            break
    if matching_link is None:
        raise RuntimeError(f"No se encontró '{lead_name}' en Sales Navigator.")

    matching_link.click()
    inmail_button = page.locator("[data-anchor-send-inmail]:visible").last
    try:
        inmail_button.wait_for(state="visible", timeout=10000)
    except Exception as error:
        raise RuntimeError(
            f"La ficha de '{lead_name}' no ofrece un botón InMail en Sales Navigator."
        ) from error

    inmail_button.click()
    page.wait_for_timeout(1500)

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
                    close_chat_overlays(page)
                    print("   👉 Abriendo ventana de InMail...")
                    action_btn.click()
                    page.wait_for_timeout(2500)
                    
                    subject_inputs = page.locator("input[name='subject'], input[placeholder*='Asunto'], input[placeholder*='Subject'], input.msg-form__subject")
                    if subject_inputs.count() > 0 and subject_rendered:
                        print(f"   ⌨️  Escribiendo asunto: {subject_rendered}")
                        target_subject = subject_inputs.last
                        target_subject.click()
                        human_type(target_subject, subject_rendered)
                        page.wait_for_timeout(800)
                        
                    body_inputs = page.locator("div.msg-form__contenteditable, div[role='textbox'], div[contenteditable='true'], textarea[name='message']")
                    if body_inputs.count() > 0:
                        print(f"   ⌨️  Escribiendo cuerpo de InMail...")
                        target_body = body_inputs.last
                        target_body.click()
                        human_type(target_body, body_rendered, force_click=True)
                        page.wait_for_timeout(1000)
                        
                        send_inmail_btns = page.locator("button.msg-form__send-button, button:has-text('Send InMail'), button:has-text('Enviar InMail'), button:has-text('Send'), button:has-text('Enviar')")
                        if send_inmail_btns.count() > 0:
                            target_send = send_inmail_btns.last
                            if not target_send.is_disabled():
                                print("   📤 Enviando InMail...")
                                target_send.click()
                                page.wait_for_timeout(3000)
                                print("   ✅ ¡InMail enviado con éxito!")
                    close_chat_overlays(page)

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

                if scenario in {"NO_INMAIL", "CONNECT"}:
                    print("   ⚠️ No hay InMail utilizable; no se enviará una solicitud de conexión.")
                    results.append({"personId": lead["id"], "name": lead_name, "status": "SKIPPED", "scenario": scenario})
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
                            close_chat_overlays(page)
                            action_btn.click()
                            page.wait_for_timeout(2500)
                            
                            chat_boxes = page.locator("div.msg-form__contenteditable, div[role='textbox'], div[contenteditable='true']")
                            if chat_boxes.count() > 0:
                                target_box = chat_boxes.last
                                target_box.click()
                                page.wait_for_timeout(500)
                                human_type(target_box, body_rendered)
                                page.wait_for_timeout(1000)
                                
                                send_buttons = page.locator("button.msg-form__send-button, button[type='submit']:has-text('Send'), button:has-text('Enviar')")
                                if send_buttons.count() > 0:
                                    target_send = send_buttons.last
                                    if not target_send.is_disabled():
                                        target_send.click()
                                        page.wait_for_timeout(3000)
                            close_chat_overlays(page)
                        action_type = "linkedin.dm_sent"

                    elif scenario == "INMAIL":
                        close_chat_overlays(page)
                        open_sales_navigator_inmail(page, lead)

                        subject_inputs = page.locator(
                            "input[name='subject']:visible, "
                            "input[aria-label='Subject (required)']:visible, "
                            "input[aria-label='Asunto (obligatorio)']:visible, "
                            "input[placeholder*='Asunto']:visible, "
                            "input[placeholder*='Subject']:visible, "
                            "input.msg-form__subject:visible"
                        )
                        if not subject_rendered:
                            raise RuntimeError("La plantilla de InMail no contiene asunto.")
                        try:
                            subject_inputs.first.wait_for(state="visible", timeout=10000)
                        except Exception as error:
                            raise RuntimeError(
                                "No se abrió el formulario de InMail o falta el asunto."
                            ) from error
                        if subject_inputs.count() == 0:
                            raise RuntimeError("No se abrió el formulario de InMail o falta el asunto.")
                        target_subject = subject_inputs.last
                        target_subject.click()
                        human_type(target_subject, subject_rendered)
                        page.wait_for_timeout(800)

                        body_inputs = page.locator(
                            "textarea[name='message']:visible, "
                            "textarea[id^='compose-form-text-']:visible, "
                            "div.msg-form__contenteditable:visible, "
                            "div[role='textbox']:visible, "
                            "div[contenteditable='true']:visible"
                        )
                        try:
                            body_inputs.first.wait_for(state="visible", timeout=10000)
                        except Exception as error:
                            raise RuntimeError(
                                "No se encontró el cuerpo del formulario de InMail."
                            ) from error
                        if body_inputs.count() == 0:
                            raise RuntimeError("No se encontró el cuerpo del formulario de InMail.")
                        target_body = body_inputs.last
                        human_type(target_body, body_rendered, force_click=True)
                        page.wait_for_timeout(1000)

                        send_inmail_btns = page.locator(
                            "button.msg-form__send-button, "
                            "button:has-text('Send InMail'), "
                            "button:has-text('Enviar InMail'), "
                            "button:visible"
                        )
                        enabled_send_button = None
                        for _ in range(20):
                            for index in range(send_inmail_btns.count()):
                                candidate = send_inmail_btns.nth(index)
                                if candidate.inner_text().strip() in {"Send", "Enviar", "Send InMail", "Enviar InMail"} and not candidate.is_disabled():
                                    enabled_send_button = candidate
                            if enabled_send_button is not None:
                                break
                            page.wait_for_timeout(500)
                        if enabled_send_button is None:
                            raise RuntimeError("No se encontró el botón de envío de InMail.")
                        enabled_send_button.click()
                        if not confirm_inmail_sent(page, target_body):
                            raise RuntimeError("LinkedIn no confirmó el envío del InMail.")
                        close_chat_overlays(page)
                        action_type = "linkedin.inmail_sent"

                    elif scenario == "CONNECT":
                        raise RuntimeError("Solicitud de conexión bloqueada: solo se permite DM o InMail.")

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
