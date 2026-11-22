#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
"""Compile the actual Cherryview Mi Pad 2 match filter against fake resources."""
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SOURCE = (ROOT / "drivers/pinctrl/intel/pinctrl-cherryview.c").read_text()
MATCH = re.search(r"static bool chv_mipad2_vgpio_matches[\s\S]+?\n}\n", SOURCE)[0]
DMI = re.search(r"static const struct dmi_system_id chv_mipad2\[\] = \{[\s\S]+?\n};\n", SOURCE)[0]

SHIM = r"""
#include <stdbool.h>
#include <string.h>
#include <assert.h>

#define ARRAY_SIZE(a) (sizeof(a)/sizeof((a)[0]))
#define DMI_SYS_VENDOR 0
#define DMI_PRODUCT_NAME 1
#define DMI_EXACT_MATCH(field, value) { field, value }
struct dmi_system_id { struct { int index; const char *value; } matches[2]; };
struct acpi_device { const char *uid; };
struct device { struct acpi_device *acpi; };
struct resource { unsigned long start, end; };
struct platform_device { struct device dev; struct resource *mem; };

#define ACPI_COMPANION(d) ((d)->acpi)
#define IORESOURCE_MEM 1
static const char *system_dmi[] = { "Xiaomi Inc", "Mipad2" };
static bool mipad2_vgpio;
static const struct { const char *uid; } mipad2_virtual_soc_data = { "5" };
static int mem_reads;
static bool acpi_dev_uid_match(struct acpi_device *adev, const char *uid)
{
    return adev->uid && !strcmp(adev->uid, uid);
}
static bool dmi_check_system(const struct dmi_system_id *id)
{
    for (unsigned int i = 0; i < ARRAY_SIZE(id->matches); i++)
        if (strcmp(system_dmi[id->matches[i].index], id->matches[i].value))
            return false;
    return true;
}
static struct resource *platform_get_resource(struct platform_device *p, int type, int index)
{
    assert(type == IORESOURCE_MEM && index == 0);
    mem_reads++;
    return p->mem;
}
static unsigned long resource_size(const struct resource *r)
{
    return r->end - r->start + 1;
}
"""
RUN = r"""
static void test_match(struct platform_device *p, bool expected, int reads)
{
    mem_reads = 0;
    assert(chv_mipad2_vgpio_matches(p) == expected);
    assert(mem_reads == reads);
}
int main(void)
{
    struct resource good = { 0xfeda0000, 0xfeda7fff };
    struct acpi_device a = { "5" };
    struct platform_device p = { { &a }, &good };
    test_match(&p, false, 0);
    mipad2_vgpio = true;
    test_match(&p, true, 1);
    for (const char **uid = (const char *[]){"1", "2", "3", "4", "6", "05", "", 0};
         *uid; uid++) {
        a.uid = *uid;
        test_match(&p, false, 0);
    }
    a.uid = 0;
    test_match(&p, false, 0);
    p.dev.acpi = 0;
    test_match(&p, false, 0);
    p.dev.acpi = &a;
    a.uid = "5";
    system_dmi[0] = "Not Xiaomi Inc";
    test_match(&p, false, 0);
    system_dmi[0] = "Xiaomi Inc";
    system_dmi[1] = "Mipad20";
    test_match(&p, false, 0);
    system_dmi[1] = "Mipad2";
    p.mem = 0;
    test_match(&p, false, 1);
    p.mem = &good;
    good.end--;
    test_match(&p, false, 1);
    good.start++;
    good.end += 2;
    test_match(&p, false, 1);
    good.start--;
    good.end--;
    test_match(&p, true, 1);
}
"""


class VirtualBankSafety(unittest.TestCase):
    def test_hardware_filter(self):
        with tempfile.TemporaryDirectory(prefix="mipad2-vgpio-") as temp:
            p = Path(temp)
            (p / "test.c").write_text(SHIM + DMI + MATCH + RUN)
            subprocess.run(["cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
                            "test.c", "-o", "test"], cwd=p, check=True)
            subprocess.run([str(p / "test")], cwd=p, check=True)

    def test_new_bank_is_not_in_the_regular_acpi_uid_table(self):
        ids = SOURCE.split("*chv_soc_data[] = {", 1)[1].split("};", 1)[0]
        self.assertNotIn("mipad2_virtual_soc_data", ids)
        self.assertIn("static bool mipad2_vgpio;\nmodule_param(mipad2_vgpio, bool, 0444);", SOURCE)
        self.assertIn("CHV_COMMUNITY(mipad2_virtual_gpps, 16, 0)", SOURCE)

    def test_busy_parent_rejected_before_gpio_irq_registration(self):
        probe = SOURCE.split("static int chv_pinctrl_probe(", 1)[1].split("\n}\n", 1)[0]
        guard = probe.index("soc_data == &mipad2_virtual_soc_data && irq_has_action(irq)")
        self.assertLess(guard, probe.index("chv_gpio_probe(pctrl, irq)"))
        self.assertIn("return dev_err_probe(dev, -EBUSY", probe[guard:])
        self.assertIn("if (community->acpi_space_id) {", probe)


if __name__ == "__main__":
    unittest.main(verbosity=2)
