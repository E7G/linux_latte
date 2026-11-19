#!/usr/bin/env python3
"""Check default release strictness and explicit ADC packaging gates."""
from pathlib import Path
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[3]
verifier = root/"scripts/mipad2_verify_daily_bundle.py"
checks = 0
with tempfile.TemporaryDirectory(prefix="chtwc-bundle-gates-") as name:
    tmp = Path(name)
    build = tmp/"build"
    (build/"include/config").mkdir(parents=True)
    config = "CONFIG_EROFS_FS=m\nCONFIG_NFT_NAT=m\nCONFIG_NFT_MASQ=m\n"
    (build/".config").write_text(config)
    release = build/"include/config/kernel.release"
    command = [sys.executable, str(verifier), "--build", str(build),
               "--modules", str(tmp/"modules"), "--output", str(tmp/"output"),
               "--commit", "test-only"]

    def expect(message, *extra):
        global checks
        q = subprocess.run(command + list(extra), capture_output=True, text=True, timeout=10)
        assert q.returncode != 0 and message in q.stderr, (q.returncode, q.stderr)
        assert not (tmp/"output").exists()
        checks += 1

    release.write_text("7.2.0-mipad2-integrated-adc1\n")
    expect("Unexpected release")  # Default daily3 contract remains strict.
    expect("ADC was not built as a module", "--flavor", "adc1")
    (build/".config").write_text(config + "CONFIG_IIO_CHT_WC_ADC=m\n")
    expect("Missing ADC module", "--flavor", "adc1")
    mod = tmp/"modules/lib/modules/7.2.0-mipad2-integrated-adc1/kernel"
    mod.mkdir(parents=True)
    (mod/"intel-chtwc-adc.ko").write_bytes(b"not-a-real-module")
    expect("Missing matching modules", "--flavor", "adc1")
    release.write_text("7.2.0-mipad2-integrated-daily3\n")
    expect("Missing matching modules")
    expect("Unexpected release", "--flavor", "adc1")
    expect("invalid choice", "--flavor", "anything")
    release.write_text("7.2.15-mipad2-integrated-adc2\n")
    expect("Unexpected release")
    expect("Unexpected release", "--flavor", "adc1")
    (build/".config").write_text(config)
    expect("ADC was not built as a module", "--flavor", "adc2")
    (build/".config").write_text(config + "CONFIG_IIO_CHT_WC_ADC=m\n")
    expect("Missing ADC module", "--flavor", "adc2")
    release.write_text("7.2.15-mipad2-integrated-pmic1\n")
    expect("Unexpected release")
    expect("Unexpected release", "--flavor", "adc1")
    expect("Unexpected release", "--flavor", "adc2")
    (build/".config").write_text(config)
    expect("ADC was not built as a module", "--flavor", "pmic1")
    (build/".config").write_text(config + "CONFIG_IIO_CHT_WC_ADC=m\n")
    expect("Missing ADC module", "--flavor", "pmic1")
    release.write_text("7.2.15-mipad2-integrated-lpat1\n")
    expect("Unexpected release")
    for old in ["adc1", "adc2", "pmic1"]:
        expect("Unexpected release", "--flavor", old)
    (build/".config").write_text(config)
    expect("ADC was not built as a module", "--flavor", "lpat1")
    (build/".config").write_text(config + "CONFIG_IIO_CHT_WC_ADC=m\n")
    expect("Missing ADC module", "--flavor", "lpat1")
    expect("Unexpected release", "--flavor", "lpat2")
    release.write_text("7.2.15-mipad2-integrated-lpat2\n")
    expect("Unexpected release", "--flavor", "lpat1")
    expect("Unexpected release")
    (build/".config").write_text(config)
    expect("ADC was not built as a module", "--flavor", "lpat2")
    (build/".config").write_text(config + "CONFIG_IIO_CHT_WC_ADC=m\n")
    expect("Missing ADC module", "--flavor", "lpat2")
    adc_config = config + "CONFIG_IIO_CHT_WC_ADC=m\n"
    for flavor, previous in (("lpat3", "lpat2"), ("lpat4", "lpat3"), ("lpat5", "lpat4")):
        candidate_release = f"7.2.15-mipad2-integrated-{flavor}"
        release.write_text(candidate_release + "\n")
        (build/".config").write_text(adc_config)
        expect("Unexpected release", "--flavor", previous)
        expect("Missing ADC module", "--flavor", flavor)
        candidate_modules = tmp / "modules/lib/modules" / candidate_release / "kernel"
        candidate_modules.mkdir(parents=True)
        (candidate_modules / "intel-chtwc-adc.ko").write_bytes(b"not-a-real-module")
        expect("Board thermal driver was not built as a module", "--flavor", flavor)
        (build/".config").write_text(adc_config + "CONFIG_INTEL_CHTWC_THERMAL=m\n")
        expect("Missing board thermal module", "--flavor", flavor)
        (candidate_modules / "intel_pmic_chtwc_thermal.ko.zst").write_bytes(b"not-a-real-module")
        expect("Missing matching modules", "--flavor", flavor)
print(f"PASS {checks} bundle flavor/release/module gates (not signature or hardware qualification)")
