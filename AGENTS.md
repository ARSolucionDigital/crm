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

## Environment

- Node: `^24.5.0`, Yarn: `>=4.0.2` (use `yarn`, never `npm`)
- `.env` files copied from `.env.example` via `npx nx reset:env <package>`
- Postgres on `localhost:5432`, Redis on `localhost:6379`
- MCP servers: Postgres (read-only), Playwright, Context7
