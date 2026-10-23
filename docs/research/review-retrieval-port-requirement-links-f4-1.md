# 리뷰 조사 · F4, 1회차

PR #70 리뷰 8회차의 수정 전에 2026-10-19에 쓴 조사 초안입니다. 검증된 사실이나 공용 규칙이 아니며, 리뷰는 이 문서를 수정과 함께 읽습니다.

## 문제

F4(P1): .wiki/graph.json 3행이 저장소 정체를 원래 이름 "rfg_rag"가 아니라, 연결된 worktree의 폴더 이름 "retrieval-port-requirement-links"로 적습니다. 불변 조건: 생성된 위키 메타데이터는 어느 worktree나 checkout에서 다시 만들든 원래 저장소 정체를 담아야 하고, 커밋된 생성 파일은 관리 작업이 다시 만들 때마다 바뀌면 안 됩니다.

발생: 최후 확인(backstop), 8회차.

- [P1] [P1] .wiki/graph.json:3 — 다시 만든 그래프가 worktree 이름을 저장소 정체로 씁니다

## 실패한 수정

- 커밋 023c41b('wiki: restore the rfg_rag graph keyed by the canonical repository')는 생성된 .wiki/graph.json을 손으로 고쳐 rfg_rag로 적고, 생성기는 그대로 두었습니다. 5~7회차는 통과했습니다. 925bdf0의 병합 관리 작업('Refresh wiki and architecture before merge')이 연결된 worktree 안에서 그래프를 다시 만들어 3행에 폴더 이름을 도로 적었고, 8회차가 다시 거부했습니다. 생성 결과를 손으로 고치면 다음에 다시 만들 때 버티지 못합니다.

## 출처

### S1 — Git: git-worktree 문서

- URL: https://git-scm.com/docs/git-worktree
- 확인일: 2026-10-19
- 위치: DESCRIPTION; DETAILS
- 인용: This new worktree is called a "linked worktree" as opposed to the "main worktree" prepared by git-init[1] or git-clone[1]. A repository has one main worktree (if it's not a bare repository) and zero or more linked worktrees. ... Within a linked worktree, $GIT_DIR is set to point to this private directory (e.g. /path/main/.git/worktrees/test-next in the example) and $GIT_COMMON_DIR is set to point back to the main worktree's $GIT_DIR (e.g. /path/main/.git). These settings are made in a .git file located at the top directory of the linked worktree. ... The rule of thumb is do not make any assumption about whether a path belongs to $GIT_DIR or $GIT_COMMON_DIR when you need to directly access something inside $GIT_DIR. Use git rev-parse --git-path to get the final path.
- 적용: 이 브랜치는 연결된 worktree입니다. 그 $GIT_COMMON_DIR은 주 rfg_rag/.git이며, worktree 폴더 이름이 무엇이든 공유 저장소를 가리킵니다.
- 반대 근거: bare 저장소 예외. 주 worktree가 없으면 common dir의 부모는 checkout 이름이 아닙니다.
- 검증: worktree에서 돌린 생성기와 주 checkout에서 돌린 생성기가 같은 정체를 냅니다.

### S2 — Git: git-rev-parse 문서

- URL: https://git-scm.com/docs/git-rev-parse
- 확인일: 2026-10-19
- 위치: --git-common-dir; --show-toplevel; --path-format
- 인용: --git-common-dir: Show $GIT_COMMON_DIR if defined, else $GIT_DIR. --show-toplevel: Show the (by default, absolute) path of the top-level directory of the working tree. If there is no working tree, report an error. --path-format=(absolute|relative): Controls the behavior of certain other options. If specified as absolute, the paths printed by those options will be absolute and canonical. If specified as relative, the paths will be relative to the current working directory if that is possible. The default is option specific. This option may be specified multiple times and affects only the arguments that follow it on the command line.
- 적용: 생성기가 써야 할 명령을 주고, 작업 트리 경로가 저장소가 아니라 worktree를 가리키는 이유를 설명합니다.
- 반대 근거: 기본 형식은 옵션마다 다릅니다. --path-format=absolute가 없으면 주 worktree에서는 상대 경로 '.git'이 나옵니다. 명령줄에서 --path-format은 --git-common-dir 앞에 와야 합니다.
- 검증: --path-format=absolute를 주면, worktree와 주 checkout 모두에서 부모 폴더 이름이 rfg_rag로 나옵니다.

### S3 — Git: gitignore 문서

- URL: https://git-scm.com/docs/gitignore
- 확인일: 2026-10-19
- 위치: DESCRIPTION; NOTES
- 인용: Files already tracked by Git are not affected; see the NOTES below for details. ... To stop tracking a file that is currently tracked, use git rm --cached to remove the file from the index. The filename can then be added to the .gitignore file to stop the file from being reintroduced in later commits.
- 적용: .wiki/.gitignore에 /graph.json이 있는데도 이 파일은 추적되고, 다시 만들 때마다 PR에 나타납니다. 추적을 멈추면 기존 ignore 규칙이 효과를 냅니다.
- 반대 근거: 추적을 멈추면 브랜치에서 이 파일을 읽는 리뷰어나 도구를 포함해 모두에게서 파일이 사라집니다.
- 검증: `git rm --cached .wiki/graph.json` 뒤 `git ls-files .wiki/graph.json`은 아무것도 출력하지 않고, 다시 만들어도 `git status`가 깨끗합니다.

### S4 — 커밋된 위키 구조 그래프

- URL: .wiki/graph.json
- 확인일: 2026-10-19
- 위치: 3행
- 인용: "ns": "repo", "repo": "retrieval-port-requirement-links", "nodes_from": ".wiki/corpus.json"
- 적용: 023c41b에서 손으로 rfg_rag로 고친 뒤, head 925bdf0에서 다시 만든 출력이 worktree 폴더 이름을 담고 있음을 보여 줍니다.
- 반대 근거: 찾지 못했습니다.
- 검증: 생성기를 고치고 이 worktree에서 다시 만든 뒤 3행이 "repo": "rfg_rag"이거나, 파일이 더는 추적되지 않습니다.

### S5 — 위키 폴더 ignore 규칙

- URL: .wiki/.gitignore
- 확인일: 2026-10-19
- 위치: 3-4행
- 인용: /corpus.json
/graph.json
- 적용: 저장소는 이미 생성된 corpus와 graph를 커밋하지 않는 로컬 상태로 선언합니다.
- 반대 근거: 확인하지 않음: 이 규칙이 언제 더해졌는지, main에서도 규칙과 달리 graph.json을 추적하는지.
- 검증: 수정 뒤 `git ls-files .wiki`에 graph.json이 더는 나오지 않습니다.

## 주장

- C1 (출처; S1): 연결된 worktree의 $GIT_COMMON_DIR은 주 worktree의 $GIT_DIR을 가리키며, 저장소의 모든 worktree가 이를 공유합니다. bare 저장소에는 주 worktree가 없습니다.
- C2 (출처; S1, S2): `git rev-parse --path-format=absolute --git-common-dir`는 저장소의 어느 worktree에서든 같은 절대 경로를 돌려주고, --show-toplevel은 지금 worktree 자기 폴더를 돌려줍니다.
- C3 (해석; S2, S4): graph.json 3행의 값은 worktree 폴더 이름과 정확히 같으므로, 생성기의 정체는 어디서 다시 만드느냐에 달려 있습니다. common dir의 부모에서 이름을 얻으면 이 의존이 없어집니다.
- C4 (해석; S4): 023c41b의 손 수정이 버티지 못한 것은, 병합 관리 작업이 925bdf0에서 .wiki/graph.json을 다시 만들어 3행에 worktree 이름을 도로 적었기 때문입니다.
- C5 (해석; S3, S5): 저장소 자체의 .wiki/.gitignore는 graph.json을 무시 대상으로 적지만, Git ignore 규칙은 추적되는 파일에 영향을 주지 않습니다. git rm --cached로 추적을 멈추면 다시 만든 결과가 PR diff에 들어오지 않습니다.

## 핵심 원리

Git은 저장소 하나와 그 작업 트리들을 구별합니다. 저장소에는 주 worktree 하나와 연결된 worktree가 0개 이상 있습니다. 연결된 worktree에서 $GIT_DIR은 주 .git/worktrees/ 아래의 전용 폴더를 가리키고, $GIT_COMMON_DIR은 주 worktree의 $GIT_DIR을 가리킵니다. `rev-parse --git-common-dir`는 $GIT_COMMON_DIR(없으면 $GIT_DIR)을 출력하고, `--path-format=absolute`는 이를 정규화된 절대 경로로 만듭니다. `--show-toplevel`은 지금 작업 트리의 최상위, 곧 worktree 폴더를 출력합니다. common dir은 위치와 상관없는 기준점이지만, 작업 트리 경로는 그렇지 않습니다. 이와 별개로, gitignore 규칙은 이미 추적되는 파일에 영향을 주지 않으며, `git rm --cached`로 index에서 빼야 ignore 규칙이 효과를 냅니다.

## 적용

이 브랜치는 C:/Users/dasdk/PycharmProjects/rfg_rag-worktrees/retrieval-port-requirement-links에 있는 연결된 worktree입니다. graph.json 3행의 값은 그 폴더 이름과 정확히 같으며, 작업 트리 폴더 이름에서 정체를 얻으면 바로 이렇게 나옵니다. 이 worktree의 common dir은 C:/Users/dasdk/PycharmProjects/rfg_rag 아래 주 checkout의 .git이고, 그 부모 폴더 이름은 rfg_rag입니다. 생성기는 이 저장소 밖의 wiki-agent 허브에 있으므로 수정 (1)은 그쪽에 들어갑니다. 이 저장소에서 바뀌는 것은 다시 만들거나 추적을 멈춘 .wiki/graph.json입니다. .wiki/.gitignore 4행(/graph.json)은 저장소가 이미 그래프를 로컬 생성 상태로 다룬다는 것을 보여 주므로, 수정 (2)는 기존 의도를 지키게 할 뿐 규칙을 더하지 않습니다.

## 가설

그래프 생성기는 받은 작업 트리 폴더 이름에서 저장소 정체를 얻습니다. 병합 관리 작업이 연결된 worktree 경로를 주므로, 그 이름은 worktree 폴더가 됩니다. 문제가 계속 보이게 하는 두 번째 요인도 있습니다. .wiki/.gitignore는 이미 /graph.json을 무시되는 로컬 산출물로 적지만 이 파일은 추적되고, Git ignore 규칙은 추적되는 파일에 적용되지 않습니다. 그래서 다시 만들 때마다 PR diff에 들어옵니다. 두 수정이 버틸 것입니다. (1) 생성기가 주 worktree에서 정체를 얻습니다. 곧 `git rev-parse --path-format=absolute --git-common-dir`의 부모 폴더 이름입니다. (2) 이 저장소의 .gitignore가 이미 뜻하는 대로, `git rm --cached`로 .wiki/graph.json 추적을 멈춥니다.

## 반대 근거

- bare 저장소에는 주 worktree가 없으므로, common dir의 부모는 checkout 이름이 아닙니다. 팀원의 clone(예: VM codeit)이 rfg_rag가 아닌 이름의 폴더에 있으면 정체도 달라집니다. common dir 부모 폴더 이름은 clone 하나의 배치 안에서만 안정적입니다.
- --path-format=absolute를 주지 않으면 --git-common-dir은 주 worktree에서 상대 경로 '.git'을 출력하며, 이 옵션은 Git 2.31 이상이 필요합니다. 더 오래된 Git에서는 경로를 현재 폴더 기준으로 풀어야 합니다.
- 리뷰어나 다른 도구가 PR에 .wiki/graph.json이 있기를 기대한다면, 추적을 멈추면 그들이 기대는 것이 사라집니다. main에서도 추적하는지, 이 브랜치에서만 추적하는지는 확인하지 않았습니다(shell을 쓸 수 없었음).

## 다른 방법

- .wiki/graph.json을 다시 손으로 고치기. 이미 한 번 실패했고, 다음에 다시 만들면 덮어씁니다.
- 생성기는 고치지 않고 그래프 추적만 멈추기. PR에서 F4가 사라지고 .wiki/.gitignore와도 맞지만, 로컬 그래프는 그것을 읽는 쪽에 여전히 틀린 정체를 줍니다. 생성기 수정과 함께 하면 좋지만, 대신하지는 못합니다.
- 생성기가 읽도록 .wiki/adapter.toml에 "rfg_rag" 같은 고정 이름 넣기. clone 사이에서 결정적이지만, 늘 같은 값만 담는 설정 키를 더하고(CLAUDE.md 1.1) 생성기에 새 코드 경로가 필요합니다. common dir 방식이 clone 사이에서 불안정하다고 드러날 때만 씁니다.
- `git remote get-url origin`에서 이름 얻기. clone 사이에서 안정적이지만, 원격이 있어야 하고 URL 파싱이 더해집니다.

## 실험

그래프 생성기를 worktree 경로로 한 번, 주 checkout C:/Users/dasdk/PycharmProjects/rfg_rag로 한 번 돌립니다. 수정 전에는 worktree 실행이 "retrieval-port-requirement-links"를 적어 F4를 재현합니다. 수정 뒤에는 두 실행 모두 "repo": "rfg_rag"를 적어야 합니다. 그다음 이 worktree에서 병합 관리 새로 고침을 다시 돌리고, `git diff`로 3행이 여전히 rfg_rag인지 확인합니다. 그래프 추적도 멈췄다면, `git ls-files .wiki/graph.json`이 아무것도 출력하지 않고 다시 만든 뒤에도 `git status`가 깨끗한지 확인합니다.

## 결과

관측했지만 검증하지 않았으며, 여전히 초안입니다. 수정 전에는 허브(wiki-agent `e821745`)의 `repo_graph.build`가 이 worktree에서 `"repo": "retrieval-port-requirement-links"`를, 주 checkout에서 `"repo": "rfg_rag"`를 냈습니다. `git rev-parse --path-format=absolute --git-common-dir`는 두 곳 모두에서 부모 이름이 `rfg_rag`로 나왔습니다. 이로써 F4를 재현했습니다. 수정 (1)은 이 저장소가 아니라 허브에 들어갔습니다. wiki-agent `a011636`(#177, 그쪽 main에 병합)이 common dir에서 이름을 얻는 `name_of()`를 더하고, `decisions_of()`가 공개된 기록만 세게 했습니다. 그 뒤 `build()`는 두 경로 모두에서 `"repo": "rfg_rag"`와 결정 0개를 냈습니다. 0개인 것은 여기서 `.wiki/decisions/`가 무시되어 공개된 기록이 없기 때문이며, 주 checkout도 0개를 냅니다. 이어서 이 worktree에서 `repo_graph.write`를 돌리자, `925bdf0`의 예전 새로 고침과 3행(worktree 이름 → `rfg_rag`)만 다른 `.wiki/graph.json`이 나왔습니다. 그 파일을 이 문서와 함께 커밋하므로, 다음 병합 새로 고침은 이를 바꾸지 않아야 합니다. 수정 (2), 그래프 추적 멈추기는 하지 않았습니다. 허브 `maintenance.py`가 생성 파일을 `git add -f`로 스테이징하므로, 기존 ignore 규칙으로는 다시 들어오는 것을 막지 못합니다. 병합 관리 새로 고침 전체는 서버 몫이며 여기서 다시 돌리지 않았습니다. 저장소 테스트는 바뀌지 않았고, 확인은 위의 메모리 안 build였습니다.

## 남은 한계

생성기와 병합 관리 작업은 이 저장소 밖의 허브에 있습니다. 이 작업이 허브를 바꿔도 되는지, 그 주인이 바꿔야 하는지는 확인하지 않았습니다. 확인하지 않은 것: .wiki/graph.json(그리고 .wiki/.gitignore에 함께 적힌 corpus.json)을 이 브랜치뿐 아니라 main에서도 추적하는지, 'repo' 키를 누가 더 읽으며 어떤 이름을 기대하는지, 팀원들의 clone 폴더 이름.
