# ShopAssist

ShopAssist is the backend for an online store's customer support chatbot. Customers create an account, log in, open a conversation and ask questions about orders, shipping, returns, payments and products. An AI assistant replies, and every conversation is saved in PostgreSQL. It is built for small online stores that want an AI support assistant they can run themselves, and it is designed so the AI provider can be swapped without touching the rest of the code. This repository is the first milestone: a working, tested REST API that runs locally with Docker Compose.

## Features

- Account registration and login, with passwords hashed using Argon2
- JWT access tokens that protect every conversation endpoint
- Conversations that belong to one user and are invisible to everyone else
- AI replies that use the last 20 messages of the conversation as context
- A system prompt that keeps the assistant on support topics and tells it not to invent order details, prices or policies
- A provider-agnostic AI layer, currently connected to OpenRouter
- Clear error responses when the AI is slow, rate limited or unavailable
- Database migrations with Alembic
- Interactive API documentation (Swagger UI) at `/docs`
- An automated test suite that uses its own database and a fake AI, so it never touches real data or makes real AI calls

## Roadmap

These are planned for later milestones and are **not** built yet:

- **Knowledge base:** answer questions from the store's own policies, FAQs and product information
- **Admin dashboard:** let store staff review conversations
- **File uploads:** let customers attach files such as photos of a damaged item
- **Chat interface:** a web frontend for customers (today the API is used through Swagger UI or any HTTP client)
- **Deployment:** a public instance. The app is prepared for Render and Neon (see [Deployment](#deployment)) but is not live yet.

## Tech stack

| Area | Tools |
|---|---|
| Language | Python 3.13 |
| Web framework | FastAPI, Pydantic |
| Database | PostgreSQL 16, SQLAlchemy 2.0, Alembic |
| Authentication | PyJWT (HS256), pwdlib with Argon2 |
| AI | OpenRouter through the `openai` Python library (OpenAI-compatible API) |
| Configuration | pydantic-settings, read from environment variables or a `.env` file |
| Testing | Pytest, FastAPI TestClient |
| Containers | Docker, Docker Compose |

## Architecture

```mermaid
flowchart LR
    Client["Client<br/>(Swagger UI, curl, future chat UI)"]
    API["FastAPI app<br/>auth, conversations, messages"]
    DB[("PostgreSQL 16<br/>users, conversations, messages")]
    AILayer["AI provider layer<br/>app/services/ai.py"]
    OpenRouter["OpenRouter"]

    Client -- "HTTP + JWT" --> API
    API -- "SQLAlchemy" --> DB
    API -- "generate_reply()" --> AILayer
    AILayer -- "OpenAI-compatible API" --> OpenRouter
```

When a user sends a message, the API checks the token, confirms the conversation belongs to that user, saves the message, sends the system prompt and the last 20 messages to the AI layer, saves the reply and returns it.

### Project structure

```
app/
  main.py            FastAPI app, routers, error handling, logging
  core/              settings (config.py), hashing and JWT (security.py)
  db/                SQLAlchemy base and session
  models/            User, Conversation, Message
  schemas/           Pydantic request and response models
  routers/           auth.py, conversations.py
  services/          ai.py (all AI provider calls), prompts.py (system prompt)
  dependencies.py    get_db, get_current_user, get_user_conversation
alembic/             database migrations
tests/               Pytest suite
```

## Security and design decisions

**Password hashing.** Passwords are hashed with Argon2 (through pwdlib) and never stored in plain text. Passwords must be 8 to 128 characters. The upper limit stops someone from sending a huge password to slow the server down.

**Login errors that don't reveal accounts.** A wrong password and an unknown email return the same `401` with the same message. When the email doesn't exist, the server still checks the password against a dummy Argon2 hash, so both cases take about the same time and response timing can't be used to find out which emails are registered. Emails are stored in lowercase, so `Alice@Example.com` and `alice@example.com` are the same account.

**JWT verification.** Tokens are signed with HS256, and only HS256 is accepted when verifying, so a token can't switch to a weaker algorithm or to `none`. Every token must contain an expiry (`exp`) and a user id (`sub`). After the signature and expiry are checked, the user is loaded from the database, so a token for a deleted user stops working. Every failure (missing token, bad signature, expired token, deleted user) returns the same `401` with a `WWW-Authenticate: Bearer` header.

**Ownership checks.** One shared dependency, `get_user_conversation`, looks up a conversation by its id and the current user's id in a single query. A conversation that doesn't exist and one that belongs to someone else both return the same `404`, so users can't discover other users' conversation ids.

**Passwords never echoed or logged.** API responses use explicit schemas, so the password hash is never returned. FastAPI's default validation error normally repeats the invalid input back to the client; ShopAssist removes that value, so a rejected password isn't sent back. The app never logs passwords, hashes, message content, the JWT secret or the API key.

**Provider-agnostic AI layer.** All AI calls go through `generate_reply()` in `app/services/ai.py`. The endpoints don't know which provider is behind it. Adding another provider, such as Anthropic, means writing one function with the same inputs and output and registering it under a new `AI_PROVIDER` name.

**AI failure handling.** Timeouts, connection errors, rate limits, provider errors and empty replies all return `502` with a friendly message, and no assistant message is saved. The user's message is kept, so the conversation history stays accurate. Automatic retries are turned off so a failing request doesn't multiply the wait time or use up the free tier's daily limit. The logs record which model answered, or the type of error, but never the conversation text.

**Configuration and secrets.** All credentials come from environment variables. `.env` is listed in both `.gitignore` and `.dockerignore`, so it is never committed or copied into an image. The test container blanks the AI key, so tests can't reach OpenRouter even by mistake.

## Setup

### Prerequisites

- [Docker](https://docs.docker.com/get-docker/) with Docker Compose v2 (the `docker compose` command)
- Git
- An OpenRouter account for AI replies (free, see below). Everything else works without it.

### 1. Clone the repository

```bash
git clone https://github.com/Techy-Pabs/shopassist.git
cd shopassist
```

### 2. Create your `.env` file

```bash
cp .env.example .env
```

Then open `.env` and fill in real values. At minimum, change `POSTGRES_PASSWORD` (and the matching password inside `DATABASE_URL`), set `JWT_SECRET_KEY` and set `OPENROUTER_API_KEY`.

To generate a strong `JWT_SECRET_KEY`, run either of these:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(64))"
docker run --rm python:3.13-slim python -c "import secrets; print(secrets.token_urlsafe(64))"
```

### Environment variables

| Variable | Required | Default | What it does |
|---|---|---|---|
| `POSTGRES_USER` | Yes | | Database user that PostgreSQL creates on first start |
| `POSTGRES_PASSWORD` | Yes | | Password for that user |
| `POSTGRES_DB` | Yes | | Name of the database PostgreSQL creates on first start |
| `DATABASE_URL` | Yes | | How the API connects to the database. The user, password and database name must match the three values above, and the host is `db` (the database service's name in Docker Compose). Format: `postgresql+psycopg://USER:PASSWORD@db:5432/DB` |
| `JWT_SECRET_KEY` | Yes | | Secret used to sign login tokens. Use a long random value and keep it private. |
| `JWT_EXPIRE_MINUTES` | No | `30` | How long a login token stays valid |
| `STORE_NAME` | No | `ShopAssist` | Store name used in the assistant's system prompt |
| `AI_PROVIDER` | No | `openrouter` | Which AI provider to use. `openrouter` is the only one available today. |
| `AI_MODEL` | Yes | | Model to request from the provider. `openrouter/free` lets OpenRouter pick a free model for each request. |
| `AI_BASE_URL` | No | `https://openrouter.ai/api/v1` | Address of the provider's API |
| `OPENROUTER_API_KEY` | For AI replies | | Your OpenRouter key. Without it the app still runs, but sending a message returns `502`. |
| `AI_TIMEOUT_SECONDS` | No | `30` | How long to wait for an AI reply before giving up |
| `AI_MAX_TOKENS` | No | `500` | Upper limit on the length of each AI reply |

PostgreSQL only reads `POSTGRES_USER`, `POSTGRES_PASSWORD` and `POSTGRES_DB` the first time it creates its data. If you change them later, reset the database with `docker compose down -v` (this deletes all data) and start again.

### Getting a free OpenRouter key

1. Create an account at [openrouter.ai](https://openrouter.ai).
2. Go to [openrouter.ai/keys](https://openrouter.ai/keys) and create a key.
3. Paste it into `.env` as `OPENROUTER_API_KEY`.

With `AI_MODEL=openrouter/free` there is no cost. Free models have a daily request limit (50 requests a day at the time of writing), and the model that answers can change from one request to the next.

## Running the app

Start the API and the database in the background:

```bash
docker compose up -d --build
```

The API container applies any pending database migrations each time it starts, then starts the server. If a migration fails, the container stops instead of running against a half-updated database. You can also apply migrations by hand:

```bash
docker compose exec api alembic upgrade head
```

Check that the API is running:

```bash
curl http://localhost:8000/health
```

You should see `{"status":"ok","service":"shopassist"}`.

Other useful commands:

```bash
docker compose logs -f api   # follow the API logs
docker compose down          # stop everything (your data is kept)
docker compose down -v       # stop everything and delete the database
```

### Using the API in Swagger UI

Open [http://localhost:8000/docs](http://localhost:8000/docs).

1. Use **POST /auth/register** to create an account (**Try it out**, fill in the body, **Execute**).
2. Use **POST /auth/login** with the same details and copy the `access_token` from the response.
3. Click **Authorize** at the top right, paste the token (without the word `Bearer`) and confirm.
4. Create a conversation with **POST /conversations**, then send messages with **POST /conversations/{conversation_id}/messages**.

Tokens expire after `JWT_EXPIRE_MINUTES`. If requests start returning `401`, log in again and paste the new token.

## Running the tests

```bash
docker compose run --rm --build tests
```

This builds a test image, starts the database if it isn't running, and runs the full suite. For one line per test:

```bash
docker compose run --rm --build tests pytest -v
```

The tests:

- run in a separate database (your database name plus `_test`, for example `shopassist_test`), which is created automatically and emptied before every test, so your development data is never touched
- replace the AI with a fake, so no test makes a real network call
- cover registration, login, token checks, `/auth/me`, conversation ownership, sending messages, the 20-message history limit, AI failures and input validation

Test tools (`requirements-dev.txt`) are only installed in the test image, not in the image the API runs from.

## Deployment

ShopAssist is set up to run on [Render](https://render.com) (the API, as a Docker web service) with [Neon](https://neon.tech) (the PostgreSQL database). Both have free tiers. Docker Compose is only used for local development; in production the API runs on its own and connects to Neon over the internet.

### How the production container starts

The default build target in the `Dockerfile` is the production image. When it starts, it runs `scripts/start.sh`, which:

1. applies database migrations with `alembic upgrade head`, and stops the container if they fail
2. starts uvicorn on `0.0.0.0`, on the port in the `PORT` environment variable (Render sets this automatically; it defaults to `8000` locally)

Running migrations on startup means no separate migration step is needed, which matters because Render's free tier has no pre-deploy command or shell access.

### 1. Create the database on Neon

1. Create a Neon project. PostgreSQL 16 matches the local setup.
2. Open **Connect** on the project dashboard and copy the connection string. Turn off connection pooling first, so you get the direct connection (the host name won't contain `-pooler`). Neon recommends direct connections for running migrations, and this app runs them on every start.

The string looks like this:

```
postgresql://USER:PASSWORD@ep-example-123456.REGION.aws.neon.tech/neondb?sslmode=require&channel_binding=require
```

Use it exactly as Neon gives it. The app switches `postgresql://` to the `psycopg` driver automatically and keeps `sslmode=require` and `channel_binding=require`, so the connection is encrypted.

### 2. Create the web service on Render

1. In Render, choose **New**, then **Web Service**, and connect the GitHub repository.
2. Set the language to **Docker**. Render finds the `Dockerfile` in the project root and builds the production image.
3. Choose the **Free** instance type.
4. Under **Advanced**, set the health check path to `/health`.
5. Add the environment variables below, then create the service.

The tables are created on the first start, when the container runs the migrations. After that, every push to the connected branch triggers a new build and deploy.

### Production environment variables

| Variable | Required | What to set |
|---|---|---|
| `DATABASE_URL` | Yes | The Neon connection string from step 1, unchanged |
| `JWT_SECRET_KEY` | Yes | A new long random value. Don't reuse your local one. |
| `AI_MODEL` | Yes | `openrouter/free`, or another OpenRouter model |
| `OPENROUTER_API_KEY` | Yes | Your OpenRouter key |
| `JWT_EXPIRE_MINUTES` | No | Defaults to `30` |
| `STORE_NAME` | No | Defaults to `ShopAssist` |
| `AI_PROVIDER` | No | Defaults to `openrouter` |
| `AI_BASE_URL` | No | Defaults to `https://openrouter.ai/api/v1` |
| `AI_TIMEOUT_SECONDS` | No | Defaults to `30` |
| `AI_MAX_TOKENS` | No | Defaults to `500` |

Not needed in production:
- `POSTGRES_USER`, `POSTGRES_PASSWORD` and `POSTGRES_DB` only configure the local database container.
- `PORT` is set by Render.

### Free tier behaviour

- **Cold starts.** A free Render service goes to sleep after 15 minutes without requests. The next request wakes it up, which takes about a minute, so the first call after a quiet period is slow. Requests are fast again once it's awake.
- **Idle database.** Neon's free tier also pauses the database when it's idle and resumes it on the next query, which adds a short delay. Connections that Neon closed while idle are detected and replaced automatically (SQLAlchemy's `pool_pre_ping`), so they don't cause errors.

A live link will be added here once the app is deployed.

## API endpoints

| Method | Path | Auth | Description | Responses |
|---|---|---|---|---|
| GET | `/health` | No | Health check | `200` |
| POST | `/auth/register` | No | Create an account. Body: `email`, `password` | `201` user, `400` email taken, `422` invalid input |
| POST | `/auth/login` | No | Log in. Body: `email`, `password` | `200` access token, `401` wrong email or password |
| GET | `/auth/me` | Yes | The logged-in user | `200`, `401` |
| POST | `/conversations` | Yes | Start a conversation. Optional body: `title` | `201`, `401` |
| GET | `/conversations` | Yes | Your conversations, newest first | `200`, `401` |
| GET | `/conversations/{conversation_id}/messages` | Yes | Messages in a conversation, oldest first | `200`, `401`, `404` |
| POST | `/conversations/{conversation_id}/messages` | Yes | Send a message and get the AI's reply. Body: `content` (1 to 2000 characters) | `201` reply, `401`, `404`, `422`, `502` AI unavailable |

"Auth: Yes" means the request needs an `Authorization: Bearer <token>` header. User responses contain only `id`, `email` and `created_at`.

## Screenshots and demo

_Coming soon._

- Screenshot: Swagger UI with the endpoint list
- Screenshot: a conversation with AI replies
- Demo video: registering, logging in and chatting with the assistant

## Current limitations

- Login tokens can't be revoked before they expire, and there are no refresh tokens yet.
- There is no rate limiting on login or messages.
- Replies are returned in one piece, not streamed.
- On the free OpenRouter tier, the daily request limit applies and reply quality varies with the model OpenRouter picks.
