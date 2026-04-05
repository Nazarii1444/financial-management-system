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

## Примітки

- Дані для прототипу можуть бути в `mock`-форматі; підключення до API налаштовується окремо.

