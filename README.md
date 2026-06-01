# Retail Concierge — Консьерж для ритейла

Чат-помощник для продуктового магазина. Покупатель описывает запрос на естественном языке («собери безлактозный завтрак до 1500 руб»), Claude подбирает товары из каталога и добавляет их в корзину.

## Стек

- **Backend**: Python 3.11+, FastAPI, SQLAlchemy, SQLite
- **AI**: Claude claude-sonnet-4-6 (Anthropic API) с tool use
- **Frontend**: чистый HTML/JS (без фреймворков)

## Быстрый старт

```bash
# 1. Установить зависимости
cd backend
pip install -r requirements.txt

# 2. Задать API-ключ
cp ../.env.example .env
# Вписать ANTHROPIC_API_KEY в .env

# 3. Запустить
python main.py
```

Открыть http://localhost:8000

## Структура

```
market/
├── backend/
│   ├── main.py        # FastAPI приложение, маршруты
│   ├── concierge.py   # Claude AI логика + tool use
│   ├── database.py    # SQLAlchemy модели (Product, CartItem)
│   ├── seed.py        # Наполнение каталога тестовыми данными
│   └── requirements.txt
└── frontend/
    └── index.html     # Чат-интерфейс + корзина
```

## Примеры запросов

- «Собери безлактозный завтрак до 1500 руб»
- «Хочу веганский завтрак до 800 рублей»
- «Подбери продукты для овсяной каши»
- «Что можно купить для перекуса до 500 руб?»
- «Очисти корзину и подбери завтрак с яйцами»
