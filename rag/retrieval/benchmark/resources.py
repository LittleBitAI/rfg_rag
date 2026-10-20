"""다른 프로세스를 조작하지 않고 프로세스·CUDA 최대 메모리를 측정한다."""
import platform
import shutil
import subprocess
import threading
import time
from importlib.metadata import version

import psutil
import torch

from .common import OUT


def machine():
    free, total = torch.cuda.mem_get_info()
    disk = shutil.disk_usage(OUT)
    return {"platform": platform.platform(), "python": platform.python_version(), "cpu": platform.processor(),
            "gpu": torch.cuda.get_device_name(), "gpu_total_bytes": total, "gpu_free_bytes": free,
            "disk_free_bytes": disk.free, "host_total_bytes": psutil.virtual_memory().total,
            "host_available_bytes": psutil.virtual_memory().available,
            "nvidia_smi": subprocess.check_output(["nvidia-smi", "--query-gpu=name,driver_version,memory.total,memory.used,memory.free",
                                                    "--format=csv"], text=True).strip(),
            "versions": {p: version(p) for p in ["torch", "transformers", "sentence-transformers", "numpy",
                                                "faiss-cpu", "rank-bm25", "kiwipiepy", "psutil", "huggingface-hub"]}}


class ResourceMonitor:
    def __init__(self):
        self.process = psutil.Process()
        self.peak_rss = 0
        self.peak_device = 0
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self.sample, daemon=True)

    def sample(self):
        while not self.stop.is_set():
            self.peak_rss = max(self.peak_rss, self.process.memory_info().rss)
            free, total = torch.cuda.mem_get_info()
            self.peak_device = max(self.peak_device, total - free)
            self.stop.wait(0.2)

    def __enter__(self):
        torch.cuda.reset_peak_memory_stats()
        self.start = time.perf_counter()
        self.thread.start()
        return self

    def __exit__(self, *args):
        torch.cuda.synchronize()
        self.seconds = time.perf_counter() - self.start
        self.stop.set()
        self.thread.join()

    def result(self):
        return {"seconds": self.seconds, "peak_process_rss_bytes_sampled": self.peak_rss,
                "peak_cuda_allocated_bytes": torch.cuda.max_memory_allocated(),
                "peak_cuda_reserved_bytes": torch.cuda.max_memory_reserved(),
                "peak_device_used_bytes_sampled_includes_other_processes": self.peak_device,
                "sampling_interval_seconds": 0.2}
