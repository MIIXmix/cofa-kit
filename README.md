# cofa-kit

Codex 작업용 개인 지침·설정·스킬 모음. 과제 내용·답안·결과물 코드는 포함하지 않는다.

| 경로 | 내용 |
|---|---|
| `AGENTS.md` | 작업 규칙(원본 보존, 개인정보, 지시성 문구, 코드 계산, 기록) |
| `.codex/config.toml` | 서브에이전트 동시 1개·중첩 1단계 제한 |
| `.codex/agents/executor.toml` | 실행자 서브에이전트 (기본: 메인 모델 상속, Luna 6 지정은 주석 해제) |
| `.codex/agents/verifier.toml` | 독립 검증 서브에이전트 (기본: 상속, Sol 6.0 지정은 주석 해제, 최대 5항목·1회) |
| `.codex/agents/auditor.toml` | 읽기 전용(`sandbox_mode = "read-only"`) 적대적 감사 서브에이전트, 5단계 중 감사 단계 담당 |
| `.agents/skills/elicit-requirements` | 담당자 질문 목록 → REQUIREMENTS.md, 최대 2라운드·20분, 남은 항목은 판단 위임 |
| `.agents/skills/independent-verify` | 원자료 기반 독립 재계산·대조 |
| `.agents/skills/pre-submit` | 제출 전 점검표 + 서술형 예상 질문 6개 |
| `.agents/skills/plan-and-scope` | PLAN.md(수용 기준·MVP·시간 배분) + COLLAB_LOG.md |
| `.agents/skills/webapp-build` | 웹 서비스 세로 단위 구현, 0.0.0.0·Browser 미리보기 규칙 |
| `.agents/skills/webapp-test` | 수용 기준 → 자동 테스트, Browser 수동 점검표 |
| `.agents/skills/cofa-semiconductor` | 반도체 수율·검사·결함·설비 시계열(SPC) 분석 규칙. 출처: [ripplelover/cofa-ready-kit](https://github.com/ripplelover/cofa-ready-kit) (MIT, 폴더 안 LICENSE), 원본에 없는 join-check 도구 언급만 수정 |
| `install.sh` | 작업 폴더에 복사(기존 파일은 덮어쓰지 않음) |

메인 모델(Sol 6.1)은 세션에서 `/model`로 선택한다. 샌드박스·승인 설정은 지정하지 않는다(플랫폼 설정 상속).

## 설치 (Codex가 이 README를 읽고 실행)
1. 이 저장소를 작업 폴더 **밖**(`/tmp/cofa-kit`)에 clone한다. 작업 폴더 안에 clone하지 않는다.
2. 작업 폴더 루트에서 `bash /tmp/cofa-kit/install.sh` 를 실행한다. 기존 파일은 덮어쓰지 않는다.
3. 출력된 `[copy]`/`[append]`/`[skip]` 결과를 그대로 보고한다.
4. 커밋은 install.sh가 한다(저장소가 없으면 git init, 이름·이메일이 없으면 저장소 단위로 지정).
5. 사용자에게 "Codex를 종료 후 다시 실행해야 규칙·스킬이 적용된다"고 알린다.
