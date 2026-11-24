"""Tests for the trusted harness itself: fail-closed verdicts, artifact handling, the sandbox."""
import json
import os
import pathlib
import sys
import tempfile
import time
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "harness"))
sys.path.insert(0, str(ROOT / "scripts"))
import deltaos_harness as H  # noqa: E402
from validate_receipt import validate  # noqa: E402


class HarnessCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="deltaos-harness-test-")
        base = pathlib.Path(self.tmp.name)
        os.chmod(base, 0o755)
        self.saved = (H.WORKSPACE, H.LOGS, H.TESTS)
        H.WORKSPACE, H.LOGS, H.TESTS = base / "workspace", base / "logs", base / "tests"
        for path in (H.WORKSPACE, H.LOGS, H.TESTS):
            path.mkdir()
        (H.TESTS / "grade.py").write_text("# stand-in grader\n")

    def tearDown(self):
        H.WORKSPACE, H.LOGS, H.TESTS = self.saved
        self.tmp.cleanup()

    def grade(self, body):
        self.assertEqual(H.run_grader("deltaos/unit-test", "test/1", body), 0)
        receipt = json.loads((H.LOGS / "receipt.json").read_text())
        reward = (H.LOGS / "reward.txt").read_text().strip()
        self.assertEqual(reward, str(receipt["reward"]))
        self.assertEqual(json.loads((H.LOGS / "feedback.json").read_text()), receipt)
        self.assertEqual(validate(receipt), [])
        return receipt


class Verdicts(HarnessCase):
    def test_pass_needs_a_true_check_and_evidence(self):
        def body(ctx):
            ctx.receipt.artifact("a.c", b"int x;")
            ctx.receipt.check("semantics", True)
            ctx.receipt.add_evidence("TESTED", "it works", "pass", "3 cases")
        receipt = self.grade(body)
        self.assertEqual((receipt["reward"], receipt["assurance"]), (1, "TESTED"))

    def test_strongest_passing_class_is_the_summary(self):
        def body(ctx):
            ctx.receipt.artifact("a.c", b"int x;")
            ctx.receipt.check("a", True)
            ctx.receipt.add_evidence("PROVED_WITHIN_MODEL", "all inputs", "pass", "cbmc")
            ctx.receipt.add_evidence("TESTED", "cases", "pass", "5")
            ctx.receipt.add_evidence("KERNEL_ACCEPTED", "loads", "not_run", "")
        self.assertEqual(self.grade(body)["assurance"], "PROVED_WITHIN_MODEL")

    def test_no_checks_is_not_a_pass(self):
        receipt = self.grade(lambda ctx: ctx.receipt.artifact("a.c", b""))
        self.assertEqual(receipt["reward"], 0)

    def test_only_not_run_checks_is_not_a_pass(self):
        def body(ctx):
            ctx.receipt.artifact("a.c", b"")
            ctx.receipt.check("kernel", "NOT_RUN: off")
        self.assertEqual(self.grade(body)["reward"], 0)

    def test_one_false_check_fails(self):
        def body(ctx):
            ctx.receipt.artifact("a.c", b"")
            ctx.receipt.check("a", True)
            ctx.receipt.check("b", False)
        receipt = self.grade(body)
        self.assertEqual((receipt["reward"], receipt["assurance"]), (0, "REFUTED"))
        self.assertEqual(receipt["counterexample"]["failed"], ["b"])

    def test_reject_becomes_refuted_with_counterexample(self):
        def body(ctx):
            ctx.receipt.artifact("a.c", b"")
            ctx.receipt.check("a", True)
            raise H.Reject("wrong_decision", case=[1, 2], expected=0, actual=1)
        receipt = self.grade(body)
        self.assertEqual((receipt["reward"], receipt["assurance"]), (0, "REFUTED"))
        self.assertEqual(receipt["counterexample"]["case"], [1, 2])

    def test_crash_in_grader_is_unknown_and_zero(self):
        def body(ctx):
            ctx.receipt.artifact("a.c", b"")
            ctx.receipt.check("a", True)
            raise RuntimeError("grader bug")
        receipt = self.grade(body)
        self.assertEqual((receipt["reward"], receipt["assurance"]), (0, "UNKNOWN"))
        self.assertIn("grader bug", receipt["error"])

    def test_reward_is_zero_while_the_grader_runs(self):
        seen = []

        def body(ctx):
            seen.append((H.LOGS / "reward.txt").read_text())
            ctx.receipt.artifact("a.c", b"")
            ctx.receipt.check("a", True)
            ctx.receipt.add_evidence("TESTED", "x", "pass", "y")
        self.grade(body)
        self.assertEqual(seen, ["0\n"])

    def test_missing_required_tool_fails_closed(self):
        def body(ctx):
            ctx.receipt.artifact("a.c", b"")
            ctx.receipt.check("a", True)
            ctx.require_tool("definitely-not-a-real-tool-xyz", "proof")
        os.environ.pop("DELTAOS_ALLOW_DEGRADED", None)
        receipt = self.grade(body)
        self.assertEqual((receipt["reward"], receipt["assurance"]), (0, "UNKNOWN"))

    def test_seed_is_replayable(self):
        os.environ["DELTAOS_SEED"] = "feedface"
        try:
            self.assertEqual(H.episode_seed(), "feedface")
            first = [H.rng("feedface", "cases").random() for _ in range(3)]
            again = [H.rng("feedface", "cases").random() for _ in range(3)]
            other = [H.rng("feedface", "faults").random() for _ in range(3)]
        finally:
            del os.environ["DELTAOS_SEED"]
        self.assertEqual(first, again)
        self.assertNotEqual(first, other)
        self.assertNotEqual(H.episode_seed(), H.episode_seed())


class Artifacts(HarnessCase):
    def test_reads_a_regular_file(self):
        (H.WORKSPACE / "a.c").write_bytes(b"int x;")
        self.assertEqual(H.read_artifact("a.c"), b"int x;")

    def test_refuses_missing_symlink_directory_and_oversize(self):
        (H.TESTS / "secret").write_text("hidden")
        os.symlink(H.TESTS / "secret", H.WORKSPACE / "link.c")
        (H.WORKSPACE / "dir.c").mkdir()
        (H.WORKSPACE / "big.c").write_bytes(b"x" * 300_000)
        for name in ("absent.c", "link.c", "dir.c", "big.c"):
            with self.assertRaises(H.Reject, msg=name):
                H.read_artifact(name)


class SandboxRuns(HarnessCase):
    def setUp(self):
        super().setUp()
        self.sbx = H.Sandbox()

    def tearDown(self):
        self.sbx.close()
        super().tearDown()

    def test_runs_and_captures(self):
        result = self.sbx.run(["sh", "-c", "cat; echo err >&2; exit 3"], input=b"hello")
        self.assertEqual((result.returncode, result.stdout, result.stderr.strip()), (3, b"hello", b"err"))

    def test_environment_is_scrubbed(self):
        os.environ["DELTAOS_SECRET_FOR_TEST"] = "leak"
        try:
            result = self.sbx.run(["sh", "-c", "env"])
        finally:
            del os.environ["DELTAOS_SECRET_FOR_TEST"]
        self.assertNotIn(b"leak", result.stdout)
        self.assertNotIn(b"DELTAOS_", result.stdout)

    def test_timeout_kills_the_whole_session(self):
        marker = self.sbx.path("alive")
        started = time.monotonic()
        result = self.sbx.run(["sh", "-c", f"(sleep 1; touch {marker}) & sleep 30"], timeout=0.5)
        self.assertTrue(result.timed_out)
        self.assertLess(time.monotonic() - started, 10)
        time.sleep(1.5)
        self.assertFalse(marker.exists(), "a background child outlived the run")

    def test_output_flood_is_cut_off(self):
        result = self.sbx.run(["sh", "-c", "while :; do echo aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa; done"],
                              timeout=20, max_output=1 << 20,
                              limits={"cpu": 10, "fsize": 1 << 20, "nofile": 64})
        self.assertFalse(result.ok)
        self.assertLessEqual(len(result.stdout), 1 << 20)

    @unittest.skipUnless(H.LINUX and os.geteuid() == 0, "uid separation needs root on Linux")
    def test_candidate_cannot_touch_the_verdict_or_the_tests(self):
        H.lock_down()
        self.assertTrue(self.sbx.separated)
        result = self.sbx.run(["sh", "-c", f"id -u; echo 1 > {H.LOGS}/reward.txt; cat {H.TESTS}/grade.py"])
        self.assertEqual(result.stdout.split()[0], str(self.sbx.uid).encode())
        self.assertNotIn(b"stand-in grader", result.stdout)
        self.assertFalse((H.LOGS / "reward.txt").exists())

    @unittest.skipUnless(H.LINUX and os.geteuid() == 0, "uid separation needs root on Linux")
    def test_kill_all_reaches_a_daemon_that_left_the_session(self):
        marker = self.sbx.path("daemon-alive")
        self.sbx.run(["sh", "-c", f"setsid sh -c 'sleep 2; touch {marker}' >/dev/null 2>&1 &"])
        self.sbx.kill_all()
        time.sleep(2.5)
        self.assertFalse(marker.exists(), "a daemonised candidate process survived kill_all")


class IntegerC(unittest.TestCase):
    OK = [
        "int f(unsigned int a, unsigned int b) { if (a & 1U) return (a ^ b) == 0x10U; return a > b ? 1 : 0; }",
        "static int g(unsigned x) { return x * 16U >> 3; } int f(unsigned char n) { return g((unsigned)n + 1U) > 255U; }",
        "typedef unsigned int u32; int f(u32 a) { u32 m = (u32)(a & 0xffU); return m == 9U && (a & ~0U) != 0; }",
        "struct budget { unsigned long long remaining; unsigned long long total; };"
        "int charge(struct budget *state, unsigned long long amount) {"
        " if (!state || amount > state->remaining) return 0; state->remaining -= amount; return 1; }",
    ]
    BAD = {
        "sizeof": "int f(int a) { return sizeof(long double) == 8; }",
        "address": "int f(int a) { int p = 0; return (unsigned long)&p > 5; }",
        "address after cast": "typedef unsigned long u64; int f(int a) { int p; return (u64)&p >> 63; }",
        "asm": 'int f(int a) { __asm__("nop"); return a; }',
        "builtin": "int f(int a) { return __builtin_constant_p(a); }",
        "array": "int f(int a) { static const int t[2] = {0, 1}; return t[a & 1]; }",
        "string": 'int f(int a) { return "x"[0]; }',
        "function value": "int f(int a) { return (unsigned long)f > 1; }",
        "float": "int f(int a) { return a * 1.5 > 2; }",
        "long double": "int f(int a) { long double x = a; return x > 2; }",
        "pointer param leak": "struct budget { unsigned long long r; };"
                              "int charge(struct budget *s, unsigned long long x) { return (unsigned long)s > x; }",
        "other struct": "struct other { int x; }; int f(int a) { return a; }",
        "label address": "int f(int a) { l: return (unsigned long)&&l > 0; }",
    }

    def test_accepts_plain_integer_code(self):
        for text in self.OK:
            self.assertEqual(H.integer_c_problems(text, function="charge", structs=("budget",)), [], text)

    def test_rejects_ways_to_observe_the_target(self):
        for label, text in self.BAD.items():
            self.assertTrue(H.integer_c_problems(text, function="charge", structs=("budget",)), label)


class Freestanding(unittest.TestCase):
    def test_rules(self):
        clean = {"undefined": [], "sections": {".text": 40, ".rodata": 8, ".bss": 0}}
        H.require_freestanding(clean)
        for report in ({"undefined": ["write"], "sections": {".text": 1}},
                       {"undefined": [], "sections": {".text": 1, ".init_array": 8}},
                       {"undefined": [], "sections": {".text": 1, ".bss": 4}}):
            with self.assertRaises(H.Reject):
                H.require_freestanding(report)
        H.require_freestanding({"undefined": ["memcpy"], "sections": {".text": 1, ".data": 8}},
                               allowed_undefined=("memcpy",), allow_mutable_state=True)


if __name__ == "__main__":
    unittest.main()
