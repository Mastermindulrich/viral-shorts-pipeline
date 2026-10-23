import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
import pipeline as p
import preparation as prep

class SourceCatalogTests(unittest.TestCase):
    def test_numbers_persist_and_titles_display(self):
        with tempfile.TemporaryDirectory() as td, patch.object(p,'DATA',Path(td)):
            def add(key,title):
                folder=Path(td)/'imports'/key
                folder.mkdir(parents=True)
                source=folder/'source.mp4';source.touch()
                p.write(folder/'source.json',dict(input=str(source),title=title,source_url='https://example.com/'+key))
            add('first','First title')
            self.assertEqual(prep.source_catalog()[0]['label'],'Import 001 — First title')
            add('second','Second title')
            result=prep.source_catalog()
            self.assertEqual([x['number'] for x in result],[1,2])
            (Path(td)/'imports'/'first'/'source.mp4').unlink()
            add('third','Third title')
            result=prep.source_catalog()
            self.assertEqual([x['number'] for x in result],[2,3])
