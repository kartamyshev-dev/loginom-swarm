# Состояние реализации — 2026-09-25

Рабочая ветка: `swarm-bootstrap`. `origin/swarm` пока содержит только базовый тег.
Черновой PR: https://github.com/kartamyshev-dev/loginom-swarm/pull/1
Первый commit 880b7d3a3. Изменения ещё не приняты в swarm. Старый сервер Paperclip продолжает работу.

- Cloud enrollment: active; instance inst_a03bb598-b988-41a9-aeb4-3fccd41202f0.
- GitHub connection 26610ae5-466f-4c30-a9ce-7736678aa1d7: active personal OAuth,
  kartamyshev-dev, доступен только kartamyshev-dev/loginom-swarm. Требуется установка
  GitHub App владельцем gooddaytoday для loginom-ai-agent.
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
самостоятельные checkout и инфраструктурный CLI-кандидат. Восстановление проверяется.

Ближайший незавершённый блок — серверная память: пока есть только policy с
отрицательными тестами. Не выдавать её за работающий gateway. Далее нужны Linux
hooks/enrollment, настоящий capture/extraction/read-back, coordinator native cases,
независимый Loginom save/reopen, qualification отказов и production rollout.
Отдельный внешний блок — GitHub App на gooddaytoday/loginom-ai-agent; установку
может выполнить владелец. Доступ к kartamyshev-dev/loginom-swarm уже подтверждён.
