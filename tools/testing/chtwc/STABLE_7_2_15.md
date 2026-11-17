# Linux 7.2.15 integration source gate

The cumulative upstream source update is pinned to:

- Source-reference base v7.2: `8d3ae59288f1e7d58d76558a6ee96d533bc5019f`.
- Stable v7.2.15 commit: `497791a0a96b866d90add64041c47acdff49cae6`.
- Annotated stable tag object: `5b4b7d230e9992c9791c0f235412e8347e0317cd`.
- Existing Mi Pad2 integration: `aa139eedac4812e79fea1c312fe5500103b50e80`.

The upstream comparison reports 5,935 commits after v7.2. Our original major
version upgrade was applied as a source patch, not an upstream ancestry merge.
This update likewise records the source references without rewriting history
or pretending that upstream commits were individual cherry-picks.

A three-way source merge used the explicit v7.2 reference. There were 4,469
upstream-only paths and 480 custom-only paths; their resulting identities match
the corresponding upstream and existing custom trees exactly. All other
unaffected paths remain unchanged. Thirty-nine paths changed on both sides.
The two actual insertion conflicts were resolved as follows:

- Keep Mi Pad2 Silvermont/Airmont tuning **and** the upstream Rust APX gate.
- Keep the upstream Marvell AHCI interrupt handler **and** the existing
  `int`-returning NVMe-remap handoff, including caller error propagation.

`test-stable-integration.py` checks these two reviewed file identities, source
version, and negative controls. CI also compiles AHCI separately with Clang,
runs the actual ADC protocol tests with GCC/Clang sanitizers, and builds the
full Mi Pad2 image and matching cryptographically verified signed modules.

Source checks and compilation do not establish successful boot, calibrated
temperatures, thermal policy, daily-use reliability or a hang fix. ADC1 raw
acquisition qualification on 7.2.0 does not qualify a 7.2.15 image. New hardware
qualification remains required; existing fallback images and defaults must be
retained. No standalone thermal OpRegion or fabricated temperature is enabled.
