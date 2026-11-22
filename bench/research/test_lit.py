"""Testes determinísticos do lit.py da skill research, sem rede.
Uso: py -I -m unittest discover -s bench/research -p "test_*.py" -v"""
import contextlib, importlib.util, io, json, os, pathlib, sys, tempfile, unittest
from unittest import mock

sys.dont_write_bytecode = True  # nada de __pycache__ dentro da pasta da skill

ROOT = pathlib.Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("lit", ROOT / "skills/research/lit.py")
lit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lit)

CORPUS = [
    {"id": "doi:10.5555/benford", "ids": ["doi:10.5555/benford", "s2:111"], "title": "Benford's law and COVID-19 death counts",
     "year": 2021, "authors": ["A. Autor"], "venue": "J Test", "abstract": "We test whether daily COVID-19 deaths follow Benford's law and find deviations consistent with under-reporting in some states.",
     "snippets": [{"text": "Conformity to Benford's law is not proof of accurate reporting, since epidemic curves span few orders of magnitude.", "section": "Discussion"}], "sources": ["teste"]},
    {"id": "doi:10.5555/outro", "ids": ["doi:10.5555/outro"], "title": "Hospital capacity planning",
     "year": 2019, "authors": ["B. Autor"], "venue": "", "abstract": "A queueing model for hospital beds.", "snippets": [], "sources": ["teste"]},
]


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self.corpus = self.tmp / "corpus.jsonl"
        self.corpus.write_text("".join(json.dumps(r) + "\n" for r in CORPUS), encoding="utf-8")
        self.reg = self.tmp / "papers.jsonl"
        self.env = {"LIT_CORPUS": str(self.corpus)}

    def run_lit(self, *argv):
        out = io.StringIO()
        old = dict(os.environ)
        os.environ.update(self.env)
        try:
            with contextlib.redirect_stdout(out):
                rc = lit.main(["--registry", str(self.reg), *argv])
        finally:
            os.environ.clear(); os.environ.update(old)
        return rc, out.getvalue()


class TestIds(unittest.TestCase):
    def test_formas_de_doi(self):
        for s in ["10.1093/PubMed/fdab161", "doi:10.1093/pubmed/fdab161", "https://doi.org/10.1093/pubmed/fdab161", "[doi:10.1093/pubmed/fdab161]"]:
            self.assertEqual(lit.norm_id(s), "doi:10.1093/pubmed/fdab161")

    def test_outros_ids(self):
        self.assertEqual(lit.norm_id("CorpusId:215416146"), "s2:215416146")
        self.assertEqual(lit.norm_id("https://openalex.org/w123"), "openalex:W123")
        self.assertEqual(lit.norm_id("PMID:34000000"), "pmid:34000000")

    def test_id_invalido(self):
        with self.assertRaises(lit.UsageError):
            lit.norm_id("Silva 2021")

    def test_faixa_de_ano(self):
        self.assertTrue(lit.year_ok(2021, "2020-"))
        self.assertFalse(lit.year_ok(2019, "2020-"))
        self.assertTrue(lit.year_ok(2019, "-2020"))
        self.assertFalse(lit.year_ok(2022, "2019-2021"))
        self.assertFalse(lit.year_ok(None, "2020-"))


class TestCorpus(Base):
    def test_search_ordena_e_registra(self):
        rc, out = self.run_lit("search", "Benford COVID deaths")
        self.assertEqual(rc, 0)
        self.assertTrue(out.startswith("[doi:10.5555/benford]"))
        self.assertNotIn("doi:10.5555/outro", out)
        self.assertIn("doi:10.5555/benford", self.reg.read_text(encoding="utf-8"))

    def test_get_inexistente_sai_com_2_e_nao_registra(self):
        rc, out = self.run_lit("get", "doi:10.9999/inventado")
        self.assertEqual(rc, 2)
        self.assertIn("não encontrado", out)
        self.assertFalse(self.reg.exists())

    def test_get_mostra_trechos(self):
        rc, out = self.run_lit("get", "s2:111")
        self.assertEqual(rc, 0)
        self.assertIn("trecho 1 (Discussion)", out)

    def test_snippets(self):
        rc, out = self.run_lit("snippets", "orders of magnitude epidemic", "--paper", "doi:10.5555/benford")
        self.assertEqual(rc, 0)
        self.assertIn("few orders of magnitude", out)


class TestVerify(Base):
    def verify(self, text):
        self.run_lit("get", "doi:10.5555/benford")
        rep = self.tmp / "rel.md"
        rep.write_text(text, encoding="utf-8")
        return self.run_lit("verify", str(rep))

    def test_trecho_literal_passa(self):
        rc, out = self.verify('| A1 | contestada | [doi:10.5555/benford] "Conformity to Benford’s law is not proof of accurate reporting" |\n')
        self.assertEqual(rc, 0, out)

    def test_reticencias_e_id_alternativo(self):
        rc, out = self.verify('- [s2:111] "We test whether daily COVID-19 deaths ... consistent with under-reporting"\n')
        self.assertEqual(rc, 0, out)

    def test_doi_inventado_falha(self):
        rc, out = self.verify('- [doi:10.9999/inventado] "Benford conformity proves there was no under-reporting in Brazil"\n')
        self.assertEqual(rc, 1)
        self.assertIn("fora do registro", out)

    def test_trecho_parafraseado_falha(self):
        rc, out = self.verify('- [doi:10.5555/benford] "Benford conformity proves that the reported death counts are accurate"\n')
        self.assertEqual(rc, 1)
        self.assertIn("não aparece", out)

    def test_trecho_de_outro_paper_falha(self):
        self.run_lit("get", "doi:10.5555/outro")
        rc, out = self.verify('- [doi:10.5555/outro] "Conformity to Benford\'s law is not proof of accurate reporting"\n')
        self.assertEqual(rc, 1)

    def test_sem_trecho_ou_curto_falha(self):
        rc, out = self.verify('- [doi:10.5555/benford] sustenta a ideia\n- [doi:10.5555/benford] "Benford\'s law"\n')
        self.assertEqual(rc, 1)
        self.assertIn("sem trecho", out)
        self.assertIn("curto demais", out)

    def test_duas_citacoes_na_mesma_linha(self):
        self.run_lit("get", "doi:10.5555/outro")
        rc, out = self.verify('[doi:10.5555/benford] "We test whether daily COVID-19 deaths follow Benford\'s law" e [doi:10.5555/outro] "A queueing model for hospital beds under epidemic demand"\n')
        self.assertEqual(rc, 1)  # o segundo trecho não está no resumo citado
        self.assertIn("FALHA linha 1 [doi:10.5555/outro]", out)
        self.assertIn("OK    linha 1 [doi:10.5555/benford]", out)

    def test_id_em_crase_nao_conta_como_evidencia(self):
        rc, out = self.verify('| `doi:10.9999/inventado` | não localizada |\n- [doi:10.5555/benford] "We test whether daily COVID-19 deaths follow Benford\'s law"\n')
        self.assertEqual(rc, 0, out)


ALPHA = {"id": "doi:10.5555/alpha", "ids": ["doi:10.5555/alpha", "pmid:100"], "title": "The treatment reduced",
         "year": 2020, "authors": [], "venue": "", "abstract": "mortality in adults. The treatment reduced mortality in adults by a third.", "snippets": [], "sources": ["teste"]}


class TestAchadosDaRevisao(Base):
    """Achados da revisão do Codex sobre o commit 7a0815d: cada um era um falso OK ou um erro mal classificado."""

    def write_reg(self, *recs):
        lit.Registry(self.reg).add(list(recs))

    def verify_text(self, text):
        rep = self.tmp / "rel.md"
        rep.write_text(text, encoding="utf-8")
        return self.run_lit("verify", str(rep))

    def test_1_id_com_espaco_nao_escapa(self):
        self.write_reg(ALPHA)
        rc, out = self.verify_text('[doi:10.5555/alpha] "The treatment reduced mortality in adults by a third"\n[doi: 10.9999/fake] "The treatment eradicated every known disease"\n')
        self.assertEqual(rc, 1, out)

    def test_1b_doi_solto_fora_do_formato_falha(self):
        self.write_reg(ALPHA)
        rc, out = self.verify_text('Segundo 10.9999/fake, "The treatment eradicated every known disease today"\n')
        self.assertEqual(rc, 1, out)

    def test_2_dois_dois_com_pmid_comum_nao_se_fundem(self):
        beta = {**json.loads(json.dumps(ALPHA)), "id": "doi:10.5555/beta", "ids": ["doi:10.5555/beta", "pmid:100"],
                "abstract": "The placebo improved survival in a completely unrelated pediatric trial with a long follow-up of many years"}
        self.write_reg(ALPHA, beta)
        rc, out = self.verify_text('[doi:10.5555/alpha] "The placebo improved survival in a completely unrelated pediatric trial"\n')
        self.assertEqual(rc, 1, out)

    def test_3_aspas_internas_falham(self):
        self.write_reg(ALPHA)
        rc, out = self.verify_text('[doi:10.5555/alpha] “The treatment reduced mortality in adults "despite the invented results" in both trials”\n')
        self.assertEqual(rc, 1, out)
        rc, out = self.verify_text('[doi:10.5555/alpha] "The treatment reduced mortality in adults "despite the invented results" in both trials"\n')
        self.assertEqual(rc, 1, out)

    def test_4_trecho_nao_e_reaproveitado(self):
        self.write_reg(ALPHA)
        rc, out = self.verify_text('[doi:10.5555/alpha] "The treatment reduced mortality in adults by a third"; [doi:10.5555/alpha] confirmed this result\n')
        self.assertEqual(rc, 1, out)

    def test_5_pontuacao_alterada_falha(self):
        self.write_reg(ALPHA)
        rc, out = self.verify_text('[doi:10.5555/alpha] "The treatment reduced mortality? In adults! by a third"\n')
        self.assertEqual(rc, 1, out)

    def test_6_trecho_nao_atravessa_campos(self):
        rec = {**json.loads(json.dumps(ALPHA)), "abstract": "mortality in adults was the primary outcome of this cohort."}
        self.write_reg(rec)
        rc, out = self.verify_text('[doi:10.5555/alpha] "The treatment reduced mortality in adults was the primary outcome"\n')
        self.assertEqual(rc, 1, out)

    def test_7_colchete_extra_no_id_falha(self):
        self.write_reg(ALPHA)
        rc, out = self.verify_text('[doi:10.5555/alpha[] "The treatment reduced mortality in adults by a third"\n')
        self.assertEqual(rc, 1, out)

    def test_8_fonte_com_erro_nao_vira_nao_encontrado(self):
        def fake(url, headers=None, s2=False):
            if "semanticscholar" in url:
                raise lit.ApiError("HTTP 503")
            raise lit.NotFound(url)
        with mock.patch.object(lit, "http_json", fake), mock.patch.dict(os.environ, {"S2_API_KEY": "x"}):
            with self.assertRaises(lit.ApiError):
                lit.online_get("doi:10.5555/alpha")

    def test_9_timeout_vira_erro_tratado(self):
        with mock.patch.object(lit.urllib.request, "urlopen", side_effect=TimeoutError("timed out")), mock.patch.object(lit.time, "sleep"):
            with self.assertRaises(lit.ApiError):
                lit.http_json("https://api.openalex.org/works")

    def test_10_faixa_de_ano_invalida(self):
        for bad in ["-", "20-21", "abc"]:
            with self.assertRaises(lit.UsageError):
                lit.parse_year(bad)
        self.assertEqual(lit.parse_year("2020-"), (2020, None))

    def test_retratado_nao_vale_como_evidencia(self):
        self.write_reg({**json.loads(json.dumps(ALPHA)), "retracted": True})
        rc, out = self.verify_text('[doi:10.5555/alpha] "The treatment reduced mortality in adults by a third"\n')
        self.assertEqual(rc, 1, out)
        self.assertIn("retratado", out)

    def test_trecho_correto_continua_passando(self):
        self.write_reg(ALPHA)
        rc, out = self.verify_text('| A1 | sustentada | [doi:10.5555/alpha] “The treatment reduced mortality in adults by a third.” |\n')
        self.assertEqual(rc, 0, out)


if __name__ == "__main__":
    unittest.main()
