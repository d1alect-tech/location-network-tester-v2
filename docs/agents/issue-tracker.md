# Issue tracker: GitHub

Tickets for this repo live as GitHub issues on `d1alect-tech/location-network-tester-v2`.
Use the `gh` CLI for all operations.

Scope note: issues track **waves of work**. The delivery queue itself lives in
`docs/roadmap.md`, not in issue bodies (see `AGENTS.md`, "Queue"). Issue #1 states the
same split: "Трекинг — этот issue-ряд, очередь — `docs/roadmap.md`".

## Conventions

- **Create an issue**: `gh issue create --title "..." --body "..."`. Use a heredoc for multi-line bodies.
- **Read an issue**: `gh issue view <number> --comments`.
- **List issues**: `gh issue list --state open --json number,title,body,labels`.
  On PowerShell 5.1 pipe through `ConvertFrom-Json` instead of `--jq`; the shell
  eats the backslashes in a jq string-interpolation expression.
- **Comment on an issue**: `gh issue comment <number> --body "..."`
- **Apply / remove labels**: `gh issue edit <number> --add-label "..."` / `--remove-label "..."`
- **Close**: `gh issue close <number> --comment "..."`

`gh` infers the repo from `git remote -v` when run inside the clone; `origin` here is
`https://github.com/d1alect-tech/location-network-tester-v2.git`. In a detached worktree or
when the remote is missing, pass `-R d1alect-tech/location-network-tester-v2` explicitly.

Issue titles and bodies are written in Russian. Match that language when you write to the tracker.

## The wave trackers

Issues #1–#9 are all **open** and all follow one shape: one tracker per wave, titled
`[<wave>] Трекер волны <wave> (скоуп — за владельцем)`.

| Issue | Wave | Subject |
|---|---|---|
| #1 | W0 | Зелёный baseline f01c737 — закрыть красный хвост гейтов |
| #2 | C1 | Трекер волны C1 |
| #3 | C3 | Трекер волны C3 |
| #4 | U3 | Трекер волны U3 |
| #5 | U1 | Трекер волны U1 |
| #6 | C2 | Трекер волны C2 |
| #7 | U2 | Трекер волны U2 |
| #8 | C0 | Трекер волны C0 |
| #9 | U4 | Трекер волны U4 |

Scope for each wave is set by the repo owner, not inferred by an agent. Don't open a
new tracker for work that belongs inside an existing wave; comment on that wave instead.

A tracker body records measured gate state against a named baseline commit
(ruff / basedpyright / tsc / biome / playwright / pytest counts) plus the module-size
ledger. When you update one, re-measure in a clean worktree rather than copying numbers forward.

## Labels

The repo carries only GitHub's default label set:

`accessibility`, `bug`, `documentation`, `duplicate`, `enhancement`,
`good first issue`, `help wanted`, `invalid`, `question`, `wontfix`

There is no custom triage or workflow label vocabulary here, and none of the wave
trackers is currently labelled. Don't filter on labels that don't exist, and don't
invent a namespace without the owner's agreement.

## Pull requests as a triage surface

**No.** This is a private single-owner repo and it has never had a pull request.
Work lands through branches and merges on the main tree, not through PR review.
If that changes, `gh pr view` / `gh pr diff` / `gh pr list` are the equivalents,
and note that GitHub shares one number space across issues and PRs, so a bare
`#42` may be either.

## When a skill says "publish to the issue tracker"

Create a GitHub issue, or comment on the relevant wave tracker.

## When a skill says "fetch the relevant ticket"

Run `gh issue view <number> --comments`.
