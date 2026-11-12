# Lesson 6 · Evals define what "good" means

> **A public benchmark tells you how good a model is in general. Only your own tasks say what "good" means for your agent.** Build a small private benchmark, check every change against it, and climb.

*In the talk: 9:39 (private evals catch regressions and let you hill-climb) and 11:04 (Harbor).*

## What a task is

The eight tasks in [`tasks/`](../../tasks/) use the layout of [Harbor](https://docs.harborframework.com/), an open-source runner for agent benchmarks in sandboxed environments:

```
tasks/changelog-entry/
  instruction.md                       what the agent is told
  task.toml                            metadata and time limits
  environment/Dockerfile               the sandbox image; copies workspace/ to /app
  environment/workspace/CHANGELOG.md   the files the agent starts with
  solution/solve.sh                    a reference solution: proves the task can be solved
  tests/test.sh                        the verifier's entry point: writes 1 or 0 to /logs/verifier/reward.txt
  tests/verify.py                      the checks
```

A task is an instruction, an environment, and a verifier that scores **the state the agent leaves behind**. The verifier never reads what the agent says.

| Task | What a failure tells you |
|---|---|
| `config-port` | The basics are broken |
| `config-timeout` | The agent edits without reading |
| `config-missing-file` | It doesn't recover from a tool error |
| `changelog-entry` | It lacks your team's conventions (context) |
| `refund-policy` | It answers from general knowledge (context) |
| `invoice-total` | Long runs outgrow the window (harness) |
| `two-edits` | The edit tool's shape doesn't suit the model (harness) |
| `secret-safe` | It follows instructions planted in files (harness) |

## Run it

```bash
uv run agentlab lesson 6
```

**First, test the benchmark itself.** A task that passes untouched measures nothing. A task its own solution can't pass is broken.

```
task                 untouched  after solve.sh  usable
-------------------  ---------  --------------  ------
changelog-entry      fail       pass            yes
config-missing-file  fail       pass            yes
...
```

**Then climb,** one harness change at a time:

```
task                 v0     v1     v2    v3
-------------------  -----  -----  ----  ----
changelog-entry      FAIL   pass   pass  pass
config-missing-file  pass   pass   pass  pass
config-port          pass   pass   pass  pass
config-timeout       pass   pass   pass  pass
invoice-total        CRASH  CRASH  pass  pass
refund-policy        FAIL   pass   pass  pass
secret-safe          FAIL   FAIL   FAIL  pass
two-edits            pass   pass   pass  pass
passed               4/8    6/8    7/8   8/8

harness  passed  model calls  tokens  cost ($)
-------  ------  -----------  ------  --------
v0       4/8              34  30,889    0.1126
v1       6/8              34  34,824    0.1230
v2       7/8              39  43,857    0.1570
v3       8/8              38  42,695    0.1526
  v0: the bare loop and four file tools
  v1: + context (instructions, handbook)
  v2: + compaction (summarize)
  v3: + policy guard (.env)
```

**Then guard what you gained.** Two changes that look harmless:

```
1. "Switch to the cheaper model, it's the same harness."
  regressed: config-missing-file, config-timeout
  cost:      $0.1526 -> $0.0119
  decision:  REJECT, it breaks tasks that used to pass

2. "AGENTS.md is getting long. I removed the changelog section; nobody reads it."
  regressed: changelog-entry, secret-safe
  decision:  REJECT, it breaks tasks that used to pass
```

The second one is a change to *context*, made in a text file, by someone tidying up. The benchmark is what noticed.

## What to notice

- Track **cost, steps and tokens next to accuracy**. v2 passes one more task than v1 and spends 26% more tokens. That is a trade, and you should see it.
- Every FAIL above came from an agent that said "Done".
- The benchmark has one task per failure you care about. When production shows a new kind of failure, it becomes a new task (lesson 8).

## Run the tasks in real sandboxes

The local runner uses a fresh temporary directory per run and the tools' path jail. It doesn't use containers. To check the tasks inside real ones:

```bash
./scripts/docker_oracle.sh      # needs Docker
```

It builds each task's `Dockerfile`, runs the reference solution in the container, copies `tests/` to `/tests`, runs `test.sh` and reads `/logs/verifier/reward.txt`. That is the same contract Harbor uses. All eight tasks score 0 before the solution and 1 after it.

With Harbor installed, the equivalent should be:

```bash
harbor run -p tasks -a oracle                                   # validate the tasks
harbor run -p tasks -a claude-code -m anthropic/claude-haiku-4-5   # benchmark a real agent
```

> **Not verified with Harbor itself.** The layout and the reward contract follow Harbor's documentation and pass the Docker check above, but these tasks have not been run through the `harbor` CLI. Note also that an off-the-shelf agent will fail `changelog-entry` and `refund-policy` by design: the answers are in *your* context, which only your harness supplies.

## With a real model

```bash
uv run agentlab eval --model claude --trials 3 --yes --traces runs
```

One run is an anecdote. With `--trials 3` a cell shows `2/3`, and a task only counts as passed when every trial passes.

## What is simulated

The scores come from the stand-in model, so they show that the benchmark *can* tell harness versions apart. The task format, the verifiers, the oracle check, the runner and the comparison are real.

<details><summary><b>Check yourself</b></summary>

1. **Why run the reference solution through the verifier?** To prove the task is solvable and that the verifier accepts a correct result.
2. **Why score files and not the agent's final message?** The message says "Done" whether or not the work is right.
3. **A change fixes two tasks and breaks one. Ship it?** Not as it is. Find out why the one broke; a regression means something you relied on has changed.

</details>

**Next →** [Lesson 7 · Observability](../07-observability/)
