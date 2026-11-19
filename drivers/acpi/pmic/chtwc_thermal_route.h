/* SPDX-License-Identifier: GPL-2.0-only */
/* CHT thermal source ownership; no registration or hardware writes. */
#ifndef CHTWC_THERMAL_ROUTE_H
#define CHTWC_THERMAL_ROUTE_H

#include <linux/errno.h>
#include <linux/types.h>

enum chtwc_thermal_owner {
	CHTWC_THERMAL_SYS0 = 0,
	CHTWC_THERMAL_SYS1,
	CHTWC_THERMAL_SYS2,
	CHTWC_THERMAL_DIE,
	CHTWC_THERMAL_BAT0,
	CHTWC_THERMAL_BAT1,
	CHTWC_THERMAL_BATZONE,
	CHTWC_THERMAL_OWNERS,
};

/* Bank order: THRM0, THRM1, THRM2, THRM3. Level bit meanings are separate. */
static const u16 chtwc_thermal_status_regs[] = {0x6e04, 0x6e05, 0x6e06, 0x6ed9};
static const u16 chtwc_thermal_mask_regs[] = {0x6e0d, 0x6e12, 0x6e13, 0x6eda};

/*
 * Windows CHT d7a8: SYS0..2/die span THRM0, THRM1 and THRM3.
 * Windows d164: BAT0/BAT1 SHARE THRM1 bit4, plus separate THRM2 fields.
 * Android WC_THRMIRQ1/MTHRMIRQ1 and PMIC_INT_BZIRQ establish BATZONE bit7.
 * A shared source requires ALL recipients ready, not merely one of them.
 */
static const u8 chtwc_thermal_owner_sources[CHTWC_THERMAL_OWNERS][4] = {
	{0x11, 0x01, 0x00, 0x10},
	{0x22, 0x02, 0x00, 0x20},
	{0x44, 0x04, 0x00, 0x40},
	{0x08, 0x08, 0x00, 0x80},
	{0x00, 0x10, 0x41, 0x00},
	{0x00, 0x10, 0x82, 0x00},
	{0x00, 0x80, 0x00, 0x00},
};

struct chtwc_thermal_route {
	u8 acknowledge[4];
	u8 missing[4];
	u8 recipients;
};

/*
 * Pure planning: caller snapshots masked status and records delivery to EVERY
 * recipient BEFORE issuing any W1C. On any unowned enabled source, all planned
 * acknowledgements remain zero. This is not an atomic hardware snapshot or a
 * lifetime guarantee: the single owner must serialize registration/PM/masks.
 */
static inline int chtwc_thermal_plan(const u8 status[4], const u8 masks[4],
		unsigned int ready, struct chtwc_thermal_route *plan)
{
	struct chtwc_thermal_route result = {0};
	unsigned int bank, bit, owner, required, pending;
	bool missing = false;

	if (!status || !masks || !plan || ready & ~((1U << CHTWC_THERMAL_OWNERS) - 1))
		return -EINVAL;
	for (bank = 0; bank < 4; bank++) {
		pending = status[bank] & ~masks[bank];
		for (bit = 1; bit <= 0x80; bit <<= 1) {
			if (!(pending & bit))
				continue;
			required = 0;
			for (owner = 0; owner < CHTWC_THERMAL_OWNERS; owner++)
				if (chtwc_thermal_owner_sources[owner][bank] & bit)
					required |= 1U << owner;
			if (!required || (required & ready) != required) {
				result.missing[bank] |= bit;
				missing = true;
			} else {
				result.acknowledge[bank] |= bit;
				result.recipients |= required;
			}
		}
	}
	if (missing) {
		for (bank = 0; bank < 4; bank++)
			result.acknowledge[bank] = 0;
		result.recipients = 0;
	}
	*plan = result;
	return missing ? -ENXIO : 0;
}

/* Check documented sources enabled before parent IRQ activation. Reserved bits
 * are NOT assumed valid; actual unexpected asserted status is rejected above.
 */
static inline int chtwc_thermal_ownership_ready(const u8 masks[4],
		unsigned int ready)
{
	struct chtwc_thermal_route plan;
	u8 status[4] = {0};
	unsigned int bank, owner;

	for (bank = 0; bank < 4; bank++)
		for (owner = 0; owner < CHTWC_THERMAL_OWNERS; owner++)
			status[bank] |= chtwc_thermal_owner_sources[owner][bank];
	return chtwc_thermal_plan(status, masks, ready, &plan);
}

#endif
