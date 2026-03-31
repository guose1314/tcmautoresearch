import unittest

from src.collector.literature_retriever import LiteratureRetriever


class TestLiteratureRetrieverPubmedHelpers(unittest.TestCase):
    def setUp(self):
        self.retriever = LiteratureRetriever({})

    def tearDown(self):
        self.retriever.close()

    def test_extract_pubmed_year_and_doi(self):
        item = {
            "pubdate": "2024 Aug",
            "articleids": [
                {"idtype": "pmid", "value": "123"},
                {"idtype": "doi", "value": "10.1000/test"},
            ],
        }
        self.assertEqual(self.retriever._extract_pubmed_year(item), 2024)
        self.assertEqual(self.retriever._extract_pubmed_doi(item), "10.1000/test")

    def test_build_single_pubmed_record_handles_empty_item(self):
        record = self.retriever._build_single_pubmed_record("123", {})
        self.assertIsNone(record)


if __name__ == "__main__":
    unittest.main()
