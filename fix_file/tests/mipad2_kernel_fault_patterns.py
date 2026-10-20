"""Lexical severity markers: do not count the suffix of 'debug:' as a BUG."""
import re

FAULT_PATTERNS = {
    'BUG': r'(?<!\w)(?:BUG:|kernel BUG at\b|kernel BUG!)',
    'WARNING': r'(?<!\w)WARNING:',
    'Oops': r'(?<!\w)Oops:',
    'GPU HANG': r'(?<!\w)GPU HANG\b',
}

def count_faults(text):
    return {name: len(re.findall(pattern, text, re.I))
            for name, pattern in FAULT_PATTERNS.items()}
