# Workspace

## Railway Deployment

Files added for Railway hosting:
- `main.py` — root entry point (`python main.py` from repo root)
- `requirements.txt` — Python dependencies for nixpacks
- `.python-version` — pins Python 3.11
- `railway.toml` — Railway build/deploy config (start command, restart policy)
- `.gitignore` — excludes `.db`, `node_modules`, Replit-specific files

**Important:** The bot uses SQLite (`bot/freelancer_bot.db`). On Railway, attach a **Volume** mounted at `/app/bot/` to persist data across restarts.

## Overview

pnpm workspace monorepo using TypeScript. Each package manages its own dependencies.
Additionally, this workspace hosts a **Telegram bot** for freelancers (`main.py`), built with Python/aiogram.

## Stack

- **Monorepo tool**: pnpm workspaces
- **Node.js version**: 24
- **Package manager**: pnpm
- **TypeScript version**: 5.9
- **API framework**: Express 5
- **Database**: PostgreSQL + Drizzle ORM (for TS apps); SQLite + aiosqlite (for Telegram bot)
- **Validation**: Zod (`zod/v4`), `drizzle-zod`
- **API codegen**: Orval (from OpenAPI spec)
- **Build**: esbuild (CJS bundle)
- **Python**: 3.11 + aiogram 3.13, aiosqlite, apscheduler

## Telegram Bot (FreelanceBot)

A Telegram bot for freelancers (Russian language) located in `bot/` and started via `main.py`.

### Features
- 💰 Income tracking — parses "логотип 15000" style messages
- 👥 Client management — name, contact, notes
- 📁 Project management — statuses: in_progress / completed / paid
- 📊 Analytics — monthly income, average check, project count
- 🔔 Reminders — deadlines and payment reminders (scheduled via APScheduler)
- 💳 Subscription system — 7-day free trial, paid plans (1/3/12 months via Telegram Stars)
- 🔐 Subscription middleware — checks every action for active subscription/trial

### Architecture

```
bot/
├── database/
│   └── db.py           # SQLite DB operations (users, clients, projects, incomes, reminders, payments)
├── handlers/
│   ├── start.py        # /start, /help, /status, main menu
│   ├── income.py       # Income tracking + quick text parsing
│   ├── clients.py      # Client management
│   ├── projects.py     # Project management with status changes
│   ├── analytics.py    # Analytics dashboard
│   ├── reminders.py    # Reminder creation/list
│   └── payment.py      # Telegram Stars payments, /buy, paywall
├── middlewares/
│   └── subscription.py # Subscription check middleware
├── services/
│   └── text_parser.py  # Natural language income parser
├── payments/           # Payment-related (stub USDT, etc.)
└── utils/
    └── scheduler.py    # APScheduler for reminder notifications
main.py                 # Bot entry point
```

### Running
- Workflow: `Telegram Bot` — runs `python3 main.py`
- Requires: `TELEGRAM_BOT_TOKEN` secret

### Subscription Plans (Telegram Stars)
- 1 month: 250 Stars
- 3 months: 640 Stars (−15%)
- 12 months: 2100 Stars (−30%)
- Free trial: 7 days

## Structure

```text
artifacts-monorepo/
├── artifacts/              # Deployable applications
│   └── api-server/         # Express API server
├── bot/                    # Telegram bot (Python)
├── lib/                    # Shared libraries
│   ├── api-spec/           # OpenAPI spec + Orval codegen config
│   ├── api-client-react/   # Generated React Query hooks
│   ├── api-zod/            # Generated Zod schemas from OpenAPI
│   └── db/                 # Drizzle ORM schema + DB connection
├── scripts/                # Utility scripts (single workspace package)
├── main.py                 # Telegram bot entry point
├── pnpm-workspace.yaml     # pnpm workspace
├── tsconfig.base.json      # Shared TS options
├── tsconfig.json           # Root TS project references
└── package.json            # Root package with hoisted devDeps
```

## TypeScript & Composite Projects

Every package extends `tsconfig.base.json` which sets `composite: true`. The root `tsconfig.json` lists all packages as project references. This means:

- **Always typecheck from the root** — run `pnpm run typecheck`
- **`emitDeclarationOnly`** — we only emit `.d.ts` files during typecheck
- **Project references** — when package A depends on package B, A's `tsconfig.json` must list B in its `references` array

## Root Scripts

- `pnpm run build` — runs `typecheck` first, then recursively runs `build` in all packages
- `pnpm run typecheck` — runs `tsc --build --emitDeclarationOnly` using project references

## Packages

### `artifacts/api-server` (`@workspace/api-server`)

Express 5 API server. Routes live in `src/routes/` and use `@workspace/api-zod` for validation and `@workspace/db` for persistence.

### `lib/db` (`@workspace/db`)

Database layer using Drizzle ORM with PostgreSQL.

### `lib/api-spec` (`@workspace/api-spec`)

Owns the OpenAPI 3.1 spec (`openapi.yaml`) and Orval config.

### `lib/api-zod` (`@workspace/api-zod`)

Generated Zod schemas from the OpenAPI spec.

### `lib/api-client-react` (`@workspace/api-client-react`)

Generated React Query hooks and fetch client.

### `scripts` (`@workspace/scripts`)

Utility scripts package.
