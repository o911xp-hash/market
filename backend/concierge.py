import json
import os
import re
from typing import Optional
import anthropic
from sqlalchemy.orm import Session
from database import Product, CartItem


_api_key = os.environ.get("ANTHROPIC_API_KEY", "")
client = anthropic.Anthropic(api_key=_api_key) if _api_key else None

TOOLS = [
    {
        "name": "search_products",
        "description": (
            "Поиск товаров в каталоге магазина. "
            "Используй для поиска продуктов по названию, категории или тегам."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Строка поиска по названию или описанию (необязательно)",
                },
                "category": {
                    "type": "string",
                    "description": "Фильтр по категории: Молочные продукты, Крупы, Хлеб, Яйца, Фрукты, Ягоды, Напитки, Орехи, Овощи, Рыба, Мясо и др.",
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Фильтр по тегам: безлактозный, веганский, завтрак, обед, белок, безглютеновый",
                },
                "max_price": {
                    "type": "number",
                    "description": "Максимальная цена товара в рублях",
                },
            },
            "required": [],
        },
    },
    {
        "name": "add_to_cart",
        "description": "Добавить товар в корзину покупателя.",
        "input_schema": {
            "type": "object",
            "properties": {
                "product_id": {
                    "type": "integer",
                    "description": "ID товара из каталога",
                },
                "quantity": {
                    "type": "integer",
                    "description": "Количество единиц товара (по умолчанию 1)",
                    "default": 1,
                },
            },
            "required": ["product_id"],
        },
    },
    {
        "name": "get_cart",
        "description": "Получить текущее содержимое корзины и итоговую сумму.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
    {
        "name": "clear_cart",
        "description": "Очистить корзину полностью.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
]

SYSTEM_PROMPT = """Ты — умный консьерж-помощник для продуктового магазина.
Покупатель описывает, что хочет купить (например: «собери безлактозный завтрак до 1500 руб»),
а ты подбираешь подходящие товары из каталога и добавляешь их в корзину.

Правила работы:
1. Сначала найди подходящие товары через search_products
2. Выбери разумный набор с учётом бюджета и предпочтений
3. Добавь каждый выбранный товар в корзину через add_to_cart
4. После добавления всех товаров покажи итог корзины через get_cart
5. Кратко объясни свой выбор покупателю на русском языке
6. Не добавляй товары, которые не соответствуют требованиям (напр., продукты с лактозой при запросе «безлактозный»)
7. Следи за бюджетом — не превышай указанную сумму

Отвечай кратко, дружелюбно, на русском языке."""


def search_products_impl(db: Session, query: str = "", category: str = "", tags: list = None, max_price: float = None):
    q = db.query(Product).filter(Product.in_stock == True)

    if query:
        q = q.filter(
            Product.name.ilike(f"%{query}%") | Product.description.ilike(f"%{query}%")
        )
    if category:
        q = q.filter(Product.category.ilike(f"%{category}%"))
    if max_price is not None:
        q = q.filter(Product.price <= max_price)

    products = q.all()

    if tags:
        filtered = []
        for p in products:
            product_tags = [t.strip().lower() for t in (p.tags or "").split(",")]
            if all(t.lower() in product_tags for t in tags):
                filtered.append(p)
        products = filtered

    return [
        {
            "id": p.id,
            "name": p.name,
            "category": p.category,
            "price": p.price,
            "unit": p.unit,
            "calories_per_100g": p.calories_per_100g,
            "tags": p.tags,
            "description": p.description,
        }
        for p in products
    ]


def add_to_cart_impl(db: Session, session_id: str, product_id: int, quantity: int = 1):
    product = db.query(Product).filter(Product.id == product_id, Product.in_stock == True).first()
    if not product:
        return {"error": f"Товар с ID {product_id} не найден или отсутствует"}

    item = db.query(CartItem).filter(
        CartItem.session_id == session_id,
        CartItem.product_id == product_id,
    ).first()

    if item:
        item.quantity += quantity
    else:
        item = CartItem(session_id=session_id, product_id=product_id, quantity=quantity)
        db.add(item)

    db.commit()
    return {"added": product.name, "price": product.price, "quantity": quantity}


def get_cart_impl(db: Session, session_id: str):
    items = db.query(CartItem).filter(CartItem.session_id == session_id).all()
    if not items:
        return {"items": [], "total": 0}

    result = []
    total = 0.0
    for item in items:
        product = db.query(Product).filter(Product.id == item.product_id).first()
        if product:
            subtotal = product.price * item.quantity
            total += subtotal
            result.append({
                "product_id": product.id,
                "name": product.name,
                "price": product.price,
                "unit": product.unit,
                "quantity": item.quantity,
                "subtotal": subtotal,
            })

    return {"items": result, "total": round(total, 2)}


def clear_cart_impl(db: Session, session_id: str):
    deleted = db.query(CartItem).filter(CartItem.session_id == session_id).delete()
    db.commit()
    return {"cleared": True, "items_removed": deleted}


def run_tool(tool_name: str, tool_input: dict, db: Session, session_id: str):
    if tool_name == "search_products":
        return search_products_impl(
            db,
            query=tool_input.get("query", ""),
            category=tool_input.get("category", ""),
            tags=tool_input.get("tags", []),
            max_price=tool_input.get("max_price"),
        )
    elif tool_name == "add_to_cart":
        return add_to_cart_impl(
            db,
            session_id=session_id,
            product_id=tool_input["product_id"],
            quantity=tool_input.get("quantity", 1),
        )
    elif tool_name == "get_cart":
        return get_cart_impl(db, session_id=session_id)
    elif tool_name == "clear_cart":
        return clear_cart_impl(db, session_id=session_id)
    return {"error": "Unknown tool"}


def _demo_chat(user_message: str, db: Session, session_id: str) -> str:
    """Fallback when no API key: keyword-based matching for demo."""
    msg = user_message.lower()

    # Parse budget
    budget_match = re.search(r'(\d+)\s*(руб|₽|р\.)', msg)
    budget = float(budget_match.group(1)) if budget_match else 2000.0

    # Determine tags to search
    tags = []
    if "безлактоз" in msg:
        tags.append("безлактозный")
    if "веган" in msg:
        tags.append("веганский")
    if "завтрак" in msg or "утро" in msg:
        tags.append("завтрак")
    if "обед" in msg or "ужин" in msg:
        tags.append("обед")
    if not tags:
        tags = ["завтрак"]

    products = search_products_impl(db, tags=tags, max_price=budget)
    if not products:
        products = search_products_impl(db, max_price=budget)

    # Greedy fill up to budget
    selected = []
    total = 0.0
    for p in products:
        if total + p["price"] <= budget:
            selected.append(p)
            total += p["price"]
        if len(selected) >= 6:
            break

    if not selected:
        return "К сожалению, не нашёл подходящих товаров в указанном бюджете."

    for p in selected:
        add_to_cart_impl(db, session_id=session_id, product_id=p["id"], quantity=1)

    names = "\n".join(f"• {p['name']} — {p['price']} ₽" for p in selected)
    return (
        f"(⚠️ Демо-режим — API-ключ не задан)\n\n"
        f"Подобрал для вас:\n{names}\n\n"
        f"Итого: {total:.0f} ₽ из {budget:.0f} ₽\n\n"
        f"Всё добавлено в корзину!"
    )


def chat(user_message: str, history: list, db: Session, session_id: str) -> tuple[str, list]:
    if not client:
        reply = _demo_chat(user_message, db, session_id)
        new_history = history + [
            {"role": "user", "content": user_message},
            {"role": "assistant", "content": reply},
        ]
        return reply, new_history

    messages = history + [{"role": "user", "content": user_message}]

    while True:
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=messages,
        )

        if response.stop_reason == "tool_use":
            tool_results = []
            assistant_content = response.content

            for block in response.content:
                if block.type == "tool_use":
                    result = run_tool(block.name, block.input, db, session_id)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(result, ensure_ascii=False),
                    })

            messages.append({"role": "assistant", "content": assistant_content})
            messages.append({"role": "user", "content": tool_results})

        else:
            text = "".join(
                block.text for block in response.content if hasattr(block, "text")
            )
            messages.append({"role": "assistant", "content": text})
            return text, messages
