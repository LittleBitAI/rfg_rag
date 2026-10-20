# prompts

골든 질문 생성·검증 프롬프트 파일을 둡니다. `write_run` 은 이 폴더의 파일마다 SHA-256 을
run 매니페스트의 `prompt_snapshot` 에 기록합니다.

- `A/{topic}.txt`: A 의 주제 전용 생성 프롬프트
- `B.txt`: B 의 고정 생성 프롬프트. 모든 주제가 이 파일 하나를 씁니다
- `C.txt`: 비교 실험에서 사람이 Pro 채팅에 붙여 넣을 C 프롬프트. B 처럼 고정 글에 주제 명세와 train 묶음들을 넣습니다 (`experiment.pro_packets`)
- `validator.txt`: 독립 검증기의 프롬프트. 주제 · 생성 프롬프트와 무관하게 질문과 근거 단위만 받습니다. 검증 기록(`validation.json`)에 SHA-256 이 남습니다

`$topic` · `$requires` · `$structure` 자리에 주제 명세 값이 들어가 system 메시지가 되고,
근거 묶음 컨텍스트는 user 메시지로 그대로 보냅니다.
