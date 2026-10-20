#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
"""Exact board/detect/PM functions against ordered GPIO/CCI stubs, NOT physical timing proof."""
from pathlib import Path
import hashlib,json,os,re,subprocess,sys,tempfile

root=Path(os.environ.get('MIPAD2_KERNEL_SOURCE',Path(__file__).resolve().parents[2]))
prototype='--prototype' in sys.argv
output=Path(os.environ.get('MIPAD2_TEST_OUTPUT',tempfile.mkdtemp(prefix='mipad2-t4ka3-reset-report-')));output.mkdir(parents=True,exist_ok=True)
def extract(s,name):
    m=re.search(r'^static (?:bool|int) '+name+r'\([^;]*?\)\n\{',s,re.M);assert m,name
    i=s.index('{',m.start())+1;depth=1
    while depth:depth+=(s[i]=='{')-(s[i]=='}');i+=1
    return s[m.start():i]
prefix=r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <string.h>
#include <errno.h>
typedef uint8_t u8;typedef uint16_t u16;typedef uint64_t u64;
#define DMI_SYS_VENDOR 0
#define DMI_PRODUCT_NAME 1
#define I2C_FUNC_I2C 1
#define T4KA3_REG_PRODUCT_ID_HIGH 0
#define T4KA3_REG_PRODUCT_ID_LOW 1
#define T4KA3_PRODUCT_ID 0x1490
struct i2c_adapter{bool supported;};
struct i2c_client{struct i2c_adapter *adapter;};
struct v4l2_subdev{struct i2c_client *client;};
struct gpio_desc{int id;bool active_low;int logical;};
struct device{void *data;bool acpi;};
struct t4ka3_data{struct v4l2_subdev sd;struct device *dev;void *regmap;struct gpio_desc *powerdown_gpio,*reset_gpio;};
_Static_assert(offsetof(struct t4ka3_data,sd)==0,"real driver's first-member PM data layout");
static const char *vendor,*product;
static bool dmi_match(int field,const char *s){return !strcmp(field?product:vendor,s);}
#define ACPI_COMPANION(d) ((d)->acpi ? (void*)1 : NULL)
#define dev_err(...) ((void)0)
static void *dev_get_drvdata(struct device*d){return d->data;}
static struct i2c_client *v4l2_get_subdevdata(struct v4l2_subdev*s){return s->client;}
static bool i2c_check_functionality(struct i2c_adapter*a,int mask){assert(mask==I2C_FUNC_I2C);return a->supported;}
enum { WAIT_RANGE, WAIT_FIXED, GPIO, CCI_HIGH, CCI_LOW };
struct event{int op,a,b;};
static struct event observed[64],gold[64];static unsigned observed_count,gold_count;static int fault;
static void event(int op,int a,int b){assert(observed_count<64);observed[observed_count++]=(struct event){op,a,b};}
static void want(int op,int a,int b){assert(gold_count<64);gold[gold_count++]=(struct event){op,a,b};}
static void usleep_range(unsigned lo,unsigned hi){event(WAIT_RANGE,(int)lo,(int)hi);}
static void fsleep(unsigned us){event(WAIT_FIXED,(int)us,0);}
static void gpiod_set_value_cansleep(struct gpio_desc*g,int value){assert(g&&value>=0&&value<=1);g->logical=value;event(GPIO,g->id,value);}
static int cci_read(void *map,int reg,u64 *value,int *error){
 assert(map==(void*)1&&error&&value&&(reg==0||reg==1));
 if(*error)return *error; /* actual CCI accumulated-error short circuit */
 event(reg?CCI_LOW:CCI_HIGH,0,0);
 if((fault==1&&!reg)||(fault==2&&reg))*error=-EREMOTEIO;
 else if(fault==4&&!reg)*error=-ETIMEDOUT;
 else *value=reg?0x90:(fault==3?0x15:0x14);
 return *error;
}
'''
main=r'''
static int expected_return(void){return fault==1||fault==2?-EREMOTEIO:fault==4?-ETIMEDOUT:fault==3||fault==5?-ENODEV:0;}
static void golden(bool board,bool reset,bool powerdown){
 gold_count=0;want(WAIT_RANGE,5000,6000);
 if(powerdown)want(GPIO,1,0);
 if(reset&&board){want(WAIT_FIXED,1000,0);want(GPIO,2,0);want(WAIT_FIXED,1000,0);want(GPIO,2,1);want(WAIT_FIXED,1000,0);}
 if(reset)want(GPIO,2,0);
 want(WAIT_FIXED,20000,0);
 if(fault!=5){want(CCI_HIGH,0,0);if(fault!=1&&fault!=4)want(CCI_LOW,0,0);}
 if(expected_return()){if(powerdown)want(GPIO,1,1);if(reset)want(GPIO,2,1);}
}
int main(void){
 static const char *vendors[]={"Xiaomi Inc","Xiaomi Inc","Xiaomi Inc","Xiaomi","LENOVO","Xiaomi Inc","","Xiaomi Inc"};
 static const char *products[]={"Mipad2","Mipad2 Pro","Mipad2 ","Mipad2","Mipad2","MI PAD 2","",""};
 const unsigned repeats[]={1,2,64};unsigned cases=0,failed=0,resumes=0,physical_low_high_low_high_checks=0;
 for(unsigned identity=0;identity<8;identity++)for(unsigned acpi=0;acpi<2;acpi++)for(unsigned have_reset=0;have_reset<2;have_reset++)for(unsigned have_pd=0;have_pd<2;have_pd++)for(unsigned reset_low=0;reset_low<2;reset_low++)for(unsigned pd_low=0;pd_low<2;pd_low++)for(fault=0;fault<6;fault++)for(unsigned repeat=0;repeat<3;repeat++){
  struct i2c_adapter adapter={.supported=fault!=5};struct i2c_client client={.adapter=&adapter};
  struct gpio_desc reset={.id=2,.active_low=reset_low,.logical=1},pd={.id=1,.active_low=pd_low,.logical=1};
  struct device dev={.acpi=acpi};struct t4ka3_data sensor={.sd={.client=&client},.dev=&dev,.regmap=(void*)1,.powerdown_gpio=have_pd?&pd:NULL,.reset_gpio=have_reset?&reset:NULL};
  dev.data=&sensor.sd;vendor=vendors[identity];product=products[identity];bool board=identity==0&&acpi;
  assert(t4ka3_has_mipad2_otp(&sensor)==board);
  bool ok=true;
  for(unsigned n=0;n<repeats[repeat];n++){
   observed_count=0;golden(board,have_reset,have_pd);int ret=t4ka3_pm_resume(&dev);resumes++;
   ok=ok&&ret==expected_return()&&observed_count==gold_count&&!memcmp(observed,gold,gold_count*sizeof(*gold));
   if(have_reset)ok=ok&&reset.logical==(ret!=0);
   if(have_pd)ok=ok&&pd.logical==(ret!=0);
   if(board&&have_reset&&reset_low&&!ret){
    int physical[8]={0};unsigned count=1;
    for(unsigned i=0;i<observed_count;i++)if(observed[i].op==GPIO&&observed[i].a==2){assert(count<8);physical[count++]=observed[i].b^reset.active_low;}
    const int expected[]={0,1,0,1};ok=ok&&count==4&&!memcmp(physical,expected,sizeof(expected));physical_low_high_low_high_checks++;
   }
   observed_count=gold_count=0;assert(!t4ka3_pm_suspend(&dev));
   if(have_pd){want(GPIO,1,1);}
   if(have_reset){want(GPIO,2,1);}
   ok=ok&&observed_count==gold_count&&!memcmp(observed,gold,gold_count*sizeof(*gold));
   if(have_reset){ok=ok&&reset.logical==1;}
   if(have_pd){ok=ok&&pd.logical==1;}
  }
  cases++;if(!ok)failed++;
 }
 printf("{\"cases\":%u,\"failed\":%u,\"resumes\":%u,\"physical_pulse_checks\":%u}\n",cases,failed,resumes,physical_low_high_low_high_checks);
 return 0;
}
'''
with tempfile.TemporaryDirectory(prefix='mipad2-t4ka3-reset-build-') as d:
    for label in (['original','candidate'] if prototype else ['current']):
        p=Path('/tmp/mipad2-r25-t4ka3-reset-20261020')/(label+'.c') if prototype else root/'drivers/media/i2c/t4ka3.c'
        s=p.read_text();functions='\n'.join(extract(s,n) for n in ['t4ka3_has_mipad2_otp','t4ka3_detect','t4ka3_pm_suspend','t4ka3_pm_resume'])
        generated=Path(d)/(label+'.c');generated.write_text(prefix+functions+main);exe=generated.with_suffix('')
        q=subprocess.run(['cc','-std=gnu11','-O1','-g','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-fno-sanitize-recover=all','-fno-omit-frame-pointer','-no-pie',str(generated),'-o',str(exe)],capture_output=True,text=True)
        assert q.returncode==0,q.stderr
        q=subprocess.run([str(exe)],capture_output=True,text=True,env=dict(os.environ,ASAN_OPTIONS='detect_leaks=1:halt_on_error=1'))
        assert q.returncode==0 and not q.stderr,q.stderr
        result=json.loads(q.stdout);assert result['cases']==4608 and result['resumes']==102912 and result['physical_pulse_checks']==268,result
        assert result['failed']==144 if label=='original' else result['failed']==0,result
        report=dict(label=label,source_sha256=hashlib.sha256(s.encode()).hexdigest(),functions_sha256=hashlib.sha256(functions.encode()).hexdigest(),contract=result,sanitizers=['address','undefined','leak'],scope='Exact DMI/ACPI identity, ID-read, PM suspend/resume functions. GPIO/CCI/delay/ACPI/DMI stubs and independent OEM-sequence golden; no actual clocks, power rails, firmware reset, bus latency, cold-boot or image/recording proof.')
        dest=output/('mipad2-r25-t4ka3-reset-'+label+'-host.json');assert not dest.exists();dest.write_text(json.dumps(report,indent=2)+'\n')
        print(label,json.dumps(result),flush=True)
