#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
skill-bootstrap 自检 —— 端到端验证引导机制

不联网: 现场用标准库造一个合法的 wheel 包当作被测依赖,
        再让引导器用 --no-index 从本地目录安装它。

流程:
  1. 造一个迷你 skill (含模块级重依赖导入 + __main__ 守卫的入口脚本)
  2. 用 init_skill_runtime.py 给它装上引导器
  3. 在干净环境里跑入口脚本 -> 引导器应建 venv、离线装依赖、重跑成功

用法:
  python selftest.py
"""
import ast
import base64
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, bool(ok), detail))
    mark = "\u2713" if ok else "\u2717"
    line = f"  {mark} {name}"
    if detail:
        line += f"   [{detail}]"
    print(line, flush=True)
    return ok


def section(title):
    print(f"\n{title}", flush=True)


# --------------------------------------------------------------- 造 wheel

def build_wheel(outdir, name="dummy-dep", version="0.0.1", module="dummy_dep"):
    """用标准库造一个合法的 pure-python wheel (离线安装的被测依赖)"""
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    dist = name.replace("-", "_")
    fn = outdir / f"{dist}-{version}-py3-none-any.whl"

    files = {
        f"{module}.py": 'VALUE = "ok"\n',
        f"{dist}-{version}.dist-info/METADATA":
            f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n",
        f"{dist}-{version}.dist-info/WHEEL":
            "Wheel-Version: 1.0\n"
            "Generator: skill-bootstrap-selftest\n"
            "Root-Is-Purelib: true\n"
            "Tag: py3-none-any\n",
    }
    record = []
    with zipfile.ZipFile(fn, "w", zipfile.ZIP_DEFLATED) as z:
        for path, text in files.items():
            data = text.encode("utf-8")
            z.writestr(path, data)
            digest = base64.urlsafe_b64encode(
                hashlib.sha256(data).digest()).rstrip(b"=").decode()
            record.append(f"{path},sha256={digest},{len(data)}")
        rec = f"{dist}-{version}.dist-info/RECORD"
        record.append(f"{rec},,")
        z.writestr(rec, "\n".join(record) + "\n")
    return fn


# --------------------------------------------------------------- 造迷你 skill

DEMO_SRC = '''#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""迷你 skill 的入口脚本 (自检用)"""
import sys

# 模块级的重依赖导入, 失败即退出 ——
# 这正是挂载点必须放在模块顶部、而不能放进 main() 的原因
try:
    import dummy_dep
except ImportError:
    sys.exit("缺少 dummy_dep")


def main():
    print("DEMO_OK", dummy_dep.VALUE)
    return 0


if __name__ == "__main__":
    sys.exit(main())
'''


def make_mini_skill(root):
    d = Path(root) / "mini-skill"
    (d / "scripts").mkdir(parents=True)
    (d / "SKILL.md").write_text(
        "---\nname: mini-skill\ndescription: 自检用的迷你技能\n---\n",
        encoding="utf-8")
    (d / "scripts" / "demo.py").write_text(DEMO_SRC, encoding="utf-8")
    return d


# --------------------------------------------------------------- 运行助手

def parse_json_tail(out):
    """从混合输出里取出 JSON 对象 (引导器的日志可能排在前面)"""
    i = out.find("{")
    if i < 0:
        return {}
    try:
        return json.loads(out[i:])
    except Exception:
        return {}


def run(cmd, env_extra=None, cwd=None, timeout=600):
    env = dict(os.environ)
    env.update(env_extra or {})
    env.pop("PYTHONPATH", None)
    t0 = time.time()
    try:
        p = subprocess.run(cmd, env=env, cwd=str(cwd) if cwd else None,
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                           timeout=timeout)
        out = p.stdout.decode("utf-8", "replace")
        return p.returncode, out, time.time() - t0
    except subprocess.TimeoutExpired as e:
        out = (e.stdout or b"").decode("utf-8", "replace")
        return -9, out + "\n<TIMEOUT>", time.time() - t0


# --------------------------------------------------------------- 主流程

def main():
    tmp = Path(tempfile.mkdtemp(prefix="skill-bs-"))
    try:
        return _run(tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _run(tmp):
    py = sys.executable
    print("=" * 62)
    print("  skill-bootstrap 自检")
    print("=" * 62)
    print(f"  解释器: {py}")
    print(f"  临时区: {tmp}")

    wheels_ok = tmp / "wheels_ok"
    wheels_empty = tmp / "wheels_empty"
    wheels_empty.mkdir(parents=True, exist_ok=True)
    cwd = tmp / "cwd"
    cwd.mkdir(parents=True, exist_ok=True)

    # ---------------- 1. 造 wheel ----------------
    section("[1/9] 造离线 wheel (纯标准库, 不联网)")
    try:
        whl = build_wheel(wheels_ok)
        check("生成 dummy-dep wheel", whl.is_file(), whl.name)
    except Exception as e:
        check("生成 dummy-dep wheel", False, str(e))
        return _summary()

    # ---------------- 2. 造迷你 skill ----------------
    section("[2/9] 造迷你 skill")
    mini = make_mini_skill(tmp)
    demo = mini / "scripts" / "demo.py"
    check("迷你 skill 就绪", demo.is_file(), str(mini.name))

    # ---------------- 3. 语法与无依赖导入 ----------------
    section("[3/9] 引擎自身可在无第三方依赖下导入")
    rc, out, _ = run([py, "-c",
                      f"import sys; sys.path.insert(0, r'{HERE}');"
                      "import skill_bootstrap as b;"
                      "print('ENGINE_VERSION', b.ENGINE_VERSION)"],
                     cwd=cwd)
    check("引擎可独立导入", rc == 0 and "ENGINE_VERSION" in out,
          out.strip().splitlines()[-1] if out.strip() else "")

    # ---------------- 4. 脚手架 ----------------
    section("[4/9] 运行脚手架 (dry-run 后正式执行)")
    rc, out, _ = run([py, str(HERE / "init_skill_runtime.py"), str(mini),
                      "--core", "dummy_dep=dummy-dep",
                      "--group", "stdlib=json,pathlib",
                      "--group", "never=zzz_no_such_pkg_xyz=zzz-no-such-pkg-xyz",
                      "--entry", "demo.py:core",
                      "--dry-run"], cwd=cwd)
    check("dry-run 不报错", rc == 0, f"exit={rc}")

    rc, out, _ = run([py, str(HERE / "init_skill_runtime.py"), str(mini),
                      "--core", "dummy_dep=dummy-dep",
                      "--group", "stdlib=json,pathlib",
                      "--group", "never=zzz_no_such_pkg_xyz=zzz-no-such-pkg-xyz",
                      "--entry", "demo.py:core"], cwd=cwd)
    ok_scaffold = rc == 0
    check("脚手架执行成功", ok_scaffold, out.strip().splitlines()[-1] if out.strip() else "")

    engine_dst = mini / "scripts" / "skill_bootstrap.py"
    cfg_dst = mini / "scripts" / "deps.json"
    check("引擎已复制到目标 skill", engine_dst.is_file())
    check("deps.json 已生成", cfg_dst.is_file())

    cfg = {}
    if cfg_dst.is_file():
        try:
            cfg = json.loads(cfg_dst.read_text(encoding="utf-8"))
        except Exception as e:
            check("deps.json 可解析", False, str(e))
    check("deps.json 内容正确",
          cfg.get("env_prefix") == "MINI_SKILL"
          and cfg.get("default_groups") == ["core"]
          and set(cfg.get("groups", {})) == {"core", "stdlib", "never"},
          f"prefix={cfg.get('env_prefix')} groups={list(cfg.get('groups', {}))}")

    # ---------------- 5. 挂载点在模块顶部 ----------------
    section("[5/9] 挂载点位置 (必须在重依赖导入之前)")
    src = demo.read_text(encoding="utf-8")
    lines = src.splitlines()
    hook_line = next((i for i, ln in enumerate(lines) if "ensure_and_reexec" in ln), None)
    heavy_line = next((i for i, ln in enumerate(lines) if "import dummy_dep" in ln), None)
    check("挂载点已插入", hook_line is not None,
          f"第 {hook_line + 1} 行" if hook_line is not None else "")
    check("挂载点早于重依赖导入",
          hook_line is not None and heavy_line is not None and hook_line < heavy_line,
          f"hook@{hook_line} < import@{heavy_line}")
    try:
        ast.parse(src)
        check("插入后语法正确", True)
    except SyntaxError as e:
        check("插入后语法正确", False, str(e))

    # 幂等
    rc, out, _ = run([py, str(HERE / "init_skill_runtime.py"), str(mini),
                      "--core", "dummy_dep=dummy-dep", "--entry", "demo.py:core"],
                     cwd=cwd)
    ok_idem = rc == 0 and out.count("已含挂载点") == 1
    check("重复执行幂等 (跳过已挂载)", ok_idem)

    # ---------------- 6. --check 无副作用 + 快速路径 ----------------
    section("[6/9] --check 无副作用 / 依赖齐全时开销")
    rt1 = tmp / "rt_check"
    env_check = {"MINI_SKILL_RUNTIME_DIR": str(rt1)}
    t0 = time.time()
    rc, out, _ = run([py, str(engine_dst), "--check", "--groups", "stdlib"],
                     env_extra=env_check, cwd=cwd)
    dt = time.time() - t0
    check("--check 对已就绪分组返回 0", rc == 0, f"{dt * 1000:.0f} ms")
    check("--check 未创建任何目录", not rt1.exists(),
          "无残留" if not rt1.exists() else "!! 有残留")
    check("快速路径开销可接受", dt < 3.0, f"{dt * 1000:.0f} ms")

    rc, out, _ = run([py, str(engine_dst), "--check", "--groups", "core",
                      "--json"], env_extra=env_check, cwd=cwd)
    j = parse_json_tail(out)
    check("缺依赖时 --check 能识别",
          rc == 1 and j.get("action") == "disabled"
          and "dummy_dep" in (j.get("missing") or []),
          f"exit={rc} missing={j.get('missing')}")

    # ---------------- 7. 纯离线自动安装 (主验证) ----------------
    section("[7/9] 纯离线自动安装 (建 venv -> --no-index 装 -> 重跑)")
    rt2 = tmp / "rt_install"
    env_inst = {
        "MINI_SKILL_RUNTIME_DIR": str(rt2),
        "MINI_SKILL_FIND_LINKS": str(wheels_ok),
    }
    rc, out, dt = run([py, str(demo)], env_extra=env_inst, cwd=cwd, timeout=900)
    check("入口脚本首次调用即成功", rc == 0 and "DEMO_OK ok" in out,
          f"exit={rc} {dt:.1f}s")
    check("走了离线安装 (--no-index)", "--no-index" in out)
    check("运行时 venv 已建立", (rt2 / "venv").is_dir(), str(rt2.name))

    # 直接问运行时 venv 的解释器, 确认依赖真的落在它里面
    ve = rt2 / "venv"
    vpy = next((str(ve / r) for r in ("Scripts/python.exe", "bin/python", "bin/python3")
                if (ve / r).is_file()), None)
    ok_inst = False
    if vpy:
        rc2, out2, _ = run([vpy, "-c", "import dummy_dep; print(dummy_dep.VALUE)"], cwd=cwd)
        ok_inst = rc2 == 0 and "ok" in out2
    check("依赖确实落进运行时 venv", ok_inst, vpy or "未找到 venv 解释器")

    # 第二次调用: 应复用运行时 venv, 不再安装
    rc, out, dt2 = run([py, str(demo)], env_extra=env_inst, cwd=cwd, timeout=300)
    check("二次调用复用而非重装",
          rc == 0 and "DEMO_OK ok" in out and "--no-index" not in out,
          f"exit={rc} {dt2:.1f}s")
    check("二次调用更快", dt2 < dt, f"{dt2:.1f}s < {dt:.1f}s")

    # ---------------- 8. 关闭开关 ----------------
    section("[8/9] 关闭自动安装 / 失败路径")
    rt3 = tmp / "rt_noauto"
    rc, out, dt = run([py, str(demo)],
                      env_extra={"MINI_SKILL_RUNTIME_DIR": str(rt3),
                                 "MINI_SKILL_NO_AUTO_INSTALL": "1"},
                      cwd=cwd, timeout=300)
    check("关闭后退出码为 3", rc == 3, f"exit={rc}")
    check("关闭后未建运行时 venv", not rt3.exists())
    check("关闭后打印补齐指引", "补齐方式" in out)

    # 无本地包且无网 -> 立即失败, 不挂起
    rt4 = tmp / "rt_broken"
    rc, out, dt = run([py, str(demo)],
                      env_extra={"MINI_SKILL_RUNTIME_DIR": str(rt4),
                                 "MINI_SKILL_FIND_LINKS": str(wheels_empty),
                                 "MINI_SKILL_GROUPS": "never"},
                      cwd=cwd, timeout=300)
    check("包缺失时明确报错而非挂起", rc == 3 and dt < 180,
          f"exit={rc} {dt:.1f}s")
    check("报错含 pip 线索", "No matching distribution" in out or "ERROR" in out)

    # ---------------- 9. 仓库洁净 ----------------
    section("[9/9] 产物与洁净度")
    check("skill 内未产生 .runtime 残留", not (mini / ".runtime").exists())
    check("wheel 目录保持在临时区", not (mini / "wheelhouse").exists())

    return _summary()


def _summary():
    print()
    print("=" * 62)
    total = len(RESULTS)
    passed = sum(1 for _, ok, _ in RESULTS if ok)
    failed = [n for n, ok, _ in RESULTS if not ok]
    print(f"  结果: {passed} 通过, {total - passed} 失败, 共 {total} 项")
    if failed:
        print("  失败项:")
        for n in failed:
            print(f"    - {n}")
    print("=" * 62)
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
