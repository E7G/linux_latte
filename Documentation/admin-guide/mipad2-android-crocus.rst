Mi Pad 2: Droidloom Android graphics
===================================

Scope
-----

This is a Mi Pad 2 Cherryview-specific integration, not an Android emulator
or a claim of universal application compatibility. The host remains Linux;
Android uses its own Bionic userspace and the host i915 render node.

Kernel prerequisites
--------------------

The 7.2 daily2 build retains the existing tablet drivers and adds signed,
demand-loaded ``nft_chain_nat`` and ``nft_masq`` modules. Droidloom requires
these in addition to Binder, namespaces, cgroups, seccomp, veth and EROFS.
The ruleset can be checked in a private network namespace without changing
the host's firewall. This configuration change is not a general freeze fix.

Why Iris failed
---------------

The pinned Mesa 26.1.7 source explicitly rejects ``INTEL_PLATFORM_CHV`` in
``iris_bufmgr_get_for_fd()``. The Droidloom image used here contains Iris
but not the Crocus implementation needed by Cherryview. Rendering therefore
fails with ``EGL_NOT_INITIALIZED`` and SurfaceFlinger repeatedly aborts with
``no suitable EGLConfig``. Renaming a DRI stub cannot add a missing driver.

Build and deployment
---------------------

``.github/workflows/mipad2-android-mesa.yml`` builds Mesa 26.1.7 from its
SHA256-pinned official source archive. A native, source-matched ``mesa_clc``
is built first, followed by the Android NDK x86_64 API35 Crocus driver.
The target uses Android's ``libz.so``, not a Linux host library. The artifact
includes hashes, build metadata and the Mesa license. Host-only compiler
libraries must never be installed into Android.

On the tested package pair, ``android_file_overrides`` already contains a
``/vendor/lib64/libgallium_dri.so`` target sourced from the packaged runtime.
Replace only that override's source with a verified, versioned Crocus
``libgallium_dri.so``. Do not append a duplicate target. Preserve the complete
previous cell configuration and original packages. Stop the Android cell
before changing its library source; start again afterwards. A device reboot
is not needed for this userspace-only change. Never replace the host Mesa
or truncate a library mapped by a running process.

Verification
------------

The tested clean artifact was built by run 43417690893 from source commit
``f288a22efd637ae060acd8b5310fb81f45c32052``. Its Gallium SHA256 is
``33b8e0e9e39461eb4e3cfa583c596b21ccff6dff08619b21b995e6dca7cf3d4a``.
The following were observed on the tablet after an Android stop/start:

* Droidloom reports Android ready; ``sys.boot_completed`` is ``1``.
* SurfaceFlinger reports Intel CHV, OpenGL ES 3.2, Mesa 26.1.7.
* The package/application catalog responds and networking reaches the Internet.
* The reported ABIs are ``x86_64,arm64-v8a`` and the configured native bridge
  is ``libberberis_arm64.so``. This does not prove every ARM64 app works.
* The desktop was not restarted for the Android driver change.

User-facing application rendering, touch behavior, specific applications,
translation compatibility, suspend and extended daily use require separate
validation. The image does not advertise 32-bit application support.
Autostart is deliberately not enabled by this integration. Package updates
may regenerate cell configuration; recheck the single Gallium override and
hardware renderer after updating Droidloom rather than assuming persistence.
