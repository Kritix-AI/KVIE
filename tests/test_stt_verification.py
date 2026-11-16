"""
tests/test_stt_verification.py - Empirical verification and stress testing for STT & CUDA acceleration.

Verifies:
1. Linux and Windows NVIDIA library resolution in _register_nvidia_dlls()
2. Warmup inference execution (8000 samples @ 16kHz float32, generator draining, graceful fallback)
3. Device telemetry dictionary contract, schema, and PyTorch/NVML fallback behavior
4. Loaded device and compute type tracking
"""

import os
import sys
import ctypes
import unittest
from unittest.mock import MagicMock, patch
import concurrent.futures

import Backend.voice.STT as STT


class TestSTTVerification(unittest.TestCase):
    def setUp(self):
        # Reset STT module-level state before each test
        self.original_asr_model = STT._asr_model
        self.original_loaded_device = STT._loaded_device
        self.original_loaded_compute_type = STT._loaded_compute_type
        STT._asr_model = None
        STT._loaded_device = None
        STT._loaded_compute_type = None

    def tearDown(self):
        STT._asr_model = self.original_asr_model
        STT._loaded_device = self.original_loaded_device
        STT._loaded_compute_type = self.original_loaded_compute_type

    # ── 1. Library Resolution Tests ──────────────────────────────────────────

    def test_01_register_nvidia_dlls_windows(self):
        """Windows library resolution adds directories to DLL search path and os.environ['PATH']."""
        mock_add_dll = MagicMock()
        fake_sp = os.path.abspath("fake_site_win")
        nvidia_root = os.path.join(fake_sp, "nvidia")
        cublas_bin = os.path.join(nvidia_root, "cublas", "bin")

        with patch("sys.platform", "win32"), \
             patch("site.getsitepackages", return_value=[fake_sp]), \
             patch("site.getusersitepackages", return_value=""), \
             patch("os.path.isdir", side_effect=lambda p: p == nvidia_root), \
             patch("os.walk", return_value=[(cublas_bin, [], ["cublas64_12.dll", "readme.txt"])]), \
             patch("os.add_dll_directory", mock_add_dll, create=True):

            orig_path = os.environ.get("PATH", "")
            try:
                STT._register_nvidia_dlls()
                self.assertTrue(mock_add_dll.called)
                mock_add_dll.assert_called_with(cublas_bin)
                self.assertIn(cublas_bin, os.environ["PATH"])
            finally:
                os.environ["PATH"] = orig_path

    def test_02_register_nvidia_dlls_linux_so_scanning(self):
        """Linux resolution prepends LD_LIBRARY_PATH and preloads .so files with RTLD_GLOBAL."""
        mock_cdll = MagicMock()
        fake_sp = os.path.abspath("fake_site_linux")
        nvidia_root = os.path.join(fake_sp, "nvidia")
        cublas_lib = os.path.join(nvidia_root, "cublas", "lib")
        cudnn_lib = os.path.join(nvidia_root, "cudnn", "lib")

        mock_walk_results = [
            (cublas_lib, [], ["libcublas.so.12", "libcublasLt.so.12.1", "license.txt"]),
            (cudnn_lib, [], ["libcudnn.so", "libcudnn_cnn_infer.so.8.9.7", "notice.md"]),
        ]

        with patch("sys.platform", "linux"), \
             patch("site.getsitepackages", return_value=[fake_sp]), \
             patch("site.getusersitepackages", return_value=""), \
             patch("os.path.isdir", side_effect=lambda p: p == nvidia_root), \
             patch("os.walk", return_value=mock_walk_results), \
             patch.object(ctypes, "CDLL", mock_cdll):

            orig_ld = os.environ.get("LD_LIBRARY_PATH")
            try:
                os.environ["LD_LIBRARY_PATH"] = "/usr/local/lib"
                STT._register_nvidia_dlls()

                # Verify LD_LIBRARY_PATH prepending
                ld_path = os.environ.get("LD_LIBRARY_PATH", "")
                self.assertTrue(ld_path.startswith(cudnn_lib + os.pathsep + cublas_lib) or
                                ld_path.startswith(cublas_lib + os.pathsep + cudnn_lib) or
                                (cublas_lib in ld_path and cudnn_lib in ld_path))
                self.assertIn("/usr/local/lib", ld_path)

                # Verify ctypes.CDLL called for all .so files (4 total)
                self.assertEqual(mock_cdll.call_count, 4)
                loaded_paths = [call[0][0] for call in mock_cdll.call_args_list]
                self.assertTrue(any("libcublas.so.12" in p for p in loaded_paths))
                self.assertTrue(any("libcublasLt.so.12.1" in p for p in loaded_paths))
                self.assertTrue(any("libcudnn.so" in p for p in loaded_paths))
                self.assertTrue(any("libcudnn_cnn_infer.so.8.9.7" in p for p in loaded_paths))

                # Verify non-.so files were ignored
                self.assertFalse(any("license.txt" in p for p in loaded_paths))
                self.assertFalse(any("notice.md" in p for p in loaded_paths))

                # Verify RTLD_GLOBAL was passed if available
                rtld_global = getattr(ctypes, "RTLD_GLOBAL", 0)
                for call in mock_cdll.call_args_list:
                    self.assertEqual(call[1].get("mode"), rtld_global)
            finally:
                if orig_ld is not None:
                    os.environ["LD_LIBRARY_PATH"] = orig_ld
                else:
                    os.environ.pop("LD_LIBRARY_PATH", None)

    def test_03_register_nvidia_dlls_resilience(self):
        """_register_nvidia_dlls does not crash when CDLL fails or sitepackages throws."""
        with patch("sys.platform", "linux"), \
             patch("site.getsitepackages", side_effect=RuntimeError("Cannot read site-packages")), \
             patch("site.getusersitepackages", side_effect=Exception("User site error")):
            # Should gracefully pass without exception
            try:
                STT._register_nvidia_dlls()
            except Exception as e:
                self.fail(f"_register_nvidia_dlls raised unexpected exception: {e}")

        # When CDLL throws OSError on corrupt library
        fake_sp = os.path.abspath("fake_site_corrupt")
        nvidia_root = os.path.join(fake_sp, "nvidia")
        lib_dir = os.path.join(nvidia_root, "cublas", "lib")

        with patch("sys.platform", "linux"), \
             patch("site.getsitepackages", return_value=[fake_sp]), \
             patch("site.getusersitepackages", return_value=""), \
             patch("os.path.isdir", return_value=True), \
             patch("os.walk", return_value=[(lib_dir, [], ["corrupt.so"])]), \
             patch.object(ctypes, "CDLL", side_effect=OSError("invalid ELF header")):
            try:
                STT._register_nvidia_dlls()
            except Exception as e:
                self.fail(f"_register_nvidia_dlls failed to handle CDLL OSError: {e}")

    # ── 2. Warmup Tests ──────────────────────────────────────────────────────

    def test_04_warmup_missing_model_returns_false_safely(self):
        """warmup with nonexistent snapshot returns False without raising."""
        res = STT.warmup(model_name="nonexistent_snapshot_xyz_123")
        self.assertFalse(res)

    def test_05_warmup_default_uninstalled_returns_false_safely(self):
        """warmup without args on machine without local snapshot returns False safely."""
        with patch("Backend.voice.ModelManager.get_model_snapshot_path", return_value=None):
            res = STT.warmup()
            self.assertFalse(res)

    def test_06_warmup_inference_execution_and_generator_draining(self):
        """warmup executes 0.5s (8000 samples @ 16kHz float32) and drains generator."""
        mock_model = MagicMock()
        mock_segment = MagicMock(text="test")
        mock_generator = iter([mock_segment])
        mock_model.transcribe.return_value = (mock_generator, MagicMock())

        STT._asr_model = mock_model
        STT._loaded_device = "cuda"
        STT._loaded_compute_type = "float16"

        res = STT.warmup()
        self.assertTrue(res)
        self.assertTrue(mock_model.transcribe.called)

        # Inspect parameters passed to transcribe
        call_args, call_kwargs = mock_model.transcribe.call_args
        audio_buffer = call_args[0]

        # Verify 0.5s audio @ 16000Hz = exactly 8000 samples float32
        self.assertEqual(len(audio_buffer), 8000)
        self.assertEqual(audio_buffer.dtype.name, "float32")
        self.assertTrue((audio_buffer == 0).all())

        # Verify inference parameters
        self.assertEqual(call_kwargs.get("language"), "en")
        self.assertEqual(call_kwargs.get("beam_size"), 1)
        self.assertEqual(call_kwargs.get("vad_filter"), False)

    def test_07_warmup_transcribe_exception_graceful(self):
        """warmup catches inference exceptions (e.g. CUDA OOM or runtime failure) safely."""
        mock_model = MagicMock()
        mock_model.transcribe.side_effect = RuntimeError("CUDA driver error")
        STT._asr_model = mock_model

        res = STT.warmup()
        self.assertFalse(res)

    def test_08_warmup_empty_generator_graceful(self):
        """warmup drains empty generator safely without StopIteration exception."""
        mock_model = MagicMock()
        mock_model.transcribe.return_value = (iter([]), MagicMock())
        STT._asr_model = mock_model

        res = STT.warmup()
        self.assertTrue(res)

    def test_09_warmup_concurrent_execution(self):
        """Concurrent warmup calls are thread-safe and do not deadlock."""
        mock_model = MagicMock()
        mock_model.transcribe.return_value = (iter([MagicMock()]), MagicMock())
        STT._asr_model = mock_model

        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            futures = [executor.submit(STT.warmup) for _ in range(8)]
            results = [f.result() for f in futures]

        self.assertTrue(all(r is True for r in results))

    # ── 3. Device Telemetry Tests ─────────────────────────────────────────────

    def test_10_telemetry_schema_and_types_cpu(self):
        """Telemetry returns all required keys and correct CPU defaults."""
        with patch.object(STT, "_cuda_available", return_value=False):
            telem = STT.get_device_telemetry()

        expected_keys = {
            "gpu_name", "compute_type", "vram_allocated_mb",
            "vram_reserved_mb", "vram_total_mb", "vram_free_mb",
            "device", "gpu_available"
        }
        self.assertEqual(set(telem.keys()), expected_keys)
        self.assertEqual(telem["device"], "cpu")
        self.assertEqual(telem["gpu_available"], False)
        self.assertEqual(telem["compute_type"], "int8")
        self.assertIsNone(telem["gpu_name"])
        self.assertIsNone(telem["vram_allocated_mb"])
        self.assertIsNone(telem["vram_reserved_mb"])
        self.assertIsNone(telem["vram_total_mb"])
        self.assertIsNone(telem["vram_free_mb"])

    def test_11_telemetry_cuda_pytorch_metrics(self):
        """Telemetry correctly calculates and returns PyTorch CUDA VRAM statistics in MB."""
        with patch.object(STT, "_cuda_available", return_value=True), \
             patch("torch.cuda.is_available", return_value=True), \
             patch("torch.cuda.get_device_name", return_value="NVIDIA RTX 4090"), \
             patch("torch.cuda.memory_allocated", return_value=1024 * 1024 * 3000), \
             patch("torch.cuda.memory_reserved", return_value=1024 * 1024 * 4000), \
             patch("torch.cuda.mem_get_info", return_value=(1024 * 1024 * 20000, 1024 * 1024 * 24000)):

            STT._asr_model = MagicMock()
            STT._loaded_device = "cuda"
            STT._loaded_compute_type = "float16"

            telem = STT.get_device_telemetry()
            self.assertEqual(telem["device"], "cuda")
            self.assertEqual(telem["gpu_available"], True)
            self.assertEqual(telem["compute_type"], "float16")
            self.assertEqual(telem["gpu_name"], "NVIDIA RTX 4090")
            self.assertEqual(telem["vram_allocated_mb"], 3000)
            self.assertEqual(telem["vram_reserved_mb"], 4000)
            self.assertEqual(telem["vram_free_mb"], 20000)
            self.assertEqual(telem["vram_total_mb"], 24000)

    def test_12_telemetry_nvml_fallback(self):
        """Telemetry falls back to pynvml when PyTorch cannot provide total VRAM or GPU name."""
        mock_pynvml = MagicMock()
        mock_handle = MagicMock()
        mock_pynvml.nvmlDeviceGetHandleByIndex.return_value = mock_handle
        mock_pynvml.nvmlDeviceGetName.return_value = "NVIDIA A10G (NVML)"

        mock_mem = MagicMock()
        mock_mem.total = 1024 * 1024 * 24576
        mock_mem.free = 1024 * 1024 * 18432
        mock_mem.used = 1024 * 1024 * 6144
        mock_pynvml.nvmlDeviceGetMemoryInfo.return_value = mock_mem

        # Simulate PyTorch failing to return mem_get_info
        with patch.object(STT, "_cuda_available", return_value=True), \
             patch("torch.cuda.is_available", return_value=True), \
             patch("torch.cuda.get_device_name", side_effect=Exception("Driver mismatch")), \
             patch("torch.cuda.mem_get_info", side_effect=Exception("Not supported")), \
             patch.dict("sys.modules", {"pynvml": mock_pynvml}):

            STT._asr_model = MagicMock()
            STT._loaded_device = "cuda"
            STT._loaded_compute_type = "float16"

            telem = STT.get_device_telemetry()
            self.assertEqual(telem["device"], "cuda")
            self.assertEqual(telem["gpu_available"], True)
            self.assertEqual(telem["gpu_name"], "NVIDIA A10G (NVML)")
            self.assertEqual(telem["vram_total_mb"], 24576)
            self.assertEqual(telem["vram_free_mb"], 18432)
            self.assertEqual(telem["vram_allocated_mb"], 6144)
            self.assertTrue(mock_pynvml.nvmlInit.called)
            self.assertTrue(mock_pynvml.nvmlShutdown.called)

    def test_13_telemetry_loaded_model_tracking(self):
        """get_active_device and get_active_compute_type reflect active model state."""
        self.assertIsNone(STT.get_active_device())
        self.assertIsNone(STT.get_active_compute_type())

        STT._asr_model = MagicMock()
        STT._loaded_device = "cuda"
        STT._loaded_compute_type = "float16"

        self.assertEqual(STT.get_active_device(), "cuda")
        self.assertEqual(STT.get_active_compute_type(), "float16")

        STT._asr_model = None
        self.assertIsNone(STT.get_active_device())
        self.assertIsNone(STT.get_active_compute_type())


if __name__ == "__main__":
    unittest.main()
