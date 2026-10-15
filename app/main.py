import logging

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, RedirectResponse

from app.routers import auth, conversations

# Show INFO logs from our own modules (e.g. which AI model answered)
logging.basicConfig(level=logging.INFO, format="%(levelname)s:     %(name)s: %(message)s")
# httpx (used by the openai library) would otherwise log every request it makes
logging.getLogger("httpx").setLevel(logging.WARNING)

app = FastAPI(title="ShopAssist")


@app.exception_handler(RequestValidationError)
def validation_error_handler(request: Request, exc: RequestValidationError):
    # FastAPI's default 422 response echoes back the invalid value, which
    # could be a password. Send the error details without the "input".
    errors = [{k: v for k, v in e.items() if k != "input"} for e in exc.errors()]
    return JSONResponse(status_code=422, content={"detail": jsonable_encoder(errors)})


app.include_router(auth.router)
app.include_router(conversations.router)


# Visiting the base URL opens the Swagger page. Hidden from the docs themselves.
@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse(url="/docs")


@app.get("/health")
def health():
    return {"status": "ok", "service": "shopassist"}
