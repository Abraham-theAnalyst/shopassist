# ShopAssist: Milestone 1 Spec

## Goal
A backend API for an e-commerce customer support chatbot. Users can register,
log in, start conversations, and chat with an AI support assistant. All
conversations and messages are saved in PostgreSQL. Runs locally with Docker Compose.

## In scope
- User registration and login with JWT
- Protected conversation and chat endpoints
- AI replies from OpenRouter (currently the free model router, openrouter/free),
  acting as a support assistant for a store
- Conversations and messages stored in PostgreSQL
- Docker Compose setup (API + database)
- Pytest tests and a short README

## Out of scope (later milestones)
Knowledge base, admin dashboard, file uploads, frontend, refresh tokens,
streaming replies, deployment.

## Tech
- Python 3.13 (inside Docker), FastAPI, Pydantic
- PostgreSQL 16, SQLAlchemy 2.0, Alembic for migrations
- Password hashing: a well-maintained library (pwdlib with Argon2, or bcrypt)
- JWT: PyJWT
- AI: OpenRouter, called through the openai Python library as an
  OpenAI-compatible client, behind a provider-agnostic AI layer so another
  provider (such as Anthropic) can be added without changing the endpoints
- Config: pydantic-settings reading from a .env file
- Tests: Pytest with FastAPI's TestClient

## Configuration (.env)
DATABASE_URL, JWT_SECRET_KEY, JWT_EXPIRE_MINUTES (default 30),
AI_PROVIDER (default "openrouter"), AI_MODEL (e.g. openrouter/free),
AI_BASE_URL (https://openrouter.ai/api/v1), OPENROUTER_API_KEY,
AI_TIMEOUT_SECONDS (default 30), AI_MAX_TOKENS (default 500), STORE_NAME.
- .env must be in .gitignore and never committed.
- Commit a .env.example with placeholder values.

## Data model
users
- id (PK), email (unique, required), hashed_password (required), created_at

conversations
- id (PK), user_id (FK to users.id, required), title (nullable), created_at

messages
- id (PK), conversation_id (FK to conversations.id, required)
- role ("user" or "assistant"), content (text), created_at

Relationships: a user has many conversations; a conversation has many messages.

## Endpoints
Public
- GET  /health                        returns {"status": "ok"}
- POST /auth/register                 body: email, password; returns user (no password)
- POST /auth/login                    body: email, password; returns access_token

Protected (require "Authorization: Bearer <token>")
- POST /conversations                 create a conversation; returns it
- GET  /conversations                 list the current user's conversations
- GET  /conversations/{id}/messages   list messages in a conversation, oldest first
- POST /conversations/{id}/messages   body: content; saves the user message,
                                      calls the AI, saves and returns the reply

## Rules
- Passwords are hashed, never stored or returned as plain text.
- Password minimum length: 8 characters. Email must be valid format.
- Registering an existing email returns 400.
- Wrong email or password returns 401 with the same message for both
  (do not reveal which one was wrong).
- Users can only access their own conversations. Accessing another user's
  conversation returns 404.
- Message content: required, max 2000 characters.
- When calling the AI, send the system prompt plus the last 20 messages
  of the conversation as history.
- If the AI call fails, return 502 with a friendly error and do not save
  an assistant message.
- The API key and JWT secret must never appear in logs or responses.

## AI system prompt
The assistant is a friendly customer support agent for {STORE_NAME}, an
online store. It helps with questions about orders, shipping, returns,
payments, and products. It must not invent order details, prices, or
policies; when it doesn't know, it says so and suggests contacting the
store's support team. Replies are short and clear.

## Project structure
app/
  main.py
  core/        config.py, security.py (hashing, JWT)
  db/          session.py, base.py
  models/      user.py, conversation.py, message.py
  schemas/     Pydantic request and response models
  routers/     auth.py, conversations.py
  services/    ai.py (all AI provider calls live here)
  dependencies.py   get_db, get_current_user
alembic/
tests/
docker-compose.yml, Dockerfile, requirements.txt, .env.example, README.md

## Tests (minimum)
1. Register succeeds; registering the same email again returns 400
2. Login with wrong password returns 401
3. Protected endpoint without a token returns 401
4. A user cannot read another user's conversation (404)
5. Sending a message saves both messages and returns the reply
   (mock the AI service; tests must not call the real API)

## Build order (one slice at a time)
1. Project skeleton, /health, Dockerfile, Docker Compose with PostgreSQL
2. Database models and the first Alembic migration
3. Register and login
4. get_current_user dependency and a protected test route
5. Conversation endpoints
6. AI service and the send message endpoint
7. Tests
8. README

## Done when
- docker compose up starts the API and database with no errors
- All endpoints work from the Swagger page at /docs
- All tests pass
- README explains what it is, how to set up .env, and how to run it and the tests