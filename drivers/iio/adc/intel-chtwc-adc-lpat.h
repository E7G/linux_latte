/* SPDX-License-Identifier: GPL-2.0-only */
/* Mi Pad2 PMIC LPAT: decikelvin and nominal ohms, not INT340x LPAT units. */
#ifndef INTEL_CHTWC_ADC_LPAT_H
#define INTEL_CHTWC_ADC_LPAT_H

#include <linux/limits.h>
#include <linux/math64.h>
#include <linux/units.h>

#include "intel-chtwc-adc-core.h"

#define CHTWC_LPAT_MAX_POINTS 256

struct chtwc_adc_lpat_point {
	int decikelvin;
	int ohms;
};

/* Validate once before exposing processed channels; never extrapolate. */
static inline bool chtwc_adc_lpat_valid(const struct chtwc_adc_lpat_point *p,
					unsigned int count)
{
	unsigned int i;

	if (!p || count < 2 || count > CHTWC_LPAT_MAX_POINTS)
		return false;
	for (i = 0; i < count; i++) {
		if (p[i].decikelvin < 0 || p[i].decikelvin > INT_MAX / 100 ||
		    p[i].ohms <= 0)
			return false;
		if (i && (p[i].decikelvin <= p[i - 1].decikelvin ||
			  p[i].ohms >= p[i - 1].ohms))
			return false;
	}
	return true;
}

/*
 * Only the three board NTCs share the factory PMIC table. Battery, ID and
 * especially the non-NTC PMIC die must not acquire a fictitious temperature.
 * The caller supplies the count and selector from ONE completed acquisition.
 * Return status separately: negative Celsius is a valid successful result.
 */
static inline int chtwc_adc_temperature(unsigned int index,
				       const struct chtwc_adc_sample *sample,
				       const struct chtwc_adc_lpat_point *p,
				       unsigned int count, int *millicelsius)
{
	s64 value, rise;
	unsigned int i;
	int ohms, ret;

	if (!sample || !millicelsius || !chtwc_adc_lpat_valid(p, count))
		return -EINVAL;
	if (index < 5 || index > 7)
		return -EOPNOTSUPP;
	/* Rail codes cannot establish a finite, in-range physical temperature. */
	if (!sample->count || sample->count == 0xfff)
		return -ENODATA;
	ret = chtwc_adc_resistance(index, sample, &ohms);
	if (ret)
		return ret;
	if (ohms > p[0].ohms || ohms < p[count - 1].ohms)
		return -ERANGE;
	for (i = 1; i < count; i++) {
		if (ohms < p[i].ohms)
			continue;
		/* Bound by validation: both products fit signed 64-bit. */
		rise = (s64)(p[i - 1].ohms - ohms) *
			(p[i].decikelvin - p[i - 1].decikelvin) * 100;
		value = (s64)p[i - 1].decikelvin * 100 +
			div_s64(rise, p[i - 1].ohms - p[i].ohms);
		*millicelsius = value + ABSOLUTE_ZERO_MILLICELSIUS;
		return 0;
	}
	return -ERANGE;
}

#endif /* INTEL_CHTWC_ADC_LPAT_H */
