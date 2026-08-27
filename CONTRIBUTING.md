# Contributing to Santa Studio

If you have never contributed to an open project before, this page is written
for you. Nothing here assumes you already know how GitHub works. Read it in
order, or jump to [Your first contribution, step by step](#your-first-contribution-step-by-step)
if you want to start doing rather than reading.

---

## Why it is worth doing

Santa Studio is free to use for anything you are not making money from. Putting
its videos on a channel you earn from needs a **commercial grant** — and one
accepted contribution earns you a permanent one. See [LICENSE](LICENSE).

**Any accepted contribution counts.** Not just code:

- fixing a typo, or a sentence in the documentation that reads badly
- reporting a bug that turns out to be real
- correcting an explanation that is wrong or out of date
- adding a missing piece of documentation
- answering somebody's question in an issue
- a feature, a fix, a test

There is no minimum size, and the grant does not expire. A one-line
documentation fix earns the same grant as a new provider does.

---

## What makes a contribution easy to accept

The person reviewing your work is trying to answer one question: **can I merge
this without having to go and check things myself?** Everything below is about
making that answer obvious.

The three things that decide it:

1. **It does one thing.** A pull request that fixes a bug *and* renames some
   variables *and* adds a feature cannot be reviewed as a unit — the reviewer
   has to agree with all three or reject all three.
2. **It says what was wrong.** Not what you changed — the diff already says
   that. What was broken, and how you know it is not broken now.
3. **The tests pass.** Run them before you push. `python -m pytest`.

---

## Your first contribution, step by step

This walks through the whole thing with nothing skipped. It uses fixing a typo
in the documentation as the example, because that is a real contribution and
the smallest possible one.

### Step 0 — What you need

- A [GitHub account](https://github.com/signup) (free).
- Git installed. Check with `git --version`. If that fails:
  `sudo apt install git` on Ubuntu/Debian, `brew install git` on macOS,
  or [git-scm.com](https://git-scm.com/downloads) on Windows.
- For code changes, Python 3.11 or newer. Documentation changes need neither
  Python nor a working install.

Tell git who you are, once, if you never have:

```bash
git config --global user.name "Your Name"
git config --global user.email "you@example.com"
```

### Step 1 — Fork the repository

A **fork** is your own copy of the project on GitHub. You cannot write to
somebody else's repository, so you work in your copy and then offer the change
back.

Open [the repository](https://github.com/shivamm-shukla/santa-studio) and press
**Fork**, top right. Accept the defaults. You now have
`github.com/YOUR-USERNAME/santa-studio`.

### Step 2 — Clone it to your machine

**Cloning** downloads your fork so you can edit it.

```bash
git clone https://github.com/YOUR-USERNAME/santa-studio.git
cd santa-studio
```

Then tell git where the original lives, so you can pull in other people's
changes later. It is conventionally called `upstream`:

```bash
git remote add upstream https://github.com/shivamm-shukla/santa-studio.git
```

### Step 3 — Make a branch

A **branch** is a separate line of work. Never work directly on `main` — it
makes your fork hard to keep in sync, and it makes a second contribution
awkward.

```bash
git checkout -b fix-typo-in-readme
```

Name it after what it does. `fix-typo-in-readme`, `add-cerebras-provider`,
`caption-timing-off-by-one`. Not `patch-1`, not `my-changes`.

### Step 4 — Make the change

Edit the file. Change one thing. Save.

If you are changing code, read [the house style](#the-house-style) below first —
it is short, and matching it saves a round of review.

### Step 5 — Check it

For a documentation change, read it back once.

For a code change:

```bash
python -m pytest
```

Every test must pass. If a test fails and you think the test is wrong, say so
in your pull request rather than deleting it — sometimes it is wrong, and that
is a conversation worth having.

If you changed behaviour, add a test for it. See
[Writing a test](#writing-a-test).

### Step 6 — Commit

A **commit** is a saved change with a message explaining it.

```bash
git add README.md
git commit -m "Fix the misspelled provider name in the keys table"
```

`git add .` adds everything you changed. Prefer naming the files, so you do not
commit a stray scratch file by accident.

See [commit messages](#commit-messages) for what to write.

### Step 7 — Push

**Pushing** uploads your branch to your fork on GitHub.

```bash
git push origin fix-typo-in-readme
```

### Step 8 — Open the pull request

A **pull request** (PR) asks the maintainer to take your change.

Go to your fork on GitHub. There will be a banner offering to open a pull
request from the branch you just pushed — press it. If there is no banner,
press **Contribute → Open pull request**.

A template will fill the description box. Fill it in. It is short, and it is
the whole difference between a PR that gets merged today and one that sits
waiting for questions.

Press **Create pull request**. You are done.

### Step 9 — Review

The maintainer will read it and either merge it or ask something. A question is
not a rejection — it usually means the change is fine and one thing about it is
unclear.

To make a further change, commit and push to the same branch. The pull request
updates itself; you do not open a new one.

### Step 10 — Claim your grant

Once your contribution is merged, comment on it asking for your commercial
grant, or open an issue using the **Commercial grant** template. You will get a
signed `grant.json` file. Install it:

```bash
python studio.py licence grant.json
```

Check it took:

```bash
python studio.py licence
```

Videos you make from then on carry no mark.

---

## Setting up to work on the code

Documentation changes need none of this. Code changes need a working install.

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Then check the machine is ready:

```bash
python studio.py doctor
```

It prints every dependency, key and quota with the fix beside anything missing.

You do **not** need API keys to work on most of this project. Tests never call
a live provider. You need keys only to run the pipeline end to end, and the
free tiers listed in the [README](README.md#keys) are enough — none of them
asks for a card.

Run the tests:

```bash
python -m pytest              # all of them, about six minutes
python -m pytest tests/test_sources.py -q      # one file
python -m pytest -k caption   # everything matching "caption"
```

---

## The house style

This codebase has a consistent voice. Matching it is not a formality — it is
most of what makes it possible to come back to a file after two months and
still understand it.

### Comments say why, not what

The code already says what it does. A comment earns its place by explaining
something the code cannot: why it is written this odd way, what broke when it
was written the obvious way, what will happen if someone "simplifies" it.

```python
# Bad - says what the line already says
# Loop over the sources and filter them
kept = [s for s in sources if relevant(s)]

# Good - says what the reader could not have known
# OpenAlex answered "how a metal box rewired world trade" with four papers on
# photosynthesis, because they carry the word "rewiring". Every index here
# answers a keyword search and none of them fails one, so a bad query comes
# back looking exactly like a good one.
kept = [s for s in sources if relevant(s)]
```

If you fixed a bug, the comment that stops it coming back is usually worth more
than the fix.

### Commit messages

The title is a sentence saying what the change does, in the imperative, with no
prefix and no ticket number:

```
Ask a provider when it will be back instead of waiting for midnight
Make the booth show what it is doing, and record something worth cloning
Fix the misspelled provider name in the keys table
```

Not `fix: bug`, not `Updated files`, not `WIP`.

For anything bigger than a typo, add a body explaining the failure it fixes.
Write it for somebody reading `git log` in a year with no memory of this.

### Writing a test

Tests are named as full sentences describing the behaviour they protect, and
their docstring says what went wrong to make them necessary:

```python
def test_a_provider_that_says_when_it_will_be_back_is_believed():
    """Groq's daily token budget is a rolling window and it says so. Taking
    midnight UTC for an answer parked a run for ten hours to wait out fifteen
    minutes."""
```

Not `test_quota_1`. Somebody reading a failure should learn what broke from the
name alone.

Tests must not call a live API, download anything, or write outside their
temporary directory. `tests/conftest.py` points every test at a throwaway
storage directory automatically.

---

## Reporting a bug

Open an issue using the **Bug report** template. The thing that decides whether
a bug can be fixed is whether it can be reproduced, so the most valuable part
is the exact steps, the exact error, and what you expected instead.

If you are not sure it is a bug, report it anyway. A report that turns out to
be a misunderstanding still usually means the documentation was unclear, which
is itself worth fixing — and it still counts as a contribution.

---

## Suggesting a feature

Open an issue using the **Feature request** template before writing code, if
the change is more than small. It is a short conversation that saves you the
possibility of building something that does not fit, and the maintainer will
tell you either way quickly.

Two things this project is deliberate about, worth knowing before you propose
something:

- **It runs on free tiers.** A feature that needs a paid API is a hard sell
  unless it degrades cleanly without one.
- **Sources have to be real.** Anything that puts an unverified claim or an
  invented citation into a video will be rejected, however good it looks.

---

## What gets rejected

Rarely, and for reasons worth knowing in advance:

- **Reformatting somebody else's code.** A diff that is 90% whitespace hides
  the 10% that matters.
- **Large changes with no prior discussion.** Not because they are unwelcome,
  but because it is painful to turn one down after somebody spent a weekend.
- **Anything that weakens sourcing.** See above.
- **Adding a dependency for something small.** This project is deliberately
  light. If forty lines will do it, forty lines is better than a package.
- **AI-generated changes nobody read.** Use whatever tools you like, but you
  are the author, and you should be able to explain every line.

---

## A code of conduct

There is one, it is short, and it is in [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).
The summary is: be decent to people, assume they meant well, and remember that
somebody asking an obvious question is somebody who decided this project was
worth their time.

---

## Where things are

| | |
|---|---|
| [README.md](README.md) | What it does and how to run it |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | How it is put together and why — read this before a code change |
| [docs/SPEC.md](docs/SPEC.md) | What it is meant to do, and an honest status for every claim |
| [docs/ROADMAP.md](docs/ROADMAP.md) | The engineering plan and what each phase delivered |
| [room/README.md](room/README.md) | The 3D studio front end |
| [reel/README.md](reel/README.md) | How the demo film is built |
| [LICENSE](LICENSE) | What you may do with this, and how to earn commercial rights |

---

## Still stuck?

Open an issue and say so. "I tried to follow CONTRIBUTING and got lost at step
4" is a useful bug report about this page, and fixing this page is a
contribution like any other.
