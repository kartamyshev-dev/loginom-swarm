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

## Ubuntu 26.04 LAN host

Пакетный профиль `bwrap-userns-restrict` добавляет `unpriv_bwrap` с запретом
всех capabilities, включая вложенный user namespace Chromium. Это подтверждено
DENIED sys_admin и вторичной SUID sandbox ошибкой; SUID-биты не менять.

Для Swarm используется неизменяемая root-owned копия пакетного Bubblewrap
0.11.1-1ubuntu0.3 по пути `/usr/local/libexec/loginom-swarm/bwrap`. Установка:
`swarm/migration/install-bubblewrap.sh`; runtime проверяет SHA256 перед каждым
запуском. Системный `/usr/bin/bwrap` и его AppArmor policy остаются без изменений.
Процессы Swarm сохраняют собственный enforced профиль loginom-swarm-worker,
NoNewPrivileges, пустые host capabilities, --unshare-all и --cap-drop ALL.
Идентичный бинарник не получает SUID/capabilities. Роли имеют UID21001 на LAN host.

Обновление bubblewrap требует новой квалификации binary hash, изменения pin
в installer и sandbox.py, повторных boundary/Chromium checks. Эта копия не
обновляется автоматически apt; включена в ежедневную резервную копию.

Профиль LAN worker объявляет ABI5.0: ABI3.0 не включает userns_create mediation
и Ubuntu26.04 добавляет fallback unprivileged_userns с запретом capabilities
даже при наличии текстового userns rule. ABI обновлён только у Swarm; глобальные
профили и sysctl не изменяются. Применение требует перезапуска worker.

ABI5.0 сам по себе недостаточен: при запуске от непривилегированного пользователя
Ubuntu сохраняет компонент unconfined в стеке. Профиль Swarm явно привязан к
единственному root-owned пути dedicated Bubblewrap; exec переводит этот компонент
в тот же профиль. Живой тест подтвердил внутри sandbox строго
`loginom-swarm-worker (enforce)`, без fallback unprivileged_userns.

Chromium проверяется через Playwright из закреплённого CLI и его Node24.19.0,
под Xvfb, с chromiumSandbox=true. Прямой --dump-dom был неподходящим тестом
для этого графического окружения. Проверены about:blank и chrome://sandbox:
namespace и Seccomp-BPF Yes, без подключения к Loginom, профили read-only.
