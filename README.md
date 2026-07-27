# LocalRP

Desktop + web интерфейс для локальных LLM, заточенный под длинные RP-сессии.
Память живёт в SQLite, а не в промпте: после каждого ответа модель отдельным
скрытым запросом извлекает структурированные изменения (персонажи, события,
отношения, факты, обещания, секреты...), а перед следующим ответом движок
подбирает только релевантные записи по тегам/сущностям — без эмбеддингов по
умолчанию, с опциональной архитектурой под них.

## Быстрый старт (dev)

### Backend

```bash
cd backend
python3 -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env          # при необходимости поправьте секреты/порты
python -m uvicorn app.main:app --host 0.0.0.0 --port 8420 --reload
```

При первом запуске backend сам создаёт SQLite-базу (`data/localrp.db`) и все таблицы.

### Frontend (веб)

```bash
cd frontend
npm install
npm run dev
```

Откройте `http://localhost:5173`. Первый запуск попросит создать администратора.

### Доступ с телефона

Backend слушает `0.0.0.0:8420`, frontend dev-сервер — `0.0.0.0:5173`.
Узнайте локальный IP компьютера (`ip addr` / `ipconfig`) и откройте
`http://<IP компьютера>:5173` в браузере телефона в той же сети.

### Desktop (Tauri)

```bash
cd frontend
npm install
npm run tauri dev     # разработка
npm run tauri build   # сборка установщика
```

Tauri-обёртка при старте сама поднимает backend-процесс локально.

## Подключение модели

В Settings укажите провайдера:

- **llama.cpp** — запустите `llama-server` и укажите его адрес (обычно `http://localhost:8080`)
- **LM Studio** — включите Local Server в LM Studio, укажите адрес (обычно `http://localhost:1234`)
- **Ollama** — укажите `http://localhost:11434`, приложение работает через нативный `/api/chat`
- **OpenAI-compatible** — любой другой сервер с `/v1/chat/completions`

Приложение не завязано на конкретную модель; по умолчанию рассчитано на Gemma 4 26B,
но будет работать с любой моделью, которую отдаёт выбранный провайдер.

## Структура проекта

```
backend/app/
  models/        — схема SQLAlchemy (все таблицы памяти)
  services/memory/   — extraction (скрытый JSON-запрос) + retrieval (без эмбеддингов) + prompt builder
  services/providers/ — адаптеры llama.cpp/LM Studio/Ollama/OpenAI-compatible
  services/auth/     — Argon2, JWT, refresh, CSRF
  api/routes/        — auth, chat (streaming), characters, memory (generic CRUD для остальных
                        11 типов сущностей), timeline/search/settings/inspector, backup

frontend/src/
  App.tsx             — роутинг (HashRouter) + общий shell с нав-рейлом
  components/         — NavRail, ChatSelector, MemoryFlagsBar, RevisionHistory
  store/chatStore.ts  — общий активный чат для всех разделов
  pages/
    ChatPage.tsx           — чат (SSE-стриминг, "нить памяти")
    MemoryEditorPage.tsx   — редактор памяти: все типы сущностей, pin/canon/false/enable, история
    CharactersPage.tsx     — карточки персонажей + подробный редактор
    TimelinePage.tsx       — вертикальная временная линия по story_day
    SearchPage.tsx         — поиск по всем типам записей и сообщениям
    SettingsPage.tsx       — провайдер/модель/параметры генерации/режим памяти
    PromptInspectorPage.tsx — сборка промпта без отправки: блоки, токены, отобранные сущности
    LoginPage.tsx           — первый запуск / вход
  styles/             — тёмная тема, токены + стили под каждый раздел
  src-tauri/          — desktop-обёртка
```

## Раздел «Память» (Memory Editor)

Все 12 типов сущностей (Character, Location, Item, Organization, Event, Fact,
Goal, Promise, Secret, Relationship, StoryArc, SceneSummary, ArcSummary)
редактируются через единый интерфейс: список слева по типу → список записей →
детальная форма справа с закреплением/канон/ложь/вкл-выкл, ползунком важности
и полной историей изменений (кто, когда, что было/стало). Character CRUD
работает через `api/routes/characters.py` (более богатая схема полей), все
остальные типы — через новый `api/routes/memory.py`, который управляется
единым реестром `ENTITY_REGISTRY` вместо одиннадцати почти одинаковых файлов.

## Известные ограничения этой версии

- `MemoryEmbeddings` — таблица и точка расширения есть, векторный retrieval
  не реализован (включается через `memory_retrieval_mode` в settings).
- Tauri sidecar в dev-версии запускает системный `python3` напрямую;
  для дистрибутива backend стоит собрать через PyInstaller и подключить
  как `externalBin`.
- Фронтенд не пересобирался в этой среде через `npm run build` (нет доступа
  к npm-реестру в песочнице) — синтаксис и типы проверены вручную и через
  `tsc`-совместимые правила, но перед продакшн-сборкой стоит прогнать
  `npm install && npm run build` локально.
