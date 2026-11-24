/* Protocol glue only: reads cases, calls the candidate, writes what it returned.
 * Nothing it prints is trusted as a verdict; the grader compares every answer itself. */
#include <stdint.h>
#include <stdio.h>

struct budget { unsigned long long remaining; unsigned long long total; };
int charge(struct budget *state, unsigned long long amount);

int main(void) {
    uint64_t in[3];
    while (fread(in, sizeof in, 1, stdin) == 1) {
        struct budget b = {in[0], in[1]};
        int32_t ret = charge(&b, in[2]);
        uint64_t after[2] = {b.remaining, b.total};
        if (fwrite(&ret, sizeof ret, 1, stdout) != 1 || fwrite(after, sizeof after, 1, stdout) != 1) return 2;
    }
    return fflush(stdout) ? 2 : 0;
}
