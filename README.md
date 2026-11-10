# cofa-kit

Codex 작업용 개인 지침·설정·스킬 모음. 과제 내용·답안·결과물 코드는 포함하지 않는다.

| 경로 | 내용 |
|---|---|
| `AGENTS.md` | 작업 규칙(원본 보존, 개인정보와 결정적 가명 ID, 지시성 문구, 코드 계산, 결정 카드, 15분 작업 단위와 PROGRESS.md) |
| `.codex/config.toml` | 서브에이전트 중첩 1단계 제한(동시 실행 수는 지정 안 함, 병렬 규칙과 동시 최대 3개는 AGENTS.md 8-7) |
| `.codex/agents/executor.toml` | 실행자 서브에이전트, 병렬 실행 전제(지정 파일만 수정, 커밋은 메인) (기본: 메인 모델 상속, Luna 6 지정은 주석 해제) |
| `.codex/agents/verifier.toml` | 독립 검증 서브에이전트 (기본: 상속, Sol 6.0 지정은 주석 해제, 최대 5항목·1회) |
| `.codex/agents/auditor.toml` | 읽기 전용(`sandbox_mode = "read-only"`) 적대적 감사 서브에이전트, MVP 동작 직후 1회(요구사항 대조, 남은 구현과 병렬) |
| `.agents/skills/elicit-requirements` | 담당자 질문 목록 → REQUIREMENTS.md, 계획을 막는 질문만 2라운드와 20분 상한, 나머지는 구현 중에도 계속. 개인정보와 보안 질문 목록 포함 |
| `.agents/skills/modeling-options` | 데이터 조합, 군집, 분류, 배정, 경로, 거리 계산, 예측과 이상 탐지, 일정 배정의 방법 후보표와 트레이드오프 최적화 공통 규칙, 효과 표 |
| `.agents/skills/independent-verify` | 원자료 기반 독립 재계산·대조 |
| `.agents/skills/pre-submit` | 제출 전 점검표 + 서술형 예상 질문 6개. `scripts/cofa_check.py`(표준 라이브러리만)가 필수 파일, 식별정보, 키 하드코딩, 의존성, 원본 변경, 미커밋을 기계 점검하고 실패마다 고치는 법을 출력 |
| `.agents/skills/cofa-rules` | AGENTS.md 지도의 세부 규칙(근거 파일, 개인정보, 작업 단위와 병렬). AGENTS.md는 40줄 지도로 유지 |
| `.agents/skills/plan-and-scope` | PLAN.md(수용 기준·MVP·시간 배분) + COLLAB_LOG.md |
| `.agents/skills/webapp-build` | 웹 서비스 세로 단위 구현, 0.0.0.0·Browser 미리보기 규칙, 보안과 배포 기본값, 데이터 갱신(버전, diff, 재업로드) |
| `.agents/skills/webapp-test` | 수용 기준 → 자동 테스트, Browser 수동 점검표 |
| `.agents/skills/cofa-semiconductor` | 반도체 수율·검사·결함·설비 시계열(SPC) 분석 규칙. 출처: [ripplelover/cofa-ready-kit](https://github.com/ripplelover/cofa-ready-kit) (MIT, 폴더 안 LICENSE), 원본에 없는 join-check 도구 언급만 수정 |
| `install.sh`, `install.ps1` | 작업 폴더에 복사(기존 파일은 덮어쓰지 않음). `.ps1`은 Windows용 |

메인 모델(Sol 6.1)은 세션에서 `/model`로 선택한다. 샌드박스·승인 설정은 지정하지 않는다(플랫폼 설정 상속).

## 설치 (Codex가 이 README를 읽고 실행)
1. 이 저장소를 작업 폴더 **밖**(`/tmp/cofa-kit`)에 clone한다. 작업 폴더 안에 clone하지 않는다.
2. 작업 폴더 루트에서 OS에 맞는 쪽 하나만 실행한다. 기존 파일은 덮어쓰지 않는다. 경로는 공백이 있어도 되게 따옴표로 묶는다.
   - Windows(PowerShell): `powershell -ExecutionPolicy Bypass -File "<키트 경로>\install.ps1"`
   - Linux, macOS, Git Bash: `bash "/tmp/cofa-kit/install.sh"`
3. 출력된 `[copy]`/`[append]`/`[skip]`/`[fail]`/`[warn]` 결과를 그대로 보고한다. `[fail]`이 있으면 설치가 끝났다고 말하지 않는다.
   - `python3`가 Microsoft Store 별칭이거나 없으면 `python`을 쓴다(예: `python .agents\skills\pre-submit\scripts\cofa_check.py`).
4. 커밋은 install.sh(또는 install.ps1)가 한다(저장소가 없으면 git init, 이름·이메일이 없으면 저장소 단위로 지정). 두 스크립트는 커밋 방식이 다르다.
   - install.ps1: 이번 실행에서 실제로 복사하거나 append한 키트 경로(있으면 `.cofa_baseline` 포함)만 add하고, 그 경로로 한정해 커밋한다. 이미 스테이징된 다른 파일은 커밋하지 않고 그대로 둔다. `.gitignore` 등으로 add하지 못한 경로는 이유와 함께 보고하고 나머지만 커밋한다. git이 없거나 저장소 소유자 문제로 git을 못 쓰면 파일 복사만 하고 git 단계는 건너뛴다. 실패가 있으면 종료 코드 1로 끝난다.
   - install.sh: 키트 경로 전체를 add하고 스테이징된 내용 전체를 커밋한다. add가 하나라도 실패하면 커밋하지 않고 사람이 직접 하도록 안내한다.
5. 사용자에게 "Codex를 종료 후 다시 실행해야 규칙·스킬이 적용된다"고 알린다.
