import sys
import unittest
from pathlib import Path

# Add project root to sys.path
PROJ_ROOT = Path(__file__).parent.parent
if str(PROJ_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJ_ROOT))

import ai_client # noqa: E402
import tts_generator # noqa: E402
import inspect # noqa: E402

class TestAIQueue(unittest.TestCase):
    """
    AI Radio Echo — AI Model Queue Contract Test.
    Locks the production and local reasoning tiers to prevent logic drift.
    """

    def test_ai_writer_models(self):
        """Verify the exact strings for AI Writing Model sets."""
        # Set A: Production Queue (High-Fidelity Reasoning)
        expected_a = [
            "gemini-3.5-flash",
            "gemini-3.1-flash-lite-preview",
            "gemini-2.5-flash-lite",
            "gemini-3-flash-preview",
            "meta-llama/llama-4-scout-17b-16e-instruct",
            "gemini-2.5-flash",
            "gemma-4-31b-it",
            "gemma-4-26b-a4b-it",
        ]
        self.assertEqual(ai_client.MODEL_SET_A, expected_a, "AI MODEL_SET_A has drifted!")

        # Set B: Local / Development Queue (Baseline Stability)
        # Should be exact reverse of Set A
        expected_b = expected_a[::-1]
        self.assertEqual(ai_client.MODEL_SET_B, expected_b, "AI MODEL_SET_B is not the reverse of Set A!")

    def test_audio_production_tier(self):
        """Verify production uses the free Edge TTS engine."""
        source = inspect.getsource(tts_generator.generate_segment_audio)
        
        self.assertIn("_run_edge_tts", source, "Production audio missing Edge TTS.")

    def test_audio_non_production_tier(self):
        """Verify that local/non-production runs use only edge-tts or silent fallback."""
        source = inspect.getsource(tts_generator.generate_segment_audio)
        
        # Ensure that if not use_cloud, we eventually call edge-tts or the fallback.
        self.assertIn("_run_edge_tts(text, voice, path)", source, "Local audio logic missing edge-tts call.")
        self.assertIn("_generate_ffmpeg_audio_fallback(text, path)", source, "Local audio logic missing silent fallback.")

if __name__ == "__main__":
    unittest.main()
