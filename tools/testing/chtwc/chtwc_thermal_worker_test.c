// SPDX-License-Identifier: GPL-2.0-only
/* Real kernel workqueue tests; no PMIC, platform device or IRQ registration. */
#include <kunit/test.h>
#include <linux/completion.h>
#include <linux/kthread.h>
#include <linux/module.h>
#include <linux/sched/task.h>

#include "chtwc_thermal_worker.h"

struct worker_fixture {
	struct chtwc_thermal_worker worker;
	struct mutex owner;
	struct completion entered[4];
	struct completion notified[4];
	struct completion release;
	struct completion stop_entered;
	struct completion stop_done;
	struct chtwc_thermal_event events[4];
	struct task_struct *stopper;
	atomic_t calls;
	bool block_first;
	bool owner_held;
};

static void worker_notify(void *context, const struct chtwc_thermal_event *event)
{
	struct worker_fixture *fixture = context;
	int index = atomic_inc_return(&fixture->calls) - 1;

	if (index >= ARRAY_SIZE(fixture->events))
		return;
	fixture->events[index] = *event;
	complete(&fixture->entered[index]);
	if (!index && fixture->block_first)
		wait_for_completion_timeout(&fixture->release, msecs_to_jiffies(2000));
	/* Represents thermal refresh acquiring the ADC owner itself. */
	mutex_lock(&fixture->owner);
	mutex_unlock(&fixture->owner);
	complete(&fixture->notified[index]);
}

static void worker_cleanup(void *context)
{
	struct worker_fixture *fixture = context;

	if (fixture->owner_held) {
		mutex_unlock(&fixture->owner);
		fixture->owner_held = false;
	}
	complete_all(&fixture->release);
	chtwc_thermal_worker_stop(&fixture->worker);
	/* Keep fixture lifetime safe even when the negative control breaks stop. */
	flush_work(&fixture->worker.work);
	if (fixture->stopper) {
		kthread_stop(fixture->stopper);
		put_task_struct(fixture->stopper);
	}
}

static struct worker_fixture *worker_fixture_create(struct kunit *test)
{
	struct worker_fixture *fixture;
	int index, ret;

	fixture = kunit_kzalloc(test, sizeof(*fixture), GFP_KERNEL);
	if (!fixture)
		return NULL;
	mutex_init(&fixture->owner);
	for (index = 0; index < ARRAY_SIZE(fixture->entered); index++) {
		init_completion(&fixture->entered[index]);
		init_completion(&fixture->notified[index]);
	}
	init_completion(&fixture->release);
	init_completion(&fixture->stop_entered);
	init_completion(&fixture->stop_done);
	atomic_set(&fixture->calls, 0);
	ret = chtwc_thermal_worker_init(&fixture->worker, fixture, worker_notify);
	if (ret)
		return NULL;
	ret = kunit_add_action_or_reset(test, worker_cleanup, fixture);
	return ret ? NULL : fixture;
}

static void worker_restart_test(struct kunit *test)
{
	struct worker_fixture *fixture = worker_fixture_create(test);
	unsigned long done;

	KUNIT_ASSERT_NOT_NULL(test, fixture);
	KUNIT_EXPECT_EQ(test, chtwc_thermal_worker_record(&fixture->worker, 1, 1),
			-ESHUTDOWN);
	chtwc_thermal_worker_stop(&fixture->worker);
	chtwc_thermal_worker_start(&fixture->worker);
	chtwc_thermal_worker_start(&fixture->worker);
	KUNIT_ASSERT_EQ(test, chtwc_thermal_worker_record(&fixture->worker, 1, 1), 0);
	done = wait_for_completion_timeout(&fixture->notified[0], msecs_to_jiffies(2000));
	KUNIT_ASSERT_NE(test, done, 0UL);
	chtwc_thermal_worker_stop(&fixture->worker);
	chtwc_thermal_worker_stop(&fixture->worker);
	KUNIT_EXPECT_EQ(test, chtwc_thermal_worker_record(&fixture->worker, 2, 2),
			-ESHUTDOWN);
	KUNIT_EXPECT_EQ(test, atomic_read(&fixture->calls), 1);
	chtwc_thermal_worker_start(&fixture->worker);
	KUNIT_ASSERT_EQ(test, chtwc_thermal_worker_record(&fixture->worker, 4, 0), 0);
	done = wait_for_completion_timeout(&fixture->notified[1], msecs_to_jiffies(2000));
	KUNIT_ASSERT_NE(test, done, 0UL);
	chtwc_thermal_worker_stop(&fixture->worker);
	KUNIT_EXPECT_EQ(test, atomic_read(&fixture->calls), 2);
	KUNIT_EXPECT_EQ(test, fixture->events[1].pending, (u8)4);
	KUNIT_EXPECT_EQ(test, fixture->events[1].levels, (u8)0);
}

static void worker_adc_owner_test(struct kunit *test)
{
	struct worker_fixture *fixture = worker_fixture_create(test);
	unsigned long entered, done;

	KUNIT_ASSERT_NOT_NULL(test, fixture);
	chtwc_thermal_worker_start(&fixture->worker);
	mutex_lock(&fixture->owner);
	fixture->owner_held = true;
	/* Producer must return while callback waits for this same owner. */
	KUNIT_EXPECT_EQ(test, chtwc_thermal_worker_record(&fixture->worker, 1, 1), 0);
	entered = wait_for_completion_timeout(&fixture->entered[0], msecs_to_jiffies(2000));
	KUNIT_EXPECT_NE(test, entered, 0UL);
	KUNIT_EXPECT_FALSE(test, completion_done(&fixture->notified[0]));
	mutex_unlock(&fixture->owner);
	fixture->owner_held = false;
	done = wait_for_completion_timeout(&fixture->notified[0], msecs_to_jiffies(2000));
	KUNIT_ASSERT_NE(test, done, 0UL);
	chtwc_thermal_worker_stop(&fixture->worker);
}

static int worker_stopper(void *context)
{
	struct worker_fixture *fixture = context;

	complete(&fixture->stop_entered);
	chtwc_thermal_worker_stop(&fixture->worker);
	complete(&fixture->stop_done);
	return 0;
}

static void worker_stop_running_test(struct kunit *test)
{
	struct worker_fixture *fixture = worker_fixture_create(test);
	unsigned long entered, done;

	KUNIT_ASSERT_NOT_NULL(test, fixture);
	fixture->block_first = true;
	chtwc_thermal_worker_start(&fixture->worker);
	KUNIT_ASSERT_EQ(test, chtwc_thermal_worker_record(&fixture->worker, 1, 1), 0);
	entered = wait_for_completion_timeout(&fixture->entered[0], msecs_to_jiffies(2000));
	KUNIT_ASSERT_NE(test, entered, 0UL);
	fixture->stopper = kthread_create(worker_stopper, fixture, "chtwc-kunit-stop");
	if (IS_ERR(fixture->stopper)) {
		fixture->stopper = NULL;
		KUNIT_FAIL(test, "could not start stop thread");
		return;
	}
	get_task_struct(fixture->stopper);
	wake_up_process(fixture->stopper);
	entered = wait_for_completion_timeout(&fixture->stop_entered, msecs_to_jiffies(2000));
	KUNIT_ASSERT_NE(test, entered, 0UL);
	done = wait_for_completion_timeout(&fixture->stop_done, msecs_to_jiffies(20));
	KUNIT_EXPECT_EQ(test, done, 0UL);
	complete_all(&fixture->release);
	done = wait_for_completion_timeout(&fixture->stop_done, msecs_to_jiffies(2000));
	KUNIT_ASSERT_NE(test, done, 0UL);
	KUNIT_EXPECT_EQ(test, chtwc_thermal_worker_record(&fixture->worker, 1, 0),
			-ESHUTDOWN);
	KUNIT_EXPECT_EQ(test, atomic_read(&fixture->calls), 1);
}

static void worker_coalesce_running_test(struct kunit *test)
{
	struct worker_fixture *fixture = worker_fixture_create(test);
	unsigned long entered, done;

	KUNIT_ASSERT_NOT_NULL(test, fixture);
	fixture->block_first = true;
	chtwc_thermal_worker_start(&fixture->worker);
	KUNIT_ASSERT_EQ(test, chtwc_thermal_worker_record(&fixture->worker, 0x10, 0x10), 0);
	entered = wait_for_completion_timeout(&fixture->entered[0], msecs_to_jiffies(2000));
	KUNIT_ASSERT_NE(test, entered, 0UL);
	KUNIT_ASSERT_EQ(test, chtwc_thermal_worker_record(&fixture->worker, 1, 1), 0);
	KUNIT_ASSERT_EQ(test, chtwc_thermal_worker_record(&fixture->worker, 2, 2), 0);
	KUNIT_ASSERT_EQ(test, chtwc_thermal_worker_record(&fixture->worker, 1, 0), 0);
	complete_all(&fixture->release);
	done = wait_for_completion_timeout(&fixture->notified[1], msecs_to_jiffies(2000));
	KUNIT_ASSERT_NE(test, done, 0UL);
	chtwc_thermal_worker_stop(&fixture->worker);
	KUNIT_EXPECT_EQ(test, atomic_read(&fixture->calls), 2);
	KUNIT_EXPECT_EQ(test, fixture->events[1].pending, (u8)3);
	KUNIT_EXPECT_EQ(test, fixture->events[1].levels, (u8)2);
}

static struct kunit_case worker_cases[] = {
	KUNIT_CASE(worker_restart_test),
	KUNIT_CASE(worker_adc_owner_test),
	KUNIT_CASE(worker_stop_running_test),
	KUNIT_CASE(worker_coalesce_running_test),
	{}
};

static struct kunit_suite worker_suite = {
	.name = "chtwc-thermal-worker",
	.test_cases = worker_cases,
};
kunit_test_suite(worker_suite);

MODULE_LICENSE("GPL");
