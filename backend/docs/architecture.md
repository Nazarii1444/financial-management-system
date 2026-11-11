# Архітектура системи

```mermaid
graph TB
    subgraph Client["Клієнтська частина"]
        UI["React + TypeScript\n(SPA)"]
    end

    subgraph Backend["Серверна частина (FastAPI)"]
        direction TB
        AUTH["Модуль автентифікації\nJWT / OAuth2 / 2FA (TOTP)"]
        TX["Модуль транзакцій\n(прості, рекурентні, імпорт)"]
        BUD["Модуль бюджетів\n(особистий / сімейний / бізнесовий)"]
        GOALS["Модуль цілей\n(накопичувальні банки)"]
        ANALYTICS["Аналітичний модуль\n(7 видів звітів)"]
        FILES["Модуль файлів\n(OCR чеків, завантаження)"]
        SETTINGS["Налаштування\n(профіль, підписка, сповіщення)"]
        CURRENCY["Модуль валют\n(курси НБУ, конвертація)"]
    end

    subgraph DB["База даних"]
        PG[("PostgreSQL")]
    end

    subgraph External["Зовнішні сервіси"]
        NBU["API НБУ\n(валютні курси)"]
        GOOGLE["Google OAuth2"]
        GITHUB["GitHub OAuth2"]
    end

    UI -->|"REST API (HTTPS)"| AUTH
    UI --> TX
    UI --> BUD
    UI --> GOALS
    UI --> ANALYTICS
    UI --> FILES
    UI --> SETTINGS
    UI --> CURRENCY

    AUTH --> PG
    TX --> PG
    BUD --> PG
    GOALS --> PG
    ANALYTICS --> PG
    FILES --> PG
    SETTINGS --> PG
    CURRENCY --> PG

    CURRENCY -->|"щогодинний cron"| NBU
    AUTH --> GOOGLE
    AUTH --> GITHUB
```

## Опис компонентів

| Компонент | Технологія | Призначення |
|---|---|---|
| Клієнтська частина | React, TypeScript | SPA-інтерфейс, взаємодія через REST API |
| Серверна частина | FastAPI (Python, async) | Обробка запитів, бізнес-логіка |
| База даних | PostgreSQL | Постійне зберігання всіх даних |
| Автентифікація | JWT + TOTP + OAuth2 | Безпечний доступ до системи |
| Валютні курси | API НБУ | Актуальні курси, оновлення щогодини |
| Соціальний вхід | Google, GitHub OAuth2 | Швидка реєстрація / вхід |

