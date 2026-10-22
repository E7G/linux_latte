/* SPDX-License-Identifier: GPL-2.0-only
 * Actual libasound UCM API runner against the explicit fake control plugin. */

#include <alsa/asoundlib.h>
#include <alsa/use-case.h>
#include <stdio.h>
int main(void){snd_use_case_mgr_t *m=NULL;int rc=snd_use_case_mgr_open(&m,"hw:0");if(rc<0){fprintf(stderr,"open: %s\n",snd_strerror(rc));return 10;}
 rc=snd_use_case_set(m,"_verb","HiFi");if(rc<0){fprintf(stderr,"verb: %s\n",snd_strerror(rc));return 11;}
 const char *dev[]={"Speaker","Headphones","IntMic","HeadsetMic"};
 for(int n=0;n<3;n++)for(unsigned i=0;i<4;i++){rc=snd_use_case_set(m,"_enadev",dev[i]);if(rc<0){fprintf(stderr,"enable %s: %s\n",dev[i],snd_strerror(rc));return 12;}rc=snd_use_case_set(m,"_disdev",dev[i]);if(rc<0)return 13;}
 snd_use_case_mgr_close(m);snd_config_update_free_global();printf("real ALSA %s: 3x4 enable/disable cycles pass\n",snd_asoundlib_version());return 0;}
