#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <fcntl.h>
#include <sys/stat.h>
/* The trusted child program checks the actual post-exec descriptor table. */
int main(void) {
    const char *want=getenv("DELTAOS_PUBLIC_TEXT");
    if (!want) return 11;
    for(int fd=4;fd<256;fd++) {
        if (fcntl(fd,F_GETFD)>=0) return 20;
    }
    if (fcntl(3,F_GETFD)<0) return 30;
    char buffer[256]={0};
    ssize_t n=read(3,buffer,sizeof(buffer));
    if (n<0 || n!=(ssize_t)strlen(want) || memcmp(buffer,want,(size_t)n)!=0) return 40;
    /* External receipt prevents a no-op launcher that just returns 0 from
     * passing a process-launch task. It is NOT cryptographic attestation. */
    const char *receipt=getenv("DELTAOS_RECEIPT_PATH");
    const char *token=getenv("DELTAOS_RECEIPT_TOKEN");
    if (!receipt || !token) return 41;
    FILE *fp=fopen(receipt,"w");
    if(!fp) return 42;
    if(fputs(token,fp)==EOF || fclose(fp)!=0) return 43;
    return 0;
}
