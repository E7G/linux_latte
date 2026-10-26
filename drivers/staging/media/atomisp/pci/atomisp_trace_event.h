/* SPDX-License-Identifier: GPL-2.0 */
/*
 * Support Camera Imaging tracer core.
 *
 * Copyright (c) 2013 Intel Corporation. All Rights Reserved.
 */
#undef TRACE_SYSTEM
#define TRACE_SYSTEM atomisp

#if !defined(ATOMISP_TRACE_EVENT_H) || defined(TRACE_HEADER_MULTI_READ)
#define ATOMISP_TRACE_EVENT_H

#include <linux/tracepoint.h>
#include <linux/string.h>

/*
 * Associate CSS exposure IDs with completed vb2 buffers. Exposure IDs identify
 * accepted ISYS frames, not every physical sensor frame. Stream-start DONE
 * buffers can have exposure ID zero; error/flush completions may carry stale
 * IDs. Consumers must distinguish completion state and stream epoch.
 */
TRACE_EVENT(atomisp_buffer_done,
	    TP_PROTO(int minor, unsigned int index, unsigned int sequence,
		     unsigned int exp_id, unsigned int isp_config_id, int state,
		     u64 timestamp_ns, unsigned long bytesused),

	    TP_ARGS(minor, index, sequence, exp_id, isp_config_id, state,
		    timestamp_ns, bytesused),

	    TP_STRUCT__entry(
		__field(int, minor)
		__field(unsigned int, index)
		__field(unsigned int, sequence)
		__field(unsigned int, exp_id)
		__field(unsigned int, isp_config_id)
		__field(int, state)
		__field(u64, timestamp_ns)
		__field(unsigned long, bytesused)
	),

	    TP_fast_assign(
		__entry->minor = minor;
		__entry->index = index;
		__entry->sequence = sequence;
		__entry->exp_id = exp_id;
		__entry->isp_config_id = isp_config_id;
		__entry->state = state;
		__entry->timestamp_ns = timestamp_ns;
		__entry->bytesused = bytesused;
	),

	    TP_printk("minor=%d index=%u sequence=%u exp_id=%u isp_config_id=%u state=%d timestamp_ns=%llu bytesused=%lu",
		      __entry->minor, __entry->index, __entry->sequence,
		      __entry->exp_id, __entry->isp_config_id, __entry->state,
		      (unsigned long long)__entry->timestamp_ns, __entry->bytesused)
);

TRACE_EVENT(camera_meminfo,

	    TP_PROTO(const char *name, int uptr_size, int counter, int sys_size,
		     int sys_res_size, int cam_sys_use, int cam_dyc_use,
		     int cam_res_use),

	    TP_ARGS(name, uptr_size, counter, sys_size, sys_res_size, cam_sys_use,
		    cam_dyc_use, cam_res_use),

	    TP_STRUCT__entry(
		__array(char, name, 24)
		__field(int, uptr_size)
		__field(int, counter)
		__field(int, sys_size)
		__field(int, sys_res_size)
		__field(int, cam_res_use)
		__field(int, cam_dyc_use)
		__field(int, cam_sys_use)
	    ),

	    TP_fast_assign(
		strscpy(__entry->name, name, 24);
		__entry->uptr_size = uptr_size;
		__entry->counter = counter;
		__entry->sys_size = sys_size;
		__entry->sys_res_size = sys_res_size;
		__entry->cam_res_use = cam_res_use;
		__entry->cam_dyc_use = cam_dyc_use;
		__entry->cam_sys_use = cam_sys_use;
	    ),

	    TP_printk(
		"<%s> User ptr memory:%d pages,\tISP private memory used:%d pages:\tsysFP system size:%d,\treserved size:%d\tcamFP sysUse:%d,\tdycUse:%d,\tresUse:%d.\n",
		__entry->name, __entry->uptr_size, __entry->counter,
		__entry->sys_size, __entry->sys_res_size, __entry->cam_sys_use,
		__entry->cam_dyc_use, __entry->cam_res_use)
	   );

TRACE_EVENT(camera_debug,

	    TP_PROTO(const char *name, char *info, const int line),

	    TP_ARGS(name, info, line),

	    TP_STRUCT__entry(
		__array(char, name, 24)
		__array(char, info, 24)
		__field(int, line)
	    ),

	    TP_fast_assign(
		strscpy(__entry->name, name, 24);
		strscpy(__entry->info, info, 24);
		__entry->line = line;
	    ),

	    TP_printk("<%s>-<%d> %s\n", __entry->name, __entry->line,
		      __entry->info)
	   );

TRACE_EVENT(ipu_cstate,

	    TP_PROTO(int cstate),

	    TP_ARGS(cstate),

	    TP_STRUCT__entry(
		__field(int, cstate)
	    ),

	    TP_fast_assign(
		__entry->cstate = cstate;
	    ),

	    TP_printk("cstate=%d", __entry->cstate)
	   );

TRACE_EVENT(ipu_pstate,

	    TP_PROTO(int freq, int util),

	    TP_ARGS(freq, util),

	    TP_STRUCT__entry(
		__field(int, freq)
		__field(int, util)
	    ),

	    TP_fast_assign(
		__entry->freq = freq;
		__entry->util = util;
	    ),

	    TP_printk("freq=%d util=%d", __entry->freq, __entry->util)
	   );
#endif

#undef TRACE_INCLUDE_PATH
#undef TRACE_INCLUDE_FILE
#define TRACE_INCLUDE_PATH .
#define TRACE_INCLUDE_FILE   atomisp_trace_event
/* This part must be outside protection */
#include <trace/define_trace.h>
