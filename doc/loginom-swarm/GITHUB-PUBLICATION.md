# Публикация от личного аккаунта

По указанию пользователя от 25.09.2026 публикация выполняется через личный OAuth
GitHub CLI аккаунта `kartamyshev-dev` (ID 97161574), а не через GitHub App владельца.
Цель: `gooddaytoday/loginom-ai-agent`, PR в `loginom`, отдельная ветка каждого узла.
Существующее подключение Paperclip Cloud сохранено как legacy и не является
источником полномочий для публикации узлов.

## Установка и повторный вход

На VPS от root выполнить `swarm/scripts/install-publisher.sh`, затем
`swarm/scripts/publisher-login.sh` в устойчивой терминальной сессии. Открыть
выданный GitHub device URL и подтвердить вход как `kartamyshev-dev`.
`python3 swarm/scripts/verify-publisher.py` проверяет фактическую identity,
приватность файлов, push permission и наличие базовой ветки. Проверка не публикует.
Токены с Mac не копируются. Инструкция GitHub: https://cli.github.com/manual/gh_auth_login.

Системный пользователь `loginom-publisher` имеет отдельный UID и home
`/var/lib/loginom-swarm-publisher` с правами 0700, без shell-входа, sudo и Docker.
GitHub CLI хранит токен в приватном `~/.config/gh/hosts.yml` (0600): на сервере
нет desktop keychain. Каталог не включён в mounts моделей и недоступен worker UID.
Переменные запуска очищаются, GH_CONFIG_DIR явно указывает на личный профиль.
Git author и committer: `kartamyshev-dev`,
`97161574+kartamyshev-dev@users.noreply.github.com`. Это привязка к аккаунту,
не криптографическая подпись commit. Автор PR определяется реальным OAuth входом.

## Контракт будущего координатора

Перед публикацией проверить identity, права, ответственного инициатора кампании,
закреплённый кандидат и независимый PASS. Только доверенный служебный код использует
профиль публикатора. Нельзя выполнять код кандидата, hooks или его Git config
в окружении с токеном. Моделям профиль не выдаётся.

Публиковать только новую ветку, без force push, merge, релиза или запуска следующего
узла. Сохранять branch/commit/PR и request key в native case; неизвестный исход
мутации требует reconciliation, а не слепого повторения. Если авторизация исчезла
или вошёл другой аккаунт — blocked. Повтор события не должен создать второй PR.

Полный автоматический координатор ещё не реализован. Проверка OAuth и тестового
PR сама по себе не открывает обработку Sampling. Publisher в Paperclip paused.

## Резервное копирование

Профиль публикатора включён в worker.tar.gz ежедневной root-only копии; logs
исключены. При восстановлении сначала создать пользователя installer-ом, затем
извлечь каталог только в доверенную систему, назначить владельцем loginom-publisher
(числовой UID на новом VPS может отличаться), сохранить 0700 каталогов и 0600
hosts.yml. Выполнить verify-publisher; если OAuth отозван — повторить вход.
Копии на том же VPS не защищают от полной потери сервера.

## Проверка 25.09.2026

Серверный OAuth и push permission подтверждены. Реально создана ветка
`swarm-publication-probe`, commit `6aa209c8caa7fa7512a6350a03def6042c3921cc`
и [draft PR #2](https://github.com/gooddaytoday/loginom-ai-agent/pull/2) в `loginom`.
GitHub API подтвердил author/committer и автора PR `kartamyshev-dev`.
PR закрыт без merge; ветка оставлена для проверки. Sampling не запускался.
