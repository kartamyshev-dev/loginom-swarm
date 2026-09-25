import importlib.util
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "runtime" / (name + ".py"))
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


env = module("environment")
policy = module("evidence")


class BoundaryTests(unittest.TestCase):
    def test_control_plane_and_shell_injection_secrets_do_not_reach_models(self):
        source = {name: "sensitive" for name in ["DATABASE_URL", "BETTER_AUTH_SECRET",
                  "PAPERCLIP_SECRETS_MASTER_KEY", "PAPERCLIP_API_KEY", "GH_TOKEN",
                  "OPENVIKING_API_KEY", "BASH_ENV", "LD_PRELOAD", "NODE_OPTIONS",
                  "PYTHONPATH", "HTTP_PROXY", "GIT_CONFIG_COUNT", "SERVER_PASSWORD"]}
        clean = env.model_environment(source, "developer", "/opt/loginom-worker/profiles/sampling/developer")
        self.assertFalse(set(source) & set(clean))

    def test_acceptance_keeps_uncertain_mutations_blocked(self):
        clean = env.model_environment({}, "acceptance", "/opt/loginom-worker/profiles/sampling/acceptance")
        self.assertEqual(clean["LOGINOM_AI_AGENT_STRICT_RECOVERY"], "1")

    def test_cross_role_profile_rejected(self):
        with self.assertRaises(ValueError):
            env.model_environment({}, "reviewer", "/opt/loginom-worker/profiles/sampling/developer")

    def test_blank_readiness_never_starts_node(self):
        with self.assertRaises(policy.Blocked):
            policy.admit({"node": "sampling", "manualStart": True}, {})

    def test_review_of_old_commit_is_rejected(self):
        with self.assertRaises(policy.Blocked):
            policy.review("a" * 40, {"commit": "b" * 40, "decision": "pass", "openFindings": []}, "tree", "tree")

    def test_reviewer_mutation_is_rejected(self):
        with self.assertRaises(policy.Blocked):
            policy.review("a" * 40, {"commit": "a" * 40, "decision": "pass", "openFindings": []}, "before", "after")

    def test_claimed_pass_without_candidate_is_rejected(self):
        with self.assertRaises(policy.Blocked):
            policy.accept("a" * 40, {}, {"status": "completed", "actual": [1]}, [1])

    def test_retry_never_ignores_unknown_mutation_or_limits(self):
        for args in [(2, 10, True, True), (0, 28800, True, True),
                     (0, 10, False, True), (0, 10, True, False)]:
            with self.subTest(args=args), self.assertRaises(policy.Blocked):
                policy.correction(*args)
        self.assertEqual(policy.correction(1, 100), 2)


if __name__ == "__main__":
    unittest.main()
