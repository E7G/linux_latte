// SPDX-License-Identifier: GPL-2.0-only
/* Full-bank transport on real workqueues with a fake PMIC, never real I/O. */
#include <kunit/test.h>
#include <linux/completion.h>
#include <linux/kthread.h>
#include <linux/module.h>
#include <linux/sched/task.h>

#include "chtwc_thermal_transport.h"

struct transport_fixture;
struct transport_receiver {
	struct transport_fixture *fixture;
	unsigned int owner;
	atomic_t calls;
	struct completion done[3];
	struct chtwc_thermal_packet packets[3];
};

struct transport_fixture {
	struct chtwc_thermal_transport transport;
	struct transport_receiver receivers[CHTWC_THERMAL_OWNERS];
	u8 status[4], masks[4];
	unsigned int io_calls, writes, fail_at;
	bool apply_error, block_first;
	struct completion entered, release, stop_entered, stop_done;
	struct task_struct *stopper;
	int stop_result;
};

static int transport_read(void *context, unsigned int reg, unsigned int *value)
{
	struct transport_fixture *fixture = context;
	unsigned int bank;

	if (++fixture->io_calls == fixture->fail_at)
		return -ETIMEDOUT;
	for (bank = 0; bank < 4; bank++) {
		if (reg == chtwc_thermal_mask_regs[bank]) {
			*value = fixture->masks[bank];
			return 0;
		}
		if (reg == chtwc_thermal_status_regs[bank]) {
			*value = fixture->status[bank];
			return 0;
		}
	}
	return -EINVAL;
}

static int transport_write(void *context, unsigned int reg, unsigned int value)
{
	struct transport_fixture *fixture = context;
	unsigned long flags;
	unsigned int bank;
	bool fail = ++fixture->io_calls == fixture->fail_at;
	u64 recorded;

	spin_lock_irqsave(&fixture->transport.lock, flags);
	recorded = fixture->transport.sequence;
	spin_unlock_irqrestore(&fixture->transport.lock, flags);
	/* Snapshot must be durable before W1C, even if worker already took it. */
	if (!recorded)
		return -EPROTO;
	for (bank = 0; bank < 4; bank++) {
		if (reg != chtwc_thermal_status_regs[bank])
			continue;
		fixture->writes++;
		if (!fail || fixture->apply_error)
			fixture->status[bank] &= ~value;
		return fail ? -ETIMEDOUT : 0;
	}
	return -EINVAL;
}

static void transport_notify(void *context, const struct chtwc_thermal_packet *packet)
{
	struct transport_receiver *receiver = context;
	struct transport_fixture *fixture = receiver->fixture;
	int index = atomic_inc_return(&receiver->calls) - 1;

	if (index >= ARRAY_SIZE(receiver->packets))
		return;
	receiver->packets[index] = *packet;
	if (receiver->owner == CHTWC_THERMAL_BAT0 && !index && fixture->block_first) {
		complete(&fixture->entered);
		wait_for_completion_timeout(&fixture->release, msecs_to_jiffies(2000));
	}
	complete(&receiver->done[index]);
}

static void transport_cleanup(void *context)
{
	struct transport_fixture *fixture = context;

	complete_all(&fixture->release);
	chtwc_thermal_transport_stop(&fixture->transport);
	flush_work(&fixture->transport.work);
	if (fixture->stopper) {
		kthread_stop(fixture->stopper);
		put_task_struct(fixture->stopper);
	}
}

static struct transport_fixture *transport_create(struct kunit *test, unsigned int ready)
{
	struct transport_fixture *fixture;
	unsigned int owner, index;
	int ret;

	fixture = kunit_kzalloc(test, sizeof(*fixture), GFP_KERNEL);
	if (!fixture)
		return NULL;
	memset(fixture->masks, 255, sizeof(fixture->masks));
	init_completion(&fixture->entered);
	init_completion(&fixture->release);
	init_completion(&fixture->stop_entered);
	init_completion(&fixture->stop_done);
	ret = chtwc_thermal_transport_init(&fixture->transport, fixture,
					   transport_read, transport_write);
	if (ret)
		return NULL;
	ret = kunit_add_action_or_reset(test, transport_cleanup, fixture);
	if (ret)
		return NULL;
	for (owner = 0; owner < CHTWC_THERMAL_OWNERS; owner++) {
		struct transport_receiver *receiver = &fixture->receivers[owner];

		receiver->fixture = fixture;
		receiver->owner = owner;
		atomic_set(&receiver->calls, 0);
		for (index = 0; index < ARRAY_SIZE(receiver->done); index++)
			init_completion(&receiver->done[index]);
		if (ready & (1U << owner)) {
			ret = chtwc_thermal_transport_consumer(&fixture->transport, owner,
							 receiver, transport_notify);
			if (ret)
				return NULL;
		}
	}
	return fixture;
}

static void transport_shared_fanout_test(struct kunit *test)
{
	struct transport_fixture *fixture = transport_create(test, 0x30);
	unsigned int owner;

	KUNIT_ASSERT_NOT_NULL(test, fixture);
	fixture->masks[1] = 0xef;
	KUNIT_ASSERT_EQ(test, chtwc_thermal_transport_start(&fixture->transport), 0);
	KUNIT_EXPECT_EQ(test, chtwc_thermal_transport_consumer(&fixture->transport,
			CHTWC_THERMAL_BAT0, NULL, NULL), -EBUSY);
	fixture->status[1] = 0x30; /* Shared enabled bit10 plus masked latched bit20. */
	KUNIT_ASSERT_EQ(test, chtwc_thermal_transport_capture(&fixture->transport), 1);
	for (owner = CHTWC_THERMAL_BAT0; owner <= CHTWC_THERMAL_BAT1; owner++) {
		struct transport_receiver *receiver = &fixture->receivers[owner];

		KUNIT_ASSERT_NE(test, wait_for_completion_timeout(&receiver->done[0],
				msecs_to_jiffies(2000)), 0UL);
		KUNIT_EXPECT_EQ(test, receiver->packets[0].pending[1], (u8)0x10);
		KUNIT_EXPECT_EQ(test, receiver->packets[0].recipients, (u8)0x30);
		KUNIT_EXPECT_EQ(test, receiver->packets[0].sequence, 1ULL);
	}
	KUNIT_EXPECT_EQ(test, fixture->writes, 1U);
	KUNIT_EXPECT_EQ(test, fixture->status[1], (u8)0x20);
	KUNIT_EXPECT_EQ(test, chtwc_thermal_transport_stop(&fixture->transport), 0);
	KUNIT_EXPECT_EQ(test, chtwc_thermal_transport_consumer(&fixture->transport,
			CHTWC_THERMAL_BAT0, NULL, NULL), 0);
	KUNIT_EXPECT_EQ(test, chtwc_thermal_transport_start(&fixture->transport), -ENXIO);
}

static void transport_fault_snapshot_test(struct kunit *test)
{
	struct transport_fixture *fixture = transport_create(test, 1);
	struct transport_receiver *receiver;
	unsigned int calls;

	KUNIT_ASSERT_NOT_NULL(test, fixture);
	receiver = &fixture->receivers[0];
	fixture->masks[0] = 0xfe;
	KUNIT_ASSERT_EQ(test, chtwc_thermal_transport_start(&fixture->transport), 0);
	fixture->status[0] = 1;
	fixture->io_calls = 0;
	fixture->fail_at = 9; /* Eight reads followed by failed-but-applied W1C. */
	fixture->apply_error = true;
	KUNIT_ASSERT_EQ(test, chtwc_thermal_transport_capture(&fixture->transport), -ETIMEDOUT);
	KUNIT_ASSERT_NE(test, wait_for_completion_timeout(&receiver->done[0],
			msecs_to_jiffies(2000)), 0UL);
	KUNIT_EXPECT_EQ(test, receiver->packets[0].pending[0], (u8)1);
	KUNIT_EXPECT_EQ(test, fixture->status[0], (u8)0);
	calls = fixture->io_calls;
	KUNIT_EXPECT_EQ(test, chtwc_thermal_transport_capture(&fixture->transport), -EIO);
	KUNIT_EXPECT_EQ(test, fixture->io_calls, calls);
	KUNIT_EXPECT_EQ(test, chtwc_thermal_transport_start(&fixture->transport), -EIO);
	KUNIT_ASSERT_EQ(test, chtwc_thermal_transport_stop(&fixture->transport), 0);
	fixture->fail_at = 0;
	KUNIT_ASSERT_EQ(test, chtwc_thermal_transport_start(&fixture->transport), 0);
	KUNIT_EXPECT_EQ(test, chtwc_thermal_transport_capture(&fixture->transport), 0);
}

static void transport_read_faults_test(struct kunit *test)
{
	unsigned int fail;

	for (fail = 1; fail <= 8; fail++) {
		struct transport_fixture *fixture = transport_create(test, 127);

		KUNIT_ASSERT_NOT_NULL(test, fixture);
		fixture->masks[0] = 0xfe;
		KUNIT_ASSERT_EQ(test, chtwc_thermal_transport_start(&fixture->transport), 0);
		fixture->io_calls = 0;
		fixture->fail_at = fail;
		KUNIT_EXPECT_EQ(test, chtwc_thermal_transport_capture(&fixture->transport),
				-ETIMEDOUT);
		KUNIT_EXPECT_EQ(test, fixture->writes, 0U);
		KUNIT_EXPECT_EQ(test, fixture->transport.sequence, 0ULL);
		KUNIT_EXPECT_EQ(test, chtwc_thermal_transport_stop(&fixture->transport), 0);
	}
}

static void transport_board_only_ownership_test(struct kunit *test)
{
	struct transport_fixture *fixture = transport_create(test, 7);

	KUNIT_ASSERT_NOT_NULL(test, fixture);
	KUNIT_EXPECT_EQ(test, chtwc_thermal_transport_start(&fixture->transport), -ENODATA);
	fixture->masks[0] = 0xfe;
	fixture->masks[1] = 0xef;
	KUNIT_EXPECT_EQ(test, chtwc_thermal_transport_start(&fixture->transport), -ENXIO);
	KUNIT_EXPECT_EQ(test, fixture->writes, 0U);

	fixture->masks[1] = 0xff;
	KUNIT_ASSERT_EQ(test, chtwc_thermal_transport_start(&fixture->transport), 0);
	fixture->status[0] = 0x01;
	fixture->status[1] = 0x10;
	KUNIT_EXPECT_EQ(test, chtwc_thermal_transport_capture(&fixture->transport), 1);
	KUNIT_EXPECT_EQ(test, fixture->writes, 1U);
	KUNIT_EXPECT_EQ(test, fixture->status[1], (u8)0x10);

	/* Firmware enables the shared battery source after activation. */
	fixture->masks[1] = 0xef;
	fixture->status[0] = 0x01;
	KUNIT_EXPECT_EQ(test, chtwc_thermal_transport_capture(&fixture->transport), -ENXIO);
	KUNIT_EXPECT_EQ(test, fixture->writes, 1U);
	KUNIT_EXPECT_EQ(test, fixture->status[0], (u8)0x01);
	KUNIT_EXPECT_EQ(test, fixture->status[1], (u8)0x10);
	KUNIT_ASSERT_EQ(test, chtwc_thermal_transport_stop(&fixture->transport), 0);
	KUNIT_EXPECT_EQ(test, chtwc_thermal_transport_start(&fixture->transport), -ENXIO);
}

static int transport_stopper(void *context)
{
	struct transport_fixture *fixture = context;

	complete(&fixture->stop_entered);
	fixture->stop_result = chtwc_thermal_transport_stop(&fixture->transport);
	complete(&fixture->stop_done);
	return 0;
}

static void transport_stop_drains_critical_test(struct kunit *test)
{
	struct transport_fixture *fixture = transport_create(test, 0x30);
	unsigned int owner;
	unsigned long done;

	KUNIT_ASSERT_NOT_NULL(test, fixture);
	fixture->masks[1] = 0xef;
	fixture->block_first = true;
	KUNIT_ASSERT_EQ(test, chtwc_thermal_transport_start(&fixture->transport), 0);
	fixture->status[1] = 0x10;
	KUNIT_ASSERT_EQ(test, chtwc_thermal_transport_capture(&fixture->transport), 1);
	KUNIT_ASSERT_NE(test, wait_for_completion_timeout(&fixture->entered,
			msecs_to_jiffies(2000)), 0UL);
	fixture->status[1] = 0x10;
	KUNIT_ASSERT_EQ(test, chtwc_thermal_transport_capture(&fixture->transport), 1);
	fixture->stopper = kthread_create(transport_stopper, fixture, "chtwc-transport-stop");
	if (IS_ERR(fixture->stopper)) {
		fixture->stopper = NULL;
		KUNIT_FAIL(test, "could not start stop thread");
		return;
	}
	get_task_struct(fixture->stopper);
	wake_up_process(fixture->stopper);
	KUNIT_ASSERT_NE(test, wait_for_completion_timeout(&fixture->stop_entered,
			msecs_to_jiffies(2000)), 0UL);
	done = wait_for_completion_timeout(&fixture->stop_done, msecs_to_jiffies(20));
	KUNIT_EXPECT_EQ(test, done, 0UL);
	complete_all(&fixture->release);
	KUNIT_ASSERT_NE(test, wait_for_completion_timeout(&fixture->stop_done,
			msecs_to_jiffies(2000)), 0UL);
	KUNIT_EXPECT_EQ(test, fixture->stop_result, 0);
	for (owner = CHTWC_THERMAL_BAT0; owner <= CHTWC_THERMAL_BAT1; owner++) {
		KUNIT_EXPECT_EQ(test, atomic_read(&fixture->receivers[owner].calls), 2);
		KUNIT_EXPECT_EQ(test, fixture->receivers[owner].packets[1].sequence, 2ULL);
	}
	KUNIT_EXPECT_EQ(test, chtwc_thermal_transport_capture(&fixture->transport), -ESHUTDOWN);
}

static struct kunit_case transport_cases[] = {
	KUNIT_CASE(transport_shared_fanout_test),
	KUNIT_CASE(transport_fault_snapshot_test),
	KUNIT_CASE(transport_read_faults_test),
	KUNIT_CASE(transport_board_only_ownership_test),
	KUNIT_CASE(transport_stop_drains_critical_test),
	{}
};

static struct kunit_suite transport_suite = {
	.name = "chtwc-thermal-transport",
	.test_cases = transport_cases,
};
kunit_test_suite(transport_suite);

MODULE_LICENSE("GPL");
