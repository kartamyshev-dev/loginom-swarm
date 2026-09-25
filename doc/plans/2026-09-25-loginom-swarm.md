# Реализация Loginom Swarm

Согласованный результат: ручной старт Sampling из Paperclip, далее разработка,
независимое ревью, до двух исправлений, полная сборка, слепая приёмка и PR в
`gooddaytoday/loginom-ai-agent:loginom`. Слияние, релиз, следующий узел ручные.

1. Форк от v2026.916.1, ветка swarm, изолированные рабочие PR, реестр изменений.
2. Импорт инфраструктуры без потери production ID/данных; секреты вне Git/image.
3. Ручной update workflow со stable tag/commit, merge, отчётом конфликтов и PR;
   CI, сборка, manifest совместимости; deploy отдельно.
4. Контейнер Paperclip из исходников форка плюс отдельная host-служба: pinned
   Codex, Node/Bun/Chromium, Loginom CLI, Python, GitHub CLI, bwrap, Xvfb.
   Отдельные постоянные checkout/.git.
5. Изоляция ролей и allowlist окружения; immutable wrappers; review read-only;
   только служебный publisher получает личный GitHub CLI OAuth; отдельные server OAuth.
6. Linux OpenViking generation с exact registration → канонический Mac Peer;
   реальные thread ID/hooks/cursors; gateway без мастер-ключа в model env;
   capture/extraction/read-back, deny чужому Peer; локальную генерацию не менять.
7. Native pipelines/cases: leases, expectedVersion, requestKey, дедупликация;
   immutable evidence и oracle; locks не удалять по возрасту; ambiguous → blocked.
8. Live smoke: ресурсы, sandbox, memory, точные модели, сохранение/reopen Loginom,
   полная сборка CLI, тестовый draft PR, негативные сценарии, restore backup.
9. Backup всех профилей/checkouts/регистраций/артефактов + БД, семь дней на VPS.
10. Отдельный ручной deploy после проверок/backup, сохранение digest для отката;
    передача инструкций и готовой точки старта без запуска Sampling.

Модели: gpt-6-astra medium (dev/review), openai/gpt-6-sol low (CLI acceptance).
Одна тяжёлая стадия, один Loginom agent одновременно, acceptance ≤30 мин,
активное время узла ≤8 ч. VPS увеличивает пользователь при измеренной нехватке.

## Согласованное изменение 25.09.2026

Пользователь выбрал отдельную непривилегированную службу исполнителей на том же
VPS. Docker nested bwrap остановился на mount /proc EPERM; выключать защиту Docker
не разрешено. Управление, native cases, ответственный пользователь и ручной старт
остаются в Paperclip. Node/Bun/Chromium, Codex, CLI и memory runtime устанавливаются
в immutable host runtime. Контейнер форка получает только клиент/координатор;
нет Docker socket, root SSH или model credentials в control-plane контейнере.

## Личная публикация (25.09.2026)

По прямому указанию пользователя ветки, push и PR должны выполняться как
`kartamyshev-dev`. Использовать отдельный личный GitHub CLI OAuth на сервере,
без требования GitHub App владельца gooddaytoday. Не копировать токен с Mac.
Моделям не выдавать профиль публикатора; идентичность инициатора сохранять
в Paperclip. Перед каждой публикацией проверять identity, права и PASS кандидата.
