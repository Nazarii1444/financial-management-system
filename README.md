# Financial Management System

FastAPI backend (`backend/`) + React/Vite frontend (`frontend/`) + PostgreSQL.

## Запуск через Docker

Потрібен [Docker Desktop](https://www.docker.com/products/docker-desktop/).

```bash
docker compose up --build
```

| Сервіс | Адреса |
| --- | --- |
| Застосунок | http://localhost:5173 |
| API / Swagger | http://localhost:8000/docs |

При першому старті бекенд створює таблиці й заповнює БД демо-даними.
Вхід: `alice@example.com` / `password123` (так само `bob@`, `carol@`, … `@example.com`).

Корисні команди:

```bash
docker compose up -d --build     # у фоні
docker compose logs -f backend   # логи бекенду
docker compose down              # зупинити (дані зберігаються у volume)
docker compose down -v           # зупинити й видалити БД та завантажені файли
```

Налаштування (порти, паролі, `SECRET_KEY`, OAuth-ключі, вимкнення демо-даних `SEED_DATA=false`) —
скопіюйте `.env.example` у `.env` поруч із `docker-compose.yml`.

Як влаштовано: nginx у контейнері `frontend` віддає зібраний SPA і проксіює `/api` на `backend:8000`,
тож браузер ходить на один origin і CORS не потрібен.

## Локальна розробка без Docker

- Бекенд: `backend/README.md`
- Фронтенд: `frontend/README.md`

Що ще не реалізовано на бекенді — `docs/INTEGRATION_GAPS.md`.
