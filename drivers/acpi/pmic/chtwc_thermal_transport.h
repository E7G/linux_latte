/* SPDX-License-Identifier: GPL-2.0-only */
/* Full-bank capture/fanout transport; does not bind or enable hardware. */
#ifndef CHTWC_THERMAL_TRANSPORT_H
#define CHTWC_THERMAL_TRANSPORT_H

#include <linux/container_of.h>
#include <linux/mutex.h>
#include <linux/spinlock.h>
#include <linux/workqueue.h>

#include "chtwc_thermal_route.h"

/* Coalesced raw pending bits, not levels, edge counts or temperatures. */
struct chtwc_thermal_packet {
	u8 pending[4];
	u8 recipients;
	u64 sequence;
};

struct chtwc_thermal_consumer {
	void *context;
	void (*notify)(void *, const struct chtwc_thermal_packet *);
};

struct chtwc_thermal_transport {
	spinlock_t lock;
	struct mutex lifecycle;
	struct work_struct work;
	struct chtwc_thermal_consumer consumers[CHTWC_THERMAL_OWNERS];
	struct chtwc_thermal_packet pending;
	void *context;
	int (*read)(void *, unsigned int, unsigned int *);
	int (*write)(void *, unsigned int, unsigned int);
	u64 sequence;
	u8 ready;
	bool stopping, faulted;
	bool active; /* lifecycle only */
};

static void chtwc_thermal_transport_run(struct work_struct *work)
{
	struct chtwc_thermal_transport *transport =
		container_of(work, struct chtwc_thermal_transport, work);
	struct chtwc_thermal_packet packet;
	unsigned long flags;
	unsigned int owner;

	spin_lock_irqsave(&transport->lock, flags);
	packet = transport->pending;
	transport->pending = (struct chtwc_thermal_packet){0};
	spin_unlock_irqrestore(&transport->lock, flags);
	/* Consumer slots cannot change until stop has drained accepted packets.
	 * Deliver every recipient even when stop starts during this fanout.
	 */
	for (owner = 0; owner < CHTWC_THERMAL_OWNERS; owner++)
		if (packet.recipients & (1U << owner))
			transport->consumers[owner].notify(
				transport->consumers[owner].context, &packet);
}

static inline int chtwc_thermal_transport_init(struct chtwc_thermal_transport *transport,
		void *context, int (*read)(void *, unsigned int, unsigned int *),
		int (*write)(void *, unsigned int, unsigned int))
{
	if (!transport || !read || !write)
		return -EINVAL;
	*transport = (struct chtwc_thermal_transport){0};
	spin_lock_init(&transport->lock);
	mutex_init(&transport->lifecycle);
	INIT_WORK(&transport->work, chtwc_thermal_transport_run);
	transport->context = context;
	transport->read = read;
	transport->write = write;
	transport->stopping = true;
	disable_work(&transport->work);
	return 0;
}

/* Process context, inactive/drained only. NULL notify unregisters a slot.
 * Never call lifecycle APIs from notify or with a callback-needed lock held.
 */
static inline int chtwc_thermal_transport_consumer(struct chtwc_thermal_transport *transport,
		unsigned int owner, void *context,
		void (*notify)(void *, const struct chtwc_thermal_packet *))
{
	unsigned long flags;
	int ret = 0;

	if (owner >= CHTWC_THERMAL_OWNERS)
		return -EINVAL;
	mutex_lock(&transport->lifecycle);
	spin_lock_irqsave(&transport->lock, flags);
	if (transport->active || transport->pending.recipients)
		ret = -EBUSY;
	else {
		transport->consumers[owner] = (struct chtwc_thermal_consumer){context, notify};
		if (notify)
			transport->ready |= 1U << owner;
		else
			transport->ready &= ~(1U << owner);
	}
	spin_unlock_irqrestore(&transport->lock, flags);
	mutex_unlock(&transport->lifecycle);
	return ret;
}

/* Owner must keep IRQ producers quiescent and serialize hardware mask writers
 * during start. Checks masks; never changes a mask or monitor enable itself.
 */
static inline int chtwc_thermal_transport_start(struct chtwc_thermal_transport *transport)
{
	u8 masks[4];
	unsigned int bank, value;
	unsigned long flags;
	int ret = 0;

	mutex_lock(&transport->lifecycle);
	if (transport->active) {
		spin_lock_irqsave(&transport->lock, flags);
		ret = transport->faulted ? -EIO : 0;
		spin_unlock_irqrestore(&transport->lock, flags);
		goto unlock;
	}
	if (transport->pending.recipients) {
		ret = -EUCLEAN;
		goto unlock;
	}
	for (bank = 0; bank < 4; bank++) {
		ret = transport->read(transport->context, chtwc_thermal_mask_regs[bank], &value);
		if (ret)
			goto unlock;
		masks[bank] = value;
	}
	ret = chtwc_thermal_ownership_ready(masks, transport->ready);
	if (ret)
		goto unlock;
	enable_work(&transport->work);
	spin_lock_irqsave(&transport->lock, flags);
	transport->faulted = false;
	transport->stopping = false;
	spin_unlock_irqrestore(&transport->lock, flags);
	transport->active = true;
unlock:
	mutex_unlock(&transport->lifecycle);
	return ret;
}

/* Nested threaded-IRQ context, serialized by the single hardware IRQ owner.
 * No owner/lifecycle mutex. Snapshot masks/status, queue immutable fanout to
 * ALL recipients, then W1C once per bank. On ack error the copy survives.
 * The caller must quarantine/recover its owned IRQ on negative return; this
 * layer never disables another protection or touches a parent mask itself.
 */
static inline int chtwc_thermal_transport_capture(struct chtwc_thermal_transport *transport)
{
	struct chtwc_thermal_route plan;
	u8 masks[4], status[4], ready;
	unsigned int bank, value;
	unsigned long flags;
	int ret;

	spin_lock_irqsave(&transport->lock, flags);
	ret = transport->stopping ? -ESHUTDOWN : transport->faulted ? -EIO : 0;
	ready = transport->ready;
	spin_unlock_irqrestore(&transport->lock, flags);
	if (ret)
		return ret;
	for (bank = 0; bank < 4; bank++) {
		ret = transport->read(transport->context, chtwc_thermal_mask_regs[bank], &value);
		if (ret)
			goto fault;
		masks[bank] = value;
		ret = transport->read(transport->context, chtwc_thermal_status_regs[bank], &value);
		if (ret)
			goto fault;
		status[bank] = value;
	}
	ret = chtwc_thermal_plan(status, masks, ready, &plan);
	if (ret)
		goto fault;
	if (!plan.recipients)
		return 0;
	spin_lock_irqsave(&transport->lock, flags);
	if (transport->stopping) {
		spin_unlock_irqrestore(&transport->lock, flags);
		return -ESHUTDOWN;
	}
	for (bank = 0; bank < 4; bank++)
		transport->pending.pending[bank] |= plan.acknowledge[bank];
	transport->pending.recipients |= plan.recipients;
	transport->pending.sequence = ++transport->sequence;
	schedule_work(&transport->work);
	spin_unlock_irqrestore(&transport->lock, flags);
	for (bank = 0; bank < 4; bank++) {
		if (!plan.acknowledge[bank])
			continue;
		ret = transport->write(transport->context, chtwc_thermal_status_regs[bank],
				       plan.acknowledge[bank]);
		if (ret)
			goto fault;
	}
	return 1;
fault:
	spin_lock_irqsave(&transport->lock, flags);
	transport->faulted = true;
	spin_unlock_irqrestore(&transport->lock, flags);
	return ret;
}

/* Owner masks/synchronizes IRQ producers BEFORE stop/destruction; stopping
 * alone cannot extend an in-flight producer's memory lifetime. No callback-
 * needed mutex may be held here. Drain accepted fanout BEFORE disabling work,
 * otherwise a queued critical event could be canceled after its W1C ack.
 */
static inline int chtwc_thermal_transport_stop(struct chtwc_thermal_transport *transport)
{
	unsigned long flags;
	int ret = 0;

	mutex_lock(&transport->lifecycle);
	if (transport->active) {
		spin_lock_irqsave(&transport->lock, flags);
		transport->stopping = true;
		spin_unlock_irqrestore(&transport->lock, flags);
		flush_work(&transport->work);
		disable_work_sync(&transport->work);
		spin_lock_irqsave(&transport->lock, flags);
		if (transport->pending.recipients) {
			transport->faulted = true;
			ret = -EUCLEAN;
		}
		spin_unlock_irqrestore(&transport->lock, flags);
		transport->active = false;
	}
	mutex_unlock(&transport->lifecycle);
	return ret;
}

#endif
