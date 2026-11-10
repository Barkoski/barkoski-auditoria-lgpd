# -*- coding: utf-8 -*-
"""Testes da varredura.py contra o projeto-isca sintético (somente stdlib).

Rodar (a partir da raiz do repositório):
    py -I -m unittest discover -s skills/auditoria-lgpd-br/evals -v
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest

AQUI = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(os.path.dirname(AQUI), "scripts", "varredura.py")
ISCA = os.path.join(AQUI, "fixture-site-isca")

# Valores sintéticos plantados na isca (nenhum deve aparecer inteiro na saída).
SEGREDOS = ["Teste-Isca-123456", "tok_isca_ABCDEF0123456789falso", "000.000.000-00",
            "fulano@exemplo.invalid"]
NOMES_TMP = ["documento-isca-01", "documento-isca-02", "documento-isca-03",
             "documento-isca-04", "documento-isca-05"]


def rodar(raiz, *extra):
    return subprocess.run([sys.executable, "-I", SCRIPT, raiz] + list(extra),
                          capture_output=True, text=True, encoding="utf-8")


class TestVarredura(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmpdir = tempfile.mkdtemp(prefix="varredura-test-")
        cls.md_path = os.path.join(cls.tmpdir, "r.md")
        cls.json_path = os.path.join(cls.tmpdir, "r.json")
        r1 = rodar(ISCA, "--saida", cls.md_path)
        r2 = rodar(ISCA, "--saida", cls.json_path)
        assert r1.returncode == 0, r1.stderr
        assert r2.returncode == 0, r2.stderr
        with open(cls.md_path, encoding="utf-8") as fh:
            cls.md = fh.read()
        with open(cls.json_path, encoding="utf-8") as fh:
            cls.raw_json = fh.read()
        cls.data = json.loads(cls.raw_json)
        cls.achados = cls.data["achados"]

    def tem(self, categoria, arquivo=None, regra=None, sev=None, trecho=None):
        for a in self.achados:
            if a["categoria"] != categoria:
                continue
            if arquivo and a["arquivo"] != arquivo:
                continue
            if regra and a["regra"] != regra:
                continue
            if sev and a["severidade_sugerida"] != sev:
                continue
            if trecho and trecho not in a["trecho_mascarado"]:
                continue
            return True
        return False

    def test_esquema_dos_achados(self):
        chaves = {"regra", "categoria", "severidade_sugerida", "arquivo", "linha",
                  "trecho_mascarado", "dica"}
        for a in self.achados:
            self.assertEqual(set(a), chaves)
            self.assertIn(a["severidade_sugerida"], ("alta", "média", "baixa", "info"))
        ordem = {"alta": 0, "média": 1, "baixa": 2, "info": 3}
        sevs = [ordem[a["severidade_sugerida"]] for a in self.achados]
        self.assertEqual(sevs, sorted(sevs))
        self.assertIn("limites", self.data)
        self.assertIn("resumo_por_categoria", self.data)

    def test_segredos_php(self):
        self.assertTrue(self.tem("segredos", "config.php", sev="alta", trecho="DB_PASS"))
        self.assertTrue(self.tem("segredos", "config.php", sev="alta", trecho="API_TOKEN"))
        # getenv() é placeholder: não deve ser achado
        self.assertFalse(self.tem("segredos", "config.php", trecho="SMTP_PASSWORD"))

    def test_chave_publica_e_info(self):
        self.assertTrue(self.tem("segredos", ".env.example", sev="info",
                                 trecho="NEXT_PUBLIC_SUPABASE_ANON_KEY"))
        self.assertFalse(self.tem("segredos", ".env.example", sev="alta"))

    def test_rastreador_google_fonts(self):
        self.assertTrue(self.tem("rastreadores_terceiros", "includes/header.php"))

    def test_coleta_formulario(self):
        for campo in ("nome", "email", "telefone"):
            self.assertTrue(self.tem("coleta_dados_pessoais", "contato.php",
                                     regra="campo_formulario", trecho='name="%s"' % campo), campo)
        self.assertTrue(self.tem("coleta_dados_pessoais", "dump.sql", regra="coluna_schema"))

    def test_sessao_sem_cookie_secure(self):
        self.assertTrue(self.tem("sessao_cookies", "contato.php",
                                 regra="session_start_sem_cookie_secure"))

    def test_log_post_inteiro(self):
        self.assertTrue(self.tem("logs", "contato.php"))

    def test_artefatos(self):
        self.assertTrue(self.tem("artefatos_deploy", "dump.sql"))
        self.assertTrue(self.tem("artefatos_deploy", "setup.php"))
        self.assertTrue(self.tem("artefatos_deploy", regra="sem_gitignore"))

    def test_empacotamento_primeiro_segmento(self):
        achado = [a for a in self.achados if a["categoria"] == "empacotamento"
                  and a["arquivo"] == "build-zip.ps1" and a["regra"] == "empacotamento_nao_exclui"]
        self.assertTrue(achado)
        t = achado[0]["trecho_mascarado"]
        self.assertIn("config.php", t)
        self.assertIn("tmp/", t)
        self.assertIn("primeiro segmento", achado[0]["dica"])

    def test_pasta_documentos_so_contagem(self):
        achado = [a for a in self.achados if a["categoria"] == "pastas_documentos"]
        self.assertEqual(len(achado), 1)
        self.assertEqual(achado[0]["arquivo"], "tmp/")
        self.assertIn(".jpg: 5", achado[0]["trecho_mascarado"])

    def test_htaccess_nao_cobre(self):
        achado = [a for a in self.achados if a["categoria"] == "protecao_web"
                  and a["regra"] == "htaccess_nao_cobre"]
        self.assertTrue(achado)
        t = achado[0]["trecho_mascarado"]
        self.assertIn("tmp/", t)
        self.assertIn("dump.sql", t)
        self.assertNotIn("config.php", t)  # esse está coberto
        self.assertTrue(self.tem("protecao_web", regra="sem_redirect_https", sev="info"))

    def test_nenhum_valor_sensivel_na_saida(self):
        for saida, nome in ((self.md, "md"), (self.raw_json, "json")):
            for v in SEGREDOS:
                self.assertNotIn(v, saida, "%s vazou na saída %s" % (v[:3], nome))
            # JWT completo da anon key também não aparece
            with open(os.path.join(ISCA, ".env.example"), encoding="utf-8") as fh:
                linhas = fh.readlines()
            for linha in linhas:
                if linha.startswith("NEXT_PUBLIC_SUPABASE_ANON_KEY="):
                    jwt = linha.split("=", 1)[1].strip()
                    self.assertNotIn(jwt, saida)
                    self.assertNotIn(jwt[:40], saida)

    def test_nomes_de_tmp_nao_aparecem(self):
        for saida in (self.md, self.raw_json):
            for n in NOMES_TMP:
                self.assertNotIn(n, saida)

    def test_recusa_saida_dentro_da_raiz(self):
        alvo = os.path.join(ISCA, "relatorio-nao-pode.md")
        r = rodar(ISCA, "--saida", alvo)
        self.assertNotEqual(r.returncode, 0)
        self.assertFalse(os.path.exists(alvo))
        self.assertIn("dentro da pasta auditada", r.stderr)
        # subpasta também
        alvo2 = os.path.join(ISCA, "tmp", "x.json")
        r = rodar(ISCA, "--saida", alvo2)
        self.assertNotEqual(r.returncode, 0)
        self.assertFalse(os.path.exists(alvo2))

    def test_somente_leitura(self):
        antes = sorted(os.path.join(d, f) for d, _, fs in os.walk(ISCA) for f in fs)
        rodar(ISCA)
        depois = sorted(os.path.join(d, f) for d, _, fs in os.walk(ISCA) for f in fs)
        self.assertEqual(antes, depois)

    def test_pastas_ignoradas_sao_reportadas(self):
        with tempfile.TemporaryDirectory() as raiz:
            os.makedirs(os.path.join(raiz, "node_modules", "x"))
            with open(os.path.join(raiz, "node_modules", "x", "a.js"), "w") as fh:
                fh.write("fbq('init','1')")
            with open(os.path.join(raiz, "grande.txt"), "w") as fh:
                fh.write("a" * 200)
            r = rodar(raiz, "--formato", "json", "--max-bytes", "100")
            self.assertEqual(r.returncode, 0)
            d = json.loads(r.stdout)
            self.assertIn("node_modules", d["limites"]["pastas_ignoradas_existentes"])
            self.assertIn("grande.txt", d["limites"]["acima_max_bytes"])
            self.assertEqual(d["achados"], [])

    def test_symlink_para_fora_nao_e_seguido(self):
        with tempfile.TemporaryDirectory() as raiz, tempfile.TemporaryDirectory() as fora:
            with open(os.path.join(fora, "segredo.php"), "w") as fh:
                fh.write("<?php define('DB_PASS','ValorForaDaRaiz99');")
            try:
                os.symlink(fora, os.path.join(raiz, "link"), target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("sem permissão para criar symlink")
            r = rodar(raiz, "--formato", "json")
            self.assertNotIn("ValorForaDaRaiz99", r.stdout)
            self.assertEqual(json.loads(r.stdout)["achados"], [])


if __name__ == "__main__":
    unittest.main()
