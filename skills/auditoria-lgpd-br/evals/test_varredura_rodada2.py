# -*- coding: utf-8 -*-
"""Testes da segunda rodada: falsos positivos, mascaramento, .env, migrations, pastas de build."""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

AQUI = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(os.path.dirname(AQUI), "scripts", "varredura.py")
HEX32 = "9f8e7d6c5b4a39281706f5e4d3c2b1a0"
B64 = "QWxhZGRpbjpvcGVuU2VzYW1lMTIzNDU2Nzg5MA"
JWT = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJpc2NhLXNpbnRldGljYSJ9.assinaturaFALSAisca0123456789"


def rodar_json(raiz):
    r = subprocess.run([sys.executable, "-I", SCRIPT, raiz, "--formato", "json"],
                       capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, r.stderr
    return r.stdout, json.loads(r.stdout)


def escrever(base, rel, conteudo):
    p = os.path.join(base, *rel.split("/"))
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(conteudo)


class Base(unittest.TestCase):
    def setUp(self):
        self.raiz = tempfile.mkdtemp(prefix="varredura-r2-")
        self.addCleanup(shutil.rmtree, self.raiz, ignore_errors=True)


class TestFalsoPositivoLeituraDeChave(Base):
    def test_codigo_que_so_le_a_chave_nao_e_segredo(self):
        escrever(self.raiz, "scripts/sondas/a.mjs",
                 "const chave = env.split(/\r?\n/).find((l) => l.startsWith('PARCEIRO_API_KEY='));\n"
                 "const k = process.env.MINHA_API_KEY;\nconst t = import.meta.env.VITE_TOKEN;\n"
                 "const s = { token: 'TOKEN_DO_AMBIENTE', senha: 'SENHA_LIDA' };\n")
        escrever(self.raiz, "scripts/b.py", "import os\nsecret = os.environ['MEU_SEGREDO']\nsenha = getenv('X')\n")
        escrever(self.raiz, "config.php", "<?php define('DB_PASS', 'Valor-Real-9988');\n")
        _, d = rodar_json(self.raiz)
        segs = [a for a in d["achados"] if a["categoria"] == "segredos"]
        self.assertEqual([a["arquivo"] for a in segs], ["config.php"])


class TestMascaramentoDeTokens(Base):
    def test_linha_json_minificada_com_varios_tokens(self):
        linha = ('{"previewModeId":"%s","a":"%s","b":"%s","x":"fbq(\'init\',\'1\')",'
                 '"c":"%s"}' % (HEX32, B64, JWT, HEX32[::-1]))
        escrever(self.raiz, "cache/.previewinfo.js", "var cfg=" + linha + ";fbq('init','123');\n")
        escrever(self.raiz, "m/001.sql", "-- " + HEX32 + "\nCREATE TABLE t (cpf VARCHAR(14)); -- " + B64 + "\n")
        bruto, d = rodar_json(self.raiz)
        self.assertTrue(d["achados"])
        for v in (HEX32, HEX32[::-1], B64, JWT, B64[:20], JWT[:20]):
            self.assertNotIn(v, bruto)
        conteudo = ("segredos", "rastreadores_terceiros", "coleta_dados_pessoais",
                    "sessao_cookies", "logs", "ia_externa")
        for a in d["achados"]:
            if a["categoria"] in conteudo:
                self.assertLessEqual(len(a["trecho_mascarado"]), 135)
                for t in re.findall(r"[A-Za-z0-9_\-+/=]{16,}", a["trecho_mascarado"]):
                    self.assertFalse(re.search(r"\d", t) and re.search(r"[A-Za-z]", t), t[:4])


class TestPastasDeBuild(Base):
    def test_next_auditoria_e_minificados_nao_sao_varridos(self):
        escrever(self.raiz, ".next-auditoria/cache/x.js", "define('DB_PASS','Valor-Real-9988');\n")
        escrever(self.raiz, "coverage/a.js", "fbq('init','1')\n")
        escrever(self.raiz, "public/lib.min.js", "fbq('init','1')\n")
        escrever(self.raiz, "ok.js", "console.log('oi')\n")
        _, d = rodar_json(self.raiz)
        self.assertEqual(d["achados"], [])
        ign = d["limites"]["pastas_ignoradas_existentes"]
        self.assertIn(".next-auditoria", ign)
        self.assertIn("coverage", ign)
        self.assertEqual(d["limites"]["compilados_pulados"], 1)


class TestArquivoAmbiente(Base):
    def test_agregado_sem_git(self):
        escrever(self.raiz, ".env", "DB_PASSWORD=Valor-Real-9988\nAPI_TOKEN=tok_abcdef123456xyz\nPORT=3000\n")
        bruto, d = rodar_json(self.raiz)
        envs = [a for a in d["achados"] if a["regra"] == "arquivo_ambiente"]
        self.assertEqual(len(envs), 1)
        self.assertIn("2 valor(es) secreto(s)", envs[0]["trecho_mascarado"])
        self.assertIn("DB_PASSWORD", envs[0]["trecho_mascarado"])
        self.assertNotIn("Valor-Real-9988", bruto)
        self.assertNotIn("tok_abcdef123456xyz", bruto)
        self.assertEqual([a for a in d["achados"] if a["categoria"] == "artefatos_deploy" and a["arquivo"] == ".env"], [])

    def test_severidade_depende_do_git(self):
        try:
            subprocess.run(["git", "init", "-q", self.raiz], check=True, capture_output=True, timeout=20)
        except (OSError, subprocess.SubprocessError):
            self.skipTest("git indisponível")
        escrever(self.raiz, ".gitignore", ".env.local\n")
        escrever(self.raiz, ".env", "DB_PASSWORD=Valor-Real-9988\n")
        escrever(self.raiz, ".env.local", "DB_PASSWORD=Valor-Real-9988\n")
        _, d = rodar_json(self.raiz)
        sev = {a["arquivo"]: a["severidade_sugerida"] for a in d["achados"] if a["regra"] == "arquivo_ambiente"}
        self.assertEqual(sev.get(".env"), "alta")
        self.assertEqual(sev.get(".env.local"), "info")


class TestMigrationsEDumps(Base):
    def test_migration_nao_e_dump_mas_dump_e(self):
        escrever(self.raiz, "banco/migrations/001_init.sql", "CREATE TABLE a (id INT);\n")
        escrever(self.raiz, "banco/schema.sql", "CREATE TABLE b (id INT);\n")
        escrever(self.raiz, "banco/copia.sql", "COPY clientes (id) FROM stdin;\n1\n\\.\n")
        escrever(self.raiz, "banco/cheio.sql", "".join("INSERT INTO t VALUES (%d);\n" % i for i in range(60)))
        escrever(self.raiz, "banco/x.dump", "binario?")
        _, d = rodar_json(self.raiz)
        art = {a["arquivo"]: a for a in d["achados"] if a["categoria"] == "artefatos_deploy"}
        for ok in ("banco/migrations/001_init.sql", "banco/schema.sql"):
            self.assertEqual(art[ok]["severidade_sugerida"], "info", ok)
        for dump in ("banco/copia.sql", "banco/cheio.sql", "banco/x.dump"):
            self.assertEqual(art[dump]["severidade_sugerida"], "alta", dump)


class TestAgrupamentoMd(Base):
    def test_md_tem_top10_e_agrupa(self):
        for i in range(5):
            escrever(self.raiz, "pag/p%d.html" % i, "<link href='https://fonts.googleapis.com/css?family=A'>\n")
        r = subprocess.run([sys.executable, "-I", SCRIPT, self.raiz], capture_output=True, text=True, encoding="utf-8")
        self.assertIn("## Top 10 para olhar primeiro", r.stdout)
        self.assertIn("pag/ (5 ocorrências)", r.stdout)
        self.assertEqual(r.stdout.count("pag/ (5 ocorrências)"), 2)  # top10 + tabela; não 5 linhas


if __name__ == "__main__":
    unittest.main()
