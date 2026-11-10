# -*- coding: utf-8 -*-
"""Rodada 4: pasta de documentos em que PDFs/imagens são minoria (documentação do projeto)."""
import unittest

from test_varredura_rodada2 import Base, escrever, rodar_json


def pasta(d, caminho):
    return [a for a in d["achados"] if a["regra"] == "pasta_de_documentos" and a["arquivo"] == caminho]


class TestPastaDocumentosMinoria(Base):
    def test_docs_majoritariamente_texto_vira_media(self):
        for i in range(5):
            escrever(self.raiz, "docs/anexo%d.pdf" % i, "%PDF-1.4 sintetico\n")
        for i in range(30):
            escrever(self.raiz, "docs/capitulo%d.md" % i, "# Capitulo %d\nTexto.\n" % i)
        _, d = rodar_json(self.raiz)
        a = pasta(d, "docs/")
        self.assertEqual(len(a), 1)
        self.assertEqual(a[0]["severidade_sugerida"], "média")
        self.assertIn("minoria", a[0]["dica"])

    def test_tmp_majoritariamente_documentos_continua_alta(self):
        for i in range(8):
            escrever(self.raiz, "tmp/pagina%d.jpg" % i, "x")
        escrever(self.raiz, "tmp/ocr.py", "print('ok')\n")
        _, d = rodar_json(self.raiz)
        a = pasta(d, "tmp/")
        self.assertEqual(len(a), 1)
        self.assertEqual(a[0]["severidade_sugerida"], "alta")


if __name__ == "__main__":
    unittest.main()
