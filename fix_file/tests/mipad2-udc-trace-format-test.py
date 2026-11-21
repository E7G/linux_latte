#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Verify the real kernel preprocessor output for the UDC endpoint event."""

from pathlib import Path
import re
import sys


def validate(text):
    # The event's text shown in tracefs is read by userspace decoders.
    metadata = re.search(r"print_fmt_udc_log_ep\[\]\s*=([^;]*);", text)
    if not metadata or not re.search(r',\s*REC->ret"\s*$', metadata[1]):
        raise ValueError("UDC endpoint format does not describe the recorded return value")

    # The ftrace pretty-printer has its own local `ret` (TRACE_TYPE_*).
    # Check the actual invocation after macro substitution, not its signature.
    printer = re.search(
        r"trace_raw_output_udc_log_ep\s*\([^)]*\)\s*\{(.*?)return trace_handle_return",
        text, re.DOTALL,
    )
    if not printer or not re.search(
        r'trace_event_printf\(iter,\s*"%s: mps .*?'
        r'\? "enabled" : "disabled",\s*field->ret\s*\);',
        printer[1], re.DOTALL,
    ):
        raise ValueError("UDC endpoint text printer does not use the recorded return value")


if __name__ == "__main__":
    try:
        validate(Path(sys.argv[1]).read_text())
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    print("UDC endpoint metadata and printer use the actual return value")
