struct budget { unsigned long long remaining; unsigned long long total; };
int charge(struct budget *s, unsigned long long n){
 if(n>s->remaining) return 0;
 s->remaining-=n;
 if(n>(~0ULL-s->total)) return 0;
 s->total+=n; return 1;
}
