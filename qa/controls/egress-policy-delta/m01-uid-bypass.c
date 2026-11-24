int policy_decide(unsigned int uid, unsigned int ip, unsigned short port, unsigned int proto, unsigned int prior) {
  if(prior) return 1;
  return ip==0x0a040209U && port==443U && proto==6U;
}
