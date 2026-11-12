"""Refuse presentation substitutions that can misidentify published data."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from catalog_presentation import apply_presentation, apply_field_semantics


def save(root, path, value):
    data = (json.dumps(value, sort_keys=True) + '\n').encode()
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return {'path': path, 'sha256': hashlib.sha256(data).hexdigest()}


class CatalogPresentationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        tile = 'https://data.source.coop/nthh/example/example.pmtiles'
        data = {'href': 'https://data.source.coop/nthh/example/example.parquet', 'type': 'application/vnd.apache.parquet', 'roles': ['data'], 'file:checksum': '1220'+'a'*64, 'file:size': 42}
        before = {'href': 'style.json', 'type': 'application/vnd.mapbox.style+json', 'roles': ['style','default'], 'file:checksum':'1220'+'b'*64, 'file:size': 100}
        self.collection = {'assets': {'data':data,'tiles':{'href':tile,'type':'application/vnd.pmtiles','roles':['visual']},'style':before}, 'links':[{'rel':'style','href':'style.json'}]}
        self.record = {'id':'example','publication':{'release':'v1','catalog':{},'source_coop':{'owner':'nthh','product_id':'example'}}}
        style={'version':8,'sources':{'data':{'type':'vector','url':'pmtiles://'+tile}},'layers':[{'id':'background','type':'background','paint':{'background-color':'#fff'}},{'id':'a','source':'data','source-layer':'a','type':'line'}]}
        pin=save(self.root,'style-v2.json',style); size=(self.root/pin['path']).stat().st_size
        url='https://data.source.coop/nthh/example/style-v2.json'
        receipt=save(self.root,'receipt.json',{'status':'complete','objects':[{'status':'verified','url':url,'sha256':pin['sha256'],'size_bytes':size,'cors_passed':True}]})
        self.manifest={'schema_version':1,'dataset_id':'example','release':'v1','hosting':receipt,'assets':[{'asset_id':'style','before':copy.deepcopy(before),'filename':'style-v2.json','href':url,**pin,'size_bytes':size,'title':'A meaningful style','media_type':'application/vnd.mapbox.style+json'}]}
        self.bind()

    def bind(self):
        self.record['publication']['catalog']['presentation']=save(self.root,'manifest.json',self.manifest)

    def test_overlay_preserves_analytical_and_pmtiles_identity(self):
        original=copy.deepcopy(self.collection['assets'])
        tree={'example/style.json':b'old','example/README.md':b'doc'}
        apply_presentation(self.root,self.record,self.collection,tree)
        self.assertEqual(self.collection['assets']['data'],original['data'])
        self.assertEqual(self.collection['assets']['tiles'],original['tiles'])
        self.assertNotIn('example/style.json',tree)
        self.assertEqual(self.collection['links'][0]['href'],self.manifest['assets'][0]['href'])

    def test_cannot_replace_data_even_with_matching_before_identity(self):
        item=self.manifest['assets'][0];item['asset_id']='data';item['before']=copy.deepcopy(self.collection['assets']['data']);self.bind()
        with self.assertRaisesRegex(ValueError,'cannot replace'):
            apply_presentation(self.root,self.record,self.collection,{})

    def test_changed_input_style_requires_new_review(self):
        self.collection['assets']['style']['file:size']+=1
        with self.assertRaisesRegex(ValueError,'identity differs'):
            apply_presentation(self.root,self.record,self.collection,{})

    def test_missing_cors_proof_refused(self):
        receipt=json.loads((self.root/'receipt.json').read_text());receipt['objects'][0]['cors_passed']=False
        self.manifest['hosting']=save(self.root,'receipt.json',receipt);self.bind()
        with self.assertRaisesRegex(ValueError,'CORS verification'):
            apply_presentation(self.root,self.record,self.collection,{})

    def test_unbound_pmtiles_source_refused(self):
        path=self.root/'style-v2.json';s=json.loads(path.read_text());s['sources']['data']['url']='pmtiles://https://unrelated.example/file.pmtiles'
        pin=save(self.root,'style-v2.json',s);item=self.manifest['assets'][0];item.update(pin,size_bytes=path.stat().st_size)
        receipt=json.loads((self.root/'receipt.json').read_text());receipt['objects'][0].update(sha256=item['sha256'],size_bytes=item['size_bytes'])
        self.manifest['hosting']=save(self.root,'receipt.json',receipt);self.bind()
        with self.assertRaisesRegex(ValueError,'existing PMTiles'):
            apply_presentation(self.root,self.record,self.collection,{})

    def test_fields_cannot_attach_to_different_release(self):
        sem={'bound_assets':{'data':{'sha256':'f'*64}},'assets':{'data':{'fields':{'id':{'definition':'Producer identifier'}}}}}
        self.record['publication']['catalog']['field_semantics']=save(self.root,'fields.json',sem)
        self.collection['table:columns']=[{'asset':'data','name':'id','type':'int64'}]
        with self.assertRaisesRegex(ValueError,'binding differs'):
            apply_field_semantics(self.root,self.record,self.collection)

    def test_partial_field_definitions_refused(self):
        sem={'bound_assets':{'data':{'sha256':'a'*64}},'assets':{'data':{'fields':{}}}}
        self.record['publication']['catalog']['field_semantics']=save(self.root,'fields.json',sem)
        self.collection['table:columns']=[{'asset':'data','name':'id','type':'int64'}]
        with self.assertRaisesRegex(ValueError,'lacks definition'):
            apply_field_semantics(self.root,self.record,self.collection)


if __name__ == '__main__':
    unittest.main()
