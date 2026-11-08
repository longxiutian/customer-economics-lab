"""No provider requests or scientific fits; Linux fixtures own only their children."""
import json
from contextlib import closing
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from hosting import cpu_pool as pool


def contract(analysis_workers=45):
    config = {"broker_url": "https://example.invalid", "worker_key": "fixture-only",
              "session_id": "session_12345", "store_id": "analysis_12345", "release_hash": "a"*64,
              "source_release_sha256": "b"*64, "runtime": "/hickory/fixture/store",
              "analysis_workers": analysis_workers}
    environment = {"STUDIO_NORTH_RELEASE_SHA256": "b"*64, "STUDIO_NORTH_PARENT_JOB_ID": "12345",
        "STUDIO_NORTH_JOB_RUNTIME": "/tmp/fixture-pool", "STUDIO_NORTH_JOB_END": "5000",
        "STUDIO_NORTH_ANALYSIS_CPUS": ",".join(map(str, range(analysis_workers))),
        "STUDIO_NORTH_HELPER_CPUS": ",".join(map(str, range(analysis_workers, analysis_workers+3)))}
    router = {"session_id": config["session_id"], "expires_at": 4000,
        "queue_path": "/tmp/fixture-pool/router.sqlite", "telemetry_path": "/tmp/fixture-pool/telemetry.sqlite",
        "client_progress_root": "/tmp/fixture-pool/progress", "status_path": "/tmp/fixture-pool/model-status.json",
        "minimum_ready_replicas": 4, "replicas": [{"capacity": 2} for _ in range(4)]}
    return config, environment, router


def plan_for(config=None, environment=None, router=None, **kwargs):
    a,b,c = contract()
    return pool.validate(a if config is None else config, b if environment is None else environment,
                         c if router is None else router, now=1000,
                         affinity=kwargs.get("affinity", set(range(48))),
                         topology=kwargs.get("topology", {i:(0,i) for i in range(48)}))


class PoolContractTests(unittest.TestCase):
    def test_twenty_four_core_default_and_explicit_legacy_layout(self):
        a,b,c=contract(21)
        for explicit in (True,False):
            cfg=dict(a)
            if not explicit:cfg.pop('analysis_workers')
            plan=plan_for(cfg,b,c,affinity=set(range(24)),topology={i:(0,i) for i in range(24)})
            self.assertEqual(plan.analysis_cpus,tuple(range(21)))
            self.assertEqual(plan.helper_cpus,(21,22,23))
            self.assertEqual(pool.worker_config(plan,'analysis',21)['worker_id'],'session_12345-analysis-021')
        # The previous 48-core deployment remains representable explicitly.
        self.assertEqual(len(plan_for().analysis_cpus),45)

    def test_reduced_layout_rejects_oversubscription_overlap_and_smt_aliases(self):
        a,b,c=contract(21)
        topology={i:(0,i) for i in range(24)}
        with self.assertRaises(ValueError):
            plan_for(dict(a,analysis_workers=22),b,c,affinity=set(range(24)),topology=topology)
        with self.assertRaises(ValueError):
            plan_for(a,b,c,affinity=set(range(23)),topology=topology)
        with self.assertRaises(ValueError):
            plan_for(a,dict(b,STUDIO_NORTH_HELPER_CPUS='0,22,23'),c,affinity=set(range(24)),topology=topology)
        topology[23]=topology[0]
        with self.assertRaises(ValueError):
            plan_for(a,b,c,affinity=set(range(24)),topology=topology)

    def test_deadline_is_shared_minimum(self):
        self.assertEqual(plan_for().deadline, 4000)
        a,b,c=contract();c['expires_at']=4971
        with self.assertRaises(ValueError):plan_for(a,b,c)
        c['expires_at']=4970
        self.assertEqual(plan_for(a,b,c).deadline,4970)
        for bad in ("nan", "inf", 900, 19121):
            a,b,c=contract(); b["STUDIO_NORTH_JOB_END"]=bad
            with self.subTest(bad=bad), self.assertRaises(ValueError):plan_for(a,b,c)

    def test_cpu_assignments_are_real_distinct_physical_cores(self):
        with self.assertRaises(ValueError):plan_for(affinity=set(range(47)))
        topology={i:(0,i) for i in range(48)};topology[47]=topology[0]
        with self.assertRaises(ValueError):plan_for(topology=topology)
        a,b,c=contract();b['STUDIO_NORTH_HELPER_CPUS']='0,46,47'
        with self.assertRaises(ValueError):plan_for(a,b,c)
        a,b,c=contract();b['STUDIO_NORTH_ANALYSIS_CPUS']='0,1,2'
        with self.assertRaises(ValueError):plan_for(a,b,c)

    def test_worker_count_bounds(self):
        for key,value in [('analysis_workers',46),('analysis_workers',0),('analysis_workers',True),('interactive_workers',9),('interactive_workers',True)]:
            a,b,c=contract();a[key]=value
            with self.subTest(key=key,value=value),self.assertRaises(ValueError):plan_for(a,b,c)

    def test_identity_and_router_paths_fail_closed(self):
        a,b,c=contract();b['LAB_SESSION_ID']='other_session'
        with self.assertRaises(ValueError):plan_for(a,b,c)
        a,b,c=contract();b['LAB_ANALYSIS_STORE_ID']='other_store'
        with self.assertRaises(ValueError):plan_for(a,b,c)
        a,b,c=contract();c['client_progress_root']='/tmp/other'
        with self.assertRaises(ValueError):plan_for(a,b,c)
        a,b,c=contract();c['minimum_ready_replicas']=1
        with self.assertRaises(ValueError):plan_for(a,b,c)
        a,b,c=contract();a['source_release_sha256']='c'*64
        with self.assertRaises(ValueError):plan_for(a,b,c)

    def test_worker_cannot_inherit_model_or_opus_credentials(self):
        raw={'STUDIO_NORTH_GPU1_TOKEN':'fixture','STUDIO_NORTH_GPU99_TOKEN':'fixture',
             'BLUECHIP_METERED_SERVICE_TOKEN':'fixture','STUDIO_NORTH_METERED_URL':'fixture',
             'PATH':'fixture-path','CUDA_VISIBLE_DEVICES':'0','OMP_NUM_THREADS':'45'}
        clean=pool.worker_environment(raw)
        self.assertFalse(any(k.endswith('_TOKEN') for k in clean))
        self.assertNotIn('STUDIO_NORTH_METERED_URL',clean)
        self.assertEqual(clean['PATH'],'fixture-path')
        self.assertEqual(clean['OMP_NUM_THREADS'],'1')
        self.assertEqual(clean['JAX_PLATFORMS'],'cpu')
        self.assertEqual(clean['CUDA_VISIBLE_DEVICES'],'-1')

    def test_worker_and_router_share_ipc_and_identity(self):
        plan=plan_for();cfg=pool.worker_config(plan,'analysis',1)
        self.assertEqual(cfg['worker_id'],'session_12345-analysis-001')
        self.assertEqual(cfg['progress_root'],str(plan.jobtmp/'progress'))
        self.assertEqual(cfg['model_status_path'],str(plan.jobtmp/'model-status.json'))
        self.assertEqual(cfg['telemetry']['session_id'],cfg['session_id'])
        self.assertEqual(cfg['expires_at'],4000)
        self.assertFalse(cfg['debrief_enabled'])

    def test_store_identity_is_exclusive_and_never_overwritten(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);pool.bind_store(root,'session_12345','analysis_12345')
            original=(root/'store.json').read_bytes()
            pool.bind_store(root,'session_12345','analysis_12345')
            with self.assertRaises(ValueError):pool.bind_store(root,'session_12345','different_store')
            self.assertEqual(original,(root/'store.json').read_bytes())
            with self.assertRaises(FileExistsError):pool.write_json(root/'store.json',{},exclusive=True)

    def test_backup_includes_committed_wal_without_copying_live_database(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);source=root/'source.sqlite';destination=root/'saved.sqlite'
            with closing(sqlite3.connect(source)) as db:
                db.execute('PRAGMA journal_mode=WAL')
                db.execute('CREATE TABLE evidence(value TEXT)');db.commit()
                db.execute('INSERT INTO evidence VALUES (?)',('committed-evidence',));db.commit()
                record=pool.backup_sqlite(source,destination)
                self.assertEqual(record['bytes'],destination.stat().st_size)
                with closing(sqlite3.connect(destination)) as archived:
                    self.assertEqual(archived.execute('SELECT value FROM evidence').fetchall(),[('committed-evidence',)])
                db.execute('INSERT INTO evidence VALUES (?)',('uncommitted',))
                pool.backup_sqlite(source,root/'second.sqlite')
                with closing(sqlite3.connect(root/'second.sqlite')) as archived:
                    self.assertEqual(archived.execute('SELECT count(*) FROM evidence').fetchone()[0],1)

    def test_backup_does_not_create_absent_source(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            self.assertIsNone(pool.backup_sqlite(root/'absent',root/'out'))
            self.assertFalse((root/'absent').exists())

    def test_model_readiness_requires_fresh_exact_capacity(self):
        plan=plan_for()
        with tempfile.TemporaryDirectory() as d:
            from dataclasses import replace
            plan=replace(plan,jobtmp=Path(d))
            value={'ready':True,'ready_replicas':4,'admission_capacity':8,'last_checked_at':999,'expires_at':4000}
            pool.write_json(Path(d)/'model-status.json',value)
            self.assertTrue(pool.model_ready(plan,1000))
            self.assertFalse(pool.model_ready(plan,1030))
            value['admission_capacity']=1;pool.write_json(Path(d)/'model-status.json',value)
            self.assertFalse(pool.model_ready(plan,1000))

    def test_local_filesystem_rejects_network_storage(self):
        with patch.object(pool.subprocess,'run',return_value=subprocess.CompletedProcess([],0,'nfs4\n','')):
            with self.assertRaises(ValueError):pool.check_local_runtime(Path('/tmp'))


@unittest.skipUnless(sys.platform=='linux','Requires Linux process ownership and affinity')
class LinuxOwnershipTests(unittest.TestCase):
    def test_failed_worker_degrades_without_killing_or_restarting_sibling(self):
        with tempfile.TemporaryDirectory() as d:
            script=r'''
import json,os,subprocess,sys,time
from pathlib import Path
from hosting.cpu_pool import ProcessOwner,worker_environment,worker_inventory,proc_snapshot
root=Path(sys.argv[1]);owner=ProcessOwner(root/'logs');owner.adopt_orphans()
core=min(os.sched_getaffinity(0));env=worker_environment(os.environ);marker=root/'orphan.json'
grandchild="import os,signal,time,json;from pathlib import Path;signal.signal(signal.SIGTERM,signal.SIG_IGN);Path("+repr(str(marker))+").write_text(json.dumps({'pid':os.getpid()}));time.sleep(120)"
bad_program="import subprocess,sys,time;subprocess.Popen([sys.executable,'-c',"+repr(grandchild)+"],start_new_session=True);time.sleep(.15);sys.exit(9)"
bad=owner.spawn([sys.executable,'-c',bad_program],name='bad',cpus=(core,),environment=env);bad['lane']='analysis'
good=owner.spawn([sys.executable,'-c','import time;time.sleep(120)'],name='good',cpus=(core,),environment=env);good['lane']='interactive'
try:
 bad['process'].wait(timeout=4)
 assert marker.exists()
 # The orphan was never observed while its original parent was alive.
 alive,health=worker_inventory(owner,[bad,good],root/'receipts',{'session_id':'fixture_session'})
 orphan=json.loads(marker.read_text())['pid'];snap=proc_snapshot()
 assert orphan not in snap or snap[orphan]['state']=='Z'
 assert good['process'].poll() is None and [r['name'] for r in alive]==['good']
 assert health['degraded'] and health['remaining_analysis_slots']==0 and health['remaining_interactive_slots']==1
 assert len(owner.children)==2 and bad['process'].returncode==9
 receipt=json.loads((root/'receipts/bad-exit.json').read_text())
 assert receipt['restarted'] is False and receipt['other_workers_stopped'] is False
 worker_inventory(owner,[bad,good],root/'receipts',{'session_id':'fixture_session'})
 assert len(owner.children)==2 and good['process'].poll() is None
 (root/'result.json').write_text(json.dumps({'passed':True,'health':health}))
finally:owner.stop(grace=.1)
'''
            done=subprocess.run([sys.executable,'-c',script,d],capture_output=True,text=True,timeout=12,cwd=pool.ROOT)
            self.assertEqual(done.returncode,0,done.stderr)
            self.assertTrue(json.loads((Path(d)/'result.json').read_text())['passed'])

    def test_detached_grandchildren_are_stopped_without_touching_bystander(self):
        # Run the subreaper in a separate fixture process, not the test runner.
        with tempfile.TemporaryDirectory() as d:
            result=Path(d)/'result.json'
            script=r'''
import json,os,signal,subprocess,sys,time
from pathlib import Path
from hosting.cpu_pool import ProcessOwner,worker_environment,proc_snapshot
root=Path(sys.argv[1]);owner=ProcessOwner(root/'logs');owner.adopt_orphans()
core=min(os.sched_getaffinity(0));marker=root/'grandchild.json'
grandchild="import os,signal,time,json;from pathlib import Path;signal.signal(signal.SIGTERM,signal.SIG_IGN);Path("+repr(str(marker))+").write_text(json.dumps({'pid':os.getpid(),'affinity':sorted(os.sched_getaffinity(0)),'token_present':'STUDIO_NORTH_GPU1_TOKEN' in os.environ}));time.sleep(120)"
parent="import subprocess,sys,time,signal;signal.signal(signal.SIGTERM,signal.SIG_IGN);subprocess.Popen([sys.executable,'-c',"+repr(grandchild)+"],start_new_session=True);time.sleep(120)"
env=worker_environment(dict(os.environ,STUDIO_NORTH_GPU1_TOKEN='fixture-only'))
record=owner.spawn([sys.executable,'-c',parent],name='slot',cpus=(core,),environment=env)
until=time.monotonic()+5
while not marker.exists() and time.monotonic()<until:time.sleep(.02)
assert marker.exists()
v=json.loads(marker.read_text());owner.observe();started=time.monotonic();owner.stop(grace=.15)
snap=proc_snapshot();v.update(stopped=v['pid'] not in snap or snap[v['pid']]['state']=='Z',parent_stopped=record['process'].poll() is not None,cleanup_seconds=time.monotonic()-started)
(root/'result.json').write_text(json.dumps(v))
'''
            bystander=subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)'],start_new_session=True)
            try:
                done=subprocess.run([sys.executable,'-c',script,d],capture_output=True,text=True,timeout=12,
                                    cwd=pool.ROOT)
                self.assertEqual(done.returncode,0,done.stderr)
                value=json.loads(result.read_text())
                self.assertTrue(value['stopped']);self.assertTrue(value['parent_stopped'])
                self.assertEqual(len(value['affinity']),1)
                self.assertFalse(value['token_present'])
                self.assertLess(value['cleanup_seconds'],4)
                self.assertIsNone(bystander.poll())
            finally:
                bystander.terminate();bystander.wait(timeout=3)


if __name__=='__main__':
    unittest.main()
