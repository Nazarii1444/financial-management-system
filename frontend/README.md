# Frontend

Веб-інтерфейс фінансового застосунку: React, Vite, TypeScript, Tailwind CSS, React Router.

## Вимоги

- [Node.js](https://nodejs.org/) 20+ (рекомендовано LTS)

## Встановлення

```bash
cd frontend
npm install
```

## Команди

| Команда        | Опис                          |
| -------------- | ----------------------------- |
| `npm run dev`  | Локальний dev-сервер (Vite)   |
| `npm run build`| Production-збірка у `dist/`   |
| `npm run preview` | Перегляд зібраного білду   |

Після `npm run dev` відкрий у браузері URL з терміналу (зазвичай `http://localhost:5173/`; якщо порт зайнятий — Vite обере інший, наприклад `5174`).

## Структура

- `index.html` — точка входу для Vite
- `src/main.tsx` — монтування React
- `src/app/` — додаток: сторінки, маршрути, контекст, компоненти
- `src/styles/` — глобальні стилі (Tailwind, тема, шрифти)

## Підключення до бекенду

Фронтенд працює з FastAPI-бекендом (`backend/`). У dev-режимі Vite проксіює `/api` на бекенд,
тому CORS налаштовувати не потрібно.

1. Запустіть бекенд (див. `backend/README.md`, розділ «Швидкий локальний запуск») — за замовчуванням `http://127.0.0.1:8000`.
2. Якщо бекенд на іншій адресі — скопіюйте `.env.example` у `.env` і змініть `VITE_BACKEND_URL`.
3. `npm run dev` і відкрийте `http://localhost:5173`.

Демо-вхід (після `python -m scripts.seed`): `alice@example.com` / `password123`.

| Команда | Опис |
| --- | --- |
| `npm run typecheck` | Перевірка типів TypeScript |

## Структура API-шару

- `src/app/lib/api.ts` — HTTP-клієнт, токени (access/refresh, авто-оновлення), усі ендпоінти
- `src/app/types/api.ts` — типи відповідей бекенду
- `src/app/lib/errors.ts` — переклад помилок бекенду (укр/англ)
- `src/app/i18n/translations.ts` — усі тексти інтерфейсу українською та англійською

Чого ще бракує на бекенді — `docs/INTEGRATION_GAPS.md`.

