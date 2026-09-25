# Проверки и совместимость

| Компонент | Зафиксировано | Статус |
|---|---|---|
| Paperclip | v2026.916.1 / d554c478 | исходная production версия |
| PostgreSQL | 17 | существующая БД сохранена |
| Codex CLI | 0.155.1 | developer/reviewer ChatGPT login проверен |
| Loginom standalone CLI | 0.1.16 | установлен на VPS; OpenAI OAuth проверен |
| Loginom source | f81ebded7333ae7d974fdc5f87e8864cf75dd9c7 | база кандидата |
| Node для Loginom | 24.19.0 | manifest исходного проекта |
| Bun | 1.3.14 / 0d9b296af33f2b851fcbf4df3e9ec89751734ba4 | установлен, SHA256 и commit проверены |
| Chromium | revision 1243 | manifest исходного проекта |
| OpenViking plugin | 0.8.1 | Linux-интеграция ещё не введена |

Выполнено 25.09.2026: установка зависимостей pnpm 9.15.4 с frozen lock;
`pnpm -r typecheck` успешно на локальной машине (Node 25.9.0);
восемь отрицательных тестов политики и окружения; проверка реестра upstream.
Локальный `pnpm build` завершился успешно. Production Docker
сборка, CI на GitHub и новые интеграционные проверки ещё не подтверждены.

Допуск live-системы: отсутствие OOM, доступно не менее 512 MiB RAM и 20 GiB
диска при сборке и приёмке; стабильный Paperclip; изоляция процессов/секретов;
Chromium sandbox; точные модели; общий Peer с capture/extraction; Loginom save и
независимое reopen; тестовый draft PR; восстановление backup; повторы/отмена/
сбой авторизации/отрицательная приёмка без ложного PASS. Результаты привязывать
к digest образа и hashes артефактов, а не переносить с прежнего окружения.

Проверка host sandbox: bwrap с отдельными PID/IPC/UTS/network/mount namespaces
успешен, UID1000, каталоги /opt/paperclip и соседних профилей не видны.
Astra medium: короткий запрос через developer OAuth, точный ответ получен,
инструменты не вызывались. Loginom acceptance setup: ready, hasApiKey=true,
hasPassword=false; реальный Chromium sandbox включён, AppArmor-профиль применён.
Это ещё не проверка сохранения и повторного открытия пакета.

Первый полный test:run: 12337 passed, 2 failed, 82 skipped; 4 suites не загрузились
из-за переноса workflow fixtures. Пути исправлены без изменения assertions;
команда в baseline docs исправлена. Повтор всех шести затронутых suites:
105 tests passed. Один тест agent-conversations, упавший на ожидании idle,
прошёл в целевом повторе. Следующие части полного test runner ещё не проверены.
Node workflow tests: 68 passed, 4 failed в npm-publish ожиданиях (локальный Bash3.2);
причина ещё требует проверки на поддерживаемом Linux/Bash, не считать зелёным CI.

Sol low: короткий запрос через standalone CLI завершился с exit0, точным ответом,
без tool_use. Проверка вызвала реальную модель openai/gpt-6-sol, variant low.
Host worker: 11 проверок каждой из трёх ролей и 6 negative RPC PASS.
Python integration policy: 12 tests PASS.

Backup restore PASS: 20260925T002721Z, 210 таблиц и точное совпадение fingerprint
строк; отдельная распаковка worker profiles/state/config. Проверки изоляции
повторены после restart. Backup ждёт heavy lock до 8 часов, службы не останавливаются
во время активной работы. CLI acceptance получает STRICT_RECOVERY=1: неизвестная
мутация должна блокировать продолжение; новый профиль ещё не проверен live.

На GitHub contracts PASS для 880b7d3a3; application CI ещё выполняется.
Унаследованный commitperclip dependency-review завершился ошибкой: dependency
graph не включён в форке. Этот устаревший workflow отключён через API; новый
Swarm CI остаётся включён. Это не ошибка тестов приложения.

## Проверка host runtime и полной CLI-сборки

Изолированная source-сборка f81ebded7333ae7d974fdc5f87e8864cf75dd9c7 завершилась:
версия 0.0.0-dev-202609250039, sourceDirty=false, archive SHA256
ce8f3ef2da0515c024f8d5fd174881d16980a6287fdc9a9c6bdabbb1d32a61a3.
Штатный verifyCliManifest повторно проверил все файлы и права; зависимости:
Bun1.3.14, Node24.19.0, Playwright1.63.0-alpha-2026-08-31, MCP0.0.80, Chromium1243.
Минимум свободной памяти 1228 MiB, диска 68 GiB; 111 секунд. Обработка узла
не выполнялась. Первый итоговый wrapper ошибочно искал sourceCommit в корне
manifest; исправлен на metadata.sourceCommit, проверен существующий артефакт
штатным verifier без повторной сборки. Исходный failed receipt сохранён отдельно
от успешной проверки manifest; его не переписывали на PASS.

Codex0.155.1 установлен отдельно через pinned npm package с lock/integrity.
Профили developer/reviewer/acceptance перемещены только внутри VPS в
profiles/sampling; Mac-токены не копировались. Developer и reviewer имеют
самостоятельные .git, без alternates/hardlinks. В полном sandbox подтверждены
оба ChatGPT OAuth и LOGINOM_CONNECTION_VALID приёмщика с STRICT_RECOVERY=1.

Входной cache CLI в root-owned toolchain используется для сборки. Его права
нормализованы для чтения и поэтому он не является запускаемым installed artifact.
Для infrastructure check используется штатно установленный 0.1.16-prod payload,
смонтированный строго read-only с исходными manifest modes (включая vendor0600).
Не исправлять ошибки manifest отключением проверки или изменением его hashes.
Для приёмки узла потребуется отдельный проверенный полный candidate.

GitHub CI на 8b308fa40: contracts PASS, typecheck PASS, image source build PASS;
полный test:run ещё выполняется. Готовность source build не означает production deploy.
Подготовка Paperclip повторена через API: те же pipeline/case IDs, executionStarted=false.

Container→host Unix socket PASS в отдельном UID1000/cap_drop ALL/network-none
контейнере. Worker сообщает processingEnabled=false. 20 локальных Python
проверок PASS, включая успешный update merge и конфликт без изменения рабочей ветки.

## Личная публикация GitHub — 25.09.2026

Отдельный server OAuth GitHub CLI: identity kartamyshev-dev/97161574,
permissions.push=true для gooddaytoday/loginom-ai-agent. Реальный Git push
создал swarm-publication-probe, PR #2 в loginom создан как draft и закрыт без
слияния. API подтвердил author/committer kartamyshev-dev у commit
6aa209c8caa7fa7512a6350a03def6042c3921cc и того же автора PR.
Токен 0600 в отдельном UID999, worker UID1000 не может его читать.
Проверены shell syntax, Python compilation, 20 контрактных тестов и registry.
Автоматический координатор ещё не интегрирован; Sampling не запускался.

Backup 20260925T011019Z завершён успешно. Из его worker archive в отдельный
временный каталог восстановлены publisher home, .config/gh и hosts.yml:
credential bytes совпали с сервером, права каталогов/файла закрыты (PASS).
Это целевая проверка добавленного профиля; полный DB restore этого снимка
повторно не выполнялся. После backup Paperclip/DB healthy, host worker active.


## Протокол исполнителя и память — 25.09.2026, продолжение

38 локальных Python tests PASS: журнал операций, отмена и прерывание, scope памяти,
MCP stdio, идемпотентность по позиции capture, повторяющийся текст в новых ходах,
повреждённое состояние, aged locks, empty transcript shrink и vendor hashes.
Registry и git diff whitespace checks PASS.

Native diagnostic case прошёл три sandbox роли до done. Повтор после restart
не создаёт новую операцию. Отмена fixed probe: cancelled/cleanupConfirmed=true.
Это инфраструктурный coordinator, не реализация полного цикла узла.

Две Astra medium сессии получили доверенные native hooks и продолжили свои thread
ID. Обе прошли recall/capture/commit, включая новый journal-v2 после restart.
Обе через Codex app-server обнаружили только memory find/read, успешно выполнили
поиск и чтение известной записи; чужой Peer отвергнут, hooks остаются trusted.
На Mac OpenViking find/read подтвердили extraction серверного сообщения в общий
канонический Peer. Sampling не запускался.

Backup 20260925T070958Z: checksum PASS; изолированное восстановление БД PASS,
210 таблиц и fingerprint строк совпали. Worker archive извлечён отдельно;
publisher OAuth bytes/modes совпали, память восстановлена со связанными thread ID,
cursor и hashes sealed config. Снимок сделан до перехода gateway journal на schema2.
Последующая backup должна сохранить и новую схему журнала.

CI 18488e955 завершён по общему тайм-ауту 90 минут, а не с подтверждённым итоговым
PASS. Typecheck и image прошли; general server/UI/workspace части тестов проходили,
но весь последовательный запуск не завершился. Новый downstream workflow делит
тот же набор штатными upstream группами: 316+333=649 general server suites,
72+75=147 serialized suites, плюс обе полные группы workspaces. Проверены отсутствие
пересечений и полнота выбора. Новый удалённый прогон ещё не подтверждён.
