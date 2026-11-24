int policy_decide(unsigned int uid, unsigned int ip, unsigned short port, unsigned int proto, unsigned int prior) {
  if(prior) return 1;
  return uid==10042U && (ip & 0xffffff00U)==0x0a040200U && port==443U && proto==6U;
}
