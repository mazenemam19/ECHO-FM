#!/usr/bin/env python3
"""Verifies the free Edge TTS generation path."""

import sys
import unittest
import tempfile
import shutil
import os
from unittest.mock import AsyncMock, call, patch
from pathlib import Path

# ── Import Fix ────────────────────────────────────────────────────────────────
PROJ_ROOT = Path(__file__).parent.parent
if str(PROJ_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJ_ROOT))

import tts_generator # noqa: E402

class TestTTSPriority(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.output_path = os.path.join(self.test_dir, "path.wav")

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    @patch("tts_generator.time.sleep")
    @patch("tts_generator._edge_tts_async", new_callable=AsyncMock)
    def test_edge_tts_retries_transient_failures(self, mock_async, mock_sleep):
        """Should retry Edge TTS with backoff before succeeding."""
        mock_async.side_effect = [(False, "TimeoutError"), (False, "TimeoutError"), (True, "")]

        self.assertTrue(tts_generator._run_edge_tts("Test", "ALISTAIR", self.output_path))
        self.assertEqual(mock_async.await_count, 3)
        mock_sleep.assert_has_calls([call(2), call(4)])

    @patch("tts_generator.time.sleep")
    @patch("tts_generator._edge_tts_async", new_callable=AsyncMock)
    def test_edge_tts_fast_fails_on_permanent_errors(self, mock_async, mock_sleep):
        """Should not retry permanent Edge TTS failures."""
        mock_async.return_value = (False, "Invalid voice name")

        self.assertFalse(tts_generator._run_edge_tts("Test", "ALISTAIR", self.output_path))
        self.assertEqual(mock_async.await_count, 1)
        mock_sleep.assert_not_called()

    @patch("tts_generator._run_edge_tts")
    @patch("tts_generator._is_audio_valid")
    @patch("tts_generator._apply_audio_processing")
    def test_edge_tts_success(self, mock_apply, mock_valid, mock_edge):
        """Should use Edge TTS when it succeeds."""
        mock_valid.return_value = True
        mock_apply.return_value = True
        mock_edge.return_value = True
        
        success, engine = tts_generator.generate_segment_audio("Test", "ALISTAIR", self.output_path, use_cloud=True)
        
        self.assertTrue(success)
        self.assertEqual(engine, "edge-tts")
        mock_edge.assert_called_once()

    @patch("tts_generator._run_edge_tts")
    @patch("tts_generator._is_audio_valid")
    @patch("tts_generator._apply_audio_processing")
    def test_edge_tts_failure_uses_existing_explicit_fallback(self, mock_apply, mock_valid, mock_edge):
        """Should use the existing explicit silent fallback if Edge TTS fails."""
        mock_edge.return_value = False
        mock_valid.return_value = True
        mock_apply.return_value = True
        
        with patch("tts_generator._generate_ffmpeg_audio_fallback", return_value=True):
            success, engine = tts_generator.generate_segment_audio("Test", "ALISTAIR", self.output_path, use_cloud=True)
        
        self.assertTrue(success)
        self.assertEqual(engine, "silent-fallback")
        mock_edge.assert_called_once()

    @patch("tts_generator._run_edge_tts")
    @patch("tts_generator._is_audio_valid")
    @patch("tts_generator._apply_audio_processing")
    def test_quality_failure_uses_explicit_fallback(self, mock_apply, mock_valid, mock_edge):
        """Should use the explicit fallback if Edge TTS output is invalid."""
        mock_edge.return_value = True
        mock_valid.return_value = False
        mock_apply.return_value = True
        
        with patch("tts_generator._generate_ffmpeg_audio_fallback", return_value=True):
            success, engine = tts_generator.generate_segment_audio("Test words", "ALISTAIR", self.output_path, use_cloud=True)
        
        self.assertTrue(success)
        self.assertEqual(engine, "silent-fallback")
        mock_edge.assert_called_once()

if __name__ == "__main__":
    unittest.main()
