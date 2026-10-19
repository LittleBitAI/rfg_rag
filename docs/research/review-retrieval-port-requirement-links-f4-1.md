# Review research — F4, cycle 1

Draft research before the fix of review round 8 of PR #70, written 2026-10-19. It is not a verified fact or a shared rule: the review reads it with the fix.

## Problem

F4 (P1): .wiki/graph.json line 3 records the repository identity as "retrieval-port-requirement-links", the linked worktree's folder name, instead of the canonical "rfg_rag". Invariant: generated wiki metadata carries the canonical repository identity no matter which worktree or checkout regeneration runs in, and a committed generated file must not drift every time maintenance regenerates it.

Trigger: backstop, rounds 8.

- [P1] [P1] .wiki/graph.json:3 — regenerated graph uses the worktree name as repository identity

## Failed fixes

- Commit 023c41b ('wiki: restore the rfg_rag graph keyed by the canonical repository') edited the generated .wiki/graph.json by hand to say rfg_rag and left the generator alone. Rounds 5-7 passed. Merge maintenance at 925bdf0 ('Refresh wiki and architecture before merge') regenerated the graph from inside the linked worktree and wrote the folder name back into line 3, so round 8 refused again. A hand edit to generated output cannot hold against the next regeneration.

## Sources

### S1 — Git - git-worktree Documentation

- URL: https://git-scm.com/docs/git-worktree
- Retrieved: 2026-10-19
- Locator: DESCRIPTION; DETAILS
- Fragment: This new worktree is called a "linked worktree" as opposed to the "main worktree" prepared by git-init[1] or git-clone[1]. A repository has one main worktree (if it's not a bare repository) and zero or more linked worktrees. ... Within a linked worktree, $GIT_DIR is set to point to this private directory (e.g. /path/main/.git/worktrees/test-next in the example) and $GIT_COMMON_DIR is set to point back to the main worktree's $GIT_DIR (e.g. /path/main/.git). These settings are made in a .git file located at the top directory of the linked worktree. ... The rule of thumb is do not make any assumption about whether a path belongs to $GIT_DIR or $GIT_COMMON_DIR when you need to directly access something inside $GIT_DIR. Use git rev-parse --git-path to get the final path.
- Applicability: This branch is a linked worktree. Its $GIT_COMMON_DIR is the main rfg_rag/.git, which names the shared repository whatever the worktree folder is called.
- Counterevidence: Bare-repository exception: with no main worktree, the parent of the common dir is not a checkout name.
- Validation: A generator run from the worktree yields the same identity as a run from the main checkout.

### S2 — Git - git-rev-parse Documentation

- URL: https://git-scm.com/docs/git-rev-parse
- Retrieved: 2026-10-19
- Locator: --git-common-dir; --show-toplevel; --path-format
- Fragment: --git-common-dir: Show $GIT_COMMON_DIR if defined, else $GIT_DIR. --show-toplevel: Show the (by default, absolute) path of the top-level directory of the working tree. If there is no working tree, report an error. --path-format=(absolute|relative): Controls the behavior of certain other options. If specified as absolute, the paths printed by those options will be absolute and canonical. If specified as relative, the paths will be relative to the current working directory if that is possible. The default is option specific. This option may be specified multiple times and affects only the arguments that follow it on the command line.
- Applicability: Gives the command the generator should use, and explains why the working-tree path names the worktree rather than the repository.
- Counterevidence: The default format is option-specific: without --path-format=absolute the main worktree prints a relative '.git'. --path-format must come before --git-common-dir on the command line.
- Validation: With --path-format=absolute, the parent folder's basename resolves to rfg_rag from both the worktree and the main checkout.

### S3 — Git - gitignore Documentation

- URL: https://git-scm.com/docs/gitignore
- Retrieved: 2026-10-19
- Locator: DESCRIPTION; NOTES
- Fragment: Files already tracked by Git are not affected; see the NOTES below for details. ... To stop tracking a file that is currently tracked, use git rm --cached to remove the file from the index. The filename can then be added to the .gitignore file to stop the file from being reintroduced in later commits.
- Applicability: .wiki/.gitignore lists /graph.json, yet the file is tracked and regenerations show up in the PR. Untracking it lets the existing ignore rule take effect.
- Counterevidence: Untracking removes the file for everyone, including any reviewer or tool that reads it from the branch.
- Validation: After `git rm --cached .wiki/graph.json`, `git ls-files .wiki/graph.json` prints nothing and a regeneration leaves `git status` clean.

### S4 — Committed wiki architecture graph

- URL: .wiki/graph.json
- Retrieved: 2026-10-19
- Locator: line 3
- Fragment: "ns": "repo", "repo": "retrieval-port-requirement-links", "nodes_from": ".wiki/corpus.json"
- Applicability: Shows the output regenerated at head 925bdf0 carrying the worktree folder name, after the hand edit in 023c41b had set it to rfg_rag.
- Counterevidence: none found
- Validation: After the generator fix and a regeneration from this worktree, line 3 reads "repo": "rfg_rag" (or the file is no longer tracked).

### S5 — Wiki directory ignore rules

- URL: .wiki/.gitignore
- Retrieved: 2026-10-19
- Locator: lines 3-4
- Fragment: /corpus.json
/graph.json
- Applicability: The repository already declares the generated corpus and graph as local, uncommitted state.
- Counterevidence: Not checked: when this rule was added, and whether main also tracks graph.json despite it.
- Validation: `git ls-files .wiki` no longer lists graph.json after the fix.

## Claims

- C1 (source; S1): A linked worktree's $GIT_COMMON_DIR points to the main worktree's $GIT_DIR, which all worktrees of the repository share. A bare repository has no main worktree.
- C2 (source; S1, S2): `git rev-parse --path-format=absolute --git-common-dir` returns the same absolute path from any worktree of a repository, while --show-toplevel returns the current worktree's own folder.
- C3 (interpretation; S2, S4): The value in graph.json line 3 is exactly the worktree folder's basename, so the generator's identity depends on where regeneration runs. Deriving it from the parent of the common dir removes that dependence.
- C4 (interpretation; S4): The hand edit in 023c41b did not hold because merge maintenance regenerated .wiki/graph.json at 925bdf0 and wrote the worktree name back into line 3.
- C5 (interpretation; S3, S5): The repository's own .wiki/.gitignore marks graph.json as ignored, but Git ignore rules do not affect tracked files. Untracking it with git rm --cached would stop regenerations from entering the PR diff.

## Core theory

Git separates one repository from its working trees. A repository has one main worktree and zero or more linked worktrees. In a linked worktree $GIT_DIR points to a private directory under the main .git/worktrees/, and $GIT_COMMON_DIR points back to the main worktree's $GIT_DIR. `rev-parse --git-common-dir` prints $GIT_COMMON_DIR (else $GIT_DIR), and `--path-format=absolute` makes it absolute and canonical. `--show-toplevel` prints the current working tree's top level, which is the worktree folder. The common dir is a location-independent anchor; the working-tree path is not. Separately, gitignore rules do not affect files already tracked; `git rm --cached` removes them from the index so the ignore rule takes effect.

## Applicability

This branch is a linked worktree at C:/Users/dasdk/PycharmProjects/rfg_rag-worktrees/retrieval-port-requirement-links. The value in graph.json line 3 equals that folder's basename exactly, which is what a working-tree-basename derivation produces. The common dir for this worktree is the main checkout's .git under C:/Users/dasdk/PycharmProjects/rfg_rag, whose parent basename is rfg_rag. The generator lives in the wiki-agent hub, outside this repository, so change (1) lands there; in this repository the change is the regenerated or untracked .wiki/graph.json. .wiki/.gitignore line 4 (/graph.json) shows the repository already treats the graph as local generated state, so change (2) only enforces existing intent and does not add a rule.

## Hypothesis

The graph generator takes the repository identity from the basename of the working-tree directory it is given. Merge maintenance gives it the linked worktree path, so the basename is the worktree folder. A second factor keeps the problem visible: .wiki/.gitignore already lists /graph.json as a local, ignored artifact, but the file is tracked, and Git ignore rules do not apply to tracked files. Every regeneration therefore lands in the PR diff. Two changes would hold. (1) The generator derives the identity from the main worktree: the basename of the parent of `git rev-parse --path-format=absolute --git-common-dir`. (2) This repository stops tracking .wiki/graph.json with `git rm --cached`, as its own .gitignore already intends.

## Counterevidence

- For a bare repository there is no main worktree, so the parent of the common dir is not a checkout name. A teammate's clone (for example on the VM codeit) in a folder not named rfg_rag would also get a different identity. The parent-of-common-dir basename is stable only within one clone layout.
- --git-common-dir prints a relative '.git' in the main worktree unless --path-format=absolute is given, and that option needs Git 2.31 or later. An older Git would need the path resolved against the cwd.
- If reviewers or other tools expect .wiki/graph.json in the PR, untracking it removes something they rely on. Whether it is tracked on main as well, or only on this branch, was not checked (no shell was available).

## Alternatives

- Edit .wiki/graph.json by hand again: already failed once, and the next regeneration overwrites it.
- Untrack the graph only, without the generator fix: makes F4 disappear from the PR and matches .wiki/.gitignore, but the local graph still carries the wrong identity for whatever reads it. A good companion to the generator fix, not a replacement for it.
- Put a fixed name such as "rfg_rag" in .wiki/adapter.toml for the generator to read: deterministic across clones, but it adds a config key that only ever holds one value (CLAUDE.md 1.1) and needs a new generator code path. Use it only if the common-dir derivation proves unstable across clones.
- Derive the name from `git remote get-url origin`: stable across clones, but it depends on a remote existing and adds URL parsing.

## Experiment

Run the graph generator once with the worktree path and once with the main checkout C:/Users/dasdk/PycharmProjects/rfg_rag. Before the fix the worktree run writes "retrieval-port-requirement-links", which reproduces F4. After the fix both runs must write "repo": "rfg_rag". Then rerun the merge-maintenance refresh in this worktree and confirm with `git diff` that line 3 still reads rfg_rag. If the graph is also untracked, check that `git ls-files .wiki/graph.json` prints nothing and that `git status` stays clean after a regeneration.

## Result

pending — the fix records what it observed here, with the tests and the commit.

## Unresolved limits

The generator and merge maintenance are in the hub, outside this repository. It is unconfirmed whether this task may change the hub or whether its owner must. Unchecked: whether .wiki/graph.json (and corpus.json, also listed in .wiki/.gitignore) is tracked on main as well as on this branch; who else reads the 'repo' key and which name they expect; and teammates' clone folder names.
