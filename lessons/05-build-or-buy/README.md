# Lesson 5 · Build or buy, and keeping the in-distribution pieces close

> **Models are best at what they saw in training. Use an off-the-shelf harness when your task looks like that; build your own where your domain doesn't. Even then, keep ordinary operations, like editing a file, in the shape the model already knows.**

*In the talk: 7:03 (build or buy) and 8:24 (keep in-distribution pieces close).*

## The decision

| Your task | Then |
|---|---|
| Looks like what models are trained on (coding, research, writing, file work) | **Buy.** An off-the-shelf harness is already tuned for it. Start there. |
| Unusual domain, unusual tools, strict rules about what may happen | **Build**, or customize: add gates, checks and domain tools through middleware (lesson 4). |
| In between | Start with a general harness for speed. Tighten it as your eval shows where it fails. |

And inside a custom harness:

| Piece | Keep it standard? |
|---|---|
| Reading, editing, searching files; running commands | **Yes.** Use the tool shapes the model was trained with. |
| Your domain's actions (book a shipment, approve a claim) | No. These are yours to design. |

## One job, two tool shapes

```python
edit_file(path, old_str, new_str)  # replace an exact string
patch_lines(path, start_line, end_line, text)  # replace a range of line numbers
```

Both can do the task. What changes is which one the model is used to.

## Run it

```bash
uv run agentlab lesson 5
```

The task: add one line to `server.js` and change another.

```
model             edit tool offered     model calls  tokens  result
----------------  --------------------  -----------  ------  ------
scripted-careful  edit_file (native)              3   2,171  pass
scripted-careful  patch_lines                     3   2,246  FAIL
scripted-liner    edit_file                       5   4,563  pass
scripted-liner    patch_lines (native)            3   2,246  pass
```

The failure raised no error:

```
server.js after `scripted-careful` used patch_lines (line numbers from one read, applied top-down):

  2  const express = require("express");
  3  const PORT = 8080;   <- the helmet line was here for a moment; the second patch overwrote it
  4  const PORT = 3000;   <- still 3000: the patch meant for this line landed one line up
```

The first patch inserted a line, so every line number after it was stale. A model that knows line patches applies them bottom-up. One that doesn't, doesn't.

The fix is in the harness:

```
  scripted-careful  -> harness offers edit_file    -> PASS in 3 model calls
  scripted-liner    -> harness offers patch_lines  -> PASS in 3 model calls
```

`build_agent(..., edit=None)` reads `model.native_edit_tool` and offers that shape ([`lab.py`](../../src/agentlab/lab.py)). A harness that supports several models keeps a small profile per model for exactly this.

## What to notice

- **Out of distribution rarely looks like an error.** Row 2 is a wrong file and a confident "Done". Row 3 is a right file at twice the cost.
- **The mechanism in row 2 is real**, whatever the model: line numbers go stale after an insert. Exact-string edits don't have that problem, which is one reason that shape is common.
- A "better" tool the model hasn't seen can do worse than a plain one it has. Measure before you replace a standard tool.

## What is simulated

Which shape each stand-in is "used to" is a setting (`native_edit_tool`), and the mistakes it makes with the other shape are scripted. So the table shows *that* tool shape can decide an outcome, not how any real model behaves. To measure a real one, run the eval once per shape:

```python
build_agent(get_model("claude"), workspace, edit="patch_lines")  # versus edit="edit_file"
```

<details><summary><b>Check yourself</b></summary>

1. **Why did `patch_lines` corrupt the file without an error?** Both patches were valid ranges. The second used a line number from before the first patch moved everything down.
2. **You are building a harness for insurance claims. Which tools do you design yourself?** The claim actions. Not file editing or search.
3. **How would you know your custom tool is worse than the standard one?** Run the same eval with each and compare pass rate, steps and tokens.

</details>

**Next →** [Lesson 6 · Evals](../06-evals/)
