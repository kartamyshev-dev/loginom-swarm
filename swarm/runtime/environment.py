"""One explicit environment contract for untrusted model processes.

The coordinator/publisher use Paperclip's native short-lived credentials. Model
processes receive neither administrative credentials nor the Paperclip API key.
"""
import re

COMMON = {"LANG", "LC_ALL", "TERM", "COLORTERM", "NO_COLOR"}
ROLE_NAMES = {"developer", "reviewer", "acceptance"}


def model_environment(source, role, profile):
    if role not in ROLE_NAMES:
        raise ValueError("Unknown model role")
    if not re.fullmatch(r"/opt/loginom-worker/profiles/[a-z0-9_-]+/(developer|reviewer|acceptance)", profile):
        raise ValueError("Profile must be a registered per-campaign role directory")
    if profile.rsplit("/", 1)[1] != role:
        raise ValueError("Profile belongs to another role")
    result = {key: value for key, value in source.items() if key in COMMON}
    result.update(HOME=profile, TMPDIR="/tmp", PATH="/opt/loginom-swarm/runtime/bin:/usr/local/bin:/usr/bin:/bin",
                  LANG=result.get("LANG", "C.UTF-8"), GIT_TERMINAL_PROMPT="0")
    if role == "acceptance":
        result.update(LOGINOM_AI_AGENT_CLI_PROFILE=profile, DISPLAY=":99",
                      LOGINOM_AI_AGENT_STRICT_RECOVERY="1", LOGINOM_AI_AGENT_SYSTEM_PROXY="off")
    else:
        result["CODEX_HOME"] = profile
    return result
