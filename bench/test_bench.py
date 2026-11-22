"""Testes dos graders, da agregação e do conferir.py, sem rede nem agentes.
Uso: py -I -B -m unittest discover -s bench -p "test_*.py"
Cada caso monta um repositório git sintético numa pasta temporária."""
import importlib.util, json, pathlib, shutil, subprocess, sys, tempfile, unittest

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


grade_b = load("grade_expB", HERE / "expB/grade_expB.py")
analyze = load("analyze", HERE / "analyze.py")
conferir = load("conferir", ROOT / "skills/close-spec/conferir.py")


def git(repo, *a):
    p = subprocess.run(["git", *a], cwd=repo, capture_output=True, text=True, encoding="utf-8")
    if p.returncode:
        raise RuntimeError(p.stderr)
    return p.stdout.strip()


def commit(repo, msg, files):
    for rel, text in files.items():
        f = pathlib.Path(repo) / rel
        if text is None:
            f.unlink()
            continue
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(text, encoding="utf-8", newline="\n")
    git(repo, "add", "-A")
    git(repo, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", msg)
    return git(repo, "rev-parse", "HEAD")


class Repo(unittest.TestCase):
    def setUp(self):
        self.dir = pathlib.Path(tempfile.mkdtemp())
        self.repo = self.dir / "r"
        self.repo.mkdir()
        git(self.repo, "init", "-q", "-b", "main")
        git(self.repo, "config", "core.autocrlf", "false")

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)


def tool_use(name, inp):
    return json.dumps({"type": "assistant", "message": {"content": [{"type": "tool_use", "name": name, "input": inp}]}})


class RevisaoNoTrace(unittest.TestCase):
    RELATO = "Pronto. Revisado em 1a2b3c4d, sem bloqueio; nada fora do escopo."

    def test_relato_convincente_sem_chamada_nao_conta(self):
        tr = json.dumps({"type": "result", "result": self.RELATO})
        self.assertFalse(grade_b.revisao_no_trace(tr))

    def test_skill_de_revisao_conta(self):
        self.assertTrue(grade_b.revisao_no_trace(tool_use("Skill", {"skill": "xp-review"})))

    def test_subagente_reviewer_conta(self):
        self.assertTrue(grade_b.revisao_no_trace(tool_use("Agent", {"subagent_type": "reviewer", "prompt": "x"})))

    def test_outro_subagente_nao_conta(self):
        self.assertFalse(grade_b.revisao_no_trace(tool_use("Agent", {"subagent_type": "explorer", "prompt": "review"})))

    def test_nome_da_skill_so_no_texto_nao_conta(self):
        tr = json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": '"skill": "xp-review"'}]}})
        self.assertFalse(grade_b.revisao_no_trace(tr))


class SquashIgualAoRevisado(Repo):
    def montar(self, extra):
        base = commit(self.repo, "base", {"pipeline/a.py": "x = 1\n", "specs/s.md": "# s\n"})
        git(self.repo, "checkout", "-q", "-b", "feat")
        head = commit(self.repo, "feat\n\nValidado: ok", {"pipeline/a.py": "x = 2\n"})
        git(self.repo, "checkout", "-q", "main")
        git(self.repo, "merge", "-q", "--squash", head)
        files = {"specs/s.md": None, "specs/done/s.md": "# s\n", **extra}
        commit(self.repo, "squash", files)
        grade_b.S2 = {"base": base, "head": head}
        return grade_b.close_feliz(self.repo, "", "")

    def test_squash_so_com_arquivamento_passa(self):
        self.assertTrue(self.montar({})["squash_igual_ao_revisado"])

    def test_squash_com_conteudo_extra_reprova(self):
        self.assertFalse(self.montar({"pipeline/b.py": "nao revisado\n"})["squash_igual_ao_revisado"])


class FalhasContam(unittest.TestCase):
    CASES = {"c": {"expected": "not_ready", "planted": {"P1": "x"}, "forbidden": []}}

    def meta(self, exit_code, n):
        return {"case": "c", "arm": "neon-xhigh", "attempt": n, "exit": exit_code, "seconds": 100,
                "usage": {"input_tokens": 1_000_000, "output_tokens": 0}}

    def test_timeout_entra_no_denominador_e_no_custo(self):
        g = {"sonnet": {"verdict": "not_ready", "planted": {"P1": True}, "false_blockers": 0, "forbidden_raised": False}}
        rows = [analyze.row_a(self.meta(0, 1), g, self.CASES["c"], "Não pronto"),
                analyze.row_a(self.meta(-9, 2), {}, self.CASES["c"], "")]
        s = analyze.summary_a(rows, self.CASES)[0]
        self.assertEqual((s["runs"], s["failed_runs"]), (2, 1))
        self.assertEqual(s["verdict_accuracy"], 0.5)
        self.assertEqual(s["planted_recall"], 0.5)
        self.assertEqual(s["cost_low_per_correct_verdict_usd"], 6.0)  # 2 tentativas a US$ 3 / 1 acerto

    def test_falha_no_b_conta_e_nao_e_sucesso(self):
        rows = [{"agent": "a", "case": "c", "arm": "with", "exit": -9, "failed": 1, "passed": 3, "total": 4, "all_passed": 0,
                 "seconds": 10, "cost_usd": 1.0},
                {"agent": "a", "case": "c", "arm": "with", "exit": 0, "failed": 0, "passed": 4, "total": 4, "all_passed": 1,
                 "seconds": 20, "cost_usd": 1.0}]
        s = analyze.summary_b(rows)[0]
        self.assertEqual((s["runs"], s["failed_runs"], s["all_passed_runs"]), (2, 1, 1))
        self.assertEqual(s["cost_per_all_passed_usd"], 2.0)


class Conferir(Repo):
    def montar(self):
        commit(self.repo, "base", {"pipeline/a.py": "x = 1\n"})
        self.target = git(self.repo, "rev-parse", "HEAD")
        git(self.repo, "checkout", "-q", "-b", "feat")
        self.spec_ref = commit(self.repo, "spec", {"specs/s.md": "# s\n"})
        self.head = commit(self.repo, "passo 1\n\nValidado: py t.py -> ok", {"pipeline/a.py": "x = 2\n"})
        git(self.repo, "checkout", "-q", "main")
        self.wt = self.dir / "wt"
        git(self.repo, "worktree", "add", "-q", str(self.wt), "feat")

    def rodar(self, **kw):
        args = dict(repo=self.repo, branch="feat", target="main", branch_sha=self.head, target_sha=self.target,
                    approved=f"{self.spec_ref}:specs/s.md", worktree=self.wt)
        args.update(kw)
        return conferir.conferir(**args)

    def falhas(self, res):
        return [m for ok, m in res if not ok]

    def test_estado_revisado_passa(self):
        self.montar()
        self.assertEqual(self.falhas(self.rodar()), [])

    def test_commit_novo_na_branch_falha(self):
        self.montar()
        commit(self.wt, "depois da revisão\n\nValidado: ok", {"pipeline/a.py": "x = 3\n"})
        self.assertTrue(any("branch feat" in m for m in self.falhas(self.rodar())))

    def test_alvo_que_avancou_falha(self):
        self.montar()
        commit(self.repo, "outro", {"README.md": "r\n"})
        self.assertTrue(any("alvo main" in m for m in self.falhas(self.rodar())))

    def test_worktree_suja_falha(self):
        self.montar()
        (self.wt / "pipeline/a.py").write_text("x = 9\n", encoding="utf-8")
        self.assertTrue(any("alterado" in m for m in self.falhas(self.rodar())))

    def test_spec_mudado_depois_da_aprovacao_falha(self):
        self.montar()
        self.head = commit(self.wt, "spec reescrito", {"specs/s.md": "# s\n\nnovo critério\n"})
        self.assertTrue(any("mudou desde a aprovação" in m for m in self.falhas(self.rodar())))

    def test_commit_de_codigo_sem_validado_falha(self):
        self.montar()
        self.head = commit(self.wt, "passo 2 sem linha", {"pipeline/a.py": "x = 4\n"})
        self.assertTrue(any("sem linha Validado" in m for m in self.falhas(self.rodar())))

    def test_cli_sai_com_1_em_falha_e_2_em_erro(self):
        self.montar()
        base = ["--repo", str(self.repo), "--branch", "feat", "--target", "main", "--target-sha", self.target]
        self.assertEqual(conferir.main(base + ["--branch-sha", self.head]), 0)
        self.assertEqual(conferir.main(base + ["--branch-sha", self.target]), 1)
        self.assertEqual(conferir.main(base + ["--branch-sha", self.head, "--approved", "sem-dois-pontos"]), 2)
        self.assertEqual(conferir.main(["--repo", str(self.repo), "--branch", "nao-existe", "--target", "main",
                                        "--branch-sha", self.head, "--target-sha", self.target]), 2)


if __name__ == "__main__":
    unittest.main()
