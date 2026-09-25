"""Coordinator policy for native Paperclip case transitions.

No independent queue or database lives here. The authoritative case version,
lease, stage, and documents remain in Paperclip. These pure gates reject stale,
incomplete, or mismatched evidence before the coordinator requests a transition.
"""
import re

STAGES = ("ready", "admission", "preparation", "development", "review", "build",
          "acceptance", "publication", "awaiting-human")
GATES = {"resources", "isolation", "developer_oauth", "reviewer_oauth",
         "acceptance_oauth", "exact_models", "memory", "loginom", "toolchain",
         "github", "backup_restore"}
SHA = re.compile(r"^[0-9a-f]{40}$")
DIGEST = re.compile(r"^[0-9a-f]{64}$")


class Blocked(ValueError):
    pass


def require(condition, reason):
    if not condition:
        raise Blocked(reason)


def admit(case, evidence):
    require(case.get("node") == "sampling", "Only Sampling is enabled")
    require(case.get("manualStart") is True and case.get("responsibleUserId"), "Manual owner start required")
    require(SHA.fullmatch(case.get("sourceCommit", "")), "Source commit must be pinned")
    require(evidence.get("imageDigest") == case.get("imageDigest") and
            re.fullmatch(r"sha256:[0-9a-f]{64}", evidence.get("imageDigest", "")), "Image evidence does not match")
    require(set(evidence.get("checks", {})) == GATES, "Incomplete admission evidence")
    for key in GATES:
        result = evidence["checks"][key]
        require(result.get("status") == "pass" and result.get("artifactSha256") and
                DIGEST.fullmatch(result["artifactSha256"]), f"Unverified gate: {key}")
    require(evidence.get("availableMemoryMiB", 0) >= 512, "Less than 512 MiB available")
    require(evidence.get("freeDiskGiB", 0) >= 20, "Less than 20 GiB free")
    require(evidence.get("oom") is False, "OOM status not verified")


def review(candidate_commit, report, before_tree, after_tree):
    require(SHA.fullmatch(candidate_commit), "Invalid candidate commit")
    require(report.get("commit") == candidate_commit, "Review does not match candidate")
    require(before_tree == after_tree and bool(before_tree), "Reviewer changed candidate")
    require(report.get("decision") == "pass" and report.get("openFindings") == [], "Review has unresolved findings")
    require(bool(report.get("artifactSha256")) and DIGEST.fullmatch(report["artifactSha256"]), "Review artifact missing")


def accept(commit, build, observation, oracle):
    require(SHA.fullmatch(commit), "Invalid acceptance commit")
    require(build.get("commit") == commit, "Build does not match reviewed commit")
    require(build.get("completeCli") is True, "Acceptance requires full CLI build")
    digest = build.get("sha256", "")
    require(DIGEST.fullmatch(digest), "Missing candidate hash")
    require(observation.get("cliSha256") == digest, "Acceptance used another CLI")
    require(observation.get("commit") == commit, "Acceptance commit mismatch")
    require(observation.get("status") == "completed", "Unknown or failed acceptance outcome")
    require(observation.get("elapsedSeconds", 1801) <= 1800, "Acceptance time limit exceeded")
    require(observation.get("nodeType") == "Sampling", "Wrong Loginom node")
    require(observation.get("modes") == ["sequential", "offset"], "Required Sampling modes not covered")
    require(observation.get("saved") is True and observation.get("reopenedIndependently") is True,
            "Save and independent reopen required")
    require(observation.get("cleanupConfirmed") is True, "Loginom cleanup is not confirmed")
    require(bool(oracle) and observation.get("actual") == oracle, "Independent oracle mismatch")
    require(DIGEST.fullmatch(observation.get("artifactSha256", "")), "Acceptance evidence missing")


def correction(cycles, active_seconds, mutation_known=True, cleanup_confirmed=True):
    require(type(cycles) is int and 0 <= cycles < 2, "Correction limit reached")
    require(0 <= active_seconds < 8 * 3600, "Active processing time limit reached")
    require(mutation_known, "Unknown mutation outcome requires reconciliation")
    require(cleanup_confirmed, "Cleanup must be confirmed before another attempt")
    return cycles + 1
