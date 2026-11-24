import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

from gym_runtime import (DeltaOSEnvironment, ScenarioError, consistent_hypotheses, generate,
                         informative_probes, validate)
from gym_runtime.evaluate import evaluate
from gym_runtime.policies import CarefulPolicy

ROOT = pathlib.Path(__file__).resolve().parents[2]
DEMO = json.loads((ROOT / "scenarios" / "diagnosis-demo.json").read_text())
HIDDEN = json.loads((ROOT / "scenarios" / "not-observable-demo.json").read_text())


def play(env, actions):
    out = None
    for action in actions:
        out = env.step(action)
    return out


class Rewards(unittest.TestCase):
    def test_justified_correct_answer(self):
        env = DeltaOSEnvironment(DEMO, "fd-leak", seed=1)
        _, reward, terminated, truncated, info = play(env, [
            {"type": "observe", "name": "proc-fd-inventory"},
            {"type": "answer", "hypothesis": "fd-leak"}])
        self.assertEqual(info["outcome"], "justified_correct")
        self.assertEqual(info["consistent_hypotheses"], ["fd-leak"])
        self.assertAlmostEqual(reward, 1 - 0.25 * 2 / 10)
        self.assertTrue(terminated)
        self.assertFalse(truncated)

    def test_lucky_correct_answer_earns_nothing(self):
        env = DeltaOSEnvironment(DEMO, "fd-leak", seed=1)
        _, reward, _, _, info = env.step({"type": "answer", "hypothesis": "fd-leak"})
        self.assertEqual((reward, info["outcome"]), (0.0, "lucky_correct"))

    def test_wrong_answer_costs(self):
        env = DeltaOSEnvironment(DEMO, "fd-leak", seed=1)
        _, reward, _, _, info = env.step({"type": "answer", "hypothesis": "vfs-stall"})
        self.assertEqual((reward, info["outcome"]), (-1.0, "wrong"))

    def test_unknown_hypothesis_is_invalid(self):
        env = DeltaOSEnvironment(DEMO, "fd-leak", seed=1)
        _, reward, _, _, info = env.step({"type": "answer", "hypothesis": "cosmic-ray"})
        self.assertEqual((reward, info["outcome"]), (-1.0, "invalid"))

    def test_abstain_when_nothing_can_tell_the_rest_apart(self):
        env = DeltaOSEnvironment(HIDDEN, "slow-disk", seed=3)
        play(env, [{"type": "observe", "name": "proc-fd-inventory"}])
        _, reward, _, _, info = env.step({"type": "abstain"})
        self.assertEqual(info["consistent_hypotheses"], ["page-cache-thrash", "slow-disk"])
        self.assertEqual((reward, info["outcome"]), (0.5, "abstain_not_observable"))

    def test_premature_abstention_earns_nothing(self):
        env = DeltaOSEnvironment(DEMO, "vfs-stall", seed=3)
        _, reward, _, _, info = env.step({"type": "abstain"})
        self.assertEqual((reward, info["outcome"]), (0.0, "abstain_premature"))

    def test_abstention_counts_the_budget(self):
        case = json.loads(json.dumps(DEMO))
        case["budget"] = 1
        env = DeltaOSEnvironment(case, "vfs-stall", seed=3)
        play(env, [{"type": "observe", "name": "python-asyncio-tasks"}])
        _, reward, _, _, info = env.step({"type": "abstain"})
        self.assertEqual(info["outcome"], "abstain_not_observable")

    def test_step_penalties(self):
        env = DeltaOSEnvironment(DEMO, "vfs-stall", seed=3)
        self.assertEqual(env.step({"type": "observe", "name": "nope"})[1], -0.05)
        self.assertEqual(env.step({"type": "dance"})[1], -0.05)
        self.assertEqual(env.step("not a dict")[1], -0.05)
        play(env, [{"type": "observe", "name": "syscall-latency"}, {"type": "observe", "name": "syscall-latency"}])
        _, reward, _, _, info = env.step({"type": "observe", "name": "syscall-latency"})
        self.assertEqual((reward, info["error"]), (-0.1, "over_budget"))

    def test_truncation(self):
        env = DeltaOSEnvironment(DEMO, "vfs-stall", seed=3, max_steps=3)
        env.step({"type": "dance"})
        env.step({"type": "dance"})
        _, reward, terminated, truncated, info = env.step({"type": "dance"})
        self.assertEqual((reward, terminated, truncated, info["outcome"]), (0.0, False, True, "truncated"))
        with self.assertRaises(RuntimeError):
            env.step({"type": "abstain"})


class Episodes(unittest.TestCase):
    def test_hidden_cause_is_not_in_the_observation(self):
        env = DeltaOSEnvironment(DEMO, "fd-leak", seed=1)
        observation, _ = env.reset()
        self.assertNotIn("fd-leak", json.dumps({k: v for k, v in observation.items() if k != "hypotheses"
                                                and k != "probes"}))

    def test_reset_restores_budget_and_history(self):
        env = DeltaOSEnvironment(DEMO, "vfs-stall", seed=10)
        env.step({"type": "observe", "name": "vfs-fsync-latency"})
        observation, _ = env.reset()
        self.assertEqual((observation["remaining_budget"], observation["history"]), (10, []))

    def test_seeded_reset_is_reproducible(self):
        env = DeltaOSEnvironment(DEMO, seed=0)
        causes_a = [env.reset(seed=s) and env.hidden for s in range(20)]
        causes_b = [env.reset(seed=s) and env.hidden for s in range(20)]
        self.assertEqual(causes_a, causes_b)
        self.assertGreater(len(set(causes_a)), 1)

    def test_cause_from_options(self):
        env = DeltaOSEnvironment(DEMO, seed=0)
        env.reset(options={"hidden_cause": "vfs-stall"})
        self.assertEqual(env.hidden, "vfs-stall")
        with self.assertRaises(ScenarioError):
            env.reset(options={"hidden_cause": "nope"})

    def test_observations_are_copies(self):
        env = DeltaOSEnvironment(DEMO, "fd-leak", seed=1)
        observation, _ = env.reset()
        observation["probes"][0]["readings"]["fd-leak"].append("tampered")
        observation["history"].append({"probe": "x", "value": "y"})
        fresh = env.state()["observation"]
        self.assertNotIn("tampered", fresh["probes"][0]["readings"]["fd-leak"])
        self.assertEqual(fresh["history"], [])

    def test_constructor_does_not_keep_the_callers_dict(self):
        case = json.loads(json.dumps(DEMO))
        env = DeltaOSEnvironment(case, "fd-leak", seed=1)
        case["probes"].clear()
        self.assertEqual(len(env.state()["observation"]["probes"]), 5)


class Scenarios(unittest.TestCase):
    def test_validation_messages(self):
        bad = [[], {"hypotheses": []}, {"hypotheses": ["a", "a"], "budget": 1, "probes": []},
               {"hypotheses": ["a"], "budget": -1, "probes": []},
               {"hypotheses": ["a", "b"], "budget": 1, "probes": [{"name": "p", "cost": 1, "readings": {"a": [1]}}]},
               {"hypotheses": ["a"], "budget": 1, "probes": [{"name": "p", "cost": -2, "readings": {"a": [1]}}]}]
        for case in bad:
            with self.assertRaises(ScenarioError):
                validate(case)

    def test_consistency_and_informative_probes(self):
        history = [{"probe": "proc-fd-inventory", "value": "stable"}]
        fits = consistent_hypotheses(HIDDEN, history)
        self.assertEqual(fits, ["page-cache-thrash", "slow-disk"])
        self.assertEqual(informative_probes(HIDDEN, fits, 10), [])
        self.assertIn("ebpf-sched-switch", informative_probes(DEMO, DEMO["hypotheses"], 10))

    def test_generator(self):
        self.assertEqual(generate(5), generate(5))
        case = generate(7, hypotheses=5, probes=6, unobservable_pair=True)
        for probe in case["probes"]:
            self.assertEqual(probe["readings"]["cause-0"], probe["readings"]["cause-1"])


class Policies(unittest.TestCase):
    def test_careful_beats_guessing(self):
        for case in (DEMO, HIDDEN, generate(11, hypotheses=5, probes=7, budget=14)):
            table = evaluate(case, episodes=150)
            self.assertGreater(table["careful"]["mean_reward"], table["guess"]["mean_reward"])
            self.assertGreaterEqual(table["careful"]["mean_reward"], table["one-probe"]["mean_reward"])

    def test_abstaining_beats_guessing_when_not_observable(self):
        table = evaluate(HIDDEN, episodes=200)
        self.assertGreater(table["careful"]["outcomes"].get("abstain_not_observable", 0), 0)
        self.assertGreater(table["careful"]["mean_reward"], 0.4)

    def test_careful_never_answers_without_evidence(self):
        env = DeltaOSEnvironment(DEMO, seed=0)
        policy = CarefulPolicy()
        for seed in range(50):
            observation, _ = env.reset(seed=seed)
            while True:
                observation, _, terminated, truncated, info = env.step(policy.act(observation))
                if terminated or truncated:
                    self.assertIn(info["outcome"], ("justified_correct", "abstain_not_observable"))
                    break


class Server(unittest.TestCase):
    def run_server(self, lines, *extra):
        proc = subprocess.run([sys.executable, "-m", "gym_runtime.stdio_server",
                               str(ROOT / "scenarios" / "diagnosis-demo.json"), *extra],
                              input="\n".join(lines) + "\n", capture_output=True, text=True, cwd=ROOT, timeout=30)
        return proc, [json.loads(line) for line in proc.stdout.splitlines()]

    def test_protocol_round_trip(self):
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as cause:
            cause.write("fd-leak\n")
        proc, out = self.run_server([
            json.dumps({"op": "reset", "seed": 4, "episode_id": "e1"}),
            json.dumps({"op": "step", "action": {"type": "observe", "name": "proc-fd-inventory"}}),
            json.dumps({"op": "step", "action": {"type": "answer", "hypothesis": "fd-leak"}}),
            json.dumps({"op": "state"}),
            "not json",
            json.dumps({"op": "fly"}),
            json.dumps({"op": "step", "action": {"type": "abstain"}}),
        ], "--cause-file", cause.name, "--seed", "4")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(out[1]["info"]["measurement"]["value"], "growing")
        self.assertEqual(out[2]["info"]["outcome"], "justified_correct")
        self.assertEqual(out[3]["episode_id"], "e1")
        self.assertTrue(out[3]["done"])
        self.assertIn("error", out[4])
        self.assertIn("error", out[5])
        self.assertIn("error", out[6])

    def test_cause_on_the_command_line_is_refused(self):
        proc = subprocess.run([sys.executable, "-m", "gym_runtime.stdio_server",
                               str(ROOT / "scenarios" / "diagnosis-demo.json"), "fd-leak"],
                              capture_output=True, text=True, cwd=ROOT, timeout=30)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("--cause-file", proc.stderr)


if __name__ == "__main__":
    unittest.main()
