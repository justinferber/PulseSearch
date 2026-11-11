"""R3-A2R2: existing Python selection and genuine published cp313 wheel support."""
import os
import pathlib
import subprocess
import sys
import unittest
from unittest import mock
import provision
import select_python

ROOT=pathlib.Path(__file__).resolve().parent

class PythonCompatibilityTests(unittest.TestCase):
    def test_release_accepts_only_official_torch_26_linux_cp310_to_cp313(self):
        self.assertEqual(provision.SUPPORTED_PYTHON, {(3,10),(3,11),(3,12),(3,13)})
        self.assertNotIn((3,14), provision.SUPPORTED_PYTHON)
    def test_versions_match_selector(self):
        self.assertEqual(select_python.SUPPORTED, provision.SUPPORTED_PYTHON)
    def test_launcher_uses_selected_python_only_for_approved_provision(self):
        s=(ROOT/'OnePass.sh').read_text()
        self.assertIn('"$F/select_python.py"',s)
        self.assertIn('"$PYTHON_BIN" -B "$F/provision.py" --root "$PARENT"',s)
        self.assertNotIn('python3 -B "$F/provision.py"',s)
    def test_explicit_version_does_not_silently_fallback(self):
        with mock.patch.dict(os.environ, {'PULSE_R3A2_PYTHON':'/nonexistent/python'}, clear=False):
            with self.assertRaisesRegex(RuntimeError, 'HOLD_OWNER_SELECTED_PYTHON_NOT_USABLE'):
                select_python.select()
    def test_no_supported_python_holds_instead_of_installing(self):
        with mock.patch.dict(os.environ, {'PULSE_R3A2_PYTHON':''}, clear=False), \
             mock.patch.object(select_python, 'check',side_effect=ValueError('blocked')):
            with self.assertRaisesRegex(RuntimeError, 'HOLD_NO_PYTHON_310_TO_313'):
                select_python.select()
    def test_allowed_interpreter_resolves_actual_program_without_install(self):
        if sys.version_info[:2] not in provision.SUPPORTED_PYTHON:
            self.skipTest('Host Python outside allowed wheel tags')
        path,version=select_python.check(sys.executable)
        self.assertTrue(pathlib.Path(path).exists())
        self.assertEqual(version, f'{sys.version_info.major}.{sys.version_info.minor}')
    def test_provision_has_no_system_install(self):
        s=(ROOT/'provision.py').read_text()
        self.assertNotIn('apt-get',s)
        self.assertIn('REQUIREMENTS=',s)
        self.assertIn('HOLD_PYTHON_310_TO_313_REQUIRED_FOR_PINNED_CPU_WHEEL',s)
        self.assertIn('verify_upstream_wheel',s)
    def test_pins_and_model_safetensors_unchanged(self):
        self.assertEqual(provision.WEIGHTS_SHA,'3c9f31665447c8911517620762200d2245a2518d6e7208acc78cd9db317e21ad')
        self.assertEqual(provision.REQUIREMENTS, ('sentence-transformers==5.1.2','transformers==4.57.1','huggingface-hub==0.35.3','torch==2.6.0+cpu'))
        self.assertIn('model.safetensors',provision.FILES)

if __name__=='__main__': unittest.main()
