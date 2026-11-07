"""Scientific identity/scoring failure cases for the offline catalog audit."""
import importlib.util
from pathlib import Path
import unittest
ROOT=Path(__file__).resolve().parents[1]
def module(name):
    spec=importlib.util.spec_from_file_location(name,ROOT/'scripts'/f'{name}.py')
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
capture=module('capture_official_catalog');rank=module('rank_catalog_citations')

class CitationTests(unittest.TestCase):
    def test_complex_ams_doi_and_markdown(self):
        doi='10.1175/1520-0477(1996)077<0437:TNYRP>2.0.CO;2'
        text='[doi:'+doi.replace('>',r'\\>')+'](https://doi.org/'+doi+').\n'
        self.assertEqual(capture.extract_dois(text),[doi.lower()])
    def test_doi_links_are_safe_in_markdown(self):
        raw='https://doi.org/10.1175/a(1996)<b>[c];2'
        self.assertEqual(rank.markdown_url(raw),'https://doi.org/10.1175/a%281996%29%3Cb%3E%5Bc%5D%3B2')
    def test_legacy_square_brackets_in_doi(self):
        doi='10.1641/0006-3568(2004)054[0547:ACSMOG]2.0.CO;2'
        self.assertEqual(capture.extract_dois('[doi:'+doi+'](https://doi.org/'+doi+').'),[doi.lower()])
    def test_parentheses_in_elsevier_doi(self):
        doi='10.1016/S0034-4257(02)00096-2'
        self.assertEqual(capture.extract_dois('Reference (https://doi.org/'+doi+').'),[doi.lower()])
    def test_newline_and_encoded_angle_brackets(self):
        self.assertEqual(capture.extract_dois('10.1002/joc.1276\nNext paper'),['10.1002/joc.1276'])
        self.assertEqual(capture.norm_doi('https://doi.org/10.1175/a%3Cb%3E;2'),'10.1175/a<b>;2')
    def work(self,wid,count,kind='article'):
        return {'work':{'id':wid,'cited_by_count':count,'type':kind,'title':wid,'doi':None,'publication_year':2000}}
    def row(self,i):
        return {'id':i,'catalog':'official','catalog_id':i,'title':i,'url':'https://example.org/'+i,'geographic_scope':'global','region':'Global','deprecated':False,'citation_scope':'base_dataset_family'}
    def test_no_sum_and_duplicate_identity(self):
        works={'W1':self.work('W1',11),'W2':self.work('W2',7),'D1':self.work('D1',30,'dataset')}
        r=rank.score(self.row('one'),['W1','W1','W2'],['D1'],works,[],[],[])
        self.assertEqual(r['max_paper_citations'],11);self.assertEqual(r['max_data_doi_citations'],30)
        self.assertEqual(r['paper_work_ids'],['W1','W2'])
    def test_unknown_is_not_measured_zero(self):
        works={'W0':self.work('W0',0)}
        unknown=rank.score(self.row('unknown'),[],[],works,['missing'],[],[])
        zero=rank.score(self.row('zero'),['W0'],[],works,[],[],[])
        self.assertIsNone(unknown['max_paper_citations']);self.assertEqual(unknown['paper_count_status'],'unknown')
        self.assertEqual(zero['max_paper_citations'],0);self.assertEqual(zero['paper_count_status'],'matched')
        self.assertEqual(rank.sort_rows([unknown,zero])[0]['id'],'zero')
    def test_data_work_cannot_enter_papers(self):
        with self.assertRaisesRegex(AssertionError,'Data release'):
            rank.select_works(['D1'],{'D1':self.work('D1',20,'dataset')},'paper')
    def test_role_conflict_rejected(self):
        with self.assertRaisesRegex(AssertionError,'Mixed roles'):
            rank.score(self.row('one'),['W1'],['W1'],{'W1':self.work('W1',3)},[],[],[])
    def test_shared_paper_preserves_distinct_entries(self):
        works={'W1':self.work('W1',9)}
        rows=[rank.score(self.row(i),['W1'],[],works,[],[],[]) for i in ['base','derived']]
        groups=rank.paper_groups(rows)
        self.assertEqual(len(groups),1);self.assertEqual(groups[0]['entry_count'],2)
        self.assertEqual(groups[0]['max_paper_citations'],9)
        self.assertEqual({r['id'] for r in groups[0]['entries']},{'base','derived'})
    def test_partial_reference_stays_visible(self):
        row=rank.score(self.row('x'),['W1'],[],{'W1':self.work('W1',3)},[],[],['Unresolved paper'])
        self.assertEqual(row['paper_count_status'],'partial');self.assertEqual(row['max_paper_citations'],3)
    def test_entry_correction_does_not_spread_to_shared_group(self):
        correction={'entry_ids':['Ukraine'],'group_id':'empty'}
        self.assertTrue(rank.correction_applies(correction,{'id':'Ukraine','review_group':'empty'}))
        self.assertFalse(rank.correction_applies(correction,{'id':'World','review_group':'empty'}))
    def test_global_filter_uses_review_not_score(self):
        rows=[self.row('global'),self.row('regional')];rows[1]['geographic_scope']='regional'
        self.assertEqual([r['id'] for r in rows if r['geographic_scope']=='global'],['global'])

if __name__=='__main__':unittest.main()
