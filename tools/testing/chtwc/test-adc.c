// SPDX-License-Identifier: GPL-2.0-only
/* Tests the same protocol code included by the actual IIO driver. */
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#define current get_current()
#include "intel-chtwc-adc-core.h"

struct mock {
	struct chtwc_adc_io io;
	unsigned char regs[65536];
	unsigned int calls, fail_call, writes, arms, disarms, faults, idle_calls;
	unsigned int high_reads, low_reads, unstable, expected, high_reg;
	unsigned int request_value, acked, wait_error, arm_error, disarm_error;
};

static int failure(struct mock *m)
{
	return ++m->calls == m->fail_call ? -EREMOTEIO : 0;
}

static int mock_read(void *context, unsigned int reg, unsigned int *value)
{
	struct mock *m = context;
	int ret = failure(m);

	if (ret)
		return ret;
	assert(reg < 65536);
	*value = m->regs[reg];
	if (reg == m->high_reg) {
		m->high_reads++;
		if (m->unstable == 1)
			*value ^= (m->high_reads - 1) & 1;
		if (m->unstable == 3 && m->high_reads == 2)
			*value ^= 1;
	}
	if (reg == m->high_reg + 1) {
		m->low_reads++;
		if (m->unstable == 2)
			*value ^= m->low_reads & 1;
	}
	return 0;
}

static int mock_write(void *context, unsigned int reg, unsigned int value)
{
	struct mock *m = context;
	int ret = failure(m);

	/* A failing bus write may have reached hardware. */
	m->writes++;
	if (reg == CHTWC_ADC_IRQ_STATUS) {
		m->acked |= value;
		m->regs[reg] &= ~value;
	} else {
		assert(reg == CHTWC_ADC_REQUEST);
		m->request_value = value;
		m->regs[reg] = value | CHTWC_ADC_BUSY;
	}
	return ret;
}

static int mock_idle(void *context)
{
	struct mock *m = context;
	int ret = failure(m);

	m->idle_calls++;
	return ret ? ret : (m->regs[CHTWC_ADC_REQUEST] & CHTWC_ADC_BUSY ?
			    -ETIMEDOUT : 0);
}

static int mock_arm(void *context, unsigned int mask)
{
	struct mock *m = context;
	int ret = failure(m);

	m->arms++;
	m->expected = mask;
	m->regs[CHTWC_ADC_IRQ_MASK] &= ~mask;
	return ret ? ret : (m->arm_error ? -EIO : 0);
}

static int mock_wait(void *context)
{
	struct mock *m = context;
	int ret = failure(m);

	if (ret)
		return ret;
	if (m->wait_error)
		return -ETIMEDOUT;
	m->regs[CHTWC_ADC_REQUEST] &= ~CHTWC_ADC_BUSY;
	m->regs[CHTWC_ADC_IRQ_STATUS] |= m->expected;
	ret = chtwc_adc_capture_irq(&m->io, m->expected);
	return ret == 1 ? 0 : (ret ? ret : -ETIMEDOUT);
}

static int mock_disarm(void *context, unsigned int mask)
{
	struct mock *m = context;
	int ret = failure(m);

	m->disarms++;
	m->regs[CHTWC_ADC_IRQ_MASK] |= mask;
	return ret ? ret : (m->disarm_error ? -EIO : 0);
}

static void mock_fault(void *context)
{
	struct mock *m = context;

	m->faults++;
	m->regs[CHTWC_ADC_IRQ_MASK] |= CHTWC_ADC_OWNED_IRQS;
}

static void init(struct mock *m, unsigned int channel)
{
	memset(m, 0, sizeof(*m));
	m->io = (struct chtwc_adc_io) {
		m, mock_read, mock_write, mock_idle, mock_arm,
		mock_wait, mock_disarm, mock_fault,
	};
	m->regs[CHTWC_ADC_IRQ_MASK] = 0xff;
	m->high_reg = chtwc_adc_channels[channel].high_reg;
	m->regs[m->high_reg] = 0x13;
	m->regs[m->high_reg + 1] = 0x45;
}

int main(void)
{
	static struct mock m;
	struct chtwc_adc_sample sample;
	unsigned int channel, status, bit, checks = 0, total_calls, fail;
	int ret;

	assert(ARRAY_SIZE(chtwc_adc_channels) == 11);
	for (channel = 0; channel < ARRAY_SIZE(chtwc_adc_channels); channel++) {
		unsigned int mask = BIT(chtwc_adc_channels[channel].irq_bit);
		unsigned int other = mask == BIT(6) ? BIT(0) : BIT(6);

		init(&m, channel);
		m.regs[CHTWC_ADC_IRQ_STATUS] = other | CHTWC_ADC_TICK_IRQ | mask;
		assert(chtwc_adc_acquire(&m.io, channel, &sample) == 0);
		assert(sample.count == 0x345 && sample.selector == 1);
		assert(m.request_value == BIT(chtwc_adc_channels[channel].request_bit));
		assert(m.acked == mask);
		assert(m.regs[CHTWC_ADC_IRQ_STATUS] == (other | CHTWC_ADC_TICK_IRQ));
		assert(m.regs[CHTWC_ADC_IRQ_MASK] == 0xff);
		assert(m.arms == 1 && m.disarms == 1 && !m.faults && m.idle_calls == 2);
		assert(m.high_reads == 4 && m.low_reads == 2);
		total_calls = m.calls;
		checks++;
		for (fail = 1; fail <= total_calls; fail++) {
			init(&m, channel); m.fail_call = fail;
			sample = (struct chtwc_adc_sample) { 0xabcd, 0xef };
			ret = chtwc_adc_acquire(&m.io, channel, &sample);
			assert(ret == -EREMOTEIO || ret == -EUCLEAN);
			assert(sample.count == 0xabcd && sample.selector == 0xef);
			assert(m.disarms == m.arms);
			assert(m.regs[CHTWC_ADC_IRQ_MASK] == 0xff && m.faults <= 1);
			if (m.request_value && m.idle_calls < 2)
				assert(m.faults);
			checks++;
		}
	}
	for (bit = 0; bit < 8; bit++) {
		for (status = 0; status < 256; status++) {
			init(&m, 0); m.regs[CHTWC_ADC_IRQ_STATUS] = status;
			ret = chtwc_adc_capture_irq(&m.io, BIT(bit));
			assert(ret == !!(status & BIT(bit) & CHTWC_ADC_OWNED_IRQS));
			assert(m.acked == (status & BIT(bit) & CHTWC_ADC_OWNED_IRQS));
			assert(m.regs[CHTWC_ADC_IRQ_STATUS] == (status & ~m.acked));
			assert(m.writes == (unsigned int)ret);
			checks++;
		}
	}
	for (bit = 0; bit < 16; bit++) {
		init(&m, 5); m.regs[m.high_reg] = bit << 4;
		sample = (struct chtwc_adc_sample) { 0xabcd, 0xef };
		ret = chtwc_adc_acquire(&m.io, 5, &sample);
		if (!bit || bit == 9 || bit >= 12)
			assert(ret == -ENODATA && sample.count == 0xabcd);
		else
			assert(!ret && sample.count == 0x45 && sample.selector == bit);
		assert(!m.faults && m.disarms == 1);
		init(&m, 2); m.regs[m.high_reg] = bit << 4;
		assert(chtwc_adc_acquire(&m.io, 2, &sample) == 0);
		assert(sample.count == 0x45); /* Die is not an NTC. */
		checks += 2;
	}
	for (bit = 1; bit <= 3; bit++) {
		init(&m, 5); m.unstable = bit;
		sample = (struct chtwc_adc_sample) { 0xabcd, 0xef };
		ret = chtwc_adc_acquire(&m.io, 5, &sample);
		if (bit == 3)
			assert(!ret && sample.count == 0x345);
		else
			assert(ret == -EAGAIN && sample.count == 0xabcd);
		assert(m.high_reads <= 12 && m.low_reads <= 6 && m.disarms == 1);
		assert(!m.faults); checks++;
	}
	init(&m, 5); m.wait_error = 1;
	assert(chtwc_adc_acquire(&m.io, 5, &sample) == -ETIMEDOUT);
	assert(m.faults == 1 && m.disarms == 1); checks++;
	init(&m, 5); m.arm_error = 1;
	assert(chtwc_adc_acquire(&m.io, 5, &sample) == -EIO);
	assert(m.faults == 1 && m.disarms == 1 && !m.request_value); checks++;
	init(&m, 5); m.disarm_error = 1; sample.count = 0xabcd;
	assert(chtwc_adc_acquire(&m.io, 5, &sample) == -EUCLEAN);
	assert(m.faults == 1 && sample.count == 0xabcd); checks++;
	init(&m, 5); m.regs[CHTWC_ADC_REQUEST] = CHTWC_ADC_BUSY;
	assert(chtwc_adc_acquire(&m.io, 5, &sample) == -ETIMEDOUT);
	assert(m.faults == 1 && !m.writes && !m.arms && !m.disarms); checks++;
	init(&m, 5);
	assert(chtwc_adc_acquire(&m.io, 11, &sample) == -EINVAL);
	assert(chtwc_adc_acquire(&m.io, UINT32_MAX, &sample) == -EINVAL);
	assert(chtwc_adc_acquire(&m.io, 5, NULL) == -EINVAL);
	assert(!m.calls && !m.writes && !m.faults); checks += 3;
	/* Independent vendor table oracle: all 12-bit counts and source codes. */
	{
		const uint32_t factors[16] = {
			0, 260420, 130210, 65100, 32550, 16280,
			8140, 4070, 2030, 0, 260420, 130210, 0, 0, 0, 0,
		};
		unsigned int selector, count, index;
		int ohms, ret;

		for (index = 0; index < ARRAY_SIZE(chtwc_adc_channels); index++) {
			for (selector = 0; selector < 16; selector++) {
				for (count = 0; count < 4096; count++) {
					sample.count = count; sample.selector = selector;
					ohms = -12345;
					ret = chtwc_adc_resistance(index, &sample, &ohms);
					if (!(index == 1 || index == 3 || index == 4 ||
					      index == 5 || index == 6 || index == 7 || index == 8))
						assert(ret == -EOPNOTSUPP && ohms == -12345);
					else if (!factors[selector])
						assert(ret == -ENODATA && ohms == -12345);
					else
						assert(!ret && ohms == (int)((uint64_t)count * factors[selector] / 1000));
					checks++;
				}
			}
		}
		sample.count = 4096; sample.selector = 6; ohms = -12345;
		assert(chtwc_adc_resistance(5, &sample, &ohms) == -ERANGE && ohms == -12345);
		sample.count = 3000; sample.selector = 255;
		assert(chtwc_adc_resistance(5, &sample, &ohms) == -ENODATA && ohms == -12345);
		assert(chtwc_adc_resistance(11, &sample, &ohms) == -EINVAL);
		assert(chtwc_adc_resistance(UINT32_MAX, &sample, &ohms) == -EINVAL);
		assert(chtwc_adc_resistance(5, NULL, &ohms) == -EINVAL);
		assert(chtwc_adc_resistance(5, &sample, NULL) == -EINVAL);
		checks += 6;
	}
	printf("PASS %u real-core acquisition/IRQ/W1C/fault/stability/nominal-resistance cases\n", checks);
	return 0;
}
