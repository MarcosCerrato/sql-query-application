"""Answer service: generate a natural-language response from SQL results via Ollama."""
import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from schemas import AnswerRequest
from service import build_prompt

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["POST", "GET"],
    allow_headers=["Content-Type"],
)


@app.post("/answer")
async def answer(req: AnswerRequest):
    if not req.rows:
        return {"answer": "The query returned no results."}

    prompt = build_prompt(req.question, req.sql, req.rows)

    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(
            f"{settings.ollama_url}/api/generate",
            json={"model": settings.model, "prompt": prompt, "stream": False},
        )
        if resp.status_code != 200:
            raise HTTPException(status_code=502, detail="Ollama error: " + resp.text)
        answer_text = resp.json().get("response", "").strip()

    if answer_text.startswith("NOT_APPLICABLE"):
        return {"answer": "I can only answer questions about the available sales data."}

    return {"answer": answer_text}


@app.get("/health")
def health():
    return {"status": "ok"}
