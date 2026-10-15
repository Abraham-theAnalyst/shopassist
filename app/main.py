from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.routers import auth, conversations

app = FastAPI(title="ShopAssist")


@app.exception_handler(RequestValidationError)
def validation_error_handler(request: Request, exc: RequestValidationError):
    # FastAPI's default 422 response echoes back the invalid value, which
    # could be a password. Send the error details without the "input".
    errors = [{k: v for k, v in e.items() if k != "input"} for e in exc.errors()]
    return JSONResponse(status_code=422, content={"detail": jsonable_encoder(errors)})


app.include_router(auth.router)
app.include_router(conversations.router)


@app.get("/health")
def health():
    return {"status": "ok", "service": "shopassist"}
