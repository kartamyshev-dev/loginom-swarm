# Состояние реализации — 2026-09-25

Рабочая ветка: `swarm-bootstrap`. `origin/swarm` пока содержит только базовый тег.
Черновой PR: https://github.com/kartamyshev-dev/loginom-swarm/pull/1
Первый commit 880b7d3a3. Изменения ещё не приняты в swarm. Старый сервер Paperclip продолжает работу.

- Cloud enrollment: active; instance inst_a03bb598-b988-41a9-aeb4-3fccd41202f0.
- GitHub connection 26610ae5-466f-4c30-a9ce-7736678aa1d7: active personal OAuth,
  kartamyshev-dev, доступен только kartamyshev-dev/loginom-swarm. Сохранено как
  legacy-подключение; публикация узлов переводится на личный GitHub CLI OAuth.
- Доступ подключения ограничен publisher e7e6aed2-95b5-41ed-bccc-21f1bd2b7015;
  publisher paused, command /usr/bin/false, heartbeat/wakeOnDemand выключены.
- Codex developer и reviewer: сервер подтвердил Logged in using ChatGPT.
- Standalone CLI acceptance: OpenAI oauth подтверждён providers list.
- Astra medium smoke PASS; Sol low через standalone CLI: короткий запрос PASS, без tools.
- Linux memory и resource peaks ещё не проверены.
- Компания 428979e0-2e82-476d-9448-506379c83ac9, проект
  148af952-3d5d-4a4a-9257-1884ee15d552; существующий Sampling issue/agent сохраняются.
- Секреты `.env`, `private/` исключены из Git и Docker context; права .env 0600.

Далее: закончить OAuth и GitHub scope; реализовать и проверить Linux runtime,
memory gateway и enrollment, native case coordinator, сборку CLI и приёмку;
расширить backups; пройти live gates; только после этого передать ручной старт.
Никаких readiness receipts без фактической проверки. Не удалять старый SSH пилот
до подтверждённой замены. Не запускать Sampling, не сливать node PR автоматически.

## Отдельная служба исполнителей (подтверждено пользователем)

Вложенный Docker sandbox не прошёл mount /proc. Контейнер production не ослаблялся.
Установлена host-служба `loginom-swarm-worker`, UID1000, без capabilities,
NoNewPrivileges, AppArmor, отдельные Bubblewrap namespaces. API только Unix socket;
processingEnabled=false. Регистрированы только пустые infrastructure fixtures.
Проверены 11 границ для каждой роли и 6 отрицательных запросов. Sampling не запускался.
ProtectKernelLogs systemd маскирует /proc/kmsg и ломает новый proc mount; эту
директиву не применять. Host /proc не передаётся модели: bwrap создаёт свой proc/PID.

Pinned Node24.19.0, Bun1.3.14 (полный commit), CLI0.1.16 установлены root-owned
в /opt/loginom-swarm/toolchains/20260925.1, SHA256 архивов и Node проверены.
Loginom acceptance setup: ready, hasApiKey=true, hasPassword=false; AppArmor
позволяет штатный Chromium sandbox. Проверка save/reopen ещё впереди.

Native pipeline c92742f4-f55a-42e3-9c3b-93b58da4f2a6,
case 038456b1-e389-4724-a212-436bb4dbd197, stage=setup, без автоматики.
Локальные typecheck и build PASS; целевые 105 тестов PASS после исправления путей
workflow fixtures. Полный test:run ещё не зелёный; подробности в VALIDATION.md.

Дальше: координация native cases, рабочие OAuth-профили в полном sandbox,
Linux memory с настоящими hooks/enrollment, полная CLI-сборка, независимая
приёмка и измерения ресурсов, расширенные backups, CI и source-built deployment.
Пустой transport/setup service не считать готовым исполнителем кампании.

Backup 20260925T002721Z: восстановлена отдельная БД, 210 таблиц, fingerprint
строк совпал со снимком. Worker archive извлечён и проверен. После рестарта
11 sandbox checks × 3 роли + 6 negative RPC прошли повторно; health production ok.
Полная CLI source build и archive roundtrip завершены; штатный manifest verifier
PASS, sourceDirty=false. Минимум1228MiB RAM/68GiB disk; подробности VALIDATION.
OAuth profiles перенесены в profiles/sampling, standalone Git checkout dev/review
созданы. Оба Codex login status и Loginom acceptance check прошли внутри sandbox.
Node run, memory enrollment, автоматический координатор ещё не активированы.
На GitHub для 8b308fa40 contracts/typecheck/image PASS, test:run выполняется.

## Проверенный переход на host service

Container → host Unix socket: PASS из отдельного контейнера UID1000,
network=none, cap_drop ALL, read-only; processingEnabled=false. Production
Compose не переключался на новый образ.

Reviewer c6a145a3-695e-46e8-927e-e2a828d2204b и acceptance
c863d349-9642-41ae-9a46-4025d2d5d534 созданы через API, paused, command=false,
heartbeat/wakeOnDemand отключены. Повтор подготовки вернул те же IDs.
Developer c49d36f3-1b4d-4f09-8184-acc73daef2c5 сохранён; SSH-пилот не удалён.
Новая backup 20260925T005034Z включает перемещённые profiles/sampling,
самостоятельные checkout и инфраструктурный CLI-кандидат. Восстановление PASS: 210 таблиц, fingerprint строк и извлечённые профили совпали.

Ближайший незавершённый блок — серверная память: пока есть только policy с
отрицательными тестами. Не выдавать её за работающий gateway. Далее нужны Linux
hooks/enrollment, настоящий capture/extraction/read-back, coordinator native cases,
независимый Loginom save/reopen, qualification отказов и production rollout.
GitHub App владельца больше не требуется: пользователь выбрал личную публикацию.
На Mac API подтвердил kartamyshev-dev (97161574) и permissions.push=true для
gooddaytoday/loginom-ai-agent. На VPS создан отдельный loginom-publisher и
подтверждён личный OAuth. Сервер создал ветку swarm-publication-probe и draft PR
https://github.com/gooddaytoday/loginom-ai-agent/pull/2, закрытый без слияния.
Автор PR, author и committer тестового commit 6aa209c8caa7fa7512a6350a03def6042c3921cc
проверены через GitHub API: kartamyshev-dev. Worker не может прочитать токен;
hosts.yml имеет 0600. Ветка оставлена как доказательство проверки.
В Paperclip обновлены metadata/capabilities publisher, status=paused, command=false.
Токены с Mac не копировались. Publisher и Sampling остаются остановлены.

Личная GitHub публикация: реализация d7809bab9 в draft PR1. Снимок
20260925T011019Z завершён, целевое восстановление нового OAuth-профиля прошло:
данные и закрытые права совпали. Полная повторная проверка БД этого снимка
не выполнялась; предыдущие restore proofs остаются в VALIDATION.md.

## Аудит готовности 25.09.2026, 01:22 UTC

Актуальная сводка: [READINESS-AUDIT-2026-09-25.md](READINESS-AUDIT-2026-09-25.md).
Повторно подтверждены health VPS, личный GitHub push permission и paused роли.
Новые конкретные пробелы: pipeline transitions/documentKeys пусты; worker принимает
только probe; candidate build и acceptance mount пока инфраструктурные; отдельный
Loginom development профиль отсутствует. Полный координатор и memory gateway не
реализованы. CI текущего 18488e955: contracts PASS, application/image выполняются.
Аудит не запускал узел и не менял рабочую конфигурацию. Документы аудита сохраняются
локально без push, чтобы не отменять текущий полный CI проверяемого commit.


## Остановка по запросу пользователя — 2026-09-25T06:20:25+00:00

Работа остановлена в безопасном месте. Активных execution jobs нет; heavy lock
свободен, Sampling остаётся setup/manualStart=false. Worker и memory gateway
работают как инфраструктурные службы. Подробная актуальная точка продолжения:
[STOP-2026-09-25.md](STOP-2026-09-25.md). Этот checkpoint заменяет устаревшие
утверждения аудита об отсутствии gateway и transitions. Текущие изменения
сохранены локально, без commit/push; MCP инструменты памяти ещё не установлены.


## Продолжение после остановки — 25.09.2026

Пользователь возобновил работу. Остановка в STOP-2026-09-25.md — исторический
снимок, не текущий запрет продолжения. Sampling по-прежнему запускать нельзя.
MCP find/read теперь установлены, подключены и проверены через реальный Codex у
обеих ролей, включая отказ чужому Peer и trusted hooks. Journal schema2 мигрирован
из подтверждённого commit/cursor, обе роли прошли capture/commit после migration.
Расширенная backup 20260925T070958Z восстановлена отдельно: DB210+fingerprint,
publisher bytes/modes, memory thread/cursor/sealed hashes PASS. См. MEMORY.md.
Локально 38 Python tests PASS; CI разделён на штатные группы после выявленного
90-минутного тайм-аута. Source fork production deployment и полный node coordinator
по-прежнему не готовы. Следом: финальная синхронизация runtime, restart/boundary
checks, новый snapshot schema2, commit/PR и полный CI; далее независимая Loginom
приёмка и настоящий stage runner/publisher. Узел запускает только пользователь.


## Текущая точка продолжения — CLI infrastructure BLOCKED, 25.09.2026

HEAD форка опубликован: `44b9dca5acb78462d3b345431e75d1f9b0ab1444`, draft PR #1.
Worker после финального обновления прошёл проверки границ; оба MCP memory профиля
проверены повторно. Backup `20260925T071935Z` восстановлен отдельно: контрольные
суммы, DB210/fingerprint, publisher bytes/modes, memory thread/cursor/sealed config PASS.

Реальная Sol low инфраструктурная приёмка CLI0.1.16 остановилась на проверке
загруженного CSV: `DISCOVERY_DIRECTORY_CHANGED`, exit4, сохранения результата нет.
Подробности и доказательства: [CLI-INFRASTRUCTURE-2026-09-25.md](CLI-INFRASTRUCTURE-2026-09-25.md).
Повторный доступ к общему Loginom аккаунту заблокирован durable journal;
6 штатных recovery записей сохраняются, remote cleanup не подтверждён.
Sampling остаётся setup; узел не запускался. Не объявлять Loginom gate PASS.

Следующие работы: разбор/устранение CLI blocker с сохранением исходных receipts;
полный node stage runner и publisher integration; отдельный development Loginom
профиль после reconciliation; квалификация всех отказов; live upstream-update
workflow; завершение CI; source-built production deployment и ручная передача.
Qualification/barrier файлы сохраняются локальным commit; push не должен
прерывать текущий полный CI `36107169612` на `44b9dca5a`.

Пользователь решил обновить CLI отдельно. Не менять исходники loginom-ai-agent
и не создавать исправление CLI в этой задаче. Это внешний незакрытый gate;
новую версию и reconciliation нужно подтвердить перед следующим Loginom тестом.
Отчёт опубликован и прочитан обратно через native case document
`infrastructure-qualification`; case всё ещё setup/manualStart=false.


## Миграция в LAN — в работе, 25.09.2026

Пользователь разрешил выполнение миграции на 10.200.4.106.
Актуальное состояние и следующий шаг: [MIGRATION-2026-09-25.md](MIGRATION-2026-09-25.md).
Источник заморожен: контейнеры, исполнители и backup timer остановлены.
Холодный снимок полностью передан, проверен, извлечён и сверён после remap
владельцев: 803875 записей, PASS. Установка в рабочие каталоги завершена, допуск активации закрыт.
Безопасная точка для пользовательской перезагрузки с новым CPU достигнута;
на назначении сохранён pre-reboot.json. После reboot сначала проверить AVX2
и VPN, затем восстановить БД. Производственный запуск ещё не выполнен.
Новая VPN-подписка заменяет старую VLESS-конфигурацию. Sampling не запускать.
