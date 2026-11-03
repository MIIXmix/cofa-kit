#!/usr/bin/env bash
# 사용법: 과제 작업 폴더(루트)에서
#   git clone https://github.com/<계정>/cofa-kit /tmp/cofa-kit && bash /tmp/cofa-kit/install.sh
# 원칙: 플랫폼이 이미 둔 파일은 절대 덮어쓰지 않는다.
set -euo pipefail
OURS_CFG=0
KIT="$(cd "$(dirname "$0")" && pwd)"
DEST="$(pwd)"

# 0) 설치 전부터 있던 미추적 경로(홈 폴더 환경 파일 등)를 기록: cofa_check 미커밋 검사에서 뺀다
git rev-parse --git-dir >/dev/null 2>&1 || { git init -q && echo "[git] 저장소가 없어 git init" || echo "[git] git init 실패. 사람에게 보고"; }
# 최상위 숨김 경로만 기록한다(과제 파일은 처음에 커밋해야 하므로 기준선에 넣지 않는다)
if [ "$(cd "$(git rev-parse --show-toplevel)" && pwd -P)" != "$(pwd -P)" ]; then
  echo "[baseline] 작업 폴더가 저장소 루트가 아님, 기록 안 함"
elif [ ! -e "$DEST/.cofa_baseline" ]; then
  git -c core.quotepath=off status --porcelain -unormal | sed -n 's/^?? //p' | sed 's/^"//; s/"$//' | grep '^\.' > "$DEST/.cofa_baseline" || true
  echo "[baseline] 숨김 미추적 경로 $(wc -l < "$DEST/.cofa_baseline")개 기록 (.cofa_baseline, 수정 금지)"
fi

# 1) AGENTS.md: 없으면 복사, 있으면 플랫폼 내용 아래에 덧붙임(기존 내용 유지)
if [ -f "$DEST/AGENTS.md" ]; then
  if ! grep -q "작업 규칙 (모든 단계에 적용)" "$DEST/AGENTS.md"; then
    printf '\n\n' >> "$DEST/AGENTS.md"
    cat "$KIT/AGENTS.md" >> "$DEST/AGENTS.md"
    echo "[append] 기존 AGENTS.md 아래에 규칙 추가"
  else
    echo "[skip] AGENTS.md 에 이미 규칙 있음"
  fi
else
  cp "$KIT/AGENTS.md" "$DEST/AGENTS.md"; echo "[copy] AGENTS.md"
fi

# 2) 서브에이전트 정의: 같은 이름 파일이 있으면 건너뜀
mkdir -p "$DEST/.codex/agents"
for f in "$KIT"/.codex/agents/*.toml; do
  n="$(basename "$f")"
  if [ -e "$DEST/.codex/agents/$n" ]; then echo "[skip] .codex/agents/$n 존재"
  else cp "$f" "$DEST/.codex/agents/$n"; echo "[copy] .codex/agents/$n"; fi
done

# 3) 프로젝트 config.toml: 플랫폼 파일이 있으면 절대 건드리지 않음
if [ -e "$DEST/.codex/config.toml" ]; then
  echo "[skip] .codex/config.toml 존재 → 수정하지 않음. 중첩 금지는 AGENTS.md 규칙으로 대체"
else
  cp "$KIT/.codex/config.toml" "$DEST/.codex/config.toml"; echo "[copy] .codex/config.toml"
  OURS_CFG=1
fi

# 4) 스킬: 같은 이름 폴더가 있으면 건너뜀
mkdir -p "$DEST/.agents/skills"
for d in "$KIT"/.agents/skills/*/; do
  n="$(basename "$d")"
  if [ -e "$DEST/.agents/skills/$n" ]; then echo "[skip] skill $n 존재"
  else cp -r "$d" "$DEST/.agents/skills/$n"; echo "[copy] skill $n"; fi
done

# 5) 설치 기록 커밋 (작업 이력에 외부 자료 사용 사실을 남김). .git이 읽기 전용이어도 설치는 끝까지 간다
set +e
git config user.name  >/dev/null 2>&1 || git config user.name  "candidate"
git config user.email >/dev/null 2>&1 || git config user.email "candidate@local"
# 키트가 놓은 파일만 커밋 (플랫폼 소유 파일은 건드리지 않음)
ok=1
git add AGENTS.md || ok=0
for f in "$KIT"/.codex/agents/*.toml; do git add ".codex/agents/$(basename "$f")" || ok=0; done
for d in "$KIT"/.agents/skills/*/; do git add ".agents/skills/$(basename "$d")" || ok=0; done
if [ "$OURS_CFG" = 1 ]; then git add .codex/config.toml || ok=0; fi
if [ -e .cofa_baseline ]; then git add .cofa_baseline || ok=0; fi
if [ "$ok" = 0 ]; then echo "[git] git add 실패(.git 읽기 전용 등). 파일 설치는 끝남. 우회하지 말고 사람이 직접: git add AGENTS.md .codex/agents .agents/skills (있으면 .cofa_baseline) 후 git commit -m '키트 설치'"
elif git diff --cached --quiet; then echo "[git] 커밋할 변경 없음"
elif git commit -q -m "작업 규칙·서브에이전트·스킬 설정 (출처: 공개 저장소 MIIXmix/cofa-kit)"; then echo "[git] 설치 커밋 완료"
else echo "[git] 커밋 실패(.git 읽기 전용 등). 파일 설치는 끝남. 우회하지 말고 사람이 직접 커밋"; fi

echo
echo "다음: 1) Codex 종료(/quit) 후 다시 실행(codex)"
echo "      2) '규칙 2번이 뭐야?' 로 AGENTS.md 로드 확인"
echo "      3) (선택) /model 로 ID 확인 → .codex/agents/*.toml 의 model 주석 해제"
