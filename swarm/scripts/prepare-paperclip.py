#!/usr/bin/env python3
"""Create a non-running native pipeline. Repeated preparation reuses identities."""
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("owner_api", ROOT / "swarm/scripts/paperclip-api.py")
api = importlib.util.module_from_spec(spec)
spec.loader.exec_module(api)
cfg = json.loads((ROOT / "swarm/config/campaign.json").read_text())
stages = [
    ("setup", "Подготовка системы — запуск закрыт", "open"),
    ("ready", "Ожидает ручного старта", "open"),
    ("admission", "Проверка допуска", "working"),
    ("preparation", "Семантика и эталон", "working"),
    ("development", "Разработка", "working"),
    ("review", "Независимое ревью", "review"),
    ("build", "Полная сборка CLI", "working"),
    ("acceptance", "Приёмка в Loginom", "working"),
    ("publication", "Публикация PR", "working"),
    ("awaiting-human", "PR ожидает решения пользователя", "review"),
    ("blocked", "Остановлено — нужен разбор", "open"),
    ("done", "Решение пользователя принято", "done"),
    ("cancelled", "Отменено", "cancelled"),
]
c = api.Client()
try:
    pipelines = c.request("GET", f'/api/companies/{cfg["companyId"]}/pipelines')
    candidates = [row.get("pipeline", row) for row in pipelines]
    matches = [row for row in candidates if row["key"] == cfg["pipelineKey"]]
    if len(matches) > 1:
        raise RuntimeError("Ambiguous pipeline identity")
    if matches:
        pipeline = matches[0]
    else:
        result = c.request("POST", f'/api/companies/{cfg["companyId"]}/pipelines', {
            "key": cfg["pipelineKey"], "name": "Loginom Swarm — один узел",
            "projectId": cfg["projectId"], "enforceTransitions": True,
            "description": "Подготовка системы. Автоматизации ещё не подключены. Sampling не запускать до завершения инфраструктурных проверок.",
            "stages": [{"key": key, "name": name, "kind": kind, "position": index * 100, "config": ({"approveToStageKey": "build" if key == "review" else "done", "rejectToStageKey": "blocked", "requestChangesToStageKey": "development", "reviewerKind": "any" if key == "review" else "human"} if kind == "review" else {})}
                       for index, (key, name, kind) in enumerate(stages)]})
        pipeline = result.get("pipeline", result)
    # Do not replace live transitions/config during a repeated preparation.
    cases = c.request("GET", f'/api/pipelines/{pipeline["id"]}/cases')
    matches = [row["case"] for row in cases if row["case"].get("caseKey") == "sampling-pilot"]
    if len(matches) > 1:
        raise RuntimeError("Ambiguous Sampling case")
    case = matches[0] if matches else c.request("POST", f'/api/pipelines/{pipeline["id"]}/cases', {
        "caseKey": "sampling-pilot",
        "title": "Sampling: последовательный отбор и отбор со смещением",
        "stageKey": "setup", "summary": "Система готовится. Запуск закрыт до проверок памяти, sandbox, Loginom, сборки и GitHub.",
        "fields": {"node": "sampling", "manualStart": False, "setupStatus": "incomplete",
                   "sourceCommit": cfg["sourceCommit"], "correctionCycles": 0, "activeSeconds": 0}})["case"]
    links = c.request("GET", f'/api/cases/{case["id"]}/issue-links')
    if not any(row.get("issueId", row.get("link", {}).get("issueId")) == cfg["originIssueId"] for row in links):
        c.request("POST", f'/api/cases/{case["id"]}/issue-links', {"issueId": cfg["originIssueId"], "role": "origin"})
    cfg.update(pipelineId=pipeline["id"], caseId=case["id"])
    (ROOT / "swarm/config/campaign.json").write_text(json.dumps(cfg, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({"pipelineId": pipeline["id"], "caseId": case["id"], "executionStarted": False}))
finally:
    c.close()
