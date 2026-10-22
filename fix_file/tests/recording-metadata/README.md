# Strict recording metadata arrival analysis

Run `python3 -m unittest -v` and `python3 -O -m unittest -v` here: 45 tests.

Input is decoded control-call intervals and exact encoder-input PTS/offset keys selected within qualified nonempty EOS epochs. Raw traces, ownership tables and pixels are not published. No frame fitting, trimming or assumed synchronous source/encoder call. Queue sink-arrival to worker-begin includes blocked enqueue, not isolated residence. See ../../MIPAD2_R17H_CURRENT_CAPS_DEVICE.md.
