# cofa-kit

Codex 작업용 개인 지침·설정·스킬 모음. 과제 내용·답안·결과물 코드는 포함하지 않는다.

| 경로 | 내용 |
|---|---|
| `AGENTS.md` | 작업 규칙(원본 보존, 개인정보, 지시성 문구, 코드 계산, 기록) |
| `.codex/config.toml` | 서브에이전트 동시 1개·중첩 1단계 제한 |
| `.codex/agents/executor.toml` | 실행자 서브에이전트 (Luna 6) |
| `.codex/agents/verifier.toml` | 독립 검증 서브에이전트 (Sol 6.0) |
| `.agents/skills/elicit-requirements` | 담당자 질문 목록 → REQUIREMENTS.md, 모호성 0까지 반복 |
| `.agents/skills/independent-verify` | 원자료 기반 독립 재계산·대조 |
| `.agents/skills/pre-submit` | 제출 전 점검표 + 서술형 예상 질문 6개 |
| `install.sh` | 작업 폴더에 복사(기존 파일은 덮어쓰지 않음) |

메인 모델(Sol 6.1)은 세션에서 `/model`로 선택한다. 샌드박스·승인 설정은 지정하지 않는다(플랫폼 설정 상속).
