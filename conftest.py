"""Root conftest.py — ensures pytest uses importlib for test discovery across workloads."""
import pytest

collect_ignore_glob = ["**/node_modules/**"]
