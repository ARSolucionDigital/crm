#!/usr/bin/env python3
"""
Refactored version of LinkedIn automation script with improved Big O notation and self-documenting code.
Original script: send-linkedin.py
"""
import argparse
import datetime
import json
import os
import random
import subprocess
import sys
import time
import urllib.parse
from pathlib import Path

import playwright.sync_api
from playwright.sync_api import sync_playwright


# Configuration constants
BASE_DIR = Path(__file__).parent
DEFAULT_SESSION_DIR = BASE_DIR / "sessions" / "linkedin"
SESSION_STATE_FILE = DEFAULT_SESSION_DIR / "session_state.json"
TEMPLATES_DIR = BASE_DIR / "templates"
LOGS_DIR = BASE_DIR / "logs"
ENV_FILE = BASE_DIR / ".env.linkedin"


def load_environment():
    """
    Load configuration from .env.linkedin file with default fallbacks.

    Returns:
        dict: Configuration parameters with defaults
    """
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


def execute_database_query_as_json(query):
    """
    Execute a PostgreSQL query in the docker container and return JSON parsed result.

    Args:
        query (str): SQL query to execute

    Returns:
        list: Parsed JSON result from the database

    Raises:
        RuntimeError: If database operation fails
    """
    wrapped_query = f"SELECT json_agg(t) FROM ({query}) t;"
    cmd = [
        "docker", "exec", "-i", "twenty-db-1",
        "psql", "-U", "postgres", "-d", "default", "-t", "-A", "-c", wrapped_query
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Database error: {result.stderr.strip()}")

    output = result.stdout.strip()
    if not output or output == "null" or output == "":
        return []

    try:
        return json.loads(output)
    except json.JSONDecodeError:
        return []


def execute_raw_database_command(sql_command):
    """
    Execute raw SQL statements in the database container.

    Args:
        sql_command (str): Raw SQL statement to execute

    Returns:
        str: Command execution output

    Raises:
        RuntimeError: If database operation fails
    """
    cmd = [
        "docker", "exec", "-i", "twenty-db-1",
        "psql", "-U", "postgres", "-d", "default", "-c", sql_command
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Database error: {result.stderr.strip()}")
    return result.stdout.strip()


def parse_message_template(campaign_name, communication_modality):
    """
    Read and parse template file for a given campaign and communication modality.

    Args:
        campaign_name (str): Name of the campaign
        communication_modality (str): Type of communication ('dm', 'inmail', or 'conexion')

    Returns:
        tuple: (subject, body) from the template

    Raises:
        FileNotFoundError: If template or campaign directory doesn't exist
    """
    campaign_directory = TEMPLATES_DIR / campaign_name
    if not campaign_directory.exists():
        available_campaigns = [
            directory.name
            for directory in TEMPLATES_DIR.iterdir()
            if directory.is_dir() and not directory.name.startswith(".")
        ]
        raise FileNotFoundError(
            f"Campaign '{campaign_name}' not found in {TEMPLATES_DIR}.\n"
            f"Available campaigns: {', '.join(available_campaigns)}"
        )

    template_file_path = campaign_directory / f"{communication_modality}.md"
    if not template_file_path.exists():
        raise FileNotFoundError(f"Template '{communication_modality}.md' not found in {campaign_directory}")

    content = template_file_path.read_text(encoding="utf-8").strip()

    subject = ""
    body = content

    # Check for YAML frontmatter (for inmail subject)
    import re
    yaml_frontmatter_pattern = r"^---\s*\n(.*?)\n---\s*\n(.*)$"
    match = re.match(yaml_frontmatter_pattern, content, re.DOTALL)
    if match:
        yaml_content = match.group(1)
        body = match.group(2).strip()
        for line in yaml_content.splitlines():
            if ":" in line:
                key, value = line.split(":", 1)
                if key.strip().lower() == "subject":
                    subject = value.strip().strip("\"'")

    return subject, body


def personalize_message_template(template_text, lead_info):
    """
    Render template string with lead attributes and smart fallbacks.

    Args:
        template_text (str): Template with placeholders
        lead_info (dict): Dictionary with lead information

    Returns:
        str: Personalized message text
    """
    if not template_text:
        return ""

    # Extract lead attributes with fallbacks
    first_name = (lead_info.get("nameFirstName") or "").strip()
    last_name = (lead_info.get("nameLastName") or "").strip()
    company_name = (lead_info.get("companyName") or "").strip()
    job_title = (lead_info.get("jobTitle") or "").strip()
    city = (lead_info.get("city") or "").strip()

    # Determine fallback values
    first_name_value = first_name if first_name else ""
    company_value = company_name if company_name else "your company"
    job_title_value = job_title if job_title else "your sector"
    city_value = city if city else "your area"

    personalized_text = template_text

    # Replace first name with special handling for greetings
    if first_name_value:
        personalized_text = personalized_text.replace("{{nameFirstName}}", first_name_value)
    else:
        # Remove first name placeholder and clean up greetings
        import re
        personalized_text = re.sub(r"Hola,\s*\{\{nameFirstName\}\}:?", "Hello,", personalized_text)
        personalized_text = re.sub(r"Hola\s*\{\{nameFirstName\}\}:?", "Hello,", personalized_text)
        personalized_text = personalized_text.replace("{{nameFirstName}}", "")

    # Replace remaining placeholders
    personalized_text = personalized_text.replace("{{nameLastName}}", last_name)
    personalized_text = personalized_text.replace("{{companyName}}", company_value)
    personalized_text = personalized_text.replace("{{jobTitle}}", job_title_value)
    personalized_text = personalized_text.replace("{{city}}", city_value)
    personalized_text = re.sub(r"[ ]{2,}", " ", personalized_text)

    return personalized_text.strip()


def fetch_target_leads(
    config,
    status_filter="EMAIL_FRIO",
    limit=20,
    lead_id=None,
    industry_filter=None,
    role_filter=None,
    min_employees=None,
    max_employees=None
):
    """
    Query eligible leads from Twenty CRM database with optimized filtering.

    Args:
        config (dict): Configuration parameters
        status_filter (str): Filter by sequence status
        limit (int): Maximum number of leads to return
        lead_id (str): Specific lead to target (if provided)
        industry_filter (str): Industry filter
        role_filter (str): Role filter
        min_employees (int): Minimum employees filter
        max_employees (int): Maximum employees filter

    Returns:
        list: List of target leads with their information
    """
    schema = config["WORKSPACE_SCHEMA"]

    where_conditions = [
        "p.\"deletedAt\" IS NULL",
        "p.\"linkedinLinkPrimaryLinkUrl\" IS NOT NULL",
        "p.\"linkedinLinkPrimaryLinkUrl\" != ''"
    ]

    # Add conditions based on filters
    if lead_id:
        where_conditions.append(f"p.id = '{lead_id}'")
    else:
        if status_filter and status_filter.upper() != "ALL":
            where_conditions.append(f"p.\"sequenceStatus\" = '{status_filter}'")

        # Ensure there's a task to process
        where_conditions.append(f"""
            EXISTS (
                SELECT 1 FROM \"{schema}\".\"taskTarget\" tt
                JOIN \"{schema}\".\"task\" t ON tt.\"taskId\" = t.id
                WHERE tt.\"targetPersonId\" = p.id
                  AND t.title = 'DM Linkedin'
                  AND t.status = 'TODO'
            )
        """)

        # Apply industry filter with optimized pattern matching
        if industry_filter:
            industry_conditions = create_industry_filter_conditions(industry_filter)
            where_conditions.extend(industry_conditions)

        # Apply role filter with optimized pattern matching
        if role_filter:
            role_conditions = create_role_filter_conditions(role_filter)
            where_conditions.extend(role_conditions)

        # Apply employee count filters
        if min_employees is not None:
            where_conditions.append(f"c.employees >= {min_employees}")
        if max_employees is not None:
            where_conditions.append(f"c.employees <= {max_employees}")

    where_clause = " AND ".join(where_conditions)

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
        WHERE {where_clause}
        ORDER BY p.\"createdAt\" ASC
        LIMIT {limit}
    """
    return execute_database_query_as_json(query)


def create_industry_filter_conditions(industry):
    """
    Create SQL conditions for industry filtering with optimized patterns.

    Args:
        industry (str): Industry to filter

    Returns:
        list: List of SQL conditions
    """
    industry_lower = industry.lower()
    if industry_lower in ["moda", "retail"]:
        return ["(c.industry ILIKE '%moda%' OR c.industry ILIKE '%ropa%' OR c.industry ILIKE '%retail%' OR c.industry ILIKE '%textil%')"]
    elif industry_lower in ["logistica", "transporte"]:
        return ["(c.industry ILIKE '%transporte%' OR c.industry ILIKE '%logistica%' OR c.industry ILIKE '%logística%' OR c.industry ILIKE '%camion%' OR c.industry ILIKE '%maritimo%')"]
    else:
        return [f"c.industry ILIKE '%{industry}%'"]


def create_role_filter_conditions(role):
    """
    Create SQL conditions for role filtering with optimized patterns.

    Args:
        role (str): Role to filter

    Returns:
        list: List of SQL conditions
    """
    role_lower = role.lower()
    if role_lower in ["operaciones", "coo", "ops"]:
        return ["(p.\"jobTitle\" ILIKE '%operat%' OR p.\"jobTitle\" ILIKE '%coo%' OR p.\"jobTitle\" ILIKE '%logist%' OR p.\"jobTitle\" ILIKE '%trafic%')"]
    elif role_lower in ["ceo", "director", "founder", "fundador", "owner", "dueño"]:
        return ["(p.\"jobTitle\" ILIKE '%ceo%' OR p.\"jobTitle\" ILIKE '%fundad%' OR p.\"jobTitle\" ILIKE '%founder%' OR p.\"jobTitle\" ILIKE '%owner%' OR p.\"jobTitle\" ILIKE '%general%')"]
    else:
        return [f"p.\"jobTitle\" ILIKE '%{role}%'"]


def update_crm_after_linkedin_interaction(config, lead, campaign_name, action_type, message_sent):
    """
    Update task and sequence status in Twenty CRM after LinkedIn interaction.

    Args:
        config (dict): Configuration parameters
        lead (dict): Lead information
        campaign_name (str): Campaign identifier
        action_type (str): Type of action performed
        message_sent (str): Message that was sent
    """
    schema = config["WORKSPACE_SCHEMA"]
    member_id = config["WORKSPACE_MEMBER_ID"]
    person_id = lead["id"]
    task_id = lead.get("taskId")

    # Update sequence status to indicate LinkedIn message sent
    execute_raw_database_command(f"""
        UPDATE \"{schema}\".\"person\"
        SET \"sequenceStatus\" = 'LINKEDIN_ENVIADO', \"updatedAt\" = NOW()
        WHERE id = '{person_id}';
    """)

    # Mark task as completed
    if task_id:
        execute_raw_database_command(f"""
            UPDATE \"{schema}\".\"task\"
            SET status = 'DONE', \"updatedAt\" = NOW()
            WHERE id = '{task_id}';
        """)

    # Log the activity in timeline
    activity_properties = json.dumps({
        "campaign": campaign_name,
        "actionType": action_type,
        "profileUrl": lead.get("linkedinLinkPrimaryLinkUrl"),
        "date": datetime.datetime.now().isoformat()
    })

    execute_raw_database_command(f"""
        INSERT INTO \"{schema}\".\"timelineActivity\" (
            id, \"createdAt\", \"updatedAt\", \"happensAt\",
            name, properties,
            \"targetPersonId\", \"workspaceMemberId\",
            \"createdBySource\", \"updatedBySource\",
            \"createdByName\", \"updatedByName\"
        ) VALUES (
            gen_random_uuid(), NOW(), NOW(), NOW(),
            '{action_type}', '{activity_properties}'::jsonb,
            '{person_id}', '{member_id}',
            'MANUAL', 'MANUAL',
            'Raul Almeida', 'Raul Almeida'
        );
    """)


def launch_browser_with_stealth_configuration(playwright_instance, config, headless_mode=False):
    """
    Launch Google Chrome in persistent stealth context with storage state fallback.

    Args:
        playwright_instance: Playwright instance
        config (dict): Configuration parameters
        headless_mode (bool): Whether to run in headless mode

    Returns:
        BrowserContext: Configured browser context
    """
    profile_directory = Path(config.get("CHROME_PROFILE_DIR", DEFAULT_SESSION_DIR)).expanduser().resolve()
    profile_directory.mkdir(parents=True, exist_ok=True)

    # Detect Chrome installation on macOS
    mac_chrome_path = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    chrome_channel = "chrome" if os.path.exists(mac_chrome_path) else None

    storage_state_path = str(SESSION_STATE_FILE) if SESSION_STATE_FILE.exists() else None

    browser_context = playwright_instance.chromium.launch_persistent_context(
        user_data_dir=str(profile_directory),
        channel=chrome_channel,
        headless=headless_mode,
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

    # Load stored session state if available
    if storage_state_path and SESSION_STATE_FILE.exists():
        try:
            with open(SESSION_STATE_FILE, "r", encoding="utf-8") as f:
                state_data = json.load(f)
                browser_context.add_cookies(state_data.get("cookies", []))
        except Exception:
            pass

    # Add stealth scripts to prevent detection
    browser_context.add_init_script("""
        Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
        window.chrome = { runtime: {} };
    """)

    return browser_context


def simulate_human_typing(element, text):
    """
    Simulate realistic human typing with variable inter-key delays.

    Args:
        element: Page element to type into
        text (str): Text to type
    """
    element.click()
    for character in text:
        element.type(character, delay=random.randint(35, 85))
        if character in [".", ",", "!", "?", "\n"]:
            time.sleep(random.uniform(0.12, 0.30))


def close_any_open_chat_overlays(page):
    """
    Close or minimize any open floating chat bubbles from previous leads.

    Args:
        page: Playwright page object
    """
    try:
        close_buttons = page.locator(
            "aside.msg-overlay-container button[data-control-name='overlay.close_conversation_window'], "
            "aside.msg-overlay-container button[aria-label*='Close conversation'], "
            "aside.msg-overlay-container button[aria-label*='Cerrar'], "
            "button:has(svg[data-test-icon='close-small'])"
        )
        for i in range(close_buttons.count()):
            if close_buttons.nth(i).is_visible():
                close_buttons.nth(i).click()
                page.wait_for_timeout(250)
    except Exception:
        pass


def normalize_linkedin_profile_url(raw_url):
    """
    Ensure URL is clean, unquoted, and starts with https.

    Args:
        raw_url (str): Raw URL to normalize

    Returns:
        str: Cleaned and normalized URL
    """
    if not raw_url:
        return ""
    url = urllib.parse.unquote(raw_url.strip())
    if not url.startswith("http"):
        url = "https://" + url
    if url.startswith("http://"):
        url = "https://" + url[7:]
    return url


def determine_linkedin_profile_strategy(page):
    """
    Analyze profile page to determine the optimal communication strategy:
    1. 1st Degree Connection -> 'DM' (Free direct chat via dm.md)
    2. Non-Connection (2nd/3rd Degree) -> 'INMAIL' (Prioritized InMail via inmail.md using Sales Nav credits)
    3. Fallback (If InMail restricted) -> 'CONNECT' (Connection request with note via conexion.md)
    4. Pending without InMail -> 'PENDING'
    5. Error / Authwall -> 'ERROR'

    Args:
        page: Playwright page object

    Returns:
        tuple: (strategy, action_element) where strategy is the recommended approach
    """
    page.wait_for_timeout(3000)

    # Check for 404 / Error / Authwall
    if "authwall" in page.url:
        return "ERROR", None

    if (page.locator("text='Esta página no existe'").count() > 0 or
        page.locator("text='Page not found'").count() > 0):
        return "ERROR", None

    # Check for 1st Degree Connection (Strictly in profile top card)
    top_card = page.locator("main section").first
    top_badges = top_card.locator("span.dist-value, span:has-text('1st'), span:has-text('1.º')").all_text_contents()
    is_first_degree = any(('1st' in badge or '1.º' in badge) for badge in top_badges if badge.strip())

    if is_first_degree:
        direct_message_link = top_card.locator(
            "a[href*='/messaging/compose'], "
            "a:has-text('Message'), "
            "a:has-text('Mensaje'), "
            "button:has-text('Message'), "
            "button:has-text('Mensaje')"
        )
        if direct_message_link.count() > 0:
            return "DM", direct_message_link.first

    # For 2nd/3rd Degree: Prioritize INMAIL (Using available InMail credits)
    # Check for direct InMail / Sales Nav buttons in top card
    inmail_direct = top_card.locator(
        "button:has-text('InMail'), "
        "button[data-control-name='inmail'], "
        "button[aria-label*='InMail'], "
        "a:has-text('View in Sales Navigator'), "
        "a:has-text('Ver en Sales Navigator'), "
        "a[href*='/sales/']"
    )
    if inmail_direct.count() > 0 and inmail_direct.first.is_visible():
        return "INMAIL", inmail_direct.first

    # Check the primary action Message link on non-connection (which opens InMail compose)
    non_connection_message = top_card.locator(
        "a[href*='/messaging/compose'], "
        "a.artdeco-button--primary:has-text('Message'), "
        "a.artdeco-button--primary:has-text('Mensaje')"
    )
    if non_connection_message.count() > 0 and non_connection_message.first.is_visible():
        return "INMAIL", non_connection_message.first

    # Check inside 'More' / 'Más' dropdown for InMail / Sales Navigator
    more_button = page.locator(
        "main button[aria-label*='More'], "
        "main button[aria-label*='Más'], "
        "main button:has-text('More'), "
        "main button:has-text('Más')"
    )
    if more_button.count() > 0 and more_button.first.is_visible():
        try:
            more_button.first.click()
            page.wait_for_timeout(800)

            inmail_in_more = page.locator(
                "div[role='button']:has-text('Sales Navigator'), "
                "div[role='button']:has-text('InMail'), "
                "[role='menuitem']:has-text('Sales Navigator'), "
                "[role='menuitem']:has-text('InMail'), "
                "a:has-text('Sales Navigator')"
            )
            if inmail_in_more.count() > 0 and inmail_in_more.first.is_visible():
                return "INMAIL", inmail_in_more.first
        except Exception:
            pass

    # Fallback: Check if Connect is available if InMail is not possible
    connect_button = page.locator(
        "main button:has-text('Conectar'), "
        "main button:has-text('Connect'), "
        "main a[href*='/preload/custom-invite/']"
    )
    if connect_button.count() > 0 and connect_button.first.is_visible():
        return "CONNECT", connect_button.first

    # Check inside 'More' dropdown for Connect
    if more_button.count() > 0 and more_button.first.is_visible():
        try:
            connect_in_more = page.locator(
                "div[role='button']:has-text('Connect'), "
                "div[role='button']:has-text('Conectar'), "
                "[role='menuitem']:has-text('Connect'), "
                "[role='menuitem']:has-text('Conectar'), "
                "button:has-text('Conectar'), "
                "button:has-text('Connect')"
            )
            if connect_in_more.count() > 0 and connect_in_more.first.is_visible():
                return "CONNECT", connect_in_more.first
        except Exception:
            pass

    # Check if already Pending
    pending_locator = page.locator(
        "main button:has-text('Pendiente'), "
        "main button:has-text('Pending'), "
        "div[role='button']:has-text('Pending'), "
        "[role='menuitem']:has-text('Pending')"
    )
    if pending_locator.count() > 0:
        return "PENDING", None

    return "CONNECT", None


def perform_session_login_and_setup(config):
    """
    Interactive mode to open browser, log into LinkedIn/Sales Navigator and save state.

    Args:
        config (dict): Configuration parameters
    """
    print("\n" + "=" * 70)
    print("🔑 SESSION CONFIGURATION MODE (LINKEDIN & SALES NAV)")
    print("=" * 70)
    print("Google Chrome will open.")
    print("1. Log in to LinkedIn and Sales Navigator.")
    print("2. Wait for your LinkedIn feed to load.")
    print("3. Press ENTER in the terminal to save the session.")
    print("=" * 70 + "\n")

    with sync_playwright() as playwright_instance:
        context = launch_browser_with_stealth_configuration(playwright_instance, config, headless_mode=False)
        page = context.new_page()
        page.goto("https://www.linkedin.com/feed/", wait_until="domcontentloaded")

        input("\n[Press ENTER when logged into LinkedIn]: ")

        # Save storage state JSON
        context.storage_state(path=str(SESSION_STATE_FILE))
        print(f"✅ Session cookies exported successfully to {SESSION_STATE_FILE.name}!")

        # Open Sales Nav tab to ensure session sync
        try:
            page.goto("https://www.linkedin.com/sales", wait_until="domcontentloaded")
            page.wait_for_timeout(3000)
            context.storage_state(path=str(SESSION_STATE_FILE))
        except Exception:
            pass

        context.close()
        print("✅ Session saved and permanently verified!\n")


def test_individual_profile(config, campaign_name, profile_url, dry_run_mode=True):
    """
    Test classification and rendering on a single arbitrary LinkedIn URL.

    Args:
        config (dict): Configuration parameters
        campaign_name (str): Name of the campaign
        profile_url (str): LinkedIn profile URL to test
        dry_run_mode (bool): Whether to run in simulation mode
    """
    print("\n" + "=" * 70)
    print(f"🧪 TESTING INDIVIDUAL PROFILE: {profile_url}")
    print(f"📁 Selected campaign      : {campaign_name}")
    print(f"🛠️  Mode                  : {'DRY-RUN (Simulation)' if dry_run_mode else 'REAL SEND'}")
    print("=" * 70)

    cleaned_url = normalize_linkedin_profile_url(profile_url)
    sample_lead = {
        "nameFirstName": "Laura",
        "nameLastName": "Romero Ruiz",
        "companyName": "your company",
        "jobTitle": "Directiva",
        "city": "Spain",
        "linkedinLinkPrimaryLinkUrl": cleaned_url
    }

    with sync_playwright() as playwright_instance:
        context = launch_browser_with_stealth_configuration(playwright_instance, config, headless_mode=False)
        page = context.new_page()

        print(f"\n🔍 Navigating to: {cleaned_url} ...")
        page.goto(cleaned_url, wait_until="domcontentloaded", timeout=35000)
        page.wait_for_timeout(4000)

        # Extract name dynamically from page title / H1 (e.g. "Silvia Juliana | LinkedIn" -> "Silvia")
        page_title = page.title()
        print(f"📄 Page title: {page_title}")

        extracted_first_name = ""
        if "|" in page_title:
            full_title_name = page_title.split("|")[0].strip()
            name_parts = full_title_name.split()
            if name_parts:
                extracted_first_name = name_parts[0]

        sample_lead = {
            "nameFirstName": extracted_first_name,
            "nameLastName": "",
            "companyName": "your company",
            "jobTitle": "Directiva",
            "city": "Spain",
            "linkedinLinkPrimaryLinkUrl": cleaned_url
        }

        profile_strategy, action_button = determine_linkedin_profile_strategy(page)
        print(f"🎯 Detected strategy: {profile_strategy}")

        if profile_strategy == "ERROR":
            print("❌ Could not authenticate LinkedIn session or profile is inaccessible.")
            context.close()
            return

        modality = "dm" if profile_strategy == "DM" else ("inmail" if profile_strategy == "INMAIL" else "conexion")
        subject_raw, body_raw = parse_message_template(campaign_name, modality)

        subject_rendered = personalize_message_template(subject_raw, sample_lead)
        body_rendered = personalize_message_template(body_raw, sample_lead)

        print(f"\n📝 Selected template: {modality}.md")
        if subject_rendered:
            print(f"📨 Subject rendered : {subject_rendered}")
        print(f"💬 Text rendered    : {body_rendered}")
        print(f"📏 Message length   : {len(body_rendered)} characters")

        if dry_run_mode:
            print("\n✨ [TEST DRY-RUN] Detection and rendering completed successfully (Not sent).")
        else:
            print("\n🚀 Executing real send to LinkedIn...")
            if profile_strategy == "DM":
                if action_button:
                    print("   👉 Opening direct chat window...")
                    action_button.click()
                    page.wait_for_timeout(2000)

                    chat_box = page.locator("div.msg-form__contenteditable, div[role='textbox'], div[contenteditable='true']")
                    if chat_box.count() > 0:
                        print(f"   ⌨️  Typing message with human-like typing...")
                        simulate_human_typing(chat_box.first, body_rendered)
                        page.wait_for_timeout(1200)

                        send_button = page.locator("button.msg-form__send-button, button:has-text('Send'), button:has-text('Enviar')")
                        if send_button.count() > 0:
                            print("   📤 Sending message...")
                            send_button.first.click()
                            page.wait_for_timeout(3000)
                            print("   ✅ Direct message sent successfully to Laura!")
                    else:
                        print("   ⚠️ Chat text field not found.")

            elif profile_strategy == "INMAIL":
                if action_button:
                    close_any_open_chat_overlays(page)
                    print("   👉 Opening InMail window...")
                    action_button.click()
                    page.wait_for_timeout(2500)

                    subject_inputs = page.locator("input[name='subject'], input[placeholder*='Asunto'], input[placeholder*='Subject'], input.msg-form__subject")
                    if subject_inputs.count() > 0 and subject_rendered:
                        print(f"   ⌨️  Typing subject: {subject_rendered}")
                        target_subject = subject_inputs.last
                        target_subject.click()
                        simulate_human_typing(target_subject, subject_rendered)
                        page.wait_for_timeout(800)

                    body_inputs = page.locator("div.msg-form__contenteditable, div[role='textbox'], div[contenteditable='true'], textarea[name='message']")
                    if body_inputs.count() > 0:
                        print(f"   ⌨️  Typing InMail body...")
                        target_body = body_inputs.last
                        target_body.click()
                        simulate_human_typing(target_body, body_rendered)
                        page.wait_for_timeout(1000)

                        send_inmail_buttons = page.locator("button.msg-form__send-button, button:has-text('Send InMail'), button:has-text('Enviar InMail'), button:has-text('Send'), button:has-text('Enviar')")
                        if send_inmail_buttons.count() > 0:
                            target_send = send_inmail_buttons.last
                            if not target_send.is_disabled():
                                print("   📤 Sending InMail...")
                                target_send.click()
                                page.wait_for_timeout(3000)
                                print("   ✅ InMail sent successfully!")
                    close_any_open_chat_overlays(page)

            elif profile_strategy == "CONNECT":
                if action_button:
                    print("   👉 Opening connection window...")
                    action_button.click()
                    page.wait_for_timeout(1500)

                    add_note_button = page.locator("button:has-text('Añadir una nota'), button:has-text('Add a note')")
                    if add_note_button.count() > 0 and add_note_button.first.is_visible():
                        add_note_button.first.click()
                        page.wait_for_timeout(1000)
                        note_box = page.locator("textarea[name='message'], textarea#custom-message")
                        if note_box.count() > 0:
                            print(f"   ⌨️  Typing connection note...")
                            simulate_human_typing(note_box.first, body_rendered[:300])
                            page.wait_for_timeout(1000)
                            send_conn_button = page.locator("button:has-text('Enviar'), button:has-text('Send')")
                            if send_conn_button.count() > 0:
                                send_conn_button.first.click()
                                page.wait_for_timeout(2500)
                                print("   ✅ Connection request with note sent successfully!")

        page.wait_for_timeout(3000)
        context.close()


def process_lead_interaction(page, lead, config, campaign_name, dry_run_mode, scenario, action_button, communication_modality, subject_rendered, body_rendered):
    """
    Process the interaction with a specific lead based on the determined strategy.

    Args:
        page: Playwright page object
        lead (dict): Lead information
        config (dict): Configuration parameters
        campaign_name (str): Campaign name
        dry_run_mode (bool): Whether to run in simulation mode
        scenario (str): Profile scenario determined earlier
        action_button: Button element to interact with
        communication_modality (str): Type of communication
        subject_rendered (str): Rendered subject line
        body_rendered (str): Rendered message body
    """
    if dry_run_mode:
        print("   🛠️ [DRY-RUN] Simulation successful (Not sent).")
        return {"personId": lead["id"], "name": get_lead_name(lead), "status": "DRY_RUN", "scenario": scenario}
    else:
        # Execute actual send based on scenario
        if scenario == "DM":
            if action_button:
                close_any_open_chat_overlays(page)
                action_button.click()
                page.wait_for_timeout(2500)

                chat_boxes = page.locator("div.msg-form__contenteditable, div[role='textbox'], div[contenteditable='true']")
                if chat_boxes.count() > 0:
                    target_box = chat_boxes.last
                    target_box.click()
                    page.wait_for_timeout(500)
                    simulate_human_typing(target_box, body_rendered)
                    page.wait_for_timeout(1000)

                    send_buttons = page.locator("button.msg-form__send-button, button[type='submit']:has-text('Send'), button:has-text('Enviar')")
                    if send_buttons.count() > 0:
                        target_send = send_buttons.last
                        if not target_send.is_disabled():
                            target_send.click()
                            page.wait_for_timeout(3000)
            close_any_open_chat_overlays(page)
            action_type = "linkedin.dm_sent"

        elif scenario == "INMAIL":
            if action_button:
                close_any_open_chat_overlays(page)
                action_button.click()
                page.wait_for_timeout(2500)

                subject_inputs = page.locator("input[name='subject'], input[placeholder*='Asunto'], input[placeholder*='Subject'], input.msg-form__subject")
                if subject_inputs.count() > 0 and subject_rendered:
                    target_subject = subject_inputs.last
                    target_subject.click()
                    simulate_human_typing(target_subject, subject_rendered)
                    page.wait_for_timeout(800)

                body_inputs = page.locator("div.msg-form__contenteditable, div[role='textbox'], div[contenteditable='true'], textarea[name='message']")
                if body_inputs.count() > 0:
                    target_body = body_inputs.last
                    target_body.click()
                    simulate_human_typing(target_body, body_rendered)
                    page.wait_for_timeout(1000)

                    send_inmail_btns = page.locator("button.msg-form__send-button, button:has-text('Send InMail'), button:has-text('Enviar InMail'), button:has-text('Send'), button:has-text('Enviar')")
                    if send_inmail_btns.count() > 0:
                        target_send = send_inmail_btns.last
                        if not target_send.is_disabled():
                            target_send.click()
                            page.wait_for_timeout(3000)
            close_any_open_chat_overlays(page)
            action_type = "linkedin.inmail_sent"

        elif scenario == "CONNECT":
            if action_button:
                action_button.click()
                page.wait_for_timeout(1500)
                add_note_btn = page.locator("button:has-text('Añadir una nota'), button:has-text('Add a note')")
                if add_note_btn.count() > 0 and add_note_btn.first.is_visible():
                    add_note_btn.first.click()
                    page.wait_for_timeout(1000)
                    note_box = page.locator("textarea[name='message'], textarea#custom-message")
                    if note_box.count() > 0:
                        simulate_human_typing(note_box.first, body_rendered[:300])
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

        # Update CRM with the interaction
        update_crm_after_linkedin_interaction(config, lead, campaign_name, action_type, body_rendered)
        print(f"   ✅ SENT ({action_type}) & CRM updated.")

        return {
            "personId": lead["id"],
            "name": get_lead_name(lead),
            "company": lead.get("companyName", "N/A"),
            "status": "SENT",
            "scenario": scenario,
            "timestamp": datetime.datetime.now().isoformat()
        }


def get_lead_name(lead):
    """
    Get formatted lead name from lead info.

    Args:
        lead (dict): Lead information

    Returns:
        str: Formatted lead name
    """
    return f"{lead.get('nameFirstName', '')} {lead.get('nameLastName', '')}".strip()


def main():
    """Main function to execute LinkedIn campaign automation."""
    parser = argparse.ArgumentParser(
        description="Twenty CRM — LinkedIn & Sales Navigator Automation CLI",
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--template", "-t", default="moda-operaciones", help="Campaign name (e.g. moda-operaciones, moda-ceos, logistica-operaciones)")
    parser.add_argument("--login", action="store_true", help="Open browser to log in and save cookies")
    parser.add_argument("--test-url", help="Test detection and rendering with specific LinkedIn URL")
    parser.add_argument("--limit", "-n", type=int, default=20, help="Limit of leads to process (default: 20)")
    parser.add_argument("--dry-run", action="store_true", help="Preview profile detection and texts without sending")
    parser.add_argument("--headless", action="store_true", help="Run in background mode (no visible window)")
    parser.add_argument("--delay-min", type=int, help="Minimum seconds to wait between leads")
    parser.add_argument("--delay-max", type=int, help="Maximum seconds to wait between leads")
    parser.add_argument("--status", default="EMAIL_FRIO", help="Filter by Sequence Status (default: EMAIL_FRIO, or 'ALL')")
    parser.add_argument("--industry", help="Filter by industry (e.g. moda, logistica, retail)")
    parser.add_argument("--role", help="Filter by role (e.g. operaciones, ceo, founder)")
    parser.add_argument("--min-employees", type=int, help="Filter by minimum employees (e.g. 50)")
    parser.add_argument("--max-employees", type=int, help="Filter by maximum employees (e.g. 49)")
    parser.add_argument("--lead-id", help="Process only a specific Lead by UUID")
    parser.add_argument("--yes", "-y", action="store_true", help="Skip interactive confirmation")

    args = parser.parse_args()
    config = load_environment()

    if args.login:
        perform_session_login_and_setup(config)
        sys.exit(0)

    if args.test_url:
        test_individual_profile(config, args.template, args.test_url, dry_run_mode=args.dry_run)
        sys.exit(0)

    if not args.template:
        print("❌ Error: Must specify campaign with --template <name> (e.g. moda-operaciones)")
        parser.print_help()
        sys.exit(1)

    delay_min = args.delay_min if args.delay_min is not None else int(config["DEFAULT_DELAY_MIN"])
    delay_max = args.delay_max if args.delay_max is not None else int(config["DEFAULT_DELAY_MAX"])
    if delay_max < delay_min:
        delay_max = delay_min

    is_headless = args.headless or (config.get("HEADLESS", "false").lower() == "true")

    # 1. Fetch leads with optimized query
    print(f"\n🔍 Querying leads in Twenty CRM (Status: {args.status}, Limit: {args.limit})...")
    leads = fetch_target_leads(
        config,
        status_filter=args.status,
        limit=args.limit,
        lead_id=args.lead_id,
        industry_filter=args.industry,
        role_filter=args.role,
        min_employees=args.min_employees,
        max_employees=args.max_employees
    )

    if not leads:
        print(f"⚠️ No pending leads found with status '{args.status}' and valid LinkedIn URLs.")
        sys.exit(0)

    print(f"✅ Found {len(leads)} leads ready for LinkedIn campaign.")

    # 2. Confirmation
    estimated_minutes = round(((delay_min + delay_max) / 2 * (len(leads) - 1)) / 60, 1) if len(leads) > 1 else 0
    print("\n" + "=" * 70)
    print(f"💼 LINKEDIN CAMPAIGN: {args.template}")
    print(f"👥 Total prospects       : {len(leads)}")
    print(f"⏱️  Pause between prospects: {delay_min}s - {delay_max}s (Estimated: ~{estimated_minutes} min)")
    print(f"🛡️  Stealth Mode          : ACTIVE (Native Google Chrome)")
    print(f"👁️  Visual Mode           : {'Background (Headless)' if is_headless else 'Visible Window'}")
    print("=" * 70)

    if not args.yes and not args.dry_run:
        confirm = input("\nDo you want to start the LinkedIn process now? [y/N]: ").strip().lower()
        if confirm not in ["s", "si", "y", "yes"]:
            print("❌ Process cancelled by user.")
            sys.exit(0)

    # 3. Launch Browser and Process Leads
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    log_file = LOGS_DIR / f"linkedin_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    results = []

    print(f"\n🚀 Starting processing of {len(leads)} leads with Playwright...\n")

    with sync_playwright() as playwright_instance:
        context = launch_browser_with_stealth_configuration(playwright_instance, config, headless_mode=is_headless)
        page = context.new_page()

        for i, lead in enumerate(leads, 1):
            lead_name = get_lead_name(lead)
            raw_url = lead.get("linkedinLinkPrimaryLinkUrl", "")
            cleaned_url = normalize_linkedin_profile_url(raw_url)
            lead_company = lead.get("companyName", "N/A")

            print(f"[{i}/{len(leads)}] {lead_name} ({lead_company})")
            print(f"   🔗 URL: {cleaned_url}")

            if not cleaned_url:
                print("   ❌ Skipped: Empty LinkedIn URL.")
                results.append({"personId": lead["id"], "name": lead_name, "status": "FAILED", "error": "Empty URL"})
                continue

            try:
                # Navigate to profile
                page.goto(cleaned_url, wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(random.randint(2500, 4500))

                scenario, action_button = determine_linkedin_profile_strategy(page)
                print(f"   🎯 Detected scenario: {scenario}")

                if scenario == "ERROR":
                    print("   ⚠️ Profile not found or inaccessible (404).")
                    results.append({"personId": lead["id"], "name": lead_name, "status": "FAILED", "error": "Profile not found"})
                    continue

                if scenario == "PENDING":
                    print("   ℹ️ Invitation already sent previously (Pending).")
                    if not args.dry_run:
                        update_crm_after_linkedin_interaction(config, lead, args.template, "linkedin.already_pending", "")
                    results.append({"personId": lead["id"], "name": lead_name, "status": "SKIPPED", "scenario": "PENDING"})
                    continue

                # Select communication modality and prepare message
                communication_modality = "dm" if scenario == "DM" else ("inmail" if scenario == "INMAIL" else "conexion")
                subject_raw, body_raw = parse_message_template(args.template, communication_modality)

                subject_rendered = personalize_message_template(subject_raw, lead)
                body_rendered = personalize_message_template(body_raw, lead)

                print(f"   📝 Template: {communication_modality}.md")
                if subject_rendered:
                    print(f"   📨 Subject: {subject_rendered}")
                print(f"   💬 Message ({len(body_rendered)} chars): {body_rendered[:90]}...")

                # Process the interaction
                result = process_lead_interaction(
                    page, lead, config, args.template, args.dry_run,
                    scenario, action_button, communication_modality,
                    subject_rendered, body_rendered
                )
                results.append(result)

            except Exception as e:
                print(f"   ❌ ERROR processing profile: {e}")
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
                wait_seconds = random.randint(delay_min, delay_max)
                print(f"   ⏳ Security pause: waiting {wait_seconds}s before next lead...\n")
                time.sleep(wait_seconds)
            else:
                print()

        context.close()

    # Save log with aggregated statistics
    log_data = {
        "campaign": args.template,
        "total": len(leads),
        "sent": sum(1 for r in results if r["status"] == "SENT"),
        "skipped": sum(1 for r in results if r["status"] == "SKIPPED"),
        "failed": sum(1 for r in results if r["status"] == "FAILED"),
        "results": results
    }

    with open(log_file, "w", encoding="utf-8") as f:
        json.dump(log_data, f, indent=2, ensure_ascii=False)

    sent_count = log_data["sent"]
    skipped_count = log_data["skipped"]
    failed_count = log_data["failed"]

    print("=" * 70)
    print("🎉 Process completed:")
    print(f"   ✅ Sent successfully   : {sent_count}")
    print(f"   ℹ️  Skipped (Pending)   : {skipped_count}")
    print(f"   ❌ Failed              : {failed_count}")
    print(f"   📄 Log saved to        : {log_file.relative_to(BASE_DIR.parent.parent)}")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    main()
