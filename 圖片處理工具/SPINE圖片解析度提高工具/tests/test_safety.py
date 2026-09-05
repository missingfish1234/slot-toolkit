"""No GPU or user assets: tiny temporary PNGs and decoder doubles."""
import importlib.util
import json
import sys
import tempfile
import threading
import types
import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image

ROOT = Path(__file__).resolve().parents[3]

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

up = load('upscale', Path(__file__).resolve().parents[1] / 'spine_alpha_upscale_tool.py')

class SafetyTests(unittest.TestCase):
    def test_source_and_work_guards(self):
        with tempfile.TemporaryDirectory() as temp:
            base=Path(temp); src=base/'src';src.mkdir();out=src/'output';work=src/'output_work'
            up.validate_paths(src,out,work)
            for bad_output,bad_work in [(src,work),(base,work),(out,src),(out,out),(out,out/'work')]:
                with self.assertRaises(ValueError): up.validate_paths(src,bad_output,bad_work)

    def test_owned_cleanup_preserves_other_files_and_resume_checks_inputs(self):
        with tempfile.TemporaryDirectory() as temp:
            base=Path(temp);work=base/'work';work.mkdir();sentinel=work/'user.txt';sentinel.write_text('keep')
            src=base/'a.png';Image.new('RGBA',(2,2),(80,100,120,128)).save(src)
            signature=up.input_signature([src],2,'model');task=up.create_work_directory(work,signature)
            self.assertEqual(up.create_work_directory(work,signature,True),task)
            changed=dict(signature,scale=4)
            with self.assertRaises(ValueError): up.create_work_directory(work,changed,True)
            with self.assertRaises(ValueError): up.cleanup_work_directory(work,base,signature)
            up.cleanup_work_directory(task,work,signature)
            self.assertEqual(sentinel.read_text(),'keep');self.assertFalse(task.exists())

    def test_collision_and_alpha_preservation(self):
        with tempfile.TemporaryDirectory() as temp:
            base=Path(temp);src=base/'a.png';raw=base/'raw';out=base/'out';raw.mkdir();out.mkdir()
            Image.new('RGBA',(2,2),(80,100,120,128)).save(src)
            Image.new('RGB',(4,4),(80,100,120)).save(raw/'a.png')
            original=out/'a.png';original.write_bytes(b'user data')
            rows=up.apply_alpha_and_validate([src],raw,out,2,{'a.png':None})
            self.assertEqual(original.read_bytes(),b'user data');self.assertEqual(rows[0]['output_file'],'a_2.png')
            self.assertTrue(rows[0]['alpha_matches_scaled_original'])
            self.assertTrue(up.apply_alpha_and_validate([src],raw,out,2,{},'skip')[0]['skipped'])
            up.write_report(rows,out/'report.csv');self.assertIn('output_file',(out/'report.csv').read_text(encoding='utf-8-sig'))

    def test_cancel_targets_windows_tree(self):
        proc=types.SimpleNamespace(pid=12345,poll=lambda:None)
        with patch.object(up.sys,'platform','win32'),patch.object(up.subprocess,'run') as run:
            up.terminate_process_tree(proc)
            self.assertEqual(run.call_args.args[0],['taskkill','/PID','12345','/T','/F'])

    def test_no_hardlink_filesystem_still_preserves_existing_output(self):
        with tempfile.TemporaryDirectory() as temp:
            original=Path(temp)/'a.png';original.write_bytes(b'keep')
            with patch.object(up.os,'link',side_effect=OSError('no hard links')):
                created=up.publish_png(Image.new('RGBA',(2,2)),original)
            self.assertEqual(original.read_bytes(),b'keep');self.assertEqual(created.name,'a_2.png')
            with Image.open(created) as image: self.assertEqual(image.size,(2,2))
            self.assertFalse(list(Path(temp).glob('*.tmp')))

    def test_last_frame_collision_and_cancel(self):
        class Cap:
            def isOpened(self):return True
            def get(self,key):return 3
            def set(self,*args):pass
            def read(self):return True,object()
            def release(self):pass
        cv=types.SimpleNamespace(VideoCapture=lambda p:Cap(),CAP_PROP_FRAME_COUNT=1,CAP_PROP_POS_FRAMES=2,COLOR_BGR2RGB=3,cvtColor=lambda *x:x[0])
        with patch.dict(sys.modules,{'cv2':cv}):
            last=load('last_frame',ROOT/'測試工具/影片處理工具/影片快速導出最後一張工具/影片快速導出最後一張工具/last_frame_exporter_auto.py')
        with tempfile.TemporaryDirectory() as temp,patch.object(last.Image,'fromarray',return_value=Image.new('RGB',(2,2))):
            first=last.extract_last_frame('demo.mp4',temp);second=last.extract_last_frame('demo.mov',temp)
            self.assertNotEqual(first,second);self.assertTrue(Path(first).exists());self.assertTrue(Path(second).exists())
            cancel=threading.Event();cancel.set()
            with self.assertRaises(InterruptedError):last.extract_last_frame('demo.webm',temp,cancel=cancel)
            self.assertEqual(len(list(Path(temp).glob('*.png'))),2)

if __name__ == '__main__': unittest.main()
