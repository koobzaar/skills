"""Confere se uma branch ainda é a que o revisor julgou, antes do portão de `implement` e do squash de `close-spec`.

Uso:
  python conferir.py --repo <checkout> --branch <branch> --target <alvo> --branch-sha <SHA> --target-sha <SHA>
                     [--approved <SHA>:<specs/slug.md>] [--worktree <caminho>]

Checagens, uma linha por resultado (OK ou FALHA):
  - a branch e o alvo estão nos SHAs revisados;
  - a worktree da branch (se informada) está no SHA revisado e sem mudanças;
  - o spec na branch é igual ao da referência aprovada (se informada);
  - todo commit de <alvo>..<branch> que não mexe só em specs/ tem uma linha "Validado:" (ou "Validated:").

Sai com 0 se tudo passou, 1 se alguma checagem falhou e 2 se a chamada ou o git falharam. Não roda os critérios de
aceite do spec: eles continuam sendo executados pelo agente, no HEAD atual. Só usa a biblioteca padrão.
"""
import argparse
import re
import subprocess
import sys


class GitError(Exception):
    pass


def git(cwd, *args, check=True):
    p = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if check and p.returncode:
        raise GitError(f"git {' '.join(args)}: {p.stderr.strip()}")
    return p.returncode, p.stdout.strip()


def same_sha(actual, expected):
    return len(expected) >= 7 and actual.startswith(expected.lower())


def conferir(repo, branch, target, branch_sha, target_sha, approved=None, worktree=None):
    """Lista de (ok, mensagem)."""
    out = []
    _, b = git(repo, "rev-parse", "--verify", f"{branch}^{{commit}}")
    _, t = git(repo, "rev-parse", "--verify", f"{target}^{{commit}}")
    out.append((same_sha(b, branch_sha), f"branch {branch} em {b[:12]}; revisado: {branch_sha[:12]}"))
    out.append((same_sha(t, target_sha), f"alvo {target} em {t[:12]}; revisado: {target_sha[:12]}"))

    if worktree:
        _, head = git(worktree, "rev-parse", "HEAD")
        _, status = git(worktree, "status", "--porcelain")
        out.append((same_sha(head, branch_sha), f"worktree {worktree} em {head[:12]}"))
        n = len(status.splitlines())
        out.append((not status, "worktree sem mudanças" if not status else f"worktree com {n} arquivo(s) alterado(s)"))

    if approved:
        if ":" not in approved:
            raise GitError(f"--approved deve ser <SHA>:<caminho do spec>, recebido: {approved}")
        ref, spec = approved.split(":", 1)
        rc, _ = git(repo, "diff", "--quiet", ref, b, "--", spec, check=False)
        if rc > 1:
            raise GitError(f"não consegui comparar {spec} entre {ref} e {branch}")
        out.append((rc == 0, f"spec {spec} igual ao aprovado em {ref[:12]}" if rc == 0
                    else f"spec {spec} mudou desde a aprovação em {ref[:12]}"))

    _, log = git(repo, "rev-list", "--no-merges", "--reverse", f"{t}..{b}")
    sem_validado = []
    for sha in log.split():
        _, files = git(repo, "diff-tree", "--no-commit-id", "--name-only", "-r", "--root", sha)
        if files and all(f.startswith("specs/") for f in files.splitlines()):
            continue  # commit só do spec ou de pendências
        _, msg = git(repo, "log", "-1", "--format=%B", sha)
        if not re.search(r"^(Validado|Validated):", msg, re.M | re.I):
            sem_validado.append(sha[:12])
    out.append((not sem_validado, "todo commit de código tem linha Validado:" if not sem_validado
                else "commits sem linha Validado: " + ", ".join(sem_validado)))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--repo", default=".")
    ap.add_argument("--branch", required=True)
    ap.add_argument("--target", required=True)
    ap.add_argument("--branch-sha", required=True)
    ap.add_argument("--target-sha", required=True)
    ap.add_argument("--approved")
    ap.add_argument("--worktree")
    a = ap.parse_args(argv)
    try:
        res = conferir(a.repo, a.branch, a.target, a.branch_sha, a.target_sha, a.approved, a.worktree)
    except GitError as e:
        print(f"ERRO {e}")
        return 2
    for ok, msg in res:
        print(("OK    " if ok else "FALHA ") + msg)
    return 0 if all(ok for ok, _ in res) else 1


if __name__ == "__main__":
    sys.exit(main())
