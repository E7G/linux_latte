// SPDX-License-Identifier: GPL-2.0
/*
 * Support for Intel Camera Imaging ISP subsystem.
 * Copyright (c) 2015, Intel Corporation.
 */

#include <linux/bug.h>
#include <linux/limits.h>
#include <linux/math64.h>

#include "ia_css_types.h"
#include "sh_css_defs.h"
#include "ia_css_debug.h"
#include "sh_css_frac.h"

#include "ia_css_dp.host.h"

/* We use a different set of DPC configuration parameters when
 * DPC is used before OBC and NORM. Currently these parameters
 * are used in usecases which selects both BDS and DPC.
 **/
const struct ia_css_dp_config default_dp_10bpp_config = {
	1024,
	2048,
	32768,
	32768,
	32768,
	32768
};

const struct ia_css_dp_config default_dp_config = {
	8192,
	2048,
	32768,
	32768,
	32768,
	32768
};

static unsigned int
ia_css_dp_encode_coefficient(u32 gain, u32 numerator, u32 denominator)
{
	u64 coefficient;

	/* Invalid userspace/firmware WB gains must not crash the kernel. */
	if (WARN_ON_ONCE(!denominator))
		denominator = 1U << 15;

	coefficient = div64_u64((u64)gain * numerator, denominator);
	if (coefficient > U32_MAX)
		coefficient = U32_MAX;

	return uDIGIT_FITTING((u32)coefficient, 8, SH_CSS_DP_GAIN_SHIFT);
}

void
ia_css_dp_encode(
    struct sh_css_isp_dp_params *to,
    const struct ia_css_dp_config *from,
    unsigned int size)
{
	(void)size;
	to->threshold_single =
	    SH_CSS_BAYER_MAXVAL;
	to->threshold_2adjacent =
	    uDIGIT_FITTING(from->threshold, 16, SH_CSS_BAYER_BITS);
	to->gain =
	    uDIGIT_FITTING(from->gain, 8, SH_CSS_DP_GAIN_SHIFT);

	to->coef_rr_gr =
	    ia_css_dp_encode_coefficient(from->gain, from->gr, from->r);
	to->coef_rr_gb =
	    ia_css_dp_encode_coefficient(from->gain, from->gb, from->r);
	to->coef_bb_gb =
	    ia_css_dp_encode_coefficient(from->gain, from->gb, from->b);
	to->coef_bb_gr =
	    ia_css_dp_encode_coefficient(from->gain, from->gr, from->b);
	to->coef_gr_rr =
	    ia_css_dp_encode_coefficient(from->gain, from->r, from->gr);
	to->coef_gr_bb =
	    ia_css_dp_encode_coefficient(from->gain, from->b, from->gr);
	to->coef_gb_bb =
	    ia_css_dp_encode_coefficient(from->gain, from->b, from->gb);
	to->coef_gb_rr =
	    ia_css_dp_encode_coefficient(from->gain, from->r, from->gb);
}

void
ia_css_dp_dump(
    const struct sh_css_isp_dp_params *dp,
    unsigned int level)
{
	if (!dp) return;
	ia_css_debug_dtrace(level, "Defect Pixel Correction:\n");
	ia_css_debug_dtrace(level, "\t%-32s = %d\n",
			    "dp_threshold_single_w_2adj_on",
			    dp->threshold_single);
	ia_css_debug_dtrace(level, "\t%-32s = %d\n",
			    "dp_threshold_2adj_w_2adj_on",
			    dp->threshold_2adjacent);
	ia_css_debug_dtrace(level, "\t%-32s = %d\n",
			    "dp_gain", dp->gain);
	ia_css_debug_dtrace(level, "\t%-32s = %d\n",
			    "dpc_coef_rr_gr", dp->coef_rr_gr);
	ia_css_debug_dtrace(level, "\t%-32s = %d\n",
			    "dpc_coef_rr_gb", dp->coef_rr_gb);
	ia_css_debug_dtrace(level, "\t%-32s = %d\n",
			    "dpc_coef_bb_gb", dp->coef_bb_gb);
	ia_css_debug_dtrace(level, "\t%-32s = %d\n",
			    "dpc_coef_bb_gr", dp->coef_bb_gr);
	ia_css_debug_dtrace(level, "\t%-32s = %d\n",
			    "dpc_coef_gr_rr", dp->coef_gr_rr);
	ia_css_debug_dtrace(level, "\t%-32s = %d\n",
			    "dpc_coef_gr_bb", dp->coef_gr_bb);
	ia_css_debug_dtrace(level, "\t%-32s = %d\n",
			    "dpc_coef_gb_bb", dp->coef_gb_bb);
	ia_css_debug_dtrace(level, "\t%-32s = %d\n",
			    "dpc_coef_gb_rr", dp->coef_gb_rr);
}

void
ia_css_dp_debug_dtrace(
    const struct ia_css_dp_config *config,
    unsigned int level)
{
	ia_css_debug_dtrace(level,
			    "config.threshold=%d, config.gain=%d\n",
			    config->threshold, config->gain);
}

void
ia_css_init_dp_state(
    void/*struct sh_css_isp_dp_vmem_state*/ * state,
    size_t size)
{
	memset(state, 0, size);
}
