/* SPDX-License-Identifier: GPL-2.0-only
 * Synthetic ALSA control backend: no PCM or physical device access. */

#include <alsa/asoundlib.h>
#include <alsa/control_external.h>
#include <errno.h>
#include <stdlib.h>
#include <string.h>
struct ctl_def {const char *name; unsigned items;const char *labels[4];};
static const struct ctl_def defs[]={{"DAC1 Playback Switch",0,{}},
{"Ext Spk Switch",0,{}},
{"Headphone Switch",0,{}},
{"Headset Mic Switch",0,{}},
{"IF2 ADC Mux",3,{"IF_ADC1","IF_ADC2","DAC_REF"}},
{"IF3 ADC Mux",3,{"IF_ADC1","IF_ADC2","DAC_REF"}},
{"IN Capture Volume",0,{}},
{"Int Mic Switch",0,{}},
{"RECMIX1L BST3 Switch",0,{}},
{"RECMIX1L INL Switch",0,{}},
{"RECMIX1R BST4 Switch",0,{}},
{"RECMIX1R INR Switch",0,{}},
{"STO1 ADC Capture Switch",0,{}},
{"STO1 ADC Capture Volume",0,{}},
{"Stereo1 ADC MIXL ADC1 Switch",0,{}},
{"Stereo1 ADC MIXR ADC1 Switch",0,{}},
{"Stereo1 ADC Source",2,{"ADC1","ADC2"}},
{"Stereo1 ADC1 Source",2,{"ADC","DAC MIX"}},
{"codec_out0 Gain 0 Volume",0,{}},
{"Amp Input",2,{"Left","Right"}},
{"Amp Input1",2,{"Left","Right"}},
{"Left Amp Input",2,{"Left","Right"}},
{"Right Amp Input",2,{"Left","Right"}}};
static long values[128][2];
struct fake {snd_ctl_ext_t ext;};
static int present(unsigned i){
 const char *n=defs[i].name,*mode=getenv("MP2_CTL_LAYOUT");
 int old=!strcmp(n,"Amp Input")||!strcmp(n,"Amp Input1");
 int modern=!strcmp(n,"Left Amp Input")||!strcmp(n,"Right Amp Input");
 if(!strcmp(mode,"legacy"))return !modern;
 if(!strcmp(mode,"modern"))return !old;
 if(!strcmp(mode,"missing_right"))return !old&&strcmp(n,"Right Amp Input");
 if(!strcmp(mode,"legacy_missing_right"))return !modern&&strcmp(n,"Amp Input1");
 if(!strcmp(mode,"missing_left"))return !old&&strcmp(n,"Left Amp Input");
 if(!strcmp(mode,"mixed_right"))return strcmp(n,"Left Amp Input");
 if(!strcmp(mode,"none"))return !old&&!modern;
 return 1;
}
static void close_ctl(snd_ctl_ext_t *e){free(e->private_data);}
static int count_ctl(snd_ctl_ext_t *e){(void)e;unsigned n=0;for(unsigned i=0;i<sizeof(defs)/sizeof(defs[0]);i++)n+=present(i);return (int)n;}
static int list_ctl(snd_ctl_ext_t *e,unsigned offset,snd_ctl_elem_id_t *id){
 (void)e;for(unsigned i=0;i<sizeof(defs)/sizeof(defs[0]);i++)if(present(i)&&offset--==0){snd_ctl_elem_id_set_interface(id,SND_CTL_ELEM_IFACE_MIXER);snd_ctl_elem_id_set_name(id,defs[i].name);snd_ctl_elem_id_set_numid(id,i+1);return 0;}return -ENOENT;
}
static snd_ctl_ext_key_t find_ctl(snd_ctl_ext_t *e,const snd_ctl_elem_id_t *id){
 (void)e;unsigned num=snd_ctl_elem_id_get_numid(id);for(unsigned i=0;i<sizeof(defs)/sizeof(defs[0]);i++)if(present(i)&&((num&&num==i+1)||(!num&&!strcmp(snd_ctl_elem_id_get_name(id),defs[i].name))))return i;return SND_CTL_EXT_KEY_NOT_FOUND;
}
static int attr(snd_ctl_ext_t *e,snd_ctl_ext_key_t k,int *t,unsigned *acc,unsigned *count){
 (void)e;*acc=SND_CTL_EXT_ACCESS_READWRITE;*count=1;*t=defs[k].items?SND_CTL_ELEM_TYPE_ENUMERATED:strstr(defs[k].name,"Switch")?SND_CTL_ELEM_TYPE_BOOLEAN:SND_CTL_ELEM_TYPE_INTEGER;
 if(strstr(defs[k].name,"Capture Volume"))*count=2;return 0;
}
static int int_info(snd_ctl_ext_t *e,snd_ctl_ext_key_t k,long *a,long *b,long *step){(void)e;(void)k;*a=0;*b=100;*step=1;return 0;}
static int enum_info(snd_ctl_ext_t *e,snd_ctl_ext_key_t k,unsigned *n){(void)e;*n=defs[k].items;return 0;}
static int enum_name(snd_ctl_ext_t *e,snd_ctl_ext_key_t k,unsigned item,char *dst,size_t n){(void)e;if(item>=defs[k].items)return -EINVAL;snprintf(dst,n,"%s",defs[k].labels[item]);return 0;}
static int read_int(snd_ctl_ext_t *e,snd_ctl_ext_key_t k,long *v){(void)e;v[0]=values[k][0];if(strstr(defs[k].name,"Capture Volume"))v[1]=values[k][1];return 0;}
static int read_enum(snd_ctl_ext_t *e,snd_ctl_ext_key_t k,unsigned *v){(void)e;v[0]=values[k][0];return 0;}
static int write_int(snd_ctl_ext_t *e,snd_ctl_ext_key_t k,long *v){
 (void)e;values[k][0]=v[0];if(strstr(defs[k].name,"Capture Volume"))values[k][1]=v[1];FILE *f=fopen(getenv("MP2_CTL_LOG"),"a");if(!f)return -errno;fprintf(f,"%s|%ld\n",defs[k].name,v[0]);fclose(f);return 1;
}
static int write_enum(snd_ctl_ext_t *e,snd_ctl_ext_key_t k,unsigned *v){long x=v[0];return write_int(e,k,&x);}
static const snd_ctl_ext_callback_t callbacks={.close=close_ctl,.elem_count=count_ctl,.elem_list=list_ctl,.find_elem=find_ctl,.get_attribute=attr,.get_integer_info=int_info,.get_enumerated_info=enum_info,.get_enumerated_name=enum_name,.read_integer=read_int,.read_enumerated=read_enum,.write_integer=write_int,.write_enumerated=write_enum};
SND_CTL_PLUGIN_DEFINE_FUNC(mp2test){
 (void)root;(void)conf;struct fake *f=calloc(1,sizeof(*f));if(!f)return -ENOMEM;
 f->ext.version=SND_CTL_EXT_VERSION;f->ext.card_idx=0;strcpy(f->ext.id,"MP2TEST");strcpy(f->ext.driver,"cht-bsw-rt5659");strcpy(f->ext.name,"MiPad2 synthetic controls");strcpy(f->ext.longname,"No hardware: real ALSA UCM parser test");strcpy(f->ext.mixername,"MP2 test");f->ext.poll_fd=-1;f->ext.callback=&callbacks;f->ext.private_data=f;
 int rc=snd_ctl_ext_create(&f->ext,name,mode);if(rc<0){free(f);return rc;}*handlep=f->ext.handle;return 0;
}
SND_CTL_PLUGIN_SYMBOL(mp2test);
