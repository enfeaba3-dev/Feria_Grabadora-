import tempfile
import unittest
import wave
from io import BytesIO
from pathlib import Path

from audio_pipeline import pcm16_to_wav_bytes
from config_manager import DEFAULT_CONFIG,load_config,save_config,validate_config,validate_hotkey
from logging_setup import tail_log
from text_utils import merge_transcript


class ConfigTests(unittest.TestCase):
    def test_default_model(self):
        config,warnings=validate_config({})
        self.assertEqual(config['model'],'large-v3-turbo')
        self.assertIsInstance(warnings,list)

    def test_invalid_values_are_repaired(self):
        config,warnings=validate_config({'model':'fake','language':'espanol','device':'quantum','dictation':{'hotkey':'h'}})
        self.assertEqual(config['model'],'large-v3-turbo')
        self.assertEqual(config['language'],'')
        self.assertEqual(config['device'],'auto')
        self.assertEqual(config['dictation']['hotkey'],'f8')
        self.assertGreaterEqual(len(warnings),3)

    def test_safe_hotkeys(self):
        self.assertTrue(validate_hotkey('f8')[0])
        self.assertTrue(validate_hotkey('ctrl+alt+f10')[0])
        self.assertTrue(validate_hotkey('right ctrl')[0])
        self.assertFalse(validate_hotkey('h')[0])
        self.assertFalse(validate_hotkey('ctrl+h')[0])

    def test_atomic_config_roundtrip(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'config.json'
            saved,_=save_config({'model':'small','dictation':{'hotkey':'f9'}},path)
            loaded=load_config(path)
            self.assertEqual(saved,loaded)
            self.assertEqual(loaded['model'],'small')
            self.assertEqual(loaded['dictation']['hotkey'],'f9')


class AudioTests(unittest.TestCase):
    def test_pcm_to_wav(self):
        payload=pcm16_to_wav_bytes(b'\x00\x00'*1600)
        with wave.open(BytesIO(payload),'rb') as handle:
            self.assertEqual(handle.getnchannels(),1)
            self.assertEqual(handle.getsampwidth(),2)
            self.assertEqual(handle.getframerate(),16000)
            self.assertEqual(handle.getnframes(),1600)


class TextMergeTests(unittest.TestCase):
    def test_overlap_is_removed(self):
        merged,overlap=merge_transcript('Hola mundo, esto es una prueba','esto es una prueba para Chrome')
        self.assertEqual(merged,'Hola mundo, esto es una prueba para Chrome')
        self.assertEqual(overlap,4)

    def test_punctuation_does_not_break_overlap(self):
        merged,overlap=merge_transcript('Buenos días, Enrique.','Enrique, vamos a probar')
        self.assertEqual(merged,'Buenos días, Enrique. vamos a probar')
        self.assertEqual(overlap,1)


class LogTests(unittest.TestCase):
    def test_tail_log(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'test.log'
            path.write_text('\n'.join(str(i) for i in range(20)),encoding='utf-8')
            self.assertEqual(tail_log(path,3),['17','18','19'])


if __name__=='__main__':
    unittest.main()
