"""CPU-only checks for failures that could silently break a transfer."""
import hashlib,importlib.util,json,os,subprocess,sys,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'migration/tools'))
import models
from configure_runtime import resolve_config

class MigrationTests(unittest.TestCase):
    def test_git_lfs_pointer_is_not_a_weight(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'weight.bin';p.write_bytes(b'version https://git-lfs.github.com/spec/v1\noid sha256:abcd\n')
            spec={'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
            self.assertIn('git_lfs_pointer',models.check(p,spec))
    def test_broken_link_is_not_a_weight(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'weight';p.symlink_to('missing_blob')
            self.assertEqual(models.check(p,{'bytes':5,'sha256':'0'*64}),['broken_symlink'])
    def test_missing_shard_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);p=root/'model.index.json';p.write_text(json.dumps({'weight_map':{'layer':'missing.safetensors'}}))
            self.assertTrue(models.verify_indices(root,[{'target':p.name}]))
    def test_path_escape_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):models.target(Path(d).resolve(),'../outside.bin')
    def test_relocation_resolves_all_active_paths(self):
        with tempfile.TemporaryDirectory(prefix='healthmon paths ') as d:
            root=Path(d);(root/'configs').mkdir();(root/'configs/runtime.json').write_bytes((ROOT/'configs/runtime.json').read_bytes())
            c=resolve_config(root,root/'new-envs',root/'blender')
            self.assertEqual(c['trellis_cache'],str(root/'models/trellis'))
            self.assertEqual(c['qwen_python'],str(root/'new-envs/qwen/bin/python'))
            self.assertNotIn('/workspace/',json.dumps(c));self.assertNotIn('${',json.dumps(c))
    def test_manual_config_never_overwritten(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'configs').mkdir();(root/'configs/runtime.json').write_bytes((ROOT/'configs/runtime.json').read_bytes())
            p=root/'configs/runtime.local.json';p.write_text('{"my_setting": 123}\n');before=p.read_bytes()
            r=subprocess.run([sys.executable,str(ROOT/'migration/tools/configure_runtime.py'),'--runtime-root',str(root),'--replace-generated'],capture_output=True)
            self.assertNotEqual(r.returncode,0);self.assertEqual(p.read_bytes(),before)
    def test_existing_runtime_loader_accepts_new_template(self):
        from unittest.mock import patch
        spec=importlib.util.spec_from_file_location('selected',ROOT/'scripts/run_selected_3d.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'configs').mkdir();(root/'configs/runtime.json').write_bytes((ROOT/'configs/runtime.json').read_bytes())
            with patch.object(module,'ROOT',root),patch.dict(os.environ,{'HEALTHMON_RUNTIME':str(root),'HEALTHMON_ENVS':str(root/'envs'),'HEALTHMON_BLENDER':'/usr/bin/blender','HEALTHMON_MATTING_CHECKPOINT':str(root/'models/matting/bria-rmbg.onnx')}):
                c=module.load_runtime(root/'configs/runtime.json')
                self.assertEqual(c['trellis_cache'],str(root/'models/trellis'));self.assertNotIn('${',json.dumps(c))
if __name__=='__main__':unittest.main()
