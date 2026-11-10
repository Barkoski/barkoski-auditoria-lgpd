# -*- coding: utf-8 -*-
"""Testes da terceira rodada: credenciais de teste, CPF/CNPJ, telefone, campos, .git, pastas, rastreadores, empacotamento."""
import subprocess
import unittest

from test_varredura_rodada2 import Base, escrever, rodar_json

VALOR_ENV = "Valor-Sintetico-7788"
OUTRA_SENHA = "Outra-Senha-Teste-5566"


def achados(d, **kw):
    return [a for a in d["achados"] if all(a.get(k) == v for k, v in kw.items())]


class TestCredenciaisDeTeste(Base):
    def test_teste_em_portugues_vira_baixa(self):
        escrever(self.raiz, "scripts/testar_login.mjs", "const SENHA = '%s';\n" % OUTRA_SENHA)
        escrever(self.raiz, "ocr/sonda_x.py", "senha = '%s'\n" % OUTRA_SENHA)
        escrever(self.raiz, "src/app.mjs", "const SENHA = '%s';\n" % OUTRA_SENHA)
        bruto, d = rodar_json(self.raiz)
        sev = {a["arquivo"]: a["severidade_sugerida"] for a in d["achados"] if a["categoria"] == "segredos"}
        self.assertEqual(sev["scripts/testar_login.mjs"], "baixa")
        self.assertEqual(sev["ocr/sonda_x.py"], "baixa")
        self.assertEqual(sev["src/app.mjs"], "alta")
        self.assertIn("Credencial de teste?", achados(d, arquivo="scripts/testar_login.mjs")[0]["dica"])

    def test_valor_igual_ao_do_env_e_alta_mesmo_em_teste_sem_vazar(self):
        escrever(self.raiz, ".env.local", "DB_PASSWORD=%s\nPORT=3000\n" % VALOR_ENV)
        escrever(self.raiz, "scripts/testar_copia.mjs", "const SENHA = '%s';\n" % VALOR_ENV)
        escrever(self.raiz, "src/cfg.json", '{"foo": "%s"}\n' % VALOR_ENV)   # chave sem nome de segredo
        escrever(self.raiz, "scripts/testar_outra.mjs", "const SENHA = '%s';\n" % OUTRA_SENHA)
        bruto, d = rodar_json(self.raiz)
        for arq in ("scripts/testar_copia.mjs", "src/cfg.json"):
            a = achados(d, arquivo=arq, regra="segredo_copiado_de_env")
            self.assertEqual(len(a), 1, arq)
            self.assertEqual(a[0]["severidade_sugerida"], "alta")
            self.assertIn(".env.local", a[0]["dica"])
            self.assertIn("DB_PASSWORD", a[0]["dica"])
        self.assertEqual(achados(d, arquivo="scripts/testar_outra.mjs")[0]["severidade_sugerida"], "baixa")
        self.assertNotIn(VALOR_ENV, bruto)
        self.assertNotIn(OUTRA_SENHA, bruto)

    def test_copia_versionada_no_git_diz_versionado(self):
        try:
            subprocess.run(["git", "init", "-q", self.raiz], check=True, capture_output=True, timeout=20)
        except (OSError, subprocess.SubprocessError):
            self.skipTest("git indisponível")
        escrever(self.raiz, ".gitignore", ".env.local\n")
        escrever(self.raiz, ".env.local", "API_KEY=%s\n" % VALOR_ENV)
        escrever(self.raiz, "manifest.json", '{"API_KEY": "%s"}\n' % VALOR_ENV)
        subprocess.run(["git", "-C", self.raiz, "add", "manifest.json"], check=True, capture_output=True, timeout=20)
        _, d = rodar_json(self.raiz)
        a = achados(d, arquivo="manifest.json")[0]
        self.assertEqual(a["severidade_sugerida"], "alta")
        self.assertIn("versionado no git", a["dica"])


class TestCpfCnpj(Base):
    def test_digitos_verificadores(self):
        escrever(self.raiz, "a.txt", "000.000.000-00 111.111.111-11 123.456.789-00 11.111.111/1111-11 12.345.678/0001-00\n")
        escrever(self.raiz, "real.txt", "529.982.247-25 e 11.222.333/0001-81\n")
        escrever(self.raiz, "exemplo/amostra.txt", "529.982.247-25 e 11.222.333/0001-81\n")
        bruto, d = rodar_json(self.raiz)
        self.assertEqual(achados(d, arquivo="a.txt"), [])
        r = {x["regra"]: x["severidade_sugerida"] for x in achados(d, arquivo="real.txt")}
        self.assertEqual(r, {"cpf_no_arquivo": "média", "cnpj_no_arquivo": "baixa"})   # CNPJ: pessoa jurídica
        escrever(self.raiz, "LEIA-ME.md", "529.982.247-25 e 123.456.789-09\n")
        _, d2 = rodar_json(self.raiz)
        self.assertEqual({x["severidade_sugerida"] for x in achados(d2, arquivo="LEIA-ME.md")}, {"baixa"})
        e = {x["regra"]: x["severidade_sugerida"] for x in achados(d, arquivo="exemplo/amostra.txt")}
        self.assertEqual(e, {"cpf_no_arquivo": "baixa", "cnpj_no_arquivo": "baixa"})
        self.assertNotIn("529.982.247-25", bruto)


class TestTelefone(Base):
    def test_cnj_e_ids_nao_sao_telefone(self):
        escrever(self.raiz, "dados/juris.json",
                 '{"p": "0001234-56.2020.4.03.6100", "id": 98765432101234, "d": "2020-11-22", '
                 '"n": "5001234-56.2021.4.01.3400", "x": "987654321"}\n')
        escrever(self.raiz, "dados/contato.json", '{"t": "(11) 98765-4321"}\n')
        _, d = rodar_json(self.raiz)
        self.assertEqual(achados(d, arquivo="dados/juris.json", regra="telefone_no_arquivo"), [])
        self.assertEqual(len(achados(d, arquivo="dados/contato.json", regra="telefone_no_arquivo")), 1)

    def test_pasta_cache_com_prefixo_e_ignorada(self):
        escrever(self.raiz, "x/.cache_experimento/a.json", '{"t": "(11) 98765-4321"}\n')
        _, d = rodar_json(self.raiz)
        self.assertEqual(d["achados"], [])
        self.assertIn("x/.cache_experimento", d["limites"]["pastas_ignoradas_existentes"])


class TestCampoFormulario(Base):
    def test_placeholder_nao_classifica(self):
        escrever(self.raiz, "p.tsx", '<input type="text" name="assunto" placeholder="Informe o CPF e a saúde do paciente" />\n'
                                      '<input type="text" name="cpf" />\n')
        _, d = rodar_json(self.raiz)
        campos = [a for a in d["achados"] if a["regra"] == "campo_formulario"]
        self.assertEqual(len(campos), 1)
        self.assertIn('name="cpf"', campos[0]["trecho_mascarado"])


class TestGitEPastas(Base):
    def test_git_na_raiz_e_info_e_em_pasta_servida_e_alta(self):
        escrever(self.raiz, ".git/HEAD", "ref: refs/heads/main\n")
        escrever(self.raiz, "public/.git/HEAD", "ref: refs/heads/main\n")
        _, d = rodar_json(self.raiz)
        sev = {a["arquivo"]: a["severidade_sugerida"] for a in achados(d, regra="git_presente")}
        self.assertEqual(sev[".git"], "info")
        self.assertEqual(sev["public/.git"], "alta")

    def test_imagens_em_public_baixa_e_documentos_alta(self):
        for i in range(5):
            escrever(self.raiz, "public/fotos/f%d.png" % i, "x")
            escrever(self.raiz, "public/pdf/d%d.pdf" % i, "x")
            escrever(self.raiz, "uploads/u%d.jpg" % i, "x")
        _, d = rodar_json(self.raiz)
        sev = {a["arquivo"]: a["severidade_sugerida"] for a in achados(d, categoria="pastas_documentos")}
        self.assertEqual(sev["public/fotos/"], "baixa")
        self.assertEqual(sev["public/pdf/"], "alta")
        self.assertEqual(sev["uploads/"], "alta")
        self.assertIn("público por desenho", achados(d, arquivo="public/fotos/")[0]["dica"])


class TestRastreadorDedupe(Base):
    def test_google_fonts_uma_linha_por_arquivo(self):
        escrever(self.raiz, "h.php", '<link rel="preconnect" href="https://fonts.googleapis.com">\n'
                                      '<link rel="preconnect" href="https://fonts.gstatic.com">\n'
                                      '<link href="https://fonts.googleapis.com/css2?family=A" rel="stylesheet">\n')
        _, d = rodar_json(self.raiz)
        self.assertEqual(len(achados(d, categoria="rastreadores_terceiros")), 1)


class TestEmpacotamentoSoSerio(Base):
    def test_credencial_de_teste_nao_entra_na_lista(self):
        escrever(self.raiz, ".vercelignore", "node_modules\n")
        escrever(self.raiz, "scripts/testar_a.mjs", "const SENHA = '%s';\n" % OUTRA_SENHA)
        _, d = rodar_json(self.raiz)
        for a in d["achados"]:
            if a["categoria"] == "empacotamento":
                self.assertNotIn("testar_a", a["trecho_mascarado"])
        self.assertEqual([a for a in d["achados"] if a["regra"] == "empacotamento_nao_exclui"], [])


if __name__ == "__main__":
    unittest.main()
