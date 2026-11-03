---
name: cofa-rules
description: AGENTS.md 지도의 세부 규칙 모음. 개인정보 원본을 처음 열거나 가명 처리할 때, evidence/ 근거 파일을 쓸 때, 작업 단위를 쪼개거나 executor를 병렬로 맡기거나 세션이 끊겨 재개할 때 해당 파일을 읽는다.
---

# 세부 규칙 (AGENTS.md 번호와 같다)

| 언제 | 읽을 파일 |
|---|---|
| 단계를 넘기기 전, evidence/ 파일을 쓸 때, 감사 시점 판단 | [references/flow-evidence.md](references/flow-evidence.md) (0번) |
| 데이터 파일을 처음 열 때, 가명 ID, 마스킹, 시각 데이터 | [references/data-privacy.md](references/data-privacy.md) (2번, 4-2) |
| 계획에서 단위 쪼개기, 병렬 executor, 커밋, 막힌 단위, 세션 재개 | [references/units-parallel.md](references/units-parallel.md) (8-4~8-7) |

AGENTS.md의 한 줄 규칙과 이 파일들이 다르게 읽히면 이 파일들의 문구가 우선한다.
