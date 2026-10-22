#define _GNU_SOURCE
#include <errno.h>
#include <stdio.h>
#include <string.h>
#include <sys/timex.h>
#include <time.h>
static double clock_seconds(clockid_t id)
{
 struct timespec t;
 if(clock_gettime(id,&t))return -1;
 return t.tv_sec+t.tv_nsec*1e-9;
}
int main(void)
{
 const clockid_t ids[]={CLOCK_MONOTONIC,CLOCK_MONOTONIC_RAW,CLOCK_BOOTTIME,CLOCK_REALTIME};
 double first[4];for(int i=0;i<4;i++)first[i]=clock_seconds(ids[i]);
 printf("baseline_mono=%.9f baseline_raw=%.9f baseline_boottime=%.9f baseline_realtime=%.9f\n",first[0],first[1],first[2],first[3]);
 for(int n=0;n<=180;n++) {
  struct timex t={0}; /* modes0 queries only; no clock adjustment */
  int state=adjtimex(&t);if(state<0){perror("adjtimex query");return 1;}
  printf("sample=%d mono=%.9f raw=%.9f boottime=%.9f realtime=%.9f frequency_scaled_ppm=%ld tick_us=%ld offset=%ld status=%d state=%d timeconstant=%ld\n",
   n,clock_seconds(ids[0])-first[0],clock_seconds(ids[1])-first[1],clock_seconds(ids[2])-first[2],clock_seconds(ids[3])-first[3],
   t.freq,t.tick,t.offset,t.status,state,t.constant);
  fflush(stdout);
  if(n<180) {struct timespec pause={.tv_nsec=500000000};while(nanosleep(&pause,&pause)&&errno==EINTR){}}
 }
 return 0;
}
