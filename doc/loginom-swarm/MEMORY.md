# Серверная память Loginom Swarm

Статус 25.09.2026: обе роли зарегистрированы; live recall, capture, extraction,
resume и MCP find/read проверены. Это готовность подсистемы памяти, не разрешение
обработки Sampling. Координатор разработки и приёмка ещё не завершены.

## Граница доступа

Канонический Peer —
`viking://user/kartamyshev/peers/-Users-kartamyshev-Git-loginom-ai-agent/memories`.
Серверный путь checkout не создаёт новый Peer. Локальная генерация основного
проекта 20260924.1 остаётся без изменений. Серверная генерация — 20260925.1.

Разработчик и ревьювер имеют отдельные реальные Codex thread ID, checkout,
OAuth-профиль и cursor. Приёмщик не получает интеграцию памяти. Bubblewrap
монтирует только собственный профиль, собственную регистрацию и root-owned код.
`hooks.json` и `config.toml` перекрываются read-only файлами из memory-sealed.
Root/DB/Paperclip/publisher credentials в sandbox отсутствуют.

Шлюз `loginom-swarm-memory` слушает только 127.0.0.1:8766. Его master credential
лежит в `/etc/loginom-swarm/memory-gateway.json` (root:loginom-memory,0640).
Профили имеют разные scoped credentials, связываемые шлюзом с ролью и thread ID.
Модели не получают master credential. Политика шлюза ограничивает чтение и поиск
точным Peer, capture и commit — собственной сессией `cx-<real Codex thread ID>`.
Нет remember, resource import, прямой записи в Peer, чужих сессий или произвольного
HTTP proxy. Конфигурацию шлюза и его ответы никогда не печатать целиком.

## Регистрация и hooks

1. Установить root-owned runtime, gateway service и проверенный vendor snapshot.
2. `prepare-memory-roles.py` создаёт pending регистрации и определения hooks.
3. `memory_bootstrap.py ROLE` работает непривилегированно под AppArmor и Bubblewrap.
   Он проверяет hooks/list, доверяет проверенным hashes штатным config/batchWrite,
   начинает настоящую Astra medium сессию и проверяет завершённый подготовительный
   ход. Если bootstrap прервался после создания thread, продолжает именно его.
4. `enroll-memory-role.py ROLE` проверяет observer receipt, SessionStart, завершение
   хода и hooks, затем закрепляет thread ID и read-only настройки.
5. `configure-memory-tools.py` добавляет только stdio find/read; настройки меняет
   оператор снаружи sandbox. При изменении hooks обязательно повторять штатную
   проверку trust. Не использовать bypass флаги.
6. `memory_qualification.py ROLE LABEL` выполняет только короткий инфраструктурный
   ход. LABEL не повторять: receipt с таким именем блокирует новый запуск заранее.
7. `memory_tools_qualification.py ROLE` проверяет инструменты через настоящий
   pinned Codex app-server, resume того же thread, чужой Peer и сохранённый trust.

Команды observer запускаются через:
`runuser -u loginom-worker -- aa-exec -p loginom-swarm-worker -- python3 -I ...`.
Они держат общую heavy lock. Это операторские проверки, не RPC модели.
Не запускать bootstrap/enrollment повторно поверх active регистрации.

SessionStart проверяет identity и cursor; UserPromptSubmit делает scoped recall.
Stop и PreCompact выполняют штатный catch-up и commit/extraction. У SessionEnd
в Codex лимит 3 секунды: он проверяет локально, что tail полностью захвачен и
commit cursor совпадает, без HTTP. Ошибки hook не являются успехом этапа:
координатор обязан проверить native lifecycle и собственные receipts.

## Повторы и сбои

Gateway journal schema2 привязывает мутацию к thread, типу операции и позиции
capture. Один и тот же текст в разных ходах сохраняется отдельно. Повтор старой
операции возвращает сохранённый результат, даже после более новых операций.
Изменённое содержимое для занятой позиции, неверный cursor и неизвестный результат
записи блокируют мутации. Сначала fsync uncertain, затем HTTP, затем fsync result.
Поле swarm_capture_offset не передаётся OpenViking.

Старый schema1 перенесён только после проверки завершённого commit digest и
совпадения cursor с успешным native Stop receipt. Сохранены legacy-v1 файлы и
предварительная полная backup. Не редактировать cursor или journal вручную,
не удалять lock по возрасту, не повторять неизвестную мутацию наугад.

Vendor plugin0.8.1 использует собственный capture/extraction протокол. В
`swarm/memory/vendor-plugin/provenance.json` перечислены оригинальные и новые
hashes и ограниченные патчи: aged lock не захватывается, повреждённый state не
обнуляется, transcript shrink (включая пустой файл) останавливает capture, cursor
пишется через atomic rename+fsync. Apache LICENSE сохранена. Это независимая
серверная копия; локальный plugin не изменён.

## Доказательства и обслуживание

`/opt/loginom-worker/state/memory-*.json` — observer receipts, вне model mounts.
`profiles/sampling/ROLE/swarm-memory` — отдельные cursor и hook metadata.
`/var/lib/loginom-swarm-memory` — private transport journals.
Обычные health responses не означают готовность capture/extraction.

На Mac через зарегистрированные OpenViking tools найдена и прочитана запись
`.../memories/events/2026/09/25/swarm_memory_acknowledge.md` с серверным маркером.
Точные IDs и историю проверок см. CHECKPOINT.md и STOP-2026-09-25.md. Отдельная
проверка из уже существующей основной задачи проекта пока не выполнена.

Ежедневная backup включает gateway config/state/code/unit, registrations,
sealed files, профили и receipts. Она ждёт heavy lock и останавливает worker и
gateway на время снимка. Restore проверяет связность thread/cursor и hashes
sealed файлов, не запуская модели. Копии на том же VPS не защищают от потери VPS.

Контракты транспорта сверены с [MCP tools](https://modelcontextprotocol.io/specification/2025-11-25/server/tools)
и [Codex app-server](https://learn.chatgpt.com/docs/app-server). Фактические схемы
берутся из установленного Codex0.155.1; смена версии требует повторной проверки.
