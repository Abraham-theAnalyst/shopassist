from fastapi import FastAPI

app = FastAPI(title="ShopAssist")


@app.get("/health")
def health():
    return {"status": "ok", "service": "shopassist"}
