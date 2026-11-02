#!/usr/bin/env bash
# 自检：从上游基线出发打一遍补丁，逐项断言后再决定是否编译。
#
#   ./customizations/verify.sh            # 静态自检
#   ./customizations/verify.sh --build    # 静态自检 + 编译
#
# 断言内容：
#   1) 补丁从干净基线可完整应用；
#   2) 重复执行不产生任何字节变化（幂等）；
#   3) 改动文件集合与补丁声明完全一致（不误伤上游）；
#   4) 行尾风格无损（CRLF 文件仍是 CRLF）；
#   5) 每个 [fork:tag:name] 标记各出现一次；
#   6) Kotlin 结构括号配平、无 TODO 占位、无未引用的 payload。
set -uo pipefail

cd "$(dirname "$0")/.."
ROOT=$(pwd)

BUILD=0
if [ "${1:-}" = "--build" ]; then
  BUILD=1
fi

fail() {
  echo
  echo "自检失败：$1"
  exit 1
}

echo "== 1/4 还原上游基线 =="
if [ -d customizations/.state ]; then
  while IFS= read -r created; do
    [ -n "$created" ] && [ -f "$created" ] && rm -f "$created"
  done < <(cat customizations/.state/created-*.txt 2>/dev/null)
fi
rm -rf customizations/.state
# 基线指向上游 tag，而不是 HEAD：补丁产物本身也在版本库里（为了可复现构建），
# 用 HEAD 当基线会让补丁全部命中标记而跳过，自检就变成空转。
# customizations/ 自身是补丁基础设施，这里不回滚。
BASE_TAG="${FORK_BASE_TAG:-4204-0.1.9}"
# 基线定位：有 tag 就用 tag，没有就退回固定提交号。
# 远端仓库刻意不挂 tag —— GitHub 会把 tag 列在 Releases 区块里，看着像发了版本。
if git rev-parse -q --verify "refs/tags/$BASE_TAG" >/dev/null; then
  BASE_REF="refs/tags/$BASE_TAG"
else
  BASE_REF="${FORK_BASE_COMMIT:-4cf17c7461bf773836bb062aba06b4e217e52104}"
  git rev-parse -q --verify "$BASE_REF^{commit}" >/dev/null ||
    fail "基线既没有 tag $BASE_TAG，也没有提交 $BASE_REF"
fi
export FORK_BASE_REF="$BASE_REF"
git checkout "$BASE_REF" -- app/ || fail "无法还原上游基线 $BASE_REF"
# app/src 下所有未跟踪文件都是补丁产物（payload 落盘），一并清理，避免维护白名单。
git ls-files --others --exclude-standard -- app/src | while IFS= read -r extra; do
  rm -f "$extra"
done
echo "   基线已还原（$BASE_REF）"
python customizations/checks.py snapshot || fail "无法记录行尾基线"

echo "== 2/4 应用补丁（第一遍） =="
bash customizations/apply.sh || fail "补丁应用失败"
mkdir -p customizations/.state
{
  # 改动 + 新增都要进快照：新增文件在文件已存在时只会记进 created，
  # 只快照 touched 会让幂等断言漏掉一半文件。
  while IFS= read -r file; do
    [ -n "$file" ] && [ -f "$file" ] && sha256sum "$file"
  done < <(cat customizations/.state/touched-*.txt customizations/.state/created-*.txt 2>/dev/null | sort -u)
} > customizations/.state/hashes.txt
echo "   已记录 $(wc -l < customizations/.state/hashes.txt) 个文件的哈希"

echo "== 3/4 重复应用（第二遍，应无写入） =="
second=$(bash customizations/apply.sh) || fail "补丁第二遍执行失败"
echo "$second" | sed 's/^/   /'
if echo "$second" | grep -q "写入 [1-9]"; then
  fail "补丁非幂等：第二遍仍写入了内容"
fi

echo "== 4/4 结构断言 =="
python customizations/checks.py || fail "结构断言未通过"

if [ "$BUILD" = "1" ]; then
  echo
  echo "== 编译校验 =="
  ./gradlew --no-daemon :app:compileDebugKotlin || fail "编译失败"
  echo "   编译通过"
fi

echo
echo "全部自检通过（$ROOT）"
