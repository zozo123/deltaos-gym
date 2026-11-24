#!/usr/bin/env python3
"""Crash-cut model checker for a restricted VFS syscall interface.

This models durability transitions. It is not proof of physical-disk behavior
or complete Linux VFS semantics. The candidate is compiled and executed in a
child process for local reliability, not in a security-grade microVM.
"""
import ctypes
import errno
import json
import os
import pathlib
import random
import subprocess
import sys

WORKSPACE = pathlib.Path(os.environ.get('DELTAOS_WORKSPACE', '/workspace'))
TESTS = pathlib.Path(os.environ.get('DELTAOS_TESTS', '/tests'))
LOGS = pathlib.Path(os.environ.get('DELTAOS_LOGS', '/logs/verifier'))
LOGS.mkdir(parents=True, exist_ok=True)
SO = pathlib.Path(os.environ.get('DELTAOS_VFS_SO', '/tmp/deltaos-publisher.so'))

CREATE = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_void_p)
WRITE = ctypes.CFUNCTYPE(ctypes.c_long, ctypes.c_void_p,
                        ctypes.POINTER(ctypes.c_ubyte), ctypes.c_size_t)
SIMPLE = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_void_p)

class Ops(ctypes.Structure):
    _fields_ = [
        ('ctx', ctypes.c_void_p),
        ('create_temp', CREATE), ('write_temp', WRITE),
        ('fsync_temp', SIMPLE), ('rename_temp', SIMPLE),
        ('fsync_directory', SIMPLE), ('close_temp', SIMPLE),
        ('remove_temp', SIMPLE),
    ]

class KernelModel:
    def __init__(self, scenario):
        self.sc = scenario
        self.old = bytes.fromhex(scenario['old'])
        self.new = bytes.fromhex(scenario['new'])
        self.volatile = bytearray()
        self.durable_temp = None
        self.exists = False
        self.renamed = False
        self.dir_synced = False
        self.closed = False
        self.call = 0
        self.eintr_done = False
        self.fault_triggered = False
        self.snapshots = []
        self.operations = []
        self._checkpoint('initial')
        self.callbacks = [
            CREATE(self.create), WRITE(self.write), SIMPLE(self.fsync),
            SIMPLE(self.rename), SIMPLE(self.fsync_dir), SIMPLE(self.close),
            SIMPLE(self.remove),
        ]
        self.ops = Ops(None, *self.callbacks)

    def _checkpoint(self, operation):
        self.snapshots.append({
            'op': operation,
            'renamed': self.renamed,
            'dir_synced': self.dir_synced,
            'durable_temp': self.durable_temp,
        })
        self.operations.append(operation)

    def _fault(self, operation):
        self.call += 1
        if self.call == self.sc.get('fail_at', -1):
            self.fault_triggered = True
            self._checkpoint(operation + ':EIO')
            return True
        return False

    def create(self, ctx):
        if self._fault('create'): return -errno.EIO
        if self.exists: return -errno.EEXIST
        self.exists = True
        self._checkpoint('create')
        return 0

    def write(self, ctx, pointer, length):
        if self._fault('write'): return -errno.EIO
        if self.sc.get('eintr', False) and not self.eintr_done:
            self.eintr_done = True
            self._checkpoint('write:EINTR')
            return -errno.EINTR
        if not self.exists or self.closed or self.renamed: return -errno.EBADF
        count = min(int(length), int(self.sc['chunk']))
        if count:
            self.volatile += ctypes.string_at(pointer, count)
        self._checkpoint('write:' + str(count))
        return count

    def fsync(self, ctx):
        if self._fault('fsync_file'): return -errno.EIO
        if not self.exists: return -errno.EBADF
        self.durable_temp = bytes(self.volatile)
        self._checkpoint('fsync_file')
        return 0

    def rename(self, ctx):
        if self._fault('rename'): return -errno.EIO
        if not self.exists: return -errno.ENOENT
        self.renamed = True
        self._checkpoint('rename')
        return 0

    def fsync_dir(self, ctx):
        if self._fault('fsync_dir'): return -errno.EIO
        self.dir_synced = self.renamed
        self._checkpoint('fsync_dir')
        return 0

    def close(self, ctx):
        if self._fault('close'): return -errno.EIO
        self.closed = True
        self._checkpoint('close')
        return 0

    def remove(self, ctx):
        if self._fault('remove'): return -errno.EIO
        if not self.renamed:
            self.exists = False
            self.volatile = bytearray()
        self._checkpoint('remove')
        return 0

    def crash_values(self, snap):
        if not snap['renamed']:
            return [self.old]
        persisted = snap['durable_temp']
        if persisted is None:
            # An unsynced, possibly torn inode may survive as zeroed data.
            persisted = b'<TORN_BYTES>'
        if snap['dir_synced']:
            return [persisted]
        return [self.old, persisted]

    def verify(self, rc):
        permitted = {self.old, self.new}
        for index, snap in enumerate(self.snapshots):
            for value in self.crash_values(snap):
                if value not in permitted:
                    return False, {'reason': 'crash_torn_bytes',
                                   'cut': index, 'after': snap['op'],
                                   'value_prefix': value[:32].hex()}
        last = self.snapshots[-1]
        if not self.fault_triggered and rc != 0:
            return False, {'reason': 'fails_without_unrecoverable_io_error',
                           'operations': self.operations[-12:]}
        if rc == 0:
            if (not last['renamed'] or not last['dir_synced'] or
                last['durable_temp'] != self.new):
                return False, {'reason': 'false_durable_success',
                               'operations': self.operations[-12:]}
        return True, None

def child(s):
    sim = KernelModel(s)
    lib = ctypes.CDLL(str(SO))
    fun = lib.publish
    fun.restype = ctypes.c_int
    fun.argtypes = [ctypes.POINTER(Ops), ctypes.POINTER(ctypes.c_ubyte), ctypes.c_size_t]
    payload = sim.new
    array = (ctypes.c_ubyte * max(1, len(payload)))()
    if payload:
        ctypes.memmove(array, payload, len(payload))
    rc = fun(ctypes.byref(sim.ops), array, len(payload))
    ok, failure = sim.verify(rc)
    return {'passed': ok, 'counterexample': failure,
            'return_code': rc, 'syscalls': len(sim.operations)-1}

def scenarios():
    rng = random.Random(172920)
    cases = []
    # Force short writes and EINTR, then place I/O failure at each API step.
    for length in (0, 1, 39, 1001, 4096):
        old = bytes(rng.randrange(256) for _ in range(37))
        new = bytes(rng.randrange(256) for _ in range(length))
        for chunk in (3, 97, 4096):
            base = {'old': old.hex(), 'new': new.hex(), 'chunk': chunk}
            cases += [dict(base), dict(base, eintr=True)]
            for k in range(1, 9):
                cases.append(dict(base, fail_at=k))
    return cases

def main():
    if '--batch' in sys.argv:
        try:
            for index, item in enumerate(json.loads(sys.stdin.read())):
                outcome = child(item)
                if not outcome['passed']:
                    outcome['batch_index'] = index
                    print(json.dumps(outcome))
                    return
            print(json.dumps({'passed': True}))
        except BaseException as ex:
            print(json.dumps({'passed': False, 'counterexample': {'reason': str(ex)}}))
        return
    source = WORKSPACE / 'publisher.c'
    report = {'passed': False, 'checks': {}, 'cases': 0, 'model': 'restricted-vfs-crash-v1'}
    try:
        if not source.exists() or source.stat().st_size > 200000:
            raise ValueError('Missing or oversized publisher.c')
        compile_cmd = ['gcc', '-std=c11', '-O2', '-fPIC', '-shared',
                       '-Wall', '-Wextra', '-I' + str(TESTS),
                       str(source), '-o', str(SO)]
        p = subprocess.run(compile_cmd, capture_output=True, text=True, timeout=30)
        report['checks']['compile'] = p.returncode == 0
        if p.returncode:
            raise RuntimeError('compile: ' + p.stderr[-1000:])
        cases = scenarios()
        for offset in range(0, len(cases), 20):
            batch = cases[offset:offset+20]
            p = subprocess.run([sys.executable, str(pathlib.Path(__file__).resolve()), '--batch'],
                               input=json.dumps(batch), capture_output=True, text=True,
                               timeout=35)
            if p.returncode:
                report['counterexample'] = {'reason': 'candidate_exit', 'stderr': p.stderr[-500:]}
                break
            try:
                outcome = json.loads(p.stdout)
            except Exception:
                outcome = {'passed': False, 'counterexample': {'reason': 'candidate_bad_output'}}
            if not outcome.get('passed'):
                idx = offset + outcome.get('batch_index', 0)
                report['cases'] = idx+1
                report['counterexample'] = outcome.get('counterexample')
                sc = cases[idx]
                report['case'] = {k: (v[:24]+'...' if k in ('new', 'old') else v)
                                  for k,v in sc.items()}
                break
            report['cases'] += len(batch)
        else:
            report['checks']['crash_cut_model'] = True
            report['passed'] = True
    except Exception as ex:
        report['error'] = str(ex)
    (LOGS/'reward.txt').write_text('1\n' if report['passed'] else '0\n')
    (LOGS/'feedback.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2))

if __name__ == '__main__':
    main()
