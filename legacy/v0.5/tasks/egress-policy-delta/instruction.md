# Repair the artifact-proxy egress policy without opening other destinations

You are given `/workspace/policy.c`, the authorization decision function called by a Linux `cgroup/connect4` eBPF program. The current implementation incorrectly permits an entire `/24` network.

Implement this exact contract by **editing only `/workspace/policy.c`**:

1. Preserve every connection where `previously_allowed == 1`.
2. If `previously_allowed == 0`, allow **only** a TCP (`proto=6`) connection from UID `10042` to IPv4 `10.4.2.9` on destination port `443`.
3. Deny all other combinations, including neighboring IPs, UDP, other ports, and other UIDs.
4. Return exactly `1` (allow) or `0` (deny). Preserve the C ABI shown in the file.
5. Do not change the separate trusted verifier, the task instruction, or compilation configuration.

The IP argument is an unsigned 32-bit **host-order** IPv4 value: `10.4.2.9 == 0x0a040209`. The port is an unsigned host-order destination port. The eBPF adapter performs network-to-host conversion before calling the function.

You can use clang and gcc for local checks. The private judge compiles your file to native code and also embeds it into an eBPF bytecode target. It uses an independent reference predicate and many edge cases. Passing the Linux verifier or compiling to BPF alone is **not** proof of functional correctness.

Finish with `/workspace/policy.c` containing your implementation. Do not submit logs or text as the result.
