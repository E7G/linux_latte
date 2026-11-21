#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Generate a native GStreamer regression test from the patched function."""

import sys
from pathlib import Path


text = Path(sys.argv[1]).read_text()
start = text.index("static gboolean\ngst_v4l2_object_atomisp_stepwise_rates (")
end = text.index("\n}", start) + 2
assert 'g_str_equal (v4l2object->vcap.driver, "atomisp")' in text

print(r"""
#include <assert.h>
#include <gst/gst.h>
#include <linux/videodev2.h>
""", text[start:end], r"""
static gboolean allows(GstCaps *caps, gint n, gint d)
{
	GstCaps *requested = gst_caps_new_simple("video/x-raw",
		"framerate", GST_TYPE_FRACTION, n, d, NULL);
	gboolean result = gst_caps_can_intersect(caps, requested);
	gst_caps_unref(requested);
	return result;
}

static void exercise(guint32 ppl, guint32 rate, guint32 min_vts,
		     gint exact30_n, gint exact30_d, gboolean supports60)
{
	struct v4l2_frmival_stepwise src = {
		{ ppl * min_vts, rate }, { ppl * 65535, rate }, { ppl, rate }
	};
	GValue val = G_VALUE_INIT;
	GstCaps *caps = gst_caps_new_empty_simple("video/x-raw");

	assert(gst_v4l2_object_atomisp_stepwise_rates(&src, &val));
	assert(GST_VALUE_HOLDS_FRACTION_RANGE(&val));
	gst_structure_take_value(gst_caps_get_structure(caps, 0), "framerate", &val);
	assert(allows(caps, 30, 1) && allows(caps, exact30_n, exact30_d));
	assert(allows(caps, 60, 1) == supports60 && !allows(caps, 120, 1));
	gst_caps_unref(caps);
}

int main(int argc, char **argv)
{
	GValue val = G_VALUE_INIT;
	struct v4l2_frmival_stepwise range = {
		{1, 30}, {2, 60}, {1, 10000}
	};

	gst_init(&argc, &argv);
	exercise(2688, 160000000, 1120, 78125, 2604, FALSE);
	exercise(3440, 257174400, 1100, 30, 1, TRUE);
	exercise(2688, 160000000, 1480, 78125, 2604, FALSE);
	exercise(3440, 257174400, 1460, 30, 1, FALSE);
	assert(gst_v4l2_object_atomisp_stepwise_rates(&range, &val));
	assert(GST_VALUE_HOLDS_FRACTION(&val));
	assert(gst_value_get_fraction_numerator(&val) == 30 &&
	       gst_value_get_fraction_denominator(&val) == 1);
	g_value_unset(&val);
	range.max = (struct v4l2_fract) { 1, 60 };
	assert(!gst_v4l2_object_atomisp_stepwise_rates(&range, &val));
	range.max = (struct v4l2_fract) { 1, 0 };
	assert(!gst_v4l2_object_atomisp_stepwise_rates(&range, &val));
	range.max = (struct v4l2_fract) { 1, 1 };
	range.step.numerator = 0;
	assert(!gst_v4l2_object_atomisp_stepwise_rates(&range, &val) && !G_VALUE_TYPE(&val));
	g_print("PASS: exact helper admits nominal and native 30fps, rejects rates outside valid bounds\n");
}
""")
