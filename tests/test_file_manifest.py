import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from hosting.file_manifest import build_manifest, sha


class FileManifestTests(unittest.TestCase):
    def test_worker_observation_requires_operator_opt_in(self):
        from hosting.bluechip_worker import observe_files
        class Broker:
            config={'runtime':'/fixture/runtime','session_id':'session01','store_id':'store001','lane':'analysis'}
            calls=[]
            def request(self,*a,**kw):self.calls.append((a,kw));return {'ok':True,'applied':True}
        broker=Broker();job={'run_id':'10000000-0000-4000-8000-000000000001'}
        with patch('hosting.file_manifest.build_manifest',return_value={'fixture':True}) as build:
            observe_files(broker,job);build.assert_not_called()
            broker.config['file_map_paths_disclosable']=True
            observe_files(broker,job)
            self.assertTrue(build.call_args.kwargs['paths_disclosable'])
            self.assertEqual(broker.calls[0][0][0],'/api/worker/manifest')
            broker.config['lane']='debrief';observe_files(broker,job)
            self.assertEqual(build.call_count,1)

    def test_readonly_allowlist_and_database_observation(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root/'source'; source.mkdir()
            workspace = root/'workspaces/10000000-0000-4000-8000-000000000001'
            workspace.mkdir(parents=True)
            (source/'analysis.py').write_text('pinned source')
            (source/'secret.env').write_text('not publishable')
            (workspace/'lesson').mkdir()
            (workspace/'lesson/table.csv').write_text('a,b\n1,2\n')
            release = {'inputs':{'hashes':{}},'implementation':{'analysis.py':sha(source/'analysis.py')}}
            release['release_hash'] = hashlib.sha256(json.dumps(release,sort_keys=True,separators=(',', ':')).encode()).hexdigest()
            (workspace/'release.json').write_text(json.dumps(release))
            catalog = root/'catalog.json'
            catalog.write_text(json.dumps({'releases':[release['release_hash']],'groups':[
                {'root':'source','rels':['analysis.py']},{'root':'workspace','rels':['lesson/table.csv']}]}))
            args = dict(session_id='session01',store_id='store001',catalog_path=catalog,paths_disclosable=True)
            before = {str(p):(p.stat().st_mtime_ns,sha(p)) for p in root.rglob('*') if p.is_file()}
            m = build_manifest(source,workspace,**args)
            after = {str(p):(p.stat().st_mtime_ns,sha(p)) for p in root.rglob('*') if p.is_file()}
            self.assertEqual(before,after)
            self.assertEqual([e['rel'] for e in m['entries']],['analysis.py','lesson/table.csv'])
            self.assertEqual(m['duckdb_scan'],{'found':0,'complete':True})
            (workspace/'unexpected.duckdb').write_bytes(b'db')
            self.assertEqual(build_manifest(source,workspace,**args)['duckdb_scan']['found'],1)
            (source/'analysis.py').write_text('changed')
            with self.assertRaisesRegex(ValueError,'hash mismatch'):
                build_manifest(source,workspace,**args)

    def test_symlink_escape(self):
        from hosting.file_manifest import safe_file
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);allowed=root/'allowed';allowed.mkdir();outside=root/'outside';outside.write_text('secret')
            try:(allowed/'link').symlink_to(outside)
            except OSError:self.skipTest('Host does not permit test symlinks')
            self.assertFalse(safe_file(allowed,allowed/'link'))


if __name__ == '__main__':
    unittest.main()
