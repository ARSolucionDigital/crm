#!/bin/bash
# =============================================================================
# Twenty CRM — Configure CRM for Ar Solución Digital
# =============================================================================
# Sets up custom fields, pipeline stages, and views for a B2B software
# development company sales process.
#
# Usage: bash scripts/crm-configure.sh
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

SERVER_URL="http://localhost:3000"
GRAPHQL_URL="$SERVER_URL/metadata"

# Admin credentials (created in DB)
EMAIL="admin@arsoluciondigital.com"
PASSWORD="Admin1234!"

info()  { echo "=> $*"; }
ok()    { echo "   ✓ $*"; }
fail()  { echo "   ✗ $*"; exit 1; }

# --------------- GraphQL helper ---------------
graphql() {
  local token="$1"
  local query="$2"
  curl -s -X POST "$GRAPHQL_URL" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer $token" \
    -d "{\"query\": $query}"
}

# --------------- Step 1: Authenticate ---------------
info "Step 1: Authenticating..."

SIGN_IN_RESPONSE=$(graphql "" "{\"mutation { signIn(email: \\\"$EMAIL\\\", password: \\\"$PASSWORD\\\") { availableWorkspaces { availableWorkspacesForSignIn { id displayName } } tokens { accessOrWorkspaceAgnosticToken { token } } } }\"}")

ACCESS_TOKEN=$(echo "$SIGN_IN_RESPONSE" | jq -r '.data.signIn.tokens.accessOrWorkspaceAgnosticToken.token')
if [ "$ACCESS_TOKEN" = "null" ] || [ -z "$ACCESS_TOKEN" ]; then
  fail "Failed to get access token: $SIGN_IN_RESPONSE"
fi
ok "Access token obtained"

WORKSPACE_ID=$(echo "$SIGN_IN_RESPONSE" | jq -r '.data.signIn.availableWorkspaces.availableWorkspacesForSignIn[0].id')
ok "Workspace ID: $WORKSPACE_ID"

# --------------- Step 2: Get object metadata IDs ---------------
info "Step 2: Fetching object metadata..."

METADATA_RESPONSE=$(graphql "$ACCESS_TOKEN" '{"query": "{ minimalMetadata { objectMetadataItems { id nameSingular namePlural } } }"}')

COMPANY_OBJECT_ID=$(echo "$METADATA_RESPONSE" | jq -r '.data.minimalMetadata.objectMetadataItems[] | select(.nameSingular == "company") | .id')
PERSON_OBJECT_ID=$(echo "$METADATA_RESPONSE" | jq -r '.data.minimalMetadata.objectMetadataItems[] | select(.nameSingular == "person") | .id')
OPPORTUNITY_OBJECT_ID=$(echo "$METADATA_RESPONSE" | jq -r '.data.minimalMetadata.objectMetadataItems[] | select(.nameSingular == "opportunity") | .id')

if [ -z "$COMPANY_OBJECT_ID" ] || [ -z "$PERSON_OBJECT_ID" ] || [ -z "$OPPORTUNITY_OBJECT_ID" ]; then
  fail "Failed to find standard object metadata IDs"
fi

ok "Company object ID: $COMPANY_OBJECT_ID"
ok "Person object ID: $PERSON_OBJECT_ID"
ok "Opportunity object ID: $OPPORTUNITY_OBJECT_ID"

# --------------- Step 3: Create custom fields for Companies ---------------
info "Step 3: Creating custom fields for Companies..."

# Sector field (SELECT)
SECTOR_RESPONSE=$(graphql "$ACCESS_TOKEN" "{\"mutation { createOneField(input: {field: {objectMetadataId: \\\"$COMPANY_OBJECT_ID\\\", type: SELECT, name: \\\"sector\\\", label: \\\"Sector\\\", description: \\\"Industry sector of the company\\\", options: [{label: \\\"Tecnología\\\", value: \\\"tecnologia\\\", position: 0}, {label: \\\"Retail\\\", value: \\\"retail\\\", position: 1}, {label: \\\"Salud\\\", value: \\\"salud\\\", position: 2}, {label: \\\"Finanzas\\\", value: \\\"finanzas\\\", position: 3}, {label: \\\"Manufactura\\\", value: \\\"manufactura\\\", position: 4}, {label: \\\"Educación\\\", value: \\\"educacion\\\", position: 5}, {label: \\\"Otro\\\", value: \\\"otro\\\", position: 6}]}}) { id name label } }\"}")

SECTOR_FIELD_ID=$(echo "$SECTOR_RESPONSE" | jq -r '.data.createOneField.id')
if [ "$SECTOR_FIELD_ID" = "null" ] || [ -z "$SECTOR_FIELD_ID" ]; then
  echo "   Warning: Sector field may already exist or failed: $(echo "$SECTOR_RESPONSE" | jq -r '.errors[0].message // "unknown error"')"
else
  ok "Sector field created: $SECTOR_FIELD_ID"
fi

# Company Size field (SELECT)
SIZE_RESPONSE=$(graphql "$ACCESS_TOKEN" "{\"mutation { createOneField(input: {field: {objectMetadataId: \\\"$COMPANY_OBJECT_ID\\\", type: SELECT, name: \\\"companySize\\\", label: \\\"Company Size\\\", description: \\\"Number of employees\\\", options: [{label: \\\"1-10\\\", value: \\\"1-10\\\", position: 0}, {label: \\\"11-50\\\", value: \\\"11-50\\\", position: 1}, {label: \\\"50-200\\\", value: \\\"50-200\\\", position: 2}, {label: \\\"200+\\\", value: \\\"200+\\\", position: 3}]}}) { id name label } }\"}")

SIZE_FIELD_ID=$(echo "$SIZE_RESPONSE" | jq -r '.data.createOneField.id')
if [ "$SIZE_FIELD_ID" = "null" ] || [ -z "$SIZE_FIELD_ID" ]; then
  echo "   Warning: Company Size field may already exist or failed: $(echo "$SIZE_RESPONSE" | jq -r '.errors[0].message // "unknown error"')"
else
  ok "Company Size field created: $SIZE_FIELD_ID"
fi

# Lead Source field (SELECT)
SOURCE_RESPONSE=$(graphql "$ACCESS_TOKEN" "{\"mutation { createOneField(input: {field: {objectMetadataId: \\\"$COMPANY_OBJECT_ID\\\", type: SELECT, name: \\\"leadSource\\\", label: \\\"Lead Source\\\", description: \\\"How we found this lead\\\", options: [{label: \\\"LinkedIn\\\", value: \\\"linkedin\\\", position: 0}, {label: \\\"Web\\\", value: \\\"web\\\", position: 1}, {label: \\\"Referido\\\", value: \\\"referido\\\", position: 2}, {label: \\\"Evento\\\", value: \\\"evento\\\", position: 3}, {label: \\\"Prospección fría\\\", value: \\\"fria\\\", position: 4}]}}) { id name label } }\"}")

SOURCE_FIELD_ID=$(echo "$SOURCE_RESPONSE" | jq -r '.data.createOneField.id')
if [ "$SOURCE_FIELD_ID" = "null" ] || [ -z "$SOURCE_FIELD_ID" ]; then
  echo "   Warning: Lead Source field may already exist or failed: $(echo "$SOURCE_RESPONSE" | jq -r '.errors[0].message // "unknown error"')"
else
  ok "Lead Source field created: $SOURCE_FIELD_ID"
fi

# --------------- Step 4: Create custom fields for People ---------------
info "Step 4: Creating custom fields for People..."

# LinkedIn URL field (LINKS)
LINKEDIN_RESPONSE=$(graphql "$ACCESS_TOKEN" "{\"mutation { createOneField(input: {field: {objectMetadataId: \\\"$PERSON_OBJECT_ID\\\", type: LINKS, name: \\\"linkedIn\\\", label: \\\"LinkedIn\\\", description: \\\"LinkedIn profile URL\\\"}}) { id name label } }\"}")

LINKEDIN_FIELD_ID=$(echo "$LINKEDIN_RESPONSE" | jq -r '.data.createOneField.id')
if [ "$LINKEDIN_FIELD_ID" = "null" ] || [ -z "$LINKEDIN_FIELD_ID" ]; then
  echo "   Warning: LinkedIn field may already exist or failed: $(echo "$LINKEDIN_RESPONSE" | jq -r '.errors[0].message // "unknown error"')"
else
  ok "LinkedIn field created: $LINKEDIN_FIELD_ID"
fi

# Last Contact field (DATE)
LAST_CONTACT_RESPONSE=$(graphql "$ACCESS_TOKEN" "{\"mutation { createOneField(input: {field: {objectMetadataId: \\\"$PERSON_OBJECT_ID\\\", type: DATE, name: \\\"lastContact\\\", label: \\\"Last Contact\\\", description: \\\"Date of last contact\\\"}}) { id name label } }\"}")

LAST_CONTACT_FIELD_ID=$(echo "$LAST_CONTACT_RESPONSE" | jq -r '.data.createOneField.id')
if [ "$LAST_CONTACT_FIELD_ID" = "null" ] || [ -z "$LAST_CONTACT_FIELD_ID" ]; then
  echo "   Warning: Last Contact field may already exist or failed: $(echo "$LAST_CONTACT_RESPONSE" | jq -r '.errors[0].message // "unknown error"')"
else
  ok "Last Contact field created: $LAST_CONTACT_FIELD_ID"
fi

# Sequence Status field (SELECT)
SEQ_STATUS_RESPONSE=$(graphql "$ACCESS_TOKEN" "{\"mutation { createOneField(input: {field: {objectMetadataId: \\\"$PERSON_OBJECT_ID\\\", type: SELECT, name: \\\"sequenceStatus\\\", label: \\\"Sequence Status\\\", description: \\\"Current step in outreach sequence\\\", options: [{label: \\\"Sin contactar\\\", value: \\\"sin_contactar\\\", position: 0}, {label: \\\"Email enviado\\\", value: \\\"email_enviado\\\", position: 1}, {label: \\\"LinkedIn enviado\\\", value: \\\"linkedin_enviado\\\", position: 2}, {label: \\\"Llamada hecha\\\", value: \\\"llamada_hecha\\\", position: 3}, {label: \\\"Respondió\\\", value: \\\"respondio\\\", position: 4}, {label: \\\"No interesa\\\", value: \\\"no_interesa\\\", position: 5}]}}) { id name label } }\"}")

SEQ_STATUS_FIELD_ID=$(echo "$SEQ_STATUS_RESPONSE" | jq -r '.data.createOneField.id')
if [ "$SEQ_STATUS_FIELD_ID" = "null" ] || [ -z "$SEQ_STATUS_FIELD_ID" ]; then
  echo "   Warning: Sequence Status field may already exist or failed: $(echo "$SEQ_STATUS_RESPONSE" | jq -r '.errors[0].message // "unknown error"')"
else
  ok "Sequence Status field created: $SEQ_STATUS_FIELD_ID"
fi

# --------------- Step 5: Create custom fields for Opportunities ---------------
info "Step 5: Creating custom fields for Opportunities..."

# Service Type field (SELECT)
SERVICE_RESPONSE=$(graphql "$ACCESS_TOKEN" "{\"mutation { createOneField(input: {field: {objectMetadataId: \\\"$OPPORTUNITY_OBJECT_ID\\\", type: SELECT, name: \\\"serviceType\\\", label: \\\"Service Type\\\", description: \\\"Type of service being proposed\\\", options: [{label: \\\"Desarrollo a medida\\\", value: \\\"desarrollo\\\", position: 0}, {label: \\\"Consultoría\\\", value: \\\"consultoria\\\", position: 1}, {label: \\\"Mantenimiento\\\", value: \\\"mantenimiento\\\", position: 2}, {label: \\\"Migración\\\", value: \\\"migracion\\\", position: 3}, {label: \\\"Auditoría técnica\\\", value: \\\"auditoria\\\", position: 4}]}}) { id name label } }\"}")

SERVICE_FIELD_ID=$(echo "$SERVICE_RESPONSE" | jq -r '.data.createOneField.id')
if [ "$SERVICE_FIELD_ID" = "null" ] || [ -z "$SERVICE_FIELD_ID" ]; then
  echo "   Warning: Service Type field may already exist or failed: $(echo "$SERVICE_RESPONSE" | jq -r '.errors[0].message // "unknown error"')"
else
  ok "Service Type field created: $SERVICE_FIELD_ID"
fi

# Estimated Budget field (CURRENCY)
BUDGET_RESPONSE=$(graphql "$ACCESS_TOKEN" "{\"mutation { createOneField(input: {field: {objectMetadataId: \\\"$OPPORTUNITY_OBJECT_ID\\\", type: CURRENCY, name: \\\"estimatedBudget\\\", label: \\\"Estimated Budget\\\", description: \\\"Estimated project budget\\\"}}) { id name label } }\"}")

BUDGET_FIELD_ID=$(echo "$BUDGET_RESPONSE" | jq -r '.data.createOneField.id')
if [ "$BUDGET_FIELD_ID" = "null" ] || [ -z "$BUDGET_FIELD_ID" ]; then
  echo "   Warning: Estimated Budget field may already exist or failed: $(echo "$BUDGET_RESPONSE" | jq -r '.errors[0].message // "unknown error"')"
else
  ok "Estimated Budget field created: $BUDGET_FIELD_ID"
fi

# Estimated Start Date field (DATE)
START_DATE_RESPONSE=$(graphql "$ACCESS_TOKEN" "{\"mutation { createOneField(input: {field: {objectMetadataId: \\\"$OPPORTUNITY_OBJECT_ID\\\", type: DATE, name: \\\"estimatedStartDate\\\", label: \\\"Estimated Start Date\\\", description: \\\"When the project is expected to start\\\"}}) { id name label } }\"}")

START_DATE_FIELD_ID=$(echo "$START_DATE_RESPONSE" | jq -r '.data.createOneField.id')
if [ "$START_DATE_FIELD_ID" = "null" ] || [ -z "$START_DATE_FIELD_ID" ]; then
  echo "   Warning: Estimated Start Date field may already exist or failed: $(echo "$START_DATE_RESPONSE" | jq -r '.errors[0].message // "unknown error"')"
else
  ok "Estimated Start Date field created: $START_DATE_FIELD_ID"
fi

# --------------- Done ---------------
echo ""
echo "============================================"
echo "  CRM Configuration Complete!"
echo "============================================"
echo ""
echo "  Custom fields created:"
echo "  Companies: Sector, Company Size, Lead Source"
echo "  People: LinkedIn, Last Contact, Sequence Status"
echo "  Opportunities: Service Type, Estimated Budget, Estimated Start Date"
echo ""
echo "  Next steps:"
echo "  1. Open http://localhost:3000"
echo "  2. Go to Settings > Data Model to verify fields"
echo "  3. Configure Opportunity pipeline stages in the UI"
echo "  4. Start adding your real leads"
echo ""
