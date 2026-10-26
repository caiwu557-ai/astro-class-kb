import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('kb',Path(__file__).parent/'skills'/'astro-class-kb'/'scripts'/'kb.py')
kb=importlib.util.module_from_spec(spec);spec.loader.exec_module(kb)


class ReaderChecks(unittest.TestCase):
    def test_bilingual_query_and_pagination(self):
        records=[{'id':'a','title':'Urinary system.pdf','course':'组织学与胚胎学','trail':['泌尿系统'],'url':'https://example.org/a'},
                 {'id':'b:13','title':'Urinary system.pdf','course':'组织学与胚胎学','keywords':['filtration','podocyte'],'locator':{'pdf_page':13},'record_kind':'page-keywords','url':'https://example.org/b'}]
        with patch.object(kb,'records',return_value=iter(records)):
            result=kb.search('泌尿系统',limit=1)
            self.assertEqual(result['results'][0]['id'],'a')
        with patch.object(kb,'records',return_value=iter(records)):
            result=kb.search('podocyte filtration')
            self.assertEqual(result['results'][0]['locator']['pdf_page'],13)
            self.assertEqual(result['results'][0]['excerpt'],'')


if __name__=='__main__':unittest.main()
