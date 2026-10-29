#!/usr/bin/env bash
# 사용법: 과제 작업 폴더(루트)에서
#   git clone https://github.com/<계정>/cofa-kit /tmp/cofa-kit && bash /tmp/cofa-kit/install.sh
# 원칙: 플랫폼이 이미 둔 파일은 절대 덮어쓰지 않는다.
set -euo pipefail
OURS_CFG=0
KIT="$(cd "$(dirname "$0")" && pwd)"
DEST="$(pwd)"

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
  echo "[skip] .codex/config.toml 존재 → 수정하지 않음. 동시 실행 제한은 AGENTS.md 규칙으로 대체"
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

# 5) 설치 기록 커밋 (작업 이력에 외부 자료 사용 사실을 남김)
git rev-parse --git-dir >/dev/null 2>&1 || { git init -q; echo "[git] 저장소가 없어 git init"; }
git config user.name  >/dev/null 2>&1 || git config user.name  "candidate"
git config user.email >/dev/null 2>&1 || git config user.email "candidate@local"
# 키트가 놓은 파일만 커밋 (플랫폼 소유 파일은 건드리지 않음)
git add AGENTS.md
for f in "$KIT"/.codex/agents/*.toml; do git add ".codex/agents/$(basename "$f")"; done
for d in "$KIT"/.agents/skills/*/; do git add ".agents/skills/$(basename "$d")"; done
[ "$OURS_CFG" = 1 ] && git add .codex/config.toml
if git diff --cached --quiet; then echo "[git] 커밋할 변경 없음"
else git commit -q -m "작업 규칙·서브에이전트·스킬 설정 (출처: 공개 저장소 MIIXmix/cofa-kit)" && echo "[git] 설치 커밋 완료"; fi

echo
echo "다음: 1) Codex 종료(/quit) 후 다시 실행(codex)"
echo "      2) '규칙 2번이 뭐야?' 로 AGENTS.md 로드 확인"
echo "      3) (선택) /model 로 ID 확인 → .codex/agents/*.toml 의 model 주석 해제"
