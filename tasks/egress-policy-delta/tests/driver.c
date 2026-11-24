/* Protocol glue only: reads cases, calls the candidate, writes what it returned.
 * It runs in the sandbox next to candidate code, so nothing it prints is trusted
 * as a verdict; the grader compares every answer with the contract itself. */
#include <stdint.h>
#include <stdio.h>

int policy_decide(unsigned int, unsigned int, unsigned short, unsigned int, unsigned int);

int main(void) {
    uint32_t in[5];
    int32_t out;
    while (fread(in, sizeof in, 1, stdin) == 1) {
        out = policy_decide(in[0], in[1], (unsigned short)in[2], in[3], in[4]);
        if (fwrite(&out, sizeof out, 1, stdout) != 1) return 2;
    }
    return fflush(stdout) ? 2 : 0;
}
