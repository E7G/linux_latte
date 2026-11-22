/* SPDX-License-Identifier: GPL-2.0 */
#undef TRACE_SYSTEM
#define TRACE_SYSTEM pmc_atom

#if !defined(_TRACE_PMC_ATOM_H) || defined(TRACE_HEADER_MULTI_READ)
#define _TRACE_PMC_ATOM_H

#include <linux/tracepoint.h>

TRACE_EVENT(pmc_atom_s2idle,

	TP_PROTO(u32 func_dis, u32 func_dis_2, u32 d3_sts_0, u32 d3_sts_1,
		 u32 pss, u32 forced_clks),

	TP_ARGS(func_dis, func_dis_2, d3_sts_0, d3_sts_1, pss, forced_clks),

	TP_STRUCT__entry(
		__field(u32, func_dis)
		__field(u32, func_dis_2)
		__field(u32, d3_sts_0)
		__field(u32, d3_sts_1)
		__field(u32, pss)
		__field(u32, forced_clks)
	),

	TP_fast_assign(
		__entry->func_dis = func_dis;
		__entry->func_dis_2 = func_dis_2;
		__entry->d3_sts_0 = d3_sts_0;
		__entry->d3_sts_1 = d3_sts_1;
		__entry->pss = pss;
		__entry->forced_clks = forced_clks;
	),

	TP_printk("func_dis=0x%08x func_dis_2=0x%08x d3_sts_0=0x%08x d3_sts_1=0x%08x pss=0x%08x forced_clks=0x%08x",
		  __entry->func_dis, __entry->func_dis_2,
		  __entry->d3_sts_0, __entry->d3_sts_1,
		  __entry->pss, __entry->forced_clks)
);

#endif /* _TRACE_PMC_ATOM_H */

#include <trace/define_trace.h>
