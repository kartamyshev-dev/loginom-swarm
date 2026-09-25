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
