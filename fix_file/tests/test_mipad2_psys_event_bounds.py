# SPDX-License-Identifier: GPL-2.0
"""Compile real PSYS decoder/ISR bodies with ASan/UBSan and stubbed devices.

This is a host-side memory-safety regression, not camera or firmware qualification.
The vulnerable negative control is reconstructed in memory by removing only the
PSYS bounds/recovery patch. No kernel source is edited and no device is opened.
"""
from pathlib import Path
import argparse
import hashlib
import json
import os
import re
import subprocess
import tempfile


def need(value, message):
    if not value:
        raise RuntimeError(message)


def take(text, marker, end):
    start = text.index(marker)
    return text[start:text.index(end, start) + len(end)]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def vulnerable_controls(css, compat):
    helper = take(css, 'static bool ia_css_is_valid_psys_event(', '\n}\n')
    need(css.count(helper + '\n') == 1, 'Unique bounds helper required')
    old = css.replace(helper + '\n', '')
    for indent in ['\t', '\t\t']:
        guard = (indent + 'if (!ia_css_is_valid_psys_event(payload[0])) {\n' +
                 indent + '\tIA_CSS_ERROR("Invalid PSYS event type %u", payload[0]);\n' +
                 indent + '\treturn -EPROTO;\n' + indent + '}\n')
        need(old.count(guard) == 1, 'Unique bounds check required at each lookup')
        old = old.replace(guard, '')
    current = take(compat, 'int atomisp_css_isr_thread(', '\n}\n')
    old_caller = current.replace('struct atomisp_css_event current_event;\n\tint ret;',
                                 'struct atomisp_css_event current_event;')
    old_caller = old_caller.replace(
        'while (!(ret = ia_css_dequeue_psys_event(&current_event.event))) {',
        'while (!ia_css_dequeue_psys_event(&current_event.event)) {')
    recovery = ('\n\tif (ret == -EPROTO) {\n'
                '\t\tdev_err(isp->dev, "ISP returned an invalid PSYS event type\\n");\n'
                '\t\tqueue_work(system_long_wq, &isp->assert_recovery_work);\n'
                '\t\treturn ret;\n\t}\n')
    need(old_caller.count(recovery) == 1, 'Explicit protocol recovery required')
    return old, compat.replace(current, old_caller.replace(recovery, ''))


def run(source, output, compiler, baseline_ref=None):
    source = source.resolve(strict=True)
    need(not output.exists(), 'Use a new output directory; existing evidence is never overwritten')
    output.mkdir(parents=False)
    prefix = source / 'drivers/staging/media/atomisp/pci'
    css = (prefix / 'sh_css.c').read_text()
    compat = (prefix / 'atomisp_compat_css20.c').read_text()
    before = {str(p): digest(p) for p in [prefix / 'sh_css.c', prefix / 'atomisp_compat_css20.c']}
    old_css, old_compat = vulnerable_controls(css, compat)
    if baseline_ref:
        env = dict(os.environ, GIT_NO_LAZY_FETCH='1')
        for name, old in [('sh_css.c', old_css), ('atomisp_compat_css20.c', old_compat)]:
            p = subprocess.run(['git', '-c', 'gc.auto=0', '-c', 'maintenance.auto=false',
                                '-C', str(source), 'show', baseline_ref + ':' +
                                'drivers/staging/media/atomisp/pci/' + name],
                               capture_output=True, text=True, env=env, timeout=30)
            need(p.returncode == 0 and p.stdout == old, 'Negative control differs from explicit baseline: ' + name)
    public = (prefix / 'ia_css_event_public.h').read_text()
    internal = (prefix / 'sh_css_internal.h').read_text()
    warnings = []
    for path in prefix.rglob('*.h'):
        text = path.read_text()
        if re.search(r'enum ia_css_fw_warning\s*\{', text):
            warnings.append(take(text, 'enum ia_css_fw_warning', '\n};'))
    need(len(warnings) == 1, 'Unique real firmware-warning enum required')
    parts = {
        'SP_ENUM': take(internal, 'enum sh_css_sp_event_type {', '\n};'),
        'HOST_ENUM': take(public, 'enum ia_css_event_type {', '\n};'),
        'WARNING_ENUM': warnings[0],
        'EVENT_STRUCT': take(public, 'struct ia_css_event {', '\n};'),
        'EVENT_DECODE': take((prefix / 'runtime/event/src/event.c').read_text(), 'void ia_css_event_decode(', '\n}\n'),
        'TABLE': take(css, 'static enum ia_css_event_type convert_event_sp_to_host_domain[] = {', '\n};'),
        'HELPER': take(css, 'static bool ia_css_is_valid_psys_event(', '\n}\n'),
        'DEQUEUE_BASELINE': take(old_css, 'int\nia_css_dequeue_psys_event(', '\n}\n').replace('ia_css_dequeue_psys_event(', 'baseline_dequeue('),
        'DEQUEUE_CANDIDATE': take(css, 'int\nia_css_dequeue_psys_event(', '\n}\n').replace('ia_css_dequeue_psys_event(', 'candidate_dequeue('),
        'CALLER_BASELINE': take(old_compat, 'int atomisp_css_isr_thread(', '\n}\n').replace('atomisp_css_isr_thread(', 'baseline_isr('),
        'CALLER_CANDIDATE': take(compat, 'int atomisp_css_isr_thread(', '\n}\n').replace('atomisp_css_isr_thread(', 'candidate_isr('),
    }
    fixture = Path(__file__).with_name('mipad2_psys_event_bounds_fixture.c.in').read_text()
    for name, text in parts.items():
        need(fixture.count('@' + name + '@') == 1, 'Unique fixture placeholder required')
        fixture = fixture.replace('@' + name + '@', text)
    need(not re.search(r'@[A-Z_]+@', fixture), 'Unexpanded fixture placeholder')
    cfile = output / 'actual-functions.c'
    cfile.write_text(fixture)
    executable = output / 'actual-functions'
    args = [compiler, '-std=gnu11', '-g', '-O1', '-Wall', '-Wextra', '-Werror',
            '-Wno-unused-parameter', '-fsanitize=address,undefined,bounds',
            '-fno-sanitize-recover=all', '-fno-omit-frame-pointer', str(cfile), '-o', str(executable)]
    (output / 'compiler-command.json').write_text(json.dumps(args, indent=2) + '\n')
    p = subprocess.run(args, capture_output=True, text=True, timeout=90)
    (output / 'compile.log').write_text(p.stdout + p.stderr)
    need(p.returncode == 0, p.stderr[-4000:])
    env = dict(os.environ, ASAN_OPTIONS='detect_leaks=1:halt_on_error=1',
               UBSAN_OPTIONS='halt_on_error=1:print_stacktrace=1')
    p = subprocess.run([str(executable)], capture_output=True, text=True, env=env, timeout=90)
    (output / 'positive.stdout').write_text(p.stdout)
    (output / 'positive.stderr').write_text(p.stderr)
    need(p.returncode == 0, p.stderr[-4000:])
    matrix = json.loads(p.stdout)
    need(matrix['invalid_first_rejected'] == matrix['invalid_second_TIMER_rejected'] == 240,
         'Both complete invalid-u8 event domains must be tested')
    need(matrix['FW_ASSERT_line_module_equivalence_cases'] == 131072 and matrix['sanitizer_matrix_pass'],
         'Full line-number matrix for module0/module255 required')
    negative = []
    for mode in ['old-first-oob', 'old-second-oob']:
        p = subprocess.run([str(executable), mode], capture_output=True, text=True, env=env, timeout=30)
        (output / (mode + '.stderr')).write_text(p.stderr)
        need(p.returncode != 0 and re.search(r'out of bounds|global-buffer-overflow', p.stderr),
             'Vulnerable control did not reproduce a sanitizer OOB: ' + mode)
        negative.append(dict(mode=mode, exit_code=p.returncode,
                             stderr_sha256=digest(output / (mode + '.stderr'))))
    need(all(digest(Path(n)) == value for n, value in before.items()), 'Test changed kernel sources')
    result = dict(state='PSYS-real-functions-ASAN-UBSAN-pass', matrix=matrix,
                  source_sha256=before, fixture_sha256=digest(cfile), ELF_sha256=digest(executable),
                  negative_controls=negative, device_dependencies_stubbed=True,
                  hardware_or_firmware_root_cause_proven=False, output=str(output))
    (output / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-tree', type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument('--output', type=Path)
    parser.add_argument('--compiler', default='clang')
    parser.add_argument('--baseline-ref', help='Optional local Git ref: verify the in-memory rollback is byte-exact; no lazy fetch')
    args = parser.parse_args()
    output = args.output.resolve() if args.output else Path(tempfile.mkdtemp(prefix='mipad2-psys-parent-')) / 'run'
    print(json.dumps(run(args.source_tree, output, args.compiler, args.baseline_ref), indent=2))
