#!/usr/bin/env python3
"""Audit actual Mi Pad 2 7.2 modules from the release defconfig."""

import argparse
import json
from pathlib import Path
import re
import subprocess
import tempfile

from mipad2_verify_daily_bundle import sha, signed_parts


RELEASE = re.compile(r"7\.2\.[0-9]+-mipad2-integrated-[a-zA-Z0-9._-]+")
REQUIRED = (
    "drivers/iio/adc/intel-chtwc-adc",
    "drivers/acpi/pmic/intel_pmic_chtwc_thermal",
    "fs/erofs/erofs",
    "net/netfilter/nft_nat",
    "net/netfilter/nft_masq",
    "net/netfilter/nft_chain_nat",
)


def verify_modules(root, cert, release):
    """Verify staged bytes against the public certificate and the full ABI."""
    if not RELEASE.fullmatch(release) or root.name != release:
        raise ValueError(f"Unexpected 7.2 release and module root: {release}, {root}")
    kernel = root / "kernel"
    if not kernel.is_dir() or kernel.is_symlink():
        raise ValueError("Missing real kernel module directory")
    for path in kernel.rglob("*"):
        if path.is_symlink():
            raise ValueError(f"Unexpected symlink in module tree: {path}")
    required = tuple(kernel / (name + ".ko.zst") for name in REQUIRED)
    for path in required:
        if not path.is_file() or path.stat().st_size == 0:
            raise ValueError(f"Missing required release module: {path.relative_to(root)}")

    paths = sorted(path for path in kernel.rglob("*")
                   if path.is_file() and re.search(r"\.ko(?:\.[^.]+)?$", path.name))
    verified = {}
    negative = False

    with tempfile.TemporaryDirectory(prefix="mipad2-release-modules-") as name:
        scratch = Path(name)
        pem = scratch / "cert.pem"
        payload_file = scratch / "payload"
        signature_file = scratch / "signature"
        subprocess.run(
            ["openssl", "x509", "-inform", "DER", "-in", cert, "-out", pem], check=True,
        )
        command = [
            "openssl", "cms", "-verify", "-binary", "-inform", "DER",
            "-in", signature_file, "-content", payload_file, "-certfile", pem,
            "-nointern", "-noverify", "-out", "/dev/null",
        ]
        for path in paths:
            if not path.name.endswith(".ko.zst"):
                raise ValueError(f"Unexpected module format: {path.relative_to(root)}")
            vermagic = subprocess.check_output(
                ["modinfo", "-F", "vermagic", path], text=True,
            ).split(maxsplit=1)
            if not vermagic or vermagic[0] != release:
                raise ValueError(f"Wrong vermagic: {path.relative_to(root)}")

            data = subprocess.check_output(["zstd", "-dc", path])
            payload, signature = signed_parts(data)
            if not payload:
                raise ValueError(f"Empty signed module: {path.relative_to(root)}")
            payload_file.write_bytes(payload)
            signature_file.write_bytes(signature)
            result = subprocess.run(command, capture_output=True)
            if result.returncode:
                raise ValueError(f"CMS verification failed: {path.relative_to(root)}")
            if not negative:
                damaged = bytearray(payload)
                damaged[-1] ^= 1
                payload_file.write_bytes(damaged)
                if subprocess.run(command, capture_output=True).returncode == 0:
                    raise ValueError("Tampered module was accepted")
                negative = True
            verified[str(path.relative_to(root))] = sha(path)

    return {
        "kernelrelease": release,
        "module_certificate_sha256": sha(cert),
        "modules_verified": len(verified),
        "module_sha256": verified,
        "signature_negative_control_passed": negative,
        "hardware_boot_verified": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("modules", type=Path)
    parser.add_argument("certificate", type=Path)
    parser.add_argument("kernelrelease")
    args = parser.parse_args()
    try:
        result = verify_modules(args.modules, args.certificate, args.kernelrelease)
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"release module verification failed: {error}\n")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
