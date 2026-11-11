"""R3-A2R1 regression: all baseline helper imports resolve during preflight."""
import os, pathlib, subprocess, sys, tempfile, unittest

ROOT=pathlib.Path(__file__).resolve().parent

class PreflightImportFixTests(unittest.TestCase):
    def test_preflight_imports_resolve_with_scoped_local_pythonpath(self):
        env={**os.environ, 'PYTHONPATH':str(ROOT)+os.pathsep+str(ROOT/'accepted_loader')+os.pathsep+str(ROOT/'accepted_hybrid'), 'PYTHONDONTWRITEBYTECODE':'1'}
        p=subprocess.run([sys.executable,'-B','-c','import r3a_cases, r3a_eval, r3a_local_model, hybrid_core, semantic_ranker, r3a2_eval; print("R3A2_IMPORT_PATHS_VERIFIED")'],env=env,capture_output=True,text=True,timeout=20)
        self.assertEqual(p.returncode,0,p.stderr)
        self.assertIn('R3A2_IMPORT_PATHS_VERIFIED',p.stdout)
    def test_onepass_preflight_uses_same_scoped_path(self):
        s=(ROOT/'OnePass.sh').read_text('utf-8')
        self.assertIn('PYTHONPATH="$F:$F/accepted_loader:$F/accepted_hybrid" python3 -B "$F/preflight.py"',s)
        self.assertIn('R3A2_IMPORT_PATHS_VERIFIED',s)
    def test_preflight_reaches_sha_guard_instead_of_module_error(self):
        with tempfile.TemporaryDirectory() as d:
            db=pathlib.Path(d)/'fake.sqlite';db.write_bytes(b'not-the-owner-index')
            report=pathlib.Path(d)/'fake-report.json';report.write_text('{}')
            env={**os.environ,'PYTHONPATH':str(ROOT)+os.pathsep+str(ROOT/'accepted_loader')+os.pathsep+str(ROOT/'accepted_hybrid'), 'PYTHONDONTWRITEBYTECODE':'1'}
            p=subprocess.run([sys.executable,'-B',str(ROOT/'preflight.py'),'--index',str(db),'--owner-report',str(report)],env=env,capture_output=True,text=True,timeout=20)
            self.assertNotEqual(p.returncode,0)
            self.assertIn('HOLD_OWNER_INDEX_SHA_MISMATCH',p.stdout+p.stderr)
            self.assertNotIn('ModuleNotFoundError',p.stdout+p.stderr)

if __name__=='__main__':unittest.main()
