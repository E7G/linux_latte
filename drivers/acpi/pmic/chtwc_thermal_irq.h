/* SPDX-License-Identifier: GPL-2.0-only */
/* Board ALERT capture/notification protocol; no hardware enable policy. */
#ifndef CHTWC_THERMAL_IRQ_H
#define CHTWC_THERMAL_IRQ_H

#include <linux/errno.h>
#include <linux/types.h>

#define CHTWC_THERMAL_BOARD_IRQS 0x77
#define CHTWC_THERMAL_STATUS 0x6e04
#define CHTWC_THERMAL_LEVELS 0x4f19

struct chtwc_thermal_event {
	u8 pending;
	u8 levels;
};

/* Caller holds a short queue-only spinlock, NEVER the ADC/owner mutex. */
struct chtwc_thermal_pending {
	struct chtwc_thermal_event event;
	bool stopping;
};

/* Coalesced latest level per pending bit, NOT a count/history of crossings. */
static inline int chtwc_thermal_record(struct chtwc_thermal_pending *queue,
		unsigned int pending, unsigned int levels)
{
	if (!queue || pending & ~CHTWC_THERMAL_BOARD_IRQS)
		return -EINVAL;
	if (queue->stopping)
		return -ESHUTDOWN;
	queue->event.levels = (queue->event.levels & ~pending) | (levels & pending);
	queue->event.pending |= pending;
	return 0;
}

/* Called under the same queue spinlock; consumer processes copy after unlock. */
static inline bool chtwc_thermal_take(struct chtwc_thermal_pending *queue,
		struct chtwc_thermal_event *event)
{
	if (!queue || !event || !queue->event.pending)
		return false;
	*event = queue->event;
	queue->event.pending = 0;
	queue->event.levels = 0;
	return true;
}

struct chtwc_thermal_irq_io {
	void *context;
	int (*read)(void *, unsigned int, unsigned int *);
	int (*write)(void *, unsigned int, unsigned int);
	/* Bounded immutable copy + schedule_work; no allocation or owner mutex. */
	int (*record)(void *, unsigned int, unsigned int);
};

/*
 * Nested THRM handler: never waits for ADC ownership or calls AML/thermal core.
 * Record BEFORE W1C: a write returning an error may still have cleared status.
 * On ack failure the snapshot remains queued (later delivery may be duplicate).
 * Returns 1 if captured, 0 if no owned pending source, negative errno on error.
 * Capturing only six board bits does not establish sole ownership of the parent
 * THRM source: other thermal sources MUST have an owner before enabling it.
 */
static inline int chtwc_thermal_capture(struct chtwc_thermal_irq_io *io)
{
	unsigned int status, pending, levels;
	int ret;

	if (!io || !io->read || !io->write || !io->record)
		return -EINVAL;
	ret = io->read(io->context, CHTWC_THERMAL_STATUS, &status);
	if (ret)
		return ret;
	pending = status & CHTWC_THERMAL_BOARD_IRQS;
	if (!pending)
		return 0;
	ret = io->read(io->context, CHTWC_THERMAL_LEVELS, &levels);
	if (ret)
		return ret;
	ret = io->record(io->context, pending, levels & pending);
	if (ret)
		return ret;
	ret = io->write(io->context, CHTWC_THERMAL_STATUS, pending);
	return ret ? ret : 1;
}

#endif
