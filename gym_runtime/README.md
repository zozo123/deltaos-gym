# Step environment for active diagnosis

`DeltaOSEnvironment` is a Gymnasium-style `reset()`/`step()` environment. A hidden root
cause is drawn per episode; the agent spends a budget on probes whose readings can
overlap between causes, then answers or abstains. It scores how the answer was reached,
not only whether it was right.

| Episode ends with | Reward | `info["outcome"]` |
|---|---:|---|
| the right answer, and the observations rule out every other cause | `1 - 0.25 * cost_used / budget` | `justified_correct` |
| the right answer, but other causes still fit the observations | `0` | `lucky_correct` |
| a wrong or unknown answer | `-1` | `wrong`, `invalid` |
| abstaining when no affordable probe can tell the remaining causes apart | `+0.5` | `abstain_not_observable` |
| abstaining when a probe could still help | `0` | `abstain_premature` |
| the step limit (default `4 * probes + 4`) | `0` | `truncated` |

Unknown probes or actions cost `-0.05` per step, a probe over budget `-0.1`.

```sh
PYTHONPATH=. python3 -m unittest discover -s gym_runtime/tests
PYTHONPATH=. python3 -m gym_runtime.evaluate            # baseline policies on scenarios/*.json
echo fd-leak > /tmp/cause
printf '%s\n' '{"op":"reset","seed":1}' \
  '{"op":"step","action":{"type":"observe","name":"proc-fd-inventory"}}' \
  '{"op":"step","action":{"type":"answer","hypothesis":"fd-leak"}}' |
  PYTHONPATH=. python3 -m gym_runtime.stdio_server scenarios/diagnosis-demo.json --cause-file /tmp/cause
```

Baselines, mean reward over 400 seeded episodes (`gym_runtime.evaluate`):

| Policy | `diagnosis-demo` | `not-observable-demo` |
|---|---:|---:|
| guess without looking | -0.775 | -0.635 |
| one probe, then the first cause that fits | -0.234 | -0.046 |
| probe until one cause fits, abstain when nothing can separate the rest | +0.899 | +0.631 |

The scenarios are explicit finite observation models with simulated readings, not
measurements from a live kernel. The hidden cause never leaves the environment process
and is never taken from the command line.
