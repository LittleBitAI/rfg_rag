# configs

골든 파이프라인 설정 파일을 둡니다. `write_run` 은 이 폴더의 파일마다 SHA-256 을
run 매니페스트의 `config_snapshot` 에 기록합니다.

- `topics/{topic}.json`: 주제 명세 (요구 구조, 출력 `structure` 필드, 근거 묶음 선택 규칙). 분포 계획이 파일별 SHA-256 을 고정합니다.

A · B 의 run 설정(모델, 최대 호출 수, 예산, 단가)은 여기에 두지 않습니다. 기본 유료 실행이 생기지 않도록
실행할 때마다 CLI 플래그로 받고(`golden_pipeline/README.md` 의 실행기와 CLI), 그 내용과 SHA-256 이 run 매니페스트에 남습니다.
