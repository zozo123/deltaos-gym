import os
import sys
import unittest

from instrumentation.proc_lens import observe

LINUX = sys.platform.startswith("linux")


@unittest.skipUnless(LINUX, "proc_lens reads /proc")
class ProcLensTests(unittest.TestCase):
    def test_self(self):
        obs = observe(os.getpid())
        self.assertEqual(obs["pid"], os.getpid())
        self.assertGreaterEqual(obs["open_fd_count"], 3)
        self.assertEqual(obs["assurance"], "best_effort_procfs_snapshot_not_complete_event_trace")

    def test_cloexec_flag_is_reported(self):
        r, w = os.pipe()
        os.set_inheritable(w, True)
        try:
            fds = {f["fd"]: f for f in observe(os.getpid())["fds"]}
            self.assertTrue(fds[r]["cloexec"])
            self.assertFalse(fds[w]["cloexec"])
        finally:
            os.close(r)
            os.close(w)

    def test_children_are_listed(self):
        pid = os.fork()
        if pid == 0:
            os.read(os.open("/dev/zero", os.O_RDONLY), 1)
            os._exit(0)
        try:
            self.assertIn(pid, observe(os.getpid())["children"])
        finally:
            os.waitpid(pid, 0)

    def test_nonexistent(self):
        obs = observe(2147483640)
        self.assertEqual(obs["open_fd_count"], 0)
        self.assertIsNone(obs["status"])
        self.assertGreaterEqual(len(obs["capture_errors"]), 1)


if __name__ == "__main__":
    unittest.main()
