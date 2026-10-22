// SPDX-License-Identifier: GPL-2.0
/* Test real kernel atomic primitives on private counters, no hardware I/O. */
#include <linux/atomic.h>
#include <linux/init.h>
#include <linux/limits.h>
#include <linux/module.h>

#define CHECK(condition) do { \
	if (!(condition)) { \
		pr_err("mipad2_atomic_wrap: FAIL line %d\n", __LINE__); \
		return -EINVAL; \
	} \
} while (0)

#define BOUNDARIES(type, prefix, minimum, maximum) do { \
	type v; \
	prefix##_set(&v, maximum); \
	CHECK(prefix##_add_return(1, &v) == minimum); \
	CHECK(prefix##_read(&v) == minimum); \
	CHECK(prefix##_add_return(-1, &v) == maximum); \
	CHECK(prefix##_read(&v) == maximum); \
	CHECK(prefix##_fetch_add_unless(&v, 1, 0) == maximum); \
	CHECK(prefix##_read(&v) == minimum); \
	CHECK(prefix##_fetch_add_unless(&v, -1, 0) == minimum); \
	CHECK(prefix##_read(&v) == maximum); \
	CHECK(prefix##_fetch_add_unless(&v, 1, maximum) == maximum); \
	CHECK(prefix##_read(&v) == maximum); \
	prefix##_set(&v, 0); \
	CHECK(prefix##_fetch_add_unless(&v, 1, 0) == 0); \
	CHECK(prefix##_read(&v) == 0); \
	prefix##_set(&v, maximum); \
	CHECK(prefix##_inc_unless_negative(&v)); \
	CHECK(prefix##_read(&v) == minimum); \
	CHECK(!prefix##_inc_unless_negative(&v)); \
	CHECK(prefix##_read(&v) == minimum); \
	CHECK(prefix##_dec_unless_positive(&v)); \
	CHECK(prefix##_read(&v) == maximum); \
	CHECK(!prefix##_dec_unless_positive(&v)); \
	CHECK(prefix##_read(&v) == maximum); \
	prefix##_set(&v, 1); \
	CHECK(prefix##_dec_if_positive(&v) == 0); \
	CHECK(prefix##_read(&v) == 0); \
	CHECK(prefix##_dec_if_positive(&v) == -1); \
	CHECK(prefix##_read(&v) == 0); \
} while (0)

static int __init mipad2_atomic_wrap_init(void)
{
	int i;

	for (i = 0; i < 1000; i++) {
		BOUNDARIES(atomic_t, atomic, S32_MIN, S32_MAX);
		BOUNDARIES(atomic64_t, atomic64, S64_MIN, S64_MAX);
	}
	pr_info("mipad2_atomic_wrap: PASS 1000 rounds of real 32/64-bit boundary and guard tests\n");
	return 0;
}

static void __exit mipad2_atomic_wrap_exit(void)
{
	pr_info("mipad2_atomic_wrap: unloaded; private counters only\n");
}

module_init(mipad2_atomic_wrap_init);
module_exit(mipad2_atomic_wrap_exit);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("Private-counter atomic wrapping regression, no hardware I/O");
