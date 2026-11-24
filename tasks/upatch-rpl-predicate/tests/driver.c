/* Protocol glue only: the candidate's answer for every value of n, in order. */
#include <stdint.h>
#include <stdio.h>

int rpl_fix_rejects(unsigned char n);

int main(void) {
    for (unsigned n = 0; n < 256; n++) {
        int32_t out = rpl_fix_rejects((unsigned char)n);
        if (fwrite(&out, sizeof out, 1, stdout) != 1) return 2;
    }
    return fflush(stdout) ? 2 : 0;
}
