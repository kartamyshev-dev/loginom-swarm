# Paperclip

Публичный адрес: https://paperclip.kartamyshev.dev

Проект содержит инфраструктуру установки Paperclip v2026.916.1. Исходный код приложения находится в https://github.com/paperclipai/paperclip.

## Подключение и обслуживание

SSH-реквизиты находятся в локальном `.env` (права `0600`, исключён из Git). Требуется `sshpass`. Скрипт не печатает пароль:

```sh
./scripts/server.sh
./scripts/server.sh 'cd /opt/paperclip && docker compose ps'
./scripts/server.sh 'cd /opt/paperclip && docker compose logs --tail=100 paperclip'
```

Секреты приложения находятся только в `/opt/paperclip/.env` на сервере. Не копировать туда SSH-реквизиты. Не публиковать вывод `docker compose config`: он содержит секреты; для проверки использовать `docker compose config -q`.

Приложение и PostgreSQL не публикуют порты хоста. Caddy обслуживает 80/443, автоматически продлевает TLS и поддерживает WebSocket. Данные находятся в `/opt/paperclip/data`, образы закреплены по digest. Начальный `instance-config.json` копируется в `data/paperclip/instances/default/config.json` только при первой установке; действующую конфигурацию не перезаписывать при обновлении.

## Первый вход

Использовать одноразовую ссылку из локального `private/admin-invite.txt`, создать свою учётную запись и принять приглашение владельца. Файл исключён из Git. При истечении ссылки создать новую:

```sh
./scripts/server.sh 'cd /opt/paperclip && docker compose exec -T paperclip node cli/node_modules/tsx/dist/cli.mjs cli/src/index.ts auth bootstrap-ceo'
```

Не использовать `--force`, если владелец уже зарегистрирован. AI-агенты и их авторизация настраиваются отдельно.

## Резервные копии

`paperclip-backup.timer` запускает копирование ежедневно в 03:15–03:20 по Москве. Срок хранения — 7 суток; каталог `/opt/paperclip/backups`, доступ только root. Во время копирования приложение кратковременно останавливается для согласованности файлов с БД. Скрипт автоматически запускает его снова даже при ошибке копирования.

Архив включает дамп PostgreSQL, данные Paperclip, секреты и конфигурацию. TLS-сертификаты не архивируются: Caddy может выпустить их заново.

```sh
./scripts/server.sh 'systemctl start paperclip-backup.service'
./scripts/server.sh 'systemctl list-timers paperclip-backup.timer --no-pager'
./scripts/server.sh 'journalctl -u paperclip-backup.service -n 30 --no-pager'
```

Копии на этом же сервере не защищают от потери сервера. Внешнее хранилище пока не настроено. Секреты в архиве не зашифрованы отдельно: защищать архив как пароль.

## Обновление

1. Проверить release notes и совместимость миграций выбранного релиза. Сохранить текущие digest и конфигурацию.
2. Выполнить резервную копию и проверить `SHA256SUMS`.
3. Закрепить новый официальный образ по digest в `compose.yaml`, синхронизировать конфигурацию с сервером. Не заменять действующий `.env`.
4. Выполнить в `/opt/paperclip`: `docker compose config -q`, `docker compose pull`, `docker compose up -d --wait`.
5. Проверить HTTPS, `/api/health`, вход и данные. Записать версию и результаты в `DEPLOYMENT.md`.

Автоматическое обновление образов не включено. Откат после несовместимой миграции требует старого образа и восстановления соответствующей резервной копии, а не только смены тега.

## Восстановление

Действия ниже заменяют текущие данные; перед восстановлением сохранить отдельную копию текущего состояния.

1. Выбрать каталог копии, проверить `sha256sum -c SHA256SUMS`. Просмотреть список `tar -tzf files.tar.gz`.
2. Остановить таймер и весь стек: `systemctl stop paperclip-backup.timer`, затем `docker compose down` **без `-v`**.
3. Переместить действующий `data` в отдельный каталог сохранения. Извлечь `files.tar.gz` в `/opt/paperclip`; архив восстанавливает `.env`, конфигурацию, скрипты и `data/paperclip`.
4. Запустить только БД: `docker compose up -d --wait db`. Новая пустая БД должна использовать пароль из восстановленного `.env`.
5. Восстановить дамп: `docker compose exec -T db pg_restore -U paperclip -d paperclip --exit-on-error < /путь/к/database.dump`.
6. Выполнить `docker compose up -d --wait`; Caddy получает сертификат при наличии корректного DNS и доступных портов 80/443. Проверить вход, данные и health.
7. Установить восстановленные unit-файлы из `systemd/` в `/etc/systemd/system/`, выполнить `systemctl daemon-reload` и `systemctl enable --now paperclip-backup.timer`.

Не удалять сохранённое предыдущее состояние до успешной проверки. Не применять `docker compose down -v`.
