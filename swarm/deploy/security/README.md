# Изоляция исполнителей на VPS

По решению пользователя 25.09.2026 исполнители вынесены в отдельную host-службу.
Paperclip остаётся в Docker. Production Docker security policy не менялась.
`container-probe/` — только исторические материалы неудавшейся проверки; их не
следует подключать к production Compose.

`loginom-swarm-worker.apparmor` основан на Moby profiles commit
`245180c51918481c0525424b3ee025d2b435d46c`; исходный шаблон и лицензия сохранены.
Добавлены userns/mount/pivot_root для непривилегированного namespace. Host-служба
UID1000 не получает capabilities, Docker socket или SSH-доступ. Модели запускаются
только через root-owned `runtime/sandbox.py`: отдельные PID/IPC/UTS/user/mount
namespaces, пустой корень, собственный /proc, точные mounts текущей роли.

Root-owned регистрация задаёт workspace/profile. Ревьювер получает workspace
read-only. Control socket, state, секреты Paperclip и чужие профили не монтируются.
Окружение строится из allowlist. Доступ к сети добавляется только операторским кодом
для OAuth/API; infrastructure probe запускается без сети.

systemd ProtectKernelLogs маскирует /proc/kmsg и мешает mount нового proc внутри
непривилегированного namespace. Не использовать также ProtectProc, ProcSubset или
ProtectKernelTunables. Изоляцию процессов обеспечивает Bubblewrap; host /proc не
bind-mount-ится. NoNewPrivileges и пустой CapabilityBoundingSet сохраняются.

Проверка `swarm/scripts/verify-host-worker.py` выполняется на VPS. 11 проверок для
каждой роли и шесть отрицательных RPC-запросов прошли. Это ещё не проверка полного
model/browser workload. Служба остаётся в setup и отклоняет запуск кампаний.
