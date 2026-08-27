# Security

## Reporting a vulnerability

Do not open a public issue for a security problem.

Report it privately through
[GitHub's private vulnerability reporting](https://github.com/shivamm-shukla/santa-studio/security/advisories/new),
or by direct message to the maintainer. You will get an acknowledgement within a
few days, and told what is being done about it.

If you would like credit in the fix, say so — you will get it.

## What is in scope

- Anything that lets a crafted input — a topic, a reference URL, a research
  result, a source page — run code, read files it should not, or write outside
  the project's own storage directory.
- Anything that leaks credentials from `.env`, the config directory, or a
  project export.
- Anything in the web app or its API that lets a page on another origin drive a
  run or read its output.

## What is not

- **The commercial grant can be bypassed by editing the source.** This is known,
  documented in `licence.py`, and stated in [LICENSE](LICENSE) section 4. The
  code runs on the user's own machine from source they can read; no check
  written here could prevent it. What makes it a breach is the licence, not the
  code. Reports of "I removed the watermark" are not vulnerabilities.

  A way to make a *forged* grant validate — one not signed with the project's
  private key — **is** a vulnerability, and an important one. Report that.

- **Free-tier API keys in your own `.env`.** They are yours; keep them out of
  screenshots and out of pull requests.

## For contributors

Two things this project is careful about, worth knowing before you touch them:

- **The signing key is not in this repository and must never be.** `licence.py`
  holds the public half only. If you find a private key committed anywhere,
  report it privately — it means every grant ever issued needs replacing.
- **Sources are fetched from the open internet and read by a model.** Treat
  anything that comes back as untrusted text. It must never be executed,
  evaluated, or written to a path derived from its own content.

## Credentials in a checkout

`.env` and the config directory are git-ignored. Before pushing:

```bash
git diff --cached          # read what you are about to commit
python studio.py export    # zips a project with credentials excluded by construction
```
