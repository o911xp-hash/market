import uuid
from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
import os

from database import get_db, init_db, Product, CartItem
from concierge import chat, get_cart_impl, clear_cart_impl
from seed import seed

app = FastAPI(title="Retail Concierge API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory conversation history per session
sessions: dict[str, list] = {}


@app.on_event("startup")
def startup():
    init_db()
    seed()


# ── Models ──────────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None


class ChatResponse(BaseModel):
    reply: str
    session_id: str
    cart: dict


class CartClearRequest(BaseModel):
    session_id: str


# ── Routes ───────────────────────────────────────────────────────────────────

@app.post("/api/chat", response_model=ChatResponse)
def handle_chat(req: ChatRequest, db: Session = Depends(get_db)):
    session_id = req.session_id or str(uuid.uuid4())
    history = sessions.get(session_id, [])

    reply, updated_history = chat(req.message, history, db, session_id)
    sessions[session_id] = updated_history

    cart = get_cart_impl(db, session_id)
    return ChatResponse(reply=reply, session_id=session_id, cart=cart)


@app.get("/api/cart/{session_id}")
def get_cart(session_id: str, db: Session = Depends(get_db)):
    return get_cart_impl(db, session_id)


@app.delete("/api/cart/{session_id}")
def clear_cart(session_id: str, db: Session = Depends(get_db)):
    sessions.pop(session_id, None)
    return clear_cart_impl(db, session_id)


@app.get("/api/catalog")
def get_catalog(db: Session = Depends(get_db)):
    products = db.query(Product).filter(Product.in_stock == True).all()
    return [
        {
            "id": p.id,
            "name": p.name,
            "category": p.category,
            "price": p.price,
            "unit": p.unit,
            "tags": p.tags,
            "description": p.description,
        }
        for p in products
    ]


# Serve frontend
FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend")

@app.get("/")
def root():
    return FileResponse(os.path.join(FRONTEND_DIR, "index.html"))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
