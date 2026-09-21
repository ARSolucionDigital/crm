# Twenty CRM — Agent Guidelines

## Quick Commands

```bash
yarn start                              # Start everything (front + server + worker)
npx nx start twenty-front               # Frontend dev server -> localhost:3001
npx nx start twenty-server              # Backend -> localhost:3000
npx nx run twenty-server:worker         # Background worker (BullMQ)
bash packages/twenty-utils/setup-dev-env.sh  # First-time setup (Postgres + Redis + .env)
bash packages/twenty-utils/setup-dev-env.sh --reset  # Wipe data and restart
```

## Build Order

`twenty-shared` must be built before anything that depends on it:

```bash
npx nx build twenty-shared
npx nx build twenty-ui     # depends on twenty-shared
npx nx build twenty-front   # depends on twenty-shared, twenty-ui
npx nx build twenty-server  # depends on twenty-shared
```

All `build`, `start`, `test`, `typecheck`, and `lint` targets have `dependsOn: ["^build"]` in nx.json, so Nx handles this automatically. Manual builds only needed when you change `twenty-shared` or `twenty-ui` and want to avoid full rebuild.

## Verification (run after changes)

```bash
npx nx lint:diff-with-main twenty-front   # Fast: only changed files vs main
npx nx lint:diff-with-main twenty-server
npx nx lint:diff-with-main twenty-front --configuration=fix  # Auto-fix
npx nx typecheck twenty-front
npx nx typecheck twenty-server
npx nx test twenty-front                  # Jest unit tests
npx nx test twenty-server
```

Run a single test file:
```bash
cd packages/twenty-front && npx jest path/to/test.test.ts --config=packages/twenty-front/jest.config.mjs
cd packages/twenty-server && npx jest path/to/test.test.ts --config=packages/twenty-server/jest.config.mjs
```

Integration tests (server only, resets DB first):
```bash
npx nx run twenty-server:test:integration:with-db-reset
```

## Database

```bash
npx nx database:reset twenty-server                    # Truncate + init + seed
npx nx database:reset twenty-server --configuration=no-seed  # No seed data
npx nx run twenty-server:database:init:prod            # Init schema
npx nx run twenty-server:database:migrate:prod         # Run instance commands
npx nx run twenty-server:database:migrate:generate --name <name> --type <fast|slow>  # Generate migration
```

- Entity changes require generating an **instance command** via `database:migrate:generate`
- **Fast** = schema changes only; **slow** = includes `runDataMigration` step for data backfills
- Commands use `@RegisteredInstanceCommand` / `@RegisteredWorkspaceCommand` decorators
- Never delete or rewrite committed instance command `up`/`down` logic
- MCP Postgres server (`.mcp.json`) is read-only — use for inspection, not writes

## GraphQL

```bash
npx nx run twenty-front:graphql:generate              # Data types (codegen.cjs)
npx nx run twenty-front:graphql:generate --configuration=metadata  # Metadata types
```

Run after any GraphQL schema changes before typecheck.

## Storybook

```bash
npx nx storybook:build twenty-front
npx nx storybook:test twenty-front
```

## Code Conventions

- **Functional components only** — no class components
- **Named exports only** — no default exports
- **Types over interfaces** (except when extending third-party types)
- **String literals over enums** (except for GraphQL enums)
- **No `any` type** — strict TypeScript enforced
- **No abbreviations** in variable names (`user` not `u`)
- Use `isDefined()`, `isNonEmptyString()`, `isNonEmptyArray()` from `twenty-shared` instead of manual guards
- Styling: **Linaria** (zero-runtime CSS-in-JS), `styled()` pattern
- State: **Jotai** for global state (atoms, selectors, atom families)
- i18n: **Lingui** — run `lingui:extract` then `lingui:compile` after adding new messages

## Package Boundaries

| Package | Purpose |
|---|---|
| `twenty-front` | React app (Vite, Jotai, Apollo, Linaria) |
| `twenty-server` | NestJS API (GraphQL Yoga, TypeORM, BullMQ) |
| `twenty-ui` | Shared UI component library |
| `twenty-shared` | Common types/utils — **build first** |
| `twenty-emails` | Email templates (React Email) |
| `twenty-oxlint-rules` | Custom oxlint rules — lint depends on this |
| `twenty-client-sdk` | Client SDK for apps |
| `twenty-sdk` | Server SDK |
| `twenty-cli` | CLI tool |
| `create-twenty-app` | App scaffolding |
| `twenty-e2e-testing` | Playwright E2E tests |
| `twenty-utils` | Utility scripts |
| `twenty-docs` | Documentation |
| `twenty-companion` | Companion application |
| `twenty-zapier` | Zapier integration |
| `twenty-claude-skills` | Claude AI skills |
| `twenty-docker` | Docker configurations |

## Environment

- Node: `^24.5.0`, Yarn: `>=4.0.2` (use `yarn`, never `npm`)
- `.env` files copied from `.env.example` via `npx nx reset:env <package>`
- Postgres on `localhost:5432`, Redis on `localhost:6379`
- MCP servers: Postgres (read-only), Playwright, Context7

## Testing

### Unit Tests
```bash
npx nx test twenty-front
npx nx test twenty-server
```

### E2E Tests
```bash
npx nx run twenty-e2e-testing:test
```

### Storybook Tests
```bash
npx nx storybook:test twenty-front
```

## Deployment

### Production Server
- **URL:** https://crm.arsoluciondigital.com
- **Server:** Hetzner `root@2.29.38.181` (SSH key: `~/.ssh/crm_hetzner`)
- **Stack:** Docker Compose (server, worker, Postgres 16, Redis)
- **SSL:** Let's Encrypt auto-renewal

### Deploy (from local machine)
```bash
# Dispatch the reviewed main branch through GitHub Actions (requires gh auth)
bash scripts/deploy.sh twenty
# BookStack is an independent, manual workflow
bash scripts/deploy.sh bookstack
```

The workflow builds an image identified by the Git SHA, publishes it, creates a
backup, deploys over SSH, checks health, and records rollback state. The local
script never stages files, creates commits, or pushes the current worktree.

### Server-side deploy script
```bash
# Managed scripts installed without restarting services
ssh -i ~/.ssh/crm_hetzner root@2.29.38.181 "ls -la /opt/twenty-crm/managed/production"
ssh -i ~/.ssh/crm_hetzner root@2.29.38.181 "ls -la /opt/twenty-crm/managed/bookstack"
```

### Production Builds
```bash
npx nx build twenty-front --configuration=production
npx nx build twenty-server --configuration=production
```

### Docker
```bash
docker build -f packages/twenty-docker/twenty/Dockerfile --target twenty -t twenty-local:dev .
```

## Server Management

### Quick SSH
```bash
ssh -i ~/.ssh/crm_hetzner root@2.29.38.181
```

### Containers
```bash
ssh -i ~/.ssh/crm_hetzner root@2.29.38.181 "cd /opt/twenty-crm && docker compose ps"
ssh -i ~/.ssh/crm_hetzner root@2.29.38.181 "cd /opt/twenty-crm && docker compose logs --tail=50 server"
ssh -i ~/.ssh/crm_hetzner root@2.29.38.181 "cd /opt/twenty-crm && docker compose restart server worker"
```

### Backups
```bash
# Server backups (auto daily at 2AM, keeps 7 daily + 4 weekly)
ssh -i ~/.ssh/crm_hetzner root@2.29.38.181 "ls -lh /opt/twenty-crm/backups/"

# Download latest backup to local ~/Desktop/twenty-backups/
bash scripts/download-backup.sh
```

### Database (on server)
```bash
# Direct psql on server
ssh -i ~/.ssh/crm_hetzner root@2.29.38.181 "docker compose -f /opt/twenty-crm/docker-compose.yml exec -T db psql -U postgres -d default"
```

## Security

- **SSH:** Key-only auth, fail2ban active, root login via key only
- **Nginx:** Security headers, rate limiting (API: 10r/s, Auth: 5r/m), server_tokens off
- **Docker:** Port 3000 bound to localhost only, resource limits per container
- **Auto-updates:** unattended-upgrades enabled for security patches
- **Firewall:** UFW (22, 80, 443 only)

## CI/CD

The project uses Nx for managing the monorepo and follows standard CI/CD practices:
- Linting and type checking on all commits
- Unit tests run on pull requests
- Integration tests run on main branch
- Storybook deployment on release
- Automated dependency updates through Dependabot

## Performance Optimization

- Code splitting and lazy loading in frontend
- Caching strategies for API responses
- Database query optimization
- Background job processing with BullMQ
