/* SPDX-License-Identifier: GPL-2.0-only */
/*
 * CHT Whiskey Cove acquisition protocol, derived from Intel's GPLv2 Android
 * definitions: latte-dev/android_kernel_xiaomi_latte d2afb1de9a76.
 * No thermistor/die calibration or autonomous-monitor policy is implied.
 */
#ifndef INTEL_CHTWC_ADC_CORE_H
#define INTEL_CHTWC_ADC_CORE_H

#include <linux/errno.h>
#include <linux/kernel.h>
#include <linux/types.h>

#define CHTWC_ADC_REQUEST		0x4f02
#define CHTWC_ADC_BUSY		BIT(0)
#define CHTWC_ADC_IRQ_STATUS	0x6e08
#define CHTWC_ADC_IRQ_MASK	0x6e15
#define CHTWC_ADC_OWNED_IRQS	0x7f
#define CHTWC_ADC_TICK_IRQ	BIT(7)

struct chtwc_adc_channel {
	u16 high_reg;
	u8 request_bit;
	u8 irq_bit;
	bool thermistor;
};

/* Channel11 (VREF) aliases AGND in the vendor table without a proven mux. */
static const struct chtwc_adc_channel chtwc_adc_channels[] = {
	{ 0x4f03, 5, 0, false }, /* VBAT (VBUS in vendor channel enum) */
	{ 0x4f06, 4, 1, true  }, /* BATID */
	{ 0x4f42, 3, 2, false }, /* PMIC die: not an NTC */
	{ 0x4f15, 2, 3, true  }, /* BATTEMP0 */
	{ 0x4f17, 2, 3, true  }, /* BATTEMP1 */
	{ 0x4f38, 3, 2, true  }, /* SYSTEMP0 */
	{ 0x4f3a, 3, 2, true  }, /* SYSTEMP1 */
	{ 0x4f3c, 3, 2, true  }, /* SYSTEMP2 */
	{ 0x4f08, 1, 5, true  }, /* USBID */
	{ 0x4f13, 7, 6, false }, /* PEAK */
	{ 0x4f0a, 6, 4, false }, /* AGND */
};

struct chtwc_adc_sample {
	u16 count;
	u8 selector;
};

/*
 * Nominal resistance in ohms, matching the vendor OpRegion/ALERT ABI.
 * The legacy IIO path divides this by ten; do not copy that ten-ohm-unit ABI.
 * Count and current selector MUST come from the same completed acquisition.
 * This is not a calibrated temperature or the PMIC die transfer function.
 */
static inline int chtwc_adc_resistance(unsigned int index,
				       const struct chtwc_adc_sample *sample,
				       int *ohms)
{
	static const u32 factor[] = {
		0, 260420, 130210, 65100, 32550, 16280,
		8140, 4070, 2030, 0, 260420, 130210,
	};
	unsigned int selector;

	if (index >= ARRAY_SIZE(chtwc_adc_channels) || !sample || !ohms)
		return -EINVAL;
	if (!chtwc_adc_channels[index].thermistor)
		return -EOPNOTSUPP;
	if (sample->count > 0xfff)
		return -ERANGE;
	selector = sample->selector;
	if (selector >= ARRAY_SIZE(factor) || !factor[selector])
		return -ENODATA;
	/* Maximum intermediate4095*260420 fits u32; publish only on success. */
	*ohms = sample->count * factor[selector] / 1000;
	return 0;
}

/*
 * Caller serializes acquisition and PM/removal. arm/disarm own only the ADC
 * level1 virtual IRQ and selected level2 mask, never the physical parent IRQ.
 * disarm must synchronize the handler even if arm partially failed.
 */
struct chtwc_adc_io {
	void *context;
	int (*read)(void *context, unsigned int reg, unsigned int *value);
	int (*write)(void *context, unsigned int reg, unsigned int value);
	int (*wait_idle)(void *context);
	int (*arm)(void *context, unsigned int mask);
	int (*wait_done)(void *context);
	int (*disarm)(void *context, unsigned int mask);
	void (*fault)(void *context);
};

/* W1C: acknowledge only this transaction, never read/modify/write status. */
static inline int chtwc_adc_capture_irq(const struct chtwc_adc_io *io,
				       unsigned int expected)
{
	unsigned int status, pending;
	int ret;

	ret = io->read(io->context, CHTWC_ADC_IRQ_STATUS, &status);
	if (ret)
		return ret;
	pending = status & expected & CHTWC_ADC_OWNED_IRQS;
	if (!pending)
		return 0;
	ret = io->write(io->context, CHTWC_ADC_IRQ_STATUS, pending);
	return ret ? ret : 1;
}

/*
 * Two equal high/low/high observations, bounded retries. Stability check only:
 * NOT a documented hardware latch, freshness guarantee or proof against ABA.
 */
static inline int chtwc_adc_read_sample(const struct chtwc_adc_io *io,
				       const struct chtwc_adc_channel *channel,
				       struct chtwc_adc_sample *sample)
{
	unsigned int first, low, last, previous = 0;
	bool have_previous = false;
	int attempt, ret;

	for (attempt = 0; attempt < 6; attempt++) {
		ret = io->read(io->context, channel->high_reg, &first);
		if (ret)
			return ret;
		ret = io->read(io->context, channel->high_reg + 1, &low);
		if (ret)
			return ret;
		ret = io->read(io->context, channel->high_reg, &last);
		if (ret)
			return ret;
		if (first != last) {
			have_previous = false;
			continue;
		}
		first = (last << 8) | low;
		if (have_previous && first == previous) {
			u8 selector = last >> 4;

			if (channel->thermistor &&
			    (!selector || selector == 9 || selector >= 12))
				return -ENODATA;
			sample->count = first & 0xfff;
			sample->selector = selector;
			return 0;
		}
		previous = first;
		have_previous = true;
	}
	return -EAGAIN;
}

/* Publish a sample only after completion, hardware idle and IRQ cleanup. */
static inline int chtwc_adc_acquire(const struct chtwc_adc_io *io,
				   unsigned int index,
				   struct chtwc_adc_sample *sample)
{
	const struct chtwc_adc_channel *channel;
	struct chtwc_adc_sample result;
	bool uncertain = false;
	unsigned int mask;
	int ret, cleanup;

	if (index >= ARRAY_SIZE(chtwc_adc_channels) || !sample)
		return -EINVAL;
	channel = &chtwc_adc_channels[index];
	mask = BIT(channel->irq_bit);
	ret = io->wait_idle(io->context);
	if (ret)
		goto fault;
	ret = io->write(io->context, CHTWC_ADC_IRQ_STATUS, mask);
	if (ret)
		goto fault;
	ret = io->arm(io->context, mask);
	if (ret) {
		uncertain = true;
		goto disarm;
	}
	ret = io->write(io->context, CHTWC_ADC_REQUEST,
			BIT(channel->request_bit));
	if (ret) {
		uncertain = true; /* A failed write may have reached hardware. */
		goto disarm;
	}
	ret = io->wait_done(io->context);
	if (ret) {
		uncertain = true;
		goto disarm;
	}
	ret = io->wait_idle(io->context);
	if (ret) {
		uncertain = true;
		goto disarm;
	}
	ret = chtwc_adc_read_sample(io, channel, &result);
disarm:
	cleanup = io->disarm(io->context, mask);
	if (cleanup) {
		ret = -EUCLEAN;
		uncertain = true;
	}
	if (uncertain)
		goto fault;
	if (!ret)
		*sample = result;
	return ret;
fault:
	io->fault(io->context);
	return ret;
}

#endif
