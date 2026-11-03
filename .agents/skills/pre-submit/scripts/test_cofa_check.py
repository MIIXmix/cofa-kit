import contextlib
import importlib.util
import io
import os
import re
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cofa_check.py")
NOTES = "\n".join("## " + k for k in ["판단과 근거", "결정 카드", "검증 결과", "남은 한계", "데이터 처리"])
NOTES = NOTES.replace("## 결정 카드", "## 결정 카드\n결정: 정렬 방식 / 고른 안: 안정 정렬") + "\n"


class CheckCase(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.d = self.td.name
        self.git("init", "-q")
        for f in "README.md REQUIREMENTS.md PLAN.md PROGRESS.md COLLAB_LOG.md".split():
            self.w(f, "x\n")
        self.w("NOTES.md", NOTES)
        self.w("app.py", "import os\nprint(os.name)\n")
        self.w("requirements.txt", "# 외부 패키지 없음\n")
        self.commit()

    def tearDown(self):
        self.td.cleanup()

    def git(self, *a):
        subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t"] + list(a),
                       cwd=self.d, check=True, capture_output=True)

    def commit(self):
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "c")

    def w(self, rel, text, enc="utf-8"):
        p = os.path.join(self.d, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding=enc, newline="\n") as fh:
            fh.write(text)

    def run_check(self, *args, **kw):
        r = subprocess.run([sys.executable, SCRIPT, "--root", kw.get("root", self.d)] + list(args), capture_output=True,
                           text=True, encoding="utf-8", cwd=kw.get("cwd"), env=dict(os.environ, PYTHONIOENCODING="utf-8"))
        return r.returncode, r.stdout

    def status(self, out, name):
        m = re.search(r"\[(\w+)\] %s:" % name, out)
        return m and m.group(1)


class Tests(CheckCase):
    def test_clean_repo_passes(self):
        rc, out = self.run_check()
        self.assertEqual(rc, 0, out)
        self.assertIn("FAIL 0 /", out)

    def test_secret_fails_without_echoing_value(self):
        self.w("app.py", 'SECRET_KEY = "abcdef123456"\n')
        self.commit()
        rc, out = self.run_check()
        self.assertEqual(rc, 1, out)
        self.assertEqual(self.status(out, "secrets"), "FAIL")
        self.assertIn("app.py:1", out)
        self.assertNotIn("abcdef123456", out)

    def test_no_code_files_is_not_a_pass(self):
        os.remove(os.path.join(self.d, "app.py"))
        self.commit()
        self.assertEqual(self.status(self.run_check()[1], "secrets"), "FAIL")

    def _pii_repo(self, result_text):
        self.w("raw/people.csv", "이름,사번\n홍길동,E001\n", "utf-8-sig")
        self.w("out/result.txt", result_text)
        self.commit()
        return self.run_check("--raw", "raw", "--pii-source", "raw/people.csv", "--pii-cols", "이름")

    def test_pii_leak_fails_without_echoing_value(self):
        rc, out = self._pii_repo("담당: 홍길동\n")
        self.assertEqual(rc, 1, out)
        self.assertEqual(self.status(out, "pii_leak"), "FAIL")
        self.assertIn("out/result.txt:1", out)
        self.assertNotIn("홍길동", out)

    def test_pii_in_any_check_output_is_masked(self):
        self.w("홍길동/app.py", 'SECRET_KEY = "abcdef123456"\n')
        rc, out = self._pii_repo("담당: P-001\n")
        self.assertEqual(self.status(out, "secrets"), "FAIL", out)
        self.assertNotIn("홍길동", out)
        self.assertNotIn("abcdef123456", out)

    def test_yaml_key_name_suffix_not_secret(self):
        self.w("k8s.yaml", "secretName: postgres-credentials\ntoken_url: https://auth.example/token\n")
        self.w("app.py", "x = 1\n")
        self.commit()
        rc, out = self.run_check()
        self.assertEqual(self.status(out, "secrets"), "PASS", out)

    def test_pii_leak_in_work_copy_fails(self):
        self.w("work/people_clean.csv", "id,이름\nP-001,홍길동\n")
        rc, out = self._pii_repo("담당: P-001\n")
        self.assertEqual(self.status(out, "pii_leak"), "FAIL", out)
        self.assertIn("work/people_clean.csv:2", out)
        self.assertNotIn("홍길동", out)

    def test_pii_clean_passes(self):
        rc, out = self._pii_repo("담당: P-001\n")
        self.assertEqual(self.status(out, "pii_leak"), "PASS", out)
        self.assertEqual(self.status(out, "raw_unchanged"), "PASS", out)

    def test_pii_bad_column_fails(self):
        self.w("raw/people.csv", "이름,사번\n홍길동,E001\n", "cp949")
        self.commit()
        rc, out = self.run_check("--pii-source", "raw/people.csv", "--pii-cols", "성명")
        self.assertEqual(self.status(out, "pii_leak"), "FAIL", out)

    def test_notes_without_decision_card_fails(self):
        self.w("NOTES.md", NOTES.replace("결정 카드", "기타"))
        self.commit()
        self.assertEqual(self.status(self.run_check()[1], "notes_sections"), "FAIL")

    def test_empty_decision_card_fails(self):
        self.w("NOTES.md", NOTES.replace("\n결정: 정렬 방식 / 고른 안: 안정 정렬", ""))
        self.commit()
        self.assertEqual(self.status(self.run_check()[1], "notes_sections"), "FAIL")

    def test_tracked_env_fails(self):
        self.w(".env", "K=1\n")
        self.w(".gitignore", ".env\n")
        self.git("add", "-f", ".env", ".gitignore")
        self.git("commit", "-q", "-m", "env")
        rc, out = self.run_check()
        self.assertEqual(rc, 1, out)
        self.assertEqual(self.status(out, "env_files"), "FAIL")

    def test_env_not_ignored_fails(self):
        self.w(".env", "K=1\n")
        self.assertEqual(self.status(self.run_check()[1], "env_files"), "FAIL")

    def test_modified_raw_fails(self):
        self.w("raw/data.csv", "a,b\n1,2\n")
        self.commit()
        self.w("raw/data.csv", "a,b\n1,3\n")
        rc, out = self.run_check("--raw", "raw/data.csv")
        self.assertEqual(rc, 1, out)
        self.assertEqual(self.status(out, "raw_unchanged"), "FAIL")

    def test_missing_dependency_fails(self):
        if not hasattr(sys, "stdlib_module_names"):
            self.skipTest("stdlib_module_names 없는 파이썬")
        self.w("app.py", "import requests\nimport os\n")
        self.commit()
        rc, out = self.run_check()
        self.assertEqual(self.status(out, "deps"), "FAIL", out)
        self.assertIn("app.py:1", out)
        self.w("requirements.txt", "Requests==2.0\n")
        self.commit()
        self.assertEqual(self.status(self.run_check()[1], "deps"), "PASS")

    def test_debug_true_fails(self):
        self.w("app.py", "app.run(host='0.0.0.0', debug=True)\n")
        self.commit()
        self.assertEqual(self.status(self.run_check()[1], "debug_mode"), "FAIL")

    def test_baseline_untracked_ignored_but_new_file_fails(self):
        self.w(".bashrc", "x\n")
        self.w(".cache/a/b.txt", "x\n")
        self.w(".cofa_baseline", ".bashrc\n.cache/\n")
        self.assertEqual(self.status(self.run_check()[1], "git_clean"), "PASS")
        self.w("new.txt", "x\n")
        self.w(".cache/a/c.txt", "x\n")
        rc, out = self.run_check()
        self.assertEqual(self.status(out, "git_clean"), "FAIL", out)
        self.assertIn("new.txt", out)
        self.assertNotIn(".cache", out)
        os.remove(os.path.join(self.d, "new.txt"))
        self.w(".bashrc.bak", "x\n")  # 기준선 파일 이름 접두만 같은 새 파일은 잡는다
        rc, out = self.run_check()
        self.assertEqual(self.status(out, "git_clean"), "FAIL", out)
        self.assertIn(".bashrc.bak", out)
        os.remove(os.path.join(self.d, ".bashrc.bak"))
        self.git("add", ".bashrc")
        self.git("commit", "-q", "-m", "b")
        self.assertEqual(self.status(self.run_check()[1], "git_clean"), "PASS")
        self.w(".bashrc", "z\n")  # 추적 파일 수정은 기준선에 있어도 잡는다
        rc, out = self.run_check()
        self.assertEqual(self.status(out, "git_clean"), "FAIL", out)
        self.assertIn(".bashrc", out)

    def test_baseline_ignores_non_hidden_entries(self):
        self.w("data/demo.csv", "a\n1\n")
        self.w(".cofa_baseline", "data/\nREADME.md\n./\n")
        rc, out = self.run_check()
        self.assertEqual(self.status(out, "git_clean"), "FAIL", out)
        self.assertIn("data/demo.csv", out)

    def test_baseline_unused_when_root_is_subfolder(self):
        self.w(".task/app.py", "x = 1\n")
        self.w(".task/.cofa_baseline", ".task/\n")  # 저장소 루트 기준 경로라 가드가 없으면 전부 숨겨진다
        self.w(".bashrc", "x\n")  # root 밖 상위 파일은 검사 범위가 아니다
        rc, out = self.run_check(root=os.path.join(self.d, ".task"))
        self.assertEqual(self.status(out, "git_clean"), "FAIL", out)
        self.assertIn(".task/app.py", out)
        self.assertNotIn(".bashrc", out)

    def test_hidden_env_dir_hint_says_no_git_add(self):
        self.w(".local/lib/site.py", "x\n")
        self.w(".bash_history", "x\n")
        self.w(".gitignore", "x\n")
        rc, out = self.run_check()
        self.assertRegex(out, r"\.local/lib/site\.py[^\n]*git add 금지")
        self.assertRegex(out, r"\.bash_history[^\n]*git add 금지")
        self.assertNotRegex(out, r"\.gitignore 커밋되지[^\n]*git add 금지")

    def test_uncommitted_fails_and_bad_args_exit_2(self):
        self.w("new.txt", "x\n")
        self.assertEqual(self.status(self.run_check()[1], "git_clean"), "FAIL")
        self.assertEqual(self.run_check("--pii-source", "x.csv")[0], 2)

    # 1. 읽지 않은 파일을 조용히 넘기지 않는다
    def test_large_text_file_is_scanned(self):
        rc, out = self._pii_repo(("x" * 99 + "\n") * 15000 + "원본 이름: 홍길동\n")
        self.assertEqual(self.status(out, "pii_leak"), "FAIL", out)
        self.assertIn("out/result.txt:15001", out)
        self.assertNotIn("홍길동", out)

    def test_binary_file_is_listed_as_unscanned(self):
        os.makedirs(os.path.join(self.d, "out"))
        with open(os.path.join(self.d, "out", "data.xlsx"), "wb") as fh:
            fh.write(b"PK\x03\x04\x00\x00\x00\x00data")
        rc, out = self._pii_repo("담당: P-001\n")
        self.assertEqual(self.status(out, "pii_leak"), "WARN", out)
        self.assertIn("out/data.xlsx", out)
        self.assertIn("CSV로 내보내", out)
        self.assertEqual(rc, 0, out)

    # 2, 3. 하위 폴더 .env와 gitignore 판정
    def test_nested_env_untracked_fails_and_no_git_add_hint(self):
        self.w("backend/.env", "K=1\n")
        rc, out = self.run_check()
        self.assertEqual(rc, 1, out)
        self.assertEqual(self.status(out, "env_files"), "FAIL", out)
        self.assertRegex(out, r"backend/\.env[^\n]*\.gitignore")
        self.assertNotRegex(out, r"backend/\.env[^\n]*git add")

    def test_nested_env_tracked_fails(self):
        self.w("backend/.env.local", "K=1\n")
        self.commit()
        rc, out = self.run_check()
        self.assertEqual(self.status(out, "env_files"), "FAIL", out)
        self.assertIn("git rm --cached backend/.env.local", out)

    def test_gitignore_glob_is_judged_by_git(self):
        self.w(".env", "K=1\n")
        self.w("backend/.env", "K=1\n")
        self.w(".gitignore", "**/.env\n")
        self.commit()
        self.assertEqual(self.status(self.run_check()[1], "env_files"), "PASS")

    # 4, 5, 6. secrets 규칙
    def test_unquoted_yaml_secret_fails_without_echoing_value(self):
        self.w("config.yaml", "password: hunter2hunter2\n")
        self.commit()
        rc, out = self.run_check()
        self.assertEqual(self.status(out, "secrets"), "FAIL", out)
        self.assertIn("config.yaml:1", out)
        self.assertNotIn("hunter2hunter2", out)
        self.w("config.yaml", "password: ${DB_PASSWORD}\napi_key: <your-key-here>\n# token: abcdefghijkl\nname: short\n")
        self.commit()
        self.assertEqual(self.status(self.run_check()[1], "secrets"), "PASS")

    def test_ipynb_and_tsx_are_scanned_and_work_dir_too(self):
        for rel, text in [("nb.ipynb", '{"source": ["api_key = \\"abcdef123456\\"\\n"]}\n'),
                          ("ui.tsx", 'const apiKey = "abcdef123456";\n'),
                          ("work/tmp.py", 'SECRET_KEY = "abcdef123456"\n')]:
            self.w(rel, text)
            self.commit()
            out = self.run_check()[1]
            self.assertEqual(self.status(out, "secrets"), "FAIL", rel + out)
            self.assertIn(rel + ":1", out)
            os.remove(os.path.join(self.d, rel))

    def test_key_name_false_positives_pass(self):
        self.w("app.py", 'tokenizer = "bert-base-uncased"\nx = {"token_type": "bearer", "tokens": "abcdefgh"}\nsecretary = "abcdefgh"\n')
        self.commit()
        self.assertEqual(self.status(self.run_check()[1], "secrets"), "PASS")

    def test_template_sample_dist_files_not_scanned(self):
        self.w(".env.template", 'API_KEY="abcdefghij"\n')
        self.w(".env.sample", 'API_KEY="abcdefghij"\n')
        self.w("config.yaml.dist", "password: hunter2hunter2\n")
        self.commit()
        out = self.run_check()[1]
        self.assertEqual(self.status(out, "secrets"), "PASS", out)
        self.assertEqual(self.status(out, "env_files"), "PASS", out)

    def test_private_key_rule_fails_without_echo(self):
        self.w("app.py", 'K = "-----BEGIN RSA PRIVATE KEY-----"\n')
        self.commit()
        out = self.run_check()[1]
        self.assertEqual(self.status(out, "secrets"), "FAIL", out)
        self.assertNotIn("BEGIN RSA", out)

    # 7. deps 오탐
    def test_deps_dotted_import_setup_py_and_r_include(self):
        if not hasattr(sys, "stdlib_module_names"):
            self.skipTest("stdlib_module_names 없는 파이썬")
        self.w("app.py", "import google.generativeai\nimport requests\nimport pip\n")
        self.w("setup.py", "from setuptools import setup\nimport wheel\n")
        self.w("requirements.txt", "-r requirements/base.txt\ngoogle-generativeai==1.0\n")
        self.w("requirements/base.txt", "requests==2.0\n")
        self.commit()
        out = self.run_check()[1]
        self.assertEqual(self.status(out, "deps"), "PASS", out)

    # 8. --raw 없이 원본 폴더 제외
    def test_no_raw_excludes_source_folder_with_warn(self):
        self.w("raw/people.csv", "이름,사번\n홍길동,E001\n", "utf-8-sig")
        self.w("raw/orders.csv", "고객\n홍길동\n")
        self.commit()
        rc, out = self.run_check("--pii-source", "raw/people.csv", "--pii-cols", "이름")
        self.assertEqual(rc, 0, out)
        self.assertEqual(self.status(out, "pii_leak"), "WARN", out)
        self.assertIn("원본 폴더를 --raw로 지정하면 원본 변경 검사도 한다", out)
        self.assertNotIn("홍길동", out)

    # 9. 경로에 개인정보가 있으면 가린다
    def test_pii_in_path_is_masked_in_git_clean(self):
        self._pii_repo("담당: P-001\n")
        self.w("홍길동_보고서.txt", "x\n")
        rc, out = self.run_check("--raw", "raw", "--pii-source", "raw/people.csv", "--pii-cols", "이름")
        self.assertEqual(self.status(out, "git_clean"), "FAIL", out)
        self.assertIn("경로 가림", out)
        self.assertNotIn("홍길동", out)

    # 10. 필수 파일 대상 0개
    def test_empty_require_fails(self):
        rc, out = self.run_check("--require", "")
        self.assertEqual(self.status(out, "required_files"), "FAIL", out)
        self.assertEqual(rc, 1)

    # 11. 경로 해석과 인자 검증
    def test_pii_source_falls_back_to_cwd_when_not_under_root(self):
        self.w("out/result.txt", "담당: 홍길동\n")
        self.commit()
        with tempfile.TemporaryDirectory() as other:
            with open(os.path.join(other, "people.csv"), "w", encoding="utf-8") as fh:
                fh.write("이름\n홍길동\n")
            out = self.run_check("--pii-source", "people.csv", "--pii-cols", "이름", cwd=other)[1]
        self.assertEqual(self.status(out, "pii_leak"), "FAIL", out)
        self.assertIn("out/result.txt:1", out)

    def test_absolute_raw_and_pii_source_paths(self):
        self.w("raw/people.csv", "이름\n홍길동\n")
        self.w("out/result.txt", "담당: P-001\n")
        self.commit()
        out = self.run_check("--raw", os.path.join(self.d, "raw"), "--pii-source",
                             os.path.join(self.d, "raw", "people.csv"), "--pii-cols", "이름")[1]
        self.assertEqual(self.status(out, "pii_leak"), "PASS", out)
        self.assertEqual(self.status(out, "raw_unchanged"), "PASS", out)

    def test_pii_min_len_below_one_exits_2(self):
        self.assertEqual(self.run_check("--pii-min-len", "0")[0], 2)

    # 12. 오류 경로
    def test_check_exception_prints_type_only(self):
        spec = importlib.util.spec_from_file_location("cofa_check_mod", SCRIPT)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        def boom(c):
            raise ValueError("SECRETVALUE123")
        buf = io.StringIO()
        with mock.patch.object(mod, "CHECKS", [("boom", boom)]), contextlib.redirect_stdout(buf):
            rc = mod.main(["--root", self.d])
        self.assertEqual(rc, 1)
        self.assertIn("ValueError", buf.getvalue())
        self.assertNotIn("SECRETVALUE123", buf.getvalue())

    def test_warn_only_exits_0(self):
        self.w("app.py", "import os\nprint(os.environ.get('HOME'))\n")
        self.commit()
        rc, out = self.run_check()
        self.assertEqual(self.status(out, "env_files"), "WARN", out)
        self.assertEqual(rc, 0, out)
        self.assertIn("FAIL 0 / WARN 1", out)

    def test_not_a_git_repo_fails_git_clean(self):
        with tempfile.TemporaryDirectory() as plain:
            with open(os.path.join(plain, "app.py"), "w") as fh:
                fh.write("import os\n")
            rc, out = self.run_check(root=plain)
        self.assertEqual(self.status(out, "git_clean"), "FAIL", out)
        self.assertEqual(rc, 1)


if __name__ == "__main__":
    unittest.main()
