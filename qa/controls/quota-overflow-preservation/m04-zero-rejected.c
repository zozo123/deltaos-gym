struct budget { unsigned long long remaining; unsigned long long total; };
int charge(struct budget *s, unsigned long long n){
 if(n==0 || n>s->remaining || n>(~0ULL-s->total)) return 0;
 s->remaining-=n; s->total+=n; return 1;
}
