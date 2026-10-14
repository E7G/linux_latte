#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
"""Exact CSS-uninit callback: idempotence only, not hardware/partial-init proof."""
from pathlib import Path
import os,subprocess,tempfile
r=Path(os.environ.get('MIPAD2_KERNEL_SOURCE',str(Path(__file__).resolve().parents[2])))
s=(r/'drivers/staging/media/atomisp/pci/atomisp_compat_css20.c').read_text();a=s.index('void atomisp_css_uninit(');i=s.index('{',a)+1;depth=1
while depth:
 depth+=(s[i]=='{')-(s[i]=='}');i+=1
prefix=r"""
#include <stdbool.h>
#include <assert.h>
#include <stdio.h>
struct atomisp_device {bool css_initialized;};
static int calls;static struct atomisp_device *current;
static void ia_css_uninit(void){assert(!current->css_initialized);calls++;}
"""
suffix=r"""
int main(void){unsigned cases=0;for(int ready=0;ready<2;ready++)for(int repeat=1;repeat<5;repeat++){
 struct atomisp_device isp={.css_initialized=ready};current=&isp;calls=0;
 for(int j=0;j<repeat;j++)atomisp_css_uninit(&isp);
 assert(!isp.css_initialized&&calls==ready);
 isp.css_initialized=true;atomisp_css_uninit(&isp);assert(calls==ready+1&&!isp.css_initialized);cases++;
}printf("PASS %u exact CSS-uninit initialized/uninitialized/retry/reinit host cases; no hardware claim\n",cases);}
"""
with tempfile.TemporaryDirectory(prefix='mipad2-css-uninit-') as d:
 p=Path(d)/'test.c';p.write_text(prefix+s[a:i]+suffix);binary=Path(d)/'test'
 subprocess.run(['cc','-std=gnu11','-O2','-Wall','-Wextra','-Werror',str(p),'-o',str(binary)],check=True)
 subprocess.run([str(binary)],check=True)
