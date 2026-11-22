"""Testes do atualizar.py. Rodar com: python -m unittest discover tests

Nada aqui mexe no GitHub nem no repositório de verdade: o git e o gh são simulados
e os arquivos ficam numa pasta temporária.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import atualizar  # noqa: E402

README = "topo\n<!-- programas:inicio -->\nvelho\n<!-- programas:fim -->\nrodape\n"
PROGRAMAS = [
    {"nome": "App A", "pasta": "A", "descricao": "does A"},
    {"nome": "App B", "pasta": "B", "descricao": "does B"},
]


class GitFalso:
    """Simula o git do perfil. `ao_puxar` roda quando o script faz pull/fetch."""

    def __init__(self, tags, ao_puxar=None, push_falha=False):
        self.tags = list(tags)
        self.ao_puxar = ao_puxar
        self.push_falha = push_falha
        self.chamadas = []

    def __call__(self, *args, pasta=None, env=None):
        self.chamadas.append(args)
        if args[0] in ("pull", "fetch") and self.ao_puxar:
            f, self.ao_puxar = self.ao_puxar, None
            f(self)
        if args[0] == "tag" and args[1] == "--list":
            return "\n".join(sorted(self.tags, key=lambda t: [int(x) for x in t[1:].split(".")], reverse=True))
        if args[0] == "tag" and args[1] == "-a":
            self.tags.append(args[2])
        if args[0] == "tag" and args[1] == "-d":
            self.tags.remove(args[2])
        if args[0] == "push" and self.push_falha:
            raise RuntimeError("git push: rejected (fetch first)")
        if args[0] == "log":
            return "Perfil v1.0.5: App A v1.1\n\n- **App A**: v1.0 → v1.1"
        return ""

    def fez(self, *inicio):
        return any(c[:len(inicio)] == inicio for c in self.chamadas)


class Base(unittest.TestCase):
    def setUp(self):
        self.pasta = tempfile.mkdtemp()
        self.docs = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.docs, "A"))
        os.makedirs(os.path.join(self.docs, "B"))
        self.escrever("README.md", README)
        self.escrever("versoes.json", json.dumps({"App A": "v1.0", "App B": "v2.0"}))
        self.escrever("programas.json", json.dumps(PROGRAMAS))
        self.gh = []
        self.release_existe = True
        p = [
            mock.patch.object(atualizar, "AQUI", self.pasta),
            mock.patch.object(atualizar, "DOCS", self.docs),
            mock.patch.object(atualizar.subprocess, "run", self.gh_falso),
            mock.patch.object(atualizar, "ESPERA_TRAVA", 0.3),
        ]
        for x in p:
            x.start()
            self.addCleanup(x.stop)
        self.addCleanup(shutil.rmtree, self.pasta, True)
        self.addCleanup(shutil.rmtree, self.docs, True)

    def gh_falso(self, cmd, **kw):
        self.gh.append(cmd)
        rc = 0
        if "view" in cmd and not self.release_existe:
            rc = 1
        if kw.get("check") and rc:
            raise subprocess.CalledProcessError(rc, cmd)
        return subprocess.CompletedProcess(cmd, rc, "", "")

    def escrever(self, nome, texto):
        with open(os.path.join(self.pasta, nome), "w", encoding="utf-8") as f:
            f.write(texto)

    def ler(self, nome):
        with open(os.path.join(self.pasta, nome), encoding="utf-8") as f:
            return f.read()

    def rodar(self, git, versoes, argv=("atualizar.py",)):
        with mock.patch.object(atualizar, "git", git), \
             mock.patch.object(atualizar, "ultima_versao_da_pasta", lambda p: versoes[p["nome"]]), \
             mock.patch.object(sys, "argv", list(argv)):
            atualizar.main()

    def releases_criadas(self):
        return [c for c in self.gh if "create" in c]


class TestAtualizar(Base):
    def test_readme_e_lido_depois_do_pull(self):
        """Mudança que outra conversa enviou ao README não pode ser apagada."""
        def outra_conversa(g):
            self.escrever("README.md", README.replace("topo", "topo NOVO"))
        git = GitFalso(["v1.0.5"], ao_puxar=outra_conversa)
        self.rodar(git, {"App A": "v1.1", "App B": "v2.0"})
        self.assertIn("topo NOVO", self.ler("README.md"))

    def test_tag_contada_depois_do_pull(self):
        """Se outra conversa já criou a v1.0.6, esta tem que ser a v1.0.7."""
        def outra_conversa(g):
            g.tags.append("v1.0.6")
            self.escrever("versoes.json", json.dumps({"App A": "v1.0", "App B": "v2.1"}))
        git = GitFalso(["v1.0.5"], ao_puxar=outra_conversa)
        self.rodar(git, {"App A": "v1.1", "App B": "v2.1"})
        self.assertIn("v1.0.7", git.tags)
        self.assertEqual(len(self.releases_criadas()), 1)
        self.assertIn("v1.0.7", self.releases_criadas()[0])

    def test_pasta_sumida_nao_rebaixa_versao(self):
        """Pasta mudada de lugar não pode virar 'in development' no perfil."""
        shutil.rmtree(os.path.join(self.docs, "B"))
        git = GitFalso(["v1.0.5"])
        with mock.patch.object(atualizar, "git", git), mock.patch.object(sys, "argv", ["x"]), \
             mock.patch.object(atualizar, "ultima_versao_da_pasta", lambda p: "v1.0"):
            atualizar.main()
        self.assertEqual(json.loads(self.ler("versoes.json"))["App B"], "v2.0")
        self.assertEqual(self.releases_criadas(), [])

    def test_programas_json_com_campo_faltando(self):
        self.escrever("programas.json", json.dumps([{"nome": "App A", "pasta": "A"}]))
        git = GitFalso(["v1.0.5"])
        with self.assertRaises(ValueError) as e:
            self.rodar(git, {"App A": "v1.1"})
        self.assertIn("App A", str(e.exception))
        self.assertIn("descricao", str(e.exception))
        self.assertFalse(git.fez("commit"))

    def test_programas_json_com_nome_repetido(self):
        self.escrever("programas.json", json.dumps(PROGRAMAS + [PROGRAMAS[0]]))
        git = GitFalso(["v1.0.5"])
        with self.assertRaises(ValueError) as e:
            self.rodar(git, {"App A": "v1.1", "App B": "v2.0"})
        self.assertIn("App A", str(e.exception))

    def test_release_que_faltou_e_criada_na_proxima_vez(self):
        """Se o gh falhou depois do push, a próxima execução cria a release que faltou."""
        self.release_existe = False
        git = GitFalso(["v1.0.5"])
        self.rodar(git, {"App A": "v1.0", "App B": "v2.0"})  # nada mudou
        criadas = self.releases_criadas()
        self.assertEqual(len(criadas), 1)
        self.assertIn("v1.0.5", criadas[0])

    def test_release_existente_nao_e_criada_de_novo(self):
        git = GitFalso(["v1.0.5"])
        self.rodar(git, {"App A": "v1.0", "App B": "v2.0"})
        self.assertEqual(self.releases_criadas(), [])

    def test_push_recusado_desfaz_commit_e_tag(self):
        git = GitFalso(["v1.0.5"], push_falha=True)
        with self.assertRaises(RuntimeError):
            self.rodar(git, {"App A": "v1.1", "App B": "v2.0"})
        self.assertNotIn("v1.0.6", git.tags)
        self.assertTrue(git.fez("reset"))
        self.assertEqual(self.releases_criadas(), [])

    def test_duas_conversas_ao_mesmo_tempo(self):
        """Com outra conversa rodando (trava recente), esta espera e desiste com aviso."""
        self.escrever(".atualizar.lock", "outra")
        git = GitFalso(["v1.0.5"])
        with self.assertRaises(RuntimeError) as e:
            self.rodar(git, {"App A": "v1.1", "App B": "v2.0"})
        self.assertIn("outra", str(e.exception).lower())
        self.assertFalse(git.fez("commit"))

    def test_trava_velha_e_ignorada(self):
        """Trava esquecida por uma execução que travou não bloqueia para sempre."""
        self.escrever(".atualizar.lock", "velha")
        velho = time.time() - 3600
        os.utime(os.path.join(self.pasta, ".atualizar.lock"), (velho, velho))
        git = GitFalso(["v1.0.5"])
        self.rodar(git, {"App A": "v1.1", "App B": "v2.0"})
        self.assertIn("v1.0.6", git.tags)
        self.assertFalse(os.path.exists(os.path.join(self.pasta, ".atualizar.lock")))


class TestVersao(unittest.TestCase):
    def test_contagem(self):
        self.assertEqual(atualizar.versao_seguinte("v0.1.9"), "v0.2.0")
        self.assertEqual(atualizar.versao_seguinte("v0.9.9"), "v1.0.0")
        self.assertEqual(atualizar.versao_seguinte("v1.0.305"), "v1.0.306")
        self.assertEqual(atualizar.versao_seguinte("v1.0.999"), "v1.1.0")
        self.assertEqual(atualizar.versao_seguinte("v1.9.999"), "v2.0.0")


if __name__ == "__main__":
    unittest.main()
