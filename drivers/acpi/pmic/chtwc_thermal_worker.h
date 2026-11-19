/* SPDX-License-Identifier: GPL-2.0-only */
/* Kernel workqueue adapter; no PMIC/IRQ registration or hardware enables. */
#ifndef CHTWC_THERMAL_WORKER_H
#define CHTWC_THERMAL_WORKER_H

#include <linux/container_of.h>
#include <linux/mutex.h>
#include <linux/spinlock.h>
#include <linux/workqueue.h>

#include "chtwc_thermal_irq.h"

struct chtwc_thermal_worker {
	spinlock_t queue_lock;
	struct mutex lifecycle_lock;
	struct work_struct work;
	struct chtwc_thermal_pending queue;
	void *context;
	void (*notify)(void *, const struct chtwc_thermal_event *);
	bool active; /* lifecycle_lock only */
};

static void chtwc_thermal_worker_run(struct work_struct *work)
{
	struct chtwc_thermal_worker *worker =
		container_of(work, struct chtwc_thermal_worker, work);
	struct chtwc_thermal_event event;
	unsigned long flags;
	bool present;

	spin_lock_irqsave(&worker->queue_lock, flags);
	present = !worker->queue.stopping &&
		chtwc_thermal_take(&worker->queue, &event);
	spin_unlock_irqrestore(&worker->queue_lock, flags);
	/* No queue/owner/lifecycle locks across external callbacks. In particular,
	 * thermal-zone refresh may call IIO and acquire the ADC mutex itself.
	 */
	if (present)
		worker->notify(worker->context, &event);
}

/* Process context, before publishing to IRQ producers. Starts disabled. */
static inline int chtwc_thermal_worker_init(struct chtwc_thermal_worker *worker,
		void *context, void (*notify)(void *, const struct chtwc_thermal_event *))
{
	if (!worker || !notify)
		return -EINVAL;
	spin_lock_init(&worker->queue_lock);
	mutex_init(&worker->lifecycle_lock);
	INIT_WORK(&worker->work, chtwc_thermal_worker_run);
	worker->queue = (struct chtwc_thermal_pending){ .stopping = true };
	worker->context = context;
	worker->notify = notify;
	worker->active = false;
	disable_work(&worker->work);
	return 0;
}

/* Process context. Hardware owner must refresh state before enabling IRQs. */
static inline void chtwc_thermal_worker_start(struct chtwc_thermal_worker *worker)
{
	unsigned long flags;

	mutex_lock(&worker->lifecycle_lock);
	if (!worker->active) {
		enable_work(&worker->work);
		spin_lock_irqsave(&worker->queue_lock, flags);
		worker->queue.stopping = false;
		spin_unlock_irqrestore(&worker->queue_lock, flags);
		worker->active = true;
	}
	mutex_unlock(&worker->lifecycle_lock);
}

/* IRQ-compatible, no waits/allocations/owner mutex. Queue and schedule together
 * under queue_lock so stopping cannot leave an unsynchronized enqueue behind.
 */
static inline int chtwc_thermal_worker_record(void *context,
		unsigned int pending, unsigned int levels)
{
	struct chtwc_thermal_worker *worker = context;
	unsigned long flags;
	int ret;

	spin_lock_irqsave(&worker->queue_lock, flags);
	ret = chtwc_thermal_record(&worker->queue, pending, levels);
	if (!ret && pending)
		schedule_work(&worker->work);
	spin_unlock_irqrestore(&worker->queue_lock, flags);
	return ret;
}

/*
 * Process context, NEVER from notify or while holding a lock notify may need.
 * Hardware owner must mask/synchronize IRQ producers before final destruction;
 * stop itself rejects further records but cannot extend a producer's lifetime.
 * No callback is running after return. Undelivered snapshots are discarded;
 * resume must refresh current hardware state rather than replay stale events.
 */
static inline void chtwc_thermal_worker_stop(struct chtwc_thermal_worker *worker)
{
	unsigned long flags;

	mutex_lock(&worker->lifecycle_lock);
	if (worker->active) {
		spin_lock_irqsave(&worker->queue_lock, flags);
		worker->queue.stopping = true;
		spin_unlock_irqrestore(&worker->queue_lock, flags);
		disable_work_sync(&worker->work);
		spin_lock_irqsave(&worker->queue_lock, flags);
		worker->queue.event = (struct chtwc_thermal_event){0};
		spin_unlock_irqrestore(&worker->queue_lock, flags);
		worker->active = false;
	}
	mutex_unlock(&worker->lifecycle_lock);
}

#endif
